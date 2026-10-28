import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from measure import footprint

KILL_GIB = 58.0
POLL_S = 60
GIB = 1024 ** 3


def _free_gib() -> float:
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    page = 16384
    free = 0
    for line in out.splitlines():
        for key in ("Pages free", "Pages inactive", "Pages purgeable",
                    "Pages speculative"):
            if line.startswith(key):
                free += int(line.split(":")[1].strip().rstrip("."))
    return free * page / GIB


def _run_step(step: dict, ledger: Path) -> dict:
    t0 = time.time()
    entry = {"step": step["id"], "argv": step["argv"], "started": t0}
    proc = subprocess.Popen(step["argv"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT,
                            start_new_session=True)
    peak_rss = 0.0
    peak_fp = 0.0
    killed = False
    while True:
        try:
            proc.wait(timeout=POLL_S)
            break
        except subprocess.TimeoutExpired:
            fp_b = footprint.phys_footprint(proc.pid)
            rss_b = footprint.resident_size(proc.pid)
            fp = (fp_b or rss_b or 0) / GIB
            rss = (rss_b or 0) / GIB
            peak_fp = max(peak_fp, fp)
            peak_rss = max(peak_rss, rss)
            if fp >= KILL_GIB:
                killed = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                break
    entry.update(exit_code=proc.returncode, killed_at_footprint=killed,
                 wall_s=round(time.time() - t0, 1),
                 peak_footprint_gib=round(peak_fp, 2),
                 peak_rss_gib=round(peak_rss, 2))
    expected = step.get("payload_sha256")
    out = step.get("out")
    if expected and out and Path(out).exists():
        import hashlib
        got = hashlib.sha256(Path(out).read_bytes()).hexdigest()
        entry.update(payload_sha256=got, sha_ok=got == expected)
    with ledger.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def main() -> int:
    manifest = json.loads(Path(sys.argv[1]).read_text())
    ledger = Path(sys.argv[2])
    ledger.parent.mkdir(parents=True, exist_ok=True)
    for step in manifest["steps"]:
        need = step.get("free_gib", 40.0)
        while _free_gib() < need:
            with ledger.open("a") as fh:
                fh.write(json.dumps({"step": step["id"],
                                     "waiting_free_gib": need}) + "\n")
            time.sleep(POLL_S)
        _run_step(step, ledger)
    with ledger.open("a") as fh:
        fh.write(json.dumps({"batch_done": True, "ts": time.time()}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
