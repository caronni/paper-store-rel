#!/bin/bash
# Historical template of the 018.10 replay (2026-07-12).
# Inputs (the decimated-*_1600.tiff captures) are in the evidence archive;
# not runnable from the repo alone.

E018="${1:?evidence dir holding decimated-*_1600.tiff}"
OUT="${2:-experiments/018-confetti-c3-play/build/try_3}"

# Historical template for the successful try_3 recovery session.  The commands
# below built the first four-scan state from confetti batches 1 and 2.  The user
# then ingested decimated-3_1600.tiff and decimated-3-2nd_1600.tiff with the
# same session_decode.py invocation and ran another repass.  The resulting
# state contains all six basenames, 532 certified tiles, and emitted the
# byte-exact 103,195-byte payload (sha256 4c75fe59241499a8...).
#
# Therefore this file is a reusable driver/template, not a complete literal
# transcript of the commands that closed the volume.

# scanimage -d pixma:04A91912_<SERIAL> --resolution 4800 --mode gray --format=tiff -o hp-e018-canon-4800-confetti-3.tiff -v
# scanimage -d pixma:04A91912_<SERIAL> --resolution 4800 --mode gray --format=tiff -o hp-e018-canon-4800-confetti-3-2ndtake.tiff -v
# env/bin/python experiments/018-confetti-c3-play/decimate_scan.py "$E018"/hp-e018-canon-4800-confetti-3.tiff "$E018"/decimated-3_1600.tiff --factor 3
# env/bin/python experiments/018-confetti-c3-play/decimate_scan.py "$E018"/hp-e018-canon-4800-confetti-3-2ndtake.tiff "$E018"/decimated-3-2nd_1600.tiff --factor 3

env/bin/python experiments/018-confetti-c3-play/session_decode.py --fresh --piece-chain anchor --dpi 1600 --state "$OUT"/e018-session_state.pkl --diag "$OUT"/diag1 "$E018"/decimated-1_1600.tiff

env/bin/python experiments/018-confetti-c3-play/session_decode.py --piece-chain anchor --dpi 1600 --state "$OUT"/e018-session_state.pkl --diag "$OUT"/diag2 "$E018"/decimated-1-2nd_1600.tiff

env/bin/python experiments/018-confetti-c3-play/session_decode.py --piece-chain anchor --dpi 1600 --state "$OUT"/e018-session_state.pkl --diag "$OUT"/diag3 "$E018"/decimated-2_1600.tiff

env/bin/python experiments/018-confetti-c3-play/session_decode.py --piece-chain anchor --dpi 1600 --state "$OUT"/e018-session_state.pkl --diag "$OUT"/diag4 "$E018"/decimated-2-2nd_1600.tiff

env/bin/python experiments/018-confetti-c3-play/repass.py \
    "$E018"/decimated-1_1600.tiff \
    "$E018"/decimated-1-2nd_1600.tiff \
    "$E018"/decimated-2_1600.tiff \
    "$E018"/decimated-2-2nd_1600.tiff \
    --dpi 1600 \
    --state "$OUT"/e018-session_state.pkl

env/bin/python experiments/018-confetti-c3-play/draw_decode_map.py \
    --state "$OUT"/e018-session_state.pkl \
    --dpi 1600 --out "$OUT"/repass-map.png
