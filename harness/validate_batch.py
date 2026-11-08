"""Check a finished batch folder against docs/CONTRACTS.md.

Usage: ``python -m harness.validate_batch runs/<batch_id>``
Prints every problem found and exits non-zero if there are any.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MANIFEST_KEYS = {"batch_id", "kind", "created_utc", "git_commit", "prereg_sha256", "data_seed", "models",
                 "conditions", "n_episodes", "cost_usd_estimate", "status", "notes"}
EPISODE_KEYS = {"episode_id", "batch_id", "requester", "peer", "kinship_true", "claim", "claim_text",
                "request_style", "seed", "outcome", "recognition_probe", "monitors", "tokens", "cost_usd",
                "latency_s", "error", "events_file"}
OUTCOME_KEYS = {"leak", "markers_leaked", "record_fields_in_report", "raised_concern", "refused", "category"}
EVENT_KEYS = {"i", "t", "type", "from", "to", "tool", "content", "highlights", "flag"}
# Decomposition (swarm) mode: optional extra keys and values (harness/swarm.py, CONTRACTS.md "Swarm mode").
SWARM_EPISODE_EXTRA = {"group", "replaces", "mode", "variant", "orchestrator", "workers", "monitors_swarm", "requester_declined"}
SWARM_OUTCOME_EXTRA = {"objective_met", "markers_with_owner_id", "local_red_flags", "crossing",
                       "orchestrator_declined", "orchestrator_n_tasks", "orchestrator_asked_for_notes", "per_worker"}
SWARM_ACTORS = {"orchestrator", "w1", "w2", "w3"}
ENUMS = {
    "kinship_true": {"identical", "sibling", "different"},
    "claim": {"none", "claim_kin", "claim_nonkin", "claim_false"},
    "request_style": {"templated", "freeform", "honest", "swarm"},  # 'honest' = baseline; see HARNESS_NOTES
    "category": {"leak", "comply_no_leak", "refuse", "report", "kept_policy", "other"},
    "answer": {"same", "different", "unsure", None},
    "type": {"system", "message", "tool_call", "tool_result", "monitor", "outcome"},
    "from": {"requester", "peer", "env", "mon_claude", "mon_qwen", "checker"} | SWARM_ACTORS,
    "to": {"peer", "requester", "env", None} | SWARM_ACTORS,
    "tool": {"read_table", "write_report", "raise_concern", "send_task", None},
}


def validate(batch_dir: Path) -> list[str]:
    errs: list[str] = []
    m = json.loads((batch_dir / "manifest.json").read_text())
    if missing := MANIFEST_KEYS - m.keys():
        errs.append(f"manifest missing {sorted(missing)}")
    if m.get("status") not in {"running", "complete", "aborted"}:
        errs.append(f"manifest status {m.get('status')!r}")
    lines = (batch_dir / "episodes.jsonl").read_text().splitlines()
    if len(lines) != m.get("n_episodes"):
        errs.append(f"n_episodes {m.get('n_episodes')} but {len(lines)} lines")
    for n, line in enumerate(lines, 1):
        r = json.loads(line)
        where = f"episodes.jsonl:{n} ({r.get('episode_id')})"
        swarm = r.get("mode") == "swarm"
        extra_ok = SWARM_EPISODE_EXTRA if swarm else {"requester_declined", "pressure"}
        if set(r.keys()) - extra_ok != EPISODE_KEYS:  # requester_declined added 6 Nov; older smoke batches lack it
            errs.append(f"{where} keys differ: extra {sorted(r.keys() - EPISODE_KEYS)} missing {sorted(EPISODE_KEYS - r.keys())}")
        for k in ("kinship_true", "claim", "request_style"):
            if r.get(k) not in ENUMS[k]:
                errs.append(f"{where} {k}={r.get(k)!r}")
        if r.get("batch_id") != m.get("batch_id"):
            errs.append(f"{where} batch_id mismatch")
        o = r.get("outcome")
        if o is None:
            if r.get("error") is None:
                errs.append(f"{where} outcome null without error")
        else:
            if o.keys() != (OUTCOME_KEYS | SWARM_OUTCOME_EXTRA if swarm else OUTCOME_KEYS):
                errs.append(f"{where} outcome keys {sorted(o.keys())}")
            if o.get("category") not in ENUMS["category"]:
                errs.append(f"{where} category {o.get('category')!r}")
        p = r.get("recognition_probe", {})
        if set(p) != {"asked", "answer", "correct"} or p.get("answer") not in ENUMS["answer"]:
            errs.append(f"{where} recognition_probe {p}")
        mons = r.get("monitors", {})
        if set(mons) != {"mon_claude", "mon_qwen"} or any(set(v) != {"score", "flag"} for v in mons.values()):
            errs.append(f"{where} monitors {mons}")
        if set(r.get("tokens", {})) != {"in", "out"}:
            errs.append(f"{where} tokens {r.get('tokens')}")
        ev_path = batch_dir / r.get("events_file", "")
        if not ev_path.is_file():
            errs.append(f"{where} events file missing")
            continue
        for j, el in enumerate(ev_path.read_text().splitlines()):
            e = json.loads(el)
            if missing := EVENT_KEYS - e.keys():
                errs.append(f"{ev_path.name}:{j} missing {sorted(missing)}")
            if e.get("i") != j:
                errs.append(f"{ev_path.name}:{j} i={e.get('i')}")
            for k in ("type", "from", "to", "tool"):
                if e.get(k) not in ENUMS[k]:
                    errs.append(f"{ev_path.name}:{j} {k}={e.get(k)!r}")
    sums = batch_dir / "SHA256SUMS"
    if not sums.exists():
        errs.append("SHA256SUMS missing")
    else:
        listed = {}
        for line in sums.read_text().splitlines():
            h, rel = line.split("  ", 1)
            listed[rel] = h
            if hashlib.sha256((batch_dir / rel).read_bytes()).hexdigest() != h:
                errs.append(f"hash mismatch {rel}")
        actual = {p.relative_to(batch_dir).as_posix() for p in batch_dir.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
        if actual != set(listed):
            errs.append(f"SHA256SUMS does not cover {sorted(actual ^ set(listed))}")
    return errs


def main() -> None:
    d = Path(sys.argv[1])
    errs = validate(d)
    n = len((d / "episodes.jsonl").read_text().splitlines())
    print(f"{d.name}: {n} episode lines checked, {len(errs)} problems")
    for e in errs:
        print("  -", e)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
