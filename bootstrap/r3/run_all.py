"""Every verification case of bootstrap/r3 through run_case.py, six at a
time; the summary to build/r3/runs/summary.json.  Harness only.
  env/bin/python bootstrap/r3/run_all.py [--receiver FILE] [--tag TAG] [CASE ...]
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[0] / "build" / "r3"
CASES = {   # case -> (c4?, scans in the order the finder feeds them)
    "base1200": (False, ["base1200_p0.pgm", "base1200_p1.pgm"]),
    "p1first": (False, ["base1200_p1.pgm", "base1200_p0.pgm"]),
    "s2400": (False, ["s2400_p0.pgm:2400", "s2400_p1.pgm:2400"]),
    "scale": (False, ["scale_p0.pgm", "scale_p1.pgm"]),
    "rot03": (False, ["rot03_p0.pgm", "rot03_p1.pgm"]),
    "rot15": (False, ["rot15_p0.pgm", "rot15_p1.pgm"]),
    "seam": (False, ["seam_p0.pgm", "seam_p1.pgm"]),
    "combo": (False, ["combo_p0.pgm", "combo_p1.pgm"]),
    "turn90": (False, ["turn90_p0.pgm", "turn90_p1.pgm"]),
    "turn270": (False, ["turn270_p0.pgm", "turn270_p1.pgm"]),
    "rough": (False, ["rough_p0.pgm", "rough_p1.pgm"]),
    "blank40": (False, ["blank40_p0.pgm", "blank40_p1.pgm"]),
    "c4_base1200": (True, ["base1200_p0.pgm", "base1200_p1.pgm"]),
    "c4_combo": (True, ["combo_p0.pgm", "combo_p1.pgm"]),
    "c4_blank40": (True, ["blank40_p0.pgm", "blank40_p1.pgm"]),
}
args = sys.argv[1:]
extra, tag = [], ""
if "--receiver" in args:
    i = args.index("--receiver")
    extra = ["--receiver", args[i + 1]]
    del args[i:i + 2]
if "--tag" in args:
    i = args.index("--tag")
    tag = args[i + 1]
    del args[i:i + 2]
names = args or list(CASES)


def run(name):
    c4, scans = CASES[name]
    cmd = [sys.executable, str(HERE / "run_case.py")] + (["--c4"] if c4 else []) + \
          [name + tag] + (extra if not c4 else []) + scans
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    return json.loads(out[:out.rindex("}") + 1])


with ThreadPoolExecutor(6) as ex:
    res = list(ex.map(run, names))
summary = OUT / "runs" / f"summary{tag}.json"
old = json.loads(summary.read_text()) if summary.exists() else {}
old.update({r["case"]: r for r in res})
summary.write_text(json.dumps(old, indent=1))
for r in res:
    lines = [ln.split(": ", 1)[-1] for ln in r["stdout"]]
    print(f"{r['case']:16s} byte-exact {'YES' if r['byte_exact'] else 'NO '} {r['wall_s']:6.1f} s | "
          + " | ".join(lines))
