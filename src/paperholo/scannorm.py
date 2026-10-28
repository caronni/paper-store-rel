"""Scan normalization front end — the acquire-v2 input stage (decoder-axis).

Turns AN ARBITRARY SCAN (300-4800 dpi, grey or RGB, unknown placement) into
a canonical decode footing: one plane-reduced 2-D reflectance image whose
cell pitch lands on the px/cell LADDER (CANONICAL_CELL_PX = 6 or 8 px/cell,
+-4% = the lock_grid capture band). Three stages:

1. reduce_plane: RGB -> the format hypothesis' plane channel (measured
   channel convention: C reads best in R, M in G, Y in B; K = luma). Grey
   passes through. 16-bit inputs normalized honestly (not the /255-iff->1.5
   heuristic acquire._normalize_refl applies to 8-bit).
2. measure_cell_pitch: blind lattice pitch in scan px over a WIDE band —
   an octave ladder of gradient-magnitude zoom-DFT probes (the lock_grid
   Stage-0 machinery, freed from its single 6 px nominal). Returns the
   dominant coherent lattice pitch + a confidence contrast; the caller maps
   pitch_px x scan_dpi -> absolute cell pitch -> encoding shortlist
   (paperholo.formats).
3. normalize_to_canonical: rational box-average resample (aperture-honest —
   the 012.3 pattern; NEVER spline: order>=3 rings on binary content and a
   second interpolation is one more than a real scanner has) landing the
   measured pitch within the +-4% capture band of a CANONICAL_CELL_PX
   footing, preferring the least resampling.
   Upsampling (np.repeat) adds no information and is applied only from the
   3 px/cell marginal floor; below MIN_CELL_PX the input is REFUSED with
   diagnostics (a 300 dpi scan of a c3@600 print = 1.5 px/cell is
   information-theoretically dead — say so, don't flail).

px/cell ladder doctrine (LAYERS.md riders): 6 solid / 4 marginal / 2
Nyquist-edge / <2 dead — MIN_CELL_PX=3.0 is the refuse floor, [3,4) is
flagged marginal in the result.

Determinism: no RNG anywhere. All functions are pure.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from paperholo.sync import estimate_lattice

MIN_CELL_PX = 3.0          # refuse below (measured-degraded floor, see doc)
MARGINAL_CELL_PX = 4.0     # [MIN, MARGINAL) decodes but is flagged
CAPTURE_BAND = 0.04        # lock_grid's pitch capture half-width (+-4%)
# octave probe ladder for the blind pitch search (px/cell nominals); spans
# c2@600dpi-scan (2 px/cell, below floor -> measured then refused) through
# c3@4800 (24 px/cell) with half-octave steps so every true pitch lies
# within estimate_lattice's capture band of some probe
PITCH_PROBES_PX = (2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0)

# plane -> RGB channel reduction (measured convention: A3 state fields score
# per-cell r,g,b core density; C rides R, M rides G, Y rides B, K = luma)
_PLANE_CHANNEL = {"C": 0, "M": 1, "Y": 2}


@dataclass(frozen=True)
class PitchMeasurement:
    """Blind lattice measurement on a plane-reduced scan.

    pitch_px is the integer-ratio-consistent FUNDAMENTAL of the credible
    spectral lines — but on real channels that fundamental may be the DOT
    lattice, not the cell lattice (toner dot rows resolve optically at high
    dpi; the sim's bilinear resample kinks at dot boundaries the same way —
    measured during the acquire-v2 build: a geometry=True c2 scan at
    4 px/dot measures 2.00 px, the dot lattice's 2nd harmonic, while the
    8 px cell line hides beneath it). `strong` carries every credible line
    so the FORMAT hypothesis (which knows cell_dots) can enumerate cell-
    pitch interpretations and let the BCH word gate arbitrate."""

    pitch_px: float            # fundamental of the credible lines, scan px
    angle_rad: float           # lattice angle (folded to (-pi/4, pi/4])
    contrast: float            # peak/median spectral contrast (confidence)
    probe_px: float            # == pitch_px (historical name; the chosen
    #   fundamental, not the ladder probe)
    candidates: tuple[tuple[float, float], ...]  # (pitch_px, contrast) all probes
    strong: tuple[tuple[float, float], ...] = ()  # credible lines (deduped)


@dataclass(frozen=True)
class NormalizedScan:
    """Canonical-footing image + the bookkeeping to invert it."""

    img: np.ndarray            # 2-D float, ~2 px/dot, ink-dark reflectance
    scale_num: int             # canonical px = scan px * scale_num/scale_den
    scale_den: int
    cell_px_est: float         # measured pitch AFTER rescale (target 2*cd)
    marginal: bool             # source was in the [3,4) px/cell band
    notes: str = ""


class ScanRefused(ValueError):
    """Input measured below the decodable floor — carries diagnostics."""

    def __init__(self, msg: str, *, pitch_px: float | None = None):
        super().__init__(msg)
        self.pitch_px = pitch_px


def reduce_plane(img: np.ndarray, plane: str = "K") -> np.ndarray:
    """2-D float reflectance from grey/RGB(A), 8- or 16-bit, for one plane
    hypothesis. Output matches acquire._normalize_refl conventions
    (ink-dark, [0,1]-ish); constant offset/gain beyond that is irrelevant
    (detection z-normalizes)."""
    arr = np.asarray(img)
    if arr.ndim == 3:
        if arr.shape[2] < 3:
            arr = arr[..., 0]
        elif plane in _PLANE_CHANNEL:
            arr = arr[..., _PLANE_CHANNEL[plane]]
        else:                       # K (or unknown): luma over RGB
            arr = arr[..., :3].mean(axis=2)
    elif arr.ndim != 2:
        raise ValueError(f"scan must be 2-D or 3-D, got shape {arr.shape}")
    arr = np.ascontiguousarray(arr, np.float64)
    if arr.size:
        mx = float(arr.max())
        if mx > 255.5:              # 16-bit class
            arr = arr / 65535.0
        elif mx > 1.5:              # 8-bit class
            arr = arr / 255.0
    return arr


CONTRAST_FLOOR = 30.0      # per-band peak/median below this = no credible
#   lattice line at that probe. Calibrated on synthetic kcell pages (true
#   lines measure 60-1700+ across the ladder; aliased sub-Nyquist junk 22;
#   empty bands 4). A COURTESY diagnostic only — decode correctness always
#   rides the BCH word gate downstream, never this threshold.
MEASURE_WIN_PX = 2048      # central measurement window (>=64 periods at the
#   largest probe; a 2.3-gigapixel 4800dpi page must not be FFT'd whole)


def measure_cell_pitch(img2d: np.ndarray,
                       probes_px: tuple[float, ...] = PITCH_PROBES_PX
                       ) -> PitchMeasurement:
    """Blind wide-band lattice pitch: run the Stage-0 spectral estimator at
    each ladder probe (each band-limited +-1 octave), then identify the
    FUNDAMENTAL among the credible candidates.

    Selection rule (measured, not assumed — see the acquire-v2 build notes):
    per-band contrast values are NOT comparable across probes (each band
    normalizes by its own median floor), and on oversampled scans the
    gradient comb's HARMONICS out-contrast the fundamental (24 px/cell
    page: 3rd harmonic at 8 px measured contrast 435 vs fundamental 110).
    But every credible candidate of a true lattice with pitch P sits at
    ~P/k, integer k. So: keep candidates with contrast >= CONTRAST_FLOOR,
    and take the LARGEST pitch P whose fellow candidates all sit within 8%
    of an integer division of P. Junk low-frequency peaks fail the
    integer-ratio test; sub-Nyquist aliased lattices fail the floor."""
    # central measurement window (speed + memmap friendliness)
    if min(img2d.shape) > MEASURE_WIN_PX:
        cy, cx = img2d.shape[0] // 2, img2d.shape[1] // 2
        h = MEASURE_WIN_PX // 2
        img2d = np.ascontiguousarray(
            img2d[cy - h:cy + h, cx - h:cx + h], np.float64)
    cands: list[tuple[float, float, float]] = []   # (pitch, contrast, angle)
    for probe in probes_px:
        # estimate_lattice needs a few periods per window
        if min(img2d.shape) < 8 * probe:
            continue
        try:
            est = estimate_lattice(img2d, pitch_px_nominal=float(probe))
        except Exception:
            continue
        cands.append((float(est["pitch_px"]), float(est["contrast"]),
                      float(est["angle_rad"])))
    strong: list[tuple[float, float, float]] = []
    for pitch, contrast, angle in cands:
        if contrast < CONTRAST_FLOOR:
            continue
        # dedupe near-identical pitches from adjacent probes (keep best)
        for i, (p0, c0, _) in enumerate(strong):
            if abs(pitch / p0 - 1.0) < 0.02:
                if contrast > c0:
                    strong[i] = (pitch, contrast, angle)
                break
        else:
            strong.append((pitch, contrast, angle))
    if not strong:
        best = max(cands, key=lambda t: t[1], default=None)
        raise ScanRefused(
            "no credible lattice line at any probe pitch "
            f"(best contrast {best[1]:.1f} at {best[0]:.2f} px < floor "
            f"{CONTRAST_FLOOR})" if best else
            "no lattice line found at any probe pitch",
            pitch_px=best[0] if best else None)
    strong.sort(key=lambda t: -t[0])               # pitch descending
    chosen: tuple[float, float, float] | None = None
    for pitch, contrast, angle in strong:
        consistent = True
        for p2, _, _ in strong:
            k = max(1.0, round(pitch / p2))
            if abs(pitch / p2 - k) > 0.08 * k:
                consistent = False
                break
        if consistent:
            chosen = (pitch, contrast, angle)
            break
    if chosen is None:                              # mixed spectrum: fall
        chosen = max(strong, key=lambda t: t[1])    # back to best contrast
    pitch, contrast, angle = chosen
    if angle > np.pi / 4:
        angle -= np.pi / 2
    return PitchMeasurement(pitch_px=pitch, angle_rad=angle,
                            contrast=contrast, probe_px=pitch,
                            candidates=tuple((p, c) for p, c, _ in cands),
                            strong=tuple((p, c) for p, c, _ in strong))


def _box_resample(img: np.ndarray, num: int, den: int) -> np.ndarray:
    """Rational-factor aperture resample: np.repeat by num (exact), then
    den x den box means (exact). Both steps are integrating apertures — no
    spline ringing, no second bilinear pass."""
    out = img
    if num > 1:
        out = np.repeat(np.repeat(out, num, axis=0), num, axis=1)
    if den > 1:
        h = (out.shape[0] // den) * den
        w = (out.shape[1] // den) * den
        out = out[:h, :w].reshape(h // den, den, w // den, den).mean((1, 3))
    return np.ascontiguousarray(out)


CANONICAL_CELL_PX = (6.0, 8.0)   # allowed decode footings (px/cell). The
#   receiver's px thresholds are calibrated at 6 (c3 frozen baseline); 8 is
#   admitted because MEASURED during the acquire-v2 build: a c2 page at its
#   native 8 px/cell locks pitch to 8.001/8.000 and reads 25.8%, while the
#   3/4-box resample to 6 px/cell mislocks the u-pitch (+2.8%) and reads
#   40% — resampling is never free; the footing rule prefers the ladder
#   point reachable with the LEAST resampling (no-op > integer > rational).


def normalize_to_canonical(img2d: np.ndarray, pitch_px: float,
                           cell_dots: int) -> NormalizedScan:
    """Resample so the measured cell pitch lands within lock_grid's +-4%
    capture band around one of CANONICAL_CELL_PX, preferring the least
    resampling. Refuses below MIN_CELL_PX. cell_dots is currently unused
    (the footing rule is deliberately cell-size-agnostic) — RESERVED for
    per-encoding floor scaling; kept so callers already thread it."""
    if pitch_px < MIN_CELL_PX * (1.0 - CAPTURE_BAND):
        raise ScanRefused(
            f"cell pitch {pitch_px:.2f} px < {MIN_CELL_PX} px/cell floor "
            f"(px/cell ladder: 6 solid / 4 marginal / 3 floor / <3 dead) — "
            f"rescan at higher dpi", pitch_px=pitch_px)
    marginal = pitch_px < MARGINAL_CELL_PX * (1.0 - CAPTURE_BAND)
    # candidate (num, den, target): small rationals landing within the band;
    # score prefers no-op, then integer factors, then small rationals
    best: tuple[float, int, int, float] | None = None   # (score,num,den,ach)
    for target in CANONICAL_CELL_PX:
        for d in range(1, 17):
            n = max(1, round(target * d / pitch_px))
            achieved = pitch_px * n / d
            err = abs(achieved / target - 1.0)
            if err > CAPTURE_BAND:
                continue
            if n > 4:                    # cap upsample transients (memory)
                continue
            score = (0.0 if (n, d) == (1, 1) else
                     1.0 if (n == 1 or d == 1) else 2.0)
            score += err * 10.0 + (n * n + d) * 0.02
            if best is None or score < best[0]:
                best = (score, n, d, achieved)
    if best is None:
        raise ScanRefused(
            f"no small rational rescale lands pitch {pitch_px:.2f} px "
            f"within +-4% of any canonical footing {CANONICAL_CELL_PX}",
            pitch_px=pitch_px)
    _, num, den, achieved = best
    img = _box_resample(img2d, num, den) if (num, den) != (1, 1) else img2d
    notes = ("upsampled (no information added; source below the canonical "
             "footing)" if num > den else "")
    return NormalizedScan(img=img, scale_num=num, scale_den=den,
                          cell_px_est=achieved, marginal=marginal,
                          notes=notes)


def normalize_to_canonical_rgb(img: np.ndarray,
                               norm: NormalizedScan) -> np.ndarray:
    """(H', W', 3) float RGB companion of a luma NormalizedScan: each channel
    reduced honestly (reduce_plane per plane — C rides R, M rides G, Y rides
    B) and resampled with the SAME rational factor the luma decision froze
    (norm.scale_num/scale_den). One footing decision per scan — the color
    receiver's per-plane registration (COLOR-DESIGN D5) then measures
    plane-vs-luma offsets on a shared pixel frame; letting each channel pick
    its own footing would alias a resample difference into a fake plane
    offset. Channel order is R, G, B == the plane-channel measurement
    convention (index l reads plane "CMY"[l] best)."""
    arr = np.asarray(img)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError(f"RGB scan must be (H, W, >=3), got {arr.shape}")
    chans = [reduce_plane(arr, pl) for pl in ("C", "M", "Y")]  # R, G, B
    if (norm.scale_num, norm.scale_den) != (1, 1):
        chans = [_box_resample(c, norm.scale_num, norm.scale_den)
                 for c in chans]
    out = np.stack(chans, axis=-1)
    if out.shape[:2] != norm.img.shape:
        raise ValueError(
            f"RGB frame {out.shape[:2]} does not land on the luma frame "
            f"{norm.img.shape} — pass the SAME source scan both paths")
    return out
