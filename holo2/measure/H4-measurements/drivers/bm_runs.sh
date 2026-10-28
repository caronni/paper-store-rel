#!/bin/zsh
# STRICTLY sequential lockstep-BM A/B on the h4 worktree.
# One decode at a time; each wrapped in /usr/bin/time -l. Ports 8691+.
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
SCAN=$D/e028-genclean-c2-r0700.tiff
EXP=$D/w1a-gc-serial.bin

run() {   # name port workers driver arm
  local N=$1 P=$2 W=$3 DRV=$4 ARM=$5
  rm -rf $D/state-$N
  {
    echo "=== START $N ($DRV, arm=$ARM, W=$W) $(date) ==="
    BM_ARM=$ARM /usr/bin/time -l $PY $D/run_decode_bm.py \
        $DRV $TREE $SCAN 1200 $P $N $W $EXP
    echo "EXIT_CODE=$?"
    echo "=== END $N $(date) ==="
  } > $D/$N.log 2>&1
}

for spec in "$@"; do
  set -A parts ${(s:,:)spec}
  run $parts[1] $parts[2] $parts[3] $parts[4] $parts[5]
done
echo "ALL RUNS DONE $(date)"
