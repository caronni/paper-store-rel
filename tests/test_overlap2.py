"""Exp 002.2 overlap2 sheet: determinism, geometry, stream order, byte-identity
pins for earlier printed stimuli, and the gs tiffsep semantics preflight.

What ghostscript 10.07 ACTUALLY does with this page (measured on this machine;
gs verifies emission semantics ONLY — it does not emulate the M281 RIP's
re-screening, so screening upside vs 002.0c is decided on the printed sheet):

- Block A put_cmyk_bitmap composites (7-state c3/c4/c6, 8-state+K c4, 3-plane
  50% c4/c6): every separation == its GT plane exactly, and plates without
  content stay empty. gs neither screens nor knocks out image-path composites.
- Block A single-plane imagemask references: exact (the 002.0 bit-faithful path).
- S1 imagemask in [/Separation (ink) /DeviceCMYK tint] with `1 setcolor` +
  `true setoverprint`, NO OPM: every separation == GT. gs honors
  Separation-space overprint on tiffsep by default (no -dOverprint flag
  needed). The 002.1 P2 lesson (DeviceCMYK + setoverprint still knocks out at
  OPM 0) does NOT carry over: OPM governs DeviceCMYK *zero components* only;
  a Separation space simply does not address the other colorants, so
  overprint alone exempts them (PLRM 4.8.4/8.5.3). Measured discriminator:
  at C&M overlap sites the C plate stays inked (knockout would erase ~31k px
  in the 15x15 mm field).
- S2 (S1 + the guarded OPM-1 dance): byte-identical separations to S1 — the
  dance is accepted and irrelevant for Separation spaces, harmless end to end.
- S3 one 3-component /DeviceN [(Cyan)(Magenta)(Yellow)] /DeviceCMYK image:
  every separation == GT; Black untouched; Y written as explicit 0 where its
  tint is 0 (the DeviceN twin of put_cmyk_bitmap behaves like it).
- No spot-color separation files appear: gs maps the (Cyan)/(Magenta)/(Yellow)
  Separation and DeviceN colorant names onto the process plates.

The paper decides truth for the M281 RIP; these asserts pin gs semantics so an
interpreter/flag regression cannot masquerade as an engine finding.
"""
from __future__ import annotations

import hashlib
import pytest
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "002-calibration-page"
BUILD = EXP / "build"

# 2026-09-06: every test here reads a build that a test regenerates in place;
# test_calpage.py, test_composite_probe.py, test_modprobe.py write the same
# directory.  One xdist worker per build directory (pyproject: --dist
# loadgroup).
pytestmark = pytest.mark.xdist_group("build-002-003-probes")
EXP001 = ROOT / "experiments" / "001-engine-characterization"

# byte-identity pins for artifacts that already went to (or gate) hardware:
# regenerating them must reproduce the logged sha256 even though gen_overlap2
# left psgen untouched — cheap insurance against accidental default-path drift.
PINS = (
    (EXP001 / "gen_gridtest.py", EXP001 / "build" / "gridtest.ps",
     "904a5393cc04b86055a0132b1f993e4dac2ba4c6f99fd419c9edf38cfc13fe30"),
    (EXP / "gen_calpage.py", BUILD / "calpage.ps",
     "39ce59e51e70690896e23fc414e4c77af83ede923818d2acd41a1ba24241534b"),
    (EXP / "gen_composite_probe.py", BUILD / "composite_probe.ps",
     "58637ad3773315451f0a585bf4419ea395ac36baba5215f5ed04880102086cdd"),
)

_STATE: dict = {}


def _generate() -> tuple[str, str, tuple]:
    r = subprocess.run([sys.executable, str(EXP / "gen_overlap2.py")],
                       capture_output=True, text=True, timeout=600, cwd=str(EXP))
    assert r.returncode == 0, f"gen_overlap2.py failed:\n{r.stdout}\n{r.stderr}"
    ps_sha = hashlib.sha256((BUILD / "overlap2.ps").read_bytes()).hexdigest()
    mf_sha = hashlib.sha256((BUILD / "overlap2_manifest.json").read_bytes()).hexdigest()
    gt_shas = tuple(sorted(
        (p.name, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in (BUILD / "overlap2_gt").glob("*.npy")))
    return ps_sha, mf_sha, gt_shas


def _built() -> None:
    if "sha" not in _STATE:
        _STATE["sha"] = _generate()


def _manifest() -> dict:
    _built()
    return json.loads((BUILD / "overlap2_manifest.json").read_text())


# -- 1. determinism -----------------------------------------------------------

def test_determinism_byte_identical() -> None:
    a = _generate()
    b = _generate()
    assert a == b, "regeneration not byte-identical"
    assert len(b[2]) == 49, f"expected 49 gt files, got {len(b[2])}"
    _STATE["sha"] = b


# -- 2. geometry ----------------------------------------------------------------

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
    cal_mf = BUILD / "calpage_manifest.json"
    if cal_mf.exists():
        cal = json.loads(cal_mf.read_text())
        cal_corners = {e["params"]["satellites"]: e for e in cal["patches"]
                       if e["kind"] == "corner_mark"}
        for n in (1, 2, 3, 4):
            for k in ("x_dots", "y_dots", "w_dots", "h_dots", "params"):
                assert corners[n][k] == cal_corners[n][k], \
                    f"corner {n}: {k} differs from calpage"


def test_single_page_and_stream_order() -> None:
    """ONE page; ALL Block-A bitmaps stream before any S-block; S1 < S2 < S3;
    the END sentinel is the very last element (error containment: a mid-image
    fault can only cost later S-blocks, never Block A)."""
    mf = _manifest()
    ps = (BUILD / "overlap2.ps").read_text()
    assert "%%Pages: 1" in ps and ps.count("%%Page:") == 1
    assert ps.count("showpage") == 1

    first_sep = ps.index("/Separation (")
    first_dn = ps.index("/DeviceN [")
    # every Block-A DeviceCMYK 4-channel image precedes any S-block
    assert ps.count("/Decode [0 1 0 1 0 1 0 1]") == 6  # A1 x3, A2, A3 x2
    assert ps.rindex("/Decode [0 1 0 1 0 1 0 1]") < first_sep
    # every Block-A imagemask precedes any S-block: 4 corners + plus lattice
    # + 5 single-plane refs, and nothing else
    n_plus = sum(1 for e in mf["patches"] if e["kind"] == "plus_mark")
    assert ps[:first_sep].count("imagemask") == 4 + n_plus + 5
    # S ordering: S1 before S2 before S3; DeviceN only in S3
    assert ps.index("% ---- S1/") < ps.index("% ---- S2/") < ps.index("% ---- S3/")
    assert first_sep < first_dn
    assert ps[first_sep:first_dn].count("imagemask") == 14  # 7 paints x S1,S2
    assert ps.count("/Separation (") == 14
    assert ps.count("/DeviceN [") == 3                      # S3 patches
    assert ps.count("/Decode [0 1 0 1 0 1]") == 3           # 3-comp DeviceN images
    # END sentinel last: nothing paintable after it but the sentinel itself
    si = ps.index("% ---- END sentinel")
    tail = ps[si:]
    for tok in ("imagemask", "/Separation (", "/DeviceN [", ">> image"):
        assert tok not in tail, f"{tok!r} streams after the END sentinel"
    assert "showpage" in tail and tail.rstrip().endswith("%%EOF")


def test_gt_shapes_whole_manifest() -> None:
    mf = _manifest()
    seen: dict[str, str] = {}
    n_gt = 0
    for e in mf["patches"]:
        if e["gt"] is None:
            continue
        assert seen.setdefault(e["gt"], e["name"]) == e["name"], \
            f"gt file {e['gt']} shared by {seen[e['gt']]} and {e['name']}"
        gt = np.load(BUILD / e["gt"])
        assert gt.shape == (e["h_dots"], e["w_dots"]), \
            f"{e['name']}: gt {gt.shape} vs manifest ({e['h_dots']},{e['w_dots']})"
        n_gt += 1
    assert n_gt == 45  # 49 files minus the 4 *_states.npy cell-index arrays


def test_s_content_byte_identical_across_variants() -> None:
    """S1/S2/S3 must paint the same per-plane bits — emission path is the ONLY
    variable (one rng draw per patch slot)."""
    mf = _manifest()
    for slot, planes in (("field_cm", "CM"), ("field_cmy", "CMY"), ("solid_cm", "CM")):
        for p in planes:
            ref = np.load(BUILD / f"overlap2_gt/S1__{slot}_{p}.npy")
            for vid in ("S2", "S3"):
                other = np.load(BUILD / f"overlap2_gt/{vid}__{slot}_{p}.npy")
                assert np.array_equal(ref, other), f"{vid}/{slot} {p} differs from S1"
    for e in mf["patches"]:
        if e["params"].get("block") == "B":
            assert e["params"]["paint_order"][0] == "C", "paint order must start at C"


# -- 3. gs tiffsep semantics ----------------------------------------------------

def _separations() -> dict[str, np.ndarray]:
    """Render one tiffsep pass at 600 dpi; return boolean ink maps per plane."""
    _built()
    if "seps" in _STATE:
        return _STATE["seps"]
    assert shutil.which("gs") is not None, "ghostscript required for preflight"
    sepdir = BUILD / "preflight_sep_overlap2"
    sepdir.mkdir(exist_ok=True)
    for old in sepdir.glob("ov_*.tif*"):
        old.unlink()
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=tiffsep",
                    "-r600", "-o", str(sepdir / "ov_%d.tif"),
                    str(BUILD / "overlap2.ps")], check=True, timeout=600)
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    # no spot separations may appear: Separation/DeviceN colorant names must
    # map onto the process plates (finding, see module docstring)
    extra = sorted(p.name for p in sepdir.glob("ov_1(*.tif")
                   if p.name not in {f"ov_1({n}).tif"
                                     for n in ("Cyan", "Magenta", "Yellow", "Black")})
    assert not extra, f"unexpected spot separations: {extra}"
    seps = {}
    for plane, name in (("C", "Cyan"), ("M", "Magenta"), ("Y", "Yellow"), ("K", "Black")):
        # tiffsep separation polarity: ink = 0 (dark), paper = 255
        seps[plane] = np.asarray(Image.open(sepdir / f"ov_1({name}).tif")) < 128
    _STATE["seps"] = seps
    return seps


def _crop(seps: dict, mf: dict, plane: str, name: str) -> np.ndarray:
    e = next(e for e in mf["patches"] if e["name"] == name)
    return seps[plane][e["y_dots"]: e["y_dots"] + e["h_dots"],
                       e["x_dots"]: e["x_dots"] + e["w_dots"]]


def _gt(mf: dict, name: str) -> np.ndarray:
    e = next(e for e in mf["patches"] if e["name"] == name)
    return np.load(BUILD / e["gt"]).astype(bool)


def _assert_same(got: np.ndarray, want: np.ndarray, what: str) -> None:
    assert np.array_equal(got, want), \
        f"{what}: {int((got != want).sum())}/{want.size} px differ"


def test_gs_tiffsep_block_a_separations_exact() -> None:
    """gs neither screens nor knocks out image-path composites: every Block-A
    separation == its GT plane; content-free plates stay empty."""
    mf, seps = _manifest(), _separations()
    for base, planes in (("A1/state7_c3", "CMY"), ("A1/state7_c4", "CMY"),
                         ("A1/state7_c6", "CMY"), ("A2/state8k_c4", "CMYK"),
                         ("A3/comp_c4", "CMY"), ("A3/comp_c6", "CMY")):
        for p in planes:
            _assert_same(_crop(seps, mf, p, f"{base}_{p}"), _gt(mf, f"{base}_{p}"),
                         f"{base} {p}")
        if "K" not in planes:
            assert not _crop(seps, mf, "K", f"{base}_C").any(), f"{base}: K plate marked"
    for name in ("A4/ref_C_c4", "A4/ref_M_c4", "A4/ref_Y_c4", "A4/ref_K_c4",
                 "A4/ref_K_c6"):
        e = next(e for e in mf["patches"] if e["name"] == name)
        (p,) = e["planes"]
        _assert_same(_crop(seps, mf, p, name), _gt(mf, name), name)


def _assert_sep_variant_preserved(vid: str) -> None:
    mf, seps = _manifest(), _separations()
    for slot, planes in ((f"{vid}/field_cm", "CM"), (f"{vid}/field_cmy", "CMY")):
        for p in planes:
            _assert_same(_crop(seps, mf, p, f"{slot}_{p}"), _gt(mf, f"{slot}_{p}"),
                         f"{slot} {p}")
    for p in "CM":
        assert _crop(seps, mf, p, f"{vid}/solid_cm_{p}").all(), f"{vid}/solid_cm {p}"
    # discriminator vs the P1/P2-style knockout hypothesis: overlap sites
    # exist and the EARLIER paint (C) survives the later ones there
    C, M = _gt(mf, f"{vid}/field_cm_C"), _gt(mf, f"{vid}/field_cm_M")
    assert (C & M).sum() > 20000, "field_cm overlap unexpectedly sparse"
    assert _crop(seps, mf, "C", f"{vid}/field_cm_C")[C & M].all(), \
        f"{vid}: C knocked out at C&M overlap"
    # unaddressed plates stay clean
    for slot in ("field_cm", "field_cmy", "solid_cm"):
        assert not _crop(seps, mf, "K", f"{vid}/{slot}_C").any(), \
            f"{vid}/{slot}: K plate marked"
    assert not _crop(seps, mf, "Y", f"{vid}/field_cm_C").any(), \
        f"{vid}/field_cm: Y plate marked"


def test_gs_tiffsep_s1_separation_overprint_honored_without_opm() -> None:
    """MEASURED gs 10.07 finding: Separation-space overprint is honored on
    tiffsep by default — separations == GT with NO OPM and no -dOverprint flag
    (unlike 002.1 P2, where DeviceCMYK + setoverprint still knocked out at
    OPM 0). The M281 RIP may differ; the printed sheet decides."""
    _assert_sep_variant_preserved("S1")


def test_gs_tiffsep_s2_opm_dance_identical_to_s1() -> None:
    """The guarded OPM-1 dance is accepted and changes nothing for Separation
    spaces on gs — byte-identical separations to S1 inside the probe rects."""
    _assert_sep_variant_preserved("S2")
    mf, seps = _manifest(), _separations()
    for slot in ("field_cm", "field_cmy", "solid_cm"):
        for p in ("C", "M", "Y"):
            _assert_same(_crop(seps, mf, p, f"S2/{slot}_C"),
                         _crop(seps, mf, p, f"S1/{slot}_C"),
                         f"S2 vs S1 {slot} {p} plate")


def test_gs_tiffsep_s3_devicen_image_exact() -> None:
    """The 3-component DeviceN CMY image behaves as put_cmyk_bitmap's twin on
    gs: every separation == GT (explicit 0 tints included), Black untouched."""
    mf, seps = _manifest(), _separations()
    for slot, planes in (("S3/field_cm", "CM"), ("S3/field_cmy", "CMY")):
        for p in planes:
            _assert_same(_crop(seps, mf, p, f"{slot}_{p}"), _gt(mf, f"{slot}_{p}"),
                         f"{slot} {p}")
    for p in "CM":
        assert _crop(seps, mf, p, f"S3/solid_cm_{p}").all(), f"S3/solid_cm {p}"
    # the image writes explicit zeros on addressed plates, leaves Black alone
    assert not _crop(seps, mf, "Y", "S3/field_cm_C").any(), "S3 CM rect marked Y"
    for slot in ("field_cm", "field_cmy", "solid_cm"):
        assert not _crop(seps, mf, "K", f"S3/{slot}_C").any(), f"S3/{slot} marked K"


# -- 4. byte-identity pins for earlier hardware-facing artifacts -----------------

def test_pins_gridtest_calpage_composite_probe_byte_identical() -> None:
    for script, out, want in PINS:
        r = subprocess.run([sys.executable, str(script)], capture_output=True,
                           text=True, timeout=600, cwd=str(script.parent))
        assert r.returncode == 0, f"{script.name} failed:\n{r.stdout}\n{r.stderr}"
        got = hashlib.sha256(out.read_bytes()).hexdigest()
        assert got == want, f"{out.name} drifted: {got}"


if __name__ == "__main__":
    for fn in (test_determinism_byte_identical,
               test_geometry_no_overlaps_labels_clear_bounds,
               test_registration_marks_match_calpage_geometry,
               test_single_page_and_stream_order,
               test_gt_shapes_whole_manifest,
               test_s_content_byte_identical_across_variants,
               test_gs_tiffsep_block_a_separations_exact,
               test_gs_tiffsep_s1_separation_overprint_honored_without_opm,
               test_gs_tiffsep_s2_opm_dance_identical_to_s1,
               test_gs_tiffsep_s3_devicen_image_exact,
               test_pins_gridtest_calpage_composite_probe_byte_identical):
        fn()
        print(f"PASS {fn.__name__}")
    print("all overlap2 tests passed")
