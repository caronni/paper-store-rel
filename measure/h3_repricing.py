#!/usr/bin/env python
"""COLOUR-LANE REPRICING — one sim decode, its bits, and its job order.

    PYTHONPATH=src:. env/bin/python measure/h3_repricing.py \\
        --tree . --sim color --workers 1 --complete \\
        --fixtures build/h3-repricing/fixtures \\
        --run-root build/h3-repricing/runs/color-w1-head \\
        --out build/h3-repricing/color-w1-head.json

WHY. The colour lane's scheduling defect (assembly priced as a head
re-fit) is invisible in a payload sha: the run still closes, it simply
closes with every colour certificate landing after the last placement.
This instrument runs holo3's OWN decode path against a CHOSEN tree
(``--tree``, so a pristine checkout and the working tree can be
compared without a rebuild) and records three things per run:

  * the outcome — payload sha256, certificate count, and a sha over the
    sorted (address, user bits) pairs, so identity is one comparison;
  * the scheduler — per-plugin job counts, and the colour lane's fire
    log (stage + cost + cpu per fire, from JobDone);
  * the interleave — the JobDone index of the last ``place`` job and of
    the first job that minted a certificate, which is what the defect
    actually costs (colour payload work strictly after placement).

Sim captures come from the receiver's test fixture builders
(``holo.receiver.tests``) through the persistent cache directory
``--fixtures``, so both trees decode the byte-identical capture.
Nothing here reimplements a decode: the argv is parsed by
``holo.receiver.cli``'s own parser and run through ``engine._Engine``
the way ``cli._decode`` does.

THE TREE. holo3 is the record's name; the module is ``holo.receiver``
under ``<tree>/src`` since the 2026-09-05 move (2099338) — there is no
``holo3`` package any more.  ``--tree`` puts ``<tree>/src`` FIRST on
``sys.path`` (ahead of whatever PYTHONPATH says), and before any
capture or decode the tool resolves ``holo.receiver.__file__`` and
refuses unless it lies under that ``<tree>/src``: a comparison whose
two runs silently imported the same receiver measures nothing.  The
record carries the resolved file as ``holo3_file``.

MEMORY: one decode per process; the process exits when the decode does.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

import numpy as np

SIMS = ("k", "color", "k-degraded", "k-mixed", "color-hard",
        "color-hard-shifted", "color-hard-pair")


def _load_tree(tree: Path) -> Path:
    """Put ``<tree>/src`` first on ``sys.path``; return that directory.

    ``holo`` lives under ``src/``, so inserting the tree's ROOT (as this
    tool did before 2026-10-03) left PYTHONPATH to decide which receiver
    ran and made ``--tree`` inert.  The root follows ``src`` for any
    top-level sibling (``measure``) a caller imports; ``src`` wins.
    """
    root = Path(tree).resolve()
    src = root / "src"
    if not (src / "holo" / "receiver").is_dir():
        raise SystemExit(f"h3_repricing: --tree {root} has no "
                         f"src/holo/receiver")
    for entry in (str(root), str(src)):
        while entry in sys.path:
            sys.path.remove(entry)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(src))
    return src


def _receiver_file(src: Path) -> Path:
    """``holo.receiver.__file__``, refused unless it lies under ``src``.

    Called BEFORE any capture or decode: a ``holo`` already imported
    from another tree (``sys.modules`` wins over ``sys.path``) would
    otherwise cost a whole decode before anyone noticed.
    """
    module = importlib.import_module("holo.receiver")
    location = Path(module.__file__).resolve()
    if not location.is_relative_to(Path(src).resolve()):
        raise SystemExit(f"h3_repricing: holo.receiver resolved to "
                         f"{location}, not under the chosen tree's {src}")
    return location


def _capture(sim: str, fixtures: Path) -> tuple:
    """One or more sim captures, from the shared fixture cache.

    Both trees read the same cache directory, so a comparison is never
    confounded by a re-render.
    """
    from holo.receiver.tests import _h3_fixture_build, _h3_sims

    # the harness's OWN cache key, never a copy of it: a re-derivation
    # here silently forks the cache the moment a sim is added
    root = Path(fixtures).resolve() / _h3_fixture_build._cache_key()

    def materialise(name: str, expected: dict, builder) -> Path:
        outdir = root / name
        if _h3_sims.verify(outdir, expected) is not None:
            builder(outdir)
            problem = _h3_sims.verify(outdir, expected)
            if problem is not None:
                raise SystemExit(f"fixture build failed: {problem}")
        return outdir

    base = _h3_sims.capture_k(
        materialise("k", _h3_sims.EXPECTED_K, _h3_sims.make_k))
    if sim == "k":
        return (base,)
    if sim == "color":
        return (_h3_sims.capture_color(
            materialise("color", _h3_sims.EXPECTED_COLOR,
                        _h3_sims.make_color)),)
    if sim == "k-mixed":
        outdir = materialise(
            "k-mixed", _h3_sims.EXPECTED_MIXED,
            lambda staging: _h3_sims.make_k_mixed(base.tiff, staging))
        return _h3_sims.capture_k_mixed(outdir, base)
    if sim.startswith("color-hard"):
        outdir = materialise("color-hard", _h3_sims.EXPECTED_HARD,
                             _h3_sims.make_color_hard_pair)
        control = _h3_sims.capture_color_hard(
            outdir, _h3_sims.CONTROL_TIFF_NAME, "hard-control")
        shifted = _h3_sims.capture_color_hard(
            outdir, _h3_sims.SHIFTED_TIFF_NAME, "hard-shifted")
        if sim == "color-hard":
            return (control,)
        if sim == "color-hard-shifted":
            return (shifted,)
        return (control, shifted)
    return (_degraded_capture(base, root / "degraded"),)


def _degraded_capture(base, outdir: Path):
    """conftest's degraded K raster, rebuilt outside the pytest fixture."""
    import tifffile

    from holo.receiver.tests import _h3_sims, conftest as h3_conftest

    target = Path(outdir) / "sim-k-degraded-1200dpi.tiff"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(
            target, h3_conftest._degraded_raster(tifffile.imread(base.tiff)))
    return _h3_sims.SimCapture(
        name="k-degraded", format_ref=base.format_ref, dpi=base.dpi, rot_k=0,
        tiff=target, tiff_sha256=_h3_sims.sha256_file(target),
        payload=base.payload, payload_sha256=base.payload_sha256,
        payload_bytes=base.payload_bytes, emit_dir=None)


def _certificate_signature(certificates: dict) -> str:
    digest = hashlib.sha256()
    for key in sorted(certificates):
        digest.update(repr(tuple(key)).encode())
        digest.update(np.asarray(certificates[key].user_bits,
                                 np.uint8).tobytes())
    return digest.hexdigest()


def _fire_log(events: tuple, plugin: str) -> list[dict]:
    from holo.receiver import data

    rows = []
    index = 0
    for event in events:
        if not isinstance(event, data.JobDone):
            continue
        index += 1
        if event.plugin != plugin:
            continue
        rows.append({"job_index": index, "subject": repr(event.subject),
                     "cost": int(event.cost),
                     "cpu_s": round(float(event.cpu_s), 3),
                     "n_certificates": int(event.n_certificates)})
    return rows


def _interleave(events: tuple) -> dict:
    from holo.receiver import data

    index = 0
    total = 0
    last_place = 0
    first_cert = None
    certs_before_last_place = 0
    seen_certs = 0
    place_indices = []
    cert_indices = []
    for event in events:
        if not isinstance(event, data.JobDone):
            continue
        index += 1
        total = index
        if event.plugin == "place":
            last_place = index
            place_indices.append(index)
        if event.n_certificates:
            seen_certs += int(event.n_certificates)
            cert_indices.append(index)
            if first_cert is None:
                first_cert = index
    for job_index in cert_indices:
        if job_index < last_place:
            certs_before_last_place += 1
    return {"n_jobs": total, "last_place_job": last_place,
            "first_certificate_job": first_cert,
            "n_place_jobs": len(place_indices),
            "n_certifying_jobs": len(cert_indices),
            "certifying_jobs_before_last_place": certs_before_last_place,
            "certificates_total": seen_certs,
            "placement_at_certificate_fraction": _latency(events)}


def _latency(events: tuple) -> dict:
    """How far into PLACEMENT each quarter of the certificates landed.

    The defect's own measurement: colour payload work that waits for
    placement to be exhausted shows up here as every fraction landing
    at ~100% of the place jobs, against the K path's steady climb.
    """
    from holo.receiver import data

    jobs = [event for event in events if isinstance(event, data.JobDone)]
    n_place = sum(1 for job in jobs if job.plugin == "place")
    total = sum(job.n_certificates for job in jobs)
    marks: dict[str, float] = {}
    seen_place = 0
    seen_certs = 0
    for job in jobs:
        if job.plugin == "place":
            seen_place += 1
        seen_certs += job.n_certificates
        for fraction in (0.25, 0.5, 0.75, 1.0):
            key = f"{fraction:.2f}"
            if key not in marks and total and seen_certs >= fraction * total:
                marks[key] = round(100.0 * seen_place / max(1, n_place), 1)
    return marks


def _watch_color_lane(records: list) -> None:
    """Read-only probe: what the colour lane faced at each fire.

    Wraps ``color_region.prepare_color`` and records, per fire, how many
    windows the lane holds and how many of them already carry a standing
    colour evidence row.  The difference is the ASSEMBLY DEBT — the
    windows for which this fire is first work, not a re-fit.
    """
    import dataclasses

    from holo.receiver import engine
    from holo.receiver.plugins import color_region

    original = color_region.COLOR_DESCRIPTOR.prepare

    def probed(store: object, subject: tuple, stage: str):
        capture_id, level_index, page = subject
        wids = store.lane_page_windows(capture_id, level_index, page)
        with_rows = 0
        for wid in wids:
            placement = store.placement(wid)
            if placement is None:
                continue
            if store.color_row((capture_id, level_index, page,
                                placement.patch_ordinal)) is not None:
                with_rows += 1
        # the lane's OWN debt, where the tree has the accessor: windows
        # no fire has covered. Not the same as "windows without an
        # evidence row" — a covered window that is fully certified, or
        # whose emission mask is empty, has no row to show for it
        store_debt = (len(store.color_lane_debt(
            (capture_id, level_index, page)))
            if hasattr(store, "color_lane_debt") else None)
        job = original(store, subject, stage)
        if job is not None:
            records.append({"subject": repr(tuple(subject)), "stage": stage,
                            "n_windows": len(wids),
                            "n_with_rows": with_rows,
                            "rowless_windows": len(wids) - with_rows,
                            "store_debt": store_debt})
        return job

    probed_descriptor = dataclasses.replace(
        color_region.COLOR_DESCRIPTOR, prepare=probed)
    engine.DESCRIPTORS = tuple(
        probed_descriptor if descriptor.name == "color" else descriptor
        for descriptor in engine.DESCRIPTORS)
    engine.DESCRIPTOR_BY_NAME["color"] = probed_descriptor


def _plugin_jobs(events: tuple) -> dict:
    from holo.receiver import data

    counts: dict[str, int] = {}
    for event in events:
        if isinstance(event, data.JobDone):
            counts[event.plugin] = counts.get(event.plugin, 0) + 1
    return dict(sorted(counts.items()))


def _plugin_cpu(events: tuple) -> dict:
    from holo.receiver import data

    totals: dict[str, float] = {}
    for event in events:
        if isinstance(event, data.JobDone):
            totals[event.plugin] = totals.get(event.plugin, 0.0) + float(
                event.cpu_s)
    return {name: round(value, 2) for name, value in sorted(totals.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="h3_repricing")
    parser.add_argument("--tree", type=Path, default=Path("."))
    parser.add_argument("--sim", choices=SIMS, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--run-root", dest="run_root", type=Path,
                        required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--no-close", dest="no_close", action="store_true")
    args = parser.parse_args(argv)

    receiver_file = _receiver_file(_load_tree(args.tree))
    captures = _capture(args.sim, args.fixtures)

    from holo.receiver import cli, engine

    lane_probe: list = []
    _watch_color_lane(lane_probe)

    run_dir = Path(args.run_root).resolve()
    if run_dir.exists():
        import shutil

        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    out_path = run_dir / "payload.bin"
    argv_decode = (
        ["decode"]
        + [str(capture.tiff) for capture in captures]
        + [part for capture in captures
           for part in ("--dpi", str(int(capture.dpi)))]
        + ["--format", captures[0].format_ref, "--out", str(out_path),
           "--workers", str(args.workers), "--run-dir", str(run_dir)])
    if args.complete:
        argv_decode.append("--complete")
    if args.no_close:
        argv_decode.append("--no-close")
    parsed = cli._build_parser().parse_args(argv_decode)
    request = cli._request(parsed)
    events: list = []
    instance = engine._Engine(request, events)
    result = instance.run()
    certificates = dict(instance._certificates)
    payload = result.payload
    record = {
        "tree": str(Path(args.tree).resolve()),
        "holo3_file": str(receiver_file),
        "sim": args.sim,
        "workers": args.workers,
        "complete": bool(args.complete),
        "status": result.status,
        "payload_sha256": (hashlib.sha256(payload).hexdigest()
                           if payload is not None else None),
        "n_payload_bytes": None if payload is None else len(payload),
        "certified": len(certificates),
        "certificate_signature_sha256": _certificate_signature(certificates),
        "certificate_addresses": [list(key) for key in sorted(certificates)],
        "plugin_jobs": _plugin_jobs(tuple(events)),
        "plugin_cpu_s": _plugin_cpu(tuple(events)),
        "interleave": _interleave(tuple(events)),
        "color_fires": _fire_log(tuple(events), "color"),
        "color_lane_probe": lane_probe,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(record, indent=1) + "\n")
    summary = record["interleave"]
    print(f"{args.sim} w{args.workers} "
          f"complete={bool(args.complete)} -> {result.status} "
          f"certs={record['certified']} "
          f"payload={record['payload_sha256']}")
    print(f"  jobs {record['plugin_jobs']}")
    print(f"  cpu  {record['plugin_cpu_s']}")
    print(f"  last place job {summary['last_place_job']} of "
          f"{summary['n_jobs']}; first certifying job "
          f"{summary['first_certificate_job']}; certifying jobs before "
          f"the last place job {summary['certifying_jobs_before_last_place']}")
    for fire, probe in zip(record["color_fires"],
                           record["color_lane_probe"]):
        print(f"  color fire @job {fire['job_index']} "
              f"{probe['subject']} stage {probe['stage']} "
              f"cost {fire['cost']} cpu {fire['cpu_s']}s "
              f"windows {probe['n_windows']} rowless "
              f"{probe['rowless_windows']} store-debt "
              f"{probe['store_debt']}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("HOLO3_RUN_SLOW_TESTS", "1")
    raise SystemExit(main())
