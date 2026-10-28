"""`analyzer.export_facts` — the ledger's certificates back into a snapshot.

The synthetic half fabricates a three-fact snapshot and two ledgers and
pins the contract: the snapshot's own facts come back in the same order,
the analyzer's certificates are APPENDED after them, a key the snapshot
already certifies is skipped, a duplicate across ledgers takes the first
ledger's bits, a DISAGREEMENT is fatal, and the list-rung toggle moves
exactly the rows it says it does.

The `@needs_i_run` half is the real one: sheet I's resume-3 snapshot
(5,880 certificates) plus the analyzer's three, read back through
`holo3.snapshot.read` at 5,883 with gate 1 green on the three added.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from holo3 import data, snapshot

from analyzer import export_facts as export_mod

from ._analyzer_fixtures import I_GEN_DIR, I_PAYLOAD, I_RUN_DIR, needs_i_run

SNAP_KEY = (0, 0, 0, "Y")
BITS_A = np.array([1, 0, 1, 1, 0, 0, 1, 0], np.uint8)
BITS_B = np.array([0, 1, 1, 0, 1, 0, 0, 1], np.uint8)
BITS_C = np.array([1, 1, 0, 0, 1, 1, 0, 0], np.uint8)
BITS_SNAP = np.array([0, 0, 1, 1, 1, 0, 1, 0], np.uint8)


def _certificate(key, bits, source):
    page, ty, tx, stream_id = key
    return data.Certificate(page=page, ty=ty, tx=tx, stream_id=stream_id,
                            user_bits=np.asarray(bits, np.uint8),
                            source=source)


def _base_snapshot(path: Path) -> tuple:
    """One non-certificate fact then two certificates — `collect`'s order."""
    facts = (
        data.LatticeSeed(capture_id="cap0", level_index=0, region_index=0,
                         rows=np.arange(6, dtype=np.int64).reshape(3, 2),
                         support_cells=17, window_ordinal=2),
        _certificate(SNAP_KEY, BITS_SNAP, "tiles/scan"),
        _certificate((0, 9, 9, "C"), BITS_SNAP, "tiles/planek150"),
    )
    snapshot.write(path, facts)
    return facts


def _row(key, verdict, rung, generation, bits, rule="sum"):
    page, ty, tx, stream_id = key
    return {"type": "row", "page": page, "ty": ty, "tx": tx,
            "stream_id": stream_id, "verdict": verdict,
            "certifying_rung": rung, "certifying_rule": rule,
            "generation": generation,
            "rungs": {"user_bits": [int(bit) for bit in bits]}}


def _write_ledger(path: Path, rows, **header) -> Path:
    head = {"type": "header", "format_ref": "L:c2-cmy8-r0700-p120-x1@3392x2368",
            "run_dir": "/tmp/fake", "seed": 20260903,
            "exposure_distinct": 7, "exposure_expected_false": 1.6e-9,
            "exposure_bound_expected_false": 0.01}
    head.update(header)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(head) + "\n")
        for row in rows:
            stream.write(json.dumps(row) + "\n")
    return path


def _ledgers(tmp_path: Path) -> tuple[Path, Path]:
    first = _write_ledger(tmp_path / "a.jsonl", [
        _row((0, 1, 1, "C"), "certified", "L0", 0, BITS_A),
        _row((0, 2, 2, "M"), "certified_list", "L4:flip", 1, BITS_B),
        # already in the snapshot with the SAME bits -> skipped, counted
        _row(SNAP_KEY, "certified", "L0", 0, BITS_SNAP),
        # not a certificate -> never exported
        _row((0, 4, 4, "Y"), "open", None, 0, BITS_C),
    ])
    second = _write_ledger(tmp_path / "b.jsonl", [
        # the same key and the same bits as ledger a -> a duplicate
        _row((0, 1, 1, "C"), "certified", "L1", 0, BITS_A),
        _row((0, 3, 3, "Y"), "certified", "L2:damped@300", 2, BITS_C),
    ], exposure_distinct=2, exposure_expected_false=4.7e-10)
    return first, second


# ------------------------------------------------------------- synthetic

def test_appends_after_the_snapshots_own_certificates(tmp_path):
    base = _base_snapshot(tmp_path / "facts.npz")
    first, second = _ledgers(tmp_path)
    out = tmp_path / "new.npz"
    manifest = export_mod.export(tmp_path / "facts.npz", [first, second], out)

    back = snapshot.read(out)
    assert len(back) == len(base) + 3
    # every snapshot fact, in the same order, unchanged
    assert [type(fact).__name__ for fact in back[:3]] == [
        "LatticeSeed", "Certificate", "Certificate"]
    assert back[0].support_cells == 17
    assert np.array_equal(back[0].rows, base[0].rows)
    assert back[1].source == "tiles/scan"
    # the analyzer's three, sorted by key, AFTER them
    added = back[3:]
    assert [(fact.page, fact.ty, fact.tx, fact.stream_id) for fact in added] \
        == [(0, 1, 1, "C"), (0, 2, 2, "M"), (0, 3, 3, "Y")]
    assert [fact.source for fact in added] == [
        "analyzer/L0", "analyzer/L4:flip", "analyzer/L2:damped@300"]
    assert np.array_equal(added[0].user_bits, BITS_A)
    assert added[0].user_bits.dtype == np.uint8
    assert manifest["verified"]["n_certificates"] == 5
    assert manifest["output"]["sha256"] == export_mod.file_sha256(out)


def test_manifest_counts_and_exposure(tmp_path):
    _base_snapshot(tmp_path / "facts.npz")
    first, second = _ledgers(tmp_path)
    out = tmp_path / "new.npz"
    manifest = export_mod.export(tmp_path / "facts.npz", [first, second], out)
    counts = manifest["counts"]
    assert counts["snapshot_certificates"] == 2
    assert counts["added"] == 3
    assert counts["added_certified"] == 2
    assert counts["added_certified_list"] == 1
    assert counts["skipped_already_certified"] == 1
    assert counts["skipped_duplicate_across_ledgers"] == 1
    assert counts["skipped_list_rung_excluded"] == 0
    assert counts["total_after_export"] == 5
    assert counts["by_stream"] == {"C": 1, "M": 1, "Y": 1}
    assert counts["by_rung"] == {"L0": 1, "L2:damped@300": 1, "L4:flip": 1}
    assert counts["by_generation"] == {"0": 1, "1": 1, "2": 1}
    assert manifest["format_ref_from"] == "ledger header"
    assert manifest["ledgers"][0]["exposure"] == {
        "distinct": 7, "expected_false": 1.6e-9,
        "bound_expected_false": 0.01}
    assert manifest["ledgers"][1]["exposure"]["distinct"] == 2
    assert manifest["ledgers"][0]["sha256"] == export_mod.file_sha256(first)
    assert manifest["snapshot"]["sha256"] == export_mod.file_sha256(
        tmp_path / "facts.npz")
    # timestamp-free: no clock anywhere in the manifest
    blob = json.dumps(manifest)
    assert "time" not in blob and "date" not in blob
    written = json.loads(
        (tmp_path / ("new.npz" + export_mod.MANIFEST_SUFFIX)).read_text())
    assert written["counts"] == counts


def test_list_rung_toggle(tmp_path):
    _base_snapshot(tmp_path / "facts.npz")
    first, second = _ledgers(tmp_path)
    out = tmp_path / "new.npz"
    manifest = export_mod.export(tmp_path / "facts.npz", [first, second], out,
                                 include_list_rungs=False)
    counts = manifest["counts"]
    assert counts["added"] == 2
    assert counts["added_certified_list"] == 0
    assert counts["skipped_list_rung_excluded"] == 1
    keys = [(fact.page, fact.ty, fact.tx, fact.stream_id)
            for fact in snapshot.read(out)[3:]]
    assert keys == [(0, 1, 1, "C"), (0, 3, 3, "Y")]


def test_conflict_between_two_ledgers_is_fatal(tmp_path):
    _base_snapshot(tmp_path / "facts.npz")
    first = _write_ledger(tmp_path / "a.jsonl", [
        _row((0, 1, 1, "C"), "certified", "L0", 0, BITS_A)])
    second = _write_ledger(tmp_path / "b.jsonl", [
        _row((0, 1, 1, "C"), "certified", "L0", 0, BITS_B)])
    out = tmp_path / "new.npz"
    with pytest.raises(export_mod.ExportError, match="CONFLICT"):
        export_mod.export(tmp_path / "facts.npz", [first, second], out)
    assert not out.exists()


def test_conflict_with_the_snapshot_is_fatal(tmp_path):
    _base_snapshot(tmp_path / "facts.npz")
    first = _write_ledger(tmp_path / "a.jsonl", [
        _row(SNAP_KEY, "certified", "L0", 0, BITS_A)])
    out = tmp_path / "new.npz"
    with pytest.raises(export_mod.ExportError, match="CONFLICT"):
        export_mod.export(tmp_path / "facts.npz", [first], out)
    assert not out.exists()


def test_a_wrong_verdict_refuses(tmp_path):
    _base_snapshot(tmp_path / "facts.npz")
    first = _write_ledger(tmp_path / "a.jsonl", [
        _row((0, 1, 1, "C"), "wrong", "L0", 0, BITS_A)])
    with pytest.raises(export_mod.ExportError, match="wrong"):
        export_mod.export(tmp_path / "facts.npz", [first],
                          tmp_path / "new.npz")


def test_certificate_bearing_other_verdicts_are_counted(tmp_path):
    """A `false_accept` row is dropped, but never silently (review W1)."""
    _base_snapshot(tmp_path / "facts.npz")
    first = _write_ledger(tmp_path / "a.jsonl", [
        _row((0, 1, 1, "C"), "false_accept", "L4:flip", 0, BITS_A),
        _row((0, 5, 5, "M"), "certified", "L0", 0, []),
        _row((0, 3, 3, "Y"), "certified", "L0", 0, BITS_C),
    ])
    manifest = export_mod.export(tmp_path / "facts.npz", [first],
                                 tmp_path / "new.npz")
    counts = manifest["counts"]
    assert counts["added"] == 1
    assert counts["skipped_other_verdict"] == 1
    assert counts["skipped_no_user_bits"] == 1
    assert manifest["skipped_other_verdict_keys"] == [[0, 1, 1, "C"]]
    keys = [(fact.page, fact.ty, fact.tx, fact.stream_id)
            for fact in snapshot.read(tmp_path / "new.npz")[3:]]
    assert keys == [(0, 3, 3, "Y")]


def test_dry_run_writes_nothing(tmp_path):
    _base_snapshot(tmp_path / "facts.npz")
    first, second = _ledgers(tmp_path)
    out = tmp_path / "new.npz"
    manifest = export_mod.export(tmp_path / "facts.npz", [first, second], out,
                                 dry_run=True)
    assert manifest["dry_run"] is True
    assert manifest["counts"]["added"] == 3
    assert manifest["output"]["sha256"] is None
    assert manifest["verified"] is None
    assert not out.exists()
    assert not (tmp_path / ("new.npz" + export_mod.MANIFEST_SUFFIX)).exists()


def test_refuses_to_overwrite_the_base_snapshot(tmp_path):
    _base_snapshot(tmp_path / "facts.npz")
    first, _second = _ledgers(tmp_path)
    with pytest.raises(export_mod.ExportError, match="never overwrites"):
        export_mod.export(tmp_path / "facts.npz", [first],
                          tmp_path / "facts.npz")


def test_the_export_opens_no_payload_and_calls_the_consistency_hook(
        tmp_path, monkeypatch):
    """2026-09-04: gate 1 is gone; a fountain consistency hook replaced it.

    The export used to take `--gt-dir/--payload` and compare every added
    certificate with the emitted user bits.  That is a scoring question
    (`analyzer score`), so what runs here instead is a truth-free check
    on the union — the over-determined GF(2) system — reached through a
    guarded `close.consistency` so this tool is green before the hook
    lands.  The hook has since LANDED, so both branches are pinned here:
    the real one, and the guard that survives it.
    """
    import inspect
    signature = inspect.signature(export_mod.export)
    assert "gt_dir" not in signature.parameters
    assert "payload" not in signature.parameters
    assert not hasattr(export_mod, "gate_added")

    _base_snapshot(tmp_path / "facts.npz")
    first, _second = _ledgers(tmp_path)

    # The real hook: four 8-bit certificates cannot solve a fountain, so
    # it comes back `checked` False and `ok` True — an unproven union is
    # not a poisoned one, and the manifest says which of the two it is.
    manifest = export_mod.export(tmp_path / "facts.npz", [first],
                                 tmp_path / "new.npz", dry_run=True)
    assert manifest["consistency_skipped"] is None
    assert manifest["consistency"]["ok"] is True
    assert manifest["consistency"]["checked"] is False
    assert manifest["consistency"]["n_certificates"] == 4

    # And the guard still holds: with the hook gone the export runs and
    # SAYS no check ran, rather than claiming one did.
    monkeypatch.delattr(export_mod.close_mod, "consistency", raising=False)
    manifest = export_mod.export(tmp_path / "facts.npz", [first],
                                 tmp_path / "new2.npz", dry_run=True)
    assert manifest["consistency"] is None
    assert "not built yet" in manifest["consistency_skipped"]

    seen: list = []

    def hook(certificates, row):
        seen.append((len(certificates), row))
        return {"ok": True, "checked": len(certificates)}

    monkeypatch.setattr(export_mod.close_mod, "consistency", hook,
                        raising=False)
    manifest = export_mod.export(tmp_path / "facts.npz", [first],
                                 tmp_path / "new3.npz", dry_run=True)
    assert manifest["consistency"] == {"ok": True,
                                       "checked": seen[0][0]}
    assert manifest["consistency_skipped"] is None


def test_a_failing_consistency_hook_refuses_the_export(tmp_path,
                                                       monkeypatch):
    _base_snapshot(tmp_path / "facts.npz")
    first, _second = _ledgers(tmp_path)
    monkeypatch.setattr(
        export_mod.close_mod, "consistency",
        lambda certificates, row: {"ok": False, "reason": "rank fell"},
        raising=False)
    with pytest.raises(export_mod.ExportError, match="rank fell"):
        export_mod.export(tmp_path / "facts.npz", [first],
                          tmp_path / "new.npz")
    assert not (tmp_path / "new.npz").exists()


def test_source_spelling_survives_holo3s_own_fold(tmp_path):
    """The chosen `source` is never parsed on the resume path.

    `store._fold_certificate` and `tiles._merge_certificate` only quote
    it; nothing splits it on `/`.  This pins that a certificate carrying
    `analyzer/L2:damped@300` round-trips through the snapshot codec with
    the string intact.
    """
    facts = (_certificate((0, 1, 1, "C"), BITS_A,
                          export_mod.source_for("L2:damped@300")),)
    snapshot.write(tmp_path / "one.npz", facts)
    assert snapshot.read(tmp_path / "one.npz")[0].source == \
        "analyzer/L2:damped@300"
    assert export_mod.source_for(None) == "analyzer"


def test_cli_export_facts(tmp_path, capsys):
    from analyzer import cli

    _base_snapshot(tmp_path / "facts.npz")
    first, second = _ledgers(tmp_path)
    out = tmp_path / "new.npz"
    code = cli.main(["export-facts", "--snapshot", str(tmp_path / "facts.npz"),
                     "--ledger", str(first), "--ledger", str(second),
                     "--out", str(out)])
    assert code == 0
    assert "5880" not in capsys.readouterr().out
    assert len(snapshot.read(out)) == 6

    bad = _write_ledger(tmp_path / "c.jsonl", [
        _row((0, 1, 1, "C"), "certified", "L0", 0, BITS_B)])
    code = cli.main(["export-facts", "--snapshot", str(tmp_path / "facts.npz"),
                     "--ledger", str(first), "--ledger", str(bad),
                     "--out", str(tmp_path / "other.npz")])
    assert code == 2
    assert "EXPORT REFUSED" in capsys.readouterr().err


# ---------------------------------------------------------- the real run

@needs_i_run
def test_sheet_i_resume3_export_reaches_5883(tmp_path):
    ledger = Path("scratch/analyzer/I-resume3/ledger.jsonl")
    if not ledger.exists():                       # pragma: no cover
        pytest.skip(f"{ledger} is absent")
    out = tmp_path / "facts-with-analyzer.npz"
    manifest = export_mod.export(
        I_RUN_DIR / "facts.npz", [ledger], out,
        gt_dir=I_GEN_DIR, payload=I_PAYLOAD)
    counts = manifest["counts"]
    print(f"\nsheet I export: {counts['snapshot_certificates']} + "
          f"{counts['added']} = {counts['total_after_export']} "
          f"certificates; by stream {counts['by_stream']}; "
          f"by rung {counts['by_rung']}; gate 1 "
          f"{manifest['gate_1']['checked']} checked, "
          f"{manifest['gate_1']['mismatches']} mismatches; "
          f"out {out.stat().st_size / 1e6:.1f} MB")
    assert counts["snapshot_certificates"] == 5880
    assert counts["added"] == 3
    assert counts["total_after_export"] == 5883
    assert counts["skipped_already_certified"] == 0
    assert manifest["gate_1"]["checked"] == 3
    assert manifest["gate_1"]["mismatches"] == 0
    assert manifest["format_ref"] == "L:c2-cmy8-r0700-p120-x1@3392x2368"

    back = snapshot.read(out)
    certs = export_mod.snapshot_certificates(back)
    assert len(certs) == 5883
    assert manifest["verified"]["n_certificates"] == 5883
    added = back[-3:]
    assert [(fact.page, fact.ty, fact.tx, fact.stream_id) for fact in added] \
        == [(0, 0, 0, "C"), (0, 36, 27, "Y"), (0, 36, 29, "Y")]
    assert [fact.source for fact in added] == [
        "analyzer/L2:damped@300", "analyzer/L0", "analyzer/L0"]
    assert all(fact.user_bits.dtype == np.uint8 for fact in added)
