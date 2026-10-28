#!/usr/bin/env bash
# demo.sh — the 3-page c2/r0700 counting-volume chain, decoded by holo2.
#
# 1 MB counting payload -> 3-page c2-r0700 volume at source fraction 0.7
# -> 600 dpi print TIFFs (gs) -> nominal-profile synthetic scans at 4800 dpi
# -> 3 scrap platens per page (20 scraps each) -> holo2 decode on :8024.
#
# Only the LAST step is holo2. holo2 is the receiver rewrite and nothing
# else: generation, the channel simulator and the scrap cutter stay in
# holo v1 (src/holo) and are invoked exactly as before. The v1 receiver
# (`confetti.py decode`) is what confetti2 replaces.
#
# Flag mapping from the v1-shaped invocation this script was translated
# from (the v1 receiver's selection flags do not survive):
#
#   --alias a4-4mm            -> --printer hp-m281-ink   (A4, 4.5 mm margins;
#                                there is no 4.0 mm row — this is the e028
#                                ink-clip geometry, c2-r0700@3392x2368)
#   --cell c2 --codec k
#     --rates r0700           -> --coding c2-r0700
#   --filler 0                -> implicit: every k-v1 row is n_filler=0
#   --source-fraction 0.7     -> unchanged (generation only; the receiver
#                                learns K from the metadata sidechannel)
#   confetti.py decode ...    -> ./confetti2.py ...   (decode is implicit —
#                                holo2 has exactly one command)
#   --scan F --dpi D          -> --scan F --dpi D, but BOTH repeat and pair
#                                positionally; no scan may omit its DPI
#   --last-page 2             -> --pages 3            (page COUNT, not index)
#   --state DIR               -> --state-dir DIR      (journal + blob store)
#   -o FILE                   -> --output FILE        (never overwritten)
#   (implicit page geometry)  -> --tiles-y/--tiles-x, operator-declared:
#                                holo2 refuses to guess a printed field
#   :8024                     -> --diag-port 8024 (the default; the diag
#                                endpoint is always on, and a port that will
#                                not bind costs one stderr line, not the run)
#
# COST WARNING: --output-dpi 4800 makes every page raster ~6.7 GB
# (39680x56128 RGB, uncompressed BigTIFF), and this chain writes 3 of them
# plus 9 scrap platens of the same size — roughly 85 GB on disk, all of
# which the decode then ingests. SCAN_DPI=1200 is the other supported rung
# and is what the archived real captures are decimated to anyway (e028
# knife-edge: the Canon's glass-level information ceiling is ~860 dpi).
#
# RERUN: this script is RESUMABLE, and re-running it on a run directory
# that already holds the expensive preparation costs seconds, not hours.
# Every stage is gated on its own output:
#
#   payload   rewritten unconditionally (1 MB, deterministic)
#   volume    skipped when manifest.json's payload sha AND every page's
#             ps_sha256 match the files on disk — the volume's own record
#             of what it is, so an adopted volume is the one this payload
#             produced, not merely a directory of the right shape
#   print/    skipped per page when the raster is STRUCTURALLY COMPLETE:
#   scan/     the TIFF header's last strip offset+bytecount must fit
#   scraps    inside the file. Header-only, ~30 ms for all 15 rasters, and
#             it is what catches a run killed mid-write. An incomplete
#             raster is deleted and rebuilt (the v1 writers publish by
#             hardlink-from-staging and refuse every overwrite, so a
#             leftover under the live name has to go before a retry).
#             A complete scan skips the gs render too — the print TIFF is
#             only the distorter's input.
#   receive   resumes from --state-dir on its own: the journal is
#             authoritative and replays what the last run committed
#             (holo2/docs/DESIGN.md §5.6, F-16), and <state-dir>.prepared
#             re-uses the content-addressed prepared planes — 42 GB of
#             fill/filter/support that would otherwise be rebuilt. When
#             recovered.bin is already there the decode is skipped
#             entirely and only the verification runs.
#
# The run directory carries a parameter stamp (demo-params.txt), and a
# rerun under changed parameters REFUSES rather than mixing two chains.
#
# Synthetic qualification against the `nominal` profile — not a hardware
# run, and holo2's receiver status is PROVISIONAL.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUN_DIR="${1:-build/demo}"
DIAG_PORT="${2:-8024}"
if [ -z "$RUN_DIR" ]; then
  echo "empty run directory" >&2
  exit 1
fi
PYTHON="./env/bin/python"
CODING="c2-r0700"
PRINTER="hp-m281-ink"
SOURCE_FRACTION="0.7"
PAGES=3
SCAN_DPI=4800
SCRAPS=20
PLATENS=3
# c2-r0700@3392x2368 = 53x37 tiles/page (1961 tiles). Operator-declared to
# the receiver; `./confetti.py capacity --coding … --printer … --json`
# prints the field this generate call lays down.
TILES_Y=53
TILES_X=37
# holo2's default is 1, and serial is the measured-fastest configuration on
# the current leaves (M-WS 2026-08-15: the stand-in fires are GIL-bound).
# 8 is carried over from the v1 invocation; drop it to 1 if timing matters.
WORKERS=8

# --- resume machinery ---------------------------------------------------

# Is this raster fully written? The TIFF header alone answers it: every
# strip's offset+bytecount must land inside the file. Cheap (no pixels are
# read) and exactly the failure a killed writer leaves behind.
tif_complete() {
  [ -f "$1" ] || return 1
  "$PYTHON" - "$1" <<'PY'
import os
import sys

import tifffile

path = sys.argv[1]
try:
    size = os.path.getsize(path)
    with tifffile.TiffFile(path) as tif:
        need = max(offset + count
                   for page in tif.pages
                   for offset, count in zip(page.dataoffsets,
                                            page.databytecounts))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if need <= size else 1)
PY
}

# Do the volume's own manifest shas match the files on disk, for THIS
# payload and THIS page count? `confetti.py generate` refuses to write
# into an existing directory, so adopting one has to be an identity check,
# not an existence check.
volume_complete() {
  "$PYTHON" - "$RUN_DIR/volume" "$RUN_DIR/payload-counting.bin" "$PAGES" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

volume, payload, pages = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


try:
    manifest = json.loads((volume / "manifest.json").read_text())
    if manifest["payload"]["sha256"] != sha256(payload):
        raise SystemExit(1)
    if len(manifest["pages"]) != pages:
        raise SystemExit(1)
    for page in manifest["pages"]:
        ps = volume / page["ps"]
        if not ps.is_file() or sha256(ps) != page["ps_sha256"]:
            raise SystemExit(1)
except Exception:
    raise SystemExit(1)
PY
}

params_now() {
  cat <<EOF
coding=$CODING
printer=$PRINTER
source_fraction=$SOURCE_FRACTION
pages=$PAGES
scan_dpi=$SCAN_DPI
scraps=$SCRAPS
platens=$PLATENS
tiles=${TILES_Y}x${TILES_X}
EOF
}

PARAMS_FILE="$RUN_DIR/demo-params.txt"
mkdir -p "$RUN_DIR"
if [ -f "$PARAMS_FILE" ]; then
  if ! params_now | diff -q "$PARAMS_FILE" - >/dev/null; then
    echo "refusing to resume $RUN_DIR: built with different parameters" >&2
    params_now | diff "$PARAMS_FILE" - >&2 || true
    echo "use a fresh run directory, or delete this one" >&2
    exit 1
  fi
  echo "resuming run directory: $RUN_DIR"
else
  if [ -n "$(ls -A "$RUN_DIR")" ]; then
    echo "note: adopting $RUN_DIR, which carries no parameter stamp — its" >&2
    echo "      artifacts are taken on faith (only structure is checked)" >&2
  fi
  params_now > "$PARAMS_FILE"
fi

# 1 MB counting payload: byte i = i & 0xFF. Rewritten every run — it is
# deterministic and costs nothing, so a truncated leftover cannot survive.
"$PYTHON" -c "
import sys
from pathlib import Path
Path(sys.argv[1]).write_bytes(bytes(i & 0xFF for i in range(1000000)))
" "$RUN_DIR/payload-counting.bin"

if volume_complete; then
  echo "volume: manifest + $PAGES page(s) verified against sha, skipping generate"
else
  # `generate` refuses to write into an existing directory, so a volume
  # that failed the identity check has to go first — but only a directory
  # that is recognizably a holo volume, never an unexplained one.
  if [ -d "$RUN_DIR/volume" ]; then
    if [ -f "$RUN_DIR/volume/manifest.json" ]; then
      echo "volume: present but not this payload's — regenerating"
      rm -rf "$RUN_DIR/volume"
    else
      echo "refusing: $RUN_DIR/volume exists and is not a holo volume" >&2
      exit 1
    fi
  fi
  ./confetti.py generate \
    "$RUN_DIR/payload-counting.bin" \
    --coding "$CODING" \
    --printer "$PRINTER" \
    --source-fraction "$SOURCE_FRACTION" \
    --out "$RUN_DIR/volume"
fi

# Render, distort and scrap-cut each printed page. Pages are independent
# (per-page seeds, distinct outputs), so this loop parallelizes if the disk
# can take it; it is serial here because each stage is already I/O-bound at
# 4800 dpi.
for page in $(seq 0 $((PAGES - 1))); do
  printf -v P '%03d' "$page"

  if tif_complete "$RUN_DIR/scan-page$P.tif"; then
    echo "page $P: scan present, skipping render + distort"
  else
    rm -f "$RUN_DIR/scan-page$P.tif"

    if tif_complete "$RUN_DIR/print-page$P.tif"; then
      echo "page $P: print raster present, skipping gs"
    else
      gs \
        -dSAFER \
        -dBATCH \
        -dNOPAUSE \
        -dQUIET \
        -sDEVICE=tiff24nc \
        -r600 \
        -g4960x7016 \
        -sOutputFile="$RUN_DIR/print-page$P.tif" \
        "$RUN_DIR/volume/page$P.ps"
    fi

    env PYTHONPATH=src "$PYTHON" -m holo.qualification.color_distort \
      "$RUN_DIR/print-page$P.tif" \
      "$RUN_DIR/scan-page$P.tif" \
      --profile nominal \
      --output-dpi "$SCAN_DPI" \
      --seed "$page"
  fi

  # The platen set is cut in one call and published together, so it is
  # adopted or rebuilt as a SET: scrap_scan refuses if any member exists.
  platens_missing=0
  for platen in $(seq 1 "$PLATENS"); do
    printf -v S '%03d' "$platen"
    if ! tif_complete "$RUN_DIR/scrap-p$page-$S.tif"; then
      platens_missing=$((platens_missing + 1))
    fi
  done
  if [ "$platens_missing" -eq 0 ]; then
    echo "page $P: $PLATENS scrap platen(s) present, skipping cut"
  else
    for platen in $(seq 1 "$PLATENS"); do
      printf -v S '%03d' "$platen"
      if [ -e "$RUN_DIR/scrap-p$page-$S.tif" ]; then
        echo "page $P: re-cutting the platen set, dropping scrap-p$page-$S.tif"
        rm -f "$RUN_DIR/scrap-p$page-$S.tif"
      fi
    done
    env PYTHONPATH=src "$PYTHON" -m holo.qualification.scrap_scan \
      "$RUN_DIR/scan-page$P.tif" \
      "$RUN_DIR/scrap-p$page.tif" \
      --pages "$PLATENS" \
      --scraps "$SCRAPS" \
      --seed $((100 + page))
  fi
done

# --scan/--dpi pair in order, one --dpi per --scan, no exceptions: DPI is
# operator-declared in holo2 and there is no default to fall back on.
SCAN_ARGS=()
for page in $(seq 0 $((PAGES - 1))); do
  for platen in $(seq 1 "$PLATENS"); do
    printf -v S '%03d' "$platen"
    SCAN_ARGS+=(--scan "$RUN_DIR/scrap-p$page-$S.tif" --dpi "$SCAN_DPI")
  done
done

if [ -f "$RUN_DIR/recovered.bin" ]; then
  # holo2 never overwrites a recovered payload (exit 3), and it has nothing
  # left to do here: the object was published, which means VERIFIED.
  echo "recovered payload already present, skipping the receive"
else
  echo "live diagnostics: http://127.0.0.1:$DIAG_PORT/"

  # A RESUME needs no flag: the journal in --state-dir is authoritative and
  # replays what the last run committed, and <state-dir>.prepared hands back
  # the prepared planes it already built.
  ./confetti2.py \
    "${SCAN_ARGS[@]}" \
    --coding "$CODING" \
    --tiles-y "$TILES_Y" \
    --tiles-x "$TILES_X" \
    --pages "$PAGES" \
    --workers "$WORKERS" \
    --diag-port "$DIAG_PORT" \
    --state-dir "$RUN_DIR/receive" \
    --output "$RUN_DIR/recovered.bin"
fi

# Exit 0 from confetti2 already means VERIFIED (the payload envelope's own
# SHA-256 gates publication). This is the independent second opinion.
cmp "$RUN_DIR/payload-counting.bin" "$RUN_DIR/recovered.bin"
echo "verified byte-identical recovery: $RUN_DIR/recovered.bin"
shasum -a 256 "$RUN_DIR/payload-counting.bin" "$RUN_DIR/recovered.bin"
