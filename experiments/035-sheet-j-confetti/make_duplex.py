"""Splice single-page holo emissions into one duplex PostScript job.

Reproduces the e035 sheet-J `duplex.ps` byte-for-byte from `page000.ps` and
`page001.ps`: the first page's DSC header with the title, page count and the
setpagedevice line rewritten for duplex, then every page's body (from its
`%%Page:` line through `showpage`) renumbered, then one trailer.

    python make_duplex.py page000.ps page001.ps -o duplex.ps [--title TITLE]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

PAGE_RE = re.compile(rb"^%%Page: 1 1\n", re.M)
SHOWPAGE = b"showpage\n"
TRAILER = b"%%Trailer\n%%EOF\n"


def split_page(ps: bytes) -> tuple[bytes, bytes]:
    """Return (header up to and excluding %%Page, body from after %%Page through showpage)."""
    m = PAGE_RE.search(ps)
    if m is None:
        raise ValueError("no %%Page: 1 1 line")
    end = ps.rfind(SHOWPAGE)
    if end < 0:
        raise ValueError("no showpage")
    return ps[: m.start()], ps[m.end() : end + len(SHOWPAGE)]


def duplex_header(header: bytes, n_pages: int, title: bytes | None) -> bytes:
    lines = header.split(b"\n")
    out = []
    for line in lines:
        if line.startswith(b"%%Title:"):
            if title is None:
                base = line[len(b"%%Title: ") :]
                base = re.sub(rb" p\d{3} J=[0-9a-f]+$", b"", base)
                pages = b"+".join(b"p%03d" % i for i in range(n_pages))
                line = b"%%Title: " + base + b" " + pages + b" duplex"
            else:
                line = b"%%Title: " + title
        elif line.startswith(b"%%Pages:"):
            line = b"%%%%Pages: %d" % n_pages
        elif b"setpagedevice" in line and b"/Duplex false" in line:
            line = line.replace(b"/Duplex false", b"/Duplex true /Tumble false")
        out.append(line)
    return b"\n".join(out)


def splice(pages: list[bytes], title: bytes | None = None) -> bytes:
    header, _ = split_page(pages[0])
    parts = [duplex_header(header, len(pages), title)]
    for i, ps in enumerate(pages, start=1):
        _, body = split_page(ps)
        parts.append(b"%%%%Page: %d %d\n" % (i, i) + body)
    parts.append(TRAILER)
    return b"".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", nargs="+", type=Path, help="single-page .ps emissions, in print order")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--title", help="override the %%Title line (default: derived from page 1)")
    ap.add_argument("--expect-sha256", help="refuse to write unless the result has this sha256")
    a = ap.parse_args(argv)
    data = splice([p.read_bytes() for p in a.pages], a.title.encode() if a.title else None)
    digest = hashlib.sha256(data).hexdigest()
    if a.expect_sha256 and digest != a.expect_sha256:
        print(f"sha256 mismatch: got {digest}, expected {a.expect_sha256}", file=sys.stderr)
        return 1
    a.out.write_bytes(data)
    print(f"{a.out}: {len(data)} bytes sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
