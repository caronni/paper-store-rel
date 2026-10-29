"""receiver.py on real (simulated) scans of MIXED piles: the refuter's
volumes VA (60,000 B, 1 page), VB (400,000 B, 4 pages) and VF (the fossil
seed), scanned by the refuter's own scanner model (build/r3-refute/).  Every
payload file the session writes is matched against every truth.  Harness only.
  env/bin/python bootstrap/r3/run_mixed.py [CASE ...]
"""
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parent / "build" / "r3-refute"
OUT = HERE.parent / "build" / "r3" / "runs_mixed"
TRUTH = {json.loads((REF / v / "info.json").read_text())["payload_sha256"]: v.upper()
         for v in ("va", "vb", "vf")}
CASES = {   # case -> (scans in the finder's order, the volumes that must come out)
    "mixed_vbp3_va_vbp2_vbp1": (["vb_p3", "va_warp", "vb_p2", "vb_p1"], {"VA", "VB"}),
    "mixed_va_first": (["va_crop60", "vb_p0", "vb_p1"], {"VA", "VB"}),
    "vb_p3_p2": (["vb_p3", "vb_p2"], {"VB"}),
    "vb_p2twice_p0": (["vb_p2", "vb_p2", "vb_p0"], {"VB"}),
    "va_mirror": (["va_mirror"], set()),
    "vf_into_v2": (["vf_p0"], set()),
}


def run(case):
    scans, expect = CASES[case]
    run_dir = OUT / case
    run_dir.mkdir(parents=True, exist_ok=True)
    for f in run_dir.glob("payload*.bin"):
        f.unlink()
    lines = "".join(f"{REF / 'scans' / (s + '.pgm')} 1200\n" for s in scans) + "\n"
    t = time.time()
    cp = subprocess.run([sys.executable, str(HERE / "receiver.py")], input=lines,
                        capture_output=True, text=True, cwd=run_dir)
    wall = time.time() - t
    got = {f.name: TRUTH.get(hashlib.sha256(f.read_bytes()).hexdigest(), "WRONG")
           for f in sorted(run_dir.glob("payload*.bin"))}
    res = {"case": case, "wall_s": round(wall, 1), "files": got,
           "ok": set(got.values()) == expect and len(got) == len(expect),
           "stdout": cp.stdout.replace("scan (PGM file [dpi]; empty line ends): ", "")
                     .replace(str(REF / "scans") + "/", "").strip().splitlines(),
           "stderr": cp.stderr[-2000:]}
    (run_dir / "result.json").write_text(json.dumps(res, indent=1))
    return res


names = sys.argv[1:] or list(CASES)
with ThreadPoolExecutor(3) as ex:
    for r in ex.map(run, names):
        print(f"{r['case']}: {'OK' if r['ok'] else 'FAIL'} {r['wall_s']} s files {r['files']}")
        for ln in r["stdout"]:
            print("    " + ln)
        if r["stderr"]:
            print("    STDERR " + r["stderr"])
