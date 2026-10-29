"""Resume instrument: round-trip, add-a-sheet, and worker parity.

Every case decodes a sim to completion into a run dir, then decodes
again from that run dir's `facts.npz` with `--resume`, and records both
sides: payload sha, exact certificate signature, per-plugin job counts,
snapshot size, and the status row the run's operator sees.  The point
of the resumed run is that it is residue-only, so the job-count ratio
(resumed / original, per plugin) is reported rather than gated — no
invented threshold.

    python measure/resume_parity.py --out resume.json
    python measure/resume_parity.py --out resume.json --only roundtrip-k

Cases:
  roundtrip-k / roundtrip-color  the same captures re-declared; the
      close must verify byte-exact against the original payload.
  add-a-sheet  capture A of the two-capture mixed sim alone, then a
      resume with A+B declared, against a from-scratch A+B decode.
      Payload identity is the gate; certificate-set identity is not
      (path dependence is accepted — the repeatability ruling).
  workers  the K resume replayed at workers 8; payload bytes only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from donegeo_parity import certificate_signature, fixtures


def _decode(root: Path, label: str, scans: tuple[tuple[Path, float], ...],
            format_ref: str, workers: int = 1,
            resume: Path | None = None) -> dict:
    from holo.receiver import data, engine, snapshot
    from holo.receiver.diag import model as diag_model, readout

    run_dir = root / "runs" / label
    request = data.DecodeRequest(
        scans=tuple(path for path, _dpi in scans),
        dpis=tuple(float(dpi) for _path, dpi in scans),
        format_ref=format_ref, max_pages=1, workers=workers, complete=True,
        no_close=False, diag_port=None, run_dir=run_dir, resume=resume)
    events: list = []
    started = time.monotonic()
    instance = engine._Engine(request, events)
    result = instance.run()
    wall_s = time.monotonic() - started
    signature, n_certs = certificate_signature(instance._certificates)
    state = run_dir / snapshot.NAME
    # the status a resumed run shows its operator: the tiles row counts
    # this run's own outcomes, so the replay has to be named beside them
    folded = diag_model.fold(diag_model.empty(), events)
    # what the frontier retired and WHY: on a resume the done gate is the
    # dominant exit, and `cause` is the only place it is nameable
    # (`getattr` so this instrument also reads a pre-cause tree)
    causes: dict[str, int] = {}
    for event in events:
        if isinstance(event, data.WorkerRetired):
            cause = getattr(event, "cause", "") or "unnamed"
            causes[cause] = causes.get(cause, 0) + 1
    return {
        "label": label,
        "retire_causes": dict(sorted(causes.items())),
        "workers": workers,
        "resumed_from": None if resume is None else str(resume),
        "status": result.status,
        "tiles_row": readout.six_row_status(folded)[4],
        "replayed": readout.status(folded)["replayed"],
        "payload_sha256": result.payload_sha256,
        "n_bytes": None if result.payload is None else len(result.payload),
        "certified": n_certs,
        "certificate_signature": signature,
        "jobs": {row.plugin: row.jobs for row in result.plugin_rows
                 if row.jobs},
        "state_path": str(state),
        "state_bytes": state.stat().st_size if state.is_file() else None,
        "wall_s": round(wall_s, 2),
    }


def _ratio(first: dict, second: dict) -> dict:
    rows = {}
    for plugin in sorted(set(first["jobs"]) | set(second["jobs"])):
        before = first["jobs"].get(plugin, 0)
        after = second["jobs"].get(plugin, 0)
        rows[plugin] = [before, after,
                        None if not before else round(after / before, 3)]
    total_before = sum(first["jobs"].values())
    total_after = sum(second["jobs"].values())
    rows["TOTAL"] = [total_before, total_after,
                     None if not total_before
                     else round(total_after / total_before, 3)]
    return rows


def roundtrip(root: Path, name: str, scans, format_ref: str) -> dict:
    from holo.receiver import snapshot

    first = _decode(root, f"{name}-first", scans, format_ref)
    state = Path(first["state_path"])
    second = _decode(root, f"{name}-resume", scans, format_ref,
                     resume=state)
    facts = snapshot.read(state)
    kinds: dict[str, int] = {}
    for fact in facts:
        name_of = type(fact).__name__
        kinds[name_of] = kinds.get(name_of, 0) + 1
    return {
        "case": f"roundtrip-{name}",
        "first": first,
        "resumed": second,
        "job_ratio": _ratio(first, second),
        "snapshot_facts": dict(sorted(kinds.items())),
        "payload_identical": (first["payload_sha256"]
                              == second["payload_sha256"]
                              and second["status"] == "verified"),
        "certificates_identical": (first["certificate_signature"]
                                   == second["certificate_signature"]),
    }


def add_a_sheet(root: Path, scans, format_ref: str) -> dict:
    a_only = scans[:1]
    both = scans
    first = _decode(root, "sheet-a", a_only, format_ref)
    resumed = _decode(root, "sheet-ab-resume", both, format_ref,
                      resume=Path(first["state_path"]))
    scratch = _decode(root, "sheet-ab-scratch", both, format_ref)
    return {
        "case": "add-a-sheet",
        "capture_a": first,
        "resumed_ab": resumed,
        "scratch_ab": scratch,
        "job_ratio_vs_scratch": _ratio(scratch, resumed),
        "certificates_grew": resumed["certified"] > first["certified"],
        "payload_identical": (resumed["payload_sha256"]
                              == scratch["payload_sha256"]
                              and resumed["status"] == "verified"),
        "certificates_identical_to_scratch": (
            resumed["certificate_signature"]
            == scratch["certificate_signature"]),
    }


def workers_parity(root: Path, name: str, scans, format_ref: str) -> dict:
    first = _decode(root, f"{name}-w-first", scans, format_ref)
    state = Path(first["state_path"])
    serial = _decode(root, f"{name}-resume-w1", scans, format_ref,
                     workers=1, resume=state)
    parallel = _decode(root, f"{name}-resume-w8", scans, format_ref,
                       workers=8, resume=state)
    return {
        "case": f"workers-{name}",
        "resume_w1": serial,
        "resume_w8": parallel,
        "payload_identical": (serial["payload_sha256"]
                              == parallel["payload_sha256"]
                              and serial["status"] == "verified"),
    }


def collect(root: Path, only: tuple[str, ...] | None) -> dict:
    from holo.receiver.tests import _h3_sims

    scans = fixtures(root)
    k_ref = _h3_sims.K_FORMAT_REF
    color_ref = _h3_sims.COLOR_FORMAT_REF
    cases = {
        "roundtrip-k": lambda: roundtrip(root, "k", scans["k"], k_ref),
        "roundtrip-color": lambda: roundtrip(root, "color", scans["color"],
                                             color_ref),
        "add-a-sheet": lambda: add_a_sheet(root, scans["k-mixed"], k_ref),
        "workers-k": lambda: workers_parity(root, "k", scans["k"], k_ref),
    }
    rows = []
    for name, build in cases.items():
        if only is not None and name not in only:
            continue
        row = build()
        rows.append(row)
        print(f"  {name}: "
              f"payload_identical={row.get('payload_identical')} "
              f"ratio={row.get('job_ratio', {}).get('TOTAL')}", flush=True)
    return {"cases": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fixture-root", type=Path,
                        default=Path("/tmp/holo3-donegeo-fixtures"))
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args(argv)
    record = collect(args.fixture_root,
                     tuple(args.only) if args.only else None)
    text = json.dumps(record, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.write_text(text)
        print(f"wrote {args.out} "
              f"({hashlib.sha256(text.encode()).hexdigest()[:12]})")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
