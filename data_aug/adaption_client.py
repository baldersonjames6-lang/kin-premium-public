"""Minimal Adaption REST client (stdlib only). Never prints or writes the API key."""
from __future__ import annotations
import json, os, urllib.request, urllib.error
from pathlib import Path

BASE = "https://api.prod.adaptionlabs.ai/api/v1"


def _key() -> str:
    env = Path(os.environ.get("KIN_ENV", "~/42-workspace/experiments/apart-swarm-2026/.env")).expanduser()
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("ADAPTION_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("ADAPTION_API_KEY not found in KIN_ENV file")


def call(method: str, path: str, body: dict | None = None, timeout: int = 180) -> tuple[int, dict]:
    req = urllib.request.Request(BASE + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + _key(),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")[:500]
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, {"raw": txt}


def respond(model: str, instructions: str, user: str, temperature: float = 0.9,
            max_output_tokens: int = 2000) -> dict:
    status, data = call("POST", "/responses", {"model": model, "instructions": instructions,
                                               "input": user, "temperature": temperature,
                                               "max_output_tokens": max_output_tokens, "store": False})
    if status != 200:
        raise RuntimeError(f"responses.create HTTP {status}: {str(data)[:300]}")
    return data
