"""Format registry + blind format identification — acquire-v2 (decoder-axis).

LAYERS.md §0 defines the FormatDescriptor; until now it was "played
per-experiment" by each gen_eNNN hand-building a ComposeSpec. This module
reifies it: a registry row = the COMPLETE tuple a receiver needs to
hypothesis-test one printed format (PILOTS-DESIGN doctrine: "every registry
entry is a complete FormatDescriptor — no partial format sharing").

Identification contract (implicit format signaling, R5):
- the pilot VALUE scramble label (b"pilot-values-v<N>/<plane>") IS the
  format identity; a wrong (seed, version-label, plane) reads coin flips
  and the BCH word gate rejects cleanly — measured 0/200k random-word FA
  (v2), 0 false accepts on real scans (012.3), and C_v3 subset C_v2 nesting
  never bites because labels differ before the code is reached.
- the scramble is PITCH- and GEOMETRY-BLIND: it cannot separate two
  hypotheses sharing (seed, version, plane) but differing in encoding or
  page_cells. Discrimination there rides (a) the measured absolute cell
  pitch (600 dpi print => c2 = 84.7 um, c3 = 127 um, c4 = 169 um — well
  separated vs the +-0.6% worst measured scanner scale) and (b) Stage-B
  neighbor arithmetic. KNOWN HOLE (measured in the acquire-v2 read): a
  wrong page WIDTH with the right seed can pass Stage B on same-row
  neighbors alone (v3 counter c+-1 is tiles_x-invariant); y-neighbor
  confirmation is reported as geometry_confirmed on ScanAcquireResult —
  as printed there is no colliding pair (all sheets differ in seed), so
  this is a diagnostic, not a gate.

Registry rows carry a DEFAULT seed for the known printed sheets; callers
supply their own seed for new volumes (the seed is the key, never guessed).
E018b is the declared exception: its two generic payload profiles carry
fixed public FORMAT keys so the receiver knows them before payload recovery.
Those keys do not identify a payload instance; an E018b session must bind one
physical sheet/volume and verify its sidecar length/hash.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from paperholo import acquire, compose, scannorm
from paperholo.dust import DustLayout
from paperholo.pilots import PilotLayout


@dataclass(frozen=True)
class FormatDescriptor:
    """One complete printed-format hypothesis (format axis, immutable).

    v4 (cmy8) rows carry the training-dust layout too (D7: layout_version 4
    = {cmy8-c3, p60b6 sites, v4 value labels, dust}); identification stays
    LUMA — scannorm.reduce_plane falls back to luma for plane "CMY" and the
    v4 word channel is plane-"K" by design."""

    format_id: str                 # e.g. "arch-v3-c3" — registry key
    seed: bytes                    # per-sheet key (callers may override)
    layout_version: int
    encoding_id: str               # -> cell_dots via the encodings registry
    page_cells_yx: tuple[int, int]
    plane: str = "K"
    notes: str = ""
    dust: DustLayout | None = None   # v4 only
    # LDPC rate rung the sheet was PRINTED at (a format fact, not a decode
    # knob — e023 review F5: a wrong CLI rate silently certifies nothing).
    # None = the sheet carries no LDPC payload layer (e011/e012/e014) or the
    # rate is per-level (e017: rungs live in COLOR-DESIGN P5, out of the
    # single-level v1 scope).
    ldpc_rate: str | None = None

    def spec(self) -> compose.ComposeSpec:
        return compose.ComposeSpec(
            layout_version=self.layout_version,
            encoding_id=self.encoding_id,
            plane=self.plane,
            pilot=PilotLayout(version=self.layout_version),
            page_cells_yx=self.page_cells_yx,
            dust=self.dust)

    @property
    def cell_dots(self) -> int:
        return self.spec().cell_dots

    @property
    def cell_pitch_mm(self) -> float:
        """Physical cell pitch (600 dpi print — every registered format)."""
        return self.cell_dots * 25.4 / 600.0


# the printed archive sheets to date (seeds from their gen_e01N.py)
FORMAT_REGISTRY: tuple[FormatDescriptor, ...] = (
    FormatDescriptor("e012-v3-c3", b"paper-store/exp012-pilot1", 3,
                     "kcell-c3", (2220, 1500),
                     notes="ARCH-1 A4 archive sheet (012.3 hw-validated)"),
    FormatDescriptor("e014-v3-c2", b"paper-store/exp014-c2", 3,
                     "kcell-c2", (3300, 2220),
                     notes="ARCH-2 c2 A4 sheet (encode-side; blind = new)"),
    FormatDescriptor("e011-v2-c3", b"paper-store/exp011-pilot1", 2,
                     "kcell-c3", (2220, 1500),
                     notes="exp-011 layout_version-2 page (never printed)"),
    FormatDescriptor("e016-v3-c2", b"paper-store/exp016-arch3", 3,
                     "kcell-c2", (3300, 2220),
                     notes="ARCH-3 coded c2 volume (fountain-v1 + LDPC "
                           "r0550; printed 016.1)",
                     ldpc_rate="r0550"),
    # ARCH-C color page (layout_version 4). Dust density FROZEN by probe P3
    # (run 017.0): 0.5% of cells = 18 sites per 60x60 pilot tile, pure_quota
    # 3 (0.25% measured label-sufficient at the <=0.03 b/cell bar on both
    # engines, knee ~0.1%; 0.5% carries 2x safety and funds the P4
    # registration job). Pinned by the gen_e017 golden. Identification
    # stays luma (v4 words are K-plane).
    FormatDescriptor("e017-v4-cmy8", b"paper-store/exp017-color", 4,
                     "cmy8-c3", (2220, 1500), plane="CMY",
                     notes="ARCH-C cmy8 color volume (COLOR-DESIGN D1-D7; "
                           "unprinted — sim/build stage)",
                     dust=DustLayout(sites_per_tile=18, pure_quota=3)),
    # CONFETTI-C3-PLAY (printed 2026-07-11, volume recovered byte-exact
    # 018.10). Seed matches gen_e018.py SEED — registered here so e022's
    # drivers stop retyping it (the 012.3 drifted-reimplementation class).
    # Appended LAST: it shares e012's geometry/encoding, so identification
    # order keeps e012 first for equal-seed test candidates.
    FormatDescriptor("e018-v3-c3", b"paper-store/exp018-confetti-c3", 3,
                     "kcell-c3", (2220, 1500),
                     notes="CONFETTI-C3-PLAY c3 K play volume (e012 "
                           "geometry; printed + recovered 018.10)",
                     ldpc_rate="r0550"),
    # Generic E018b payload-sheet profiles. Unlike e018's one-off volume,
    # these keys are FORMAT CONSTANTS and deliberately do not depend on the
    # payload hash: a receiver can identify the sheet and know its pilot /
    # scramble / fountain key before recovering any payload bytes. Data
    # length + expected hash remain volume-descriptor facts in the sidecar
    # manifest (R5).
    FormatDescriptor("e018b-v3-c3",
                     b"paper-store/018b-c3-r0550-0.5", 3,
                     "kcell-c3", (2220, 1500),
                     notes="generic E018b c3 K payload sheet; fixed public "
                           "r0550 / K/N<=0.5 key",
                     ldpc_rate="r0550"),
    FormatDescriptor("e018b-v3-c2",
                     b"paper-store/018b-c2-r0550-0.5", 3,
                     "kcell-c2", (3300, 2220),
                     notes="generic E018b c2 K payload sheet; fixed public "
                           "r0550 / K/N<=0.5 key",
                     ldpc_rate="r0550"),
)


@dataclass
class ScanAcquireResult:
    """acquire_scan outcome: identified format + the window's decode."""

    ok: bool
    fmt: FormatDescriptor | None = None
    pitch: scannorm.PitchMeasurement | None = None
    pitch_hyp_px: float = 0.0      # the ACCEPTED cell-pitch hypothesis
    norm: scannorm.NormalizedScan | None = None
    result: acquire.AcquireResult | None = None    # canonical-footing decode
    geometry_confirmed: bool = False   # >=1 y-neighbor pilot tile decoded
    tried: list = field(default_factory=list)      # (format_id, failed_stage)
    diagnostics: dict = field(default_factory=dict)


def _cell_pitch_hypotheses(pitch: scannorm.PitchMeasurement,
                           fmt: FormatDescriptor,
                           scan_dpi: float | None) -> list[float]:
    """Candidate CELL pitches (scan px) for one format hypothesis.

    A credible spectral line may be the cell lattice, the DOT lattice, or a
    harmonic of either (measured: geometry=True c2 at 4 px/dot puts its
    strongest line at 2.00 px = dot 2nd harmonic; a clean 24 px/cell page
    puts its 3rd harmonic above its fundamental). So: every strong line p
    times every multiplier m in 1..2*cell_dots is a cell-pitch hypothesis;
    with trusted scan_dpi they are pruned to +-10% of the format's physical
    pitch (registry pitches are >=33% apart; worst measured scanner scale
    error +-0.6%), else deduped and capped. The BCH word gate downstream is
    the arbiter — a wrong hypothesis costs one clean rejection."""
    lines = list(pitch.strong) or [(pitch.pitch_px, pitch.contrast)]
    # strongest source lines first, small multipliers first — the reviewed
    # failure mode was an ascending-pitch global cap evicting the true cell
    # pitch behind low-pitch junk lines (measured on the Canon 2400 scan
    # without scan_dpi: true 12.05 px evicted by {3.34, 4.16} multiples)
    lines.sort(key=lambda t: -t[1])
    scored: list[tuple[float, float]] = []     # (rank_score, hypothesis)
    for rank, (p, _) in enumerate(lines[:3]):
        for m in range(1, 2 * fmt.cell_dots + 1):
            h = p * m
            if h < scannorm.MIN_CELL_PX * (1.0 - scannorm.CAPTURE_BAND):
                continue
            if all(abs(h / h0 - 1.0) > 0.02 for _, h0 in scored):
                scored.append((rank + 0.1 * m, h))
    hyps = [h for _, h in scored]
    if scan_dpi is not None:
        target_px = scan_dpi * fmt.cell_dots / 600.0   # 600 dpi print
        hyps = [h for h in hyps if abs(h / target_px - 1.0) <= 0.10]
        hyps.sort(key=lambda h: abs(h / target_px - 1.0))
        return hyps[:4]
    scored.sort(key=lambda t: t[0])
    return [h for _, h in scored][:6]


def _shortlist(pitch: scannorm.PitchMeasurement, scan_dpi: float | None,
               candidates: Sequence[FormatDescriptor]
               ) -> list[tuple[FormatDescriptor, float]]:
    """(format, cell_pitch_hypothesis) pairs to try, best-first."""
    out: list[tuple[FormatDescriptor, float]] = []
    for fmt in candidates:
        for h in _cell_pitch_hypotheses(pitch, fmt, scan_dpi):
            out.append((fmt, h))
    return out


def _find_field_bbox(img: np.ndarray, cell_px: int
                     ) -> tuple[int, int, int, int] | None:
    """Locate the printed field (ink-dark rectangle) in a normalized scan
    by per-axis darkness profiles: threshold 30% below paper white toward
    the field level, take the longest run per axis. Returns (y0, y1, x0,
    x1) px or None when no credible field exists (callers fall back to
    whole-image tiling). Accuracy is a few cells — window ALIGNMENT only,
    never addressing (addresses always come from the pilots)."""
    out = []
    for ax in (1, 0):                       # rows first (y), then cols (x)
        prof = img.mean(axis=ax)
        k = max(2 * cell_px, 8)
        prof = np.convolve(prof, np.ones(k) / k, mode="same")
        white = float(np.quantile(prof, 0.98))
        field = float(np.quantile(prof, 0.10))
        if white - field < 0.05:            # no ink contrast anywhere
            return None
        inside = prof < white - 0.3 * (white - field)
        idx = np.flatnonzero(inside)
        if idx.size < 64 * cell_px:         # under a tile of field: refuse
            return None
        brk = np.flatnonzero(np.diff(idx) > 1)
        starts = np.r_[idx[0], idx[brk + 1]]
        ends = np.r_[idx[brk], idx[-1]]
        li = int(np.argmax(ends - starts))
        out.append((int(starts[li]), int(ends[li]) + 1))
    (y0, y1), (x0, x1) = out
    return y0, y1, x0, x1


def _mirror_pad_field(img: np.ndarray, bbox: tuple[int, int, int, int],
                      pad_px: int) -> tuple[int, int, int, int]:
    """Reflect a strip of in-field content outward into the blank margins
    (016.2 boundary finding: field-edge cells read 37/22/19/15% for cells
    0-3 — margin-white neighbors starve the ctx detector and the local
    grid; a mirrored strip gives them in-distribution context AFTER the
    scan, printing nothing). Mutates img's margin regions in place;
    corners stay blank. Returns the padded bbox. The mirrored strip
    carries no addressable payload — mirrored pilot words are not valid
    codewords under the value scramble, so the BCH gate rejects them."""
    h, w = img.shape
    y0, y1, x0, x1 = bbox
    pt = min(pad_px, y0, y1 - y0)
    pb = min(pad_px, h - y1, y1 - y0)
    pl = min(pad_px, x0, x1 - x0)
    pr = min(pad_px, w - x1, x1 - x0)
    if pt > 0:
        img[y0 - pt:y0, x0:x1] = img[y0:y0 + pt, x0:x1][::-1]
    if pb > 0:
        img[y1:y1 + pb, x0:x1] = img[y1 - pb:y1, x0:x1][::-1]
    if pl > 0:
        img[y0:y1, x0 - pl:x0] = img[y0:y1, x0:x0 + pl][:, ::-1]
    if pr > 0:
        img[y0:y1, x1:x1 + pr] = img[y0:y1, x1 - pr:x1][:, ::-1]
    return y0 - pt, y1 + pb, x0 - pl, x1 + pr


def _y_neighbor_confirmed(res: acquire.AcquireResult) -> bool:
    """True iff the post-fold word decode succeeded on >=2 pilot tiles in
    the same COLUMN (different ty) — the Stage-B geometry hole closes only
    with a y-neighbor, because the v3 counter's x-neighbor arithmetic is
    tiles_x-invariant (acquire-v2 read, §4)."""
    ok_tiles = [t for t, nerr in res.tile_words.items() if nerr >= 0]
    cols: dict[int, set[int]] = {}
    for ty, tx in ok_tiles:
        cols.setdefault(tx, set()).add(ty)
    return any(len(tys) >= 2 for tys in cols.values())


def acquire_scan(img: np.ndarray, *,
                 candidates: Sequence[FormatDescriptor] = FORMAT_REGISTRY,
                 seed: bytes | None = None,
                 scan_dpi: float | None = None,
                 include_mirror: bool = False,
                 anchor_rounds: int = 2,
                 detector: str = "global",
                 calibrate: bool = False,
                 color_features: str = "rgb") -> ScanAcquireResult:
    """Fully blind scan-to-decode: measure -> shortlist -> hypothesis-test.

    img: 2-D grey or 3-D RGB scan window (any resolution the px/cell ladder
    admits). seed overrides every candidate's registry seed (one seed, many
    format shapes — the new-volume pattern). scan_dpi, when trusted, prunes
    the shortlist by absolute pitch; without it every candidate is tried at
    its own rescale hypothesis (the BCH gate rejects wrong ones cleanly).

    Color formats (n_levels == 3): identification stays LUMA (v4 words are
    plane-"K" by design); when img is 3-D the RGB channels are normalized
    with the SAME resample the luma footing froze and threaded to the color
    payload stage. A GREY scan of a color page still identifies + addresses
    (diagnostics carry color_payload_pending — the payload needs RGB).
    """
    t0 = time.perf_counter()
    if img.size > 700_000_000:
        raise ValueError(
            "acquire_scan is a WINDOW-level API (this image is "
            f"{img.size/1e6:.0f} Mpx) — use page_decode, or pass a crop")
    out = ScanAcquireResult(ok=False)
    tried_planes: dict[str, scannorm.PitchMeasurement] = {}
    reduced: dict[str, np.ndarray] = {}
    cands = list(candidates)
    if seed is not None:
        cands = [FormatDescriptor(f.format_id, seed, f.layout_version,
                                  f.encoding_id, f.page_cells_yx, f.plane,
                                  f.notes, f.dust) for f in cands]
    # measure pitch once per distinct plane reduction (K for everything today)
    for fmt in cands:
        if fmt.plane not in reduced:
            reduced[fmt.plane] = scannorm.reduce_plane(img, fmt.plane)
            try:
                tried_planes[fmt.plane] = scannorm.measure_cell_pitch(
                    reduced[fmt.plane])
            except scannorm.ScanRefused as e:
                out.tried.append((fmt.format_id, f"pitch: {e}"))
                continue
    if not tried_planes:
        out.diagnostics["failed_stage"] = "pitch"
        out.diagnostics["timings_s"] = {"total": time.perf_counter() - t0}
        return out
    rgb_in = img if (img.ndim == 3 and img.shape[2] >= 3) else None
    # shortlist per plane group, then hypothesis-test
    for plane, pitch in tried_planes.items():
        group = [f for f in cands if f.plane == plane]
        for fmt, pitch_hyp in _shortlist(pitch, scan_dpi, group):
            try:
                norm = scannorm.normalize_to_canonical(
                    reduced[plane], pitch_hyp, fmt.cell_dots)
            except scannorm.ScanRefused as e:
                out.tried.append((fmt.format_id, f"normalize: {e}"))
                continue
            spec = fmt.spec()
            color_kwargs: dict = {}
            if spec.n_levels == 3 and rgb_in is not None:
                # SAME resample as the luma footing (see acquire's D5 note)
                color_kwargs = {
                    "rgb": scannorm.normalize_to_canonical_rgb(rgb_in, norm),
                    "color_features": color_features}
            res = acquire.acquire_and_decode(
                norm.img, spec, fmt.seed,
                include_mirror=include_mirror, anchor_rounds=anchor_rounds,
                cell_px_nominal=norm.cell_px_est,
                detector=detector, calibrate=calibrate, **color_kwargs)
            if res.ok:
                out.ok = True
                out.fmt = fmt
                out.pitch = pitch
                out.pitch_hyp_px = pitch_hyp
                out.norm = norm
                out.result = res
                out.geometry_confirmed = _y_neighbor_confirmed(res)
                out.diagnostics["timings_s"] = {
                    "total": time.perf_counter() - t0}
                return out
            out.tried.append(
                (fmt.format_id, res.diagnostics.get("failed_stage")))
    out.diagnostics["failed_stage"] = "all_formats_rejected"
    out.diagnostics["timings_s"] = {"total": time.perf_counter() - t0}
    return out


def _win_coverage(int_img: np.ndarray, y0: int, x0: int, side: int
                  ) -> float:
    """Window mask-coverage from a zero-padded integral image."""
    y1, x1 = y0 + side, x0 + side
    s = (int_img[y1, x1] - int_img[y0, x1]
         - int_img[y1, x0] + int_img[y0, x0])
    return float(s) / float(side * side)


def _top_coverage_windows(mask: np.ndarray, side: int, n: int,
                          min_cov: float, min_sep: int
                          ) -> list[tuple[int, int, float]]:
    """Greedy top-N (y0, x0, cov) window origins by mask coverage on a
    side//4 stride grid, separated by >= min_sep px (§15.6 I1: ID-retry
    and mask-snapped window candidates)."""
    H, W = mask.shape
    if H < side or W < side:
        return []
    ii = np.pad(np.cumsum(np.cumsum(
        mask.astype(np.float64), 0), 1), ((1, 0), (1, 0)))
    stride = max(1, side // 4)
    cands = []
    for y0 in range(0, H - side + 1, stride):
        for x0 in range(0, W - side + 1, stride):
            cov = _win_coverage(ii, y0, x0, side)
            if cov >= min_cov:
                cands.append((cov, y0, x0))
    cands.sort(reverse=True)
    out: list[tuple[int, int, float]] = []
    for cov, y0, x0 in cands:
        if all(abs(y0 - oy) >= min_sep or abs(x0 - ox) >= min_sep
               for oy, ox, _ in out):
            out.append((y0, x0, cov))
            if len(out) >= n:
                break
    return out


def page_decode(img: np.ndarray, *, scan_id: str,
                state: "object | None" = None,
                candidates: Sequence[FormatDescriptor] = FORMAT_REGISTRY,
                seed: bytes | None = None,
                scan_dpi: float | None = None,
                window_cells: int = 600, overlap_cells: int = 60,
                id_window_px: int | None = None,
                align_to_field: bool = False,
                mirror_pad_cells: int = 0,
                anchor_rounds: int = 2,
                detector: str = "global",
                calibrate: bool = False,
                color_features: str = "rgb",
                mask: np.ndarray | None = None,
                mask_min_cov: float = 0.65,
                id_retry: int = 0,
                fold_id_window: bool = False
                ) -> tuple[ScanAcquireResult, object]:
    """Whole-scan decode into a PageDecodeState (acquire-v2 driver).

    Identifies the format on a central window (acquire_scan), then tiles the
    NORMALIZED image with overlapping windows, blind-acquires each (absolute
    addressing per window — windows that fail are skipped, they are margin/
    blank/damage), and folds every ok window into the map under one scan_id.
    Pass an existing PageDecodeState as `state` to accumulate further scans
    (F6); its (spec, seed, page) must match the identified format.

    §15.6 options (all default-off; regression identity preserved):
    mask — bool array in the RAW img frame (piece interior, e.g. a
    confetti scrap on backing). Tiling windows below mask_min_cov
    coverage are skipped (measured stage-A pass boundary ~0.7 — the
    bbox-anchored grid put 6/6 of a rotated triangle's windows at
    0.35-0.62 on backing, 018.2) and mask-snapped top-coverage window
    candidates are ADDED on a quarter-stride grid.
    id_retry — on central-ID failure, retry acquire_scan at up to N
    top-mask-coverage crops before giving up (measured: id-crop
    coverage does NOT predict id success — retry-elsewhere is the fix,
    not center-on-ink). Requires mask.
    fold_id_window — a SUCCESSFUL identification window is a decoded
    window like any other: fold it into the state instead of
    discarding it (018.2: p8's ID crop decoded 8/9 words and was
    thrown away).

    Returns (identification, PageDecodeState). Higher layers then run
    state.decode_tiles(...) / certified_results() — see paperholo.tilemap.
    """
    from paperholo import tilemap  # local import: keep module DAG flat

    # identify on a central crop (a wrong hypothesis must not pay a
    # full-page lock; review finding), then normalize the FULL image once.
    # id_window_px caps the crop: c2 needs ~25 mm windows (014.1: a 40 mm
    # window vetoed at 29% BER from warp accumulation while 25 mm read 8%),
    # and the 4096 px default is 43 mm at the 8 px/cell footing.
    H0, W0 = img.shape[:2]
    id_px = min(H0, W0, id_window_px or 4096)
    ident = acquire_scan(
        np.ascontiguousarray(img[(H0 - id_px) // 2:(H0 + id_px) // 2,
                                 (W0 - id_px) // 2:(W0 + id_px) // 2]),
        candidates=candidates, seed=seed, scan_dpi=scan_dpi,
        anchor_rounds=anchor_rounds, detector=detector, calibrate=calibrate,
        color_features=color_features)
    if (not ident.ok and id_retry > 0 and mask is not None
            and mask.shape[:2] == img.shape[:2]):
        # §15.6 I1: the central crop is one sample, not a verdict.
        # (Retry needs the mask in the RAW frame; a mismatched-shape
        # mask silently skips retry rather than mis-cropping.)
        for (ry, rx, cov) in _top_coverage_windows(
                np.asarray(mask, bool), id_px, id_retry,
                min_cov=mask_min_cov, min_sep=id_px // 2):
            retry = acquire_scan(
                np.ascontiguousarray(img[ry:ry + id_px, rx:rx + id_px]),
                candidates=candidates, seed=seed, scan_dpi=scan_dpi,
                anchor_rounds=anchor_rounds, detector=detector,
                calibrate=calibrate, color_features=color_features)
            if retry.ok:
                retry.diagnostics["id_retry_origin_px"] = (ry, rx)
                retry.diagnostics["id_retry_cov"] = cov
                ident = retry
                break
    if not ident.ok:
        return ident, state
    fmt = ident.fmt
    spec = fmt.spec()
    # NOTE memory ceiling: the full-page float reduction is materialized
    # here (~4.5 GB for an A4 2400 dpi grey scan, 4x that for a color page's
    # luma + RGB channels; 4800 dpi whole-page needs pre-decimation or the
    # windowed hardware-scorer path — chunked normalization is queued
    # follow-up work).
    norm_full = scannorm.normalize_to_canonical(
        scannorm.reduce_plane(img, fmt.plane), ident.pitch_hyp_px,
        fmt.cell_dots)
    rgb_full = None
    if spec.n_levels == 3 and img.ndim == 3 and img.shape[2] >= 3:
        rgb_full = scannorm.normalize_to_canonical_rgb(img, norm_full)
    cell_px = int(round(ident.norm.cell_px_est))
    win_px = window_cells * cell_px
    stride_px = max(1, (window_cells - overlap_cells) * cell_px)
    H, W = norm_full.img.shape
    if state is None:
        state = tilemap.PageDecodeState(spec, fmt.seed,
                                        page=ident.result.page)
    elif state.spec != spec or state.seed != fmt.seed:
        raise ValueError("supplied PageDecodeState (spec, seed) does not "
                         "match the identified format")
    n_ok = 0
    # window grid: align to the printed field when asked (016.2 finding:
    # image-anchored tiling leaves boundary windows ~40% blank margin ->
    # Stage A fails -> an evidence desert over the outermost ~2 tile
    # rows/cols). mirror_pad_cells additionally reflects field content
    # into the margins so field-edge cells decode with in-distribution
    # ctx neighborhoods (mutates the internal reduced image's margins).
    bbox = None
    if align_to_field or mirror_pad_cells:
        bbox = _find_field_bbox(norm_full.img, cell_px)
        ident.diagnostics["field_bbox_px"] = bbox
        if bbox is not None and mirror_pad_cells > 0:
            bbox = _mirror_pad_field(norm_full.img, bbox,
                                     mirror_pad_cells * cell_px)
            ident.diagnostics["field_bbox_padded_px"] = bbox
    if bbox is not None:
        fy0, fy1, fx0, fx1 = bbox
        fy0, fx0 = max(0, fy0), max(0, fx0)
        fy1, fx1 = min(H, fy1), min(W, fx1)
        y_hi = max(fy1 - win_px, fy0)
        x_hi = max(fx1 - win_px, fx0)
        ys = list(range(fy0, y_hi + 1, stride_px))
        xs = list(range(fx0, x_hi + 1, stride_px))
        if ys[-1] < y_hi:
            ys.append(y_hi)
        if xs[-1] < x_hi:
            xs.append(x_hi)
        ys = [min(max(0, y), max(0, H - win_px)) for y in ys]
        xs = [min(max(0, x), max(0, W - win_px)) for x in xs]
    else:
        ys = list(range(0, max(H - win_px, 0) + 1, stride_px)) or [0]
        xs = list(range(0, max(W - win_px, 0) + 1, stride_px)) or [0]
        # ensure the far edges are covered
        if ys[-1] + win_px < H:
            ys.append(H - win_px)
        if xs[-1] + win_px < W:
            xs.append(W - win_px)
    origins = [(y0, x0) for y0 in ys for x0 in xs]
    nm_full = None                 # resampled piece mask (normalized frame)
    if mask is not None:
        # §15.6 mask-aware grid: resample the RAW-frame mask onto the
        # normalized image, drop grid windows below mask_min_cov, ADD
        # mask-snapped top-coverage candidates (quarter-stride greedy)
        m = np.asarray(mask, bool)
        yy = np.clip((np.arange(H) * m.shape[0] / H).astype(int),
                     0, m.shape[0] - 1)
        xx = np.clip((np.arange(W) * m.shape[1] / W).astype(int),
                     0, m.shape[1] - 1)
        nm = m[yy][:, xx]
        nm_full = nm            # keep for per-window emission masking below
        ii = np.pad(np.cumsum(np.cumsum(
            nm.astype(np.float64), 0), 1), ((1, 0), (1, 0)))
        if H >= win_px and W >= win_px:
            kept = [(y0, x0) for (y0, x0) in origins
                    if _win_coverage(ii, y0, x0, win_px) >= mask_min_cov]
        else:
            # sub-window image (elongated piece narrower than one
            # window): the fallback grid already clamps origins — keep
            # it whole rather than index past the integral image
            # (review-confirmed crash, 018.3)
            kept = list(origins)
        snapped = [(y0, x0) for (y0, x0, _c) in _top_coverage_windows(
            nm, win_px, n=32, min_cov=max(mask_min_cov, 0.7),
            min_sep=max(1, stride_px // 2))]
        seen = set(kept)
        for o in snapped:
            if o not in seen:
                kept.append(o)
                seen.add(o)
        ident.diagnostics["mask_windows"] = {
            "grid": len(origins), "kept": len(kept) - len(
                [o for o in snapped if o not in set(origins)]),
            "snapped_added": len([o for o in snapped
                                  if o not in set(origins)])}
        origins = kept
    if fold_id_window and ident.result is not None:
        res0 = ident.result
        if (res0.ok and res0.page == state.page
                and not res0.diagnostics.get("color_payload_pending")):
            state.add_acquire_result(scan_id, res0)
            n_ok += 1
    for (y0, x0) in origins:
        win = np.ascontiguousarray(
            norm_full.img[y0:y0 + win_px, x0:x0 + win_px])
        color_kwargs: dict = {}
        if rgb_full is not None:
            color_kwargs = {
                "rgb": np.ascontiguousarray(
                    rgb_full[y0:y0 + win_px, x0:x0 + win_px]),
                "color_features": color_features}
        res = acquire.acquire_and_decode(
            win, spec, fmt.seed, anchor_rounds=anchor_rounds,
            cell_px_nominal=float(cell_px),
            detector=detector, calibrate=calibrate,
            cell_mask=(nm_full[y0:y0 + win_px, x0:x0 + win_px]
                       if nm_full is not None else None),
            **color_kwargs)
        if (res.ok and res.page == state.page
                and not res.diagnostics.get("color_payload_pending")):
            # a grey scan of a color page addresses but carries no
            # color payload — nothing to fold into the map
            state.add_acquire_result(scan_id, res)
            n_ok += 1
    ident.diagnostics["n_windows_ok"] = n_ok
    ident.diagnostics["n_windows_tried"] = len(origins)
    state.note_scan_added()          # marginal-utility bookkeeping (F6 loop)
    return ident, state
