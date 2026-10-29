"""R3 test volume + simulated flatbed scans for bootstrap/r3/receiver.py.

Generator-side harness (uses src/holo, numpy, scipy, ghostscript); the
receiver never imports anything from here and never reads a sidecar.

  volume   payload (bootstrap/*.md + src/holo/format/*.py, concatenated with
           '==> path <==' headers, cut at PAYLOAD_BYTES) -> `holo generate
           --format c3-k-r0550@35x24 --source-fraction 0.5` (A4-6mm, the
           default printer) -> each page's PostScript rasterised by
           ghostscript at 600 dpi with the bitcmyk device, K plane taken
           (never pbmraw) and checked against the generator's own GT dots.
  scans    simulated flatbed captures of every page, one PGM per
           (variant, page) + a truth JSON sidecar each.

Outputs under bootstrap/build/r3/ (gitignored).  Run from the worktree root:
  PYTHONPATH=src env/bin/python bootstrap/r3/make_test_volume.py volume
  PYTHONPATH=src env/bin/python bootstrap/r3/make_test_volume.py scans [variant ...]
  (add --c4 to either for the c4-k-r0550@26x18 variant, output build/r3/c4/)
"""
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
C4 = "--c4" in sys.argv
OUT = ROOT / "bootstrap" / "build" / "r3" / ("c4" if C4 else "")
FORMAT = "c4-k-r0550@26x18" if C4 else "c3-k-r0550@35x24"
CELL_DOTS = 4 if C4 else 3
Q = "0.5"
PAYLOAD_BYTES = 110_000 if C4 else 200_000   # needs two pages at q 0.5
PAGE_DOTS_YX = (7016, 4960)                   # A4 at 600 dpi

# variant -> (dpi, rotation deg, scale, seams, blank fraction)
VARIANTS = {
    "base1200": (1200, 0.0, 1.0, False, 0.0),
    "s2400": (2400, 0.0, 1.0, False, 0.0),
    "scale": (1200, 0.0, 1.004, False, 0.0),
    "rot03": (1200, 0.3, 1.0, False, 0.0),
    "rot15": (1200, 1.5, 1.0, False, 0.0),
    "seam": (1200, 0.0, 1.0, True, 0.0),
    "combo": (1200, 180.3, 1.004, True, 0.0),
    "blank40": (1200, 0.0, 1.0, False, 0.4),
}
# a rougher channel (overrides of the light defaults below): heavier blur,
# toner gain (+~0.4 dot per edge), lower contrast, much more noise, on top
# of the 0.3 degree / +0.4 % / seam geometry -- to exercise the LDPC
ROUGH = {"rough": dict(paper=215.0, ink=75.0, noise=34.0, blur=0.75,
                       gain_sigma=0.5, gain=1.7, cell_flips=0.03)}
VARIANTS["rough"] = (1200, 0.3, 1.004, True, 0.0)
# quarter turns of the base capture (the page laid sideways on the bed)
TURNS = {"turn90": 1, "turn270": 3}
PAPER_GREY, INK_GREY, NOISE_SIGMA = 232.0, 38.0, 6.0
BLUR_SIGMA_DOTS = 0.35            # light optical blur, in printed dots
SEAM_FIRST_MM, SEAM_STEP_MM, SEAM_DOTS = 16.51, 18.288, 0.84


def run(*cmd, env=None):
    subprocess.run(cmd, check=True, env=env)


def make_payload() -> bytes:
    parts = []
    files = sorted((ROOT / "bootstrap").glob("*.md")) + sorted(
        (ROOT / "src" / "holo" / "format").glob("*.py"))
    for f in files:
        parts.append(f"==> {f.relative_to(ROOT)} <==\n".encode())
        parts.append(f.read_bytes())
    data = b"".join(parts)
    assert len(data) >= PAYLOAD_BYTES
    return data[:PAYLOAD_BYTES]


def volume():
    OUT.mkdir(parents=True, exist_ok=True)
    payload = make_payload()
    (OUT / "payload.bin").write_bytes(payload)
    vol = OUT / "vol"
    if not vol.exists():
        import os
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        run(sys.executable, "-m", "holo.cli", "generate", "--format", FORMAT,
            "--source-fraction", Q, "-o", str(vol), str(OUT / "payload.bin"),
            env=env)
    man = json.loads((vol / "manifest.json").read_text())
    pages = sorted(vol.glob("page*.ps"))
    truth = {"format": FORMAT, "q": Q, "payload_bytes": len(payload),
             "payload_sha256": hashlib.sha256(payload).hexdigest(),
             "pages": len(pages), "manifest": man}
    for ps in pages:
        k_png = ps.with_suffix(".k.npy")
        if not k_png.exists():
            raw = ps.with_suffix(".cmyk")
            run("gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-r600",
                "-sDEVICE=bitcmyk", f"-sOutputFile={raw}", str(ps))
            h, w = PAGE_DOTS_YX
            b = np.frombuffer(raw.read_bytes(), np.uint8)
            assert b.size == h * w // 2, (b.size, h, w)
            # bitcmyk: 4 bits per pixel, C M Y K, MSB first; K = bit 0 of the nibble
            hi, lo = b >> 4, b & 15
            nib = np.stack([hi, lo], axis=1).reshape(h, w)
            k = (nib & 1).astype(np.uint8)
            cmy = (nib & 14).any()
            assert not cmy, "colour toner on a K page"
            np.save(k_png, k)
            raw.unlink()
        k = np.load(k_png)
        gt = np.unpackbits(np.load(str(ps).replace(".ps", "_gt.npy")),
                           axis=1, bitorder="big")
        oy, ox = find_origin(man)
        field = k[oy:oy + gt.shape[0], ox:ox + gt.shape[1]][:, :]
        same = np.array_equal(field, gt[:, :field.shape[1]])
        outside = int(k.sum() - field.sum())
        truth.setdefault("gs_vs_gt", []).append(
            {"page": ps.name, "field_identical": bool(same),
             "ink_outside_field": outside, "origin_dots_yx": [oy, ox],
             "field_dots_yx": list(gt.shape)})
        print(ps.name, "gs K plane == generator GT:", same,
              "ink outside field:", outside)
    (OUT / "volume.json").write_text(json.dumps(truth, indent=1))
    print(json.dumps({k: v for k, v in truth.items() if k != "manifest"},
                     indent=1))


def find_origin(man):
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("origin_dots_yx",) and isinstance(v, list):
                    return v
                r = walk(v)
                if r:
                    return r
        if isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r
        return None
    r = walk(man)
    if r is None:
        raise SystemExit("no origin_dots_yx in manifest")
    return tuple(r)


def simulate(page_k: np.ndarray, dpi: int, rot_deg: float, scale: float,
             seams: bool, rng: np.random.Generator, ch=None):
    """Render one 600-dpi dot page as a flatbed capture: the page (plus a
    white bed margin) at `dpi`, rotated about its centre by rot_deg,
    scaled by `scale`, Canon seams (the image shifted +0.84 printed dots in
    x for every sensor column beyond 16.51 + 18.288k mm, cumulative), light
    Gaussian blur, Gaussian noise, 8-bit grey."""
    h, w = page_k.shape
    f = dpi / 600.0
    bed = int(round(8 / 25.4 * dpi))                # 8 mm white bed margin
    H, W = int(h * f) + 2 * bed, int(w * f) + 2 * bed
    ch = dict(dict(paper=PAPER_GREY, ink=INK_GREY, noise=NOISE_SIGMA,
                   blur=BLUR_SIGMA_DOTS, gain_sigma=0.0, gain=1.0), **(ch or {}))
    src = page_k.astype(np.float32)
    if ch["gain_sigma"]:
        src = np.clip(ndimage.gaussian_filter(src, ch["gain_sigma"]) * ch["gain"], 0, 1)
    th = math.radians(rot_deg)
    c, s = math.cos(th), math.sin(th)
    cy_s, cx_s = (H - 1) / 2, (W - 1) / 2           # scan centre (px)
    cy_p, cx_p = (h - 1) / 2, (w - 1) / 2           # page centre (dots)
    seam_px = []
    if seams:
        mm = SEAM_FIRST_MM
        while mm / 25.4 * dpi < W:
            seam_px.append(mm / 25.4 * dpi)
            mm += SEAM_STEP_MM
    seam_px = np.array(seam_px)
    sigma_px = ch["blur"] * f
    pad = int(4 * sigma_px) + 2
    out = np.empty((H, W), np.uint8)
    xs = np.arange(W, dtype=np.float64)
    shift = (np.searchsorted(seam_px, xs, side="right") * SEAM_DOTS * f
             if seams else np.zeros(W))
    xs_eff = xs - shift                              # sensor col -> image col
    strip = 512
    for y0 in range(0, H, strip):
        y1 = min(H, y0 + strip)
        ya, yb = max(0, y0 - pad), min(H, y1 + pad)
        yy = np.arange(ya, yb, dtype=np.float64)[:, None]
        dy = (yy - cy_s) / (f * scale)
        dx = (xs_eff[None, :] - cx_s) / (f * scale)
        # inverse rotation: scan offset -> page offset
        py = c * dy + s * dx + cy_p
        px = -s * dy + c * dx + cx_p
        ink = ndimage.map_coordinates(src, [py, px], order=1, mode="constant",
                                      cval=0.0)
        ink = ndimage.gaussian_filter(ink, sigma_px, mode="nearest")
        img = ch["paper"] - (ch["paper"] - ch["ink"]) * ink
        img += rng.normal(0.0, ch["noise"], img.shape)
        out[y0:y1] = np.clip(np.rint(img[y0 - ya:y0 - ya + (y1 - y0)]),
                             0, 255).astype(np.uint8)
    truth = {"dpi": dpi, "rotation_deg": rot_deg, "scale": scale,
             "seams_px": seam_px.tolist(), "seam_dots": SEAM_DOTS if seams
             else 0.0, "bed_margin_px": bed, "blur_sigma_px": sigma_px,
             "channel": ch,
             "size_hw": [H, W]}
    return out, truth


def write_pgm(path: Path, img: np.ndarray):
    h, w = img.shape
    with open(path, "wb") as fh:
        fh.write(f"P5\n{w} {h}\n255\n".encode())
        fh.write(np.ascontiguousarray(img).tobytes())


def scans(names):
    vt = json.loads((OUT / "volume.json").read_text())
    man = vt["manifest"]
    oy, ox = find_origin(man)
    tile_dots = 64 * CELL_DOTS
    pages = sorted((OUT / "vol").glob("page*.k.npy"))
    for name in names or list(VARIANTS) + list(TURNS):
        if name in TURNS:
            for pi in range(len(pages)):
                path = OUT / f"{name}_p{pi}.pgm"
                base = OUT / f"base1200_p{pi}.pgm"
                raw = base.read_bytes()
                w, h = map(int, raw.split(b"\n")[1].split())
                img = np.frombuffer(raw[-w * h:], np.uint8).reshape(h, w)
                write_pgm(path, np.rot90(img, TURNS[name]))
                path.with_suffix(".truth.json").write_text(json.dumps(
                    {"variant": name, "page": pi, "from": base.name,
                     "np_rot90_k": TURNS[name], "format": FORMAT}))
                print("wrote", path.name)
            continue
        dpi, rot, scale, seams, blank = VARIANTS[name]
        for pi, kp in enumerate(pages):
            path = OUT / f"{name}_p{pi}.pgm"
            if path.exists():
                print("exists", path.name)
                continue
            k = np.load(kp)
            rng = np.random.default_rng(1000 * pi + sum(map(ord, name)))
            blanked = []
            flips = (ROUGH.get(name) or {}).get("cell_flips", 0.0)
            if flips:            # print defects: whole cells inverted at random
                gt = np.load(str(kp).replace(".k.npy", "_gt.npy"))
                ch_, cw_ = gt.shape[0] // CELL_DOTS, gt.shape[1] * 8 // CELL_DOTS
                flip = rng.random((ch_, cw_)) < flips
                big = np.kron(flip, np.ones((CELL_DOTS, CELL_DOTS), np.uint8)).astype(bool)
                k = k.copy()
                fld = k[oy:oy + big.shape[0], ox:ox + big.shape[1]]
                fld[big] ^= 1
            if blank:
                gt = np.load(str(kp).replace(".k.npy", "_gt.npy"))
                ty_n = gt.shape[0] // tile_dots
                tx_n = gt.shape[1] * 8 // tile_dots
                n = ty_n * tx_n
                pick = np.sort(rng.choice(n, int(round(blank * n)),
                                          replace=False))
                k = k.copy()
                for t in pick:
                    ty, tx = divmod(int(t), tx_n)
                    y, x = oy + ty * tile_dots, ox + tx * tile_dots
                    k[y:y + tile_dots, x:x + tile_dots] = 0
                    blanked.append([ty, tx])
            img, truth = simulate(k, dpi, rot, scale, seams, rng, ROUGH.get(name))
            write_pgm(path, img)
            truth.update(variant=name, page=pi, blanked_tiles=blanked,
                         origin_dots_yx=[oy, ox], format=FORMAT)
            path.with_suffix(".truth.json").write_text(json.dumps(truth))
            print("wrote", path.name, img.shape)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--c4"]
    if not args or args[0] == "volume":
        volume()
    elif args[0] == "scans":
        scans(args[1:])
