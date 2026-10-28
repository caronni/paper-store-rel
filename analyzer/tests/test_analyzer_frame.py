"""W1b — the footprint and the known-bit frame (DESIGN §4.3, §4.5).

Two halves.  The OFFLINE half needs no run dir at all: a real format row
(the sheet-I fossil identity), synthetic certificates built by the
format's own encoder, and the question "does the target key's payload
leak into the frame".  The RUN-DIR half checks the frame against the
EMITTED FIELD — the only place in this wave where ground truth is
allowed, and only as a test oracle.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from holo3.data import Certificate
from holo3.format import identity, keystream, tile_codec
from holo3.plugins import color_sites

from analyzer import frame
from analyzer.types import RunInputs

from ._analyzer_fixtures import i_inputs, i_truth, needs_i_run

FORMAT_REF = "L:c2-cmy8-r0700-p120-x1@3392x2368"


# ------------------------------------------------------------- offline

def _row():
    return identity.resolve_format_ref(FORMAT_REF)


def _inputs(row) -> RunInputs:
    """A RunInputs carrying only what frame.py reads."""
    return RunInputs(
        run_dir=Path("."), format_ref=row.row_id, row=row,
        geometry=frame.geometry_of(row), pitch_in=row.pitch_in,
        tiles_yx=tuple(row.tiles_yx), cells_yx=tuple(row.cells_yx),
        live_pages=(0,), declared_pages=(0,), captures=(), lanes=(),
        lane_policy="all", rung_ppc=None, certificates={},
        plane_fields={}, pooled_ctx={}, lattice_seeds=(), windows={},
        surveys={}, metadata_word=None, metadata_version=None,
        metadata_state="absent", k_total=None, rank_report=None,
        close_report={}, provenance={})


def _certs(row, page: int, ty: int, tx: int, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    out = {}
    for fact in row.streams:
        bits = rng.integers(0, 2, fact.user_bits, dtype=np.uint8)
        out[(page, ty, tx, fact.stream_id)] = Certificate(
            page=page, ty=ty, tx=tx, stream_id=fact.stream_id,
            user_bits=bits, source="test/synthetic")
    return out


def test_tile_footprint_shape_masks_and_clipping():
    row = _row()
    fp = frame.tile_footprint(row, 0, 10, 10, 16)
    assert fp.page_cells_yx.shape == (96 * 96, 2)
    assert int(fp.in_tile.sum()) == 64 * 64
    assert fp.page_shape_cells_yx == tuple(row.cells_yx)
    # cargo = payload cells only; 120 furniture sites per tile.
    assert int((fp.in_tile & fp.cargo).sum()) == row.payload_cells
    assert int((fp.in_tile & ~fp.cargo).sum()) == row.n_sites
    # row-major page order is what sample.lane_footprint relies on.
    keys = (fp.page_cells_yx[:, 0] * row.cells_yx[1]
            + fp.page_cells_yx[:, 1])
    assert np.all(np.diff(keys) > 0)
    # a corner tile clips instead of running off the page.
    corner = frame.tile_footprint(row, 0, 0, 0, 16)
    assert corner.page_cells_yx[:, 0].min() == 0
    assert corner.page_cells_yx.shape[0] == 80 * 80
    assert frame.footprint_tiles(corner) == ((0, 0), (0, 1), (1, 0), (1, 1))


def test_target_key_is_excluded_and_the_siblings_are_not():
    row = _row()
    inputs = _inputs(row)
    certs = _certs(row, 0, 10, 10)
    fp = frame.tile_footprint(row, 0, 10, 10, 0)
    inside = fp.in_tile & fp.cargo
    full = color_sites.certified_projection(
        row, inputs.geometry, 0, 10, 10, certs)
    assert full is not None
    full_bits = full[0].reshape(-1, 3)
    local = ((fp.page_cells_yx[:, 0] % 64) * 64
             + fp.page_cells_yx[:, 1] % 64)
    for stream_id, plane in (("C", 0), ("M", 1), ("Y", 2)):
        kf = frame.known_frame(inputs, certs, fp, (0, 10, 10, stream_id),
                               metadata_known=False)
        # the assertion of DESIGN §4.5, restated as the test's own claim
        assert int(kf.known[inside, plane].sum()) == 0
        for other in (0, 1, 2):
            if other == plane:
                continue
            assert kf.known[inside, other].all()
            assert np.array_equal(kf.bits[inside, other],
                                  full_bits[local[inside], other])
        # furniture is untouched by the exclusion
        assert kf.known[fp.in_tile & ~fp.cargo].all()


def test_a_contaminated_frame_is_a_run_abort():
    """The assertion fires when the exclusion is defeated."""
    row = _row()
    inputs = _inputs(row)
    certs = _certs(row, 0, 10, 10)
    fp = frame.tile_footprint(row, 0, 10, 10, 0)
    # Poison the memo the way a target-inclusive cache would.  Each
    # certificate MAPPING gets its own memo dict, under its own token.
    token = frame._certs_token(inputs, certs)
    inputs._cache["frame_certs_registry"]["memo"][token] = {
        (0, 10, 10, (0, 10, 10, "C")): color_sites.certified_projection(
            row, inputs.geometry, 0, 10, 10, certs)}
    with pytest.raises(frame.FrameError, match="exclusion FAILED"):
        frame.known_frame(inputs, certs, fp, (0, 10, 10, "C"),
                          metadata_known=False)


def test_the_memo_does_not_carry_a_withheld_certificate_across(
) -> None:
    """DESIGN §8: a withheld frame must not be served the full frame.

    The projection memo is keyed by (page, ty, tx, excluded_key) plus a
    token for the certificate MAPPING.  Without the token the second call
    below — same footprint, same target, a neighbour tile's certificates
    withheld — came straight back out of the cache and was byte-identical
    to the first (measured 2026-09-03: 11,762 known bits either way).
    """
    row = _row()
    inputs = _inputs(row)
    full = {**_certs(row, 0, 10, 10, seed=3),
            **_certs(row, 0, 10, 11, seed=4)}
    withheld = {key: value for key, value in full.items()
                if (key[1], key[2]) != (10, 11)}
    fp = frame.tile_footprint(row, 0, 10, 10, 16)
    target = (0, 10, 10, "C")
    kf_full = frame.known_frame(inputs, full, fp, target,
                                metadata_known=False)
    kf_withheld = frame.known_frame(inputs, withheld, fp, target,
                                    metadata_known=False)
    assert int(kf_full.known.sum()) > int(kf_withheld.known.sum())
    assert kf_full.detail["n_tiles_projected"] == 2
    assert kf_withheld.detail["n_tiles_projected"] == 1
    # ... and the memo still WORKS: the same mapping twice is one build.
    again = frame.known_frame(inputs, withheld, fp, target,
                              metadata_known=False)
    assert np.array_equal(again.bits, kf_withheld.bits)
    assert np.array_equal(again.known, kf_withheld.known)
    assert len(inputs._cache["frame_certs_registry"]["by_id"]) == 2


def test_metadata_cell_carries_bit_xor_dither_and_is_in_tile_cargo():
    row = _row()
    inputs = _inputs(row)
    certs = _certs(row, 0, 10, 10)
    fp = frame.tile_footprint(row, 0, 10, 10, 4)
    counter = row.tile_counter(0, 10, 10)
    order = keystream.color_cell_permutation(row.seed, counter,
                                             row.payload_cells)
    dither = keystream.cmy8_dither_bits(row.seed, "Y", counter,
                                        row.payload_cells)
    j = int(np.flatnonzero(np.asarray(order) == 0)[0])
    flat_cell, dither0, position = frame.metadata_cell_of(
        row, inputs.geometry, (0, 10, 10, "Y"))
    assert position == j
    assert flat_cell == int(np.asarray(inputs.geometry.payload_flat)[j])
    assert dither0 == int(dither[0])

    for bit in (0, 1):
        kf = frame.known_frame(inputs, certs, fp, (0, 10, 10, "Y"),
                               metadata_known=True, metadata_bit=bit)
        assert kf.metadata_cell is not None
        cell = kf.metadata_cell
        assert (fp.in_tile & fp.cargo)[cell]
        assert kf.known[cell, 2]
        assert int(kf.bits[cell, 2]) == (bit ^ dither0)
        # ONE cell only: everything else in-tile stays unknown.
        assert int(kf.known[fp.in_tile & fp.cargo, 2].sum()) == 1
    # and not injected when the word is untrusted
    kf = frame.known_frame(inputs, certs, fp, (0, 10, 10, "Y"),
                           metadata_known=False)
    assert kf.metadata_cell is None
    assert int(kf.known[fp.in_tile & fp.cargo, 2].sum()) == 0


def test_metadata_cell_matches_what_the_encoder_would_print():
    """info bit 0 is the metadata bit — checked against encode_frame."""
    row = _row()
    inputs = _inputs(row)
    fact = row.streams[2]
    rng = np.random.default_rng(11)
    user = rng.integers(0, 2, fact.user_bits, dtype=np.uint8)
    for bit in (0, 1):
        user[0] = bit
        certs = {(0, 10, 10, "Y"): Certificate(
            page=0, ty=10, tx=10, stream_id="Y", user_bits=user.copy(),
            source="test/synthetic")}
        projection = color_sites.certified_projection(
            row, inputs.geometry, 0, 10, 10, certs)
        assert projection is not None
        flat_cell, dither0, _ = frame.metadata_cell_of(
            row, inputs.geometry, (0, 10, 10, "Y"))
        printed = projection[0].reshape(-1, 3)[flat_cell, 2]
        assert int(printed) == (bit ^ dither0)
    assert tile_codec.transmitted_positions(
        fact.rung_children[0][0], fact.rung_children[0][1])[0] == 0


def test_discriminating_labels_exclude_the_targets_own_payload():
    row = _row()
    inputs = _inputs(row)
    certs = _certs(row, 0, 10, 10)
    fp0 = frame.tile_footprint(row, 0, 10, 10, 0)
    kf0 = frame.known_frame(inputs, certs, fp0, (0, 10, 10, "C"),
                            metadata_known=False)
    # with no halo and the target excluded, only DUST can discriminate.
    assert kf0.n_discriminating <= row.n_dust
    assert kf0.detail["n_discriminating_in_tile"] == 0
    fp = frame.tile_footprint(row, 0, 10, 10, 16)
    kf = frame.known_frame(inputs, certs, fp, (0, 10, 10, "C"),
                           metadata_known=False)
    assert kf.n_discriminating >= kf0.n_discriminating
    assert kf.furniture_kind is not None
    assert int(((kf.furniture_kind == 0) & fp.in_tile).sum()) == 100
    assert int(((kf.furniture_kind == 1) & fp.in_tile).sum()) == row.n_dust


# ------------------------------------------------------------- run dir

def _all_streams_tile(inputs, prefer=(0, 10, 10)):
    page, ty, tx = prefer
    streams = tuple(fact.stream_id for fact in inputs.row.streams)
    if all((page, ty, tx, s) in inputs.certificates for s in streams):
        return page, ty, tx
    for key in sorted(inputs.certificates):
        page, ty, tx, _ = key
        if all((page, ty, tx, s) in inputs.certificates for s in streams):
            return page, ty, tx
    raise AssertionError("no tile has all three streams certified")


@needs_i_run
def test_sheet_i_frame_equals_the_emitted_field_and_hides_the_target():
    inputs = i_inputs()
    truth = i_truth()
    row = inputs.row
    page, ty, tx = _all_streams_tile(inputs)
    fp = frame.tile_footprint(row, page, ty, tx, 16)
    inside = fp.in_tile & fp.cargo
    field = truth.fields[page].plane_bits
    cells = fp.page_cells_yx

    for stream_id, plane in (("C", 0), ("M", 1), ("Y", 2)):
        kf = frame.known_frame(inputs, inputs.certificates, fp,
                               (page, ty, tx, stream_id),
                               metadata_known=False)
        # (c): the run-abort assertion holds on a REAL certified tile.
        assert int(kf.known[inside, plane].sum()) == 0
        # every known bit, halo included, equals what was emitted.
        for other in range(3):
            rows = np.flatnonzero(kf.known[:, other])
            assert rows.size > 0
            emitted = field[other, cells[rows, 0], cells[rows, 1]]
            assert np.array_equal(kf.bits[rows, other], emitted), (
                f"{stream_id}: frame plane {other} disagrees with the "
                f"emitted field on {int((kf.bits[rows, other] != emitted).sum())} cell(s)")
        # the other two streams ARE laid inside the target tile.
        for other in range(3):
            if other == plane:
                continue
            assert kf.known[inside, other].all()
            emitted = field[other, cells[inside][:, 0], cells[inside][:, 1]]
            assert np.array_equal(kf.bits[inside, other], emitted)


@needs_i_run
def test_sheet_i_metadata_cell_is_the_emitted_bit():
    from analyzer import truth as truth_module
    inputs = i_inputs()
    truth = i_truth()
    page, ty, tx = _all_streams_tile(inputs)
    fp = frame.tile_footprint(inputs.row, page, ty, tx, 0)
    field = truth.fields[page].plane_bits
    for stream_id, plane in (("C", 0), ("M", 1), ("Y", 2)):
        key = (page, ty, tx, stream_id)
        bit = truth_module.metadata_bit(inputs, key)
        if bit is None:
            pytest.skip("the run's metadata word is untrusted")
        kf = frame.known_frame(inputs, inputs.certificates, fp, key,
                               metadata_known=True, metadata_bit=bit)
        assert kf.metadata_cell is not None
        cell = fp.page_cells_yx[kf.metadata_cell]
        assert int(kf.bits[kf.metadata_cell, plane]) == int(
            field[plane, cell[0], cell[1]])


def test_two_threads_tokenising_interleaved_never_alias():
    """W3: the certificate-set token is MONOTONE and never recycled.

    The previous spelling cleared the whole registry once eight mappings
    had been seen and handed out token 0 again.  Under threads that
    ALIASES: one worker's fresh mapping takes the token another worker's
    live mapping is still writing projections under, and a `--withhold`
    frame is served the full certificate set out of the cache.

    Two threads tokenise many distinct mappings in interleaved order, far
    past `_MAX_CERT_SETS`.  Each mapping's token must be stable while it
    is held, and no two LIVE mappings may ever share one.
    """
    import threading

    row = _row()
    inputs = _inputs(row)
    n_each = 40
    mine = [[{("x", index): index} for index in range(n_each)]
            for _side in range(2)]
    seen: list[list[tuple[int, int]]] = [[], []]
    start = threading.Barrier(2)
    step = threading.Barrier(2)

    def worker(side: int) -> None:
        start.wait()
        for index in range(n_each):
            mapping = mine[side][index]
            token = frame._certs_token(inputs, mapping)
            step.wait()                        # force the interleaving
            again = frame._certs_token(inputs, mapping)
            seen[side].append((token, again))

    threads = [threading.Thread(target=worker, args=(side,))
               for side in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # a token is stable while its mapping is held ...
    for side in (0, 1):
        for token, again in seen[side]:
            assert token == again
    # ... and no token is ever handed to two different mappings.
    tokens = [token for side in (0, 1) for token, _again in seen[side]]
    assert len(tokens) == len(set(tokens)) == 2 * n_each
    assert max(tokens) == 2 * n_each - 1        # monotone, no reset

    # the memo stays bounded even though the counter does not.
    registry = inputs._cache["frame_certs_registry"]
    assert len(registry["memo"]) <= frame._MAX_CERT_SETS
    assert registry["next_token"] == 2 * n_each
