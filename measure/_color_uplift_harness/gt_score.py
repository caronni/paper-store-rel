"""Offline GT scorer: truth path FIRST, then errors, certs, and close.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.gt_score truth --capture xerox-c3-cmy7
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.gt_score state --capture hp-c3-cmy8
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.gt_score run --run <run.json>

TRUTH-PATH DISCIPLINE (mandatory, memory: truth-path-discipline).  Every
scoring mode first re-encodes the CERTIFIED tiles through the canonical
production leaf ``color_projection.project_certified_color_tile`` (K:
``records.printed_cells_from_record``) and requires exact agreement with
the emitted ground truth on the cells those certificates own.  Slot
raster is NOT codeword order and the GT packing is not the cell grid —
hand-rolled reconstructions drift, so nothing here rolls its own.  If the
truth path does not validate, the scorer REFUSES to report error numbers.

WRONG-CERT AUDIT (bar B5).  The same projection comparison run over every
certificate is the campaign's hard bar: a single certified cell that
disagrees with GT prints CAMPAIGN-STOP and exits non-zero.

GT layout (emit manifest): ``page000_gt.npy`` is packed bits, shape
``(3, cells_y*cell_dots, packed_x)`` for color (plane order C,M,Y) and
``(cells_y*cell_dots, packed_x)`` for K, bitorder big.  Cell blocks are
solid, so per-cell bits are the ``[::cell_dots, ::cell_dots]`` corner
samples and the physical state is ``C | M<<1 | Y<<2``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import corpus, state_cache
from .corpus import CaptureRow

TILE_CELLS = 64


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """Per-cell emitted page truth in the receiver's own cell grid."""

    key: str
    kind: str
    cell_bits: np.ndarray          # (3, cells_y, cells_x) or (cells_y, cells_x)
    cells_yx: tuple[int, int]
    array_sha256: str

    @property
    def states(self) -> np.ndarray:
        """Physical state ids ``C | M<<1 | Y<<2`` (color) or bits (K)."""
        if self.cell_bits.ndim == 2:
            return self.cell_bits
        return (self.cell_bits[0].astype(np.uint8)
                | (self.cell_bits[1].astype(np.uint8) << 1)
                | (self.cell_bits[2].astype(np.uint8) << 2))

    def tile_bits(self, ty: int, tx: int) -> np.ndarray:
        """One tile's GT as ``(64,64,3)`` (color) or ``(64,64)`` (K)."""
        y0, x0 = ty * TILE_CELLS, tx * TILE_CELLS
        if self.cell_bits.ndim == 2:
            return self.cell_bits[y0:y0 + TILE_CELLS, x0:x0 + TILE_CELLS]
        block = self.cell_bits[:, y0:y0 + TILE_CELLS, x0:x0 + TILE_CELLS]
        return np.ascontiguousarray(np.transpose(block, (1, 2, 0)))


def load_ground_truth(row: CaptureRow) -> GroundTruth:
    manifest = row.manifest()
    page = manifest["pages"][0]
    cell_dots = int(manifest["cell_dots"])
    cells_y, cells_x = (int(value) for value in manifest["page_cells_yx"])
    packed = np.load(row.gt_path())
    expected = tuple(int(value) for value in page["gt_packed_shape"])
    if tuple(packed.shape) != expected:
        raise SystemExit(
            f"{row.key}: GT shape {packed.shape} != manifest {expected}")
    array_sha = hashlib.sha256(packed.tobytes()).hexdigest()
    if array_sha != page["gt_sha256"]:
        raise SystemExit(
            f"{row.key}: GT array sha {array_sha[:16]}… != manifest "
            f"{page['gt_sha256'][:16]}…")
    if page["gt_bitorder"] != "big":
        raise SystemExit(f"{row.key}: unexpected GT bitorder")
    axis = packed.ndim - 1
    bits = np.unpackbits(packed, axis=axis, bitorder="big")
    if packed.ndim == 3:
        if page.get("gt_plane_order") != ["C", "M", "Y"]:
            raise SystemExit(f"{row.key}: unexpected GT plane order")
        bits = bits[:, :, :cells_x * cell_dots]
        cell_bits = bits[:, ::cell_dots, ::cell_dots]
        if cell_bits.shape != (3, cells_y, cells_x):
            raise SystemExit(
                f"{row.key}: GT cell grid {cell_bits.shape} != "
                f"(3,{cells_y},{cells_x})")
    else:
        bits = bits[:, :cells_x * cell_dots]
        cell_bits = bits[::cell_dots, ::cell_dots]
        if cell_bits.shape != (cells_y, cells_x):
            raise SystemExit(
                f"{row.key}: GT cell grid {cell_bits.shape} != "
                f"({cells_y},{cells_x})")
    return GroundTruth(
        row.key, row.kind, np.ascontiguousarray(cell_bits),
        (cells_y, cells_x), array_sha)


def _certificates_by_address(certificates) -> dict:
    grouped: dict[tuple[int, int, int], list] = {}
    for record in certificates:
        grouped.setdefault(
            (int(record.page), int(record.tile_yx[0]), int(record.tile_yx[1])),
            []).append(record)
    return grouped


def audit_certificates(certificates, spec, truth: GroundTruth) -> dict:
    """Project every certificate and compare with GT (truth path + B5).

    Colour: ``project_certified_color_tile`` re-encodes the protected
    frame and reports which components it OWNS; only owned cells are
    compared, so a partial CMY8 certificate never claims its siblings.
    K: ``printed_cells_from_record`` is the same authority for the single
    plane.
    """
    grouped = _certificates_by_address(certificates)
    compared = 0
    disagreeing = 0
    bad_addresses: list[dict] = []
    per_stream_cells: dict[str, int] = {}
    if truth.kind in ("cmy7", "cmy8"):
        from holo.receive.color_projection import project_certified_color_tile

        for address, rows in sorted(grouped.items()):
            projection = project_certified_color_tile(rows, spec, address)
            known = np.asarray(projection.known_mask)
            bits = np.asarray(projection.component_bits)
            gt = truth.tile_bits(address[1], address[2])
            # Furniture is format-known for every plane; restrict the audit
            # to the cells THESE certificates actually authorize by
            # subtracting the furniture-only projection.
            furniture = project_certified_color_tile((), spec, address)
            owned = known & ~np.asarray(furniture.known_mask)
            mismatch = int(np.count_nonzero(bits[owned] != gt[owned]))
            compared += int(np.count_nonzero(owned))
            # Exact per-stream accounting: a CMY7 "main" certificate owns
            # all three planes of the payload cells; each CMY8 stream owns
            # exactly its own plane (§6.2 component-only law).
            per_certificate = (
                spec.payload_cells * 3 if truth.kind == "cmy7"
                else spec.payload_cells)
            for record in rows:
                per_stream_cells[record.stream_id] = (
                    per_stream_cells.get(record.stream_id, 0)
                    + per_certificate)
            if mismatch:
                disagreeing += 1
                bad_addresses.append({
                    "address": list(address),
                    "streams": sorted(row.stream_id for row in rows),
                    "mismatched_cells": mismatch,
                    "owned_cells": int(np.count_nonzero(owned)),
                })
    else:
        from holo.receive.records import printed_cells_from_record

        for address, rows in sorted(grouped.items()):
            gt = truth.tile_bits(address[1], address[2])
            for record in rows:
                # K re-encodes the COMPLETE printed field (word/filler
                # sites and page scramble included), so every cell of the
                # tile is owned by this one certificate.
                bits = np.asarray(
                    printed_cells_from_record(record, spec)).reshape(64, 64)
                mismatch = int(np.count_nonzero(bits != gt))
                compared += int(bits.size)
                per_stream_cells[record.stream_id] = (
                    per_stream_cells.get(record.stream_id, 0) + int(bits.size))
                if mismatch:
                    disagreeing += 1
                    bad_addresses.append({
                        "address": list(address),
                        "streams": [record.stream_id],
                        "mismatched_cells": mismatch,
                        "owned_cells": int(bits.size),
                    })
    return {
        "certificates": len(certificates),
        "addresses": len(grouped),
        "cells_compared": compared,
        "cells_agreeing": compared - sum(
            row["mismatched_cells"] for row in bad_addresses),
        "agreement": (1.0 if compared == 0 else
                      1.0 - sum(row["mismatched_cells"]
                                for row in bad_addresses) / compared),
        "disagreeing_addresses": disagreeing,
        "wrong_certificate_addresses": bad_addresses[:20],
        "owned_cells_by_stream": dict(sorted(per_stream_cells.items())),
    }


def _decoded_states(kind: str, values: np.ndarray) -> np.ndarray:
    """Hard per-cell decisions from one evidence tensor (kind-aware)."""
    if kind == "cmy7":
        # Six W-relative scores; W is the implicit zero.
        widened = np.concatenate(
            (np.zeros((values.shape[0], 1), values.dtype), values), axis=1)
        return np.argmax(widened, axis=1).astype(np.uint8)
    if kind == "cmy8":
        return (values > 0.0).astype(np.uint8)
    return (values > 0.0).astype(np.uint8)


def score_blocks(blocks, spec, truth: GroundTruth) -> dict:
    """Per-cell hard-decision error of retained evidence, by lane.

    Retained blocks are exactly the tiles whose streams did NOT all
    certify — the population every uplift packet is aiming at.
    """
    from holo.format import pilots

    payload_mask = np.zeros(4096, dtype=bool)
    if truth.kind in ("cmy7", "cmy8"):
        payload_mask[np.asarray(
            pilots.color_payload_cell_indices(spec.family_seed),
            dtype=np.int64)] = True
    else:
        # K's payload cells are the complement of its word/filler sites.
        payload_mask[:] = True
        payload_mask[np.asarray(
            pilots.site_cell_indices(spec.family_seed, spec.n_filler),
            dtype=np.int64)] = False
    by_lane: dict[str, dict] = {}
    for block in blocks:
        lane = by_lane.setdefault(block.lane_id, {
            "blocks": 0, "cells": 0, "payload_cells": 0,
            "state_errors": 0, "payload_state_errors": 0,
            "plane_cells": 0, "plane_errors": 0})
        observed = np.asarray(block.observed_flat(), dtype=np.int64)
        values = np.asarray(block.printed_llr(), dtype=np.float64)
        if values.ndim == 1:
            values = values[:, None]
        gt_tile = truth.tile_bits(block.tile_yx[0], block.tile_yx[1])
        flat_gt = gt_tile.reshape(4096, -1)
        selected = payload_mask[observed]
        decoded = _decoded_states(truth.kind, values)
        if truth.kind == "cmy7":
            gt_states = (flat_gt[observed, 0]
                         | (flat_gt[observed, 1] << 1)
                         | (flat_gt[observed, 2] << 2))
            wrong = decoded != gt_states
            lane["state_errors"] += int(np.count_nonzero(wrong))
            lane["payload_state_errors"] += int(
                np.count_nonzero(wrong & selected))
        elif truth.kind == "cmy8":
            gt_planes = flat_gt[observed, :]
            wrong = decoded != gt_planes
            lane["plane_errors"] += int(np.count_nonzero(wrong))
            lane["plane_cells"] += int(wrong.size)
            state_wrong = wrong.any(axis=1)
            lane["state_errors"] += int(np.count_nonzero(state_wrong))
            lane["payload_state_errors"] += int(
                np.count_nonzero(state_wrong & selected))
        else:
            gt_bits = flat_gt[observed, 0]
            wrong = decoded[:, 0] != gt_bits
            lane["state_errors"] += int(np.count_nonzero(wrong))
            lane["payload_state_errors"] += int(
                np.count_nonzero(wrong & selected))
        lane["blocks"] += 1
        lane["cells"] += int(observed.size)
        lane["payload_cells"] += int(np.count_nonzero(selected))
    for lane in by_lane.values():
        lane["state_error_rate"] = (
            lane["state_errors"] / lane["cells"] if lane["cells"] else None)
        lane["payload_state_error_rate"] = (
            lane["payload_state_errors"] / lane["payload_cells"]
            if lane["payload_cells"] else None)
        lane["plane_error_rate"] = (
            lane["plane_errors"] / lane["plane_cells"]
            if lane["plane_cells"] else None)
    return dict(sorted(by_lane.items()))


def _close_report(spec, certificates, row: CaptureRow) -> dict:
    from holo.receive.fountain_close import close_volume
    from holo.receive.records import certificate_for_close

    if not certificates:
        return {"status": "open", "reason": "no certificates"}
    outcome = close_volume(
        tuple(certificate_for_close(record, spec)
              for record in certificates), spec)
    payload = getattr(outcome, "payload", None)
    report: dict = {"status": outcome.status}
    if payload is None:
        report["reason"] = getattr(outcome, "reason", None)
        return report
    digest = hashlib.sha256(payload).hexdigest()
    recorded = corpus.provenance_row(row.key)
    report.update({
        "bytes": len(payload),
        "sha256": digest,
        "matches_emitted_payload": digest == recorded["payload_sha256"],
    })
    archived = row.recovered_path()
    if archived is not None and archived.is_file():
        report["matches_archived_recovered_bin"] = (
            digest == recorded["artifacts"]["recovered"]["sha256"])
    return report


def certificates_from_run(rows: list[dict]) -> list:
    from holo.receive.evidence import TileCertificateRecord

    return [
        TileCertificateRecord(
            certificate_id=row["certificate_id"],
            page=int(row["page"]),
            tile_yx=(int(row["tile_yx"][0]), int(row["tile_yx"][1])),
            packed_user_bits=bytes.fromhex(row["packed_user_bits_hex"]),
            origin_attempt_id=row.get("origin_attempt_id", "replayed"),
            stream_id=row["stream_id"],
        )
        for row in rows
    ]


def _truth_verdict(audit: dict) -> dict:
    """ONE truth-path predicate for all three scorer modes.

    "No certificate disagreed" is not the same claim as "the truth path
    was exercised": a state with nothing certified compares zero cells
    and passes the disagreement test trivially.  `truth` always demanded
    a non-empty comparison; `state` and `run` did not, so a 0-certificate
    row (a B6 control, an early abort) reported itself VALIDATED off an
    empty audit.  Both facts are now published side by side, and a
    certificate that owns no comparable cell — certificates present,
    cells compared zero — is an unexpected shape that fails outright
    rather than reading vacuous.
    """
    compared = int(audit.get("cells_compared", 0))
    return {
        "truth_path_validated": (
            int(audit.get("disagreeing_addresses", 0)) == 0 and compared > 0),
        "truth_path_vacuous": (
            compared == 0 and int(audit.get("certificates", 0)) == 0),
    }


def _emit(report: dict, out: Path | None) -> int:
    text = json.dumps(report, indent=1, sort_keys=True)
    if out is not None:
        out.write_text(text + "\n")
    print(text)
    audit = report.get("certificate_audit", {})
    if audit.get("disagreeing_addresses"):
        print("CAMPAIGN-STOP: a certificate disagrees with ground truth "
              f"({audit['disagreeing_addresses']} addresses) — bar B5 is "
              "the campaign-stopping hard bar", file=sys.stderr)
        return 2
    return 0


def cmd_truth(args: argparse.Namespace) -> int:
    """Truth-path validation alone: the acceptance gate for the scorer."""
    row = corpus.capture(args.capture)
    cache = state_cache.load(row, verbose=False)
    state_cache.verify_against_provenance(row, cache)
    spec = corpus.resolve_spec(row, cache.format_row_id)
    truth = load_ground_truth(row)
    certificates = list(cache.certificates_by_id.values())
    audit = audit_certificates(certificates, spec, truth)
    report = {
        "mode": "truth",
        "capture": row.key,
        "kind": row.kind,
        "format_row_id": cache.format_row_id,
        "state_sha256": cache.state_sha256,
        "gt_array_sha256": truth.array_sha256,
        "gt_cells_yx": list(truth.cells_yx),
        "certificate_audit": audit,
        **_truth_verdict(audit),
    }
    return _emit(report, Path(args.out) if args.out else None)


def cmd_state(args: argparse.Namespace) -> int:
    """Score an ARCHIVED state: truth path, per-lane error, close."""
    from holo.receive.session import load_session

    row = corpus.capture(args.capture)
    cache = state_cache.load(row, verbose=False)
    state_cache.verify_against_provenance(row, cache)
    spec = corpus.resolve_spec(row, cache.format_row_id)
    truth = load_ground_truth(row)
    certificates = list(cache.certificates_by_id.values())
    audit = audit_certificates(certificates, spec, truth)
    report = {
        "mode": "state",
        "capture": row.key,
        "kind": row.kind,
        "format_row_id": cache.format_row_id,
        "state_sha256": cache.state_sha256,
        "certificates": len(certificates),
        "certificates_by_stream": {},
        "certificate_audit": audit,
        **_truth_verdict(audit),
    }
    counts: dict[str, int] = {}
    for record in certificates:
        counts[record.stream_id] = counts.get(record.stream_id, 0) + 1
    report["certificates_by_stream"] = dict(sorted(counts.items()))
    # Stop on DISAGREEMENT, not on vacuity: a state that certified
    # nothing still has a block ledger and a (trivially open) close worth
    # reporting, and its `truth_path_vacuous` flag already says the audit
    # proved nothing.  A certificates-without-cells state is the
    # unexpected shape and stops here with the disagreement cases.
    if not (report["truth_path_validated"] or report["truth_path_vacuous"]):
        return _emit(report, Path(args.out) if args.out else None)
    if args.blocks:
        state = load_session(row.state_path(), defer_fountain_validation=True)
        report["retained_block_error"] = score_blocks(
            state.blocks, spec, truth)
        report["retained_blocks"] = len(state.blocks)
    if args.close:
        report["close"] = _close_report(spec, certificates, row)
    return _emit(report, Path(args.out) if args.out else None)


def cmd_run(args: argparse.Namespace) -> int:
    """Score a run JSON produced by :mod:`ab_runner`."""
    run = json.loads(Path(args.run).read_text())
    row = corpus.capture(run["capture"])
    spec = corpus.resolve_spec(row, run["format_row_id"])
    truth = load_ground_truth(row)
    certificates = certificates_from_run(run["certificates"])
    audit = audit_certificates(certificates, spec, truth)
    counts: dict[str, int] = {}
    for record in certificates:
        counts[record.stream_id] = counts.get(record.stream_id, 0) + 1
    report = {
        "mode": "run",
        "run": str(args.run),
        "capture": row.key,
        "arm": run["arm"],
        "run_mode": run["mode"],
        "force_null": run["force_null"],
        "worktree_head": run["worktree"]["head"],
        "color_payload_policy_id": run["color_payload_policy_id"],
        "certificates": len(certificates),
        "certificates_by_stream": dict(sorted(counts.items())),
        "archived_certificates": run.get("archived", {}).get("certificates"),
        "certificate_audit": audit,
        **_truth_verdict(audit),
        "certificate_set_vs_archived": set_difference(run),
    }
    if args.close:
        report["close"] = _close_report(spec, certificates, row)
    return _emit(report, Path(args.out) if args.out else None)


def set_difference(run: dict) -> dict:
    archived = set(run.get("archived", {}).get("certificate_ids", ()))
    replayed = {row["certificate_id"] for row in run["certificates"]}
    if not archived:
        return {"comparable": False}
    return {
        "comparable": True,
        "archived": len(archived),
        "produced": len(replayed),
        "identical": archived == replayed,
        "missing": len(archived - replayed),
        "extra": len(replayed - archived),
        "missing_examples": sorted(archived - replayed)[:10],
        "extra_examples": sorted(replayed - archived)[:10],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.gt_score", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    item = sub.add_parser("truth")
    item.add_argument("--capture", required=True)
    item.add_argument("--out", default=None)
    item.set_defaults(handler=cmd_truth)

    item = sub.add_parser("state")
    item.add_argument("--capture", required=True)
    item.add_argument("--blocks", action="store_true",
                      help="score retained evidence blocks (re-reads the "
                           "state; minutes on the multi-GB rows)")
    item.add_argument("--close", action="store_true")
    item.add_argument("--out", default=None)
    item.set_defaults(handler=cmd_state)

    item = sub.add_parser("run")
    item.add_argument("--run", required=True)
    item.add_argument("--close", action="store_true")
    item.add_argument("--out", default=None)
    item.set_defaults(handler=cmd_run)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    from _color_uplift_harness import gt_score as _module

    raise SystemExit(_module.main())
