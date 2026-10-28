"""The ingest frontier: declared scans, expanded one at a time (H4
streaming ingestion).

Streaming ingestion's descriptor half. ``capture`` owns the FIRE — open,
authenticate, survey, propose (``capture.IngestWorker``) — and this is
the provider that decides when one exists, which is the whole of the
scheduling design:

**1. Ingest is descriptor work, not a third source** (point 1). One
spendable attempt per declared scan, identity = the scan
(``capture.scan_key``: the resolved path and the operator's DPI), so the
ledger's spend row under that work id is the durable statement "this
lineage has already read these bytes at this DPI". A resumed session
therefore does not re-survey a 2.29 GB TIFF to learn facts its store
already holds — and it does not even need the ledger to say so in the
ordinary case, because the derivation below has already dropped the scan
from the frontier.

**2. Sequential by derivation, with no new gate mechanism** (point 2).
This provider mints exactly ONE descriptor: the first declared scan whose
capture record does not stand. Scan N+1 becomes expandable only when scan
N's record has landed, which buys three properties for free — the survey's
~8x-raster transient is capped at one in flight whatever the pool width
(the reason streaming beats parallel segmentation at all), ingest order is
deterministic in both the serial and the pooled lane, and the engine
needed no admission control, no lease and no gate to get either.

**Why it lives in ``solve``.** The frontier question is "which declared
scans are not yet ingested", and the join between a DECLARATION and an
acquisition RECORD can only be made by something that has opened the file
— which is the plane (``SessionPlane.scan_capture``, filled by
attach-by-reopen). ``capture`` may not import ``solve``, so the provider
that asks the plane lives on this side of the line and the worker it
mints lives on that one. R3 is untouched: ``capture`` still writes every
record it owns.

**The scan list is CLOSED OVER, not derived** (point 1, the payload
provider's precedent): the scans are session INPUTS — what the operator
typed — so the composition root hands them to the provider at
composition (``cli.real_providers``), and the provider derives only the
"not yet ingested" half against durable facts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..capture import FAMILY_INGEST, ROUTE_SURVEY, IngestWorker, scan_key
from ..core import Decline, ExpansionRequest, SolveView, WorkDescriptor
from ..format import FormatRowSpec
from .view import as_plane


class RealIngestProvider:
    """The declared scans, as one spendable attempt each — mint the head."""

    family = FAMILY_INGEST
    # Annotated, not inferred: ``core.Provider`` declares this
    # ``tuple[str, ...]`` (the B12 lesson). The frontier this expands
    # from is the session's declared scans and the capture records that
    # resolve them.
    sources: tuple[str, ...] = ("scan", "capture")

    def __init__(self, row: FormatRowSpec,
                 scans: Iterable[tuple[Path, float]] = (), *,
                 provider_id: str = "capture-ingest-v0") -> None:
        self.provider_id = provider_id
        #: The footing ladder needs the printed cell size, and that is
        #: the ONLY thing an ingest takes from the format row (§5.1:
        #: ``ppc = pitch_in x dpi``).  A PITCH, not a dot count, since
        #: C3 (RULINGS G4, 2026-08-22): the row knows what its cell
        #: physically measures, and nothing on this path knows — or
        #: needs — the dpi of the engine that printed it.
        self.pitch_in = row.pitch_in
        self.scans = tuple((Path(path), float(dpi)) for path, dpi in scans)

    def expand(self, view: SolveView,
               request: ExpansionRequest) -> tuple[WorkDescriptor, ...]:
        """The FIRST declared scan whose capture record does not stand.

        One descriptor at a time and never two: that is point 2's
        derivation chain, and it is stated as an early return rather than
        as a gate because it IS the eligibility rule — a scan whose
        predecessor has not landed is not un-schedulable, it is a scan
        this frontier cannot yet name work for.

        Total, cheap and stateless, like every other expansion: one
        dictionary lookup per declared scan, no file touched, no memo of
        its own. The plane's resolution memo is what makes it cheap, and
        the plane fills that memo on the committing thread, where the
        file was going to be opened anyway.
        """
        plane = as_plane(view)
        for path, dpi in self.scans:
            if plane.scan_capture(path, dpi) is not None:
                continue
            return (request.mint(FAMILY_INGEST, scan_key(path, dpi),
                                 ROUTE_SURVEY),)
        return ()

    def worker(self, view: SolveView,
               descriptor: WorkDescriptor) -> IngestWorker | Decline:
        """Bind the fire. The descriptor names the scan; nothing else is read.

        The subject is looked up in the CLOSED-OVER list rather than
        parsed back out of the key: the provider's own declaration is the
        authority on what this session was handed, and a descriptor
        naming a scan this composition does not hold is not this
        provider's work.

        WHERE THE RUNGS GO IS BOUND HERE (H4-LANES stage 1). The fire
        emits the ladder's sub-native footing rasters as a by-product,
        and they belong beside the prepared planes in this lineage's
        ``<state-dir>.prepared`` sibling — which is a fact about a
        SESSION, and ``capture`` knows nothing about sessions. The plane
        does (:meth:`~holo2.solve.PlaneView.derived_directory`), and the
        plane is right here, so the directory is handed to the worker at
        binding time. Nothing about the descriptor, the identity or the
        spend moves: the fire is named by the declared scan exactly as
        before, and where it puts its derived pixels is not part of what
        it is.
        """
        for path, dpi in self.scans:
            if scan_key(path, dpi) == descriptor.subject:
                return IngestWorker(path, dpi, self.pitch_in,
                                    as_plane(view).derived_directory())
        return Decline(f"{descriptor.subject} is not a declared scan of this "
                       "session")


__all__ = ["RealIngestProvider"]
