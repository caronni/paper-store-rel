#!/usr/bin/env bash
# Acquire a raw, uncorrected scan for decoding.
# TODO(M4): pin device + backend flags after `scanimage -L` on the target scanner.
set -euo pipefail
OUT="${1:?usage: scan.sh <out.tiff> [dpi]}"
DPI="${2:-2400}"
scanimage --format=tiff --resolution "$DPI" --mode Color --depth 16 > "$OUT"
# DESIGN.md 3: >=2x symbol-frequency oversampling, 16-bit, all "enhancements"/ICC off
# (the off-switches are backend-specific; document them here once known).
echo "scanned -> $OUT"
sha256sum "$OUT"
