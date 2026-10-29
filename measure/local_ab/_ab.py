"""The two arms, over one frozen store.

Both arms consume THE SAME components — the per-lane `TileCut`s
`tiles.local` already builds — so the comparison is exactly the one the
mission asks: given the lanes that cover a failed tile, is it better to
sum them into one attempt, or to attempt each on its own?

    UNION              one `tiles.attempt_tile` over every component;
                       the cuts are summed by `tiles._combine`.

    PER-ORIGIN         one `tiles.attempt_tile` per component, same
                       stage (`STAGE_LOCAL150`), so the same 150-iteration
                       BP budget. Mirrors what `tiles.retry` does with a
                       failed attempt's origin.

    ROW                `local_ctx.prepare_local` itself (`run_row`).
                       Since the hybrid landed 2026-08-31 the row is
                       UNION-THEN-LANES: the union attempt first, and on
                       its failure each covering lane alone, stopping at
                       the first certificate. The A/B is what decided
                       that shape; `run_row` is what replays it.

    N0 (null)          the union arm's own components RE-LABELLED to a
                       neighbouring tile address. Same pixels, same
                       calibration, wrong address: the address-bound slot
                       permutation, dither and CRC must refuse it. A
                       certificate here would mean the harness can
                       manufacture one, and the battery is void.

NOTHING IS FED BACK. Neither arm's certificates enter the store, so no
subject is ever helped by another subject's win and the two arms see
byte-identical evidence. Both yields are therefore LOWER BOUNDS on what
a scheduled production stage would reach — equally, so the comparison
between them is unaffected.

THE ARMS ARE NOT REIMPLEMENTATIONS. Both run on components from
`local_ctx._color_lane_plans` + `local_ctx._color_components` — i.e.
`local_ctx._prepare_color`'s body, in order — and both attempt through
`tiles.attempt_tile` at the row's own stage. That claim is CHECKED
rather than asserted: :func:`verify_row` runs
`local_ctx.prepare_local` itself — the callable the engine would have
dispatched — on the same subjects and compares its verdict to the arms'
union (`harness._agrees`).

(`SubjectResult.recorded` reads `store.attempt_outcome` for the same
attempt key. The harness detaches the row from the decode, so it is
normally `None`; it stays because it is free and because a non-`None`
value would mean the row DID run and its verdict must match.)
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, replace as dc_replace
from fractions import Fraction

import numpy as np

from holo.receiver.data import AttemptFact, Certificate, TileOutcome
from holo.receiver.format.identity import Family
from holo.receiver.plugins import local_ctx, tiles

STAGE_LOCAL = local_ctx.STAGE_LOCAL

#: Certificates are compared at USER BITS, upstream of every permutation.
Address = tuple[int, int, int, str]


@dataclass(frozen=True)
class Subject:
    """One (tile, stream, rung) the local row would be armed on."""

    page: int
    ty: int
    tx: int
    stream_id: str
    ppc: Fraction
    lanes: tuple[tuple[str, int], ...]

    @property
    def address(self) -> Address:
        return (self.page, self.ty, self.tx, self.stream_id)

    @property
    def key(self) -> tuple[int, int, int, str, str]:
        return (self.page, self.ty, self.tx, self.stream_id, str(self.ppc))


@dataclass(frozen=True)
class ArmOutcome:
    """One arm on one subject."""

    certified: bool
    cpu_seconds: float
    #: per-attempt (label, outcome, n_iters, thread seconds); one row
    #: for the union arm, one per lane for the per-origin arm.
    attempts: tuple[tuple[str, str, int, float], ...]
    #: the certificate's user bits, when the arm minted one.
    bits: np.ndarray | None
    #: the per-origin arm's winning lane label, if any.
    winner: str | None
    #: the null arm's deliberately wrong address.
    address: Address | None = None


@dataclass(frozen=True)
class SubjectResult:
    subject: Subject
    n_components: int
    component_signature: tuple[tuple[str, int], ...]
    build_cpu_seconds: float
    union: ArmOutcome
    per_origin: ArmOutcome
    null: ArmOutcome
    #: the decode's own `tiles.local` verdict on the identical attempt,
    #: when it ran one; `None` when the row never fired this attempt.
    recorded: str | None


def lane_label(lane: tuple[str, int]) -> str:
    return f"{lane[0][:8]}/L{lane[1]}"


def ppc_values(store: object) -> tuple[Fraction, ...]:
    """Every rung the store carries, finest first."""
    seen: set[Fraction] = set()
    for capture_id in store.captures():
        for level in store.capture(capture_id).levels:
            seen.add(level.ppc)
    return tuple(sorted(seen, reverse=True))


def armed_addresses(events: Sequence[object]) -> frozenset[Address]:
    """Addresses an ORDINARY attempt has already failed on.

    `local_ctx._local_subjects` arms the row on a failed `AttemptFact`
    whose stage is one of `ARMING_STAGES` — scan, union, retry150 — so
    that, and not merely "uncertified", is the production population.
    The distinction matters whenever the decode did not run to
    exhaustion: an address nothing has attempted yet is not residue, it
    is unfinished work, and letting it into the population would measure
    the arms on tiles the ordinary path might still have won.
    """
    sources = {tiles.source_tag(stage) for stage in local_ctx.ARMING_STAGES}
    return frozenset(
        (int(event.page), int(event.ty), int(event.tx), str(event.stream_id))
        for event in events
        if isinstance(event, TileOutcome)
        and str(event.source) in sources
        and str(event.result) == tiles.OUTCOME_FAILED)


def subjects(store: object, positions: tuple[tuple[int, int], ...],
             armed: frozenset[Address],
             page: int = 0) -> tuple[tuple[Subject, ...], dict]:
    """Residue tiles the local row's own eligibility reaches, and a census.

    The gate is `local_ctx._local_eligible` verbatim — the tile-LANE
    subject the row has carried since 2026-09-21, so the gate is asked
    once per tile-lane and this measurement's per-STREAM population is
    filtered by `local_ctx.armed_streams` — plus `armed`, the row's own
    arming condition from the event stream (see
    :func:`armed_addresses`), plus the one condition this measurement
    adds: the rung must be covered by MORE THAN ONE LANE, because a
    single-lane subject has no union to lose to.

    The census says why the residue that did NOT arm did not, per rung.
    A population this measurement never reaches is a fact about the
    material, and it is reported rather than silently absent.
    """
    out: list[Subject] = []
    census: dict[str, dict[str, int]] = {}
    for ppc in ppc_values(store):
        counts = {"uncertified": 0, "never_attempted": 0, "no_lane": 0,
                  "one_lane": 0, "ineligible_empty_reach": 0,
                  "ineligible_no_certified_neighbour": 0, "kept": 0}
        for ty, tx in positions:
            for stream in store.row.streams:
                lane_subject = (page, ty, tx, ppc)
                if store.has_certificate((page, ty, tx, stream.stream_id)):
                    continue
                counts["uncertified"] += 1
                if (page, ty, tx, stream.stream_id) not in armed:
                    counts["never_attempted"] += 1
                    continue
                lanes = store.cover_lanes(page, ty, tx, ppc)
                if not lanes:
                    counts["no_lane"] += 1
                    continue
                if len(lanes) < 2:
                    counts["one_lane"] += 1
                    continue
                if (not local_ctx._local_eligible(store, lane_subject)
                        or stream.stream_id not in local_ctx.armed_streams(
                            store, page, ty, tx, ppc)):
                    reach = local_ctx.neighbourhood_tiles(
                        store, page, ty, tx, ppc)
                    counts["ineligible_empty_reach" if not reach
                           else "ineligible_no_certified_neighbour"] += 1
                    continue
                counts["kept"] += 1
                out.append(Subject(page, ty, tx, stream.stream_id, ppc,
                                   tuple(lanes)))
        census[str(ppc)] = counts
    return tuple(out), census


def probe_subjects(store: object, positions: tuple[tuple[int, int], ...],
                   limit: int, page: int = 0) -> tuple[Subject, ...]:
    """The POSITIVE control: subjects taken from CERTIFIED addresses.

    The arms never consult the target's own certificate — they build a
    local head and decode — so a certified address is a subject whose
    answer is known in advance. Running the machinery there exercises
    every line of this module on material that MUST certify in both
    arms and match ground truth, which is the half a residue population
    cannot test: a residue that fails everywhere is equally consistent
    with a correct harness and a broken one.
    """
    out: list[Subject] = []
    for ppc in ppc_values(store):
        for ty, tx in positions:
            if len(out) >= limit:
                return tuple(out)
            for stream in store.row.streams:
                if not store.has_certificate((page, ty, tx,
                                              stream.stream_id)):
                    continue
                lanes = store.cover_lanes(page, ty, tx, ppc)
                if len(lanes) < 2:
                    continue
                out.append(Subject(page, ty, tx, stream.stream_id, ppc,
                                   tuple(lanes)))
                break
    return tuple(out)


def reach_report(store: object, positions: tuple[tuple[int, int], ...],
                 limit: int, page: int = 0) -> list[dict]:
    """Why an uncertified address did or did not arm — the row's own reach."""
    rows: list[dict] = []
    for ppc in ppc_values(store):
        for ty, tx in positions:
            if len(rows) >= limit:
                return rows
            for stream in store.row.streams:
                if store.has_certificate((page, ty, tx, stream.stream_id)):
                    continue
                reach = local_ctx.neighbourhood_tiles(store, page, ty, tx,
                                                      ppc)
                donors = local_ctx.certified_neighbours(
                    store, page, reach, (ty, tx))
                k_wids, color_keys = (), ()
                for lane in store.cover_lanes(page, ty, tx, ppc):
                    k, c = store.tile_cover((page, ty, tx, lane[0], lane[1]))
                    k_wids = k_wids + k
                    color_keys = color_keys + c
                rows.append({
                    "ty": ty, "tx": tx, "stream": stream.stream_id,
                    "ppc": str(ppc), "n_reach_tiles": len(reach),
                    "reach": [list(item) for item in reach[:12]],
                    "n_certified_neighbours": len(donors),
                    "n_k_windows": len(k_wids),
                    "n_color_rows": len(color_keys)})
                break
    return rows


def build_components(store: object, subject: Subject,
                     ) -> tuple[list[tiles.TileCut], float]:
    """`local_ctx._prepare_color`'s body: the per-lane cuts, and its CPU.

    This is the expensive half — one `color_region.region_job` per lane,
    the whole colour head re-fitted over the covering windows alone — and
    BOTH arms consume its output unchanged, so it is charged once and
    reported separately from either arm's decode cost.
    """
    if store.row.family is Family.K:
        raise SystemExit(
            "local_ab: the K arm is out of scope — this measurement is "
            "about multi-capture COLOUR material, where one lane's cut is "
            "a whole locally re-fitted head")
    plans = local_ctx._color_lane_plans(
        store, subject.page, subject.ty, subject.tx, subject.ppc)
    certificates = store.certificates()
    started = time.thread_time()
    components = local_ctx._color_components(
        store.row, store.geometry, plans, certificates,
        subject.page, subject.ty, subject.tx)
    return components, time.thread_time() - started


def _certificate_of(facts: tuple[object, ...]) -> Certificate | None:
    for fact in facts:
        if isinstance(fact, Certificate):
            return fact
    return None


def run_union(store: object, subject: Subject,
              components: list[tiles.TileCut]) -> ArmOutcome:
    """The row's FIRST attempt: one `tiles.attempt_tile` over every lane.

    Until 2026-08-31 this called `local_ctx._attempt` whole, because
    that was one attempt over every component and nothing else. The
    hybrid changed `_attempt` into union-then-lanes, so calling it here
    would make this arm the hybrid and the A/B vacuous. What the union
    arm is has not changed at all — the same single `attempt_tile` over
    the same components at the same stage — so the arm is written out
    rather than borrowed, and `run_row` is what exercises the row.
    """
    started = time.thread_time()
    result = tiles.attempt_tile(store.row, store.geometry, tuple(components),
                                subject.stream_id, tiles.STAGE_LOCAL150)
    spent = time.thread_time() - started
    return ArmOutcome(certified=result.certificate is not None,
                      cpu_seconds=spent,
                      attempts=((f"union:{len(components)}",
                                 str(result.event.result),
                                 int(result.event.bp_iters),
                                 round(spent, 4)),),
                      bits=(None if result.certificate is None
                            else np.asarray(result.certificate.user_bits)),
                      winner=None)


def run_per_origin(store: object, subject: Subject,
                   components: list[tiles.TileCut]) -> ArmOutcome:
    """One attempt per covering lane, same stage and BP budget.

    Every lane is attempted even after one certifies: the extra decodes
    cost a few seconds and they are what says whether the winner was the
    only lane that could, or one of several. The report prices BOTH
    exhaustion and first-certificate stopping from these rows.
    """
    rows: list[tuple[str, str, int, float]] = []
    bits: np.ndarray | None = None
    winner: str | None = None
    # `local_ctx.lane_order` — the row's own order since the hybrid, and
    # the same order this arm always walked (sorted on capture_id), now
    # named once instead of twice.
    for cut in local_ctx.lane_order(components):
        started = time.thread_time()
        result = tiles.attempt_tile(store.row, store.geometry, (cut,),
                                    subject.stream_id, tiles.STAGE_LOCAL150)
        spent = time.thread_time() - started
        label = lane_label((cut.capture_id, cut.level_index))
        rows.append((label, str(result.event.result),
                     int(result.event.bp_iters), round(spent, 4)))
        if result.certificate is not None and bits is None:
            bits = np.asarray(result.certificate.user_bits)
            winner = label
    return ArmOutcome(certified=bits is not None,
                      cpu_seconds=sum(row[3] for row in rows),
                      attempts=tuple(rows), bits=bits, winner=winner)


def run_null(store: object, subject: Subject,
             components: list[tiles.TileCut]) -> ArmOutcome:
    """The union arm's evidence, re-labelled to a neighbouring address.

    Same pixels, same local head, same combining — only the tile address
    moves by one column. The slot permutation, the dither and the CRC are
    all address-bound, so this must certify NOTHING.
    """
    tiles_y, tiles_x = store.row.tiles_yx
    wrong_tx = subject.tx + 1 if subject.tx + 1 < tiles_x else subject.tx - 1
    if not 0 <= wrong_tx < tiles_x or not components:
        return ArmOutcome(False, 0.0, (), None, None)
    wrong = (subject.page, subject.ty, wrong_tx, subject.stream_id)
    moved = [dc_replace(cut, tx=wrong_tx) for cut in components]
    started = time.thread_time()
    result = tiles.attempt_tile(store.row, store.geometry, tuple(moved),
                                subject.stream_id, tiles.STAGE_LOCAL150)
    return ArmOutcome(
        certified=result.certificate is not None,
        cpu_seconds=time.thread_time() - started,
        attempts=((f"null:tx{wrong_tx}", str(result.event.result),
                   int(result.event.bp_iters),
                   round(time.thread_time() - started, 4)),),
        bits=(None if result.certificate is None
              else np.asarray(result.certificate.user_bits)),
        winner=None, address=wrong)


def measure(store: object, subject: Subject) -> SubjectResult:
    """One subject, both arms and the null, over one frozen store."""
    components, build_cpu = build_components(store, subject)
    signature = tiles.component_signature(components)
    recorded = store.attempt_outcome(tiles.attempt_key(
        subject.page, subject.ty, subject.tx, subject.stream_id,
        tiles.STAGE_LOCAL150, components))
    if not components:
        empty = ArmOutcome(False, 0.0, (), None, None)
        return SubjectResult(subject, 0, signature, build_cpu, empty, empty,
                             empty, recorded)
    return SubjectResult(
        subject=subject, n_components=len(components),
        component_signature=signature, build_cpu_seconds=build_cpu,
        union=run_union(store, subject, components),
        per_origin=run_per_origin(store, subject, components),
        null=run_null(store, subject, components),
        recorded=recorded)


def attempt_label(signature: Sequence[tuple[str, int]]) -> str:
    """Name one attempt by the component set it was made over.

    A signature with more than one lane in it is the union attempt; a
    signature with exactly one is that lane alone. This is how a replay
    tells the two halves of the hybrid row apart after the fact: the
    `AttemptFact` carries `tiles.component_signature`, so the row's own
    facts say which attempt won without the driver having to guess.
    """
    if len(signature) > 1:
        return f"union:{len(signature)}"
    return lane_label(tuple(signature[0]))


def run_row(store: object, subject: Subject) -> ArmOutcome | None:
    """The ROW ITSELF — `local_ctx.prepare_local` — on one subject.

    Not an arm reconstructed here: this is the callable the engine would
    have dispatched, run whole, including its own component build. Its
    `cpu_seconds` therefore covers that build, which the two arms report
    separately; the numbers are not comparable and the report says so.

    `None` means the row REFUSED to prepare — a different answer from
    "prepared and certified nothing", and one a parity check must not
    silently fold into the other.

    Every attempt the row made is recovered from its own facts, so the
    winner is named the same way whether the union won or a lane did.

    Since 2026-09-21 the row's subject is the tile-LANE and one fire
    decodes EVERY armed stream off one build, so the facts are filtered
    to this measurement's stream: the arms are per-stream and the
    comparison must stay so.  The reported `cpu_seconds` is still the
    whole fire's, which is what the row actually costs, and the report
    already says the row's and the arms' CPU are not comparable.
    """
    key = (subject.page, subject.ty, subject.tx, subject.ppc)
    job = local_ctx.prepare_local(store, key, STAGE_LOCAL)
    if job is None:
        return None
    result = job()
    rows: list[tuple[str, str, int, float]] = []
    winner: str | None = None
    for fact in result.facts:
        if not isinstance(fact, AttemptFact):
            continue
        if str(fact.stream_id) != subject.stream_id:
            continue
        label = attempt_label(fact.components)
        rows.append((label, str(fact.outcome), int(fact.n_iters),
                     round(float(result.cpu_s), 4)))
        if fact.outcome == tiles.OUTCOME_CERTIFIED and winner is None:
            winner = label
    certificate = _certificate_of(
        tuple(fact for fact in result.facts
              if not isinstance(fact, Certificate)
              or str(fact.stream_id) == subject.stream_id))
    return ArmOutcome(certified=certificate is not None,
                      cpu_seconds=float(result.cpu_s), attempts=tuple(rows),
                      bits=(None if certificate is None
                            else np.asarray(certificate.user_bits)),
                      winner=winner)


def verify_row(store: object, subject: Subject) -> dict:
    """Run `local_ctx.prepare_local` itself and report what it decided.

    This is the row's PRODUCTION entry point — the callable the engine
    would have run for this subject — so its verdict is the standard the
    arms have to meet. It rebuilds the components from scratch, which is
    why it is sampled rather than run on everything: the check is that
    the arms are the row, and a sample settles that.

    Since the hybrid landed, the row IS the union arm followed on
    failure by the per-origin arm, so its verdict is compared against
    `union or per_origin` — see `harness._agrees`.
    """
    outcome = run_row(store, subject)
    if outcome is None:
        return {"prepared": False}
    return {"prepared": True, "certified": outcome.certified,
            "outcome": outcome.attempts[0][1] if outcome.attempts else None,
            "winner": outcome.winner,
            "n_attempts": len(outcome.attempts),
            "attempts": [list(row[:3]) for row in outcome.attempts],
            "cpu_seconds": round(outcome.cpu_seconds, 3)}


def classify(result: SubjectResult) -> str:
    if result.union.certified and result.per_origin.certified:
        return "both"
    if result.union.certified:
        return "union_only"
    if result.per_origin.certified:
        return "per_origin_only"
    return "neither"
