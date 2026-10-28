"""The measured-channel acceptance gate (ground rule G5: simulation
before toner).

The printed field goes through paperholo.channel.simulator — the measured
M281 model (development morphology, anisotropic PSF, mottle, print wander,
scanner y-steps, CCD comb) — and must decode blind through the production
receiver. paperholo here is a qualification-only import (HOLO-DESIGN §1).

Measured 2026-07-29 on this branch:
- c3 passes BYTE-EXACT with full geometry (49/49 tiles).
- c2 passes BYTE-EXACT at 8 px/cell with geometry off (92/100) — the
  sim's white-closure floor is survivable at the right footing.
- 2026-07-30 ROOT-CAUSE + FIX: the port had dropped legacy
  lattice_reciprocal's prior_f zoom-refit arm. On the closure-dominated
  c2 channel the x cell fundamental is ~8-10x weaker than y; the blind
  strongest-peak argmax locks texture/speckle decoys, the (correct)
  pitch/shear gate refuses, and refusal blocks every placement route.
  Re-porting the arm (retry around the region/declared prior, identical
  gates) moved the matrix: clean 4/8/16 px/cell = 98/91/89 (was
  25/92/39), geometry-ON 8 px = 71 VERIFIED (was 6), 16 px = 72 VERIFIED
  (was 7). Remaining documented residue: 4 px/cell geometry-on = 23
  (non-target footing; the record always called 2 px/dot marginal) and
  the survey's fixed 2048-px spectral cap still reads c_dots=None at
  16 px/cell (descriptor fallback covers placement).

2026-08-09 REGRESSION FIX (test axis; no production change). v0.42
(commit dcd2025) parked the whole lane tail behind the invocation-only
``--mopup``/``--refine`` flags: ``session_model._plan_bound`` stops a
flagless invocation BEFORE the first M entry, so this gate silently began
driving the ordinary ladder alone. dcd2025 taught the sibling slow-lane
acceptance test ``test_phased_roundtrip_e2e`` the new flags but not this
file. Green at dcd2025^, red at dcd2025, red ever since.

WHAT WAS LOST IS THE MOP-UP LEVELS, NOT REFINEMENT — measured 2026-08-09
at main 6c3f676, three flag arms per case (certificates; the c2 8 px arm
is unaffected because its close preempts at lane 0):

    case                     default   +mopup   +mopup+refine
    c2 full, geometry ON     0 (FAIL)  64 ok    64 ok
    c2 16 px, deferred       85        95       95

R(Lk) contributes ZERO certificates on this corpus, so ``--refine`` helps
only because the plan-prefix law makes it include the pending M-levels.
(This corrects RECEIVE-DESIGN v0.46 and CANARY-D5-DISAGREEMENTS §6, which
recorded the cause as "flagless gates lost inline refinement".) Note the
geometry-ON c2 collapse is total, not marginal: the ordinary ladder
certifies NOTHING there — every certificate on that page is mop-up.

``run_refine=True`` is the chosen bound: it is what the sibling e2e
adopted in this very commit and what every real-capture decode of record
uses (e029/e030: ``--complete --refine``), and it pins the R-lane path
for free while R yield is zero. ``run_mopup=True`` is the measured
minimal equivalent. The flags are invocation-only — absent from the
semantic policy and from every schema — so no printed-format or numeric
anchor moves with them.
"""
from __future__ import annotations

import hashlib
import os
import time
import warnings
from dataclasses import replace

import numpy as np
import pytest

from holo.format.descriptor import CODINGS, FormatSpec
from holo.gen.emit import emit_volume
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput

_SLOW = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the measured-channel gate",
)

_PAYLOAD = hashlib.sha256(b"measured-gate").digest() * 4

# Wall-budget tripwires on the decode alone (channel synthesis is
# excluded), NOT profiling — the doctrine instrument is
# `confetti.py decode --profile-timing`.  ~3x the 2026-07-30 measured
# walls; a breach means a search/scheduling mechanism regressed.


def _dots(tmp_path, coding_id: str) -> tuple[FormatSpec, np.ndarray]:
    spec = FormatSpec(CODINGS[coding_id], "measured-gate", (60.0, 60.0), 1.0)
    out = tmp_path / f"vol-{coding_id}"
    emit_volume(spec, _PAYLOAD, 0.5, out)
    gt = np.load(out / "page000_gt.npy")
    return spec, np.unpackbits(gt, axis=1, bitorder="big").astype(np.uint8)


def _decode(tmp_path, spec, dots, *, oversample: int, geometry: bool,
            defer: bool = False):
    from paperholo.channel import simulator  # qualification-only import

    scanner = replace(simulator.M281_SCANNER, oversample=oversample)
    scan = simulator.print_scan(dots, simulator.ChannelParams(
        scanner=scanner, seed=7, geometry=geometry))
    img = np.clip(scan * 255, 0, 255).astype(np.uint8)
    # A real platen always surrounds the sheet; edge-to-edge texture makes
    # the survey's field/background threshold meaningless (measured: the
    # marginless field shattered into 36-48 survey regions).
    m = oversample * 120
    canvas = np.full(
        (img.shape[0] + 2 * m, img.shape[1] + 2 * m), 245, np.uint8)
    canvas[m:m + img.shape[0], m:m + img.shape[1]] = img
    request = ReceiveRequest(
        spec,
        (CaptureInput(canvas, 600.0 * oversample),),
        state_path=tmp_path / f"gate-{oversample}-{int(geometry)}.json",
        page_hypotheses=(0,),
        defer_fountain_close=defer,
        # v0.42: drive the whole plan — ordinary ladder, M-levels, R(Lk)
        # refinement.  Every arm of this gate uses the same bound, so the
        # 8 px vs 16 px comparison below stays like-for-like.
        run_refine=True,
    )
    started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("always", ProvisionalReceiverWarning)
        result = run_receive(request, pipeline=production_pipeline(request))
    return result, time.perf_counter() - started


def _assert_wall_budget(wall_s: float, budget_s: float, label: str) -> None:
    assert wall_s <= budget_s, (
        f"{label}: decode took {wall_s:.1f}s, budget {budget_s:.0f}s — a "
        "scheduling/search mechanism regressed; profile with "
        "`confetti.py decode --profile-timing`")


@_SLOW
def test_c3_full_measured_channel_byte_exact(tmp_path) -> None:
    spec, dots = _dots(tmp_path, "c3-r0550")
    result, wall_s = _decode(tmp_path, spec, dots, oversample=2, geometry=True)
    assert result.verified
    assert result.payload == _PAYLOAD
    assert len(result.state.certificates) == spec.tiles_per_page
    _assert_wall_budget(wall_s, 240.0, "c3 full measured channel")


@_SLOW
def test_c2_clean_channel_byte_exact_at_8px(tmp_path) -> None:
    """The development floor alone is survivable at c2's measured footing."""
    spec, dots = _dots(tmp_path, "c2-r0550")
    result, wall_s = _decode(tmp_path, spec, dots, oversample=4,
                             geometry=False)
    assert result.verified
    assert result.payload == _PAYLOAD
    assert len(result.state.certificates) >= 90
    _assert_wall_budget(wall_s, 240.0, "c2 clean 8px")


@_SLOW
def test_c2_clean_16px_does_not_lose_certificates(tmp_path) -> None:
    """More resolution must never certify fewer tiles than less.

    defer_fountain_close so every lane contributes before the count —
    the ordinary verified-recovery stop ends the run at lane 0
    (adjudicated 2026-07-30: 89 certificates was lane 0 alone).
    """
    spec, dots = _dots(tmp_path, "c2-r0550")
    result, wall_s = _decode(tmp_path, spec, dots, oversample=8,
                             geometry=False, defer=True)
    assert result.verified
    assert len(result.state.certificates) >= 90
    _assert_wall_budget(wall_s, 420.0, "c2 clean 16px deferred")


@_SLOW
def test_c2_full_measured_channel_verifies(tmp_path) -> None:
    """c2 through the complete measured channel at its qualified footing."""
    spec, dots = _dots(tmp_path, "c2-r0550")
    result, wall_s = _decode(tmp_path, spec, dots, oversample=4,
                             geometry=True)
    assert result.verified
    assert result.payload == _PAYLOAD
    assert len(result.state.certificates) >= 60
    _assert_wall_budget(wall_s, 240.0, "c2 full measured channel")
