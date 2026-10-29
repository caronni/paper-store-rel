#!/usr/bin/env bash
# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates the overnight search beside it (gitignored here) with: measure/rung-ladder/search/run_overnight.sh
# The rung-ladder construction search, overnight: ONE command, every stage resumable.
#
#   cd <repo>
#   nohup measure/rung-ladder/search/run_overnight.sh > /dev/null 2>&1 &
#
#   run_overnight.sh            the night (out dirs search/overnight-*; banners -> search/overnight.log)
#   run_overnight.sh --smoke    every stage on tiny grids (out dirs search/smoke-run/*)
#   run_overnight.sh --status   where the run is (banners + the running stage's last progress line)
#
# Stop: kill <pid in search/overnight.pid> (SIGTERM; or Ctrl-C in the foreground): the running stage
# stops cleanly (finished lines are fsync'd), the rest are skipped, the summary is written over what
# exists.  (SIGINT sent with kill to a script started with & from a non-interactive shell is ignored
# by bash -- use SIGTERM.)  Resume: the same command.  A stage that finished (exit 0) leaves a marker and is skipped
# on a rerun; an unfinished stage resumes from its results.jsonl (common.Search skips done lines).
# Exit policy: a stage exiting 3 (finished, some codes hit a worker error; they wrote no line, a
# rerun retries them) is logged and the night CONTINUES without its marker; any other non-zero exit
# (a crash, a refusal, 130 = stopped) ends the pipeline, and the summary is still written.
# Plan and sizing: search/RUN-PLAN.md.
set -u

S="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$S/../../.." && pwd)"
PY="$ROOT/env/bin/python"
export PYTHONPATH="$ROOT/src:$ROOT"
export VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1   # before any pool spawns
WORKERS=${WORKERS:-14}
DECODER=${DECODER:-fast}

MODE=overnight
case "${1:-}" in
  --smoke) MODE=smoke ;;
  --status) MODE=status ;;
  "") ;;
  *) echo "usage: $0 [--smoke|--status]"; exit 2 ;;
esac

if [ "$MODE" = smoke ]; then
  OUT="$S/smoke-run"; LOG="$OUT/overnight.log"
  CONF_ARGS=(--top 1 --top-hard 1 --trials 40)
  A1_ARGS=(--smoke --frozen-rungs off); AF_ARGS=(--smoke --primary off --frozen-rungs on)
  A2_ARGS=(--smoke --secondary --primary off --frozen-rungs off); B1_ARGS=(--smoke); B2_ARGS=(--smoke)
else
  OUT="$S"; LOG="$S/overnight.log"
  # sizing: RUN-PLAN.md (sizing.py over the measured fast-decoder cost per decode)
  CONF_ARGS=(--top 12 --top-hard 3 --trials 5000)
  A1_ARGS=(--overnight --frozen-rungs off --seeds 24 --finalists 24 --n-fine 8)
  AF_ARGS=(--overnight --primary off --frozen-rungs on)
  A2_ARGS=(--overnight --secondary --primary off --frozen-rungs off --seeds 16)
  B1_ARGS=(--overnight --secondary --seeds 12); B2_ARGS=(--overnight)
fi
STATE="$OUT/overnight-state"
mkdir -p "$OUT" "$STATE" "$OUT/logs"

if [ "$MODE" = status ]; then
  [ -f "$LOG" ] || { echo "no run yet ($LOG missing)"; exit 0; }
  grep -E '^\[.*\] (====|DONE|FAIL|STOP|SKIP|WARN)' "$LOG" | tail -20
  cur=$(ls -t "$OUT"/logs/*.log 2>/dev/null | head -1)
  [ -n "$cur" ] && { echo "--- $cur"; grep -E '^\[ *[0-9]+s\]|finished|STOPPED|error' "$cur" | tail -3; }
  exit 0
fi

echo $$ > "$OUT/overnight.pid"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" | tee -a "$LOG" >&2; }

CHILD=""; STOP=0
on_signal() { STOP=1; log "STOP requested (signal): stopping the running stage cleanly"; [ -n "$CHILD" ] && kill -TERM "$CHILD" 2>/dev/null; }
trap on_signal INT TERM

FAILED=""
# run_stage NAME -- command...   (skipped when its marker holds the same command line)
run_stage() {
  local name=$1; shift; shift
  local marker="$STATE/$name.done" cmdline="$*"
  if [ "$STOP" = 1 ] || [ -n "$FAILED" ]; then log "SKIP $name (pipeline stopped)"; return; fi
  if [ -f "$marker" ] && [ "$(cat "$marker")" = "$cmdline" ]; then log "SKIP $name (done earlier; marker $marker)"; return; fi
  log "==== STAGE $name START: $cmdline"
  local t0=$SECONDS
  "$@" >> "$OUT/logs/$name.log" 2>&1 &
  CHILD=$!
  wait "$CHILD"; local rc=$?
  while kill -0 "$CHILD" 2>/dev/null; do wait "$CHILD"; rc=$?; done   # wait returns early on a trapped signal
  CHILD=""
  local el=$(( SECONDS - t0 ))
  local tail3; tail3=$(grep -E 'finished|STOPPED|wall|errors|summary|FAIL|Traceback|Error' "$OUT/logs/$name.log" | tail -3 | tr '\n' ' ')
  if [ $rc -eq 0 ]; then
    echo "$cmdline" > "$marker"; log "DONE $name in $((el/60)) min: $tail3"
  elif [ $rc -eq 3 ]; then
    log "WARN $name finished WITH WORKER ERRORS in $((el/60)) min (no marker; a rerun retries the failed codes): $tail3"
  elif [ $rc -eq 130 ] || [ "$STOP" = 1 ]; then
    STOP=1; log "STOP $name stopped after $((el/60)) min (rc $rc); rerun the same command to resume"
  else
    FAILED=$name; log "FAIL $name rc=$rc after $((el/60)) min: $tail3 (see $OUT/logs/$name.log)"
  fi
}

log "==== run_overnight.sh $MODE: pid $$, workers $WORKERS, decoder $DECODER, out $OUT"

# 0. preflight: the fast decoder's twin tests (skipped when done on this numpy build)
NP=$("$PY" -c 'import numpy; print(numpy.__version__)')
run_stage preflight-np$NP -- bash -c "'$PY' '$S/fast/test_fastdecode.py' && '$PY' '$S/fast/test_tasks_fast.py' && '$PY' '$S/fast/test_variants_fast.py'"

# 1. Tier A, primary rungs k=1664, 1280 (the bulk of the budget)
run_stage A-primary -- "$PY" "$S/recipe_search.py" "${A1_ARGS[@]}" --out "$OUT/overnight-A" \
  --workers "$WORKERS" --decoder "$DECODER"
# 2. Tier A, the frozen production rungs as full rows (k=2240..3520, frozen codes as named baselines)
run_stage A-frozen -- "$PY" "$S/recipe_search.py" "${AF_ARGS[@]}" --out "$OUT/overnight-AF" \
  --workers "$WORKERS" --decoder "$DECODER"
# 3. Tier A, secondary rungs k=1600, 1216 (same dir as primary, primary NOT re-staged: B2 copies its plain rows from it)
run_stage A-secondary -- "$PY" "$S/recipe_search.py" "${A2_ARGS[@]}" --out "$OUT/overnight-A" \
  --workers "$WORKERS" --decoder "$DECODER"
# 4. Tier B1, DE-designed profiles (all four search k)
run_stage B1 -- "$PY" "$S/de_profile.py" "${B1_ARGS[@]}" --out "$OUT/overnight-B1" \
  --workers "$WORKERS" --decoder "$DECODER"
# 5. Tier B2, ARA / IRAA variants over Tier A's configs (plain rows copied from overnight-A)
run_stage B2 -- "$PY" "$S/variants_search.py" "${B2_ARGS[@]}" --copy-from "$OUT/overnight-A" --out "$OUT/overnight-B2" \
  --workers "$WORKERS" --decoder "$DECODER"
# 6. confirmation of the cross-tier finalists at FRESH trials (t >= 20000, never used for selection)
run_stage confirm -- "$PY" "$S/confirm.py" --runs "$OUT/overnight-A" "$OUT/overnight-AF" "$OUT/overnight-B1" "$OUT/overnight-B2" \
  --out "$OUT/overnight-CONF" "${CONF_ARGS[@]}" --workers "$WORKERS" --decoder "$DECODER"

# 7. the ONE combined table, always (also after a stop or a failure: over what exists)
log "==== STAGE summarize (always)"
if "$PY" "$S/summarize_all.py" --runs "$OUT/overnight-A" "$OUT/overnight-AF" "$OUT/overnight-B1" "$OUT/overnight-B2" \
     --conf "$OUT/overnight-CONF" --out "$OUT/overnight-ALL" >> "$OUT/logs/summarize.log" 2>&1; then
  log "DONE summarize -> $OUT/overnight-ALL/TABLES-search.md"
else
  log "FAIL summarize (see $OUT/logs/summarize.log)"
fi
if [ -n "$FAILED" ]; then log "==== END: FAILED at $FAILED"; exit 1; fi
if [ "$STOP" = 1 ]; then log "==== END: STOPPED (rerun the same command to resume)"; exit 130; fi
log "==== END: all stages done"
exit 0
