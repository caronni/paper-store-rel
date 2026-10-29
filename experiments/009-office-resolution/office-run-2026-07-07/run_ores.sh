#!/usr/bin/env bash
# run_ores.sh — ORES-1: tickle 1200+ resolution out of the office Xerox
# AltaLink C8245 via PJL / PCL over the raw JetDirect socket (port 9100).
#
# WHAT THIS DOES, plainly:
#   - sends a handful of prepared print jobs to a printer over TCP 9100;
#   - one job (J0) is read-only and prints NOTHING (a PJL capability query) —
#     its reply is captured to a text file;
#   - the rest print ONE sheet each (K-only line/dot patterns, no color);
#   - it never deletes, configures persistently, or changes device state
#     beyond the per-job PJL settings inside each file (which do not persist).
#   Every step asks before sending. Nothing runs without you typing "yes".
#
# It does NOT scan. After printing, scan the sheets on a KNOWN scanner (home
# flatbed 1200 dpi, or the Canon 4800 once it lands) — see SCAN PROTOCOL below.
#
# Review before running:  less run_ores.sh
# Run:                     ./run_ores.sh            (uses <ip>)
#          or:             ./run_ores.sh <host>     (override address)
set -euo pipefail

HOST="${1:-${PAPERHOLO_XEROX_HOST:-<ip>}}"
PORT=9100
HERE="$(cd "$(dirname "$0")" && pwd)"
JOBS="$HERE/jobs"
OUT="$HERE/responses"
mkdir -p "$OUT"

echo "=================================================================="
echo " ORES-1  ->  Xerox AltaLink C8245 at ${HOST}:${PORT}"
echo " jobs dir : $JOBS"
echo " captures : $OUT"
echo "=================================================================="
echo
echo "Requires 'nc' (netcat) and TCP reachability to ${HOST}:${PORT}."
command -v nc >/dev/null || { echo "ERROR: nc not found on PATH"; exit 1; }
echo

confirm() {  # confirm "<prompt>"  -> returns 0 on yes, 1 otherwise
  local ans
  read -r -p "$1 [yes/skip] " ans
  [ "$ans" = "yes" ]
}

send_print() {  # send_print <file> <sheet-label> <what-it-tests>
  local f="$JOBS/$1" label="$2" note="$3"
  [ -f "$f" ] || { echo "  MISSING: $f (skipping)"; return 0; }
  echo "------------------------------------------------------------------"
  echo " PRINT  $1"
  echo "   tests : $note"
  echo "   sha   : $(shasum -a 256 "$f" | cut -d' ' -f1)"
  echo "   bytes : $(wc -c < "$f" | tr -d ' ')"
  if confirm "   send this print job to ${HOST}:${PORT}?"; then
    nc -w 20 "$HOST" "$PORT" < "$f"
    echo "   sent. >>> PEN-ANNOTATE the ejected sheet: \"${label}\" + today's date."
    echo "   >>> keep the sheet; do not reprint."
  else
    echo "   skipped."
  fi
  echo
}

query_readback() {  # query_readback <file> <outfile>
  local f="$JOBS/$1" o="$OUT/$2"
  [ -f "$f" ] || { echo "  MISSING: $f (skipping)"; return 0; }
  echo "------------------------------------------------------------------"
  echo " QUERY  $1   (READ-ONLY — prints nothing; captures the reply)"
  echo "   sha   : $(shasum -a 256 "$f" | cut -d' ' -f1)"
  if confirm "   send this query and capture the reply to responses/$2?"; then
    # -w read-timeout lets the socket close after the printer stops talking.
    nc -w 8 "$HOST" "$PORT" < "$f" | tee "$o" || true
    echo "   captured -> $o"
  else
    echo "   skipped."
  fi
  echo
}

echo ">> Step 1: capability query (no paper). Its reply tells us which"
echo ">> RESOLUTION values and languages the RIP admits."
query_readback "ores_query.pjl" "ores_query_response.txt"

echo ">> Step 2: the resolution-unlock prints. One sheet each; the sheet's"
echo ">> own 600-grid control fields always survive — the >600-grid fields"
echo ">> survive only if that command path unlocked the finer grid."
send_print "ores_pspjl1200.job"       "J1 PS+PJL 1200"        "does PJL SET RESOLUTION=1200 override what PostScript refused?"
send_print "ores_pcl1200.pcl"         "J2 PCL 1200"           "native PCL raster at 1200 dpi"
send_print "ores_pcl1200_pjlres.pcl"  "J3 PCL 1200 +PJLres"   "PCL raster 1200 with the PJL resolution hint too"
send_print "ores_pcl2400.pcl"         "J4 PCL 2400"           "push to 2400 if 1200 worked"

echo ">> Step 3: the different-day characterization batch (007.9) — verbatim"
echo ">> reprints on the AltaLink to bound engine-2 day/consumable variance."
send_print "e004.ps"    "BATCH e004 finalists"  "A3/A4/B1/B2 day-2 sample"
send_print "e006c.ps"   "BATCH e006 LOOP-C"     "healthy LOOP-C, second day"
send_print "e006bw.ps"  "BATCH e006 LOOP-BW"    "B1/RLL, second day"

cat <<'EOF'
==================================================================
 DONE sending. SCAN PROTOCOL (enhancements OFF, scan UPRIGHT):
   - ORES sheets J1-J4 : SCAN ON THE CANON 4800 (grey). The whole point
     is to detect a >600-dpi grid, and a >600 print scanned at 1200 is
     undersampled -- the fine-grid fields alias no matter what the
     printer did. The home 1200 flatbed is a ROUGH SCREEN only (trust
     just the 600-control fields there). J4 @2400 REQUIRES the Canon.
   - BATCH sheets        : home flatbed, per their experiments
     (e006c/e004 COLOR 1200 dpi; e006bw GREY 1200 dpi).
   - All 4 corner marks in frame, scan UPRIGHT (the analyzer does not
     read the chiral marks -- a rotated/flipped scan misreads).
   - Also grab the captured responses/ores_query_response.txt — it
     records what the RIP said it supports.
 Then hand the scans + the response file back for analysis
 (analyze_ores.py declares each field UNLOCKED / COLLAPSED / MARGINAL).
==================================================================
EOF
