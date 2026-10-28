"""Decode a holo3 sim from a NAMED TREE and dump what a decode is.

The plane-fields null proof is a two-tree claim — "with the dial off,
this branch decodes what an unmodified checkout decodes" — so it cannot
be made from inside one checkout's own test suite.  This driver takes the
tree to import as an argument, runs one sim decode in-process, and writes
the payload sha, the full certificate signature (address + user bits) and
the per-row job counts as JSON.  Two runs, one diff, no reasoning.

    python measure/h3_plane_fields.py sims --sims-dir DIR
    python measure/h3_plane_fields.py decode --tree ROOT --sim color \
        --sims-dir DIR --workers 1 --out run.json [--plane-fields] \
        [--drop tiles.local --drop tiles.planek]
    python measure/h3_plane_fields.py compare a.json b.json

`--drop` removes a scheduler row from the decode entirely, which is how
the stimulus is held to account: if a degraded page still certifies
everything with the field's rivals dropped, the page is not degraded.

`sims` builds the frozen sim artefacts (they are sha-gated, so both trees
consume byte-identical stimuli).  `decode` never touches a real scan.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path


def _import_tree(root: Path) -> None:
    for entry in (str(root / "src"), str(root)):
        if entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)


def _sims_module(root: Path) -> object:
    _import_tree(root)
    from holo3.tests import _h3_sims

    return _h3_sims


def build_sims(root: Path, sims_dir: Path) -> dict[str, str]:
    sims = _sims_module(root)
    report: dict[str, str] = {}
    for name, builder, expected in (
            ("k", sims.make_k, sims.EXPECTED_K),
            ("color", sims.make_color, sims.EXPECTED_COLOR)):
        target = sims_dir / name
        if sims.verify(target, expected) is not None:
            builder(target)
        problem = sims.verify(target, expected)
        report[name] = "frozen-sha-ok" if problem is None else problem
    return report


def _link(source: Path, target: Path) -> None:
    import shutil

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def capture_for(root: Path, sims_dir: Path, sim: str,
                amplitude_dots: float | None = None,
                noise_sd: float | None = None,
                patch_shift_px: int | None = None) -> object:
    sims = _sims_module(root)
    if sim == "k":
        return sims.capture_k(sims_dir / "k")
    colour = sims.capture_color(sims_dir / "color")
    if sim == "color":
        return colour
    if sim == "color-patch":
        return _color_patch_capture(root, sims, sims_dir, colour,
                                    patch_shift_px)
    amplitude = (sims.SHIFTED_AMPLITUDE_DOTS if amplitude_dots is None
                 else amplitude_dots)
    noise = sims.SHIFTED_NOISE_SD if noise_sd is None else noise_sd
    emit = sims_dir / "color-hard"
    if not (emit / sims.HARD_PAYLOAD_NAME).is_file():
        sims.make_color_hard(emit)
    target = sims_dir / f"color-hard-a{amplitude:g}-n{noise:g}"
    if not (target / sims.SHIFTED_TIFF_NAME).is_file():
        for name in (sims.HARD_EMIT_DIRNAME, sims.HARD_PAYLOAD_NAME):
            _link(emit / name, target / name)
        sims.render_hard_pair(target, amplitude, noise)
    if sim == "hard-faint":
        if not (target / sims.FAINT_TIFF_NAME).is_file():
            sims.render_hard_faint(target, amplitude, noise)
        return sims.capture_color_hard(target, sims.FAINT_TIFF_NAME,
                                       "hard-faint")
    if sim == "hard-control":
        return sims.capture_color_hard(target, sims.CONTROL_TIFF_NAME,
                                       "hard-control")
    return sims.capture_color_hard(target, sims.SHIFTED_TIFF_NAME,
                                   "hard-shifted")


def _color_patch_capture(root: Path, sims: object, sims_dir: Path,
                         colour: object,
                         patch_shift_px: int | None = None) -> object:
    """The colour local-head patch capture, built the test's own way.

    The raster builder lives in the suite's conftest, so the instrument
    imports it rather than restating it: a second copy of a stimulus is
    a second stimulus, and the whole point of measuring here is to say
    something about the one the module pins.  `patch_shift_px` sweeps
    the ONE magnitude the module has to choose, by setting the constant
    the builder reads — so a swept render and the pinned render come out
    of the same code.
    """
    import tifffile

    from holo3.tests import conftest as h3_conftest

    shift = (h3_conftest.COLOR_PATCH_SHIFT_PX if patch_shift_px is None
             else int(patch_shift_px))
    target = (sims_dir / "local-patch"
              / f"sim-color-local-patch-s{shift:d}-1200dpi.tiff")
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        h3_conftest.COLOR_PATCH_SHIFT_PX = shift
        tifffile.imwrite(target, h3_conftest._color_patch_raster(
            tifffile.imread(colour.tiff)))
    return sims.SimCapture(
        name="color-local-patch", format_ref=colour.format_ref,
        dpi=colour.dpi, rot_k=0, tiff=target,
        tiff_sha256=sims.sha256_file(target), payload=colour.payload,
        payload_sha256=colour.payload_sha256,
        payload_bytes=colour.payload_bytes, emit_dir=colour.emit_dir)


def _probe_fits(record: list) -> object:
    """Wrap the per-plane fit so refused fits are visible too.

    A fit that publishes nothing is the interesting case (that is what a
    clean sim must do), and a refusal leaves no fact behind — so the
    instrument watches the fitter itself.
    """
    from holo3.plugins import fields

    original = fields.fit_page

    def wrapped(*args, **kwargs):
        fits = original(*args, **kwargs)
        for plane, fit in enumerate(fits):
            record.append({
                "plane": int(plane),
                "refused": fit is None,
                "n_sites": None if fit is None else int(fit.n_sites),
                "median_delta_dots": (None if fit is None
                                      else round(fit.median_delta_dots, 4)),
                "residual": None if fit is None else round(fit.residual, 4),
                "published": bool(fit is not None
                                  and fields.publishable(fit)),
                # PER-TIER ACCOUNTING.  Each tier's sites, weight mass
                # and measured effect -- the fit with that tier's
                # equations subtracted, differenced against the joint
                # fit.  Exact, and it needs no certificate headroom,
                # which is what makes it usable on a sim whose rescue
                # tiers close everything by themselves.
                "tiers": None if fit is None else fit.tiers,
                "gain_check": None if fit is None else fit.gain_check,
            })
        return fits

    fields.fit_page = wrapped
    return original


def _ablate_tier(name: str) -> None:
    """Silence one evidence tier for the length of one decode.

    Harness-side runtime composition, the standing rule: the ablation
    exists only inside this process and the tree does not move for it.
    The photometric tier is silenced by emptying its share of every
    window's partition, which is exactly "these sites contributed
    nothing" and leaves the other two tiers' sites untouched -- the
    attribution law still holds under every ablation.
    """
    import numpy as np

    from holo3.plugins import fields as fields_module
    from holo3.plugins import field_tiers

    if name == field_tiers.TIER_ANCHOR:
        fields_module.anchor_pass = lambda *a, **k: ((), (), ())
        return
    if name == field_tiers.TIER_BLIND:
        fields_module.blind_pass = lambda *a, **k: ((), (), ())
        return
    if name == field_tiers.TIER_PHOTOMETRIC:
        original = fields_module.window_sites

        def without_photometry(*args, **kwargs):
            site = original(*args, **kwargs)
            if site is None:
                return None
            import dataclasses as dc
            return dc.replace(site, partition=dc.replace(
                site.partition, photometric=np.zeros(0, np.int64)))

        fields_module.window_sites = without_photometry
        return
    raise SystemExit(f"h3_plane_fields: unknown tier {name!r}")


def _clamp_first() -> None:
    """Run the OTHER clamp order for one decode, harness-side.

    `fields.settle` subtracts the plane-common part and then clamps.
    This substitutes the reverse — clamp each plane, then subtract — so
    the order can be decided by a measured pair instead of by argument.
    Runtime composition, the standing rule: the tree does not move for a
    measurement.
    """
    from holo3.lib import plane_field
    from holo3.plugins import fields as fields_module

    def clamp_then_subtract(fields_by_plane: list) -> list:
        clipped = [None if field is None else plane_field.clamp(field)
                   for field in fields_by_plane]
        return fields_module.plane_relative(clipped)

    fields_module.settle = clamp_then_subtract


def _tighten_clamp(ceiling: float) -> None:
    """Lower MAX_DELTA_DOTS for one decode so the clamp actually bites.

    The order question — subtract the plane-common part before or after
    the clamp — is only a question when the clamp BINDS.  On the
    displaced sim with three tiers and the median form it does not
    (max |delta| 1.785 against a 2.0 ceiling), so the honest way to ask
    is to move the ceiling rather than the stimulus: same page, same
    evidence, same fit, one constant.
    """
    from holo3.lib import plane_field

    # `clamp`'s ceiling is a DEFAULT ARGUMENT, bound at def time, so
    # reassigning the module constant here does nothing at all — the
    # first attempt at this knob was inert and its two arms both ran at
    # the real 2.0 ceiling.  Substituting the function is what bites.
    original = plane_field.clamp

    def tight(delta_dots_xy, max_delta_dots=float(ceiling)):
        return original(delta_dots_xy, max_delta_dots)

    plane_field.clamp = tight


def _tally_blind(record: dict) -> None:
    """Count WHY the blind tier declines, per plane.

    The tier produced no observations at all on the displaced sim, and
    the guards it can decline at are distinguishable: too few rows in
    the window, a log loss that would not fit, or a sweep that never
    beat its own centre.  Guessing between them was already wrong once.

    A tree older than the three-tier fitter has no blind tier to tally,
    and comparing one tree against another is this driver's whole job —
    so an absent tier is "nothing to count here", not a crash.  It
    crashed exactly once, decoding a pre-anchortier checkout for a null
    proof, which is why the guard is here.
    """
    try:
        from holo3.plugins import field_tiers
    except ImportError:
        return
    from holo3.plugins import fields as fields_module

    real_offset = field_tiers.blind_offset
    real_pass = fields_module.blind_pass

    def counted_offset(sample, labels, split, radius, *args, **kwargs):
        out = real_offset(sample, labels, split, radius, *args, **kwargs)
        key = ("starved" if out is None
               else "no-improvement" if out[1] == 0.0 else "offset")
        record[key] = record.get(key, 0) + 1
        return out

    def counted_pass(sites, *args, **kwargs):
        for site in sites:
            n = int(site.partition.blind.size)
            record["windows"] = record.get("windows", 0) + 1
            record["blind_rows_min"] = min(
                record.get("blind_rows_min", n), n)
            record["blind_rows_max"] = max(
                record.get("blind_rows_max", n), n)
            if n < 2 * field_tiers.BLIND_MIN_PER_HALF:
                record["window-too-small"] = record.get(
                    "window-too-small", 0) + 1
        field_tiers.blind_offset = counted_offset
        try:
            return real_pass(sites, *args, **kwargs)
        finally:
            field_tiers.blind_offset = real_offset

    fields_module.blind_pass = counted_pass


def _dump_fields(fields: dict, run_dir: Path) -> list[dict]:
    """Save every standing field so its shape can be scored against the
    displacement the stimulus actually injected."""
    import numpy as np

    rows: list[dict] = []
    for key, field in sorted(fields.items()):
        # the level index BELONGS in the name: a colour page is fitted
        # once per lane (capture, level), and until 2026-08-31 all of a
        # page's lanes wrote the same file, so every shape score was
        # silently taken on whichever lane sorted last
        path = run_dir / f"field-p{key[3]}-page{key[2]}-lvl{key[1]}.npy"
        np.save(path, field.delta_dots_xy)
        rows.append({
            "key": [str(key[0]), int(key[1]), int(key[2]), int(key[3])],
            "path": str(path),
            "n_certificates": int(field.n_certificates),
            "n_sites": int(field.n_sites),
            "residual": round(float(field.residual), 4),
            "median_delta_dots": round(float(field.median_delta_dots), 4),
            "tile_row_mean_dx": [
                round(float(value), 4)
                for value in field.delta_dots_xy[..., 0].mean(axis=1)],
        })
    return rows


def field_truth(field_path: Path, tiles_y: int, cell_dots: int,
                amplitude_dots: float, cycles: float) -> dict[str, object]:
    """Score a dumped field against the injected displacement."""
    import numpy as np

    delta = np.load(field_path)
    tile_dots = 64 * cell_dots
    dots_h = tiles_y * tile_dots
    rows = np.arange(dots_h, dtype=np.float64)
    injected = np.round(
        amplitude_dots * np.sin(2.0 * np.pi * cycles * rows / dots_h))
    per_tile = injected.reshape(tiles_y, tile_dots).mean(axis=1)
    fitted = delta[..., 0].mean(axis=1)
    order_a = np.argsort(np.argsort(per_tile))
    order_b = np.argsort(np.argsort(fitted))
    return {
        "injected_tile_row_dots": [round(float(v), 4) for v in per_tile],
        "fitted_tile_row_dots": [round(float(v), 4) for v in fitted],
        "pearson": round(float(np.corrcoef(per_tile, fitted)[0, 1]), 4),
        "spearman": round(float(np.corrcoef(order_a, order_b)[0, 1]), 4),
        "amplitude_ratio": round(
            float(np.abs(fitted).max() / max(np.abs(per_tile).max(), 1e-9)),
            4),
        "sign_agreement": round(float(np.mean(
            np.sign(fitted[np.abs(per_tile) > 0.25])
            == np.sign(per_tile[np.abs(per_tile) > 0.25]))), 4),
    }


def _drop_rows(engine: object, names: tuple[str, ...]) -> None:
    """Take rows out of the schedule entirely, for arm attribution.

    A row that is not in `DESCRIPTORS` is never born, never priced and
    never fired, so what a decode loses when one is dropped is that
    row's own yield and nothing else.  Instrument-only: the tree under
    test is unmodified, and a dropped row is named in the record.
    """
    if not names:
        return
    unknown = sorted(set(names) - set(engine.DESCRIPTOR_BY_NAME))
    if unknown:
        raise SystemExit(f"no such row: {unknown}")
    engine.DESCRIPTORS = tuple(descriptor for descriptor in engine.DESCRIPTORS
                               if descriptor.name not in names)
    engine.DESCRIPTOR_BY_NAME = {descriptor.name: descriptor
                                 for descriptor in engine.DESCRIPTORS}


def decode(root: Path, sims_dir: Path, sim: str, workers: int,
           plane_fields: bool, run_dir: Path, out_path: Path,
           probe_fits: bool = False, amplitude_dots: float | None = None,
           noise_sd: float | None = None,
           ablate: str | None = None,
           clamp_first: bool = False,
           max_delta_dots: float | None = None,
           drop: tuple[str, ...] = (),
           patch_shift_px: int | None = None) -> dict[str, object]:
    capture = capture_for(root, sims_dir, sim, amplitude_dots, noise_sd,
                          patch_shift_px)
    from holo3 import cli, data, engine

    _drop_rows(engine, drop)
    fits: list = []
    if probe_fits:
        _probe_fits(fits)
    if ablate:
        _ablate_tier(ablate)
    if clamp_first:
        _clamp_first()
    if max_delta_dots is not None:
        _tighten_clamp(max_delta_dots)
    blind_tally: dict = {}
    _tally_blind(blind_tally)

    payload_path = run_dir / "payload.bin"
    argv = ["decode", str(capture.tiff), "--dpi", str(int(capture.dpi)),
            "--format", capture.format_ref, "--out", str(payload_path),
            "--workers", str(workers), "--run-dir", str(run_dir / "run"),
            "--complete"]
    if plane_fields:
        argv.append("--plane-fields")
    captured: dict[str, object] = {}
    original = engine.decode

    def instrumented(request: object,
                     events: list | None = None) -> object:
        collected: list = [] if events is None else events
        instance = engine._Engine(request, collected)
        result = instance.run()
        captured["certificates"] = dict(instance._certificates)
        captured["jobs"] = tuple(
            event.plugin for event in collected
            if isinstance(event, data.JobDone))
        # a tree without the field cell is the null proof's other half
        captured["fields"] = dict(getattr(instance, "_plane_fields", {}))
        return result

    out = io.StringIO()
    err = io.StringIO()
    engine.decode = instrumented
    try:
        with (contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
            exit_code = cli.main(argv)
    finally:
        engine.decode = original
    certificates = captured.get("certificates", {})
    signature = [
        [list(key), bytes(certificate.user_bits).hex()]
        for key, certificate in sorted(certificates.items())]
    payload = (payload_path.read_bytes() if payload_path.is_file()
               else None)
    jobs: dict[str, int] = {}
    for plugin in captured.get("jobs", ()):
        jobs[plugin] = jobs.get(plugin, 0) + 1
    streams: dict[str, int] = {}
    for key, _certificate in sorted(certificates.items()):
        streams[str(key[3])] = streams.get(str(key[3]), 0) + 1
    report_path = cli.run_dir_for(run_dir / "run") / "report.json"
    plugin_rows: dict[str, dict] = {}
    if report_path.is_file():
        rows = json.loads(report_path.read_text())
        for plugin_row in rows.get("scheduler", {}).get("plugins", ()):
            plugin_rows[plugin_row["plugin"]] = {
                "jobs": plugin_row["jobs"],
                "certificates": plugin_row["certificates"]}
    record = {
        "tree": str(root),
        "sim": sim,
        "workers": workers,
        "plane_fields": plane_fields,
        "dropped_rows": list(drop),
        "stimulus": {"amplitude_dots": amplitude_dots,
                     "noise_sd": noise_sd,
                     "patch_shift_px": patch_shift_px},
        "exit_code": exit_code,
        "payload_sha256": (hashlib.sha256(payload).hexdigest()
                           if payload is not None else None),
        "payload_bytes": None if payload is None else len(payload),
        "expected_payload_sha256": capture.payload_sha256,
        "n_certificates": len(certificates),
        "certificate_signature_sha256": hashlib.sha256(
            json.dumps(signature, sort_keys=True).encode()).hexdigest(),
        "certificate_addresses": [row[0] for row in signature],
        "jobs": dict(sorted(jobs.items())),
        "certificates_by_stream": dict(sorted(streams.items())),
        "plugin_rows": dict(sorted(plugin_rows.items())),
        "fits": fits,
        "blind_tally": blind_tally,
        "standing_fields": _dump_fields(captured.get("fields", {}),
                                        run_dir),
        "stderr_tail": err.getvalue().splitlines()[-8:],
    }
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


def compare(left: Path, right: Path) -> int:
    a = json.loads(left.read_text())
    b = json.loads(right.read_text())
    verdicts: list[tuple[str, bool, str]] = []
    for field in ("sim", "workers", "payload_sha256", "payload_bytes",
                  "n_certificates", "certificate_signature_sha256"):
        verdicts.append((field, a[field] == b[field],
                         f"{a[field]!r} vs {b[field]!r}"))
    only_a = [row for row in a["certificate_addresses"]
              if row not in b["certificate_addresses"]]
    only_b = [row for row in b["certificate_addresses"]
              if row not in a["certificate_addresses"]]
    verdicts.append(("certificates only in left", not only_a,
                     json.dumps(only_a[:12])))
    verdicts.append(("certificates only in right", not only_b,
                     json.dumps(only_b[:12])))
    failed = 0
    for name, ok, detail in verdicts:
        print(f"{'OK  ' if ok else 'DIFF'}  {name}: {detail}")
        failed += 0 if ok else 1
    print(f"left  jobs: {json.dumps(a['jobs'], sort_keys=True)}")
    print(f"right jobs: {json.dumps(b['jobs'], sort_keys=True)}")
    print("IDENTICAL" if not failed else f"{failed} DIFFERENCES")
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="h3_plane_fields")
    commands = parser.add_subparsers(dest="command", required=True)
    sims = commands.add_parser("sims")
    sims.add_argument("--tree", type=Path, required=True)
    sims.add_argument("--sims-dir", type=Path, required=True)
    run = commands.add_parser("decode")
    run.add_argument("--tree", type=Path, required=True)
    run.add_argument("--sims-dir", type=Path, required=True)
    run.add_argument("--sim", choices=("k", "color", "color-patch",
                                       "hard-faint", "hard-shifted",
                                       "hard-control"), required=True)
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--plane-fields", dest="plane_fields",
                     action="store_true")
    run.add_argument("--run-dir", dest="run_dir", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--probe-fits", dest="probe_fits",
                     action="store_true")
    run.add_argument("--amplitude-dots", dest="amplitude_dots", type=float)
    run.add_argument("--noise-sd", dest="noise_sd", type=float)
    run.add_argument("--max-delta-dots", dest="max_delta_dots",
                     type=float, default=None,
                     help="lower the field's clamp for this decode so "
                          "the order question has something to bite on")
    run.add_argument("--clamp-first", dest="clamp_first",
                     action="store_true",
                     help="clamp each plane BEFORE subtracting the "
                          "plane-common part (the other order)")
    run.add_argument("--ablate-tier", dest="ablate", default=None,
                     choices=("photometric", "anchor", "blind"),
                     help="silence one evidence tier for this decode")
    run.add_argument("--patch-shift-px", dest="patch_shift_px", type=int,
                     help="colour-patch plane displacement in scan "
                          "pixels (2 px = 1 printed dot)")
    run.add_argument("--drop", dest="drop", action="append", default=[],
                     metavar="ROW",
                     help="remove a scheduler row from this decode "
                          "(repeatable) — arm attribution")
    diff = commands.add_parser("compare")
    diff.add_argument("left", type=Path)
    diff.add_argument("right", type=Path)
    truth = commands.add_parser("fieldtruth")
    truth.add_argument("field", type=Path)
    truth.add_argument("--tiles-y", type=int, default=10)
    truth.add_argument("--cell-dots", type=int, default=3)
    truth.add_argument("--amplitude-dots", type=float, default=2.0)
    truth.add_argument("--cycles", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.command == "sims":
        report = build_sims(args.tree.resolve(), args.sims_dir.resolve())
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if set(report.values()) == {"frozen-sha-ok"} else 1
    if args.command == "compare":
        return compare(args.left, args.right)
    if args.command == "fieldtruth":
        print(json.dumps(field_truth(args.field, args.tiles_y,
                                     args.cell_dots, args.amplitude_dots,
                                     args.cycles),
                         indent=2, sort_keys=True))
        return 0
    args.run_dir.mkdir(parents=True, exist_ok=True)
    record = decode(args.tree.resolve(), args.sims_dir.resolve(), args.sim,
                    args.workers, args.plane_fields, args.run_dir,
                    args.out, args.probe_fits, args.amplitude_dots,
                    args.noise_sd, args.ablate, args.clamp_first,
                    args.max_delta_dots, tuple(args.drop),
                    args.patch_shift_px)
    print(json.dumps({key: record[key] for key in (
        "tree", "sim", "workers", "plane_fields", "dropped_rows",
        "exit_code", "payload_sha256", "n_certificates",
        "certificates_by_stream", "certificate_signature_sha256",
        "plugin_rows", "fits")},
        indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
