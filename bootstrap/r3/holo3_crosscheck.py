"""Optional cross-check: holo's own receiver (holo3, python -m holo.receiver)
on one simulated scan, stopped at 15 minutes.  Harness only.
  PYTHONPATH=src env/bin/python bootstrap/r3/holo3_crosscheck.py SCAN [DPI] [WORKERS]
Writes build/r3/holo3/<scan>/{log.txt,result.json}.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE.parents[0] / "build" / "r3"
scan = sys.argv[1]
dpi = sys.argv[2] if len(sys.argv) > 2 else "1200"
workers = sys.argv[3] if len(sys.argv) > 3 else "4"
run = OUT / "holo3" / Path(scan).stem
run.mkdir(parents=True, exist_ok=True)
payload = run / "payload.bin"
payload.unlink(missing_ok=True)
cmd = [sys.executable, "-m", "holo.receiver", "decode", str(OUT / scan), "--dpi", dpi,
       "--format", "c3-k-r0550@35x24", "--out", str(payload), "--workers", workers,
       "--run-dir", str(run / "rundir")]
env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
t = time.time()
with open(run / "log.txt", "w") as log:
    try:
        cp = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=900)
        status = f"exit {cp.returncode}"
    except subprocess.TimeoutExpired:
        status = "stopped at 15 min"
wall = time.time() - t
truth = json.loads((OUT / "volume.json").read_text())
sha = hashlib.sha256(payload.read_bytes()).hexdigest() if payload.exists() else None
res = {"scan": scan, "dpi": dpi, "workers": workers, "status": status, "wall_s": round(wall, 1),
       "byte_exact": sha == truth["payload_sha256"], "cmd": cmd}
(run / "result.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
