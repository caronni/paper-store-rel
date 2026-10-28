"""Exp 002.1 composite emission probe: determinism, geometry, psgen overprint
flags, and the gs tiffsep OVERPRINT-semantics preflight.

What ghostscript 10.07 ACTUALLY does with each variant (measured on this
machine; the tiffsep test verifies overprint semantics ONLY — gs does not
emulate the M281 RIP's re-screening, so P0 renders clean here and screening is
decided on the printed sheet, run protocol PROTOCOL-002.1-draft.md):

- P0 put_cmyk_bitmap: every separation == its GT plane exactly (the 4-channel
  image writes all components, explicit white included).
- P1 imagemask sequential, overprint off: knockout — C sep == C&~M (2-plane),
  C&~M&~Y and M&~Y (3-plane); the C+M solid overlap leaves the C plate EMPTY.
- P2 (+ true setoverprint, OPM 0): IDENTICAL to P1 on gs. Strict PLRM
  semantics: overprint exempts only colorants the color space does not
  address; DeviceCMYK addresses all four, so zero components still knock out
  at OPM 0. Adobe-derived RIPs are known to differ here (some default OPM=1)
  — the print decides; that is why P2 and P3 are both on the sheet.
- P3 (+ OPM 1): preserved — every separation == its GT plane exactly.
  gs 10.07 dialect note: the Adobe PS3 integer form `1 setoverprintmode`
  raises /typecheck (gs wants a BOOLEAN). psgen emits a dual-guarded request
  (integer form first, boolean fallback, each where/stopped-guarded); P3
  rendering correctly proves the fallback works end to end.
- P4 single-plane imagemask: exact (the 002.0 bit-faithful path).

No -dOverprint flag is passed: tiffsep is a native separation device and the
P3-preserved result shows gs honors overprint + OPM by default at 600 dpi.
Negative finding (measured, gs 10.07): composite devices do NOT honor these
semantics — png16m and tiff32nc render P3 knocked out even with
-dOverprint=/simulate. Overprint preflights must use tiffsep; a composite
"preview" render of this page shows P2/P3 overlap wrongly and must not be
used to judge them.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "002-calibration-page"
BUILD = EXP / "build"
EXP001 = ROOT / "experiments" / "001-engine-characterization"

# hardware-log gate (experiments/001-engine-characterization.md): the printed
# gridtest.ps stimulus. psgen's default emission path must stay byte-identical.
GRIDTEST_SHA = "904a5393cc04b86055a0132b1f993e4dac2ba4c6f99fd419c9edf38cfc13fe30"

_STATE: dict = {}


def _generate() -> tuple[str, str, tuple]:
    r = subprocess.run([sys.executable, str(EXP / "gen_composite_probe.py")],
                       capture_output=True, text=True, timeout=600, cwd=str(EXP))
    assert r.returncode == 0, f"gen_composite_probe.py failed:\n{r.stdout}\n{r.stderr}"
    ps_sha = hashlib.sha256((BUILD / "composite_probe.ps").read_bytes()).hexdigest()
    mf_sha = hashlib.sha256((BUILD / "composite_probe_manifest.json").read_bytes()).hexdigest()
    gt_shas = tuple(sorted(
        (p.name, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in (BUILD / "composite_probe_gt").glob("*.npy")))
    return ps_sha, mf_sha, gt_shas


def _built() -> None:
    if "sha" not in _STATE:
        _STATE["sha"] = _generate()


def _manifest() -> dict:
    _built()
    return json.loads((BUILD / "composite_probe_manifest.json").read_text())


# -- 1. determinism -----------------------------------------------------------

def test_determinism_byte_identical() -> None:
    a = _generate()
    b = _generate()
    assert a == b, "regeneration not byte-identical"
    _STATE["sha"] = b


# -- 2. psgen overprint flags: opt-in only, default emission untouched --------

def test_psgen_overprint_flags_emission() -> None:
    from paperholo.psgen import CMYK, PSDoc

    bits = np.eye(4, dtype=np.uint8)

    def render(**kw) -> str:
        doc = PSDoc(hw_dpi=600, page_size_pt=(72, 72), title="ovp")
        doc.begin_page()
        doc.put_bitmap(bits, 10, 10, CMYK["C"], **kw)
        doc.end_page()
        return doc.render()

    plain = render()
    assert "setoverprint" not in plain, "default put_bitmap must not touch overprint"
    ovp = render(overprint=True)
    lines = ovp.splitlines()
    assert lines[lines.index("gsave") + 1] == "true setoverprint"
    assert "setoverprintmode" not in ovp
    both = render(overprint=True, opm=True)
    assert "true setoverprint" in both
    assert "/setoverprintmode where { pop" in both          # guarded, not bare
    assert "mark { 1 setoverprintmode } stopped" in both    # Adobe integer form
    assert "{ true setoverprintmode } stopped" in both      # gs boolean fallback
    # flags must be strictly additive: removing their lines recovers the default
    stripped = "\n".join(l for l in both.splitlines()
                         if "setoverprint" not in l and l not in
                         ("  { cleartomark mark { true setoverprintmode } stopped cleartomark }",
                          "  { cleartomark } ifelse } if"))
    assert stripped + "\n" == plain


def test_psgen_default_path_byte_identical_gridtest() -> None:
    """Regenerate the exp-001 printed stimulus; sha256 must equal the RESULTS
    log gate — proof the psgen flag change left the default path untouched."""
    r = subprocess.run([sys.executable, str(EXP001 / "gen_gridtest.py")],
                       capture_output=True, text=True, timeout=600, cwd=str(EXP001))
    assert r.returncode == 0, f"gen_gridtest.py failed:\n{r.stdout}\n{r.stderr}"
    sha = hashlib.sha256((EXP001 / "build" / "gridtest.ps").read_bytes()).hexdigest()
    assert sha == GRIDTEST_SHA, f"gridtest.ps drifted: {sha}"


# -- 3. geometry ---------------------------------------------------------------

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
    """Corner marks must be positionally and parametrically identical to the
    calpage ones so cal_core.register works by swapping in this manifest."""
    mf = _manifest()
    cal = json.loads((BUILD / "calpage_manifest.json").read_text()) \
        if (BUILD / "calpage_manifest.json").exists() else None
    probe_corners = {e["params"]["satellites"]: e for e in mf["patches"]
                     if e["kind"] == "corner_mark"}
    assert sorted(probe_corners) == [1, 2, 3, 4]
    n_plus = sum(1 for e in mf["patches"] if e["kind"] == "plus_mark")
    assert n_plus >= 6, f"only {n_plus} plus marks — register() needs landmarks"
    if cal is not None:
        cal_corners = {e["params"]["satellites"]: e for e in cal["patches"]
                       if e["kind"] == "corner_mark"}
        for n in (1, 2, 3, 4):
            for k in ("x_dots", "y_dots", "w_dots", "h_dots", "params"):
                assert probe_corners[n][k] == cal_corners[n][k], \
                    f"corner {n}: {k} differs from calpage"


# -- 4. gs tiffsep overprint-semantics round-trip ------------------------------

def _separations() -> dict[str, np.ndarray]:
    """Render one tiffsep pass at 600 dpi; return boolean ink maps per plane."""
    _built()
    if "seps" in _STATE:
        return _STATE["seps"]
    assert shutil.which("gs") is not None, "ghostscript required for preflight"
    sepdir = BUILD / "preflight_sep"
    sepdir.mkdir(exist_ok=True)
    for old in sepdir.glob("cp_*.tif*"):
        old.unlink()
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=tiffsep",
                    "-r600", "-o", str(sepdir / "cp_%d.tif"),
                    str(BUILD / "composite_probe.ps")], check=True, timeout=600)
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    seps = {}
    for plane, name in (("C", "Cyan"), ("M", "Magenta"), ("Y", "Yellow"), ("K", "Black")):
        # tiffsep separation polarity: ink = 0 (dark), paper = 255
        seps[plane] = np.asarray(Image.open(sepdir / f"cp_1({name}).tif")) < 128
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


def test_gs_tiffsep_p0_image_composite_exact() -> None:
    mf, seps = _manifest(), _separations()
    for patch, planes in (("field_cm", "CM"), ("field_cmy", "CMY"), ("solid_cm", "CM")):
        for p in planes:
            _assert_same(_crop(seps, mf, p, f"P0/{patch}_{p}"),
                         _gt(mf, f"P0/{patch}_{p}"), f"P0/{patch} {p}")
    # the 4-channel image also writes explicit zeros: Y plate empty in the CM rect
    assert not _crop(seps, mf, "Y", "P0/field_cm_C").any(), "P0 cm rect marked Y"


def _assert_knockout(vid: str) -> None:
    """C loses to M, M loses to Y — later paints erase earlier at overlap."""
    mf, seps = _manifest(), _separations()
    C, M = _gt(mf, f"{vid}/field_cm_C"), _gt(mf, f"{vid}/field_cm_M")
    _assert_same(_crop(seps, mf, "C", f"{vid}/field_cm_C"), C & ~M,
                 f"{vid}/field_cm C (expected knockout)")
    _assert_same(_crop(seps, mf, "M", f"{vid}/field_cm_M"), M, f"{vid}/field_cm M")
    C3, M3, Y3 = (_gt(mf, f"{vid}/field_cmy_{p}") for p in "CMY")
    _assert_same(_crop(seps, mf, "C", f"{vid}/field_cmy_C"), C3 & ~M3 & ~Y3,
                 f"{vid}/field_cmy C (expected knockout)")
    _assert_same(_crop(seps, mf, "M", f"{vid}/field_cmy_M"), M3 & ~Y3,
                 f"{vid}/field_cmy M (expected knockout)")
    _assert_same(_crop(seps, mf, "Y", f"{vid}/field_cmy_Y"), Y3, f"{vid}/field_cmy Y")
    assert not _crop(seps, mf, "C", f"{vid}/solid_cm_C").any(), \
        f"{vid}/solid_cm: C plate should be fully knocked out"
    assert _crop(seps, mf, "M", f"{vid}/solid_cm_M").all(), f"{vid}/solid_cm M"


def test_gs_tiffsep_p1_knockout() -> None:
    _assert_knockout("P1")


def test_gs_tiffsep_p2_overprint_without_opm_still_knocks_out() -> None:
    """Measured gs 10.07 behavior, per strict PLRM DeviceCMYK semantics (see
    module docstring). On the real RIP P2 may differ — the sheet decides."""
    _assert_knockout("P2")


def test_gs_tiffsep_p3_opm1_preserves_all_planes() -> None:
    mf, seps = _manifest(), _separations()
    for patch, planes in (("field_cm", "CM"), ("field_cmy", "CMY")):
        for p in planes:
            _assert_same(_crop(seps, mf, p, f"P3/{patch}_{p}"),
                         _gt(mf, f"P3/{patch}_{p}"), f"P3/{patch} {p} (overprint)")
    for p in "CM":
        assert _crop(seps, mf, p, f"P3/solid_cm_{p}").all(), f"P3/solid_cm {p}"


def test_gs_tiffsep_p4_references_exact() -> None:
    mf, seps = _manifest(), _separations()
    for p in "CMY":
        _assert_same(_crop(seps, mf, p, f"P4/ref_{p}"), _gt(mf, f"P4/ref_{p}"),
                     f"P4/ref_{p}")
        assert _crop(seps, mf, p, f"P4/solid_{p}").all(), f"P4/solid_{p}"


if __name__ == "__main__":
    for fn in (test_determinism_byte_identical,
               test_psgen_overprint_flags_emission,
               test_psgen_default_path_byte_identical_gridtest,
               test_geometry_no_overlaps_labels_clear_bounds,
               test_registration_marks_match_calpage_geometry,
               test_gs_tiffsep_p0_image_composite_exact,
               test_gs_tiffsep_p1_knockout,
               test_gs_tiffsep_p2_overprint_without_opm_still_knocks_out,
               test_gs_tiffsep_p3_opm1_preserves_all_planes,
               test_gs_tiffsep_p4_references_exact):
        fn()
        print(f"PASS {fn.__name__}")
    print("all composite-probe tests passed")
