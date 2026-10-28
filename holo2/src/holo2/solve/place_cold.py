"""The cold tier's two flavours: the fire, its page set, and its lease.

H4 W4. The carried kernel (:mod:`holo2.solve.cold`) is bit-exact-pinned
and NOT TOUCHED by this module; what lives here is everything the pull
model needs to SCHEDULE one — the page set a flavour sweeps, the residency
declaration a fire makes while it holds its transforms, and the one
function that turns an accepted correlation into an address the ordinary
fit-and-validate path can re-derive from pixels.

WHY IT IS ITS OWN MODULE. ``place_job`` owns the ladder; this owns cold's
own vocabulary, which is a different subject with a different shape — a
page-set consult, a leased resource with a lifetime, and a kernel call.
Folding it into the job would have pushed that file toward its cap for no
gain in cohesion (the cap is a seam signal, not a budget).

WHAT A COLD FIRE IS, IN THE PULL MODEL'S TERMS
-----------------------------------------------
A claim, a fire-time consult, a sweep, and a PROPOSAL. Cold never commits
a pose: :func:`cold_address` hands back the same
``(page, rot_k, origin_yx)`` triple the word route hands back, and the
job runs it through ``place_shared.place_addressed`` — E022's bounded
refinement, the re-read, the binomial-impurity straddle audit — exactly
as it would an address any other tier reached. So the FFT is
scheduling-class arithmetic, not evidence-class: nothing it computes
reaches a certificate except by way of a pose that was re-derived from
pixels and audited afterwards. That is what lets the FFT card (a later,
measured wave) consider a faster transform at all.

PER-ITEM DETERMINISM, AND THE ONE DEPENDENCE THAT IS DECLARED. Given the
same patch, the same page set and the same budget, the kernel returns the
same proposal on every run. What is NOT schedule-independent is the SET:
``live`` is the pages with a committed pose, so a window firing early
sweeps fewer pages than the same window firing late. That is ruling 4,
accepted and stated: it joins the known pooled-replay residue class,
whose banked fix is freezing the consult at dispatch.

THE TRANSFORM CACHE, AND WHY IT IS PER-FIRE (declared deviation)
----------------------------------------------------------------
The plan asks for the page-transform store to become a shared, refcounted
resource outliving the invocation that built it. It is NOT shared across
fires here, and the reason is a stop condition rather than an oversight:
the carried kernel builds its ``page_transforms`` dict as an invocation
local, so handing one IN needs a new parameter on ``correlate_patch`` —
an edit to the bit-exact-pinned kernel, which this wave was ruled not to
make. (Its own docstring names the seam: "W4 leases this dict from the
engine". Opening it is one keyword-only argument with a defaulted fresh
dict, provably arithmetic-neutral, and it belongs with the FFT card,
where kernel work belongs.)

What IS built is everything around it, at full fidelity: the resource is
NAMED by :func:`cold_transform_key` with the key the shared version
needs, and a fire declares a page-weighted :func:`cold_lease` on it, so
two concurrent colds on one shape appear to the observer as two holders
of one key — which is exactly the residency an admission gate would read.
Retention is the only half deferred, and the deferred half is the one the
plan already deferred a policy for.
"""
from __future__ import annotations

from ..core import Lease, ProgressSink, ResourceKey, key_parts
from ..format import FormatRowSpec
from .cold import correlate_patch
from .place_model import AttemptBudget, PlacementConfig
from .pose_audit import ScoreMemo
from .pose_fit import AddressPatch
from .reference import ReferenceFieldProvider
from .view import PlaneView

#: THE TWO FLAVOURS, spelled here because this module derives their page
#: sets and ``place_sched`` prices them: they are the tier names, so one
#: string is the schedule's word and the fire's word at once.
FLAVOR_LIVE = "cold_live"
FLAVOR_REST = "cold_rest"

#: The leased resource's kind. It is not a durable record kind — nothing
#: under it is ever written — but it is a ``ResourceKey`` because that is
#: what ``core.Lease`` names and what the observer renders.
KIND_COLD_TRANSFORMS = "cold-transforms"

#: How a swept page is remembered in the window's tried set. PAGE
#: granularity is the ruled dedup and it is enough: the two flavours
#: partition the domain at any instant, but ``live`` GROWS, so a page
#: swept by an earlier rest fire can reappear in a later live set — and
#: this is what keeps a window from paying for the same page twice.
#: ONE namespace for both flavours, because a window has one rung, and a
#: page swept at that rung was swept whichever flavour paid for it.
TRIED_COLD = "cold-page"


def cold_tried_id(page: int) -> str:
    """This window's tried-set element for one swept page."""
    return f"{TRIED_COLD}/{int(page)}"


# ---------------------------------------------------------- the page sets

def live_pages(view: PlaneView) -> frozenset[int]:
    """THE PAGES THIS SESSION ALREADY HAS A COMMITTED POSE ON.

    Derived, never stored, and asked of the producer rather than of an
    operator: a pose is the earliest page-anchored durable fact this
    receiver has — certificates corroborate it, but a pose alone already
    says a page reached the platen — so this generalises the e029
    scheduler observation ("--page 0 for single-sheet volumes would
    collapse the 133-page cold domain") from a flag into a fact the
    session can look up.

    MONOTONE, because a pose is identity-frozen: the set only grows, which
    is what lets a caller memoise it on the pose COUNT alone
    (``place_sched``) and what makes ruling 2's "it might fill later" a
    property rather than a hope.
    """
    return frozenset(int(record.page) for record in view.index().poses.values())


def cold_pages(row: FormatRowSpec, flavor: str,
               live: frozenset[int]) -> tuple[int, ...]:
    """One flavour's page set, in the row's own declared order.

    The two are a PARTITION of the declared domain — ``live`` is the
    domain intersected with the poses, ``rest`` is the remainder — so the
    pair sweeps every page exactly once and neither flavour has to know
    what the other did. A pose on a page outside the row's domain steers
    nothing here: this run may only address the pages its row declares.

    On a single-sheet volume this is the degenerate case the ruling
    predicts: after the first pose ``live`` is the whole domain and
    ``rest`` is empty, so the full sweep is never scheduled at all.
    """
    domain = row.page_domain
    if flavor == FLAVOR_LIVE:
        return tuple(page for page in domain if page in live)
    return tuple(page for page in domain if page not in live)


def cold_transform_key(provider: ReferenceFieldProvider,
                       pages: tuple[int, ...],
                       patch_shape: tuple[int, int]) -> ResourceKey:
    """Name the transform store one cold fire works in.

    THREE TERMS, AND THE FIRST IS A WIDENING (the page-invariance
    question, answered). v1's invariant — ``search.py:536-540``, carried
    verbatim into ``cold.py``'s page loop — is that every page of ONE
    invocation presents the same site mask, checked with ``np.array_equal``
    and raised on. That check is PRESERVED exactly as carried, and it is
    why the kernel's inner key ``(page, pad_y, pad_x, fshape)`` needs no
    site identity. It is also scoped to one sweep, so it cannot by itself
    name a store two sweeps might share: two invocations under different
    reference fields would agree page for page and disagree about what a
    page IS. So the key is WIDENED with the reference field's own printed
    interpretation — the spec values every page's ``values`` and ``sites``
    are generated from (``V1ReferenceField._key``'s own terms). Both, not
    either: the carried check guards within a sweep, the widening across
    them.

    WHAT IS DELIBERATELY NOT A TERM: the FOOTING. The plan's key names
    one, on the arithmetic that a coarse rung shrinks every page transform
    by the scale squared — true of a PIXEL-space correlation, which this
    is not. The carried kernel correlates in the page's CELL lattice:
    ``search_sites`` is the reference field's ``cells_yx`` and the padding
    is the patch's extent in CELLS, both of which a region shares across
    every footing of its capture (``geometry`` convention 2). The
    transforms are therefore rung-INVARIANT; a footing term would fragment
    one shareable store into one per lane, and the memory consequence runs
    the other way from the plan's hope — no rung pays 1/64th, but every
    rung of every capture shares ONE shape. Recorded as an amendment in
    ``H4-W4-PLAN.md`` rather than followed silently.
    """
    spec = provider.spec
    return ResourceKey(KIND_COLD_TRANSFORMS, key_parts(
        spec.seed.hex(), spec.family_seed.hex(), int(spec.plane),
        spec.cells_yx[0], spec.cells_yx[1], int(spec.n_filler),
        ",".join(str(page) for page in pages),
        patch_shape[0], patch_shape[1]))


def cold_lease(key: ResourceKey, pages: int) -> Lease:
    """The residency declaration one cold fire holds while it runs (M5).

    WEIGHTED BY PAGES, because that is what the store's size is
    proportional to — one padded transform per page and padding group —
    and a refcount of fires would tell an observer nothing about memory.

    It is a DECLARATION and not yet a budget. The book that would gate on
    it exists (``core.LeaseBook``, taken at arm and released at disarm)
    and its residency is published to the diag snapshot; what does not
    exist is a policy, because inventing one before a measured run shows
    concurrent colds actually colliding on memory would be a fabricated
    default. The sentence that lands if measurement demands one is fixed
    in advance: a cold fire consults residency BEFORE its claim and
    declines cheaply, rather than blocking a slot while holding one.
    """
    return Lease(key, weight=max(1, int(pages)))


# ------------------------------------------------------------------ the fire

def cold_address(patch: AddressPatch, provider: ReferenceFieldProvider,
                 pages: tuple[int, ...], budget: AttemptBudget, *,
                 config: PlacementConfig, progress: ProgressSink,
                 ) -> tuple[int, int, tuple[int, int]] | None:
    """Sweep ``pages`` with the carried kernel; PROPOSE an address or not.

    The kernel's own gates decide, and this function adds none of its own:
    the attempt-budget refusal, the page-invariant support floor, the
    held-out validation gate and the whole-word rival bar are all inside
    ``correlate_patch``. What happens here is the conversion of an
    ACCEPTED outcome into the triple the ladder speaks — the same shape
    ``decode_word_address`` returns, and ``None`` for every refusal.

    THE BUDGET IS THE FULL DOMAIN'S, not this flavour's (``place_sched``
    hands it ``budgets.cold``): the declared envelope is resolved over the
    row's WHOLE page domain, so a live-only or rest-only sweep attempts
    strictly fewer hypotheses than were declared. That is the union
    bound's own direction — the declaration must dominate the attempts —
    and it means the derived support floor is the strictest one, never
    loosened by a flavour's set happening to be small. It is also why the
    two flavours need no budget arithmetic of their own.

    THE HEARTBEAT IS WHAT MAKES A PAGE-BATCHED SWEEP LEGAL under the
    no-silent-stages contract (§10.3): the kernel calls back at
    count-bounded points of the page loop, at most 64 times per sweep, and
    each one is a progress quantum. So the quanta chunk per page batch,
    which is the shape the plan carried forward unchanged.
    """
    outcome = correlate_patch(
        patch, provider, pages, budget, ScoreMemo(provider),
        sample_key=0, config=config,
        page_progress=lambda _done, _total: progress.emit(1, "cold-sweep"))
    progress.emit(1, "cold-search")
    if not outcome.accepted or outcome.best is None:
        return None
    best = outcome.best
    return (int(best.page), int(best.rot_k), best.origin_yx)


__all__ = [
    "FLAVOR_LIVE", "FLAVOR_REST", "KIND_COLD_TRANSFORMS", "TRIED_COLD",
    "cold_address", "cold_lease", "cold_pages", "cold_transform_key",
    "cold_tried_id", "live_pages",
]
