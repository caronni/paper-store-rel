"""Sha-validated, read-only access to the W0 inputs.

The archived colour state is 3.7 GB and ``load_session`` costs ~200 s, so
this module reads it ONCE and caches exactly the committed facts the
probe pass consumes (the ``_color_uplift_harness.state_cache`` precedent):

* the capture facts + scale plan of the capture whose ``source_sha256``
  matches the chosen scan file;
* every ``PoseRecord`` of that capture (the committed geometry);
* every ``TileCertificateRecord`` (the tier-i evidence).

Durable evidence blocks are never cached — they are the bulk of the file
and the field builder does not read LLRs.

The cache lives under ``scratch/plane-fields/cache/`` and is keyed by the
state's size+mtime plus ``CACHE_VERSION``; the state SHA-256 is recorded
INSIDE it, so an edited or re-decoded state can never be reused silently.
Nothing is ever written next to the archived state.
"""
from __future__ import annotations

import hashlib
import pickle
import subprocess
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

CACHE_VERSION = 1

REPO = Path(__file__).resolve().parents[2]
SRC_HOLO = REPO / "src" / "holo"
MAIN_SCRATCH = Path("scratch")
OUT_DIR = MAIN_SCRATCH / "plane-fields"

# Sheet I (e033), the 2026-08-18 AltaLink c2-cmy8-r0700 pooled volume.
SHEET_I_STATE = (MAIN_SCRATCH / "xerox-v1-20260818"
                 / "I-c2-cmy8r0700-q090-4mm" / "receive.state")
SHEET_I_SCANS = {
    1: MAIN_SCRATCH / ("xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm"
                       "-2400dpi.tiff"),
    2: MAIN_SCRATCH / ("xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm"
                       "-2400dpi-displaced.tiff"),
    3: MAIN_SCRATCH / ("xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm"
                       "-2400dpi-displaced2.tiff"),
}
SCAN_SHAS = MAIN_SCRATCH / "xerox-v1-20260818" / "scan-shas.txt"
REGMAP_GT = MAIN_SCRATCH / "xerox-v1-20260818" / "regmap-gt"


def sha256_file(path: Path, chunk: int = 1 << 24) -> str:
    """Stream one file's SHA-256 (multi-GB inputs are never slurped)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(("git", *args), cwd=REPO, check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:                                      # noqa: BLE001
        return "unknown"


def receiver_tree_sha256() -> str:
    """SHA-256 over every source file under ``src/holo`` — content only."""
    digest = hashlib.sha256()
    for path in sorted(SRC_HOLO.rglob("*.py")):
        digest.update(str(path.relative_to(SRC_HOLO)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def tree_state() -> dict:
    """Identify the exact code this process imports (patch_runner mould).

    HEAD is not the code: the load-bearing field is the CONTENT hash of
    ``src/holo``; the git fields ride along as context.  Recorded at
    entry and at exit — a moved tree voids the run.
    """
    status = _git("status", "--porcelain")
    return {
        "receiver_tree_sha256": receiver_tree_sha256(),
        "head": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode()).hexdigest(),
    }


def tree_moved(before: dict, after: dict) -> bool:
    """Did the CODE move?  Git bookkeeping alone never counts."""
    return before.get("receiver_tree_sha256") != after.get(
        "receiver_tree_sha256")


def recorded_scan_shas() -> dict[str, str]:
    """``scan-shas.txt`` as {absolute path: sha256}."""
    rows: dict[str, str] = {}
    for line in SCAN_SHAS.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and len(parts[0]) == 64:
            rows[parts[1]] = parts[0]
    return rows


@dataclass(frozen=True, slots=True)
class LaneFacts:
    """One scale-plan lane, flattened out of ``LaneSpec``."""

    lane_id: str
    ordinal: int
    target_ppc: float
    native_per_view: float
    kind: str          # ordinary | mopup | refine | uplift


@dataclass(frozen=True, slots=True)
class StateFacts:
    """Everything the W0 probe pass reads out of one archived state."""

    cache_version: int
    state_path: str
    state_sha256: str
    state_bytes: int
    format_row_id: str
    receiver_policy_id: str
    close_status: str
    capture_sha256: str
    capture_dpi: float
    capture_shape_yx: tuple[int, int]
    capture_channels: int
    capture_index: int
    n_captures: int
    lanes: tuple[LaneFacts, ...]
    poses: tuple                      # PoseRecord rows of this capture
    certificates: tuple               # TileCertificateRecord rows (all)
    n_state_poses: int
    load_seconds: float


def _lane_kind(lane) -> str:
    if lane.mopup_of is not None:
        return "mopup"
    if lane.refine_of is not None:
        return "refine"
    if getattr(lane, "uplift_of", None) is not None:
        return "uplift"
    return "ordinary"


def _cache_path(state_path: Path) -> Path:
    stat = state_path.stat()
    key = f"{state_path.name}-{stat.st_size}-{int(stat.st_mtime)}"
    tag = hashlib.sha256(key.encode()).hexdigest()[:16]
    return OUT_DIR / "cache" / f"state-v{CACHE_VERSION}-{tag}.pkl"


def read_state_facts(state_path: Path, capture_sha256: str, *,
                     use_cache: bool = True) -> StateFacts:
    """Load (or reuse) the committed facts for one capture.

    ``capture_sha256`` is the SHA-256 of the scan file the caller intends
    to probe; the capture record must exist in the state, which is the
    physical-evidence binding between file and geometry.
    """
    cache = _cache_path(state_path)
    if use_cache and cache.is_file():
        try:
            with open(cache, "rb") as handle:
                facts = pickle.load(handle)
        except Exception:                                  # noqa: BLE001
            # A cache written before the 2026-08-21 move names the old
            # module path (``_plane_fields_harness._inputs``) inside the
            # pickle and no longer resolves: that is a MISS, never a
            # crash — the state is re-read and the cache rewritten.
            facts = None
        if (isinstance(facts, StateFacts)
                and facts.cache_version == CACHE_VERSION
                and facts.capture_sha256 == capture_sha256):
            return facts

    from holo.receive.observer import ProvisionalReceiverWarning
    from holo.receive.session import load_session

    started = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        state = load_session(state_path, defer_fountain_validation=True)
    load_seconds = time.time() - started

    capture = state.capture(capture_sha256)
    if capture is None:
        available = ", ".join(row.source_sha256[:12] for row in state.captures)
        raise SystemExit(
            f"state has no capture {capture_sha256[:12]}… (captures: "
            f"{available})")
    index = [row.source_sha256 for row in state.captures].index(capture_sha256)
    lanes = tuple(
        LaneFacts(
            lane_id=lane.lane_id,
            ordinal=ordinal,
            target_ppc=lane.target_ppc_num / lane.target_ppc_den,
            native_per_view=(lane.native_per_view_num
                             / lane.native_per_view_den),
            kind=_lane_kind(lane),
        )
        for ordinal, lane in enumerate(capture.plan)
    )
    facts = StateFacts(
        cache_version=CACHE_VERSION,
        state_path=str(state_path),
        state_sha256=sha256_file(state_path),
        state_bytes=state_path.stat().st_size,
        format_row_id=state.format_row_id,
        receiver_policy_id=state.receiver_policy_id,
        close_status=str(state.close.status.value),
        capture_sha256=capture.source_sha256,
        capture_dpi=float(capture.dpi),
        capture_shape_yx=tuple(int(v) for v in capture.shape_yx),
        capture_channels=int(capture.channels),
        capture_index=index,
        n_captures=len(state.captures),
        lanes=lanes,
        poses=tuple(row for row in state.poses
                    if row.capture_id == capture_sha256),
        certificates=tuple(state.certificates),
        n_state_poses=len(state.poses),
        load_seconds=load_seconds,
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    with open(cache, "wb") as handle:
        pickle.dump(facts, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return facts


__all__ = [
    "CACHE_VERSION", "LaneFacts", "MAIN_SCRATCH", "OUT_DIR", "REGMAP_GT",
    "REPO", "SHEET_I_SCANS", "SHEET_I_STATE", "StateFacts",
    "read_state_facts", "receiver_tree_sha256", "recorded_scan_shas",
    "sha256_file", "tree_moved", "tree_state",
]
