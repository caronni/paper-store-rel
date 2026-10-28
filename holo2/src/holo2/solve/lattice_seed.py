"""R5's durable fact: one reciprocal lattice seed per (footing, region).

H4-PLAN R5, built in W1. v1's region seed is FIRST-FIT-WINS SHARED
MUTABLE STATE (``src/holo/receive/placement/geometry.py:431-432``): the
first window whose lattice clears every geometric gate writes
``RegionContext.lattice_f``, and two later paths read it — an edge window
too small for its own spectrum takes it as its ONLY fit, and a full-size
window whose blind fit fails the gates zoom-refits around it. Small-window
poses therefore depended on the ORDER windows were fitted in, which is the
single largest byte-comparison risk the dossier named.

The ruling: the seed is a durable per-(footing, region) fact DERIVED from
the BEST-SUPPORTED window's fit, not from whoever fired first. Three
consequences, all mechanical:

* **the TRANSITION LAW is order-independent by construction** — it is a
  total order on ``(support, window)``, so whatever sequence of
  proposals reaches it, the standing record is the maximum of that
  sequence. NARROWED (user ruling, 2026-08-16 — "narrow the claim"): the
  PROPOSAL SET itself is schedule-dependent in the zoom-refit regime — a
  window firing before any seed exists refits blind and proposes its own
  measurement; one firing after a weak seed already stands refits
  CONDITIONED on it and abstains instead (the anti-laundering paragraph
  below), so which fits ever reach the max can depend on fire order in
  the cold-start corner. Only zoom-refit acceptances abstain this way;
  word/chain acceptances propose normally regardless of order. This
  stopped mattering materially once the wide tier's regional-affine seed
  arrived (fit over ALL placed poses at fire time, ``place_job
  .REGIONAL_SEED``): that candidate is schedule-independent by
  construction and is the conditioner searches actually lean on now, so
  this record stays what it always was — the cheap early prior, not the
  thing correctness rests on. The stronger shape — letting a CONDITIONED
  success propose too, under the existing strict-improvement rule
  (:func:`supersedes`), which already bounds any laundering — is
  recorded here rather than built, and is owed only if a measured
  regression ever traces back to this corner;
* **it agrees with v1 wherever v1's wave-front also started at its
  best-supported window** — it does: ``pick_pending`` sorts by
  ``(-support_estimate, window_id)``, which is this rank;
* **it is an ordinary record**, so a window whose blind fit refused
  re-arms when the seed appears or improves (the seed key is in its
  read-set), and the c2 root-cause arm (2026-07-30, the zoom-refit prior)
  becomes a record READ rather than a mutation nobody can replay.

What a proposal may carry is the source window's UNCONDITIONED
measurement — the fundamentals a fit reached without consulting a seed
(``pose_fit.WindowFit.unconditioned_seed``). A seeded or zoom-refitted
window measures the seed back and must not re-propose it: that would be
circular, and it would let a poorly supported window launder a better
window's numbers under its own name.

The key is ``(footing, region)`` and the source window is CONTENT. A
seed is a property of the printed lattice as one footing samples it —
every window of the region reads the same one — so keying it on the
window that happened to fit it would make each window's seed its own,
which is exactly the fact this record exists to deny.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..capture import KIND_REGION, REGION_KEY_PARTS
from ..core import (CommitRefusal, FootingId, KeyEmbed, KeyField, KeySpec,
                    RecordFamily, ResourceKey, build_key, require_own_key)

KIND_LATTICE_SEED = "seed"

LATTICE_SEED_SPEC = KeySpec(KIND_LATTICE_SEED, (
    KeyField("footing_id"),
    KeyEmbed("region", KIND_REGION, REGION_KEY_PARTS)))


def lattice_seed_key(footing_id: FootingId,
                     region: ResourceKey) -> ResourceKey:
    """The reciprocal lattice seed of one (footing, region) — R5."""
    return build_key(LATTICE_SEED_SPEC, footing_id=footing_id, region=region)


@dataclass(frozen=True)
class LatticeSeedRecord:
    """The region's fitted cell fundamentals, and who measured them.

    ``rows`` is ``pose_fit.LatticeSeed.rows``: the normalized (vertical,
    horizontal) reciprocal fundamentals in cycles per pixel, flattened
    row-major, which is the shape v1 froze into a parked row and the
    shape :meth:`~holo2.solve.pose_fit.LatticeSeed.matrix` reads back. The
    round trip through Python floats is lossless, so a seeded fit is
    bit-identical whether its seed came from memory or from this record.

    ``source_window_id`` and ``source_support_cells`` are the ranking
    values (see :func:`seed_rank`), kept as content because the fact they
    rank is the seed, not the window.
    """

    footing_id: FootingId
    region_id: ResourceKey
    rows: tuple[float, float, float, float]
    source_window_id: ResourceKey
    source_support_cells: int

    def __post_init__(self) -> None:
        if len(self.rows) != 4 or not all(
                math.isfinite(float(value)) for value in self.rows):
            raise ValueError(
                "LatticeSeedRecord.rows is four finite reciprocal terms")
        if self.source_support_cells < 0:
            raise ValueError(
                "LatticeSeedRecord.source_support_cells is a cell count")

    def resource_key(self) -> ResourceKey:
        return lattice_seed_key(self.footing_id, self.region_id)

    def matrix(self) -> np.ndarray:
        """The 2x2 reciprocal matrix a fit consumes as a prior."""
        return np.asarray(self.rows, np.float64).reshape(2, 2)


def seed_rank(support_cells: int,
              window_id: ResourceKey) -> tuple[int, ResourceKey]:
    """The total order a seed proposal is judged by — SMALLEST wins.

    ``(-support, window)``: v1's own wave-front key
    (``place.py:1073-1097``), so the window this converges on is the one
    v1's first-fit-wins happened to start at. The window id is the
    tie-break and it is a value, not a schedule, which is what makes two
    runs that fired in different orders agree.
    """
    return (-int(support_cells), window_id)


def supersedes(proposed: LatticeSeedRecord,
               current: LatticeSeedRecord | None) -> bool:
    """May ``proposed`` replace ``current`` under the R5 transition law?"""
    if current is None:
        return True
    return (seed_rank(proposed.source_support_cells,
                      proposed.source_window_id)
            < seed_rank(current.source_support_cells,
                        current.source_window_id))


def _seed_transition(key: ResourceKey, current: LatticeSeedRecord,
                     proposed: LatticeSeedRecord) -> None:
    """R5 at the wall: only a better-supported source may replace a seed.

    On the live path a worse proposal cannot reach here — the seed key is
    in every placement read-set, so a fire that read an absent (or worse)
    seed has a stale identity by the time a better one is standing, and
    the §7 re-derivation discards it. The law is stated anyway, because
    "the seed converges regardless of schedule" is a property of the
    FACT, and a fact whose invariant lives only in its writer is one
    refactor away from being untrue.
    """
    if not isinstance(current, LatticeSeedRecord) or proposed == current:
        return
    if not supersedes(proposed, current):
        raise CommitRefusal(
            f"{key}: a lattice seed is replaced only by a better-supported "
            f"source (R5); standing {current.source_support_cells} cells "
            f"from {current.source_window_id}, refusing "
            f"{proposed.source_support_cells} cells from "
            f"{proposed.source_window_id}")


def _seed_references(key: ResourceKey,
                     record: LatticeSeedRecord) -> tuple[ResourceKey, ...]:
    """A seed stands on the surveyed region it is the lattice OF.

    NOT on its source window: a window becomes a RECORD only when a fire
    places or retires it, and the fit that measures a seed may be the
    very fire that refuses its own phase objective and writes no window
    record at all. Declaring it would refuse that batch. The source
    window is provenance the record carries, not a fact it stands on.
    """
    return (record.region_id,)


def lattice_seed_family() -> RecordFamily:
    """The R5 family, as ``families.record_families`` registers it."""
    return RecordFamily(LatticeSeedRecord, KIND_LATTICE_SEED, version=1,
                        structural=True, validate=require_own_key,
                        transition=_seed_transition,
                        references=_seed_references)


__all__ = [
    "KIND_LATTICE_SEED", "LATTICE_SEED_SPEC", "LatticeSeedRecord",
    "lattice_seed_family", "lattice_seed_key", "seed_rank", "supersedes",
]
