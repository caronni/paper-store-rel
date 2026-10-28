#!/bin/zsh
# JOB A — real-sheet re-measure on the merged (post-parallelism-cards) tree.
# STRICTLY sequential; one decode at a time; /usr/bin/time -l; ports 8701+.
# FAILURE RULE: a run that is not VERIFIED + BYTE-IDENTICAL stops the chain.
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
SCAN=scratch/in/xerox-canon-c2-bw.tiff
EXP=$D/c2bw-waved.bin

run() {   # name port workers
  local N=$1 P=$2 W=$3
  rm -rf $D/state-$N
  {
    echo "=== START $N (W=$W, port=$P, tree=$TREE) $(date) ==="
    /usr/bin/time -l $PY $D/run_decode_ab.py $TREE $SCAN 4800 $P $N $W $EXP
    echo "EXIT_CODE=$?"
    echo "=== END $N $(date) ==="
  } > $D/$N.log 2>&1
  if ! grep -q "RESULT VERIFIED" $D/$N.log; then
    echo "STOP: $N not VERIFIED" ; return 1
  fi
  if ! grep -q "BYTE-IDENTICAL" $D/$N.log; then
    echo "STOP: $N not BYTE-IDENTICAL" ; return 1
  fi
  echo "OK $N $(grep -o 'wall=[0-9]*s' $D/$N.log)"
  return 0
}

run cards-real-serial 8701 1 || exit 1
run cards-real-w4     8702 4 || exit 1
run cards-real-w8     8703 8 || exit 1
echo "ALL RUNS DONE $(date)"
