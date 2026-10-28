#!/bin/zsh
# F-17 (incremental derived views) — gen-clean A/B + commit-path re-profile.
# STRICTLY SEQUENTIAL: one decode at a time, ports 8711+.
#   1) serial (W1)  vs the recorded post-cards anchor 209.7 s
#   2) W4           vs the recorded post-cards anchor 145.26 s
#   3) cProfile serial -> h4card-profile.pstats (ranking only; wall DISQUALIFIED)
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
SCAN=$D/e028-genclean-c2-r0700.tiff
EXP=$D/w1a-gc-serial.bin

for run in "h4card-gc-serial 8711 1" "h4card-gc-w4 8712 4"; do
  set -- ${=run}
  name=$1; port=$2; workers=$3
  rm -rf $D/state-$name
  {
    echo "=== START $name $(date) ==="
    /usr/bin/time -l $PY $D/run_decode_ab.py $TREE $SCAN 1200 $port \
        $name $workers $EXP
    echo "EXIT_CODE=$?"
    echo "=== END $name $(date) ==="
  } > $D/$name.log 2>&1
  echo "$name done $(date)"
done

rm -rf $D/state-h4card-profile
{
  echo "=== START h4card-profile $(date) ==="
  /usr/bin/time -l $PY $D/run_decode_profile.py $TREE $SCAN 1200 8713 \
      h4card-profile $EXP
  echo "EXIT_CODE=$?"
  echo "=== END h4card-profile $(date) ==="
} > $D/h4card-profile.log 2>&1
mv $D/cards-profile.pstats $D/h4card-profile.pstats 2>/dev/null
echo "h4card-profile done $(date)"
