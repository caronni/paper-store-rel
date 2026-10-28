"""E010 MOTIF-1 pre-flight (simulation before toner — generator side).

Checks, in order: byte-identical regeneration (sha gates reuse); codec
round-trip (symbols_to_field then re-block + exact dictionary lookup recovers
the GT indices for all three regions, no channel); every assembled region
field globally i2w3-legal (motif_codec.block_legal on the whole region);
manifest/GT schema present + GT shapes match; the dropout region's choice set
is exactly the dropout-source motifs and dropout_pair_indices is recorded;
gs pnggray -r600 pixel-exact for a crop of the main region (the clean K
imagemask must render bit-for-bit onto the GT motif field).

Runs under pytest, or standalone: env/bin/python tests/test_motif1.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "010-motif-b2"
BUILD = EXP / "build"
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(ROOT / "src"))

import motif_codec as mc  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
_cache: dict = {}


def _run_gen() -> tuple[str, str]:
    r = subprocess.run([sys.executable, "gen_motif1.py"], cwd=EXP,
                       check=True, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    ps_sha = hashlib.sha256((BUILD / "motif1.ps").read_bytes()).hexdigest()
    mf_sha = hashlib.sha256(
        (BUILD / "motif1_manifest.json").read_bytes()).hexdigest()
    return ps_sha, mf_sha


def _built() -> None:
    if "sha" not in _cache:
        _cache["sha"] = _run_gen()


def _manifest() -> dict:
    _built()
    return json.loads((BUILD / "motif1_manifest.json").read_text())


def _dictionary() -> np.ndarray:
    if "dict" not in _cache:
        _cache["dict"] = mc.build_dictionary(_manifest()["b"])
    return _cache["dict"]


def _region(mf: dict, name: str) -> dict:
    return next(r for r in mf["regions"] if r["name"] == name)


def _decode_field_to_indices(field: np.ndarray, dictionary: np.ndarray,
                             b: int) -> np.ndarray:
    """Re-block and exact-lookup each B x B block against the dictionary
    (NO channel, NO nearest-neighbour needed — the printed dots are exact)."""
    R, C = field.shape[0] // b, field.shape[1] // b
    key = {dictionary[i].tobytes(): i for i in range(len(dictionary))}
    out = np.empty((R, C), np.int64)
    for i in range(R):
        for j in range(C):
            blk = field[i * b:(i + 1) * b, j * b:(j + 1) * b]
            out[i, j] = key[np.ascontiguousarray(blk).tobytes()]
    return out


# -- 1. determinism -----------------------------------------------------------

def test_determinism_byte_identical() -> None:
    a = _run_gen()
    b = _run_gen()
    assert a == b, f"regeneration not byte-identical: {a} vs {b}"
    _cache["sha"] = b


# -- 2. manifest / GT schema --------------------------------------------------

def test_manifest_schema_and_gt_shapes() -> None:
    mf = _manifest()
    for k in ("b", "seed", "jobid", "ps_sha256", "dictionary_sha256",
              "hw_dpi", "page_size_pt", "regions", "corner_marks"):
        assert k in mf, f"missing manifest key {k}"
    assert mf["b"] == 7 and mf["hw_dpi"] == 600
    assert mf["page_size_pt"] == [595, 842]
    # dictionary sha matches the freshly built dictionary
    d = _dictionary()
    assert mf["dictionary_sha256"] == hashlib.sha256(d.tobytes()).hexdigest()
    assert mf["ps_sha256"] == _cache["sha"][0]

    names = {r["name"] for r in mf["regions"]}
    assert names == {"main", "dropout", "control"}, names
    seen: dict[str, str] = {}
    for r in mf["regions"]:
        assert r["cell_dots"] == 7
        assert r["kind"] in ("random", "dropout", "control")
        gt = np.load(BUILD / r["gt_file"])
        assert gt.shape == (r["rows"], r["cols"]), r["name"]
        assert gt.dtype.kind in "iu", (r["name"], gt.dtype)
        assert int(gt.max()) < len(d) and int(gt.min()) >= 0
        assert seen.setdefault(r["gt_file"], r["name"]) == r["name"]

    # corner marks: satellites 1..4, non-degenerate rects
    sats = sorted(c["satellites"] for c in mf["corner_marks"])
    assert sats == [1, 2, 3, 4], sats
    for c in mf["corner_marks"]:
        assert c["h_dots"] > 0 and c["w_dots"] > 0
        assert 0 < c["cx_dots"] and 0 < c["cy_dots"]


# -- 3. codec round-trip (no channel) -----------------------------------------

def test_codec_roundtrip_all_regions() -> None:
    mf = _manifest()
    d = _dictionary()
    b = mf["b"]
    for r in mf["regions"]:
        gt = np.load(BUILD / r["gt_file"])
        field = mc.symbols_to_field(gt, d, b)
        rec = _decode_field_to_indices(field, d, b)
        assert np.array_equal(rec, gt), \
            f"{r['name']}: {int((rec != gt).sum())} indices mismatch"


# -- 4. region i2w3 legality --------------------------------------------------

def test_regions_globally_i2w3_legal() -> None:
    mf = _manifest()
    d = _dictionary()
    b = mf["b"]
    for r in mf["regions"]:
        gt = np.load(BUILD / r["gt_file"])
        field = mc.symbols_to_field(gt, d, b)
        assert mc.block_legal(field), \
            f"{r['name']}: assembled field not globally i2w3-legal"


# -- 5. dropout / control choice-set semantics --------------------------------

def test_dropout_and_control_choice_sets() -> None:
    mf = _manifest()
    d = _dictionary()
    pairs = mc.dropout_pairs(d, mf["b"])
    src = {i for i, _ in pairs}
    immune = set(range(len(d))) - src

    drop = _region(mf, "dropout")
    assert "dropout_pair_indices" in drop
    dp = drop["dropout_pair_indices"]
    assert len(dp) == len(pairs) == mf["n_dropout_pairs"]
    assert {(i, j) for i, j in dp} == set(pairs)
    assert drop["n_dropout_source_motifs"] == len(src) == mf[
        "n_dropout_source_motifs"]
    gt = np.load(BUILD / drop["gt_file"])
    assert set(np.unique(gt).tolist()) <= src, "dropout uses a non-source motif"

    ctl = _region(mf, "control")
    assert ctl["n_immune_motifs"] == len(immune) == mf["n_immune_motifs"]
    gtc = np.load(BUILD / ctl["gt_file"])
    used = set(np.unique(gtc).tolist())
    assert used <= immune, "control uses a dropout-source motif"
    assert not (used & src), "control/source overlap"


# -- 6. gs render fidelity (crop of the main region) --------------------------

def _render_gray(dpi: int) -> np.ndarray:
    key = ("gray", dpi)
    if key not in _cache:
        import shutil
        assert shutil.which("gs") is not None, "ghostscript required"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "page.png"
            subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                            "-sDEVICE=pnggray", f"-r{dpi}",
                            "-o", str(out), str(BUILD / "motif1.ps")],
                           check=True, capture_output=True)
            _cache[key] = np.asarray(Image.open(out).convert("L"))
    return _cache[key]


def test_gs600_main_crop_pixel_exact() -> None:
    """gs (no screening on 1-bit imagemask) must render the main-region dots
    bit-for-bit onto the GT motif field — proves the printed bitmap IS the
    codec output (the Q2 measurement's ground truth)."""
    mf = _manifest()
    d = _dictionary()
    b = mf["b"]
    r = _region(mf, "main")
    img = _render_gray(600)
    gt = np.load(BUILD / r["gt_file"])
    # crop: first 60 x 60 motifs (avoids reading the whole 3542x2597 field)
    cr, cc = min(60, r["rows"]), min(60, r["cols"])
    x, y = r["x_dots"], r["y_dots"]
    crop = (img[y: y + cr * b, x: x + cc * b] < 128).astype(np.uint8)
    field_gt = mc.symbols_to_field(gt[:cr, :cc], d, b)
    assert np.array_equal(crop, field_gt), \
        f"main crop: {int((crop != field_gt).sum())}/{field_gt.size} px differ"


# -- 7. ANALYZER: clean positive control (detector + sampling correct) --------

def _analyzer():
    import analyze_motif1 as A  # noqa: PLC0415
    _built()  # ensure build/ artifacts exist for the analyzer to read
    return A


def test_analyzer_clean_positive_control() -> None:
    """Rasterize the GT field with NO channel and score it: symbol error must
    be ~0 in every region (proves the matched-filter detector + dot sampling
    are correct). A small residual (<0.5%) is the matched filter's inherent
    mean-centred tie floor, not a bug."""
    A = _analyzer()
    ctrl = A.clean_positive_control()
    for name in ("main", "dropout", "control"):
        se = ctrl[name]["symbol_error"]
        assert se < 0.005, f"clean control {name} symbol error {se:.4%} not ~0"
    assert ctrl["dropout"]["symbol_error"] == 0.0, "dropout clean must be exact"


# -- 8. ANALYZER: null control (rolled GT -> chance, usable MI ~ 0) -----------

def test_analyzer_null_control_is_chance() -> None:
    """A rolled-GT null must sit at ~chance symbol error ((D-1)/D >> 0.9) and
    deliver ~0 USABLE information (the permutation-null debias floors it)."""
    A = _analyzer()
    mf = _manifest()
    d = _dictionary()
    twins = A.build_twins(A.mc.dropout_pairs(d, mf["b"]))
    # score the CLEAN field, then compare the detector output to a rolled GT
    field = A._assemble_page_field(mf, d)
    grey = field.astype(float)
    b = mf["b"]
    dpm = A.dict_pm(d)
    r = next(rg for rg in mf["regions"] if rg["name"] == "main")
    coef = A.affine_identity(0, 0)
    blocks = A.region_blocks(grey, coef, r, b)
    detected = A.detect_blocks(blocks, dpm)
    sent = np.load(BUILD / r["gt_file"])
    rolled = np.roll(sent, 11, axis=0)  # scramble the pairing
    null_sym_err = float(np.mean(detected != rolled))
    assert null_sym_err > A.NULL_SYMERR_MIN, \
        f"null symbol error {null_sym_err:.3f} below chance floor"
    null_mi = A.mutual_information_bits(rolled, detected, len(d))
    real_mi = A.mutual_information_bits(sent, detected, len(d))
    # usable (real - null) must be strongly positive on the CLEAN field, and
    # the null MI must be far below the real MI (debias sanity).
    assert real_mi - null_mi > 3.0, (real_mi, null_mi)


# -- 9. ANALYZER: sim round-trip end-to-end, finite + dropout-confusion -------

def test_analyzer_sim_roundtrip_end_to_end() -> None:
    """The measured-M281 sim round-trip runs end-to-end and returns FINITE
    metrics in every region, with the dropout-confusion number populated and a
    verdict string. (This is the pre-paper Q2 prediction; we do not assert its
    value, only that the instrument produces a coherent finite result.)"""
    A = _analyzer()
    r = A.sim_roundtrip(seed=0)
    assert r["source"] == "sim" and r["verdict"] in ("GO", "NO-GO")
    for name in ("main", "dropout", "control"):
        m = r["regions"][name]
        for k in ("symbol_error", "mi_bits_per_motif", "null_mi_bits_per_motif",
                  "usable_mi_bits_per_motif", "usable_b_per_mm2"):
            assert np.isfinite(m[k]), f"{name}.{k} not finite"
        assert 0.0 <= m["symbol_error"] <= 1.0
        assert m["usable_b_per_mm2"] >= 0.0
    dc = r["regions"]["dropout"]["dropout_confusion"]
    for k in ("dropout_confusion_rate", "generic_error_rate",
              "twin_share_of_errors", "n_twin_hits", "n_blocks"):
        assert k in dc, f"dropout_confusion missing {k}"
    assert np.isfinite(dc["dropout_confusion_rate"])
    assert dc["n_blocks"] == r["regions"]["dropout"]["n_symbols"]
    # the confusion rate is a real fraction of blocks
    assert 0.0 <= dc["dropout_confusion_rate"] <= 1.0


# -- 10. ANALYZER: detector is vectorized (runtime sane on the main region) ---

def test_analyzer_detector_vectorized_runtime() -> None:
    """The matched-filter detect over the FULL D=1170 dictionary on the whole
    main region (~1.9e5 blocks) must run in a few seconds — i.e. it is the
    vectorized (N,b*b)@(b*b,D) matmul, not a python per-block loop."""
    import time  # noqa: PLC0415
    A = _analyzer()
    mf = _manifest()
    d = _dictionary()
    field = A._assemble_page_field(mf, d)
    grey = field.astype(float)
    r = next(rg for rg in mf["regions"] if rg["name"] == "main")
    coef = A.affine_identity(0, 0)
    blocks = A.region_blocks(grey, coef, r, mf["b"])
    dpm = A.dict_pm(d)
    t0 = time.perf_counter()
    det = A.detect_blocks(blocks, dpm)
    dt = time.perf_counter() - t0
    assert det.shape == (r["rows"], r["cols"])
    assert dt < 5.0, f"detect_blocks took {dt:.2f}s on the main region " \
                     "(not vectorized?)"


if __name__ == "__main__":
    fns = [test_determinism_byte_identical,
           test_manifest_schema_and_gt_shapes,
           test_codec_roundtrip_all_regions,
           test_regions_globally_i2w3_legal,
           test_dropout_and_control_choice_sets,
           test_gs600_main_crop_pixel_exact,
           test_analyzer_clean_positive_control,
           test_analyzer_null_control_is_chance,
           test_analyzer_sim_roundtrip_end_to_end,
           test_analyzer_detector_vectorized_runtime]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
