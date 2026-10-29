"""Run receiver.py (or a minified form of it) as the finder would: a fresh
working directory, the scan names on stdin, the payload compared with the
truth afterwards.  Harness only.
  env/bin/python bootstrap/r3/run_case.py CASE [--receiver FILE] SCAN[:DPI] ...
Writes build/r3/runs/CASE/{stdout.txt,result.json}.
"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[0] / "build" / "r3"
args = sys.argv[1:]
receiver = HERE / "receiver.py"
if "--c4" in args:        # the c4 volume, read by receiver.py with CELL_DOTS = 4
    args.remove("--c4")
    OUT = OUT / "c4"
    receiver = OUT / "receiver_c4.py"
    receiver.write_text((HERE / "receiver.py").read_text().replace(
        "CELL_DOTS = 3 ", "CELL_DOTS = 4 ", 1))
case = args.pop(0)
if args and args[0] == "--receiver":
    args.pop(0)
    receiver = Path(args.pop(0)).resolve()
lines = []
for a in args:
    name, _, dpi = a.partition(":")
    p = Path(name)
    if not p.is_absolute():
        p = OUT / p
    lines.append(f"{p} {dpi or 1200}")
run = OUT / "runs" / case
run.mkdir(parents=True, exist_ok=True)
(run / "payload.bin").unlink(missing_ok=True)
t = time.time()
cp = subprocess.run([sys.executable, str(receiver)], input="\n".join(lines) + "\n\n",
                    capture_output=True, text=True, cwd=run)
wall = time.time() - t
(run / "stdout.txt").write_text(cp.stdout + cp.stderr)
truth = json.loads((OUT / "volume.json").read_text())
got = run / "payload.bin"
sha = hashlib.sha256(got.read_bytes()).hexdigest() if got.exists() else None
res = {"case": case, "receiver": str(receiver), "scans": lines, "wall_s": round(wall, 1),
       "byte_exact": sha == truth["payload_sha256"], "payload_sha256": sha,
       "stdout": cp.stdout.replace("scan (PGM file [dpi]; empty line ends): ", "").strip().splitlines()}
(run / "result.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
if cp.returncode:
    print(cp.stderr)
