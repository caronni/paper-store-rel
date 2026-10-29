#!/usr/bin/env bash
# demo.sh RUN_DIR: generate a volume, transform it into a simulated scan, holo3-decode it
set -euo pipefail

RUN_DIR="${1:-build/demo}"
FORMAT="c3-k-r0550@7x7"
SOURCE_FRACTION="0.5"
DPI="1200"

mkdir -p "$RUN_DIR"
printf 'x%.0s' {1..500} > "$RUN_DIR/payload.bin"

./confetti.py generate "$RUN_DIR/payload.bin" --format "$FORMAT" --source-fraction "$SOURCE_FRACTION" -o "$RUN_DIR/volume"

gs -dSAFER -dBATCH -dNOPAUSE -dQUIET -sDEVICE=tiff24nc -r600 -sOutputFile="$RUN_DIR/print.tif" "$RUN_DIR/volume/page000.ps"
PYTHONPATH=src ./env/bin/python -m holo.qualification.color_distort "$RUN_DIR/print.tif" "$RUN_DIR/scan.tif" --profile nominal --output-dpi "$DPI" --seed 0

./confetti3.py decode "$RUN_DIR/scan.tif" --dpi "$DPI" --format "$FORMAT" --out "$RUN_DIR/recovered.bin"
