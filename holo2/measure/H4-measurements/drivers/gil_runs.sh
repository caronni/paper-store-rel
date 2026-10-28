#!/bin/zsh
# STRICTLY sequential GIL-diagnosis runs on the pinned worktree.
# One decode at a time; each wrapped in /usr/bin/time -l.
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
SCAN=$D/e028-genclean-c2-r0700.tiff
EXP=$D/w1a-gc-serial.bin

run() {   # name port workers switch_ms
  local N=$1 P=$2 W=$3 SW=$4
  {
    echo "=== START $N $(date) ==="
    GIL_SWITCH_MS=$SW /usr/bin/time -l $PY $D/run_decode_gil.py \
        $TREE $SCAN 1200 $P $N $W $EXP
    echo "EXIT_CODE=$?"
    echo "=== END $N $(date) ==="
  } > $D/$N.log 2>&1
}

for spec in "$@"; do
  set -A parts ${(s:,:)spec}
  run $parts[1] $parts[2] $parts[3] $parts[4]
done
echo "ALL RUNS DONE $(date)"
