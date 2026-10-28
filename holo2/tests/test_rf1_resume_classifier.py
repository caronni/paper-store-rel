"""Pins the two SILENT classifiers in ``holo2/measure/rf1_resume.py``
(W2, RULINGS I3/I4a, 2026-08-23).

The driver's headline numbers are a live decode's and cannot be pinned
here. These two derivations can, and both are silent when wrong — they
produce a plausible number either way, and W3's ruling reads them:

**Fork 1 — grouping by the POSE key instead of the WINDOW EXTENT.**
RULINGS I3 makes "the latest committed pose for that extent wins" the
law and I4a asks W2 for the poses-per-window distribution as the
anti-spam evidence. A pose key is its window key plus (page, affine)
(``keys.POSE_SPEC`` extends ``WINDOW_SPEC``), so a driver that grouped on
the pose key itself would report EXACTLY ONE pose per group on every
sheet — "no pose spam" as an artefact of the grouping, with the tail the
ruling is about invisible. :func:`rf1_resume.window_of` must return the
window key that ``window_key()`` itself builds.

**Fork 2 — calling every no-op collision ``unmoved_own``.**
``PoseRefineWorker.run`` refuses a revision whose canonical affine
collides with a pose that already stands, under ONE outcome string
(``refused_pose_unmoved``) covering two different facts: the search
landed back on the pose's own parent, or it landed on a SIBLING revision
already committed on that extent. Only the first is "the revision was a
no-op"; the second is a revision that moved and then met a pose already
there — which is a poses-per-window fact, not a no-op one. Collapsing the
two would inflate the no-op share the ruling asks for. The classifier
rebuilds the revised ``PoseRecord`` exactly as the worker does, so this
file also pins that it uses the STANDING pose's window/footing/page and
the verdict's affine — a mutant that reused the standing affine would
answer ``unmoved_own`` always.

No decode, no pixels, no store: a stub view carrying one pose is all
either classifier reads.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _path in (_ROOT / "holo2" / "src", _ROOT / "holo2" / "measure"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import rf1_resume as rf1                                      # noqa: E402

from holo2.core import ResourceKey                            # noqa: E402
from holo2.capture.records import region_key               # noqa: E402
from holo2.solve.keys import pose_key, window_key          # noqa: E402
from holo2.solve.records import PoseRecord                    # noqa: E402
from holo2.solve.refine import OUTCOME_ADOPTED, OUTCOME_REFUSED_PREFIX  # noqa: E402

_FOOTING = "aabbccddeeff:2/1"
_EXTENT = (0, 0, 200, 200)
_STANDING = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
_MOVED = (1.0, 0.0, 0.5, 0.0, 1.0, 0.25)
_UNMOVED = OUTCOME_REFUSED_PREFIX + "pose_unmoved"


def _pose() -> PoseRecord:
    region = region_key("ab" * 32, (0, 0), 8, (512, 512))
    window = window_key(_FOOTING, region, _EXTENT)
    return PoseRecord(window_id=window, footing_id=_FOOTING, page=0,
                      native_affine=_STANDING)


class _Index:
    def __init__(self, poses: dict[ResourceKey, PoseRecord]) -> None:
        self.poses = poses


class _View:
    """The one thing the classifier reads: ``as_plane(view).index().poses``."""

    def __init__(self, poses: dict[ResourceKey, PoseRecord]) -> None:
        self._index = _Index(poses)

    def index(self) -> _Index:
        return self._index


def _worker(pose: PoseRecord) -> rf1.TallyingWorker:
    return rf1.TallyingWorker(pose.resource_key(), None, None, None,
                              tally=rf1.RefineTally())


def test_window_of_returns_the_window_key_not_the_pose_key() -> None:
    """Fork 1: the grouping key is the extent's, one level up from a pose."""
    pose = _pose()
    key = pose.resource_key()
    assert rf1.window_of(key) == pose.window_id
    assert rf1.window_of(key) != key
    # Two poses of ONE extent group together — the fact the distribution
    # is made of, and the fact pose-key grouping would destroy.
    other = pose_key(pose.window_id, pose.page, _MOVED)
    assert rf1.window_of(other) == rf1.window_of(key)


def test_no_op_split_names_the_pose_the_revision_collided_with() -> None:
    """Fork 2: own parent vs a sibling already committed on the extent."""
    pose = _pose()
    view = _View({pose.resource_key(): pose})
    worker = _worker(pose)

    rf1._SLOT.verdict = _Verdict(_STANDING)
    assert worker._no_op_case(view, _UNMOVED) == "unmoved_own"

    rf1._SLOT.verdict = _Verdict(_MOVED)
    assert worker._no_op_case(view, _UNMOVED) == "collides_existing"


@pytest.mark.parametrize("outcome", [OUTCOME_ADOPTED,
                                     OUTCOME_REFUSED_PREFIX + "no_pixels"])
def test_only_the_no_op_outcome_is_classified(outcome: str) -> None:
    """Every other outcome contributes nothing to the no-op counter."""
    pose = _pose()
    rf1._SLOT.verdict = _Verdict(_STANDING)
    assert _worker(pose)._no_op_case(_View({pose.resource_key(): pose}),
                                     outcome) is None


def test_a_missing_verdict_is_unclassified_never_a_case() -> None:
    """An observation gap may not masquerade as a measured case."""
    pose = _pose()
    view = _View({pose.resource_key(): pose})
    rf1._SLOT.verdict = None
    assert _worker(pose)._no_op_case(view, _UNMOVED) == "unclassified"
    rf1._SLOT.verdict = _Verdict(None)
    assert _worker(pose)._no_op_case(view, _UNMOVED) == "unclassified"
    # A pose that is gone (condemned and dropped from the index) too.
    rf1._SLOT.verdict = _Verdict(_STANDING)
    assert _worker(pose)._no_op_case(_View({}), _UNMOVED) == "unclassified"


class _Verdict:
    """``refine_fit.Revision``'s one field this classifier reads."""

    def __init__(self, affine: tuple[float, ...] | None) -> None:
        self.affine = affine
