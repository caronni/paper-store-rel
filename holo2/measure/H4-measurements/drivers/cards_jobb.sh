#!/bin/zsh
# JOB B — the commit-path profile, gen-clean SERIAL, strictly sequential.
#   1) cProfile run  -> cards-profile.pstats  (ranking; walls DISQUALIFIED)
#   2) counters run  -> cards-commitcost.json (profiler-free cost + merge
#                       value-equality, the numbers the card is priced on)
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
SCAN=$D/e028-genclean-c2-r0700.tiff
EXP=$D/w1a-gc-serial.bin

rm -rf $D/state-cards-profile
{
  echo "=== START cards-profile $(date) ==="
  /usr/bin/time -l $PY $D/run_decode_profile.py $TREE $SCAN 1200 8711 \
      cards-profile $EXP
  echo "EXIT_CODE=$?"
  echo "=== END cards-profile $(date) ==="
} > $D/cards-profile.log 2>&1
echo "profile run done $(date)"

rm -rf $D/state-cards-commitcost
{
  echo "=== START cards-commitcost $(date) ==="
  /usr/bin/time -l $PY $D/run_decode_commitcost.py $TREE $SCAN 1200 8712 \
      cards-commitcost 1 $EXP
  echo "EXIT_CODE=$?"
  echo "=== END cards-commitcost $(date) ==="
} > $D/cards-commitcost.log 2>&1
echo "commitcost run done $(date)"
