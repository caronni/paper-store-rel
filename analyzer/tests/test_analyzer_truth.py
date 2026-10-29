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

from ._analyzer_fixtures import (F1_PAYLOAD_BYTES, I_FORMAT_REF,
                                 emitted_inputs, emitted_two_pages,
                                 emitted_volume, needs_sim, sim_run,
                                 sim_truth)

#: sha256 of `det_bytes(b"analyzer-tier-f1", 20000)`, computed 2026-10-09:
#: the payload rule itself, pinned apart from the file it writes.
F1_PAYLOAD_SHA256 = (
    "a6860f5749bbd8eb1a210af0ee920a9baf0ce177d20e5d9b8a1ecb2424182be4")


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


def test_load_truth_refuses_a_wrong_payload(tmp_path: Path):
    volume = emitted_volume()
    fake = tmp_path / "payload.bin"
    fake.write_bytes(b"\x00" * 16)
    with pytest.raises(truth.TruthError) as excinfo:
        truth.load_truth(volume.emit_dir, fake, volume.row, 1,
                         format_ref=volume.format_ref)
    assert "manifest declares" in str(excinfo.value)


def test_load_truth_refuses_above_max_pages(tmp_path: Path):
    """The refusal precedes opening anything: neither path exists."""
    from holo.receiver.format import identity
    row = identity.resolve_format_ref(I_FORMAT_REF)
    with pytest.raises(truth.TruthError) as excinfo:
        truth.load_truth(tmp_path / "gen", tmp_path / "payload.bin", row, 9,
                         format_ref=I_FORMAT_REF, max_pages=4)
    assert "max-gt-pages" in str(excinfo.value)



def test_the_metadata_bit_left_this_module_for_inputs():
    """It was BLIND all along; a blind driver may not import truth."""
    from analyzer import inputs as inputs_mod
    assert not hasattr(truth, "metadata_bit")
    assert not hasattr(truth, "metadata_bits")
    assert callable(inputs_mod.metadata_bit)
    assert callable(inputs_mod.metadata_bits)


def test_a_payload_without_a_generation_dir_still_reconstructs():
    """The `close`-recovered-payload case (RULED 2026-09-04).

    No manifest, no sha gate and no emitted field — the user bits come
    from the bytes alone, and the gates that need the field say they
    were skipped instead of pretending they ran.
    """
    volume = emitted_volume()
    run = emitted_inputs(volume)
    bare = truth.load_truth(None, volume.payload_path, volume.row, 1,
                            format_ref=volume.format_ref)
    assert bare.fields == {}
    assert bare.gen_dir is None and bare.manifest == {}
    assert bare.payload_sha256 == volume.truth.payload_sha256
    assert set(bare.user_bits) == set(volume.truth.user_bits)
    for key in bare.user_bits:
        assert np.array_equal(bare.user_bits[key], volume.truth.user_bits[key])
    assert "skipped" in truth.gate_projection(bare, run, run.geometry)
    assert "skipped" in truth.gate_block_constant(bare, run)


# ------------------------------------------------ an emitted volume (F1)

def test_the_emitted_truth_loads_the_payload_and_the_emitted_field():
    volume = emitted_volume()
    gt = volume.truth
    assert gt.payload_bytes == F1_PAYLOAD_BYTES == 20000
    assert gt.payload_sha256 == F1_PAYLOAD_SHA256
    assert gt.n_pages == 1
    assert len(gt.user_bits) == 10 * 10 * 3
    assert set(gt.fields) == {0}
    assert gt.fields[0].cells_yx == volume.row.cells_yx == (640, 640)
    assert gt.field_dir == volume.emit_dir


def test_a_two_page_volume_loads_both_pages_and_both_fields():
    """F4: a payload past one page, so the truth is per page — the
    shape sheet J's duplex volume needs, at 10x10."""
    volume = emitted_two_pages()
    gt = volume.truth
    assert len(sorted(volume.emit_dir.glob("page*_gt.npy"))) == 2
    assert gt.n_pages == 2
    assert set(gt.fields) == {0, 1}
    assert len(gt.user_bits) == 2 * 300
    assert {key[0] for key in gt.user_bits} == {0, 1}


def test_the_gates_bookkeeping_on_the_emitted_volume():
    """The gates' COUNTS on F1, nothing more for gate 1: the certificates
    here ARE the truth's own user bits, so its zero mismatches is a
    tautology and what is pinned is how many it checks.  Gate 1 against
    certificates a receiver minted is the TIER S test below."""
    volume = emitted_volume()
    run = emitted_inputs(volume)
    report = truth.validate_truth(volume.truth, run, run.geometry)
    assert report["certificates"] == {
        "gate": "certificates", "checked": 300, "mismatches": 0}
    assert report["projection"]["tiles"] == 96
    assert report["projection"]["cells"] == 96 * 64 * 64 * 3
    assert report["block_constant"]["cells_probed"] == 4096


@needs_sim
def test_the_three_gates_pass_on_every_receiver_certificate():
    """Gate 1 where it is not a tautology: the holo3 RECEIVER's
    certificates from the decoded sim against holo1's re-encoding of the
    emitted payload (TIER S)."""
    from holo.receiver.tests._h3_support import assert_measured
    run = sim_run()
    report = truth.validate_truth(sim_truth(), run, run.geometry)
    assert report["certificates"]["mismatches"] == 0
    assert_measured("gate 1 over the --complete sim decode",
                    report["certificates"]["checked"], 300)
    assert report["projection"]["tiles"] == 96
    assert report["projection"]["cells"] == 96 * 64 * 64 * 3
    assert report["block_constant"]["cells_probed"] == 4096


# ------------------------------------------------------ gate 1 refuses

#: The F1 volume's geometry and streams under another AES seed: the
#: uniform r0550 triplet names the same 10x10 page and the same user-bit
#: lengths, and mints ``holo/v2/1i200-cmy8-r0550-p120-v1@10x10``.
FORKED_REF = "c3-cmy8-r0550@10x10"


def test_the_certificate_gate_catches_a_seed_fork():
    """A FORMAT FORK, and gate 1 says so — sheet J's mechanism in small.

    Sheet J was generated with the AES seed ``holo/v2/c2-cmy8-r0547@53x37``
    (the display spelling was canonical then); commit b8471fc (2026-09-02,
    "canonical format id is the explicit spelling") makes the same
    ``--format c2-cmy8-r0547@53x37`` mint
    ``holo/v2/1i300-cmy8-r0547-p120-v1@53x37`` instead.  Systematic
    fountain rows are seed-independent, so they still match; every repair
    row does not.  Here the run's certificates are the emitted payload
    re-encoded under a forked seed of the same geometry.  This pins the
    refusal, not the fork.  When EVERY certificate differs the message
    names the format fork as the suspect.
    """
    from holo.receiver.format import identity

    volume = emitted_volume()
    forked_row = identity.resolve_format_ref(FORKED_REF)
    assert forked_row.seed != volume.row.seed
    assert tuple(forked_row.tiles_yx) == tuple(volume.row.tiles_yx)
    forked = truth.load_truth(None, volume.payload_path, forked_row, 1,
                              format_ref=FORKED_REF)
    run = emitted_inputs(volume, forked.user_bits)
    with pytest.raises(truth.TruthError) as excinfo:
        truth.gate_certificates(volume.truth, run)
    message = str(excinfo.value)
    assert "WRONG CERTIFICATE" in message
    # the systematic rows (K of them) survive the fork, the repair rows not
    k_total = emitted_inputs(volume).k_total
    assert f"{300 - k_total} of 300 checked" in message
    assert "every one" not in message

    flipped = {key: 1 - np.asarray(bits, np.uint8)
               for key, bits in volume.truth.user_bits.items()}
    with pytest.raises(truth.TruthError) as excinfo:
        truth.gate_certificates(volume.truth,
                                emitted_inputs(volume, flipped))
    assert "300 of 300 checked (every one" in str(excinfo.value)


# --------------------------------------------------- the holo1 seed bridge

def test_the_holo1_bridge_is_a_noop_when_holo1_already_mints_the_seed():
    """Sheets A–I are v1 fossils: holo1 names them, so nothing is patched."""
    from holo.receiver.format import identity

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
    from holo.receiver.format import identity

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

    for seed in (b"holo/v1/c2-r0700/3392x2368",       # not a v2 seed
                 b"holo/v2/not-a-coding@53x37"):      # v2, unbuildable
        row = SimpleNamespace(row_id="L:fake@53x37", seed=seed,
                              tiles_yx=(53, 37), streams=(),
                              pooled_fountain=True,
                              tile_counter=lambda *_: 0)
        with pytest.raises(truth.TruthError):
            truth._rebuilt_v2_spec(row)
