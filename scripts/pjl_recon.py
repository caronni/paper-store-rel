#!/usr/bin/env python3
"""Read-only device recon over JetDirect 9100 (PJL INFO + guarded PS probe).

Queries only — prints NOTHING and changes NO device state:
  phase 1: PJL INFO ID / CONFIG / VARIABLES / STATUS (the long-shelved
           zero-paper recon from exp 002; enumerates settable variables
           incl. DENSITY / ECONOMODE / RET and their ranges).
  phase 2: a minimal PostScript job with NO showpage, every query inside a
           stopped-guard, results returned on the socket backchannel:
           statusdict density operators (historical HP /setprintdensity),
           currentpagedevice key list.

Usage: pjl_recon.py [host] > transcript.txt     (default host <host>)
Run ONLY with explicit user authorization in-session (.claude/rules/
hardware.md — this touches the engine, even though it cannot print).
"""
from __future__ import annotations

import socket
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "<host>"
PORT = 9100
UEL = b"\x1b%-12345X"

PJL_JOB = UEL + b"@PJL\r\n" \
    b"@PJL INFO ID\r\n" \
    b"@PJL INFO CONFIG\r\n" \
    b"@PJL INFO VARIABLES\r\n" \
    b"@PJL INFO STATUS\r\n" + UEL

PS_PROBE = UEL + b"@PJL ENTER LANGUAGE=POSTSCRIPT\r\n" + b"""%!PS
/say { print (\\n) print flush } def
(== ps-probe begin ==) say
{ statusdict /setprintdensity known
  { (statusdict setprintdensity: KNOWN) } { (statusdict setprintdensity: absent) } ifelse say
} stopped { (statusdict setprintdensity: ERROR) say } if
{ statusdict /printdensity known
  { (statusdict printdensity: KNOWN) } { (statusdict printdensity: absent) } ifelse say
} stopped { (statusdict printdensity: ERROR) say } if
{ statusdict /product get say } stopped { (product: ERROR) say } if
(== currentpagedevice keys ==) say
{ currentpagedevice { pop 128 string cvs say } forall
} stopped { (currentpagedevice walk: ERROR) say } if
(== ps-probe end ==) say
""" + UEL


def talk(payload: bytes, label: str, quiet_s: float = 4.0,
         total_s: float = 25.0) -> bytes:
    print(f"---- {label}: sending {len(payload)} bytes to {HOST}:{PORT} ----",
          file=sys.stderr)
    out = b""
    with socket.create_connection((HOST, PORT), timeout=10) as s:
        s.sendall(payload)
        s.settimeout(quiet_s)
        t0 = time.time()
        while time.time() - t0 < total_s:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            out += chunk
    print(f"---- {label}: received {len(out)} bytes ----", file=sys.stderr)
    return out


def main() -> None:
    for label, payload in (("pjl-info", PJL_JOB), ("ps-probe", PS_PROBE)):
        data = talk(payload, label)
        sys.stdout.write(f"\n======== {label} ========\n")
        sys.stdout.write(data.decode("latin-1", errors="replace"))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
