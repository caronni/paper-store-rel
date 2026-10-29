"""The Y-as-K read: poses in, yellow certificates out.

Four steps, each of them a call into UNCHANGED holo3 code wherever
holo3 already has the code:

1. **poses** come from outside. Yellow never self-addresses — the
   colour word renders states {0, 3}, whose yellow bit is zero at every
   one of the 100 word sites (``src/holo/format/pilots.py``
   ``color_word_states``; holo3's ``pilots.color_word_states`` is the
   same arithmetic), so a Y-only reader can never find the page. The
   poses here are the committed poses of an ordinary run that placed
   and addressed the page through C and M.
2. **sampling** is ``calibrate.sampled_window_means`` — holo3's own
   aperture filter and its own bilinear read — called once per channel
   at those poses, then unmixed (``_spectral``). Filtering and
   unmixing are both linear, so this is exactly sampling the synthetic
   yellow-as-black plane.
3. **detection** is holo3's black-and-white machinery, verbatim:
   ``calibrate.window_scores`` (median split, mean-absolute-deviation
   scale), ``calibrate.fit_window_calibration`` (the PAVA
   score-to-probability map on a parity-held-out split), and
   ``calibrate.apply_region_context`` (the nine-bin neighbour-count
   detector with its own held-out adoption gate). The only thing that
   differs from a K page is WHICH CELLS CARRY LABELS: on a K page the
   word sites are half ones, here they are all zeros, so the yellow
   labels are the 20 dust sites per tile — the lead's "fill back tile
   addresses according to dust locations" — plus the payload cells of
   any tile already certified in Y ("certified neighbours").
4. **decoding** is the UNCHANGED codec: a per-plane ``TileCut`` whose
   Y column carries the calibrated LLRs goes through
   ``tiles.attempt_tile`` -> ``tile_codec.cmy8_decode_stream`` at 150
   belief-propagation iterations. cmy8 is per-plane independent LDPC,
   so a stand-alone Y decode is bit-for-bit the codeword the colour
   path would decode. Zero-wrong is inherited from that gate (LDPC
   syndrome + CRC-32 + the address-bound slot permutation); every
   certificate is ALSO checked against the emitted payload.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

TILE = 64
Y_STREAM = "Y"
Y_PLANE = 2


@dataclass(frozen=True)
class Pose:
    """One committed window pose, as the archive recorded it."""

    capture_id: str
    level_index: int
    region_index: int
    extent_cells: tuple[int, int, int, int]
    page: int
    page_origin_yx: tuple[int, int]
    rot_k: int
    native_affine: tuple[float, ...]
    pitch_px: float
    route: str
    mismatch: float

    @property
    def window_id(self) -> tuple:
        return (self.capture_id, self.level_index, self.region_index,
                self.extent_cells)

    @property
    def shape_yx_cells(self) -> tuple[int, int]:
        y0, x0, y1, x1 = self.extent_cells
        return (y1 - y0, x1 - x0)

    def page_rect(self) -> tuple[int, int, int, int]:
        height, width = self.shape_yx_cells
        if self.rot_k % 2:
            height, width = width, height
        y0, x0 = self.page_origin_yx
        return (y0, x0, y0 + height, x0 + width)


def poses_from_events(rows: list[dict], capture_id: str,
                      level_index: int) -> list[Pose]:
    out: list[Pose] = []
    for event in rows:
        if (event.get("capture") != capture_id
                or int(event.get("level_index", -1)) != level_index
                or not event.get("accepted")):
            continue
        y0, x0, y1, x1 = (int(v) for v in event["extent_cells"])
        out.append(Pose(
            capture_id=capture_id, level_index=level_index,
            region_index=int(event["region_index"]),
            extent_cells=(y0, x0, y1, x1), page=int(event["page"]),
            page_origin_yx=tuple(int(v) for v in event["page_origin_yx"]),
            rot_k=int(event.get("rot_k", 0)),
            native_affine=tuple(float(v) for v in event["native_affine"]),
            pitch_px=float(event["pitch_px"]), route=str(event["route"]),
            mismatch=float(event["mismatch"])))
    out.sort(key=lambda pose: (pose.page_origin_yx, pose.extent_cells))
    return out


def poses_overlapping(poses: list[Pose],
                      cell_rect: tuple[int, int, int, int]) -> list[Pose]:
    """``cell_rect`` is (cy0, cy1, cx0, cx1), half open."""
    cy0, cy1, cx0, cx1 = cell_rect
    return [pose for pose in poses
            if (lambda r: r[0] < cy1 and r[2] > cy0
                and r[1] < cx1 and r[3] > cx0)(pose.page_rect())]


def region_pitch_px(poses: list[Pose]) -> float:
    from holo.receiver.plugins import calibrate

    return calibrate.region_pitch_px([pose.pitch_px for pose in poses])


def placement_of(pose: Pose, patch_ordinal: int):
    """A real ``data.Placement``, so holo3's own helpers can be used.

    The archive does not record ``local_cells_yx`` (the support-masked
    local cell list), so the full window rectangle is used. That is a
    SUPERSET of what the run itself sampled; cells outside the page are
    dropped by ``calibrate.window_page_cells`` and cells outside the
    raster refuse the window, so the difference can only cost coverage,
    never invent it.
    """
    from holo.receiver.data import Placement

    height, width = pose.shape_yx_cells
    grid_y, grid_x = np.meshgrid(np.arange(height, dtype=np.int64),
                                 np.arange(width, dtype=np.int64),
                                 indexing="ij")
    local = np.stack((grid_y.ravel(), grid_x.ravel()), axis=1)
    return Placement(
        window_id=pose.window_id, capture_id=pose.capture_id,
        level_index=pose.level_index, region_index=pose.region_index,
        patch_ordinal=patch_ordinal, page=pose.page, rot_k=pose.rot_k,
        page_origin_yx=pose.page_origin_yx,
        native_affine=pose.native_affine, pitch_px=pose.pitch_px,
        route=pose.route, local_cells_yx=local)


# --------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------


def shift_offsets_px(native_affine: tuple[float, ...], frame: Fraction,
                     shift_dots: float, cell_dots: int) -> np.ndarray | None:
    """A constant sampling offset of ``shift_dots`` along page +x."""
    from holo.receiver.lib.geometry import compose_from_native

    if shift_dots == 0.0:
        return None
    terms = np.asarray(compose_from_native(tuple(native_affine), frame),
                       np.float64).reshape(2, 3)
    delta_cells = np.array([0.0, shift_dots / float(cell_dots)])
    return (terms[:, :2] @ delta_cells).reshape(1, 2)


def sample_channels(planes, points_yx: np.ndarray,
                    raster_shape_yx: tuple[int, int],
                    pitch_px: float) -> np.ndarray:
    """(N, 3) aperture-filtered channel means, holo3's own sampler."""
    from holo.receiver.plugins import calibrate

    return np.stack([
        calibrate.sampled_window_means((planes[channel],), points_yx,
                                       raster_shape_yx, pitch_px)
        for channel in range(3)], axis=1).astype(np.float64)


# --------------------------------------------------------------------
# format truth at a window's cells
# --------------------------------------------------------------------


def window_truth(row, geometry, page: int, page_cells_yx: np.ndarray,
                 certificates: dict, memo: dict) -> tuple[np.ndarray,
                                                          np.ndarray,
                                                          np.ndarray]:
    """(bits (N, 3), known (N, 3), furniture_known (N, 3)).

    This is ``color_region.build_window_rows``' evidence half, called
    through the same two pure functions it calls, without its
    ``WindowRows`` container (which carries scan points this module
    computes for itself). The third return separates the FORMAT's own
    knowledge (word and dust sites, available on any page whatever the
    receiver has done) from what certificates add, so the two roles
    certified siblings play — regressors for the mixing fit, and labels
    for the calibration — can be ablated independently.
    """
    from holo.receiver.plugins.color_model import reference_states
    from holo.receiver.plugins.color_sites import certified_projection
    from holo.receiver.format.tile_codec import states_to_planes

    cells = np.asarray(page_cells_yx, np.int64)
    states, _kinds = reference_states(row, geometry, page, cells)
    bits = np.zeros((cells.shape[0], 3), np.uint8)
    known = np.zeros((cells.shape[0], 3), bool)
    furniture = states >= 0
    if np.any(furniture):
        bits[furniture] = states_to_planes(states[furniture])
        known[furniture] = True
    furniture_known = known.copy()
    tiles_x = row.tiles_yx[1]
    code = (cells[:, 0] // TILE) * tiles_x + cells[:, 1] // TILE
    for tile_code in np.unique(code):
        ty, tx = divmod(int(tile_code), tiles_x)
        if (page, ty, tx) not in memo:
            memo[(page, ty, tx)] = certified_projection(
                row, geometry, page, ty, tx, certificates)
        projection = memo[(page, ty, tx)]
        if projection is None:
            continue
        tile_bits, tile_known = projection
        selected = np.flatnonzero(code == tile_code)
        local_y = cells[selected, 0] % TILE
        local_x = cells[selected, 1] % TILE
        picked_bits = tile_bits[local_y, local_x]
        picked_known = tile_known[local_y, local_x]
        chosen = bits[selected]
        chosen[picked_known] = picked_bits[picked_known]
        bits[selected] = chosen
        known[selected] |= picked_known
    return bits, known, furniture_known


def y_labels(bits: np.ndarray, known: np.ndarray) -> np.ndarray:
    """int8 labels for the K-grade calibration: -1 where Y is unknown."""
    labels = np.full(bits.shape[0], -1, np.int8)
    selected = np.asarray(known, bool)[:, Y_PLANE]
    labels[selected] = np.asarray(bits, np.uint8)[selected, Y_PLANE]
    return labels


# --------------------------------------------------------------------
# the K-grade read
# --------------------------------------------------------------------


@dataclass
class WindowRead:
    ordinal: int
    pose: Pose
    page_cells_yx: np.ndarray
    values: np.ndarray
    bits: np.ndarray
    #: everything known: format furniture plus certified siblings.
    known: np.ndarray
    #: the format's own knowledge alone — word and dust sites.
    furniture_known: np.ndarray
    labels: np.ndarray
    cargo_mask: np.ndarray
    evidence: object | None = None

    def sibling_mask(self, siblings: str) -> np.ndarray:
        """Which knowledge the MIXING model may use as regressors."""
        return (self.furniture_known if siblings == "furniture"
                else self.known)


def read_windows(planes, poses: list[Pose], row, geometry, frame: Fraction,
                 pitch_px: float, cell_dots: int, certificates: dict,
                 shift_dots: float = 0.0,
                 labels_from: str = "certified") -> list[WindowRead]:
    """Sample every pose once; attach format truth and Y labels.

    ``labels_from="furniture"`` restricts the CALIBRATION labels to the
    format's own word and dust sites while leaving the mixing fit its
    certified regressors — the ablation that says which of the two jobs
    a certified neighbour is doing.
    """
    from holo.receiver.plugins import calibrate
    from holo.receiver.plugins.color_sites import cargo_row_indices

    raster_shape = (int(planes[0].shape[0]), int(planes[0].shape[1]))
    memo: dict = {}
    out: list[WindowRead] = []
    for ordinal, pose in enumerate(poses):
        placement = placement_of(pose, ordinal)
        page_cells = calibrate.window_page_cells(
            placement, pose.shape_yx_cells, row.cells_yx)
        if not page_cells.shape[0]:
            continue
        offsets = shift_offsets_px(pose.native_affine, frame, shift_dots,
                                   cell_dots)
        points = calibrate.scan_points_yx(pose.native_affine, frame,
                                          page_cells, offsets)
        if not calibrate.points_inside_raster(points, raster_shape):
            continue
        values = sample_channels(planes, points, raster_shape, pitch_px)
        bits, known, furniture_known = window_truth(
            row, geometry, pose.page, page_cells, certificates, memo)
        label_mask = (furniture_known if labels_from == "furniture"
                      else known)
        cargo = np.zeros(page_cells.shape[0], bool)
        cargo[cargo_row_indices(geometry, page_cells)] = True
        out.append(WindowRead(ordinal=ordinal, pose=pose,
                              page_cells_yx=page_cells, values=values,
                              bits=bits, known=known,
                              furniture_known=furniture_known,
                              labels=y_labels(bits, label_mask),
                              cargo_mask=cargo))
    return out


def window_heldout_logloss(read: WindowRead, unmix, mode: str,
                           siblings: str = "certified") -> float | None:
    """holo3's own model-selection number for one window's yellow read.

    ``fit_window_calibration`` splits the window's KNOWN labels by site
    parity and reports the log loss of the PAVA map on the half it did
    not see. Comparing that number across sampling offsets compares
    models on one fixed held-out label set — the ordinary use of a
    held-out score, and blind: the labels are the format's own dust
    states and whatever certified neighbours reach the window.
    """
    from holo.receiver.plugins import calibrate
    from . import _spectral

    score_y = _spectral.y_score(unmix, read.values, read.bits,
                                read.sibling_mask(siblings), mode)
    scores = calibrate.window_scores(np.asarray(-score_y, np.float32))
    fit = calibrate.fit_window_calibration(scores, read.labels,
                                           read.page_cells_yx)
    return fit.heldout_logloss if fit.accepted else None


def read_windows_best_shift(planes, poses: list[Pose], row, geometry,
                            frame: Fraction, pitch_px: float,
                            cell_dots: int, certificates: dict, unmix,
                            mode: str, shifts,
                            labels_from: str = "certified",
                            siblings: str = "certified",
                            ) -> tuple[list[WindowRead], list[dict]]:
    """Per-window sampling offset, chosen BLIND on held-out labels.

    The yellow plane's registration wanders across the page (e033's
    measured x-registration sinusoid, 0.83 dot peak, ~100 mm period), so
    one global offset cannot serve a live column and a dead one at
    once. This picks each window's own offset by the only blind
    criterion available — the window's held-out log loss on its own
    yellow labels, which in a dead band means the 20 dust sites per
    tile. That is the lead's "fill back tile addresses according to
    dust locations", used as a registration anchor rather than as an
    address.
    """
    chosen: dict[int, WindowRead] = {}
    best: dict[int, float] = {}
    picked: dict[int, float] = {}
    for shift in shifts:
        reads = read_windows(planes, poses, row, geometry, frame, pitch_px,
                             cell_dots, certificates, float(shift),
                             labels_from)
        for read in reads:
            index = read.ordinal
            loss = window_heldout_logloss(read, unmix, mode, siblings)
            if loss is None:
                continue
            if index not in best or loss < best[index]:
                best[index] = loss
                picked[index] = float(shift)
                chosen[index] = read
    ordered = [chosen[index] for index in sorted(chosen)]
    table = [{"window": list(chosen[index].pose.page_origin_yx),
              "shift_dots": picked[index],
              "heldout_logloss": best[index]}
             for index in sorted(chosen)]
    return ordered, table


def calibrate_reads(reads: list[WindowRead], unmix, mode: str,
                    siblings: str = "certified"):
    """holo3's PAVA fit per window, then its region context over them."""
    from holo.receiver.plugins import calibrate
    from . import _spectral

    rows = []
    for read in reads:
        score_y = _spectral.y_score(unmix, read.values, read.bits,
                                    read.sibling_mask(siblings), mode)
        # "as black on white": ink is DARK, so the synthetic luma is the
        # negated yellow presence. window_scores removes level and scale.
        scores = calibrate.window_scores(
            np.asarray(-score_y, np.float32))
        fit = calibrate.fit_window_calibration(scores, read.labels,
                                               read.page_cells_yx)
        placement = placement_of(read.pose, read.ordinal)
        read.evidence = calibrate._evidence(placement, read.page_cells_yx,
                                            scores, read.labels, fit)
        rows.append(read.evidence)
    corrected, ctx = calibrate.apply_region_context(tuple(rows))
    for read, evidence in zip(reads, corrected, strict=True):
        read.evidence = evidence
    return corrected, ctx


# --------------------------------------------------------------------
# the unchanged codec
# --------------------------------------------------------------------


def label_prior(evidence) -> float | None:
    """The class balance of the labels the window's PAVA map was fitted
    on. On a K page this is ~0.5 (word values are a BCH codeword under a
    keystream scramble); on the yellow plane it is ~0.11, because the
    100 word sites of every tile are yellow-BLANK by format law and only
    the 20 dust sites carry yellow marks."""
    labels = np.asarray(evidence.reference_values, np.int8)
    known = labels >= 0
    if not np.any(known):
        return None
    return float(labels[known].mean())


def evidence_llr(evidence, prior_correction: bool) -> np.ndarray:
    """The calibrated LLRs, optionally re-based on the payload's prior.

    A DELIBERATE DEVIATION from the K path, reported as one. holo3's
    calibration answers "what is P(this cell is inked | its score)"
    for a population whose class balance is the LABELS'. The payload
    cells' balance is 1/2 EXACTLY — an LDPC codeword under an AES
    keystream dither — and on a K page the two coincide, so nothing in
    holo3 ever had to correct for the difference. On the yellow plane
    they do not coincide, and the fitted LLRs carry the labels' 8:1
    bias against ink into the decoder. Subtracting the label prior's
    logit restores the payload's own prior; nothing else is touched,
    and the map stays the monotone one PAVA fitted.
    """
    llr = np.asarray(evidence.printed_llr, np.float64)
    if not prior_correction:
        return llr
    prior = label_prior(evidence)
    if prior is None or not 0.0 < prior < 1.0:
        return llr
    return llr - float(np.log(prior / (1.0 - prior)))


def tile_candidates(reads: list[WindowRead], geometry, page: int, ty: int,
                    tx: int, prior_correction: bool = False):
    from holo.receiver.plugins.color_sites import cargo_row_indices

    y0, x0 = ty * TILE, tx * TILE
    candidates = []
    order_keys = []
    for index, read in enumerate(reads):
        evidence = read.evidence
        if evidence is None or not evidence.accepted:
            continue
        cells = np.asarray(evidence.page_cells_yx, np.int64)
        selected = cargo_row_indices(geometry, cells)
        picked = cells[selected]
        llr = np.asarray(
            evidence_llr(evidence, prior_correction), np.float32)[selected]
        inside = ((picked[:, 0] >= y0) & (picked[:, 0] < y0 + TILE)
                  & (picked[:, 1] >= x0) & (picked[:, 1] < x0 + TILE))
        if not np.any(inside):
            continue
        values = np.zeros((int(np.count_nonzero(inside)), 3), np.float32)
        values[:, Y_PLANE] = llr[inside]
        candidates.append((index, page, picked[inside],
                           np.flatnonzero(inside), values))
        order_keys.append((float(evidence.heldout_logloss),
                           evidence.window_id[3],
                           int(evidence.region_index), 0))
    return candidates, order_keys


@dataclass
class Lane:
    """One capture's read of the case, at one resolution level."""

    capture_id: str
    level_index: int
    label: str
    reads: list[WindowRead]


def misaddressed_cut(cut, ty: int, tx: int):
    """The same evidence, relabelled as the tile next door.

    THE FALSE-ACCEPT PROBE. A tile's flat cell index is
    ``(y % 64) * 64 + (x % 64)``, so relabelling a neighbour's cut
    changes nothing about the LLR field — only the ADDRESS the codec
    decodes it under, and with it the slot permutation ``(a_t, b_t)``,
    the AES dither and the metadata equation. Well-calibrated evidence
    at the wrong address must never certify; if it ever does, the
    zero-wrong claim of every arm above is void.
    """
    from dataclasses import replace as dc_replace

    return dc_replace(cut, ty=ty, tx=tx)


def attempt_y_tile(lanes: list[Lane], row, geometry, page: int, ty: int,
                   tx: int, prior_correction: bool = False,
                   misaddress: tuple[int, int] | None = None):
    """One Y-stream attempt through the production codec, unchanged.

    Several lanes are the ordinary MULTI-CAPTURE UNION: one owner-frozen
    cut per capture, summed by ``tiles._combine`` exactly as
    ``tiles.prepare_union`` sums them. No new arithmetic — the same
    equal-weight LLR addition the receiver already performs, on
    de-correlated per-capture context (the F1 o F6 law).
    """
    from holo.receiver.plugins import tiles

    source_ty, source_tx = misaddress if misaddress is not None else (ty, tx)
    cuts = []
    for lane in lanes:
        candidates, order_keys = tile_candidates(
            lane.reads, geometry, page, source_ty, source_tx,
            prior_correction)
        if not candidates:
            continue
        cut = tiles.assemble_cut(candidates, order_keys, row.cells_yx,
                                 lane.capture_id, lane.level_index, page,
                                 source_ty, source_tx)
        if cut is None:
            continue
        cuts.append(cut if misaddress is None
                    else misaddressed_cut(cut, ty, tx))
    if not cuts:
        return None
    return tiles.attempt_tile(row, geometry, tuple(cuts), Y_STREAM,
                              tiles.STAGE_RETRY150)


def attempt_all(lanes: list[Lane], row, geometry, page: int, positions,
                prior_correction: bool = False,
                misaddress_by: tuple[int, int] | None = None) -> dict:
    started = time.perf_counter()
    results = {}
    for ty, tx in positions:
        source = (None if misaddress_by is None
                  else (ty + misaddress_by[0], tx + misaddress_by[1]))
        results[(ty, tx)] = attempt_y_tile(lanes, row, geometry, page, ty,
                                           tx, prior_correction, source)
    return {"results": results,
            "wall_seconds": time.perf_counter() - started}
