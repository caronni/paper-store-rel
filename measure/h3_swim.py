"""Drive the swim row's gates: the null proof, the existence proof, and
the field-hint ablation.

Four dials on one in-process decode, so every arm differs from its
control in exactly one of them:

    --shape sine|step   which displacement the degraded page carries
    --plane-fields      the standing per-plane field, on or off
    --drop-rows         rows removed from the descriptor table
    --no-hint           the swim starts its search from ZERO instead of
                        from the standing field's value (the ablation)

The record it writes is schema-compatible with
``measure/h3_plane_fields.py``, so ``h3_plane_fields.py compare a.json
b.json`` diffs any two arms — payload sha, certificate signature,
per-address set difference and per-row job counts.

    PYTHONPATH=. python measure/h3_swim.py sims --tree . --sims-dir DIR
    PYTHONPATH=. python measure/h3_swim.py decode --tree . --sims-dir DIR \
        --sim hard-shifted --shape step --plane-fields \
        --run-dir R --out arm.json

`decode` never touches a real scan: every capture is rendered from the
colour sim's own emitted ground truth.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import h3_plane_fields as base  # noqa: E402

SIMS = ("k", "color", "hard-shifted", "hard-control")


def capture_for(root: Path, sims_dir: Path, sim: str, shape: str,
                amplitude_dots: float | None,
                noise_sd: float | None) -> object:
    """The base driver's capture, plus the displacement SHAPE dial."""
    sims = base._sims_module(root)
    if sim in ("k", "color"):
        return base.capture_for(root, sims_dir, sim)
    amplitude = (sims.SHIFTED_AMPLITUDE_DOTS if amplitude_dots is None
                 else amplitude_dots)
    noise = sims.SHIFTED_NOISE_SD if noise_sd is None else noise_sd
    emit = sims_dir / "color-hard"
    if not (emit / sims.HARD_PAYLOAD_NAME).is_file():
        sims.make_color_hard(emit)
    target = sims_dir / f"color-hard-{shape}-a{amplitude:g}-n{noise:g}"
    if not (target / sims.SHIFTED_TIFF_NAME).is_file():
        for name in (sims.HARD_EMIT_DIRNAME, sims.HARD_PAYLOAD_NAME):
            base._link(emit / name, target / name)
        sims.render_hard_pair(target, amplitude, noise, shape)
    name = (sims.CONTROL_TIFF_NAME if sim == "hard-control"
            else sims.SHIFTED_TIFF_NAME)
    return sims.capture_color_hard(target, name, sim)


def _ablate_hint(swim: object) -> None:
    """Start every search from zero — the field-hint ablation arm.

    Only the START moves.  Bounds, resolution, objective, labels and
    the certificate gate are untouched, so a delta against the hinted
    arm is the hint's and nothing else's.
    """
    import numpy as np

    def zero_hint(plane_fields: object, page_cells_yx: object) -> tuple:
        zero = np.zeros((np.asarray(page_cells_yx).shape[0], 2), np.float64)
        return (zero, zero.copy(), zero.copy())

    swim._hint_offsets = zero_hint


def _watch_swim(swim: object, record: list) -> None:
    """Record every window fit the row makes, hint ablated or not."""
    original = swim.fit_window

    def wrapped(*args, **kwargs):
        fit = original(*args, **kwargs)
        if fit is not None:
            record.append({
                "patch_ordinal": int(fit.patch_ordinal),
                "n_cells": int(fit.n_cells),
                "n_evaluations": int(fit.n_evaluations),
                "correlations": [round(float(value), 6)
                                 for value in fit.correlations],
                "log_likelihoods": [round(float(value), 3)
                                    for value in fit.log_likelihoods],
                "translation_dots": [
                    None if affine is None
                    else [round(float(value), 4)
                          for value in affine.translation]
                    for affine in fit.affines],
                "linear_dots": [
                    None if affine is None
                    else [round(float(value), 4)
                          for value in affine.linear.ravel()]
                    for affine in fit.affines],
            })
        return fit

    swim.fit_window = wrapped


def decode(root: Path, sims_dir: Path, sim: str, workers: int,
           plane_fields: bool, run_dir: Path, out_path: Path, shape: str,
           drop_rows: tuple[str, ...], no_hint: bool,
           amplitude_dots: float | None, noise_sd: float | None,
           watch: bool) -> dict[str, object]:
    capture = capture_for(root, sims_dir, sim, shape, amplitude_dots,
                          noise_sd)
    from holo3 import cli, data, engine
    from holo3.plugins import swim

    if no_hint:
        _ablate_hint(swim)
    fits: list = []
    if watch:
        _watch_swim(swim, fits)

    standing = engine.DESCRIPTORS
    if drop_rows:
        kept = tuple(descriptor for descriptor in standing
                     if descriptor.name not in drop_rows)
        if len(kept) != len(standing) - len(drop_rows):
            raise SystemExit(f"--drop-rows {drop_rows} names a row that "
                             f"is not in the descriptor table")
        engine.DESCRIPTORS = kept

    payload_path = run_dir / "payload.bin"
    argv = ["decode", str(capture.tiff), "--dpi", str(int(capture.dpi)),
            "--format", capture.format_ref, "--out", str(payload_path),
            "--workers", str(workers), "--run-dir", str(run_dir / "run"),
            "--complete"]
    if plane_fields:
        argv.append("--plane-fields")
    captured: dict[str, object] = {}
    original = engine.decode

    def instrumented(request: object, events: list | None = None) -> object:
        collected: list = [] if events is None else events
        instance = engine._Engine(request, collected)
        result = instance.run()
        captured["certificates"] = dict(instance._certificates)
        captured["jobs"] = tuple(
            event.plugin for event in collected
            if isinstance(event, data.JobDone))
        captured["cpu"] = tuple(
            (event.plugin, float(event.cpu_s)) for event in collected
            if isinstance(event, data.JobDone))
        captured["fields"] = dict(getattr(instance, "_plane_fields", {}))
        return result

    out = io.StringIO()
    err = io.StringIO()
    engine.decode = instrumented
    try:
        with (contextlib.redirect_stdout(out),
              contextlib.redirect_stderr(err)):
            exit_code = cli.main(argv)
    finally:
        engine.decode = original
        engine.DESCRIPTORS = standing

    certificates = captured.get("certificates", {})
    signature = [
        [list(key), bytes(certificate.user_bits).hex()]
        for key, certificate in sorted(certificates.items())]
    payload = (payload_path.read_bytes() if payload_path.is_file()
               else None)
    jobs: dict[str, int] = {}
    for plugin in captured.get("jobs", ()):
        jobs[plugin] = jobs.get(plugin, 0) + 1
    cpu: dict[str, float] = {}
    for plugin, seconds in captured.get("cpu", ()):
        cpu[plugin] = cpu.get(plugin, 0.0) + seconds
    sources: dict[str, int] = {}
    for certificate in certificates.values():
        source = str(certificate.source)
        sources[source] = sources.get(source, 0) + 1
    record = {
        "tree": str(root),
        "sim": sim,
        "shape": shape,
        "workers": workers,
        "plane_fields": plane_fields,
        "drop_rows": list(drop_rows),
        "no_hint": no_hint,
        "exit_code": exit_code,
        "payload_sha256": (hashlib.sha256(payload).hexdigest()
                           if payload is not None else None),
        "payload_bytes": None if payload is None else len(payload),
        "expected_payload_sha256": capture.payload_sha256,
        "n_certificates": len(certificates),
        "certificate_signature_sha256": hashlib.sha256(
            json.dumps(signature, sort_keys=True).encode()).hexdigest(),
        "certificate_addresses": [row[0] for row in signature],
        "certificate_sources": dict(sorted(sources.items())),
        "jobs": dict(sorted(jobs.items())),
        "cpu_s": {name: round(value, 3)
                  for name, value in sorted(cpu.items())},
        "swim_fits": fits,
        "standing_fields": base._dump_fields(captured.get("fields", {}),
                                             run_dir),
        "stderr_tail": err.getvalue().splitlines()[-8:],
    }
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


def sweep(tree: Path, sims_dir: Path, out_dir: Path,
          arms: tuple[tuple[str, tuple[str, ...]], ...]) -> int:
    """Run named arms one at a time, each in its own process.

    A separate process per arm on purpose: the hint ablation replaces a
    module attribute, and the memory budget says one production decode
    at a time.  Serial, so two arms never share a core.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name, extra in arms:
        record = out_dir / f"{name}.json"
        if record.is_file():
            print(f"skip  {name} (already recorded)")
            continue
        argv = [sys.executable, str(Path(__file__).resolve()), "decode",
                "--tree", str(tree), "--sims-dir", str(sims_dir),
                "--run-dir", str(out_dir / name), "--out", str(record),
                *extra]
        print(f"run   {name}: {' '.join(extra)}", flush=True)
        done = subprocess.run(argv, cwd=str(tree), env={
            **os.environ, "PYTHONPATH": str(tree)})
        if done.returncode != 0:
            failures += 1
            print(f"FAIL  {name} exit {done.returncode}")
    return 1 if failures else 0


def summarise(out_dir: Path, control: str) -> int:
    """One table over a sweep: yield, attribution, cost, and the fits.

    Everything a reader needs to decide whether the row earned its
    price, against the named in-register control: how many of the
    control's addresses each arm recovered, who minted them, what the
    arm spent, and — for the arms that ran the search — how far the
    search actually moved.
    """
    records = {path.stem: json.loads(path.read_text())
               for path in sorted(out_dir.glob("*.json"))}
    if control not in records:
        print(f"no control record {control!r} in {out_dir}")
        return 1
    reference = {tuple(row) for row in
                 records[control]["certificate_addresses"]}
    print(f"control {control}: {len(reference)} certificates, payload "
          f"{'OK' if records[control]['payload_sha256'] == records[control]['expected_payload_sha256'] else 'MISMATCH'}")
    print(f"{'arm':28} {'certs':>6} {'missed':>7} {'payload':>8} "
          f"{'swim jobs':>10} {'swim cpu_s':>11} {'total cpu_s':>12}")
    for name, record in records.items():
        addresses = {tuple(row) for row in record["certificate_addresses"]}
        payload = ("byte-exact"
                   if record["payload_sha256"]
                   == record["expected_payload_sha256"] else "NO")
        print(f"{name:28} {len(addresses):6d} "
              f"{len(reference - addresses):7d} {payload:>8} "
              f"{record['jobs'].get('tiles.swim', 0):10d} "
              f"{record['cpu_s'].get('tiles.swim', 0.0):11.1f} "
              f"{sum(record['cpu_s'].values()):12.1f}")
    for name, record in records.items():
        fits = record.get("swim_fits") or []
        if not fits:
            continue
        moved = [(entry, plane) for entry in fits for plane in range(3)
                 if entry["translation_dots"][plane] is not None]
        print(f"\n{name}: {len(fits)} window fits, {len(moved)} plane "
              f"corrections, "
              f"{sum(entry['n_evaluations'] for entry in fits)} objective "
              f"evaluations, "
              f"{sum(entry['n_cells'] for entry in fits) // max(len(fits), 1)}"
              f" provable cells per fit (mean)")
        for plane in range(3):
            deltas = [abs(entry["translation_dots"][plane][0])
                      for entry in fits
                      if entry["translation_dots"][plane] is not None]
            if deltas:
                print(f"  plane {plane}: {len(deltas)} corrections, "
                      f"|dx| median {sorted(deltas)[len(deltas) // 2]:.3f} "
                      f"max {max(deltas):.3f} dots")
        sources = record.get("certificate_sources", {})
        print(f"  certificate sources: {json.dumps(sources, sort_keys=True)}")
    return 0


def parse_arms(spec: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """`name=--flag --flag;name=...` — arms as data, not as code."""
    arms: list[tuple[str, tuple[str, ...]]] = []
    for entry in spec.split(";"):
        if not entry.strip():
            continue
        name, _, flags = entry.partition("=")
        arms.append((name.strip(), tuple(flags.split())))
    return tuple(arms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="h3_swim")
    commands = parser.add_subparsers(dest="command", required=True)
    many = commands.add_parser("sweep")
    many.add_argument("--tree", type=Path, required=True)
    many.add_argument("--sims-dir", type=Path, required=True)
    many.add_argument("--out-dir", type=Path, required=True)
    many.add_argument("--arms")
    many.add_argument("--arms-file", dest="arms_file", type=Path)
    table = commands.add_parser("summary")
    table.add_argument("--out-dir", type=Path, required=True)
    table.add_argument("--control", required=True)
    sims = commands.add_parser("sims")
    sims.add_argument("--tree", type=Path, required=True)
    sims.add_argument("--sims-dir", type=Path, required=True)
    run = commands.add_parser("decode")
    run.add_argument("--tree", type=Path, required=True)
    run.add_argument("--sims-dir", type=Path, required=True)
    run.add_argument("--sim", choices=SIMS, required=True)
    run.add_argument("--shape", choices=("sine", "step"), default="sine")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--plane-fields", dest="plane_fields",
                     action="store_true")
    run.add_argument("--drop-rows", dest="drop_rows", default="")
    run.add_argument("--no-hint", dest="no_hint", action="store_true")
    run.add_argument("--watch-fits", dest="watch", action="store_true")
    run.add_argument("--run-dir", dest="run_dir", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--amplitude-dots", dest="amplitude_dots", type=float)
    run.add_argument("--noise-sd", dest="noise_sd", type=float)
    args = parser.parse_args(argv)
    if args.command == "summary":
        return summarise(args.out_dir, args.control)
    if args.command == "sweep":
        spec = (args.arms_file.read_text() if args.arms_file
                else args.arms or "")
        return sweep(args.tree, args.sims_dir, args.out_dir,
                     parse_arms(spec))
    if args.command == "sims":
        report = base.build_sims(args.tree, args.sims_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if all(value == "frozen-sha-ok"
                        for value in report.values()) else 1
    base._import_tree(args.tree)
    args.run_dir.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    record = decode(
        args.tree, args.sims_dir, args.sim, args.workers,
        args.plane_fields, args.run_dir, args.out, args.shape,
        tuple(name for name in args.drop_rows.split(",") if name),
        args.no_hint, args.amplitude_dots, args.noise_sd, args.watch)
    print(json.dumps({key: record[key] for key in (
        "sim", "shape", "plane_fields", "drop_rows", "no_hint",
        "exit_code", "n_certificates", "payload_sha256",
        "expected_payload_sha256", "certificate_sources", "jobs",
        "cpu_s")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
