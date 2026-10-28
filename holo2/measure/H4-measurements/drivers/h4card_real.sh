#!/bin/zsh
# F-17 — the ONE real-sheet serial run (gen-clean win 1.65x >= 1.3x gate).
# Waits for the gen-clean batch to finish first: strictly sequential.
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
SCAN=scratch/in/xerox-canon-c2-bw.tiff
EXP=$D/c2bw-waved.bin

until grep -q "h4card-profile done" $D/h4card_runs.out; do sleep 10; done

rm -rf $D/state-h4card-real-serial
{
  echo "=== START h4card-real-serial $(date) ==="
  /usr/bin/time -l $PY $D/run_decode_ab.py $TREE $SCAN 4800 8714 \
      h4card-real-serial 1 $EXP
  echo "EXIT_CODE=$?"
  echo "=== END h4card-real-serial $(date) ==="
} > $D/h4card-real-serial.log 2>&1
echo "h4card-real-serial done $(date)"
