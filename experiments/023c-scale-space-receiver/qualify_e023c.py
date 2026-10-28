#!/usr/bin/env python
"""Run the E023c native/box3 geometry-sampler factorial.

This is a qualification-only runner, not a production receiver state.  It
uses the two byte-pinned E023b.0 states as immutable E021/E022 geometry
inventories, then genuinely resamples the original rasters in four lanes:

    NN  native geometry,    native sampler
    DD  box3 geometry,      box3 sampler
    ND  native geometry,    box3 sampler
    DN  box3 geometry,      native sampler

Every lane independently performs PAVA, the registered context correction,
one-owner freezing, append-consistent LDPC scheduling, and final max-150 BP.
The lanes share no LLR evidence.  They meet only at the conflict-checked CRC
certificate boundary.

The unit of orchestration is one physical capture.  Both sampler views finish
all four emissions before any lane advances to the next capture.  With two
workers, one worker owns the native raster (NN then DN) while the other owns
the box3 raster (DD then ND).  State application remains deterministic and
ordered after the all-view barrier.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E023B = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(E023B))
sys.path.insert(0, str(HERE))

import qualify_e023b_arms as arms  # noqa: E402
import qualify_e023b_multiview as multiview  # noqa: E402
import scale_space  # noqa: E402
from paperholo import payloaddec, pilotsearch, receiver  # noqa: E402


REPORT_PATH = HERE / "E023C-QUALIFICATION.json"
LANE_ORDER = ("NN", "DD", "ND", "DN")
LANE_CONFIG = {
    "NN": ("native", "native", None),
    "DD": ("decimated", "decimated", None),
    "ND": ("native", "decimated", "to_box"),
    "DN": ("decimated", "native", "from_box"),
}
SAMPLER_GROUPS = {
    "native": ("NN", "DN"),
    "decimated": ("DD", "ND"),
}
EXPECTED_FINAL = {
    "DD": multiview.EXPECTED["branches"]["decimated"]["after_bp"],
    "NN": multiview.EXPECTED["branches"]["native"]["after_bp"],
    "baseline_union": multiview.EXPECTED["branches"]["union"]["certificates"],
}


@dataclass(frozen=True)
class FrozenScan:
    footing: str
    scan_id: str
    capture_id: str
    source_path: Path
    source_sha256: str
    source_size: int
    dpi: float
    image_shape: tuple[int, int]
    placements: tuple[pilotsearch.PlacedWindow, ...]
    pava_window_evidence: tuple[payloaddec.WindowEmission, ...]
    pava_emission: payloaddec.ScanEmission


@dataclass(frozen=True)
class Footing:
    name: str
    dpi: float
    pages: tuple[int, ...]
    rate_id: str
    search_config: pilotsearch.SearchConfig
    scans: tuple[FrozenScan, ...]
    reference: dict


@dataclass
class BlindRun:
    report: dict
    certificates: dict[str, dict]
    sessions: dict[str, receiver.ReceiverSession]


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"cannot serialize {type(value)!r}")


def _sha256_json(value) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_json_atomic(path: Path, payload: dict) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True,
                       default=_json_default) + "\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _certificate_summary(certs: dict) -> dict:
    return {
        "count": len(certs),
        "set_sha256": arms._certificate_set_digest(certs),
        "bits_sha256": arms._certificate_bits_digest(certs),
    }


def _packed_certificates(certs: dict) -> dict:
    return {
        key: scale_space.PackedCertificate(
            n_bits=int(value[0]), packed_bits=value[1], bitorder="big")
        for key, value in certs.items()
    }


def _portfolio_snapshot(
    portfolio: scale_space.CertificatePortfolio,
) -> dict:
    return {
        key: (
            row.certificate.n_bits,
            np.packbits(row.certificate.bits(), bitorder="big").tobytes(),
        )
        for key, row in portfolio.certificates.items()
    }


def _load_footing(name: str, path: Path) -> tuple[object, Footing]:
    expected = arms.FOOTINGS[name]["sha256"]
    session, reference = arms._load_frozen_session(path, expected)
    descriptor = arms._descriptor(session.envelope.format_id)
    scans = []
    for record in session.scans:
        source = Path(record.source_path).resolve()
        scans.append(FrozenScan(
            footing=name,
            scan_id=str(record.scan_id),
            capture_id=str(record.capture_id),
            source_path=source,
            source_sha256=str(record.source_sha256),
            source_size=int(record.source_size),
            dpi=float(record.dpi),
            image_shape=tuple(int(value) for value in record.image_shape),
            placements=tuple(record.result.placements),
            pava_window_evidence=tuple(record.window_evidence),
            pava_emission=record.emission,
        ))
    footing = Footing(
        name=name,
        dpi=float(session.envelope.dpi),
        pages=tuple(int(value) for value in session.envelope.pages),
        rate_id=str(session.envelope.rate_id),
        search_config=session.envelope.search_config,
        scans=tuple(scans),
        reference=reference,
    )
    del session
    gc.collect()
    return descriptor, footing


def _pair_footings(
    native: Footing,
    decimated: Footing,
    limit: int | None,
) -> list[dict[str, FrozenScan]]:
    if len(native.scans) != len(decimated.scans):
        raise ValueError("native and decimated state scan counts differ")
    count = len(native.scans) if limit is None else min(limit, len(native.scans))
    pairs = []
    for index, (nat, dec) in enumerate(
            zip(native.scans, decimated.scans, strict=True)):
        if index >= count:
            break
        if nat.capture_id != dec.capture_id:
            raise ValueError(
                f"capture order differs at {index}: "
                f"{nat.capture_id!r} != {dec.capture_id!r}")
        pairs.append({"native": nat, "decimated": dec})
    if not pairs:
        raise ValueError("at least one physical capture is required")
    return pairs


def _source_preflight(pairs: list[dict[str, FrozenScan]]) -> dict:
    rows = []
    totals = {
        "pairs": 0,
        "derived_pixels": 0,
        "mismatched_pixels": 0,
        "uncompared_pixels": 0,
    }
    for index, pair in enumerate(pairs):
        print(
            f"preflight {index + 1}/{len(pairs)} "
            f"{pair['native'].capture_id}: source hashes + exact box3",
            flush=True)
        identities = {}
        for name in ("native", "decimated"):
            scan = pair[name]
            sha256, size = receiver.file_identity(scan.source_path)
            if (sha256, size) != (scan.source_sha256, scan.source_size):
                raise ValueError(
                    f"{scan.source_path} differs from its frozen state")
            identities[name] = {
                "path": str(scan.source_path),
                "sha256": sha256,
                "size": size,
                "dpi": scan.dpi,
                "shape": list(scan.image_shape),
            }
        native_image = receiver.load_image(pair["native"].source_path)
        decimated_image = receiver.load_image(pair["decimated"].source_path)
        comparison = scale_space.compare_box_decimation(
            native_image, decimated_image, 3, chunk_rows=256)
        if not comparison.exact:
            raise ValueError(
                f"{pair['native'].capture_id}: external box3 raster differs "
                f"from the exact registered transform: {comparison}")
        row = {
            "capture_id": pair["native"].capture_id,
            "sources": identities,
            "box3": asdict(comparison),
        }
        rows.append(row)
        totals["pairs"] += 1
        totals["derived_pixels"] += comparison.compared_pixels
        totals["mismatched_pixels"] += comparison.mismatched_pixels
        totals["uncompared_pixels"] += comparison.uncompared_pixels
        del native_image, decimated_image
        gc.collect()
    totals["all_sources_match_frozen_identity"] = True
    totals["all_box3_pixels_exact"] = (
        totals["mismatched_pixels"] == 0
        and totals["uncompared_pixels"] == 0)
    return {"captures": rows, "totals": totals}


def _synthetic_source_sha(
    lane: str,
    geometry: FrozenScan,
    sampler: FrozenScan,
) -> str:
    return hashlib.sha256(
        (
            f"e023c/factorial-v1/{lane}/{geometry.capture_id}/"
            f"{geometry.source_sha256}/{sampler.source_sha256}"
        ).encode("ascii")
    ).hexdigest()


def _lane_placements(
    lane: str,
    geometry: FrozenScan,
    sampler: FrozenScan,
) -> tuple[list[pilotsearch.PlacedWindow], dict]:
    _geometry_name, _sampler_name, direction = LANE_CONFIG[lane]
    transform = scale_space.BoxPixelTransform(3)
    scan_id = f"{lane.lower()}-{geometry.scan_id}"
    placements = []
    core_cells = 0
    mapped_min = np.array([np.inf, np.inf], np.float64)
    mapped_max = np.array([-np.inf, -np.inf], np.float64)
    for placed in geometry.placements:
        if direction is None:
            current = placed
        else:
            current = scale_space.transfer_placed_window(
                placed, transform, direction=direction, scan_id=scan_id)
        check = scale_space.require_transferred_core_in_bounds(
            current, sampler.image_shape)
        core_cells += check.n_core_cells
        if check.mapped_min_yx is not None:
            mapped_min = np.minimum(mapped_min, check.mapped_min_yx)
            mapped_max = np.maximum(mapped_max, check.mapped_max_yx)
        placements.append(current)
    return placements, {
        "placements": len(placements),
        "authoritative_core_cells": core_cells,
        "out_of_bounds": 0,
        "mapped_min_yx": (
            None if not np.isfinite(mapped_min).all()
            else [float(value) for value in mapped_min]),
        "mapped_max_yx": (
            None if not np.isfinite(mapped_max).all()
            else [float(value) for value in mapped_max]),
    }


def _window_metrics(
    pava_rows: tuple[payloaddec.WindowEmission, ...],
    context: payloaddec.ReprofileResult,
    emission: payloaddec.ScanEmission,
) -> dict:
    accepted = [row for row in context.emissions if not row.refused]
    fits = list(context.context_fits)
    heldout = np.asarray(
        [row.heldout_logloss for row in accepted], np.float64)
    return {
        "windows": len(context.emissions),
        "pava_refused": sum(row.refused for row in pava_rows),
        "context_refused": sum(row.refused for row in context.emissions),
        "accepted": len(accepted),
        "emitted_cells": sum(
            int(vector["index"].size) for vector in emission.pages.values()),
        "heldout_logloss_mean": (
            float(heldout.mean()) if heldout.size else None),
        "heldout_logloss_median": (
            float(np.median(heldout)) if heldout.size else None),
        "context_fits": len(fits),
        "context_eligible": sum(fit.eligible for fit in fits),
        "context_adopted": sum(fit.adopted for fit in fits),
        "context_reasons": {
            reason: sum(fit.reason == reason for fit in fits)
            for reason in sorted({fit.reason for fit in fits})
        },
    }


def _sample_lane(
    lane: str,
    geometry: FrozenScan,
    sampler: FrozenScan,
    image: np.ndarray,
    descriptor,
    pages: tuple[int, ...],
) -> tuple[object, dict]:
    started = time.monotonic()
    placements, bounds = _lane_placements(lane, geometry, sampler)
    same_view = geometry.footing == sampler.footing
    scan_id = (
        geometry.scan_id if same_view
        else f"{lane.lower()}-{geometry.scan_id}")
    source_sha256 = (
        sampler.source_sha256 if geometry.footing == sampler.footing
        else _synthetic_source_sha(lane, geometry, sampler))
    result = pilotsearch.SearchResult(placements=placements)
    scan = payloaddec.E022Scan(
        scan_id=scan_id,
        source_path=str(sampler.source_path),
        source_sha256=source_sha256,
        dpi=sampler.dpi,
        result=result,
    )
    pava_rows = tuple(payloaddec.collect_window_evidence(
        scan, image, descriptor.spec(), descriptor.seed, pages,
        detector_profile=payloaddec.DETECTOR_PAVA_V1))
    pava_emission = payloaddec.freeze_scan_emission(
        scan, list(pava_rows), descriptor.spec())
    rows_exact = emission_exact = None
    if same_view:
        rows_exact = (
            len(pava_rows) == len(geometry.pava_window_evidence)
            and all(
                arms._legacy_row_exact(got, want)
                for got, want in zip(
                    pava_rows, geometry.pava_window_evidence, strict=True)
            )
        )
        emission_exact = arms._emission_exact(
            pava_emission, geometry.pava_emission)
        if not rows_exact or not emission_exact:
            raise ValueError(
                f"{lane}/{geometry.capture_id}: live same-view PAVA "
                "resampling differs from the frozen E023b evidence")
    context = payloaddec.reprofile_window_evidence(
        tuple(placements), pava_rows, descriptor.spec(), descriptor.seed,
        payloaddec.DETECTOR_CTX_PAVA_V1)
    emission = payloaddec.freeze_scan_emission(
        scan, list(context.emissions), descriptor.spec())
    record = SimpleNamespace(
        scan_id=scan_id,
        capture_id=geometry.capture_id,
        source_sha256=source_sha256,
        emission=emission,
        tile_evidence_digests=receiver.tile_evidence_digests(
            emission, descriptor.spec(), descriptor.seed),
    )
    metrics = {
        "lane": lane,
        "capture_id": geometry.capture_id,
        "scan_id": scan_id,
        "geometry_source": geometry.footing,
        "sampler_source": sampler.footing,
        "source_sha256": source_sha256,
        "bounds": bounds,
        "same_view_pava_rows_exact": rows_exact,
        "same_view_pava_emission_exact": emission_exact,
        "pava_emission_digest": receiver._canonical_digest(pava_emission),
        "context_emission_digest": receiver._canonical_digest(emission),
        "sampling": _window_metrics(pava_rows, context, emission),
        "elapsed_s": time.monotonic() - started,
    }
    del pava_rows, pava_emission, context, placements, result
    gc.collect()
    return record, metrics


def _sample_group(
    sampler_name: str,
    pair: dict[str, FrozenScan],
    descriptor,
    pages: tuple[int, ...],
) -> dict[str, tuple[object, dict]]:
    sampler = pair[sampler_name]
    image = receiver.load_image(sampler.source_path)
    outputs = {}
    try:
        for lane in SAMPLER_GROUPS[sampler_name]:
            geometry_name = LANE_CONFIG[lane][0]
            outputs[lane] = _sample_lane(
                lane, pair[geometry_name], sampler, image,
                descriptor, pages)
    finally:
        del image
        gc.collect()
    return outputs


def _new_lane_sessions(
    descriptor,
    footings: dict[str, Footing],
) -> dict[str, receiver.ReceiverSession]:
    sessions = {}
    for lane in LANE_ORDER:
        geometry_name, sampler_name, _direction = LANE_CONFIG[lane]
        geometry = footings[geometry_name]
        sampler = footings[sampler_name]
        sessions[lane] = receiver.ReceiverSession.create(
            descriptor,
            geometry.pages,
            sampler.dpi,
            rate_id=geometry.rate_id,
            detector_profile=payloaddec.DETECTOR_CTX_PAVA_V1,
            search_config=geometry.search_config,
        )
    return sessions


def _prefix_row(
    session: receiver.ReceiverSession,
    capture_id: str,
    counts: dict,
) -> dict:
    certs = arms._certificate_snapshot(session)
    return {
        "capture_id": capture_id,
        "certificates": _certificate_summary(certs),
        "attempts": arms._attempt_metrics(session),
        "tile_states": arms._state_counts(session),
        "transaction": counts,
    }


def _run_blind(
    pairs: list[dict[str, FrozenScan]],
    descriptor,
    footings: dict[str, Footing],
    workers: int,
) -> BlindRun:
    sessions = _new_lane_sessions(descriptor, footings)
    prefixes = {lane: [] for lane in LANE_ORDER}
    sampling = {lane: [] for lane in LANE_ORDER}
    started = time.monotonic()
    for index, pair in enumerate(pairs):
        capture_id = pair["native"].capture_id
        print(
            f"\ncapture {index + 1}/{len(pairs)} {capture_id}: "
            f"sample four lanes ({workers} worker{'s' if workers != 1 else ''})",
            flush=True)
        if workers == 1:
            groups = {
                name: _sample_group(
                    name, pair, descriptor, footings[name].pages)
                for name in ("native", "decimated")
            }
        else:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    name: pool.submit(
                        _sample_group, name, pair, descriptor,
                        footings[name].pages)
                    for name in ("native", "decimated")
                }
                groups = {
                    name: futures[name].result()
                    for name in ("native", "decimated")
                }
        barrier = {}
        for group in groups.values():
            barrier.update(group)
        if set(barrier) != set(LANE_ORDER):
            raise ValueError("capture barrier did not produce all four lanes")
        print("  all-view barrier complete; apply lanes", flush=True)
        for lane in LANE_ORDER:
            record, metrics = barrier[lane]
            sessions[lane], counts = receiver._apply_scan_unchecked(
                sessions[lane], record)
            sampling[lane].append(metrics)
            prefix = _prefix_row(sessions[lane], capture_id, counts)
            prefixes[lane].append(prefix)
            print(
                f"  {lane}: cells={metrics['sampling']['emitted_cells']:,} "
                f"cert={prefix['certificates']['count']} "
                f"crc={prefix['attempts']['crc_calls']}",
                flush=True)
        del groups, barrier
        gc.collect()

    certificates = {}
    lane_reports = {}
    for lane in LANE_ORDER:
        before = arms._certificate_snapshot(sessions[lane])
        retry = multiview._retry_without_record_validation(sessions[lane])
        after = arms._certificate_snapshot(sessions[lane])
        certificates[lane] = after
        metrics = arms._attempt_metrics(sessions[lane])
        lane_reports[lane] = {
            "geometry": LANE_CONFIG[lane][0],
            "sampler": LANE_CONFIG[lane][1],
            "prefix": prefixes[lane],
            "sampling": sampling[lane],
            "before_bp": _certificate_summary(before),
            "after_bp": _certificate_summary(after),
            "retry": retry,
            "attempts": metrics,
            "tile_states": arms._state_counts(sessions[lane]),
            "fatal": list(sessions[lane].decode.fatal),
        }
        print(
            f"{lane} final: {len(before)} -> {len(after)} "
            f"({metrics['crc_calls']} CRC calls, "
            f"{metrics['bp_iterations']} BP iterations)",
            flush=True)

    packed = {
        lane: _packed_certificates(certificates[lane])
        for lane in LANE_ORDER
    }
    portfolio = scale_space.merge_certificate_portfolio(packed)
    portfolio_certs = _portfolio_snapshot(portfolio)
    baseline = scale_space.merge_certificate_portfolio({
        lane: packed[lane] for lane in ("NN", "DD")
    })
    baseline_certs = _portfolio_snapshot(baseline)
    baseline_set = set(baseline_certs)
    pairwise = []
    for left_index, left in enumerate(LANE_ORDER):
        for right in LANE_ORDER[left_index + 1:]:
            a, b = set(certificates[left]), set(certificates[right])
            pairwise.append({
                "left": left,
                "right": right,
                "intersection": len(a & b),
                "left_only": len(a - b),
                "right_only": len(b - a),
                "union": len(a | b),
            })
    portfolio_report = {
        "baseline_NN_DD": _certificate_summary(baseline_certs),
        "all_four": _certificate_summary(portfolio_certs),
        "gained_beyond_baseline": {
            "count": len(set(portfolio_certs) - baseline_set),
            "tiles": [
                list(key) for key in sorted(
                    set(portfolio_certs) - baseline_set)
            ],
        },
        "cross_lane_unique_beyond_baseline": {
            lane: [
                list(key) for key in sorted(
                    set(certificates[lane]) - baseline_set)
            ]
            for lane in ("ND", "DN")
        },
        "pairwise": pairwise,
        "certificate_sources": {
            ".".join(str(value) for value in key): list(row.lanes)
            for key, row in portfolio.certificates.items()
        },
        "aggregate_cost": {
            "crc_calls": sum(
                lane_reports[lane]["attempts"]["crc_calls"]
                for lane in LANE_ORDER),
            "bp_iterations": sum(
                lane_reports[lane]["attempts"]["bp_iterations"]
                for lane in LANE_ORDER),
        },
        "conflicts": [],
    }
    semantic = {
        "lanes": {
            lane: {
                "emission_digests": [
                    row["context_emission_digest"]
                    for row in sampling[lane]
                ],
                "prefix": [
                    {
                        "capture_id": row["capture_id"],
                        "certificates": row["certificates"],
                        "transaction": row["transaction"],
                    }
                    for row in prefixes[lane]
                ],
                "before_bp": lane_reports[lane]["before_bp"],
                "after_bp": lane_reports[lane]["after_bp"],
                "retry": lane_reports[lane]["retry"],
            }
            for lane in LANE_ORDER
        },
        "portfolio": {
            key: portfolio_report[key]
            for key in ("baseline_NN_DD", "all_four",
                        "gained_beyond_baseline", "conflicts")
        },
    }
    report = {
        "lanes": lane_reports,
        "portfolio": portfolio_report,
        "authoritative_digest": _sha256_json(semantic),
        "elapsed_s": time.monotonic() - started,
        "workers": workers,
        "semantics": {
            "capture_barrier": (
                "all four correlated lane emissions complete before any "
                "lane advances to the next physical capture"),
            "evidence": (
                "one vote per physical capture/cell inside each lane; "
                "no LLR values cross lanes"),
            "merge": "syndrome+CRC certificates only; conflicts are fatal",
        },
    }
    return BlindRun(report, certificates, sessions)


def _ground_truth_audit(
    blind: BlindRun,
    descriptor,
    rate_id: str,
) -> dict:
    # This is intentionally the only ground-truth open in this runner.
    # Every emission, decoder attempt, certificate and portfolio result is
    # already frozen in ``blind`` before this function is called.
    _field, gt_bits, _neighbors, reference = arms._load_ground_truth(
        descriptor)
    audits = {}
    emitted = {}
    for lane in LANE_ORDER:
        certs = blind.certificates[lane]
        wrong = arms._wrong_certificates(
            certs, descriptor, gt_bits, rate_id)
        audits[lane] = {
            "certificates": len(certs),
            "wrong_count": len(wrong),
            "wrong_tiles": [list(key) for key in wrong],
        }
        total = wrong_cells = 0
        for record in blind.sessions[lane].scans:
            for page, vector in record.emission.pages.items():
                if page != 0:
                    raise ValueError(
                        "frozen E018 ground truth covers page 0 only")
                index = np.asarray(vector["index"], np.int64)
                hard = (np.asarray(vector["llr"]) > 0.0).astype(np.uint8)
                total += int(index.size)
                wrong_cells += int(np.count_nonzero(
                    hard != gt_bits[index]))
        emitted[lane] = {
            "cells": total,
            "wrong": wrong_cells,
            "ber": wrong_cells / total if total else None,
        }
    return {
        "sha256": reference["sha256"],
        "loaded_after_all_blind_outputs": True,
        "certificate_audits": audits,
        "all_certificates_correct": all(
            row["wrong_count"] == 0 for row in audits.values()),
        "emitted_payload": emitted,
    }


def _summary_matches(observed: dict, expected: dict) -> bool:
    return all(observed.get(key) == value for key, value in expected.items())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--native", type=Path, default=arms.FOOTINGS["native"]["path"])
    parser.add_argument(
        "--decimated", type=Path,
        default=arms.FOOTINGS["decimated"]["path"])
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument(
        "--limit-captures", type=int,
        help="development-only prefix; full qualification uses all captures")
    parser.add_argument("--out", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    if args.limit_captures is not None and args.limit_captures <= 0:
        parser.error("--limit-captures must be positive")
    started = time.monotonic()

    print("Load byte-pinned E023b geometry inventories", flush=True)
    descriptor, native = _load_footing("native", args.native)
    descriptor2, decimated = _load_footing("decimated", args.decimated)
    if descriptor2.format_id != descriptor.format_id:
        raise ValueError("native and decimated format identities differ")
    if (native.pages, native.rate_id) != (
            decimated.pages, decimated.rate_id):
        raise ValueError("native and decimated decode envelopes differ")
    footings = {"native": native, "decimated": decimated}
    pairs = _pair_footings(native, decimated, args.limit_captures)
    full = len(pairs) == len(native.scans) == len(decimated.scans)

    preflight = _source_preflight(pairs)
    blind = _run_blind(
        pairs, descriptor, footings, workers=args.workers)
    ground_truth = _ground_truth_audit(
        blind, descriptor, native.rate_id)

    lanes = blind.report["lanes"]
    portfolio = blind.report["portfolio"]
    same_view_exact = all(
        row["same_view_pava_rows_exact"] is True
        and row["same_view_pava_emission_exact"] is True
        for lane in ("NN", "DD")
        for row in lanes[lane]["sampling"]
    )
    gates = {
        "complete_state_sha256_pins": True,
        "source_files_match_frozen_identities": (
            preflight["totals"]["all_sources_match_frozen_identity"]),
        "all_external_box3_pixels_exact": (
            preflight["totals"]["all_box3_pixels_exact"]),
        "physical_capture_pairing": True,
        "same_view_live_pava_exact_to_frozen": same_view_exact,
        "all_transferred_authoritative_cores_in_bounds": all(
            row["bounds"]["out_of_bounds"] == 0
            for lane in LANE_ORDER
            for row in lanes[lane]["sampling"]),
        "no_cross_lane_llr_merge": True,
        "no_certificate_conflicts": (
            not portfolio["conflicts"]),
        "ground_truth_loaded_after_blind_outputs": (
            ground_truth["loaded_after_all_blind_outputs"]),
        "all_certificates_ground_truth_correct": (
            ground_truth["all_certificates_correct"]),
    }
    if full:
        gates.update({
            "DD_frozen_anchor_exact": _summary_matches(
                lanes["DD"]["after_bp"], EXPECTED_FINAL["DD"]),
            "NN_frozen_anchor_exact": _summary_matches(
                lanes["NN"]["after_bp"], EXPECTED_FINAL["NN"]),
            "NN_DD_union_frozen_anchor_exact": _summary_matches(
                portfolio["baseline_NN_DD"],
                EXPECTED_FINAL["baseline_union"]),
        })
    gates_ok = all(value is True for value in gates.values())
    report = {
        "experiment": "e023c-scale-space-factorial-v1",
        "status": (
            "QUALIFIED" if full and gates_ok
            else "DEVELOPMENT_PREFIX" if not full and gates_ok
            else "FAILED"),
        "qualification_only": True,
        "production_entrypoint_built": False,
        "boundary": "LDPC and below; no fountain/rank/stop condition",
        "capture_count": len(pairs),
        "full_capture_set": full,
        "execution": blind.report,
        "preflight": preflight,
        "ground_truth": ground_truth,
        "gates": gates,
        "gates_ok": gates_ok,
        "implementation": {
            "qualifier_sha256": arms._stream_sha256(
                Path(__file__).resolve()),
            "scale_space_sha256": arms._stream_sha256(
                HERE / "scale_space.py"),
            "design_sha256": arms._stream_sha256(HERE / "README.md"),
            "payloaddec_sha256": arms._stream_sha256(
                Path(payloaddec.__file__).resolve()),
            "receiver_sha256": arms._stream_sha256(
                Path(receiver.__file__).resolve()),
            "arms_qualifier_sha256": arms._stream_sha256(
                E023B / "qualify_e023b_arms.py"),
            "multiview_qualifier_sha256": arms._stream_sha256(
                E023B / "qualify_e023b_multiview.py"),
        },
        "inputs": {
            "native_state": {
                "path": str(args.native),
                **native.reference,
            },
            "decimated_state": {
                "path": str(args.decimated),
                **decimated.reference,
            },
        },
        "elapsed_s": time.monotonic() - started,
    }
    _write_json_atomic(args.out, report)
    print(
        f"\nE023c {report['status']}: "
        f"NN={lanes['NN']['after_bp']['count']} "
        f"DD={lanes['DD']['after_bp']['count']} "
        f"ND={lanes['ND']['after_bp']['count']} "
        f"DN={lanes['DN']['after_bp']['count']} "
        f"baseline={portfolio['baseline_NN_DD']['count']} "
        f"all4={portfolio['all_four']['count']} "
        f"new={portfolio['gained_beyond_baseline']['count']} "
        f"digest={blind.report['authoritative_digest'][:16]} "
        f"-> {args.out}",
        flush=True)
    return 0 if gates_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
