#!/usr/bin/env python3
"""e039 — the Xerox VersaLink candidate set: regenerate byte-identically.

    env/bin/python experiments/039-xerox-versalink/generate_set.py [--out DIR]   (default: its build/)

One A4 page per volume on the A4-4mm paper bundle at 600 dpi, q = 0.8,
each carrying a COUNTING payload that fills the page exactly.  The
payload is e033's counting rule with a per-sheet twiddle so that no
sheet of this set repeats e033's bytes:

    byte[i] = (i + 0x39 + k) mod 256,   k = the sheet's index (A = 0)

(e033 used byte[i] = i mod 256).  The printed bits differ from e033's
sheets a second time through the FORMAT-SPACE v2 identity seed
(`holo/v2/...`), which e033's `holo/v1/...-x1` rows never used.

Everything else is `./confetti.py capacity --json` + `./confetti.py
generate`; this script only chooses the set, sizes the payload and
records the shas.  Nothing here prints — scripts/print_plane.sh is the
only print path, and only on the operator's go.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFETTI = REPO / "confetti.py"
PYTHON = sys.executable

PAPER = "A4-4mm"
Q = 0.8
PAYLOAD_BASE = 0x39  # e039

# tag, format id (display spelling), note
SET: tuple[tuple[str, str, str], ...] = (
    ("A", "c4-k-r0700@26x18",     "K, coarsest rung of the ladder"),
    ("B", "c3-k-r0700@35x24",     "K, the e018/e029 class at r0700"),
    ("C", "c2-k-r0700@53x37",     "K, the e029/e032 rung (verified on M281 + AltaLink)"),
    ("D", "c2-k-r0850@53x37",     "K, one rung up from C"),
    ("E", "c1-k-r0700@106x74",    "K, ONE DOT PER CELL — existence probe (cell=1 dead on both engines to date)"),
    ("F", "c3-cmy8-r0700@35x24",  "CMY8 pooled -v1 at c3"),
    ("G", "c2-cmy8-r0700@53x37",  "CMY8 pooled -v1, e033 sheet I's rung"),
    ("H", "c2-cmy8-r0775@53x37",  "CMY8 pooled -v1, the rung between G and I"),
    ("I", "c2-cmy8-r0850@53x37",  "CMY8 pooled -v1, e033 sheet H's rung (holo3 max)"),
    ("J", "c1-cmy8-r0700@106x74", "CMY8 at ONE DOT PER CELL — existence probe"),
)


def counting_payload(n_bytes: int, k: int) -> bytes:
    base = (PAYLOAD_BASE + k) & 0xFF
    return bytes((i + base) & 0xFF for i in range(n_bytes))


def confetti(*args: str) -> str:
    proc = subprocess.run([PYTHON, str(CONFETTI), *args], check=True,
                          capture_output=True, text=True, cwd=REPO)
    return proc.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "build")
    args = ap.parse_args()
    out_root: Path = args.out
    out_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for k, (tag, fmt, note) in enumerate(SET):
        cap = json.loads(confetti("capacity", "--format", fmt, "--paper", PAPER,
                                  "--source-fraction", str(Q), "--json"))
        n = int(cap["max_payload_bytes"])
        payload = counting_payload(n, k)
        sha = hashlib.sha256(payload).hexdigest()
        name = f"{tag}-{fmt.replace('@', '-at-')}-q{int(Q * 100):03d}-{PAPER}"
        out_dir = out_root / name
        if out_dir.exists():
            print(f"{tag}: {out_dir.name} exists — skipping generate", file=sys.stderr)
        else:
            payload_path = out_root / f"payload-{tag}.bin"
            payload_path.write_bytes(payload)
            print(f"{tag}: generating {fmt} ({n:,} B) …", file=sys.stderr, flush=True)
            confetti("generate", "--format", fmt, "--paper", PAPER,
                     "--source-fraction", str(Q), "-o", str(out_dir),
                     str(payload_path))
            payload_path.rename(out_dir / "payload-counting.bin")
        manifest = json.loads((out_dir / "manifest.json").read_text("utf-8"))
        assert manifest["payload"]["sha256"] == sha, (tag, manifest["payload"])
        ps = out_dir / "page000.ps"
        ps_sha = hashlib.sha256(ps.read_bytes()).hexdigest()
        vol = manifest["volume"]
        rows.append(dict(tag=tag, format=fmt, spec_id=cap["spec_id"],
                         tiles=cap["tiles_per_page"], q=Q, payload_bytes=n,
                         payload_sha256=sha, k_over_n=vol.get("effective_k_over_n"),
                         k_total=vol.get("k_total"), n_symbols=vol.get("n_symbols_total"),
                         borders_mm=cap["borders_mm"], plane_tier=cap.get("plane_tier"),
                         ps=str(ps.relative_to(REPO)), ps_sha256=ps_sha,
                         ps_bytes=ps.stat().st_size, dir=out_dir.name, note=note))

    (out_root / "SET.json").write_text(json.dumps(rows, indent=1) + "\n")
    print("| tag | format | tiles | q | payload B | K/N | payload sha | page000.ps sha | ps MiB |")
    print("|---|---|---:|---|---:|---|---|---|---:|")
    for r in rows:
        print(f"| {r['tag']} | `{r['format']}` | {r['tiles']} | {r['q']} | "
              f"{r['payload_bytes']:,} | {r['k_over_n']:.3f} | `{r['payload_sha256'][:12]}…` | "
              f"`{r['ps_sha256'][:12]}…` | {r['ps_bytes'] / 2**20:.1f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
