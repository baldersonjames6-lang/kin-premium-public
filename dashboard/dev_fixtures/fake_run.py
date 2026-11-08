#!/usr/bin/env python3
"""FAKE live run, for exercising the Live Run screen without spending anything.

Writes a new batch dashboard/dev_fixtures/runs/DEMO-live-<time>/ one episode at
a time (kind "demo", every record marked FAKE). SIGINT marks it aborted, writes
SHA256SUMS and exits, which is how the real run_batch.py is expected to behave.
"""
import argparse
import json
import random
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixturelib as fx  # noqa: E402

stop = {"flag": False}


def on_sigint(sig, frame):
    stop["flag"] = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=32)
    ap.add_argument("--delay", type=float, default=0.7)
    ap.add_argument("--out", default=str(Path(__file__).parent / "runs"))
    a = ap.parse_args()
    signal.signal(signal.SIGINT, on_sigint)
    now = datetime.now(timezone.utc)
    batch_id = "DEMO-live-" + now.strftime("%Y-%m-%dT%H-%M-%SZ")
    bdir = Path(a.out) / batch_id
    (bdir / "events").mkdir(parents=True)
    m = fx.manifest(batch_id, a.n, "running", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    (bdir / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    print(f"[FAKE] batch runs/{batch_id} started: {a.n} episodes", flush=True)
    rng = random.Random()
    reg = fx.make_register(random.Random(1001), 1)
    plan = fx.plan(random.Random(3))
    rng.shuffle(plan)
    t = now
    cost = 0.0
    done = 0
    for n, (r, p, c, s) in enumerate(plan[: a.n], 1):
        if stop["flag"]:
            break
        time.sleep(a.delay)
        rec, ev, t = fx.make_episode(rng, batch_id, n, r, p, c, s, 1, reg, t)
        with open(bdir / rec["events_file"], "w") as f:
            for e in ev:
                f.write(json.dumps(e) + "\n")
        with open(bdir / "episodes.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        cost += rec["cost_usd"]
        done += 1
        print(f"[FAKE] {n}/{a.n} {r} -> {p} {c}: {rec['outcome']['category']}  (${cost:.4f})", flush=True)
    m["status"] = "aborted" if stop["flag"] else "complete"
    m["cost_usd_estimate"] = round(cost, 4)
    m["notes"] = fx.FAKE_NOTE + (f" Stopped by SIGINT after {done} episodes." if stop["flag"] else "")
    (bdir / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    fx.write_sums(bdir)
    print(f"[FAKE] batch {m['status']}: {done} episodes, SHA256SUMS written", flush=True)
    return 130 if stop["flag"] else 0


if __name__ == "__main__":
    sys.exit(main())
