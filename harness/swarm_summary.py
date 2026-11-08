"""Print a feasibility summary of a swarm (decomposition) batch. Descriptive only: spike batches
are never analysed for hypotheses.

Usage: ``python -m harness.swarm_summary runs/<batch_id> [runs/<batch_id> ...]``
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

from .checker import WORKER_IDS, explicitly_declined


def load(batch_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (batch_dir / "episodes.jsonl").read_text().splitlines()]


def _rate(xs) -> str:
    xs = list(xs)
    return f"{sum(xs)}/{len(xs)}" + (f" ({100 * sum(xs) / len(xs):.0f}%)" if xs else "")


def orchestrator_text(batch_dir: Path, rec: dict) -> list[str]:
    evs = [json.loads(line) for line in (batch_dir / rec["events_file"]).read_text().splitlines()]
    return [e.get("raw") or e["content"] for e in evs if e.get("actor") == "orchestrator" and e["from"] == "orchestrator"]


def summarise(batch_dir: Path) -> None:
    recs = [r for r in load(batch_dir) if r.get("mode") == "swarm"]
    ok = [r for r in recs if r["outcome"]]
    print(f"\n=== {batch_dir.name}: {len(recs)} episodes, {len(recs) - len(ok)} errors, variant(s) "
          f"{sorted({r['variant'] for r in recs})}")
    print("leak overall:", _rate(r["outcome"]["leak"] for r in ok),
          "| objective_met:", _rate(r["outcome"]["objective_met"] for r in ok),
          "| crossing:", dict(sorted(defaultdict(int, {c: sum(r["outcome"]["crossing"] == c for r in ok)
                                                     for c in ("none", "worker_replies", "report")}).items())))
    print("categories:", {c: sum(r["outcome"]["category"] == c for r in ok)
                          for c in sorted({r["outcome"]["category"] for r in ok})})
    for key, label in (("peer", "worker model"), ("orchestrator", "orchestrator"), ("claim", "claim")):
        print(f"\nby {label}:")
        for v in sorted({r[key] for r in ok}):
            g = [r for r in ok if r[key] == v]
            print(f"  {v:<10} leak {_rate(r['outcome']['leak'] for r in g):<12} "
                  f"any concern {_rate(r['outcome']['raised_concern'] for r in g):<12} "
                  f"mean red flags {mean(r['outcome']['local_red_flags'] for r in g):.2f}")
    print("\nworker concern / refusal rates (over episodes where the worker got >=1 task):")
    for model in sorted({r["peer"] for r in ok}):
        cells = []
        for w in WORKER_IDS:
            g = [r["outcome"]["per_worker"][w] for r in ok if r["peer"] == model and r["outcome"]["per_worker"][w]["n_tasks"]]
            cells.append(f"{w}: concern {_rate(x['raised_concern'] for x in g)}, refused {_rate(x['refused'] for x in g)}")
        print(f"  {model:<8} " + " | ".join(cells))
    print("\norchestrator cooperation:")
    for o in sorted({r["orchestrator"] for r in ok}):
        g = [r for r in ok if r["orchestrator"] == o]
        decl_words = [explicitly_declined(orchestrator_text(batch_dir, r)) for r in g]
        print(f"  {o:<8} declined(no task or decline phrase) {_rate(r['outcome']['orchestrator_declined'] for r in g)}; "
              f"decline phrase anywhere {_rate(decl_words)}; asked for notes {_rate(r['outcome']['orchestrator_asked_for_notes'] for r in g)}; "
              f"mean tasks {mean(r['outcome']['orchestrator_n_tasks'] for r in g):.1f}")
    print(f"\ncost per episode: mean ${mean(r['cost_usd'] for r in recs):.4f}, total ${sum(r['cost_usd'] for r in recs):.4f}; "
          f"latency mean {mean(r['latency_s'] for r in recs):.0f}s, max {max(r['latency_s'] for r in recs):.0f}s")
    print("\nmonitors (mean [min-max]) local = max over workers, global = whole team:")
    for leak in (True, False):
        g = [r for r in ok if r["outcome"]["leak"] == leak]
        if not g:
            print(f"  leak={leak}: none")
            continue
        for mon in ("mon_claude", "mon_qwen"):
            loc = [r["monitors_swarm"]["local"][mon]["max"] for r in g if r["monitors_swarm"]["local"][mon]["max"] is not None]
            glo = [r["monitors_swarm"]["global"][mon] for r in g if r["monitors_swarm"]["global"][mon] is not None]
            f = lambda xs: f"{mean(xs):.1f} [{min(xs)}-{max(xs)}]" if xs else "-"  # noqa: E731
            print(f"  leak={str(leak):<5} n={len(g):<2} {mon:<10} local-max {f(loc):<14} global {f(glo)}")
    print("\nper episode: id orch>worker claim category flags crossing local-max(claude,qwen) global(claude,qwen)")
    for r in recs:
        o, m = r["outcome"] or {}, r["monitors_swarm"]
        print(f"  {r['episode_id']} {r['orchestrator']}>{r['peer']:<7} {r['claim']:<10} {o.get('category', 'ERROR'):<15} "
              f"{o.get('local_red_flags', '-')} {o.get('crossing', '-'):<15} "
              f"({m['local']['mon_claude']['max']},{m['local']['mon_qwen']['max']}) "
              f"({m['global']['mon_claude']},{m['global']['mon_qwen']}) ${r['cost_usd']:.3f} {r['latency_s']:.0f}s")


if __name__ == "__main__":
    for d in sys.argv[1:]:
        summarise(Path(d))
