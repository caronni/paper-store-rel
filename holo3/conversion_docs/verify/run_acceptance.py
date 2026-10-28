#!/usr/bin/env python
"""Serial acceptance driver for holo3 (contract R/14-1).

Reads _distill/verify/acceptance.json and runs the holo3 decodes ONE at a
time (64 GB machine — never in parallel):

    cd <checkout> && PYTHONPATH=. \
        env314t/bin/python -m holo3 decode <scans...> --dpi ... --format ... \
        --pages N --out <rundir>/recovered.bin --workers 8

PASS = byte count AND sha256 of the recovered payload match the manifest.
Special steps:
  - step 8 (kind workers-ab): re-runs step 3 twice, --workers 1 vs the
    high worker count, comparing payload bytes (must be identical and match
    the step-3 manifest) and wall time (>= 3.0x speedup required).
  - step 9 (negative control, has "expect"): PASS = exit code 2 and no
    output file written.

Usage:
    env314t/bin/python _distill/verify/run_acceptance.py [options]
      --only STEP[,STEP...]   run a subset (repeatable)
      --continue              keep going after a failure (default: stop)
      --workers N             override the default 8 workers
      --timeout-s S           per-decode wall timeout (0 = none, default)
      --check                 only verify the manifest + scan paths, no runs

Outputs land under _distill/verify/runs/<step-id>/ (recovered.bin,
log.txt, result.json) plus an appended runs/ledger.jsonl. The script
degrades gracefully while the holo3 CLI does not exist yet (clear
NOT-RUNNABLE message, exit 3). This file is _distill scratch: comments
allowed, throwaway quality, but it must actually run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path("<checkout>")
PYTHON = ROOT / "env314t" / "bin" / "python"
MANIFEST = ROOT / "_distill" / "verify" / "acceptance.json"
RUNS_DIR = ROOT / "_distill" / "verify" / "runs"
WORKERS_AB_BASE_ID = "3"  # step 8's note: "re-run step 3"
WORKERS_AB_MIN_SPEEDUP = 3.0
DEFAULT_WORKERS = 8

LEDGER_HEADER = (
    f"{'STEP':<6} {'STATUS':<22} {'BYTES':>9} {'SHA':>4} "
    f"{'WALL(s)':>9} {'RSS(GiB)':>9}  DETAIL"
)


def fmt_row(step_id: str, status: str, nbytes: int | None, sha_ok: str,
            wall_s: float | None, rss_bytes: int | None, detail: str = "") -> str:
    b = "-" if nbytes is None else str(nbytes)
    w = "-" if wall_s is None else f"{wall_s:.1f}"
    r = "-" if rss_bytes is None else f"{rss_bytes / 2**30:.2f}"
    return f"{step_id:<6} {status:<22} {b:>9} {sha_ok:>4} {w:>9} {r:>9}  {detail}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict[str, Any] | None:
    if not MANIFEST.is_file():
        print(f"ERROR: manifest not found: {MANIFEST}")
        return None
    try:
        with MANIFEST.open("r") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: manifest does not parse: {MANIFEST}: {exc}")
        return None
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        print("ERROR: manifest has no 'steps' list")
        return None
    return manifest


def preflight_scans(steps: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Report missing scan files per step (never fails the whole script)."""
    missing_by_step: dict[str, list[str]] = {}
    for step in steps:
        missing = [s for s in step.get("scans", []) if not Path(s).is_file()]
        if missing:
            missing_by_step[str(step["id"])] = missing
    if missing_by_step:
        print("WARNING: missing scan files (their steps will be SKIPPED):")
        for step_id, paths in missing_by_step.items():
            for p in paths:
                print(f"  step {step_id}: MISSING {p}")
    else:
        print("preflight: all referenced scan paths exist")
    return missing_by_step


def cli_probe() -> tuple[bool, str]:
    """Is `python -m holo3` runnable at all? Graceful while wave-2 builds."""
    if not PYTHON.is_file():
        return False, f"interpreter missing: {PYTHON}"
    main_py = ROOT / "holo3" / "__main__.py"
    if not main_py.is_file():
        present = sorted(
            p.name for p in (ROOT / "holo3").glob("*.py")) if (ROOT / "holo3").is_dir() else []
        return False, (f"holo3/__main__.py does not exist yet "
                       f"(holo3/*.py present: {', '.join(present) or 'none'})")
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    try:
        proc = subprocess.run(
            [str(PYTHON), "-m", "holo3", "--help"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "probe `python -m holo3 --help` timed out after 120 s"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        return False, ("probe `python -m holo3 --help` exited "
                       f"{proc.returncode}:\n  " + "\n  ".join(tail))
    return True, "ok"


def run_child(argv: list[str], log_path: Path,
              timeout_s: float) -> tuple[int, float, int | None, bool]:
    """Run one decode; return (exit_code, wall_s, peak_rss_bytes, timed_out).

    Uses posix_spawn + os.wait4 so the rusage (resource.struct_rusage) is
    for THIS child alone, not the accumulated RUSAGE_CHILDREN max.
    """
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    with log_path.open("ab") as log_f, open(os.devnull, "rb") as devnull:
        log_f.write((" ".join(argv) + "\n").encode())
        log_f.flush()
        file_actions = [
            (os.POSIX_SPAWN_DUP2, devnull.fileno(), 0),
            (os.POSIX_SPAWN_DUP2, log_f.fileno(), 1),
            (os.POSIX_SPAWN_DUP2, log_f.fileno(), 2),
        ]
        start = time.monotonic()
        pid = os.posix_spawn(argv[0], argv, env, file_actions=file_actions)
    deadline = None if timeout_s <= 0 else start + timeout_s
    timed_out = False
    while True:
        done_pid, status, ru = os.wait4(pid, os.WNOHANG)
        if done_pid == pid:
            break
        now = time.monotonic()
        if deadline is not None and now > deadline and not timed_out:
            timed_out = True
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.5)
    wall_s = time.monotonic() - start
    exit_code = os.waitstatus_to_exitcode(status)
    # ru is a resource.struct_rusage; ru_maxrss is bytes on darwin, KiB on linux
    peak_rss: int | None = None
    if ru is not None and ru.ru_maxrss > 0:
        peak_rss = int(ru.ru_maxrss) if sys.platform == "darwin" else int(ru.ru_maxrss) * 1024
    return exit_code, wall_s, peak_rss, timed_out


def decode_argv(step: dict[str, Any], out_path: Path, workers: int,
                prefer_alt: bool = False) -> list[str]:
    argv = [str(PYTHON), "-m", "holo3", "decode"]
    argv += [str(s) for s in step["scans"]]
    for dpi in step["dpi"]:
        argv += ["--dpi", str(dpi)]
    if step.get("alt_route") and (prefer_alt or not step.get("format")):
        # contract 14-2 second route: --coding/--printer sugar (e029 step)
        argv += ["--coding", str(step["alt_route"]["coding"]),
                 "--printer", str(step["alt_route"]["printer"])]
    elif step.get("format"):
        argv += ["--format", str(step["format"])]
    argv += ["--pages", str(step.get("pages", 1))]
    argv += ["--out", str(out_path), "--workers", str(workers)]
    return argv


def fresh_rundir(name: str) -> Path:
    rundir = RUNS_DIR / name
    rundir.mkdir(parents=True, exist_ok=True)
    out = rundir / "recovered.bin"
    if out.exists():
        out.unlink()
    log = rundir / "log.txt"
    if log.exists():
        log.unlink()
    return rundir


def tail_log(log_path: Path, n: int = 12) -> None:
    try:
        lines = log_path.read_text(errors="replace").splitlines()[-n:]
    except OSError:
        return
    for line in lines:
        print(f"    | {line}")


def run_decode_once(step: dict[str, Any], run_name: str, workers: int,
                    timeout_s: float, prefer_alt: bool = False) -> dict[str, Any]:
    """One decode invocation + payload verification against the manifest."""
    rundir = fresh_rundir(run_name)
    out = rundir / "recovered.bin"
    log = rundir / "log.txt"
    argv = decode_argv(step, out, workers, prefer_alt)
    print(f"  run: {' '.join(argv)}")
    exit_code, wall_s, peak_rss, timed_out = run_child(argv, log, timeout_s)

    result: dict[str, Any] = {
        "step": str(step["id"]), "run": run_name, "argv": argv,
        "workers": workers, "exit_code": exit_code, "wall_s": round(wall_s, 3),
        "peak_rss_bytes": peak_rss, "timed_out": timed_out,
        "out": str(out), "log": str(log),
        "bytes": None, "sha256": None, "sha_ok": "-", "status": "FAIL",
    }

    negative = "expect" in step and "payload_sha256" not in step
    if timed_out:
        result["status"] = "TIMEOUT"
    elif negative:
        # step 9 class: expect exit 2 and no output file
        if exit_code == 2 and not out.exists():
            result["status"] = "PASS"
        else:
            result["status"] = "FAIL"
            result["detail"] = (f"expected exit 2 + no output; got exit "
                                f"{exit_code}, output {'present' if out.exists() else 'absent'}")
    else:
        if out.exists():
            nbytes = out.stat().st_size
            digest = sha256_file(out)
            result["bytes"] = nbytes
            result["sha256"] = digest
            bytes_ok = nbytes == step.get("payload_bytes")
            sha_ok = digest == step.get("payload_sha256")
            result["sha_ok"] = "ok" if sha_ok else "BAD"
            if bytes_ok and sha_ok:
                result["status"] = "PASS"
            else:
                result["status"] = "FAIL"
                result["detail"] = (f"bytes {nbytes} vs {step.get('payload_bytes')}, "
                                    f"sha {'match' if sha_ok else 'MISMATCH'}")
        else:
            result["status"] = "OPEN" if exit_code == 2 else "FAIL"
            result["detail"] = f"exit {exit_code}, no output file"

    with (rundir / "result.json").open("w") as f:
        json.dump(result, f, indent=2)
    return result


def run_workers_ab(steps_by_id: dict[str, dict[str, Any]], workers_hi: int,
                   timeout_s: float, step_id: str) -> dict[str, Any]:
    """Step 8: step 3 at --workers 1 vs --workers <hi>; identical payload + speedup."""
    base = steps_by_id.get(WORKERS_AB_BASE_ID)
    verdict: dict[str, Any] = {"step": step_id, "status": "FAIL", "runs": []}
    if base is None:
        verdict["detail"] = f"base step {WORKERS_AB_BASE_ID} not in manifest"
        return verdict
    missing = [s for s in base.get("scans", []) if not Path(s).is_file()]
    if missing:
        verdict["status"] = "SKIP"
        verdict["detail"] = f"missing scan(s): {missing}"
        return verdict

    r1 = run_decode_once(base, f"{step_id}/w1", 1, timeout_s)
    print(fmt_row(f"{step_id}.w1", r1["status"], r1["bytes"], r1["sha_ok"],
                  r1["wall_s"], r1["peak_rss_bytes"], "workers=1"))
    rn = run_decode_once(base, f"{step_id}/w{workers_hi}", workers_hi, timeout_s)
    print(fmt_row(f"{step_id}.w{workers_hi}", rn["status"], rn["bytes"], rn["sha_ok"],
                  rn["wall_s"], rn["peak_rss_bytes"], f"workers={workers_hi}"))
    verdict["runs"] = [r1, rn]

    identical = (r1["sha256"] is not None and r1["sha256"] == rn["sha256"]
                 and r1["bytes"] == rn["bytes"])
    both_pass = r1["status"] == "PASS" and rn["status"] == "PASS"
    speedup = (r1["wall_s"] / rn["wall_s"]) if rn["wall_s"] else 0.0
    verdict["speedup"] = round(speedup, 2)
    verdict["wall_s"] = rn["wall_s"]
    verdict["bytes"] = rn["bytes"]
    verdict["sha_ok"] = rn["sha_ok"]
    verdict["peak_rss_bytes"] = rn["peak_rss_bytes"]
    if both_pass and identical and speedup >= WORKERS_AB_MIN_SPEEDUP:
        verdict["status"] = "PASS"
        verdict["detail"] = f"identical payloads, speedup {speedup:.2f}x"
    else:
        verdict["detail"] = (f"pass(w1)={r1['status']} pass(w{workers_hi})={rn['status']} "
                             f"identical={identical} speedup={speedup:.2f}x "
                             f"(need >= {WORKERS_AB_MIN_SPEEDUP}x)")
    rundir = RUNS_DIR / step_id
    rundir.mkdir(parents=True, exist_ok=True)
    with (rundir / "result.json").open("w") as f:
        json.dump(verdict, f, indent=2)
    return verdict


def append_ledger(entry: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    entry = dict(entry, ts=time.strftime("%Y-%m-%dT%H:%M:%S"))
    entry.pop("argv", None)
    entry.pop("runs", None)
    with (RUNS_DIR / "ledger.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="holo3 serial acceptance driver")
    ap.add_argument("--only", action="append", default=None, metavar="STEP",
                    help="run only these step ids (repeatable; comma-separated ok)")
    ap.add_argument("--continue", dest="keep_going", action="store_true",
                    help="continue past failures (default: stop on first)")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help=f"worker count for decodes (default {DEFAULT_WORKERS})")
    ap.add_argument("--timeout-s", type=float, default=0.0,
                    help="per-decode wall timeout in seconds (0 = none)")
    ap.add_argument("--alt-route", action="store_true",
                    help="where a step has alt_route, decode via "
                         "--coding/--printer instead of --format (contract 14-2)")
    ap.add_argument("--check", action="store_true",
                    help="verify manifest + scan paths only; run nothing")
    args = ap.parse_args()

    os.chdir(ROOT)
    manifest = load_manifest()
    if manifest is None:
        return 1
    steps: list[dict[str, Any]] = manifest["steps"]
    steps_by_id = {str(s["id"]): s for s in steps}

    selected_ids = list(steps_by_id)
    if args.only:
        wanted = [tok for chunk in args.only for tok in chunk.split(",") if tok]
        unknown = [w for w in wanted if w not in steps_by_id]
        if unknown:
            print(f"ERROR: unknown step id(s) {unknown}; valid: {list(steps_by_id)}")
            return 1
        selected_ids = [sid for sid in steps_by_id if sid in wanted]

    missing_by_step = preflight_scans(steps)
    if args.check:
        print(f"manifest ok: {len(steps)} steps; selected: {selected_ids}")
        return 0 if not missing_by_step else 1

    runnable, why = cli_probe()
    if not runnable:
        print()
        print("NOT-RUNNABLE: the holo3 decode CLI is not available yet.")
        print(f"  {why}")
        print("  (wave-2/integrator work in progress — manifest and scan "
              "preflight above still ran; re-run once holo3/__main__.py lands)")
        return 3

    print()
    print(LEDGER_HEADER)
    n_pass = n_fail = n_skip = 0
    stopped = False
    for sid in selected_ids:
        step = steps_by_id[sid]
        if stopped:
            print(fmt_row(sid, "NOT-RUN", None, "-", None, None,
                          "stopped after earlier failure"))
            continue
        if step.get("kind") == "workers-ab":
            verdict = run_workers_ab(steps_by_id, args.workers, args.timeout_s, sid)
            print(fmt_row(sid, verdict["status"], verdict.get("bytes"),
                          verdict.get("sha_ok", "-"), verdict.get("wall_s"),
                          verdict.get("peak_rss_bytes"), verdict.get("detail", "")))
            append_ledger(verdict)
            status = verdict["status"]
        elif sid in missing_by_step:
            # environmental gap: report + skip, never abort the whole run
            print(fmt_row(sid, "SKIP", None, "-", None, None,
                          f"missing scan(s): {missing_by_step[sid]}"))
            append_ledger({"step": sid, "status": "SKIP",
                           "detail": f"missing scans {missing_by_step[sid]}"})
            status = "SKIP"
        else:
            result = run_decode_once(step, sid, args.workers, args.timeout_s,
                                     args.alt_route)
            print(fmt_row(sid, result["status"], result["bytes"], result["sha_ok"],
                          result["wall_s"], result["peak_rss_bytes"],
                          result.get("detail", "")))
            append_ledger(result)
            status = result["status"]
            if status != "PASS":
                tail_log(Path(result["log"]))
        if status == "PASS":
            n_pass += 1
        elif status == "SKIP":
            n_skip += 1
        else:
            n_fail += 1
            if not args.keep_going:
                stopped = True

    print()
    print(f"RESULT: {n_pass} PASS / {n_fail} FAIL / {n_skip} SKIP "
          f"of {len(selected_ids)} selected (runs/ledger.jsonl appended)")
    if n_fail:
        return 1
    if n_skip:
        print("RESULT: INCOMPLETE (skipped steps — missing scans)")
        return 1
    print("RESULT: all selected steps PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
