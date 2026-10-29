"""The store's WRITE half: the fold dispatch and the typed folds.

Split out of ``store`` at the 1000-line seam.  A fold is the only
writer of a cell, and it answers the merge three things — whether the
fact changed anything, which ``FactKey``s it moved, and which
accounting family it belongs to.  ``store`` keeps the read half: the
cells themselves, the accessors that read them, and the done geometry
derived from the certificate frontier.

``_Folds`` is never instantiated: it carries no state of its own and
every cell it writes is created by ``_Store.__init__``, which is why
the two halves are one class at runtime.
"""
from __future__ import annotations

import os
from dataclasses import replace
from typing import Callable

import numpy as np

from . import data, sched_trace
from .data import CertKey, RegionKey
from .descriptor import (
    FactKey,
    KEY_ATTEMPT,
    KEY_COLOR_POP,
    KEY_COLOR_ROW,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    KEY_FIELD_OBS,
    KEY_LANE_POSES,
    KEY_LATTICE_SEED,
    KEY_LIVE_PAGES,
    KEY_PAGE_CERTS,
    KEY_PLACE_STAGE,
    KEY_PLANE_FIELD,
    KEY_POOLED_CTX,
    KEY_POSE_AFFINE,
    KEY_POSE_ROUTE,
    KEY_REGION_CTX,
    KEY_REGION_PITCH,
    KEY_TILE,
    KEY_WINDOW_DONE,
)
from .format import metadata
from .plugins import (
    calibrate,
    color_region_head,
    contradiction,
    place,
    place_sched,
    refine,
    tiles,
    words,
)


#: The cell-class law (ratified 2026-08-29): for a DECISION cell the
#: MUTATOR is the gatekeeper and the ordinal belongs to the cell's
#: schema, not to any producer -- forced by the two-writer placement
#: cell, where per-producer ordinals give no ordering at all.
def _adopts(standing: object | None, fact: object,
            ordinal: Callable[[object], tuple]) -> bool:
    return standing is None or ordinal(fact) > ordinal(standing)


#: A MEASUREMENT HATCH, NOT A PRODUCT DECISION.  The colour row's fold
#: is last-write-wins and its `heldout_logloss` is first in the
#: ownership order key, so "the newest row stands" and "the best row
#: stands" are different receivers.  `HOLO3_COLOR_ROW_ADOPT` runs the
#: other two so the difference can be MEASURED on paper; the ruling on
#: which one the receiver should ship is Germano's and nothing in the
#: tree anticipates it.  The default is byte-identical to the shipped
#: engine and the hatch is read ONCE, at store construction, so no fold
#: ever consults an environment variable.
ENV_COLOR_ROW_ADOPT = "HOLO3_COLOR_ROW_ADOPT"

#: `last` — the shipped fold: any difference in loss, values or cells
#: adopts (default, byte-identical).
ADOPT_LAST = "last"
#: `improve` — adopt only a strictly lower loss, a changed cell set, or
#: a first row.
ADOPT_IMPROVE = "improve"
#: `nonworse` — as `improve`, but an equal loss also adopts.
ADOPT_NONWORSE = "nonworse"
COLOR_ROW_ADOPT_MODES: tuple[str, ...] = (
    ADOPT_LAST, ADOPT_IMPROVE, ADOPT_NONWORSE)


def color_row_adopt_by_env(environ: dict[str, str] | None = None) -> str:
    """Read the hatch.  Anything unrecognised is the shipped default."""
    env = os.environ if environ is None else environ
    mode = env.get(ENV_COLOR_ROW_ADOPT, "").strip().lower()
    return mode if mode in COLOR_ROW_ADOPT_MODES else ADOPT_LAST


def _quality_refuses(mode: str, standing: data.ColorEvidenceRow,
                     fact: data.ColorEvidenceRow) -> bool:
    """Would this mode keep the standing row?

    A changed CELL SET is never refused under either mode: the cells a
    row covers are its contribution to the tile cover, and dropping a
    row because its loss rose would also drop cells no other row
    carries.  Only the loss decides when the geometry is the same.  A
    non-finite new loss refuses under both (it cannot be shown better).
    """
    if mode == ADOPT_LAST:
        return False
    if not np.array_equal(standing.page_cells_yx, fact.page_cells_yx):
        return False
    new = float(fact.heldout_logloss)
    old = float(standing.heldout_logloss)
    if not np.isfinite(new):
        return True
    return new >= old if mode == ADOPT_IMPROVE else new > old


#: FOLD-TIME MEASUREMENT (sched_trace_folds), default off.  The two
#: evidence cells that carry a `heldout_logloss` fold last-write-wins,
#: and that loss is first in the ownership order key -- so a record of
#: what the loss and the values DID at each fold is the only way to ask
#: whether "changed" and "better" are the same event.  Both call sites
#: sit behind `if sched_trace.TRACE.enabled:`, so the OFF path is one
#: attribute read.
def _note_fold(kind: str, key: tuple, changed: bool,
               standing: object | None, fact: object, values_attr: str,
               keys: tuple, reason: str, cover: tuple = ()) -> None:
    trace = sched_trace.TRACE
    trace.folds.note(
        kind=kind, key=key, changed=changed, standing=standing, fact=fact,
        standing_cells=(None if standing is None
                        else standing.page_cells_yx),
        standing_values=(None if standing is None
                         else getattr(standing, values_attr)),
        new_cells=fact.page_cells_yx,
        new_values=getattr(fact, values_attr),
        keys=keys, reason=reason, cover=cover, wall_s=trace.wall_s())


def _update_cover(forward: dict, inverse: dict, member: object,
                  new_keys: tuple) -> None:
    old_keys = inverse.get(member, ())
    if new_keys == old_keys:
        return
    for key in old_keys:
        standing = forward.get(key)
        if standing is None:
            continue
        standing.discard(member)
        if not standing:
            del forward[key]
    for key in new_keys:
        forward.setdefault(key, set()).add(member)
    inverse[member] = new_keys


class _Folds:

    #: The measurement hatch's shipped value, in the spirit of
    #: `_Engine._trace_on`: `_Store.__init__` sets the instance one from
    #: the environment.  The fold reads it through `getattr` because
    #: some hand-built test stores are a `SimpleNamespace` and inherit
    #: nothing -- either way an unconfigured store folds exactly as the
    #: shipped engine does.
    _color_row_adopt: str = ADOPT_LAST

    def _fold(self, fact: object) -> tuple[bool, tuple[FactKey, ...], str]:
        if isinstance(fact, data.Certificate):
            return self._fold_certificate(fact)
        if isinstance(fact, data.Capture):
            return self._fold_capture(fact)
        if isinstance(fact, data.CaptureSurvey):
            return self._fold_survey(fact)
        if isinstance(fact, data.Window):
            return self._fold_window(fact)
        if isinstance(fact, data.Placement):
            return self._fold_placement(fact)
        if isinstance(fact, place_sched.PlaceOutcome):
            return self._fold_place_outcome(fact)
        if isinstance(fact, data.LatticeSeed):
            return self._fold_lattice_seed(fact)
        if isinstance(fact, data.WindowEvidence):
            return self._fold_evidence(fact)
        if isinstance(fact, calibrate.CtxOutcome):
            return self._fold_ctx_outcome(fact)
        if isinstance(fact, refine.RefineOutcome):
            return self._fold_refine_outcome(fact)
        if isinstance(fact, data.AttemptFact):
            return self._fold_attempt(fact)
        if isinstance(fact, data.ColorEvidenceRow):
            return self._fold_color_row(fact)
        if isinstance(fact, color_region_head.ColorLaneFit):
            return self._fold_color_lane_fit(fact)
        if isinstance(fact, data.ColorCtxPopulation):
            return self._fold_color_pop(fact)
        if isinstance(fact, data.PooledColorCtx):
            return self._fold_pooled_ctx(fact)
        if isinstance(fact, data.FieldObservations):
            return self._fold_field_observations(fact)
        if isinstance(fact, data.PlaneField):
            return self._fold_plane_field(fact)
        if isinstance(fact, data.EvidenceRevision):
            return self._fold_evidence_revision(fact)
        raise data.IntegrityError(
            f"unknown fact type {type(fact).__name__} reached the fold")

    def _fold_capture(
            self, fact: data.Capture) -> tuple[bool, tuple[FactKey, ...],
                                               str]:
        if fact.capture_id in self._captures:
            return False, (), "other"
        self._captures[fact.capture_id] = fact
        for level in fact.levels:
            self._levels[(fact.capture_id, level.index)] = level
        return True, (), "other"

    def _fold_survey(
            self,
            fact: data.CaptureSurvey) -> tuple[bool, tuple[FactKey, ...],
                                               str]:
        #: Frames are built whatever the survey measured, including from
        #: an archived survey that measured nothing: `region_frame` reads
        #: the DECLARED pitch, never `fact.pitch_px`, so gating windows on
        #: the vote lost whole captures for nothing.  RULINGS.md D5.
        self._surveys[fact.capture_id] = fact
        capture = self._captures[fact.capture_id]
        for level in capture.levels:
            base = 0
            for region in fact.regions:
                frame = place.region_frame(region, level, self.row.pitch_in,
                                           capture.dpi,
                                           capture.platen_backing)
                if frame is None:
                    continue
                key: RegionKey = (fact.capture_id, level.index,
                                  region.region_index)
                self._frames[key] = frame
                plan = place.window_plan(frame, level.index, base)
                base += len(plan)
                for window in plan:
                    self._ingest(window)
            self._plan_total[(fact.capture_id, level.index)] = base
        return True, (), "other"

    def _fold_window(
            self, fact: data.Window) -> tuple[bool, tuple[FactKey, ...],
                                              str]:
        wid = fact.window_id
        if wid in self._windows:
            return False, (), "other"
        self._windows[wid] = fact
        self._ordinal_wid[(fact.capture_id, fact.level_index,
                           fact.ordinal)] = wid
        self._place_stages[wid] = place_sched.WindowState(
            window=fact, parent=fact.parent)
        # THE PARENT/CHILD LINK IS THE FACT'S, and the store keeps both
        # ends of it: a child Window carries its parent's id, so this
        # relation survives a snapshot (it did not before 2026-09-21 --
        # `_subdivide` wrote it, and a resume never ran `_subdivide`).
        # No key: nothing standing reads a window, and the outcome that
        # follows the children out of the subdivide job emits the
        # parent's own.
        parent = (None if fact.parent is None
                  else self._place_stages.get(fact.parent))
        if parent is not None and wid not in parent.children:
            parent.children += (wid,)
        return True, (), "other"

    def _fold_place_outcome(
            self,
            fact: place_sched.PlaceOutcome) -> tuple[bool,
                                                     tuple[FactKey, ...],
                                                     str]:
        wid = fact.window_id
        state = self._place_stages.get(wid)
        if state is None:
            return True, (), "other"
        retired_before = state.retired
        before = (len(state.tried), state.centre_spent, state.rest_spent,
                  state.wide_spent, state.cold_armed, state.cold_live_spent,
                  state.cold_rest_spent, state.dormant_since, state.retired,
                  state.subdivide_armed, state.subdivided,
                  state.support_refused)
        result = fact.result
        state.tried |= set(result.tried_now)
        if result.stage_spent == words.STAGE_CENTRE:
            state.centre_spent = True
        elif result.stage_spent == words.STAGE_REST:
            state.rest_spent = True
        if result.wide_spent:
            state.wide_spent = True
            state.cold_armed = True
        if result.cold_spent == place.STAGE_COLD_LIVE:
            state.cold_live_spent = True
        elif result.cold_spent == place.STAGE_COLD_REST:
            state.cold_rest_spent = True
        outcome = result.outcome
        if outcome == "accepted":
            pass
        elif outcome == place.OUTCOME_SUBDIVIDED:
            # The rung ran: the children came out of the same job ahead
            # of this fact and are already folded, so what is left is to
            # retire the rung.  THE FRANCHISE A FRESH SUBDIVISION KEEPS
            # (base's `if state.children: return`, restored by the
            # stage-2 review): a window that has just quartered itself
            # is spent only against the consults it has been OFFERED,
            # and `place.stage_of` answers STAGE_RING again the moment
            # `untried_consult` is non-empty -- so a neighbour that
            # places later hands it a new seed and one more ring pass,
            # and the settle after THAT latches.  A quartering that
            # minted nothing changed no prospect and latches at once,
            # and so does one a support refusal left as the last rung.
            state.subdivided = True
            if not state.children or state.support_refused:
                self._settle_ladder(state)
        elif outcome == "insufficient_support":
            # The ladder is done with this window whatever its shape --
            # all but a quartering a refusal ARMED before this pass ran:
            # base quartered inside that refusal's fold, so the children
            # were owed already, and latching here retired the window
            # `exhausted` without them (review 2026-10-17, D1).  So the
            # refusal is a ladder state like the others and settles
            # through `_settle_ladder`: `stage_of` answers the armed
            # rung or nothing, the flag moves this window's own key, and
            # an unarmed window latches here exactly as before.  A
            # parent owed an afterlife keeps its BOOKMARK either way --
            # `place_retire_cause` holds it (review 2026-09-21).
            state.support_refused = True
            self._settle_ladder(state)
        elif outcome in place.SUBDIVISION_DIRECT:
            # v1's order: a window whose own fit refused, or whose
            # straddle audit refused an address it had accepted,
            # quarters at once -- with rungs still on its ladder.  The
            # fold ARMS the rung; `place.stage_of` schedules it.
            state.subdivide_armed = True
            if outcome == "pose_refused":
                # Asleep only if nothing woke it mid-pass: a wake the
                # pass did not read is a reason to retry, not one to
                # swallow (`merging_sleep_version`, S7 2026-10-03).
                state.dormant_since = self.merging_sleep_version(wid)
            else:
                self._settle_ladder(state)
        else:
            self._settle_ladder(state)
        after = (len(state.tried), state.centre_spent, state.rest_spent,
                 state.wide_spent, state.cold_armed, state.cold_live_spent,
                 state.cold_rest_spent, state.dormant_since, state.retired,
                 state.subdivide_armed, state.subdivided,
                 state.support_refused)
        keys: list[FactKey] = []
        if after != before:
            keys.append((KEY_PLACE_STAGE, wid))
        # A CHILD THAT SETTLES IS ROUTED TO ITS PARENT, by the store and
        # not by a subscription: the parent's reads are fixed at birth
        # and name its own keys alone, so what reaches it is its OWN
        # place_stage key, emitted here off the parent's state.
        if state.retired != retired_before:
            parent_key = self._settle_child(state, placed=False)
            if parent_key is not None:
                keys.append(parent_key)
        # DORMANCY IS MEASURED FROM AFTER THIS FOLD'S OWN WAKE.  The
        # place_stage key above is one of `place`'s own reads -- the
        # ladder climb -- so a window that just put itself to sleep is
        # about to be woken by the very fact that put it there, and
        # would re-fire the same refusal for ever (the colour sim at
        # 750 % CPU, 2026-09-21).  `_touch` bumps a subscriber once per
        # key it holds, and the only key here this window holds is its
        # own, so the stamp moves one with it.  A parent key emitted
        # above reaches somebody ELSE's version and is not counted.
        #
        # It applies to a window already asleep too, and that is what
        # makes the `subdivide` rung reachable through a sleep: the
        # sleeper takes the rung, this fold emits its own key, the
        # stamp moves with it and the sleep resumes exactly where it
        # was.  Only somebody else's fact wakes it.
        if state.dormant_since is not None \
                and (KEY_PLACE_STAGE, wid) in keys:
            state.dormant_since += 1
        return True, tuple(keys), "other"

    # THE LADDER CLIMB, and it takes no engine call.  The state moved,
    # so `_fold_place_outcome` emits `(KEY_PLACE_STAGE, wid)` and
    # `place` -- which subscribes to its own place_stage key -- wakes on
    # it like any other row.  This is what `engine._place_repush` used
    # to force from outside the fold.
    #
    # It asks `ladder_rung`, not `ladder_stage`: a DORMANT window with
    # rungs left is asleep, not spent, and latching it here would
    # retire a window that `pose_refused` had merely put to bed.  The
    # quartering is a rung of that ladder since 2026-09-21, so a window
    # that has not subdivided is never spent -- which is also the
    # franchise a fresh subdivision keeps: `place.stage_of` answers
    # STAGE_RING again the moment `untried_consult` is non-empty, so a
    # neighbour that places later hands this window a new seed and one
    # more ring pass before the latch.
    def _settle_ladder(self, state: place_sched.WindowState) -> None:
        wid = state.window.window_id
        if place_sched.ladder_rung(self, state, wid) is not None:
            return
        # `retired` is the LADDER's latch; whether the BOOKMARK goes is
        # `place_sched.place_retire_cause`'s business, which holds the
        # row while `afterlife_owed`, so the cold pass this parent may
        # still be owed has something to wake.
        state.retired = True

    #: A CHILD SETTLED -- `placed` or `retired` moving -- and the store
    #: routes it to the PARENT's own state.  Returns the parent's own
    #: `place_stage` key when the parent's ladder-visible state moved,
    #: and None when nothing it would do has changed: a settle that is
    #: neither the cancelling one nor the last is bookkeeping, and
    #: waking the parent for it is the child-ladder noise the narrow
    #: key existed to keep out.
    #:
    #: All children settled without a pose: the parent re-arms COLD on
    #: its FULL extent -- correlation wants area.  Rare, because the
    #: ladder spends its cold rungs before it subdivides; it bites on
    #: the two refusals that quarter a window early.
    #:
    #: SETTLED is counted from the folds alone: the engine's bookmarks
    #: are not the store's business.  What that gives up is a child the
    #: DONE GATE suppresses (no stage, never a settle) -- and giving it
    #: up is right, because a done child means certified tiles already
    #: cover that quarter and re-arming the parent COLD over an area the
    #: run has already read is the work the gate exists to suppress.
    #: The parent's key reaches a LIVE bookmark since 2026-10-03: the
    #: done gate no longer retires, so a parent judged done while it
    #: waits is suppressed, not gone, and hears its last child.
    def _settle_child(self, state: place_sched.WindowState,
                      placed: bool) -> FactKey | None:
        parent_wid = state.parent
        if parent_wid is None:
            return None
        parent = self._place_stages.get(parent_wid)
        if parent is None:
            return None
        parent.children_settled.add(state.window.window_id)
        if placed:
            # A child that PLACED cancels the afterlife for good, and
            # the parent hears about it because that is the moment its
            # retire clause can come true.
            if parent.child_placed:
                return None
            parent.child_placed = True
            return (KEY_PLACE_STAGE, parent_wid)
        if not place_sched.afterlife_owed(parent):
            return None
        if len(parent.children_settled) < len(parent.children):
            return None
        parent.afterlife_used = True
        parent.cold_armed = True
        parent.dormant_since = None
        parent.support_refused = False
        parent.retired = False
        # THE AFTERLIFE MAY FIND NOTHING TO RUN (S7, 2026-10-03), and
        # then it re-latches here.  A LAZY quartering comes after the
        # cold rungs are spent, so re-arming cold buys no rung: until
        # this date the parent woke to `stage() -> None`, was never
        # latched again (`_settle_ladder` runs off its own outcomes,
        # and none follows) and never retired -- subscribed for good,
        # paying retire and ladder consults on every neighbour wake
        # (SCHED-OPEN #8's "afterlife 0 of 319" on J is this).  A
        # parent with a rung left -- a refusal that quartered it early,
        # cold unspent -- is not latched and fires it.  A full-extent
        # cold pass AFTER a lazy quartering would be new behaviour and
        # is the owner's ruling, not built.
        self._settle_ladder(parent)
        return (KEY_PLACE_STAGE, parent_wid)

    def _fold_placement(
            self, fact: data.Placement) -> tuple[bool, tuple[FactKey, ...],
                                                 str]:
        wid = fact.window_id
        standing = self._placements.get(wid)
        if not _adopts(standing, fact, data.placement_ordinal):
            return False, (), "pose"
        affine_changed = (
            standing is None
            or standing.page != fact.page
            or standing.rot_k != fact.rot_k
            or standing.page_origin_yx != fact.page_origin_yx
            or tuple(standing.native_affine) != tuple(fact.native_affine)
            or standing.pitch_px != fact.pitch_px
            or standing.patch_ordinal != fact.patch_ordinal
            or not np.array_equal(standing.local_cells_yx,
                                  fact.local_cells_yx))
        route_changed = standing is None or standing.route != fact.route
        self._placements[wid] = fact
        # Birth, change or removal: every one of them changes what this
        # capture-page's collection would measure, and the page a window
        # LEAVES changes as much as the page it arrives on — its rows
        # were taken through a window that is somewhere else now (I12).
        self._advance_evidence(wid[0], fact.page)
        if standing is not None and standing.page != fact.page:
            self._advance_evidence(wid[0], standing.page)
        # The done-cell cache keys on this stamp, so it must move whenever a
        # region gains a pose or an adopted affine changes.  Miss either and
        # `done_cells` serves geometry the run has already superseded.
        stamp_key = (wid[0], wid[2])
        n_poses, gen_total = self._pose_stamp.get(stamp_key, (0, 0))
        self._pose_stamp[stamp_key] = (
            n_poses + (1 if standing is None else 0),
            gen_total + (1 if affine_changed and standing is not None
                         else 0))
        keys: list[FactKey] = []
        if standing is not None and standing.page != fact.page:
            vacated = (wid[0], wid[1], standing.page)
            self._lane_page_wids[vacated].discard(wid)
            # The page it LEFT changed too, and only this fold knows it:
            # every row keyed on that lane-page — the field collection
            # above all — still stands on observations taken through a
            # window that is no longer there, and nothing else will wake
            # it until an unrelated fact on that page happens to.
            keys.append((KEY_LANE_POSES,) + vacated)
        self._lane_page_wids.setdefault(
            (wid[0], wid[1], fact.page), set()).add(wid)
        if affine_changed:
            self._pose_gen[wid] = self._pose_gen.get(wid, -1) + 1
            extent = wid[3]
            shape = (extent[2] - extent[0], extent[3] - extent[1])
            self._page_cells[wid] = calibrate.window_page_cells(
                fact, shape, self.row.cells_yx)
            self._window_reach[wid] = refine.reach_tiles(
                self._page_cells[wid])
            keys.append((KEY_POSE_AFFINE, wid))
            # Every class in `affine_changed` moves what this lane-page's
            # rows would measure, so all of them wake it: an origin, pitch,
            # patch or local-cell change under an unchanged native affine
            # was invisible, and an A->B->A return woke the vacated page
            # only, never the destination.  Colour, the field collection,
            # `tiles.uplift` wakes on these too (R5); `tiles.swim` took
            # the per-window `pose_affine` key instead 2026-09-21.
            keys.append((KEY_LANE_POSES, wid[0], wid[1], fact.page))
            # THE DONE PROJECTION CAN SHRINK HERE, and only here: it runs
            # through the latest adopted pose of every placed window in
            # the region, so a new or revised affine can uncover a cell
            # an unplaced neighbour was suppressed on.  That neighbour
            # left the frontier through `stage() -> None`, not through
            # retire, and it wakes on its own done key (2026-10-03).
            for reopened in self.reopened_done_windows(wid[0], wid[2]):
                keys.append((KEY_WINDOW_DONE, reopened))
        if route_changed:
            keys.append((KEY_POSE_ROUTE, wid))
        state = self._place_stages.get(wid)
        if state is not None and not state.placed:
            state.placed = True
            keys.append((KEY_PLACE_STAGE, wid))
            # `placed` is a SETTLE too, and the one that cancels a
            # parent's afterlife: the quarter carries the page.  The
            # store routes it; the parent subscribes to nothing.
            parent_key = self._settle_child(state, placed=True)
            if parent_key is not None:
                keys.append(parent_key)
        if fact.page not in self._live_pages:
            self._live_pages.add(fact.page)
            keys.append((KEY_LIVE_PAGES,))
        self._lanes_on_page.setdefault(fact.page, set()).add(
            (wid[0], wid[1]))
        key: RegionKey = wid[:3]
        values = [self._placements[owid].pitch_px
                  for owid in self.placements()
                  if owid[:3] == key]
        pitch = calibrate.region_pitch_px(values)
        standing_pitch = self._region_pitch.get(key)
        if standing_pitch is None or pitch != standing_pitch:
            # The exact median stands (it is what a job reads), but the
            # key moves only with the SAMPLING PAIR at the level the
            # jobs read it -- `pitch / scale`, spelled as they spell it:
            # a window read takes the pitch through those two integers
            # and nowhere else, so a median that wanders inside one pair
            # re-reads nothing (2026-10-03).
            self._region_pitch[key] = pitch
            scale = self._levels[(wid[0], wid[1])].scale
            pair = calibrate.sampling_pair(pitch / float(scale))
            if self._region_sampling.get(key) != pair:
                self._region_sampling[key] = pair
                keys.append((KEY_REGION_PITCH,) + tuple(key))
        # The address-word alarm, last and read-only: it writes no cell
        # and returns no key, so admission, evidence, done projection and
        # certificates are exactly what they were (D1, 2026-09-04).
        contradiction.check(self, fact, self._events)
        # The WORD route is named by the FOLD, which is the one body that
        # knows the placement's route law; the engine only tallies the
        # accounting family it is handed (`pose_word` is a `pose`).
        return True, tuple(keys), (
            "pose_word" if fact.route == place.ROUTE_WORD else "pose")

    def _fold_lattice_seed(
            self,
            fact: data.LatticeSeed) -> tuple[bool, tuple[FactKey, ...],
                                             str]:
        key: RegionKey = (fact.capture_id, fact.level_index,
                          fact.region_index)
        if not _adopts(self._lattice_seeds.get(key), fact,
                       data.lattice_seed_ordinal):
            return False, (), "other"
        self._lattice_seeds[key] = fact
        return True, ((KEY_LATTICE_SEED,) + tuple(key),), "other"

    def _fold_evidence(
            self,
            fact: data.WindowEvidence) -> tuple[bool, tuple[FactKey, ...],
                                                str]:
        wid = fact.window_id
        # THE STANDING CORRECTION, AT THE HEAD.  Calibrate publishes its
        # rows stripped (`ctx_adopted=False`, printed = marginal); under
        # an adopted region decision every accepted row is read through
        # it, so the fold hands it the standing offsets before the
        # change test.  `apply_standing_context` re-derives the marginal
        # from scores/knots/probs -- idempotent, never a double
        # correction -- so a re-fit over unchanged evidence lands as the
        # row already standing and folds as nothing: the stripped/
        # corrected ping-pong that re-fired scan and retry on every
        # calibrate pass is unrepresentable (2026-10-03).
        if fact.accepted and not fact.ctx_adopted:
            region_ctx = self._region_ctx.get(wid[:3])
            if region_ctx is not None and region_ctx.adopted:
                fact = calibrate.apply_standing_context(fact, region_ctx)
        standing = self._evidence.get(wid)
        fit_changed = (
            standing is None
            or standing.accepted != fact.accepted
            or standing.refusal_reason != fact.refusal_reason
            or standing.n_search != fact.n_search
            or standing.patch_ordinal != fact.patch_ordinal
            or not np.array_equal(standing.page_cells_yx,
                                  fact.page_cells_yx)
            or not np.array_equal(standing.scores, fact.scores,
                                  equal_nan=True)
            or not np.array_equal(standing.reference_values,
                                  fact.reference_values)
            or not np.array_equal(standing.knots, fact.knots,
                                  equal_nan=True)
            or not np.array_equal(standing.probs, fact.probs,
                                  equal_nan=True)
            or not np.array_equal(standing.marginal_llr, fact.marginal_llr,
                                  equal_nan=True))
        read_changed = (
            standing is None
            or standing.ctx_adopted != fact.ctx_adopted
            or standing.heldout_logloss != fact.heldout_logloss
            or not np.array_equal(standing.printed_llr, fact.printed_llr,
                                  equal_nan=True))
        if not fit_changed and not read_changed:
            if sched_trace.TRACE.enabled:
                _note_fold("evidence", wid, False, standing, fact,
                           "printed_llr", (), "identical",
                           self._window_cover.get(wid, ()))
            return False, (), "other"
        self._evidence[wid] = fact
        old_cover = self._window_cover.get(wid, ())
        keys: list[FactKey] = []
        if fit_changed:
            self._evidence_reach[wid] = refine.reach_tiles(
                fact.page_cells_yx)
            keys.append((KEY_EVIDENCE_FIT, wid))
            covered = (tiles.cover_keys(
                int(fact.page),
                tiles.evidence_cover_cells(self.lookup, fact.page_cells_yx),
                wid[0], wid[1]) if fact.accepted else ())
            _update_cover(self._tile_cover_k, self._window_cover, wid,
                          covered)
        if read_changed:
            keys.append((KEY_EVIDENCE_READ, wid))
        # The UNION of the old and the new cover: a tile this window
        # LEAVES has lost a component and its cut has moved too.  On the
        # read-only path the two are the same set and the LLRs are what
        # moved.
        self._advance_tile_lanes(
            set(self._window_cover.get(wid, ())) | set(old_cover))
        if sched_trace.TRACE.enabled:
            _note_fold("evidence", wid, True, standing, fact,
                       "printed_llr", tuple(keys),
                       ("fit+read" if fit_changed and read_changed
                        else "fit" if fit_changed else "read"),
                       self._window_cover.get(wid, ()))
        return True, tuple(keys), "other"

    def _fold_ctx_outcome(
            self,
            fact: calibrate.CtxOutcome) -> tuple[bool, tuple[FactKey, ...],
                                                 str]:
        """The region decision, then the catch-up over the rows standing NOW.

        The outcome carries no rows (2026-10-03): folding the job's
        prepare-time corrections was last-write-wins over any newer fit
        of the same window that merged while the ctx ran.  An ADOPTED
        decision is stored first and then re-applied to every accepted
        row standing in the region; a held or refused one has nothing to
        re-fold, because the fold head corrected every row under the
        standing offsets as it arrived -- which is also what keeps a
        refused re-fit from starving a late window (bc730a0, 274 e029
        certificates, 2026-08-30).
        """
        region_key = fact.region_key
        if not _adopts(self._region_ctx.get(region_key), fact.ctx,
                       data.region_ctx_ordinal):
            return False, (), "other"
        self._region_ctx[region_key] = fact.ctx
        keys: list[FactKey] = [(KEY_REGION_CTX,) + tuple(region_key)]
        if not fact.ctx.adopted:
            return True, tuple(keys), "other"
        for wid in self.evidences():
            if wid[:3] != region_key:
                continue
            row = self._evidence[wid]
            if not row.accepted:
                continue
            after = calibrate.apply_standing_context(row, fact.ctx)
            changed, evidence_keys, _kind = self._fold_evidence(after)
            if changed:
                self._births(after)
                keys.extend(evidence_keys)
        return True, tuple(keys), "other"

    def _fold_refine_outcome(
            self,
            fact: refine.RefineOutcome) -> tuple[bool, tuple[FactKey, ...],
                                                 str]:
        if not fact.revision.adopted:
            return True, (), "other"
        placement = self._placements[fact.window_id]
        revised = refine.revised_placement(placement, fact.revision)
        if fact.revision.candidate_logloss is not None:
            revised = replace(
                revised, quality=float(fact.revision.candidate_logloss))
        changed, keys, _kind = self._fold_placement(revised)
        if changed:
            self._births(revised)
        # `_kind` is DISCARDED, and faithfully so: `_merge`'s old test
        # was `isinstance(fact, data.Placement)` and a RefineOutcome is
        # not one, so a refinement has never counted toward `n_words`
        # even when it adopts a word route.  Now that the fold names the
        # route, that is a hole with a name; it is left alone because
        # changing it moves a published tally.
        return True, keys, "pose"

    #: THE VERDICT IS A FACT WITH A KEY, and that is what turns the
    #: residue ladder from a birth-time fan-out into a subscription: a
    #: rung reads the verdicts of the stages that arm it and re-prices
    #: itself when one of them moves.  Two ledgers of the STANDING
    #: verdict, on purpose -- the component-keyed `_attempt_outcomes` is
    #: `prepare_retry`'s idempotence floor and knows the component SET,
    #: the narrow `_attempt_latest` is what a subscriber can spell from
    #: its subject.  An identical `(outcome, generation)` on an
    #: unchanged ledger is refused exactly as it was before.  The third
    #: cell this fold writes is not a ledger of verdicts but the
    #: monotone failure memory per footing, below.
    def _fold_attempt(
            self,
            fact: data.AttemptFact) -> tuple[bool, tuple[FactKey, ...],
                                             str]:
        key = tiles.fact_attempt_key(fact)
        narrow = tiles.attempt_wake_key(self, fact)
        verdict = (fact.outcome, int(fact.generation))
        # THE MONOTONE HALF, and it is the residue ladder's franchise.
        # `_attempt_latest` keeps ONE standing verdict per narrow key,
        # so a chain head whose next read comes back below the attempt
        # floor REPLACES the failure that armed the rungs.  Base had no
        # such door -- a residue bookmark was born by the failure and
        # lived until a certificate -- so the fact that a cut once
        # failed is remembered here, and only a certificate takes the
        # stream out (2026-09-21 review; `local_ctx._failed_at`).
        # It is remembered per FOOTING, not per narrow key, so it
        # outlives the lane's place in the cover: the narrow key names a
        # lane, and a lane that leaves the cover is no longer one the
        # residue rows enumerate (2026-10-03; the lane-keyed set beside
        # it was dead and went 2026-10-18, review D11).
        if fact.outcome == tiles.OUTCOME_FAILED:
            self._attempt_ever_failed_footing.add(
                (fact.page, fact.ty, fact.tx, fact.stream_id, fact.stage,
                 tiles.attempt_footing(self, fact)))
        ledger_same = self._attempt_outcomes.get(key) == fact.outcome
        if ledger_same and self._attempt_latest.get(narrow) == verdict:
            return False, (), "other"
        self._attempt_outcomes[key] = fact.outcome
        self._attempt_latest[narrow] = verdict
        return True, ((KEY_ATTEMPT,) + narrow,), "other"

    def _fold_color_row(
            self,
            fact: data.ColorEvidenceRow) -> tuple[bool, tuple[FactKey, ...],
                                                  str]:
        key = (fact.capture_id, fact.level_index, fact.page,
               fact.patch_ordinal)
        standing = self._color_rows.get(key)
        changed = (standing is None
                   or standing.heldout_logloss != fact.heldout_logloss
                   or not np.array_equal(standing.values, fact.values,
                                         equal_nan=True)
                   or not np.array_equal(standing.page_cells_yx,
                                         fact.page_cells_yx))
        reason = "identical"
        if changed and standing is not None:
            mode = getattr(self, "_color_row_adopt", ADOPT_LAST)
            if mode != ADOPT_LAST and _quality_refuses(mode, standing, fact):
                changed = False
                reason = f"refused_{mode}"
        if not changed:
            if sched_trace.TRACE.enabled:
                _note_fold("color_row", key, False, standing, fact,
                           "values", (), reason,
                           self._color_row_cover.get(key, ()))
            return False, (), "other"
        self._color_rows[key] = fact
        old_cover = self._color_row_cover.get(key, ())
        covered = tiles.cover_keys(
            int(fact.page),
            tiles.color_cover_cells(self.geometry, fact.page_cells_yx),
            fact.capture_id, fact.level_index)
        _update_cover(self._tile_cover_color, self._color_row_cover, key,
                      covered)
        self._advance_tile_lanes(set(covered) | set(old_cover))
        keys = ((KEY_COLOR_ROW,) + key,)
        if sched_trace.TRACE.enabled:
            _note_fold("color_row", key, True, standing, fact, "values",
                       keys, "adopted", covered)
        return True, keys, "other"

    def _fold_color_pop(
            self,
            fact: data.ColorCtxPopulation) -> tuple[bool,
                                                    tuple[FactKey, ...], str]:
        key = (fact.capture_id, fact.level_index, fact.page)
        standing = self._color_pops.get(key)
        changed = (standing is None
                   or standing.rung != fact.rung
                   or not np.array_equal(standing.keys_pyx, fact.keys_pyx)
                   or not np.array_equal(standing.states, fact.states)
                   or not np.array_equal(standing.kinds, fact.kinds)
                   or not np.array_equal(standing.bins, fact.bins)
                   or not np.array_equal(standing.search, fact.search)
                   or not np.array_equal(standing.scores, fact.scores,
                                         equal_nan=True))
        if not changed:
            return False, (), "other"
        self._color_pops[key] = fact
        self._pop_lanes.setdefault((fact.page, fact.rung), set()).add(key)
        return True, ((KEY_COLOR_POP, fact.page, fact.rung),), "other"

    def _fold_pooled_ctx(
            self,
            fact: data.PooledColorCtx) -> tuple[bool, tuple[FactKey, ...],
                                                str]:
        key = (fact.page, fact.rung)
        if not _adopts(self._pooled_ctx.get(key), fact,
                       data.pooled_ctx_ordinal):
            return False, (), "other"
        self._pooled_ctx[key] = fact
        return True, ((KEY_POOLED_CTX, fact.page, fact.rung),), "other"

    def _fold_field_observations(
            self, fact: data.FieldObservations,
            ) -> tuple[bool, tuple[FactKey, ...], str]:
        """Cell per (capture, page); wake key the PAGE.

        The coarser wake key is `_fold_color_pop`'s own shape: the solve
        is page-scoped and subscribes once, so a second capture's
        collection re-arms it without any per-capture subscription and
        without a read set that has to grow.

        The revision is the ordinal (I12), and it is the store's own,
        restored on resume — so a resumed run's first collection
        outranks the collection the interrupted run made, and its solve
        outranks the field the snapshot restored, with no clock to
        carry.
        """
        key = (fact.capture_id, int(fact.page))
        if not _adopts(self._field_observations.get(key), fact,
                       data.field_observations_ordinal):
            return False, (), "other"
        self._field_observations[key] = fact
        return True, ((KEY_FIELD_OBS, int(fact.page)),), "other"

    def _fold_evidence_revision(
            self, fact: data.EvidenceRevision,
            ) -> tuple[bool, tuple[FactKey, ...], str]:
        """Restore a capture-page's revision, never lower it.

        `max` and not assignment: the resume folds the placements and
        the certificates that survived beside this number, and each of
        those advances the revision on its own.  Whichever count is
        higher is the one that keeps the collection ordinal monotone
        across the resume, which is the property I12 asks for.
        """
        key = (str(fact.capture_id), int(fact.page))
        standing = self._evidence_revision.get(key, 0)
        if int(fact.revision) <= standing:
            return False, (), "other"
        self._evidence_revision[key] = int(fact.revision)
        return True, (), "other"

    def _advance_evidence(self, capture_id: str, page: int) -> None:
        """One event on one capture-page's evidence (I12).

        Bookkeeping and never a trigger: many advances between two
        admissions of the collect row buy ONE collection, and that
        collection re-measures only the (tile, plane)s whose inputs
        moved (design §2.7).
        """
        key = (str(capture_id), int(page))
        self._evidence_revision[key] = self._evidence_revision.get(key, 0) + 1

    #: INV-G1, and it is what makes the residue rows' narrowed reads
    #: safe: EVERY call to this helper happens inside a fold that also
    #: emits a key `tiles.scan` (or `tiles.union`) subscribes to over
    #: the same cover -- `evidence_fit`, `evidence_read` or `color_row`.
    #: So a generation can never move without the chain HEAD being
    #: re-armed, and the head's new verdict is what re-arms the rungs.
    #: Break it and the whole residue freezes silently.
    #:
    #: BOTH counters are bumped here, and the footing's is bumped ONCE
    #: PER LANE EVENT rather than read as a sum over the cover: a sum
    #: goes down when a lane leaves (2026-09-21 review), and `eligible`
    #: compares these with `==`.
    def _advance_tile_lanes(self, keys: set[tiles.CoverKey]) -> None:
        for key in sorted(keys):
            self._tile_lane_generation[key] = (
                self._tile_lane_generation.get(key, 0) + 1)
            page, ty, tx, capture_id, level_index = key
            level = self._levels.get((capture_id, level_index))
            if level is None:
                continue
            footing = (page, ty, tx, level.ppc)
            self._union_generation[footing] = (
                self._union_generation.get(footing, 0) + 1)

    def _fold_plane_field(
            self,
            fact: data.PlaneField) -> tuple[bool, tuple[FactKey, ...], str]:
        key = (int(fact.page), int(fact.plane))
        if not _adopts(self._plane_fields.get(key), fact,
                       data.plane_field_ordinal):
            return False, (), "other"
        self._plane_fields[key] = fact
        return True, ((KEY_PLANE_FIELD,) + key,), "other"

    def _fold_color_lane_fit(
            self,
            fact: color_region_head.ColorLaneFit,
            ) -> tuple[bool, tuple[FactKey, ...], str]:
        key = (fact.capture_id, fact.level_index, fact.page)
        self._color_lane_assembled.setdefault(key, set()).update(
            fact.assembled)
        if fact.head_fitted:
            self._color_lane_head_fits[key] = (
                self._color_lane_head_fits.get(key, 0) + 1)
        if fact.head is not None:
            self._color_lane_head[key] = fact.head
        return True, (), "other"

    def _fold_certificate(
            self,
            fact: data.Certificate) -> tuple[bool, tuple[FactKey, ...],
                                             str]:
        key: CertKey = (fact.page, fact.ty, fact.tx, fact.stream_id)
        standing = self._certificates.get(key)
        if standing is not None:
            if np.array_equal(standing.user_bits, fact.user_bits):
                return False, (), "certificate"
            raise data.IntegrityError(
                f"conflicting certificates at {key}: "
                f"{standing.source} vs {fact.source}")
        counter = self.row.tile_counter(fact.page, fact.ty, fact.tx)
        index = (metadata.equation_index(counter,
                                         self.stream_index[fact.stream_id],
                                         len(self.row.streams))
                 if self.row.pooled_fountain else counter)
        bit = int(fact.user_bits[0])
        # One equation index carries one bit, so a disagreement is not a vote
        # to resolve but proof the certificate SET is inconsistent: an
        # integrity event, terminal.  Same law as the close's gate, where at
        # rank 24 the metadata word is unique and K can never be revised.
        prev = self._equations.get(index)
        if prev is not None and prev != bit:
            raise data.IntegrityError(
                f"opposite metadata bits at equation index {index} "
                f"(tile {key})")
        self._equations[index] = bit
        self._certificates[key] = fact
        # A certificate is new evidence for the field of every capture
        # standing on that face: its plane's own bits become a whole-tile
        # template there (design §2.5).  Which captures re-measure is the
        # ladder's business; this only records that they have more to
        # measure (I12).
        for capture_id in {lane[0] for lane
                           in self._lanes_on_page.get(fact.page, ())}:
            self._advance_evidence(capture_id, fact.page)
        return True, ((KEY_TILE, fact.page, fact.ty, fact.tx,
                       fact.stream_id),
                      (KEY_PAGE_CERTS, fact.page)), "certificate"

