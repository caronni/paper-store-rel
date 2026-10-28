#!/usr/bin/env bash
# Run the complete synthetic Holo chain used for the 2026-07-29 exercise:
# maximum-capacity c2 CMY7 page with HP M281 geometry, a clean 600 dpi
# Ghostscript render, nominal distortion sampled at Canon's 4800 dpi,
# two scan pages with 20 scraps each, and complete receiver processing.
#
# This is synthetic qualification, not a characterized HP/Canon paper channel.
# Expect roughly 20 GiB of retained raster artifacts.
set -euo pipefail

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "usage: $0 [fresh-run-directory] [diagnostic-port]"
  echo "default run directory: scratch/c2-cmy7-hp-nominal-canon4800-q070-max-20x2-<timestamp>"
  echo "default diagnostic port: 8023"
  exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUN_DIR="${1:-scratch/c2-cmy7-hp-nominal-canon4800-q070-max-20x2-$(date +%Y%m%d-%H%M%S)}"
DIAG_PORT="${2:-8023}"
PYTHON="./env/bin/python"
CODING="c2-cmy7-p120-v0"
PRINTER="hp-m281"
SOURCE_FRACTION="0.7"
EXPECTED_PAYLOAD_BYTES="966096"

if [ -e "$RUN_DIR" ]; then
  echo "refusing existing run directory: $RUN_DIR" >&2
  exit 1
fi
if ! [[ "$DIAG_PORT" =~ ^[1-9][0-9]*$ ]] || [ "$DIAG_PORT" -gt 65535 ]; then
  echo "diagnostic port must be an integer from 1 through 65535" >&2
  exit 1
fi
if lsof -nP -iTCP:"$DIAG_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "diagnostic port is already in use: $DIAG_PORT" >&2
  exit 1
fi

mkdir -p "$RUN_DIR"

CAPACITY_JSON="$(
  env PYTHONPATH=src "$PYTHON" -m holo.cli capacity \
    --coding "$CODING" \
    --source-fraction "$SOURCE_FRACTION" \
    --printer "$PRINTER" \
    --pages 1 \
    --json
)"
printf '%s\n' "$CAPACITY_JSON"
PAYLOAD_BYTES="$(
  printf '%s\n' "$CAPACITY_JSON" |
    "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["max_payload_bytes"])'
)"
if [ "$PAYLOAD_BYTES" != "$EXPECTED_PAYLOAD_BYTES" ]; then
  echo "capacity changed: expected $EXPECTED_PAYLOAD_BYTES bytes, got $PAYLOAD_BYTES" >&2
  exit 1
fi

dd \
  if=/dev/zero \
  of="$RUN_DIR/payload.bin" \
  bs="$PAYLOAD_BYTES" \
  count=1

env PYTHONPATH=src "$PYTHON" -m holo.cli generate \
  "$RUN_DIR/payload.bin" \
  --coding "$CODING" \
  --source-fraction "$SOURCE_FRACTION" \
  --printer "$PRINTER" \
  --out "$RUN_DIR/volume"

gs \
  -dSAFER \
  -dNOPAUSE \
  -dBATCH \
  -dQUIET \
  -sDEVICE=tiff24nc \
  -dTextAlphaBits=1 \
  -dGraphicsAlphaBits=1 \
  -r600 \
  -sOutputFile="$RUN_DIR/page000-gs-r600.tif" \
  "$RUN_DIR/volume/page000.ps"

env PYTHONPATH=src "$PYTHON" -m holo.qualification.color_distort \
  "$RUN_DIR/page000-gs-r600.tif" \
  "$RUN_DIR/full-nominal-r4800.tif" \
  --profile nominal \
  --seed 20260729 \
  --output-dpi 4800

env PYTHONPATH=src "$PYTHON" -m holo.qualification.scrap_scan \
  "$RUN_DIR/full-nominal-r4800.tif" \
  "$RUN_DIR/scraps-r4800.tif" \
  --pages 2 \
  --scraps 20 \
  --seed 20260730

echo "live diagnostics: http://127.0.0.1:$DIAG_PORT/"

env PYTHONPATH=src "$PYTHON" -m holo.cli decode \
  "$RUN_DIR/scraps-r4800-001.tif" \
  "$RUN_DIR/scraps-r4800-002.tif" \
  --scan-dpi 4800 \
  --scan-dpi 4800 \
  --coding "$CODING" \
  --printer "$PRINTER" \
  --page 0 \
  --state "$RUN_DIR/receive.json" \
  --out "$RUN_DIR/recovered.bin" \
  --complete \
  --diag \
  --diag-dir "$RUN_DIR/diag" \
  --diag-port "$DIAG_PORT" \
  --diag-interval 1 \
  --diag-panel-width 600

cmp "$RUN_DIR/payload.bin" "$RUN_DIR/recovered.bin"
echo "verified byte-identical recovery: $RUN_DIR/recovered.bin"
shasum -a 256 "$RUN_DIR/payload.bin" "$RUN_DIR/recovered.bin"
