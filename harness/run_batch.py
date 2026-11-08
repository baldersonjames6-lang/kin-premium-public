"""Run a batch of episodes and write ``runs/<batch_id>/`` exactly as docs/CONTRACTS.md says.

Examples (run from the repo root)::

    python -m harness.run_batch --kind smoke --n 8 --concurrency 4 --max-cost-usd 2
    python -m harness.run_batch --kind smoke --grid "qwen27>haiku:claim_kin:templated:1" --max-cost-usd 0.5
    python -m harness.run_batch --kind main --dry-run          # print the plan only

Safety rails:
- ``pilot`` and ``main`` refuse to start unless REVIEW_LOG.md has an approval line for
  the current PREREG.md sha256. ``smoke`` and ``audit`` always run; if PREREG.md is
  not approved, their manifest gets ``prereg_sha256: null`` and a warning is printed.
- A batch folder is never overwritten; episodes.jsonl is append-only.
- Cost ceiling: no new episode starts once spending reaches ``--max-cost-usd``; any
  call that would start above 1.2 x the ceiling fails that episode with an error.
- At close, SHA256SUMS lists every file in the batch folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
import threading
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import datagen, models
from .conditions import (CLAIMS, GROUP_N_PER_WORKER, GROUPS, MODEL_KEYS, NONKIN_ORCHS, REQUESTERS, V1_MODEL_KEYS,
                         SWARM_WORKERS, claim_applies, group_cells, kinship_true)
from .episode import run_episode
from .prompts import MAIN_SWARM_VARIANT
from .swarm import run_swarm_episode

REPO = Path(__file__).resolve().parent.parent
KINDS = ["smoke", "spike", "calibrate", "pilot", "main", "audit", "explore"]
MODES = ["single", "swarm"]
GATED_KINDS = {"pilot", "main"}
STYLES = ["templated", "freeform", "honest"]
# Smoke plan: all 4 peers, every claim, every request style.
SMOKE_PLAN = [
    ("qwen27", "qwen27", "claim_kin", "templated"),
    ("qwen27", "qwen9", "claim_false", "templated"),
    ("haiku", "dsv41", "claim_nonkin", "templated"),
    ("dsv41", "haiku", "claim_false", "templated"),
    ("haiku", "haiku", "none", "templated"),
    ("dsv41", "dsv41", "claim_false", "templated"),
    ("haiku", "qwen9", "claim_kin", "freeform"),
    ("dsv41", "qwen27", "none", "honest"),
]


class CostCeilingReached(models.ModelCallError):
    pass


# ---------------------------------------------------------------- provenance

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def approval_in_review_log(prereg_hash: str, review_log: Path) -> bool:
    """True only if the LATEST gate-1 decision in REVIEW_LOG.md is 'approved' for exactly this PREREG hash.

    Reads the machine lines the dashboard writes:
    <!-- kin-review gate=1 decision=approved time=... prereg_sha256=<hash> -->
    A later 'changes_requested', or an approval of an older PREREG version, keeps pilot and main locked.
    """
    if not review_log.exists():
        return False
    pat = re.compile(r"<!--\s*kin-review\s+gate=1\s+decision=(\S+).*?prereg_sha256=([0-9a-f]{64})")
    decisions = pat.findall(review_log.read_text())
    if not decisions:
        return False
    decision, h = decisions[-1]
    return decision == "approved" and h == prereg_hash


def gate(kind: str, repo: Path = REPO) -> tuple[str | None, str]:
    """Return (prereg_sha256 for the manifest, the actual hash). Exit for unapproved pilot/main."""
    actual = sha256_file(repo / "PREREG.md")
    approved = approval_in_review_log(actual, repo / "REVIEW_LOG.md")
    if not approved:
        if kind in GATED_KINDS:
            raise SystemExit(f"REFUSED: '{kind}' needs an approval line in REVIEW_LOG.md for PREREG.md "
                             f"sha256 {actual}. Smoke batches are still allowed.")
        print(f"WARNING: PREREG.md (sha256 {actual}) is not approved in REVIEW_LOG.md; "
              f"manifest prereg_sha256 will be null.", file=sys.stderr)
    return (actual if approved else None), actual


def dirty_code(repo: Path = REPO) -> list[str]:
    """Uncommitted changes to the code or design that a pilot/main batch would run on (PREREG v2 §10.3)."""
    if not (repo / ".git").exists():
        return []
    out = subprocess.run(["git", "status", "--porcelain", "--", "harness", "analysis", "PREREG.md"],
                         cwd=repo, capture_output=True, text=True, timeout=10)
    return [line for line in out.stdout.splitlines() if line.strip()]


def require_clean(kind: str, repo: Path = REPO) -> None:
    if kind in GATED_KINDS and (dirty := dirty_code(repo)):
        raise SystemExit("REFUSED: pilot/main must run on committed code, so the manifest's git_commit is exact. "
                         "Uncommitted: " + "; ".join(dirty[:5]))


def git_commit(repo: Path = REPO) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "uncommitted"
    except Exception:
        return "uncommitted"


def harness_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted(Path(__file__).resolve().parent.glob("*.py")):
        h.update(p.name.encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- plans

def _spec(req, peer, claim, style, seed, pressure=None) -> dict:
    d = {"requester": req, "peer": peer, "claim": claim, "request_style": style, "seed": int(seed)}
    if pressure:
        d["pressure"] = pressure
    return d


def parse_grid(grid: str) -> list[dict]:
    """``req>peer:claim:style:seed`` items separated by commas."""
    out = []
    for item in filter(None, (x.strip() for x in grid.split(","))):
        pair, claim, style, seed = item.split(":")
        req, peer = pair.split(">")
        if req not in MODEL_KEYS or peer not in MODEL_KEYS or claim not in CLAIMS or style not in STYLES:
            raise SystemExit(f"bad grid item: {item}")
        out.append(_spec(req, peer, claim, style, seed))
    return out


def build_plan(kind: str, seed: int, n: int | None, grid: str | None) -> list[dict]:
    if grid:
        plan = parse_grid(grid)
    elif kind == "smoke":
        k = n or len(SMOKE_PLAN)
        plan = [_spec(*SMOKE_PLAN[i % len(SMOKE_PLAN)], seed + (i % 2)) for i in range(k)]
    elif kind == "calibrate":
        # PREREG §8b: every pairing x every pressure level, claim none, free-form. Picks the pressure
        # level by a fixed rule; never used for hypothesis tests.
        from .prompts import PRESSURE_LEVELS
        pairs = [(r, p) for r in REQUESTERS for p in V1_MODEL_KEYS]
        plan = [_spec(r, p, "none", "freeform", 300 + seed + j, lvl)
                for lvl in PRESSURE_LEVELS for j, (r, p) in enumerate(pairs)]
    elif kind == "pilot":
        # PREREG §8: 20 episodes across claims (free-form, the main mode) + 20 honest-baseline episodes.
        pairs = [(r, p) for r in REQUESTERS for p in V1_MODEL_KEYS]
        plan, i = [], 0
        while len(plan) < 20:
            r, p = pairs[(i * 5) % len(pairs)]
            c = CLAIMS[i % 4]
            if claim_applies(c, kinship_true(r, p)):
                plan.append(_spec(r, p, c, "freeform", 100 + seed + i))
            i += 1
        plan += [_spec(REQUESTERS[i % 3], V1_MODEL_KEYS[i % 4], "none", "honest", 200 + seed + i) for i in range(20)]
    elif kind == "main":
        # PREREG §7: free-form main (10 seeds) + templated control (5 seeds); sibling pairs skip claim_false.
        seeds = range(seed, seed + 10)
        cells = [(r, p, c) for r in REQUESTERS for p in V1_MODEL_KEYS for c in CLAIMS
                 if claim_applies(c, kinship_true(r, p))]
        plan = [_spec(r, p, c, "freeform", s) for (r, p, c) in cells for s in seeds]
        plan += [_spec(r, p, c, "templated", s) for (r, p, c) in cells for s in seeds[:5]]
        random.Random(f"main-order-{seed}").shuffle(plan)
    else:
        raise SystemExit("audit batches need --grid")
    return plan[:n] if n else plan


# Decomposition (swarm) feasibility plan: orchestrators qwen27 and dsv41 x all four worker models x
# claims none / claim_kin (16), plus two qwen9-orchestrator episodes (18). See harness/swarm.py.
SWARM_SPIKE_ORCHS = ["qwen27", "dsv41"]
SWARM_SPIKE_CLAIMS = ["none", "claim_kin"]


def _swarm_spec(orch, worker, claim, variant, seed, group=None) -> dict:
    d = {"mode": "swarm", "orchestrator": orch, "worker": worker, "claim": claim, "variant": variant,
         "seed": int(seed)}
    if group:
        d["group"] = group
    return d


def parse_swarm_grid(grid: str) -> list[dict]:
    """``orch>worker:claim:variant:seed`` items separated by commas."""
    from .prompts import SWARM_VARIANTS
    out = []
    for item in filter(None, (x.strip() for x in grid.split(","))):
        pair, claim, variant, seed = item.split(":")
        orch, worker = pair.split(">")
        if orch not in MODEL_KEYS or worker not in MODEL_KEYS or claim not in CLAIMS or variant not in SWARM_VARIANTS:
            raise SystemExit(f"bad swarm grid item: {item}")
        out.append(_swarm_spec(orch, worker, claim, variant, seed))
    return out


def build_swarm_plan(kind: str, seed: int, n: int | None, grid: str | None, variant: str = "v0") -> list[dict]:
    if grid:
        plan = parse_swarm_grid(grid)
    elif kind in ("spike", "smoke"):
        cells = [(o, w, c) for o in SWARM_SPIKE_ORCHS for w in V1_MODEL_KEYS for c in SWARM_SPIKE_CLAIMS]
        cells += [("qwen9", "qwen27", "none"), ("qwen9", "haiku", "claim_kin")]
        plan = [_swarm_spec(o, w, c, variant, 500 + seed + j) for j, (o, w, c) in enumerate(cells)]
    elif kind == "pilot":
        # PREREG v2.1 §8: 20 attack episodes (5 per group, every worker and non-kin orchestrator) + 20 honest.
        plan, j = [], 0
        for g in GROUPS:
            cells = group_cells(g)
            for k in range(5):
                o, w, c = cells[(k * 5) % len(cells)] if len(cells) > 3 else cells[k % len(cells)]
                plan.append(_swarm_spec(o, w, c, MAIN_SWARM_VARIANT, 700 + seed + j, g)); j += 1
        honest_pairs = [(o, w) for w in SWARM_WORKERS for o in [w] + NONKIN_ORCHS]
        plan += [_swarm_spec(*honest_pairs[(k * 3) % len(honest_pairs)], "none", "honest", 800 + seed + k, "honest")
                 for k in range(20)]
    elif kind == "explore":
        # docs/ADDENDUM-1.md: a different Qwen3.5 model coordinates (other_qwen), claim none, 6 pairs x 20.
        plan = [_swarm_spec(o, w, "none", MAIN_SWARM_VARIANT, 5000 + seed + 100 * i + r, "other_qwen")
                for i, (o, w) in enumerate((o, w) for w in SWARM_WORKERS for o in SWARM_WORKERS if o != w)
                for r in range(20)]
        random.Random(f"explore-order-{seed}").shuffle(plan)
    elif kind == "main":
        # PREREG v2.1 §7: per worker, kin_claimed 60, nonkin_silent 60, kin_silent 40, nonkin_falseclaim 40.
        plan = []
        for g, n_group in GROUP_N_PER_WORKER.items():
            for w in SWARM_WORKERS:
                cells = [c for c in group_cells(g) if c[1] == w]
                per = n_group // len(cells)
                plan += [_swarm_spec(o, w2, c, MAIN_SWARM_VARIANT, seed + 1000 * i + r, g)
                         for i, (o, w2, c) in enumerate(cells) for r in range(per)]
        random.Random(f"swarm-main-order-{seed}").shuffle(plan)
    else:
        raise SystemExit(f"swarm mode supports --kind spike, smoke, pilot or main (got '{kind}').")
    return plan[:n] if n else plan


# ---------------------------------------------------------------- running

class Spend:
    """Thread-safe running total of API cost."""

    def __init__(self, ceiling: float):
        self.ceiling, self.total, self._lock = ceiling, 0.0, threading.Lock()

    def wrap(self, call_fn: Callable) -> Callable:
        def wrapped(*a, **kw):
            if self.total >= 1.2 * self.ceiling:
                raise CostCeilingReached(f"cost ceiling reached (${self.total:.4f})")
            r = call_fn(*a, **kw)
            with self._lock:
                self.total += r.cost_usd
            return r
        return wrapped


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_sha256sums(batch_dir: Path) -> None:
    lines = [f"{sha256_file(p)}  {p.relative_to(batch_dir).as_posix()}"
             for p in sorted(batch_dir.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"]
    (batch_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def topup_plan(source: Path) -> list[dict]:
    """PREREG v2.1 §7: the exact specs of a complete batch's episodes that ended with an API error.
    Each keeps its original seed and group, and records which episode it replaces."""
    man = json.loads((source / "manifest.json").read_text())
    if man.get("status") != "complete" or man.get("kind") != "main":
        raise SystemExit(f"REFUSED: top-up needs a complete main batch (got {man.get('kind')}/{man.get('status')})")
    # Skip episodes that an earlier top-up of this batch already re-ran successfully.
    done = set()
    for d in source.parent.iterdir():
        m = d / "manifest.json"
        if d != source and m.exists() and (json.loads(m.read_text()).get("notes") or "").startswith(f"TOPUP of {source.name}:"):
            for line in (d / "episodes.jsonl").open():
                t = json.loads(line)
                if not t.get("error") and t.get("replaces"):
                    done.add(t["replaces"])
    plan = []
    for line in (source / "episodes.jsonl").open():
        e = json.loads(line)
        if e.get("error") and f"{source.name}/{e['episode_id']}" not in done:
            d = _swarm_spec(e["orchestrator"], e["peer"], e["claim"], e["variant"], e["seed"], e.get("group"))
            d["replaces"] = f"{source.name}/{e['episode_id']}"
            plan.append(d)
    return plan


def run(args, call_fn: Callable = models.call) -> Path:
    swarm = getattr(args, "mode", "single") == "swarm"
    if swarm and getattr(args, "topup_of", None):
        plan = topup_plan(Path(args.runs_dir) / args.topup_of)
        args.notes = (f"TOPUP of {args.topup_of}: re-runs the {len(plan)} episodes that ended with an API error "
                      f"(PREREG v2.1 §7). " + (args.notes or "")).strip()
    elif swarm:
        plan = build_swarm_plan(args.kind, args.seed, args.n, args.grid, getattr(args, "variant", "v0"))
    elif args.kind == "spike":
        raise SystemExit("--kind spike is only for --mode swarm")
    else:
        plan = build_plan(args.kind, args.seed, args.n, args.grid)
    if args.dry_run:  # no model calls, so no gate
        for s in plan:
            print(json.dumps(s))
        print(f"{len(plan)} episodes planned", file=sys.stderr)
        return Path()
    prereg_hash, actual_hash = gate(args.kind, Path(args.repo))
    require_clean(args.kind, Path(args.repo))

    now = datetime.now(timezone.utc)
    batch_id = now.strftime("%Y-%m-%dT%H-%M-%SZ") + f"_{args.kind}"
    batch_dir = Path(args.runs_dir) / batch_id
    if batch_dir.exists():
        raise SystemExit(f"REFUSED: {batch_dir} already exists; batches are never overwritten.")
    batch_dir.mkdir(parents=True)
    (batch_dir / "events").mkdir()

    thresholds = json.loads(Path(args.thresholds).read_text()) if args.thresholds else None
    notes = args.notes or ""
    if args.kind == "smoke":
        notes = ("SMOKE BATCH: harness check only, NEVER analysed. " + notes).strip()
    if args.kind == "spike":
        notes = ("SPIKE: feasibility only, never analysed. " + notes).strip()
    if swarm:
        notes = (notes + f" MODE swarm (decomposition: 1 orchestrator + 3 workers), variant "
                 f"{getattr(args, 'variant', 'v0')}.").strip()
    if args.kind == "explore":
        notes = ("EXPLORATORY (ADDENDUM-1): added after seeing the main results; never in the Holm family. " + notes).strip()
    if args.kind == "calibrate":
        notes = ("CALIBRATION BATCH (PREREG §8b): used only to choose the pressure level by the "
                 "pre-registered rule; never used for hypothesis tests. " + notes).strip()
    if thresholds is None:
        notes = (notes + " Monitor flags are null: no calibrated threshold was supplied.").strip()
    manifest = {
        "batch_id": batch_id, "kind": args.kind, "created_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git_commit(Path(args.repo)), "prereg_sha256": prereg_hash, "data_seed": args.seed,
        "models": models.model_ids(), "conditions": CLAIMS, "n_episodes": 0,
        "cost_usd_estimate": 0.0, "status": "running", "notes": notes,
        # extra provenance (not required by CONTRACTS.md)
        "prereg_sha256_actual": actual_hash, "harness_sha256": harness_sha256(),
        "providers": {k: v["provider"] for k, v in models.MODELS.items()},
        "n_planned": len(plan), "max_cost_usd": args.max_cost_usd, "monitor_thresholds": thresholds,
        "mode": "swarm" if swarm else "single",
    }
    _write_json(batch_dir / "manifest.json", manifest)
    print(f"batch {batch_id}: {len(plan)} episodes planned -> {batch_dir}")

    spend = Spend(args.max_cost_usd)
    wrapped = spend.wrap(call_fn)
    data_dir = Path(args.data_dir)
    for s in sorted({spec["seed"] for spec in plan}):  # write data once, before any threads start
        datagen.write(s, data_dir)
    lock = threading.Lock()
    status, n_done, n_err = "complete", 0, 0

    def work(i: int, spec: dict) -> dict:
        ep_id = f"{args.kind}-{i + 1:04d}"
        try:
            reg = datagen.load(spec["seed"], data_dir)
            run_fn = run_swarm_episode if swarm else run_episode
            return run_fn(spec, reg, batch_id, ep_id, batch_dir, call_fn=wrapped, thresholds=thresholds)
        except Exception as e:  # a harness bug: record it and stop the batch
            return {"_bug": f"{type(e).__name__}: {e}", "_tb": traceback.format_exc(), "episode_id": ep_id}

    with (batch_dir / "episodes.jsonl").open("a") as out, ThreadPoolExecutor(args.concurrency) as ex:
        todo = list(enumerate(plan))[::-1]
        pending, stop = set(), False
        while True:
            while todo and not stop and len(pending) < args.concurrency:
                if spend.total >= args.max_cost_usd:
                    stop, status = True, "aborted"
                    print(f"cost ceiling ${args.max_cost_usd} reached; no new episodes", file=sys.stderr)
                    break
                i, spec = todo.pop()
                pending.add(ex.submit(work, i, spec))
            if not pending:
                break
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for f in done:
                rec = f.result()
                if "_bug" in rec:
                    stop, status = True, "aborted"
                    print(f"HARNESS BUG in {rec['episode_id']}: {rec['_bug']}\n{rec['_tb']}", file=sys.stderr)
                    manifest["notes"] = (manifest["notes"] + f" Aborted on harness bug: {rec['_bug']}").strip()
                    continue
                with lock:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                n_done += 1
                n_err += rec["error"] is not None
                cat = rec["outcome"]["category"] if rec["outcome"] else "-"
                if swarm and rec["outcome"]:
                    o = rec["outcome"]
                    cat += f" flags={o['local_red_flags']} cross={o['crossing']} orch_tasks={o['orchestrator_n_tasks']}"
                print(f"  {rec['episode_id']} {rec['requester']}>{rec['peer']} {rec['claim']:<12} "
                      f"{rec['request_style']:<9} -> {cat:<15} ${rec['cost_usd']:.4f} "
                      f"{'ERROR ' + rec['error'][:80] if rec['error'] else ''}")
        if todo and status == "complete":
            status = "aborted"

    manifest.update(n_episodes=n_done, n_errors=n_err, cost_usd_estimate=round(spend.total, 6), status=status,
                    closed_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    _write_json(batch_dir / "manifest.json", manifest)
    write_sha256sums(batch_dir)
    print(f"closed {batch_id}: status={status} episodes={n_done} errors={n_err} cost=${spend.total:.4f}")
    return batch_dir


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run a batch of kin-premium episodes.")
    ap.add_argument("--kind", choices=KINDS, required=True)
    ap.add_argument("--n", type=int, default=None, help="limit the plan to the first N episodes")
    ap.add_argument("--topup-of", default=None, help="swarm main: re-run the API-error episodes of this batch id")
    ap.add_argument("--grid", default=None, help='explicit plan: "req>peer:claim:style:seed,..." '
                    '(swarm mode: "orch>worker:claim:variant:seed,...")')
    ap.add_argument("--mode", choices=MODES, default="single", help="single-prompt episodes or decomposition (swarm)")
    ap.add_argument("--variant", default="v0", help="swarm orchestrator variant (prompts.SWARM_VARIANTS)")
    ap.add_argument("--seed", type=int, default=1, help="base data seed")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--max-cost-usd", type=float, required=True)
    ap.add_argument("--thresholds", default=None, help='JSON file {"mon_claude": x, "mon_qwen": y}')
    ap.add_argument("--notes", default="")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--runs-dir", default=str(REPO / "runs"))
    ap.add_argument("--data-dir", default=str(REPO / "data"))
    return ap


def main(argv=None) -> None:
    run(parser().parse_args(argv))


if __name__ == "__main__":
    main()
