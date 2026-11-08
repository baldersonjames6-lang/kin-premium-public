"""Checklist: the batch runner's safety rails and output layout (docs/CONTRACTS.md)."""
import hashlib
import json

import pytest

from conftest import FakeModels
from harness import run_batch
from harness.validate_batch import validate


def make_repo(tmp_path, review_log=None):
    (tmp_path / "PREREG.md").write_text("# prereg v1\n")
    if review_log is not None:
        (tmp_path / "REVIEW_LOG.md").write_text(review_log)
    return tmp_path


def prereg_hash(repo):
    return hashlib.sha256((repo / "PREREG.md").read_bytes()).hexdigest()


def args(repo, kind="smoke", **kw):
    argv = ["--kind", kind, "--max-cost-usd", "1", "--repo", str(repo), "--runs-dir", str(repo / "runs"),
            "--data-dir", str(repo / "data"), "--concurrency", "2"]
    for k, v in kw.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
    return run_batch.parser().parse_args(argv)


def test_pilot_is_refused_without_a_review_log_approval(tmp_path):
    repo = make_repo(tmp_path)
    with pytest.raises(SystemExit, match="REFUSED"):
        run_batch.run(args(repo, "pilot"), call_fn=FakeModels([]))


def test_main_is_refused_when_the_approval_is_for_a_different_prereg_hash(tmp_path):
    repo = make_repo(tmp_path, review_log="<!-- kin-review gate=1 decision=approved time=2026-11-06T16:00:00Z prereg_sha256=" + "0" * 64 + " -->\n")
    with pytest.raises(SystemExit, match="REFUSED"):
        run_batch.run(args(repo, "main"), call_fn=FakeModels([]))


def test_only_the_latest_gate1_decision_for_this_exact_hash_unlocks_pilot_and_main(tmp_path):
    h, other = "a" * 64, "b" * 64
    log = tmp_path / "REVIEW_LOG.md"

    def approved(*lines):
        log.write_text("\n".join(lines) + "\n")
        return run_batch.approval_in_review_log(h, log)
    ok = f"<!-- kin-review gate=1 decision=approved time=t prereg_sha256={h} -->"
    changes = f"<!-- kin-review gate=1 decision=changes_requested time=t prereg_sha256={h} -->"
    assert approved(ok)
    assert not approved(changes)                       # changes requested is not approval
    assert not approved(ok, changes)                   # a later change request re-locks the run
    assert approved(changes, ok)                       # re-approved after the change request
    assert not approved(ok.replace(h, other))          # approval of a different PREREG version
    assert not approved(f"Gate 1: PREREG.md APPROVED sha256={h}")  # free text without the machine line
    assert not approved(ok.replace("gate=1", "gate=2"))  # approving another gate is not enough


def test_pilot_is_allowed_once_the_current_prereg_hash_is_approved(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "REVIEW_LOG.md").write_text(f"<!-- kin-review gate=1 decision=approved time=t prereg_sha256={prereg_hash(repo)} -->\n")
    assert run_batch.gate("pilot", repo) == (prereg_hash(repo), prereg_hash(repo))


def test_smoke_runs_without_approval_and_records_prereg_sha256_as_null(tmp_path):
    repo = make_repo(tmp_path)
    out = run_batch.run(args(repo, n=3), call_fn=FakeModels([]))
    m = json.loads((out / "manifest.json").read_text())
    assert m["prereg_sha256"] is None
    assert m["prereg_sha256_actual"] == prereg_hash(repo)
    assert m["status"] == "complete" and m["n_episodes"] == 3
    assert "NEVER analysed" in m["notes"]


def test_smoke_batch_output_passes_the_contract_validator(tmp_path):
    repo = make_repo(tmp_path)
    out = run_batch.run(args(repo, n=8), call_fn=FakeModels([]))
    assert validate(out) == []


def test_refuses_to_overwrite_an_existing_batch_folder(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    out = run_batch.run(args(repo, n=1), call_fn=FakeModels([]))

    class FrozenNow:
        @staticmethod
        def now(tz=None):
            from datetime import datetime
            return datetime.strptime(out.name.split("_")[0], "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=tz)
    monkeypatch.setattr(run_batch, "datetime", FrozenNow)
    with pytest.raises(SystemExit, match="already exists"):
        run_batch.run(args(repo, n=1), call_fn=FakeModels([]))


def test_batch_stops_cleanly_at_the_cost_ceiling(tmp_path):
    repo = make_repo(tmp_path)
    a = args(repo, n=8)
    a.max_cost_usd = 0.004  # each fake episode costs about $0.005
    a.concurrency = 1
    out = run_batch.run(a, call_fn=FakeModels([]))
    m = json.loads((out / "manifest.json").read_text())
    assert m["status"] == "aborted" and m["n_episodes"] < 8
    assert validate(out) == []


def test_sha256sums_cover_every_file_in_the_batch(tmp_path):
    repo = make_repo(tmp_path)
    out = run_batch.run(args(repo, n=2), call_fn=FakeModels([]))
    listed = {line.split("  ", 1)[1] for line in (out / "SHA256SUMS").read_text().splitlines()}
    assert {"manifest.json", "episodes.jsonl", "events/smoke-0001.jsonl"} <= listed


def test_smoke_plan_covers_all_four_peers_and_at_least_three_claims():
    plan = run_batch.build_plan("smoke", 1, 8, None)
    assert {s["peer"] for s in plan} == {"qwen27", "qwen9", "dsv41", "haiku"}
    assert len({s["claim"] for s in plan}) >= 3


def test_main_plan_is_460_freeform_and_230_templated_with_no_haiku_requester_and_no_sibling_false_claims():
    plan = run_batch.build_plan("main", 1, None, None)
    # 12 pairings x 4 claims, minus claim_false for the 2 sibling pairings = 46 cells
    assert sum(s["request_style"] == "freeform" for s in plan) == 460   # 46 cells x 10 seeds
    assert sum(s["request_style"] == "templated" for s in plan) == 230  # 46 cells x 5 seeds
    assert all(s["requester"] != "haiku" for s in plan)
    from harness.conditions import kinship_true
    assert not any(s["claim"] == "claim_false" and kinship_true(s["requester"], s["peer"]) == "sibling" for s in plan)


def test_pilot_plan_has_20_freeform_covering_every_claim_and_20_honest():
    plan = run_batch.build_plan("pilot", 1, None, None)
    freeform = [s for s in plan if s["request_style"] == "freeform"]
    assert len(freeform) == 20 and {s["claim"] for s in freeform} == {"none", "claim_kin", "claim_nonkin", "claim_false"}
    assert sum(s["request_style"] == "honest" for s in plan) == 20


def test_pilot_and_main_refuse_to_run_on_uncommitted_code(tmp_path):
    import subprocess
    repo = tmp_path / "r"
    (repo / "harness").mkdir(parents=True)
    (repo / "harness" / "x.py").write_text("a = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c"], cwd=repo, check=True)
    run_batch.require_clean("main", repo)                      # clean: allowed
    (repo / "harness" / "x.py").write_text("a = 2\n")
    with pytest.raises(SystemExit, match="committed code"):
        run_batch.require_clean("main", repo)
    run_batch.require_clean("smoke", repo)                     # smoke is never blocked
