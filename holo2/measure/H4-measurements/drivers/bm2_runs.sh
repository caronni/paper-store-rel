#!/bin/zsh
# BINARY TWO-STEP BM card. STRICTLY SEQUENTIAL, one process at a time,
# ports 8731+.
#   1) bm2_bench: decompose (scalar / 26-step / 13-step) + whole
#      decode_many + the 4-thread GIL-free f, one capture for all three
#   2) gen-clean SERIAL A/B vs the recorded anchor:
#      123 s, VERIFIED, certified 1357, commits 1918, fires 2323
# No real-sheet run: the expected win is below the 1.3x rule.
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
GC=$D/e028-genclean-c2-r0700.tiff
GCEXP=$D/w1a-gc-serial.bin

rm -rf $D/state-bm2-bench
{
  echo "=== START bm2-bench $(date) ==="
  /usr/bin/time -l $PY $D/bm2_bench.py $TREE $GC 1200 10 4 3
  echo "EXIT_CODE=$?"
  echo "=== END bm2-bench $(date) ==="
} > $D/bm2-bench.log 2>&1
echo "bm2-bench done $(date)"

rm -rf $D/state-bm2-gc-serial
{
  echo "=== START bm2-gc-serial $(date) ==="
  /usr/bin/time -l $PY $D/run_decode_ab.py $TREE $GC 1200 8731 \
      bm2-gc-serial 1 $GCEXP
  echo "EXIT_CODE=$?"
  echo "=== END bm2-gc-serial $(date) ==="
} > $D/bm2-gc-serial.log 2>&1
echo "bm2-gc-serial done $(date)"
echo "ALL RUNS DONE $(date)"
