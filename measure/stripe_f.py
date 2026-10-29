"""Sheet F stripe analysis — what is optically different about the tiles
whose M and Y planes certified (one process-direction stripe) versus the
tiles whose C plane alone certified (the rest of the page).

Read-only instrument over a finished holo3 run dir and the sheet's
emitted ground-truth bitmap.  Uses the analyzer's own placement/crop
path (`sample.read_rgb` at the committed pose) so every cell sample is
the receiver's, and the GT bitmap (sha-gated against the manifest) for
the printed state of every cell.

Truth path: the GT/placement mapping is validated first on certified C
tiles (the C plane's hard decisions must agree with GT) before any
number about M or Y is trusted.

Outputs (all in --out): metrics.json (per tile), summary.md, and PNG
figures rendered with PIL (no matplotlib in the venv).

    PYTHONPATH=src:. python -m measure.stripe_f \
        --run-dir <evidence>/hp-F-20260913.96911 \
        --gen-dir <evidence>/xerox-v1-20260818/F-c3-cmy8v1-q090-4mm \
        --format-ref L:c3-cmy8-p120-v1@2240x1536 \
        --out build/hp-F-20260913-stripe
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from analyzer.frame import tile_footprint
from analyzer.inputs import load_run
from analyzer.sample import lane_footprint, lanes_for_tile, open_crops, \
    read_rgb

PLANES = ("C", "M", "Y")          # plane index == sensitive channel index
CHANNELS = ("R", "G", "B")
TILE = 64
OFFSETS = tuple(float(v) for v in np.arange(-1.5, 1.51, 0.5))


# ----------------------------------------------------------------- truth --

def load_gt_cells(gen_dir: Path) -> np.ndarray:
    manifest = json.loads((gen_dir / "manifest.json").read_text())
    page = manifest["pages"][0]
    gt_path = gen_dir / page["gt"]
    packed = np.load(gt_path)
    # the manifest hashes the packed array's bytes (and each plane's),
    # not the .npy file
    sha = hashlib.sha256(packed.tobytes()).hexdigest()
    if sha != page["gt_sha256"]:
        raise SystemExit(f"GT sha mismatch: {sha} != {page['gt_sha256']}")
    for p, want in enumerate(page["gt_plane_sha256"]):
        got = hashlib.sha256(np.ascontiguousarray(packed[p]).tobytes()).hexdigest()
        if got != want:
            raise SystemExit(f"GT plane {p} sha mismatch")
    if page["gt_plane_order"] != list(PLANES) or page["gt_bitorder"] != "big":
        raise SystemExit(f"unexpected GT layout: {page}")
    bits = np.unpackbits(packed, axis=2, bitorder="big")
    cell_dots = int(manifest["cell_dots"])
    cells_y, cells_x = manifest["page_cells_yx"]
    bits = bits[:, :cells_y * cell_dots, :cells_x * cell_dots]
    centre = bits[:, cell_dots // 2::cell_dots, cell_dots // 2::cell_dots]
    corner = bits[:, 0::cell_dots, 0::cell_dots]
    agree = float(np.mean(centre == corner))
    if agree < 0.999:
        raise SystemExit(f"GT cells are not {cell_dots}x{cell_dots} blocks "
                         f"(corner/centre agreement {agree:.4f})")
    return centre.astype(np.uint8)      # (3, cells_y, cells_x)


# --------------------------------------------------------------- reading --

def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    if a.size < 8 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def radial_psd(patch: np.ndarray, n_bins: int = 48) -> np.ndarray:
    """Radially averaged power spectrum, bins over 0..0.5 cycles/px."""
    p = patch.astype(np.float64)
    p -= p.mean()
    h, w = p.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    spec = np.abs(np.fft.fftshift(np.fft.fft2(p * win))) ** 2
    fy = np.fft.fftshift(np.fft.fftfreq(h))
    fx = np.fft.fftshift(np.fft.fftfreq(w))
    fr = np.sqrt(fy[:, None] ** 2 + fx[None, :] ** 2)
    edges = np.linspace(0.0, 0.5, n_bins + 1)
    out = np.zeros(n_bins)
    for i in range(n_bins):
        m = (fr >= edges[i]) & (fr < edges[i + 1])
        out[i] = spec[m].mean() if m.any() else np.nan
    return out


def band_power(psd: np.ndarray, centre: float, rel: float = 0.12) -> float:
    edges = np.linspace(0.0, 0.5, psd.size + 1)
    mid = 0.5 * (edges[:-1] + edges[1:])
    m = (mid >= centre * (1 - rel)) & (mid <= centre * (1 + rel))
    return float(np.nanmean(psd[m])) if m.any() else float("nan")


def analyze_tile(inputs, gt_cells: np.ndarray, ty: int, tx: int,
                 keep_patch: bool = False) -> dict | None:
    fp = tile_footprint(inputs.row, 0, ty, tx, 0, geometry=inputs.geometry)
    lanes = lanes_for_tile(inputs, 0, ty, tx)
    if not lanes:
        return None
    lane = lanes[0]
    lfp = lane_footprint(lane, fp)
    if lfp is None:
        return None
    cell_dots = int(inputs.row.pitch_in * 600)
    crops = open_crops(lane, lfp, bound_dots=2.0, cell_dots=cell_dots,
                       keep_raw=True)
    cells = fp.page_cells_yx
    gt = gt_cells[:, cells[:, 0], cells[:, 1]].astype(bool)     # (3, n)
    # 64x64 grids for neighbour logic (halo 0: footprint == tile, row-major)
    gt_grid = gt.reshape(3, TILE, TILE)

    reads: dict[tuple[float, float], np.ndarray] = {}
    obs_mask: dict[tuple[float, float], np.ndarray] = {}
    for dx in OFFSETS:
        for dy in OFFSETS:
            r = read_rgb(crops, lfp, offset_dots_xy=(dx, dy))
            if r.refusal:
                continue
            vals = r.values_rgb
            ok = lfp.observed & np.all(np.isfinite(vals), axis=1)
            reads[(dx, dy)] = vals
            obs_mask[(dx, dy)] = ok
    if not reads:
        return None

    white = ~gt[0] & ~gt[1] & ~gt[2]
    out: dict = {"ty": ty, "tx": tx, "n_reads": len(reads)}
    for p, name in enumerate(PLANES):
        single = gt[p] & ~np.any(np.delete(gt, p, axis=0), axis=0)
        # registration: the offset where the sensitive channel anticorrelates
        # most with this plane's ink (single-ink vs white cells only)
        best = None
        for (dx, dy), vals in reads.items():
            ok = obs_mask[(dx, dy)] & (single | white)
            c = pearson(gt[p][ok], vals[ok, p])
            if np.isfinite(c) and (best is None or c < best[0]):
                best = (c, dx, dy)
        if best is None:
            continue
        corr, dx, dy = best
        vals = reads[(dx, dy)]
        ok = obs_mask[(dx, dy)]
        ch = vals[:, p]
        mu_w, sd_w = float(ch[ok & white].mean()), float(ch[ok & white].std())
        sel = ok & single
        mu_p, sd_p = float(ch[sel].mean()), float(ch[sel].std())
        dprime = (mu_w - mu_p) / np.sqrt(0.5 * (sd_w ** 2 + sd_p ** 2))
        under = gt[p] & np.any(np.delete(gt, p, axis=0), axis=0)
        mu_under = float(ch[ok & under].mean()) if (ok & under).any() else np.nan
        # isolated vs in-run ink cells of this plane (interior cells only)
        g = gt_grid[p]
        interior = np.zeros((TILE, TILE), bool)
        interior[1:-1, 1:-1] = True
        n_up = np.zeros_like(g); n_up[1:] = g[:-1]
        n_dn = np.zeros_like(g); n_dn[:-1] = g[1:]
        n_lf = np.zeros_like(g); n_lf[:, 1:] = g[:, :-1]
        n_rt = np.zeros_like(g); n_rt[:, :-1] = g[:, 1:]
        iso = (g & ~n_up & ~n_dn & ~n_lf & ~n_rt & interior).ravel()
        run_h = (g & n_lf & n_rt & interior).ravel()
        run_v = (g & n_up & n_dn & interior).ravel()
        sing_own = ~np.any(np.delete(gt, p, axis=0), axis=0)
        mu_iso = float(ch[ok & iso & sing_own].mean()) if (ok & iso & sing_own).sum() > 5 else np.nan
        mu_run_h = float(ch[ok & run_h & sing_own].mean()) if (ok & run_h & sing_own).sum() > 5 else np.nan
        mu_run_v = float(ch[ok & run_v & sing_own].mean()) if (ok & run_v & sing_own).sum() > 5 else np.nan
        # crosstalk: this plane's ink seen in the other two channels
        others = [float(vals[sel, q].mean() - vals[ok & white, q].mean())
                  for q in range(3) if q != p]
        out[name] = {
            "corr": corr, "reg_dx_dots": dx, "reg_dy_dots": dy,
            "white_mu": mu_w, "white_sd": sd_w,
            "ink_mu": mu_p, "ink_sd": sd_p, "dprime": float(dprime),
            "contrast": mu_w - mu_p,
            "under_mu": mu_under,
            "iso_mu": mu_iso, "run_h_mu": mu_run_h, "run_v_mu": mu_run_v,
            "n_single": int(sel.sum()), "n_white": int((ok & white).sum()),
            "xtalk_other_channels": others,
        }
        # keep per-cell samples for pooled histograms (single-ink & white)
        out.setdefault("_samples", {})[name] = (
            ch[ok & white].astype(np.float32), ch[sel].astype(np.float32))

    # raw patch of the tile at the committed pose (offset 0)
    r0 = read_rgb(crops, lfp, offset_dots_xy=(0.0, 0.0))
    pts = r0.points_yx
    if pts is not None and np.isfinite(pts).any():
        yy = pts[lfp.observed, 0] - crops.y0
        xx = pts[lfp.observed, 1] - crops.x0
        pitch = float(crops.pitch_px_level)
        y0 = int(np.floor(np.nanmin(yy) - pitch / 2)); y1 = int(np.ceil(np.nanmax(yy) + pitch / 2))
        x0 = int(np.floor(np.nanmin(xx) - pitch / 2)); x1 = int(np.ceil(np.nanmax(xx) + pitch / 2))
        raw = crops.raw_rgb
        y0, x0 = max(0, y0), max(0, x0)
        y1, x1 = min(raw.shape[0], y1), min(raw.shape[1], x1)
        patch = np.asarray(raw[y0:y1, x0:x1])
        spectra = {}
        for q, cname in enumerate(CHANNELS):
            psd = radial_psd(patch[..., q])
            spectra[cname] = psd
            out[f"psd_{cname}_cell"] = band_power(psd, 1.0 / pitch)
            out[f"psd_{cname}_dot"] = band_power(psd, cell_dots / pitch)
            out[f"psd_{cname}_low"] = band_power(psd, 0.5 / pitch, 0.5)
        out["_psd"] = spectra
        out["pitch_px"] = pitch
        if keep_patch:
            out["_patch"] = patch
            out["_points"] = np.stack((yy - y0, xx - x0), axis=1)
            out["_gt"] = gt[:, lfp.observed]
    return out


# ------------------------------------------------------------ plotting --

def _canvas(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (w, h), (255, 255, 255))
    return im, ImageDraw.Draw(im)


def plot_lines(series, title: str, xlabel: str, ylabel: str,
               size=(700, 420), logy=False, vlines=()) -> Image.Image:
    im, d = _canvas(*size)
    W, H = size
    L, R, T, B = 70, 20, 40, 50
    xs_all = np.concatenate([np.asarray(s[1], float) for s in series])
    ys_all = np.concatenate([np.asarray(s[2], float) for s in series])
    ys_all = ys_all[np.isfinite(ys_all)]
    if logy:
        ys_all = np.log10(ys_all[ys_all > 0])
    x0, x1 = float(np.nanmin(xs_all)), float(np.nanmax(xs_all))
    y0, y1 = float(np.nanmin(ys_all)), float(np.nanmax(ys_all))
    if y1 == y0:
        y1 = y0 + 1
    def X(v): return L + (v - x0) / (x1 - x0) * (W - L - R)
    def Y(v): return H - B - (v - y0) / (y1 - y0) * (H - T - B)
    d.rectangle([L, T, W - R, H - B], outline=(0, 0, 0))
    d.text((L, 10), title, fill=(0, 0, 0))
    d.text((W // 2 - 40, H - 22), xlabel, fill=(0, 0, 0))
    d.text((4, T), ylabel, fill=(0, 0, 0))
    for k in range(5):
        v = y0 + (y1 - y0) * k / 4
        d.text((4, Y(v) - 6), f"{v:.2f}", fill=(80, 80, 80))
        d.line([L, Y(v), W - R, Y(v)], fill=(230, 230, 230))
    for k in range(5):
        v = x0 + (x1 - x0) * k / 4
        d.text((X(v) - 10, H - B + 4), f"{v:.3g}", fill=(80, 80, 80))
    for xv in vlines:
        d.line([X(xv), T, X(xv), H - B], fill=(200, 200, 200))
    for i, (label, xs, ys, color) in enumerate(series):
        xs = np.asarray(xs, float); ys = np.asarray(ys, float)
        if logy:
            ys = np.where(ys > 0, np.log10(np.where(ys > 0, ys, 1)), np.nan)
        pts = [(X(a), Y(b)) for a, b in zip(xs, ys) if np.isfinite(b)]
        if len(pts) > 1:
            d.line(pts, fill=color, width=2)
        d.text((W - R - 200, T + 6 + 14 * i), label, fill=color)
    return im


def plot_hist(groups, title: str, xlabel: str, bins: np.ndarray,
              size=(700, 420)) -> Image.Image:
    series = []
    mid = 0.5 * (bins[:-1] + bins[1:])
    for label, data, color in groups:
        data = np.asarray(data, float)
        if data.size == 0:
            continue
        h, _ = np.histogram(data, bins=bins)
        series.append((f"{label} (n={data.size})", mid, h / max(1, h.sum()), color))
    return plot_lines(series, title, xlabel, "fraction", size=size)


def grid_figure(tiles: list[tuple[str, dict]], scale: float, out: Path,
                zoom_cells: int | None = None) -> None:
    """Rows = tiles; cols = RGB, R, G, B (optionally a GT-overlay zoom)."""
    cols = ["RGB", "R (C ink)", "G (M ink)", "B (Y ink)"]
    if zoom_cells:
        cols = ["RGB zoom + GT (M magenta, Y yellow)"]
    rows = []
    for label, t in tiles:
        patch = t["_patch"]
        if zoom_cells:
            pitch = t["pitch_px"]
            n = int(zoom_cells * pitch)
            oy = patch.shape[0] // 2 - n // 2
            ox = patch.shape[1] // 2 - n // 2
            sub = patch[oy:oy + n, ox:ox + n]
            im = Image.fromarray(sub).resize((int(n * scale), int(n * scale)),
                                             Image.NEAREST)
            dr = ImageDraw.Draw(im)
            pts = t["_points"]; gt = t["_gt"]
            for (py, px), m, y in zip(pts, gt[1], gt[2]):
                if not (oy <= py < oy + n and ox <= px < ox + n):
                    continue
                cy, cx = (py - oy) * scale, (px - ox) * scale
                r = pitch * scale * 0.45
                if m:
                    dr.rectangle([cx - r, cy - r, cx + r, cy + r],
                                 outline=(255, 0, 255))
                if y:
                    dr.rectangle([cx - r * 0.7, cy - r * 0.7, cx + r * 0.7,
                                  cy + r * 0.7], outline=(230, 200, 0))
            ims = [im]
        else:
            ims = [Image.fromarray(patch)]
            for q in range(3):
                ims.append(Image.fromarray(patch[..., q]).convert("RGB"))
            ims = [im.resize((int(im.width * scale), int(im.height * scale)),
                             Image.BOX) for im in ims]
        rows.append((label, ims))
    w = max(im.width for _, ims in rows for im in ims)
    h = max(im.height for _, ims in rows for im in ims)
    pad, head = 8, 18
    W = len(cols) * (w + pad) + pad
    H = len(rows) * (h + head + pad) + head + pad
    canvas = Image.new("RGB", (W, H), (240, 240, 240))
    d = ImageDraw.Draw(canvas)
    for j, c in enumerate(cols):
        d.text((pad + j * (w + pad), 2), c, fill=(0, 0, 0))
    for i, (label, ims) in enumerate(rows):
        y = head + pad + i * (h + head + pad)
        d.text((pad, y), label, fill=(0, 0, 0))
        for j, im in enumerate(ims):
            canvas.paste(im, (pad + j * (w + pad), y + head))
    canvas.save(out)


# ------------------------------------------------------------------ main --

def summarize(group: list[dict]) -> dict:
    keys = ["dprime", "contrast", "white_mu", "white_sd", "ink_mu", "ink_sd",
            "under_mu", "iso_mu", "run_h_mu", "run_v_mu", "reg_dx_dots",
            "reg_dy_dots", "corr"]
    out = {}
    for p in PLANES:
        vals = [t[p] for t in group if p in t]
        out[p] = {k: (float(np.nanmean([v[k] for v in vals])),
                      float(np.nanstd([v[k] for v in vals])))
                  for k in keys} if vals else {}
    for k in [f"psd_{c}_{b}" for c in CHANNELS for b in ("cell", "dot", "low")]:
        v = [t[k] for t in group if k in t]
        out[k] = (float(np.nanmean(v)), float(np.nanstd(v))) if v else None
    out["n"] = len(group)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--gen-dir", required=True)
    ap.add_argument("--format-ref", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-rows", type=int, default=8)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    inputs = load_run(args.run_dir, format_ref=args.format_ref)
    gt_cells = load_gt_cells(Path(args.gen_dir))
    assert gt_cells.shape[1:] == tuple(inputs.cells_yx), (gt_cells.shape, inputs.cells_yx)
    # the analyzer's own truth path (measure/c-third-layer-20260906/dump_cells.py
    # route): the emitted per-cell field from the manifest-gated payload;
    # the GT bitmap unpack above must agree with it bit for bit.
    from analyzer import truth as truth_mod
    gen_dir = Path(args.gen_dir)
    payloads = sorted(gen_dir.glob("payload*.bin"))
    truth = truth_mod.load_truth(gen_dir, payloads[0], inputs.row, 1,
                                 format_ref=args.format_ref)
    field = truth.fields[0]
    bits3 = np.stack([np.asarray(field.plane_bits[p]).astype(np.uint8)
                      for p in range(3)])
    if bits3.shape != gt_cells.shape or not np.array_equal(bits3, gt_cells):
        mism = float(np.mean(bits3 != gt_cells)) if bits3.shape == gt_cells.shape else float("nan")
        raise SystemExit(f"truth mismatch: analyzer field {bits3.shape} vs GT "
                         f"bitmap {gt_cells.shape}, disagreement {mism}")
    print("truth: analyzer per-cell field == GT bitmap cells, bit for bit")

    by_tile: dict[tuple[int, int], set] = defaultdict(set)
    for (page, ty, tx, stream) in inputs.certificates:
        if page == 0:
            by_tile[(ty, tx)].add(stream)
    full = sorted(k for k, s in by_tile.items() if s >= {"C", "M", "Y"})
    c_only = sorted(k for k, s in by_tile.items() if s == {"C"})
    print(f"tiles: full C+M+Y {len(full)}, C-only {len(c_only)}, "
          f"any-cert {len(by_tile)}")

    # --- truth-path validation on certified C tiles: R must anticorrelate
    # with the C bit at the committed pose.
    val = []
    for (ty, tx) in c_only[:12]:
        t = analyze_tile(inputs, gt_cells, ty, tx)
        if t and "C" in t:
            val.append(t["C"]["corr"])
    print("validation: C-plane corr(GT C bit, R) on 12 certified-C tiles:",
          np.round(val, 3))
    if not val or np.nanmedian(val) > -0.5:
        raise SystemExit("mapping/GT validation FAILED — refusing to continue")

    # --- rows to profile: rows holding a full tile, evenly spaced
    full_rows = sorted({ty for ty, _ in full})
    step = max(1, len(full_rows) // args.max_rows)
    rows = full_rows[::step][:args.max_rows]
    stripe_cols = sorted({tx for _, tx in full})
    print("full-tile rows", full_rows, "-> profiling rows", rows,
          "stripe columns", stripe_cols)

    tiles_yx = inputs.tiles_yx
    results: list[dict] = []
    for ty in rows:
        for tx in range(tiles_yx[1]):
            t = analyze_tile(inputs, gt_cells, ty, tx)
            if t is None:
                continue
            t["streams"] = sorted(by_tile.get((ty, tx), ()))
            t["dist"] = min(abs(tx - c) for c in stripe_cols)
            results.append(t)
        print(f"row {ty}: {sum(1 for t in results if t['ty'] == ty)} tiles")

    def grp(pred):
        return [t for t in results if pred(t)]
    groups = {
        "stripe (C+M+Y certified)": grp(lambda t: set(t["streams"]) >= {"C", "M", "Y"}),
        "C-only, 1-2 cols from stripe": grp(lambda t: t["streams"] == ["C"] and 1 <= t["dist"] <= 2),
        "C-only, >=4 cols from stripe": grp(lambda t: t["streams"] == ["C"] and t["dist"] >= 4),
    }
    summary = {name: summarize(g) for name, g in groups.items()}

    # --- summary.md
    lines = ["# Sheet F stripe analysis", "",
             f"run dir `{args.run_dir}`, rows {rows}, stripe columns {stripe_cols}", ""]
    lines += ["| group | n | plane | d' | contrast | white mu (sd) | ink mu (sd) | under-other-ink mu | iso mu | run-h mu | run-v mu | reg dx,dy (dots) | corr |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in summary.items():
        for p in PLANES:
            v = s[p]
            if not v:
                continue
            lines.append(
                f"| {name} | {s['n']} | {p} | {v['dprime'][0]:.2f}±{v['dprime'][1]:.2f} "
                f"| {v['contrast'][0]:.1f} | {v['white_mu'][0]:.1f} ({v['white_sd'][0]:.1f}) "
                f"| {v['ink_mu'][0]:.1f} ({v['ink_sd'][0]:.1f}) | {v['under_mu'][0]:.1f} "
                f"| {v['iso_mu'][0]:.1f} | {v['run_h_mu'][0]:.1f} | {v['run_v_mu'][0]:.1f} "
                f"| {v['reg_dx_dots'][0]:+.2f},{v['reg_dy_dots'][0]:+.2f} | {v['corr'][0]:.2f} |")
    lines += ["", "| group | PSD R cell | PSD G cell | PSD B cell | PSD R dot | PSD G dot | PSD B dot | PSD G low | PSD B low |",
              "|---|---|---|---|---|---|---|---|---|"]
    for name, s in summary.items():
        f = lambda k: f"{s[k][0]:.3g}" if s.get(k) else "-"
        lines.append(f"| {name} | {f('psd_R_cell')} | {f('psd_G_cell')} | {f('psd_B_cell')} "
                     f"| {f('psd_R_dot')} | {f('psd_G_dot')} | {f('psd_B_dot')} | {f('psd_G_low')} | {f('psd_B_low')} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    # --- per-tile metrics (drop arrays)
    slim = []
    for t in results:
        slim.append({k: v for k, v in t.items() if not k.startswith("_")})
    (out / "metrics.json").write_text(json.dumps(slim, indent=1, default=float))

    # --- column profile of d' per plane
    prof = {p: [] for p in PLANES}
    for tx in range(tiles_yx[1]):
        col = [t for t in results if t["tx"] == tx]
        for p in PLANES:
            v = [t[p]["dprime"] for t in col if p in t]
            prof[p].append(float(np.nanmean(v)) if v else np.nan)
    xs = np.arange(tiles_yx[1])
    plot_lines([("C (R channel)", xs, prof["C"], (0, 160, 220)),
                ("M (G channel)", xs, prof["M"], (200, 0, 160)),
                ("Y (B channel)", xs, prof["Y"], (200, 170, 0))],
               "single-ink vs white separation d' by tile column (mean over rows)",
               "tile column tx", "d'", vlines=stripe_cols).save(out / "profile_dprime.png")
    regp = {p: [] for p in PLANES}
    for tx in range(tiles_yx[1]):
        col = [t for t in results if t["tx"] == tx]
        for p in PLANES:
            v = [t[p]["reg_dx_dots"] for t in col if p in t]
            regp[p].append(float(np.nanmean(v)) if v else np.nan)
    plot_lines([("C dx", xs, regp["C"], (0, 160, 220)),
                ("M dx", xs, regp["M"], (200, 0, 160)),
                ("Y dx", xs, regp["Y"], (200, 170, 0))],
               "best-correlation x offset per plane (printer dots) by tile column",
               "tile column tx", "dots", vlines=stripe_cols).save(out / "profile_regx.png")

    # --- pooled histograms (G for M, B for Y), stripe vs far
    bins = np.linspace(0, 260, 53)
    for p, ch in (("M", "G"), ("Y", "B"), ("C", "R")):
        series = []
        for (name, g), colors in zip(groups.items(),
                                     [((0, 120, 0), (0, 200, 0)), ((120, 60, 0), (220, 120, 0)),
                                      ((0, 0, 140), (60, 60, 240))]):
            wh = np.concatenate([t["_samples"][p][0] for t in g if "_samples" in t and p in t["_samples"]] or [np.zeros(0)])
            ink = np.concatenate([t["_samples"][p][1] for t in g if "_samples" in t and p in t["_samples"]] or [np.zeros(0)])
            series.append((f"{name}: white cells", wh, colors[0]))
            series.append((f"{name}: single-{p} cells", ink, colors[1]))
        plot_hist(series, f"{ch} channel per cell: white vs single-{p} ink", f"{ch} value (0 dark .. 255 white)",
                  bins, size=(900, 480)).save(out / f"hist_{p}.png")

    # --- spectra: mean radial PSD per group, G and B
    for ch in ("G", "B", "R"):
        series = []
        for (name, g), color in zip(groups.items(), [(0, 160, 0), (220, 120, 0), (60, 60, 240)]):
            ps = [t["_psd"][ch] for t in g if "_psd" in t]
            if not ps:
                continue
            m = np.nanmean(np.stack(ps), axis=0)
            edges = np.linspace(0, 0.5, m.size + 1)
            series.append((name, 0.5 * (edges[:-1] + edges[1:]), m, color))
        pitch = results[0]["pitch_px"]
        plot_lines(series, f"radial power spectrum, {ch} channel (log10)", "cycles/px",
                   "log10 power", logy=True, size=(900, 480),
                   vlines=[1 / pitch, 3 / pitch]).save(out / f"psd_{ch}.png")

    # --- patches: middle profiled row, stripe tile + neighbours at 1, 4, 8
    ty = rows[len(rows) // 2]
    tx_s = [tx for (r, tx) in full if r == ty]
    if not tx_s:
        ty, tx0 = full[len(full) // 2]
    else:
        tx0 = tx_s[0]
    side = 1 if tx0 < tiles_yx[1] // 2 else -1
    picks = [(f"stripe tile ({ty},{tx0}) streams {sorted(by_tile[(ty, tx0)])}", ty, tx0)]
    for dcol in (1, 4, 8):
        tx = tx0 + side * dcol
        if 0 <= tx < tiles_yx[1]:
            picks.append((f"tile ({ty},{tx}) {dcol} cols away, streams {sorted(by_tile.get((ty, tx), ()))}", ty, tx))
    tiles = []
    for label, r, c in picks:
        t = analyze_tile(inputs, gt_cells, r, c, keep_patch=True)
        if t and "_patch" in t:
            tiles.append((label, t))
    grid_figure(tiles, 0.5, out / "patches.png")
    grid_figure(tiles, 3.0, out / "zoom_gt.png", zoom_cells=12)
    print("figures written to", out)


if __name__ == "__main__":
    main()
