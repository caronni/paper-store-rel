"""Reference decoder for the exp002 machine strip (LAY=1). Pure numpy.

Strip geometry (normative — panel design + arbitration):
- module MX = max(4, round(HWX/100)) x MY = max(4, round(HWY/100)) device dots;
- 724 x 11 modules: solid 1-module border, 1-module quiet, top clock
  (black-first), 5 data rows, inverted bottom clock (white-first), quiet, border;
- data row: sync 1011 | 78 bytes x (8 bits MSB-first + even-parity bit) |
  row-XOR byte (9 modules) | 5 white pad = 720 interior modules;
- payload: 5 x 78 = 390 bytes = 388 ASCII key=value (NUL-terminated, 0xA5-padded)
  + CRC-16/CCITT-FALSE big-endian over bytes [0:388].

The decoder is self-scaling AND skew-tolerant. v1 failed on real flatbed scans
(0 strips on scans/test-scan-calpage-bw.png) because it required the border to
be a >0.5-width dark run inside a SINGLE image row: at the measured 0.36 deg
scan skew the 8700-px border drifts ~55 px in y, so no such row exists, while
gs renders (0 deg) passed. v2 fixes exactly that, per the original design
intent (border find via long-run detection, clock-pair per-column
interpolation):
- borders are found as LINES: solid runs (fill >= 0.95) detected per vertical
  column band are clustered across bands and LSQ-fitted to y = p1*x + p0
  (tolerates skew to ~1.4 deg; solid patches / rulers / data rows are rejected
  by x-span, band coverage and the 10-module pairing constraint);
- module x centers come from quadrature demodulation of the CLOCK PAIR: the
  top clock minus the inverted bottom clock is a full-amplitude square wave
  with period 2 modules; its unwrapped phase is inverted per column, so module
  pitch error and scanner drift cannot accumulate over 720 columns;
- module y centers interpolate between the two fitted border lines and are
  refined by the measured clock-row darkness centroids (linear in row index);
- decode thresholds are local per strip (robust percentiles of the strip
  region), not global to the page (platen margins / page content vary).

180-degree rotation is auto-detected via payload magic/CRC, not clock
polarity: the clock geometry alone is 180-degree invariant (the inverted
bottom clock, column-reversed, reads black-first again since WI is even).
"""
from __future__ import annotations

import math
import sys

import numpy as np

MAGIC = b"PHCAL1;"
W_MODULES = 724          # full strip width incl border+quiet
H_MODULES = 11
WI = 720                 # interior modules per row
NR = 5                   # data rows
NB = 78                  # bytes per row
KNOWN_KEYS = ("LAY", "J", "S", "R0", "LL", "RD", "RE", "PS", "IB", "PR", "V", "RV", "SN")


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflect, no xorout."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def levels(img: np.ndarray) -> tuple[float, float, float]:
    """(white, black, midpoint threshold) from robust percentiles."""
    white = float(np.percentile(img, 90))
    black = float(np.percentile(img, 2))
    return white, black, (white + black) / 2


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[(start, end), ...] of True runs in a 1-D bool array (end exclusive)."""
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def _find_bars(dark: np.ndarray, m0_px: float) -> list[dict]:
    """Long, thin, SOLID horizontal bars (strip borders) as fitted lines.

    Detection is per vertical column band (width ~W/64): rows whose band fill
    fraction is >= 0.95 form runs of border-like height (0.35..3.5 modules).
    Runs are clustered across nearby bands with a skew-tolerant linkage
    (|dy| <= 0.025*|dx| + 0.6 module) and clusters spanning >= 0.55 of the
    image width with >= 50% band coverage are LSQ-fitted (one outlier-clip
    pass) to y = p1*x + p0. The bar x-extent is then re-measured at full
    resolution along the fitted line. Data rows (~50% fill, peaks ~0.94 on the
    real scan) stay below the 0.95 fill gate; solid patches and ruler
    baselines fail span/coverage or, later, pairing.
    """
    h_img, w_img = dark.shape
    band_w = max(8, w_img // 64)
    n_bands = w_img // band_w
    bf = dark[:, : n_bands * band_w].reshape(h_img, n_bands, band_w).mean(axis=2)
    dets: list[tuple[float, float, float, int]] = []   # (xc, yc, h, band)
    for band in range(n_bands):
        for s, e in _runs(bf[:, band] >= 0.95):
            if 0.35 * m0_px <= e - s <= 3.5 * m0_px:
                dets.append(((band + 0.5) * band_w, (s + e) / 2.0, float(e - s), band))
    n = len(dets)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if abs(dets[j][3] - dets[i][3]) > 3:
                continue
            dx = abs(dets[j][0] - dets[i][0])
            if dx == 0:
                continue
            if abs(dets[j][1] - dets[i][1]) <= 0.025 * dx + 0.6 * m0_px:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    bars: list[dict] = []
    xall = np.arange(w_img)
    for idxs in clusters.values():
        xs = np.array([dets[i][0] for i in idxs])
        ys = np.array([dets[i][1] for i in idxs])
        hs = np.array([dets[i][2] for i in idxs])
        bands = sorted({dets[i][3] for i in idxs})
        if xs.max() - xs.min() < 0.55 * w_img:
            continue
        if len(bands) < 0.5 * (bands[-1] - bands[0] + 1):
            continue
        p = np.polyfit(xs, ys, 1)
        keep = np.abs(ys - np.polyval(p, xs)) <= 0.6 * m0_px
        if keep.sum() >= 8:
            p = np.polyfit(xs[keep], ys[keep], 1)
        # full-resolution x extent along the fitted line
        hwin = max(1, int(round(0.35 * float(np.median(hs)))))
        rows = np.clip(np.round(np.polyval(p, xall)).astype(int)[None, :]
                       + np.arange(-hwin, hwin + 1)[:, None], 0, h_img - 1)
        colfrac = dark[rows, xall[None, :]].mean(axis=0)
        cruns = _runs(colfrac > 0.6)
        if not cruns:
            continue
        x0, x1 = max(cruns, key=lambda t: t[1] - t[0])
        if x1 - x0 < 0.55 * w_img:
            continue
        bars.append({"p1": float(p[0]), "p0": float(p[1]),
                     "x0": float(x0), "x1": float(x1),
                     "h": float(np.median(hs))})
    bars.sort(key=lambda b: b["p0"])
    return bars


def _bar_y(bar: dict, x: np.ndarray | float) -> np.ndarray | float:
    return bar["p0"] + bar["p1"] * x


def _pair_bars(bars: list[dict], img_w: int) -> list[tuple[dict, dict]]:
    """Pair top/bottom borders of the same strip: same x-extent and slope,
    center-line separation = 10 modules (module = extent / 724)."""
    pairs = []
    for i in range(len(bars)):
        for j in range(i + 1, len(bars)):
            a, b = bars[i], bars[j]
            mw = ((a["x1"] - a["x0"]) + (b["x1"] - b["x0"])) / 2.0 / W_MODULES
            if mw <= 0:
                continue
            tol_x = max(0.008 * img_w, 3.0 * mw)
            if abs(a["x0"] - b["x0"]) > tol_x or abs(a["x1"] - b["x1"]) > tol_x:
                continue
            if abs(a["p1"] - b["p1"]) > 0.012:
                continue
            xc = (a["x0"] + a["x1"]) / 2.0
            sep = _bar_y(b, xc) - _bar_y(a, xc)
            if sep > 0 and abs(sep / (10.0 * mw) - 1.0) < 0.25:
                pairs.append((a, b))
    return pairs


def _decode_pair(img: np.ndarray, top: dict, bot: dict) -> dict | None:
    """Decode one strip between two fitted border lines (clock-pair tracking)."""
    h_img, w_img = img.shape
    x0 = (top["x0"] + bot["x0"]) / 2.0
    x1 = (top["x1"] + bot["x1"]) / 2.0
    mx = (x1 - x0) / W_MODULES
    xc = (x0 + x1) / 2.0
    my_mid = (_bar_y(bot, xc) - _bar_y(top, xc)) / 10.0
    if mx < 2.0 or my_mid < 2.0:
        return None

    # -- local threshold from the strip region (NOT the page-global levels) --
    ry0 = int(max(0, math.floor(min(_bar_y(top, x0), _bar_y(top, x1)) - 2 * my_mid)))
    ry1 = int(min(h_img, math.ceil(max(_bar_y(bot, x0), _bar_y(bot, x1)) + 2 * my_mid)))
    region = img[ry0:ry1, int(max(0, x0)): int(min(w_img, x1))]
    w95 = float(np.percentile(region, 95))
    b05 = float(np.percentile(region, 5))
    if w95 - b05 < 16:
        return None
    thr = (w95 + b05) / 2.0

    # -- clock-pair profiles: interior row 0 (even cols dark) minus row 6
    #    (odd cols dark) is a period-2-module square wave -------------------
    xs = np.arange(int(math.ceil(x0 + 1.6 * mx)), int(math.floor(x0 + 722.4 * mx)))
    if len(xs) < 50 * 2:
        return None
    xs = np.clip(xs, 0, w_img - 1)
    my_x = (_bar_y(bot, xs) - _bar_y(top, xs)) / 10.0
    hw = max(1, int(round(0.3 * my_mid)))
    off = np.arange(-hw, hw + 1)

    def band_dark(y_center: np.ndarray) -> np.ndarray:
        rows = np.clip(np.round(y_center).astype(int)[None, :] + off[:, None],
                       0, h_img - 1)
        return (img[rows, xs[None, :]] < thr).mean(axis=0)

    s = band_dark(_bar_y(top, xs) + 2 * my_x) - band_dark(_bar_y(top, xs) + 8 * my_x)

    # quadrature demodulation at the nominal clock frequency; the unwrapped
    # total phase advances pi per module column and absorbs pitch error/drift.
    f0 = 1.0 / (2.0 * mx)
    carrier = 2.0 * np.pi * f0 * (xs - xs[0])
    ker = np.ones(max(3, int(round(4 * mx))))
    ker /= len(ker)
    zs = np.convolve(s * np.exp(-1j * carrier), ker, mode="same")
    psi = np.maximum.accumulate(np.unwrap(np.angle(zs)) + carrier)

    # anchor absolute phase at mid-strip column 360 (even -> psi = 0 mod 2pi);
    # geometry places it within +-0.5 module, so the nearest-2pi round is safe.
    c_mid = 360
    ia = int(np.clip(np.searchsorted(xs, x0 + (2 + c_mid + 0.5) * mx),
                     1, len(xs) - 2))
    targets = (round(psi[ia] / (2 * np.pi)) * 2 * np.pi - c_mid * np.pi
               + np.pi * np.arange(WI))
    if targets[0] < psi[2] or targets[-1] > psi[-3]:
        return None
    x_col = np.interp(targets, psi, xs.astype(float))

    # clock lock quality: sign of s at every recovered column center
    s_at = np.interp(x_col, xs, s)
    even = np.arange(WI) % 2 == 0
    clock_score = float(((s_at > 0) == even).mean())
    if clock_score < 0.95:
        return None

    # -- y refinement: PER-COLUMN clock-row darkness centroids ---------------
    # The straight border-line fit is biased where the paper warps locally
    # (measured: rows sit 1-3 px above the lines at the left end of the
    # bottom strip — same warp class as the coherent +3.5-dot plus-mark shift
    # in the registration report) and border dot-gain asymmetry inflates the
    # border separation (~ -1.5 px at the bottom clock on both real strips).
    # The dark clock modules measure the true row center locally; smoothing
    # over ~41 modules and interpolating over all columns fixes both effects,
    # linearly in row index between the two clock rows.
    my_col = (_bar_y(bot, x_col) - _bar_y(top, x_col)) / 10.0
    yt_col = _bar_y(top, x_col)
    x_int = np.clip(np.round(x_col).astype(int), 0, w_img - 1)
    hw2 = max(2, int(round(0.9 * my_mid)))
    off2 = np.arange(-hw2, hw2 + 1)

    def centroid_track(rowi: int, cols: np.ndarray, base_dy: np.ndarray
                       ) -> np.ndarray:
        """Smoothed per-column ABSOLUTE y offset (model -> measured) of one
        interior row, from darkness centroids at the given (dark) modules.
        Columns whose window is nearly all dark (vertically merged with a
        neighbor row — the centroid says nothing there) are skipped."""
        y_cen = yt_col[cols] + (2 + rowi) * my_col[cols] + base_dy[cols]
        rows = np.clip(np.round(y_cen).astype(int)[None, :] + off2[:, None],
                       0, h_img - 1)
        d = (img[rows, x_int[cols][None, :]] < thr).astype(np.float32)
        wsum = d.sum(axis=0)
        good = (wsum > 0.5 * hw2) & (wsum < 0.9 * len(off2))
        if good.sum() < 20:
            return base_dy
        cen = (d * off2[:, None].astype(np.float32)).sum(axis=0)[good] / wsum[good]
        dy_abs = (base_dy[cols] + np.round(y_cen) - y_cen)[good] + cen
        # median over a +-30-module x window (x-based, not index-based: valid
        # modules can be sparse near the strip ends), interpolated everywhere
        xg = x_col[cols][good]
        half = 30.0 * mx
        sm = np.array([np.median(dy_abs[max(0, np.searchsorted(xg, xg[i] - half)):
                                        np.searchsorted(xg, xg[i] + half)])
                       for i in range(len(dy_abs))])
        out = np.interp(x_col, xg, sm)
        return np.clip(out - base_dy, -0.4 * my_mid, 0.4 * my_mid) + base_dy

    zero = np.zeros(WI)
    d_top = centroid_track(0, np.flatnonzero(even), zero)
    d_bot = centroid_track(6, np.flatnonzero(~even), zero)
    dy_rows = [d_top + (d_bot - d_top) * rowi / 6.0 for rowi in range(7)]

    # -- sample the 7 interior rows at the tracked column centers ------------
    # y window deliberately tighter than x: residual y warp + vertical dot
    # gain from the row below are the dominant error source on real scans.
    wx = max(1, int(round(0.3 * mx)))
    wy = max(1, int(round(0.17 * my_mid)))
    oy, ox = np.mgrid[-wy: wy + 1, -wx: wx + 1]

    def sample_bits(dys: list[np.ndarray]) -> list[np.ndarray]:
        out = []
        for rowi in range(7):
            y_cen = yt_col + (2 + rowi) * my_col + dys[rowi]
            rows = np.clip(np.round(y_cen).astype(int)[:, None, None] + oy[None],
                           0, h_img - 1)
            cols = np.clip(x_int[:, None, None] + ox[None], 0, w_img - 1)
            out.append(img[rows, cols].reshape(WI, -1).mean(axis=1) < thr)
        return out

    row_bits = sample_bits(dy_rows)

    # decision-directed data-row y refinement: local warp between the clock
    # rows (measured: row 1 rides 3-4 px above the clock interpolation over a
    # ~700-px stretch of the real bottom strip) is tracked per data row from
    # its own vertically-isolated dark modules, then bits are resampled.
    for _ in range(2):
        new_dy = list(dy_rows)
        for rowi in range(1, 6):
            iso = row_bits[rowi] & ~row_bits[rowi - 1] & ~row_bits[rowi + 1]
            cols = np.flatnonzero(iso)
            if len(cols) >= 30:
                new_dy[rowi] = centroid_track(rowi, cols, dy_rows[rowi])
        dy_rows = new_dy
        row_bits = sample_bits(dy_rows)

    payload = bytearray(390)
    sync_err = parity_err = rowxor_err = 0
    for r in range(NR):
        bits = row_bits[1 + r].astype(np.uint8)
        if list(bits[0:4]) != [1, 0, 1, 1]:
            sync_err += 1
        rx = 0
        for i in range(NB):
            grp = bits[4 + 9 * i: 4 + 9 * i + 9]
            val = int(np.packbits(grp[:8])[0])
            if int(grp[:8].sum()) % 2 != int(grp[8]):
                parity_err += 1
            payload[r * NB + i] = val
            rx ^= val
        xg = bits[4 + 9 * NB: 4 + 9 * NB + 9]
        xval = int(np.packbits(xg[:8])[0])
        if xval != rx or int(xg[:8].sum()) % 2 != int(xg[8]):
            rowxor_err += 1

    payload = bytes(payload)
    crc_ok = crc16_ccitt_false(payload[:388]) == int.from_bytes(payload[388:390], "big")
    return {
        "payload": payload,
        "crc_ok": crc_ok,
        "magic_ok": payload.startswith(MAGIC),
        "sync_errors": sync_err,
        "parity_errors": parity_err,
        "rowxor_errors": rowxor_err,
        "clock_score": clock_score,
        "module_px": (mx, my_mid),
        "origin_px": (x0, _bar_y(top, x0) - my_mid / 2),
        "skew_deg": math.degrees(math.atan(top["p1"])),
        "clock_dy_px": (float(np.median(d_top)), float(np.median(d_bot))),
        "threshold": thr,
        "fields": parse_payload(payload) if payload.startswith(MAGIC) else {},
    }


def parse_payload(payload: bytes) -> dict[str, str]:
    """KEY=-anchored field extraction (values may contain ';', e.g. PR)."""
    nul = payload.find(b"\x00")
    text = payload[: nul if nul >= 0 else 388].decode("ascii", errors="replace")
    anchors = []
    for k in KNOWN_KEYS:
        i = text.find(";" + k + "=")
        if i >= 0:
            anchors.append((i + 1, k))
    anchors.sort()
    fields: dict[str, str] = {}
    for n, (pos, k) in enumerate(anchors):
        vstart = pos + len(k) + 1
        if n + 1 < len(anchors):
            fields[k] = text[vstart: anchors[n + 1][0] - 1]
        else:
            fields[k] = text[vstart:].rstrip(";")
    return fields


def decode_image(img: np.ndarray) -> list[dict]:
    """Find and decode all machine strips in a grayscale page image.

    Returns one dict per decoded strip, top to bottom. Tries the image as-is,
    then rotated 180 degrees (each result carries 'rotated_180'). NOTE: the
    clock geometry alone is 180-degree invariant (the inverted bottom clock,
    column-reversed, reads black-first again since WI is even), so orientation
    is decided by payload magic/CRC, not by clock polarity.
    """
    if img.ndim != 2:
        raise ValueError(f"expected 2-D grayscale, got shape {img.shape}")
    w_img = img.shape[1]
    m0_px = w_img / 830.0   # module ~0.01 inch on a ~8.3-inch-wide page scan
    _, _, thr = levels(img)
    fallback: list[dict] = []
    for rotated in (False, True):
        view = img[::-1, ::-1] if rotated else img
        results = []
        for top, bot in _pair_bars(_find_bars(view < thr, m0_px), w_img):
            r = _decode_pair(view, top, bot)
            if r is not None:
                r["rotated_180"] = rotated
                results.append(r)
        if any(s["crc_ok"] or s["magic_ok"] for s in results):
            return results
        if results and not fallback:
            fallback = results
    return fallback


def main(argv: list[str]) -> int:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    img = np.asarray(Image.open(argv[1]).convert("L"))
    strips = decode_image(img)
    print(f"{len(strips)} strip(s) decoded")
    for n, s in enumerate(strips):
        print(f"-- strip {n}: crc_ok={s['crc_ok']} magic_ok={s['magic_ok']} "
              f"clock={s['clock_score']:.3f} module_px={s['module_px'][0]:.2f} "
              f"skew={s['skew_deg']:+.3f} deg rot180={s['rotated_180']} "
              f"sync/parity/xor errs={s['sync_errors']}/{s['parity_errors']}/{s['rowxor_errors']}")
        for k, v in s["fields"].items():
            print(f"   {k} = {v}")
    return 0 if strips and all(s["crc_ok"] for s in strips) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
