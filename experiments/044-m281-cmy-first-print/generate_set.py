"""e044 — regenerate the two cmy counting volumes printed on the M281 (P1, 2026-10-11), byte-identically.

Sheet A: c2-cmy-r0775x0700@53x37, counting payload k = 0, 1,123,545 B (the row's capacity at q 0.8).
Sheet B: c3-cmy-r0850@35x24,      counting payload k = 1,   558,886 B.
Counting rule (e039): byte[i] = (i + 0x39 + k) mod 256.  A4-4mm, --printer hp-m281 (the rgb route: three
single-toner ASCII85 imagemasks per page in the registry's hp-m281 values), --source-fraction 0.8.

    PYTHONPATH=src env/bin/python experiments/044-m281-cmy-first-print/generate_set.py --out build/e044 [--verify]

--verify checks every payload and job against JOB-SHA256.txt beside this script.  The jobs and GT are derived
and not committed; the printed copies live in scratch2/e044/jobs/ (the evidence archive's home later).
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
    ("A", "c2-cmy-r0775x0700@53x37", 1_123_545, 0),
    ("B", "c3-cmy-r0850@35x24", 558_886, 1),
)
Q = "0.8"
PAPER = "A4-4mm"
PRINTER = "hp-m281"


def counting_payload(n_bytes: int, k: int) -> bytes:
    return ((np.arange(n_bytes, dtype=np.int64) + PAYLOAD_BASE + k) % 256).astype(np.uint8).tobytes()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path("build/e044"))
    ap.add_argument("--verify", action="store_true", help="check payloads and jobs against JOB-SHA256.txt")
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
            for p, name in ((pay, pay.name), (job, f"E044-{sheet}-page000.ps")):
                good = sha256(p) == expected.get(name)
                ok &= good
                print(f"   {'ok ' if good else 'MISMATCH'} {name}")
    if a.verify and not ok:
        raise SystemExit("verify FAILED")


if __name__ == "__main__":
    main()
