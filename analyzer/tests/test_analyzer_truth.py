"""analyzer.truth — the three gates and the payload loader (PLAN §1.2).

Truth is the OFFLINE scorer's input since 2026-09-04: `metadata_bit`
moved to `analyzer.inputs` (it was always blind), and a generation dir
became optional so a payload a CLOSE recovered can be scored against.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from analyzer import truth

from ._analyzer_fixtures import (I_GEN_DIR, I_PAYLOAD, J_GEN_DIR, J_PAYLOAD,
                                 i_inputs, i_truth, j_inputs, needs_i_run,
                                 needs_j_run)


# ------------------------------------------------------------- synthetic

def test_manifest_dir_takes_the_gen_dir_or_its_volume(tmp_path: Path):
    root = tmp_path / "root"
    (root / "volume").mkdir(parents=True)
    with pytest.raises(truth.TruthError):
        truth.manifest_dir(root)
    (root / "volume" / "manifest.json").write_text("{}", "utf-8")
    assert truth.manifest_dir(root) == root / "volume"
    (root / "manifest.json").write_text("{}", "utf-8")
    assert truth.manifest_dir(root) == root


def test_rng_is_a_pure_function_of_its_parts():
    a = truth._rng(7, "gate2", 0, 3).integers(0, 1 << 40, 8)
    b = truth._rng(7, "gate2", 0, 3).integers(0, 1 << 40, 8)
    c = truth._rng(7, "gate2", 0, 4).integers(0, 1 << 40, 8)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_gate2_sample_reaches_every_tile_row():
    """Stratified means every row, not the first `sample/per_row` of them."""
    from types import SimpleNamespace
    for tiles_yx, sample in (((53, 37), 96), ((20, 5), 96), ((53, 37), 40)):
        picks = truth._sample_tiles(
            SimpleNamespace(tiles_yx=tiles_yx), 0, sample, 11)
        assert len(picks) == len(set(picks)) == sample
        rows = {ty for ty, _tx in picks}
        assert max(rows) == tiles_yx[0] - 1
        if sample >= tiles_yx[0]:
            assert len(rows) == tiles_yx[0]
    again = truth._sample_tiles(SimpleNamespace(tiles_yx=(53, 37)), 0, 96, 11)
    assert again == truth._sample_tiles(
        SimpleNamespace(tiles_yx=(53, 37)), 0, 96, 11)


@needs_i_run
def test_load_truth_refuses_a_wrong_payload(tmp_path: Path):
    run = i_inputs()
    fake = tmp_path / "payload.bin"
    fake.write_bytes(b"\x00" * 16)
    with pytest.raises(truth.TruthError) as excinfo:
        truth.load_truth(I_GEN_DIR, fake, run.row, 1,
                         format_ref=run.format_ref)
    assert "manifest declares" in str(excinfo.value)


@needs_i_run
def test_load_truth_refuses_above_max_pages():
    run = i_inputs()
    with pytest.raises(truth.TruthError) as excinfo:
        truth.load_truth(I_GEN_DIR, I_PAYLOAD, run.row, 9,
                         format_ref=run.format_ref, max_pages=4)
    assert "max-gt-pages" in str(excinfo.value)



def test_the_metadata_bit_left_this_module_for_inputs():
    """It was BLIND all along; a blind driver may not import truth."""
    from analyzer import inputs as inputs_mod
    assert not hasattr(truth, "metadata_bit")
    assert not hasattr(truth, "metadata_bits")
    assert callable(inputs_mod.metadata_bit)
    assert callable(inputs_mod.metadata_bits)


@needs_i_run
def test_a_payload_without_a_generation_dir_still_reconstructs():
    """The `close`-recovered-payload case (RULED 2026-09-04).

    No manifest, no sha gate and no emitted field — the user bits come
    from the bytes alone, and the gates that need the field say they
    were skipped instead of pretending they ran.
    """
    run = i_inputs()
    bare = truth.load_truth(None, I_PAYLOAD, run.row, 1,
                            format_ref=run.format_ref)
    assert bare.fields == {}
    assert bare.gen_dir is None and bare.manifest == {}
    assert bare.payload_sha256 == i_truth().payload_sha256
    key = sorted(run.certificates)[0]
    assert np.array_equal(bare.user_bits[key], i_truth().user_bits[key])
    assert "skipped" in truth.gate_projection(bare, run, run.geometry)
    assert "skipped" in truth.gate_block_constant(bare, run)


# ------------------------------------------------------------ sheet I

@needs_i_run
def test_i_truth_loads_the_payload_and_the_emitted_field():
    run = i_inputs()
    gt = i_truth()
    assert gt.payload_bytes == 1798761
    assert gt.payload_sha256.startswith("2445b95db5b49bf3")
    assert gt.n_pages == 1
    assert len(gt.user_bits) == 5883
    assert set(gt.fields) == {0}
    assert gt.fields[0].cells_yx == run.cells_yx
    assert gt.field_dir == I_GEN_DIR


@needs_i_run
def test_i_three_gates_pass_on_every_certificate():
    run = i_inputs()
    report = truth.validate_truth(i_truth(), run, run.geometry)
    assert report["certificates"] == {
        "gate": "certificates", "checked": 5880, "mismatches": 0}
    assert report["projection"]["tiles"] == 96
    assert report["projection"]["cells"] == 96 * 64 * 64 * 3
    assert report["block_constant"]["cells_probed"] == 4096


@needs_i_run
def test_i_metadata_bit_equals_user_bits_zero_on_every_certificate():
    """The §1 producer, checked against 5,880 independent witnesses."""
    run = i_inputs()
    bad = [key for key, certificate in run.certificates.items()
           if truth.metadata_bit(run, key) != int(certificate.user_bits[0])]
    assert bad == []
    assert len(run.certificates) == 5880


@needs_i_run
def test_i_metadata_bit_is_none_without_a_trusted_word():
    import dataclasses
    run = i_inputs()
    blind = dataclasses.replace(run, metadata_word=None)
    assert truth.metadata_bit(blind, (0, 0, 0, "C")) is None


# ------------------------------------------------------------ sheet J

@needs_j_run
def test_j_manifest_lives_under_volume_and_the_payload_one_level_up():
    run = j_inputs()
    gt = truth.load_truth(J_GEN_DIR, J_PAYLOAD, run.row, 2,
                          format_ref=run.format_ref)
    assert gt.field_dir == J_GEN_DIR / "volume"
    assert gt.payload_path == J_PAYLOAD
    assert gt.n_pages == 2
    assert len(gt.user_bits) == 2 * 53 * 37 * 3
    assert set(gt.fields) == {0, 1}


@needs_j_run
def test_j_certificate_gate_catches_the_seed_fork():
    """Sheet J is a FORMAT FORK against the current tree, and gate 1 says so.

    The J sheet and its emitted field were generated with the AES seed
    ``holo/v2/c2-cmy8-r0547@53x37`` (the display spelling was canonical
    then); commit b8471fc (2026-09-02, "canonical format id is the
    explicit spelling") makes the same ``--format c2-cmy8-r0547@53x37``
    mint ``holo/v2/1i300-cmy8-r0547-p120-v1@53x37`` instead.  Systematic
    fountain rows are seed-independent, so page-0 C and M still match;
    every repair row and every word/dust state does not.  Gate 1 is
    exactly the instrument that must refuse to score such a run — this
    test pins the refusal, not the fork.
    """
    run = j_inputs()
    gt = truth.load_truth(J_GEN_DIR, J_PAYLOAD, run.row, 2,
                          format_ref=run.format_ref)
    with pytest.raises(truth.TruthError) as excinfo:
        truth.gate_certificates(gt, run)
    assert "WRONG CERTIFICATE" in str(excinfo.value)


# --------------------------------------------------- the holo1 seed bridge

def test_the_holo1_bridge_is_a_noop_when_holo1_already_mints_the_seed():
    """Sheets A–I are v1 fossils: holo1 names them, so nothing is patched."""
    from holo3.format import identity

    truth._install_holo1()
    from holo.format import resolve as holo1_resolve

    ref = "L:c2-cmy8-r0700-p120-x1@3392x2368"
    row = identity.resolve_format_ref(ref)
    before = holo1_resolve.resolve_format_ref
    with truth._holo1_resolution(ref, row) as resolved:
        assert resolved == ref
        assert holo1_resolve.resolve_format_ref is before, "patched a v1 ref"
    assert holo1_resolve.resolve_format_ref is before


def test_the_holo1_bridge_rebuilds_sheet_j_and_restores_the_resolver():
    """J's v2 fossil lives in holo3's catalogue only — holo1 gets a spec."""
    from holo3.format import identity

    truth._install_holo1()
    from holo.format import resolve as holo1_resolve

    ref = "L:c2-cmy8-r0547@53x37"
    row = identity.resolve_format_ref(ref)
    before = holo1_resolve.resolve_format_ref
    assert bytes(holo1_resolve.resolve_format_ref(
        "c2-cmy8-r0547@53x37").seed) != bytes(row.seed), "no fork to bridge"
    with truth._holo1_resolution(ref, row):
        spec = holo1_resolve.resolve_format_ref(ref)
        assert bytes(spec.seed) == bytes(row.seed)
        assert tuple(spec._tiles_yx) == tuple(row.tiles_yx)
        assert tuple(spec.stream_ids) == tuple(
            fact.stream_id for fact in row.streams)
        # a ref the bridge was not opened for still takes holo1's own route
        assert holo1_resolve.resolve_format_ref(
            "L:c2-r0700@3392x2368").seed == b"holo/v1/c2-r0700/3392x2368"
    assert holo1_resolve.resolve_format_ref is before


def test_the_holo1_bridge_refuses_a_seed_it_cannot_rebuild():
    from types import SimpleNamespace

    truth._install_holo1()
    for seed in (b"holo/v1/c2-r0700/3392x2368",       # not a v2 seed
                 b"holo/v2/not-a-coding@53x37"):      # v2, unbuildable
        row = SimpleNamespace(row_id="L:fake@53x37", seed=seed,
                              tiles_yx=(53, 37), streams=(),
                              pooled_fountain=True,
                              tile_counter=lambda *_: 0)
        with pytest.raises(truth.TruthError):
            truth._rebuilt_v2_spec(row)


@needs_j_run
def test_j_gate_1_passes_with_the_fossil_format_ref():
    """The positive half of the fork test above (PLAN §3, §6)."""
    from analyzer import inputs as inputs_mod

    from ._analyzer_fixtures import J_RUN_DIR

    run = inputs_mod.load_run(J_RUN_DIR, format_ref="L:c2-cmy8-r0547@53x37")
    gt = truth.load_truth(J_GEN_DIR, J_PAYLOAD, run.row, 2,
                          format_ref=run.format_ref)
    gate = truth.gate_certificates(gt, run)
    assert gate == {"gate": "certificates", "checked": 657, "mismatches": 0}
