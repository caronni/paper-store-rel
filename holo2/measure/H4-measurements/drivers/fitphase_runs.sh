#!/bin/zsh
# _FIT_PHASE BATCHING card. STRICTLY SEQUENTIAL, one process at a time,
# ports 8741+.
#   1) fitphase_bench: decompose (coords / interpolate / reduce) + the
#      whole objective + every captured call + the 4-thread GIL-free f
#   2) gen-clean SERIAL A/B, switch OFF then ON. The OFF run is the
#      CONTROL against the recorded anchor (116 s, VERIFIED, certified
#      1357, commits 1918, fires 2323 — the two-step card's).
#   3) gen-clean W4 A/B, switch OFF then ON. The 54 s W4 anchor predates
#      the two-step card, so the OFF run RE-ANCHORS it before the ON run
#      is read against anything.
# No real-sheet run: the expected win is below the 1.3x rule.
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
GC=$D/e028-genclean-c2-r0700.tiff
GCEXP=$D/w1a-gc-serial.bin

rm -rf $D/state-fitphase-bench
{
  echo "=== START fitphase-bench $(date) ==="
  /usr/bin/time -l $PY $D/fitphase_bench.py $TREE $GC 1200 12 4 3
  echo "EXIT_CODE=$?"
  echo "=== END fitphase-bench $(date) ==="
} > $D/fitphase-bench.log 2>&1
echo "fitphase-bench done $(date)"

for arm in off on; do
  rm -rf $D/state-fp-gc-serial-$arm
  {
    echo "=== START fp-gc-serial-$arm $(date) ==="
    /usr/bin/time -l $PY $D/run_decode_fitphase.py $TREE $GC 1200 8741 \
        fp-gc-serial-$arm 1 $arm $GCEXP
    echo "EXIT_CODE=$?"
    echo "=== END fp-gc-serial-$arm $(date) ==="
  } > $D/fp-gc-serial-$arm.log 2>&1
  echo "fp-gc-serial-$arm done $(date)"
done

for arm in off on; do
  rm -rf $D/state-fp-gc-w4-$arm
  {
    echo "=== START fp-gc-w4-$arm $(date) ==="
    /usr/bin/time -l $PY $D/run_decode_fitphase.py $TREE $GC 1200 8742 \
        fp-gc-w4-$arm 4 $arm $GCEXP
    echo "EXIT_CODE=$?"
    echo "=== END fp-gc-w4-$arm $(date) ==="
  } > $D/fp-gc-w4-$arm.log 2>&1
  echo "fp-gc-w4-$arm done $(date)"
done
echo "ALL RUNS DONE $(date)"
