"""Yield-identity and work-delta instrument for the done-geometry gate.

Decodes every sim fixture in whatever holo3 tree is on `sys.path` and
writes one JSON record per case: the payload sha, an exact certificate
signature (address + user bits), the per-plugin job counts and the
engine's own scheduling counters.  Two trees are compared by diffing the
two JSON files:

    PYTHONPATH=<baseline tree> python src/holo/receiver/measure/donegeo_parity.py \
        --out baseline.json
    PYTHONPATH=<work tree>     python src/holo/receiver/measure/donegeo_parity.py \
        --out work.json
    python src/holo/receiver/measure/donegeo_parity.py --compare baseline.json work.json

The certificate signature is the gate: identical payloads with a moved
certificate set is a yield change, not a scheduling change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

CASES: tuple[tuple[str, str, int, bool], ...] = (
    # label, fixture, workers, complete
    ("k-w1", "k", 1, True),
    ("k-w8", "k", 8, False),
    ("color-w1", "color", 1, True),
    ("color-w8", "color", 8, False),
    ("degraded-w1", "k-degraded", 1, True),
    ("mixed-w1", "k-mixed", 1, True),
    ("mixed-w8", "k-mixed", 8, False),
    ("null-w1", "k-null", 1, True),
)


def _tree_root() -> Path:
    import holo.receiver

    return Path(holo.receiver.__file__).resolve().parent


def fixtures(root: Path) -> dict[str, tuple[tuple[Path, float], ...]]:
    """Materialise the sim captures the pytest fixtures use, unchanged."""
    import numpy as np
    import tifffile

    from holo.receiver.tests import _h3_sims
    from holo.receiver.tests import conftest as h3_conftest

    reason = _h3_sims.producer_unavailable_reason()
    if reason is not None:
        raise SystemExit(reason)
    root.mkdir(parents=True, exist_ok=True)
    k_dir = h3_conftest._materialise("k", _h3_sims.make_k,
                                     _h3_sims.EXPECTED_K, root)
    color_dir = h3_conftest._materialise("color", _h3_sims.make_color,
                                         _h3_sims.EXPECTED_COLOR, root)
    k_capture = _h3_sims.capture_k(k_dir)
    color_capture = _h3_sims.capture_color(color_dir)
    mixed_dir = h3_conftest._materialise(
        "k-mixed",
        lambda staging: _h3_sims.make_k_mixed(k_capture.tiff, staging),
        _h3_sims.EXPECTED_MIXED, root)
    mixed_a, mixed_b = _h3_sims.capture_k_mixed(mixed_dir, k_capture)

    degraded = root / "degraded" / "sim-k-degraded-1200dpi.tiff"
    if not degraded.is_file():
        degraded.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(degraded, h3_conftest._degraded_raster(
            tifffile.imread(k_capture.tiff)))
    null = root / "null" / "sim-k-null-1200dpi.tiff"
    if not null.is_file():
        null.parent.mkdir(parents=True, exist_ok=True)
        shape = tifffile.imread(k_capture.tiff).shape
        rng = np.random.default_rng(h3_conftest.NULL_RASTER_SEED)
        noise = rng.normal(0.0, h3_conftest.NULL_RASTER_NOISE_SD, size=shape)
        paper = np.clip(h3_conftest.NULL_RASTER_PAPER + noise, 0,
                        255).astype(np.uint8)
        tifffile.imwrite(null, paper)

    dpi = _h3_sims.DPI
    return {
        "k": ((k_capture.tiff, dpi),),
        "color": ((color_capture.tiff, dpi),),
        "k-degraded": ((degraded, dpi),),
        "k-null": ((null, dpi),),
        "k-mixed": ((mixed_a.tiff, dpi), (mixed_b.tiff, _h3_sims.MIXED_DPI_B)),
    }


def _format_ref(fixture: str) -> str:
    from holo.receiver.tests import _h3_sims

    return (_h3_sims.COLOR_FORMAT_REF if fixture == "color"
            else _h3_sims.K_FORMAT_REF)


def certificate_signature(certificates: dict) -> tuple[str, int]:
    import numpy as np

    digest = hashlib.sha256()
    for key in sorted(certificates):
        digest.update(repr(tuple(key)).encode())
        digest.update(np.asarray(certificates[key].user_bits,
                                 np.uint8).tobytes())
    return digest.hexdigest(), len(certificates)


def run_case(label: str, fixture: str, workers: int, complete: bool,
             scans: tuple[tuple[Path, float], ...], root: Path) -> dict:
    from holo.receiver import data, engine

    run_dir = root / "runs" / label
    request = data.DecodeRequest(
        scans=tuple(path for path, _dpi in scans),
        dpis=tuple(float(dpi) for _path, dpi in scans),
        format_ref=_format_ref(fixture), max_pages=1, workers=workers,
        complete=complete, no_close=False, diag_port=None, run_dir=run_dir)
    events: list = []
    started = time.monotonic()
    instance = engine._Engine(request, events)
    result = instance.run()
    wall_s = time.monotonic() - started
    signature, n_certs = certificate_signature(instance._certificates)
    stat = [event for event in events if isinstance(event, data.EngineStat)]
    counters = ({} if not stat else {
        "stale_skips": stat[-1].stale_skips,
        "retired": stat[-1].retired,
        "wakes": stat[-1].wakes})
    outcomes: dict[str, int] = {}
    for outcome in instance._attempt_outcomes.values():
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {
        "label": label,
        "fixture": fixture,
        "workers": workers,
        "complete": complete,
        "status": result.status,
        "payload_sha256": result.payload_sha256,
        "n_bytes": None if result.payload is None else len(result.payload),
        "certified": n_certs,
        "certificate_signature": signature,
        "certificate_keys_sha256": hashlib.sha256(
            repr(sorted(map(tuple, instance._certificates))).encode(),
        ).hexdigest(),
        "jobs": {row.plugin: row.jobs for row in result.plugin_rows
                 if row.jobs},
        "poses": {row.plugin: row.poses for row in result.plugin_rows
                  if row.poses},
        "counters": counters,
        "attempt_outcomes": dict(sorted(outcomes.items())),
        "wall_s": round(wall_s, 2),
    }


def collect(root: Path, labels: tuple[str, ...] | None) -> dict:
    scans = fixtures(root)
    rows = []
    for label, fixture, workers, complete in CASES:
        if labels is not None and label not in labels:
            continue
        rows.append(run_case(label, fixture, workers, complete,
                             scans[fixture], root))
        print(f"  {label}: {rows[-1]['status']} "
              f"certs={rows[-1]['certified']} "
              f"jobs={rows[-1]['jobs']}", flush=True)
    return {"tree": str(_tree_root()), "cases": rows}


def compare(baseline: dict, work: dict) -> int:
    rows = {case["label"]: case for case in baseline["cases"]}
    problems = 0
    for case in work["cases"]:
        base = rows.get(case["label"])
        print(f"\n== {case['label']} ==")
        if base is None:
            print("  MISSING from baseline")
            problems += 1
            continue
        # a multi-worker run interleaves nondeterministically: its payload
        # is the invariant, its certificate set and job counts are not
        serial = case["workers"] == 1
        fields = (("status", "payload_sha256", "certified",
                   "certificate_signature", "certificate_keys_sha256")
                  if serial else ("status", "payload_sha256"))
        for field in fields:
            if base[field] != case[field]:
                print(f"  YIELD DIFFERENCE {field}: "
                      f"{base[field]} -> {case[field]}")
                problems += 1
        if serial and base["certificate_signature"] \
                == case["certificate_signature"]:
            print(f"  yield identical: {case['certified']} certificates, "
                  f"payload {case['payload_sha256']}")
        for plugin in sorted(set(base["jobs"]) | set(case["jobs"])):
            before = base["jobs"].get(plugin, 0)
            after = case["jobs"].get(plugin, 0)
            if before == after:
                continue
            arrow = "GREW" if after > before else "shrank"
            print(f"  jobs {plugin}: {before} -> {after} ({arrow})")
            if after > before and serial:
                problems += 1
        for key in ("stale_skips", "retired", "wakes"):
            before = base["counters"].get(key)
            after = case["counters"].get(key)
            if before != after:
                print(f"  counter {key}: {before} -> {after}")
    print(f"\n{problems} problem(s)")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fixture-root", type=Path,
                        default=Path("/tmp/holo3-donegeo-fixtures"))
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args(argv)
    if args.compare is not None:
        baseline = json.loads(args.compare[0].read_text())
        work = json.loads(args.compare[1].read_text())
        return 1 if compare(baseline, work) else 0
    print(f"tree: {_tree_root()}", flush=True)
    record = collect(args.fixture_root,
                     tuple(args.only) if args.only else None)
    if args.out is not None:
        args.out.write_text(json.dumps(record, indent=2, sort_keys=True))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
