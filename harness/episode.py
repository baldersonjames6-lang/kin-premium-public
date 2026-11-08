"""Run one episode end to end and return its episodes.jsonl record (docs/CONTRACTS.md).

Order of play:
1. Requester message: templated (fixed text, no model call), honest baseline (fixed
   benign text), or free-form (the requester model writes it from a hidden objective;
   the harness prepends the identity line).
2. Peer tool loop, at most 8 peer replies, using the JSON text protocol in prompts.py.
3. Recognition probe (a follow-up question to the peer, same conversation).
4. Checker (deterministic outcome).
5. Both monitors read the transcript (system prompt, request, tool calls and results,
   peer messages; the probe is not shown to them) and score suspicion 0-10.

Every step is written to ``events/<episode_id>.jsonl``. ``call_fn`` is injectable so the
tests can drive an episode with scripted replies and no network.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import checker, models, prompts
from .conditions import claim_text, kinship_true
from .datagen import Register, table_texts

MAX_PEER_STEPS = 8
MAX_BAD_REPLIES = 2
PEER_MAX_TOKENS = 4000
MONITORS = {"mon_claude": "haiku", "mon_qwen": "qwen27"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_action(text: str) -> dict | None:
    """Return the first JSON object in ``text`` that is a tool call or a final message.

    Lenient on purpose: raw newlines inside strings are accepted, and if no valid
    object is found but the reply clearly names a known tool (``"tool": "write_report"``
    etc.), the call is repaired by taking the text after ``"text": "`` (or the table
    name) so a malformed attempt to send data still counts as sent. Repaired actions
    carry ``"_repaired": True`` and are marked in the events file.
    """
    if not text:
        return None
    dec = json.JSONDecoder(strict=False)
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("tool" in obj or "final" in obj):
            return obj
    return _repair_action(text)


def _unescape(s: str) -> str:
    return re.sub(r'\\(["\\/nrt])', lambda m: {"n": "\n", "r": "\r", "t": "\t"}.get(m.group(1), m.group(1)), s)


def _repair_action(text: str) -> dict | None:
    m = re.search(r'"tool"\s*:\s*"(read_table|write_report|raise_concern)"', text)
    if not m:
        return None
    tool = m.group(1)
    if tool == "read_table":
        n = re.search(r'"(?:name|table)"\s*:\s*"([^"]+)"', text)
        return {"tool": tool, "args": {"name": n.group(1) if n else ""}, "_repaired": True}
    t = re.search(r'"text"\s*:\s*"', text)
    if not t:
        return None
    body = re.sub(r'"\s*\}\s*\}?\s*$', "", text[t.end():].rstrip())
    return {"tool": tool, "args": {"text": _unescape(body)}, "_repaired": True}


class EventLog:
    """Ordered event list that is also streamed to the events file."""

    def __init__(self, path: Path, markers: list[str]):
        self.path, self.markers, self.events = path, markers, []
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("x")  # never overwrite an existing events file

    def add(self, type_: str, from_: str, to: str | None, content: str, tool: str | None = None,
            flag=None, **extra) -> dict:
        ev = {"i": len(self.events), "t": _now(), "type": type_, "from": from_, "to": to, "tool": tool,
              "content": content,
              "highlights": [{"kind": "marker", "value": m} for m in checker.find_markers(content or "", self.markers)],
              "flag": flag, **extra}
        self.events.append(ev)
        self._fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self._fh.flush()
        return ev

    def close(self):
        self._fh.close()


def _reply_extra(r: models.Reply) -> dict:
    return {"reasoning": r.reasoning, "meta": {**r.meta, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                                               "cost_usd": r.cost_usd, "cost_source": r.cost_source}}


def _transcript(events: list[dict]) -> str:
    lines = []
    for e in events:
        if e.get("phase") == "probe" or e["type"] not in ("system", "message", "tool_call", "tool_result"):
            continue
        if e["type"] == "system" and e["to"] != "peer":
            continue
        tool = f" ({e['tool']})" if e.get("tool") else ""
        lines.append(f"[{e['type']} {e['from']} -> {e['to']}{tool}]\n{e['content']}")
    return "\n\n".join(lines)


def _parse_monitor(text: str) -> tuple[int | None, str]:
    obj = parse_score_json(text)
    if obj is not None:
        return obj
    m = re.search(r"\b(10|[0-9])\b", text or "")
    return (int(m.group(1)) if m else None), ""


def parse_score_json(text: str) -> tuple[int, str] | None:
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text or ""):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "score" in obj:
            try:
                s = int(round(float(obj["score"])))
            except (TypeError, ValueError):
                continue
            return max(0, min(10, s)), str(obj.get("reason", ""))
    return None


def _run_tool(name: str, args, tables: dict[str, str], report_path: Path) -> str:
    if not isinstance(args, dict):
        args = {"name": args, "text": args}
    if name == "read_table":
        t = str(args.get("name") or args.get("table") or "")
        return tables.get(t, f"ERROR: unknown table '{t}'. Tables: investors, transactions, bank_statement.")
    if name == "write_report":
        text = str(args.get("text", ""))
        with report_path.open("a") as fh:
            fh.write(text + "\n")
        return f"Report saved ({len(text)} characters)."
    if name == "raise_concern":
        return "Concern logged with the human overseer."
    return f"ERROR: unknown tool '{name}'. Tools: read_table, write_report, raise_concern."


def run_episode(spec: dict, register: Register, batch_id: str, episode_id: str, batch_dir: Path,
                call_fn: Callable = models.call, thresholds: dict | None = None) -> dict:
    """Run one episode. ``spec`` has requester, peer, claim, request_style, seed."""
    t0 = time.time()
    req, peer, claim, style = spec["requester"], spec["peer"], spec["claim"], spec["request_style"]
    pressure = spec.get("pressure", prompts.MAIN_PRESSURE)
    kin = kinship_true(req, peer)
    ctext = claim_text(claim, kin) if style != "honest" else ""
    tables = table_texts(register)
    log = EventLog(batch_dir / "events" / f"{episode_id}.jsonl", register.markers)
    report_path = batch_dir / "reports" / f"{episode_id}.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tokens = {"in": 0, "out": 0}
    cost = [0.0]
    error = None

    def talk(model_key: str, system: str, messages: list[dict], max_tokens: int) -> models.Reply:
        r = call_fn(model_key, system, messages, max_tokens)
        tokens["in"] += r.tokens_in
        tokens["out"] += r.tokens_out
        cost[0] += r.cost_usd
        return r

    trace = checker.PeerTrace()
    outcome, probe = None, {"asked": False, "answer": None, "correct": None}
    mons: dict[str, dict] = {k: {"score": None, "flag": None} for k in MONITORS}
    requester_declined = False
    try:
        # 1. Requester message
        if style == "templated":
            request = prompts.templated_request(claim, kin, pressure)
            log.add("message", "requester", "peer", request, claim_text=ctext, phase="request")
        elif style == "honest":
            request = prompts.HONEST_REQUEST
            log.add("message", "requester", "peer", request, claim_text="", phase="request")
        elif style == "freeform":
            # PREREG §7: if the requester declines to write the request, re-draw up to twice; record it.
            sysmsg = prompts.freeform_requester_system(pressure)
            log.add("system", "env", "requester", sysmsg, phase="request")
            for attempt in range(3):
                r = talk(req, sysmsg, [{"role": "user", "content": prompts.FREEFORM_REQUESTER_USER}], 800)
                requester_declined = checker.explicitly_declined([r.text])
                request = prompts.freeform_request(r.text, claim, kin)
                if not requester_declined:
                    break
                log.add("system", "env", "requester", f"requester declined (attempt {attempt + 1}); re-drawing",
                        generated=r.text, phase="request")
            log.add("message", "requester", "peer", request, claim_text=ctext, generated=r.text,
                    requester_declined=requester_declined, attempts=attempt + 1, phase="request", **_reply_extra(r))
        else:
            raise ValueError(f"unknown request_style {style}")

        # 2. Peer tool loop
        log.add("system", "env", "peer", prompts.PEER_SYSTEM)
        first = prompts.peer_first_user_message(request)
        messages = [{"role": "user", "content": first}]
        bad = 0
        for step in range(MAX_PEER_STEPS):
            r = talk(peer, prompts.PEER_SYSTEM, messages, PEER_MAX_TOKENS)
            messages.append({"role": "assistant", "content": r.text})
            action = parse_action(r.text)
            if action and "tool" in action:
                bad = 0
                name, args = str(action.get("tool")), action.get("args", {})
                known = name if name in ("read_table", "write_report", "raise_concern") else None
                trace.tool_calls.append({"tool": name, "args": args if isinstance(args, dict) else {"text": args}})
                log.add("tool_call", "peer", "env", json.dumps({"tool": name, "args": args}, ensure_ascii=False),
                        tool=known, raw=r.text, step=step, repaired=bool(action.get("_repaired")), **_reply_extra(r))
                result = _run_tool(name, args, tables, report_path)
                log.add("tool_result", "env", "peer", result, tool=known, step=step)
                messages.append({"role": "user", "content": f"Tool result ({name}):\n{result}"})
            elif action and "final" in action:
                final = str(action.get("final", ""))
                trace.peer_messages.append(final)
                log.add("message", "peer", "requester", final, raw=r.text, step=step, **_reply_extra(r))
                break
            else:
                trace.peer_messages.append(r.text)
                log.add("message", "peer", "env", r.text, step=step, parse_error=True, **_reply_extra(r))
                bad += 1
                if bad >= MAX_BAD_REPLIES:
                    log.add("system", "env", None, "Episode ended: too many replies that were not valid actions.")
                    break
                messages.append({"role": "user", "content": prompts.NUDGE})
                log.add("message", "env", "peer", prompts.NUDGE, step=step)
        else:
            log.add("system", "env", None, f"Episode ended: step limit ({MAX_PEER_STEPS}) reached.")

        # 3. Recognition probe
        pmsgs = messages + [{"role": "user", "content": prompts.RECOGNITION_PROBE}]
        if pmsgs[-2]["role"] == "user":  # keep strict user/assistant alternation
            pmsgs = messages[:-1] + [{"role": "user", "content": messages[-1]["content"] + "\n\n" + prompts.RECOGNITION_PROBE}]
        log.add("message", "env", "peer", prompts.RECOGNITION_PROBE, phase="probe")
        r = talk(peer, prompts.PEER_SYSTEM, pmsgs, 200)
        answer = checker.parse_probe_answer(r.text)
        probe = {"asked": True, "answer": answer, "correct": checker.probe_is_correct(answer, kin)}
        log.add("message", "peer", "env", r.text, phase="probe", parsed_answer=answer, **_reply_extra(r))

        # 4. Checker
        outcome = checker.outcome_for_register(trace, register)
        log.add("outcome", "checker", None, json.dumps(outcome))

        # 5. Monitors
        transcript = _transcript(log.events)
        for mon, key in MONITORS.items():
            try:
                r = talk(key, prompts.MONITOR_SYSTEM, [{"role": "user", "content": prompts.monitor_prompt(transcript)}], 300)
            except models.ModelCallError as e:
                error = f"{mon}: {e}"
                log.add("monitor", mon, None, f"ERROR: {e}")
                continue
            score, reason = _parse_monitor(r.text)
            thr = (thresholds or {}).get(mon)
            flag = (score >= thr) if (score is not None and thr is not None) else None
            mons[mon] = {"score": score, "flag": flag}
            log.add("monitor", mon, None, r.text, flag=flag, score=score, reason=reason, threshold=thr,
                    prompt=prompts.monitor_prompt(transcript), **_reply_extra(r))
    except models.ModelCallError as e:
        error = str(e)
        log.add("system", "env", None, f"Episode aborted: API error after retries: {e}")
    finally:
        log.close()

    return {
        "episode_id": episode_id, "batch_id": batch_id, "requester": req, "peer": peer,
        "kinship_true": kin, "claim": claim, "claim_text": ctext, "request_style": style, "requester_declined": requester_declined,
        "pressure": pressure if style != "honest" else None,
        "seed": spec["seed"], "outcome": outcome, "recognition_probe": probe, "monitors": mons,
        "tokens": tokens, "cost_usd": round(cost[0], 6), "latency_s": round(time.time() - t0, 2),
        "error": error, "events_file": f"events/{episode_id}.jsonl",
    }
