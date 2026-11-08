"""Thin chat clients for the Hugging Face router and Anthropic, with retries and cost accounting.

One entry point: ``call(model_key, system, messages, max_tokens)`` returns a ``Reply``.
``messages`` is a list of ``{"role": "user"|"assistant", "content": str}``.

- Keys are read from the .env file named by ``KIN_ENV`` and are never printed or logged.
- HF models are pinned to one provider (``:deepinfra``) so every call goes to the same
  backend; thinking is switched off with ``chat_template_kwargs.enable_thinking = False``.
- Anthropic: ``thinking`` is explicitly disabled. ``temperature`` is NOT sent for
  claude-haiku-5-5 because the API rejects it ("deprecated for this model").
- Up to 3 retries on timeouts, 429 and 5xx, with exponential back-off.
- Cost: the HF router's own ``usage.estimated_cost`` when present, otherwise the
  published per-token price below. ``cost_source`` says which was used.
"""
from __future__ import annotations

import json
import os
import random
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HF_URL = "https://router.huggingface.co/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
TEMPERATURE = 0.7
TIMEOUT_S = 180
MAX_RETRIES = 3

# USD per million tokens (input, output). HF: router /v1/models listing for the
# pinned provider (deepinfra), checked 2026-11-06. Anthropic: published list price,
# Haiku 5.5, prompts up to 100k tokens.
MODELS = {
    "qwen27": {"api": "hf", "id": "Qwen/Qwen3.5-27B", "provider": "deepinfra", "price": (0.26, 2.60)},
    "qwen9": {"api": "hf", "id": "Qwen/Qwen3.5-9B", "provider": "deepinfra", "price": (0.10, 0.15)},
    "dsv41": {"api": "hf", "id": "deepseek-ai/DeepSeek-V4.1-Flash", "provider": "deepinfra", "price": (0.20, 0.60)},
    # Added for PREREG v2.1 (6 Nov, after James asked for more DeepSeek and Qwen models). Prices from the
    # router listing for deepinfra, checked 2026-11-06 ~16:55 UTC.
    "qwen35a3b": {"api": "hf", "id": "Qwen/Qwen3.5-35B-A3B", "provider": "deepinfra", "price": (0.14, 1.00)},
    "dsv4pro": {"api": "hf", "id": "deepseek-ai/DeepSeek-V4-Pro", "provider": "deepinfra", "price": (1.30, 2.60)},
    "glm53f": {"api": "hf", "id": "zai-org/GLM-5.3-Flash", "provider": "deepinfra", "price": (0.15, 0.50)},
    "gemma31": {"api": "hf", "id": "google/gemma-4-31B-it", "provider": "deepinfra", "price": (0.20, 0.40)},
    "llama4s": {"api": "hf", "id": "meta-llama/Llama-4-Scout-17B-16E-Instruct", "provider": "novita", "price": (0.10, 0.30)},  # deepinfra returned 429/504 at 16:41; novita price not listed, deepinfra price used as estimate
    "kimi26": {"api": "hf", "id": "moonshotai/Kimi-K2.6", "provider": "deepinfra", "price": (0.75, 3.50)},
    "haiku": {"api": "anthropic", "id": "claude-haiku-5-5", "provider": "anthropic", "price": (0.10, 0.50)},
}


class ModelCallError(RuntimeError):
    """Raised after the retries are used up. The message never contains secrets."""


@dataclass
class Reply:
    text: str
    reasoning: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    cost_source: str
    meta: dict = field(default_factory=dict)  # provider, model_returned, response_id, latency_s, attempts


_ENV: dict[str, str] = {}


def _env() -> dict[str, str]:
    if not _ENV:
        path = Path(os.environ.get("KIN_ENV", "~/42-workspace/experiments/apart-swarm-2026/.env")).expanduser()
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                _ENV[k.strip()] = v.strip().strip('"').strip("'")
    return _ENV


def model_ids() -> dict[str, str]:
    return {k: v["id"] for k, v in MODELS.items()}


def _post(url: str, headers: dict, body: dict) -> tuple[dict, dict, int]:
    """POST with retries. Returns (json, response headers, attempts)."""
    data = json.dumps(body).encode()
    last = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return json.loads(r.read()), dict(r.headers), attempt + 1
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")
            last = f"HTTP {e.code}: {detail}"
            if e.code not in (408, 409, 425, 429) and e.code < 500:
                raise ModelCallError(last) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < MAX_RETRIES:
            time.sleep(2 ** (attempt + 1) + random.random())
    raise ModelCallError(f"failed after {MAX_RETRIES} retries: {last}")


def _price(key: str, tin: int, tout: int) -> float:
    pin, pout = MODELS[key]["price"]
    return (tin * pin + tout * pout) / 1e6


def _call_hf(key: str, system: str, messages: list[dict], max_tokens: int) -> Reply:
    m = MODELS[key]
    body = {"model": f"{m['id']}:{m['provider']}",
            "messages": [{"role": "system", "content": system}] + messages,
            "max_tokens": max_tokens, "temperature": TEMPERATURE,
            "chat_template_kwargs": {"enable_thinking": False}}
    headers = {"Authorization": "Bearer " + _env()["HF_TOKEN"], "Content-Type": "application/json"}
    t0 = time.time()
    d, h, attempts = _post(HF_URL, headers, body)
    msg = d["choices"][0]["message"]
    usage = d.get("usage") or {}
    tin, tout = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    if usage.get("estimated_cost") is not None:
        cost, src = float(usage["estimated_cost"]), "hf_router_estimated_cost"
    else:
        cost, src = _price(key, tin, tout), "price_table_estimate"
    return Reply(text=msg.get("content") or "", reasoning=msg.get("reasoning_content") or msg.get("reasoning"),
                 tokens_in=tin, tokens_out=tout, cost_usd=cost, cost_source=src,
                 meta={"provider": h.get("x-inference-provider") or h.get("X-Inference-Provider") or m["provider"],
                       "model_returned": d.get("model"), "response_id": d.get("id"),
                       "finish_reason": d["choices"][0].get("finish_reason"),
                       "latency_s": round(time.time() - t0, 2), "attempts": attempts})


def _call_anthropic(key: str, system: str, messages: list[dict], max_tokens: int) -> Reply:
    m = MODELS[key]
    body = {"model": m["id"], "system": system, "messages": messages, "max_tokens": max_tokens,
            "thinking": {"type": "disabled"}}
    headers = {"x-api-key": _env()["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    t0 = time.time()
    d, h, attempts = _post(ANTHROPIC_URL, headers, body)
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    thinking = "".join(b.get("thinking", "") for b in d.get("content", []) if b.get("type") == "thinking") or None
    usage = d.get("usage") or {}
    tin = int(usage.get("input_tokens") or 0) + int(usage.get("cache_read_input_tokens") or 0) \
        + int(usage.get("cache_creation_input_tokens") or 0)
    tout = int(usage.get("output_tokens") or 0)
    return Reply(text=text, reasoning=thinking, tokens_in=tin, tokens_out=tout,
                 cost_usd=_price(key, tin, tout), cost_source="price_table_estimate",
                 meta={"provider": "anthropic", "model_returned": d.get("model"), "response_id": d.get("id"),
                       "finish_reason": d.get("stop_reason"), "latency_s": round(time.time() - t0, 2),
                       "attempts": attempts})


def call(model_key: str, system: str, messages: list[dict], max_tokens: int = 2000) -> Reply:
    """Send one chat turn to ``model_key`` and return the reply."""
    if MODELS[model_key]["api"] == "hf":
        return _call_hf(model_key, system, messages, max_tokens)
    return _call_anthropic(model_key, system, messages, max_tokens)
