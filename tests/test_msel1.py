"""Exp 008 MSEL-1 pre-flight (simulation before toner — gates any print).

Two-page portable mode-selection job. Checks, in order: byte-identical
regeneration (sha gates reuse); portable stream structure (LanguageLevel 2,
%%Pages: 2, exactly ONE guarded PageSize request, ZERO /HWResolution
operations anywhere — MSEL-1 measures the device-default render path by
design — masks before put_cmyk composites, both END sentinels last-in-page,
Clean7Bit, <= 16 MB); manifest geometry (600-dot units, per-page
disjointness with composite/pair grouping, bounds, labels clear);
ground-truth integrity; gs render fidelity (pnggray -r600 pixel-exact for
representative K fields on BOTH pages, tiffsep pixel-exact for an A3
composite's three planes); stripdec round-trips on 1200-dpi renders of both
pages (p1 plain PHCAL1;LAY=1 payload, p2 PHCAL1;PG=2 preamble); the FULL
analyzer on the clean 1200 grey renders (corner-mark registration + strips
+ K portfolio + adequacy + decision table — a perfect channel must read
robust=c6, dense=c2, CMY='needs color scan'); and the M0 SIM GATE: the
pf1 portfolio through the measured M281 simulator (print_scan
geometry=False; A3 via rescreen + measured crosstalk compose) must produce
the PRE-REGISTERED recommendation (experiments/008-mode-select.md): robust
K = c4-or-larger, dense K = c3 (c2 lands in the fragile tier and is
excluded), CMY = A3-7st-c3 screened-class.

Runs under pytest, or standalone: env/bin/python tests/test_msel1.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "008-mode-select"
BUILD = EXP / "build"
MM_DOT = 600.0 / 25.4

for _p in (str(EXP), str(ROOT / "experiments" / "002-calibration-page")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import analyze_msel1 as am  # noqa: E402
import cal_core as cc  # noqa: E402
import stripdec  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
_STATE: dict = {}


def _generate() -> tuple[str, str]:
    r = subprocess.run([sys.executable, str(EXP / "gen_msel1.py")],
                       capture_output=True, text=True, timeout=600,
                       cwd=str(EXP))
    assert r.returncode == 0, f"gen_msel1.py failed:\n{r.stdout}\n{r.stderr}"
    return (hashlib.sha256((BUILD / "msel1.ps").read_bytes()).hexdigest(),
            hashlib.sha256(
                (BUILD / "msel1_manifest.json").read_bytes()).hexdigest())


def _built() -> None:
    if "sha" not in _STATE:
        _STATE["sha"] = _generate()


def _manifest() -> dict:
    _built()
    return json.loads((BUILD / "msel1_manifest.json").read_text())


def _render_gray(dpi: int) -> tuple[np.ndarray, np.ndarray]:
    _built()
    key = ("gray", dpi)
    if key not in _STATE:
        subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                        "-sDEVICE=pnggray", f"-r{dpi}",
                        "-o", str(BUILD / f"preflight_{dpi}_%d.png"),
                        str(BUILD / "msel1.ps")], check=True, timeout=600)
        _STATE[key] = tuple(
            np.asarray(Image.open(BUILD / f"preflight_{dpi}_{n}.png")
                       .convert("L")) for n in (1, 2))
    return _STATE[key]


def _render_tiffsep() -> dict[str, np.ndarray]:
    """Page-1 boolean ink maps per plane at 600 (tiffsep: ink = dark)."""
    _built()
    if "sep" not in _STATE:
        subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                        "-sDEVICE=tiffsep", "-r600",
                        "-o", str(BUILD / "preflight_sep_%d.tif"),
                        str(BUILD / "msel1.ps")], check=True, timeout=600)
        seps = {}
        for plane, name in (("C", "Cyan"), ("M", "Magenta"), ("Y", "Yellow"),
                            ("K", "Black")):
            f = BUILD / f"preflight_sep_1({name}).tif"
            seps[plane] = np.asarray(Image.open(f)) < 128
        _STATE["sep"] = seps
    return _STATE["sep"]


# -- 1. determinism -----------------------------------------------------------

def test_determinism_byte_identical() -> None:
    a = _generate()
    b = _generate()
    assert a == b, f"regeneration not byte-identical: {a} vs {b}"
    _STATE["sha"] = b


# -- 2. portable stream structure ----------------------------------------------

def test_stream_structure_portability() -> None:
    _built()
    ps = (BUILD / "msel1.ps").read_text()
    assert len(ps) <= 16_000_000, f"ps {len(ps) / 1e6:.1f} MB > 16 MB budget"
    assert ps.isascii(), "%%DocumentData: Clean7Bit violated (non-ASCII byte)"
    assert "%%LanguageLevel: 2" in ps
    assert "%%Pages: 2" in ps and ps.count("%%Page:") == 2
    spd = [ln for ln in ps.splitlines()
           if "setpagedevice" in ln and not ln.lstrip().startswith("%")]
    assert spd == ["{ << /PageSize [595 842] >> setpagedevice }"
                   " stopped { } if"], spd
    # NO resolution operation anywhere in the job (DISC-1's role, not MSEL's);
    # HWResolution appears only as currentpagedevice READS in the strip code.
    for ln in ps.splitlines():
        if "HWResolution" in ln and not ln.lstrip().startswith("%"):
            assert "setpagedevice" not in ln, ln
    mf = _manifest()
    for page in (1, 2):
        lo = ps.index(f"%%Page: {page} {page}")
        hi = ps.index("%%Page: 2 2") if page == 1 else len(ps)
        seg = ps[lo:hi]
        assert "setpagedevice" not in seg, f"page {page} not request-free"
        i_cmyk = seg.index("% ==== put_cmyk_bitmap composites")
        assert seg.rindex("imagemask") < i_cmyk, \
            f"p{page}: masks must stream before cmyk composites"
        i_s = seg.index("% ---- END sentinel")
        assert i_s > i_cmyk
        assert "imagemask" not in seg[i_s:] and ">> image" not in seg[i_s:], \
            f"p{page}: END sentinel must be last"
    assert f"(END {mf['jobid']} exp008 msel1 p2) show" in ps
    # the emission probe P3 carries overprint + guarded OPM-1
    assert "true setoverprint" in ps
    assert "/setoverprintmode where" in ps


# -- 3. geometry ---------------------------------------------------------------

def _union_rects(mf: dict) -> dict[tuple, list]:
    """One bounding rect per element per page; composite planes / pair
    halves share one key (their overlap is deliberate, inside the group)."""
    groups: dict[tuple, list] = {}
    for e in mf["patches"] + mf["infrastructure"]:
        key = (e.get("page", 1), e.get("composite_of") or e["name"])
        x, y = e["x_dots"], e["y_dots"]
        w, h = e["w_dots"], e["h_dots"]
        g = groups.setdefault(key, [x, y, x + w, y + h, e["kind"]])
        g[0], g[1] = min(g[0], x), min(g[1], y)
        g[2], g[3] = max(g[2], x + w), max(g[3], y + h)
    return groups


def test_geometry_bounds_overlaps_labels() -> None:
    mf = _manifest()
    bx0, by0, bx1, by1 = [round(v * MM_DOT) for v in mf["content_bounds_mm"]]
    groups = _union_rects(mf)
    for (page, name), (x0, y0, x1, y1, _) in groups.items():
        assert bx0 <= x0 and x1 <= bx1 and by0 <= y0 and y1 <= by1, \
            f"p{page}/{name} outside content bounds"
    keys = list(groups)
    for i, a in enumerate(keys):
        ax0, ay0, ax1, ay1, _ = groups[a]
        for b in keys[i + 1:]:
            if a[0] != b[0]:
                continue
            bx, by, bx2, by2, _ = groups[b]
            assert ax1 <= bx or bx2 <= ax0 or ay1 <= by or by2 <= ay0, \
                f"overlap: {a} vs {b}"
    for lb in mf["labels"]:
        lx0, ly0 = lb["x_dots"], lb["y_dots"]
        lx1, ly1 = lx0 + lb["w_dots"], ly0 + lb["h_dots"]
        assert bx0 <= lx0 and lx1 <= bx1 and by0 <= ly0 and ly1 <= by1, \
            f"label {lb['text']!r} outside bounds"
        for (page, name), (x0, y0, x1, y1, _) in groups.items():
            if page != lb["page"]:
                continue
            assert lx0 >= x1 or x0 >= lx1 or ly0 >= y1 or y0 >= ly1, \
                f"label {lb['text']!r} intersects {name}"


# -- 4. ground truth -----------------------------------------------------------

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
            f"{e['name']}: gt {gt.shape} vs ({e['h_dots']},{e['w_dots']})"
        assert set(np.unique(gt)) <= {0, 1}, e["name"]
        n += 1
    # state GTs match their cell grids
    for e in mf["patches"]:
        if "states_gt" not in e.get("params", {}):
            continue
        cell = e["params"]["cell_dots"]
        st = np.load(BUILD / e["params"]["states_gt"])
        assert st.shape == (e["h_dots"] // cell, e["w_dots"] // cell), e["name"]
        assert st.max() < e["params"]["n_states"], e["name"]
    assert n >= 60, f"only {n} ground-truth files"


# -- 5. gs render fidelity -----------------------------------------------------

def _crop_equal(img: np.ndarray, e: dict, gt: np.ndarray) -> None:
    x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
    crop = (img[y: y + h, x: x + w] < 128).astype(np.uint8)
    assert np.array_equal(crop, gt), \
        f"{e['name']}: {int((crop != gt).sum())}/{gt.size} pixels differ"


def test_gs600_gt_pixel_exact() -> None:
    mf = _manifest()
    p1, p2 = _render_gray(600)
    byname = {e["name"]: e for e in mf["patches"]}
    for nm in ("pf1/k_c2", "pf1/k_c3", "pf1/k_c6", "pf1/k_rll", "adq/k_c3",
               "adq/entropy", "morph/chk1"):
        e = byname[nm]
        assert e["page"] == 1, nm
        _crop_equal(p1, e, np.load(BUILD / e["gt"]))
    for nm in ("p2big/k_c3", "p2pf1/k_c2", "p2/morph/chk2"):
        e = byname[nm]
        assert e["page"] == 2, nm
        _crop_equal(p2, e, np.load(BUILD / e["gt"]))


def test_gs600_cmyk_pixel_exact() -> None:
    mf = _manifest()
    seps = _render_tiffsep()
    n = 0
    for e in mf["patches"]:
        if e.get("composite_of") not in ("pf1/a3_c3", "em/p0_cm"):
            continue
        gt = np.load(BUILD / e["gt"]).astype(bool)
        x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
        crop = seps[e["planes"][0]][y: y + h, x: x + w]
        assert np.array_equal(crop, gt), \
            f"{e['name']}: {int((crop != gt).sum())}/{gt.size} px differ"
        n += 1
    assert n == 5, n   # A3: C,M,Y + P0 probe: C,M


# -- 6. strips round-trip ------------------------------------------------------

def test_gs1200_strips_roundtrip() -> None:
    mf = _manifest()
    p1, p2 = _render_gray(1200)
    for page, img in ((1, p1), (2, p2)):
        strips = stripdec.decode_image(img)
        assert len(strips) == 2, f"page {page}: {len(strips)} strips"
        for s in strips:
            assert s["magic_ok"] and s["crc_ok"], f"page {page} strip broken"
            f = s["fields"]
            assert f["J"] == mf["jobid"]
            assert f["S"] == mf["strip_s_field"]
            assert f["LAY"] == "1"
            assert f["PS"] == "595x842", f"PageSize not honored: {f['PS']}"
            pref = (mf["payload_prefix"] if page == 1
                    else mf["payload_prefix_p2"])
            assert s["payload"].startswith(pref.encode()), s["payload"][:48]


# -- 7. analyzer end-to-end on the clean render --------------------------------

def test_analyzer_render_roundtrip() -> None:
    """Full real-scan path (corner-mark registration -> strips -> portfolio
    scoring -> decision) on the noise-free 1200 render: a perfect channel
    must read every K tier solid, hence robust=c6 (largest) and dense=c2
    (rule monotonicity: a clean channel legitimately unlocks c2)."""
    mf_am = am.load_manifest()
    _render_gray(1200)
    scans: dict[str, dict | None] = {"p1_color": None, "p2_color": None}
    for page in (1, 2):
        scan = cc.load_scan(BUILD / f"preflight_1200_{page}.png",
                            compute_sha256=False)
        reg = cc.register(scan, am.page_mf(mf_am, page))
        assert reg["residual_rms_dots"] < 0.2, reg["residual_rms_dots"]
        scans[f"p{page}_grey"] = scan
    rep = am.analyze(scans, mf_am)
    for pg in ("page1", "page2"):
        assert [s["crc_ok"] for s in rep["strips"][pg]] == [True, True]
    assert all(s["pg2"] for s in rep["strips"]["page2"])
    assert len(rep["k_rows"]) == 23 and len(rep["rll_rows"]) == 7
    for r in rep["k_rows"]:
        assert r["ber"] < 0.005 and r["null_ok"], r
    for r in rep["rll_rows"]:
        assert r["ber_dots"] < 0.005 and r["null_ok"], r
    rec = rep["recommendation"]
    assert rec["robust_k"]["cell_dots"] == 6
    assert rec["robust_k"]["margin"].startswith("full")
    assert rec["dense_k"]["cell_dots"] == 2      # clean channel unlocks c2
    assert rec["cmy"]["verdict"] == "needs color scan"
    adq = rec["scanner_adequacy"]
    assert adq["adequate_solid_class_modes"] is True
    assert adq["checks"]["compression"]["verdict"] == "indeterminate"


# -- 8. M0 sim gate: pre-registered recommendation on M281 defaults ------------

def test_sim_decision_m281_defaults() -> None:
    """Measured-simulator round-trip of the decision logic (sim-genie
    footing, geometry=False): the pre-registered outcome of
    experiments/008-mode-select.md MUST come out — robust K c4-or-larger,
    dense K = c3 (c2 excluded in the fragile tier), CMY = A3-7st-c3
    screened-class; the screen classifier must also clear its unscreened
    control."""
    from paperholo.channel.simulator import planes_to_rgb_refl

    mf = am.load_manifest()
    pm1 = am.page_mf(mf, 1)
    k_rows, rll_rows = [], []
    for i, c in enumerate((2, 3, 4, 5, 6)):
        e = cc.entry(pm1, f"pf1/k_c{c}")
        r = am.score_pn(am.sim_k_scan(e, seed=100 + i), e)
        assert r["null_ok"] and r["locked"], r
        k_rows.append(r)
    e = cc.entry(pm1, "pf1/k_rll")
    r = am.score_rll(am.sim_k_scan(e, seed=200), e)
    assert r["null_ok"], r
    rll_rows.append(r)

    comp = "pf1/a3_c3"
    planes = {e2["planes"][0]: cc.load_gt(e2) for e2 in pm1["patches"]
              if e2.get("composite_of") == comp}
    e0 = next(e2 for e2 in pm1["patches"] if e2.get("composite_of") == comp)
    cscan = am.sim_color_scan(planes, e0, seed=300, screened=True)
    a3 = am.score_state(cscan, pm1, comp)
    assert a3 is not None and a3["locked"], a3
    screen = am.screen_hunt(cscan, pm1, comp)
    assert screen["screened"], screen
    assert abs(screen["peaks"][0]["lpi"] - 165.0) < 8.0, screen["peaks"][0]
    scr_ctl = am.screen_hunt(am.sim_color_scan(planes, e0, seed=310,
                                               screened=False), pm1, comp)
    assert not scr_ctl["screened"], scr_ctl   # unscreened control clears

    def dens(planes_on: tuple[str, ...]) -> dict[str, float]:
        one = np.ones((8, 8))
        rgb = planes_to_rgb_refl({p: one for p in planes_on})
        paper = planes_to_rgb_refl({"C": np.zeros((8, 8))})
        return {ch: float(np.log10(paper[..., i].mean() / rgb[..., i].mean()))
                for i, ch in enumerate("rgb")}

    d = {f"xr/clean_{p}": dens((p,)) for p in "CMYK"}
    d.update({f"xr/cmyk_{cm}": dens(tuple(cm)) for cm in ("CM", "CY", "MY")})

    rec = am.decide(k_rows, rll_rows, [a3], [], {"density": d}, None, screen,
                    None, color_available=True)
    by_cell = {t["cell_dots"]: t for t in rec["k_table"]}
    assert by_cell[2]["tier"] == "fragile", by_cell[2]     # sim c2 ~14%
    assert by_cell[3]["worst_ber"] < 0.05, by_cell[3]      # sim c3 ~3%
    assert rec["robust_k"]["cell_dots"] >= 4, rec["robust_k"]
    assert rec["robust_k"]["margin"].startswith("full")
    assert rec["dense_k"]["cell_dots"] == 3, rec["dense_k"]
    assert "c2_upside_note" in rec
    assert rec["rll_b2_anchor"]["proxy_b_per_mm2"] > 40.0
    assert rec["cmy"]["verdict"] == "A3_7st_c3", rec["cmy"]
    assert rec["cmy"]["channel_class"] == "screened_composite"
    assert rec["cmy"]["worst_position_mi_b_cell"] >= am.A3_MI_FLOOR


if __name__ == "__main__":
    fns = [test_determinism_byte_identical,
           test_stream_structure_portability,
           test_geometry_bounds_overlaps_labels,
           test_gt_files_load_and_match,
           test_gs600_gt_pixel_exact,
           test_gs600_cmyk_pixel_exact,
           test_gs1200_strips_roundtrip,
           test_analyzer_render_roundtrip,
           test_sim_decision_m281_defaults]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
