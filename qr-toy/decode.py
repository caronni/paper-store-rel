#!/usr/bin/env python3
"""Verbose, single-frame experiment. No fountain decoder or payload oracle."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

# common makes the repository's src/ importable for this standalone script.
from common import FORMAT, PAYLOAD_BYTES, format_parts
import acquire
from holo.receiver.plugins import calibrate, tiles


def decode(
    image_path: Path, out: Path, *, max_side: int = 1800,
    pose_radius: float = 3., max_candidates: int = 3,
    max_known_errors: int = 20, flatten_lighting: bool = False,
    radial_k1: float = 0., verify: Path | None = None,
) -> int:
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report: dict[str, Any] = {
        "format": FORMAT,
        "status": "failed",
        "events": [],
        "attempts": [],
        "options": dict(
            max_side=max_side, pose_radius=pose_radius,
            max_candidates=max_candidates, max_known_errors=max_known_errors,
            flatten_lighting=flatten_lighting, radial_k1=radial_k1,
        ),
    }

    def log(stage: str, message: str) -> None:
        event = dict(
            step=len(report["events"]) + 1,
            seconds=round(time.monotonic() - started, 3),
            stage=stage, message=message,
        )
        report["events"].append(event)
        print(f'[{event["step"]:02d} +{event["seconds"]:.3f}s] {stage}: {message}', flush=True)
        with (out / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def save_image(name: str, pixels: np.ndarray) -> None:
        Image.fromarray(np.uint8(np.clip(pixels, 0, 1) * 255)).save(out / name)

    try:
        if max_side < 128 or not .5 <= pose_radius <= 12 or max_candidates < 1:
            raise ValueError(
                "max-side >=128, pose-radius between 0.5 and 12, candidates >=1 required"
            )
        if (not np.isfinite(radial_k1) or abs(radial_k1) > .5
                or not 0 <= max_known_errors <= 103):
            raise ValueError(
                "radial-k1 must be finite within ±0.5; known errors within 0..103"
            )
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        report["image_sha256"] = digest
        _, row, geometry, cells, reference = format_parts()
        known = reference >= 0
        log("contract", f"{FORMAT}; page=0, tile=(0,0); 103 known cells; "
            f"arbitrary {PAYLOAD_BYTES} bytes; no fountain/envelope")
        grey, rgb = acquire.read_image(
            image_path, max_side, flatten_lighting, radial_k1, log,
        )
        normalized, quads = acquire.segment(grey, max_candidates, log)
        poses: list[acquire.Pose] = []
        for index, quad in enumerate(quads):
            try:
                rectified, _, regions = acquire.production_survey(
                    normalized, quad, row.pitch_in, log,
                )
            except (ValueError, np.linalg.LinAlgError) as exc:
                log("survey", f"candidate {index}: diagnostic unavailable: {exc}; "
                    "continuing toy search")
            else:
                save_image(f"candidate-{index}-survey.png", rectified)
                if not regions:
                    log("survey", "no production region: continuing explicit "
                        "toy envelope/known-cell fallback")
            try:
                poses.extend(acquire.find_poses(
                    normalized, quad, cells[known, ::-1] + .5,
                    reference[known], pose_radius, index, log,
                ))
            except (ValueError, np.linalg.LinAlgError) as exc:
                log("pose", f"candidate {index}: rejected invalid geometry: {exc}")
        for pose in sorted(poses, key=lambda p: (p.errors, p.loss)):
            if pose.errors > max_known_errors:
                continue
            log("sampling", f"candidate={pose.candidate}, rotation={pose.rotation * 90}, "
                f"mirror={pose.mirrored}; known errors={pose.errors}/103")
            for aperture in (.2, .1, .3):
                means, observed = acquire.cell_samples(normalized, pose.quad, aperture)
                # Out-of-image samples have a white fill value, not measured
                # evidence. Exclude them from both calibration label sets.
                observed_reference = np.where(observed, reference, -1)
                fit = calibrate.fit_window_calibration(
                    calibrate.window_scores(means), observed_reference, cells,
                )
                log("calibration", f"aperture=±{aperture:g} cell; "
                    f"observed={observed.sum()}/4096; accepted={fit.accepted}; "
                    f"reason={fit.reason}; training known sites={fit.n_search}; "
                    f"photometric heldout loss={fit.heldout_logloss}")
                if not fit.accepted:
                    continue
                cut = tiles.TileCut(
                    digest, 0, 0, 0, 0,
                    fit.marginal_llr[observed, None], np.flatnonzero(observed),
                )
                for stage in (tiles.STAGE_SCAN, tiles.STAGE_RETRY150):
                    result = tiles.attempt_tile(
                        row, geometry, (cut,), row.streams[0].stream_id, stage,
                    )
                    fact = result.fact
                    pose_record = {**asdict(pose), "quad": pose.quad.tolist()}
                    report["attempts"].append({
                        **asdict(fact), "pose": pose_record, "aperture": aperture,
                    })
                    log("LDPC/CRC", f"stage={stage}; informative={fact.n_informative}; "
                        f"iterations={fact.n_iters}; syndrome={fact.syndrome_ok}; "
                        f"CRC={fact.crc_ok}; outcome={fact.outcome}")
                    if result.certificate is None:
                        continue
                    bits = result.certificate.user_bits
                    if len(bits) != 1 + 8 * PAYLOAD_BYTES:
                        raise ValueError("unexpected certified frame size")
                    payload = np.packbits(bits[1:]).tobytes()
                    (out / "recovered.bin").write_bytes(payload)
                    printed = tiles.printed_cells_for(row, geometry, 0, 0, 0, bits).ravel()
                    errors = int(np.count_nonzero(((means < .5) != printed) & observed))
                    report.update(
                        status="certified",
                        payload_sha256=hashlib.sha256(payload).hexdigest(),
                        payload_bytes=len(payload), metadata_bit=int(bits[0]),
                        pose=pose_record, aperture=aperture,
                        postdecode_hard_cell_errors=errors,
                    )
                    save_image(
                        "sampled-cells.png",
                        np.repeat(np.repeat(means.reshape(64, 64), 8, 0), 8, 1),
                    )
                    overlay = Image.fromarray(rgb)
                    ImageDraw.Draw(overlay).line(
                        [tuple(p) for p in np.vstack((pose.quad, pose.quad[0]))],
                        fill="red", width=3,
                    )
                    overlay.save(out / "pose.png")
                    log("certified", f"wrote {len(payload)} bytes; "
                        f"sha256={report['payload_sha256']}; "
                        f"hard cell disagreements against certified re-encoding={errors}; "
                        f"metadata bit={bits[0]} discarded")
                    if verify is not None:
                        # This is deliberately the first access to any expected payload.
                        try:
                            expected = verify.read_bytes()
                        except OSError as exc:
                            report["status"] = "verification_failed"
                            report["verification_error"] = str(exc)
                            log("post-decode verification",
                                f"could not read expected file: {exc}")
                            return 3
                        matches = expected == payload
                        report["verification_matches"] = matches
                        log("post-decode verification", f"expected file matches={matches}; "
                            "never used during acquisition or decoding")
                        if not matches:
                            report["status"] = "verification_failed"
                            return 3
                    return 0
        raise ValueError(
            "no LDPC+CRC certified frame; inspect candidate images "
            "and pose/calibration diagnostics"
        )
    except (ValueError, OSError, np.linalg.LinAlgError) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        log("failure", str(exc))
        return 2
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        (out / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-side", type=int, default=1800)
    parser.add_argument("--pose-radius", type=float, default=3.)
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument("--max-known-errors", type=int, default=20)
    parser.add_argument("--flatten-lighting", action="store_true")
    parser.add_argument("--radial-k1", type=float, default=0.)
    parser.add_argument("--verify", type=Path, help="compare only AFTER certified decode")
    args = vars(parser.parse_args())
    args["image_path"] = args.pop("image")
    try:
        return decode(**args)
    except FileExistsError:
        parser.error("output directory already exists; choose a fresh --out")
    except OSError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
