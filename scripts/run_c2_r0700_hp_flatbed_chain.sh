#!/usr/bin/env bash
# Run the synthetic Holo chain for the K-only c2-r0700 rung on the measured
# HP channel: a 5-page maximum-capacity volume at source fraction 0.7 with
# HP M281 geometry, clean 600 dpi Ghostscript renders, the frozen CAL-1
# hp-m281-flatbed-k print+scan simulator (bit-faithful K imagemask path,
# emits 1200 dpi grayscale), two scrap sheets of 25 scraps per printed
# page (10 captures), and receiver processing with mop-up and refinement.
#
# This is synthetic qualification against the characterized CAL-1 channel
# (screened-composite emission), not a fresh hardware run.
# Scrap long edges are 24-72mm: the tool's default 28-105mm cannot place
# 25 non-overlapping scraps per sheet at this canvas size (probed on the
# exact 14032x9920 @1200dpi canvas, all 10 sheets, 2026-08-02).
# decode --workers assumes the holo-parallel-tier1 receiver is merged.
# The five per-page front-end chains run in parallel (each CAL-1 distort
# takes ~35 s and peaks at a few GB of RAM).
# Expect roughly 7 GiB of retained raster artifacts.
set -euo pipefail

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "usage: $0 [fresh-run-directory] [diagnostic-port]"
  echo "default run directory: scratch/c2-r0700-hp-flatbed1200-q070-5p-25x2-<timestamp>"
  echo "default diagnostic port: 8023"
  exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUN_DIR="${1:-scratch/c2-r0700-hp-flatbed1200-q070-5p-25x2-$(date +%Y%m%d-%H%M%S)}"
DIAG_PORT="${2:-8023}"
PYTHON="./env/bin/python"
CODING="c2-r0700"
PRINTER="hp-m281"
SOURCE_FRACTION="0.7"
PAGES=5
SCAN_DPI=1200
SEED_BASE=20260802
WORKERS=16
EXPECTED_PAYLOAD_BYTES="2244263"

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
    --pages "$PAGES" \
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

# Render, distort, and scrap-cut one printed page. Pages are independent
# (per-page seeds, distinct outputs, atomic staging in both tools), so the
# five chains run in parallel below.
front_end_page() {
  local page="$1" P SEED
  printf -v P '%03d' "$page"
  SEED=$((SEED_BASE + page))

  gs \
    -dSAFER \
    -dNOPAUSE \
    -dBATCH \
    -dQUIET \
    -sDEVICE=tiff24nc \
    -dTextAlphaBits=1 \
    -dGraphicsAlphaBits=1 \
    -r600 \
    -sOutputFile="$RUN_DIR/page$P-gs-r600.tif" \
    "$RUN_DIR/volume/page$P.ps"

  env PYTHONPATH=src "$PYTHON" -m holo.qualification.color_distort \
    "$RUN_DIR/page$P-gs-r600.tif" \
    "$RUN_DIR/page$P-hp1200.tif" \
    --profile hp-m281-flatbed-k \
    --seed "$SEED" \
    --output-dpi "$SCAN_DPI"

  env PYTHONPATH=src "$PYTHON" -m holo.qualification.scrap_scan \
    "$RUN_DIR/page$P-hp1200.tif" \
    "$RUN_DIR/scraps-p$P.tif" \
    --pages 2 \
    --scraps 25 \
    --size-mm 24 72 \
    --seed "$SEED"
}

PIDS=()
for page in $(seq 0 $((PAGES - 1))); do
  front_end_page "$page" &
  PIDS+=($!)
done
for pid in "${PIDS[@]}"; do
  wait "$pid"
done

SCAN_ARGS=()
DPI_ARGS=()
PAGE_ARGS=()
for page in $(seq 0 $((PAGES - 1))); do
  printf -v P '%03d' "$page"
  for sheet in 001 002; do
    SCAN_ARGS+=("$RUN_DIR/scraps-p$P-$sheet.tif")
    DPI_ARGS+=(--scan-dpi "$SCAN_DPI")
  done
  PAGE_ARGS+=(--page "$page")
done

echo "live diagnostics: http://127.0.0.1:$DIAG_PORT/"

env PYTHONPATH=src "$PYTHON" -m holo.cli decode \
  "${SCAN_ARGS[0]}" \
  "${DPI_ARGS[0]}" "${DPI_ARGS[1]}"\
  --coding "$CODING" \
  --printer "$PRINTER" \
  "${PAGE_ARGS[@]}" \
  --state "$RUN_DIR/receive.json" \
  --out "$RUN_DIR/recovered.bin" \
  --mopup \
  --refine \
  --workers "$WORKERS" \
  --diag \
  --diag-dir "$RUN_DIR/diag" \
  --diag-port "$DIAG_PORT" \
  --diag-interval 1 \
  --diag-panel-width 600

env PYTHONPATH=src "$PYTHON" -m holo.cli decode \
  "${SCAN_ARGS[@]}" \
  "${DPI_ARGS[@]}" \
  --coding "$CODING" \
  --printer "$PRINTER" \
  "${PAGE_ARGS[@]}" \
  --state "$RUN_DIR/receive.json" \
  --out "$RUN_DIR/recovered.bin" \
  --mopup \
  --refine \
  --workers "$WORKERS" \
  --diag \
  --diag-dir "$RUN_DIR/diag" \
  --diag-port "$DIAG_PORT" \
  --diag-interval 1 \
  --diag-panel-width 600

cmp "$RUN_DIR/payload.bin" "$RUN_DIR/recovered.bin"
echo "verified byte-identical recovery: $RUN_DIR/recovered.bin"
shasum -a 256 "$RUN_DIR/payload.bin" "$RUN_DIR/recovered.bin"
