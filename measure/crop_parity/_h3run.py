#!/usr/bin/env python
"""THE HOLO3 SIDE — one crop decode in a subprocess, with its bits.

    PYTHONPATH=. env314t/bin/python -m measure.crop_parity._h3run \\
        --certs-out <run>/holo3-certs.json -- \\
        decode <crop.tiff> --dpi 4800 --format L:c2-r0700@3392x2368 \\
        --no-close --workers 1 --run-dir <run> --out <run>/holo3.out

WHY NOT THE PLAIN CLI. ``holo3 decode`` writes ``events.jsonl`` and
``report.json``, which give the certified ADDRESS set — but holo3 keeps
no state file, and no event carries a certificate's user bits. The
zero-wrong audit needs the bits. So this entry runs the CLI's OWN path
and keeps the store:

    args    = holo3.cli._build_parser().parse_args(argv)
    request = holo3.cli._request(args)          # the CLI's own request
    engine._Engine(request, events).run()       # what cli._decode calls
    certificates()                              # _Store's public reader

Nothing is reimplemented: the argv is parsed by holo3's parser, so a
flag this harness passes means exactly what it means on the command
line, and the run dir gets the same ``events.jsonl`` / ``report.json``
the CLI would have written (``engine._diag_products`` runs inside
``run()``). The one thing added is ``--certs-out``: a JSON sidecar of
``{address: packed user bits}`` for the audit.

DEGRADED MODE. If a future holo3 refactor moves ``_Engine`` or
``certificates()``, this entry falls back to ``holo3.cli.main(argv)``
and writes a certs sidecar marked ``bits_available: false``. The
harness then reports the address-level comparison and says, in the
report, that the wrong-certificate audit could not run on this side —
never a silent zero.

MEMORY: one decode per process, ``--workers 1`` by default from the
caller, and the process exits when the decode does.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np


def _packed(bits: np.ndarray) -> str:
    array = np.asarray(bits, dtype=np.uint8).ravel()
    return np.packbits(array, bitorder="little").tobytes().hex()


def _run_with_store(argv: list[str]) -> dict:
    from holo3 import cli, engine

    args = cli._build_parser().parse_args(argv)
    if args.command != "decode":
        raise SystemExit("_h3run: only 'decode' is supported")
    request = cli._request(args)
    events: list = []
    started = time.perf_counter()
    running = engine._Engine(request, events)
    result = running.run()
    wall = time.perf_counter() - started
    certificates = running.certificates()
    rows = []
    for key in sorted(certificates):
        page, ty, tx, stream = key
        certificate = certificates[key]
        rows.append({"address": [int(page), int(ty), int(tx), str(stream)],
                     "n_bits": int(np.asarray(
                         certificate.user_bits).ravel().size),
                     "bits": _packed(certificate.user_bits),
                     "source": str(certificate.source)})
    return {"bits_available": True, "wall_seconds": wall,
            "status": str(result.status),
            "n_certificates": int(result.certified),
            "run_dir": str(request.run_dir),
            "certificates": rows}


def _run_cli_only(argv: list[str]) -> dict:
    from holo3 import cli

    started = time.perf_counter()
    code = cli.main(argv)
    return {"bits_available": False, "wall_seconds": time.perf_counter()
            - started, "status": f"cli exit {code}", "n_certificates": None,
            "run_dir": None, "certificates": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--certs-out", type=Path, required=True)
    parser.add_argument("decode_argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    decode_argv = [item for item in args.decode_argv if item != "--"]
    if not decode_argv or decode_argv[0] != "decode":
        raise SystemExit("_h3run: pass the holo3 decode argv after --")

    try:
        payload = _run_with_store(decode_argv)
    except AttributeError as exc:            # a holo3 refactor moved a seam
        print(f"_h3run: store route unavailable ({exc}); falling back to "
              f"the plain CLI — the bit audit cannot run on this side",
              file=sys.stderr)
        payload = _run_cli_only(decode_argv)
    args.certs_out.parent.mkdir(parents=True, exist_ok=True)
    args.certs_out.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    print(f"_h3run: {payload['status']}, "
          f"{len(payload['certificates'])} certificates in "
          f"{payload['wall_seconds']:.1f} s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
