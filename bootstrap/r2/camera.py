#!/usr/bin/env python3
"""R2 camera / scanner degradation simulator, v1 (R2-FORMAT.md v1, "What the
camera simulator must reproduce").

600-dpi page bitmap (PBM P4, or PNG: dark = ink) -> constrained PGM
(P5 default, P2 with --p2): header exactly b'P5\\nW H\\n255\\n' then W*H bytes
(P2: the same header with 'P2', then one image row per line, values
separated by single spaces), no comments.  Seeded and deterministic.

Pipeline (all in page space until the warp):
  1. reflectance: paper P where the bit is 0, ink K where it is 1 (damage,
     --damage, edits the page first: see damage.py);
  2. area-average to an integer sub-grid of f dots (f chosen so the
     sub-grid samples at least twice per output pixel);
  3. Gaussian blur, sigma^2 = blur_modules^2 + 1/(12 spm^2) (optics PSF
     plus the pixel's box aperture), in module units;
  4. perspective.  WHOLE PAGE (no --crop/--frame; v0, unchanged): the page's
     four corners, placed at spm samples per module inside a canvas padded
     by pad_frac of the diagonal, each displaced by a random vector uniform
     in a disc of radius persp * (page diagonal in output pixels); optional
     rotation about the page centre.  FRAME (--crop/--frame): the frame is
     the page region X0..X0+W, Y0..Y0+H (fractions of the page bitmap) at
     spm samples per module, no padding; the region's four corners are
     rotated by --rotate about the frame centre and each displaced uniformly
     in a disc of radius persp * (FRAME diagonal in output pixels), so the
     camera sees a slightly different quadrilateral of the page; only the
     page window the frame needs is blurred (exact away from its edges).
     Either way: homography through the four points, every output pixel
     centre inverse-mapped and bilinearly sampled; outside the page =
     background B;
  5. illumination: gain 1 + illum*(2t-1), t in [0,1] the pixel's position
     along a random direction across the frame (so +-illum);
  6. additive Gaussian noise sigma = noise/255; clip; round to 0..255;
  7. image-space damage (crop-E cuts), then --rot90 K: K quarter turns
     CLOCKWISE of the finished frame.

A truth sidecar (OUT.json, OUT minus its extension) records every
parameter, the seed, the frame (name, crop fractions, region in dots), the
rotation, the damage records (with the grid blocks each touches), the corner
displacements and the homography page-dots -> frame-pixels after every cut
and rotation (`homography_page_dots_to_px`; pixel (u, v) spans [u, u+1) x
[v, v+1); dot (x, y) likewise in page dots), plus, with --sidecar,
`homography_grid_modules_to_px` (module (c, r) spans [c, c+1) x [r, r+1)).

Presets (parameters; v0's, unchanged):
  nominal     2.0 spm, persp 0.02, blur 0.6, illum 0.20, noise 10
  hard        1.5 spm, otherwise nominal
  flatbed300  300 dpi (spm = module_dots/2), persp 0, rotate 0.5 deg,
              blur 0.10, illum 0.03, noise 3, white lid background
  (R2-FORMAT v1's envelope is blur <= 0.45 module: pass --blur.)
Frames (--frame NAME = a --crop rectangle, fractions of the page bitmap):
  tl tr bl br   the four quarters (half width x half height)
  top mid bot   the three thirds by height, full width (mid = the centre
                third)
  centre        the central quarter (0.25 .. 0.75 both ways)

Usage: camera.py PAGE.pbm OUT.pgm [--sidecar PAGE.json | --module-dots 12]
                 [--preset nominal] [--seed 1] [--spm X] [--persp X]
                 [--blur X] [--illum X] [--noise X] [--rotate DEG]
                 [--paper X] [--ink X] [--background X] [--p2]
                 [--png PREVIEW.png]
                 [--crop X0 Y0 W H | --frame NAME] [--rot90 K]
                 [--damage KIND ...]          (KINDS: see damage.py)
--damage needs --sidecar (the grid geometry and the bullseye list).
"""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import damage as dmg  # noqa: E402

PRESETS = {
    "nominal": dict(spm=2.0, persp=0.02, blur=0.6, illum=0.20, noise=10.0,
                    rotate=0.0, paper=0.80, ink=0.10, background=0.30,
                    pad_frac=0.02),
    "hard": dict(spm=1.5, persp=0.02, blur=0.6, illum=0.20, noise=10.0,
                 rotate=0.0, paper=0.80, ink=0.10, background=0.30,
                 pad_frac=0.02),
    "flatbed300": dict(dpi=300, persp=0.0, blur=0.10, illum=0.03,
                       noise=3.0, rotate=0.5, paper=0.88, ink=0.06,
                       background=0.93, pad_frac=0.01),
}
FRAMES = {
    "tl": (0.0, 0.0, 0.5, 0.5), "tr": (0.5, 0.0, 0.5, 0.5),
    "bl": (0.0, 0.5, 0.5, 0.5), "br": (0.5, 0.5, 0.5, 0.5),
    "top": (0.0, 0.0, 1.0, 1 / 3), "mid": (0.0, 1 / 3, 1.0, 1 / 3),
    "bot": (0.0, 2 / 3, 1.0, 1 / 3),
    "centre": (0.25, 0.25, 0.5, 0.5),
}
PARAMS = ("spm", "persp", "blur", "illum", "noise", "rotate", "paper", "ink",
          "background")


def load_page(path):
    raw = open(path, "rb").read()
    if raw[:2] == b"P4":
        parts = raw.split(b"\n", 2)
        w, h = map(int, parts[1].split())
        bits = np.unpackbits(np.frombuffer(parts[2], dtype=np.uint8))
        return bits.reshape(h, -1)[:, :w].astype(np.uint8)
    im = np.asarray(Image.open(path).convert("L"))
    return (im < 128).astype(np.uint8)


def area_down(a, f):
    if f == 1:
        return a
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3))


def gauss_blur(a, sigma):
    """Separable Gaussian, sigma in pixels of a; edges replicate."""
    if sigma <= 0:
        return a
    r = max(1, int(math.ceil(3.5 * sigma)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k = (k / k.sum()).astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r, r)
        p = np.pad(a, pad, mode="edge")
        out = np.zeros_like(a)
        n = a.shape[axis]
        for i, kv in enumerate(k):
            sl = [slice(None), slice(None)]
            sl[axis] = slice(i, i + n)
            out += kv * p[tuple(sl)]
        a = out
    return a


def homography(src, dst):
    m = []
    for (x, y), (u, v) in zip(src, dst):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y, u])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y, v])
    m = np.array(m, dtype=np.float64)
    hvec = np.linalg.solve(m[:, :8], m[:, 8])
    return np.append(hvec, 1.0).reshape(3, 3)


def bilinear(img, qx, qy, outside):
    h, w = img.shape
    x0 = np.floor(qx).astype(np.int64)
    y0 = np.floor(qy).astype(np.int64)
    fx = (qx - x0).astype(np.float32)
    fy = (qy - y0).astype(np.float32)
    x0c = np.clip(x0, 0, w - 1)
    x1c = np.clip(x0 + 1, 0, w - 1)
    y0c = np.clip(y0, 0, h - 1)
    y1c = np.clip(y0 + 1, 0, h - 1)
    v = ((img[y0c, x0c] * (1 - fx) + img[y0c, x1c] * fx) * (1 - fy)
         + (img[y1c, x0c] * (1 - fx) + img[y1c, x1c] * fx) * fy)
    return np.where(outside, np.float32(0), v), outside


def simulate(page, md, p, seed):
    """Whole-page capture (v0, unchanged)."""
    rng = np.random.default_rng(seed)
    hd, wd = page.shape
    spm = p["spm"]
    s = spm / md                               # output px per dot
    f = max(1, int(md / (2.0 * spm)))          # sub-grid dots per sample
    refl = np.float32(p["paper"]) - np.float32(p["paper"] - p["ink"]) * \
        page.astype(np.float32)
    sub = area_down(refl, f).astype(np.float32)
    sig_mod = math.sqrt(p["blur"] ** 2 + 1.0 / (12.0 * spm * spm))
    sub = gauss_blur(sub, sig_mod * md / f)
    diag_px = math.hypot(wd * s, hd * s)
    disp_max = p["persp"] * diag_px
    rot = math.radians(p["rotate"])
    rot_px = abs(math.sin(rot)) * max(wd, hd) * s * 0.5
    pad = int(math.ceil(disp_max + rot_px + p["pad_frac"] * diag_px)) + 2
    cw, ch = int(math.ceil(wd * s)) + 2 * pad, int(math.ceil(hd * s)) + 2 * pad
    src = [(0.0, 0.0), (wd, 0.0), (wd, hd), (0.0, hd)]
    cx, cy = wd / 2.0, hd / 2.0
    disp = []
    dst = []
    for (x, y) in src:
        rx = cx + (x - cx) * math.cos(rot) - (y - cy) * math.sin(rot)
        ry = cy + (x - cx) * math.sin(rot) + (y - cy) * math.cos(rot)
        ang = rng.uniform(0, 2 * math.pi)
        rad = disp_max * math.sqrt(rng.uniform(0, 1))
        dx, dy = rad * math.cos(ang), rad * math.sin(ang)
        disp.append((dx, dy))
        dst.append((pad + rx * s + dx, pad + ry * s + dy))
    hm = homography(src, dst)
    hinv = np.linalg.inv(hm)
    vv, uu = np.mgrid[0:ch, 0:cw]
    u = uu.astype(np.float64) + 0.5
    v = vv.astype(np.float64) + 0.5
    den = hinv[2, 0] * u + hinv[2, 1] * v + hinv[2, 2]
    x = (hinv[0, 0] * u + hinv[0, 1] * v + hinv[0, 2]) / den
    y = (hinv[1, 0] * u + hinv[1, 1] * v + hinv[1, 2]) / den
    outside = (x < 0) | (y < 0) | (x >= wd) | (y >= hd)
    img, _ = bilinear(sub, x / f - 0.5, y / f - 0.5, outside)
    img = np.where(outside, np.float32(p["background"]), img)
    ang = rng.uniform(0, 2 * math.pi)
    t = uu * math.cos(ang) + vv * math.sin(ang)
    t = (t - t.min()) / max(1e-9, float(t.max() - t.min()))
    img = img * (1.0 + p["illum"] * (2.0 * t - 1.0)).astype(np.float32)
    img = img + rng.normal(0.0, p["noise"] / 255.0, img.shape).astype(
        np.float32)
    out = np.clip(np.rint(img * 255.0), 0, 255).astype(np.uint8)
    truth = dict(seed=seed, module_dots=md, sub_dots=f,
                 blur_total_modules=sig_mod, canvas=[cw, ch], pad_px=pad,
                 corner_disp_px=disp,
                 corner_disp_max_frac_diag=max(math.hypot(a, b)
                                               for a, b in disp) / diag_px,
                 illum_dir_rad=ang, homography_page_dots_to_px=hm.tolist())
    return out, truth


def simulate_frame(page, md, p, seed, region):
    """Partial frame: region = (X0, Y0, W, H) in page dots."""
    rng = np.random.default_rng(seed)
    hd, wd = page.shape
    X0, Y0, CW, CH = region
    spm = p["spm"]
    s = spm / md
    f = max(1, int(md / (2.0 * spm)))
    fw, fh = int(round(CW * s)), int(round(CH * s))
    if fw < 1 or fh < 1:
        raise SystemExit("frame smaller than one pixel")
    diag_px = math.hypot(CW * s, CH * s)
    disp_max = p["persp"] * diag_px
    rot = math.radians(p["rotate"])
    src = [(X0, Y0), (X0 + CW, Y0), (X0 + CW, Y0 + CH), (X0, Y0 + CH)]
    fcx, fcy = CW * s / 2.0, CH * s / 2.0
    disp, dst = [], []
    for (x, y) in src:
        u, v = (x - X0) * s - fcx, (y - Y0) * s - fcy
        ru = fcx + u * math.cos(rot) - v * math.sin(rot)
        rv = fcy + u * math.sin(rot) + v * math.cos(rot)
        ang = rng.uniform(0, 2 * math.pi)
        rad = disp_max * math.sqrt(rng.uniform(0, 1))
        dx, dy = rad * math.cos(ang), rad * math.sin(ang)
        disp.append((dx, dy))
        dst.append((ru + dx, rv + dy))
    hm = homography(src, dst)
    hinv = np.linalg.inv(hm)
    vv, uu = np.mgrid[0:fh, 0:fw]
    u = uu.astype(np.float64) + 0.5
    v = vv.astype(np.float64) + 0.5
    den = hinv[2, 0] * u + hinv[2, 1] * v + hinv[2, 2]
    x = (hinv[0, 0] * u + hinv[0, 1] * v + hinv[0, 2]) / den
    y = (hinv[1, 0] * u + hinv[1, 1] * v + hinv[1, 2]) / den
    outside = (x < 0) | (y < 0) | (x >= wd) | (y >= hd)
    sig_mod = math.sqrt(p["blur"] ** 2 + 1.0 / (12.0 * spm * spm))
    marg = int(math.ceil(4.0 * sig_mod * md)) + 2 * f + 2
    xa = max(0, int(math.floor(x.min())) - marg) // f * f
    ya = max(0, int(math.floor(y.min())) - marg) // f * f
    xb = min(wd, int(math.ceil(x.max())) + marg)
    yb = min(hd, int(math.ceil(y.max())) + marg)
    if xb - xa >= f and yb - ya >= f:
        win = page[ya:yb, xa:xb]
        refl = np.float32(p["paper"]) - np.float32(p["paper"] - p["ink"]) * \
            win.astype(np.float32)
        sub = area_down(refl, f).astype(np.float32)
        sub = gauss_blur(sub, sig_mod * md / f)
        img, _ = bilinear(sub, (x - xa) / f - 0.5, (y - ya) / f - 0.5,
                          outside)
    else:
        img = np.zeros((fh, fw), dtype=np.float32)
        outside = np.ones((fh, fw), dtype=bool)
    img = np.where(outside, np.float32(p["background"]), img)
    ang = rng.uniform(0, 2 * math.pi)
    t = uu * math.cos(ang) + vv * math.sin(ang)
    t = (t - t.min()) / max(1e-9, float(t.max() - t.min()))
    img = img * (1.0 + p["illum"] * (2.0 * t - 1.0)).astype(np.float32)
    img = img + rng.normal(0.0, p["noise"] / 255.0, img.shape).astype(
        np.float32)
    out = np.clip(np.rint(img * 255.0), 0, 255).astype(np.uint8)
    truth = dict(seed=seed, module_dots=md, sub_dots=f,
                 blur_total_modules=sig_mod, canvas=[fw, fh], pad_px=0,
                 page_window_dots=[xa, ya, xb, yb], corner_disp_px=disp,
                 corner_disp_max_frac_diag=max(math.hypot(a, b)
                                               for a, b in disp) / diag_px,
                 illum_dir_rad=ang, homography_page_dots_to_px=hm.tolist())
    return out, truth


def rot90_cw(img, hm, k):
    """k quarter turns clockwise; pixel (u, v) -> (h - v, u) per turn."""
    hm = np.asarray(hm, dtype=np.float64)
    for _ in range(k % 4):
        h = img.shape[0]
        hm = np.array([[0, -1, h], [1, 0, 0], [0, 0, 1]],
                      dtype=np.float64) @ hm
        img = np.rot90(img, -1)
    return np.ascontiguousarray(img), hm


def capture(page, md, p, seed, region=None, rot90=0, cuts=(), wd=None,
            hd=None):
    """simulate / simulate_frame, then the cuts, then rot90.  -> (img,
    truth) with the final homography in truth['homography_page_dots_to_px']
    and the warp's own in truth['homography_page_dots_to_canvas_px']."""
    hd = page.shape[0] if hd is None else hd
    wd = page.shape[1] if wd is None else wd
    if region is None:
        img, truth = simulate(page, md, p, seed)
    else:
        img, truth = simulate_frame(page, md, p, seed, region)
    hm = np.array(truth["homography_page_dots_to_px"])
    truth["homography_page_dots_to_canvas_px"] = hm.tolist()
    cut_recs = []
    for c in cuts:
        img, hm, rec = dmg.cut(img, hm, c, wd, hd)
        cut_recs.append(rec)
    img, hm = rot90_cw(img, hm, rot90)
    truth.update(cuts=cut_recs, rot90=rot90 % 4, rot90_direction="clockwise",
                 size_px=[img.shape[1], img.shape[0]],
                 homography_page_dots_to_px=(hm / hm[2, 2]).tolist())
    return img, truth


def write_pgm(path, img, p2=False):
    h, w = img.shape
    with open(path, "wb") as fo:
        if p2:
            fo.write(b"P2\n%d %d\n255\n" % (w, h))
            for row in img:
                fo.write((" ".join(map(str, row.tolist())) + "\n").encode())
        else:
            fo.write(b"P5\n%d %d\n255\n" % (w, h))
            fo.write(img.tobytes())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("page")
    ap.add_argument("out")
    ap.add_argument("--sidecar")
    ap.add_argument("--module-dots", type=int)
    ap.add_argument("--preset", default="nominal", choices=sorted(PRESETS))
    ap.add_argument("--seed", type=int, default=1)
    for k in PARAMS:
        ap.add_argument("--" + k, type=float)
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--png")
    fr = ap.add_mutually_exclusive_group()
    fr.add_argument("--crop", type=float, nargs=4,
                    metavar=("X0", "Y0", "W", "H"),
                    help="frame = this region, fractions of the page bitmap")
    fr.add_argument("--frame", choices=sorted(FRAMES),
                    help="a named --crop rectangle")
    ap.add_argument("--rot90", type=int, default=0, choices=(0, 1, 2, 3),
                    help="quarter turns clockwise of the finished frame")
    ap.add_argument("--damage", action="append", default=[],
                    metavar="KIND", help="see damage.py; repeatable")
    a = ap.parse_args(argv)
    side = json.load(open(a.sidecar)) if a.sidecar else None
    md = a.module_dots
    if md is None:
        md = side["module_dots"] if side else 12
    p = dict(PRESETS[a.preset])
    if "dpi" in p:
        p["spm"] = md * p.pop("dpi") / 600.0
    for k in PARAMS:
        if getattr(a, k) is not None:
            p[k] = getattr(a, k)
    page = load_page(a.page)
    hd, wd = page.shape
    crop = FRAMES[a.frame] if a.frame else (tuple(a.crop) if a.crop else None)
    region = None
    if crop is not None:
        if crop[2] <= 0 or crop[3] <= 0:
            raise SystemExit("--crop W and H must be positive")
        region = (crop[0] * wd, crop[1] * hd, crop[2] * wd, crop[3] * hd)
    cuts = [k for k in a.damage if dmg.is_cut(k)]
    if cuts and region is not None:
        raise SystemExit("crop-* damage cuts a whole-page capture; use "
                         "--crop for a partial frame instead")
    recs = []
    page_kinds = [k for k in a.damage if not dmg.is_cut(k)]
    if page_kinds:
        if side is None:
            raise SystemExit("--damage needs --sidecar")
        page = page.astype(np.float32)
        for k in page_kinds:
            page, rec = dmg.apply(page, side, k, p["paper"], p["ink"],
                                  p["background"])
            recs.append(rec)
    img, truth = capture(page, md, p, a.seed, region, a.rot90, cuts, wd, hd)
    write_pgm(a.out, img, a.p2)
    if a.png:
        Image.fromarray(img).save(a.png)
    sha = hashlib.sha256(open(a.out, "rb").read()).hexdigest()
    rec = dict(preset=a.preset, params=p, page=a.page,
               page_sha256=hashlib.sha256(open(a.page, "rb").read())
               .hexdigest(), out=a.out, out_sha256=sha,
               format="P2" if a.p2 else "P5",
               frame=a.frame, crop_frac=list(crop) if crop else None,
               region_dots=list(region) if region else [0, 0, wd, hd],
               damage=recs, **truth)
    if side is not None:
        g2d = np.array([[md, 0, side["x0_dots"]], [0, md, side["y0_dots"]],
                        [0, 0, 1]], dtype=np.float64)
        hmg = np.array(truth["homography_page_dots_to_px"]) @ g2d
        rec["homography_grid_modules_to_px"] = (hmg / hmg[2, 2]).tolist()
        rec["page_sidecar"] = a.sidecar
    stem = a.out.rsplit(".", 1)[0]
    with open(stem + ".json", "w") as fo:
        json.dump(rec, fo, indent=1)
    print(f"{a.out}: {img.shape[1]}x{img.shape[0]} "
          f"({img.size / 1e6:.2f} MP) spm={p['spm']}"
          f"{' frame=' + (a.frame or str(list(crop))) if crop else ''}"
          f"{' rot90=' + str(a.rot90) if a.rot90 else ''}"
          f"{' damage=' + ','.join(a.damage) if a.damage else ''}"
          f" sha256={sha}")


if __name__ == "__main__":
    sys.exit(main())
