"""RECORDS capture owns: what an acquisition durably IS (§5.1, §5.3).

``ingest`` is the writer of every record here, which is why they live in
this package (R3 ownership rule: the package that WRITES a family owns
its schema). Nothing else may mint them — a capture record is an
authentication fact and a region record is a survey fact.

* :class:`CaptureRecord` (+ :class:`FootingSpec`) — one authenticated
  acquisition and its derived footing ladder. ``source_sha256`` is THE
  acquisition identity (L1).
* :class:`RegionRecord` — one surveyed payload region of one capture.

Shape change, R3 (OR-12 closed) and the hash-free identity law
--------------------------------------------------------------
``RegionRecord`` gained its **capture parent** and the **support-grid
geometry** its lattice is laid out on: ``support_origin_px``,
``support_step_px``, ``support_extent_px``. Before R3 the region id
digested exactly those components and the record kept none of them, so
durable state alone could not place the region's lattice — the H3bis
real-run diagnosis found this the hard way, and DESIGN §15 OR-12 recorded
it. With the mask blob beside them, the three fields rebuild the survey's
``SupportMask`` exactly, and the cell lattice is then
``CellLattice.over(support_origin_px, support_extent_px, pitch)`` with the
pitch derived from the declared dpi and ``pitch_in_vote``
— all durable. Re-surveying on resume remains an operational choice, not
a requirement to KNOW the geometry.

The identity law then made the digest id redundant and it is **gone**
(2026-08-11): a region IS its capture and its support grid, so
:func:`region_key` builds the key from exactly those values and the
record carries no ``region_id`` field to disagree with its key. The
family validates the agreement at the commit wall and at load (F-07's
mechanism, second adopter).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from ..core import (BlobRef, CaptureSha, CommitRefusal, FootingId, KeyField,
                    KeySpec, RecordFamily, ResourceKey, build_key,
                    collection_key, parse_key, require_finite_positive,
                    require_own_key, require_sha256_hex)

KIND_CAPTURE = "capture"
KIND_REGION = "region"
KIND_ATTACHMENT = "attachment"
KIND_SCAN = "scan"

#: A region key, declared as slots (``core.keys``): capture sha, support
#: origin y/x, step, extent y/x. The arity is DERIVED from the spec and
#: exported, because ``solve``'s ``window`` embeds these parts wholesale
#: and an embed is only injective against a fixed arity.
REGION_SPEC = KeySpec(KIND_REGION, (
    KeyField("capture_sha256"), KeyField("origin_yx", 2, cast=int),
    KeyField("step_px", cast=int), KeyField("extent_px", 2, cast=int)))
REGION_KEY_PARTS = REGION_SPEC.arity


def capture_key(source_sha256: CaptureSha) -> ResourceKey:
    return ResourceKey(KIND_CAPTURE, (source_sha256,))


def region_key(capture_sha256: CaptureSha, origin_yx: tuple[int, int],
               step_px: int, extent_px: tuple[int, int]) -> ResourceKey:
    """One surveyed region, named by the values that define it (§10.2).

    The support grid — origin, step, extent — is what the region IS on
    its capture: it places the lattice, it clips the last row and column,
    and two distinct regions of one capture are two distinct grids.
    """
    return build_key(REGION_SPEC, capture_sha256=capture_sha256,
                     origin_yx=origin_yx, step_px=step_px,
                     extent_px=extent_px)


def parse_region_key(key: ResourceKey) -> tuple[CaptureSha, tuple[int, int],
                                                int, tuple[int, int]]:
    """The values a region key names, back out of it."""
    values = parse_key(REGION_SPEC, key)
    return (CaptureSha(values["capture_sha256"]), values["origin_yx"],
            values["step_px"], values["extent_px"])


def attachment_key(source_sha256: CaptureSha) -> ResourceKey:
    """M12: "this capture's pixels are attached to this session".

    Physical work whose raster is detached names this key and declines
    with it as its wake, so a resume with capture B attached sleeps A's
    windows instead of losing them. The key carries no record; an absent
    record reads as ``ABSENT_VERSION`` like any other key.
    """
    return ResourceKey(KIND_ATTACHMENT, (source_sha256,))


#: A DECLARED scan, as slots: the resolved source path and the
#: operator-declared true DPI. Those two values are the whole of what an
#: operator hands a session about an acquisition, and they are what a
#: streaming ingest is named — and spent — by.
SCAN_SPEC = KeySpec(KIND_SCAN, (KeyField("path"),
                                KeyField("dpi", cast=float)))


def scan_key(path: Path | str, dpi: float) -> ResourceKey:
    """One DECLARED acquisition input — the streaming ingest's subject.

    THE ONE KEY IN THIS PACKAGE THAT IS NOT A FACT ABOUT BYTES (H4
    streaming ingestion). Every other name here hangs off
    ``source_sha256``, which is the acquisition identity (L1) — and
    which nobody can know before the file has been read. Streaming
    ingestion needs a name for the work of
    finding that out, so it names the DECLARATION instead: the path the
    operator typed (resolved, so a rerun from another directory is the
    same declaration) and the DPI they declared with it. Change either and
    it is a different scan, which is exactly right — a corrected DPI is a
    different acquisition interpretation (Q2), and a different file is a
    different file.

    It carries no record, like :func:`attachment_key`. What makes it
    durable is the SPEND row an ingest attempt leaves under it: "this
    lineage has already read these bytes at this DPI" is a ledger fact,
    which is what keeps a resumed session from re-surveying a 2.29 GB TIFF
    to learn what its store already holds.
    """
    return build_key(SCAN_SPEC, path=str(Path(path).resolve()),
                     dpi=float(dpi))


def parse_scan_key(key: ResourceKey) -> tuple[Path, float]:
    """The declared path and DPI a scan key names, back out of it."""
    values = parse_key(SCAN_SPEC, key)
    return Path(values["path"]), float(values["dpi"])


#: Every authenticated capture. A capture arriving mid-session is a
#: frontier expansion (M3/M12), not a worker.
COLLECTION_CAPTURES = collection_key("captures")


@dataclass(frozen=True)
class FootingSpec:
    """§5.1: one (capture, aperture) evidence lane — its capture INCLUDED.

    B9 (F-05/D5c) collapsed ``ingest.FootingView`` into this record. The
    view existed for one reason: a footing must answer "which capture am
    I a lane of?" and the durable spec could not, so an in-memory pair
    was rebuilt on every ingest — which also meant only an INGESTED
    capture had footings at all. With the parent on the record the lane
    answers by record, which is exactly what the catalog path needs: a
    resumed session handed no pixels still holds every footing its
    durable evidence cites (``capture.catalog``).

    The parent is validated against :class:`CaptureRecord`'s own identity
    (below), so the repetition cannot drift, and the family version bump
    (1 -> 2) refuses a state written before the collapse.
    """

    footing_id: FootingId
    ppc: Fraction
    capture_sha256: CaptureSha

    def __post_init__(self) -> None:
        require_sha256_hex(self.capture_sha256, "FootingSpec.capture_sha256")


@dataclass(frozen=True)
class CaptureRecord:
    """§5.1. ``source_sha256`` is THE acquisition identity (L1).

    The structural checks mirror ``scan.SourceId``'s and are not
    redundant with them: ``SourceId`` guards the INGEST boundary, this
    guards the LOAD one (``store`` decodes an envelope straight into this
    constructor), which is where a nonfinite ``dpi_true`` would arrive.
    Two of the four are ``core``'s shared validators — the same value
    laws every wall in the tree states, spelled once.

    ``platen_backing`` (v3, 2026-08-17) is the median native luma of the
    raster's four 32-px borders — the scalar every unsupported pixel of
    every region is filled to, and one of the inputs ``solve.prepared``
    hashes into a prepared plane's file name. It is a deterministic
    function of the authenticated bytes like ``shape_px`` and ``dtype``,
    so F-08's freeze covers it on exactly the same terms; what makes it a
    RECORD rather than a session memo is that a resume without the file
    cannot compute it, and therefore could not name the prepared planes
    already sitting in ``<state-dir>.prepared``. It may legally be 0.0 (a
    black border), so the guard is finiteness, not positivity.
    """

    source_sha256: CaptureSha
    dpi_true: float
    shape_px: tuple[int, int]
    dtype: str
    channels: int
    platen_backing: float
    footings: tuple[FootingSpec, ...]

    def resource_key(self) -> ResourceKey:
        return capture_key(self.source_sha256)

    def __post_init__(self) -> None:
        require_sha256_hex(self.source_sha256, "CaptureRecord.source_sha256")
        require_finite_positive(self.dpi_true, "CaptureRecord.dpi_true")
        if not np.isfinite(self.platen_backing):
            raise ValueError("CaptureRecord.platen_backing must be finite")
        try:
            np.dtype(self.dtype)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid CaptureRecord.dtype {self.dtype!r}") from exc
        if len(self.shape_px) != 2 or any(value < 1 for value in self.shape_px):
            raise ValueError(
                "CaptureRecord.shape_px must be two positive integers")
        if self.channels not in (1, 3):
            raise ValueError("CaptureRecord.channels must be 1 or 3")
        ppcs = [footing.ppc for footing in self.footings]
        if any(b <= a for a, b in zip(ppcs, ppcs[1:])):
            raise ValueError("CaptureRecord.footings must ascend in ppc (§5.1)")
        foreign = sorted({footing.capture_sha256 for footing in self.footings}
                         - {self.source_sha256})
        if foreign:
            raise ValueError(
                f"CaptureRecord.footings name capture {foreign[0][:12]}, not "
                f"{self.source_sha256[:12]} — a lane belongs to ONE "
                "acquisition (§5.1)")


@dataclass(frozen=True)
class RegionRecord:
    """§5.3, per (capture, region) — with the lattice it sits on (OR-12).

    DEVIATION from the §5.3 sketch (H2c, listed for adjudication):
    ``pitch_in_vote`` is ``Fraction | None``, not required. The survey
    legally declines to name one cell pitch for a platen — no credible
    lattice line, no candidate pitch within tolerance, or a tied vote —
    and ``survey.RegionCandidate`` already carries that refusal as
    ``None`` rather than inventing a pitch (L4: no manufactured facts).
    Widening the record is the alternative to either fabricating a vote
    at the store boundary or dropping a real region from the durable
    plane; a region with no vote is recorded honestly and schedules no
    windows (``solve.plans.region_view``).

    C3 (RULINGS G4, 2026-08-22) made the vote a PITCH — an exact
    rational of an inch, serialised by the codec as
    ``[numerator, denominator]`` — where it was ``c_dots_vote: int``, a
    count of dots on a 600-dpi engine grid the receiver never observed.
    The family version goes 3 -> 4 and a state written before it refuses
    at open BY NAME (the freshness doctrine: holo2 state is regenerable
    and there are no migration decoders).

    The support fields are the survey's own block-constant grid: cell
    ``(iy, ix)`` of ``support_mask_ref`` covers the half-open native
    rectangle at ``support_origin_px + support_step_px * (iy, ix)``, and
    ``support_extent_px`` clips the last row and column at the capture
    boundary. They are also, with the capture sha, this record's
    IDENTITY: :meth:`resource_key` rebuilds the key it is stored under.
    """

    capture_sha256: CaptureSha
    support_mask_ref: BlobRef
    pitch_in_vote: Fraction | None
    support_origin_px: tuple[int, int]
    support_step_px: int
    support_extent_px: tuple[int, int]

    def resource_key(self) -> ResourceKey:
        return region_key(self.capture_sha256, self.support_origin_px,
                          self.support_step_px, self.support_extent_px)

    def __post_init__(self) -> None:
        if min(self.support_origin_px) < 0:
            raise ValueError("RegionRecord.support_origin_px must be >= 0")
        if self.support_step_px < 1:
            raise ValueError("RegionRecord.support_step_px must be positive")
        if min(self.support_extent_px) < 1:
            raise ValueError("RegionRecord.support_extent_px must be non-empty")
        if self.pitch_in_vote is not None and self.pitch_in_vote <= 0:
            raise ValueError(
                "RegionRecord.pitch_in_vote must be positive or None")


def _capture_collections(key: ResourceKey,
                         record: CaptureRecord) -> tuple[ResourceKey, ...]:
    return (COLLECTION_CAPTURES,)


def _capture_transition(key: ResourceKey, current: CaptureRecord,
                        proposed: CaptureRecord) -> None:
    """Q2 answered in its "reject the conflict" form: one capture, one DPI.

    ``source_sha256`` is the acquisition identity (L1), but the DECLARED
    dpi is what every derived id hangs off: a footing is
    ``ppc = pitch_in * dpi`` with the aperture in its id (L2), and every
    ``EvidenceObservation`` key names a footing. A corrected DPI therefore
    renames every footing under the evidence citing it and re-mints every
    region while the old ones stay as unreachable geometry — silently
    reinterpreting old evidence, the one option Q2 forbids. Until F-05
    gives an interpretation its own identity, the conflict is refused.

    F-08 (2026-08-13) extends the same law to the WHOLE record: shape,
    dtype, channels, the platen backing and the footing ladder are
    deterministic functions of
    the authenticated bytes and the session's row, so a lawful re-ingest
    re-derives EQUAL content (B9's fresh-survey-wins is a no-op here) and
    a differing one means the ingest code moved — pre-freeze rule, refuse
    loudly rather than reinterpret standing evidence.
    """
    if not isinstance(current, CaptureRecord) or proposed == current:
        return
    if proposed.dpi_true != current.dpi_true:
        raise CommitRefusal(
            f"{key}: this capture is already ingested at dpi_true "
            f"{current.dpi_true:g}; refusing {proposed.dpi_true:g} — a "
            "corrected DPI renames every footing the committed evidence "
            "cites (Q2/F-05)")
    raise CommitRefusal(
        f"{key}: a capture record is acquisition truth (L1) and is frozen "
        "(F-08); a differing re-ingest of identical bytes means the "
        "derivation moved")


def _region_transition(key: ResourceKey, current: RegionRecord,
                       proposed: RegionRecord) -> None:
    """F-08: a surveyed region is FROZEN under its name.

    The capture and the support grid ARE the key; what a write at the
    same key could still alter is the survey's content — the pitch vote
    and the support-mask blob — which committed windows and poses stand
    on. The survey is deterministic over (bytes, dpi), so B9's
    fresh-survey-wins rule re-derives EQUAL records (a no-op here); a
    differing re-survey is a code change and refuses loudly (pre-freeze
    rule).
    """
    if isinstance(current, RegionRecord) and proposed != current:
        moved = tuple(name for name in ("pitch_in_vote", "support_mask_ref")
                      if getattr(proposed, name) != getattr(current, name))
        raise CommitRefusal(
            f"{key}: region survey content is frozen (F-08); refusing a "
            f"write that moves {', '.join(moved) or 'derived fields'}")


def _region_references(key: ResourceKey,
                       record: RegionRecord) -> tuple[ResourceKey, ...]:
    """A region stands on the capture it was surveyed from (F-07).

    LAW on the live path: ``ingest`` mints the capture record and every
    region of it in ONE batch (batch inclusion), and a re-ingest that
    re-derives an identical capture record commits its new regions
    against the capture already standing. A region whose capture is
    absent is unplaceable geometry — its lattice is
    ``support_origin/step/extent`` INTERPRETED at the capture's declared
    dpi, so without the capture there is nothing to interpret it with.
    """
    return (capture_key(record.capture_sha256),)


def _validate_region(key: ResourceKey, record: RegionRecord) -> None:
    """The key IS this region's identity: the two must agree (F-07).

    Key-aware, so a record stored under a key that names a different
    support grid is refused at the commit wall and at load rather than
    read back as geometry it is not. The parse in front of the shared
    check is the slot spec's own guard, kept because a region key is the
    one this package hands out for OTHERS to embed (``solve``'s window
    carries its six parts wholesale).
    """
    parse_region_key(key)
    require_own_key(key, record)


#: capture's families, registered by the composition root. ``RegionRecord``
#: is at version 4: R3 gave it the capture parent and the support-grid
#: geometry, and the identity law took its digest id away (v3), and C3
#: turned the survey's ``c_dots_vote: int`` into ``pitch_in_vote:
#: Fraction | None`` (v4, RULINGS G4, 2026-08-22) — so a state written
#: before any of them refuses at open by name. ``CaptureRecord`` is at
#: version 3 for the same reason, twice: B9's ``FootingView`` ->
#: ``FootingSpec`` collapse put the capture parent on every footing (v2),
#: and ``platen_backing`` joined the record on 2026-08-17 (v3) so a
#: pixel-free resume can name the prepared planes it already has. The
#: MANIFEST is what refuses an older state, by name — the state
#: directory's own layout did not move, so ``store.SCHEMA_VERSION`` does
#: not (its docstring draws exactly that line). State is regenerable;
#: there are no migration decoders.
RECORD_FAMILIES: tuple[RecordFamily, ...] = (
    # F-07's cheap adopter here: ``source_sha256`` is THE acquisition
    # identity (L1) and it IS the key, so a capture record filed under
    # another capture's sha — the one way an authentication fact can lie
    # about which bytes it authenticates — is refused at the wall and at
    # load, where every footing and region derived from it would inherit
    # the wrong parent.
    # F-07's relational half: a capture DECLARES NO REFERENCES, and the
    # reason is the L1 law itself — an acquisition is a root fact. It
    # stands on the authenticated bytes and on nothing durable: its
    # footings name their own capture (checked above, not a reference to
    # another record), and every other record in the tree is downstream
    # of it. There is nothing here that could dangle.
    RecordFamily(CaptureRecord, KIND_CAPTURE, version=3, structural=True,
                 validate=require_own_key,
                 transition=_capture_transition,
                 collections=_capture_collections),
    RecordFamily(RegionRecord, KIND_REGION, version=4, structural=True,
                 validate=_validate_region,
                 transition=_region_transition,
                 references=_region_references),
)

__all__ = [
    "COLLECTION_CAPTURES", "CaptureRecord", "FootingSpec", "KIND_ATTACHMENT",
    "KIND_CAPTURE", "KIND_REGION", "KIND_SCAN", "RECORD_FAMILIES",
    "REGION_KEY_PARTS", "RegionRecord", "attachment_key", "capture_key",
    "parse_region_key", "parse_scan_key", "region_key", "scan_key",
]
