#!/usr/bin/env bash
# Print a prepared .ps job wrapped in a per-job PJL envelope: DENSITY 1-5,
# optional RET=ON|OFF or ECONOMODE=ON|OFF. Uses @PJL SET only (never
# DEFAULT) — nothing persists on the engine after the job.
# SAFETY: interactive confirmation required; Claude Code must ask the user
# first (.claude/rules/hardware.md). Same raw 9100 discipline as
# print_plane.sh; PJL variable provenance: the exp 005.0 recon
# (experiments/005-density-ladder.md).
set -euo pipefail
FILE="${1:?usage: print_density.sh <job.ps> <density 1-5> [RET=OFF|ECONOMODE=ON] [host]}"
DENS="${2:?density 1-5 required}"
EXTRA="${3:-}"
HOST="${4:-${PAPERHOLO_PRINTER_HOST:-<host>}}"
[[ "$DENS" =~ ^[1-5]$ ]] || { echo "density must be 1-5"; exit 1; }
if [ -n "$EXTRA" ] && ! [[ "$EXTRA" =~ ^(RET|ECONOMODE)=(ON|OFF)$ ]]; then
  echo "extra must be RET=ON|OFF or ECONOMODE=ON|OFF"; exit 1
fi
UEL=$'\x1b%-12345X'
read -r -p "Physically print '$FILE' at DENSITY=$DENS ${EXTRA:+$EXTRA }via raw socket $HOST:9100? [yes/NO] " ok
[ "$ok" = "yes" ] || { echo "aborted"; exit 1; }
shasum -a 256 "$FILE"
{
  printf '%s' "$UEL"
  printf '@PJL\r\n'
  printf '@PJL SET DENSITY=%s\r\n' "$DENS"
  [ -n "$EXTRA" ] && printf '@PJL SET %s\r\n' "$EXTRA"
  printf '@PJL ENTER LANGUAGE=POSTSCRIPT\r\n'
  cat "$FILE"
  printf '%s' "$UEL"
} | nc -w 10 "$HOST" 9100
echo "sent $(wc -c < "$FILE" | tr -d ' ') payload bytes at DENSITY=$DENS ${EXTRA:+($EXTRA)} to $HOST:9100"
