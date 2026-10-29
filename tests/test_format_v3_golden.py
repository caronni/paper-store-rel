"""layout_version 3 GOLDEN ANCHOR (p60b6.v3-k18, frozen 2026-07-08).

Same doctrine as tests/test_format_v2_golden.py: every other v3 test is
self-referential (two-fresh-runs determinism, structural properties), so a
mutated derivation detail regenerates a DIFFERENT format and the suite stays
green — a silent fork of the frozen layout. This file pins the v3 format axis
to values computed from the code AS FROZEN on 2026-07-08.

FAILURE OF ANY TEST HERE MEANS THE PRINTED FORMAT CHANGED. That is never a
"fix the constant" situation: bump layout_version and add a new anchor —
NEVER edit these golden values.

Pins: (a) pilot site positions for the e012 seed (v3 deliberately SHARES the
b"pilot-sites-v2" site derivation — a v3-specific site label would itself be
a format fork); (b) one full v3 encode_word codeword for a fixed
(seed, plane, counter); (c) the BCH(127,50,t=13) generator polynomial bytes
(degree 77); (d) the e012 build regenerated via subprocess against the frozen
ps sha256.

Runs under pytest, or standalone: env/bin/python tests/test_format_v3_golden.py
"""
from __future__ import annotations

import hashlib
import pytest
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EXP = ROOT / "experiments" / "012-pilot-print"
BUILD = EXP / "build"

# 2026-09-06: every test here reads a build that a test regenerates in place;
# test_e012.py writes the same directory.  One xdist worker per build directory
# (pyproject: --dist loadgroup).
pytestmark = pytest.mark.xdist_group("build-012")

from paperholo import bch, pilots  # noqa: E402

SEED = b"paper-store/exp012-pilot1"          # gen_e012.SEED (frozen)
LAYOUT3 = pilots.PilotLayout(version=3)
GEO = {"tiles_x": 25, "tiles_per_page": 925}  # e012 page: 37x25 tiles

# --- golden values, layout_version 3, frozen 2026-07-08 ----------------------
# site_positions_tile(PilotLayout(version=3), SEED): (100, 2) int64 (y, x) —
# the SHARED v2 site derivation evaluated at the e012 seed
GOLD_SITES_FIRST10 = [
    [3, 4], [1, 8], [3, 13], [4, 20], [0, 29],
    [5, 35], [3, 41], [5, 42], [1, 48], [0, 59],
]
GOLD_SITES_SHA256 = \
    "fb339840fd1493bfea7dd042affaefe65ab6fec023b1c1e0ceb5430f03ea9e09"
# encode_word(LAYOUT3, SEED, "K", page=0, ptile_y=7, ptile_x=11,
#             tiles_x=25, tiles_per_page=925): counter = 7*25 + 11 = 186,
# (100,) uint8 scrambled codeword
GOLD_WORD_K_C186 = (
    "0110001011001100010100110011111000111000011011001100000100100100"
    "001010000100110110111011010000100111"
)
# bch.CODE_V3.generator_poly(): (78,) uint8 coefficient vector, degree 77
GOLD_GPOLY_V3_SHA256 = \
    "a0be5064cfef57b2a84aaadbd7bd13b9772b1259fa041c25af0d7bde4922b684"
# build/e012.ps regenerated from SEED (gen_e012.py)
GOLD_E012_PS_SHA256 = \
    "8fcd89dd2a646b2c1d3adf092ca3f967d030f4d35d03e537bb943a14412540a1"


def test_golden_site_positions_v3() -> None:
    pos = pilots.site_positions_tile(LAYOUT3, SEED)
    assert pos.shape == (100, 2)
    assert pos[:10].tolist() == GOLD_SITES_FIRST10, \
        "pilot site derivation changed — layout_version bump required"
    got = hashlib.sha256(np.ascontiguousarray(pos, np.int64)
                         .tobytes()).hexdigest()
    assert got == GOLD_SITES_SHA256, \
        (f"site_positions_tile bytes sha {got} != golden — the printed "
         f"format changed; bump layout_version, never edit the anchor")
    # the site layer is SHARED with v2 by contract: same seed, same positions
    assert np.array_equal(pos, pilots.site_positions_tile(
        pilots.PilotLayout(), SEED)), \
        "v3 site derivation diverged from the shared v2 derivation"


def test_golden_encode_word_v3() -> None:
    w = pilots.encode_word(LAYOUT3, SEED, "K", 0, 7, 11, **GEO)
    got = "".join(str(int(b)) for b in np.asarray(w).ravel())
    assert got == GOLD_WORD_K_C186, \
        ("v3 encode_word output changed (keystream, BCH, counter packing or "
         "scramble) — layout_version bump required")
    # and the counter geometry inverts it back
    info = pilots.decode_word(w, LAYOUT3, SEED, "K", 13, **GEO)
    assert info is not None and info["counter"] == 186
    assert (info["page"], info["ptile_y"], info["ptile_x"]) == (0, 7, 11)


def test_golden_generator_poly_v3() -> None:
    g = bch.CODE_V3.generator_poly()
    assert g.shape == (78,) and g.dtype == np.uint8
    assert g[77] == 1 and g[0] == 1, "g must have degree exactly 77, g(0) != 0"
    got = hashlib.sha256(g.tobytes()).hexdigest()
    assert got == GOLD_GPOLY_V3_SHA256, \
        "BCH(127,50) generator polynomial changed — layout_version bump required"


def test_golden_e012_build_sha() -> None:
    """Regenerate build/e012.ps and pin the frozen v3 sha: catches any
    derivation drift the unit anchors above do not reach (payload stream,
    compose overlay, emission bytes)."""
    r = subprocess.run([sys.executable, str(EXP / "gen_e012.py")],
                       capture_output=True, text=True, timeout=600,
                       cwd=str(EXP))
    assert r.returncode == 0, f"gen_e012.py failed:\n{r.stdout}\n{r.stderr}"
    ps_sha = hashlib.sha256((BUILD / "e012.ps").read_bytes()).hexdigest()
    mf = json.loads((BUILD / "e012_manifest.json").read_text())
    assert mf["ps_sha256"] == ps_sha, "manifest does not describe the build"
    assert ps_sha == GOLD_E012_PS_SHA256, \
        (f"e012.ps regenerated at sha {ps_sha} != frozen "
         f"{GOLD_E012_PS_SHA256} — the printed format changed; bump "
         f"layout_version, never edit the anchor")


if __name__ == "__main__":
    for fn in (test_golden_site_positions_v3,
               test_golden_encode_word_v3,
               test_golden_generator_poly_v3,
               test_golden_e012_build_sha):
        fn()
        print(f"PASS {fn.__name__}")
