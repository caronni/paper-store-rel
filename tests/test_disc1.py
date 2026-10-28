"""Exp 007 DISC-1 pre-flight (simulation before toner — gates the office print).

Two-page job. Checks, in order: byte-identical regeneration (sha gates
reuse); portable stream structure (LanguageLevel 2, %%Pages: 2, page 1
request-free, exactly ONE guarded PageSize request, exactly FIVE guarded
/HWResolution operations — the 300/600/1200/2400 enumeration trials plus the
definitive [1200 1200] — ALL after page 1's showpage, both END sentinels
last-in-page, <= 10 MB); manifest geometry (per-page occupancy in 2400-grid
units, bounds incl. the margin-probe exception, disjointness with composite
grouping, labels clear); ground-truth integrity; gs render fidelity (pnggray
-r600 pixel-exact for the page-1 600-grid PN fields + a morphology checker
and the page-2 600-grid control; -r1200 pixel-exact for the 1200-grid c2
fields on both pages); stripdec round-trips on both page renders (page 1:
plain PHCAL1;LAY=1 payload; page 2: PG=2 + RQ* preamble, fields parse
unchanged); and a no-CLI-resolution gs run proving the enumeration plumbing
(gs grants each trial when the CLI does not pin resolution: RQ300..RQ2400 =
300/600/1200/2400 and page 2 prints at the definitive 1200 grant — with a
CLI -r, gs pins everything to the CLI value and the RQ fields record that).

Runs under pytest, or standalone: env/bin/python tests/test_disc1.py
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "007-office-disc"
BUILD = EXP / "build"
EXP002 = ROOT / "experiments" / "002-calibration-page"

sys.path.insert(0, str(EXP002))
import stripdec  # noqa: E402

_STATE: dict = {}
U_DPI = 2400
RQ_TRIALS = (300, 600, 1200, 2400)


def _generate() -> tuple[str, str]:
    r = subprocess.run([sys.executable, str(EXP / "gen_disc1.py")],
                       capture_output=True, text=True, timeout=600, cwd=str(EXP))
    assert r.returncode == 0, f"gen_disc1.py failed:\n{r.stdout}\n{r.stderr}"
    ps_sha = hashlib.sha256((BUILD / "disc1.ps").read_bytes()).hexdigest()
    mf_sha = hashlib.sha256(
        (BUILD / "disc1_manifest.json").read_bytes()).hexdigest()
    return ps_sha, mf_sha


def _built() -> None:
    if "sha" not in _STATE:
        _STATE["sha"] = _generate()


def _manifest() -> dict:
    _built()
    return json.loads((BUILD / "disc1_manifest.json").read_text())


def _load_pages(tag: str) -> tuple[np.ndarray, np.ndarray]:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    return tuple(np.asarray(Image.open(
        BUILD / f"preflight_{tag}_{n}.png").convert("L")) for n in (1, 2))


def _render(dpi: int) -> tuple[np.ndarray, np.ndarray]:
    """gs render of BOTH pages at a CLI-pinned resolution."""
    _built()
    key = ("gray", dpi)
    if key not in _STATE:
        assert shutil.which("gs") is not None, "ghostscript required"
        subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                        "-sDEVICE=pnggray", f"-r{dpi}",
                        "-o", str(BUILD / f"preflight_{dpi}_%d.png"),
                        str(BUILD / "disc1.ps")], check=True, timeout=600)
        _STATE[key] = _load_pages(str(dpi))
    return _STATE[key]


def _render_nores() -> np.ndarray:
    """gs render WITHOUT a CLI -r: the page-2 enumeration requests are
    actually granted (measured gs 10.x; a CLI -r pins them instead). Page 1
    renders at the tiny gs default — only page 2 is used."""
    _built()
    if "nores" not in _STATE:
        subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                        "-sDEVICE=pnggray",
                        "-o", str(BUILD / "preflight_auto_%d.png"),
                        str(BUILD / "disc1.ps")], check=True, timeout=600)
        _STATE["nores"] = _load_pages("auto")[1]
    return _STATE["nores"]


def _urect(e: dict) -> tuple[int, int, int, int]:
    """Element rect in 2400-grid units (lcm of the address grids)."""
    s = U_DPI // e.get("dpi", 600)
    return (e["x_dots"] * s, e["y_dots"] * s, e["w_dots"] * s, e["h_dots"] * s)


def _umm(v: float) -> int:
    return round(v / 25.4 * U_DPI)


def _rq_fields(payload: bytes) -> dict[int, int]:
    text = payload.split(b"\x00")[0].decode("ascii", "replace")
    return {int(m.group(1)): int(m.group(2))
            for m in re.finditer(r"RQ(\d+)=(\d+);", text)}


def _decode_strips(img: np.ndarray, mf: dict, expect_pg2: bool) -> list[dict]:
    strips = stripdec.decode_image(img)
    assert len(strips) == 2, f"expected 2 strips, decoded {len(strips)}"
    for s in strips:
        assert s["magic_ok"], "strip magic PHCAL1 missing"
        assert s["crc_ok"], "strip CRC-16 mismatch"
        f = s["fields"]
        assert f["J"] == mf["jobid"]
        assert f["S"] == mf["strip_s_field"]
        assert f["LAY"] == "1"
        assert f["PS"] == "595x842", f"PageSize not honored: {f['PS']}"
        if expect_pg2:
            assert s["payload"].startswith(b"PHCAL1;PG=2;"), s["payload"][:40]
        else:
            assert s["payload"].startswith(mf["payload_prefix"].encode())
            assert not _rq_fields(s["payload"]), "RQ fields leaked to page 1"
    return strips


# -- 1. determinism -----------------------------------------------------------

def test_determinism_byte_identical() -> None:
    a = _generate()
    b = _generate()
    assert a == b, f"regeneration not byte-identical: {a} vs {b}"
    _STATE["sha"] = b


# -- 2. portable stream structure ----------------------------------------------

def test_stream_structure_requests_sentinels_budget() -> None:
    _built()
    ps = (BUILD / "disc1.ps").read_text()
    assert len(ps) <= 10_000_000, f"ps {len(ps) / 1e6:.1f} MB > 10 MB budget"
    assert ps.isascii(), "%%DocumentData: Clean7Bit violated (non-ASCII byte)"
    assert "%%LanguageLevel: 2" in ps
    assert "%%Pages: 2" in ps and ps.count("%%Page:") == 2
    lines = ps.splitlines()
    spd = [ln for ln in lines
           if "setpagedevice" in ln and not ln.lstrip().startswith("%")]
    assert len(spd) == 2 + len(RQ_TRIALS), f"unexpected requests: {spd}"
    assert spd[0] == "{ << /PageSize [595 842] >> setpagedevice } stopped { } if"
    hw_req = [ln for ln in spd if "HWResolution" in ln]
    assert len(hw_req) == len(RQ_TRIALS) + 1, hw_req
    for r, ln in zip(RQ_TRIALS, hw_req):        # trials in ascending order
        assert f"/HWResolution [{r} {r}]" in ln and "stopped" in ln, ln
    assert hw_req[-1] == ("{ << /HWResolution [1200 1200] >> setpagedevice }"
                          " stopped { } if")
    # ALL resolution operations sit after page 1's showpage (scripted check)
    i_sp1 = ps.index("showpage")
    for ln in hw_req:
        assert ps.index(ln) > i_sp1, f"resolution op before showpage 1: {ln}"
    # page 1 itself is request-free; its sentinel is last in its stream
    p1 = ps[ps.index("%%Page: 1 1"): ps.index("%%Page: 2 2")]
    assert "setpagedevice" not in p1
    i_cmyk = p1.index("% ==== put_cmyk_bitmap composites")
    assert p1.rindex("imagemask") < i_cmyk
    i_s1 = p1.index("% ---- END sentinel")
    assert i_s1 > i_cmyk
    assert "imagemask" not in p1[i_s1:] and ">> image" not in p1[i_s1:]
    # page 2 sentinel is the job's last drawing op
    i_s2 = ps.rindex("% ---- END sentinel")
    assert i_s2 > ps.index("%%Page: 2 2")
    assert "imagemask" not in ps[i_s2:] and ">> image" not in ps[i_s2:]
    mf = _manifest()
    assert f"(END {mf['jobid']} exp007 disc1 p2) show" in ps[i_s2:]


# -- 3. geometry --------------------------------------------------------------

def _union_rects(mf: dict) -> dict[tuple, list]:
    """One bounding rect per element per page; composite planes/pair halves
    share one key (the C+M pair overlaps DELIBERATELY inside its group)."""
    groups: dict[tuple, list] = {}
    for e in mf["patches"] + mf["infrastructure"]:
        key = (e.get("page", 1), e.get("composite_of") or e["name"])
        x, y, w, h = _urect(e)
        g = groups.setdefault(key, [x, y, x + w, y + h, e["kind"]])
        g[0], g[1] = min(g[0], x), min(g[1], y)
        g[2], g[3] = max(g[2], x + w), max(g[3], y + h)
    return groups


def test_geometry_bounds_overlaps_labels() -> None:
    mf = _manifest()
    tol = 4   # cross-grid rounding slack (0.04 mm)
    cx0, cy0 = _umm(mf["content_bounds_mm"][0]), _umm(mf["content_bounds_mm"][1])
    cx1, cy1 = _umm(mf["content_bounds_mm"][2]), _umm(mf["content_bounds_mm"][3])
    mmin = _umm(3.5)
    mx1, my1 = _umm(210.0 - 3.5), _umm(297.0 - 3.5)
    groups = _union_rects(mf)
    for (page, name), (x0, y0, x1, y1, kind) in groups.items():
        if kind == "margin_tick":   # the one sanctioned margin exception
            assert mmin - tol <= x0 and x1 <= mx1 + tol \
                and mmin - tol <= y0 and y1 <= my1 + tol, name
        else:
            assert cx0 - tol <= x0 and x1 <= cx1 + tol \
                and cy0 - tol <= y0 and y1 <= cy1 + tol, \
                f"p{page}/{name} outside 12 mm content bounds"
    keys = list(groups)
    for i, a in enumerate(keys):
        ax0, ay0, ax1, ay1, _ = groups[a]
        for b in keys[i + 1:]:
            if a[0] != b[0]:        # different pages cannot collide
                continue
            bx0, by0, bx1, by1, _ = groups[b]
            assert ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0, \
                f"overlap: {a} vs {b}"
    for lb in mf["labels"]:
        lpage = lb.get("page", 1)
        lx0, ly0 = 4 * lb["x_dots"], 4 * lb["y_dots"]
        lx1, ly1 = lx0 + 4 * lb["w_dots"], ly0 + 4 * lb["h_dots"]
        assert cx0 - tol <= lx0 and lx1 <= cx1 + tol \
            and cy0 - tol <= ly0 and ly1 <= cy1 + tol, \
            f"label {lb['text']!r} outside bounds"
        for (page, name), (x0, y0, x1, y1, _) in groups.items():
            if page != lpage:
                continue
            assert lx0 >= x1 or x0 >= lx1 or ly0 >= y1 or y0 >= ly1, \
                f"label {lb['text']!r} intersects {name}"


# -- 4. ground truth ----------------------------------------------------------

def test_gt_files_load_and_match() -> None:
    mf = _manifest()
    seen: dict[str, str] = {}
    n = 0
    for e in mf["patches"]:
        if e["gt"] is None:
            continue
        assert seen.setdefault(e["gt"], e["name"]) == e["name"], \
            f"gt file {e['gt']} shared by {seen[e['gt']]} and {e['name']}"
        gt = np.load(BUILD / e["gt"])
        assert gt.shape == (e["h_dots"], e["w_dots"]), \
            f"{e['name']}: gt {gt.shape} vs manifest ({e['h_dots']},{e['w_dots']})"
        assert set(np.unique(gt)) <= {0, 1}, e["name"]
        n += 1
    # 8 PN + 9 tone + 4 chk + 3 CMY (page 1) + 3 PN + control (page 2)
    assert n >= 28, f"only {n} ground-truth files"


# -- 5. gs render fidelity ----------------------------------------------------

def _crop_equal(img: np.ndarray, e: dict, gt: np.ndarray) -> None:
    x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
    crop = (img[y: y + h, x: x + w] < 128).astype(np.uint8)
    assert np.array_equal(crop, gt), \
        f"{e['name']}: {int((crop != gt).sum())}/{gt.size} pixels differ"


def test_gs600_gt_pixel_exact() -> None:
    mf = _manifest()
    p1, p2 = _render(600)
    assert p1.shape == p2.shape          # CLI -r pins both pages (gs 10.x)
    byname = {e["name"]: e for e in mf["patches"]}
    for nm in [f"pn600/c{c}" for c in (1, 2, 3, 4, 5, 6)] + ["morph600/chk1"]:
        e = byname[nm]
        assert e["dpi"] == 600 and e["page"] == 1, nm
        _crop_equal(p1, e, np.load(BUILD / e["gt"]))
    e = byname["p2/pn600/c3_ctl"]        # page-2 cross-page control
    assert e["dpi"] == 600 and e["page"] == 2
    _crop_equal(p2, e, np.load(BUILD / e["gt"]))


def test_gs1200_gt_pixel_exact() -> None:
    mf = _manifest()
    p1, p2 = _render(1200)
    byname = {e["name"]: e for e in mf["patches"]}
    for nm, img in (("pn1200/c2", p1), ("p2/pn1200/c2", p2)):
        e = byname[nm]
        assert e["dpi"] == 1200, nm
        _crop_equal(img, e, np.load(BUILD / e["gt"]))


# -- 6. strip round-trips -----------------------------------------------------

def test_gs600_strips_page1() -> None:
    mf = _manifest()
    p1, _ = _render(600)
    for s in _decode_strips(p1, mf, expect_pg2=False):
        f = s["fields"]
        assert f["RE"] == "600x600", f"RE={f['RE']} at gs -r600"
        assert f["RD"] == "600x600", f"RD={f['RD']} (gs default = CLI value)"
        mx, my = s["module_px"]
        assert abs(mx - 6) < 0.1 and abs(my - 6) < 0.1, (mx, my)


def test_gs600_strips_page2_rq_pinned() -> None:
    """With a CLI -r, gs pins resolution: every enumeration trial reads back
    the CLI value — the RQ fields must say so (and RD stays the default)."""
    mf = _manifest()
    _, p2 = _render(600)
    for s in _decode_strips(p2, mf, expect_pg2=True):
        f = s["fields"]
        assert f["RE"] == "600x600" and f["RD"] == "600x600", f
        rq = _rq_fields(s["payload"])
        assert set(rq) == set(RQ_TRIALS), rq
        assert all(v == 600 for v in rq.values()), rq


def test_gs_nores_page2_rq_granted() -> None:
    """Without a CLI -r nothing pins the device: gs GRANTS each enumeration
    trial (measured 10.x) — RQ300..RQ2400 = 300/600/1200/2400 and page 2
    prints at the definitive 1200 grant. This is the plumbing proof for the
    real RIP, where the RQ read-backs are the probe's verdict."""
    mf = _manifest()
    p2 = _render_nores()
    granted = round(p2.shape[1] / (595 / 72))
    assert granted == 1200, f"definitive request not granted: {granted} dpi"
    for s in _decode_strips(p2, mf, expect_pg2=True):
        f = s["fields"]
        assert f["RE"] == "1200x1200", f
        rq = _rq_fields(s["payload"])
        assert rq == {r: r for r in RQ_TRIALS}, rq
        mx, _ = s["module_px"]
        assert abs(mx - 12) < 0.2, mx   # module max(3, floor(1200/100)) = 12


if __name__ == "__main__":
    fns = [test_determinism_byte_identical,
           test_stream_structure_requests_sentinels_budget,
           test_geometry_bounds_overlaps_labels,
           test_gt_files_load_and_match,
           test_gs600_gt_pixel_exact,
           test_gs1200_gt_pixel_exact,
           test_gs600_strips_page1,
           test_gs600_strips_page2_rq_pinned,
           test_gs_nores_page2_rq_granted]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
