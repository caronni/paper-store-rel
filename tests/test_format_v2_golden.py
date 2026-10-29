"""layout_version 2 GOLDEN ANCHOR (finding [3], wave-3).

Every other v2 test is self-referential (two-fresh-runs determinism, manifest
re-hash, structural properties): a mutated derivation detail regenerates a
DIFFERENT format and the suite stays green — a silent fork of the frozen
layout (verified: transposing the site-offset draw shape sailed through
43/43 tests while e011.ps regenerated at a new sha). This file pins the
format axis to values computed from the code AS FROZEN on 2026-07-08.

FAILURE OF ANY TEST HERE MEANS THE PRINTED FORMAT CHANGED. That is never a
"fix the constant" situation: bump layout_version and add a new anchor —
NEVER edit these golden values.

Pins: (a) pilot site positions for the e011 seed (first 10 rows literal +
sha256 of the full array bytes); (b) one full encode_word codeword for a
fixed address; (c) the BCH generator polynomial bytes; (d) the e011 build
regenerated via subprocess against the frozen ps sha256.

Runs under pytest, or standalone: env/bin/python tests/test_format_v2_golden.py
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
EXP = ROOT / "experiments" / "011-pilot-roundtrip"
BUILD = EXP / "build"

# 2026-09-06: every test here reads a build that a test regenerates in place;
# test_e011.py writes the same directory.  One xdist worker per build directory
# (pyproject: --dist loadgroup).
pytestmark = pytest.mark.xdist_group("build-011")

from paperholo import bch, pilots  # noqa: E402

SEED = b"paper-store/exp011-pilot1"          # gen_e011.SEED (frozen)

# --- golden values, layout_version 2, frozen 2026-07-08 ----------------------
# site_positions_tile(PilotLayout(), SEED): (100, 2) int64 (y_cell, x_cell)
GOLD_SITES_FIRST10 = [
    [1, 5], [2, 7], [2, 17], [3, 22], [2, 27],
    [1, 35], [3, 41], [4, 43], [5, 50], [5, 56],
]
GOLD_SITES_SHA256 = \
    "56696eecd6b6b8a50f8124c6b285d54687f6667298dd04ea13b80e46ecdbc345"
# encode_word(PilotLayout(), SEED, "K", page=0, ptile_y=7, ptile_x=11):
# (100,) uint8 scrambled codeword
GOLD_WORD_K_P0_T7_11 = (
    "1010010100000100001100101001001010010111001001100010011001111010"
    "110000010010000111100111111111000100"
)
# bch.generator_poly(): (64,) uint8 coefficient vector of the degree-63 g(x)
GOLD_GPOLY_SHA256 = \
    "7daab8ec4a693d0052cf5e70729f6d2c64b98f9e6c09fb64231ef0c7c154d40b"
# build/e011.ps regenerated from SEED (gen_e011.py, no flags)
GOLD_E011_PS_SHA256 = \
    "742c0358543485c6aec193ae4d90b3ed8c8ae94caa879c3728f225ed6e9a58bc"


def test_golden_site_positions() -> None:
    pos = pilots.site_positions_tile(pilots.PilotLayout(), SEED)
    assert pos.shape == (100, 2)
    assert pos[:10].tolist() == GOLD_SITES_FIRST10, \
        "pilot site derivation changed — layout_version bump required"
    got = hashlib.sha256(np.ascontiguousarray(pos, np.int64)
                         .tobytes()).hexdigest()
    assert got == GOLD_SITES_SHA256, \
        (f"site_positions_tile bytes sha {got} != golden — the printed "
         f"format changed; bump layout_version, never edit the anchor")


def test_golden_encode_word() -> None:
    w = pilots.encode_word(pilots.PilotLayout(), SEED, "K", 0, 7, 11)
    got = "".join(str(int(b)) for b in np.asarray(w).ravel())
    assert got == GOLD_WORD_K_P0_T7_11, \
        ("encode_word output changed (keystream, BCH, packing or scramble) "
         "— layout_version bump required")


def test_golden_generator_poly() -> None:
    g = bch.generator_poly()
    assert g.shape == (64,) and g.dtype == np.uint8
    got = hashlib.sha256(g.tobytes()).hexdigest()
    assert got == GOLD_GPOLY_SHA256, \
        "BCH generator polynomial changed — layout_version bump required"


def test_golden_e011_build_sha() -> None:
    """Regenerate build/e011.ps and pin the frozen v2 sha: catches any
    derivation drift the unit anchors above do not reach (payload stream,
    compose overlay, emission bytes)."""
    r = subprocess.run([sys.executable, str(EXP / "gen_e011.py")],
                       capture_output=True, text=True, timeout=600,
                       cwd=str(EXP))
    assert r.returncode == 0, f"gen_e011.py failed:\n{r.stdout}\n{r.stderr}"
    ps_sha = hashlib.sha256((BUILD / "e011.ps").read_bytes()).hexdigest()
    mf = json.loads((BUILD / "e011_manifest.json").read_text())
    assert mf["ps_sha256"] == ps_sha, "manifest does not describe the build"
    assert ps_sha == GOLD_E011_PS_SHA256, \
        (f"e011.ps regenerated at sha {ps_sha} != frozen "
         f"{GOLD_E011_PS_SHA256} — the printed format changed; bump "
         f"layout_version, never edit the anchor")


if __name__ == "__main__":
    for fn in (test_golden_site_positions,
               test_golden_encode_word,
               test_golden_generator_poly,
               test_golden_e011_build_sha):
        fn()
        print(f"PASS {fn.__name__}")
