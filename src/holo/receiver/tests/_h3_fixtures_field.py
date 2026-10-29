"""The PAGE-FIELD fixtures: the displaced page, its platen, its decodes.

Split out of ``conftest`` at the 1000-line seam (W6).  Every fixture
here belongs to ``docs/PAGE-FIELD-DESIGN.md`` B1 and B7 — the clean
colour emit with Y two dots out of register, the confetti platen that
mixes all four quarter turns, and the four decodes
``test_h3_e2e_field_frame`` compares — plus the two scheduling hold-out
row sets the field arms are measured against, which the yield module's
own fixtures in ``conftest`` also read.

``conftest`` imports these names, and an imported fixture function is a
registered fixture: the names a test asks for are unchanged.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from holo.receiver.tests import _h3_sims, _h3_sims_field, _h3_support
from holo.receiver.tests._h3_fixture_build import (
    _WORK_LOCK,
    DecodeRecord,
    _decode_once,
    _materialise,
    _sim_gate,
)


# `tiles.swim` is HELD OUT of the three field-yield decodes, and the
# same row set is used in all three so the arms differ only in the dial
# and the capture.  Its blind translation bound is one printed CELL —
# 3.000 dots on this c3 page, which is exactly the peak the pair
# injects — so with the field off the row undoes the whole stimulus by
# itself (measured 2026-08-31: 300/300, seven certificates minted by the
# row) and the field has nothing left to buy back.  Every OTHER rescue
# row stays live and keeps working the page.  The ruling, the four
# directions that were measured and failed instead, and the condition
# that expires the hold-out are in the receiver's
# docs/WIDENED-MATRIX-RETIREMENT-2026-09-20.md, which retired that
# module and carries its ledger.
FIELD_YIELD_HELD_OUT = ("tiles.swim",)

#: The arm the dial's retirement took away, rebuilt as a scheduling
#: hold-out — the instrument this module already uses for `tiles.swim`.
#: The field is always on for a colour family (design §2.8), so the only
#: way left to ask what it is worth is to drop its two rows and decode
#: the same capture with the same argv: same stimulus, same hold-out,
#: one variable.
FIELD_ROWS_HELD_OUT = FIELD_YIELD_HELD_OUT + ("fields.collect", "fields")


# The FRAME lane: the clean colour page with Y two dots out of register,
# read at rot 0, at rot 2, off a confetti platen mixing all four
# rotations, and once with the field's own rows dropped.  Measured
# 2026-09-08 at workers 8 under `--complete`: 41.9 + 43.7 + 36.9 + 38.5
# = 161 s of decode, more than the whole slow lane's documented wall —
# so the four sit in the widened matrix, whole, rather than one of them
# in the lane and three out of it.  A sweeps run sets the slow flag too,
# so it is the same lane as far as the gates go; what it buys is a lane
# nobody runs by accident.  (The session tripwire that once turned that
# overrun into a red run was retired 2026-09-20; the measured walls are
# CLAUDE.md's.)  The reasoning is in test_h3_e2e_field_frame.py's
# docstring.
#
# WORKERS 8, where the frame module's siblings run serial: the four
# compare CERTIFICATE SETS and page fields, and `--complete` harvests
# the whole domain, so the set is worker-independent by construction
# (measured: all four reach 300/300 and their signatures are equal).
# Serial would cost about four times the wall for the same facts.
FIELD_FRAME_LANE = "the page-field frame proofs"


@pytest.fixture(scope="session")
def sim_color_shifted(sim_root: Path) -> _h3_sims.SimCapture:
    _sim_gate("the displaced clean colour sim capture")
    with _WORK_LOCK:
        outdir = _materialise("color-shifted",
                              _h3_sims_field.make_color_shifted,
                              _h3_sims_field.EXPECTED_COLOR_SHIFTED,
                              sim_root)
    return _h3_sims_field.capture_color_shifted(outdir)


@pytest.fixture(scope="session")
def sim_color_shifted_rot2(sim_color_shifted: _h3_sims.SimCapture,
                           sim_root: Path) -> _h3_sims.SimCapture:
    with _WORK_LOCK:
        return _h3_sims.rotated_capture(sim_color_shifted, 2,
                                        sim_root / "rot")


@pytest.fixture(scope="session")
def sim_color_confetti(sim_color_shifted: _h3_sims.SimCapture,
                       sim_root: Path) -> _h3_sims.SimCapture:
    with _WORK_LOCK:
        outdir = _materialise(
            "color-confetti",
            lambda staging: _h3_sims_field.make_color_confetti(
                sim_color_shifted.tiff, staging),
            _h3_sims_field.EXPECTED_CONFETTI, sim_root)
    return _h3_sims_field.capture_color_confetti(outdir,
                                                 sim_color_shifted)


@pytest.fixture(scope="session")
def decode_color_shifted(sim_color_shifted: _h3_sims.SimCapture,
                         decode_root: Path) -> DecodeRecord:
    _h3_support.skip_unless_oracle_sweeps(FIELD_FRAME_LANE)
    # keep_planes: the analyzer's S-tier record is this same decode and
    # opens its planes (analyzer/tests/_analyzer_fixtures.py); asking for
    # them here too keeps the two lanes on one cache entry.
    return _decode_once("color-shifted", sim_color_shifted, decode_root,
                        workers=8,
                        extra_argv=("--complete", "--max-pages", "1"),
                        keep_planes=True)


@pytest.fixture(scope="session")
def decode_color_shifted_unfielded(sim_color_shifted: _h3_sims.SimCapture,
                                   decode_root: Path) -> DecodeRecord:
    _h3_support.skip_unless_oracle_sweeps(FIELD_FRAME_LANE)
    return _decode_once("color-shifted-unfielded", sim_color_shifted,
                        decode_root, workers=8,
                        extra_argv=("--complete", "--max-pages", "1"),
                        drop_rows=FIELD_ROWS_HELD_OUT)


@pytest.fixture(scope="session")
def decode_color_shifted_rot2(sim_color_shifted_rot2: _h3_sims.SimCapture,
                              decode_root: Path) -> DecodeRecord:
    _h3_support.skip_unless_oracle_sweeps(FIELD_FRAME_LANE)
    return _decode_once("color-shifted-rot2", sim_color_shifted_rot2,
                        decode_root, workers=8,
                        extra_argv=("--complete", "--max-pages", "1"))


@pytest.fixture(scope="session")
def decode_color_confetti(sim_color_confetti: _h3_sims.SimCapture,
                          decode_root: Path) -> DecodeRecord:
    _h3_support.skip_unless_oracle_sweeps(FIELD_FRAME_LANE)
    return _decode_once("color-confetti", sim_color_confetti, decode_root,
                        workers=8,
                        extra_argv=("--complete", "--max-pages", "1"))
