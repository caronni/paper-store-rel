#!/bin/zsh
# One fresh interpreter per (kind, mode, chunk) so ru_maxrss is per-mode.
cd <repo>
D=scratch/rung-ladder-20260930/search/fast
N=${N:-5600}
: > $D/bench_workers.jsonl
uptime > $D/bench_workers.load
run() {  # kind mode chunk
  PYTHONPATH=src:. OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
    env/bin/python $D/bench_workers.py --n $N --chunk $3 --kinds $1 --modes $2 \
    --out /dev/null | grep '^{' >> $D/bench_workers.jsonl
  echo "$1 $2 $3 $(uptime)" >> $D/bench_workers.load
}
for m in proc:14:1 thr:14:1 hyb:7:2; do run batch $m 50; done
for m in proc:14:1 thr:14:1; do run batch $m 16; done
run batch thr:12:1 50
run batch proc:12:1 50
for m in proc:14:1 thr:14:1 hyb:7:2; do run prod $m 50; done
echo DONE >> $D/bench_workers.load
