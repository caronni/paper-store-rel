"""The eight seams, each proved against holo3's own production code.

The decisive test is `test_the_patched_attempt_certifies_a_planted_frame`:
a random C user vector goes through `tile_codec.encode_frame`, the real
cmy8 dither and the real cell permutation onto a tile's 3,976 payload
cells (`analyzer.tests._synthetic`, which mirrors
`color_sites.certified_projection`), is read back as arity-1 K evidence,
and must come out of PRODUCTION `tiles.attempt_tile` as a certificate
whose user bits are byte-equal to what went in.  The control is the same
evidence through the UNPATCHED K attempt, which certifies nothing —
the patch is what makes the plane view exist.
"""

from __future__ import annotations

import numpy as np
import pytest

from holo.receiver.format import close as h3_close
from holo.receiver.format import identity, keystream, metadata, pilots, tile_codec
from holo.receiver.plugins import calibrate, color_model, tiles, words

from analyzer.planeview import patches as patches_mod
from analyzer.planeview import row as row_mod
from analyzer.tests import _synthetic

REF = _synthetic.R0850
KEY = (0, 12, 7, "C")
TILE_CELLS = pilots.TILE_CELLS


@pytest.fixture(scope="module")
def rows():
    return row_mod.build_plane_row(REF, "C")[:2]


@pytest.fixture
def installed(rows):
    plane, source = rows
    handle = patches_mod.install(plane, source)
    try:
        yield handle
    finally:
        handle.uninstall()


def _cut(frame, *, amplitude: float = 6.0,
         keep: np.ndarray | None = None) -> tiles.TileCut:
    """The planted frame as arity-1 K evidence over the tile's cells."""
    geometry = identity.build_site_geometry(_synthetic.row_of(frame.ref))
    payload_flat = np.asarray(geometry.payload_flat, np.int64)
    sequential = _synthetic.through_cells(frame)
    order = keystream.color_cell_permutation(
        frame.row.seed, frame.row.tile_counter(*frame.key[:3]),
        frame.row.payload_cells)
    physical = sequential[order]
    values = amplitude * (2.0 * physical.astype(np.float64) - 1.0)
    if keep is not None:
        payload_flat = payload_flat[keep]
        values = values[keep]
    return tiles.TileCut(
        capture_id="planted", level_index=0, page=frame.key[0],
        ty=frame.key[1], tx=frame.key[2],
        values=values.reshape(-1, 1), observed_flat=payload_flat)


def test_verify_seams_names_every_patch_point():
    seams = patches_mod.verify_seams()
    for needle in ("resolve_format_ref", "build_site_geometry",
                   "_attempt_k", "source_tag", "printed_cells_for",
                   "format_reference_values",
                   "reference_page", "CloseProgress._ingest",
                   "CloseProgress._settle"):
        assert any(needle in seam for seam in seams), needle


def test_the_patched_attempt_certifies_a_planted_frame(rows, installed):
    plane, source = rows
    frame = _synthetic.build_frame(REF, KEY, seed=11)
    geometry = identity.build_site_geometry(plane)
    result = tiles.attempt_tile(plane, geometry, (_cut(frame),), "C",
                                tiles.STAGE_SCAN)
    assert result.fact.outcome == tiles.OUTCOME_CERTIFIED
    assert result.certificate is not None
    assert np.array_equal(result.certificate.user_bits, frame.user)
    assert result.certificate.stream_id == "C"
    assert result.certificate.source == "planeview/scan"
    assert result.fact.n_informative == plane.payload_cells


def test_the_unpatched_k_attempt_certifies_nothing(rows):
    """The control: production's K framing cannot read a cmy8 stream."""
    plane, _source = rows
    frame = _synthetic.build_frame(REF, KEY, seed=11)
    geometry = identity.build_site_geometry(
        _synthetic.row_of(REF))            # the cmy8 geometry, unpatched
    result = tiles.attempt_tile(plane, geometry, (_cut(frame),), "C",
                                tiles.STAGE_SCAN)
    assert result.fact.outcome == tiles.OUTCOME_FAILED
    assert result.certificate is None


def test_a_starved_cut_is_below_the_floor_not_a_failure(rows, installed):
    plane, _source = rows
    frame = _synthetic.build_frame(REF, KEY, seed=3)
    keep = np.zeros(plane.payload_cells, bool)
    keep[:3399] = True                      # one bit under the 3,400 floor
    result = tiles.attempt_tile(
        plane, identity.build_site_geometry(plane),
        (_cut(frame, keep=keep),), "C", tiles.STAGE_SCAN)
    assert result.fact.outcome == tiles.OUTCOME_BELOW_FLOOR
    assert result.certificate is None


def test_the_attempt_patch_delegates_for_a_real_k_row(rows, installed):
    """A genuine K row in the same process still takes holo3's own path."""
    k_row = identity.resolve_format_ref("c3-k-r0550@7x7")
    geometry = identity.build_site_geometry(k_row)
    dense = np.zeros((tile_codec.N_CELLS, 1), np.float64)
    result = tiles._attempt_k(k_row, geometry, 0, 0, 0, 0, dense,
                              tiles.STAGE_SCAN)
    assert result.fact.outcome == tiles.OUTCOME_BELOW_FLOOR


def _c_bits_of(row, geometry, page, cells):
    states, kinds = color_model.reference_states(row, geometry, page, cells)
    bits = np.full(cells.shape[0], -1, np.int8)
    known = np.asarray(kinds, np.int8) >= 0
    bits[known] = tile_codec.states_to_planes(
        np.asarray(states, np.int8)[known])[:, 0]
    return bits


def test_the_reference_values_are_the_c_bit_at_every_known_cell(rows,
                                                                installed):
    plane, source = rows
    geometry = identity.build_site_geometry(plane)
    lookup = calibrate.build_site_lookup(geometry)
    ty, tx, page = 12, 7, 0
    ys, xs = np.meshgrid(np.arange(ty * TILE_CELLS, (ty + 1) * TILE_CELLS),
                         np.arange(tx * TILE_CELLS, (tx + 1) * TILE_CELLS),
                         indexing="ij")
    cells = np.stack((ys.ravel(), xs.ravel()), axis=1)
    got = calibrate.format_reference_values(plane, lookup, page, cells)
    want = _c_bits_of(source, identity.build_site_geometry(source), page,
                      cells)
    assert np.array_equal(got, want)
    assert int(np.count_nonzero(got >= 0)) == plane.n_sites == 120


def test_without_the_patch_the_twenty_dust_labels_are_wrong(rows):
    """Prove the defect the patch repairs is real, and only in the dust."""
    plane, source = rows
    geometry = identity.build_site_geometry(source)
    lookup = calibrate.build_site_lookup(geometry)
    ty, tx, page = 12, 7, 0
    ys, xs = np.meshgrid(np.arange(ty * TILE_CELLS, (ty + 1) * TILE_CELLS),
                         np.arange(tx * TILE_CELLS, (tx + 1) * TILE_CELLS),
                         indexing="ij")
    cells = np.stack((ys.ravel(), xs.ravel()), axis=1)
    raw = calibrate.format_reference_values(plane, lookup, page, cells)
    want = _c_bits_of(source, geometry, page, cells)
    kinds = lookup.kind[cells[:, 0] % TILE_CELLS, cells[:, 1] % TILE_CELLS]
    # every WORD site is already right: state 0 or 3, so C is the bit
    assert np.array_equal(raw[kinds == 0], want[kinds == 0])
    # and the dust is where the K filler keystream disagrees
    assert not np.array_equal(raw[kinds == 1], want[kinds == 1])


def test_the_reference_page_carries_the_c_bit_at_every_site(rows, installed):
    plane, source = rows
    page = 0
    reference = words.reference_page(plane, page)
    source_geometry = identity.build_site_geometry(source)
    for ty, tx in ((0, 0), (12, 7), (30, 31), (52, 36)):
        ys, xs = np.meshgrid(
            np.arange(ty * TILE_CELLS, (ty + 1) * TILE_CELLS),
            np.arange(tx * TILE_CELLS, (tx + 1) * TILE_CELLS),
            indexing="ij")
        cells = np.stack((ys.ravel(), xs.ravel()), axis=1)
        want = _c_bits_of(source, source_geometry, page, cells)
        known = want >= 0
        got = reference.values[cells[known, 0], cells[known, 1]]
        assert np.array_equal(got, want[known].astype(np.uint8))
        assert reference.sites[cells[known, 0], cells[known, 1]].all()


def test_the_geometry_override_gives_the_dust_order_the_lookup_needs(
        rows, installed):
    plane, source = rows
    assert np.array_equal(
        identity.build_site_geometry(plane).extra_cells_yx,
        identity.build_site_geometry(source).extra_cells_yx)


def test_resolve_knows_the_sentinel_and_only_the_sentinel(rows, installed):
    plane, _source = rows
    assert identity.resolve_format_ref(plane.row_id) is plane
    assert identity.resolve_format_ref(REF).row_id == REF
    with pytest.raises(ValueError):
        identity.resolve_format_ref("PV:not-a-row/C")


def test_uninstall_restores_every_seam(rows):
    plane, source = rows
    before = {
        "resolve": identity.resolve_format_ref,
        "geometry": identity.build_site_geometry,
        "attempt": tiles._attempt_k,
        "source_tag": tiles.source_tag,
        "reference_values": calibrate.format_reference_values,
        "reference_page": words.reference_page,
        "progress": h3_close.CloseProgress,
    }
    handle = patches_mod.install(plane, source)
    assert tiles.source_tag("scan") == "planeview/scan"
    handle.uninstall()
    assert identity.resolve_format_ref is before["resolve"]
    assert identity.build_site_geometry is before["geometry"]
    assert tiles._attempt_k is before["attempt"]
    assert tiles.source_tag is before["source_tag"]
    assert calibrate.format_reference_values is before["reference_values"]
    assert words.reference_page is before["reference_page"]
    assert h3_close.CloseProgress is before["progress"]
    assert tiles.source_tag("scan") == "tiles/scan"
    with pytest.raises(ValueError):
        identity.resolve_format_ref(plane.row_id)


# ------------------------------------------------------------- seam 7

class _Cert:
    def __init__(self, page, ty, tx, stream_id, bit):
        self.page, self.ty, self.tx = page, ty, tx
        self.stream_id = stream_id
        self.user_bits = np.array([bit], np.uint8)
        self.source = "planeview/scan"


def _metadata_bits(row, keys, plane_index, n_streams):
    """The true POOLED metadata bit of each tile, from the 24-bit word."""
    word = 0b1 | (1234 << 1)              # version 1, k 1234, 5 zero pads
    table = metadata.coefficient_table(
        metadata.max_equation_index(n_streams))
    out = []
    for page, ty, tx in keys:
        counter = row.tile_counter(page, ty, tx)
        index = metadata.equation_index(counter, plane_index, n_streams)
        out.append(int(bin(int(table[index]) & word).count("1") & 1))
    return out


def test_the_metadata_gate_accepts_the_true_pooled_equations(rows,
                                                             installed):
    plane, source = rows
    keys = [(0, ty, tx) for ty in range(6) for tx in range(12)]
    bits = _metadata_bits(plane, keys, 0, len(source.streams))
    progress = h3_close.CloseProgress(plane)
    progress.absorb({(p, y, x, "C"): _Cert(p, y, x, "C", b)
                     for (p, y, x), b in zip(keys, bits)})
    assert progress.metadata_n_unique == len(keys)
    assert progress.metadata_rank > 0
    # `_settle` is suppressed: the decoded word would be the POOLED
    # volume's k, and this run decodes one stream.
    assert progress._metadata.result is None
    assert progress.count_progress() == (progress.ready, None, ())


def test_the_same_bits_filed_at_the_unpooled_index_are_inconsistent(rows):
    """The measured defect the seventh seam exists for (2026-09-03)."""
    plane, source = rows
    keys = [(0, ty, tx) for ty in range(6) for tx in range(12)]
    bits = _metadata_bits(plane, keys, 0, len(source.streams))
    progress = h3_close.CloseProgress(plane)       # UNPATCHED class
    with pytest.raises(Exception) as caught:
        progress.absorb({(p, y, x, "C"): _Cert(p, y, x, "C", b)
                         for (p, y, x), b in zip(keys, bits)})
    assert "metadata equations inconsistent" in str(caught.value)


def test_the_progress_patch_delegates_for_a_real_row(rows, installed):
    row = identity.resolve_format_ref("c3-k-r0550@7x7")
    progress = h3_close.CloseProgress(row)
    progress.absorb({(0, 0, 0, "main"): _Cert(0, 0, 0, "main", 1)})
    assert progress.metadata_n_unique == 1


def test_a_second_install_is_refused(rows, installed):
    plane, source = rows
    with pytest.raises(patches_mod.SeamError):
        patches_mod.install(plane, source)


def _printed_truth(frame, geometry) -> np.ndarray:
    """The C bits actually laid on the tile's 64x64 cells, from scratch."""
    counter = frame.row.tile_counter(*frame.key[:3])
    order = keystream.color_cell_permutation(
        frame.row.seed, counter, frame.row.payload_cells)
    field = np.zeros(TILE_CELLS * TILE_CELLS, np.uint8)
    field[np.asarray(geometry.payload_flat, np.int64)] = (
        _synthetic.through_cells(frame)[order])
    field = field.reshape(TILE_CELLS, TILE_CELLS)
    word_cells = np.asarray(geometry.word_cells_yx, np.int64)
    word = pilots.word_values(frame.row.seed, (counter,), pilots.PLANE_K)[0]
    field[word_cells[:, 0], word_cells[:, 1]] = word
    dust_cells = np.asarray(geometry.extra_cells_yx, np.int64)
    states = pilots.dust_state_values(
        frame.row.seed, (counter,), frame.row)[0]
    field[dust_cells[:, 0], dust_cells[:, 1]] = (
        tile_codec.states_to_planes(states)[:, 0])
    return field


def test_the_printed_field_is_the_cmy8_field_not_the_k_reencode(rows,
                                                                installed):
    """Seam 8: refine's and local_ctx's targets are the printed C plane."""
    plane, _source = rows
    frame = _synthetic.build_frame(REF, KEY, seed=11)
    geometry = identity.build_site_geometry(plane)
    field = tiles.printed_cells_for(plane, geometry, *frame.key[:3],
                                    frame.user)
    assert field.shape == (TILE_CELLS, TILE_CELLS)
    assert np.array_equal(field, _printed_truth(frame, geometry))


def test_refines_own_binding_is_patched_too(rows, installed):
    """`refine` imported the name at module load; tiles alone is inert."""
    from holo.receiver.plugins import refine as h3_refine

    plane, _source = rows
    frame = _synthetic.build_frame(REF, KEY, seed=11)
    geometry = identity.build_site_geometry(plane)
    assert h3_refine.printed_cells_for is tiles.printed_cells_for
    fields = h3_refine.certified_fields(
        plane, geometry,
        (tiles.Certificate(page=frame.key[0], ty=frame.key[1],
                           tx=frame.key[2], stream_id="C",
                           user_bits=np.asarray(frame.user, np.uint8),
                           source="planeview/scan"),))
    assert np.array_equal(fields[frame.key[:3]],
                          _printed_truth(frame, geometry))


def test_the_unpatched_reencode_would_have_been_wrong(rows):
    """The control: production's K re-encode does not raise, it lies."""
    plane, _source = rows
    frame = _synthetic.build_frame(REF, KEY, seed=11)
    geometry = identity.build_site_geometry(_synthetic.row_of(REF))
    field = tiles.printed_cells_for(plane, geometry, *frame.key[:3],
                                    frame.user)
    truth = _printed_truth(frame, geometry)
    payload = np.asarray(geometry.payload_flat, np.int64)
    disagree = np.count_nonzero(
        field.ravel()[payload] != truth.ravel()[payload])
    assert disagree > payload.size // 4


def test_the_printed_cells_patch_delegates_for_a_real_k_row(rows, installed):
    k_row = identity.resolve_format_ref("c3-k-r0550@7x7")
    k_geometry = identity.build_site_geometry(k_row)
    rate_id, _shorten = k_row.streams[0].rung_children[0]
    user = np.zeros(tile_codec.tile_capacity(
        rate_id, int(k_geometry.shorten_flat.size)), np.uint8)
    user[::3] = 1
    field = tiles.printed_cells_for(k_row, k_geometry, 0, 1, 1, user)
    assert field.shape == (TILE_CELLS, TILE_CELLS)
