"""The pass driver — targets to certificates, to a fixed point (DESIGN §6b).

One call, one shape:

    targets -> per lane, the arm battery -> `calibrate.select_arm`
            -> per rule, `combine.combine` -> `ladder.run_ladder`
            -> fold the new certificates into the frame and RE-TARGET
               their 8-neighbourhood and sibling streams -> repeat.

e034 measured 82% of the production plane arm's mints as cascade, chains
seven generations deep, so a single pass is a lower bound several fold
below what the machinery does; every certificate here carries its
`generation` and its `predecessors`.

BLINDNESS (RULING, Germano, 2026-09-04).  Ground truth does not enter
this module at all — not as an argument, not as an import, not as a
verdict.  :func:`blind_key` is the whole decision path: it sees the
certificate mapping, the format row, the pixels and the blind metadata
bit, and it returns evidence, combinations and rung results.  A
gate-passing certificate is `certified` (direct rung) or `certified_list`
(list rung), full stop; the `wrong` / `false_accept` adjudication that
used to live here is the OFFLINE scorer's (`analyzer.score`), which
reads the ledger afterwards.  What the ledger must therefore CARRY for
that scorer is the certified user bits and, per rung, the packed exit
hard vector (`keep_hard`, base64 in `detail["hard_packed_b64"]`)
alongside the blind columns it already had.  An import-set test pins
that no module a run command can reach imports `truth` or `oracle`.

INDEPENDENT AGREEMENT (2026-09-04, leg 4).  Every gate-passing
certificate a key produces is collected with the physical captures its
combination leaned on, and `combine.independent_agreement` says how many
of them rest on DISJOINT captures and agree bit for bit.  Two that
DISAGREE are a contradiction — both passed syndrome and CRC, so one is a
false accept and nothing blind can say which — and the key is REFUSED:
no mint, no cascade, `refusal=independent_certificates_disagree` on the
row.  The row carries `independent_agreement` in `diag` and the ledger
header counts both.

THREADS.  Keys run on a `ThreadPoolExecutor` sharing one snapshot (it is
6.5 GB on sheet I and must never be loaded twice — DESIGN §10).  Results
are merged in the PINNED target order, not in completion order, so the
ledger is worker-count independent; the exposure ledger is one
lock-guarded object, because the bound of DESIGN §0 is a correctness
bound and correctness is not per-thread.

MEMORY.  Crops live inside `arms.evidence_for` and die with it, and the
ledger row keeps per-rung SUMMARIES (plus the 512-byte packed hard
vector), never LLR vectors, unless `config.keep_vectors` asks otherwise.
"""

from __future__ import annotations

import base64
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace as dc_replace
from typing import Any, Callable, Iterator, Mapping, Sequence

import numpy as np

from . import arms as arms_mod
from . import calibrate as cal
from . import combine as combine_mod
from . import frame as frame_mod
from . import inputs as inputs_mod
from . import ladder as ladder_mod
from . import residue as residue_mod
from . import sample as sample_mod
from .types import (PLANE_OF, VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST,
                    VERDICT_OPEN, AnalyzerConfig, Exposure,
                    Key, Ledger, LedgerRow)

#: `L7` on the command line means both erasure rungs (DESIGN §6).
RUNG_ALIASES: dict[str, tuple[str, ...]] = {"L7": ("L7a", "L7b")}

#: A progress tick every this many finished keys of a generation.
PROGRESS_EVERY = 10

#: The status doors: SIGUSR1, and SIGINFO (ctrl-T) where the platform has
#: it.  No stop door — a pass writes its ledger at the end only, and a
#: stop that wrote a partial ledger is a separate line of work.
STATUS_SIGNALS: tuple[int, ...] = tuple(
    getattr(signal, name) for name in ("SIGUSR1", "SIGINFO")
    if hasattr(signal, name))


@contextmanager
def _status_doors(watch: "Progress | None") -> Iterator[None]:
    """Arm the status signals for exactly the pass, and restore them."""
    if watch is not None:
        watch.arm()
    try:
        yield
    finally:
        if watch is not None:
            watch.disarm()


def _hms(seconds: float) -> str:
    whole = int(max(0.0, seconds))
    return f"{whole // 3600}:{whole // 60 % 60:02d}:{whole % 60:02d}"


class Progress:
    """The operator's window on a pass (2026-09-04, after the first machine 4 run
    sat silent for its whole length).

    One line per generation start and end, a tick every `every` finished
    keys with the rate and a remaining-time estimate, and a status line
    on demand from SIGUSR1 or SIGINFO.  Lines go to `emit` (the CLI prints
    them to stderr); a run without a sink is byte-identical, and nothing
    here reaches the ledger.

    The counters are written by the worker threads under `_lock` and read
    by the signal handler WITHOUT it: the handler runs on the main thread,
    which in the serial path is the thread holding the lock inside
    `key_done`, so a locking handler could deadlock the pass it reports
    on.  A status line is therefore a snapshot of plain integers, which
    is all it needs to be.
    """

    def __init__(self, emit: Callable[[str], None], *, n_targets: int,
                 exposure: Exposure | None = None,
                 every: int = PROGRESS_EVERY) -> None:
        self._emit = emit
        self._every = max(1, int(every))
        self._exposure = exposure
        self._lock = threading.Lock()
        self._started = time.perf_counter()
        self._generation_started = self._started
        self._saved: dict[int, Any] = {}
        self.n_targets = int(n_targets)
        self.generation = 0
        self.pending = 0
        self.done = 0
        self.fresh = 0
        self.certified = 0

    # ---------------------------------------------------- the doors
    def arm(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for signum in STATUS_SIGNALS:
            self._saved[signum] = signal.signal(signum, self._on_signal)

    def disarm(self) -> None:
        for signum, handler in self._saved.items():
            signal.signal(signum, handler)
        self._saved = {}

    def _on_signal(self, _signum: int, _frame: object) -> None:
        self._emit(self.status())

    def status(self) -> str:
        exposure = ("" if self._exposure is None else
                    f", exposure {int(self._exposure.distinct):,} distinct")
        return (f"status: generation {self.generation}, "
                f"{self.done}/{self.pending} done, certificates "
                f"{self.certified} (+{self.fresh} this generation)"
                f"{exposure}, elapsed "
                f"{_hms(time.perf_counter() - self._started)}")

    # ------------------------------------------------ the pass hooks
    def generation_started(self, generation: int, pending: int,
                           re_attacks: int) -> None:
        with self._lock:
            self.generation = int(generation)
            self.pending = int(pending)
            self.done = 0
            self.fresh = 0
            self._generation_started = time.perf_counter()
        self._emit(f"generation {generation}: {pending} pending "
                   f"({re_attacks} re-attacks), certificates so far "
                   f"{self.certified}, elapsed "
                   f"{_hms(time.perf_counter() - self._started)}")

    def key_done(self, key: Key, certified: bool) -> None:
        with self._lock:
            self.done += 1
            if certified:
                self.fresh += 1
                self.certified += 1
            done, fresh, pending = self.done, self.fresh, self.pending
            since = time.perf_counter() - self._generation_started
        if done % self._every and done != pending:
            return
        rate = done / since if since > 0 else 0.0
        remaining = (pending - done) / rate if rate > 0 else 0.0
        self._emit(f"  generation {self.generation}: {done}/{pending} done, "
                   f"+{fresh} certified, {since / done:.1f} s/key, "
                   f"elapsed {_hms(time.perf_counter() - self._started)}, "
                   f"remaining ~{_hms(remaining)} (last {key})")

    def generation_finished(self, generation: int, fresh: int,
                            refused: int) -> None:
        self._emit(f"generation {generation} done: +{fresh} certificates "
                   f"(total {self.certified}), {refused} refused, "
                   f"{_hms(time.perf_counter() - self._generation_started)}")

    def finished(self, generations_run: int) -> None:
        self._emit(f"pass done: {self.certified} certificates over "
                   f"{generations_run} generation(s) in "
                   f"{_hms(time.perf_counter() - self._started)}; "
                   f"writing the ledger")


class LockedSet(set):
    """A `set` whose membership test and insertion are serialised.

    `mother.gate` does `would_exceed` then `add` on the exposure's own
    set; on threads that pair races, and the exposure bound is a
    CORRECTNESS bound (DESIGN §0), not a budget.  Sharing this object
    rather than merging per-thread sets afterwards keeps the bound live.
    """

    def __init__(self, *args):
        super().__init__(*args)
        self._lock = threading.Lock()

    def add(self, item):
        with self._lock:
            super().add(item)

    def __contains__(self, item):
        with self._lock:
            return super().__contains__(item)


def shared_exposure(bound: float | None = None) -> Exposure:
    """One exposure ledger for every thread of a run."""
    exposure = Exposure(consulted=LockedSet())
    if bound is not None:
        exposure.bound_expected_false = float(bound)
    return exposure


def expand_rungs(rungs: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for name in rungs:
        out.extend(RUNG_ALIASES.get(str(name), (str(name),)))
    return tuple(out)


def _plane_field(inputs: Any, lane: Any, key: Key) -> Any:
    page, _ty, _tx, stream_id = key
    return inputs.plane_fields.get(
        (str(lane.capture_id), int(lane.level_index), int(page),
         PLANE_OF[str(stream_id)]))


def _halo_for(config: AnalyzerConfig, stream_id: str) -> int:
    if config.halo_cells is None:
        return int(arms_mod.HALO_CELLS[str(stream_id)])
    return int(config.halo_cells[str(stream_id)])


def _knobs_for(inputs: Any, config: AnalyzerConfig, key: Key, lane: Any,
               metadata_bit: int | None, smooth_field: Any) -> dict:
    return {
        "seed": int(config.seed),
        "ctx_mode": str(config.ctx_mode),
        "mix_scope_ladder": tuple(config.mix_scope_ladder),
        "lane_mix_tiles": int(config.lane_mix_tiles),
        "metadata_known": bool(config.metadata_known
                               and metadata_bit is not None),
        "metadata_bit": metadata_bit,
        "plane_field": _plane_field(inputs, lane, key),
        "smooth_field": smooth_field,
        **dict(config.knobs),
    }


# ---------------------------------------------------- the blind decision

def blind_key(inputs: Any, certs: Mapping[Key, Any], key: Key,
              config: AnalyzerConfig, exposure: Exposure, *,
              metadata_bit: int | None = None,
              smooth_fields: Mapping[Any, Any] | None = None) -> dict:
    """Everything the analyzer decides about one tile-stream, BLIND.

    No ground truth reaches this function or anything it calls; the
    certificate gate (syndrome + CRC) is the only thing that can say
    `certified` here, exactly as in production.
    """
    started = time.perf_counter()
    page, ty, tx, stream_id = key
    out: dict[str, Any] = {"key": key, "evidence": {}, "combined": {},
                           "rungs": {}, "selected": {}, "offsets": {},
                           "default_evidence": {}}
    lanes = sample_mod.lanes_for_tile(inputs, int(page), int(ty), int(tx),
                                      cover_fraction=config.cover_fraction)
    out["n_lanes"] = len(lanes)
    if not lanes:
        out["refusal"] = "no_lane_sees_this_tile"
        out["seconds"] = time.perf_counter() - started
        return out

    halo = _halo_for(config, str(stream_id))
    footprint = frame_mod.tile_footprint(inputs.row, int(page), int(ty),
                                         int(tx), halo,
                                         geometry=inputs.geometry)
    folds = cal.split_folds(footprint.page_cells_yx, int(config.seed))
    battery = config.battery_for(str(stream_id))
    default_arm = battery[0] if battery else None
    chosen: list[Any] = []
    #: GAPS-2026-09-03's re-roll: every arm's evidence is computed for the
    #: selection anyway, so the ones the select fold did not pick are kept
    #: rather than dropped.  They cost nothing more to hold and they are
    #: what the re-roll below spends.
    usable_by_lane: dict[Any, list[Any]] = {}
    for lane in lanes:
        smooth = None if smooth_fields is None else smooth_fields.get(
            (lane.lane_id, str(stream_id)))
        knobs = _knobs_for(inputs, config, key, lane, metadata_bit, smooth)
        candidates = []
        for arm in battery:
            evidence = arms_mod.evidence_for(
                inputs, certs, key, lane, arm, halo_cells=halo, knobs=knobs)
            candidates.append(evidence)
            out["evidence"][(lane.lane_id, arm)] = dict(evidence.blind)
            if arm == default_arm:
                out["default_evidence"][lane.lane_id] = evidence
                offset = evidence.blind.get("offset_dots_xy")
                if offset is not None:
                    out["offsets"][lane.lane_id] = (
                        tuple(float(value) for value in offset),
                        float(evidence.blind.get("n_labels", 0) or 0))
        usable = [item for item in candidates
                  if item.blind.get("refusal") is None
                  and bool(np.any(item.observed))]
        if not usable:
            continue
        usable_by_lane[lane.lane_id] = list(usable)
        winner, detail = cal.select_arm(usable, folds)
        out["selected"][lane.lane_id] = dict(detail)
        chosen.append(winner)

    if not chosen:
        out["refusal"] = "every_arm_refused"
        out["seconds"] = time.perf_counter() - started
        return out

    rungs = expand_rungs(config.rungs)
    knobs = {"keep_hard": True, **dict(config.knobs)}
    certified: tuple[str, str, np.ndarray] | None = None
    #: Every gate-passing certificate this key produces, with the physical
    #: captures it rests on.  Two that agree bit-for-bit on DISJOINT
    #: captures corroborate each other; two that differ are a
    #: contradiction and the key is refused (RULING 2026-09-04, leg 4).
    claims: list[combine_mod.CertificateClaim] = []
    for rule in config.rules:
        combined = combine_mod.combine(chosen, rule)
        summary = combine_mod.combine_detail(combined)
        if config.keep_vectors:
            summary["llr_sequential"] = np.asarray(combined.llr_sequential)
        out["combined"][rule] = summary
        # L3 APPLIES the footprint's context offsets, it never refits them
        # (DESIGN §6 L3, RULED after W2); `combine` pooled them over the
        # lanes this rule actually used, so they ride the rule's own knobs.
        rule_knobs = dict(knobs)
        rule_knobs.setdefault("ctx_offsets", combined.ctx_offsets)
        # L7a's disagreement set is the same kind of knob: a blind product
        # of the combination this rule just made (DESIGN §6 L7a).  The pair
        # is (indices, agreement AT those indices) — parallel arrays, which
        # is what `_rung_erase_disagree` orders its erasures by.
        if combined.disagree is not None:
            rule_knobs.setdefault(
                "disagree", (combined.disagree,
                             combined.agreement[combined.disagree]))
        results = ladder_mod.run_ladder(
            combined, inputs.row, key, rungs=rungs, knobs=rule_knobs,
            exposure=exposure, metadata_bit=metadata_bit)
        out["rungs"][rule] = results
        claims.extend(_claims_of(results, rule, summary))
        # RULING 2026-09-03 (W4 review D1): a list rung's certificate passed
        # syndrome AND CRC like any other; it mints, cascades and reaches the
        # close.  The quarantine of DESIGN §0 is on the zero-wrong CLAIM — the
        # row keeps the verdict `certified_list` and the run states its
        # exposure beside every count.
        hit = next((item for item in results
                    if item.verdict in (VERDICT_CERTIFIED,
                                        VERDICT_CERTIFIED_LIST)), None)
        if hit is not None and certified is None:
            certified = (rule, hit.rung, np.asarray(hit.user_bits, np.uint8))
            out["certified_verdict"] = hit.verdict
            out["certifying_arm"] = "|".join(
                sorted({item.arm for item in chosen}))
            if not config.all_rules:
                break

    # THE RE-ROLL (`analyzer/GAPS-2026-09-03.md` §7).  The selected arm's
    # ladder has failed and the battery's other arms are already computed —
    # the selection paid for them and used one.  On the C tiles production
    # had to work hardest for, every factor that recovers one moves the
    # soft-information rate by a hundredth across the BP waterfall, so what
    # the parity control lacks against production is ATTEMPTS, not a
    # mechanism.  Each remaining arm's evidence therefore gets its own
    # combination and its own L0/L1, gated by syndrome + CRC like anything
    # else and charged to the same exposure.  Blind throughout: no ground
    # truth reaches this, and the select fold is not consulted again — this
    # is not a second arm choice, it is more rolls of the same dice.
    if certified is None and bool(getattr(config, "reroll", False)):
        reroll_rungs = expand_rungs(
            getattr(config, "reroll_rungs", ("L0", "L1")))
        sets = combine_mod.reroll_sets(usable_by_lane, chosen)
        out["reroll"] = {"n_sets": len(sets),
                         "arms": [arm for arm, _evidence in sets],
                         "rungs": list(reroll_rungs)}
        for arm, evidence_set in sets:
            for rule in config.rules:
                combined = combine_mod.combine(evidence_set, rule)
                label = f"{rule}|reroll:{arm}"
                reroll_summary = combine_mod.combine_detail(combined)
                out["combined"][label] = reroll_summary
                rule_knobs = dict(knobs)
                rule_knobs.setdefault("ctx_offsets", combined.ctx_offsets)
                if combined.disagree is not None:
                    rule_knobs.setdefault(
                        "disagree", (combined.disagree,
                                     combined.agreement[combined.disagree]))
                results = ladder_mod.run_ladder(
                    combined, inputs.row, key, rungs=reroll_rungs,
                    knobs=rule_knobs, exposure=exposure,
                    metadata_bit=metadata_bit)
                out["rungs"][label] = results
                claims.extend(_claims_of(results, label, reroll_summary))
                hit = next((item for item in results
                            if item.verdict in (VERDICT_CERTIFIED,
                                                VERDICT_CERTIFIED_LIST)),
                           None)
                if hit is not None:
                    certified = (label, hit.rung,
                                 np.asarray(hit.user_bits, np.uint8))
                    out["certified_verdict"] = hit.verdict
                    out["certifying_arm"] = f"reroll:{arm}"
                    break
            if certified is not None:
                break

    certified, agreement = adjudicate(certified, claims)
    out["agreement"] = agreement
    if agreement["contradiction"]:
        out.pop("certified_verdict", None)
        out.pop("certifying_arm", None)
        out["refusal"] = CONTRADICTION_REFUSAL
    if certified is not None:
        out["certifying_rule"], out["certifying_rung"], out["user_bits"] = \
            certified
    out["seconds"] = time.perf_counter() - started
    return out


#: What a row says when two gate-passing certificates disagreed.
CONTRADICTION_REFUSAL = "independent_certificates_disagree"


def adjudicate(certified: tuple[str, str, np.ndarray] | None,
               claims: Sequence[combine_mod.CertificateClaim],
               ) -> tuple[tuple[str, str, np.ndarray] | None, dict]:
    """Leg 4 (RULING 2026-09-04): corroborate, or refuse the key.

    Two gate-passing certificates for one key with different bits both
    passed syndrome and CRC, so at least one is a FALSE ACCEPT and
    nothing blind can say which.  There is no majority to take and no
    tie-break that is not a guess, so the key is refused: no mint, no
    cascade, and the contradiction on the row for the record.  A key
    whose certificates all agree keeps its certificate and carries the
    count of how many of them rest on disjoint captures.
    """
    agreement = combine_mod.independent_agreement(claims)
    return (None if agreement["contradiction"] else certified), agreement


def _claims_of(results: Sequence[Any], label: str,
               summary: Mapping[str, Any]
               ) -> list[combine_mod.CertificateClaim]:
    """The gate-passing certificates one (rule, combination) produced.

    The ladder stops at its first certificate, so this is normally zero
    or one item; it is written over the whole batch anyway, because a
    ladder that ever returns two is exactly the case the contradiction
    check exists for.
    """
    captures = combine_mod.contributing_captures(summary)
    return [combine_mod.CertificateClaim(
        label=str(label), rung=str(item.rung), verdict=str(item.verdict),
        captures=captures,
        user_bits=np.asarray(item.user_bits, np.uint8))
        for item in results
        if item.verdict in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST)
        and item.user_bits is not None]


# ------------------------------------------------------------- the pass

def _row_for(census_by_key: Mapping[Key, LedgerRow], key: Key) -> LedgerRow:
    row = census_by_key.get(key)
    if row is not None:
        return dc_replace(row)
    page, ty, tx, stream_id = key
    return LedgerRow(page=page, ty=ty, tx=tx, stream_id=stream_id, esi=-1,
                     covered=True, certified_by_production=False,
                     source=None, band="unclassified",
                     band_any="unclassified", neighbours_certified=0,
                     siblings_certified=(), known_cells_in_halo=0,
                     n_discriminating_labels=0, production_attempts={},
                     metadata_known=False)


def _retarget(inputs: Any, key: Key, certified: set[Key],
              attempted: set[Key], known: Mapping[Key, Any] | None = None
              ) -> list[Key]:
    """DESIGN §6b: the 8-neighbourhood plus the tile's other streams.

    `known` is the WORKING certificate mapping, not `inputs.certificates`:
    under `--withhold` (DESIGN §8) a withheld key is not a certificate of
    this pass, and skipping it here would make the cascade unable to
    re-target the very keys the positive control is trying to win back.

    `attempted` is the caller's exclusion set.  `run` passes it EMPTY (the
    W3 cascade ruling: a key attempted in an earlier generation is
    re-attacked, because its frame at attempt time did not hold the
    certificate that triggered this re-target); it stays a parameter so a
    caller that wants one-shot behaviour can still ask for it.
    """
    known = inputs.certificates if known is None else known
    page, ty, tx, stream_id = key
    tiles_y, tiles_x = inputs.tiles_yx
    out: list[Key] = []
    for fact in inputs.row.streams:
        if fact.stream_id != stream_id:
            out.append((page, ty, tx, fact.stream_id))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = ty + dy, tx + dx
            if 0 <= ny < tiles_y and 0 <= nx < tiles_x:
                out.append((page, ny, nx, stream_id))
    return [item for item in out
            if item not in certified and item not in attempted
            and item not in known]


#: The row verdict's order (2026-09-04).  There is nothing worse than
#: `certified` for a run to say any more: `wrong` and `false_accept` were
#: GT adjudications and left with truth, so a row is `open` without a
#: certificate, `certified` when a direct rung's gate passed, and
#: `certified_list` when only a list rung's did.
VERDICT_PRECEDENCE: tuple[str, ...] = (
    VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST, VERDICT_OPEN)


def row_verdict(rung_verdicts: Sequence[str], *, has_certificate: bool
                ) -> str:
    """The row-level verdict of a tile-stream (DESIGN §0, as amended).

    `rung_verdicts` is every rung verdict the row produced, over every
    rule; `has_certificate` says whether the blind path handed back user
    bits.  A direct-rung certificate outranks a list-rung one, because
    the count that quarantines list rungs from the zero-wrong claim reads
    this column.
    """
    seen = set(str(name) for name in rung_verdicts)
    if not has_certificate:
        return VERDICT_OPEN
    if VERDICT_CERTIFIED in seen:
        return VERDICT_CERTIFIED
    return VERDICT_CERTIFIED_LIST if VERDICT_CERTIFIED_LIST in seen \
        else VERDICT_CERTIFIED


def _rung_dict(result: Any) -> dict:
    """A RungResult as the ledger stores it, hard vector INCLUDED.

    `detail["hard_packed"]` is 512 bytes of blind decoder output (the
    exit hard vector) and it used to be stripped here, because the
    in-run oracle had already turned it into `bits_wrong_*`.  With
    scoring moved offline (2026-09-04) it is the thing the scorer needs
    and nothing else can reconstruct, so it is KEPT — base64 rather than
    the hex `ledger.jsonable` would give bytes, which is 683 characters
    instead of 1,024 per rung.
    """
    detail = {name: value for name, value in result.detail.items()
              if name != "hard_packed"}
    packed = result.detail.get("hard_packed")
    if packed is not None:
        detail["hard_packed_b64"] = base64.b64encode(bytes(packed)).decode()
    return {"rung": result.rung, "verdict": result.verdict,
            "n_iters": int(result.n_iters),
            "unsat_at_exit": int(result.unsat_at_exit),
            "syndrome_ok": bool(result.syndrome_ok),
            "posterior_summary": dict(result.posterior_summary),
            "crc_consults_distinct": int(result.crc_consults_distinct),
            "seconds": float(result.seconds), "detail": detail}


def _header(inputs: Any, config: AnalyzerConfig,
            exposure: Exposure, n_targets: int) -> dict:
    return {
        "seed": int(config.seed),
        "workers": int(config.workers),
        "arms": list(config.arms),
        "refused_arms": list(config.refused_arms),
        "rules": list(config.rules),
        "rungs": list(expand_rungs(config.rungs)),
        "ctx_mode": config.ctx_mode,
        "cover_fraction": float(config.cover_fraction),
        "halo_cells": (None if config.halo_cells is None
                       else dict(config.halo_cells)),
        "max_generations": int(config.max_generations),
        "all_rules": bool(config.all_rules),
        "targets_from": config.targets_from,
        "knobs_from": config.knobs_from,
        "non_blind": bool(config.non_blind),
        "n_targets": int(n_targets),
        "format_ref": inputs.format_ref,
        "run_dir": str(inputs.run_dir),
        "captures": [{"capture": capture.capture_id, "dpi": capture.dpi,
                      "shape_px": list(capture.shape_px)}
                     for capture in inputs.captures],
        "provenance": dict(inputs.provenance),
        # No `truth` block: a run opens no payload (2026-09-04 ruling).
        # `analyzer score` records which payload IT was scored against, in
        # its own report, where that fact belongs.
        "exposure_bound_expected_false": exposure.bound_expected_false,
    }


def run(inputs: Any, targets: Sequence[Any],
        config: AnalyzerConfig | None = None, *,
        census_rows: Sequence[LedgerRow] | None = None,
        exposure: Exposure | None = None,
        certs: Mapping[Key, Any] | None = None,
        progress: Callable[[str], None] | None = None,
        progress_every: int = PROGRESS_EVERY) -> Ledger:
    """Drive `targets` to a fixed point and return the ledger (PLAN §1.2).

    `targets` are census `LedgerRow`s or bare keys.  `certs` overrides the
    working certificate mapping (the positive control hands one with the
    withheld keys removed); it is COPIED, and the pass's own certificates
    are folded into the copy, never into `inputs`.  `progress`, when
    given, receives the operator lines of :class:`Progress` and arms its
    status signals for the duration of the pass.

    There is no `truth` argument and no `allow_wrong` escape hatch: the
    2026-09-04 ruling took ground truth out of the run entirely, so the
    only verdicts this can produce are `open`, `certified` and
    `certified_list`.
    """
    config = AnalyzerConfig() if config is None else config
    exposure = shared_exposure() if exposure is None else exposure
    census_by_key: dict[Key, LedgerRow] = {}
    for row in (census_rows or ()):
        census_by_key[row.key] = row
    for item in targets:
        if isinstance(item, LedgerRow):
            census_by_key.setdefault(item.key, item)

    keys: list[Key] = [item.key if isinstance(item, LedgerRow)
                       else tuple(item) for item in targets]
    working: dict[Key, Any] = dict(inputs.certificates if certs is None
                                   else certs)
    metadata: dict[Key, int | None] = {}
    ledger = Ledger(exposure=exposure)
    ledger.header = _header(inputs, config, exposure, len(keys))

    certified: set[Key] = set()
    predecessors: dict[Key, tuple[Key, ...]] = {key: () for key in keys}
    generation_of: dict[Key, int] = {key: 0 for key in keys}
    pending = list(keys)
    smooth_fields: dict[Any, Any] = {}
    offsets: dict[Any, dict] = {}
    started = time.perf_counter()

    watch = (None if progress is None else
             Progress(progress, n_targets=len(keys), exposure=exposure,
                      every=progress_every))

    def work_one(key: Key) -> dict:
        bit = metadata.get(key)
        work = blind_key(inputs, snapshot_certs, key, config, exposure,
                         metadata_bit=bit, smooth_fields=smooth_fields)
        if watch is not None:
            watch.key_done(key, work.get("user_bits") is not None)
        return work

    row_index: dict[Key, int] = {}
    attempts: dict[Key, int] = {}
    with _status_doors(watch):
        for generation in range(int(config.max_generations)):
            # W3 cascade ruling (2026-09-03, Q2 measurement): a key attempted in
            # an EARLIER generation is re-attacked when a neighbour certifies —
            # its frame at attempt time did not hold that certificate.  Only
            # certified keys and duplicates are dropped; termination comes from
            # `fresh` (every re-target is triggered by a new certificate) and
            # from `max_generations`.
            seen_pending: set[Key] = set()
            pending = [key for key in pending
                       if key not in certified
                       and not (key in seen_pending or seen_pending.add(key))]
            if not pending:
                break
            if watch is not None:
                watch.generation_started(
                    generation, len(pending),
                    sum(1 for key in pending if attempts.get(key, 0)))
            for key in pending:
                attempts[key] = attempts.get(key, 0) + 1
            for key in pending:
                metadata.setdefault(key, inputs_mod.metadata_bit(inputs, key))
            snapshot_certs = dict(working)
            results: dict[Key, dict] = {}
            if int(config.workers) <= 1:
                for key in pending:
                    results[key] = work_one(key)
            else:
                with ThreadPoolExecutor(max_workers=int(config.workers)) as pool:
                    futures = [(key, pool.submit(work_one, key))
                               for key in pending]
                    for key, future in futures:
                        results[key] = future.result()

            fresh: list[Key] = []
            for key in pending:                     # PINNED order, not completion
                work = results[key]
                for lane_id, entry in work.get("offsets", {}).items():
                    offsets.setdefault((lane_id, key[3]), {})[
                        (key[1], key[2])] = entry
                row = _row_for(census_by_key, key)
                row.generation = generation_of.get(key, generation)
                row.predecessors = predecessors.get(key, ())
                row.evidence = {
                    f"{lane[0][:12]}/l{lane[1]}|{arm}": blind
                    for (lane, arm), blind in work.get("evidence", {}).items()}
                row.evidence["_selected"] = {
                    f"{lane[0][:12]}/l{lane[1]}": detail
                    for lane, detail in work.get("selected", {}).items()}
                row.combined = work.get("combined", {})
                row.rungs = {rule: [_rung_dict(item) for item in batch]
                             for rule, batch in work.get("rungs", {}).items()}
                agreement = work.get("agreement") or {}
                diag = {"seconds": float(work.get("seconds", 0.0)),
                        "n_lanes": int(work.get("n_lanes", 0)),
                        # Leg 4 of the correctness argument, per row: how many
                        # certificates resting on DISJOINT captures agree, and
                        # whether any two contradicted (which refused the key).
                        "independent_agreement": int(
                            agreement.get("independent_agreement", 0)),
                        "n_certificate_claims": int(
                            agreement.get("n_claims", 0)),
                        "contradiction": bool(agreement.get("contradiction",
                                                            False))}
                if work.get("refusal") == CONTRADICTION_REFUSAL:
                    diag["refused_certificate"] = True
                if agreement.get("contradiction"):
                    diag["contradicting"] = agreement.get("contradicting")
                elif agreement.get("independent_claims"):
                    diag["independent_claims"] = agreement["independent_claims"]
                if work.get("refusal"):
                    diag["refusal"] = work["refusal"]
                row.diag = diag

                rung_verdicts = [str(item["verdict"])
                                 for batch in row.rungs.values()
                                 if isinstance(batch, list) for item in batch]
                if work.get("user_bits") is not None:
                    row.certifying_rule = work["certifying_rule"]
                    row.certifying_rung = work["certifying_rung"]
                    row.certifying_arm = work.get("certifying_arm")
                    bits = np.asarray(work["user_bits"], np.uint8)
                    row.rungs["user_bits"] = bits
                    working[key] = bits
                    certified.add(key)
                    fresh.append(key)
                # A re-attack REPLACES the key's row.  Nothing needs carrying
                # over the replacement any more: the two STICKY verdicts were
                # `wrong` and `false_accept`, both GT adjudications, and both
                # left with truth (2026-09-04).  `certified`/`open` describe
                # the attempt whose evidence the row now holds, which is
                # exactly what a replacement should say.
                row.verdict = row_verdict(
                    rung_verdicts,
                    has_certificate=work.get("user_bits") is not None)
                row.diag["attempts"] = int(attempts.get(key, 1))
                if key in row_index:            # a re-attack replaces its row
                    ledger.rows[row_index[key]] = row
                else:
                    row_index[key] = len(ledger.rows)
                    ledger.rows.append(row)

            for lane_stream, by_tile in offsets.items():
                grid, _support = arms_mod.smooth_offsets(
                    {tile: value[0] for tile, value in by_tile.items()},
                    {tile: value[1] for tile, value in by_tile.items()},
                    inputs.tiles_yx)
                smooth_fields[lane_stream] = grid

            if watch is not None:
                watch.generation_finished(
                    generation, len(fresh),
                    sum(1 for key in pending if results[key].get("refusal")))
            if not fresh:
                break
            nxt: list[Key] = []
            for key in fresh:
                for follow in _retarget(inputs, key, certified, set(),
                                        working):
                    if follow not in nxt:
                        nxt.append(follow)
                    predecessors[follow] = predecessors.get(follow, ()) + (key,)
                    generation_of[follow] = generation + 1
            pending = nxt

        ledger.header.update({
            "n_rows": len(ledger.rows),
            "n_certified": len(certified),
            "n_corroborated": sum(
                1 for row in ledger.rows
                if int(row.diag.get("independent_agreement", 0) or 0) >= 2),
            "n_contradictions": sum(
                1 for row in ledger.rows if row.diag.get("contradiction")),
            "generations_run": max(
                (row.generation or 0 for row in ledger.rows), default=0) + 1,
            "seconds": time.perf_counter() - started,
            "exposure_distinct": int(exposure.distinct),
            "exposure_expected_false": float(exposure.expected_false),
        })
        if watch is not None:
            watch.finished(int(ledger.header["generations_run"]))
    return ledger


def targets_from_census(rows: Sequence[LedgerRow], spec: str
                        ) -> list[LedgerRow]:
    """`residue.target_rows`, re-exported so the CLI has one door."""
    return residue_mod.target_rows(rows, spec)
