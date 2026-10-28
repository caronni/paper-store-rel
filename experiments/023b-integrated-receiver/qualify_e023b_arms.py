#!/usr/bin/env python
"""Frozen 2x2 qualification for E023b.1 detector/decoder arms.

This runner is intentionally separate from the production entry point.  It
opens only the two byte-pinned E023b.0 rich states, replays their retained
window evidence under pava-v1 and ctx-pava-v1, and then evaluates each
detector with and without the explicit max-150 BP action.  In particular it
does *not* weaken :func:`paperholo.receiver.load_session`: the legacy pickle
compatibility exception lives only in this file and is guarded before
unpickling by a complete-file SHA-256.

Ground truth is not opened until all four blind arm outputs have been reduced
to compact certificate and hard-emission snapshots.  It is used only for the
qualification-only correctness and BER columns.
"""
from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import json
import pickle
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy import ndimage


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, payloaddec, receiver  # noqa: E402
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402


BUILD = HERE / "build"
GT_PATH = ROOT / "experiments/018-confetti-c3-play/build/e018_gt/K__e018_field.npy"
GT_SHA256 = "6c6f54b7a8dec9d5b5d4e75ce5a29af4323bb91da5eca50391cc5d5eebc5cc82"

# Complete frozen artifact identities.  A prefix is not sufficient here:
# pickle is executable input, so the digest is checked by streaming the file
# *before* pickle.load is called.
FOOTINGS = {
    "decimated": {
        "path": BUILD / "e023b_decimated.pkl",
        "sha256": "a34baa9379e23788c013b1772ef44b6f7d964c0e7aa25ef46b4d983a5880ee30",
    },
    "native": {
        "path": BUILD / "e023b_native.pkl",
        "sha256": "328e9ce6b1c6d01e722d90b0fa92324c3f280e86273a4470ba361aa505e1282e",
    },
}

# Both frozen states were produced by this exact 22-row implementation tuple.
# The canonical digest is SHA256(JSON(tuple), compact separators); pinning it
# prevents a correctly named state with a foreign legacy envelope from being
# admitted by the qualification-only compatibility path.
LEGACY_IMPLEMENTATION_SHA256 = (
    "e89d65ae5d24a7a0dd3d11a7c6b4738677d712d27e01f927b8659d3125f8a959")
LEGACY_STATE_MAGIC = "e023b-session-v1"
LEGACY_STATE_VERSION = 1

ARM_ORDER = ("baseline", "bp", "context", "combined")

# These preregistered promotion gates require process-level or repository-level
# tests.  This numerical runner deliberately does not pretend to execute them.
EXTERNAL_HARD_GATES = (
    "detector_profile_state_save_reload_and_raw_replay",
    "diagnostic_on_off_and_duplicate_input_state_identity",
    "bp_retry_idempotence_and_one_exposure_per_eligible_identity",
    "failed_context_gate_byte_identical_to_baseline_region",
    "focused_e021_through_e023b_and_complete_repository_suites",
)


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _implementation_digest(rows) -> str:
    normalized = tuple((str(name), str(value)) for name, value in rows)
    data = json.dumps(normalized, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")
    return hashlib.sha256(data).hexdigest()


def _load_frozen_session(path: Path, expected_sha256: str
                         ) -> tuple[receiver.ReceiverSession, dict]:
    """Qualification-only legacy loader, fail-closed before unpickling."""
    actual_sha256 = _stream_sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"frozen state SHA-256 mismatch for {path}: "
            f"{actual_sha256} != {expected_sha256}")
    with path.open("rb") as stream:
        envelope = pickle.load(stream)
    if (not isinstance(envelope, dict)
            or envelope.get("magic") != LEGACY_STATE_MAGIC
            or int(envelope.get("version", -1)) != LEGACY_STATE_VERSION
            or not isinstance(envelope.get("session"),
                              receiver.ReceiverSession)):
        raise ValueError(f"{path} is not the pinned E023b.0 state envelope")
    session = envelope["session"]
    implementation_sha256 = _implementation_digest(
        session.envelope.implementation_sha256)
    if implementation_sha256 != LEGACY_IMPLEMENTATION_SHA256:
        raise ValueError(
            "legacy implementation fingerprint mismatch: "
            f"{implementation_sha256} != {LEGACY_IMPLEMENTATION_SHA256}")
    if session.envelope.algorithm_id != "e023b.0-qualified-core":
        raise ValueError("frozen state is not the E023b.0 qualified core")
    # Schema-v2 added explicit detector identity and context-fit sidecars.
    # The complete file and implementation pins above authorize only this
    # narrow in-memory migration; no migrated object is accepted by or saved
    # through production load_session.
    if not hasattr(session.envelope, "detector_profile"):
        object.__setattr__(session.envelope, "detector_profile",
                           payloaddec.DETECTOR_PAVA_V1)
    for record in session.scans:
        if not hasattr(record, "detector_profile"):
            object.__setattr__(record, "detector_profile",
                               payloaddec.DETECTOR_PAVA_V1)
        if not hasattr(record, "context_fits"):
            object.__setattr__(record, "context_fits", ())
    return session, {
        "path": str(path), "sha256": actual_sha256,
        "state_magic": LEGACY_STATE_MAGIC,
        "state_version": LEGACY_STATE_VERSION,
        "algorithm_id": session.envelope.algorithm_id,
        "legacy_implementation_sha256": implementation_sha256,
        "legacy_implementation_rows": len(
            session.envelope.implementation_sha256),
    }


def _descriptor(format_id: str):
    rows = [row for row in FORMAT_REGISTRY if row.format_id == format_id]
    if len(rows) != 1:
        raise ValueError(f"format registry has {len(rows)} rows for {format_id}")
    return rows[0]


def _array_equal(a, b) -> bool:
    """Byte/dtype/shape exact array equality for historical parity gates."""
    left = np.ascontiguousarray(np.asarray(a))
    right = np.ascontiguousarray(np.asarray(b))
    return (left.dtype.str == right.dtype.str
            and left.shape == right.shape
            and left.tobytes(order="C") == right.tobytes(order="C"))


def _legacy_row_exact(a: payloaddec.WindowEmission,
                      b: payloaddec.WindowEmission) -> bool:
    """Compare every E023b.0 WindowEmission field, excluding new sidecars."""
    scalar_names = (
        "placement_ordinal", "page", "heldout_logloss", "n_train_labels",
        "n_heldout", "refused", "refuse_reason", "diagnostics",
        "region_index",
    )
    array_names = (
        "payload_index", "payload_llr", "page_cells_yx", "raw_means",
        "scores", "calibration_score_nodes",
        "calibration_probability_nodes",
    )
    return (all(getattr(a, name) == getattr(b, name)
                for name in scalar_names)
            and all(_array_equal(getattr(a, name), getattr(b, name))
                    for name in array_names))


def _current_baseline_row_exact(a: payloaddec.WindowEmission,
                                b: payloaddec.WindowEmission) -> bool:
    """Exact pava-v1 row equality including the schema-v2 sidecars."""
    return (
        _legacy_row_exact(a, b)
        and getattr(a, "detector_profile", payloaddec.DETECTOR_PAVA_V1)
        == getattr(b, "detector_profile", payloaddec.DETECTOR_PAVA_V1)
        == payloaddec.DETECTOR_PAVA_V1
        and getattr(a, "context_fit", None) is None
        and getattr(b, "context_fit", None) is None
    )


def _context_fit_errors(fit: payloaddec.ContextFit) -> list[str]:
    """Independent audit of every registered ctx-pava-v1 fit invariant."""
    errors: list[str] = []
    tau = np.asarray(fit.tau)
    search_support = np.asarray(fit.search_support_by_bin)
    validation_support = np.asarray(fit.validation_support_by_bin)
    search_observations = np.asarray(fit.search_observations_by_bin)
    validation_observations = np.asarray(
        fit.validation_observations_by_bin)
    if tau.shape != (9,) or not np.isfinite(tau).all():
        errors.append("tau must be nine finite offsets")
    else:
        if np.any(tau < payloaddec.CTX_OFFSET_MIN) or np.any(
                tau > payloaddec.CTX_OFFSET_MAX):
            errors.append("tau exceeds registered [-4,4] bounds")
        if np.any(tau[:-1] < tau[1:]):
            errors.append("tau is not nonincreasing")
    for name, support, total in (
        ("search", search_support, fit.n_search),
        ("validation", validation_support, fit.n_validation),
    ):
        if (support.shape != (9,) or not np.isfinite(support).all()
                or np.any(support < 0.0)):
            errors.append(f"{name} bin support is malformed")
        elif not np.isclose(float(support.sum()), float(total),
                            rtol=0.0, atol=1e-9):
            errors.append(f"{name} bin support does not sum to unique total")
    for name, observations, total, support in (
        ("search", search_observations, fit.n_search_observations,
         search_support),
        ("validation", validation_observations,
         fit.n_validation_observations, validation_support),
    ):
        if (observations.shape != (9,)
                or not np.issubdtype(observations.dtype, np.integer)
                or np.any(observations < 0)):
            errors.append(f"{name} raw bin observations are malformed")
        elif int(observations.sum()) != total:
            errors.append(
                f"{name} raw bin observations do not sum to total")
        elif (support.shape == (9,)
              and np.any(support > observations + 1e-12)):
            errors.append(
                f"{name} unique bin support exceeds raw observations")
    if fit.detector_profile != payloaddec.DETECTOR_CTX_PAVA_V1:
        errors.append("fit carries the wrong detector profile")
    if fit.n_search != fit.n_search_0 + fit.n_search_1:
        errors.append("SEARCH class counts do not sum to unique total")
    if fit.n_validation != fit.n_validation_0 + fit.n_validation_1:
        errors.append("VALIDATION class counts do not sum to unique total")
    if (fit.n_search_observations < fit.n_search
            or fit.n_validation_observations < fit.n_validation):
        errors.append("observation count is below unique support")
    if not (0 <= fit.n_context_valid_cells <= fit.n_context_cells):
        errors.append("context-valid cell coverage is impossible")
    if not (0 <= fit.n_refused_windows <= fit.n_windows):
        errors.append("refused-window support is impossible")

    expected_eligible = (
        fit.n_search >= payloaddec.CTX_MIN_SEARCH
        and min(fit.n_search_0, fit.n_search_1)
        >= payloaddec.CTX_MIN_SEARCH_PER_CLASS
        and fit.n_validation >= payloaddec.CTX_MIN_VALIDATION
        and min(fit.n_validation_0, fit.n_validation_1)
        >= payloaddec.CTX_MIN_VALIDATION_PER_CLASS
    )
    if fit.eligible != expected_eligible:
        errors.append("eligibility does not match registered support floors")
    if not expected_eligible:
        if fit.n_search < payloaddec.CTX_MIN_SEARCH:
            expected_reason = "insufficient_search_support"
        elif min(fit.n_search_0, fit.n_search_1) < (
                payloaddec.CTX_MIN_SEARCH_PER_CLASS):
            expected_reason = "search_class_starved"
        elif fit.n_validation < payloaddec.CTX_MIN_VALIDATION:
            expected_reason = "insufficient_validation_support"
        else:
            expected_reason = "validation_class_starved"
        if fit.reason != expected_reason:
            errors.append("ineligible fit carries the wrong reason")
        if fit.adopted:
            errors.append("ineligible fit was adopted")
        if (fit.baseline_validation_logloss is not None
                or fit.candidate_validation_logloss is not None):
            errors.append("ineligible fit carries gate losses")
        if tau.shape == (9,) and np.any(tau != 0.0):
            errors.append("ineligible fit carries nonzero offsets")
    else:
        losses = (fit.baseline_validation_logloss,
                  fit.candidate_validation_logloss)
        if any(value is None or not np.isfinite(value) for value in losses):
            errors.append("eligible fit lacks finite held-out losses")
        else:
            should_adopt = bool(losses[1] < losses[0])
            if fit.adopted != should_adopt:
                errors.append("adoption is not the strict held-out decision")
            expected_reason = ("adopted" if should_adopt
                               else "validation_gate_failed")
            if fit.reason != expected_reason:
                errors.append("eligible fit carries the wrong gate reason")
    return errors


def _emission_exact(a: payloaddec.ScanEmission,
                    b: payloaddec.ScanEmission) -> bool:
    if (a.scan_id != b.scan_id or a.source_sha256 != b.source_sha256
            or a.window_rows != b.window_rows
            or set(a.pages) != set(b.pages)):
        return False
    return all(
        set(a.pages[page]) == set(b.pages[page])
        and all(_array_equal(a.pages[page][name], b.pages[page][name])
                for name in a.pages[page])
        for page in a.pages)


def _forced_raw_replay_rows(record: receiver.ScanRecord
                            ) -> tuple[payloaddec.WindowEmission, ...]:
    """Make shallow qualification views that force baseline derivation.

    E023b.0 predates the detector sidecar fields.  Merely assigning their
    defaults would let reprofile_window_evidence return the original pava-v1
    objects as its fast path.  Marking shallow views as derived context rows
    instead exercises the raw-means -> scores -> PAVA -> payload replay for
    every stored row; the stored scores/nodes are validated derivations and
    all large arrays remain shared with the pinned state.
    """
    rows = []
    for stored in record.window_evidence:
        row = copy.copy(stored)
        row.detector_profile = payloaddec.DETECTOR_CTX_PAVA_V1
        row.context_fit = None
        rows.append(row)
    return tuple(rows)


def _profile_record(record: receiver.ScanRecord, descriptor,
                    detector_profile: str
                    ) -> tuple[receiver.ScanRecord,
                               payloaddec.ReprofileResult, bool, bool]:
    forced = _forced_raw_replay_rows(record)
    baseline_replay = payloaddec.reprofile_window_evidence(
        tuple(record.result.placements), forced, descriptor.spec(),
        descriptor.seed, payloaddec.DETECTOR_PAVA_V1)
    replay = (baseline_replay if detector_profile ==
              payloaddec.DETECTOR_PAVA_V1 else
              payloaddec.reprofile_window_evidence(
                  tuple(record.result.placements), forced,
                  descriptor.spec(), descriptor.seed, detector_profile))
    scan = payloaddec.E022Scan(
        record.scan_id, record.source_path, record.source_sha256,
        record.dpi, record.result)
    emission = payloaddec.freeze_scan_emission(
        scan, list(replay.emissions), descriptor.spec())
    baseline_exact = True
    if detector_profile == payloaddec.DETECTOR_PAVA_V1:
        baseline_exact = (
            len(replay.emissions) == len(record.window_evidence)
            and all(_legacy_row_exact(got, want) for got, want in zip(
                replay.emissions, record.window_evidence, strict=True))
            and _emission_exact(emission, record.emission))
    nonadopted_exact = True
    if detector_profile == payloaddec.DETECTOR_CTX_PAVA_V1:
        fits = {int(fit.region_index): fit for fit in replay.context_fits}
        for got, want in zip(replay.emissions, baseline_replay.emissions,
                             strict=True):
            fit = fits.get(int(got.region_index))
            if fit is None:
                raise ValueError("context replay omitted a placement region")
            # A refused window never changes.  Every row in a rejected or
            # ineligible region must be the exact raw-replayed pava-v1 row.
            if (got.refused or not fit.adopted) and not (
                    _current_baseline_row_exact(got, want)):
                nonadopted_exact = False
    profiled = replace(
        record, detector_profile=detector_profile,
        window_evidence=replay.emissions, context_fits=replay.context_fits,
        emission=emission,
        tile_evidence_digests=receiver.tile_evidence_digests(
            emission, descriptor.spec(), descriptor.seed),
        timings={**record.timings, "qualification_profile": detector_profile})
    return profiled, replay, baseline_exact, nonadopted_exact


def _state_counts(session: receiver.ReceiverSession) -> dict[str, int]:
    counts = Counter(payloaddec.full_tile_states(session.decode).values())
    return {key: int(counts[key]) for key in sorted(counts)}


def _tile_signature(session: receiver.ReceiverSession) -> tuple:
    rows = []
    for key, out in sorted(session.decode.tiles.items()):
        user = (None if out.user_bits is None else
                (int(out.user_bits.size),
                 np.packbits(out.user_bits).tobytes()))
        rows.append((key, out.state, user, out.certified_by, out.k_eff,
                     out.n_informative_best, out.n_nonshort, out.n_iters,
                     out.attempts, tuple(sorted(out.divergence.items()))))
    return tuple(rows)


def _certificate_snapshot(session: receiver.ReceiverSession
                          ) -> dict[tuple[int, int, int], tuple[int, bytes]]:
    return {
        key: (int(out.user_bits.size),
              np.packbits(out.user_bits).tobytes())
        for key, out in session.decode.tiles.items()
        if out.state == "certified" and out.user_bits is not None
    }


def _certificate_set_digest(certs: dict) -> str:
    digest = hashlib.sha256()
    for key in sorted(certs):
        digest.update(json.dumps(key, separators=(",", ":")).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _certificate_bits_digest(certs: dict) -> str:
    digest = hashlib.sha256()
    for key, (size, packed) in sorted(certs.items()):
        digest.update(json.dumps(key, separators=(",", ":")).encode("ascii"))
        digest.update(int(size).to_bytes(8, "big"))
        digest.update(packed)
    return digest.hexdigest()


def _attempt_metrics(session: receiver.ReceiverSession) -> dict:
    stages: dict[str, dict[str, int]] = {}
    for row in session.attempts:
        bucket = stages.setdefault(row.stage, {
            "ledger_records": 0, "crc_calls": 0,
            "bp_iterations": 0, "certified_new": 0,
        })
        bucket["ledger_records"] += 1
        bucket["crc_calls"] += int(row.decoder_invoked)
        bucket["bp_iterations"] += int(row.n_iters)
        bucket["certified_new"] += int(row.certified_new)
    crc_calls = sum(int(row.decoder_invoked) for row in session.attempts)
    if crc_calls != session.decode.n_attempts:
        raise ValueError("attempt ledger CRC count differs from DecodeState")
    return {
        "ledger_records": len(session.attempts),
        "crc_calls": crc_calls,
        "bp_iterations": sum(int(row.n_iters) for row in session.attempts),
        "below_floor_records": sum(
            row.state == "below_attempt_floor" for row in session.attempts),
        "crc_false_accept_budget": crc_calls * payloaddec.CRC_FALSE_ACCEPT,
        "by_stage": {key: stages[key] for key in sorted(stages)},
    }


def _prefix_row(session: receiver.ReceiverSession, scan_id: str,
                counts: dict) -> dict:
    return {
        "scan_id": scan_id,
        "tile_states": _state_counts(session),
        "certified": len(_certificate_snapshot(session)),
        "attempts": _attempt_metrics(session),
        "transaction": counts,
    }


@dataclass
class ArmCompact:
    report: dict
    certs: dict[tuple[int, int, int], tuple[int, bytes]]


def _compact_arm(session: receiver.ReceiverSession, prefix: list[dict],
                 retry: dict | None) -> ArmCompact:
    session.validate_invariants()
    certs = _certificate_snapshot(session)
    report = {
        "prefix": prefix,
        "retry": retry,
        "final": {
            "tile_states": _state_counts(session),
            "certified": len(certs),
            "attempts": _attempt_metrics(session),
            "fatal": list(session.decode.fatal),
        },
        "certificates": {
            "count": len(certs),
            "tiles": [list(key) for key in sorted(certs)],
            "set_sha256": _certificate_set_digest(certs),
            "bits_sha256": _certificate_bits_digest(certs),
        },
    }
    return ArmCompact(report, certs)


class DetectorAccumulator:
    def __init__(self, profile: str, descriptor):
        self.profile = profile
        self.pim = compose.payload_index_map(
            descriptor.spec(), descriptor.seed)
        self.heldout: list[float] = []
        self.refused = 0
        self.windows = 0
        self.fits: list[tuple[str, payloaddec.ContextFit]] = []
        self.fit_invariant_errors: list[str] = []
        self.profile_completion_errors: list[str] = []
        self.owner_rows: list[dict] = []
        self.owner_pairs: Counter[tuple[str, int, int]] = Counter()
        self.hard: dict[tuple[int, int], tuple[int, bytes]] = {}
        # Compact blind snapshot aligned to each frozen scan/page emission:
        # one uint8 provisional bin plus packed valid/adopted-region flags.
        self.owner_context: dict[
            tuple[int, int], tuple[int, bytes, bytes, bytes]
        ] = {}

    def _owner_context_snapshot(
        self, profiled: receiver.ScanRecord, page: int, vec: dict,
    ) -> tuple[int, bytes, bytes, bytes]:
        size = int(np.asarray(vec["index"]).size)
        bins = np.full(size, 255, np.uint8)
        valid = np.zeros(size, bool)
        region_adopted = np.zeros(size, bool)
        evidence = {int(row.placement_ordinal): row
                    for row in profiled.window_evidence}
        cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, bool]] = {}
        owner = np.asarray(vec["owner"], np.int64)
        index = np.asarray(vec["index"], np.int64)
        for ordinal in np.unique(owner):
            row = evidence[int(ordinal)]
            if row.refused:
                raise ValueError("refused row owns frozen payload evidence")
            if int(row.page) != int(page):
                raise ValueError("payload owner belongs to another page")
            if int(ordinal) not in cache:
                l0 = payloaddec.apply_calibration(
                    row.scores, row.calibration_score_nodes,
                    row.calibration_probability_nodes)
                count, complete = payloaddec.context_neighbor_counts(
                    row.page_cells_yx, l0 > 0.0)
                cells = np.asarray(row.page_cells_yx, np.int64)
                pidx = self.pim[cells[:, 0], cells[:, 1]]
                selected = pidx >= 0
                payload_index = pidx[selected].astype(np.int64)
                if not _array_equal(payload_index, row.payload_index):
                    raise ValueError(
                        "owner context replay changed payload indexing")
                fit = getattr(row, "context_fit", None)
                cache[int(ordinal)] = (
                    payload_index, count[selected], complete[selected],
                    bool(fit is not None and fit.adopted),
                )
            row_index, row_bin, row_valid, adopted = cache[int(ordinal)]
            positions = np.flatnonzero(owner == ordinal)
            order = np.argsort(row_index, kind="stable")
            sorted_index = row_index[order]
            match = np.searchsorted(sorted_index, index[positions])
            if (np.any(match >= sorted_index.size)
                    or not np.array_equal(
                        sorted_index[match], index[positions])):
                raise ValueError("owner context replay lost emitted cells")
            source = order[match]
            bins[positions] = row_bin[source]
            valid[positions] = row_valid[source]
            region_adopted[positions] = adopted
        if np.any(bins == 255):
            raise ValueError("owner context snapshot is incomplete")
        return (
            size, bins.tobytes(order="C"),
            np.packbits(valid, bitorder="little").tobytes(),
            np.packbits(region_adopted, bitorder="little").tobytes(),
        )

    def add(self, scan_index: int, legacy: receiver.ScanRecord,
            profiled: receiver.ScanRecord,
            replay: payloaddec.ReprofileResult) -> None:
        self.windows += len(profiled.window_evidence)
        for row in profiled.window_evidence:
            if row.refused:
                self.refused += 1
            else:
                self.heldout.append(float(row.heldout_logloss))
        self.fits.extend((profiled.scan_id, fit)
                         for fit in replay.context_fits)
        if self.profile == payloaddec.DETECTOR_CTX_PAVA_V1:
            region_windows = Counter(
                int(row.region_index) for row in profiled.window_evidence)
            region_refused = Counter(
                int(row.region_index) for row in profiled.window_evidence
                if row.refused)
            fit_regions = [int(fit.region_index)
                           for fit in replay.context_fits]
            if (len(fit_regions) != len(set(fit_regions))
                    or set(fit_regions) != set(region_windows)):
                self.profile_completion_errors.append(
                    f"{profiled.scan_id}: context fits do not cover each "
                    "placement region exactly once")
            for fit in replay.context_fits:
                region = int(fit.region_index)
                if fit.n_windows != region_windows.get(region, -1):
                    self.profile_completion_errors.append(
                        f"{profiled.scan_id}/r{region}: fit window count "
                        "does not match replay rows")
                if fit.n_refused_windows != region_refused.get(region, 0):
                    self.profile_completion_errors.append(
                        f"{profiled.scan_id}/r{region}: refused-window "
                        "count does not match replay rows")
        for fit in replay.context_fits:
            self.fit_invariant_errors.extend(
                f"{profiled.scan_id}/r{fit.region_index}: {error}"
                for error in _context_fit_errors(fit))

        compared = changed = 0
        old_owners: set[int] = set()
        new_owners: set[int] = set()
        if set(legacy.emission.pages) != set(profiled.emission.pages):
            raise ValueError("detector arm changed emitted page coverage")
        for page in sorted(legacy.emission.pages):
            old = legacy.emission.pages[page]
            new = profiled.emission.pages[page]
            if not _array_equal(old["index"], new["index"]):
                raise ValueError("detector arm changed emitted cell coverage")
            delta = np.asarray(old["owner"]) != np.asarray(new["owner"])
            compared += int(delta.size)
            changed += int(delta.sum())
            if delta.any():
                old_owners.update(int(v) for v in old["owner"][delta])
                new_owners.update(int(v) for v in new["owner"][delta])
                for before, after in zip(old["owner"][delta],
                                         new["owner"][delta], strict=True):
                    self.owner_pairs[(profiled.scan_id, int(before),
                                      int(after))] += 1
            hard = np.asarray(new["llr"]) > 0.0
            self.hard[(scan_index, int(page))] = (
                int(hard.size), np.packbits(hard, bitorder="little").tobytes())
            self.owner_context[(scan_index, int(page))] = (
                self._owner_context_snapshot(profiled, int(page), new))
        self.owner_rows.append({
            "scan_id": profiled.scan_id, "cells": compared,
            "changed": changed,
            "fraction": changed / compared if compared else None,
            "old_windows": len(old_owners), "new_windows": len(new_owners),
        })

    def summary(self) -> dict:
        heldout = np.asarray(self.heldout, np.float64)
        compared = sum(row["cells"] for row in self.owner_rows)
        changed = sum(row["changed"] for row in self.owner_rows)
        fits = [fit for _scan, fit in self.fits]
        eligible = [fit for fit in fits if fit.eligible]
        adopted = [fit for fit in fits if fit.adopted]

        def weighted_loss(name: str) -> float | None:
            rows = [(getattr(fit, name), fit.n_validation)
                    for fit in eligible if getattr(fit, name) is not None]
            if not rows or sum(weight for _value, weight in rows) == 0:
                return None
            return float(sum(value * weight for value, weight in rows)
                         / sum(weight for _value, weight in rows))

        reasons = Counter(fit.reason for fit in fits)

        def summed_bins(name: str, dtype) -> list:
            if not fits:
                return np.zeros(9, dtype).tolist()
            return np.sum(
                np.stack([np.asarray(getattr(fit, name), dtype)
                          for fit in fits]), axis=0).tolist()

        context = {
            "fits": len(fits), "eligible": len(eligible),
            "adopted": len(adopted),
            "profile_completed": not self.profile_completion_errors,
            "profile_completion_errors": list(
                self.profile_completion_errors),
            "fit_invariants_ok": not self.fit_invariant_errors,
            "fit_invariant_errors": list(self.fit_invariant_errors),
            "reasons": dict(sorted(reasons.items())),
            "context_valid_cells": sum(
                fit.n_context_valid_cells for fit in fits),
            "context_cells": sum(fit.n_context_cells for fit in fits),
            "context_valid_coverage": None,
            "search_unique_total": sum(fit.n_search for fit in fits),
            "validation_unique_total": sum(
                fit.n_validation for fit in fits),
            "search_observations_total": sum(
                fit.n_search_observations for fit in fits),
            "validation_observations_total": sum(
                fit.n_validation_observations for fit in fits),
            "search_effective_support_by_bin": summed_bins(
                "search_support_by_bin", np.float64),
            "validation_effective_support_by_bin": summed_bins(
                "validation_support_by_bin", np.float64),
            "search_raw_observations_by_bin": summed_bins(
                "search_observations_by_bin", np.int64),
            "validation_raw_observations_by_bin": summed_bins(
                "validation_observations_by_bin", np.int64),
            "search_unique_min": (min((fit.n_search for fit in fits),
                                      default=None)),
            "validation_unique_min": (min(
                (fit.n_validation for fit in fits), default=None)),
            "baseline_validation_logloss_weighted": weighted_loss(
                "baseline_validation_logloss"),
            "candidate_validation_logloss_weighted": weighted_loss(
                "candidate_validation_logloss"),
            "adopted_by_scan": dict(sorted(Counter(
                scan for scan, fit in self.fits if fit.adopted).items())),
        }
        if context["context_cells"]:
            context["context_valid_coverage"] = (
                context["context_valid_cells"] / context["context_cells"])
        if adopted:
            tau = np.stack([fit.tau for fit in adopted])
            context["adopted_tau_median"] = [float(v) for v in
                                               np.median(tau, axis=0)]
            context["adopted_tau_min"] = [float(v) for v in
                                            np.min(tau, axis=0)]
            context["adopted_tau_max"] = [float(v) for v in
                                            np.max(tau, axis=0)]

        return {
            "profile": self.profile,
            "calibration": {
                "windows": self.windows - self.refused,
                "refused": self.refused,
                "heldout_logloss_mean": (float(heldout.mean())
                                          if heldout.size else None),
                "heldout_logloss_median": (float(np.median(heldout))
                                            if heldout.size else None),
                "heldout_logloss_p95": (float(np.percentile(heldout, 95))
                                         if heldout.size else None),
                "heldout_logloss_max": (float(heldout.max())
                                         if heldout.size else None),
            },
            "context": context,
            "owner_changes": {
                "cells": compared, "changed": changed,
                "fraction": changed / compared if compared else None,
                "by_scan": self.owner_rows,
                "distinct_owner_pairs": len(self.owner_pairs),
                "top_owner_pairs": [
                    {"scan_id": key[0], "from": key[1], "to": key[2],
                     "cells": count}
                    for key, count in self.owner_pairs.most_common(12)],
            },
        }


def _legacy_replay_exact(legacy: receiver.ReceiverSession,
                         replayed: receiver.ReceiverSession) -> bool:
    return (
        replayed.decode.upstream == legacy.decode.upstream
        and replayed.decode.n_attempts == legacy.decode.n_attempts
        and tuple(replayed.attempts) == tuple(legacy.attempts)
        and replayed.attempt_ids == legacy.attempt_ids
        and _tile_signature(replayed) == _tile_signature(legacy)
        and len(replayed.scans) == len(legacy.scans)
        and all(_emission_exact(a.emission, b.emission)
                for a, b in zip(replayed.scans, legacy.scans, strict=True)))


def _run_detector(legacy: receiver.ReceiverSession, descriptor,
                  detector_profile: str
                  ) -> tuple[ArmCompact, ArmCompact, DetectorAccumulator,
                             dict]:
    session = receiver.ReceiverSession.create(
        descriptor, legacy.envelope.pages, legacy.envelope.dpi,
        rate_id=legacy.envelope.rate_id,
        detector_profile=detector_profile,
        search_config=legacy.envelope.search_config)
    prefix: list[dict] = []
    detector = DetectorAccumulator(detector_profile, descriptor)
    pava_rows_exact = True
    pava_scan_emissions_exact = True
    context_nonadopted_exact = True

    for scan_index, record in enumerate(legacy.scans):
        profiled, replay, baseline_exact, nonadopted_exact = _profile_record(
            record, descriptor, detector_profile)
        pava_rows_exact &= baseline_exact
        context_nonadopted_exact &= nonadopted_exact
        if detector_profile == payloaddec.DETECTOR_PAVA_V1:
            pava_scan_emissions_exact &= _emission_exact(
                profiled.emission, record.emission)
        detector.add(scan_index, record, profiled, replay)
        session, counts = receiver.apply_scan(session, profiled)
        prefix.append(_prefix_row(session, profiled.scan_id, counts))
        print(f"    {profiled.scan_id}: "
              f"cert={prefix[-1]['certified']} "
              f"crc={prefix[-1]['attempts']['crc_calls']}", flush=True)

    baseline = _compact_arm(session, prefix, retry=None)
    legacy_exact = (None if detector_profile != payloaddec.DETECTOR_PAVA_V1
                    else _legacy_replay_exact(legacy, session))
    retried_session, retry_counts = receiver.retry_failed_bp(session)
    retried = _compact_arm(retried_session, prefix, retry=retry_counts)
    if detector_profile == payloaddec.DETECTOR_PAVA_V1:
        gates = {
            "pava_window_rows_exact": bool(pava_rows_exact),
            "pava_scan_emissions_exact": bool(pava_scan_emissions_exact),
            "pava_append_replay_exact": bool(legacy_exact),
        }
    else:
        gates = {
            "context_profile_completed": (
                not detector.profile_completion_errors),
            "context_fit_invariants": not detector.fit_invariant_errors,
            "context_nonadopted_and_refused_rows_exact": bool(
                context_nonadopted_exact),
        }
    del retried_session, session
    gc.collect()
    return baseline, retried, detector, gates


def _unpack_certificate(value: tuple[int, bytes]) -> np.ndarray:
    size, packed = value
    return np.unpackbits(np.frombuffer(packed, np.uint8))[:size].astype(
        np.uint8, copy=False)


def _load_ground_truth(descriptor) -> tuple[np.ndarray, np.ndarray, np.ndarray,
                                             dict]:
    actual_sha256 = _stream_sha256(GT_PATH)
    if actual_sha256 != GT_SHA256:
        raise ValueError(
            f"ground-truth SHA-256 mismatch: {actual_sha256} != {GT_SHA256}")
    dots = np.load(GT_PATH)
    spec = descriptor.spec()
    field = dots[::spec.cell_dots, ::spec.cell_dots].astype(np.uint8)
    if field.shape != tuple(spec.page_cells_yx):
        raise ValueError("frozen GT geometry does not match format")
    pim = compose.payload_index_map(spec, descriptor.seed)
    cells = np.argwhere(pim >= 0)
    order = np.argsort(pim[cells[:, 0], cells[:, 1]], kind="stable")
    cells = cells[order]
    if not np.array_equal(
            pim[cells[:, 0], cells[:, 1]], np.arange(cells.shape[0])):
        raise ValueError("payload inverse is not contiguous")
    keystream = compose.payload_keystream(spec, descriptor.seed, 0)
    gt_bits = (field[cells[:, 0], cells[:, 1]]
               ^ keystream[cells[:, 0], cells[:, 1]]).astype(np.uint8)
    kernel = np.ones((3, 3), np.int16)
    kernel[1, 1] = 0
    neighbor_count = ndimage.convolve(
        field.astype(np.int16), kernel, mode="constant", cval=0)
    return field, gt_bits, neighbor_count, {
        "path": str(GT_PATH), "sha256": actual_sha256,
        "loaded_after_blind_arm_outputs": True,
    }


def _wrong_certificates(certs: dict, descriptor, gt_bits: np.ndarray,
                        rate_id: str) -> list[tuple[int, int, int]]:
    decode = payloaddec.DecodeState(descriptor, rate_id, (0,), ())
    wrong = []
    for key, packed in sorted(certs.items()):
        if key[0] != 0:
            raise ValueError("frozen E018 GT qualifies page 0 only")
        outcome = payloaddec.TileOutcome(
            page=key[0], tile_yx=(key[1], key[2]), state="certified",
            user_bits=_unpack_certificate(packed))
        pidx, tx_bits = decode.certified_payload_indices(outcome)
        if not np.array_equal(tx_bits, gt_bits[pidx]):
            wrong.append(key)
    return wrong


def _emitted_ber(detector: DetectorAccumulator,
                 legacy: receiver.ReceiverSession, gt_bits: np.ndarray,
                 neighbor_count: np.ndarray, descriptor) -> dict:
    inv = payloaddec._payload_inverse(descriptor.spec(), descriptor.seed)
    total = wrong = 0
    true_context = {value: [0, 0] for value in range(9)}
    split_names = ("all", "adopted_region", "nonadopted_region")
    provisional = {
        value: {split: [0, 0] for split in split_names}
        for value in range(9)
    }
    invalid = {split: [0, 0] for split in split_names}

    def add_metric(bucket: list[int], selected: np.ndarray,
                   bad: np.ndarray) -> None:
        bucket[0] += int(selected.sum())
        bucket[1] += int(bad[selected].sum())

    def metric(bucket: list[int]) -> dict:
        count, bad = bucket
        return {
            "cells": count,
            "wrong": bad,
            "ber": bad / count if count else None,
        }

    for scan_index, record in enumerate(legacy.scans):
        for page, vec in sorted(record.emission.pages.items()):
            if page != 0:
                raise ValueError("frozen E018 GT qualifies page 0 only")
            size, packed = detector.hard[(scan_index, int(page))]
            hard = np.unpackbits(
                np.frombuffer(packed, np.uint8), bitorder="little")[:size]
            index = np.asarray(vec["index"], np.int64)
            if index.size != size:
                raise ValueError("hard-emission snapshot changed coverage")
            bad = hard != gt_bits[index]
            total += size
            wrong += int(bad.sum())
            cells = inv[index]
            true_bins = neighbor_count[cells[:, 0], cells[:, 1]]
            for value in range(9):
                add_metric(true_context[value], true_bins == value, bad)

            (context_size, bins_packed, valid_packed,
             adopted_packed) = detector.owner_context[
                 (scan_index, int(page))]
            if context_size != size:
                raise ValueError("owner-context snapshot changed coverage")
            bins = np.frombuffer(bins_packed, np.uint8, count=size)
            valid = np.unpackbits(
                np.frombuffer(valid_packed, np.uint8),
                bitorder="little")[:size].astype(bool, copy=False)
            adopted = np.unpackbits(
                np.frombuffer(adopted_packed, np.uint8),
                bitorder="little")[:size].astype(bool, copy=False)
            if np.any(bins > 8):
                raise ValueError("owner provisional context bin is invalid")
            selections = {
                "all": np.ones(size, bool),
                "adopted_region": adopted,
                "nonadopted_region": ~adopted,
            }
            for value in range(9):
                in_bin = valid & (bins == value)
                for split, split_selected in selections.items():
                    add_metric(provisional[value][split],
                               in_bin & split_selected, bad)
            for split, split_selected in selections.items():
                add_metric(invalid[split], (~valid) & split_selected, bad)

    true_cells = sum(bucket[0] for bucket in true_context.values())
    valid_cells = sum(provisional[value]["all"][0]
                      for value in range(9))
    if true_cells != total or valid_cells + invalid["all"][0] != total:
        raise ValueError("BER context stratification lost observations")
    return {
        "cells": total, "wrong": wrong,
        "ber": wrong / total if total else None,
        "observation_semantics": {
            "unit": ("one frozen one-owner payload observation from one "
                     "scan; the same physical page cell may recur in other "
                     "scans"),
            "error_domain": "descrambled transmitted payload bits",
            "true_printed_bins": (
                "eight-neighbor ink count from the frozen printed GT field; "
                "off-page neighbors are white"),
            "provisional_bins": (
                "eight-neighbor count of owner-window baseline PAVA L0>0; "
                "valid only when all eight neighbors share that window core"),
            "adopted_region": (
                "the owner row belongs to a region whose context fit passed "
                "the held-out gate; invalid-context cells remain uncorrected"),
        },
        "by_true_printed_ink_neighbors": {
            str(value): metric(true_context[value])
            for value in range(9)
        },
        "owner_provisional_context": {
            "valid_by_provisional_ink_neighbors": {
                str(value): {
                    split: metric(provisional[value][split])
                    for split in split_names
                }
                for value in range(9)
            },
            "invalid_context": {
                split: metric(invalid[split]) for split in split_names
            },
        },
    }


def _changed_certificates(a: dict, b: dict) -> set:
    return {key for key in set(a) & set(b) if a[key] != b[key]}


def _effect(before: ArmCompact, after: ArmCompact) -> dict:
    a, b = before.certs, after.certs
    return {
        "gained": [list(key) for key in sorted(set(b) - set(a))],
        "lost": [list(key) for key in sorted(set(a) - set(b))],
        "changed": [list(key) for key in sorted(_changed_certificates(a, b))],
        "yield_delta": len(b) - len(a),
    }


def _attach_certificate_results(arms: dict[str, ArmCompact], descriptor,
                                gt_bits: np.ndarray, rate_id: str) -> None:
    baseline = arms["baseline"].certs
    for name in ARM_ORDER:
        arm = arms[name]
        current = arm.certs
        wrong = _wrong_certificates(current, descriptor, gt_bits, rate_id)
        arm.report["certificates"].update({
            "new_from_baseline": [list(key) for key in
                                  sorted(set(current) - set(baseline))],
            "lost_from_baseline": [list(key) for key in
                                   sorted(set(baseline) - set(current))],
            "changed_from_baseline": [list(key) for key in sorted(
                _changed_certificates(baseline, current))],
            "wrong": [list(key) for key in wrong],
        })


def _factorial(arms: dict[str, ArmCompact]) -> dict:
    sets = {name: set(arms[name].certs) for name in ARM_ORDER}
    bp0 = sets["bp"] - sets["baseline"]
    ctx0 = sets["context"] - sets["baseline"]
    combined = sets["combined"] - sets["baseline"]
    independent = bp0 | ctx0
    return {
        "effects": {
            "bp_at_pava": _effect(arms["baseline"], arms["bp"]),
            "context_without_bp": _effect(
                arms["baseline"], arms["context"]),
            "bp_at_context": _effect(arms["context"], arms["combined"]),
            "context_with_bp": _effect(arms["bp"], arms["combined"]),
            "combined_from_baseline": _effect(
                arms["baseline"], arms["combined"]),
        },
        "bp_context_independent_gain_overlap": [
            list(key) for key in sorted(bp0 & ctx0)],
        "bp_only_independent_gain": [
            list(key) for key in sorted(bp0 - ctx0)],
        "context_only_independent_gain": [
            list(key) for key in sorted(ctx0 - bp0)],
        "independent_gain_union": [
            list(key) for key in sorted(independent)],
        "combined_only_synergy": [
            list(key) for key in sorted(combined - independent)],
        "independent_gains_absent_from_combined": [
            list(key) for key in sorted(independent - combined)],
        "yield_interaction_difference_in_differences": (
            (len(sets["combined"]) - len(sets["context"]))
            - (len(sets["bp"]) - len(sets["baseline"]))),
        "changed_certificate_pairs": {
            "baseline_to_bp": [list(key) for key in sorted(
                _changed_certificates(arms["baseline"].certs,
                                      arms["bp"].certs))],
            "baseline_to_context": [list(key) for key in sorted(
                _changed_certificates(arms["baseline"].certs,
                                      arms["context"].certs))],
            "context_to_combined": [list(key) for key in sorted(
                _changed_certificates(arms["context"].certs,
                                      arms["combined"].certs))],
        },
    }


def run_footing(name: str, path: Path, expected_sha256: str) -> dict:
    print(f"\n=== {name}: pinned rich-state 2x2 ===", flush=True)
    legacy, reference = _load_frozen_session(path, expected_sha256)
    descriptor = _descriptor(legacy.envelope.format_id)
    if tuple(legacy.envelope.pages) != (0,):
        raise ValueError("this frozen GT qualification is page-0-only")

    print("  pava-v1 append replay", flush=True)
    baseline, bp, pava_detector, pava_gates = _run_detector(
        legacy, descriptor, payloaddec.DETECTOR_PAVA_V1)
    print("  ctx-pava-v1 append replay", flush=True)
    context, combined, context_detector, context_gates = _run_detector(
        legacy, descriptor, payloaddec.DETECTOR_CTX_PAVA_V1)
    arms = {
        "baseline": baseline, "bp": bp,
        "context": context, "combined": combined,
    }

    # All blind detector/decoder outputs now exist in compact form.  Only at
    # this boundary may qualification consult the frozen printed field.
    _field, gt_bits, neighbor_count, gt_reference = _load_ground_truth(
        descriptor)
    _attach_certificate_results(
        arms, descriptor, gt_bits, legacy.envelope.rate_id)
    pava_ber = _emitted_ber(
        pava_detector, legacy, gt_bits, neighbor_count, descriptor)
    context_ber = _emitted_ber(
        context_detector, legacy, gt_bits, neighbor_count, descriptor)

    pava_summary = pava_detector.summary()
    context_summary = context_detector.summary()
    for arm_name in ("baseline", "bp"):
        arms[arm_name].report["detector"] = pava_summary
        arms[arm_name].report["emitted_gt"] = pava_ber
    for arm_name in ("context", "combined"):
        arms[arm_name].report["detector"] = context_summary
        arms[arm_name].report["emitted_gt"] = context_ber

    factorial = _factorial(arms)
    all_correct = all(
        not arms[name].report["certificates"]["wrong"]
        for name in ARM_ORDER)
    no_changed = all(
        not arms[name].report["certificates"]["changed_from_baseline"]
        for name in ARM_ORDER)
    no_fatal = all(not arms[name].report["final"]["fatal"]
                   for name in ARM_ORDER)
    numerical_gates = {
        "state_file_sha256": True,
        "legacy_implementation_fingerprint": True,
        **pava_gates,
        **context_gates,
        "all_certificates_gt_correct": all_correct,
        "no_baseline_certificate_value_changed": no_changed,
        "no_fatal_integrity_flags": no_fatal,
    }
    numerical_gates_ok = all(
        value is True for value in numerical_gates.values())
    print(f"  result: baseline={len(baseline.certs)} bp={len(bp.certs)} "
          f"context={len(context.certs)} combined={len(combined.certs)} "
          f"BER {pava_ber['ber']:.5f}->{context_ber['ber']:.5f} "
          f"NUMERICAL {'PASS' if numerical_gates_ok else 'FAIL'} "
          "(external hard gates not run)", flush=True)
    return {
        "reference": reference,
        "ground_truth": gt_reference,
        "numerical_gates": numerical_gates,
        "numerical_gates_ok": numerical_gates_ok,
        "arms": {name: arms[name].report for name in ARM_ORDER},
        "factorial": factorial,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only", choices=("decimated", "native", "both"), default="both",
        help="qualify one footing or the frozen pair")
    parser.add_argument("--decimated", type=Path,
                        default=FOOTINGS["decimated"]["path"])
    parser.add_argument("--native", type=Path,
                        default=FOOTINGS["native"]["path"])
    parser.add_argument("--out", type=Path,
                        default=BUILD / "qualify_arms_report.json")
    args = parser.parse_args()
    selected = (("decimated",) if args.only == "decimated" else
                ("native",) if args.only == "native" else
                ("decimated", "native"))
    paths = {"decimated": args.decimated, "native": args.native}
    report = {
        "experiment": "023b.1-algorithm-arms",
        "design": str(HERE / "ALGORITHM-ARMS.md"),
        "implementation": {
            "qualification_harness_sha256": _stream_sha256(
                Path(__file__).resolve()),
            "production_entrypoint_sha256": _stream_sha256(
                HERE / "run_e023b.py"),
            "payloaddec_sha256": _stream_sha256(
                Path(payloaddec.__file__).resolve()),
            "receiver_sha256": _stream_sha256(
                Path(receiver.__file__).resolve()),
            "design_sha256": _stream_sha256(HERE / "ALGORITHM-ARMS.md"),
        },
        "factorial": {
            "detectors": [payloaddec.DETECTOR_PAVA_V1,
                          payloaddec.DETECTOR_CTX_PAVA_V1],
            "decoders": ["baseline-max60", "explicit-retry-max150"],
        },
        "boundary": "LDPC and below; no fountain/rank/stop condition",
        "qualification_scope": {
            "numerical_runner_executed": True,
            "external_hard_gates_executed": False,
            "promotion_hard_gates_ok": None,
            "note": ("A numerical pass is not a promotion pass. The "
                     "process- and repository-level hard gates below are "
                     "listed but are never executed by this runner."),
            "external_hard_gates": list(EXTERNAL_HARD_GATES),
        },
        "external_contract_tests_not_run": {
            "tests": [
                "tests/test_e023b_context.py",
                "tests/test_e023b_algorithm_arms.py",
                "tests/test_e023b_session.py",
            ],
        },
        "footings": {},
    }
    try:
        for name in selected:
            report["footings"][name] = run_footing(
                name, paths[name], FOOTINGS[name]["sha256"])
            gc.collect()
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["numerical_gates_ok"] = False
        report["status"] = "numerical_fail"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"\nE023b.1 ARMS NUMERICAL FAIL: {report['error']} "
              f"(external hard gates not run) -> {args.out}",
              file=sys.stderr)
        return 1

    report["numerical_gates_ok"] = all(
        report["footings"][name]["numerical_gates_ok"]
        for name in selected)
    report["status"] = (
        "numerical_pass_external_hard_gates_not_run"
        if report["numerical_gates_ok"] else "numerical_fail")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if report["numerical_gates_ok"]:
        print("\nE023b.1 ARMS NUMERICAL PASS; EXTERNAL HARD GATES NOT RUN "
              f"-> {args.out}")
    else:
        print("\nE023b.1 ARMS NUMERICAL FAIL; EXTERNAL HARD GATES NOT RUN "
              f"-> {args.out}")
    return 0 if report["numerical_gates_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
