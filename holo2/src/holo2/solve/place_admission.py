"""The OR-9 admission table and the algebra that derives from it.

Split out of ``place_model.py`` (H4 W2-EXIT parallelism line, the batched
Chien card) as a SEAM, not a rewrite: every line below arrived here
verbatim from ``place_model``'s first three sections, in its original
order, and ``place_model`` re-exports the whole surface — so
``from .place_model import E022_WINDOW_CELLS`` still resolves and no
importer in the tree changed.  The split was forced by the 1000-line cap
(WORKPLAN standing rules: a cap is a seam signal — split, never squeeze),
and the seam it named was already in the file's own section rules:

* **here** — WHAT the admission numbers ARE and where each came from:
  the carried constants, the two validators that police them, the two
  DERIVED bounds (:func:`identifiability_support_floor`,
  :func:`hypothesis_count`), and :data:`OR9_FLOORS`, the one table that
  gives every constant a name, an origin and a source;
* **``place_model``** — the TYPES that consume them: the coupled gate,
  the budgets, the window/sampler/audit policy, the pose vocabulary the
  kernel produces, and the domain envelope.

Nothing here imports another ``solve`` module, which is the test that the
seam is real: the table is the leaf, and the algebra is a function of the
table and of nothing else.

**The OR-9 ruling, built here** (H4-PLAN §3-W0, solve/DESIGN.md L7b):
every admission constant is either DERIVED by the algebra below or
carried as a NAMED, SOURCED datum.  :data:`OR9_FLOORS` is that table —
one row per constant, each with its origin, its source, and the holo2
placeholder it retires.  The one derived row is
``AttemptBudget.min_support``

    max(E022_SUPPORT_FLOOR_SITES,
        identifiability_support_floor(H, BER) + margin)

which is e026's site-count law (``ceil(log2(H) / (1 - h2(BER)))``) floored
by E022-v2's measured 30 sites per disjoint parity population.  Neither
bound is a tail bound for the weighted mismatch statistic, and the
declared false-accept target still owes the v1 null and the physical
qualification named by HOLO-DESIGN §9.3 — the receiver stays PROVISIONAL.

Arithmetic deliberately NOT touched (``place_model``'s own words, for the
half of them that live here): the entropy expression and its
``error == 0`` special case, ``int(math.ceil(...))`` (never ``np.rint``,
never ``int(np.ceil(...))`` — three different functions), and
:func:`hypothesis_count`'s integer overhang counting.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

import numpy as np


# --------------------------------------------------------------- the data
# Every number below is CARRIED: it has a name, a source and a row in
# OR9_FLOORS.  Nothing here is derived; the derivation is the algebra.

E022_SUPPORT_FLOOR_SITES = 30
"""Qualified E022-v2 floor for each disjoint parity population.

The score is an evidence-weighted mismatch, not a Binomial hard-error
count.  Consequently neither ``alpha`` nor a hard-BER tail may honestly be
used to derive its acceptance floor without a new weighted-statistic
qualification.
"""

E022_WINDOW_CELLS = 200
E022_OVERLAP_CELLS = 40
E022_MIN_WINDOW_CELLS = 70
E022_LAYOUT_MIN_WINDOW_CELLS = 8
E022_SUBDIVISION_MAX_DEPTH = 1
MAX_LOWER_HINTS = 8

GATE_SEARCH_TRUE = 0.20
GATE_RIVAL_DECOY = 0.20
GATE_MINIMUM_GAP = 0.08
GATE_VALIDATION_TRUE = 0.24
"""Exact strict E022-v2 placement bars (2026-07-14)."""

PROVISIONAL_ALPHA = 1e-3
PROVISIONAL_CHANNEL_BER_ENVELOPE = 0.08
PROVISIONAL_SUPPORT_MARGIN_SITES = 0


# ------------------------------------------------------------- validation

def _ratio(label: str, value: float, *, high: float,
           include_zero: bool = False) -> float:
    """Return a finite ratio in ``(0, high)`` — or ``[0, high)``."""
    result = float(value)
    low_ok = 0.0 <= result if include_zero else 0.0 < result
    if not low_ok or not result < high or not math.isfinite(result):
        bound = "[0" if include_zero else "(0"
        raise ValueError(f"{label} must be finite and in {bound}, {high})")
    return result


def _int_at_least(label: str, value: object, minimum: int) -> int:
    """Accept python and numpy integers, refuse bools — v1's exact rule.

    ``bool`` is an ``int`` subclass and so needs the explicit arm;
    ``np.bool_`` is an instance of neither ``int`` nor ``np.integer`` and
    is refused by the second clause without one.
    """
    if (isinstance(value, bool)
            or not isinstance(value, (int, np.integer))
            or int(value) < minimum):
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return int(value)


def _identity(label: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty")
    return value


# ------------------------------------------------------------- the floors

def identifiability_support_floor(
    hypotheses: int, max_true_error_rate: float
) -> int:
    """Return e026's ``ceil(log2(H) / (1 - h2(BER)))`` lower bound.

    This is the site-count identifiability law recorded in HOLO-DESIGN
    §9.3 and e026.2.  It is a necessary information bound, not a
    family-wise false-accept certificate and not a model of the weighted
    gate statistic.
    """
    domain = _int_at_least("hypotheses", hypotheses, 1)
    error = _ratio("max_true_error_rate", max_true_error_rate,
                   high=0.5, include_zero=True)
    if domain == 1:
        return 0
    entropy = (
        0.0 if error == 0.0
        else -error * math.log2(error) - (1.0 - error) * math.log2(1.0 - error)
    )
    return int(math.ceil(math.log2(domain) / (1.0 - entropy)))


def hypothesis_count(
    fragment_shape: tuple[int, int],
    page_shape: tuple[int, int],
    pages: int,
    *,
    allow_overhang: bool,
) -> int:
    """Exact integer-offset x rot90 x page domain, before support pruning.

    v1 ``placement/search.py:211``; it lives with the budgets because the
    complete-domain declaration is what the floors are derived from (L7a:
    the domain is frozen before a pixel is read, and an invocation whose
    domain is larger refuses rather than searching a prefix).
    """
    total = 0
    height, width = page_shape
    for rot_k in range(4):
        frag_height, frag_width = (
            fragment_shape if rot_k % 2 == 0 else fragment_shape[::-1]
        )
        if allow_overhang:
            positions = (height + frag_height - 1) * (width + frag_width - 1)
        else:
            positions = max(0, height - frag_height + 1) * max(
                0, width - frag_width + 1
            )
        total += positions
    return int(pages) * total


# ------------------------------------------------------- OR-9 as one table

DatumOrigin: TypeAlias = Literal["derived", "carried"]


@dataclass(frozen=True, slots=True)
class AdmissionDatum:
    """One admission constant with its provenance (OR-9's ruling).

    ``origin`` is ``derived`` when the algebra in this module computes the
    value (``value is None`` — there is no fixed number to quote) and
    ``carried`` when it is a measured or geometric datum this port brought
    across unchanged.  ``retires`` names the holo2 placeholders the row
    replaces when the kernel waves consume it.
    """

    name: str
    origin: DatumOrigin
    value: int | float | None
    source: str
    note: str
    retires: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identity("admission datum name", self.name)
        _identity("admission datum source", self.source)
        _identity("admission datum note", self.note)
        if self.origin not in ("derived", "carried"):
            raise ValueError("admission datum origin is derived or carried")
        if (self.value is None) != (self.origin == "derived"):
            raise ValueError(
                "a derived datum quotes no value; a carried datum must")


OR9_FLOORS: tuple[AdmissionDatum, ...] = (
    AdmissionDatum(
        "min_support", "derived", None,
        "model.py:173-181 (AttemptBudget.min_support), e026 + E022-v2",
        "max(E022_SUPPORT_FLOOR_SITES, identifiability_support_floor("
        "max_hypotheses, max_true_error_rate) + support_margin_sites), "
        "applied to EACH disjoint parity population",
        ("solve.placement_h3bis.SUPPORT_FLOOR = 0.9",
         "solve.toys.TOY_SUPPORT_FLOOR = 0.9"),
    ),
    AdmissionDatum(
        "e022_support_floor_sites", "carried", E022_SUPPORT_FLOOR_SITES,
        "model.py:24-30; E022-v2 measured floor (paperholo e022)",
        "the measured floor the derived rule can never fall below; a "
        "weighted mismatch statistic has no honest alpha-derived floor",
    ),
    AdmissionDatum(
        "familywise_false_accept", "carried", PROVISIONAL_ALPHA,
        "defaults.py:15 (_PROVISIONAL_ALPHA)",
        "declared target and audit field, deliberately absent from the "
        "floor formula — the record supplies no proved mapping from alpha "
        "to the weighted mismatch/rival decision",
    ),
    AdmissionDatum(
        "max_true_error_rate", "carried", PROVISIONAL_CHANNEL_BER_ENVELOPE,
        "defaults.py:16 (_PROVISIONAL_CHANNEL_BER_ENVELOPE)",
        "channel-BER envelope entering the identifiability floor; "
        "unqualified until the physical/null gate is frozen",
    ),
    AdmissionDatum(
        "support_margin_sites", "carried", PROVISIONAL_SUPPORT_MARGIN_SITES,
        "defaults.py:25 (support_margin_sites=0)",
        "safety margin added to the identifiability floor; zero today and "
        "named in V1_PRODUCTION_QUALIFICATION_NOTES as still owed",
    ),
    AdmissionDatum(
        "gate_search_true", "carried", GATE_SEARCH_TRUE,
        "model.py:32-36; exact strict E022-v2 bars (2026-07-14)",
        "search-parity true-candidate mismatch bar",
    ),
    AdmissionDatum(
        "gate_rival_decoy", "carried", GATE_RIVAL_DECOY,
        "model.py:32-36; exact strict E022-v2 bars (2026-07-14)",
        "rival/decoy mismatch bar; v0.30 evaluates it WHOLE-WORD",
    ),
    AdmissionDatum(
        "gate_minimum_gap", "carried", GATE_MINIMUM_GAP,
        "model.py:32-36; exact strict E022-v2 bars (2026-07-14)",
        "minimum true-to-rival separation",
    ),
    AdmissionDatum(
        "gate_validation_true", "carried", GATE_VALIDATION_TRUE,
        "model.py:32-36; exact strict E022-v2 bars (2026-07-14)",
        "held-out validation-parity bar",
    ),
    AdmissionDatum(
        "window_cells", "carried", E022_WINDOW_CELLS,
        "model.py:273-288 (PlacementConfig); measured E022 geometry",
        "nominal window span; characterization metrology does not "
        "participate in receiver window sizing",
        ("solve.geometry.WINDOW_CELLS = 256 (H2 spine value)",),
    ),
    AdmissionDatum(
        "overlap_cells", "carried", E022_OVERLAP_CELLS,
        "model.py:273-288 (PlacementConfig); measured E022 geometry",
        "window overlap; the step is window_cells - overlap_cells = 160",
        ("solve.geometry.WINDOW_STEP_CELLS = 128 (H2 spine value)",),
    ),
    AdmissionDatum(
        "min_window_cells", "carried", E022_MIN_WINDOW_CELLS,
        "model.py:273-288; consumed by geometry.py:564-595 (subdivide)",
        "smallest corner retry E022 fits.  DESIGN §8.2 records the cost: "
        "it refuses a 64-cell clipped window whose ~4,096 supported cells "
        "clear the derived floor easily, so the subdivision wave (W3) "
        "consults min_support and keeps this as the geometric floor only",
        ("solve.geometry.MIN_WINDOW_CELLS = 64 (one tile)",),
    ),
    AdmissionDatum(
        "layout_min_window_cells", "carried", E022_LAYOUT_MIN_WINDOW_CELLS,
        "geometry.py:538 (`if min(shape) < 8`), a bare literal in v1",
        "the LAYOUT sliver rule, and the only floor a flush-shifted "
        "lattice can reach: every window is a full window_cells square "
        "except on an axis shorter than one window, so this bites on the "
        "REGION, never on a remainder.  NOT min_window_cells, which is "
        "the subdivision retry floor the H2 spine misapplied here "
        "(H4-PLAN R12 addenda, the window-alignment ruling)",
        ("solve.geometry.MIN_WINDOW_CELLS = 70 (the subdivision floor,"
         " applied to a clipped layout)",),
    ),
    AdmissionDatum(
        "subdivision_max_depth", "carried", E022_SUBDIVISION_MAX_DEPTH,
        "geometry.py:572 (`window.depth >= 1`), a bare literal in v1",
        "one level of four corner retries, at most once per window",
    ),
    AdmissionDatum(
        "max_lower_hints", "carried", MAX_LOWER_HINTS,
        "model.py:21 (MAX_LOWER_HINTS)",
        "donor-footing hint portfolio cap; over-budget refuses the whole "
        "route, never a prefix.  R10 keeps 8 as the push-model retention",
    ),
    AdmissionDatum(
        "stage_a_min_visible_sites", "carried", 90,
        "src/holo/receive/words.py:245 (the bare `< 90` visibility gate)",
        "Stage-A per-phase visibility floor on the 100 word sites; the "
        "historical try_bch_seed decoded hard samples first and applied "
        "only this floor to the surviving candidate",
    ),
)


def admission_datum(name: str) -> AdmissionDatum:
    """Return one OR-9 row by name (the table is the constant's home)."""
    for datum in OR9_FLOORS:
        if datum.name == name:
            return datum
    raise KeyError(f"no admission datum named {name!r}")
