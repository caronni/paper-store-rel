#!/usr/bin/env python3
"""e039 — coalesce the discovery pair + the ten candidate volumes into ONE
multi-page PostScript job, one sheet per page.

    env/bin/python experiments/039-xerox-versalink/coalesce_ps.py \\
        --root experiments/039-xerox-versalink/build [-o e039-all-pages.ps]

Each source is a single-page DSC 3.0 job from `holo.gen.ps` or
`holo.characterize`.  Its body — everything after `%%EndComments` up to
`%%Trailer`, its own `setpagedevice` request included — is copied
VERBATIM; only the DSC header, the `%%Page:` numbering and the trailer
are the aggregate's.  The discovery pair goes first: its HCAL-R1
"pre-request device snapshot" reads `currentpagedevice` before its own
request, and must see the job's fresh state, not a payload page's
`/HWResolution [600 600]` request.  Nothing here prints.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


def sources(root: Path) -> list[Path]:
    disc = sorted(root.glob("discovery/hcal-discovery-bw-*.ps")) + \
        sorted(root.glob("discovery/hcal-discovery-color-*.ps"))
    vols = sorted(root.glob("[A-Z]-*/page000.ps"))
    if len(disc) != 2 or not vols:
        raise SystemExit(f"expected 2 discovery jobs + volumes under {root}: "
                         f"{len(disc)} / {len(vols)}")
    return disc + vols


def body_of(path: Path) -> tuple[bytes, bytes]:
    """(title, body): the body is every line strictly between
    `%%EndComments` and `%%Trailer`, with the source's `%%Page:` line
    dropped (the aggregate numbers the pages)."""
    title = b""
    out: list[bytes] = []
    in_body = False
    with path.open("rb") as fh:
        first = fh.readline()
        if not first.startswith(b"%!PS-Adobe-3.0"):
            raise SystemExit(f"{path}: not a DSC 3.0 job: {first[:40]!r}")
        for line in fh:
            if not in_body:
                if line.startswith(b"%%Title:"):
                    title = line[len(b"%%Title:"):].strip()
                elif line.startswith(b"%%EndComments"):
                    in_body = True
                continue
            if line.startswith(b"%%Trailer"):
                break
            if line.startswith(b"%%Page:"):
                continue
            out.append(line)
        else:
            raise SystemExit(f"{path}: no %%Trailer")
    return title, b"".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, required=True,
                    help="generate_set.py's --out")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()
    root: Path = args.root
    out: Path = args.out or root / "e039-all-pages.ps"
    srcs = sources(root)
    n = len(srcs)
    with out.open("wb") as fh:
        fh.write(b"%!PS-Adobe-3.0\n")
        fh.write(b"%%Title: e039 Xerox VersaLink set - discovery pair + candidate volumes, one sheet per page\n")
        fh.write(b"%%Creator: experiments/039-xerox-versalink/coalesce_ps.py\n")
        fh.write(b"%%LanguageLevel: 2\n%%DocumentData: Clean7Bit\n")
        fh.write(b"%%BoundingBox: 0 0 596 842\n")
        fh.write(b"%%Pages: %d\n%%EndComments\n" % n)
        for k, src in enumerate(srcs, 1):
            title, body = body_of(src)
            sha = hashlib.sha256(src.read_bytes()).hexdigest()
            rel = src.relative_to(root)
            fh.write(b"%%%%Page: %d %d\n" % (k, k))
            fh.write(b"%% e039 page %d/%d  source %s  sha256 %s\n"
                     % (k, n, str(rel).encode(), sha.encode()))
            fh.write(b"% source title: " + title + b"\n")
            fh.write(body)
            print(f"page {k:2d}: {rel}  ({sha[:12]}…)", file=sys.stderr)
        fh.write(b"%%Trailer\n%%EOF\n")
    print(f"{out}  {out.stat().st_size:,} B  sha256 "
          f"{hashlib.sha256(out.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
