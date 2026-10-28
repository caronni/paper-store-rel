"""Exp 011 pilot-compose preflight (simulation before toner — gates any print).

Checks, in order: byte-identical regeneration of build/e011.ps + manifest;
manifest geometry (field rect, >= 6 mm content margins on A4, layout_version 2,
sha/jobid consistency); payload capacity formula; payload bijection round-trip
(compose -> extract_payload == payload, fake word_provider, plus the scramble
equivalence with the encodings kcell keystream convention); the full generated
page's payload recovered from its GT bitmap; gs pnggray -r600 render
pixel-exact against the GT (the heart of this module: gs does not screen, so
the render must equal the addressed bitmap exactly) with nothing painted
outside the field rect; pilot overlay spot-check (known word bits at expected
dot coords in the render); cal_core manifest compatibility
(load_manifest/entry/load_gt unchanged); and the default word-provider path
(real pilots.encode_word).

pilots.encode_word is a HARD requirement (finding [6], wave-3): the previous
--fake-words fallback let the whole preflight go green on a non-decodable
rng-words page if pilots.encode_word ever disappeared (verified by deleting
it: 10/10 passed while the manifest recorded the fake provider). The real
path is asserted at import AND in the manifest; the injectable word_provider
seam is exercised separately with an explicit fake provider by construction
(test_payload_bijection_fake_words), never by fallback.

Runs under pytest, or standalone: env/bin/python tests/test_e011.py
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
sys.path.insert(0, str(ROOT / "src"))
EXP = ROOT / "experiments" / "011-pilot-roundtrip"
BUILD = EXP / "build"
Image.MAX_IMAGE_PIXELS = None

from paperholo import compose as cp  # noqa: E402
from paperholo import pilots  # noqa: E402
from paperholo.encodings import get_encoding, key_symbols  # noqa: E402
from paperholo.modulation import keystream, rng  # noqa: E402

SEED = b"paper-store/exp011-pilot1"   # must match gen_e011.SEED
TSEED = b"test/e011-compose"
# hard requirement (finding [6]): this preflight gates a PRINT — degrading to
# --fake-words on a missing encode_word turned it into a green pass on a
# non-decodable page. ImportError/AttributeError here IS the test failure.
assert callable(getattr(pilots, "encode_word", None)), \
    "pilots.encode_word missing — e011 preflight cannot gate a print"
_GEN_ARGS: list[str] = []
_STATE: dict = {}


def _fake_provider(seed: bytes, layout):
    """Same construction as gen_e011.fake_word_provider (rng test-words label)."""
    n_sites = (layout.period_cells // layout.block_cells) ** 2

    def provider(ty: int, tx: int) -> np.ndarray:
        label = b"test-words/" + f"{ty},{tx}".encode()
        return rng(seed, label).integers(0, 2, size=n_sites, dtype=np.uint8)

    return provider


def _gen_provider(layout):
    """The provider the generator actually used (always the real pilot code)."""
    return lambda ty, tx: np.asarray(
        pilots.encode_word(layout, SEED, "K", 0, ty, tx), dtype=np.uint8)


def _generate() -> tuple[str, str]:
    r = subprocess.run([sys.executable, str(EXP / "gen_e011.py"), *_GEN_ARGS],
                       capture_output=True, text=True, timeout=600,
                       cwd=str(EXP))
    assert r.returncode == 0, f"gen_e011.py failed:\n{r.stdout}\n{r.stderr}"
    return (hashlib.sha256((BUILD / "e011.ps").read_bytes()).hexdigest(),
            hashlib.sha256(
                (BUILD / "e011_manifest.json").read_bytes()).hexdigest())


def _built() -> None:
    if "sha" not in _STATE:
        _STATE["sha"] = _generate()


def _manifest() -> dict:
    _built()
    return json.loads((BUILD / "e011_manifest.json").read_text())


def _field_entry(mf: dict) -> dict:
    (e,) = [p for p in mf["patches"] if p["name"] == "e011_field"]
    return e


def _gt_bits() -> np.ndarray:
    _built()
    if "gt" not in _STATE:
        _STATE["gt"] = np.load(BUILD / "e011_gt" / "K__e011_field.npy")
    return _STATE["gt"]


def _render_gray() -> np.ndarray:
    _built()
    if "gray" not in _STATE:
        subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                        "-sDEVICE=pnggray", "-r600",
                        "-o", str(BUILD / "preflight_600.png"),
                        str(BUILD / "e011.ps")], check=True, timeout=600)
        _STATE["gray"] = np.asarray(
            Image.open(BUILD / "preflight_600.png").convert("L"))
    return _STATE["gray"]


# -- 1. determinism -----------------------------------------------------------

def test_determinism_byte_identical() -> None:
    a = _generate()
    b = _generate()
    assert a == b, f"regeneration not byte-identical: {a} vs {b}"
    _STATE["sha"] = b


# -- 2. manifest geometry -----------------------------------------------------

def test_manifest_geometry_and_margins() -> None:
    mf = _manifest()
    assert mf["layout_version"] == 2
    assert mf["hw_dpi"] == 600
    assert mf["seed"] == SEED.decode()
    assert mf["jobid"] == hashlib.sha256(
        SEED + b"/e011" + b"/layout2").hexdigest()[:8]
    ps = (BUILD / "e011.ps").read_text()
    assert ps.isascii(), "Clean7Bit violated"
    assert mf["ps_sha256"] == hashlib.sha256(ps.encode()).hexdigest()
    assert mf["ps_bytes"] == len(ps)
    assert f"LAY=2 J={mf['jobid']}" in ps
    # the default build must carry the REAL pilot words (finding [6]): a
    # regression in the generator's flag handling may not ship a fake page
    assert mf["word_provider"] == "pilots.encode_word"
    assert "FAKE-WORDS" not in ps

    e = _field_entry(mf)
    assert (e["x_dots"], e["y_dots"]) == (230, 178)
    assert (e["w_dots"], e["h_dots"]) == (4500, 6660)
    assert e["params"]["cell_dots"] == 3
    assert e["params"]["pilot_layout"] == "p60b6.v2"
    assert e["params"]["page_cells_yx"] == [2220, 1500]
    # >= 6.0 mm content margins on A4 (4960 x 7016 dots), all four sides
    mm_dot = 25.4 / 600.0
    margins_mm = [e["x_dots"] * mm_dot,
                  e["y_dots"] * mm_dot,
                  (4960 - e["x_dots"] - e["w_dots"]) * mm_dot,
                  (7016 - e["y_dots"] - e["h_dots"]) * mm_dot]
    assert min(margins_mm) >= 6.0, f"margins {margins_mm} mm"
    x0, y0, x1, y1 = mf["content_bounds_mm"]
    assert e["x_dots"] * mm_dot >= x0 and e["y_dots"] * mm_dot >= y0
    assert (e["x_dots"] + e["w_dots"]) * mm_dot <= x1
    assert (e["y_dots"] + e["h_dots"]) * mm_dot <= y1


def test_spec_margin_validation_rejects() -> None:
    try:
        cp.ComposeSpec(x_dots=50)   # 50 dots = 2.1 mm < 6 mm bound
    except ValueError:
        pass
    else:
        raise AssertionError("ComposeSpec accepted a 2.1 mm margin")
    try:
        cp.ComposeSpec(page_cells_yx=(2220, 1501))   # not a multiple of 60
    except ValueError:
        pass
    else:
        raise AssertionError("ComposeSpec accepted partial pilot tiles")


# -- 3. capacity + payload bijection ------------------------------------------

def test_payload_capacity_formula() -> None:
    assert cp.payload_capacity(cp.ComposeSpec()) == 2220 * 1500 - 37 * 25 * 100


def test_payload_bijection_fake_words() -> None:
    spec = cp.ComposeSpec(page_cells_yx=(120, 180))
    cap = cp.payload_capacity(spec)
    assert cap == 120 * 180 - 2 * 3 * 100
    payload = rng(TSEED, b"payload").integers(0, 2, size=cap, dtype=np.uint8)
    prov = _fake_provider(TSEED, spec.pilot)
    a = cp.compose_page(payload, spec, TSEED, page=0, word_provider=prov)
    b = cp.compose_page(payload, spec, TSEED, page=0, word_provider=prov)
    assert np.array_equal(a.cell_values, b.cell_values), "compose not deterministic"
    assert int(a.pilot_mask.sum()) == 2 * 3 * 100
    got = cp.extract_payload(a.cell_values, spec, TSEED, 0)
    assert np.array_equal(got, payload), "payload bijection broken"
    # scramble convention == encodings kcell binary convention (contract step 2)
    ks = keystream(TSEED, "CMYK".index("K"), 0, spec.page_cells_yx)
    assert np.array_equal(
        ks, key_symbols(get_encoding("kcell-c3"), spec.page_cells_yx, TSEED, 0))
    # pilot cells carry the word bits at site raster order (cell level)
    pos = cp._site_positions_tile(spec.pilot, TSEED)
    for ty, tx in ((0, 0), (1, 2)):
        word = prov(ty, tx)
        cells = a.cell_values[ty * 60 + pos[:, 0], tx * 60 + pos[:, 1]]
        assert np.array_equal(cells, word), f"tile ({ty},{tx}) word mismatch"
    # dot expansion: whole known cells through the same constellation (3x3 solid)
    assert np.array_equal(
        a.plane_bits, np.kron(a.cell_values, np.ones((3, 3), np.uint8)))
    # wrong page -> different payload (keystream is page-keyed)
    assert not np.array_equal(
        cp.extract_payload(a.cell_values, spec, TSEED, 1), payload)


def test_full_page_payload_roundtrip_from_gt() -> None:
    gt = _gt_bits()
    spec = cp.ComposeSpec()
    assert gt.shape == spec.field_dots_yx and gt.dtype == np.uint8
    cells = gt[::3, ::3]
    # every cell must be a solid 3x3 block (same constellation as payload)
    assert np.array_equal(np.kron(cells, np.ones((3, 3), np.uint8)), gt)
    payload = rng(SEED, b"e011/payload").integers(
        0, 2, size=cp.payload_capacity(spec), dtype=np.uint8)
    got = cp.extract_payload(cells, spec, SEED, 0)
    assert np.array_equal(got, payload), "generated page payload not recovered"


# -- 4. gs render pixel-exact (the module's heart) -----------------------------

def test_gs_render_pixel_exact() -> None:
    img = _render_gray()
    mf = _manifest()
    e = _field_entry(mf)
    x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
    ink = (img[y:y + h, x:x + w] < 128).astype(np.uint8)
    gt = _gt_bits()
    assert ink.shape == gt.shape
    ndiff = int((ink != gt).sum())
    assert ndiff == 0, f"render != GT bitmap at {ndiff} dots"
    # archive-style page: NOTHING painted outside the field rect
    outside = img < 128
    outside[y:y + h, x:x + w] = False
    assert not outside.any(), f"{int(outside.sum())} ink px outside field rect"


def test_pilot_overlay_spotcheck_render() -> None:
    img = _render_gray()
    mf = _manifest()
    e = _field_entry(mf)
    spec = cp.ComposeSpec()
    pos = cp._site_positions_tile(spec.pilot, SEED)
    prov = _gen_provider(spec.pilot)
    p = spec.pilot.period_cells
    for ty, tx in ((0, 0), (36, 24), (18, 12)):   # corners + center tile
        word = prov(ty, tx)
        for s in range(0, 100, 17):
            cy = ty * p + int(pos[s, 0])
            cx = tx * p + int(pos[s, 1])
            block = img[e["y_dots"] + cy * 3: e["y_dots"] + cy * 3 + 3,
                        e["x_dots"] + cx * 3: e["x_dots"] + cx * 3 + 3]
            bits = (block < 128).astype(np.uint8)
            expect = np.full((3, 3), word[s], np.uint8)
            assert np.array_equal(bits, expect), \
                f"pilot ({ty},{tx}) site {s} at cell ({cy},{cx}): " \
                f"expected {word[s]}, got\n{bits}"


# -- 5. cal_core manifest compatibility ---------------------------------------

def test_cal_core_manifest_compat() -> None:
    _built()
    exp002 = str(ROOT / "experiments" / "002-calibration-page")
    if exp002 not in sys.path:
        sys.path.insert(0, exp002)
    import cal_core as cc  # noqa: E402  (exp-002 import idiom, test_msel1 style)
    mf = cc.load_manifest(BUILD / "e011_manifest.json")
    e = cc.entry(mf, "e011_field")
    assert e["_base_dir"] == str(BUILD.resolve())
    gt = cc.load_gt(e)
    assert gt is not None and gt.shape == (6660, 4500) and gt.dtype == np.uint8
    assert np.array_equal(gt, _gt_bits())
    assert e["params"]["cell_dots"] == 3


# -- 6. default word-provider path (real pilots.encode_word) -------------------

def test_default_word_provider_real_pilots() -> None:
    spec = cp.ComposeSpec(page_cells_yx=(60, 120))
    cap = cp.payload_capacity(spec)
    payload = rng(TSEED, b"payload-real").integers(0, 2, size=cap,
                                                   dtype=np.uint8)
    composed = cp.compose_page(payload, spec, TSEED, page=3)   # default provider
    pos = cp._site_positions_tile(spec.pilot, TSEED)
    for ty, tx in ((0, 0), (0, 1)):
        word = np.asarray(
            pilots.encode_word(spec.pilot, TSEED, "K", 3, ty, tx),
            dtype=np.uint8)
        got = composed.cell_values[ty * 60 + pos[:, 0], tx * 60 + pos[:, 1]]
        assert np.array_equal(got, word)
    assert np.array_equal(
        cp.extract_payload(composed.cell_values, spec, TSEED, 3), payload)


if __name__ == "__main__":
    for fn in (test_determinism_byte_identical,
               test_manifest_geometry_and_margins,
               test_spec_margin_validation_rejects,
               test_payload_capacity_formula,
               test_payload_bijection_fake_words,
               test_full_page_payload_roundtrip_from_gt,
               test_gs_render_pixel_exact,
               test_pilot_overlay_spotcheck_render,
               test_cal_core_manifest_compat,
               test_default_word_provider_real_pilots):
        fn()
        print(f"PASS {fn.__name__}")
