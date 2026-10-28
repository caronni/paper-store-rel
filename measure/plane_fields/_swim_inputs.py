"""Sha-validated, read-only access to the W6 qualification state.

The subject of the swim pilot (docs/PLANE-FIELDS.md §6.5.5a) is the IDLE,
COMPLETE W6 state ``scratch/plane-fields/qual/receive.state`` — VERIFIED,
three 2400 dpi Canon captures, plane-fields dial ON, 5,549 certificates.
It is 3.95 GB and ``load_session`` costs minutes, so this module reads it
ONCE and caches exactly the committed facts the pilot consumes
(``_inputs``/``_color_uplift_harness.state_cache`` precedent, extended to
a MULTI-capture state):

* the close facts and every capture's facts + scale plan + level rows;
* every ``SurveyRegionRecord`` and ``PoseRecord`` (the committed
  geometry, per capture and lane);
* every ``TileCertificateRecord`` (the tier-i evidence and the residue
  the pilot's targets are drawn from).

Durable evidence blocks are never cached — they are the bulk of the file
and the pilot re-derives its own from pixels.

The cache is keyed by the state's SHA-256 plus ``CACHE_VERSION``, so an
edited or re-decoded state can never be reused silently.  NOTHING is ever
written next to the state: the pilot's whole output tree is
``scratch/plane-fields/swim-pilot/``.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

from ._inputs import (  # re-exported: one definition of each shared pin
    MAIN_SCRATCH,
    REGMAP_GT,
    REPO,
    SHEET_I_SCANS,
    recorded_scan_shas,
    sha256_file,
    tree_moved,
    tree_state,
)

CACHE_VERSION = 2
SCHEMA = "plane-fields-swim-pilot-cache-v1"

#: The W6 qualification state (docs/PLANE-FIELDS.md §6.4), dial ON.
QUAL_STATE = MAIN_SCRATCH / "plane-fields" / "qual" / "receive.state"
OUT_DIR = MAIN_SCRATCH / "plane-fields" / "swim-pilot"
CACHE_DIR = OUT_DIR / "cache"

FORMAT_REF = "L:c2-cmy8-r0700-p120-x1@3392x2368"
CAPTURE_DPI = 2400.0
#: The twelve pre-registered dead-band tile columns (§6.5.5a bar).
DEAD_BANDS = (8, 9, 10, 11, 15, 16, 17, 18, 19, 27, 28, 29)
PLANES = ("C", "M", "Y")

#: Paths that MUST NOT be touched: a second receiver is live on this tree.
FORBIDDEN_PREFIXES = (
    str(MAIN_SCRATCH / "xerox-v1-20260818" / "I-multi-pf"),
)


def refuse_forbidden(path: Path) -> None:
    """Hard stop before any access to the live run's state directory."""
    resolved = str(Path(path).resolve())
    for prefix in FORBIDDEN_PREFIXES:
        if resolved.startswith(prefix):
            raise SystemExit(
                f"REFUSING to touch {resolved}: a receiver is writing there")


@dataclass(frozen=True, slots=True)
class CaptureRow:
    """One capture's committed facts, flattened out of the state."""

    ordinal: int
    source_sha256: str
    dpi: float
    dtype: str
    shape_yx: tuple[int, int]
    channels: int
    plan: tuple                      # LaneSpec rows, in plan order
    level_lane_ids: tuple[str, ...]
    level_certificate_counts: tuple[int, ...]
    #: certificate ids minted AT each level — the only way to ask "which
    #: lane earned this tile", which the pilot's reproduction controls
    #: need in order to be fair to a single-lane replay.
    level_certificate_ids: tuple[tuple[str, ...], ...]
    quarantined_by_lane: dict[str, tuple[int, ...]]


@dataclass(frozen=True, slots=True)
class QualFacts:
    """Everything the swim pilot reads out of the qualification state."""

    cache_version: int
    state_path: str
    state_sha256: str
    state_bytes: int
    format_row_id: str
    receiver_policy_id: str
    close_status: str
    payload_sha256: str | None
    plan_lanes_appended: tuple[str, ...]
    captures: tuple[CaptureRow, ...]
    regions: tuple                   # SurveyRegionRecord rows, all captures
    poses: tuple                     # PoseRecord rows, all captures
    certificates: tuple              # TileCertificateRecord rows
    load_seconds: float

    def capture(self, source_sha256: str) -> CaptureRow:
        for row in self.captures:
            if row.source_sha256 == source_sha256:
                return row
        raise KeyError(source_sha256)

    def poses_for(self, capture_sha256: str, lane_id: str) -> tuple:
        return tuple(
            row for row in self.poses
            if row.capture_id == capture_sha256 and row.lane_id == lane_id)

    def regions_for(self, capture_sha256: str, lane_id: str) -> tuple:
        return tuple(
            row for row in self.regions
            if row.capture_id == capture_sha256 and row.lane_id == lane_id)


def require_plan_prefix(state) -> tuple[str, ...]:
    """The archived plan must be an exact PREFIX of the production plan.

    The tripwire of the plan-prefix deviation: entries past the prefix are
    supplemental lanes the archived decode never ran (here the
    PLANE-FIELDS ``u02-field`` arm).  ANY change inside the archived
    prefix means the standard ladder moved and the state cannot be
    replayed against this tree — that stops the run.
    """
    from holo.format.resolve import resolve_format_ref
    from holo.receive.cascade import scale_plan

    if state.format_row_id not in FORMAT_REF:
        raise SystemExit(
            f"state format {state.format_row_id} is not {FORMAT_REF}")
    spec = resolve_format_ref(FORMAT_REF)
    appended: list[str] = []
    for capture in state.captures:
        expected = scale_plan(
            capture.dpi, spec.cell_dots,
            codec_family=spec.codec_family, n_streams=spec.n_streams)
        archived = tuple(capture.plan)
        if expected[:len(archived)] != archived:
            raise SystemExit(
                "the archived scale plan is NOT a prefix of the production "
                "plan — the standard ladder moved; REFUSING to replay")
        appended.extend(lane.lane_id for lane in expected[len(archived):])
    return tuple(sorted(set(appended)))


def _cache_paths(state_path: Path) -> tuple[Path, Path]:
    tag = hashlib.sha256(str(state_path).encode()).hexdigest()[:16]
    return (CACHE_DIR / f"qual-v{CACHE_VERSION}-{tag}.pickle",
            CACHE_DIR / f"qual-v{CACHE_VERSION}-{tag}.json")


def build_facts(state_path: Path = QUAL_STATE, *,
                verbose: bool = True) -> QualFacts:
    """Parse the qualification state read-only and materialise the cache."""
    refuse_forbidden(state_path)
    from holo.receive.observer import ProvisionalReceiverWarning
    from holo.receive.session import (
        STATE_MAGIC,
        STATE_MIGRATIONS,
        STATE_SCHEMA_VERSION,
        SessionState,
    )
    from holo.receive.state_codec import load_typed

    started = time.time()
    sha = sha256_file(state_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        # PLAN-PREFIX DEVIATION (reported, never silent).  The W6 state was
        # decoded before the PLANE-FIELDS ``u02-field`` supplemental lane
        # joined ``cascade.scale_plan``, so today's tree's plan is one
        # entry LONGER and ``validate_state_for_spec`` refuses the whole
        # state.  This is the documented replay-fidelity case
        # (``_color_uplift_harness.replay.replay_plan``): the archived plan
        # must be an exact PREFIX of the production plan, which
        # :func:`require_plan_prefix` checks below.  Every record still
        # validates itself on construction; what is skipped is the
        # session-level spec binding, and the pilot re-asserts the parts
        # it depends on (format identity, plan prefix, close status).
        state = load_typed(
            state_path, SessionState, magic=STATE_MAGIC,
            schema=STATE_SCHEMA_VERSION, validate=None,
            migrations=STATE_MIGRATIONS)
        appended = require_plan_prefix(state)
    load_seconds = time.time() - started

    captures: list[CaptureRow] = []
    for ordinal, record in enumerate(state.captures):
        quarantined: dict[str, list[int]] = {}
        lane_ids: list[str] = []
        counts: list[int] = []
        minted: list[tuple[str, ...]] = []
        for index, level in enumerate(record.levels):
            lane = record.plan[index]
            lane_ids.append(lane.lane_id)
            payload = level.payload
            ids = () if payload is None else tuple(payload.certificate_ids)
            counts.append(len(ids))
            minted.append(ids)
            address = level.address
            if address is not None and address.quarantined_patch_ids:
                quarantined.setdefault(lane.evidence_lane_id, []).extend(
                    int(value) for value in address.quarantined_patch_ids)
        captures.append(CaptureRow(
            ordinal=ordinal,
            source_sha256=record.source_sha256,
            dpi=float(record.dpi),
            dtype=str(record.dtype),
            shape_yx=tuple(int(value) for value in record.shape_yx),
            channels=int(record.channels),
            plan=tuple(record.plan),
            level_lane_ids=tuple(lane_ids),
            level_certificate_counts=tuple(counts),
            level_certificate_ids=tuple(minted),
            quarantined_by_lane={key: tuple(sorted(set(value)))
                                 for key, value in quarantined.items()},
        ))

    facts = QualFacts(
        cache_version=CACHE_VERSION,
        state_path=str(state_path),
        state_sha256=sha,
        state_bytes=state_path.stat().st_size,
        format_row_id=state.format_row_id,
        receiver_policy_id=state.receiver_policy_id,
        close_status=str(state.close.status.value),
        payload_sha256=state.close.payload_sha256,
        plan_lanes_appended=appended,
        captures=tuple(captures),
        regions=tuple(state.regions),
        poses=tuple(state.poses),
        certificates=tuple(state.certificates),
        load_seconds=load_seconds,
    )
    del state
    pickle_path, manifest_path = _cache_paths(state_path)
    pickle_path.parent.mkdir(parents=True, exist_ok=True)
    with open(pickle_path, "wb") as handle:
        pickle.dump(facts, handle, protocol=pickle.HIGHEST_PROTOCOL)
    manifest_path.write_text(json.dumps({
        "schema": SCHEMA,
        "cache_version": CACHE_VERSION,
        "state_path": str(state_path),
        "state_sha256": sha,
        "state_bytes": facts.state_bytes,
        "format_row_id": facts.format_row_id,
        "receiver_policy_id": facts.receiver_policy_id,
        "close_status": facts.close_status,
        "payload_sha256": facts.payload_sha256,
        "plan_lanes_appended_by_this_tree": list(facts.plan_lanes_appended),
        "captures": [
            {"ordinal": row.ordinal, "sha256": row.source_sha256,
             "dpi": row.dpi, "dtype": row.dtype,
             "shape_yx": list(row.shape_yx), "channels": row.channels,
             "plan": [lane.lane_id for lane in row.plan],
             "levels": list(row.level_lane_ids),
             "certificates_by_level": list(row.level_certificate_counts)}
            for row in facts.captures],
        "regions": len(facts.regions),
        "poses": len(facts.poses),
        "certificates": len(facts.certificates),
        "load_seconds": round(load_seconds, 1),
        "tree": tree_state(),
    }, indent=1, sort_keys=True) + "\n")
    if verbose:
        print(f"cached {len(facts.certificates)} certificates, "
              f"{len(facts.poses)} poses, {len(facts.regions)} regions "
              f"from {len(facts.captures)} captures in {load_seconds:.0f}s "
              f"-> {pickle_path} ({pickle_path.stat().st_size / 1e6:.0f} MB)")
    return facts


def read_facts(state_path: Path = QUAL_STATE, *, rebuild: bool = False,
               verbose: bool = True) -> QualFacts:
    """Load the cache, rebuilding when the state SHA or version moved."""
    refuse_forbidden(state_path)
    pickle_path, manifest_path = _cache_paths(state_path)
    if not rebuild and manifest_path.is_file() and pickle_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        stat = Path(state_path).stat()
        if (manifest.get("cache_version") == CACHE_VERSION
                and manifest.get("state_bytes") == stat.st_size):
            try:
                with open(pickle_path, "rb") as handle:
                    facts = pickle.load(handle)
            except Exception:                              # noqa: BLE001
                # A cache written before the 2026-08-21 move names the
                # old module path (``_plane_fields_harness…``) inside
                # the pickle and no longer resolves: MISS, not a crash.
                facts = None
            if isinstance(facts, QualFacts):
                return facts
    return build_facts(state_path, verbose=verbose)


def verified_scan_paths() -> dict[str, Path]:
    """{capture sha256: scan path}, checked against ``scan-shas.txt``.

    The recorded shas are the physical-evidence binding between the three
    archived TIFFs and the state's capture ids; a scan whose sha is not in
    the record, or whose file has moved, stops the run.
    """
    recorded = recorded_scan_shas()
    rows: dict[str, Path] = {}
    for path in SHEET_I_SCANS.values():
        sha = recorded.get(str(path))
        if sha is None:
            raise SystemExit(f"{path} is not in the recorded scan shas")
        rows[sha] = path
    return rows


def regmap_gt_columns() -> list[dict]:
    """The supervised e033 §033.4 per-column measurement (read-only)."""
    return json.loads((REGMAP_GT / "per-column.json").read_text())


__all__ = [
    "CACHE_VERSION", "CAPTURE_DPI", "CACHE_DIR", "DEAD_BANDS", "FORMAT_REF",
    "MAIN_SCRATCH", "OUT_DIR", "PLANES", "QUAL_STATE", "REPO", "CaptureRow",
    "QualFacts", "build_facts", "read_facts", "refuse_forbidden",
    "regmap_gt_columns", "require_plan_prefix", "sha256_file", "tree_moved",
    "tree_state", "verified_scan_paths",
]


if __name__ == "__main__":
    # Re-enter through the package so the pickled dataclasses carry their
    # real module path (``python -m`` would name them ``__main__`` and no
    # later process could unpickle them) — the state_cache precedent.
    from plane_fields import _swim_inputs as _module

    _module.build_facts()
