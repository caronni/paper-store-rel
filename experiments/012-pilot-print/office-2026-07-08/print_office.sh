#!/usr/bin/env bash
# Office print run 2026-07-08 — AltaLink C8245, raw 9100 (host from 009: <ip>).
# Usage: ./print_office.sh e012.ps [more.ps ...]     (or no args = ALL sheets)
# Verifies sha256 before sending. K-only sheets => no MIC dots (measured 007.7/007.8).
set -euo pipefail
HOST="${PAPERHOLO_PRINTER_HOST:-<ip>}"
declare -A SHA=(
  [e012.ps]=8fcd89dd2a646b2c1d3adf092ca3f967d030f4d35d03e537bb943a14412540a1
  [e004.ps]=c5c35d94c0940b82a612dc48c7721130240709cce094a3438fce790d08f9ca68
  [e006bw.ps]=797232ee1a51a3c8c0ddb173ee98a7f1a249e009f9cf3543adc95bf34c4c129e
  [e006c.ps]=15e27c95d81c7a0f703147c8d783569ebc34e60818484c88b1fd2a6c9d6d960b
)
FILES=("${@:-e012.ps e012.ps e004.ps e006bw.ps e006c.ps}")
[ $# -eq 0 ] && FILES=(e012.ps e012.ps e004.ps e006bw.ps e006c.ps)
for f in "${FILES[@]}"; do
  got=$(shasum -a 256 "$f" | cut -d' ' -f1)
  [ "$got" = "${SHA[$f]}" ] || { echo "SHA MISMATCH on $f — do not print"; exit 1; }
  echo "sending $f (sha ok) -> $HOST:9100"
  nc -w 10 "$HOST" 9100 < "$f"
  sleep 2
done
echo "done. Label sheets in print order; e012 prints are content-identical (log = the only disambiguator)."
