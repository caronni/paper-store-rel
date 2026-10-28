#!/usr/bin/env python
"""Bit-equivalence of the pose refinement's two arms — RUN BY PATH.

    env/bin/python holo2/measure/refine_equivalence.py [--force-dead-switch]

``--force-dead-switch`` aliases the batched arm onto the scalar one and
exits immediately off :func:`verify_arms_are_distinct` — proof the arm-
liveness check bites, at none of the decode cost (see that function's
docstring for what it guards against).

NOT A TEST and not collectable as one: no ``test_`` name, no pytest
fixtures, a ``__main__`` entry point, and it lives outside ``testpaths``
twice over.  The user's ruling on this file, verbatim: *"keep the old one
around, maybe you also want to use it for equivalency testing — but not
as a standard test, mind you."*

WHAT IT PROVES.  ``PlacementConfig.batched_refine`` chooses between two
implementations of E022's 7x9x9 pose grid —
``pose_audit._scalar_refine_scan`` (567 interpolations, THE ORACLE) and
``pose_audit._batched_refine_scan`` (one).  Every claim the twin makes is
that the two arms are the SAME ARITHMETIC, not a close one, so the bar
here is bit-identity and nothing weaker: no ``allclose``, no tolerance,
no epsilon.  A single differing bit is a finding, not a rounding.

HOW.  It does not synthesise refinement calls; it INTERCEPTS the real
ones.  ``pose_audit.refine_patch_pose`` is wrapped so that each call the
receiver makes runs BOTH arms on the identical inputs, compares them, and
returns the ORACLE's answer — so the decode itself proceeds entirely on
the old path and the twin never influences the population it is measured
on.  The two private scans are wrapped too, which is how the SELECTION
score (the margin, which the emitted outcome does not carry) is compared
as well as the winner.  Three things are checked per call:

* **winner identity** — the chosen ``(delta_angle, delta_y, delta_x)``,
  which is where a tie-break or a NaN rule would diverge first;
* **the scores** — the winning margin and both held-out mismatches, as
  raw ``float`` equality;
* **the emitted outcome** — the whole re-sampled ``SegmentSample``, array
  for array, dtype and shape included, plus the refined pose's floats.
  This is the one that matters downstream: it is what the audit, the
  emission block and every committed pose are a function of.

THE POPULATION is real decodes over rendered fixtures (``verdicts/
_fixtures.py``'s own builders, which emit through the real ``src/holo``
generator), across six arms chosen to move the site geometry the
refinement sees: a clean page, the measured e032 channel warp, a banded
page whose right quarter kills the word code, a capture rotated by a
quarter turn so ``rot_k != 0`` re-orders the correspondence set itself, a
damaged ring that drives the corner-retry windows, and a wider page that
simply lays more windows down.  All perturbation is seeded; there is no
unseeded RNG anywhere in it.
"""
from __future__ import annotations

import sys
import tempfile
import time
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

# Self-locating, like ``./confetti.py``: neither package is pip-installed
# (env honesty), and a driver the operator runs BY PATH should not also
# demand a ``PYTHONPATH=`` prefix to find the tree it lives in.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE / "verdicts", _ROOT / "src", _ROOT / "holo2" / "src"):
    sys.path.insert(0, str(_path))

from _fixtures import (CHANNEL_ROTATION_DEG, CHANNEL_SCALE_YX,  # noqa: E402
                       build_page, render)

from holo2 import cli  # noqa: E402
from holo2.cli import real_providers  # noqa: E402
from holo2.solve import pose_audit  # noqa: E402

PX_PER_DOT = 2


# ------------------------------------------------------- the bit comparison

def _differences(left: Any, right: Any, path: str) -> list[str]:
    """Every place two values differ, to the bit. Never a tolerance."""
    if left is None or right is None:
        if left is None and right is None:
            return []
        return [f"{path}: one arm returned None ({left!r} vs {right!r})"]
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        left_array, right_array = np.asarray(left), np.asarray(right)
        if left_array.dtype != right_array.dtype:
            return [f"{path}.dtype: {left_array.dtype} vs {right_array.dtype}"]
        if left_array.shape != right_array.shape:
            return [f"{path}.shape: {left_array.shape} vs {right_array.shape}"]
        # ``equal_nan`` is only meaningful (and only accepted) for floats.
        floating = left_array.dtype.kind == "f"
        if np.array_equal(left_array, right_array, equal_nan=floating):
            return []
        unequal = left_array.ravel() != right_array.ravel()
        if floating:
            unequal &= ~(np.isnan(left_array.ravel())
                         & np.isnan(right_array.ravel()))
        where = np.flatnonzero(unequal)
        return [f"{path}: {where.size} of {left_array.size} elements differ; "
                f"first at flat {int(where[0]) if where.size else -1}"]
    if is_dataclass(left) and not isinstance(left, type):
        rows: list[str] = []
        for field in fields(left):
            rows += _differences(getattr(left, field.name),
                                 getattr(right, field.name),
                                 f"{path}.{field.name}")
        return rows
    if isinstance(left, (tuple, list)):
        if len(left) != len(right):
            return [f"{path}: length {len(left)} vs {len(right)}"]
        rows = []
        for index, (one, other) in enumerate(zip(left, right)):
            rows += _differences(one, other, f"{path}[{index}]")
        return rows
    if isinstance(left, float) and isinstance(right, float):
        if left != right and not (left != left and right != right):
            return [f"{path}: {left!r} vs {right!r} "
                    f"(ulps apart: {left.hex()} vs {right.hex()})"]
        return []
    if left != right:
        return [f"{path}: {left!r} vs {right!r}"]
    return []


class Ledger:
    """What the run saw: calls, refusals, and any divergence at all."""

    def __init__(self) -> None:
        self.calls = 0
        self.emitted = 0
        self.refused_both = 0
        self.sites: list[int] = []
        self.divergences: list[str] = []

    def record(self, oracle: Any, twin: Any, scans: list[Any],
               n_sites: int) -> None:
        self.calls += 1
        if oracle is None and twin is None:
            self.refused_both += 1
        elif oracle is not None and twin is not None:
            self.emitted += 1
        rows = _differences(oracle, twin, "outcome")
        if len(scans) == 2:
            self.sites.append(n_sites)
            rows += _differences(scans[0], scans[1], "best")
        elif scans:
            rows.append(f"arms took different paths: {len(scans)} scans ran")
        self.divergences += rows

    def report(self) -> str:
        span = (f"{min(self.sites)}-{max(self.sites)}"
                if self.sites else "n/a")
        return (f"{self.calls} refine calls: {len(self.sites)} grid scans "
                f"compared (winner + margin + held-out), {self.emitted} "
                f"emitted outcomes compared array-for-array, "
                f"{self.refused_both} refused by both arms; "
                f"reference sites per scan {span}; "
                f"{len(self.divergences)} divergences")


# ------------------------------------------------------------ the intercept

#: Row counts the FIRST call of each arm re-runs its own window under.
#: A window that reaches refinement at all is a full 200-cell one, so the
#: decode population alone clusters near N ~ 950 sites; cropping the
#: sample's mask to a band of rows is the same real pixels, real pose and
#: real correspondence set over a SMALLER one, which is what a clipped
#: edge window is.  It matters because the only place a batched reduction
#: could ever part company with a per-row one is length: numpy's pairwise
#: float64 sum blocks at 128 and its cast buffer at 8192, and this sweep
#: walks the compared population across the first of those boundaries
#: instead of asserting past it.
MASK_CROP_ROWS = (14, 16, 20, 26, 30, 40, 55, 70, 90, 110, 140, 170)


def crop_patch(patch: Any, rows: int) -> Any:
    """The same window, its sampled mask cut to its first ``rows`` rows."""
    mask = np.asarray(patch.sample.mask, bool).copy()
    mask[rows:, :] = False
    if not mask.any():
        return None
    return type(patch)(replace(patch.sample, mask=mask), patch.mask & mask)


def verify_arms_are_distinct(scalar_scan: Any, batched_scan: Any) -> None:
    """The bch harness's dead-intercepted-population lesson, the other way.

    ``force_oracle_arm`` (``bch_equivalence.py``) forces a switch OPEN and
    then VERIFIES the force took, because that harness's population goes
    empty if it does not. This harness has no such switch to force — every
    :func:`compare` call already pins both arms explicitly via
    ``replace(config, batched_refine=...)`` — so what has to be verified
    instead is that the two pinned arms are not secretly the SAME
    function. If they ever were (an aliasing refactor, or
    ``refine_patch_pose``'s own dispatch collapsing onto one arm), every
    comparison below would run one implementation against itself and
    report BIT-IDENTICAL forever — the same shape as the bch harness
    going quietly dead (measure/README: "the intercepted population had
    been DEAD since `batched_word_sweep` was flipped ON"), just silent
    instead of empty. ``--force-dead-switch`` recreates that condition on
    purpose so this assertion can be shown to bite.
    """
    if scalar_scan is batched_scan:
        raise SystemExit(
            "ARM LIVENESS: _scalar_refine_scan and _batched_refine_scan "
            "are the SAME object — the twin has collapsed onto the "
            "oracle, and every comparison below would silently compare "
            "an arm against itself.")


def install(ledger: Ledger, *, force_dead_switch: bool = False) -> None:
    """Make every refine call run both arms and compare them.

    ``force_dead_switch`` aliases the batched arm onto the scalar one
    before the liveness check runs, so a caller can prove the check
    bites without paying for a real decode.
    """
    oracle_refine = pose_audit.refine_patch_pose
    scalar_scan = pose_audit._scalar_refine_scan
    batched_scan = (scalar_scan if force_dead_switch
                    else pose_audit._batched_refine_scan)
    verify_arms_are_distinct(scalar_scan, batched_scan)
    scans: list[Any] = []
    sites: list[int] = []
    swept: set[int] = set()

    def record_scalar(config: Any, evaluate: Any) -> Any:
        best = scalar_scan(config, evaluate)
        scans.append(best)
        return best

    def record_batched(context: Any, pose: Any, points: Any,
                       *rest: Any) -> Any:
        best = batched_scan(context, pose, points, *rest)
        scans.append(best)
        sites.append(int(points.shape[0]))
        return best

    def compare(context: Any, patch: Any, provider: Any, page: int,
                origin_yx: Any, rot_k: int, config: Any, resample: Any) -> Any:
        scans.clear()
        sites.clear()
        oracle = oracle_refine(
            context, patch, provider, page, origin_yx, rot_k,
            replace(config, batched_refine=False), resample=resample)
        twin = oracle_refine(
            context, patch, provider, page, origin_yx, rot_k,
            replace(config, batched_refine=True), resample=resample)
        ledger.record(oracle, twin, list(scans), sites[0] if sites else 0)
        return oracle

    def both_arms(context: Any, patch: Any, provider: Any, page: int,
                  origin_yx: Any, rot_k: int, config: Any,
                  *, resample: Any) -> Any:
        oracle = compare(context, patch, provider, page, origin_yx, rot_k,
                         config, resample)
        # Once per capture, walk the same window down the site-count
        # ladder (see MASK_CROP_ROWS).  Guarded by ``id(context)`` so it
        # is one sweep per prepared region, not one per placed window.
        if id(context) not in swept:
            swept.add(id(context))
            for rows in MASK_CROP_ROWS:
                cropped = crop_patch(patch, rows)
                if cropped is not None:
                    compare(context, cropped, provider, page, origin_yx,
                            rot_k, config, resample)
        # The decode proceeds on the ORACLE, always: the twin must never
        # influence the population it is being measured on.
        return oracle

    pose_audit._scalar_refine_scan = record_scalar
    pose_audit._batched_refine_scan = record_batched
    pose_audit.refine_patch_pose = both_arms


# ---------------------------------------------------------------- the arms

def quarter_turn(source: Path, target: Path) -> Path:
    """The same capture on its side — the ``rot_k != 0`` correspondence set."""
    with Image.open(source) as image:
        Image.fromarray(np.rot90(np.asarray(image))).save(target)
    return target


def arms(work: Path) -> list[tuple[str, Any, tuple[tuple[Path, float], ...]]]:
    """Six decodes whose refinement geometry differs on purpose.

    The last two exist for the SITE COUNT, not for the channel: a damaged
    ring drives the corner-retry windows, and a wider page lays more
    windows down, so the compared population spans small and large ``N``
    rather than clustering on one window size.
    """
    clean = build_page("c3-k-r0550@8x8")
    channel = build_page("c2-k-r0700@8x8")
    wide = build_page("c3-k-r0550@12x12")
    clean_capture = render(clean.dots, work / "clean.png",
                           px_per_dot=PX_PER_DOT, cell_dots=clean.cell_dots,
                           noise_sigma=1.0)
    channel_capture = render(
        channel.dots, work / "channel.png", px_per_dot=PX_PER_DOT,
        cell_dots=channel.cell_dots, rotation_deg=CHANNEL_ROTATION_DEG,
        pitch_scale=CHANNEL_SCALE_YX, noise_sigma=2.0, cell_error_rate=0.02)
    banded = render(channel.dots, work / "banded.png", px_per_dot=PX_PER_DOT,
                    cell_dots=channel.cell_dots, rotation_deg=0.3,
                    pitch_scale=1.003, noise_sigma=2.0,
                    cell_error_rate=0.16, cell_error_band=(0.75, 1.0))
    ringed = render(channel.dots, work / "ringed.png", px_per_dot=PX_PER_DOT,
                    cell_dots=channel.cell_dots, noise_sigma=2.0,
                    rotation_deg=CHANNEL_ROTATION_DEG,
                    pitch_scale=CHANNEL_SCALE_YX,
                    damage_ring_tiles=1, damage_rate=0.5)
    wide_capture = render(wide.dots, work / "wide.png",
                          px_per_dot=PX_PER_DOT, cell_dots=wide.cell_dots,
                          rotation_deg=0.3, pitch_scale=1.003,
                          noise_sigma=2.0, cell_error_rate=0.02)
    turned = quarter_turn(clean_capture.path, work / "turned.png")
    return [
        ("clean c3-r0550", clean.row,
         ((clean_capture.path, clean_capture.dpi),)),
        ("e032 channel warp c2-r0700", channel.row,
         ((channel_capture.path, channel_capture.dpi),)),
        ("banded c2-r0700", channel.row, ((banded.path, banded.dpi),)),
        ("quarter-turned c3-r0550", clean.row,
         ((turned, clean_capture.dpi),)),
        ("damaged-ring c2-r0700", channel.row,
         ((ringed.path, ringed.dpi),)),
        ("wide 12x12 c3-r0550", wide.row,
         ((wide_capture.path, wide_capture.dpi),)),
    ]


def main(argv: list[str] | None = None) -> int:
    force_dead_switch = "--force-dead-switch" in (
        sys.argv[1:] if argv is None else argv)
    ledger = Ledger()
    install(ledger, force_dead_switch=force_dead_switch)
    with tempfile.TemporaryDirectory(prefix="refine-equiv-") as raw:
        work = Path(raw)
        for index, (name, row, scans) in enumerate(arms(work)):
            started, before = time.perf_counter(), ledger.calls
            state = work / f"state-{index}"
            cli.decode(
                cli.DecodeRequest(
                    scans=scans, workers=1, diag_port=0, state_dir=state,
                    output=work / f"recovered-{index}.bin", complete=True),
                row, real_providers(row, scans), fsync=False, snapshot_every=32)
            print(f"  {name}: {ledger.calls - before} refine calls, "
                  f"{time.perf_counter() - started:.1f} s", flush=True)
    print(ledger.report())
    if ledger.divergences:
        print("\nDIVERGENCE — the twin is NOT bit-identical:")
        for line in ledger.divergences[:40]:
            print(f"  {line}")
        return 1
    if not ledger.sites:
        print("NOTHING COMPARED — no refinement ran; the harness proved "
              "nothing. Check the fixtures.")
        return 1
    print("BIT-IDENTICAL on every compared call.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
