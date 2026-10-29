#!/usr/bin/env python
"""The simulated control: two captures, one of them plane-displaced.

    PYTHONPATH=src:. <python> -m measure.local_ab._sim --out build/local-ab

WHY THIS EXISTS, TWICE OVER.

**As a self-check.** It exercises every line of `_ab.py` on material
that costs seconds, so a bug in the arms is found before a real battery
spends an hour earning it. The null arm's refusal is the load-bearing
assertion: same pixels, same head, address moved one tile — nothing may
certify.

**As a measurement in its own right.** `src/holo/receiver/tests/_h3_sims.py`'s hard
pair is the multi-scan law's own regime, built on purpose: ONE emitted
colour page rendered twice, once in register and once with the Y plane
displaced by a rounded +/-2-dot sinusoid, both with the same noise draw.
That is not two independent looks at one sheet — it is one good look and
one systematically wrong one, which is exactly when the law says
equal-weight combining loses to best-single. A real sheet's captures are
three platen placements of the same print, so their errors are
print-correlated but not adversarially so; the sim brackets the real
case from the hostile side.

The stimulus is the test suite's own fixture builder, unmodified. At its
own pinned constants (`SHIFTED_PLANE` 2 = Y, `SHIFTED_AMPLITUDE_DOTS`
2.0, `SHIFTED_CYCLES` 1.0, `SHIFTED_NOISE_SD` 12.0, seed 20260830) the
pair decodes COMPLETELY — 300/300 addresses, GT-exact — so it leaves no
residue and arms no subject. That run is kept as the clean control; the
arms are exercised by re-rendering the SAME emit through the SAME
builder at a declared harder noise, which is what `render_hard_pair`'s
`noise_sd`/`amplitude_dots` parameters exist for. Each setting gets its
own directory, so a capture id never means two different images.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import _ab, _paths


def _sims():
    """The suite's own fixture builders, on this worktree's ``src``.

    Imported as a package member, not by planting `src/holo/receiver/tests` on
    `sys.path`: the hygiene gate resolves instrument imports by path and
    a `sys.path` hack reads to it (correctly) as rot.
    """
    _paths.install_src()
    from holo.receiver.tests import _h3_sims

    return _h3_sims


def variant_dir(out: Path, amplitude: float, noise: float) -> Path:
    return out / "sim" / f"a{amplitude:g}-n{noise:g}"


def build(out: Path, amplitude: float, noise: float,
          fresh: bool) -> tuple[object, Path, tuple[Path, Path]]:
    """The suite's emit, rendered at one declared (amplitude, noise)."""
    sims = _sims()
    outdir = variant_dir(out, amplitude, noise)
    outdir.mkdir(parents=True, exist_ok=True)
    control = outdir / sims.CONTROL_TIFF_NAME
    shifted = outdir / sims.SHIFTED_TIFF_NAME
    if fresh or not (control.is_file() and shifted.is_file()):
        sims.make_color_hard(outdir)
        sims.render_hard_pair(outdir, amplitude_dots=amplitude,
                              noise_sd=noise)
    return sims, outdir / sims.HARD_PAYLOAD_NAME, (control, shifted)


def decode(sims, tiffs: tuple[Path, Path], run_dir: Path,
           workers: int) -> tuple[object, object, list, float]:
    from holo.receiver import cli, engine

    argv = ["decode", str(tiffs[0]), str(tiffs[1]),
            "--dpi", str(sims.DPI), "--dpi", str(sims.DPI),
            "--format", sims.HARD_FORMAT_REF, "--no-close",
            "--out", str(run_dir / "payload.bin"),
            "--run-dir", str(run_dir), "--workers", str(workers)]
    args = cli._build_parser().parse_args(argv)
    request = cli._request(args)
    events: list = []
    started = time.perf_counter()
    store = engine._Engine(request, events)
    result = store.run()
    return store, result, events, time.perf_counter() - started


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--amplitude-dots", type=float, default=None,
                        help="Y-plane displacement peak, in printed dots "
                             "(default: the suite's 2.0)")
    parser.add_argument("--probe", type=int, default=6,
                        help="positive-control subjects taken from "
                             "certified addresses (0 disables)")
    parser.add_argument("--noise-sd", type=float, default=None,
                        help="per-pixel Gaussian sd in 8-bit levels "
                             "(default: the suite's 12.0)")
    parser.add_argument("--out", type=Path, required=True,
                        help="artefact directory (sim/, runs/, reports/)")
    args = parser.parse_args(argv)

    from .harness import _audit

    sims_probe = _sims()
    amplitude = (sims_probe.SHIFTED_AMPLITUDE_DOTS
                 if args.amplitude_dots is None else args.amplitude_dots)
    noise = (sims_probe.SHIFTED_NOISE_SD if args.noise_sd is None
             else args.noise_sd)
    sims, payload_path, tiffs = build(args.out, amplitude, noise, args.fresh)
    _paths.install_src()
    from measure.crop_parity import _gt

    payload = _gt.load_payload(payload_path, sims.HARD_PAYLOAD_SHA256,
                               sims.HARD_PAYLOAD_BYTES)
    gt = _gt.reconstruct(sims.HARD_FORMAT_REF, payload, pages=1)

    tag = f"sim-a{amplitude:g}-n{noise:g}"
    run_dir = args.out / "runs" / tag
    if args.fresh and run_dir.exists():
        import shutil

        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    store, result, events, wall = decode(sims, tiffs, run_dir,
                                         args.workers)
    decoded = {key: np.asarray(certificate.user_bits)
               for key, certificate in store.certificates().items()}
    audits = [_audit(_gt, gt, decoded, "decode certificates")]

    tiles_y, tiles_x = store.row.tiles_yx
    positions = tuple((ty, tx) for ty in range(tiles_y)
                      for tx in range(tiles_x))
    found, census = _ab.subjects(store, positions,
                                 _ab.armed_addresses(events))
    probes = _ab.probe_subjects(store, positions, args.probe)
    results = [_ab.measure(store, subject)
               for subject in tuple(found) + probes]
    probe_rows = [
        {"ty": r.subject.ty, "tx": r.subject.tx,
         "stream": r.subject.stream_id, "ppc": str(r.subject.ppc),
         "n_components": r.n_components,
         "union": r.union.certified, "per_origin": r.per_origin.certified,
         "null": r.null.certified,
         "per_origin_attempts": [list(row)
                                 for row in r.per_origin.attempts]}
        for r in results[len(found):]]

    minted: dict = {}
    null_minted: dict = {}
    for outcome in results:
        for arm in (outcome.union, outcome.per_origin):
            if arm.bits is not None:
                minted[outcome.subject.address] = arm.bits
        if outcome.null.bits is not None:
            null_minted[outcome.null.address] = outcome.null.bits
    audits.append(_audit(_gt, gt, minted, "A/B certificates"))
    audits.append(_audit(_gt, gt, null_minted, "N0 null certificates"))

    residue = results[:len(found)]
    classes = {"both": 0, "union_only": 0, "per_origin_only": 0,
               "neither": 0}
    for outcome in residue:
        classes[_ab.classify(outcome)] += 1
    summary = {
        "format_ref": sims.HARD_FORMAT_REF,
        "amplitude_dots": amplitude, "noise_sd": noise,
        "decode": {"wall_seconds": round(wall, 1),
                   "status": str(result.status),
                   "n_certificates": int(result.certified)},
        "subject_census": census,
        "reach_report": _ab.reach_report(store, positions, 4),
        "positive_control": probe_rows,
        "n_subjects": len(found),
        "classes": classes,
        "union_adds": sum(1 for r in residue if r.union.certified),
        "per_origin_adds": sum(1 for r in residue if r.per_origin.certified),
        "null_certificates": sum(1 for r in results if r.null.certified),
        "per_origin_winners": sorted(
            {r.per_origin.winner for r in results
             if r.per_origin.winner is not None}),
        "cpu_seconds": {
            "component_build_shared": round(
                sum(r.build_cpu_seconds for r in results), 1),
            "union_attempts": round(
                sum(r.union.cpu_seconds for r in results), 1),
            "per_origin_attempts": round(
                sum(r.per_origin.cpu_seconds for r in results), 1)},
        "audits": audits,
    }
    out = args.out / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{tag}.json").write_text(
        json.dumps(summary, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))

    problems = [audit for audit in audits if audit["n_wrong"]]
    if problems or summary["null_certificates"]:
        print("\nlocal_ab sim: REFUSING — wrong certificate or a null that "
              "certified")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
