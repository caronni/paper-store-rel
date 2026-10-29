"""The probe's bars: screen verdict per device-RGB value, the plateau edges and midpoints (CMY-PROBE-M281 §2, §4, §9).

THE VERDICT (CMY-PROBE-M281 §9, since e043's third reading 043.3c): the whitened whole-bar spectrum per ink
density at the five screen families (measure/cmy_probe/stipples.py `families`): a bar is `clean` iff every
family in every channel is at or below stipple_bar(white_max) = max(STIPPLE_NOISE_MIN, the sheet's white-bar
maximum over families and channels + STIPPLE_MARGIN), `marginal` up to MARGINAL_FACTOR x that, else
`screened` (verdict_of; the bar is set per sheet by apply_verdicts).  The e041 lattice score below is kept
as the LEGACY score (columns legacy_* in bars.csv, verdict_legacy), so sheet 1's records stay comparable.

Per bar (an imagemask or Indexed rectangle painted at one device RGB, 192 x 48 dots):
  - mean and sd of R, G, B over the interior, eroded BAR_MARGIN_PX scan px at 2400 dpi (x dpi / 2400);
  - the e041 screen-lattice score (measure/e041_scale_readout.py:120-131 the lattices, :446-499 the method,
    imported): in 96-px raw-scan windows (at 2400; 1.016 mm at any dpi) tiled over the interior, on the mean
    of the bar's OWN channel(s), the power at each known engine lattice (165 lpi +-14.2 deg, 188 lpi +-71 /
    +-19 deg, 212 lpi +-45 deg) over the median on that lattice's frequency ring, the mean over windows per
    lattice; score = the largest; verdict unscreened iff score <= UNSCREENED_MAX (18).  Own channel: the
    toner's scanner channel (C -> R, M -> G, Y -> B) when the bar names a toner, else e041's rule (channels
    whose value is < 128, all three when none) — the one deviation from e041's read_bar, whose bars were
    always the eight corners where the two rules agree; a 50 % tint names its toner, its RGB does not;
  - off-band structure (measure/e041_spectrum.py's method, here on the bar's own centred square window):
    the strongest off-axis spectral peak (0 / 90 deg +-4 deg excluded, as e041_spectrum.peaks) that is not
    within OFFBAND_EXCL_BINS bins of the known lattice set (every lattice's fundamentals with their harmonics
    and intermodulation products to order 3: lattice_points), as (lpi, angle, power over its ring median) —
    a screen the lattice set does not know is not mistaken for an unscreened print;
  - optional PNG of the bar window's power spectrum (e041_spectrum.save_spectrum).
Floor on THIS sheet: the white and scrambled bars' scores (MIC included); the screened control (a 50 % cyan
tint) is the positive reference.  The verdict stays at 18; the floor is reported beside it, and a sheet
whose floor reaches 18 or whose screened control does not exceed it is flagged as not discriminating.

Per ladder (sweep bars grouped by toner, axis and the fixed components, ordered by the swept component):
lower edge = the first swept value whose verdict is clean, upper edge = the last; each with its
transition value (the screened neighbour outside it; None = the plateau runs to the ladder's end, "open");
screened values between the edges are listed as holes; MIDPOINT = (lower + upper) / 2 rounded half up;
cross-talk along the plateau = the darkening of the two non-dominant scanner channels against the white bars'
mean (white - bar, per channel and their mean), per plateau bar and averaged.  Per toner a proposed rgb_solid:
per channel the midpoint of the single-axis ladder through that channel whose fixed components lie nearest
the manifest's lookup value for the toner (the registry value), the lookup value where no plateau exists.
"""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from measure.cmy_probe.specks import SPECKS_MAX, foreign_max, specks
from measure.cmy_probe.stipples import crop as stipple_crop
from measure.cmy_probe.stipples import families, worst
from measure.e041_probe_readout import SCAN_DPI_NOMINAL, Scan, sample_rect
from measure.e041_scale_readout import LATTICES, UNSCREENED_MAX, lattice_score
from measure.e041_spectrum import save_spectrum, spectrum

BAR_MARGIN_PX = 8                          # interior erosion at 2400 dpi, scan px (x dpi / 2400)
TONER_CHANNEL = {"C": 0, "M": 1, "Y": 2}
AXIS_CHANNELS = {"R": (0,), "G": (1,), "B": (2,), "RG": (0, 1)}
CHANNELS = "RGB"
OFFBAND_EXCL_BINS = 3.0                    # a peak within this many frequency bins of a lattice point is the lattice
OFFBAND_R_CYC = (0.02, 0.2)                # e041_spectrum.peaks' radial band, cycles per px at 2400 dpi
ON_AXIS_DEG = 4.0
LATTICE_ORDER = 3                          # harmonics / intermodulation order masked as "the lattice set"
# THE VERDICT's thresholds (CMY-PROBE-M281 §9), the one place they live
STIPPLE_NOISE_MIN = 25.0                   # the white bars' top on sheet 1 (043.3c: 12-25)
STIPPLE_MARGIN = 5.0                       # added to this sheet's white-bar maximum
MARGINAL_FACTOR = 2.0                      # marginal up to this multiple of the clean bar
VERDICTS = ("clean", "speckled", "marginal", "screened")   # speckled: families clean, foreign specks above SPECKS_MAX


def stipple_bar(white_max: float) -> float:
    """The clean bar on a sheet whose white bars peak at white_max (NaN: no white bar -> the noise minimum)."""
    return max(STIPPLE_NOISE_MIN, white_max + STIPPLE_MARGIN) if np.isfinite(white_max) else STIPPLE_NOISE_MIN


def verdict_of(worst_ratio: float, bar: float) -> str:
    if not np.isfinite(worst_ratio):
        return "unread"
    return "clean" if worst_ratio <= bar else ("marginal" if worst_ratio <= MARGINAL_FACTOR * bar else "screened")


# ---------------------------------------------------------------- geometry

def bar_box_mm(bar: dict[str, Any], dpi: float, margin_mm: float) -> tuple[float, float, float, float]:
    dot_mm = 25.4 / dpi
    x, y, w, h = (int(bar[k]) for k in ("x_dots", "y_dots", "w_dots", "h_dots"))
    return x * dot_mm + margin_mm, y * dot_mm + margin_mm, (x + w) * dot_mm - margin_mm, (y + h) * dot_mm - margin_mm


def own_channels(bar: dict[str, Any]) -> tuple[int, ...]:
    """The toner's scanner channel; else e041_scale_readout.own_channels on the RGB; else all three."""
    if bar.get("toner") in TONER_CHANNEL:
        return (TONER_CHANNEL[bar["toner"]],)
    rgb = bar.get("rgb")
    if rgb:
        own = tuple(c for c in range(3) if rgb[c] < 128)
        if own:
            return own
    return (0, 1, 2)


def centred_window(scan: Scan, A: np.ndarray, box_mm: tuple[float, float, float, float],
                   own: tuple[int, ...]) -> np.ndarray:
    """The largest even square raw-scan window centred on the box, mean of the own channels."""
    x0, y0, x1, y1 = box_mm
    side = int(min(x1 - x0, y1 - y0) * scan.px_per_mm) // 2 * 2
    cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    col = A[0, 0] * cx + A[0, 1] * cy + A[0, 2]
    row = A[1, 0] * cx + A[1, 1] * cy + A[1, 2]
    r0, c0 = int(round(row)) - side // 2, int(round(col)) - side // 2
    return scan.crop(r0, r0 + side, c0, c0 + side)[..., list(own)].mean(axis=2)


# ---------------------------------------------------------------- spectra

def lattice_points(cyc_scale: float) -> list[tuple[float, float]]:
    """(fy, fx), cycles per px at the scan's dpi, of the known lattice set: per lattice and per pair of its
    listed angles (a, b) every combination m k_a + n k_b with |m|, |n| <= LATTICE_ORDER (a screen's dots, and a
    clipped one, put power at the harmonics and intermodulation products of its fundamentals), mirrors
    included by the symmetric range."""
    pts: set[tuple[float, float]] = set()
    rng = range(-LATTICE_ORDER, LATTICE_ORDER + 1)
    for fr0, angles in LATTICES.values():
        fr = fr0 * cyc_scale
        ks = [(fr * math.sin(math.radians(a)), fr * math.cos(math.radians(a))) for a in angles]
        for i, (ya, xa) in enumerate(ks):
            for yb, xb in ks[i:]:
                pts |= {(round(m * ya + n * yb, 9), round(m * xa + n * xb, 9)) for m in rng for n in rng
                        if (m, n) != (0, 0)}
    return sorted(pts)


def offband_peak(g: np.ndarray, cyc_scale: float, scan_dpi: float) -> dict[str, float]:
    """The strongest off-axis, off-lattice spectral peak of a square window: e041_spectrum.peaks' candidate
    rule (radial band, 0 / 90 deg excluded, one half-plane) with a ring median of one bin width (the window
    is ~176 px, not e041_spectrum's 2048) and the known lattice points masked."""
    n = g.shape[0]
    if n < 32 or g.std() < 0.5:
        return {"lpi": float("nan"), "deg": float("nan"), "ratio": float("nan")}
    S = spectrum(g)
    f = np.fft.fftshift(np.fft.fftfreq(n))
    fy, fx = np.meshgrid(f, f, indexing="ij")
    r = np.hypot(fy, fx)
    ang = np.degrees(np.arctan2(fy, fx))
    ring = np.floor(r * n).astype(np.int64)
    med = np.zeros(ring.max() + 1)
    for k in np.unique(ring):
        med[k] = np.median(S[ring == k]) + 1e-12
    ratio = S / med[ring]
    a90 = (ang + 90.0) % 90.0
    on_axis = (a90 < ON_AXIS_DEG) | (a90 > 90.0 - ON_AXIS_DEG)
    lo, hi = OFFBAND_R_CYC[0] * cyc_scale, OFFBAND_R_CYC[1] * cyc_scale
    cand = (r > lo) & (r < hi) & ~on_axis & (fx >= 0)
    for py, px in lattice_points(cyc_scale):
        cand &= np.hypot(fy - py, fx - px) > OFFBAND_EXCL_BINS / n
    if not cand.any():
        return {"lpi": float("nan"), "deg": float("nan"), "ratio": float("nan")}
    i = int(np.argmax(np.where(cand, ratio, 0.0)))
    return {"lpi": float(r.flat[i] * scan_dpi), "deg": float(ang.flat[i]), "ratio": float(ratio.flat[i])}


# ---------------------------------------------------------------- per bar

def read_bar(scan: Scan, A: np.ndarray, bar: dict[str, Any], dpi: float, gt: Any,
             spectra_dir: Path | None = None) -> dict[str, Any]:
    """One bar: mean RGB over the interior, lattice score per lattice, best lattice, verdict, off-band peak."""
    margin_mm = BAR_MARGIN_PX * scan.dpi / SCAN_DPI_NOMINAL / scan.px_per_mm
    box = bar_box_mm(bar, dpi, margin_mm)
    step = 1.0 / scan.px_per_mm
    px = sample_rect(scan, A, np.arange(box[0], box[2], step), np.arange(box[1], box[3], step),
                     order=0).reshape(-1, 3)
    # Score each scanner channel on its own and let the largest win: a foreign toner's screen (cyan dots
    # in a magenta, magenta dots in a yellow) lives in a channel that is not the bar's own (e043, 2026-10-11:
    # the own-channel score missed those by eye-visible margins), and averaging channels dilutes it.
    per_channel = {c: lattice_score(scan, A, box, (c,)) for c in range(3)}
    best_c = max(per_channel, key=lambda c: (per_channel[c]["score"]
                                             if np.isfinite(per_channel[c]["score"]) else -1.0))
    lat = per_channel[best_c]
    own = (best_c,)
    cyc_scale = SCAN_DPI_NOMINAL / scan.dpi
    g = centred_window(scan, A, box, own)
    ob = offband_peak(g, cyc_scale, scan.dpi)
    if spectra_dir is not None and g.shape[0] >= 32:
        save_spectrum(spectrum(g), 0.2 * cyc_scale, spectra_dir / f"bar-{bar['id']}-spec.png")
    score = lat["score"]
    legacy = ("unscreened" if score <= UNSCREENED_MAX else "screened") if np.isfinite(score) else "unread"
    patch = stipple_crop(scan.img, A, bar) * scan.scale255
    fam = families(patch, dpi=scan.dpi)
    w_ch, w_fam, w_ratio = worst(fam)
    sp = specks(patch, scan.px_per_mm)
    sp_density, sp_max = foreign_max(sp, bar.get("toner"))
    key = bar.get("gt_key")
    ink_frac = float(np.asarray(gt[key]).mean()) if key and gt is not None and key in gt else None
    return {"id": bar["id"], "kind": bar["kind"], "toner": bar.get("toner"), "axis": bar.get("axis"),
            "rgb": list(bar["rgb"]) if bar.get("rgb") else None, "construct": bar.get("construct"),
            "x_dots": int(bar["x_dots"]), "y_dots": int(bar["y_dots"]),
            "mean_rgb": px.mean(0).tolist(), "sd_rgb": px.std(0).tolist(), "own": [CHANNELS[c] for c in own],
            "lattice_windows": lat["windows"], "lattice": lat["lattice"], "score": score,
            "score_rgb": [per_channel[c]["score"] for c in range(3)],
            "best_lattice": lat["best_lattice"], "verdict_legacy": legacy, "offband": ob, "gt_ink_fraction": ink_frac,
            "families": fam, "worst_channel": w_ch, "worst_family": w_fam, "worst_ratio": w_ratio,
            "specks": sp, "specks_density": sp_density, "specks_max": sp_max,
            "verdict": "unread"}


def white_max(bars: list[dict[str, Any]]) -> float:
    """The sheet's white-bar maximum over every family and channel (NaN without white bars)."""
    v = [b["worst_ratio"] for b in bars if b["kind"] == "white" and np.isfinite(b["worst_ratio"])]
    return max(v) if v else float("nan")


def apply_verdicts(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Set every bar's verdict from the sheet's own white bars; returns the stipple floor record."""
    wm = white_max(bars)
    bar = stipple_bar(wm)
    for b in bars:
        b["verdict"] = verdict_of(b["worst_ratio"], bar)
        if b["verdict"] == "clean" and b.get("specks_max", 0.0) > SPECKS_MAX:
            b["verdict"] = "speckled"                     # the eye's axis: sparse foreign dots, no lattice peak
    def worsts(kind: str) -> list[float]:
        return [b["worst_ratio"] for b in bars if b["kind"] == kind]
    scr = worsts("screened")
    return {"white_max": wm, "clean_max": bar, "marginal_max": MARGINAL_FACTOR * bar, "specks_max": SPECKS_MAX,
            "white_specks": [b.get("specks_max") for b in bars if b["kind"] == "white"],
            "noise_min": STIPPLE_NOISE_MIN, "margin": STIPPLE_MARGIN, "white": worsts("white"),
            "scrambled": worsts("scrambled"), "screened": scr,
            "discriminating": bool(scr) and min(scr) > MARGINAL_FACTOR * bar}


# ---------------------------------------------------------------- the floor

def floor_report(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """The score floor on this sheet (white and scrambled bars) and the positive reference (screened)."""
    def scores(kind: str) -> list[float]:
        return [b["score"] for b in bars if b["kind"] == kind and np.isfinite(b["score"])]
    white, scr, scrn = scores("white"), scores("scrambled"), scores("screened")
    ctl = white + scr
    floor_max = max(ctl) if ctl else float("nan")
    ref = min(scrn) if scrn else float("nan")
    disc = bool(ctl and scrn and floor_max < UNSCREENED_MAX < ref)
    return {"white": white, "scrambled": scr, "floor_max": floor_max,
            "floor_median": float(np.median(ctl)) if ctl else float("nan"),
            "screened": scrn, "screened_ref": ref, "unscreened_max": UNSCREENED_MAX, "discriminating": disc}


def white_reference(bars: list[dict[str, Any]], page_white: np.ndarray) -> np.ndarray:
    """Mean RGB of the white bars; the page white when the sheet has none."""
    w = [b["mean_rgb"] for b in bars if b["kind"] == "white"]
    return np.mean(np.array(w, np.float64), axis=0) if w else np.asarray(page_white, np.float64)


# ---------------------------------------------------------------- ladders and edges

def ladder_key(bar: dict[str, Any]) -> str:
    """'<axis>@<fixed components>/<construct>', e.g. 'G@R0B255/mask-a85', 'RG@B0/mask-hex' (sheet 2 prints
    every ladder in two constructs)."""
    swept = AXIS_CHANNELS[bar["axis"]]
    fixed = "".join(f"{CHANNELS[c]}{int(bar['rgb'][c])}" for c in range(3) if c not in swept)
    return f"{bar['axis']}@{fixed}" + (f"/{bar['construct']}" if bar.get("construct") else "")


def swept_value(bar: dict[str, Any]) -> int:
    return int(bar["rgb"][AXIS_CHANNELS[bar["axis"]][0]])


def ladders(bars: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """toner -> ladder key -> sweep bars ordered by the swept component."""
    out: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for b in bars:
        if b["kind"] == "sweep" and b.get("toner") and b.get("axis") in AXIS_CHANNELS and b.get("rgb"):
            out[b["toner"]][ladder_key(b)].append(b)
    return {t: {k: sorted(v, key=swept_value) for k, v in sorted(ls.items())} for t, ls in sorted(out.items())}


def half_up(v: float) -> int:
    return int(math.floor(v + 0.5))


def crosstalk(bar: dict[str, Any], toner: str, white: np.ndarray) -> dict[str, float]:
    """Darkening of the two non-dominant channels against the white reference (white - bar)."""
    dom = TONER_CHANNEL[toner]
    d = {CHANNELS[c]: float(white[c] - bar["mean_rgb"][c]) for c in range(3) if c != dom}
    return {**d, "mean": float(np.mean(list(d.values())))}


def ladder_edges(rows: list[dict[str, Any]], toner: str, white: np.ndarray) -> dict[str, Any]:
    """Edges, transitions, holes, midpoint and plateau cross-talk of one ordered ladder."""
    vals = [swept_value(b) for b in rows]
    steps = np.diff(vals)
    rec: dict[str, Any] = {"values": vals, "verdicts": [b["verdict"] for b in rows],
                           "scores": [b["worst_ratio"] for b in rows], "ids": [b["id"] for b in rows],
                           "step": int(np.median(steps)) if len(steps) else None, "fixed_rgb": list(rows[0]["rgb"])}
    un = [i for i, b in enumerate(rows) if b["verdict"] == "clean"]
    if not un:
        return {**rec, "lower": None, "upper": None, "midpoint": None, "lower_transition": None,
                "upper_transition": None, "lower_open": None, "upper_open": None, "holes": [], "plateau": []}
    lo, hi = un[0], un[-1]
    plateau = []
    for b in rows[lo:hi + 1]:
        if b["verdict"] == "clean":
            plateau.append({"value": swept_value(b), "id": b["id"], "mean_rgb": b["mean_rgb"],
                            "crosstalk": crosstalk(b, toner, white)})
    xt = [p["crosstalk"]["mean"] for p in plateau]
    pv = [p["value"] for p in plateau]
    slope = float(np.polyfit(pv, xt, 1)[0]) if len(pv) >= 2 else float("nan")
    return {**rec, "lower": vals[lo], "upper": vals[hi], "midpoint": half_up(0.5 * (vals[lo] + vals[hi])),
            "lower_transition": vals[lo - 1] if lo > 0 else None,
            "upper_transition": vals[hi + 1] if hi + 1 < len(vals) else None,
            "lower_open": lo == 0, "upper_open": hi == len(vals) - 1,
            "holes": [vals[i] for i in range(lo, hi + 1) if rows[i]["verdict"] != "clean"],
            "plateau": plateau, "crosstalk_mean": float(np.mean(xt)), "crosstalk_slope_per_unit": slope}


def propose_rgb(toner: str, edges: dict[str, dict[str, Any]], lookup: dict[str, list[int]]) -> dict[str, Any]:
    """Per channel the midpoint of the nearest-to-registry single-axis ladder through it; else the lookup."""
    reg = [int(v) for v in lookup.get(toner, [255, 255, 255])]
    rgb, per = list(reg), {}
    for c, ch in enumerate(CHANNELS):
        cands = [(k, e) for k, e in edges.items() if k.split("@")[0] == ch]
        if not cands:
            per[ch] = {"value": reg[c], "source": "registry (no ladder)"}
            continue

        def dist(item: tuple[str, dict[str, Any]]) -> int:
            fx = item[1]["fixed_rgb"]
            return sum(abs(int(fx[j]) - reg[j]) for j in range(3) if j != c)
        key, e = min(cands, key=dist)
        if e["midpoint"] is None:
            per[ch] = {"value": reg[c], "source": f"registry (no clean bar on {key})", "ladder": key}
            continue
        rgb[c] = int(e["midpoint"])
        per[ch] = {"value": rgb[c], "source": "midpoint", "ladder": key, "lower": e["lower"], "upper": e["upper"],
                   "lower_open": e["lower_open"], "upper_open": e["upper_open"]}
    return {"rgb": rgb, "registry": reg, "per_channel": per}


def edges_report(bars: list[dict[str, Any]], white: np.ndarray, lookup: dict[str, list[int]]) -> dict[str, Any]:
    """toner -> {'ladders': {key: edges}, 'rgb_solid': proposal}."""
    out = {}
    for toner, ls in ladders(bars).items():
        if toner not in TONER_CHANNEL:
            continue
        e = {k: ladder_edges(rows, toner, white) for k, rows in ls.items()}
        out[toner] = {"ladders": e, "rgb_solid": propose_rgb(toner, e, lookup)}
    return out


def registry_table(bars: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """toner -> construct -> the registry bar's worst family, verdict, legacy score and mean RGB, side by side."""
    out: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for b in bars:
        if b["kind"] == "registry":
            out[str(b.get("toner"))][str(b.get("construct"))] = {
                "id": b["id"], "rgb": b["rgb"], "worst_ratio": b["worst_ratio"], "worst_family": b["worst_family"],
                "worst_channel": b["worst_channel"], "verdict": b["verdict"], "legacy_score": b["score"],
                "specks_max": b.get("specks_max"), "specks_density": b.get("specks_density"),
                "verdict_legacy": b["verdict_legacy"], "best_lattice": b["best_lattice"], "mean_rgb": b["mean_rgb"]}
    return dict(out)
