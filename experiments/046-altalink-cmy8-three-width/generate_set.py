"""e046 — regenerate the cmy8 three-width counting sheet for the AltaLink C8245 (generated 2026-10-12), byte-identically.

Sheet A: c2-cmy8-r0775x0850x0700@53x37 — C at r0775, M at r0850, Y at r0700 — counting payload k = 2,
1,782,790 B (the row's capacity at q 0.8).  Counting rule (e039): byte[i] = (i + 0x39 + k) mod 256; k = 2 follows
e044's A (0) and B (1).  A4-4mm, --printer xerox-altalink-c8245 (the cmyk1 route: one DeviceCMYK image at 600 dpi),
--source-fraction 0.8.  The second column-group print after e044's cmy pair, the first with three widths
(Z 21, carried C 19 / M 21 / Y 17); printed WITHOUT a sim decode of the row by the owner's call ("We won't sim
decode. We'll just scan the sheet and see!").

    PYTHONPATH=src env/bin/python experiments/046-altalink-cmy8-three-width/generate_set.py --out build/e046 [--verify]

--verify checks the payload and the job against JOB-SHA256.txt beside this script.  The job and GT are derived
and not committed; the printed copy lives in scratch/e046/jobs/.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PAYLOAD_BASE = 0x39
SHEETS = (
    ("A", "c2-cmy8-r0775x0850x0700@53x37", 1_782_790, 2),
)
Q = "0.8"
PAPER = "A4-4mm"
PRINTER = "xerox-altalink-c8245"


def counting_payload(n_bytes: int, k: int) -> bytes:
    return ((np.arange(n_bytes, dtype=np.int64) + PAYLOAD_BASE + k) % 256).astype(np.uint8).tobytes()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path("build/e046"))
    ap.add_argument("--verify", action="store_true", help="check the payload and job against JOB-SHA256.txt")
    a = ap.parse_args()
    expected = {}
    if a.verify:
        for line in (HERE / "JOB-SHA256.txt").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                digest, name = line.split()
                expected[name] = digest
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "payloads").mkdir(exist_ok=True)
    ok = True
    for sheet, fmt, n, k in SHEETS:
        pay = a.out / "payloads" / f"counting-{sheet}-{fmt.split('-')[0]}-{n}.bin"
        pay.write_bytes(counting_payload(n, k))
        out = a.out / sheet
        subprocess.run([sys.executable, str(ROOT / "confetti.py"), "generate", "--format", fmt, "--paper", PAPER,
                        "--printer", PRINTER, "--source-fraction", Q, "-o", str(out), str(pay)], check=True)
        job = out / "page000.ps"
        print(f"{sheet} {fmt}: payload {pay.name} {sha256(pay)[:16]}…  job {job.stat().st_size} B {sha256(job)[:16]}…")
        if a.verify:
            for p, name in ((pay, pay.name), (job, f"E046-{sheet}-page000.ps")):
                good = sha256(p) == expected.get(name)
                ok &= good
                print(f"   {'ok ' if good else 'MISMATCH'} {name}")
    if a.verify and not ok:
        raise SystemExit("verify FAILED")


if __name__ == "__main__":
    main()
