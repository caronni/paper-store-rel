#!/usr/bin/env python
"""Compare final-only BP retry with retry after every acquisition prefix.

This is a qualification-only scheduling experiment.  It reuses the complete
file pins and raw-evidence reprofiling path from ``qualify_e023b_arms.py``;
production state loading and E023b processing are not relaxed or modified.

For each frozen footing and detector profile, the same ScanRecords are
appended to two fresh sessions:

* ``end_only`` receives one max-150 retry after all six scans;
* ``after_each_prefix`` receives max-150 retry after every appended scan,
  including the sixth.

Printed ground truth is opened only after all four footing/profile blind
schedules have been reduced to certificate snapshots.  It is used only to
audit CRC certificates, never to choose a schedule or decoder action.
"""
from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
QUALIFIER = HERE / "qualify_e023b_arms.py"


def _load_arms_qualifier():
    spec = importlib.util.spec_from_file_location(
        "e023b_arms_qualifier", QUALIFIER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {QUALIFIER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


q = _load_arms_qualifier()
payloaddec = q.payloaddec
receiver = q.receiver

PROFILE_ORDER = (
    payloaddec.DETECTOR_PAVA_V1,
    payloaddec.DETECTOR_CTX_PAVA_V1,
)
DEFAULT_OUT = HERE / "bp_schedule_report.json"

# Frozen after the first blind scheduling run and before this reproducer was
# promoted.  These gates make numerical or scheduling drift fail closed.
EXPECTED_ROWS = {
    "decimated": {
        payloaddec.DETECTOR_PAVA_V1: {
            "end_only": (747, 1127, 63417),
            "after_each_prefix": (748, 1270, 108459),
            "delta": (1, 143, 45042),
            "after_each_only": ((0, 28, 11),),
            "end_hashes": (
                "1e2942ccd447efb7d7bd1d06f1bc053cdea0018640cc73967d22945ad695d01f",
                "bae1bb90e23a1ce8cfa422edbd343aa1f4fe2ab2b6e0d93d5ed13dd2e9c5ec19",
            ),
            "after_hashes": (
                "ae8fe0b91c062799baa8a2537af5e182b9ee678c9abce186aed0a40c426bcebc",
                "d2121aaa1cd46b246ff68f8257bfbb9edeb7d6f427a554b9ff3c8baf4fabd2be",
            ),
        },
        payloaddec.DETECTOR_CTX_PAVA_V1: {
            "end_only": (757, 1101, 57544),
            "after_each_prefix": (757, 1241, 101340),
            "delta": (0, 140, 43796),
            "after_each_only": (),
            "end_hashes": (
                "6f4a786aa48c6a6342a5c9550a7f3f4d5a9c9b5bdbbbbb3633f22d5bc5bab103",
                "d04d51fef4cf2dca8424b294cbc0d464ec640d495400ac702a2068b5561e12cd",
            ),
            "after_hashes": (
                "6f4a786aa48c6a6342a5c9550a7f3f4d5a9c9b5bdbbbbb3633f22d5bc5bab103",
                "d04d51fef4cf2dca8424b294cbc0d464ec640d495400ac702a2068b5561e12cd",
            ),
        },
    },
    "native": {
        payloaddec.DETECTOR_PAVA_V1: {
            "end_only": (747, 1151, 67418),
            "after_each_prefix": (747, 1308, 117217),
            "delta": (0, 157, 49799),
            "after_each_only": (),
            "end_hashes": (
                "bea751cd47a6be3c54fd0787f58632c82c5cbcdc8c6c912d137fa18e22b77322",
                "64a3ec37b3ac3ef5077e0ca303d8428be6fa952442da5975f4cfe6cbf6ca8f53",
            ),
            "after_hashes": (
                "bea751cd47a6be3c54fd0787f58632c82c5cbcdc8c6c912d137fa18e22b77322",
                "64a3ec37b3ac3ef5077e0ca303d8428be6fa952442da5975f4cfe6cbf6ca8f53",
            ),
        },
        payloaddec.DETECTOR_CTX_PAVA_V1: {
            "end_only": (752, 1125, 62246),
            "after_each_prefix": (752, 1274, 109222),
            "delta": (0, 149, 46976),
            "after_each_only": (),
            "end_hashes": (
                "4a6435c91064865ca9bb9444d817ac801b77f83b7545272b5aa2d3402f875ef6",
                "c2154b32c5ba07563d42c22780c6740dd3da9ce7be8b2a3dbd40cf985516fa5d",
            ),
            "after_hashes": (
                "4a6435c91064865ca9bb9444d817ac801b77f83b7545272b5aa2d3402f875ef6",
                "c2154b32c5ba07563d42c22780c6740dd3da9ce7be8b2a3dbd40cf985516fa5d",
            ),
        },
    },
}
EXPECTED_DUAL_CONTEXT_UNION = 769
EXPECTED_DUAL_CONTEXT_HASHES = (
    "a910cce60403edd5f01a31a30aa4cf4226a78e29ecde246c59086524b65125b5",
    "2c462b6e9fda47c77e25b903bb1fc760a750a456c561932fa33bb285aa76e444",
)


def _keys(values) -> list[list[int]]:
    return [list(key) for key in sorted(values)]


def _compact(session) -> tuple[dict, dict]:
    session.validate_invariants()
    certs = q._certificate_snapshot(session)
    metrics = q._attempt_metrics(session)
    retry = metrics["by_stage"].get("retry150", {
        "ledger_records": 0,
        "crc_calls": 0,
        "bp_iterations": 0,
        "certified_new": 0,
    })
    return certs, {
        "certified": len(certs),
        "certificate_set_sha256": q._certificate_set_digest(certs),
        "certificate_bits_sha256": q._certificate_bits_digest(certs),
        "tile_states": q._state_counts(session),
        "ledger_records": metrics["ledger_records"],
        "crc_calls": metrics["crc_calls"],
        "bp_iterations": metrics["bp_iterations"],
        "retry_stage": retry,
        "fatal": list(session.decode.fatal),
    }


def _fresh_session(legacy, descriptor, profile):
    return receiver.ReceiverSession.create(
        descriptor, legacy.envelope.pages, legacy.envelope.dpi,
        rate_id=legacy.envelope.rate_id,
        detector_profile=profile,
        search_config=legacy.envelope.search_config)


def _blind_schedule(legacy, descriptor, profile) -> dict:
    end_only = _fresh_session(legacy, descriptor, profile)
    after_each = _fresh_session(legacy, descriptor, profile)
    prefixes: list[dict] = []

    for scan_index, old_record in enumerate(legacy.scans):
        record, _replay, _baseline_exact, _nonadopted_exact = (
            q._profile_record(old_record, descriptor, profile))
        end_only, _end_counts = receiver.apply_scan(end_only, record)
        after_each, append_counts = receiver.apply_scan(after_each, record)
        before_certs, before = _compact(after_each)
        after_each, retry_counts = receiver.retry_failed_bp(after_each)
        after_certs, after = _compact(after_each)
        prefixes.append({
            "scan_index": scan_index,
            "scan_id": record.scan_id,
            "append": append_counts,
            "retry": retry_counts,
            "before_retry_certified": before["certified"],
            "after_retry_certified": after["certified"],
            "retry_gained": _keys(set(after_certs) - set(before_certs)),
            "retry_changed": _keys(q._changed_certificates(
                before_certs, after_certs)),
            "cumulative_crc_calls": after["crc_calls"],
            "cumulative_bp_iterations": after["bp_iterations"],
        })
        print(
            f"    {record.scan_id}: retry "
            f"{before['certified']} -> {after['certified']} "
            f"(calls={after['crc_calls']}, "
            f"iters={after['bp_iterations']})",
            flush=True)

    end_before_certs, end_before = _compact(end_only)
    end_only, end_retry = receiver.retry_failed_bp(end_only)
    end_certs, end = _compact(end_only)
    each_certs, each = _compact(after_each)

    repeated, repeat_counts = receiver.retry_failed_bp(after_each)
    if (receiver.authoritative_digest(repeated)
            != receiver.authoritative_digest(after_each)):
        raise ValueError("repeating the final prefix retry changed state")

    end_keys = set(end_certs)
    for row in prefixes:
        gained = {tuple(key) for key in row["retry_gained"]}
        row["retry_gained_absent_from_end_only_final"] = _keys(
            gained - end_keys)

    return {
        "_end_certs": end_certs,
        "_each_certs": each_certs,
        "prefixes": prefixes,
        "end_only_before_retry": end_before,
        "end_only_retry": end_retry,
        "end_only": end,
        "after_each_prefix": each,
        "after_each_final_repeat": repeat_counts,
        "comparison": {
            "certificate_delta": len(each_certs) - len(end_certs),
            "crc_call_delta": each["crc_calls"] - end["crc_calls"],
            "bp_iteration_delta": (
                each["bp_iterations"] - end["bp_iterations"]),
            "after_each_only": _keys(set(each_certs) - set(end_certs)),
            "end_only_only": _keys(set(end_certs) - set(each_certs)),
            "changed_common": _keys(q._changed_certificates(
                end_certs, each_certs)),
        },
    }


def _audit_ground_truth(result: dict, descriptor, gt_bits,
                        rate_id: str) -> None:
    end_certs = result["_end_certs"]
    each_certs = result["_each_certs"]
    result["comparison"].update({
        "end_only_wrong": _keys(q._wrong_certificates(
            end_certs, descriptor, gt_bits, rate_id)),
        "after_each_wrong": _keys(q._wrong_certificates(
            each_certs, descriptor, gt_bits, rate_id)),
    })


def _certificate_union(results: dict, schedule: str,
                       profile: str) -> dict:
    union: dict = {}
    conflicts: set = set()
    for footing in sorted(results):
        current = results[footing]["profiles"][profile][
            f"_{schedule}_certs"]
        for key, bits in current.items():
            if key in union and union[key] != bits:
                conflicts.add(key)
            else:
                union[key] = bits
    return {"certs": union, "conflicts": conflicts}


def _strip_private(value):
    if isinstance(value, dict):
        return {
            key: _strip_private(child)
            for key, child in value.items()
            if not key.startswith("_")
        }
    if isinstance(value, list):
        return [_strip_private(child) for child in value]
    return value


def _implementation_hashes() -> dict:
    paths = {
        "schedule_qualifier": Path(__file__).resolve(),
        "arms_qualifier": QUALIFIER,
        "receiver": q.ROOT / "src/paperholo/receiver.py",
        "payloaddec": q.ROOT / "src/paperholo/payloaddec.py",
    }
    return {
        name: {
            "path": str(path.relative_to(q.ROOT)),
            "sha256": q._stream_sha256(path),
        }
        for name, path in paths.items()
    }


def _frozen_gates(report: dict) -> dict:
    row_gates = {}
    for footing, profiles in EXPECTED_ROWS.items():
        for profile, expected in profiles.items():
            row = report["footings"][footing]["profiles"][profile]
            end = row["end_only"]
            each = row["after_each_prefix"]
            comparison = row["comparison"]
            actual = {
                "end_only": (
                    end["certified"], end["crc_calls"],
                    end["bp_iterations"]),
                "after_each_prefix": (
                    each["certified"], each["crc_calls"],
                    each["bp_iterations"]),
                "delta": (
                    comparison["certificate_delta"],
                    comparison["crc_call_delta"],
                    comparison["bp_iteration_delta"]),
                "after_each_only": tuple(
                    tuple(key) for key in comparison["after_each_only"]),
                "end_hashes": (
                    end["certificate_set_sha256"],
                    end["certificate_bits_sha256"]),
                "after_hashes": (
                    each["certificate_set_sha256"],
                    each["certificate_bits_sha256"]),
            }
            row_gates[f"{footing}/{profile}"] = {
                "exact_counts_and_costs": all(
                    actual[name] == expected[name]
                    for name in (
                        "end_only", "after_each_prefix", "delta")),
                "exact_set_gain": (
                    actual["after_each_only"]
                    == expected["after_each_only"]),
                "exact_end_certificate_hashes": (
                    actual["end_hashes"] == expected["end_hashes"]),
                "exact_after_each_certificate_hashes": (
                    actual["after_hashes"] == expected["after_hashes"]),
                "no_end_only_only": not comparison["end_only_only"],
                "no_changed_common": not comparison["changed_common"],
                "all_certificates_gt_correct": (
                    not comparison["end_only_wrong"]
                    and not comparison["after_each_wrong"]),
                "no_fatal": not end["fatal"] and not each["fatal"],
                "repeat_is_noop": bool(
                    row["after_each_final_repeat"]["noop"]
                    and row["after_each_final_repeat"]["eligible"] == 0
                    and row["after_each_final_repeat"]["attempted"] == 0),
            }

    dual = report["dual_footing_context_union"]
    dual_gates = {
        "exact_count": (
            dual["end_only_count"] == EXPECTED_DUAL_CONTEXT_UNION
            and dual["after_each_prefix_count"]
            == EXPECTED_DUAL_CONTEXT_UNION),
        "no_schedule_set_difference": (
            not dual["after_each_only"] and not dual["end_only_only"]),
        "no_changed_common": not dual["changed_common"],
        "no_cross_footing_conflicts": all(
            not rows for rows in
            dual["within_schedule_cross_footing_conflicts"].values()),
        "exact_end_certificate_hashes": (
            (dual["end_only_set_sha256"],
             dual["end_only_bits_sha256"])
            == EXPECTED_DUAL_CONTEXT_HASHES),
        "exact_after_each_certificate_hashes": (
            (dual["after_each_prefix_set_sha256"],
             dual["after_each_prefix_bits_sha256"])
            == EXPECTED_DUAL_CONTEXT_HASHES),
    }
    ground_truth_gate = (
        report["ground_truth"][
            "loaded_after_all_blind_schedules"] is True)
    flat = [
        value
        for row in row_gates.values()
        for value in row.values()
    ] + list(dual_gates.values()) + [ground_truth_gate]
    return {
        "rows": row_gates,
        "dual_footing_context_union": dual_gates,
        "ground_truth_loaded_after_all_blind_schedules": (
            ground_truth_gate),
        "gates_ok": all(value is True for value in flat),
    }


def run() -> dict:
    results: dict = {}
    audit_metadata: dict = {}

    # Blind phase: finish every schedule for every footing before any call
    # that can open the qualification-only printed field.
    for footing, config in q.FOOTINGS.items():
        print(f"=== {footing} ===", flush=True)
        legacy, reference = q._load_frozen_session(
            config["path"], config["sha256"])
        descriptor = q._descriptor(legacy.envelope.format_id)
        profiles = {}
        for profile in PROFILE_ORDER:
            print(f"  {profile}", flush=True)
            profiles[profile] = _blind_schedule(
                legacy, descriptor, profile)
            gc.collect()

        results[footing] = {
            "reference": {
                "state_file": Path(reference["path"]).name,
                "state_sha256": reference["sha256"],
                "legacy_implementation_sha256": (
                    reference["legacy_implementation_sha256"]),
            },
            "profiles": profiles,
        }
        audit_metadata[footing] = (
            descriptor, legacy.envelope.rate_id)
        del legacy
        gc.collect()

    if set(results) != set(q.FOOTINGS):
        raise ValueError("ground-truth boundary reached before all footings")

    # Observer-only phase: all eight blind outputs now exist as compact
    # certificate snapshots.  Both frozen footings share one format and GT.
    descriptors = [row[0] for row in audit_metadata.values()]
    descriptor_ids = {
        (row.format_id, row.seed, row.cell_dots,
         tuple(row.spec().page_cells_yx))
        for row in descriptors
    }
    if len(descriptor_ids) != 1:
        raise ValueError("frozen footings do not share one GT descriptor")
    _field, gt_bits, _neighbors, gt_reference = q._load_ground_truth(
        descriptors[0])
    for footing, (descriptor, rate_id) in audit_metadata.items():
        for profile in PROFILE_ORDER:
            _audit_ground_truth(
                results[footing]["profiles"][profile],
                descriptor, gt_bits, rate_id)
    ground_truth = {
        "file": Path(gt_reference["path"]).name,
        "sha256": gt_reference["sha256"],
        "loaded_after_all_blind_schedules": True,
    }
    del gt_bits

    end_union = _certificate_union(
        results, "end", payloaddec.DETECTOR_CTX_PAVA_V1)
    each_union = _certificate_union(
        results, "each", payloaddec.DETECTOR_CTX_PAVA_V1)
    dual = {
        "profile": payloaddec.DETECTOR_CTX_PAVA_V1,
        "end_only_count": len(end_union["certs"]),
        "after_each_prefix_count": len(each_union["certs"]),
        "end_only_set_sha256": q._certificate_set_digest(
            end_union["certs"]),
        "end_only_bits_sha256": q._certificate_bits_digest(
            end_union["certs"]),
        "after_each_prefix_set_sha256": q._certificate_set_digest(
            each_union["certs"]),
        "after_each_prefix_bits_sha256": q._certificate_bits_digest(
            each_union["certs"]),
        "after_each_only": _keys(
            set(each_union["certs"]) - set(end_union["certs"])),
        "end_only_only": _keys(
            set(end_union["certs"]) - set(each_union["certs"])),
        "changed_common": _keys(q._changed_certificates(
            end_union["certs"], each_union["certs"])),
        "within_schedule_cross_footing_conflicts": {
            "end_only": _keys(end_union["conflicts"]),
            "after_each_prefix": _keys(each_union["conflicts"]),
        },
    }
    report = _strip_private({
        "experiment": "E023b BP scheduling: end-only vs every prefix",
        "qualification_only": True,
        "profiles": list(PROFILE_ORDER),
        "implementation_sha256": _implementation_hashes(),
        "ground_truth": ground_truth,
        "method": {
            "scan_order": "frozen E023b.0 order s000 through s005",
            "end_only": "one max-150 retry after the sixth scan",
            "after_each_prefix": (
                "one max-150 retry after each appended scan, including s005"),
            "same_profiled_records": True,
            "ground_truth_is_observer_only": True,
            "ground_truth_boundary": (
                "all four footing/profile blind schedules complete before "
                "the printed field is opened"),
        },
        "footings": results,
        "dual_footing_context_union": dual,
    })
    report["frozen_expectations"] = {
        "rows": {
            footing: {
                profile: {
                    name: (
                        [list(key) for key in value]
                        if name == "after_each_only" else list(value))
                    for name, value in expected.items()
                }
                for profile, expected in profiles.items()
            }
            for footing, profiles in EXPECTED_ROWS.items()
        },
        "dual_footing_context_union": EXPECTED_DUAL_CONTEXT_UNION,
        "dual_footing_context_union_hashes": list(
            EXPECTED_DUAL_CONTEXT_HASHES),
    }
    gates = _frozen_gates(report)
    report["gates"] = {
        "rows": gates["rows"],
        "dual_footing_context_union": (
            gates["dual_footing_context_union"]),
        "ground_truth_loaded_after_all_blind_schedules": (
            gates["ground_truth_loaded_after_all_blind_schedules"]),
    }
    report["gates_ok"] = gates["gates_ok"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"compact JSON result (default: {DEFAULT_OUT.name})")
    args = parser.parse_args()
    report = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(
        f"WROTE {args.out} "
        f"({'PASS' if report['gates_ok'] else 'FAIL'})",
        flush=True)
    return 0 if report["gates_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
