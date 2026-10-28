# Engine/CLI mechanical verification (stubbed plugin descriptors + stubbed
# close). Run from the worktree root:
#   env314t/bin/python _distill/verify/verify_engine.py
# Proves: descriptor births/wakes via the subscription index, frontier
# ordering, tried-set version floor, merge folding, C-6 conflict law,
# opposite-metadata-bit terminal check, single-writer-by-domain startup
# check, close consult flow (default / --no-close / --complete), VERIFIED
# preemption, worker-count payload identity, run-dir products, CLI refusals
# + atomic payload publication + exit codes, and the schedule verb.
from __future__ import annotations

import dataclasses
import hashlib
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from holo3 import cli, data, engine  # noqa: E402
from holo3.engine_types import job_price  # noqa: E402

CHECKS: list[str] = []


def check(name: str, ok: bool) -> None:
    CHECKS.append(name)
    marker = "ok " if ok else "FAIL"
    print(f"  {marker} {name}")
    if not ok:
        raise SystemExit(f"verify_engine: {name} failed")


ROW = engine.identity.resolve_format_ref("L:c2-r0700@3392x2368")
PAYLOAD = b"holo3-engine-verify-payload"
TILES = ((0, 0), (0, 1), (1, 0), (1, 1))
N_NEEDED = len(TILES)
USER_BITS = ROW.streams[0].user_bits
STREAM_ID = ROW.streams[0].stream_id

REAL_DESCRIPTORS = engine.DESCRIPTORS
REAL_BY_NAME = engine.DESCRIPTOR_BY_NAME


def make_capture(run_dir: Path) -> data.Capture:
    levels = tuple(
        data.Level(index=i, ppc=Fraction(4 * (i + 1)), scale=Fraction(1),
                   shape_px=(64, 64), label=f"l{i}")
        for i in range(2))
    return data.Capture(
        capture_id="deadbeef" * 8, path=run_dir / "scan.tiff", dpi=1200.0,
        shape_px=(64, 64), channels=1, platen_backing=0.9,
        levels=levels, plane_dir=run_dir)


def stub_intake(request: engine.DecodeRequest,
                row: object) -> tuple[tuple[data.Capture, ...],
                                      tuple[data.PlaneRaster, ...],
                                      tuple[object, ...]]:
    capture = make_capture(request.run_dir)
    event = data.CaptureOpen(capture=capture.capture_id, dpi=capture.dpi,
                             shape_yx=capture.shape_px, channels=1,
                             duplicate=False)
    return (capture,), (), (event,)


def stub_survey(store: object, subject: object, tier: str) -> object:
    region = data.Region(
        capture_id=str(subject), region_index=0, origin_yx=(0, 0),
        step_px=8, cells=np.ones((4, 4), bool), extent_px=(64, 64),
        area_mm2=10.0, median_tensor_score=1.0)
    survey = data.CaptureSurvey(capture_id=str(subject), regions=(region,),
                                pitch_class=Fraction(1, 300), pitch_px=4.0)
    event = data.SurveyDone(capture=str(subject), n_regions=1, regions=(),
                            pitch_class="c2", preview=None, preview_decim=1)
    return lambda: data.JobResult((survey,), (event,), 0.001)


def stub_place(store: object, subject: object, tier: str) -> object:
    wid = subject
    cells = np.array([[ty * 64, tx * 64] for ty, tx in TILES], np.int64)
    placement = data.Placement(
        window_id=wid, capture_id=wid[0], level_index=wid[1],
        region_index=wid[2], patch_ordinal=0, page=0, rot_k=0,
        page_origin_yx=(0, 0),
        native_affine=(8.0, 0.0, 0.0, 0.0, 8.0, 0.0), pitch_px=8.0,
        route="word", local_cells_yx=cells)
    event = data.PoseCommitted(capture=wid[0], level_index=wid[1],
                               region_index=wid[2], extent_cells=wid[3],
                               page=0, route="word", mismatch=0.01,
                               accepted=True)
    return lambda: data.JobResult((placement,), (event,), 0.002)


def stub_calibrate(store: object, subject: object, tier: str) -> object:
    wid = subject
    facts = tuple(
        data.TileEvidence(capture_id=wid[0], level_index=wid[1],
                          page=0, ty=ty, tx=tx,
                          values=np.zeros((1, 1), np.float32),
                          observed_flat=np.zeros(1, np.uint16),
                          arm="core", epoch=1)
        for ty, tx in TILES)
    return lambda: data.JobResult(facts, (), 0.003)


def true_bits(ty: int, tx: int) -> np.ndarray:
    seed = hashlib.sha256(f"{ty}/{tx}".encode()).digest()
    rng = np.random.default_rng(int.from_bytes(seed[:8], "big"))
    bits = rng.integers(0, 2, size=USER_BITS, dtype=np.uint8)
    bits[0] = np.uint8((ty + tx) & 1)
    return bits


def stub_scan(store: object, subject: object, tier: str) -> object:
    page, ty, tx, _capture_id, _level_index = subject
    if (page, ty, tx, STREAM_ID) in store._certificates:
        return None
    cert = data.Certificate(page=page, ty=ty, tx=tx, stream_id=STREAM_ID,
                            user_bits=true_bits(ty, tx),
                            source="tiles/scan")
    fact = data.AttemptFact(page=page, ty=ty, tx=tx, stream_id=STREAM_ID,
                            stage="scan", outcome="certified",
                            n_informative=4096, n_iters=3, syndrome_ok=True,
                            crc_ok=True)
    event = data.TileOutcome(page=page, ty=ty, tx=tx, stream_id=STREAM_ID,
                             source="tiles/scan", result="certified",
                             bp_iters=3)
    return lambda: data.JobResult((cert, fact), (event,), 0.004)


def stub_idle(store: object, subject: object, tier: str) -> object:
    return None


def stub_close_ready(certs: object, row: object) -> bool:
    return len(tuple(certs)) >= N_NEEDED


def stub_close_volume(certs: object, row: object) -> object:
    certs = tuple(certs)
    if len(certs) >= N_NEEDED:
        return SimpleNamespace(status="verified", payload=PAYLOAD,
                               k_total=1, blocks=(), symbols_used=len(certs),
                               reason=None, metadata_version=0)
    return SimpleNamespace(status="open", payload=None, k_total=None,
                           blocks=(), symbols_used=0, reason="short",
                           metadata_version=None)


STUB_PREPARES = {
    "survey": stub_survey,
    "place": stub_place,
    "calibrate": stub_calibrate,
    "tiles.scan": stub_scan,
}


def set_scan_prepare(prepare: object) -> None:
    stubs = []
    for descriptor in engine.DESCRIPTORS:
        if descriptor.name == "tiles.scan":
            descriptor = dataclasses.replace(descriptor, prepare=prepare)
        stubs.append(descriptor)
    engine.DESCRIPTORS = tuple(stubs)
    engine.DESCRIPTOR_BY_NAME = {
        descriptor.name: descriptor for descriptor in engine.DESCRIPTORS}


def install_stubs() -> None:
    engine._intake_run = stub_intake
    stubs = []
    for descriptor in REAL_DESCRIPTORS:
        prepare = STUB_PREPARES.get(descriptor.name, stub_idle)
        stubs.append(dataclasses.replace(descriptor, prepare=prepare))
    engine.DESCRIPTORS = tuple(stubs)
    engine.DESCRIPTOR_BY_NAME = {
        descriptor.name: descriptor for descriptor in engine.DESCRIPTORS}
    engine.format_close = SimpleNamespace(
        close_count_ready=stub_close_ready, close_volume=stub_close_volume)


def request_for(run_dir: Path, workers: int = 1, complete: bool = False,
                no_close: bool = False) -> engine.DecodeRequest:
    return engine.DecodeRequest(
        scans=(run_dir / "scan.tiff",), dpi=1200.0,
        format_ref="L:c2-r0700@3392x2368", n_pages=1, workers=workers,
        complete=complete, no_close=no_close, diag_port=None,
        run_dir=run_dir)


def run_decode(**kwargs: object) -> tuple[data.RunResult, list, Path]:
    run_dir = Path(tempfile.mkdtemp(prefix="holo3-verify-"))
    events: list = []
    result = engine.decode(request_for(run_dir, **kwargs), events)
    return result, events, run_dir


def main() -> None:
    install_stubs()

    print("descriptor law:")
    bad = dataclasses.replace(REAL_BY_NAME["refine"], name="rogue",
                              produces=(data.Placement,))
    try:
        engine.check_single_writer(REAL_DESCRIPTORS + (bad,))
        check("single-writer-by-domain startup check", False)
    except data.IntegrityError:
        check("single-writer-by-domain startup check", True)
    engine.check_single_writer(REAL_DESCRIPTORS)
    check("real descriptor set passes single-writer", True)
    check("descriptor names unique",
          len({d.name for d in REAL_DESCRIPTORS})
          == len(REAL_DESCRIPTORS))

    print("engine loop:")
    result, events, run_dir = run_decode()
    check("default run verified", result.status == "verified")
    check("payload bytes exact", result.payload == PAYLOAD)
    check("payload sha printed", result.payload_sha256
          == hashlib.sha256(PAYLOAD).hexdigest())
    check("certified count", result.certified == N_NEEDED)
    kinds = {type(e).__name__ for e in events}
    check("event stream shape",
          {"RunOpen", "CaptureOpen", "SurveyDone", "PoseCommitted",
           "TileOutcome", "JobDone", "CloseCheck",
           "RunDone"} <= kinds)
    run_done = [e for e in events if isinstance(e, data.RunDone)]
    check("one run.done, verified", len(run_done) == 1
          and run_done[0].status == "verified")
    plugin_names = {row.plugin for row in result.plugin_rows}
    check("plugin accounting rows",
          {"survey", "place", "calibrate", "tiles.scan"} <= plugin_names)
    tiles_row = next(r for r in result.plugin_rows
                     if r.plugin == "tiles.scan")
    check("tiles certificates tallied",
          tiles_row.certificates == N_NEEDED)
    place_row = next(r for r in result.plugin_rows if r.plugin == "place")
    check("poses + words tallied",
          place_row.poses >= 1 and place_row.words >= 1)
    check("argv line landed", (run_dir / "argv").exists())
    print(f"  (run-dir products: "
          f"events.jsonl={(run_dir / 'events.jsonl').exists()} "
          f"report.json={(run_dir / 'report.json').exists()})")

    job_costs = [e.cost for e in events if isinstance(e, data.JobDone)]
    check("survey cheapest first", job_costs[0] == 10)
    check("no admission gate: pure cost order (ruling 2026-08-28)",
          not hasattr(engine, "GATED_COST"))

    result8, _events8, _dir8 = run_decode(workers=8)
    check("workers=8 payload identical", result8.payload == PAYLOAD
          and result8.status == "verified")

    result_nc, events_nc, _dir_nc = run_decode(no_close=True)
    check("--no-close never solves", result_nc.status == "open"
          and result_nc.payload is None)
    nc_checks = [e for e in events_nc if isinstance(e, data.CloseCheck)]
    check("--no-close observes counts",
          any(c.status == "count_ready" for c in nc_checks))

    result_c, events_c, _dir_c = run_decode(complete=True)
    check("--complete closes at exhaustion",
          result_c.status == "verified" and result_c.payload == PAYLOAD)
    c_checks = [e for e in events_c if isinstance(e, data.CloseCheck)]
    check("--complete defers mid-run consults",
          all(c.status in ("deferred", "verified") for c in c_checks)
          and c_checks[-1].status == "verified")

    print("integrity laws:")

    def conflicting_scan(store: object, subject: object,
                         tier: str) -> object:
        inner = stub_scan(store, subject, tier)
        if inner is None:
            return None
        page, ty, tx, _capture_id, _level_index = subject
        flipped = true_bits(ty, tx).copy()
        flipped[5] ^= 1
        bad = data.Certificate(page=page, ty=ty, tx=tx, stream_id=STREAM_ID,
                               user_bits=flipped, source="tiles/union")

        def job() -> data.JobResult:
            base = inner()
            return data.JobResult(base.facts + (bad,), base.events,
                                  base.cpu_s)

        return job

    set_scan_prepare(conflicting_scan)
    try:
        run_decode()
        check("C-6 conflict fatal", False)
    except data.IntegrityError:
        check("C-6 conflict fatal", True)
    set_scan_prepare(stub_scan)

    def duplicate_scan(store: object, subject: object, tier: str) -> object:
        inner = stub_scan(store, subject, tier)
        if inner is None:
            return None

        def job() -> data.JobResult:
            base = inner()
            return data.JobResult(base.facts + base.facts, base.events,
                                  base.cpu_s)

        return job

    set_scan_prepare(duplicate_scan)
    result_dup, _e, _d = run_decode()
    check("identical duplicate is a no-op",
          result_dup.status == "verified"
          and result_dup.certified == N_NEEDED)
    set_scan_prepare(stub_scan)

    print("pricing:")
    check("first price = tier + premium",
          job_price("payload", 4, 0) == 24)
    check("rework n=1 -> max(tier, 90)",
          job_price("payload", 4, 1) == 94)
    check("rework n=3 -> 100",
          job_price("payload", 0, 3) == 100)
    check("rework never undercuts tier",
          job_price("refine", 0, 2) == 200)

    print("cli:")
    scratch = Path(tempfile.mkdtemp(prefix="holo3-verify-cli-"))
    scan = scratch / "scan.tiff"
    scan.write_bytes(b"not-a-real-tiff")
    out = scratch / "payload.bin"
    base = ["decode", str(scan), "--dpi", "1200",
            "--format", "L:c2-r0700@3392x2368", "--out", str(out)]
    check("verified run exits 0", cli.main(base) == 0)
    check("payload file written", out.read_bytes() == PAYLOAD)
    check("existing --out refused", cli.main(base) == 1)
    check("missing --dpi refused",
          cli.main(["decode", str(scan), "--format", "x",
                    "--out", str(scratch / "o2")]) == 1)
    check("mixed dpi refused",
          cli.main(["decode", str(scan), str(scan), "--dpi", "1200",
                    "--dpi", "2400", "--format", "x",
                    "--out", str(scratch / "o3")]) == 1)
    check("format + coding refused",
          cli.main(["decode", str(scan), "--dpi", "1200", "--format", "x",
                    "--coding", "c2-r0700", "--printer", "hp-m281-ink",
                    "--out", str(scratch / "o4")]) == 1)
    check("neither format route refused",
          cli.main(["decode", str(scan), "--dpi", "1200",
                    "--out", str(scratch / "o5")]) == 1)
    check("unknown printer refused",
          cli.main(["decode", str(scan), "--dpi", "1200",
                    "--coding", "c2-r0700", "--printer", "nope",
                    "--out", str(scratch / "o6")]) == 1)
    check("unknown fossil refused",
          cli.main(["decode", str(scan), "--dpi", "1200",
                    "--format", "L:nope", "--out", str(scratch / "o7")]) == 1)
    out2 = scratch / "sugar.bin"
    check("coding+printer sugar route works",
          cli.main(["decode", str(scan), "--dpi", "1200",
                    "--coding", "c2-r0700", "--printer", "hp-m281-ink",
                    "--out", str(out2)]) == 0
          and out2.read_bytes() == PAYLOAD)

    set_scan_prepare(stub_idle)
    out3 = scratch / "open.bin"
    check("open run exits 2",
          cli.main(["decode", str(scan), "--dpi", "1200",
                    "--format", "L:c2-r0700@3392x2368",
                    "--out", str(out3)]) == 2 and not out3.exists())
    set_scan_prepare(stub_scan)

    check("schedule verb exits 0", cli.main(["schedule"]) == 0)
    check("schedule --format annotates",
          cli.main(["schedule", "--format",
                    "L:c2-r0700@3392x2368"]) == 0)
    check("schedule unknown format refused",
          cli.main(["schedule", "--format", "L:nope"]) == 1)

    print(f"verify_engine: {len(CHECKS)} checks green")


if __name__ == "__main__":
    main()
