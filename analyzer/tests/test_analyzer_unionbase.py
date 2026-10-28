"""`analyzer union-base` — a run dir that borrows another's rasters.

The tool is small and its failure modes are the point: a snapshot whose
poses name a capture the base run does not declare would be applied to
the wrong pixels, and a base run missing a raster directory would make
every lane refuse.  Both refuse here, before anything is written.

`--targets 'open-after L1,L2'` is tested beside it because the two are
one workflow: export the harvest, build the base on it, and target what
is still open after the union.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from holo3 import data, snapshot

from analyzer import unionbase as ub
from analyzer.types import LedgerRow

CAP_A = "aaaaaaaaaaaa1111"
CAP_B = "bbbbbbbbbbbb2222"


def _run_dir(tmp_path: Path, *, captures=(CAP_A, CAP_B),
             rasters=None) -> Path:
    run = tmp_path / "base"
    run.mkdir(parents=True, exist_ok=True)
    (run / "report.json").write_text(json.dumps({
        "capture_facts": [{"capture": name, "ordinal": index, "dpi": 2400.0,
                           "channels": 3, "levels_ppc": ["8"],
                           "shape_yx": [10, 10]}
                          for index, name in enumerate(captures)],
        "pages": [0]}), "utf-8")
    (run / "events.jsonl").write_text('{"type": "RunOpen"}\n', "utf-8")
    (run / "argv").write_text("holo3 decode …\n", "utf-8")
    for name in (captures if rasters is None else rasters):
        (run / name[:12]).mkdir(exist_ok=True)
        (run / name[:12] / "l00-r.npy").write_bytes(b"not really a raster")
    return run


def _snapshot(path: Path, *capture_ids: str) -> Path:
    facts = tuple(
        data.LatticeSeed(capture_id=name, level_index=0, region_index=0,
                         rows=np.arange(6, dtype=np.int64).reshape(3, 2),
                         support_cells=17, window_ordinal=2)
        for name in capture_ids)
    snapshot.write(path, facts)
    return path


# ------------------------------------------------------------ the build

def test_the_union_base_symlinks_the_rasters_and_copies_the_small_files(
        tmp_path):
    run = _run_dir(tmp_path)
    facts = _snapshot(tmp_path / "exported.npz", CAP_A, CAP_B)
    out = tmp_path / "union"
    record = ub.build(run, facts, out)

    assert (out / "report.json").is_file() and not (
        out / "report.json").is_symlink()
    assert (out / "argv").is_file()
    assert (out / "events.jsonl").is_symlink()
    for name in (CAP_A, CAP_B):
        link = out / name[:12]
        assert link.is_symlink()
        assert link.resolve() == (run / name[:12]).resolve()
    assert (out / snapshot.NAME).is_symlink()
    assert (out / snapshot.NAME).resolve() == facts.resolve()
    assert record["captures_in_facts"] == [CAP_A[:12], CAP_B[:12]]
    assert record["captures_verified"] is True and record["n_facts"] == 2
    assert json.loads((out / ub.RECORD_NAME).read_text("utf-8")) == record


def test_a_second_build_over_the_same_out_dir_replaces_the_links(tmp_path):
    run = _run_dir(tmp_path)
    first = _snapshot(tmp_path / "one.npz", CAP_A)
    second = _snapshot(tmp_path / "two.npz", CAP_A, CAP_B)
    out = tmp_path / "union"
    ub.build(run, first, out)
    record = ub.build(run, second, out)
    assert (out / snapshot.NAME).resolve() == second.resolve()
    assert record["n_facts"] == 2


def test_facts_naming_an_undeclared_capture_refuse(tmp_path):
    """The failure this check exists for: poses on the wrong pixels."""
    run = _run_dir(tmp_path, captures=(CAP_A,))
    facts = _snapshot(tmp_path / "exported.npz", CAP_A, CAP_B)
    with pytest.raises(ub.UnionBaseError, match="does not declare"):
        ub.build(run, facts, tmp_path / "union")
    assert not (tmp_path / "union").exists()


def test_a_snapshot_with_no_capture_at_all_refuses(tmp_path):
    run = _run_dir(tmp_path)
    path = tmp_path / "certs-only.npz"
    snapshot.write(path, (data.Certificate(
        page=0, ty=0, tx=0, stream_id="Y",
        user_bits=np.zeros(8, np.uint8), source="tiles/scan"),))
    with pytest.raises(ub.UnionBaseError, match="names no capture"):
        ub.build(run, path, tmp_path / "union")


def test_a_missing_raster_directory_refuses(tmp_path):
    run = _run_dir(tmp_path, rasters=(CAP_A,))
    facts = _snapshot(tmp_path / "exported.npz", CAP_A)
    with pytest.raises(ub.UnionBaseError, match="no raster directory"):
        ub.build(run, facts, tmp_path / "union")


def test_building_over_the_base_run_dir_refuses(tmp_path):
    run = _run_dir(tmp_path)
    facts = _snapshot(tmp_path / "exported.npz", CAP_A, CAP_B)
    with pytest.raises(ub.UnionBaseError, match="never an overwrite"):
        ub.build(run, facts, run)


def test_a_missing_facts_file_refuses(tmp_path):
    run = _run_dir(tmp_path)
    with pytest.raises(ub.UnionBaseError, match="is absent"):
        ub.build(run, tmp_path / "nope.npz", tmp_path / "union")


def test_no_verify_skips_the_snapshot_read(tmp_path):
    """The escape hatch for a 12 GB snapshot, and it says so in the record."""
    run = _run_dir(tmp_path)
    facts = tmp_path / "exported.npz"
    facts.write_bytes(b"not a snapshot at all")
    record = ub.build(run, facts, tmp_path / "union", verify_facts=False)
    assert record["captures_verified"] is False
    assert record["captures_in_facts"] == [] and record["n_facts"] is None


# ------------------------------------------------------- open-after

def _census_row(ty: int, tx: int, stream: str, *, certified=False):
    return LedgerRow(page=0, ty=ty, tx=tx, stream_id=stream, esi=ty,
                     covered=True, certified_by_production=certified,
                     source="tiles/scan" if certified else None,
                     band="live", band_any="live", neighbours_certified=8,
                     siblings_certified=(), known_cells_in_halo=100,
                     n_discriminating_labels=13, production_attempts={},
                     metadata_known=True)


def _ledger(path: Path, keys, verdict="certified") -> Path:
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "header", "seed": 1}) + "\n")
        for page, ty, tx, stream_id in keys:
            stream.write(json.dumps(
                {"type": "row", "page": page, "ty": ty, "tx": tx,
                 "stream_id": stream_id, "verdict": verdict}) + "\n")
    return path


def test_open_after_subtracts_the_ledgers_certificates(tmp_path):
    rows = [_census_row(0, 0, "C"), _census_row(0, 1, "C"),
            _census_row(0, 2, "Y"), _census_row(0, 3, "Y", certified=True)]
    first = _ledger(tmp_path / "a.jsonl", [(0, 0, 0, "C")])
    second = _ledger(tmp_path / "b.jsonl", [(0, 0, 2, "Y")],
                     verdict="certified_list")
    spec = f"open-after {first},{second}"
    assert ub.is_open_after(spec) is True
    left = ub.open_after(rows, spec)
    assert [row.key for row in left] == [(0, 0, 1, "C")]
    # a production certificate was never a target to begin with
    assert (0, 0, 3, "Y") not in [row.key for row in left]


def test_open_after_ignores_rows_that_did_not_certify(tmp_path):
    rows = [_census_row(0, 0, "C"), _census_row(0, 1, "C")]
    path = _ledger(tmp_path / "a.jsonl", [(0, 0, 0, "C")], verdict="open")
    left = ub.open_after(rows, f"open-after {path}")
    assert [row.key for row in left] == [(0, 0, 0, "C"), (0, 0, 1, "C")]


def test_open_after_needs_a_ledger_and_says_which_is_missing(tmp_path):
    with pytest.raises(ub.UnionBaseError, match="names no ledger"):
        ub.open_after([], "open-after ")
    with pytest.raises(ub.UnionBaseError, match="is absent"):
        ub.open_after([], f"open-after {tmp_path / 'nope.jsonl'}")


def test_open_after_streams_the_ledgers_it_reads(tmp_path, monkeypatch):
    """The same 26 GB lesson `analyzer score` learned.

    A sheet-H pass is 2.6-5.8 GB of JSON and five of them are 18 GB;
    what `open-after` keeps out of one is a set of 4-tuples, so the rows
    go past one at a time and are never materialised.
    """
    import inspect
    from analyzer import ledger as ledger_mod
    source = inspect.getsource(ub)
    assert "ledger_mod.iter_rows" in source
    assert "ledger_mod.read_rows" not in source

    seen: list[str] = []
    original = ledger_mod.iter_rows

    def spy(path):
        seen.append(str(path))
        return original(path)

    monkeypatch.setattr(ledger_mod, "iter_rows", spy)
    path = _ledger(tmp_path / "a.jsonl", [(0, 0, 0, "C")])
    assert ub.certified_in([path]) == {(0, 0, 0, "C")}
    assert seen == [str(path)]


def test_the_cli_targets_route_reaches_open_after(tmp_path):
    from analyzer import cli
    rows = [_census_row(0, 0, "C"), _census_row(0, 1, "C")]
    path = _ledger(tmp_path / "a.jsonl", [(0, 0, 0, "C")])
    assert [row.key for row in cli._targets(rows, f"open-after {path}")] == [
        (0, 0, 1, "C")]
