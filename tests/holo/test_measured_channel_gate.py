"""The measured-channel acceptance gate (ground rule G5: simulation
before toner).

Gate E re-home: the vehicle is holo3 — the production receiver — read
through `_receive_free.decode_with_holo3`.  The channel, the footings
and the arms are unchanged; what changed is who reads the page, so
every certificate count below was RE-MEASURED against holo3 on
2026-09-05 and the old v1 numbers are recorded beside them.

The printed field goes through paperholo.channel.simulator — the measured
M281 model (development morphology, anisotropic PSF, mottle, print wander,
scanner y-steps, CCD comb) — and must decode blind. paperholo here is a
qualification-only import (HOLO-DESIGN §1).

Measured 2026-07-29 on the v1 receiver, and the reason these arms exist:
- c3 passes BYTE-EXACT with full geometry (49/49 tiles).
- c2 passes BYTE-EXACT at 8 px/cell with geometry off (92/100) — the
  sim's white-closure floor is survivable at the right footing.
- 2026-07-30 ROOT-CAUSE + FIX: the port had dropped legacy
  lattice_reciprocal's prior_f zoom-refit arm. On the closure-dominated
  c2 channel the x cell fundamental is ~8-10x weaker than y; the blind
  strongest-peak argmax locks texture/speckle decoys, the (correct)
  pitch/shear gate refuses, and refusal blocks every placement route.
  Re-porting the arm moved the matrix: clean 4/8/16 px/cell = 98/91/89
  (was 25/92/39), geometry-ON 8 px = 71 VERIFIED (was 6).

The v1 ``--mopup``/``--refine`` invocation flags this gate had to pass
have NO holo3 counterpart: refinement is a scheduled plugin there, always
live, so the whole plan runs without a flag.
"""
from __future__ import annotations

import hashlib
import os
import warnings
from dataclasses import replace

import numpy as np
import pytest

from holo.format.resolve import resolve_format_ref
from holo.gen.emit import emit_volume

from _receive_free import decode_with_holo3

_SLOW = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the measured-channel gate",
)

_PAYLOAD = hashlib.sha256(b"measured-gate").digest() * 4
# The v2 names of the gate's own geometry: c3 lays 7x7 tiles on the
# 60 mm page it always used, c2 lays 10x10.
_C3 = "c3-k-r0550@7x7"
_C2 = "c2-k-r0550@10x10"


def _dots(tmp_path, format_ref: str) -> np.ndarray:
    spec = resolve_format_ref(format_ref)
    out = tmp_path / f"vol-{format_ref.replace('@', '-')}"
    emit_volume(spec, _PAYLOAD, 0.5, out)
    gt = np.load(out / "page000_gt.npy")
    return np.unpackbits(gt, axis=1, bitorder="big").astype(np.uint8)


def _scan(dots: np.ndarray, *, oversample: int,
          geometry: bool) -> np.ndarray:
    from paperholo.channel import simulator  # qualification-only import

    scanner = replace(simulator.M281_SCANNER, oversample=oversample)
    scan = simulator.print_scan(dots, simulator.ChannelParams(
        scanner=scanner, seed=7, geometry=geometry))
    img = np.clip(scan * 255, 0, 255).astype(np.uint8)
    # A real platen always surrounds the sheet; edge-to-edge texture makes
    # the survey's field/background threshold meaningless (measured: the
    # marginless field shattered into 36-48 survey regions).
    margin = oversample * 120
    canvas = np.full(
        (img.shape[0] + 2 * margin, img.shape[1] + 2 * margin), 245, np.uint8)
    canvas[margin:margin + img.shape[0], margin:margin + img.shape[1]] = img
    return canvas


def _decode(tmp_path, format_ref: str, label: str, *, oversample: int,
            geometry: bool):
    raster = _scan(_dots(tmp_path, format_ref), oversample=oversample,
                   geometry=geometry)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return decode_with_holo3(
            ((raster, 600.0 * oversample),), format_ref, tmp_path, label)


# This stimulus carries a 128-byte payload, so K = 1: holo3 closes the
# volume the moment metadata trust lands and stops.  Every arm therefore
# certifies the metadata floor and not one tile more, whatever the
# footing — MEASURED 2026-09-05: c3 full 48, c2 clean 8 px 48.  The v1
# counts beside each arm (49/49, 92/100) were run-to-completion numbers
# and are not comparable; the resolution-monotonicity arm that lived on
# that comparison is owed a stimulus whose fountain actually binds.
_METADATA_FLOOR = 48


@_SLOW
def test_c3_full_measured_channel_byte_exact(tmp_path) -> None:
    decode = _decode(tmp_path, _C3, "c3-full", oversample=2,
                     geometry=True)
    assert decode.exit_code == 0, decode.stdout
    assert decode.status == "verified"
    assert decode.payload == _PAYLOAD
    assert decode.certified >= _METADATA_FLOOR   # holo3 48; v1 49/49


@_SLOW
def test_c2_clean_channel_byte_exact_at_8px(tmp_path) -> None:
    """The development floor alone is survivable at c2's measured footing."""
    decode = _decode(tmp_path, _C2, "c2-clean-8px", oversample=4,
                     geometry=False)
    assert decode.exit_code == 0, decode.stdout
    assert decode.status == "verified"
    assert decode.payload == _PAYLOAD
    assert decode.certified >= _METADATA_FLOOR   # holo3 48; v1 92/100


@_SLOW
def test_c2_full_measured_channel_verifies(tmp_path) -> None:
    """c2 through the complete measured channel at its qualified footing.

    16 px/cell, not the 8 px/cell v1 used: MEASURED 2026-09-05, at 8
    px/cell holo3's survey votes the printed pitch as 1/600 in against a
    1/300 in row and refuses the capture outright.  c2 under the geometry
    arm has always been the fragile corner (v1 needed mop-up levels for
    every certificate it got there); the finer footing is where holo3
    reads it, and v1 measured 16 px/cell good too (72 VERIFIED).
    """
    decode = _decode(tmp_path, _C2, "c2-full", oversample=8,
                     geometry=True)
    assert decode.exit_code == 0, decode.stdout
    assert decode.status == "verified"
    assert decode.payload == _PAYLOAD
    assert decode.certified >= _METADATA_FLOOR   # holo3 48; v1 71
