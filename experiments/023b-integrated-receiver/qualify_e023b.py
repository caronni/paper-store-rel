#!/usr/bin/env python
"""Qualify E023b compatibility, append scheduling, and raw integration.

The compatibility and append-schedule gates replay immutable qualified E023
ScanEmissions, isolating orchestration from TIFF sampling.  The integrated
gate then checks E023b states produced from the original TIFFs against the
frozen E022/E023 artifacts before accepting their final LDPC outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, ldpc, payloaddec, pilotsearch, receiver  # noqa:E402
from paperholo.formats import FORMAT_REGISTRY  # noqa:E402


E022_BUILD = ROOT / "experiments/022-pilot-tile-search/build"
E023_BUILD = ROOT / "experiments/023-payload-tiles/build"
E018_GT = ROOT / "experiments/018-confetti-c3-play/build/e018_gt"
GT_SHA256 = "6c6f54b7a8dec9d5b5d4e75ce5a29af4323bb91da5eca50391cc5d5eebc5cc82"
DEFAULTS = {
    "decimated": {
        "e022": E022_BUILD / "session_state.pkl",
        "e023": E023_BUILD / "e023_decimated.pkl",
        "integrated": HERE / "build/e023b_decimated.pkl",
        "compat_certified": 741, "compat_attempts": 1024,
        "e022_sha256": "e31fe62814d6edd8f488df2d557929a44ae44fe430e8aaada6659a16ff121e36",
        "e023_sha256": "0105617629696ca579841b1e1991b749a05a20bc4301128b9ab62930304992bc",
        "compat_bits_sha256": "536d49123f04d4d7d9a3873b36305c7d35ee179ad33e0528b6f9e1da31941502",
        "production_certified": 742, "production_attempts": 1076,
        "production_bits_sha256": (
            "583b4578816472c5010d3611d052b2e2848153c49a036a011d73903978e7c406"),
        "prefix": ((179, 236), (202, 338), (333, 499),
                   (337, 536), (730, 1000), (742, 1076)),
        "production_states": {
            "certified": 742, "attempted_failed": 51,
            "below_attempt_floor": 12, "degenerate": 35},
        "extras": {(0, 16, 18)},
    },
    "native": {
        "e022": E022_BUILD / "session_native.pkl",
        "e023": E023_BUILD / "e023_native.pkl",
        "integrated": HERE / "build/e023b_native.pkl",
        "compat_certified": 740, "compat_attempts": 1037,
        "e022_sha256": "35d89375999b13bd518880d0fae40247ed8606f5a35fd32998dbf1522b2966a0",
        "e023_sha256": "1dd30993221171c0f27cfddb3b6d605b0ce0add3e634c1f7ee37590041ae43b8",
        "compat_bits_sha256": "b1044813536a57a55a8b031bea3171ca51a7241fe07ec67df956208be9151285",
        "production_certified": 742, "production_attempts": 1098,
        "production_bits_sha256": (
            "de42262cfd029762a65c21ee59263cb90e9a32218bff4635cea50b7aa3f14f1b"),
        "prefix": ((178, 238), (198, 348), (321, 513),
                   (332, 561), (721, 1030), (742, 1098)),
        "production_states": {
            "certified": 742, "attempted_failed": 53,
            "below_attempt_floor": 10, "degenerate": 35},
        "extras": {(0, 8, 1), (0, 8, 2)},
    },
}


def _descriptor(format_id: str):
    return next(row for row in FORMAT_REGISTRY if row.format_id == format_id)


def _gt_payload_bits(descriptor) -> np.ndarray:
    spec = descriptor.spec()
    dots = np.load(E018_GT / "K__e018_field.npy")
    field = dots[::spec.cell_dots, ::spec.cell_dots].astype(np.uint8)
    if field.shape != tuple(spec.page_cells_yx):
        raise ValueError("frozen GT geometry mismatch")
    pim = compose.payload_index_map(spec, descriptor.seed)
    cells = np.argwhere(pim >= 0)
    order = np.argsort(pim[cells[:, 0], cells[:, 1]], kind="stable")
    cells = cells[order]
    ks = compose.payload_keystream(spec, descriptor.seed, 0)
    return (field[cells[:, 0], cells[:, 1]]
            ^ ks[cells[:, 0], cells[:, 1]]).astype(np.uint8)


def _certificates(decode: payloaddec.DecodeState) -> dict[tuple, bytes]:
    return {
        key: (int(out.user_bits.size), np.packbits(out.user_bits).tobytes())
        for key, out in decode.tiles.items()
        if out.state == "certified" and out.user_bits is not None
    }


def _certified_bit_set_digest(decode: payloaddec.DecodeState) -> str:
    digest = hashlib.sha256()
    for key, outcome in sorted(decode.tiles.items()):
        if outcome.state != "certified":
            continue
        assert outcome.user_bits is not None
        digest.update(repr(key).encode())
        digest.update(str(outcome.user_bits.size).encode())
        digest.update(np.packbits(outcome.user_bits).tobytes())
    return digest.hexdigest()


def _wrong_certifications(decode, gt_bits) -> list[tuple]:
    wrong = []
    for key, out in decode.tiles.items():
        if out.state != "certified":
            continue
        pidx, tx_bits = decode.certified_payload_indices(out)
        if not np.array_equal(tx_bits, gt_bits[pidx]):
            wrong.append(key)
    return sorted(wrong)


def _state_counts(decode) -> dict[str, int]:
    out = {}
    for state in payloaddec.full_tile_states(decode).values():
        out[state] = out.get(state, 0) + 1
    return out


def _compat_replay(old: payloaddec.DecodeState, descriptor,
                   pages: tuple[int, ...]) -> payloaddec.DecodeState:
    state = payloaddec.DecodeState(
        descriptor, old.rate_id, pages, old.upstream)
    for emission in old.scans:
        state.ingest_scan(emission)
    state.decode_union()
    state.divergence_pass()
    return state


def _dummy_survey(region_count: int, c_dots, pitch) -> receiver.PackedSurvey:
    rows = tuple(receiver.PackedRegion(
        bbox=(0, 0, 0, 0), mask_shape=(0, 0),
        mask_bits=np.zeros(0, np.uint8), area_mm2=0.0,
        angle_hint_deg=None, score=0.0) for _ in range(region_count))
    return receiver.PackedSurvey(
        regions=rows, c_dots=c_dots, cell_pitch_px=pitch,
        pitch_votes=(), diagnostics={"qualification_replay": True})


def _replay_record(row: dict, emission: payloaddec.ScanEmission,
                   descriptor, rate_id: str,
                   capture_id: str | None = None) -> receiver.ScanRecord:
    result = row["result"]
    placement_ids = receiver.placement_ids_for_result(
        row["source_sha256"], result)
    return receiver.ScanRecord(
        scan_id=row["scan_id"], source_path=row["source_path"],
        source_sha256=row["source_sha256"],
        source_size=int(row.get("source_size", 0)), dpi=float(row["dpi"]),
        image_shape=(0, 0), image_dtype="qualification-replay",
        capture_id=(row["source_sha256"] if capture_id is None
                    else capture_id),
        survey=_dummy_survey(
            int(row.get("region_count", 0)), row.get("c_dots"),
            row.get("cell_pitch_px")),
        result=result, placement_ids=placement_ids,
        work_plan=receiver.build_work_plan(
            result, placement_ids, descriptor.spec(), descriptor.seed,
            ldpc.LDPC_LADDER[rate_id]),
        detector_profile=payloaddec.DETECTOR_PAVA_V1,
        window_evidence=(), context_fits=(), emission=emission,
        tile_evidence_digests=receiver.tile_evidence_digests(
            emission, descriptor.spec(), descriptor.seed),
        timings={"qualification_replay": True})


def _production_replay(e022_payload: dict, old, descriptor, *,
                       capture_ids: tuple[str, ...] | None = None
                       ) -> tuple[
                           receiver.ReceiverSession,
                           tuple[tuple[int, int], ...],
                       ]:
    session = receiver.ReceiverSession.create(
        descriptor, tuple(e022_payload["pages"]), float(e022_payload["dpi"]),
        rate_id=old.rate_id)
    prefix = []
    if capture_ids is None:
        capture_ids = tuple(row["source_sha256"]
                            for row in e022_payload["scans"])
    for row, emission, capture_id in zip(
            e022_payload["scans"], old.scans, capture_ids, strict=True):
        session, _counts = receiver.replay_frozen_scan_for_qualification(
            session, _replay_record(
                row, emission, descriptor, old.rate_id, capture_id))
        prefix.append((len(_certificates(session.decode)),
                       session.decode.n_attempts))
    return session, tuple(prefix)


def _clean(value):
    """Canonical timing-free structure for E022 parity."""
    if isinstance(value, np.ndarray):
        return (str(value.dtype), tuple(value.shape), value.tobytes())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return tuple((key, _clean(row)) for key, row in sorted(value.items())
                     if key not in {"elapsed_s", "bch_elapsed_s"}
                     and not str(key).endswith("_s"))
    if isinstance(value, (list, tuple)):
        return tuple(_clean(row) for row in value)
    if is_dataclass(value):
        return tuple((row.name, _clean(getattr(value, row.name)))
                     for row in fields(value)
                     if row.name != "timings" and not row.name.endswith("_s"))
    return value


def _decode_snapshot(decode: payloaddec.DecodeState) -> tuple:
    tiles = tuple((key, _clean(outcome))
                  for key, outcome in sorted(decode.tiles.items()))
    return (decode.format_id, decode.seed, decode.rate_id, decode.pages,
            decode.upstream, decode.n_attempts, tuple(decode.fatal), tiles)


def _attempt_snapshot(session: receiver.ReceiverSession) -> tuple:
    return tuple(_clean(row) for row in session.attempts)


def _result_snapshot(result: pilotsearch.SearchResult) -> tuple:
    placements = []
    for row in result.placements:
        placements.append((
            row.region_index, (row.window.y, row.window.x, row.window.h,
                               row.window.w, row.window.support,
                               row.window.depth),
            row.page, row.origin_yx, row.rot_k, row.method, row.mismatch,
            row.validation_mismatch, row.rival_mismatch, row.support,
            row.pose.origin_yx, row.pose.jacobian_yx, row.pose.angle_deg,
            row.pose.pitch_px, row.pose.phase_yx, row.pose.footing_factor,
            row.component, row.rival_searched,
            row.predicted_residual_cells, row.bch_errors, row.scan_id,
            row.redundant, _clean(row.diagnostics),
            _clean(row.page_cells_yx)))
    tiles = []
    for key, tile in sorted(result.tiles.items()):
        observations = tuple(
            (site, tuple((row.region_index, row.window_yx, row.scan_yx,
                          row.bit, row.expected, row.weight, row.method,
                          row.scan_id) for row in values))
            for site, values in sorted(tile.observations.items()))
        tiles.append((
            key, _clean(tile.expected_bits), observations, tile.bch_ok,
            tile.bch_attempted, tile.bch_refused, tile.bch_errors,
            tile.bch_erasures))
    return (tuple(placements), tuple(tiles),
            tuple(sorted(result.region_states.items())),
            _clean(result.diagnostics))


def _emission_exact(a: payloaddec.ScanEmission,
                    b: payloaddec.ScanEmission) -> bool:
    if (a.scan_id != b.scan_id or a.source_sha256 != b.source_sha256
            or a.window_rows != b.window_rows
            or set(a.pages) != set(b.pages)):
        return False
    return all(np.array_equal(a.pages[page][key], b.pages[page][key])
               for page in a.pages for key in ("index", "llr", "owner"))


def _record_derivations_exact(
    record: receiver.ScanRecord,
    integrated: receiver.ReceiverSession,
) -> bool:
    placement_ids = receiver.placement_ids_for_result(
        record.source_sha256, record.result)
    if record.placement_ids != placement_ids:
        return False
    work = receiver.build_work_plan(
        record.result, placement_ids, integrated.decode.spec,
        integrated.decode.seed, integrated.decode.ldpc_spec)
    if record.work_plan != work:
        return False
    digests = receiver.tile_evidence_digests(
        record.emission, integrated.decode.spec, integrated.decode.seed)
    if record.tile_evidence_digests != digests:
        return False
    if len(record.window_evidence) != len(record.result.placements):
        return False
    scan = payloaddec.E022Scan(
        record.scan_id, record.source_path, record.source_sha256,
        record.dpi, record.result)
    frozen = payloaddec.freeze_scan_emission(
        scan, list(record.window_evidence), integrated.decode.spec)
    return _emission_exact(frozen, record.emission)


def _raw_record_exact(record: receiver.ScanRecord) -> bool:
    """Reject reduced replay fixtures and bind the state to actual input."""
    path = Path(record.source_path)
    if (not path.is_file() or record.image_shape == (0, 0)
            or record.image_dtype == "qualification-replay"
            or record.survey.diagnostics.get("qualification_replay")):
        return False
    if receiver.file_identity(path) != (
            record.source_sha256, record.source_size):
        return False
    image = receiver.load_image(path)
    if (tuple(image.shape[:2]) != record.image_shape
            or str(np.asarray(image).dtype) != record.image_dtype):
        return False
    for region in record.survey.regions:
        _y, _x, height, width = region.bbox
        if (region.mask_shape != (height, width)
                or region.mask_bits.size * 8 < height * width
                or not region.unpack().mask.any()):
            return False
    return True


def _integrated_check(path: Path, e022_payload: dict,
                      old: payloaddec.DecodeState,
                      descriptor) -> dict:
    if not path.exists():
        return {"ok": False, "error": f"missing integrated state {path}"}
    try:
        integrated = receiver.load_session(path)
        integrated.validate(
            descriptor, tuple(e022_payload["pages"]),
            float(e022_payload["dpi"]), rate_id=old.rate_id)
    except (ValueError, pickle.UnpicklingError, EOFError) as exc:
        return {"ok": False, "error": f"invalid integrated state: {exc}"}
    scans_ok = len(integrated.scans) == len(e022_payload["scans"])
    e021_summary_ok = scans_ok
    e022_exact = scans_ok
    emission_exact = scans_ok
    raw_records_exact = scans_ok
    derivations_exact = scans_ok
    if scans_ok:
        for got, frozen, old_emission in zip(
                integrated.scans, e022_payload["scans"], old.scans,
                strict=True):
            scans_ok &= (got.scan_id == frozen["scan_id"]
                         and got.source_sha256 == frozen["source_sha256"]
                         and got.source_size == frozen["source_size"]
                         and got.dpi == frozen["dpi"])
            e021_summary_ok &= (
                got.region_count == int(frozen["region_count"])
                and got.survey.c_dots == frozen["c_dots"]
                and got.survey.cell_pitch_px == frozen["cell_pitch_px"]
                and sum(row.angle_hint_deg is not None
                        for row in got.survey.regions)
                == int(frozen["angle_hints"]))
            e022_exact &= (_result_snapshot(got.result)
                           == _result_snapshot(frozen["result"]))
            emission_exact &= _emission_exact(got.emission, old_emission)
            raw_records_exact &= _raw_record_exact(got)
            derivations_exact &= _record_derivations_exact(got, integrated)
    expected, _prefix = _production_replay(
        e022_payload, old, descriptor,
        capture_ids=tuple(scan.capture_id for scan in integrated.scans))
    decode_scans_exact = (
        len(integrated.decode.scans) == len(integrated.scans)
        and all(_emission_exact(got, scan.emission)
                for got, scan in zip(integrated.decode.scans,
                                     integrated.scans, strict=True)))
    production_exact = (
        _decode_snapshot(integrated.decode)
        == _decode_snapshot(expected.decode)
        and _attempt_snapshot(integrated) == _attempt_snapshot(expected)
        and integrated.attempt_ids == expected.attempt_ids
        and decode_scans_exact)
    return {
        "ok": bool(scans_ok and e021_summary_ok and e022_exact
                   and emission_exact and raw_records_exact
                   and derivations_exact and production_exact),
        "source_scans_exact": bool(scans_ok),
        "e021_summary_exact": bool(e021_summary_ok),
        "e022_result_exact_without_timings": bool(e022_exact),
        "scan_emissions_exact": bool(emission_exact),
        "raw_files_and_surveys_exact": bool(raw_records_exact),
        "stored_derivations_recompute_exactly": bool(derivations_exact),
        "decode_scans_exact": bool(decode_scans_exact),
        "attempt_ledger_exact": bool(
            _attempt_snapshot(integrated) == _attempt_snapshot(expected)
            and integrated.attempt_ids == expected.attempt_ids),
        "production_outcome_exact": bool(production_exact),
        "authoritative_sha256": receiver.authoritative_digest(integrated),
    }


def run_footing(name: str, config: dict, *, integrated_path: Path,
                replay_only: bool) -> dict:
    print(f"\n=== {name} ===", flush=True)
    e022_bytes = config["e022"].read_bytes()
    e023_bytes = config["e023"].read_bytes()
    e022_sha = hashlib.sha256(e022_bytes).hexdigest()
    e023_sha = hashlib.sha256(e023_bytes).hexdigest()
    gt_sha = hashlib.sha256(
        (E018_GT / "K__e018_field.npy").read_bytes()).hexdigest()
    references_ok = (
        e022_sha == config["e022_sha256"]
        and e023_sha == config["e023_sha256"]
        and gt_sha == GT_SHA256)
    print(f"references: {'PASS' if references_ok else 'FAIL'}")
    e022_payload = pickle.loads(e022_bytes)
    descriptor = _descriptor(e022_payload["format_id"])
    old = payloaddec.load_state(config["e023"], descriptor)
    gt = _gt_payload_bits(descriptor)

    compat = _compat_replay(old, descriptor, tuple(e022_payload["pages"]))
    compat_wrong = _wrong_certifications(compat, gt)
    compat_bits_sha = _certified_bit_set_digest(compat)
    compat_exact = (
        references_ok
        and _decode_snapshot(compat) == _decode_snapshot(old)
        and len(_certificates(compat)) == config["compat_certified"]
        and compat.n_attempts == config["compat_attempts"])
    compat_exact &= (
        compat_bits_sha == config["compat_bits_sha256"]
        and not compat_wrong)
    print(f"compat: {'PASS' if compat_exact else 'FAIL'} "
          f"cert={len(_certificates(compat))} calls={compat.n_attempts} "
          f"wrong={compat_wrong}")

    production, prefix = _production_replay(e022_payload, old, descriptor)
    cert = _certificates(production.decode)
    old_cert = _certificates(old)
    extras = set(cert) - set(old_cert)
    missing = set(old_cert) - set(cert)
    common_exact = not missing and all(
        cert[key] == old_cert[key] for key in old_cert)
    wrong = _wrong_certifications(production.decode, gt)
    states = _state_counts(production.decode)
    production_bits_sha = _certified_bit_set_digest(production.decode)
    production_ok = (
        references_ok
        and len(cert) == config["production_certified"]
        and production.decode.n_attempts == config["production_attempts"]
        and states == config["production_states"]
        and common_exact and extras == config["extras"] and not wrong
        and not missing and prefix == config["prefix"]
        and production_bits_sha == config["production_bits_sha256"])
    print(f"append: {'PASS' if production_ok else 'FAIL'} "
          f"cert={len(cert)} calls={production.decode.n_attempts} "
          f"extras={sorted(extras)} wrong={wrong}")

    integrated = ({"ok": False, "skipped": True} if replay_only else
                  _integrated_check(
                      integrated_path, e022_payload, old, descriptor))
    if not replay_only:
        print(f"raw integration: {'PASS' if integrated['ok'] else 'FAIL'}")
    return {
        "references": {
            "ok": references_ok, "e022_sha256": e022_sha,
            "e023_sha256": e023_sha, "ground_truth_sha256": gt_sha,
        },
        "compatibility": {
            "ok": compat_exact, "certified": len(_certificates(compat)),
            "attempts": compat.n_attempts,
            "certified_bits_sha256": compat_bits_sha,
            "wrong": [list(key) for key in compat_wrong],
        },
        "production": {
            "ok": production_ok, "certified": len(cert),
            "attempts": production.decode.n_attempts,
            "prefix_certified_attempts": [list(row) for row in prefix],
            "states": states, "extra_tiles": [list(key) for key in sorted(extras)],
            "missing_qualified_tiles": [list(key) for key in sorted(missing)],
            "wrong": [list(key) for key in wrong],
            "common_bits_exact": common_exact,
            "certified_bits_sha256": production_bits_sha,
            "crc_false_accept_budget": (
                production.decode.n_attempts * payloaddec.CRC_FALSE_ACCEPT),
        },
        "integrated": integrated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decimated", type=Path,
                        default=DEFAULTS["decimated"]["integrated"])
    parser.add_argument("--native", type=Path,
                        default=DEFAULTS["native"]["integrated"])
    parser.add_argument("--replay-only", action="store_true")
    parser.add_argument("--out", type=Path,
                        default=HERE / "build/qualify_report.json")
    args = parser.parse_args()
    report = {
        "experiment": "023b-integrated-receiver",
        "boundary": "LDPC and below; no fountain/stop condition",
        "decimated": run_footing(
            "decimated", DEFAULTS["decimated"],
            integrated_path=args.decimated, replay_only=args.replay_only),
        "native": run_footing(
            "native", DEFAULTS["native"],
            integrated_path=args.native, replay_only=args.replay_only),
    }
    report["replay_gates_ok"] = all(
        report[name][gate]["ok"] for name in ("decimated", "native")
        for gate in ("references", "compatibility", "production"))
    report["raw_gates_ok"] = all(
        report[name]["integrated"]["ok"]
        for name in ("decimated", "native"))
    report["gates_ok"] = bool(
        report["replay_gates_ok"] and report["raw_gates_ok"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.replay_only:
        verdict = ("REPLAY PASS (RAW INTEGRATION SKIPPED)"
                   if report["replay_gates_ok"] else "REPLAY FAIL")
        print(f"\nE023b {verdict} -> {args.out}")
        return 0 if report["replay_gates_ok"] else 1
    print(f"\nE023b QUALIFICATION "
          f"{'PASS' if report['gates_ok'] else 'FAIL'} -> {args.out}")
    return 0 if report["gates_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
