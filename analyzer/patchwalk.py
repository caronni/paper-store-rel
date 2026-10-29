"""The self-discovery walk, per POPULATION — W8 B7 plus W1-W4 (2026-09-07).

BLIND, and free of every analyzer module but :mod:`analyzer.autoknobs`
(the walk), :mod:`analyzer.walkeval` (its objective) and
:mod:`analyzer.patchcache` (the block widths).  Nothing here may import
:mod:`analyzer.truth`, :mod:`analyzer.oracle` or :mod:`analyzer.score`,
and nothing here imports :mod:`analyzer.patch` — that module dispatches
into this one.

`analyzer.patch` reached DESIGN §0.4's 1000-line cap again when the
HALO-CHANNEL-2026-09-07 build landed, so the layer that chooses ONE
population's filter axes moved here.  It is a move, not a rewrite: the
per-population walk is B7's, and the three things around it are the
ruling's —

* **W1** the walk's held-out losses may be importance-weighted to the
  target tile's own cargo (`analyzer.walkeval.cargo_weights`);
* **W2** THE FRANCHISE — a population whose own search fold cannot carry
  the vote inherits a DISCOVERY (the pooled, state-agnostic walk, run
  once and memoised) and not a module constant.  Measured on sheet H at
  halo 16, 674 of 3,186 three-ink populations (21 %) took the pin and
  `auto_choices` recorded it as if it were a choice; `auto_source` is
  what makes those two countable apart;
* **W3** on the NESTED channel axis the burden of proof sits on the
  leaner side (`autoknobs.choose(nested=...)`).

W4, the regulariser's move from the end of the coordinate pass to an
inner minimisation under every candidate, is `autoknobs.choose`'s and is
not optional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from . import autoknobs
from . import patchcache
from . import walkeval
from .patchgrid import PatchError

__all__ = ["AutoLedger", "WalkContext", "choose_axes", "own_axes",
           "pooled_axes"]

#: The tag the pooled (state-agnostic) walk is recorded under.  It is the
#: tier's own name, and W2's franchise borrows that tier's walk.
POOLED_TAG: str = "agnostic"


class AutoLedger:
    """The small dicts one `patch_score` call leaves in the blind detail.

    Small ON PURPOSE: a handful of numbers per population.  The filter
    WEIGHTS never leave `analyzer.patch` (a 3,072-float vector per (lane,
    state, arm) would be copied verbatim into every ledger row).
    """

    def __init__(self) -> None:
        self.choices: dict[str, Any] = {}
        self.losses: dict[str, Any] = {}
        self.refused: dict[str, Any] = {}
        self.detail: dict[str, Any] = {}
        self.verdicts: dict[str, Any] = {}

    def record(self, tag: str, axes: Mapping[str, Any],
               losses: Mapping[str, Any], detail: Mapping[str, Any],
               source: str, axis_names: tuple[str, ...]) -> None:
        """One population's choice, its candidate losses and HOW it chose.

        WHAT THIS USED TO DROP (HALO-CHANNEL §2.2, §4.3).  A pooled count
        over `auto_choices` read an INHERITANCE as a choice — the
        record's "the search picks red 85 % of the time on the three-ink
        state" was 2,047 votes plus 674 inheritances.  `auto_source` is
        the field that separates them, and `auto_verdicts` is the paired
        test itself, so a reader can also count the 1,033 populations
        that measured `rgb` better and refused it.
        """
        if not axis_names:
            return
        self.choices[tag] = {name: axes[name] for name in axis_names}
        if losses:
            self.losses[tag] = dict(losses)
        if detail.get("refused"):
            self.refused[tag] = str(detail["refused"])
        verdicts = detail.get("verdicts") or {}
        if verdicts:
            self.verdicts[tag] = {
                str(label): {key: got.get(key) for key in
                             ("mean_difference", "standard_error", "ess",
                              "n", "adopted")}
                for label, got in verdicts.items()}
        weighting = dict(detail.get("walk_weights") or {})
        self.detail[tag] = {
            "auto_source": str(source),
            "n_walk_labels": int(detail.get("n_walk_labels", 0)),
            "adopted": dict(detail.get("adopted") or {}),
            "baseline_logloss": detail.get("baseline_logloss"),
            "inner": dict(detail.get("inner") or {}),
            "walk_ess": weighting.get("ess"),
            "walk_bins": weighting.get("n_bins"),
            "walk_unmatched": weighting.get("unmatched_cargo_fraction"),
            "walk_weighting_refused": weighting.get("refused")}


@dataclass
class WalkContext:
    """Everything one `patch_score` call's walks read, gathered once.

    The masks are the call's own (`known_target & observed & inside` is
    the row set every candidate is trained and scored on, cut at the
    walk's WIDEST geometry so the paired test is genuinely paired), and
    `pooled` is W2's memo: the state-agnostic walk, run at most once.
    """

    spec: Any
    bank: Any
    inherited_axes: Mapping[str, Any]
    axis_names: tuple[str, ...]
    walk_order: tuple[str, ...]
    inner_axis: str | None
    known_target: np.ndarray
    observed: np.ndarray
    inside: np.ndarray
    word: np.ndarray
    search: np.ndarray
    values: np.ndarray
    state: np.ndarray
    half: np.ndarray
    sel_index: np.ndarray
    agnostic_rows: np.ndarray
    pitch_px: float
    n: int
    profile: walkeval.CargoProfile | None = None
    pooled: list = field(default_factory=list)


def own_axes(ctx: WalkContext, mine: np.ndarray, rows_train: np.ndarray, *,
             tag: str, exclude_word: bool) -> tuple[dict, dict, dict]:
    """The run's OWN filter axes for one population (W8 B7).

    Every candidate is cross-fitted on this population's fit-fold rows,
    its out-of-fold scores fit a PAVA map and the map prices this
    population's SEARCH-fold labels; `autoknobs.choose` then walks the
    axes once, adopting only what clears the paired standard-error
    margin.  Nothing but the halo's own labels is in play — no local5
    rows, no pseudo rows, no self-training — so every candidate is judged
    on the same footing and the choice is not a vote about the extra
    label sets.

    THE FOLD (review 2026-09-06).  This walk MINIMISES, and DESIGN §4.8
    reserves the search fold for exactly that: "an offset chosen here has
    not seen the fold the arm choice is made on".  It used to score on
    the select fold, which `calibrate.select_arm` then paired arms on and
    `combine`'s `platt`/`best` then fitted lane weights on — so an auto
    arm's `label_llr` was a minimum over its own candidate set on
    precisely those rows.  It is the search fold's now, and `select_arm`
    refuses to report an auto arm's `heldout_logloss_search` as nested CV
    for the same reason it refuses a searching register arm's.

    THE OBJECTIVE (HALO-CHANNEL §3(b)).  Those search-fold labels are the
    halo's, and the halo's cells are 4.3-4.8x EASIER than the dead band's
    three-ink cargo the filter will price.  Under `walk_weighting=cargo`
    the per-label losses are importance-weighted onto the target tile's
    own cargo before they are paired.
    """
    if not ctx.axis_names:
        return dict(ctx.inherited_axes), {}, {}
    eval_mask = (ctx.known_target & ctx.observed & ctx.inside & mine
                 & ctx.search)
    if exclude_word:
        eval_mask = eval_mask & ~ctx.word
    rows_eval = np.flatnonzero(eval_mask)
    detail: dict[str, Any] = {}
    if not autoknobs.minority_ok(ctx.values[rows_eval]):
        return dict(ctx.inherited_axes), {}, {"refused":
                                              "below_minority_floor"}
    train_pos = ctx.sel_index[rows_train]
    eval_pos = ctx.sel_index[rows_eval]
    if np.any(train_pos < 0) or np.any(eval_pos < 0):
        return dict(ctx.inherited_axes), {}, {"refused":
                                              "rows_outside_the_selection"}
    train_labels = ctx.values[rows_train]
    eval_labels = ctx.values[rows_eval]
    train_half = ctx.half[rows_train]

    def evaluate(axes: Mapping[str, Any]) -> np.ndarray | None:
        # W8 B8: the normal equations are built once per (population,
        # cross-fit half) at the walk's widest geometry and SLICED for
        # this candidate, so a coordinate pass costs one `gemm` per half
        # rather than three per candidate
        try:
            oof, full = autoknobs.crossfit_selection(
                ctx.bank, axes, tag, train_pos, train_labels, train_half,
                shrinkage=float(axes["shrinkage"]))
        except PatchError:
            return None
        block, _ins = ctx.bank.selection(axes)
        scored = autoknobs.apply_discriminant(
            np.asarray(block[eval_pos], np.float64), full)
        return autoknobs.select_losses(oof, train_labels, scored, eval_labels)

    #: W1: this halo's histogram over (sibling state, difficulty) moved
    #: onto the TARGET TILE's own cargo.  `pooled` for the state-agnostic
    #: tier — the one that pools sibling states; a per-state walk has the
    #: state exactly right already and matches difficulty inside it.
    weights = None
    if ctx.profile is not None:
        weights, weight_detail = walkeval.cargo_weights(
            ctx.profile, state_of_row=ctx.state[rows_eval],
            z_of_row=ctx.profile.z[rows_eval],
            pooled=bool(tag == POOLED_TAG))
        detail["walk_weights"] = weight_detail
    #: W3: `red` is literally `rgb`'s first 144 columns, so on THAT axis
    #: the richer candidate is adopted unless the leaner one clears the
    #: bar.  Window and samples keep ties-to-inherited: the matrix that
    #: argues for the flip isolated one axis, and ties-go-richer
    #: everywhere would run the walk to 3,072 features on ~200 labels.
    nested = ({"channels": autoknobs.CHANNEL_CANDIDATES}
              if ctx.spec.walk_direction == _NESTED else None)

    def inner_ladder(axes: Mapping[str, Any]) -> tuple[float, ...]:
        """W4's ladder for ONE candidate, at its OWN feature count."""
        return autoknobs.shrinkage_ladder(
            int(rows_train.size),
            patchcache.block_width(axes, ctx.pitch_px))

    axes, losses, walk = autoknobs.choose(
        ctx.inherited_axes,
        {name: autoknobs.CANDIDATES[name] for name in ctx.axis_names},
        evaluate, order=ctx.walk_order, weights=weights, nested=nested,
        inner_axis=ctx.inner_axis, inner_candidates=inner_ladder)
    detail.update(walk)
    detail["n_walk_labels"] = int(rows_eval.size)
    detail["walk_fold"] = "search"
    return axes, losses, detail


#: `patchspec.WALK_DIRECTION_NESTED` / `WALK_FRANCHISE_POOLED`, spelled
#: here so this module does not import the one that builds the spec
#: (`patchspec` imports `autoknobs`, which this module also imports; the
#: two strings are pinned equal by a test).
_NESTED: str = "nested-richer"
_POOLED: str = "pooled"


def pooled_axes(ctx: WalkContext) -> tuple[dict, dict, dict]:
    """The state-agnostic walk, computed at most ONCE per `patch_score`.

    It is the tier at step 6's own walk, hoisted so W2's franchise can
    consult it before the per-state tiers are fitted.  Under
    `walk_franchise=pooled` — the SHIPPED value — a refused per-state
    walk consults it early, so it runs at the first refusal instead of
    at step 6 and the tier there reuses this memo; under `inherit`
    nothing consults it early and the call order is what it was.
    (2026-09-07 review: this said the opposite, naming `inherit` as the
    shipped value — it was `patchspec`'s default when the module was
    written and §5's isolation flipped it the same day.)
    """
    if not ctx.pooled:
        ctx.pooled.append(own_axes(ctx, np.ones(ctx.n, bool),
                                   ctx.agnostic_rows, tag=POOLED_TAG,
                                   exclude_word=False))
    return ctx.pooled[0]


def choose_axes(ctx: WalkContext, mine: np.ndarray, rows_train: np.ndarray,
                *, tag: str, exclude_word: bool,
                ) -> tuple[dict, dict, dict, str]:
    """:func:`own_axes` with W2's franchise behind it; `source` says which.

    `own` — the population walked its own search fold.  `pooled` — it
    could not (below `calibrate.SELECT_MIN_MINORITY` of its own labels)
    and took the axes of the POOLED walk, which is a discovery on this
    object under the same weighting.  `inherited` — neither could, and
    the module constants stand, which is the only branch that is a pin.
    """
    if not ctx.axis_names:
        return dict(ctx.inherited_axes), {}, {}, "inherited"
    if tag == POOLED_TAG:
        axes, losses, detail = pooled_axes(ctx)
        return (axes, losses, detail,
                "inherited" if detail.get("refused") else "own")
    axes, losses, detail = own_axes(ctx, mine, rows_train, tag=tag,
                                    exclude_word=exclude_word)
    if not detail.get("refused"):
        return axes, losses, detail, "own"
    if (str(ctx.spec.walk_franchise) != _POOLED
            or detail.get("refused") != "below_minority_floor"):
        return axes, losses, detail, "inherited"
    axes_pooled, _losses_pooled, detail_pooled = pooled_axes(ctx)
    if detail_pooled.get("refused"):
        return (axes, losses,
                {**detail, "pooled_refused": str(detail_pooled["refused"])},
                "inherited")
    #: the pooled walk's LOSSES are published once, under its own tag; a
    #: population that inherited them says so in `auto_source`.
    #:
    #: THE INHERITED RIDGE IS KNOWINGLY THE POOLED POPULATION'S
    #: (2026-09-07 review).  `axes_pooled` is a package — geometry,
    #: channels, feature kind AND the regulariser W4 minimised — and the
    #: pooled walk chose all four at its own `n_fit_rows`, roughly four
    #: times this population's.  Re-minimising the ridge here is not
    #: available: this population is here precisely because its own
    #: search fold cannot carry a paired verdict (`minority_ok`
    #: refused), so it has nothing to minimise on, and a RULE that
    #: adjusted the inherited ridge by the row ratio would be a pin of
    #: the kind §4.0 forbids.  It inherits the whole discovery or
    #: nothing; `auto_source="pooled"` is what makes the two countable
    #: apart, and HALO-CHANNEL §6 carries it as open.
    return (dict(axes_pooled), {},
            {**detail, "pooled_adopted": dict(detail_pooled.get("adopted")
                                              or {})},
            "pooled")
