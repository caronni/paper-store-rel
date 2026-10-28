#!/usr/bin/env python
"""The window fit's phase grid, batched: the DELETED arm's evidence.

    env/bin/python holo2/measure/fit_phase_equivalence.py [--fault NAME]

NOT A TEST and not collectable as one: no ``test_`` name, no pytest
fixtures, a ``__main__`` entry point, and it lives outside ``testpaths``
twice over.  It is the fourth harness of the shape ``refine_equivalence``
set, and the first whose twin is not in ``src`` at all.

WHY THE ARM IS HERE AND NOT THERE (2026-08-17; H4-PLAN's banked card 2,
un-banked and REFUTED).  ``pose_fit._fit_phase`` reads its 8x8 phase grid
with 128 ``map_coordinates`` calls; the arm below stacks them into two.
It was built behind a ``PlacementConfig`` switch, proved bit-identical on
the population below, measured, and then DELETED from ``src`` — nobody in
production would call it — following the two-step BM card's precedent,
where the arm that lost lives on as a source reconstruction in its
harness.  :data:`TWIN_BODY` IS that arm, verbatim, and the reconstruction
substitutes it into the shipped file.

WHAT IT MEASURED, and why nothing here should be un-deleted lightly::

    kernel                7.27 -> 6.82 ms         1.07x
    gen-clean serial      115 s OFF -> 116 s ON   no gain
    gen-clean W4           51 s OFF ->  48 s ON   inside the pooled band
    share of serial wall  622 fits x 7.3 ms       3.9%

    window  200   140   100    70    40    20    10  cells
    N      1600  1225  2500  1225  1600   400   100  sites
    gain   1.07  1.09  1.05  1.09  1.06  1.28  1.61  x

The mechanism is the objective's OWN stride, ``round(max(cells) / 40)``:
it holds the grid at ~40x40 for any window, so each of the 128 calls
carries ~1,600 points — far past where scipy's per-call setup matters.
Batching pays below ~400 points, and ``min_window_cells`` is 70 (stride
2, N=1,225), so that regime is unreachable by construction.  The one
asset the arm still holds is its GIL-free fraction — f 0.58 against the
shipped kernel's 0.42, four-thread — which is why this file exists: if
the free-threaded 3.14t card is ever taken, the arm is here, proved, and
can be re-priced instead of rebuilt.

WHAT IT PROVES.  That the arm and the shipped kernel are the SAME
ARITHMETIC, not a close one, so the bar is bit-identity and nothing
weaker: no ``allclose``, no tolerance, no epsilon.  A single differing
bit is a finding, not a rounding.

HOW.  It does not synthesise fits; it INTERCEPTS the real ones.
``pose_fit._fit_phase`` is wrapped so every call the receiver makes runs
THREE ways on identical arguments — the SHIPPED function, an ORACLE
RECONSTRUCTION (the shipped file with one line added, publishing the
score matrix the shipped code keeps to itself), and the TWIN
RECONSTRUCTION (that file with the phase loop replaced by
:data:`TWIN_BODY`) — and returns the SHIPPED answer, so the decode never
runs on anything under measurement.  ``pose_fit``'s view of
``scipy.ndimage`` is tapped, so the INTERPOLATED ARRAYS are compared and
not merely the numbers downstream of them.  Two comparisons per call:

* **faithfulness** — shipped vs oracle reconstruction, planes and answer.
  A reconstruction that has drifted from the file it claims to reproduce
  proves nothing about anything, so it is checked on every call rather
  than assumed;
* **equivalence** — oracle vs twin, at the interpolated planes, the
  64-entry score matrix, and the returned phase.

and one more per fitted window: ``fit_window_pose`` is run a second time
with the twin bound in place of the shipped kernel, and the whole
``WindowFit`` plus the window re-read through its pose are compared array
for array — what every downstream certificate is a function of.

THE RISK AXIS IS LENGTH.  The reduction is the one part the arm does NOT
batch: each hypothesis scores only the sites its own phase put under
``coverage > 0.9``, so the subsets are variable-length, and numpy's
pairwise float32 sum blocks BY LENGTH.  The decode population alone
clusters on fully covered windows, so on the first fit of every prepared
region the harness re-runs the same real window through a ladder of
SLANTED support cuts (:data:`SUPPORT_CUT_PERCENTILES`): a ragged
boundary, so the covered count differs BETWEEN hypotheses inside one
call, walked from a nearly-full window down through the 16-site gate to
one no hypothesis can score.  Those cuts are a length population, not a
physical claim — every arm sees identical inputs, which is all the
comparison needs.

THE POPULATION is real decodes over rendered fixtures (``verdicts/
_fixtures.py``'s own builders, which emit through the real ``src/holo``
generator), across six arms chosen to move the window geometry the fit
sees: a clean page, the measured e032 channel warp, a banded page whose
right quarter kills the word code, a capture rotated by a quarter turn, a
damaged ring that drives the corner-retry windows, and a wider page that
simply lays more windows down.  All perturbation is seeded; there is no
unseeded RNG anywhere in it.

``--fault list`` names the deliberate breakages.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import time
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage as _real_ndimage

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
from holo2.solve import pose_fit  # noqa: E402

PX_PER_DOT = 2


# --------------------------------------------------- the arm, as source

#: The shipped kernel's phase loop, which the twin replaces.  Anchored on
#: the whole block INCLUDING v1's comment, so a re-indent or a comment
#: edit fails loudly here instead of quietly reconstructing something
#: else.
SCALAR_LOOP = '''    scores = np.full((offsets.size, offsets.size), -np.inf)
    # v1 spells these loop ordinals ``iy, ix`` and then REBINDS the same
    # two names to the argmax below; distinct names, same scan order.
    for row, phase_y in enumerate(offsets):
        for column, phase_x in enumerate(offsets):
            points = (grid + np.array([phase_y, phase_x])) @ jacobian.T + base
            means = ndimage.map_coordinates(
                region.filtered, points.T, order=1, cval=region.backing
            )
            coverage = ndimage.map_coordinates(
                region.support, points.T, order=1, cval=0.0
            )
            selected = coverage > 0.9
            if int(selected.sum()) >= 16:
                scores[row, column] = float(
                    np.abs(means[selected] - midpoint).mean()
                )
'''

#: THE DELETED ARM, verbatim as it stood in ``pose_fit`` before it was
#: removed.  Every clause of its bit-identity argument was measured on
#: this numpy/scipy before it was relied on:
#:
#: * the COORDINATES are the shipped kernel's own expression, unfactored
#:   — run once per hypothesis exactly as before, then COPIED into the
#:   stack.  It does not factor the way the refinement's did (there the
#:   phase entered AFTER the matmul; here it is added to the grid BEFORE
#:   it, and addition does not distribute through the product), so
#:   identity is by CONSTRUCTION, not by luck.  Measured anyway:
#:   factoring perturbs 22-30% of coordinates by up to 4.5e-13 px and
#:   moves ZERO of 204,800 interpolated values — the observability floor
#:   of a float32 read, and the reason ``twin-factored-coords`` is a
#:   PROBE here and not a fault.  What IS load-bearing is the stack's
#:   dtype: at float32 coordinates the interpolation moves.
#: * ``map_coordinates`` at ``order=1`` does no prefilter and no
#:   cross-point work — each output point is a function of its own
#:   coordinate pair — so batching the array cannot move a bit, and its
#:   LAYOUT cannot either (probed both ways).  Output dtype follows the
#:   input (``float32`` planes), exactly as per-call.
#: * the reduction is NOT batched: each hypothesis keeps the shipped
#:   kernel's compressed float32 array and its own ``np.mean``, because
#:   numpy's pairwise sum blocks by LENGTH and equal lengths are what
#:   make equal answers.  Only the gate's counts are taken as one axis
#:   sum, which is exact over booleans at any order.
TWIN_BODY = '''    hypotheses = offsets.size * offsets.size
    points_all = np.empty((2, hypotheses, grid.shape[0]), np.float64)
    index = 0
    for phase_y in offsets:
        for phase_x in offsets:
            points = (grid + np.array([phase_y, phase_x])) @ jacobian.T + base
            points_all[:, index, :] = points.T
            index += 1
    all_means = ndimage.map_coordinates(
        region.filtered, points_all, order=1, cval=region.backing
    )
    all_coverage = ndimage.map_coordinates(
        region.support, points_all, order=1, cval=0.0
    )
    all_selected = all_coverage > 0.9
    counts = all_selected.sum(axis=1)
    scores = np.full((offsets.size, offsets.size), -np.inf)
    index = 0
    for row in range(offsets.size):
        for column in range(offsets.size):
            if int(counts[index]) >= 16:
                chosen = all_selected[index]
                scores[row, column] = float(
                    np.abs(all_means[index][chosen] - midpoint).mean()
                )
            index += 1
'''

#: The score matrix is a local the shipped kernel never returns, so a
#: reconstruction publishes it.  This is the ONLY difference between the
#: shipped function and the oracle reconstruction, and the faithfulness
#: check on every call is what says so rather than assuming it.
ARGMAX_LINE = ("    iy, ix = np.unravel_index(int(np.argmax(scores)), "
               "scores.shape)")
PUBLISH = "    _SCORES.append(scores.copy())\n" + ARGMAX_LINE


def reconstruct(name: str, substitutions: list[tuple[str, str]]) -> Any:
    """Compile one variant of the shipped module, by substitution."""
    source = Path(pose_fit.__file__).read_text()
    for found, replacement in [(ARGMAX_LINE, PUBLISH)] + substitutions:
        if source.count(found) != 1:
            raise SystemExit(
                f"{name}: an anchor is not unique ({source.count(found)} "
                f"matches) — the shipped source moved under this harness:\n"
                f"  {found.splitlines()[0]}")
        source = source.replace(found, replacement)
    module_name = f"holo2.solve._pose_fit_{name}"
    spec = importlib.util.spec_from_loader(module_name, loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "holo2.solve"
    module.__file__ = pose_fit.__file__
    sys.modules[module_name] = module
    exec(compile(source, f"<{name} reconstruction>", "exec"), module.__dict__)
    module._SCORES = []
    return module


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
    """What the run saw: calls, site spans, and any divergence at all."""

    def __init__(self) -> None:
        self.fits = 0
        self.objectives = 0
        self.faithful = 0
        self.swept = 0
        self.refused_early = 0
        self.samples = 0
        self.sites: list[int] = []
        self.ragged = 0
        self.scored: list[int] = []
        self.divergences: list[str] = []

    def record(self, shipped: Any, oracle: Any, twin: Any, tag: str) -> None:
        """One objective: the faithfulness check, then the equivalence."""
        self.objectives += 1
        # 1. the reconstruction reproduces the file it claims to.
        self.faithful += 1
        self.divergences += _differences(shipped.answer, oracle.answer,
                                         f"{tag}.faithful.answer")
        self.divergences += _differences(shipped.means, oracle.means,
                                         f"{tag}.faithful.means")
        # 2. the arm is the same arithmetic as that reconstruction.
        self.divergences += _differences(oracle.means, twin.means,
                                         f"{tag}.means")
        self.divergences += _differences(oracle.coverage, twin.coverage,
                                         f"{tag}.coverage")
        self.divergences += _differences(oracle.scores, twin.scores,
                                         f"{tag}.scores")
        self.divergences += _differences(oracle.answer, twin.answer,
                                         f"{tag}.phase")
        if oracle.scores is not None:
            self.scored.append(int(np.isfinite(oracle.scores).sum()))
        coverage = np.asarray(oracle.coverage)
        if not coverage.size:
            self.divergences.append(
                f"{tag}: the oracle's interpolations were not observed — "
                "the tap is not on the arm that ran")
            return
        counts = (coverage > 0.9).sum(axis=1)
        self.sites.append(int(counts.min()))
        self.sites.append(int(counts.max()))
        if int(counts.max()) != int(counts.min()):
            self.ragged += 1

    def report(self) -> str:
        span = (f"{min(self.sites)}-{max(self.sites)}"
                if self.sites else "n/a")
        scored = (f"{min(self.scored)}-{max(self.scored)}"
                  if self.scored else "n/a")
        return (
            f"{self.fits} fits, {self.objectives} phase objectives run THREE "
            f"ways — {self.faithful} shipped-vs-reconstruction faithfulness "
            f"checks, then oracle-vs-twin at the interpolated planes, the "
            f"score matrix and the phase answer — of which {self.swept} are "
            f"support-cut ladder steps; {self.refused_early} refused before "
            f"interpolating; {self.samples} poses re-read and compared "
            f"array-for-array; selected sites per hypothesis {span}, "
            f"hypotheses scored per grid {scored}, {self.ragged} objectives "
            f"had hypotheses of DIFFERING length; "
            f"{len(self.divergences)} divergences")


# ------------------------------------------------------------ the intercept

class _Scan:
    """One arm's whole record of one phase objective."""

    def __init__(self, scores: Any, planes: list[np.ndarray],
                 answer: Any) -> None:
        self.scores = scores
        self.planes = planes
        self.answer = answer
        # The shipped kernel interleaves (means, coverage) per hypothesis;
        # the twin issues one of each for the whole grid.  Both land here
        # as one ``(H, N)`` array per plane, which is what makes them
        # comparable AT THE INTERPOLATION and not only downstream of it.
        if len(planes) == 2 and planes[0].ndim == 2:
            self.means, self.coverage = planes[0], planes[1]
        else:
            self.means = np.stack(planes[0::2]) if planes else np.zeros((0, 0))
            self.coverage = (np.stack(planes[1::2]) if planes
                             else np.zeros((0, 0)))


class _Ndimage:
    """``pose_fit``'s view of scipy, with a tap on ``map_coordinates``.

    Only the tapped modules' calls are affected, and only while an
    objective is running: ``sample_segment`` and the region prefilter use
    the same name and must not be recorded.
    """

    def __init__(self) -> None:
        self.planes: list[np.ndarray] = []
        self.recording = False

    def __getattr__(self, name: str) -> Any:
        return getattr(_real_ndimage, name)

    def map_coordinates(self, *args: Any, **kwargs: Any) -> Any:
        result = _real_ndimage.map_coordinates(*args, **kwargs)
        if self.recording:
            self.planes.append(np.asarray(result).copy())
        return result


#: Percentiles of a SLANTED ramp over the window, used as support cuts.
#: The slant is what makes the boundary ragged in cell terms, so a
#: half-cell phase shift moves the covered count and the 64 hypotheses of
#: one call reduce arrays of DIFFERENT lengths — the only condition under
#: which a batched reduction could ever part company with a per-call one.
#: The ladder walks from a nearly-full window down through the 16-site
#: gate to one that nothing can score.
SUPPORT_CUT_PERCENTILES = (99.0, 90.0, 70.0, 50.0, 30.0, 15.0, 7.0, 3.0,
                           1.5, 0.7, 0.3, 0.1)


def slanted_cuts(support: np.ndarray) -> list[np.ndarray]:
    """The same support, cut back along a slanted ragged boundary."""
    height, width = support.shape
    ramp = (np.arange(height, dtype=np.float64)[:, None]
            + 0.37 * np.arange(width, dtype=np.float64)[None, :])
    zero = np.float32(0.0)
    thresholds = np.percentile(ramp, SUPPORT_CUT_PERCENTILES)
    return [np.where(ramp < threshold, support, zero).astype(np.float32)
            for threshold in thresholds]


class Harness:
    """Three arms on every real objective, plus the length ladder."""

    def __init__(self, ledger: Ledger,
                 substitutions: dict[str, list[tuple[str, str]]]) -> None:
        self.ledger = ledger
        self.shipped = pose_fit._fit_phase
        self.fit = pose_fit.fit_window_pose
        self.tap = _Ndimage()
        self.oracle_module = reconstruct("oracle", substitutions["oracle"])
        self.twin_module = reconstruct(
            "twin", [(SCALAR_LOOP, TWIN_BODY)] + substitutions["twin"])
        self.swept: set[int] = set()

    def install(self) -> None:
        pose_fit.ndimage = self.tap
        # Each reconstruction carries its OWN ``from scipy import
        # ndimage``: without this the tap would see one arm's
        # interpolations and not the other's, and a fault would be
        # "detected" by the tap's own blindness (it was, once).
        self.oracle_module.ndimage = self.tap
        self.twin_module.ndimage = self.tap
        pose_fit._fit_phase = self.compare
        pose_fit.fit_window_pose = self.both_fits

    def _run(self, arm: Any, sink: Any, args: tuple) -> _Scan:
        if sink is not None:
            sink.clear()
        self.tap.planes = []
        self.tap.recording = True
        try:
            answer = arm(*args)
        finally:
            self.tap.recording = False
        return _Scan(sink[-1] if sink else None, self.tap.planes, answer)

    def compare(self, region: Any, jacobian: Any, window: Any,
                config: Any, tag: str = "fit") -> Any:
        """The intercepted objective: run all three, return the SHIPPED."""
        args = (region, jacobian, window, config)
        shipped = self._run(self.shipped, None, args)
        oracle = self._run(self.oracle_module._fit_phase,
                           self.oracle_module._SCORES, args)
        twin = self._run(self.twin_module._fit_phase,
                         self.twin_module._SCORES, args)
        if not shipped.planes and not oracle.planes and not twin.planes:
            # No support at all under the window: the kernel returns
            # before it interpolates.  Still a comparison — of three
            # refusals — and still worth counting.
            self.ledger.refused_early += 1
            self.ledger.divergences += _differences(
                shipped.answer, twin.answer, f"{tag}.phase")
            return shipped.answer
        self.ledger.record(shipped, oracle, twin, tag)
        return shipped.answer

    def both_fits(self, region: Any, window: Any, *, config: Any,
                  lattice_seed: Any = None) -> Any:
        """The whole fit, twice: shipped kernel, then the twin bound in."""
        shipped_fit = self.fit(region, window, config=config,
                               lattice_seed=lattice_seed)
        self.ledger.fits += 1
        pose_fit._fit_phase = self.twin_module._fit_phase
        try:
            twin_fit = self.fit(region, window, config=config,
                                lattice_seed=lattice_seed)
        finally:
            pose_fit._fit_phase = self.compare
        self.ledger.divergences += _differences(shipped_fit, twin_fit, "fit")
        # What every downstream certificate is a function of: the window
        # re-read through each arm's pose.
        if shipped_fit.segment is not None and twin_fit.segment is not None:
            self.ledger.samples += 1
            self.ledger.divergences += _differences(
                pose_fit.sample_segment(region, shipped_fit.segment),
                pose_fit.sample_segment(region, twin_fit.segment), "sample")
        # Once per prepared region, walk the SAME real window down the
        # site-count ladder (see SUPPORT_CUT_PERCENTILES).
        if shipped_fit.segment is not None and id(region) not in self.swept:
            self.swept.add(id(region))
            jacobian = shipped_fit.segment.pose.matrix()
            for index, cut in enumerate(slanted_cuts(region.support)):
                self.ledger.swept += 1
                self.compare(replace(region, support=cut), jacobian, window,
                             config, f"cut{index}")
        # The decode proceeds on the SHIPPED kernel, always.
        return shipped_fit


# ---------------------------------------------------------------- the faults

#: Deliberate breakages, each a real substitution, with what the run is
#: EXPECTED to see.  Four break the ARM (which now lives in this file, so
#: its faults are substitutions of :data:`TWIN_BODY`); one breaks the
#: SHIPPED source the oracle reconstruction is built from, because a
#: comparison that only looks one way is not a comparison;
#: ``compare-blind`` breaks the COMPARATOR while a real fault is live,
#: and if that run still reports a divergence then this harness is
#: finding differences that are not there.
#:
#: ``oracle-coverage-gate`` is also the standing argument for comparing
#: the SCORE MATRIX and not only the answer: measured, it moves ONE score
#: of 64 without moving the argmax, so the returned phase and the
#: interpolated planes are untouched and the faithfulness check stays
#: silent through it.  The score-level comparison is what catches it —
#: an answer-level harness would have called that population clean.
#:
#: ``twin-factored-coords`` is expected to be SILENT and is a PROBE
#: rather than a fault, for a measured reason: distributing the phase
#: through the matmul perturbs 22-30% of the coordinates by up to
#: 4.5e-13 px and moves ZERO of 204,800 interpolated values, because the
#: planes are ``float32``.  The arm keeps the shipped expression anyway —
#: identity by construction beats identity by luck — and this probe is
#: what says which of the two it is.  If it ever BITES, the observability
#: floor moved and this note is stale.
FAULTS: dict[str, tuple[str, tuple[str, str], str]] = {
    "twin-float32-coords": (
        "twin",
        ("points_all = np.empty((2, hypotheses, grid.shape[0]), np.float64)",
         "points_all = np.empty((2, hypotheses, grid.shape[0]), np.float32)"),
        "detected"),
    "twin-factored-coords": (
        "twin",
        ("            points = (grid + np.array([phase_y, phase_x])) "
         "@ jacobian.T + base\n            points_all[:, index, :] = points.T",
         "            points = grid @ jacobian.T + (\n"
         "                np.array([phase_y, phase_x]) @ jacobian.T + base)\n"
         "            points_all[:, index, :] = points.T"),
        "silent"),
    "twin-batched-reduction": (
        "twin",
        ("                scores[row, column] = float(\n"
         "                    np.abs(all_means[index][chosen] "
         "- midpoint).mean()\n                )",
         "                scores[row, column] = float(\n"
         "                    (np.abs(all_means[index] - midpoint)\n"
         "                     * chosen).sum() / counts[index]\n"
         "                )"),
        "detected"),
    "twin-gate-raised": (
        "twin",
        ("            if int(counts[index]) >= 16:",
         "            if int(counts[index]) >= 64:"),
        "detected"),
    "twin-hypothesis-order": (
        "twin",
        ("    for phase_y in offsets:\n        for phase_x in offsets:",
         "    for phase_x in offsets:\n        for phase_y in offsets:"),
        "detected"),
    "oracle-coverage-gate": (
        "oracle",
        ("            selected = coverage > 0.9",
         "            selected = coverage > 0.8"),
        "detected"),
    "compare-blind": (
        "twin",
        ("points_all = np.empty((2, hypotheses, grid.shape[0]), np.float64)",
         "points_all = np.empty((2, hypotheses, grid.shape[0]), np.float32)"),
        "control"),
}


def substitutions_for(name: str | None) -> dict[str, list[tuple[str, str]]]:
    """Where an injected fault goes: into the arm's body, or into the file."""
    plan: dict[str, list[tuple[str, str]]] = {"oracle": [], "twin": []}
    if name is None:
        return plan
    target, (found, replacement), _ = FAULTS[name]
    if target == "twin":
        if TWIN_BODY.count(found) != 1:
            raise SystemExit(f"fault {name!r}: its anchor is not unique in "
                             "TWIN_BODY — the arm moved under its faults")
        globals()["TWIN_BODY"] = TWIN_BODY.replace(found, replacement)
    else:
        plan["oracle"].append((found, replacement))
    if name == "compare-blind":
        globals()["_differences"] = lambda *args, **kwargs: []
    return plan


# ---------------------------------------------------------------- the arms

def quarter_turn(source: Path, target: Path) -> Path:
    """The same capture on its side — a different window geometry."""
    with Image.open(source) as image:
        Image.fromarray(np.rot90(np.asarray(image))).save(target)
    return target


def arms(work: Path) -> list[tuple[str, Any, tuple[tuple[Path, float], ...]]]:
    """Six decodes whose WINDOW geometry differs on purpose.

    The fit runs once per window, so what moves this population is what
    moves window layout and window quality: a damaged ring drives the
    corner retries (the smallest windows the kernel ever fits), a wider
    page lays more windows down, and the warp/band/turn arms change which
    of them clear the geometric gates at all.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fault", default=None,
                        help="inject one deliberate breakage, or 'list'")
    parser.add_argument("--arms", type=int, default=0,
                        help="decode only the first N arms (0 = all)")
    options = parser.parse_args()
    if options.fault == "list":
        for name, (target, (found, _), expect) in FAULTS.items():
            print(f"  {name:24} [{expect:8}] {target}: "
                  f"{found.strip().splitlines()[0]}")
        return 0
    expect = "none"
    if options.fault is not None:
        if options.fault not in FAULTS:
            raise SystemExit(f"unknown fault {options.fault!r}")
        expect = FAULTS[options.fault][2]
        print(f"FAULT INJECTED: {options.fault} (expected: {expect})",
              flush=True)

    ledger = Ledger()
    Harness(ledger, substitutions_for(options.fault)).install()
    with tempfile.TemporaryDirectory(prefix="fit-phase-equiv-") as raw:
        work = Path(raw)
        selected = arms(work)
        if options.arms:
            selected = selected[:options.arms]
        for index, (name, row, scans) in enumerate(selected):
            started, before = time.perf_counter(), ledger.fits
            state = work / f"state-{index}"
            cli.decode(
                cli.DecodeRequest(
                    scans=scans, workers=1, diag_port=0, state_dir=state,
                    output=work / f"recovered-{index}.bin", complete=True),
                row, real_providers(row, scans), fsync=False, snapshot_every=32)
            print(f"  {name}: {ledger.fits - before} fits, "
                  f"{time.perf_counter() - started:.1f} s", flush=True)
    print(ledger.report())

    # A fault run is asking ONE question — was it caught? — and its own
    # breakage may legitimately move the liveness numbers below (the
    # oracle-side fault widens the gate it is measured through), so the
    # detection verdict is read first and the liveness gates only ever
    # explain an UNDETECTED result.
    if expect in ("detected", "silent") and ledger.divergences:
        verdict = ("DETECTED" if expect == "detected" else
                   "BIT — and it was recorded SILENT: the observability "
                   "floor moved and that note is now stale")
        print(f"FAULT {options.fault!r} {verdict} "
              f"({len(ledger.divergences)} divergences); first few:")
        for line in ledger.divergences[:6]:
            print(f"  {line}")
        return 0 if expect == "detected" else 1

    # Liveness before verdict: a reconstruction that never ran, or a
    # ladder that never got past the gate, proves nothing at all.
    if not ledger.objectives:
        print("NOTHING COMPARED — no phase objective ran; the harness proved "
              "nothing. Check the fixtures.")
        return 1
    if ledger.faithful != ledger.objectives:
        print(f"FAITHFULNESS UNCHECKED — {ledger.faithful} of "
              f"{ledger.objectives} objectives compared the shipped kernel "
              "against its reconstruction; the arm's oracle is unproven.")
        return 1
    if not ledger.ragged:
        print("NO RAGGED OBJECTIVE — every compared call reduced 64 subsets "
              "of EQUAL length, so the variable-length axis was never "
              "exercised. Check the support cuts.")
        return 1
    if min(ledger.scored) > 0 or max(ledger.scored) < 64:
        print(f"LADDER TOO NARROW — hypotheses scored per grid stayed in "
              f"{min(ledger.scored)}-{max(ledger.scored)}: the 16-site gate's "
              "both sides were not both reached.")
        return 1

    if options.fault == "compare-blind":
        seen = len(ledger.divergences)
        print(f"COMPARE-CONTROL: comparator blinded with a real fault live — "
              f"{seen} divergences reported. "
              + ("CONFIRMED: the detections above come from the comparison, "
                 "not from the population." if not seen else
                 "BROKEN: differences were reported by something other than "
                 "the comparator."))
        return 0 if not seen else 1
    if ledger.divergences:
        print("\nDIVERGENCE — the arms are NOT bit-identical:")
        for line in ledger.divergences[:40]:
            print(f"  {line}")
        return 1
    if expect == "silent":
        print(f"PROBE {options.fault!r} SILENT, as measured — the mutation is "
              "below the float32 read's resolution (see FAULTS).")
        return 0
    if options.fault:
        print(f"FAULT {options.fault!r} UNDETECTED — a hole in this harness.")
        return 1
    print("BIT-IDENTICAL on every compared call — the deleted arm still "
          "reproduces the shipped kernel exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
