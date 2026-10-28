from __future__ import annotations

from ..data import (
    Certificate,
    LatticeSeed,
    Placement,
    WindowEvidence,
    WindowId,
)
from ..descriptor import (
    FactKey,
    Job,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    KEY_LANE_POSES,
    KEY_POSE_AFFINE,
    KEY_REGION_CTX,
    KEY_REGION_PITCH,
    KEY_TILE,
    PluginDescriptor,
    Subject,
)
from ..format.identity import Family
from . import calibrate, place_sched, refine


def _revisit_calibrate(store: object, wid: WindowId) -> Job | None:
    return calibrate.window_job(store, wid)


def _revisit_place(store: object, wid: WindowId) -> Job | None:
    state = store.place_stage(wid)
    if state is None or state.placed \
            or place_sched.dormant(store, state, wid):
        return None
    if store.frame(wid[:3]) is None:
        return None
    if store.window_fully_done(wid):
        return None
    seeds = place_sched.untried_consult(store, state, wide=False)
    if not seeds:
        return None
    return place_sched.ring_pass_job(store, state, None, False, None, (),
                                     seeds)


def prepare_revisit(store: object, subject: Subject,
                    stage: str) -> Job | None:
    wid: WindowId = subject
    if store.placement(wid) is not None:
        evidence = store.evidence(wid)
        if evidence is None or evidence.accepted:
            return None
        return _revisit_calibrate(store, wid)
    return _revisit_place(store, wid)


def _revisit_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    subjects: list[Subject] = []
    for wid in store.placements():
        evidence = store.evidence(wid)
        if evidence is None or evidence.accepted:
            continue
        placement = store.placement(wid)
        if placement.page != fact.page:
            continue
        reach = store.window_reach(wid)
        if reach is None:
            continue
        if (fact.ty, fact.tx) in reach:
            subjects.append(wid)
    lanes = store.lanes_on_page(fact.page)
    for wid in store.windows():
        if (wid[0], wid[1]) not in lanes:
            continue
        state = store.place_stage(wid)
        if state is None or state.placed:
            continue
        subjects.append(wid)
    return tuple(subjects)


def _revisit_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    wid: WindowId = subject
    placement = store.placement(wid)
    if placement is not None:
        keys: list[FactKey] = [
            (KEY_POSE_AFFINE, wid),
            (KEY_EVIDENCE_FIT, wid),
            (KEY_EVIDENCE_READ, wid),
            (KEY_REGION_PITCH, wid[0], wid[1], wid[2]),
            (KEY_REGION_CTX, wid[0], wid[1], wid[2])]
        reach = store.window_reach(wid)
        if reach is not None:
            for ty, tx in reach:
                for stream in store.row.streams:
                    keys.append((KEY_TILE, placement.page, ty, tx,
                                 stream.stream_id))
        return tuple(keys)
    return tuple((KEY_LANE_POSES, wid[0], wid[1], page)
                 for page in sorted(store.live_pages()))


def _revisit_eligible(store: object, subject: Subject) -> bool:
    # the done gate, ahead of both branches: a never-placed window whose
    # supported extent is covered by certified tiles has nothing left to
    # place, and a calibration-refused one whose reach is certified in
    # every stream has nothing left to read
    if store.window_fully_done(subject):
        return False
    if store.placement(subject) is None:
        return True
    evidence = store.evidence(subject)
    return evidence is not None and not evidence.accepted


def _revisit_retire(store: object, subject: Subject) -> bool:
    placement = store.placement(subject)
    if placement is None:
        return False
    if store.row.family is not Family.K:
        return True
    evidence = store.evidence(subject)
    return evidence is not None and evidence.accepted


def _revisit_stage(store: object, subject: Subject) -> str | None:
    return refine.STAGE_REFINE


def _revisit_cost(store: object, subject: Subject, stage: str,
                  attempts: int, last_cost: int) -> int:
    return refine.REFINE_COST


REVISIT_DESCRIPTOR = PluginDescriptor(
    name="revisit",
    subject_kind="window",
    born_by=(Certificate,),
    subjects_of=_revisit_subjects,
    reads=_revisit_reads,
    eligible=_revisit_eligible,
    stage=_revisit_stage,
    cost=_revisit_cost,
    retire=_revisit_retire,
    prepare=prepare_revisit,
    produces=(WindowEvidence, Placement, LatticeSeed,
              place_sched.PlaceOutcome),
    prices=refine.PRICES,
)
