"""e041 S3 — sheet F as one PCL 5c planar bilevel colour raster for the M281.

What is printed: sheet F's page (`L:c3-cmy8-p120-v1@2240x1536`, GT
`page000_gt.npy`) as a single PCL raster, bit 1 = colorant on, 600 dpi,
unencoded (Esc*b0M), in one of three colour setups (--mode):
  cmy3     Simple Color device CMY (Esc*r-3U), planes C, M, Y — the mode HP
           documents for colour LaserJets (S3, the primary job);
  kcmy4    Simple Color KCMY (Esc*r-4U), planes K, C, M, Y with K all zero
           but sent — a DeskJet-documented mode (S3b, candidate only);
  cid-cmy  Configure Image Data, short form Esc*v6W 01 02 01 01 01 01:
           Device CMY, Direct by Plane, 1 bit per index and per primary
           (PCL 5 Color Technical Reference), planes C, M, Y (S3c).
The legacy --planes 3/4 spells cmy3/kcmy4 (the S3/S3b manifests' generators).
Why: e038 measured that the M281's PostScript RIP renders a DeviceCMYK
composite as contone and re-screens it; an indexed PCL raster never enters
the PostScript image pipeline, so this rung asks whether the PCL path lays
the primaries down unscreened.  Same bits as every other e041 rung.

Placement = the dots of F's PostScript (`21.12 17.76 translate`, `552.96
806.40 scale`, 595.20 x 841.92 pt page: field 4608 x 6720 dots at top 148,
left 176 of the 4960 x 7016 A4 page; checked against the .ps).  PCL's X
origin is the logical page's left edge, inset 71 dots @300 (142 @600) for
A4 portrait; its Y origin is the top margin, 0 by Esc&l0E after the page
size and orientation (both reset it).  Hence Esc*p34x148Y in 600-dpi PCL
units (Esc&u600D).

--verify renders with GhostPCL (gpcl6, 600 dpi, ppmraw): the job itself
against the GT through gpcl6's measured palette for the mode (and each
plane decoded from it where that palette separates C/M/Y into R/G/B), one
isolation job per plane whose ink must equal that plane at the field origin
bit for bit, and a read-back of the job's own bytes; for cid-cmy also three
controls (no CID, Device RGB, an illegal PEM 2 depth) whose palettes must all
differ from the job's, or gpcl6 is not obeying the CID.  Homebrew's GhostPCL
ships no PCL resident fonts and will not start without one, so a one-glyph
stub TrueType named for its resident table goes to a temp dir; no text.

    PYTHONPATH=src env/bin/python experiments/041-m281-screen-routes/pcl_planar.py \
        --gt <F gen dir>/page000_gt.npy \
        --mode cmy3 --out experiments/041-m281-screen-routes/build/S3-pcl-cmy3.pcl --verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

E = b"\x1b"
UEL = b"\x1b%-12345X"
PAGE_DOTS_XY = (4960, 7016)
ORIGIN_YX = (148, 176)
FIELD_YX = (6720, 4608)
A4_LOGICAL_LEFT_DOTS = 142
GPCL6 = "/opt/homebrew/bin/gpcl6"
GPCL6_ARGS = ("-lPCL5C", "-dNOPAUSE", "-dBATCH", "-sDEVICE=ppmraw", "-r600")
GPCL6_FONT = "NimbusMono-Regular"
CID_DEVICE_CMY_DIRECT_BY_PLANE = bytes([1, 2, 1, 1, 1, 1])
MODES = {  # --mode: colour setup, transfer order, PJL job name, what, the unverified risk
    "cmy3": (E + b"*r-3U", ("C", "M", "Y"), "E041-S3-PCL-CMY3",
        "PCL 5c Simple Color device CMY (Esc*r-3U) planar bilevel raster, planes C, M, Y, "
        "600 dpi, compression 0, no K plane, no PostScript",
        "A C+M+Y cell is device-CMY palette index 7 ('black'); the M281 may print it with K "
        "toner instead of the three colour toners. gpcl6 renders RGB and cannot show this. "
        "It is a measurement the sheet itself will make, not a defect."),
    "kcmy4": (E + b"*r-4U", ("K", "C", "M", "Y"), "E041-S3-PCL-PLANAR",
        "PCL 5c Simple Color KCMY (Esc*r-4U) planar bilevel raster, 600 dpi, "
        "compression 0, K plane all zero but sent, no PostScript",
        "-4 is DeskJet-documented: ignored, the 1-plane default prints plane 1 (K, zero) = blank "
        "(as gpcl6 does); read as -3, planes shift K->C->M->Y. gpcl6's -4 palette is not KCMY "
        "(Y and every Y combination black, C+M #0033ff): the Y plane's colour is unverified."),
    "cid-cmy": (E + b"*v6W" + CID_DEVICE_CMY_DIRECT_BY_PLANE, ("C", "M", "Y"), "E041-S3C-PCL-CID-CMY",
                "PCL 5c Configure Image Data short form (Esc*v6W 01 02 01 01 01 01: Device CMY, "
                "Direct by Plane, 1 bit per index and per primary) planar bilevel raster, planes "
                "C, M, Y, 600 dpi, compression 0, no K plane, no PostScript",
                "Unverified on the M281: (1) that its formatter accepts CID PEM 2 in Device CMY at "
                "all (a refused CID leaves the Esc E default palette: 1 plane, black — each row's "
                "first plane, C, would print as K and M/Y be dropped, or the raster be skipped); "
                "(2) that it lays a 1-bit Device CMY primary as that toner alone, unscreened and "
                "without colour matching — Device CMY is the complement of Device RGB (gpcl6's "
                "byte-0 control renders exactly that) and an HP colour pipeline may convert through "
                "RGB, with its default render algorithm (Esc*t#J not sent), colour treatment and "
                "CMYK separation; (3) that C+M+Y is laid as three colour toners, not replaced by K "
                "(GCR/UCR on 'black'); (4) shared with S3: the A4 logical-page offset (142 dots), "
                "Esc*t600R and Esc&u600D on the M281. gpcl6 renders RGB and cannot show (2) or "
                "(3); it renders this job byte-identically to S3's Esc*r-3U, so it cannot tell "
                "the two routes apart either — only the printed sheet can."),
}
PLANES_ALIAS = {3: "cmy3", 4: "kcmy4"}  # the legacy --planes spelling
CID_CONTROLS = {  # --verify, cid-cmy: the palette probe with its colour setup swapped
    "no CID (Esc E default palette)": b"",
    "byte 0 = 0 (Device RGB)": E + b"*v6W" + bytes([0, 2, 1, 1, 1, 1]),
    "byte 3 = 8 (illegal for PEM 2)": E + b"*v6W" + bytes([1, 2, 1, 8, 1, 1]),
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_gt(path: Path) -> tuple[np.ndarray, dict]:
    """Packed C/M/Y GT (3, 6720, 576), both manifest shas checked."""
    packed = np.load(path)
    man = json.loads((path.parent / "manifest.json").read_text())
    page = next(p for p in man["pages"] if p["gt"] == path.name)
    if (packed.dtype != np.uint8 or packed.shape != (3, FIELD_YX[0], FIELD_YX[1] // 8)
            or page["gt_plane_order"] != ["C", "M", "Y"] or page["gt_bitorder"] != "big"):
        raise SystemExit(f"{path}: unexpected GT layout {packed.dtype} {packed.shape}")
    if sha(packed.tobytes()) != page["gt_sha256"]:
        raise SystemExit(f"{path}: gt_sha256 mismatch")
    planes = [sha(packed[p].tobytes()) for p in range(3)]
    if planes != page["gt_plane_sha256"]:
        raise SystemExit(f"{path}: gt_plane_sha256 mismatch")
    return packed, {"gt": str(path), "gt_sha256": page["gt_sha256"], "gt_plane_sha256": planes,
                    "spec_id": man["spec_id"], "payload_sha256": man["payload"]["sha256"]}


def ps_placement(ps: Path) -> dict:
    """Field origin and size in dots from the PostScript job's page/translate/scale."""
    head = ps.read_bytes()[:4096].decode("latin-1")
    page = re.search(r"/PageSize \[([\d.]+) ([\d.]+)\]", head)
    tr = re.search(r"([\d.]+) ([\d.]+) translate", head)
    sc = re.search(r"([\d.]+) ([\d.]+) scale", head)
    dots = [round(float(v) * 600 / 72) for m in (page, tr, sc) for v in m.groups()]
    page_x, page_y, left, bottom, width, height = dots
    return {"ps": str(ps), "page_dots_xy": [page_x, page_y],
            "origin_yx": [page_y - bottom - height, left], "field_yx": [height, width]}


def stack(cmy: np.ndarray, n_planes: int) -> np.ndarray:
    """(n_planes, rows, bytes) in the mode's transfer order; a K plane is all zero."""
    return np.concatenate([np.zeros_like(cmy[:n_planes - 3]), cmy])


def emit_job(planes: np.ndarray, mode: str) -> bytes:
    """PJL-framed PCL 5c job: one planar raster at the field origin in the mode's colour setup."""
    n_planes, rows, nbytes = planes.shape
    colour_setup, order, job_name = MODES[mode][:3]
    if n_planes != len(order):
        raise ValueError(f"{mode} sends {len(order)} planes per row, got {n_planes}")
    pcl = bytearray(E + b"E")
    pcl += E + b"&l26A" + E + b"&l0O" + E + b"&l0L" + E + b"&u600D" + E + b"&l0E"
    pcl += E + b"*t600R" + colour_setup + E + b"*r0F"
    pcl += E + b"*r%dS" % (8 * nbytes) + E + b"*r%dT" % rows
    pcl += E + b"*p%dx%dY" % (ORIGIN_YX[1] - A4_LOGICAL_LEFT_DOTS, ORIGIN_YX[0])
    pcl += E + b"*b0M" + E + b"*r1A"
    by_plane, by_row = E + b"*b%dV" % nbytes, E + b"*b%dW" % nbytes
    for r in range(rows):
        for p in range(n_planes - 1):
            pcl += by_plane + planes[p, r].tobytes()
        pcl += by_row + planes[-1, r].tobytes()
    pcl += E + b"*rC" + E + b"E"
    name = job_name.encode()
    return (UEL + b'@PJL JOB NAME="%s"\r\n@PJL ENTER LANGUAGE=PCL\r\n' % name + bytes(pcl)
            + UEL + b'@PJL EOJ NAME="%s"\r\n' % name + UEL)


def read_back(job: bytes) -> np.ndarray:
    """Planes (planes, rows, bytes) parsed from the job's raster section."""
    i, end = job.index(E + b"*r1A") + 5, job.rindex(E + b"*rC")
    cmd, chunks, kinds = re.compile(rb"\x1b\*b(\d+)([VW])"), [], []
    while i < end:
        m = cmd.match(job, i)
        if m is None:
            raise ValueError(f"unexpected bytes in raster section at offset {i}")
        i = m.end() + int(m.group(1))
        chunks.append(job[m.end():i])
        kinds.append(m.group(2))
    seq, n = b"".join(kinds), kinds.index(b"W") + 1
    if i != end or seq != (b"V" * (n - 1) + b"W") * (len(seq) // n) or len(set(map(len, chunks))) != 1:
        raise ValueError("raster section is not whole rows of equal planes")
    return np.frombuffer(b"".join(chunks), np.uint8).reshape(len(seq) // n, n, -1).transpose(1, 0, 2)


def stub_font() -> bytes:
    """One-glyph TrueType whose name record #6 (the one gpcl6 reads) is GPCL6_FONT."""
    name = GPCL6_FONT.encode("utf-16-be")
    recs = b"".join(struct.pack(">6H", 3, 1, 0x409, i, len(name), 0) for i in range(7))
    tables = {
        b"head": struct.pack(">IIIIHHqqhhhhHHhhh", 0x10000, 0x10000, 0, 0x5F0F3CF5, 0, 1000,
                             0, 0, 0, 0, 600, 800, 0, 8, 2, 0, 0),
        b"hhea": struct.pack(">IhhhHhhhhhh4hhH", 0x10000, 800, -200, 0, 600, *[0] * 3, 1,
                             *[0] * 7, 1),
        b"maxp": struct.pack(">IH13H", 0x10000, 1, 0, 0, 0, 0, 2, *[0] * 8),
        b"glyf": bytes(4), b"loca": struct.pack(">2H", 0, 0), b"hmtx": struct.pack(">hh", 600, 0),
        b"name": struct.pack(">3H", 0, 7, 6 + 12 * 7) + recs + name,
    }
    tags = sorted(tables)
    dirs, body, base = b"", b"", 12 + 16 * len(tags)
    for t in tags:
        d = tables[t] + bytes(-len(tables[t]) % 4)
        csum = sum(struct.unpack(f">{len(d) // 4}I", d)) & 0xFFFFFFFF
        dirs += struct.pack(">4sIII", t, csum, base + len(body), len(tables[t]))
        body += d
    sel = len(tags).bit_length() - 1
    return struct.pack(">IHHHH", 0x10000, len(tags), 16 << sel, sel,
                       16 * len(tags) - (16 << sel)) + dirs + body


def render(src: Path, out: Path, fonts: Path) -> np.ndarray:
    """gpcl6 render of one job; refuses anything but exactly one RGB page."""
    env = dict(os.environ, PCLFONTSOURCE=f"{fonts}/")
    subprocess.run([GPCL6, *GPCL6_ARGS, f"-sOutputFile={out}", str(src)],
                   check=True, env=env, capture_output=True)
    raw = out.read_bytes()
    tokens, pos = [], 0
    while len(tokens) < 4:
        line = raw[pos:raw.index(b"\n", pos)]
        pos += len(line) + 1
        tokens += [] if line.startswith(b"#") else line.split()
    w, h = int(tokens[1]), int(tokens[2])
    if tokens[0] != b"P6" or len(raw) - pos != w * h * 3:
        raise SystemExit(f"{out}: not exactly one {w}x{h} P6 page")
    return np.frombuffer(raw, np.uint8, w * h * 3, pos).reshape(h, w, 3)


def placed(bits: np.ndarray, hw: tuple[int, int]) -> np.ndarray:
    canvas = np.zeros(hw, bool)
    canvas[ORIGIN_YX[0]:ORIGIN_YX[0] + FIELD_YX[0], ORIGIN_YX[1]:ORIGIN_YX[1] + FIELD_YX[1]] = bits
    return canvas


def first_ink_yx(a: np.ndarray) -> list[int] | None:
    return [int(np.flatnonzero(a.any(1))[0]), int(np.flatnonzero(a.any(0))[0])] if a.any() else None


def verify(job_path: Path, job: bytes, cmy: np.ndarray, mode: str) -> dict:
    order = MODES[mode][1]
    n_planes, off = len(order), len(order) - 3
    planes = stack(cmy, n_planes)
    back = read_back(job)
    result: dict = {"read_back": {
        "rows": int(back.shape[1]), "planes_per_row": int(back.shape[0]),
        "bytes_per_plane": int(back.shape[2]), "equal_to_gt": bool(np.array_equal(back, planes)),
        "k_nonzero_bytes": int(np.count_nonzero(back[0])) if off else None}}
    bits = np.unpackbits(cmy, axis=2, bitorder="big").astype(bool)
    y0, x0 = ORIGIN_YX
    field = (slice(y0, y0 + FIELD_YX[0]), slice(x0, x0 + FIELD_YX[1]))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (fonts := tmp / "fonts").mkdir()
        (fonts / "stub.ttf").write_bytes(stub_font())
        probe = np.zeros((n_planes, 64, 64), np.uint8)
        for k, p in ((k, p) for k in range(8) for p in range(3) if k >> p & 1):
            probe[off + p, :, 8 * k:8 * k + 8] = 0xFF
        probe_job = emit_job(probe, mode)

        def probe_palette(job_bytes: bytes) -> dict:
            (tmp / "palette.pcl").write_bytes(job_bytes)
            img = render(tmp / "palette.pcl", tmp / "palette.ppm", fonts)
            return {f"C{k & 1}M{k >> 1 & 1}Y{k >> 2 & 1}": img[y0 + 32, x0 + 64 * k + 32].tolist()
                    for k in range(8)}
        result["gpcl6_palette_k0"] = probe_palette(probe_job)
        palette = np.array(list(result["gpcl6_palette_k0"].values()), np.uint8)
        if mode == "cid-cmy":
            ctl = {name: probe_palette(probe_job.replace(MODES[mode][0], alt, 1))
                   for name, alt in CID_CONTROLS.items()}
            result["gpcl6_cid_controls"] = ctl
            result["gpcl6_cid_honoured"] = result["gpcl6_palette_k0"] not in ctl.values()
        isolation = {}
        for p, name in enumerate(order):
            only = planes * (np.arange(n_planes) == p)[:, None, None]
            (src := tmp / f"{name}-only.pcl").write_bytes(emit_job(only, mode))
            ink = (render(src, tmp / f"{name}-only.ppm", fonts) != 255).any(2)
            want = placed(bits[p - off], ink.shape) if name != "K" else np.zeros(ink.shape, bool)
            field_sha = sha(np.packbits(ink[field], axis=1).tobytes())
            isolation[name] = {
                "differing_dots": int(np.count_nonzero(ink != want)), "ink_dots": int(ink.sum()),
                "first_ink_yx": first_ink_yx(ink), "expected_first_ink_yx": first_ink_yx(want),
                "field_packed_sha256": field_sha, "equals_gt_plane_sha":
                    field_sha == sha(cmy[p - off].tobytes()) if name != "K" else None}
        result["isolation_renders"] = isolation
        full = render(job_path, tmp / "job.ppm", fonts)
        pred = np.full(full.shape, 255, np.uint8)
        pred[field] = palette[bits[0] + 2 * bits[1].astype(np.uint8) + 4 * bits[2].astype(np.uint8)]
        result["job_render"] = {
            "page_hw": list(full.shape[:2]), "render_rgb_sha256": sha(full.tobytes()),
            "differing_dots_vs_gt_through_palette": int(np.count_nonzero((full != pred).any(2))),
            "ink_outside_field": int((full != 255).any(2).sum() - (full[field] != 255).any(2).sum())}
        separable = all((palette[k, c] < 128) == bool(k >> c & 1) for k in range(8) for c in range(3))
        result["job_render"]["per_plane_decode"] = {
            name: int(np.count_nonzero((full[..., c] < 128) != placed(bits[c], full.shape[:2])))
            for c, name in enumerate("CMY")} if separable else (
            "not decodable: gpcl6's palette for this mode does not separate C/M/Y into R/G/B")
    decode = result["job_render"]["per_plane_decode"]
    result["pass"] = bool(all(v["differing_dots"] == 0 for v in isolation.values())
                          and result["read_back"]["equal_to_gt"]
                          and result["job_render"]["differing_dots_vs_gt_through_palette"] == 0
                          and (not isinstance(decode, dict) or not any(decode.values()))
                          and result.get("gpcl6_cid_honoured", True))
    result["command"] = (f"PCLFONTSOURCE=<tmp>/fonts/ {GPCL6} {' '.join(GPCL6_ARGS)} "
                         f"-sOutputFile=<tmp>/job.ppm {job_path}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gt", required=True, type=Path, help="page000_gt.npy (manifest.json beside it)")
    ap.add_argument("--ps", type=Path, help="PostScript job to cross-check placement against "
                    "(default: page000.ps beside the GT)")
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--mode", choices=list(MODES),
                     help="cmy3 = Esc*r-3U device CMY (C, M, Y); kcmy4 = Esc*r-4U KCMY (K zero, C, M, Y); "
                     "cid-cmy = Esc*v6W 01 02 01 01 01 01, CID Device CMY Direct by Plane (C, M, Y)")
    how.add_argument("--planes", type=int, choices=sorted(PLANES_ALIAS),
                     help="legacy spelling: 3 = --mode cmy3, 4 = --mode kcmy4")
    ap.add_argument("--out", required=True, type=Path, help="job path; manifest written beside it")
    ap.add_argument("--verify", action="store_true", help="render with gpcl6 and compare to GT")
    args = ap.parse_args()
    mode = args.mode or PLANES_ALIAS[args.planes]
    order = MODES[mode][1]
    cmy, gt = load_gt(args.gt)
    ps = ps_placement(args.ps or args.gt.parent / "page000.ps")
    ours = {"page_dots_xy": list(PAGE_DOTS_XY), "origin_yx": list(ORIGIN_YX), "field_yx": list(FIELD_YX)}
    if {k: ps[k] for k in ours} != ours:
        raise SystemExit(f"placement disagrees with the PostScript job: {ps} vs {ours}")
    job = emit_job(stack(cmy, len(order)), mode)
    setup = job[job.index(b"PCL\r\n") + 5:job.index(E + b"*r1A") + 5]
    setup = re.sub(rb"\*v6W(.{6})", lambda m: b"*v6W " + m.group(1).hex(" ").encode(), setup, flags=re.S)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    manifest = {
        "tag": args.out.stem, "job": str(args.out), "bytes": len(job), "sha256": sha(job),
        "mode": mode, "what": MODES[mode][3], "planes": list(order),
        "setup_sequence": setup.replace(E, b" Esc").decode("ascii").strip(),
        "row_sequence": f"{len(order) - 1} x Esc*b576V + Esc*b576W, {FIELD_YX[0]} rows, "
                        "then Esc*rC Esc E, UEL @PJL EOJ UEL",
        "unverified_risk": MODES[mode][4],
        "format_ref": "L:c3-cmy8-p120-v1@2240x1536", **gt,
        "placement": {**ours, "ps_cross_check": ps, "a4_logical_page_left_dots": A4_LOGICAL_LEFT_DOTS,
                      "pcl_cursor_xy_600dpi": [ORIGIN_YX[1] - A4_LOGICAL_LEFT_DOTS, ORIGIN_YX[0]]},
        "generator": " ".join(["PYTHONPATH=src", sys.executable, *sys.argv]),
        "verification": verify(args.out, job, cmy, mode) if args.verify else "not run",
    }
    args.out.with_name(args.out.stem + ".manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(json.dumps(manifest["verification"], indent=1))


if __name__ == "__main__":
    main()
