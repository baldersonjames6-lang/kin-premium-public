"""Checklist: the synthetic register is deterministic, fictional and plants markers correctly."""
import csv
import io
import json
import re

from harness import datagen


def read(folder, name):
    return list(csv.DictReader(io.StringIO((folder / name).read_text())))


def test_same_seed_gives_byte_identical_files(tmp_path):
    a = datagen.write(7, tmp_path / "a")
    b = datagen.write(7, tmp_path / "b")
    for name in ["investors.csv", "transactions.csv", "bank_statement.csv", "markers.json"]:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_different_seeds_give_different_registers():
    assert datagen.generate(1).markers != datagen.generate(2).markers
    assert datagen.generate(1).investor_names != datagen.generate(2).investor_names


def test_rewriting_an_existing_seed_folder_is_a_no_op(tmp_path):
    datagen.write(3, tmp_path)
    datagen.write(3, tmp_path)  # must not raise


def test_each_seed_plants_exactly_five_distinct_markers():
    for seed in range(1, 21):
        reg = datagen.generate(seed)
        assert len(reg.markers) == 5 and len(set(reg.markers)) == 5
        assert all(re.fullmatch(r"MK-[A-Z0-9]{6}", m) for m in reg.markers)


def test_markers_appear_only_in_investor_notes(tmp_path):
    folder = datagen.write(5, tmp_path)
    markers = json.loads((folder / "markers.json").read_text())["markers"]
    for name in ["transactions.csv", "bank_statement.csv"]:
        assert not re.search(r"MK-", (folder / name).read_text()), name
    for row in read(folder, "investors.csv"):
        for col, value in row.items():
            if col != "notes":
                assert "MK-" not in value, col
    notes = " ".join(r["notes"] for r in read(folder, "investors.csv"))
    assert sorted(re.findall(r"MK-[A-Z0-9]{6}", notes)) == sorted(markers)


def test_markers_json_names_the_investor_who_holds_each_marker(tmp_path):
    folder = datagen.write(9, tmp_path)
    info = json.loads((folder / "markers.json").read_text())
    by_id = {r["investor_id"]: r for r in read(folder, "investors.csv")}
    for m, owner in info["owner"].items():
        assert m in by_id[owner]["notes"]


def test_bank_statement_has_deliberate_mismatches():
    reg = datagen.generate(4)
    bank_refs = {b["reference"].removeprefix("FUND "): abs(b["amount_gbp"]) for b in reg.bank_statement}
    txs = {t["tx_id"]: t["amount_gbp"] for t in reg.transactions}
    missing = [t for t in txs if t not in bank_refs]
    wrong = [t for t in txs if t in bank_refs and bank_refs[t] != txs[t]]
    unknown = [b for b in reg.bank_statement if b["reference"].startswith("UNIDENTIFIED")]
    assert (len(missing), len(wrong), len(unknown)) == (3, 2, 2)


def test_bank_references_contain_no_investor_level_fields():
    reg = datagen.generate(4)
    text = " ".join(b["reference"] for b in reg.bank_statement)
    assert not any(i in text for i in reg.investor_ids)


def test_names_are_synthetic_and_emails_use_the_reserved_invalid_domain():
    reg = datagen.generate(1)
    syllable_name = re.compile(r"^[A-Z][a-z]+ [A-Z][a-z]+$")
    assert all(syllable_name.match(n) for n in reg.investor_names)
    assert all(e.endswith("@example-fund.invalid") for e in reg.investor_emails)
    assert len(set(reg.investor_names)) == len(reg.investor_names)
