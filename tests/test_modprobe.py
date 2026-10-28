"""Exp 003.0 modulation-probes sheet: determinism, exact constraint
verification, geometry/stream order, gs preflight, and byte-identity pins.

What ghostscript 10.07 ACTUALLY does with this page (measured on this
machine; gs verifies emission semantics ONLY — it does not emulate the M281
RIP's contone/screening path, so whether dot-disjoint multi-plane mask
content stays on the clean path is decided on the printed sheet):

- pnggray -r600: every K-only patch (constrained fields, encode incumbents,
  motif patches) renders pixel-exact against its GT.
- tiffsep -r600: D1 (two whole-field masks, same rect, zero overlapping ink),
  D2 (13k per-cell masks — placement arithmetic exact), D3/D6
  (put_cmyk_bitmap), D4 (disjoint rects), D5 (four dot-disjoint whole-field
  masks), S2/S3 (K field + C marks in white voids) ALL render separations ==
  GT, and unaddressed plates stay empty. With dot-disjoint content the
  opaque-paint knockout mechanism (002.1) is vacuous on gs; gs does not
  screen — the paper decides H1.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots
from paperholo.pilots import pilot_sites

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "003-modulation-probes"
BUILD = EXP / "build"
EXP001 = ROOT / "experiments" / "001-engine-characterization"
EXP002 = ROOT / "experiments" / "002-calibration-page"

# byte-identity pins for artifacts that already went to (or gate) hardware:
# regenerating them must reproduce the logged sha256 — cheap insurance against
# accidental drift of psgen defaults or shared builders.
PINS = (
    (EXP001 / "gen_gridtest.py", EXP001 / "build" / "gridtest.ps",
     "904a5393cc04b86055a0132b1f993e4dac2ba4c6f99fd419c9edf38cfc13fe30"),
    (EXP002 / "gen_calpage.py", EXP002 / "build" / "calpage.ps",
     "39ce59e51e70690896e23fc414e4c77af83ede923818d2acd41a1ba24241534b"),
    (EXP002 / "gen_composite_probe.py", EXP002 / "build" / "composite_probe.ps",
     "58637ad3773315451f0a585bf4419ea395ac36baba5215f5ed04880102086cdd"),
    (EXP002 / "gen_overlap2.py", EXP002 / "build" / "overlap2.ps",
     "9908e7ffd04f598ecdf54487f068f792e387f530225fe0400adfbd845b836f5f"),
)

_STATE: dict = {}


def _generate() -> tuple[str, str, tuple]:
    r = subprocess.run([sys.executable, str(EXP / "gen_modprobe.py")],
                       capture_output=True, text=True, timeout=600, cwd=str(EXP))
    assert r.returncode == 0, f"gen_modprobe.py failed:\n{r.stdout}\n{r.stderr}"
    ps_sha = hashlib.sha256((BUILD / "modprobe.ps").read_bytes()).hexdigest()
    mf_sha = hashlib.sha256((BUILD / "modprobe_manifest.json").read_bytes()).hexdigest()
    gt_shas = tuple(sorted(
        (p.name, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in (BUILD / "modprobe_gt").glob("*.npy")))
    return ps_sha, mf_sha, gt_shas


def _built() -> None:
    if "sha" not in _STATE:
        _STATE["sha"] = _generate()


def _manifest() -> dict:
    _built()
    return json.loads((BUILD / "modprobe_manifest.json").read_text())


def _patch(mf: dict, name: str) -> dict:
    return next(e for e in mf["patches"] if e["name"] == name)


def _gt(mf: dict, name: str) -> np.ndarray:
    return np.load(BUILD / _patch(mf, name)["gt"])


# -- 1. determinism -----------------------------------------------------------

def test_determinism_byte_identical() -> None:
    a = _generate()
    b = _generate()
    assert a == b, "regeneration not byte-identical"
    assert len(b[2]) == 41, f"expected 41 gt files, got {len(b[2])}"
    _STATE["sha"] = b


# -- 2. constraint verification ------------------------------------------------

def _assert_run_lengths(a: np.ndarray, min_ink: int, min_white: int,
                        what: str) -> None:
    """Independent re-implementation: every maximal run in every row AND
    column (border runs included) obeys ink >= min_ink, white >= min_white."""
    assert set(np.unique(a)) <= {0, 1}, f"{what}: not a bit array"
    for tag, b in (("rows", a), ("cols", a.T)):
        for i, line in enumerate(b):
            change = np.flatnonzero(np.diff(line.astype(np.int8))) + 1
            starts = np.concatenate(([0], change))
            ends = np.concatenate((change, [line.size]))
            vals, lens = line[starts], ends - starts
            assert (lens[vals == 1] >= min_ink).all(), \
                f"{what}: ink run < {min_ink} in {tag}[{i}]"
            assert (lens[vals == 0] >= min_white).all(), \
                f"{what}: white run < {min_white} in {tag}[{i}]"


def test_constrained_fields_exact_run_lengths() -> None:
    """K1/K2/K3/S1/S2-K must satisfy their DECLARED constraints exactly, both
    axes, whole array; entropy bookkeeping must be present and sane."""
    mf = _manifest()
    for name in ("K1", "K2", "K3", "S1", "S2_K"):
        e = _patch(mf, name)
        p = e["params"]
        a = np.load(BUILD / e["gt"])
        _assert_run_lengths(a, p["min_ink_run_dots"], p["min_white_run_dots"], name)
        se = p["sampler_entropy_bits_per_dot"]
        ce = p["ctx_model_entropy_bits_per_dot"]
        assert 0.05 < se < 1.0, f"{name}: sampler entropy {se} implausible"
        assert se <= ce + 1e-9, \
            f"{name}: ctx-model {ce} below exact sampler entropy {se}"
    declared = {("K1", 2, 3), ("K2", 2, 2), ("K3", 2, 4), ("S1", 2, 3), ("S2_K", 2, 3)}
    got = {(n, _patch(mf, n)["params"]["min_ink_run_dots"],
            _patch(mf, n)["params"]["min_white_run_dots"])
           for n, _, _ in declared}
    assert got == declared, f"constraint declarations drifted: {got}"


def test_s2_marks_in_white_voids_with_clearance() -> None:
    """Every S2 C mark is 2x2, sits inside a 4x4 all-white window of the K
    field (>= 1-dot white clearance), marks never touch, and the K field is
    byte-identical to the bare S1 control."""
    mf = _manifest()
    k = _gt(mf, "S2_K")
    c = _gt(mf, "S2_C")
    assert np.array_equal(k, _gt(mf, "S1")), "S2 K field differs from S1"
    assert not (k & c).any(), "C marks overlap K ink"
    marks = _patch(mf, "S2_C")["params"]["marks"]
    assert len(marks) == _patch(mf, "S2_C")["params"]["n_marks"]
    assert len(marks) >= 200, f"only {len(marks)} S2 marks — too few for stats"
    rebuilt = np.zeros_like(c)
    for y, x in marks:
        rebuilt[y: y + 2, x: x + 2] = 1
        assert int(k[y - 1: y + 3, x - 1: x + 3].sum()) == 0, \
            f"K ink within 1 dot of mark at {y},{x}"
    assert np.array_equal(rebuilt, c), "manifest mark list != C GT"
    o = np.array(marks)
    for i in range(len(o)):
        d = np.abs(o[i + 1:] - o[i]).max(axis=1)
        assert (d >= 3).all(), f"marks touch near {o[i].tolist()}"


def test_s3_pilot_voids_and_marks() -> None:
    """S3 sites == interior pilot_sites on the cell grid; every void window
    white in K; C marks 2x2 with a 1-dot ring; K elsewhere == base cells."""
    mf = _manifest()
    e = _patch(mf, "S3_K")
    p = e["params"]
    k, c = _gt(mf, "S3_K"), _gt(mf, "S3_C")
    base = np.load(BUILD / p["base_cells_gt"])
    n_cells = base.shape[0]
    pm = pilot_sites((n_cells, n_cells), mf["seed"].encode())
    pm[0, :] = pm[-1, :] = False
    pm[:, 0] = pm[:, -1] = False
    want_sites = sorted(map(tuple, np.argwhere(pm).tolist()))
    assert sorted(map(tuple, p["pilot_cells"])) == want_sites, \
        "manifest pilot cells != paperholo.pilots.pilot_sites interior sites"
    assert abs(p["site_fraction_of_cells"] - len(want_sites) / n_cells ** 2) < 1e-6
    expect_k = cells_to_dots(base, 3)
    expect_c = np.zeros_like(expect_k)
    for ci, cj in want_sites:
        y0, x0 = 3 * ci, 3 * cj
        expect_k[y0: y0 + 4, x0: x0 + 4] = 0
        expect_c[y0 + 1: y0 + 3, x0 + 1: x0 + 3] = 1
    assert np.array_equal(k, expect_k), "S3 K != base cells + voids"
    assert np.array_equal(c, expect_c), "S3 C != 2x2 marks at pilot cells"
    for ci, cj in want_sites:
        y0, x0 = 3 * ci, 3 * cj
        assert int(k[y0: y0 + 4, x0: x0 + 4].sum()) == 0, "pilot ring inked"


def test_motif_patches_instances_and_clearance() -> None:
    """Each motif patch: >=120 instances; at every manifest coordinate the GT
    holds EXACTLY the declared stamp inside its grown clearance window (which
    also proves >= clearance_dots separation from background and neighbors)."""
    mf = _manifest()
    motif_entries = [e for e in mf["patches"] if e["kind"] == "motif_patch"]
    assert len(motif_entries) == 12
    for e in motif_entries:
        p = e["params"]
        a = np.load(BUILD / e["gt"])
        n = a.shape[0]
        assert p["n_instances"] == len(p["instances"]) >= 120, e["name"]
        clr = p["clearance_dots"]
        assert clr >= 4
        if p["motif_kind"] == "ink":
            stamp = np.array(p["motif_shape"], dtype=np.uint8)
            oy = ox = 0
        else:
            hh, hw = p["hole_h_w_dots"]
            pad = p["pad_ink_dots"]
            stamp = np.ones((hh + 2 * pad, hw + 2 * pad), dtype=np.uint8)
            stamp[pad: pad + hh, pad: pad + hw] = 0
            oy = ox = pad
        h, w = stamp.shape
        for y0, x0 in p["instances"]:
            sy, sx = y0 - oy, x0 - ox           # stamp (pad) top-left
            gy0, gx0 = max(0, sy - clr), max(0, sx - clr)
            gy1, gx1 = min(n, sy + h + clr), min(n, sx + w + clr)
            win = a[gy0: gy1, gx0: gx1]
            expect = np.zeros_like(win)
            expect[sy - gy0: sy - gy0 + h, sx - gx0: sx - gx0 + w] = stamp
            assert np.array_equal(win, expect), \
                f"{e['name']}: stamp/clearance violated at {y0},{x0}"


def test_d_group_content_identity_across_emissions() -> None:
    """The emission path is the ONLY variable: D1 == D2 == D3 per-plane bits
    (one rng draw), D5 == D6, D4 halves are slices of the same state field,
    and all mask groups are dot-disjoint."""
    mf = _manifest()
    st = np.load(BUILD / "modprobe_gt" / "D_cm_states.npy")
    for p, idx in (("C", 1), ("M", 2)):
        want = cells_to_dots((st == idx).astype(np.uint8), 3)
        for base in ("D1", "D2", "D3"):
            assert np.array_equal(_gt(mf, f"{base}_{p}"), want), f"{base}_{p}"
    assert not (_gt(mf, "D1_C") & _gt(mf, "D1_M")).any(), "D1 not dot-disjoint"
    half = st.shape[0] // 2
    assert np.array_equal(
        _gt(mf, "D4_C"), cells_to_dots((st[:, :half] == 1).astype(np.uint8), 3))
    assert np.array_equal(
        _gt(mf, "D4_M"), cells_to_dots((st[:, half + 1:] == 2).astype(np.uint8), 3))
    st5 = np.load(BUILD / "modprobe_gt" / "D5_states.npy")
    tot = np.zeros_like(_gt(mf, "D5_C"), dtype=np.int64)
    for p, idx in (("C", 1), ("M", 2), ("Y", 3), ("K", 4)):
        want = cells_to_dots((st5 == idx).astype(np.uint8), 3)
        assert np.array_equal(_gt(mf, f"D5_{p}"), want), f"D5_{p}"
        assert np.array_equal(_gt(mf, f"D6_{p}"), want), f"D6_{p}"
        tot += want
    assert int(tot.max()) <= 1, "D5 planes not dot-disjoint"
    d2 = _patch(mf, "D2_C")["params"]
    assert d2["n_objects"] == int((st != 0).sum())
    assert mf["d2_object_count"] == d2["n_objects"]
    assert mf["ps_bytes"] <= 8_000_000, "ps exceeds the 8 MB D2 budget"


# -- 3. geometry / stream order --------------------------------------------------

def _unique_rects(mf: dict) -> list[tuple[str, int, int, int, int]]:
    seen: dict[str, tuple] = {}
    for e in mf["patches"] + mf["infrastructure"]:
        key = e.get("composite_of") or e["name"]
        seen[key] = (key, e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"])
    return list(seen.values())


def test_geometry_no_overlaps_labels_clear_bounds() -> None:
    mf = _manifest()
    rects = _unique_rects(mf)
    for i in range(len(rects)):
        ni, xi, yi, wi, hi = rects[i]
        for j in range(i + 1, len(rects)):
            nj, xj, yj, wj, hj = rects[j]
            assert not (xi < xj + wj and xj < xi + wi and yi < yj + hj and yj < yi + hi), \
                f"{ni} overlaps {nj}"
    dpm = mf["hw_dpi"] / 25.4
    x0b, y0b, x1b, y1b = 6 * dpm - 1, 6 * dpm - 1, 204 * dpm + 1, 291 * dpm + 1
    for n, x, y, w, h in rects:
        assert x >= x0b and y >= y0b and x + w <= x1b and y + h <= y1b, \
            f"{n} outside content bounds"
    for lb in mf["labels"]:
        lx, ly, lw, lh = lb["x_dots"], lb["y_dots"], lb["w_dots"], lb["h_dots"]
        assert lx >= x0b and ly >= y0b and lx + lw <= x1b and ly + lh <= y1b, \
            f"label {lb['text']!r} outside bounds"
        for n, x, y, w, h in rects:
            assert not (lx < x + w and x < lx + lw and ly < y + h and y < ly + lh), \
                f"label {lb['text']!r} intersects {n}"


def test_registration_marks_match_calpage_geometry() -> None:
    """Corner marks positionally and parametrically identical to the calpage
    ones, so cal_core.register works by swapping in this page's manifest."""
    mf = _manifest()
    corners = {e["params"]["satellites"]: e for e in mf["patches"]
               if e["kind"] == "corner_mark"}
    assert sorted(corners) == [1, 2, 3, 4]
    n_plus = sum(1 for e in mf["patches"] if e["kind"] == "plus_mark")
    assert n_plus >= 6, f"only {n_plus} plus marks — register() needs landmarks"
    cal_mf = EXP002 / "build" / "calpage_manifest.json"
    if cal_mf.exists():
        cal = json.loads(cal_mf.read_text())
        cal_corners = {e["params"]["satellites"]: e for e in cal["patches"]
                       if e["kind"] == "corner_mark"}
        for n in (1, 2, 3, 4):
            for k in ("x_dots", "y_dots", "w_dots", "h_dots", "params"):
                assert corners[n][k] == cal_corners[n][k], \
                    f"corner {n}: {k} differs from calpage"


def test_single_page_and_stream_order() -> None:
    """ONE page; ALL single-plane masks stream before the two cmyk-image
    controls (D3, D6); nothing exotic (no Separation/DeviceN — 002.2 closed
    that); the END sentinel is the very last drawing element."""
    mf = _manifest()
    ps = (BUILD / "modprobe.ps").read_text()
    assert "%%Pages: 1" in ps and ps.count("%%Page:") == 1
    assert ps.count("showpage") == 1
    assert "/Separation (" not in ps and "/DeviceN [" not in ps

    first_cmyk = ps.index("/Decode [0 1 0 1 0 1 0 1]")
    assert ps.count("/Decode [0 1 0 1 0 1 0 1]") == 2      # D3 + D6 only
    assert ps.rindex("imagemask") < first_cmyk, \
        "an imagemask streams after a cmyk-image control"
    # every content mask accounted for, and nothing else:
    # 4 corners + plus lattice + 5 K + 12 M + D1(2) + D2(objects) + D4(2)
    # + D5(4) + S1(1) + S2(2) + S3(2)
    n_plus = sum(1 for e in mf["patches"] if e["kind"] == "plus_mark")
    want_masks = 4 + n_plus + 5 + 12 + 2 + mf["d2_object_count"] + 2 + 4 + 1 + 2 + 2
    assert ps.count("imagemask") == want_masks, \
        f"imagemask count {ps.count('imagemask')} != expected {want_masks}"
    assert ps.index("% ---- D2 per-cell masks begin") < \
        ps.index("% ---- D2 per-cell masks end") < first_cmyk
    si = ps.index("% ---- END sentinel")
    tail = ps[si:]
    assert si > first_cmyk
    for tok in ("imagemask", ">> image", "/Decode ["):
        assert tok not in tail, f"{tok!r} streams after the END sentinel"
    assert "showpage" in tail and tail.rstrip().endswith("%%EOF")


# -- 4. gs preflight: pnggray GT crops + tiffsep separations ---------------------

def _pnggray() -> np.ndarray:
    _built()
    if "png" in _STATE:
        return _STATE["png"]
    assert shutil.which("gs") is not None, "ghostscript required for preflight"
    png = BUILD / "preflight_600.png"
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=pnggray",
                    "-r600", "-o", str(png), str(BUILD / "modprobe.ps")],
                   check=True, timeout=600)
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    _STATE["png"] = np.asarray(Image.open(png))
    return _STATE["png"]


def _separations() -> dict[str, np.ndarray]:
    _built()
    if "seps" in _STATE:
        return _STATE["seps"]
    assert shutil.which("gs") is not None, "ghostscript required for preflight"
    sepdir = BUILD / "preflight_sep"
    sepdir.mkdir(exist_ok=True)
    for old in sepdir.glob("mp_*.tif*"):
        old.unlink()
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=tiffsep",
                    "-r600", "-o", str(sepdir / "mp_%d.tif"),
                    str(BUILD / "modprobe.ps")], check=True, timeout=600)
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    seps = {}
    for plane, name in (("C", "Cyan"), ("M", "Magenta"), ("Y", "Yellow"), ("K", "Black")):
        # tiffsep separation polarity: ink = 0 (dark), paper = 255
        seps[plane] = np.asarray(Image.open(sepdir / f"mp_1({name}).tif")) < 128
    _STATE["seps"] = seps
    return seps


def _crop(img: np.ndarray, e: dict) -> np.ndarray:
    return img[e["y_dots"]: e["y_dots"] + e["h_dots"],
               e["x_dots"]: e["x_dots"] + e["w_dots"]]


def _assert_same(got: np.ndarray, want: np.ndarray, what: str) -> None:
    assert np.array_equal(got, want), \
        f"{what}: {int((got != want).sum())}/{want.size} px differ"


def test_gs_pnggray_gt_crops_pixel_exact() -> None:
    """K constrained field + one ink and one white motif patch render
    pixel-exact through the default (imagemask) path."""
    mf, png = _manifest(), _pnggray()
    for name in ("K1", "M/ink_t_tetromino", "M/white_3x3"):
        e = _patch(mf, name)
        _assert_same(_crop(png, e) < 128, _gt(mf, name).astype(bool), name)


def test_gs_tiffsep_d_and_s_groups_exact() -> None:
    """Separations == GT BOTH ways for D5 (4 dot-disjoint whole-field masks)
    vs D6 (cmyk image) — gs does not screen and, with zero overlapping ink,
    the opaque-paint knockout is vacuous; the paper decides H1. Same for
    D1/D2/D3/D4 and the S2/S3 K+C pairs; unaddressed plates stay empty."""
    mf, seps = _manifest(), _separations()
    groups = (("D1", "CM"), ("D2", "CM"), ("D3", "CM"),
              ("D5", "CMYK"), ("D6", "CMYK"), ("S2", "KC"), ("S3", "KC"))
    for base, planes in groups:
        for p in planes:
            e = _patch(mf, f"{base}_{p}")
            _assert_same(_crop(seps[p], e), _gt(mf, f"{base}_{p}").astype(bool),
                         f"{base} {p}")
        for p in set("CMYK") - set(planes):
            e = _patch(mf, f"{base}_{planes[0]}")
            assert not _crop(seps[p], e).any(), f"{base}: {p} plate marked"
    for name in ("D4_C", "D4_M"):
        e = _patch(mf, name)
        (p,) = e["planes"]
        _assert_same(_crop(seps[p], e), _gt(mf, name).astype(bool), name)


# -- 5. byte-identity pins for earlier hardware-facing artifacts -----------------

def test_pins_previous_sheets_byte_identical() -> None:
    for script, out, want in PINS:
        r = subprocess.run([sys.executable, str(script)], capture_output=True,
                           text=True, timeout=600, cwd=str(script.parent))
        assert r.returncode == 0, f"{script.name} failed:\n{r.stdout}\n{r.stderr}"
        got = hashlib.sha256(out.read_bytes()).hexdigest()
        assert got == want, f"{out.name} drifted: {got}"


if __name__ == "__main__":
    for fn in (test_determinism_byte_identical,
               test_constrained_fields_exact_run_lengths,
               test_s2_marks_in_white_voids_with_clearance,
               test_s3_pilot_voids_and_marks,
               test_motif_patches_instances_and_clearance,
               test_d_group_content_identity_across_emissions,
               test_geometry_no_overlaps_labels_clear_bounds,
               test_registration_marks_match_calpage_geometry,
               test_single_page_and_stream_order,
               test_gs_pnggray_gt_crops_pixel_exact,
               test_gs_tiffsep_d_and_s_groups_exact,
               test_pins_previous_sheets_byte_identical):
        fn()
        print(f"PASS {fn.__name__}")
    print("all modprobe tests passed")
