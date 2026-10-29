"""`analyzer.export_facts` — the ledger's certificates back into a snapshot.

A fabricated three-fact snapshot and two ledgers pin the contract: the
snapshot's own facts come back in the same order, the analyzer's
certificates are APPENDED after them, a key the snapshot already
certifies is skipped, a duplicate across ledgers takes the first
ledger's bits, a DISAGREEMENT is fatal, and the list-rung toggle moves
exactly the rows it says it does.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import data, snapshot

from analyzer import export_facts as export_mod


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


def test_the_export_carries_the_page_fields_and_revisions_of_its_base(
        tmp_path):
    """AI6: an export preserves every fact family it was handed.

    The analyzer's door back to the receiver is a CERTIFICATE door, and
    it is additive at both ends: it appends certificates and it strips
    nothing.  The measured reason is sheet J — an export that dropped
    the field families cost the resumed receiver its evidence revisions
    (9,118 -> 8,977 and 8,602 -> 8,276, `README.md` §2.1a) and made it
    re-solve its field from nothing.  Pinned by COUNT and by digest, so
    a family silently re-keyed fails here too.
    """
    field = data.PlaneField(
        page=0, plane=1, delta_dots_xy=np.zeros((2, 2, 2), np.float64),
        support=np.ones((2, 2), np.float64),
        uncertainty_dots=np.full((2, 2), 0.25), n_observations=4,
        n_captures=3, ordinal=41906)
    revision = data.EvidenceRevision(capture_id="cap0", page=0,
                                     revision=7964)
    base = (field, revision) + _base_snapshot(tmp_path / "only.npz")
    snapshot.write(tmp_path / "facts.npz", base)
    want = export_mod.fact_digests(base)

    first, second = _ledgers(tmp_path)
    out = tmp_path / "new.npz"
    export_mod.export(tmp_path / "facts.npz", [first, second], out)

    back = snapshot.read(out)
    names = [type(fact).__name__ for fact in back]
    assert names.count("PlaneField") == 1
    assert names.count("EvidenceRevision") == 1
    assert export_mod.fact_digests(back[:len(base)]) == want
    assert back[0].ordinal == 41906 and back[1].revision == 7964


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


def test_the_archived_corpus_convert_recipe_self_checks(tmp_path):
    """AB3's other half: strip + append leaves every other fact alone.

    `measure/page_field/convert.py` is the door an archived pre-W2 spine
    comes back through, and its own self-check is the whole assertion —
    the product route end to end on a synthetic snapshot, the non-field
    digests identical, and the three refusals (another seed, another
    spine's census, an input that never lost its field).  Run here
    because it is `analyzer.export_facts.fact_digests` that adjudicates
    it, and this is that function's module.
    """
    from measure.page_field import convert

    convert.self_check(tmp_path / "convert")
    manifest = json.loads(
        (tmp_path / "convert" / "out.npz.convert.json").read_text("utf-8"))
    # F5's route key: the CONVERSION's route is its own field, beside the
    # product's own `route` and never over it (all three manifests of
    # record named the product's and called it the conversion's).
    assert manifest["source"]["conversion_route"] == "fields-json"
    assert manifest["source"]["route"] == "self-check"


def test_a_pre_existing_convert_planes_dir_is_refused_not_deleted(tmp_path):
    """F2: the solve's scratch dir is claimed, and only then removed.

    `<out parent>/convert-planes` is a FIXED name and the solve route
    `rmtree`s it on the way out, so a directory already standing there is
    a prior or concurrent conversion's — the same rule `append` applies
    to its output, one sentence in the same voice.
    """
    from measure.page_field import convert

    work = tmp_path / "convert-planes"
    work.mkdir()
    (work / "cap0").mkdir()
    (work / "cap0" / "l00-r.npy").write_bytes(b"a prior run's raster")
    with pytest.raises(ValueError, match="never overwrites"):
        convert.claim_work_dir(work)
    assert (work / "cap0" / "l00-r.npy").read_bytes() \
        == b"a prior run's raster"

    fresh = convert.claim_work_dir(tmp_path / "elsewhere" / "convert-planes")
    assert fresh.is_dir() and not any(fresh.iterdir())


def test_the_solve_route_claims_its_work_dir_before_the_store_opens(
        tmp_path, monkeypatch):
    """The refusal lands before anything is read, and a dir this call
    created is the only one it removes.

    Every `estimate` piece is stubbed: the point is the ownership, not
    the solve, and `from_solve` has no other automated coverage —
    `self_check` drives the PRODUCT route alone.
    """
    from measure.page_field import convert
    from measure.page_field.products import Declaration

    calls: list[str] = []

    class _Archive:
        def source(self):
            return {"route": "snapshot", "source": "stub"}

    monkeypatch.setattr(convert.estimate_module, "run_dir_archive",
                        lambda run_dir: _Archive())
    def opened(declaration, work):
        calls.append("open")
        return "store"

    monkeypatch.setattr(convert.estimate_module, "open_store", opened)
    monkeypatch.setattr(convert.estimate_module, "fold_evidence",
                        lambda store, facts: {"Placement": 1})
    monkeypatch.setattr(convert.estimate_module, "collect_captures",
                        lambda store, declaration, work: (1, 1, 0.0))
    monkeypatch.setattr(convert.estimate_module, "solve_pages",
                        lambda store: ((), 0.0))
    monkeypatch.setattr(convert.snapshot, "collect", lambda store: ())

    declaration = Declaration(scans=(), dpis=(), max_pages=None,
                              format_ref=convert.SELF_FORMAT_REF)
    standing = tmp_path / "convert-planes"
    standing.mkdir()
    (standing / "keep").write_bytes(b"not this invocation's")
    with pytest.raises(ValueError, match="never overwrites"):
        convert.from_solve(declaration, (), tmp_path / "facts.npz", standing)
    assert calls == [], "the store opened over a dir it did not own"
    assert (standing / "keep").exists()

    _added, source = convert.from_solve(declaration, (),
                                        tmp_path / "facts.npz",
                                        tmp_path / "mine" / "convert-planes")
    assert calls == ["open"]
    assert not (tmp_path / "mine" / "convert-planes").exists()
    assert source["conversion_route"] == "solve" and source["route"] \
        == "snapshot"


def test_the_product_route_gates_the_grid_the_ids_and_the_captures(tmp_path):
    """F5: the census says how BIG the evidence was, these say whose.

    Nothing downstream refuses a mis-shaped grid — `plane_field.evaluate`
    clamps the tile coordinates it samples at — so the refusal has to be
    here, beside the page/plane ids and the capture binding that makes an
    appended `EvidenceRevision` this archive's.
    """
    from measure.page_field import convert

    tiles_yx = convert.SELF_TILES_YX
    good = {"pages": [{
        "page": 0, "tiles_yx": list(tiles_yx),
        "evidence_revision_by_capture": {"cap0": 7964},
        "planes": [{"plane": 1,
                    "delta_dots_xy": np.zeros(tiles_yx + (2,)).tolist(),
                    "support": np.ones(tiles_yx).tolist(),
                    "uncertainty_dots": np.full(tiles_yx, 0.3).tolist()}]}]}
    archive = convert.Declared(captures=("cap0", "cap1"), pages=(0,))
    convert.check_product_shape(good, convert.SELF_FORMAT_REF,
                                tmp_path / "fields.json", archive)

    def refuses(mutate, match, declared=None):
        payload = json.loads(json.dumps(good))
        mutate(payload["pages"][0])
        with pytest.raises(ValueError, match=match):
            convert.check_product_shape(
                payload, convert.SELF_FORMAT_REF, tmp_path / "fields.json",
                declared or convert.Declared(captures=("cap0",), pages=(0,)))

    refuses(lambda page: page.update(page=999), "outside the")
    refuses(lambda page: page.update(tiles_yx=[7, 7]), "tiles")
    refuses(lambda page: page["planes"][0].update(plane=9), "is not one of")
    refuses(lambda page: page["planes"][0].update(
        delta_dots_xy=np.zeros((7, 7, 2)).tolist()), "delta_dots_xy is")
    refuses(lambda page: page["planes"][0].update(
        support=np.ones((7, 7)).tolist()), "support is")
    refuses(lambda page: page.update(
        evidence_revision_by_capture={"capX": 1}), "does not declare")

    # M3: the format's page range is 133 for both sheets of record, so
    # page 7 walked straight through it onto a one-page archive.  The
    # run declares the range.
    refuses(lambda page: page.update(page=7),
            "not one of the pages this archive declares")
    assert convert.check_product_shape(
        json.loads(json.dumps(good).replace('"page": 0', '"page": 7')),
        convert.SELF_FORMAT_REF, tmp_path / "fields.json",
        convert.Declared(captures=("cap0",), pages=(0, 7))) is None

    # M4: an empty map passed the capture gate by having nothing in it
    refuses(lambda page: page.update(evidence_revision_by_capture={}),
            "names no evidence revision")


def test_the_captures_and_pages_come_from_the_report_then_the_journal(
        tmp_path):
    """`report.json` is the reader a converted mirror answers from; a dir
    that has only its journal answers from the head `estimate` already
    reads, and one with neither cannot bind a product at all.

    The pages come back beside the captures (M3): the report lists the
    ids, the journal's `RunOpen` gives the count, and both answer in
    ids.
    """
    from measure.page_field import convert, extract

    (tmp_path / "report.json").write_text(json.dumps(
        {"capture_facts": [{"capture": "a"}, {"capture": "b"}],
         "pages": [0]}), "utf-8")
    assert convert.declared(tmp_path / "facts.npz") \
        == (("a", "b"), (0,))

    journal = tmp_path / "only-journal"
    journal.mkdir()
    extract.write_journal(journal / "events.jsonl", "c2-cmy8-r0547@53x37",
                          ["cap0", "cap1"])
    assert convert.declared(journal / "facts.npz") \
        == (("cap0", "cap1"), (0,))

    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(ValueError, match="declares no captures"):
        convert.declared(bare / "facts.npz")

    headless = tmp_path / "no-pages"
    headless.mkdir()
    (headless / "report.json").write_text(json.dumps(
        {"capture_facts": [{"capture": "a"}]}), "utf-8")
    with pytest.raises(ValueError, match="declares no `pages`"):
        convert.declared(headless / "facts.npz")

    from analyzer import unionbase
    shapeless = tmp_path / "no-captures"
    shapeless.mkdir()
    (shapeless / "report.json").write_text(json.dumps({"pages": [0]}), "utf-8")
    with pytest.raises(unionbase.UnionBaseError,
                       match="declares no `capture_facts`"):
        convert.declared(shapeless / "facts.npz")


def test_a_converted_snapshot_that_fails_its_read_back_is_not_left_behind(
        tmp_path, monkeypatch):
    """An output that fails its own verify is unlinked, manifest and all.

    The recipe's operator renames the output into place afterwards; a
    file that exists but never proved its non-field facts identical is
    the one thing that must not be there to rename.
    """
    from measure.page_field import convert
    convert.self_check(tmp_path / "work")
    work = tmp_path / "work"
    real = convert.fact_digests
    calls = {"n": 0}

    def forked(facts):
        calls["n"] += 1
        out = real(facts)
        return out if calls["n"] == 1 else ["forked"] * len(out)
    monkeypatch.setattr(convert, "fact_digests", forked)
    with pytest.raises(ValueError, match="changed in the round trip"):
        convert.append(work / "facts.npz", work / "broken.npz",
                       convert.SELF_FORMAT_REF, product=work / "fields.json")
    assert not (work / "broken.npz").exists()
    assert not (work / ("broken.npz" + convert.MANIFEST_SUFFIX)).exists()

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


# ------------------------------ the recovery door (the memory wave, 2026-09-13)

def test_a_killed_passs_mint_file_is_an_export_input(tmp_path):
    """Item 2: `export-facts --ledger mints.jsonl` recovers EXACTLY the
    certificates a killed pass had won.

    A row is final only when its whole generation folds, so a pass that
    dies inside generation 0 has no rows at all — the mint file is the
    one that carries its certificates, and it is shaped so this tool
    needs no special case for it.
    """
    from analyzer import ledger as ledger_mod

    _base_snapshot(tmp_path / "facts.npz")
    writer = ledger_mod.LedgerWriter(
        tmp_path / "ledger.jsonl",
        {"format_ref": "L:c2-cmy8-r0700-p120-x1@3392x2368",
         "run_dir": "/tmp/fake", "seed": 3})
    for key, bits in (((0, 1, 1, "C"), BITS_A), ((0, 3, 3, "Y"), BITS_C)):
        writer.mint({"page": key[0], "ty": key[1], "tx": key[2],
                     "stream_id": key[3], "verdict": "certified",
                     "certifying_rung": "L0", "certifying_rule": "sum",
                     "generation": 0,
                     "rungs": {"user_bits": np.asarray(bits, np.uint8)}})
    writer.close()                      # killed: no footer, no rows

    # the partial LEDGER recovers nothing, and refuses nothing either
    empty = export_mod.export(tmp_path / "facts.npz",
                              [tmp_path / "ledger.jsonl"],
                              tmp_path / "none.npz", dry_run=True)
    assert empty["counts"]["added"] == 0
    assert empty["ledgers"][0]["partial"] is True

    manifest = export_mod.export(tmp_path / "facts.npz",
                                 [writer.mints_path], tmp_path / "new.npz")
    assert manifest["counts"]["added"] == 2
    assert manifest["added_keys"] == [[0, 1, 1, "C"], [0, 3, 3, "Y"]]
    added = snapshot.read(tmp_path / "new.npz")[3:]
    assert [fact.source for fact in added] == ["analyzer/L0", "analyzer/L0"]
    assert np.array_equal(added[0].user_bits, BITS_A)
    assert manifest["ledgers"][0]["n_rows"] == 2
    assert manifest["ledgers"][0]["partial"] is True
    assert manifest["format_ref_from"] == "ledger header"


def test_a_truncated_ledger_exports_the_rows_it_has_and_says_so(tmp_path):
    """A `kill -9` cuts the line it was writing; the rest is good."""
    _base_snapshot(tmp_path / "facts.npz")
    path = _write_ledger(tmp_path / "a.jsonl", [
        _row((0, 1, 1, "C"), "certified", "L0", 0, BITS_A),
        _row((0, 3, 3, "Y"), "certified", "L2:damped@300", 1, BITS_C)])
    path.write_text(path.read_text("utf-8")[:-30], "utf-8")

    manifest = export_mod.export(tmp_path / "facts.npz", [path],
                                 tmp_path / "new.npz")
    assert manifest["counts"]["added"] == 1
    assert manifest["added_keys"] == [[0, 1, 1, "C"]]
    assert manifest["ledgers"][0]["truncated_lines"] == 1
    assert manifest["ledgers"][0]["n_rows"] == 1


def test_a_re_attacked_key_exports_its_LAST_row(tmp_path):
    """A streamed ledger appends the re-attack; the export takes the
    last row, the way every reader does."""
    _base_snapshot(tmp_path / "facts.npz")
    path = _write_ledger(tmp_path / "a.jsonl", [
        _row((0, 1, 1, "C"), "open", None, 0, BITS_A),
        _row((0, 1, 1, "C"), "certified", "L2:damped@300", 1, BITS_B)])
    manifest = export_mod.export(tmp_path / "facts.npz", [path],
                                 tmp_path / "new.npz", dry_run=True)
    assert manifest["counts"]["added"] == 1
    assert manifest["counts"]["skipped_other_verdict"] == 0
    assert manifest["added_detail"]["0,1,1,C"]["rung"] == "L2:damped@300"
    assert manifest["ledgers"][0]["n_rows_superseded"] == 1
