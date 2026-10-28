"""Persistent integrated E021 -> E022 -> payload/LDPC receiver (E023b).

This module is the state and scheduling core.  It composes the qualified E023
baseline plus the explicitly registered E023b.1 detector and decoder arms in
:mod:`paperholo.payloaddec`.  It adds transactionality, replayable provenance,
and evidence-addressed attempts, but no fountain/volume layer.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import pickle
import struct
import sys
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import tifffile
from PIL import Image

from . import (acquire, bch, compose, dust, encodings, formats, ldpc,
               modulation, payloaddec, pilotcombine, pilots, pilotsearch,
               place, platen, scannorm, sync)
from .formats import FormatDescriptor


STATE_MAGIC = "e023b-session-v2"
STATE_VERSION = 2
ALGORITHM_ID = "e023b.1-algorithm-arms"
EVIDENCE_POLICY = "one-owner-per-scan/independent-capture/v1"
BASELINE_BP_MAX_ITERS = 60
RETRY_BP_MAX_ITERS = 150
BP_ALPHA = 0.8

Image.MAX_IMAGE_PIXELS = None


def _sha256_bytes(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "little"))
        digest.update(part)
    return digest.hexdigest()


def _array_bytes(value: np.ndarray, dtype) -> bytes:
    array = np.ascontiguousarray(np.asarray(value, dtype))
    return array.tobytes(order="C")


def file_identity(path: Path | str) -> tuple[str, int]:
    """Return SHA-256 and size without reading the entire TIFF into memory."""
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def load_image(path: Path | str) -> np.ndarray:
    """Canonical E023b input normalization, covered by the state fingerprint."""
    source = Path(path)
    if source.suffix.lower() in (".tif", ".tiff"):
        array = tifffile.TiffFile(str(source)).pages[0].asarray(out="memmap")
        if array.ndim == 3:
            return array[..., :3].mean(axis=2, dtype=np.float32)
        return array
    return np.asarray(Image.open(source).convert("L"))


def search_config_digest(config: pilotsearch.SearchConfig) -> str:
    payload = json.dumps(asdict(config), sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def implementation_fingerprints() -> tuple[tuple[str, str], ...]:
    """Hashes of receiver code and transitive numerical layers.

    Resuming a state across a scheduler or lower-layer implementation change
    would mix two algorithms in one evidence ledger.  Pin the complete local
    source surface used by E021--E023b, plus relevant runtime versions.
    """
    modules = (
        sys.modules[__name__], platen, scannorm, sync, pilotsearch, acquire,
        place, pilots, bch, payloaddec, ldpc, compose, dust, encodings,
        modulation, formats, pilotcombine,
    )
    rows = []
    for module in modules:
        path = Path(module.__file__).resolve()
        rows.append((module.__name__, hashlib.sha256(path.read_bytes()).hexdigest()))
    # The experiment runner owns capture-identity validation, transaction
    # ordering, and the explicit retry action.  Hash it without importing it
    # (which would create a library/CLI cycle), so an orchestration-only
    # change cannot append a different algorithm to an existing state.
    entrypoint = (Path(__file__).resolve().parents[2]
                  / "experiments/023b-integrated-receiver/run_e023b.py")
    if not entrypoint.is_file():
        raise RuntimeError(
            f"E023b production entry point is unavailable: {entrypoint}")
    rows.append(("production:e023b-entrypoint",
                 hashlib.sha256(entrypoint.read_bytes()).hexdigest()))
    for distribution in ("numpy", "scipy", "tifffile", "Pillow"):
        version = importlib.metadata.version(distribution).encode("utf-8")
        rows.append((f"runtime:{distribution}",
                     hashlib.sha256(version).hexdigest()))
    rows.append(("runtime:python", hashlib.sha256(
        sys.version.encode("utf-8")).hexdigest()))
    return tuple(rows)


def _timing_name(value: object) -> bool:
    name = str(value)
    return name == "timings" or name.endswith("_s")


def _sort_token(value: object) -> tuple[str, str]:
    """Stable ordering for the simple scalar/tuple keys in receiver state."""
    return type(value).__qualname__, repr(value)


def _canonical_update(digest, value: object) -> None:
    """Stream an exact, type-tagged semantic representation into ``digest``."""
    if value is None:
        digest.update(b"N")
    elif isinstance(value, (bool, np.bool_)):
        digest.update(b"B1" if bool(value) else b"B0")
    elif isinstance(value, (int, np.integer)):
        payload = str(int(value)).encode("ascii")
        digest.update(b"I" + len(payload).to_bytes(8, "big") + payload)
    elif isinstance(value, (float, np.floating)):
        digest.update(b"F" + struct.pack(">d", float(value)))
    elif isinstance(value, bytes):
        digest.update(b"Y" + len(value).to_bytes(8, "big") + value)
    elif isinstance(value, (str, Path)):
        payload = str(value).encode("utf-8")
        digest.update(b"S" + len(payload).to_bytes(8, "big") + payload)
    elif isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        _canonical_update(digest, (array.dtype.str, tuple(array.shape)))
        digest.update(b"A" + array.nbytes.to_bytes(8, "big"))
        digest.update(memoryview(array).cast("B"))
    elif isinstance(value, np.generic):
        _canonical_update(digest, value.item())
    elif is_dataclass(value):
        digest.update(b"D")
        _canonical_update(digest, type(value).__qualname__)
        selected = [row for row in fields(value)
                    if not _timing_name(row.name)]
        _canonical_update(digest, len(selected))
        for row in selected:
            _canonical_update(digest, row.name)
            _canonical_update(digest, getattr(value, row.name))
    elif isinstance(value, dict):
        selected = [(key, row) for key, row in value.items()
                    if not _timing_name(key)]
        selected.sort(key=lambda item: _sort_token(item[0]))
        digest.update(b"M")
        _canonical_update(digest, len(selected))
        for key, row in selected:
            _canonical_update(digest, key)
            _canonical_update(digest, row)
    elif isinstance(value, (list, tuple)):
        digest.update(b"L" if isinstance(value, list) else b"T")
        _canonical_update(digest, len(value))
        for row in value:
            _canonical_update(digest, row)
    elif isinstance(value, (set, frozenset)):
        digest.update(b"E")
        ordered = sorted(value, key=_sort_token)
        _canonical_update(digest, len(ordered))
        for row in ordered:
            _canonical_update(digest, row)
    else:
        raise TypeError(
            f"unsupported authoritative state type: {type(value).__name__}")


@dataclass(frozen=True)
class PackedRegion:
    """Lossless compact E021 region support for replay and E024."""

    bbox: tuple[int, int, int, int]
    mask_shape: tuple[int, int]
    mask_bits: np.ndarray
    area_mm2: float
    angle_hint_deg: float | None
    score: float

    def unpack(self) -> platen.PayloadRegion:
        n = int(self.mask_shape[0] * self.mask_shape[1])
        mask = np.unpackbits(np.asarray(self.mask_bits, np.uint8),
                             bitorder="little")[:n]
        return platen.PayloadRegion(
            bbox=tuple(int(v) for v in self.bbox),
            mask=mask.reshape(self.mask_shape).astype(bool, copy=False),
            area_mm2=float(self.area_mm2),
            angle_hint_deg=(None if self.angle_hint_deg is None
                            else float(self.angle_hint_deg)),
            score=float(self.score),
        )


@dataclass(frozen=True)
class PackedSurvey:
    regions: tuple[PackedRegion, ...]
    c_dots: int | None
    cell_pitch_px: float | None
    pitch_votes: tuple[tuple[int, float], ...]
    diagnostics: dict

    @classmethod
    def pack(cls, survey: platen.PayloadSurvey) -> "PackedSurvey":
        rows = []
        for region in survey.regions:
            mask = np.asarray(region.mask, bool)
            rows.append(PackedRegion(
                bbox=tuple(int(v) for v in region.bbox),
                mask_shape=tuple(int(v) for v in mask.shape),
                mask_bits=np.packbits(mask.ravel(), bitorder="little"),
                area_mm2=float(region.area_mm2),
                angle_hint_deg=(None if region.angle_hint_deg is None
                                else float(region.angle_hint_deg)),
                score=float(region.score),
            ))
        return cls(
            regions=tuple(rows),
            c_dots=(None if survey.c_dots is None else int(survey.c_dots)),
            cell_pitch_px=(None if survey.cell_pitch_px is None
                           else float(survey.cell_pitch_px)),
            pitch_votes=tuple((int(c), float(v))
                              for c, v in survey.pitch_votes),
            diagnostics=copy.deepcopy(survey.diagnostics),
        )

    def unpack(self) -> platen.PayloadSurvey:
        return platen.PayloadSurvey(
            regions=tuple(region.unpack() for region in self.regions),
            c_dots=self.c_dots,
            cell_pitch_px=self.cell_pitch_px,
            pitch_votes=self.pitch_votes,
            diagnostics=copy.deepcopy(self.diagnostics),
        )


@dataclass(frozen=True)
class SessionEnvelope:
    algorithm_id: str
    format_id: str
    seed: bytes
    cell_dots: int
    page_cells_yx: tuple[int, int]
    pages: tuple[int, ...]
    dpi: float
    rate_id: str
    detector_profile: str
    search_config: pilotsearch.SearchConfig
    search_config_sha256: str
    implementation_sha256: tuple[tuple[str, str], ...]
    evidence_policy: str = EVIDENCE_POLICY


@dataclass(frozen=True)
class TileAttempt:
    attempt_id: str
    evidence_digest: str
    page: int
    tile_yx: tuple[int, int]
    stage: str
    source: str
    scan_ids: tuple[str, ...]
    capture_ids: tuple[str, ...]
    decoder_profile: str
    state: str
    decoder_invoked: bool
    k_eff: int
    n_nonshort: int
    n_informative: int
    coverage: float
    n_iters: int
    syndrome_ok: bool | None
    crc_ok: bool | None
    n_erased: int
    certified_new: bool


@dataclass(frozen=True)
class TileWork:
    """Geometric upper bound before calibration/one-owner reduction."""

    page: int
    tile_yx: tuple[int, int]
    n_geometric: int
    n_nonshort: int
    geometric_coverage: float
    degenerate: bool
    placement_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScanRecord:
    scan_id: str
    source_path: str
    source_sha256: str
    source_size: int
    dpi: float
    image_shape: tuple[int, int]
    image_dtype: str
    capture_id: str
    survey: PackedSurvey
    result: pilotsearch.SearchResult
    placement_ids: tuple[str, ...]
    work_plan: dict[tuple[int, int, int], TileWork]
    detector_profile: str
    window_evidence: tuple[payloaddec.WindowEmission, ...]
    context_fits: tuple[payloaddec.ContextFit, ...]
    emission: payloaddec.ScanEmission
    tile_evidence_digests: dict[tuple[int, int, int], str]
    decode_skip_tiles: tuple[tuple[int, int, int], ...] = ()
    timings: dict = field(default_factory=dict)

    @property
    def region_count(self) -> int:
        return len(self.survey.regions)


def _copy_decode_state(state: payloaddec.DecodeState
                       ) -> payloaddec.DecodeState:
    """Copy only mutable aggregate state; scan emissions remain immutable."""
    clone = copy.copy(state)
    clone.scans = list(state.scans)
    clone.tiles = {}
    for key, out in state.tiles.items():
        row = copy.copy(out)
        row.user_bits = (None if out.user_bits is None
                         else np.asarray(out.user_bits, np.uint8).copy())
        row.divergence = dict(out.divergence)
        clone.tiles[key] = row
    clone.fatal = list(state.fatal)
    clone._masks = dict(state._masks)
    return clone


@dataclass
class ReceiverSession:
    envelope: SessionEnvelope
    scans: list[ScanRecord]
    decode: payloaddec.DecodeState
    attempts: list[TileAttempt] = field(default_factory=list)
    attempt_ids: set[str] = field(default_factory=set)

    @classmethod
    def create(
        cls,
        descriptor: FormatDescriptor,
        pages: tuple[int, ...],
        dpi: float,
        *,
        rate_id: str | None = None,
        detector_profile: str = payloaddec.DETECTOR_PAVA_V1,
        search_config: pilotsearch.SearchConfig = pilotsearch.SearchConfig(),
    ) -> "ReceiverSession":
        rate = rate_id or descriptor.ldpc_rate
        if rate is None:
            raise ValueError(f"{descriptor.format_id} carries no ldpc_rate")
        if rate not in ldpc.LDPC_LADDER:
            raise ValueError(f"unknown LDPC rate {rate!r}")
        if detector_profile not in payloaddec.DETECTOR_PROFILES:
            raise ValueError(
                f"unknown detector profile {detector_profile!r}")
        pages = tuple(int(page) for page in pages)
        if not pages or len(set(pages)) != len(pages):
            raise ValueError("pages must be a non-empty unique sequence")
        spec = descriptor.spec()
        envelope = SessionEnvelope(
            algorithm_id=ALGORITHM_ID,
            format_id=descriptor.format_id,
            seed=descriptor.seed,
            cell_dots=int(descriptor.cell_dots),
            page_cells_yx=tuple(int(v) for v in spec.page_cells_yx),
            pages=pages,
            dpi=float(dpi),
            rate_id=str(rate),
            detector_profile=str(detector_profile),
            search_config=search_config,
            search_config_sha256=search_config_digest(search_config),
            implementation_sha256=implementation_fingerprints(),
        )
        decode = payloaddec.DecodeState(descriptor, rate, pages, ())
        return cls(envelope=envelope, scans=[], decode=decode)

    def fork(self) -> "ReceiverSession":
        return ReceiverSession(
            envelope=self.envelope,
            scans=list(self.scans),
            decode=_copy_decode_state(self.decode),
            attempts=list(self.attempts),
            attempt_ids=set(self.attempt_ids),
        )

    @property
    def source_hashes(self) -> set[str]:
        return {scan.source_sha256 for scan in self.scans}

    @property
    def capture_ids(self) -> set[str]:
        return {scan.capture_id for scan in self.scans}

    def validate(
        self,
        descriptor: FormatDescriptor,
        pages: tuple[int, ...],
        dpi: float,
        *,
        rate_id: str | None = None,
        detector_profile: str = payloaddec.DETECTOR_PAVA_V1,
        search_config: pilotsearch.SearchConfig | None = None,
        require_current_implementation: bool = True,
    ) -> None:
        rate = rate_id or descriptor.ldpc_rate
        config = search_config or self.envelope.search_config
        spec = descriptor.spec()
        expected = (
            ALGORITHM_ID, descriptor.format_id, descriptor.seed,
            int(descriptor.cell_dots), tuple(spec.page_cells_yx),
            tuple(int(page) for page in pages), float(dpi), str(rate),
            str(detector_profile),
            search_config_digest(config), EVIDENCE_POLICY,
        )
        actual = (
            self.envelope.algorithm_id, self.envelope.format_id,
            self.envelope.seed, self.envelope.cell_dots,
            self.envelope.page_cells_yx, self.envelope.pages,
            self.envelope.dpi, self.envelope.rate_id,
            self.envelope.detector_profile,
            self.envelope.search_config_sha256,
            self.envelope.evidence_policy,
        )
        if actual != expected:
            raise ValueError(
                "e023b state format/pages/dpi/rate/config mismatch; "
                "pass --fresh or choose another --state")
        if (require_current_implementation
                and self.envelope.implementation_sha256
                != implementation_fingerprints()):
            raise ValueError(
                "e023b numerical implementation changed since this state "
                "was created; requalify and start a new state")

    def summary(self) -> dict:
        out = dict(self.decode.summary())
        out.update({
            "state_version": STATE_VERSION,
            "scan_count": len(self.scans),
            "detector_profile": self.envelope.detector_profile,
            "context_fits": sum(
                len(scan.context_fits) for scan in self.scans),
            "context_fits_eligible": sum(
                fit.eligible for scan in self.scans
                for fit in scan.context_fits),
            "context_fits_adopted": sum(
                fit.adopted for scan in self.scans
                for fit in scan.context_fits),
            "attempt_records": len(self.attempts),
            "below_floor_evaluations": sum(
                row.state == "below_attempt_floor" for row in self.attempts),
        })
        return out

    def validate_invariants(self) -> None:
        """Fail closed on ambiguous or internally inconsistent state."""
        _validate_session_invariants(self)


def authoritative_digest(session: ReceiverSession) -> str:
    """Hash every authoritative datum while excluding wall-clock timings.

    In particular this covers the packed E021 masks, complete E022 result,
    non-owner window evidence, frozen emissions, tile state, and attempt
    provenance.  It intentionally excludes process-local decoder caches and
    timing fields so command batching and diagnostics cannot perturb it.
    """
    digest = hashlib.sha256()
    _canonical_update(digest, {
        "envelope": session.envelope,
        "scans": session.scans,
        "tiles": session.decode.tiles,
        "decode_upstream": session.decode.upstream,
        "n_attempts": session.decode.n_attempts,
        "fatal": session.decode.fatal,
        "attempts": session.attempts,
    })
    return digest.hexdigest()


def _canonical_digest(value: object) -> str:
    """Timing-free exact digest for replayed authoritative substructures."""
    digest = hashlib.sha256()
    _canonical_update(digest, value)
    return digest.hexdigest()


def save_session(path: Path | str, session: ReceiverSession) -> None:
    """Atomically replace the authoritative state after one complete TIFF."""
    session.validate_invariants()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    payload = {"magic": STATE_MAGIC, "version": STATE_VERSION,
               "session": session}
    tmp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, target)


def load_session(path: Path | str) -> ReceiverSession:
    payload = pickle.loads(Path(path).read_bytes())
    if not isinstance(payload, dict) or payload.get("magic") != STATE_MAGIC:
        raise ValueError(f"{path} is not an e023b session")
    if int(payload.get("version", -1)) != STATE_VERSION:
        raise ValueError(
            f"e023b state version {payload.get('version')} != {STATE_VERSION}")
    session = payload.get("session")
    if not isinstance(session, ReceiverSession):
        raise ValueError(f"{path} has an invalid e023b payload")
    if session.envelope.implementation_sha256 != implementation_fingerprints():
        raise ValueError(
            f"{path} was created by a different receiver implementation")
    if session.attempt_ids != {row.attempt_id for row in session.attempts}:
        raise ValueError(f"{path} has a corrupt attempt index")
    session.validate_invariants()
    return session


def _placement_ids(source_sha256: str,
                   result: pilotsearch.SearchResult) -> tuple[str, ...]:
    rows = []
    for ordinal, placed in enumerate(result.placements):
        payload = json.dumps({
            "scan": source_sha256,
            "ordinal": ordinal,
            "region": int(placed.region_index),
            "page": int(placed.page),
            "origin": [int(v) for v in placed.origin_yx],
            "rot": int(placed.rot_k),
            "window": [int(placed.window.y), int(placed.window.x),
                       int(placed.window.h), int(placed.window.w)],
            "pose_origin": [float(v) for v in placed.pose.origin_yx],
            "pose_jacobian": [[float(v) for v in row]
                              for row in placed.pose.jacobian_yx],
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        rows.append("p0-" + hashlib.sha256(payload).hexdigest()[:24])
    return tuple(rows)


placement_ids_for_result = _placement_ids


def _emission_equal(a: payloaddec.ScanEmission,
                    b: payloaddec.ScanEmission) -> bool:
    if (a.scan_id != b.scan_id or a.source_sha256 != b.source_sha256
            or a.window_rows != b.window_rows
            or set(a.pages) != set(b.pages)):
        return False
    return all(
        set(a.pages[page]) == set(b.pages[page])
        and all(np.array_equal(a.pages[page][name], b.pages[page][name])
                for name in a.pages[page])
        for page in a.pages)


class _DescriptorView:
    """Minimal descriptor protocol for the shared pilot combiner."""

    def __init__(self, session: ReceiverSession):
        self.format_id = session.envelope.format_id
        self.seed = session.envelope.seed
        self._spec = session.decode.spec

    def spec(self):
        return self._spec


def _combined_pilot_result(
    session: ReceiverSession,
    extra: ScanRecord | None = None,
) -> pilotsearch.SearchResult:
    scans = [*session.scans]
    if extra is not None:
        scans.append(extra)
    return pilotcombine.combine_search_results(
        [pilotcombine.SearchResultPart(
            scan.scan_id, scan.region_count, scan.result) for scan in scans],
        _DescriptorView(session), pages=session.envelope.pages,
        decode_words=True)


def _check_combined_bch(session: ReceiverSession,
                        extra: ScanRecord | None = None) -> None:
    combined = _combined_pilot_result(session, extra)
    bad = [key for key, tile in combined.tiles.items()
           if tile.bch_ok is False]
    if bad:
        raise payloaddec.FatalIntegrityError(
            f"combined pilot contradiction at {bad[:8]}")


def build_work_plan(
    result: pilotsearch.SearchResult,
    placement_ids: tuple[str, ...],
    spec: compose.ComposeSpec,
    seed: bytes,
    ldpc_spec: ldpc.LdpcSpec,
) -> dict[tuple[int, int, int], TileWork]:
    """Map every authoritative E022 core to potential payload tiles."""
    pim = compose.payload_index_map(spec, seed)
    covered: dict[tuple[int, int, int], set[int]] = {}
    contributors: dict[tuple[int, int, int], set[str]] = {}
    for ordinal, placed in enumerate(result.placements):
        cells = np.asarray(placed.page_cells_yx, np.int64)
        if cells.size == 0:
            continue
        inside = (
            (cells[:, 0] >= 0) & (cells[:, 0] < spec.page_cells_yx[0])
            & (cells[:, 1] >= 0) & (cells[:, 1] < spec.page_cells_yx[1]))
        cells = cells[inside]
        if cells.size == 0:
            continue
        pidx = pim[cells[:, 0], cells[:, 1]]
        keep = pidx >= 0
        cells, pidx = cells[keep], pidx[keep]
        if pidx.size == 0:
            continue
        tile_y = cells[:, 0] // ldpc.TILE_CELLS
        tile_x = cells[:, 1] // ldpc.TILE_CELLS
        for ty, tx in np.unique(np.stack([tile_y, tile_x], axis=1), axis=0):
            sel = (tile_y == ty) & (tile_x == tx)
            key = (int(placed.page), int(ty), int(tx))
            covered.setdefault(key, set()).update(int(v) for v in pidx[sel])
            contributors.setdefault(key, set()).add(placement_ids[ordinal])
    out = {}
    for key, values in covered.items():
        tile_yx = (key[1], key[2])
        mask = ldpc.tile_shorten_mask(tile_yx, spec, seed)
        n_nonshort = int((~mask).sum())
        out[key] = TileWork(
            page=key[0], tile_yx=tile_yx, n_geometric=len(values),
            n_nonshort=n_nonshort,
            geometric_coverage=(len(values) / n_nonshort
                                if n_nonshort else 0.0),
            degenerate=ldpc.tile_user_capacity(mask, ldpc_spec) == 0,
            placement_ids=tuple(sorted(contributors[key])),
        )
    return out


_TILE_CODE_CACHE: dict[tuple, np.ndarray] = {}


def _payload_tile_codes(spec: compose.ComposeSpec, seed: bytes) -> np.ndarray:
    key = (seed, spec.encoding_id, tuple(spec.page_cells_yx),
           spec.pilot.version)
    if key not in _TILE_CODE_CACHE:
        inv = payloaddec._payload_inverse(spec, seed)
        tiles_x = int(np.ceil(spec.page_cells_yx[1] / ldpc.TILE_CELLS))
        _TILE_CODE_CACHE[key] = (
            (inv[:, 0] // ldpc.TILE_CELLS) * tiles_x
            + inv[:, 1] // ldpc.TILE_CELLS).astype(np.int32)
    return _TILE_CODE_CACHE[key]


def payload_indices_to_tiles(
    page: int, indices: np.ndarray, spec: compose.ComposeSpec, seed: bytes
) -> set[tuple[int, int, int]]:
    codes = _payload_tile_codes(spec, seed)[np.asarray(indices, np.int64)]
    tiles_x = int(np.ceil(spec.page_cells_yx[1] / ldpc.TILE_CELLS))
    return {(int(page), *divmod(int(code), tiles_x))
            for code in np.unique(codes)}


def tile_evidence_digests(
    emission: payloaddec.ScanEmission,
    spec: compose.ComposeSpec,
    seed: bytes,
) -> dict[tuple[int, int, int], str]:
    """Canonical per-tile identities of one frozen ScanEmission."""
    codes_all = _payload_tile_codes(spec, seed)
    tiles_x = int(np.ceil(spec.page_cells_yx[1] / ldpc.TILE_CELLS))
    out: dict[tuple[int, int, int], str] = {}
    for page, vec in emission.pages.items():
        index = np.asarray(vec["index"], np.int64)
        codes = codes_all[index]
        for code in np.unique(codes):
            sel = codes == code
            ty, tx = divmod(int(code), tiles_x)
            out[(int(page), ty, tx)] = _sha256_bytes(
                b"e023b/scan-tile-evidence/v1",
                str(int(page)).encode(), str(ty).encode(), str(tx).encode(),
                _array_bytes(index[sel], "<i8"),
                _array_bytes(np.asarray(vec["llr"])[sel], "<f4"),
                _array_bytes(np.asarray(vec["owner"])[sel], "<i4"),
            )
    return out


def make_scan_record(
    *,
    scan_id: str,
    source_path: Path | str,
    source_sha256: str,
    source_size: int,
    dpi: float,
    image: np.ndarray,
    capture_id: str,
    survey: platen.PayloadSurvey,
    result: pilotsearch.SearchResult,
    descriptor: FormatDescriptor,
    pages: tuple[int, ...],
    rate_id: str | None = None,
    detector_profile: str = payloaddec.DETECTOR_PAVA_V1,
    on_payload_region=None,
    on_context=None,
    timings: dict | None = None,
) -> ScanRecord:
    """Collect qualified E023 evidence and freeze one complete scan."""
    if detector_profile not in payloaddec.DETECTOR_PROFILES:
        raise ValueError(f"unknown detector profile {detector_profile!r}")
    for key, tile in result.tiles.items():
        if tile.bch_ok is False:
            raise payloaddec.FatalIntegrityError(
                f"scan {scan_id} tile {key}: contradictory BCH result")
    e022_scan = payloaddec.E022Scan(
        scan_id=str(scan_id), source_path=str(Path(source_path).resolve()),
        source_sha256=str(source_sha256), dpi=float(dpi), result=result)
    context_fits: list[payloaddec.ContextFit] = []

    def capture_context(region_index: int,
                        fit: payloaddec.ContextFit) -> None:
        if int(fit.region_index) != int(region_index):
            raise ValueError("context fit region identity changed")
        context_fits.append(fit)
        if on_context is not None:
            on_context(int(region_index), fit)

    evidence = payloaddec.collect_window_evidence(
        e022_scan, image, descriptor.spec(), descriptor.seed, pages,
        on_region=on_payload_region, detector_profile=detector_profile,
        on_context=capture_context)
    emission = payloaddec.freeze_scan_emission(
        e022_scan, evidence, descriptor.spec())
    placement_ids = _placement_ids(source_sha256, result)
    selected_rate = rate_id or descriptor.ldpc_rate
    if selected_rate is None:
        raise ValueError(f"{descriptor.format_id} carries no ldpc_rate")
    return ScanRecord(
        scan_id=str(scan_id),
        source_path=str(Path(source_path).resolve()),
        source_sha256=str(source_sha256),
        source_size=int(source_size), dpi=float(dpi),
        image_shape=tuple(int(v) for v in image.shape[:2]),
        image_dtype=str(np.asarray(image).dtype),
        capture_id=str(capture_id), survey=PackedSurvey.pack(survey),
        result=result, placement_ids=placement_ids,
        work_plan=build_work_plan(
            result, placement_ids, descriptor.spec(), descriptor.seed,
            ldpc.LDPC_LADDER[selected_rate]),
        detector_profile=str(detector_profile),
        window_evidence=tuple(evidence),
        context_fits=tuple(context_fits), emission=emission,
        tile_evidence_digests=tile_evidence_digests(
            emission, descriptor.spec(), descriptor.seed),
        timings={} if timings is None else dict(timings),
    )


def _normalise_decode_skip_tiles(
    session: ReceiverSession,
    values: Iterable[tuple[int, int, int]],
    *,
    stored: bool,
) -> tuple[tuple[int, int, int], ...]:
    """Validate and canonicalise certificate-boundary scheduling keys."""
    if stored and type(values) is not tuple:
        raise ValueError("decode skip marker must be a canonical tuple")
    try:
        supplied = list(values)
    except TypeError as exc:
        raise ValueError("skip_tiles must be an iterable of tile keys") from exc

    legal_pages = set(session.envelope.pages)
    legal_tiles = set(ldpc.tile_grid(session.envelope.page_cells_yx))
    normalised: list[tuple[int, int, int]] = []
    for key in supplied:
        if type(key) is not tuple or len(key) != 3:
            raise ValueError(
                "skip_tiles keys must be exact (page, tile_y, tile_x) tuples")
        if any(not isinstance(value, (int, np.integer))
               or isinstance(value, (bool, np.bool_)) for value in key):
            raise ValueError("skip_tiles key components must be integers")
        canonical = tuple(int(value) for value in key)
        page, ty, tx = canonical
        if page not in legal_pages:
            raise ValueError("skip_tiles key is on an illegal page")
        if (ty, tx) not in legal_tiles:
            raise ValueError("skip_tiles key is outside the LDPC tile grid")
        normalised.append(canonical)

    if len(normalised) != len(set(normalised)):
        raise ValueError("skip_tiles contains duplicate tile keys")
    canonical_values = tuple(sorted(normalised))
    if stored and tuple(supplied) != canonical_values:
        raise ValueError("decode skip marker is not canonical")
    return canonical_values


def _record_with_decode_skips(
    session: ReceiverSession,
    record: ScanRecord,
    skip_tiles: Iterable[tuple[int, int, int]],
) -> ScanRecord:
    """Bind requested global certificates to this scan's candidates."""
    existing = _normalise_decode_skip_tiles(
        session, record.decode_skip_tiles, stored=True)
    requested = _normalise_decode_skip_tiles(
        session, skip_tiles, stored=False)
    candidates = set(record.tile_evidence_digests)
    requested_candidates = tuple(
        key for key in requested if key in candidates)
    if existing:
        if requested_candidates != existing:
            raise ValueError(
                "prepopulated decode skip marker requires explicit matching "
                "skip_tiles")
        return record
    if not requested_candidates:
        return record
    return replace(record, decode_skip_tiles=requested_candidates)


def _validate_scan_record(session: ReceiverSession,
                          record: ScanRecord) -> None:
    """Recompute every derivation that makes a ScanRecord authoritative."""
    if not record.scan_id or not record.capture_id:
        raise ValueError("scan_id and capture_id must be non-empty")
    if record.dpi != session.envelope.dpi:
        raise ValueError(f"scan {record.scan_id}: DPI differs from session")
    if (record.detector_profile not in payloaddec.DETECTOR_PROFILES
            or record.detector_profile != session.envelope.detector_profile):
        raise ValueError(
            f"scan {record.scan_id}: detector profile differs from session")
    if len(record.source_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in record.source_sha256):
        raise ValueError(f"scan {record.scan_id}: invalid source SHA-256")
    if record.source_size < 0 or len(record.image_shape) != 2 or any(
            int(value) <= 0 for value in record.image_shape):
        raise ValueError(f"scan {record.scan_id}: invalid source metadata")
    if (record.emission.scan_id != record.scan_id
            or record.emission.source_sha256 != record.source_sha256):
        raise ValueError(f"scan {record.scan_id}: emission identity mismatch")

    legal_pages = set(session.envelope.pages)
    for placement in record.result.placements:
        if int(placement.page) not in legal_pages:
            raise ValueError(
                f"scan {record.scan_id}: placement on illegal page")
    if any(int(key[0]) not in legal_pages for key in record.result.tiles):
        raise ValueError(f"scan {record.scan_id}: pilot tile on illegal page")
    if any(int(page) not in legal_pages for page in record.emission.pages):
        raise ValueError(f"scan {record.scan_id}: emission on illegal page")

    image_h, image_w = record.image_shape
    for region in record.survey.regions:
        y0, x0, height, width = (int(value) for value in region.bbox)
        if (height < 0 or width < 0 or region.mask_shape != (height, width)
                or y0 < 0 or x0 < 0 or y0 + height > image_h
                or x0 + width > image_w
                or int(np.asarray(region.mask_bits).size) * 8
                < height * width):
            raise ValueError(
                f"scan {record.scan_id}: invalid packed E021 region")

    expected_placements = _placement_ids(
        record.source_sha256, record.result)
    if record.placement_ids != expected_placements:
        raise ValueError(f"scan {record.scan_id}: placement id mismatch")
    expected_work = build_work_plan(
        record.result, record.placement_ids, session.decode.spec,
        session.decode.seed, session.decode.ldpc_spec)
    if record.work_plan != expected_work:
        raise ValueError(f"scan {record.scan_id}: work plan mismatch")

    if len(record.window_evidence) != len(record.result.placements):
        raise ValueError(
            f"scan {record.scan_id}: incomplete window evidence")
    by_ordinal = {int(row.placement_ordinal): row
                  for row in record.window_evidence}
    if set(by_ordinal) != set(range(len(record.result.placements))):
        raise ValueError(
            f"scan {record.scan_id}: invalid window evidence ordinals")
    capacity = compose.payload_capacity(session.decode.spec)
    for ordinal, placement in enumerate(record.result.placements):
        row = by_ordinal[ordinal]
        if (row.page != placement.page
                or row.region_index != placement.region_index
                or row.page_cells_yx.ndim != 2
                or row.page_cells_yx.shape[1:] != (2,)
                or row.raw_means.size != row.page_cells_yx.shape[0]
                or row.scores.size not in (0, row.page_cells_yx.shape[0])
                or row.payload_index.size != row.payload_llr.size
                or np.any(row.payload_index < 0)
                or np.any(row.payload_index >= capacity)):
            raise ValueError(
                f"scan {record.scan_id}: inconsistent window evidence")
    scan = payloaddec.E022Scan(
        record.scan_id, record.source_path, record.source_sha256,
        record.dpi, record.result)
    replayed = payloaddec.reprofile_window_evidence(
        record.result.placements, record.window_evidence,
        session.decode.spec, session.decode.seed, record.detector_profile)
    if (_canonical_digest(replayed.emissions)
            != _canonical_digest(record.window_evidence)):
        raise ValueError(
            f"scan {record.scan_id}: stored detector evidence does not "
            "replay from its retained raw means")
    if (_canonical_digest(replayed.context_fits)
            != _canonical_digest(record.context_fits)):
        raise ValueError(
            f"scan {record.scan_id}: context fit sidecar does not replay")
    frozen = payloaddec.freeze_scan_emission(
        scan, list(replayed.emissions), session.decode.spec)
    if not _emission_equal(frozen, record.emission):
        raise ValueError(
            f"scan {record.scan_id}: stored window evidence does not "
            "reproduce the frozen emission")
    expected_digests = tile_evidence_digests(
        record.emission, session.decode.spec, session.decode.seed)
    if record.tile_evidence_digests != expected_digests:
        raise ValueError(
            f"scan {record.scan_id}: tile evidence digest mismatch")
    decode_skip_tiles = _normalise_decode_skip_tiles(
        session, record.decode_skip_tiles, stored=True)
    if any(key not in record.tile_evidence_digests
           for key in decode_skip_tiles):
        raise ValueError(
            f"scan {record.scan_id}: decode skip marker is not a candidate")
    for vector in record.emission.pages.values():
        if (set(vector) != {"index", "llr", "owner"}
                or not (vector["index"].size == vector["llr"].size
                        == vector["owner"].size)
                or (vector["index"].size > 1 and np.any(
                    vector["index"][1:] <= vector["index"][:-1]))
                or any(int(owner) not in by_ordinal
                       for owner in np.unique(vector["owner"]))):
            raise ValueError(
                f"scan {record.scan_id}: malformed frozen emission")


def _baseline_attempt_provenance(
    session: ReceiverSession,
    key: tuple[int, int, int],
    stage: str,
    source: str,
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """Expected capture frontier and digest for one baseline ledger row."""
    if stage == "scan":
        matches = [scan for scan in session.scans
                   if scan.scan_id == source]
        if len(matches) != 1 or key not in matches[0].tile_evidence_digests:
            raise ValueError("e023b scan attempt source is inconsistent")
        scan = matches[0]
        return ((scan.scan_id,), (scan.capture_id,),
                scan.tile_evidence_digests[key])

    if stage != "union":
        raise ValueError("e023b baseline attempt has an invalid stage")
    frontier = [index for index, scan in enumerate(session.scans)
                if source == f"union@{scan.scan_id}"]
    if len(frontier) != 1:
        raise ValueError("e023b union attempt source is inconsistent")
    frontier_index = frontier[0]
    if key not in session.scans[frontier_index].tile_evidence_digests:
        raise ValueError("e023b union frontier did not change this tile")
    components = [
        scan for scan in session.scans[:frontier_index + 1]
        if key in scan.tile_evidence_digests
    ]
    if len(components) < 2:
        raise ValueError("e023b union attempt has fewer than two components")
    evidence_digest = _sha256_bytes(
        b"e023b/union-tile-evidence/v1",
        *(f"{scan.scan_id}:{scan.tile_evidence_digests[key]}".encode(
            "ascii") for scan in components))
    return (tuple(scan.scan_id for scan in components),
            tuple(scan.capture_id for scan in components), evidence_digest)


def _validate_session_invariants(session: ReceiverSession) -> None:
    envelope = session.envelope
    decode = session.decode
    if envelope.detector_profile not in payloaddec.DETECTOR_PROFILES:
        raise ValueError("e023b envelope has an unknown detector profile")
    if (decode.format_id != envelope.format_id
            or decode.seed != envelope.seed
            or decode.rate_id != envelope.rate_id
            or decode.pages != envelope.pages
            or tuple(decode.spec.page_cells_yx) != envelope.page_cells_yx):
        raise ValueError("e023b envelope/decode mismatch")
    scan_ids = [scan.scan_id for scan in session.scans]
    source_hashes = [scan.source_sha256 for scan in session.scans]
    capture_ids = [scan.capture_id for scan in session.scans]
    if (len(scan_ids) != len(set(scan_ids))
            or len(source_hashes) != len(set(source_hashes))
            or len(capture_ids) != len(set(capture_ids))):
        raise ValueError("e023b scan/source/capture identities are ambiguous")
    if len(decode.scans) != len(session.scans) or any(
            not _emission_equal(got, scan.emission)
            for got, scan in zip(decode.scans, session.scans, strict=True)):
        raise ValueError("e023b decode scan list differs from source records")
    expected_upstream = tuple(
        (scan.scan_id, scan.source_sha256) for scan in session.scans)
    if decode.upstream != expected_upstream:
        raise ValueError("e023b upstream fingerprint mismatch")
    for scan in session.scans:
        _validate_scan_record(session, scan)
    if session.scans:
        _check_combined_bch(session)

    expected_ids = {row.attempt_id for row in session.attempts}
    if (len(expected_ids) != len(session.attempts)
            or session.attempt_ids != expected_ids):
        raise ValueError("e023b attempt index is inconsistent")
    if decode.n_attempts != sum(
            int(row.decoder_invoked) for row in session.attempts):
        raise ValueError("e023b CRC-attempt count is inconsistent")
    scan_map = {scan.scan_id: scan for scan in session.scans}
    scan_index = {scan.scan_id: index
                  for index, scan in enumerate(session.scans)}
    invoked_by_tile: dict[tuple[int, int, int], int] = {}
    certified_by_tile: dict[tuple[int, int, int], int] = {}
    baseline_profile = decoder_profile(
        envelope.rate_id, BASELINE_BP_MAX_ITERS, BP_ALPHA)
    retry_profile = decoder_profile(
        envelope.rate_id, RETRY_BP_MAX_ITERS, BP_ALPHA)
    latest_baseline: dict[tuple[int, int, int], TileAttempt] = {}
    latest_baseline_rank: dict[tuple[int, int, int], tuple[int, int]] = {}
    for row in session.attempts:
        key = (row.page, *row.tile_yx)
        if (row.page not in envelope.pages
                or row.attempt_id != _attempt_identity(
                    key, row.stage, row.decoder_profile,
                    row.evidence_digest)
                or len(row.scan_ids) != len(row.capture_ids)
                or any(scan_id not in scan_map for scan_id in row.scan_ids)
                or any(scan_map[scan_id].capture_id != capture_id
                       for scan_id, capture_id in zip(
                           row.scan_ids, row.capture_ids, strict=True))):
            raise ValueError("e023b attempt provenance is inconsistent")

        if row.stage in ("scan", "union"):
            if row.decoder_profile != baseline_profile:
                raise ValueError(
                    "e023b baseline stage has the wrong decoder profile")
            expected = _baseline_attempt_provenance(
                session, key, row.stage, row.source)
            if ((row.scan_ids, row.capture_ids, row.evidence_digest)
                    != expected):
                raise ValueError(
                    "e023b baseline attempt evidence is inconsistent")
            source_scan_id = (row.source if row.stage == "scan" else
                              row.source.removeprefix("union@"))
            rank = (scan_index[source_scan_id],
                    0 if row.stage == "scan" else 1)
            if rank <= latest_baseline_rank.get(key, (-1, -1)):
                raise ValueError(
                    "e023b baseline attempt chronology is inconsistent")
            latest_baseline_rank[key] = rank
            latest_baseline[key] = row
        elif row.stage == "retry150":
            if row.decoder_profile != retry_profile:
                raise ValueError(
                    "e023b retry stage has the wrong decoder profile")
            parent = latest_baseline.get(key)
            if (parent is None or not parent.decoder_invoked
                    or parent.state != "attempted_failed"
                    or row.source != parent.source
                    or row.evidence_digest != parent.evidence_digest
                    or row.scan_ids != parent.scan_ids
                    or row.capture_ids != parent.capture_ids):
                raise ValueError(
                    "e023b retry lacks its earlier failed baseline parent")
            if any(getattr(row, name) != getattr(parent, name) for name in (
                    "k_eff", "n_nonshort", "n_informative", "coverage",
                    "n_erased")):
                raise ValueError(
                    "e023b retry metrics differ from its baseline parent")
            if parent.stage == "scan":
                parent_index = scan_index[parent.source]
                n_components = sum(
                    key in scan.tile_evidence_digests
                    for scan in session.scans[:parent_index + 1])
                if n_components != 1:
                    raise ValueError(
                        "e023b retry parent is not transaction-final")
        else:
            raise ValueError("e023b attempt has an unknown stage")

        mask = decode.shorten_mask(row.tile_yx)
        expected_nonshort = int((~mask).sum())
        expected_k = max(decode.ldpc_spec.k_bits - int(mask.sum()), 0)
        degenerate = ldpc.tile_user_capacity(mask, decode.ldpc_spec) == 0
        if (row.n_nonshort != expected_nonshort or row.k_eff != expected_k
                or not np.isfinite(row.coverage)
                or not 0.0 <= row.coverage <= 1.0
                or not 0 <= row.n_informative <= row.n_nonshort
                or row.n_iters < 0
                or (not degenerate and row.n_erased
                    != row.n_nonshort - row.n_informative)):
            raise ValueError("e023b attempt accounting is inconsistent")
        if row.state == "degenerate":
            valid_state = (not row.decoder_invoked and degenerate
                           and row.n_informative == 0
                           and row.n_erased == 0
                           and row.n_iters == 0
                           and row.syndrome_ok is None and row.crc_ok is None)
        elif row.state == "below_attempt_floor":
            valid_state = (not row.decoder_invoked and not degenerate
                           and row.n_informative < row.k_eff
                           and row.n_iters == 0
                           and row.syndrome_ok is None and row.crc_ok is None)
        elif row.state == "attempted_failed":
            valid_state = (row.decoder_invoked and not degenerate
                           and row.n_informative >= row.k_eff
                           and isinstance(row.syndrome_ok, (bool, np.bool_))
                           and isinstance(row.crc_ok, (bool, np.bool_))
                           and not (bool(row.syndrome_ok)
                                    and bool(row.crc_ok)))
        elif row.state == "certified":
            valid_state = (row.decoder_invoked and not degenerate
                           and row.n_informative >= row.k_eff
                           and row.syndrome_ok is True
                           and row.crc_ok is True)
        else:
            valid_state = False
        if (not valid_state
                or row.certified_new != (row.state == "certified")):
            raise ValueError("e023b attempt state semantics are inconsistent")
        invoked_by_tile[key] = invoked_by_tile.get(key, 0) + int(
            row.decoder_invoked)
        certified_by_tile[key] = certified_by_tile.get(key, 0) + int(
            row.certified_new)
    for key, outcome in decode.tiles.items():
        if key[0] not in envelope.pages:
            raise ValueError("e023b tile outcome is on an illegal page")
        if outcome.attempts != invoked_by_tile.get(key, 0):
            raise ValueError("e023b per-tile attempt count is inconsistent")
        if outcome.state == "certified":
            if (outcome.user_bits is None
                    or certified_by_tile.get(key, 0) != 1):
                raise ValueError("e023b certificate provenance is incomplete")
        elif certified_by_tile.get(key, 0):
            raise ValueError("e023b non-certified tile owns a certificate")

        # Nonterminal states must end at the evidence frontier implied by the
        # immutable scan list, not merely at whichever baseline ledger row
        # happens to occur last.  Otherwise deleting/reordering a newest
        # union could make an explicit BP retry spend CRC on stale evidence.
        if outcome.state in ("attempted_failed", "below_attempt_floor"):
            frontiers = [
                (index, scan) for index, scan in enumerate(session.scans)
                if (key in scan.tile_evidence_digests
                    and key not in scan.decode_skip_tiles)
            ]
            if not frontiers:
                raise ValueError(
                    "e023b nonterminal tile has no unskipped source evidence")
            frontier_index, frontier = frontiers[-1]
            components = [
                scan for scan in session.scans[:frontier_index + 1]
                if key in scan.tile_evidence_digests
            ]
            expected_stage = "scan" if len(components) == 1 else "union"
            expected_source = (frontier.scan_id if len(components) == 1
                               else f"union@{frontier.scan_id}")
            expected = _baseline_attempt_provenance(
                session, key, expected_stage, expected_source)
            parent = latest_baseline.get(key)
            if (parent is None or parent.stage != expected_stage
                    or parent.source != expected_source
                    or (parent.scan_ids, parent.capture_ids,
                        parent.evidence_digest) != expected):
                raise ValueError(
                    "e023b nonterminal tile is not at its current "
                    "evidence frontier")


def attempt_ready_tiles(
    record: ScanRecord, decode: payloaddec.DecodeState
) -> set[tuple[int, int, int]]:
    """Exact post-owner attempt-floor preview without invoking the decoder."""
    ready = set()
    for key in record.tile_evidence_digests:
        page, ty, tx = key
        vec = record.emission.pages[page]
        mask = decode.shorten_mask((ty, tx))
        if ldpc.tile_user_capacity(mask, decode.ldpc_spec) == 0:
            continue
        llr4096, _mask, _coverage = ldpc.gather_tile_llrs(
            vec["llr"], vec["index"], decode.spec, decode.seed, (ty, tx))
        k_eff = max(decode.ldpc_spec.k_bits - int(mask.sum()), 0)
        n_info = int((llr4096[~mask] != 0.0).sum())
        if n_info >= k_eff:
            ready.add(key)
    return ready


def _attempt_identity(
    key: tuple[int, int, int], stage: str, decoder_profile: str,
    evidence_digest: str,
) -> str:
    return _sha256_bytes(
        b"e023b/tile-attempt/v1", repr(tuple(key)).encode("ascii"),
        stage.encode("ascii"), decoder_profile.encode("ascii"),
        evidence_digest.encode("ascii"))


def decoder_profile(rate_id: str, max_iters: int, alpha: float) -> str:
    """Stable attempt-ledger identity for the qualified hybrid decoder."""
    return (f"{rate_id}/decode_tile-max{int(max_iters)}-"
            f"alpha{float(alpha):g}")


def _apply_evaluation(
    session: ReceiverSession,
    *,
    key: tuple[int, int, int],
    stage: str,
    source: str,
    evidence_digest: str,
    scan_ids: tuple[str, ...],
    capture_ids: tuple[str, ...],
    llr_values: np.ndarray,
    payload_indices: np.ndarray,
    decoder_max_iters: int = BASELINE_BP_MAX_ITERS,
    decoder_alpha: float = BP_ALPHA,
    certificate_source: str | None = None,
) -> tuple[TileAttempt | None, bool]:
    """Evaluate one new evidence identity and append its immutable ledger."""
    page, ty, tx = key
    profile_id = decoder_profile(
        session.envelope.rate_id, decoder_max_iters, decoder_alpha)
    attempt_id = _attempt_identity(key, stage, profile_id,
                                   evidence_digest)
    if attempt_id in session.attempt_ids:
        return None, False
    out = session.decode.outcome(page, (ty, tx))
    if out.state in ("certified", "degenerate"):
        return None, False
    evaluation = payloaddec.evaluate_tile(
        llr_values, payload_indices, session.decode.spec,
        session.decode.seed, (ty, tx), session.decode.ldpc_spec,
        max_iters=decoder_max_iters, alpha=decoder_alpha)
    out.k_eff = evaluation.k_eff
    out.n_nonshort = evaluation.n_nonshort
    out.n_informative_best = max(
        out.n_informative_best, evaluation.n_informative)
    certified_new = False
    if evaluation.state == "degenerate":
        out.state = "degenerate"
    elif evaluation.state == "below_attempt_floor":
        if out.state == "unobserved":
            out.state = "below_attempt_floor"
    else:
        out.attempts += 1
        session.decode.n_attempts += 1
        if evaluation.state == "attempted_failed":
            out.state = "attempted_failed"
        else:
            assert evaluation.user_bits is not None
            if out.state == "certified" and not np.array_equal(
                    out.user_bits, evaluation.user_bits):
                message = (
                    f"tile page={page} {(ty, tx)}: conflicting "
                    f"certifications ({out.certified_by} vs {source})")
                session.decode.fatal.append(message)
                raise payloaddec.FatalIntegrityError(message)
            out.state = "certified"
            out.user_bits = evaluation.user_bits
            out.certified_by = (certificate_source if certificate_source
                                is not None else
                                ("union" if stage == "union" else source))
            out.n_iters = evaluation.n_iters
            certified_new = True
    row = TileAttempt(
        attempt_id=attempt_id, evidence_digest=evidence_digest,
        page=page, tile_yx=(ty, tx), stage=stage, source=source,
        scan_ids=scan_ids, capture_ids=capture_ids,
        decoder_profile=profile_id, state=evaluation.state,
        decoder_invoked=evaluation.decoder_invoked,
        k_eff=evaluation.k_eff, n_nonshort=evaluation.n_nonshort,
        n_informative=evaluation.n_informative,
        coverage=evaluation.coverage, n_iters=evaluation.n_iters,
        syndrome_ok=evaluation.syndrome_ok, crc_ok=evaluation.crc_ok,
        n_erased=evaluation.n_erased, certified_new=certified_new)
    session.attempts.append(row)
    session.attempt_ids.add(attempt_id)
    return row, certified_new


def _attempt_evidence(
    session: ReceiverSession,
    parent: TileAttempt,
    union_cache: dict[
        tuple[int, tuple[str, ...]], tuple[np.ndarray, np.ndarray]
    ] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Reconstruct exactly the scan/union evidence named by an attempt."""
    key = (parent.page, *parent.tile_yx)
    scans = {scan.scan_id: scan for scan in session.scans}
    components = []
    for scan_id, capture_id in zip(
            parent.scan_ids, parent.capture_ids, strict=True):
        scan = scans[scan_id]
        if scan.capture_id != capture_id or key not in scan.tile_evidence_digests:
            raise ValueError("e023b retry parent provenance is inconsistent")
        components.append(scan)

    if parent.stage == "scan":
        if len(components) != 1:
            raise ValueError("e023b scan attempt has ambiguous evidence")
        scan = components[0]
        if scan.tile_evidence_digests[key] != parent.evidence_digest:
            raise ValueError("e023b scan attempt evidence digest changed")
        vec = scan.emission.pages[parent.page]
        return vec["index"], vec["llr"]

    if parent.stage != "union" or len(components) < 2:
        raise ValueError("e023b retry parent is not a baseline scan/union")
    digest = _sha256_bytes(
        b"e023b/union-tile-evidence/v1",
        *(f"{scan.scan_id}:{scan.tile_evidence_digests[key]}".encode(
            "ascii") for scan in components))
    if digest != parent.evidence_digest:
        raise ValueError("e023b union attempt evidence digest changed")

    cache_key = (parent.page, parent.scan_ids)
    if union_cache is not None and cache_key in union_cache:
        return union_cache[cache_key]
    capacity = compose.payload_capacity(session.decode.spec)
    acc = np.zeros(capacity, np.float64)
    touched = np.zeros(capacity, bool)
    for scan in components:
        vec = scan.emission.pages[parent.page]
        acc[vec["index"]] += vec["llr"]
        touched[vec["index"]] = True
    index = np.flatnonzero(touched)
    evidence = (index, acc[index])
    if union_cache is not None:
        union_cache[cache_key] = evidence
    return evidence


def retry_failed_bp(
    session: ReceiverSession,
    *,
    skip_tiles: Iterable[tuple[int, int, int]] = (),
    on_attempt: Callable[[ReceiverSession, TileAttempt], None] | None = None,
) -> tuple[ReceiverSession, dict]:
    """Explicit max-150 repass over the latest failed baseline frontier.

    The action is transactional and evidence-addressed.  It adds at most one
    decoder/CRC exposure per currently failed tile and is a true no-op when
    the same evidence has already received its max-150 attempt.
    """
    session.validate_invariants()
    skipped = set(_normalise_decode_skip_tiles(
        session, skip_tiles, stored=False))
    baseline_profile = decoder_profile(
        session.envelope.rate_id, BASELINE_BP_MAX_ITERS, BP_ALPHA)
    retry_profile = decoder_profile(
        session.envelope.rate_id, RETRY_BP_MAX_ITERS, BP_ALPHA)
    failed = {key for key, out in session.decode.tiles.items()
              if out.state == "attempted_failed"}
    parents: dict[tuple[int, int, int], TileAttempt] = {}
    seen: set[tuple[int, int, int]] = set()
    for row in reversed(session.attempts):
        key = (row.page, *row.tile_yx)
        if (key not in failed or key in seen
                or row.stage not in ("scan", "union")
                or row.decoder_profile != baseline_profile):
            continue
        # The newest baseline evaluation is the evidence frontier even when
        # it did not clear the attempt floor.  Never tunnel through a newer
        # below-floor record to retry stale, stronger-looking evidence.
        seen.add(key)
        if row.decoder_invoked and row.state == "attempted_failed":
            parents[key] = row

    eligible = []
    skipped_failed = 0
    for key, parent in sorted(parents.items()):
        retry_id = _attempt_identity(
            key, "retry150", retry_profile, parent.evidence_digest)
        if retry_id not in session.attempt_ids:
            if key in skipped:
                skipped_failed += 1
            else:
                eligible.append((key, parent))
    if not eligible:
        return session, {
            "noop": True, "frontier": len(parents), "eligible": 0,
            "skipped_failed": skipped_failed,
            "attempted": 0, "certified": 0,
            "total_certified": sum(
                out.state == "certified"
                for out in session.decode.tiles.values()),
        }

    working = session.fork()
    newly_certified: set[tuple[int, int, int]] = set()
    union_cache: dict[
        tuple[int, tuple[str, ...]], tuple[np.ndarray, np.ndarray]
    ] = {}
    attempted = 0
    for key, parent in eligible:
        index, llr_values = _attempt_evidence(
            working, parent, union_cache)
        row, certified = _apply_evaluation(
            working, key=key, stage="retry150", source=parent.source,
            evidence_digest=parent.evidence_digest,
            scan_ids=parent.scan_ids, capture_ids=parent.capture_ids,
            llr_values=llr_values, payload_indices=index,
            decoder_max_iters=RETRY_BP_MAX_ITERS,
            decoder_alpha=BP_ALPHA,
            certificate_source=("union" if parent.stage == "union"
                                else parent.source))
        if row is None or not row.decoder_invoked:
            raise payloaddec.FatalIntegrityError(
                "e023b BP retry frontier changed during transaction")
        attempted += int(row.decoder_invoked)
        if certified:
            newly_certified.add(key)
        if on_attempt is not None:
            on_attempt(working, row)

    if newly_certified:
        # A retry has no new scan transaction, but newly certified tiles need
        # the same all-scan corroboration map as any baseline certificate.
        _update_divergence(working, working.scans[-1], newly_certified)
    working.validate_invariants()
    return working, {
        "noop": False, "frontier": len(parents),
        "eligible": len(eligible), "skipped_failed": skipped_failed,
        "attempted": attempted,
        "certified": len(newly_certified),
        "total_certified": sum(
            out.state == "certified"
            for out in working.decode.tiles.values()),
    }


def _update_divergence(
    session: ReceiverSession,
    new_scan: ScanRecord,
    newly_certified: set[tuple[int, int, int]],
) -> None:
    """Append only the divergence pairs made possible by this transaction."""
    by_id = {scan.scan_id: scan for scan in session.scans}
    for key, out in session.decode.tiles.items():
        if out.state != "certified":
            continue
        scan_ids: Iterable[str]
        if key in newly_certified:
            scan_ids = tuple(by_id)
        elif key in new_scan.tile_evidence_digests:
            scan_ids = (new_scan.scan_id,)
        else:
            continue
        pidx, tx_bits = session.decode.certified_payload_indices(out)
        order = np.argsort(pidx, kind="stable")
        sorted_idx, sorted_bits = pidx[order], tx_bits[order]
        for scan_id in scan_ids:
            emission = by_id[scan_id].emission
            vec = emission.pages.get(out.page)
            if vec is None:
                continue
            pos = np.searchsorted(sorted_idx, vec["index"])
            ok = pos < sorted_idx.size
            ok[ok] = sorted_idx[pos[ok]] == vec["index"][ok]
            if not ok.any():
                continue
            hard = (vec["llr"][ok] > 0).astype(np.uint8)
            want = sorted_bits[pos[ok]]
            out.divergence[scan_id] = float(np.mean(hard != want))


def _apply_scan_unchecked(
    session: ReceiverSession,
    record: ScanRecord,
    *,
    skip_tiles: Iterable[tuple[int, int, int]] = (),
    on_attempt: Callable[[ReceiverSession, TileAttempt], None] | None = None,
) -> tuple[ReceiverSession, dict]:
    """Apply one complete ScanRecord transaction on a private state fork.

    Stage 1 and the changed-evidence union run after every scan.  This is the
    append-consistent E023b production schedule: command grouping cannot
    change which evidence prefixes were considered.
    """
    if record.source_sha256 in session.source_hashes:
        return session, {"noop": True, "stage1": {}, "union": {}}
    if record.capture_id in session.capture_ids:
        raise ValueError(
            f"capture_id {record.capture_id!r} already exists; E023b "
            "refuses to count two derivations of one physical capture")
    record = _record_with_decode_skips(session, record, skip_tiles)
    working = session.fork()
    working.scans.append(record)
    working.decode.scans.append(record.emission)
    working.decode.upstream = tuple(
        (scan.scan_id, scan.source_sha256) for scan in working.scans)
    candidates = sorted(
        set(record.tile_evidence_digests) - set(record.decode_skip_tiles))
    newly_certified: set[tuple[int, int, int]] = set()
    counts = {
        "noop": False,
        "skipped_candidates": len(record.decode_skip_tiles),
        "stage1": {"evaluated": 0, "attempted": 0, "certified": 0},
        "union": {"evaluated": 0, "attempted": 0, "certified": 0},
    }

    for key in candidates:
        page = key[0]
        vec = record.emission.pages[page]
        row, certified = _apply_evaluation(
            working, key=key, stage="scan", source=record.scan_id,
            evidence_digest=record.tile_evidence_digests[key],
            scan_ids=(record.scan_id,), capture_ids=(record.capture_id,),
            llr_values=vec["llr"], payload_indices=vec["index"])
        if row is None:
            continue
        counts["stage1"]["evaluated"] += 1
        counts["stage1"]["attempted"] += int(row.decoder_invoked)
        counts["stage1"]["certified"] += int(certified)
        if certified:
            newly_certified.add(key)
        if on_attempt is not None:
            on_attempt(working, row)

    capacity = compose.payload_capacity(working.decode.spec)
    accumulators: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for page in {key[0] for key in candidates}:
        acc = np.zeros(capacity, np.float64)
        touched = np.zeros(capacity, bool)
        for scan in working.scans:
            vec = scan.emission.pages.get(page)
            if vec is None:
                continue
            acc[vec["index"]] += vec["llr"]
            touched[vec["index"]] = True
        idx = np.flatnonzero(touched)
        accumulators[page] = (idx, acc[idx])

    for key in candidates:
        out = working.decode.tiles.get(key)
        if out is not None and out.state in ("certified", "degenerate"):
            continue
        components = [
            (scan.scan_id, scan.capture_id,
             scan.tile_evidence_digests[key])
            for scan in working.scans if key in scan.tile_evidence_digests
        ]
        if len(components) < 2:
            continue                         # identical to Stage 1
        evidence_digest = _sha256_bytes(
            b"e023b/union-tile-evidence/v1",
            *(f"{sid}:{digest}".encode("ascii")
              for sid, _capture, digest in components))
        idx, llr_values = accumulators[key[0]]
        row, certified = _apply_evaluation(
            working, key=key, stage="union",
            source=f"union@{record.scan_id}",
            evidence_digest=evidence_digest,
            scan_ids=tuple(row[0] for row in components),
            capture_ids=tuple(row[1] for row in components),
            llr_values=llr_values, payload_indices=idx)
        if row is None:
            continue
        counts["union"]["evaluated"] += 1
        counts["union"]["attempted"] += int(row.decoder_invoked)
        counts["union"]["certified"] += int(certified)
        if certified:
            newly_certified.add(key)
        if on_attempt is not None:
            on_attempt(working, row)

    _update_divergence(working, record, newly_certified)
    counts["total_certified"] = sum(
        out.state == "certified" for out in working.decode.tiles.values())
    counts["newly_certified"] = len(newly_certified)
    return working, counts


def apply_scan(
    session: ReceiverSession,
    record: ScanRecord,
    *,
    skip_tiles: Iterable[tuple[int, int, int]] = (),
    on_attempt: Callable[[ReceiverSession, TileAttempt], None] | None = None,
) -> tuple[ReceiverSession, dict]:
    """Validate and apply one complete raw-derived scan transaction."""
    session.validate_invariants()
    # A caller-supplied ScanRecord is untrusted even when its source is an
    # already-applied no-op.  Authorize a semantic decode-skip marker before
    # taking the duplicate-source fast path.
    record = _record_with_decode_skips(session, record, skip_tiles)
    if record.source_sha256 in session.source_hashes:
        return session, {"noop": True, "stage1": {}, "union": {}}
    if record.scan_id in {scan.scan_id for scan in session.scans}:
        raise ValueError(f"scan_id {record.scan_id!r} already exists")
    if record.capture_id in session.capture_ids:
        raise ValueError(
            f"capture_id {record.capture_id!r} already exists; E023b "
            "refuses to count two derivations of one physical capture")
    _validate_scan_record(session, record)
    _check_combined_bch(session, record)
    working, counts = _apply_scan_unchecked(
        session, record, skip_tiles=record.decode_skip_tiles,
        on_attempt=on_attempt)
    working.validate_invariants()
    return working, counts


def replay_frozen_scan_for_qualification(
    session: ReceiverSession,
    record: ScanRecord,
) -> tuple[ReceiverSession, dict]:
    """Apply an old reduced emission only as a scheduling oracle.

    Frozen E023 artifacts do not contain E023b's non-owner WindowEvidence,
    so they cannot form a valid production ScanRecord.  Keeping this explicit
    prevents reduced replay fixtures from masquerading as integrated states.
    """
    return _apply_scan_unchecked(
        session, record, skip_tiles=record.decode_skip_tiles)


def as_payloaddec_session(session: ReceiverSession) -> payloaddec.E022Session:
    """Compatibility view for the frozen E023 batch qualification oracle."""
    scans = tuple(payloaddec.E022Scan(
        scan_id=scan.scan_id, source_path=scan.source_path,
        source_sha256=scan.source_sha256, dpi=scan.dpi, result=scan.result)
        for scan in session.scans)
    return payloaddec.E022Session(
        format_id=session.envelope.format_id, seed=session.envelope.seed,
        pages=session.envelope.pages, dpi=session.envelope.dpi, scans=scans)
