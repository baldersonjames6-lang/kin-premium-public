"""Tests for the review dashboard's server logic (no network, no model calls).

    python -m pytest dashboard/tests -q
Writes only to a temporary directory (REVIEW_LOG, state, report drafts).
"""
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]


@pytest.fixture()
def srv(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="kp-test-"))
    monkeypatch.setenv("KIN_REVIEW_LOG", str(tmp / "REVIEW_LOG.md"))
    monkeypatch.setenv("KIN_STATE_DIR", str(tmp / "state"))
    monkeypatch.setenv("KIN_REPORT_DIR", str(tmp / "report"))
    sys.path.insert(0, str(DASH))
    import server
    server = importlib.reload(server)
    yield server, tmp


def test_kappa_known_values(srv):
    s, _ = srv
    assert s.cohen_kappa([]) == (None, None)
    a, k = s.cohen_kappa([("leak", "leak"), ("refuse", "refuse"), ("leak", "refuse"), ("refuse", "refuse")])
    assert a == 0.75
    # pe = (2*1 + 2*3) / 16 = 0.5 -> kappa = (0.75 - 0.5) / 0.5
    assert abs(k - 0.5) < 1e-9
    a, k = s.cohen_kappa([("refuse", "refuse"), ("leak", "refuse"), ("comply_no_leak", "report")])
    assert abs(k - (1 / 3 - 2 / 9) / (1 - 2 / 9)) < 1e-9


def test_gates_unlock_in_order_and_log_block(srv):
    s, tmp = srv
    st = s.gate_status()
    assert st[1]["unlocked"] and not st[2]["unlocked"]
    with pytest.raises(ValueError):
        s.append_decision(2, "approved", "skip ahead")  # locked
    with pytest.raises(ValueError):
        s.append_decision(1, "approved", "")  # checks not ticked
    with pytest.raises(ValueError):
        s.append_decision(1, "changes_requested", "  ")  # needs a note
    for item, _ in s.GATES[1]["manual"]:
        s.set_check(1, item, True)
    r = s.append_decision(1, "approved", "looks right")
    text = (tmp / "REVIEW_LOG.md").read_text()
    sha = s.prereg_sha()
    assert f"gate=1 decision=approved" in text and sha in text and "looks right" in text
    st = s.gate_status()
    assert st[1]["state"] == "approved" and st[2]["unlocked"]
    assert (tmp / "state" / "prereg_snapshots" / f"{sha}.md").exists()
    # the harness's own approval check accepts this block
    line = next(l for l in text.splitlines() if "kin-review gate=1" in l)
    assert sha in line and "approv" in line


def test_later_gate_lines_do_not_look_like_prereg_approval(srv):
    s, tmp = srv
    for item, _ in s.GATES[1]["manual"]:
        s.set_check(1, item, True)
    s.append_decision(1, "changes_requested", "fix §6")
    sha = s.prereg_sha()
    lines = [l for l in (tmp / "REVIEW_LOG.md").read_text().splitlines() if sha in l]
    assert lines and not any("approv" in l.lower() for l in lines)
    assert s.gate_status()[1]["state"] == "changes_requested"


def test_stale_when_prereg_hash_differs(srv):
    s, tmp = srv
    (tmp / "REVIEW_LOG.md").write_text("<!-- kin-review gate=1 decision=approved time=2026-11-06T00:00:00Z prereg_sha256=" + "0" * 64 + " -->\n")
    st = s.gate_status()
    assert st[1]["state"] == "stale" and not st[2]["unlocked"]
    ok, why = s.Runner().allowed("pilot")
    assert not ok and "current PREREG" in why


def test_run_permissions(srv):
    s, _ = srv
    r = s.Runner()
    assert r.allowed("smoke")[0] and r.allowed("demo")[0]
    assert not r.allowed("pilot")[0] and not r.allowed("main")[0]
    assert not r.allowed("rm -rf")[0]


def test_tampered_fixture_fails_verification(srv):
    s, _ = srv
    good = s.verify_batch(s.FIXT_RUNS / "DEMO-fixture")
    bad = s.verify_batch(s.FIXT_RUNS / "DEMO-fixture-tampered")
    assert good["has_sums"] and all(f["ok"] for f in good["files"])
    assert not bad["all_ok"] and [f for f in bad["files"] if not f["ok"]][0]["file"] == "events/demo-0002.jsonl"


def test_demo_batches_never_analysed_and_ids_are_safe(srv):
    s, _ = srv
    ir = s.integrity_report(True)
    assert all(not b["analysed"] for b in ir["batches"] if b["fake"])
    assert s.batch_dir("../etc") is None and s.batch_dir("DEMO-../../x") is None


def test_blind_sample_is_deterministic(srv):
    s, _ = srv
    a = s.blind_sample("DEMO-fixture", "audit")
    assert a == s.blind_sample("DEMO-fixture", "audit") and len(a) == 4  # ceil(5% of 68)


def test_report_save_keeps_history(srv):
    s, tmp = srv
    s.save_section("methods", "draft one")
    s.save_section("methods", "draft two")
    assert (tmp / "report" / "methods.md").read_text() == "draft two"
    assert len(list((tmp / "report" / ".history").glob("methods-*.md"))) >= 1
    with pytest.raises(ValueError):
        s.save_section("../evil", "x")


def test_blind_context_hides_verdict(srv):
    s, _ = srv
    ctx = s.build_context({"view": "blind", "batch": "DEMO-fixture", "episode": "demo-0001", "blind": True})
    assert '"category"' not in ctx and "mon_claude" not in ctx.split("=== events ===")[-1]
    full = s.build_context({"view": "episode", "batch": "DEMO-fixture", "episode": "demo-0001"})
    assert '"category"' in full
