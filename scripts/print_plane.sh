#!/usr/bin/env bash
# Print a prepared 1-bit job on the TRUE raw path (JetDirect socket, port 9100).
# SAFETY: interactive confirmation required; Claude Code must ask the user first.
#
# Why not CUPS: not because it was caught corrupting jobs (run 001.2/001.3's
# "nondeterministic lpr" alarm was retracted — both paths printed equivalently),
# but because AppSocket 9100 removes CUPS/IPP as a variable entirely: bytes hit
# the printer's language auto-sense directly, so prints are attributable to the
# file alone. See experiments/001-engine-characterization.md runs 001.2/001.3.
# See DESIGN.md 2.4: bypass ICC/halftoning/RET/toner-save; note the MIC yellow dots.
set -euo pipefail
FILE="${1:?usage: print_plane.sh <prerendered .ps/.pcl> [host]}"
# interactive confirmation is the safety mechanism: refuse LOUDLY without a
# tty (016.1 lesson: run non-interactively, read dies at EOF under set -e
# BEFORE sending anything, and a caller piping output can mask the status)
[ -t 0 ] || { echo "refusing: interactive confirmation requires a terminal" >&2; exit 2; }
HOST="${2:-${PAPERHOLO_PRINTER_HOST:-<host>}}"
read -r -p "Physically print '$FILE' via raw socket $HOST:9100? [yes/NO] " ok
[ "$ok" = "yes" ] || { echo "aborted"; exit 1; }
shasum -a 256 "$FILE"
# PRINT_NC_WAIT (default 10 s idle) and PRINT_BACKCHANNEL (a file) keep the
# connection open after the send and capture what the printer says back on
# it — the PCL XL error report (ErrorReport eBackCh...) and PJL USTATUS come
# this way and are lost when the socket closes early (e041 S10p, 2026-10-05).
NC_WAIT="${PRINT_NC_WAIT:-10}"
if [ -n "${PRINT_BACKCHANNEL:-}" ]; then
  nc -w "$NC_WAIT" "$HOST" 9100 < "$FILE" | tee "$PRINT_BACKCHANNEL"
else
  nc -w "$NC_WAIT" "$HOST" 9100 < "$FILE"
fi
echo "sent $(wc -c < "$FILE" | tr -d ' ') bytes to $HOST:9100"
