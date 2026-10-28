# verify_diag.py — P9 build-time verification (throwaway; comments allowed
# here). No oracle exists for holo3/diag (event-consumer, holo3-native): a
# synthetic event stream covering all 10 event types across 2 pages drives
# model.fold, panes.render_frame and server.serve, and every check is a
# structural/synthetic-fixture assertion per the W2 addendum's verify duty.
#
# Run:
#   cd <checkout> && \
#   PYTHONPATH=.:src:holo2/src env314t/bin/python \
#     _distill/verify/verify_diag.py

from __future__ import annotations

import io
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

import holo3.data as data
from holo3.diag import model as dm
from holo3.diag import panes
from holo3.diag import server

CHECKS: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    CHECKS.append((name, ok))
    print(("PASS" if ok else "FAIL"), name)


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

CAP_A = "a1b2c3d4e5f6"
CAP_B = "112233445566"

run_open = data.RunOpen(
    format_id="holo3/v2/c2-cmy8-r0700@2x2", pages=2, tiles_yx=(2, 2),
    stream_ids=("K",), n_captures=2, workers=4)

capture_a = data.CaptureOpen(capture=CAP_A, dpi=2400.0, shape_yx=(4800, 3600),
                             channels=1, duplicate=False)
capture_b = data.CaptureOpen(capture=CAP_B, dpi=2400.0, shape_yx=(4800, 3600),
                             channels=1, duplicate=False)
capture_dup = data.CaptureOpen(capture=CAP_B, dpi=2400.0,
                               shape_yx=(4800, 3600), channels=1,
                               duplicate=True)

region0 = data.RegionMark(region_index=0, origin_yx=(100, 100),
                          shape_cells=(30, 30), pitch_px=8.0,
                          support_cells=850)
region1 = data.RegionMark(region_index=1, origin_yx=(400, 400),
                          shape_cells=(30, 30), pitch_px=8.0,
                          support_cells=700)
_preview = (np.random.default_rng(0).uniform(40, 220, (64, 64))
           .astype(np.float32))

survey_a = data.SurveyDone(capture=CAP_A, n_regions=2,
                           regions=(region0, region1), pitch_class="c2",
                           preview=_preview, preview_decim=4)
survey_b = data.SurveyDone(capture=CAP_B, n_regions=1, regions=(region1,),
                           pitch_class="c2", preview=None, preview_decim=1)

pose_ok = data.PoseCommitted(capture=CAP_A, level_index=0, region_index=0,
                             extent_cells=(0, 0, 128, 128), page=0,
                             route="word", mismatch=0.2, accepted=True)
pose_declined = data.PoseCommitted(capture=CAP_A, level_index=0,
                                   region_index=0, extent_cells=(0, 0, 64, 64),
                                   page=0, route="cold", mismatch=1.9,
                                   accepted=False)

window_posed = data.WindowSettled(capture=CAP_A, level_index=0,
                                  region_index=0,
                                  extent_cells=(0, 0, 30, 30), state="posed")
window_retired = data.WindowSettled(capture=CAP_A, level_index=0,
                                    region_index=1,
                                    extent_cells=(0, 0, 30, 30),
                                    state="retired")
window_parked = data.WindowSettled(capture=CAP_B, level_index=0,
                                   region_index=1,
                                   extent_cells=(0, 0, 30, 30),
                                   state="parked")
window_done = data.WindowSettled(capture=CAP_A, level_index=1,
                                 region_index=0, extent_cells=(0, 0, 30, 30),
                                 state="done")

calibrate_ok = data.CalibrateAdopted(capture=CAP_A, pool_id="pool-0",
                                     adopted=True, reason="floors met")
calibrate_no = data.CalibrateAdopted(capture=CAP_B, pool_id="pool-1",
                                     adopted=False, reason="thin support")

tile_events = (
    data.TileOutcome(page=0, ty=0, tx=0, stream_id="K", source="tiles/scan",
                     result="certified", bp_iters=12),
    data.TileOutcome(page=0, ty=0, tx=1, stream_id="K", source="tiles/scan",
                     result="failed", bp_iters=60),
    data.TileOutcome(page=0, ty=1, tx=0, stream_id="K", source="tiles/union",
                     result="floor", bp_iters=150),
    data.TileOutcome(page=1, ty=0, tx=0, stream_id="K", source="refine/rf1",
                     result="certified", bp_iters=200),
)

job_events = (
    data.JobDone(plugin="survey", subject="cap:a1b2c3d4e5f6", cost=10,
                cpu_s=0.02, n_certificates=0, n_poses=0, n_words=0),
    data.JobDone(plugin="place", subject="win:0", cost=60, cpu_s=0.6,
                n_certificates=0, n_poses=1, n_words=3),
    data.JobDone(plugin="tiles", subject="tile:0:0:0", cost=20, cpu_s=0.1,
                n_certificates=1, n_poses=0, n_words=0),
    data.JobDone(plugin="refine", subject="tile:1:0:0", cost=200, cpu_s=1.4,
                n_certificates=1, n_poses=0, n_words=0),
)

blocks = (
    data.CloseBlockRow(stream_id=None, block=0, have=180, needed=200,
                       rank=24, solved=False, short=176, groups_open=1,
                       n_groups=1),
    data.CloseBlockRow(stream_id=None, block=1, have=200, needed=200,
                       rank=24, solved=True, short=0, groups_open=0,
                       n_groups=1),
)
close_check = data.CloseCheck(certified=2, symbols_used=380, k_total=400,
                              metadata_rank=24, metadata_n_unique=61,
                              blocks=blocks, status="open")

run_done = data.RunDone(status="verified", payload_sha256="deadbeef" * 8,
                        n_bytes=465580, certified=2)

EVENTS_PRE_SURVEY = [run_open, capture_a, capture_b, capture_dup]
EVENTS_POST_SURVEY = [
    survey_a, survey_b, pose_ok, pose_declined,
    window_posed, window_retired, window_parked, window_done,
    calibrate_ok, calibrate_no,
    *tile_events, *job_events, close_check, run_done,
]
ALL_EVENTS = EVENTS_PRE_SURVEY + EVENTS_POST_SURVEY

EVENT_TYPES_SEEN = {type(event).__name__ for event in ALL_EVENTS}
check("synthetic stream covers all 10 event types",
     EVENT_TYPES_SEEN == {
         "RunOpen", "CaptureOpen", "SurveyDone", "PoseCommitted",
         "WindowSettled", "CalibrateAdopted", "TileOutcome", "JobDone",
         "CloseCheck", "RunDone"})

# -- fold: pre-survey state, then the full stream --------------------------

model_pre = dm.fold(dm.empty(), EVENTS_PRE_SURVEY)
check("cursor after pre-survey fold", model_pre.cursor == len(
    EVENTS_PRE_SURVEY))
rows_pre = dm.six_row_status(model_pre)
check("row2 says unavailable before survey",
     "unavailable before survey" in rows_pre[1])
check("row5 tiles unavailable before run-open would be wrong here"
     " (run IS open)", "UNKNOWN" in rows_pre[4])

model_full = dm.fold(model_pre, ALL_EVENTS)
check("cursor after full fold", model_full.cursor == len(ALL_EVENTS))
check("no fold errors on clean events", model_full.fold_errors == 0)
rows_full = dm.six_row_status(model_full)
check("six rows always exactly six", len(rows_full) == 6)
check("row1 carries the format id", run_open.format_id in rows_full[0])
check("row1 tags PROVISIONAL", rows_full[0].endswith("PROVISIONAL"))
check("row2 no longer unavailable", "unavailable before survey" not in
     rows_full[1])
check("row2 ingested count excludes the duplicate", "2 ingested" in
     rows_full[1])
n_regions_expected = survey_a.n_regions + survey_b.n_regions
support_expected = (region0.support_cells + region1.support_cells
                    + region1.support_cells)
check("row2 region count sums both surveys",
     f"regions {n_regions_expected}" in rows_full[1])
check("row2 support cells sums both surveys",
     f"support {support_expected} cells" in rows_full[1])
check("row3 carries workers", f"workers {run_open.workers}" in rows_full[2])
check("row4 jobs total", "jobs 4" in rows_full[3])
check("row4 cpu total", "cpu 2.1" in rows_full[3])
check("row5 unknown/addressed/attempted/certified tally",
     "UNKNOWN 3 · ADDRESSED 1 · ATTEMPTED 2 · CERTIFIED 2" in rows_full[4])
check("row6 reads VERIFIED", "VERIFIED" in rows_full[5])
check("row6 carries the metadata rank", "metadata rank 24/24" in rows_full[5])

status_full = dm.status(model_full)
check("status revision equals event count",
     status_full["revision"] == len(ALL_EVENTS))
check("status carries plugin rows", len(status_full["plugin_rows"]) == 4)

# -- revision moves only with events ----------------------------------------

model_repeat = dm.fold(model_full, ALL_EVENTS)
check("re-folding the same events is a no-op object",
     model_repeat is model_full)
extended = ALL_EVENTS + [data.JobDone(
    plugin="close", subject="close", cost=15, cpu_s=0.05,
    n_certificates=0, n_poses=0, n_words=0)]
model_more = dm.fold(model_full, extended)
check("revision advances only when events grow",
     model_more.cursor == len(extended) > model_full.cursor)

# -- a poisoned event must not raise out of the fold ------------------------

bad_pose = data.PoseCommitted(capture=CAP_A, level_index=0, region_index=0,
                              extent_cells=(0, 0), page=0, route="word",
                              mismatch=0.1, accepted=True)
bad_tile = data.TileOutcome(page=0, ty=0, tx=0, stream_id="NOT-A-STREAM",
                            source="tiles/scan", result="certified",
                            bp_iters=1)
poisoned = ALL_EVENTS + [bad_pose, bad_tile]
try:
    model_poisoned = dm.fold(dm.empty(), poisoned)
    poisoned_raised = False
except Exception:
    model_poisoned = None
    poisoned_raised = True
check("poisoned events do not raise out of the fold", not poisoned_raised)
if model_poisoned is not None:
    check("poisoned fold still advances the cursor",
         model_poisoned.cursor == len(poisoned))
    check("poisoned events are counted, not silently dropped",
         model_poisoned.fold_errors >= 2)

# -- frames: clamped sizes, all four panes, chip pixels present -------------

pane_w, pane_h = panes.pane_size(run_open.tiles_yx)
title_size = max(9, min(15, round(pane_w * 0.032)))
title_h = max(18, title_size + 9)

frame0 = panes.render_frame(model_full, 0)
check("frame page0 starts with the PNG magic", frame0[:8] == PNG_MAGIC)
image0 = Image.open(io.BytesIO(frame0)).convert("RGB")
check("frame width is four clamped panes wide",
     image0.width == 4 * pane_w)
check("frame height is one clamped pane plus the title bar",
     image0.height == title_h + pane_h)

top_strip = np.asarray(image0)[:title_h, :]
title_matches = np.all(top_strip == np.asarray(panes.TITLE_FILL),
                       axis=-1).sum()
check("title bars painted across the strip", title_matches > 1000)

frame1 = panes.render_frame(model_full, 1)
check("frame page1 starts with the PNG magic", frame1[:8] == PNG_MAGIC)

page_raster = panes.page_pane(model_full, 0, pane_w, pane_h)
green_pixels = np.all(page_raster == np.asarray(panes.CHIP_GREEN[0]),
                      axis=-1).sum()
amber_pixels = np.all(page_raster == np.asarray(panes.CHIP_AMBER[0]),
                      axis=-1).sum()
reach_pixels = np.all(page_raster == np.asarray(panes.CHIP_REACH[0]),
                      axis=-1).sum()
check("page pane shows certified green chips", green_pixels > 0)
check("page pane shows attempted amber chips", amber_pixels > 0)
check("page pane shows addressed reach chips", reach_pixels > 0)

close_raster = panes.close_pane(model_full, pane_w, pane_h)
close_green = np.all(close_raster == np.asarray(panes.GREEN), axis=-1).sum()
check("close pane paints something in the verified colour", close_green > 0)

# -- posed pages + final-frame pinning --------------------------------------

check("posed pages cover both touched pages",
     dm.posed_pages(model_full) == (0, 1))
pinned_direct = dm.pin_frames(model_full)
check("pin_frames covers the posed pages", set(pinned_direct) == {0, 1})
for _page, _png in pinned_direct.items():
    check(f"pinned frame page {_page} is a valid png",
         _png[:8] == PNG_MAGIC)

# -- report.json + events.jsonl writers --------------------------------------

_tmp = Path(tempfile.mkdtemp(prefix="holo3-diag-verify-"))
events_path = _tmp / "events.jsonl"
dm.write_events_jsonl(events_path, ALL_EVENTS)
lines = events_path.read_text().splitlines()
check("events.jsonl has one line per event", len(lines) == len(ALL_EVENTS))
first_line = json.loads(lines[0])
check("events.jsonl line carries its event type",
     first_line.get("type") == "RunOpen")
last_line = json.loads(lines[-1])
check("events.jsonl survives a numpy-bearing event",
     json.loads(lines[4]).get("type") == "SurveyDone")
check("events.jsonl last event is RunDone", last_line.get("type") ==
     "RunDone")

report_path = _tmp / "report.json"
dm.write_report(report_path, model_full)
report = json.loads(report_path.read_text())
check("report.json carries six rows", len(report.get("rows", [])) == 6)
check("report.json fold_errors is zero on a clean model",
     report.get("fold_errors") == 0)
check("report.json carries per-capture facts", len(report.get(
    "captures", [])) == 2)

# -- HTTP server: loopback, status/frame routes, live revision growth ------

live_events: list[object] = list(EVENTS_PRE_SURVEY)
srv = server.serve(0, live_events)
check("server starts on an OS-assigned port", srv is not None)
if srv is not None:
    def _get(path: str, headers: dict | None = None) -> tuple[int, bytes,
                                                              dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{srv.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read(), dict(
                    response.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers or {})

    code, body, headers = _get("/status")
    check("status route serves 200", code == 200)
    status1 = json.loads(body)
    check("status JSON parses with six rows", len(status1["rows"]) == 6)
    check("status revision equals pre-survey event count",
         status1["revision"] == len(EVENTS_PRE_SURVEY))
    check("status carries no-store", headers.get("Cache-Control") ==
         "no-store")

    code, body, _ = _get("/status")
    status1b = json.loads(body)
    check("revision does not move without new events",
         status1b["revision"] == status1["revision"])

    live_events.extend(EVENTS_POST_SURVEY)
    code, body, _ = _get("/status")
    status2 = json.loads(body)
    check("revision moves once events grow",
         status2["revision"] == len(live_events) > status1["revision"])

    code, body, _ = _get("/frame/0.png")
    check("served frame is a valid png", code == 200 and
         body[:8] == PNG_MAGIC)

    code, body, _ = _get("/")
    check("home shell served", code == 200 and b"holo3 diag" in body)

    code, body, _ = _get("/status", {"Host": "evil.example.com"})
    check("a foreign Host header is refused", code == 403)

    pinned_over_http = srv.pin()
    check("server-side pin produced frames", len(pinned_over_http) >= 1)
    code, body, _ = _get("/frame/0.png")
    check("pinned frame still serves after pin", code == 200 and
         body[:8] == PNG_MAGIC)

    srv.stop()

srv_a = server.serve(0, [])
check("first bind on a free port succeeds", srv_a is not None)
if srv_a is not None:
    srv_b = server.serve(srv_a.port, [])
    check("a busy port refuses without raising", srv_b is None)
    srv_a.stop()

print()
if any(not ok for _name, ok in CHECKS):
    failed = [name for name, ok in CHECKS if not ok]
    print(f"VERIFY FAILED: {len(failed)}/{len(CHECKS)} checks failed")
    for name in failed:
        print(f"  - {name}")
    sys.exit(1)
print(f"VERIFY OK: {len(CHECKS)}/{len(CHECKS)} checks passed "
     "(diag/model.py, diag/panes.py, diag/server.py — synthetic fixtures, "
     "no oracle)")
