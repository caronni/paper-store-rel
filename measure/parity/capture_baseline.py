"""Wave 0 baseline capture — read-only over production, artefacts into
_distill/d6-baseline/.  Run:

  cd <checkout> && env314t/bin/python \
      _distill/d6-baseline/capture_baseline.py
"""
from __future__ import annotations

import collections
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path("<checkout>")
SIM_DIR = ROOT / "_distill/verify/sim"
OUT_DIR = ROOT / "_distill/d6-baseline"
RUNS = OUT_DIR / "runs"

sys.path.insert(0, str(ROOT))

from holo3 import cli, data, engine  # noqa: E402

SIMS = {
    "k": {
        "tiff": SIM_DIR / "sim-k-1200dpi.tiff",
        "payload": SIM_DIR / "sim-k-payload.bin",
        "format_ref": "c3-k-r0550@7x7",
        "dpi": 1200,
    },
    "color": {
        "tiff": SIM_DIR / "sim-color-1200dpi.tiff",
        "payload": SIM_DIR / "sim-color-payload.bin",
        "format_ref": "c3-cmy8-r0550x0550x0547@10x10",
        "dpi": 1200,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def head_hash() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def decode_once(label: str, sim: dict, workers: int) -> dict:
    run_dir = RUNS / label / "run"
    out_path = RUNS / label / "payload.bin"
    shutil.rmtree(RUNS / label, ignore_errors=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    argv = ("decode", str(sim["tiff"]), "--dpi", str(int(sim["dpi"])),
            "--format", sim["format_ref"], "--out", str(out_path),
            "--workers", str(workers), "--run-dir", str(run_dir),
            "--complete")
    captured: dict[str, object] = {}
    original = engine.decode

    def instrumented(request, events=None):
        collected = [] if events is None else events
        instance = engine._Engine(request, collected)
        result = instance.run()
        captured["certificates"] = dict(instance._certificates)
        captured["events"] = tuple(collected)
        captured["plugin_rows"] = tuple(result.plugin_rows)
        return result

    out = io.StringIO()
    err = io.StringIO()
    engine.decode = instrumented
    started = time.monotonic()
    try:
        with (contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
            exit_code = cli.main(list(argv))
    finally:
        engine.decode = original
        wall_s = time.monotonic() - started

    certificates = captured.get("certificates", {})
    events = captured.get("events", ())
    payload = out_path.read_bytes() if out_path.is_file() else None
    report_path = cli.run_dir_for(run_dir) / "report.json"
    report = json.loads(report_path.read_text()) if report_path.is_file() else {}

    addresses = []
    bits_shas = {}
    for key in sorted(certificates):
        page, ty, tx, stream_id = key
        addresses.append([int(page), int(ty), int(tx), str(stream_id)])
        bits = np.asarray(certificates[key].user_bits, np.uint8).tobytes()
        bits_shas[f"{page},{ty},{tx},{stream_id}"] = (
            hashlib.sha256(bits).hexdigest())
    signature = hashlib.sha256()
    for key in sorted(certificates):
        signature.update(repr(tuple(key)).encode())
        signature.update(np.asarray(certificates[key].user_bits,
                                    np.uint8).tobytes())

    event_counts = collections.Counter(type(e).__name__ for e in events)
    job_events = collections.Counter(
        e.plugin for e in events if isinstance(e, data.JobDone))
    plugin_rows = {
        row.plugin: {"jobs": int(row.jobs),
                     "cpu_seconds": round(float(row.cpu_seconds), 3),
                     "certificates": int(row.certificates),
                     "poses": int(row.poses),
                     "words": int(row.words)}
        for row in captured.get("plugin_rows", ())}
    return {
        "label": label,
        "workers": workers,
        "argv": list(argv),
        "exit_code": exit_code,
        "status": "verified" if exit_code == 0 else "not-verified",
        "wall_s": round(wall_s, 3),
        "payload_bytes": None if payload is None else len(payload),
        "payload_sha256": (None if payload is None
                           else hashlib.sha256(payload).hexdigest()),
        "payload_matches_source": (
            None if payload is None
            else payload == sim["payload"].read_bytes()),
        "certified": len(certificates),
        "certificate_addresses": addresses,
        "certificate_bits_sha256": bits_shas,
        "certificate_signature_sha256": signature.hexdigest(),
        "job_counts_per_row": dict(sorted(job_events.items())),
        "report_tier_jobs": report.get("tier_jobs", {}),
        "n_events": len(events),
        "event_counts": dict(sorted(event_counts.items())),
        "report_close": report.get("close"),
        "report_run_done": report.get("run_done"),
        "report_fold_errors": report.get("fold_errors"),
        "stdout": out.getvalue(),
        "stderr_tail": err.getvalue().splitlines()[-16:],
        "plugin_rows": plugin_rows,
    }


def main() -> None:
    os.environ.setdefault("HOLO_RECEIVE_WORKERS", "1")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "head": head_hash(),
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.version,
        "numpy": np.__version__,
        "sims": {},
        "runs": {},
    }
    for name, sim in SIMS.items():
        manifest["sims"][name] = {
            "format_ref": sim["format_ref"],
            "dpi": sim["dpi"],
            "tiff": str(sim["tiff"]),
            "tiff_sha256": sha256_file(sim["tiff"]),
            "payload": str(sim["payload"]),
            "payload_sha256": sha256_file(sim["payload"]),
            "payload_bytes": sim["payload"].stat().st_size,
        }
    order = [("k", 1), ("k", 8), ("color", 1), ("color", 8)]
    for name, workers in order:
        label = f"{name}-w{workers}"
        print(f"== {label} ==", flush=True)
        record = decode_once(label, SIMS[name], workers)
        (OUT_DIR / f"{label}.json").write_text(
            json.dumps(record, indent=1, sort_keys=True))
        manifest["runs"][label] = {
            "workers": workers,
            "exit_code": record["exit_code"],
            "status": record["status"],
            "wall_s": record["wall_s"],
            "payload_sha256": record["payload_sha256"],
            "payload_bytes": record["payload_bytes"],
            "payload_matches_source": record["payload_matches_source"],
            "certified": record["certified"],
            "certificate_signature_sha256":
                record["certificate_signature_sha256"],
            "job_counts_per_row": record["job_counts_per_row"],
            "plugin_rows": record["plugin_rows"],
            "n_events": record["n_events"],
            "event_counts": record["event_counts"],
        }
        print(f"   status {record['status']} certified {record['certified']} "
              f"wall {record['wall_s']}s", flush=True)
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True))
    print(json.dumps(manifest["runs"], indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
