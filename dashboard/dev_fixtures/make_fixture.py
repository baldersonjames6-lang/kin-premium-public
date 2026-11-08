#!/usr/bin/env python3
"""Regenerate the FAKE demo batches under dashboard/dev_fixtures/ (never runs/).

    python dashboard/dev_fixtures/make_fixture.py

Creates:
  runs/DEMO-fixture/          68 FAKE episodes, complete, valid SHA256SUMS
  runs/DEMO-fixture-tampered/ 6 FAKE episodes, one file altered after hashing (shows a red cross)
  data/1/                     FAKE register with 5 planted markers
"""
import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fixturelib as fx  # noqa: E402

HERE = Path(__file__).parent


def build(batch_id, episodes_plan, status="complete", tamper=False):
    bdir = HERE / "runs" / batch_id
    if bdir.exists():
        shutil.rmtree(bdir)
    (bdir / "events").mkdir(parents=True)
    rng = random.Random(batch_id)
    reg = fx.make_register(random.Random(1001), 1)
    t = datetime(2026, 11, 6, 18, 0, 0, tzinfo=timezone.utc)
    created = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    for n, (r, p, c, s) in enumerate(episodes_plan, 1):
        rec, ev, t = fx.make_episode(rng, batch_id, n, r, p, c, s, 1, reg, t)
        rec["batch_id"] = batch_id
        with open(bdir / rec["events_file"], "w") as f:
            for e in ev:
                f.write(json.dumps(e) + "\n")
        lines.append(json.dumps(rec))
    (bdir / "episodes.jsonl").write_text("\n".join(lines) + "\n")
    m = fx.manifest(batch_id, len(lines), status, created)
    m["cost_usd_estimate"] = round(sum(json.loads(l)["cost_usd"] for l in lines), 4)
    (bdir / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    fx.write_sums(bdir)
    if tamper:
        p = bdir / "events" / "demo-0002.jsonl"
        p.write_text(p.read_text().replace("Understood", "Understood (edited after hashing)"))
    return bdir


def main():
    fx.write_register(HERE / "data", 1)
    rng = random.Random(7)
    plan = fx.plan(rng)
    print("wrote", build("DEMO-fixture", plan))
    print("wrote", build("DEMO-fixture-tampered", plan[:6], status="aborted", tamper=True))


if __name__ == "__main__":
    main()
