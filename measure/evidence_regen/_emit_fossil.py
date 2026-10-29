"""Emit one fossil-only volume (e033 A, H, I) through main's python route.

    PYTHONPATH=<tree>/src <python> _emit_fossil.py L:<fossil id> Q OUT_DIR PRINTER_ID

`./confetti.py generate --format L:...` is refused at main (cli_gen parses a
v2 id); `resolve_format_ref` resolves the fossil and `emit_volume` writes it.
The payload is e033's counting rule filling the page exactly at Q, also
written as OUT_DIR/payload-counting.bin.  Imports whichever `holo` the
PYTHONPATH names, so it runs against the tree under test.
"""
from __future__ import annotations

import sys
from pathlib import Path

from holo.format.resolve import resolve_format_ref
from holo.gen.emit import emit_volume
from holo.gen.plan import max_payload_bytes


def main(argv: list[str]) -> int:
    ref, q_text, out_text, printer_id = argv
    spec = resolve_format_ref(ref)
    q = float(q_text)
    payload = bytes(i & 0xFF for i in range(max_payload_bytes(spec, q, 1)))
    out = Path(out_text)
    emit_volume(spec, payload, q, out, printer_id=printer_id)
    (out / "payload-counting.bin").write_bytes(payload)
    print(f"{ref} q={q} {len(payload)} B -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
