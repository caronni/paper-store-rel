#!/bin/zsh
# F-17 pass 2 (the sweep's two work-key partitions added). STRICTLY
# SEQUENTIAL, one decode at a time, ports 8721+.
#   1) gen-clean serial      vs the post-cards anchor 209.7 s
#   2) gen-clean W4          vs the post-cards anchor 145.26 s
#   3) REAL SHEET serial     vs the post-cards anchor 258 s
#   4) cProfile serial       -> h4card-profile.pstats (ranking only)
#   5) cProfile on MAIN @8f15e82 -> restores cards-profile.pstats, which
#      run_decode_profile.py's hardcoded output path had overwritten in
#      pass 1 (the artifact the post-merge REPORT cites).
set -u
PY=env/bin/python
D=scratch/holo2-demo
TREE=<checkout>
MAIN=<repo>
GC=$D/e028-genclean-c2-r0700.tiff
GCEXP=$D/w1a-gc-serial.bin
REAL=scratch/in/xerox-canon-c2-bw.tiff
REALEXP=$D/c2bw-waved.bin

run_ab () {   # name port workers scan dpi expected
  rm -rf $D/state-$1
  {
    echo "=== START $1 $(date) ==="
    /usr/bin/time -l $PY $D/run_decode_ab.py $TREE $4 $5 $2 $1 $3 $6
    echo "EXIT_CODE=$?"
    echo "=== END $1 $(date) ==="
  } > $D/$1.log 2>&1
  echo "$1 done $(date)"
}

run_ab h4b-gc-serial   8721 1 $GC   1200 $GCEXP
run_ab h4b-gc-w4       8722 4 $GC   1200 $GCEXP
run_ab h4b-real-serial 8723 1 $REAL 4800 $REALEXP

rm -rf $D/state-h4b-profile
{
  echo "=== START h4b-profile $(date) ==="
  /usr/bin/time -l $PY $D/run_decode_profile.py $TREE $GC 1200 8724 \
      h4b-profile $GCEXP
  echo "EXIT_CODE=$?"
  echo "=== END h4b-profile $(date) ==="
} > $D/h4b-profile.log 2>&1
mv $D/cards-profile.pstats $D/h4b-profile.pstats
echo "h4b-profile done $(date)"

rm -rf $D/state-precard-profile
{
  echo "=== START precard-profile (MAIN @8f15e82) $(date) ==="
  /usr/bin/time -l $PY $D/run_decode_profile.py $MAIN $GC 1200 8725 \
      precard-profile $GCEXP
  echo "EXIT_CODE=$?"
  echo "=== END precard-profile $(date) ==="
} > $D/precard-profile.log 2>&1
echo "precard-profile done (cards-profile.pstats restored) $(date)"
