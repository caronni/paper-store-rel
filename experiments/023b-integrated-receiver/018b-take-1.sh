#!/usr/bin/env bash
#
# Native-footing E018b take 1: run E023b context+PAVA, final adaptive BP,
# and manifest-driven fountain scoring for both profiles on both scanners.
#
# This script intentionally DOES NOT decimate:
#   HP    inputs are processed at their native 1200 dpi.
#   Canon inputs are processed at their native 4800 dpi.
#
# The four cases use separate states so HP/Canon recovery remains directly
# comparable at their practical native footings. Because HP=1200 and
# Canon=4800, this is not a controlled scanner-only variable. Open
# http://localhost:${DIAG_PORT:-8023}/ while the script is running. The same
# port is reused sequentially; frames persist per case.
#
# Required environment:
#   SCAN_ROOT=<evidence>/e018b      the four take-1 scans (evidence archive)
#   E018B_BUILD=<gen_e018b.py's build dir, holding the two manifests>
#
# Optional environment:
#   DIAG_PORT=8023
#   PANEL_WIDTH=600
#   OUTPUT_ROOT=experiments/023b-integrated-receiver/build/take-1
#   PYTHON=env/bin/python
#   DRY_RUN=1                 print commands without running the receiver

set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-env/bin/python}"
DIAG_PORT="${DIAG_PORT:-8023}"
PANEL_WIDTH="${PANEL_WIDTH:-600}"
OUTPUT_ROOT="${OUTPUT_ROOT:-experiments/023b-integrated-receiver/build/take-1}"
SCAN_ROOT="${SCAN_ROOT:?set SCAN_ROOT to the evidence dir holding the e018b take-1 scans}"
E018B_BUILD="${E018B_BUILD:?set E018B_BUILD to the build dir of gen_e018b.py}"
DRY_RUN="${DRY_RUN:-0}"

RUNNER="experiments/023b-integrated-receiver/run_e023b.py"
SCORER="experiments/023b-integrated-receiver/score_e023b.py"
MANIFEST_C3="$E018B_BUILD/e018b-c3-012d9e3ae693_manifest.json"
MANIFEST_C2="$E018B_BUILD/e018b-c2-424e41a28257_manifest.json"

run_cmd() {
    printf '+'
    printf ' %q' "$@"
    printf '\n'
    if [[ "$DRY_RUN" != "1" ]]; then
        "$@"
    fi
}

require_file() {
    if [[ ! -f "$1" ]]; then
        printf 'missing required file: %s\n' "$1" >&2
        exit 2
    fi
}

require_executable() {
    if [[ "$1" == */* ]]; then
        if [[ ! -x "$1" ]]; then
            printf 'missing executable: %s\n' "$1" >&2
            exit 2
        fi
    elif ! command -v "$1" >/dev/null 2>&1; then
        printf 'missing command: %s\n' "$1" >&2
        exit 2
    fi
}

run_case() {
    local label="$1"
    local image="$2"
    local dpi="$3"
    local format_id="$4"
    local manifest="$5"
    local case_dir="$OUTPUT_ROOT/$label"
    local state="$case_dir/session.pkl"
    local diag="$case_dir/diag"

    require_file "$image"
    require_file "$manifest"
    mkdir -p "$case_dir"

    printf '\n=== %s: native %s dpi, %s ===\n' \
        "$label" "$dpi" "$format_id"
    printf 'Live diagnostics: http://localhost:%s/\n' "$DIAG_PORT"

    run_cmd "$PYTHON" "$RUNNER" \
        "$image" \
        --dpi "$dpi" \
        --format "$format_id" \
        --pages 0 \
        --capture-groups "e018b-take1-$label" \
        --state "$state" \
        --out "$case_dir/context.png" \
        --report "$case_dir/context.json" \
        --detector-profile ctx-pava-v1 \
        --fresh \
        --diag "$diag" \
        --diag-port "$DIAG_PORT" \
        --panel-width "$PANEL_WIDTH"

    run_cmd "$PYTHON" "$RUNNER" \
        --dpi "$dpi" \
        --format "$format_id" \
        --pages 0 \
        --state "$state" \
        --out "$case_dir/combined.png" \
        --report "$case_dir/combined.json" \
        --detector-profile ctx-pava-v1 \
        --bp-retry \
        --diag "$diag" \
        --diag-port "$DIAG_PORT" \
        --panel-width "$PANEL_WIDTH"

    run_cmd "$PYTHON" "$SCORER" \
        "$state" "$manifest" \
        --label "$label" \
        --out "$case_dir/score.json"
}

require_executable "$PYTHON"
require_file "$RUNNER"
require_file "$SCORER"
mkdir -p "$OUTPUT_ROOT"

printf 'E018b take 1 uses native scanner rasters only; no decimation step.\n'
printf 'Keep http://localhost:%s/ open to follow each sequential case.\n' \
    "$DIAG_PORT"

run_case \
    c3-hp-1200 \
    "$SCAN_ROOT/hp-e018b-c3-hp-1200-page.tiff.png" \
    1200 e018b-v3-c3 "$MANIFEST_C3"

run_case \
    c3-canon-4800 \
    "$SCAN_ROOT/hp-e018b-c3-canon-4800-page.tiff" \
    4800 e018b-v3-c3 "$MANIFEST_C3"

run_case \
    c2-hp-1200 \
    "$SCAN_ROOT/hp-e018b-c2-hp-1200-page.tiff.png" \
    1200 e018b-v3-c2 "$MANIFEST_C2"

run_case \
    c2-canon-4800 \
    "$SCAN_ROOT/hp-e018b-c2-canon-4800-page.tiff" \
    4800 e018b-v3-c2 "$MANIFEST_C2"

printf '\nTake 1 complete. Per-case reports are under %s/*/score.json\n' \
    "$OUTPUT_ROOT"
