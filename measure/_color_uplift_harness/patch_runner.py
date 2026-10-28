"""Full-pipeline micro-runs over the specimen patches.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.patch_runner run --name l00tax-a
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.patch_runner pin
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.patch_runner compare
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.patch_runner diff --a A.json --b B.json

One micro-run drives the REAL production receiver end to end over one
specimen patch (:mod:`patch_corpus`): ``run_receive`` on a fresh state in
a ``TemporaryDirectory``, survey -> placement -> BCH word solve ->
absolute addresses -> the full multi-lane payload ladder, with the
archived captures' own flag shape (``--refine``, which implies mop-up by
the plan-prefix law) and ``--page 0``.  A patch is a SCRAP: the receiver
is not told where it came from, and every address it reports it solved
for itself.

WHAT THIS TIER CAN CLAIM.  End-to-end regression and pathology
development.  A patch run is NOT a capture-level number: the region fit
sees only the patch's own furniture, the scale ladder schedules a
different open set, and the fountain can never close.  Never quote a
patch cert count as an uplift number — quote the DIFF between two patch
runs of the same specimen.

WHAT IS PINNED.  ``pin`` records each specimen's outcome keyed by the
FULL receiver policy id (``production_pipeline(...).policy_id``) AND by
the environment-hatch signature, because ``HOLO_COLOR_*`` hatches move
receiver behaviour without moving the policy id.  ``compare`` re-runs and
diffs against the pin for the CURRENT key; with no pin for that key it
falls back to the newest older pin and says so loudly.  Re-pinning is
always an explicit ``pin`` command, never a side effect of ``compare``.

Truth: every run is audited against the parent capture's emitted ground
truth through ``gt_score.audit_certificates`` (bar B5, unchanged), and
separately against the specimen's own sliced GT file, so a patch that
certified a wrong cell fails here exactly as a capture would.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np

from . import corpus, gt_score, patch_corpus

SCHEMA = "color-uplift-patch-run-1"
#: The ONE environment contract left (PK-CLEAN): force-null can only
#: REMOVE behaviour and must reach code paths that see no configuration
#: object.  The three sweep hatches are retired — a specimen run drives
#: the production ``run_receive`` ladder, which has no configuration
#: seam, so this tier runs the FROZEN constants and its entry point
#: refuses a sweep flag rather than ignoring one.
HATCH_ENV = ("HOLO_COLOR_STACK_FORCE_NULL",)


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, check=True).stdout.strip()


def _worktree_identity() -> dict:
    return {
        "head": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
    }


# The PRODUCER set: every module whose output a feature library shadows.
# Hashing these and NOT the arm ladder is what lets a library survive an
# iteration and refuse a producer change.
PRODUCER_MODULES = (
    "color_sampling.py", "color_anchoring.py", "known_field.py",
    "color_payload.py", "place.py", "color_refine.py",
)
# The ARM ladder: the iteration surface.  Never part of a library's
# validity key (moving it is the point), always REPORTED, because a
# fidelity claim — "the library reproduced the replay" — is only about
# one arm if both ran the same arm code.
ARM_MODULES = (
    "color_stack.py", "color_locality.py", "color_fitting.py",
    "color_calibration.py", "color_conditioning.py",
)
SRC_RECEIVE = Path(__file__).resolve().parents[2] / "src" / "holo" / "receive"


def _source_identity(names: tuple[str, ...]) -> str:
    """SHA-256 over the SOURCE TEXT of the named receiver modules."""
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update((SRC_RECEIVE / name).read_bytes())
    return digest.hexdigest()


def _receiver_tree_sha256() -> str:
    """SHA-256 over every source file under ``src/holo`` — content only."""
    digest = hashlib.sha256()
    root = SRC_RECEIVE.parent
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def tree_state() -> dict:
    """Identify the exact code this process is about to import.

    HEAD is not the code.  This worktree is shared with other campaign
    workers whose uncommitted diff IS the code under test, and it can be
    swapped out mid-flight: on 2026-08-08 a concurrent ``git stash
    push``/``pop`` (10:47-10:49) invalidated every run started in that
    window, and a concurrent COMMIT at 11:07 moved HEAD and emptied the
    diff without changing one byte of source.  A git-shaped fingerprint
    gets the first case right and the second one wrong, so the load-
    bearing field here is a CONTENT hash of ``src/holo``; the git fields
    ride along as context, never as the test.

    A run records this at entry and at exit.  Different snapshots mean
    the code moved under the run and the result is void.
    """
    status = _git("status", "--porcelain")
    return {
        "receiver_tree_sha256": _receiver_tree_sha256(),
        "producer_identity": _source_identity(PRODUCER_MODULES),
        "arm_identity": _source_identity(ARM_MODULES),
        "head": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode()).hexdigest(),
    }


def _tree_moved(before: dict, after: dict) -> bool:
    """Did the CODE move?  Git bookkeeping alone never counts."""
    return any(before.get(key) != after.get(key) for key in
               ("receiver_tree_sha256", "producer_identity", "arm_identity"))


def hatch_signature() -> dict:
    """The environment hatches in force, as a canonical record.

    A hatch changes receiver behaviour WITHOUT changing the policy id, so
    a pin taken under a hatch is a different baseline; the signature is
    part of the pin key for exactly that reason.
    """
    return {name: os.environ[name] for name in HATCH_ENV if os.environ.get(name)}


def pin_key(policy_id: str, hatches: dict) -> str:
    text = policy_id + "|" + json.dumps(hatches, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _request(entry: dict, path: Path, state_path: Path):
    from holo.receive.runtime import ReceiveRequest
    from holo.receive.types import CaptureInput

    capture_row = corpus.capture(entry["capture"])
    spec = corpus.resolve_spec(capture_row, entry["format_row_id"])
    return spec, ReceiveRequest(
        spec,
        (CaptureInput(str(path), float(entry["scan_dpi"])),),
        state_path=state_path,
        page_hypotheses=(int(entry["page"]),),
        # A patch can never close a volume; the close is deferred so a
        # micro-run measures the ladder and nothing else.
        defer_fountain_close=True,
        run_mopup=True,
        run_refine=True,
    )


def _lane_rows(state) -> list[dict]:
    capture = state.captures[0]
    rows = []
    for ordinal, level in enumerate(capture.levels):
        lane = capture.plan[ordinal]
        payload = level.payload
        address = level.address
        rows.append({
            "ordinal": ordinal,
            "lane_id": lane.lane_id,
            "certificates": 0 if payload is None else len(
                payload.certificate_ids),
            "attempts": 0 if payload is None else int(payload.n_attempts),
            "blocks": 0 if payload is None else int(payload.n_blocks),
            "poses": 0 if address is None else len(address.pose_ids),
            "regions": 0 if level.survey is None else len(
                level.survey.region_ids),
        })
    return rows


class AttemptCollector:
    """Keep each barrier's own ``TileAttemptRecord`` rows for the run.

    Tile-level BP margin lives in those rows and nowhere else (``n_iters``
    against the 60/150 caps, summed over the frame's LDPC children), and
    §4.5.1's discriminating statistic for the l00 head tax is a PAIRED
    ``n_iters`` comparison on the tiles both arms certify.  A patch has
    tens of tiles, not hundreds, so a certificate count alone is far too
    coarse to show that pathology — the margin is the signal.

    The rows are NOT durable: ``SessionCounters.fold`` folds them into
    per-stage tallies and the state keeps no copies.  They are therefore
    taken at the payload stage's own output, exactly as ``replay
    --record-attempts`` takes them (``product.attempts``), by wrapping
    ``ProductionColorPayload.process`` for the life of one run.  The
    wrapper reads the product and returns it untouched; it cannot change
    a decode outcome.
    """

    __slots__ = ("rows", "_saved")

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._saved = None

    def __enter__(self) -> "AttemptCollector":
        from holo.receive.production_color import ProductionColorPayload

        original = ProductionColorPayload.process
        self._saved = original
        collector = self

        def process(self, context, survey_product, address_product):
            output = original(self, context, survey_product, address_product)
            collector.rows.extend(
                {
                    "lane_id": row.lane_id,
                    "page": int(row.page),
                    "tile_yx": [int(row.tile_yx[0]), int(row.tile_yx[1])],
                    "stream_id": row.stream_id,
                    "stage": row.stage.value,
                    "state": row.state.value,
                    "n_informative": int(row.n_informative),
                    "n_iters": int(row.n_iters),
                    "syndrome_ok": row.syndrome_ok,
                    "crc_ok": row.crc_ok,
                }
                for row in output.product.attempts)
            return output

        ProductionColorPayload.process = process
        return self

    def __exit__(self, *exc: object) -> None:
        from holo.receive.production_color import ProductionColorPayload

        if self._saved is not None:
            ProductionColorPayload.process = self._saved
            self._saved = None


def _certificate_lanes(state) -> list[dict]:
    """Which barrier minted each certified address."""
    capture = state.captures[0]
    lane_by_id: dict[str, str] = {}
    for ordinal, level in enumerate(capture.levels):
        if level.payload is None:
            continue
        for identity in level.payload.certificate_ids:
            lane_by_id[identity] = capture.plan[ordinal].lane_id
    return sorted(
        ({"address": [int(row.page), int(row.tile_yx[0]),
                      int(row.tile_yx[1]), str(row.stream_id)],
          "lane_id": lane_by_id.get(row.certificate_id)}
         for row in state.certificates),
        key=lambda row: row["address"])


def _addresses(certificates) -> list[list]:
    return sorted(
        [int(row.page), int(row.tile_yx[0]), int(row.tile_yx[1]),
         str(row.stream_id)]
        for row in certificates)


def _by_stream(certificates) -> dict:
    counts: dict[str, int] = {}
    for row in certificates:
        counts[row.stream_id] = counts.get(row.stream_id, 0) + 1
    return dict(sorted(counts.items()))


def _domain_check(entry: dict, certificates) -> dict:
    """Every certified address must lie in the patch's own tile domain."""
    ty0, ty1 = entry["domain_tiles_y"]
    tx0, tx1 = entry["domain_tiles_x"]
    outside = sorted(
        [int(row.page), int(row.tile_yx[0]), int(row.tile_yx[1]),
         str(row.stream_id)]
        for row in certificates
        if not (int(row.page) == int(entry["page"])
                and ty0 <= int(row.tile_yx[0]) < ty1
                and tx0 <= int(row.tile_yx[1]) < tx1))
    core = {(ty, tx) for ty in range(*entry["core_tiles_y"])
            for tx in range(*entry["core_tiles_x"])}
    certified_tiles = {
        (int(row.tile_yx[0]), int(row.tile_yx[1])) for row in certificates}
    return {
        "outside_domain": len(outside),
        "outside_examples": outside[:10],
        "core_tiles": len(core),
        "core_tiles_certified": len(core & certified_tiles),
        "halo_tiles_certified": len(certified_tiles - core),
    }


class RegionObserver:
    """Collect the payload stage's own per-region diagnostic rows.

    The arm verdicts a specimen exists to exhibit — the cmy7 head's
    reason and saturation, A3's window counts and dispersions — are
    published only as ``payload.region`` event details.  A certificate
    count cannot say WHY two arms agree; these rows can.  Strictly
    downstream (RECEIVE-DESIGN §10): the observer sees events and never
    feeds the decode.
    """

    __slots__ = ("rows", "_lane")

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._lane = "?"

    def __call__(self, event) -> None:
        details = {row.name: row.value for row in event.details}
        lane = details.get("lane.id")
        if isinstance(lane, str):
            self._lane = lane
        if event.name != "payload.region":
            return
        row = {"lane_id": self._lane}
        row.update({
            key: value for key, value in details.items()
            if key.startswith("color.") and key not in (
                "color.region",)})
        self.rows.append(row)

    def by_lane(self) -> dict:
        out: dict[str, list[dict]] = {}
        for row in self.rows:
            out.setdefault(row["lane_id"], []).append(
                {key: value for key, value in row.items()
                 if key != "lane_id"})
        return out


def _gt_slice_check(entry: dict, truth) -> dict:
    """The specimen's own GT file must equal the parent page's slice."""
    stored = np.load(entry["gt"])
    cy0, cy1 = entry["domain_cells_y"]
    cx0, cx1 = entry["domain_cells_x"]
    live = truth.cell_bits[:, cy0:cy1, cx0:cx1]
    return {
        "shape": list(stored.shape),
        "identical_to_parent_slice": bool(
            stored.shape == live.shape and np.array_equal(stored, live)),
    }


def run_patch(name: str, *, arm: str, workers: int | None,
              out: Path | None = None, verbose: bool = True) -> dict:
    """One end-to-end micro-decode of one specimen patch."""
    from holo.receive import _parallel
    from holo.receive.observer import ProvisionalReceiverWarning
    from holo.receive.production import production_pipeline
    from holo.receive.runtime import run_receive

    entry = patch_corpus.manifest_row(name)
    path = Path(entry["tiff"])
    if not path.is_file():
        raise SystemExit(f"{name}: patch tiff missing at {path}")
    live_sha = corpus.sha256_file(path)
    if live_sha != entry["tiff_sha256"]:
        raise SystemExit(
            f"{name}: patch sha {live_sha[:16]}… != manifest "
            f"{entry['tiff_sha256'][:16]}… — REFUSING to run")
    recorded = corpus.provenance_row(entry["capture"])
    if recorded["artifacts"]["tiff"]["sha256"] != entry["capture_sha256"]:
        raise SystemExit(
            f"{name}: the parent capture moved — REFUSING to run")
    if workers is not None:
        _parallel.set_worker_count(workers)

    hatches = hatch_signature()
    # Snapshot the tree BEFORE the receiver modules are imported and again
    # after the run; a shared worktree can move underneath a decode.
    tree_before = tree_state()
    with tempfile.TemporaryDirectory(prefix=f"holo-patch-{name}-") as scratch:
        state_path = Path(scratch) / "receive.state"
        spec, request = _request(entry, path, state_path)
        regions = RegionObserver()
        with warnings.catch_warnings(), AttemptCollector() as collector:
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            pipeline = production_pipeline(request)
            started = time.perf_counter()
            cpu_started = time.process_time()
            result = run_receive(request, pipeline=pipeline,
                                 observer=regions)
        wall = time.perf_counter() - started
        cpu = time.process_time() - cpu_started
        state = result.state
        certificates = tuple(state.certificates)
        lane_rows = _lane_rows(state)
        certificate_lanes = _certificate_lanes(state)
        attempts = collector.rows
        state_bytes = state_path.stat().st_size if state_path.is_file() else 0

    tree_after = tree_state()
    capture_row = corpus.capture(entry["capture"])
    truth = gt_score.load_ground_truth(capture_row)
    audit = gt_score.audit_certificates(certificates, spec, truth)
    report = {
        "schema": SCHEMA,
        "mode": "patch",
        "arm": arm,
        "name": name,
        "theme": entry["theme"],
        "capture": entry["capture"],
        "kind": entry["kind"],
        "engine": entry["engine"],
        "format_row_id": entry["format_row_id"],
        "patch_sha256": live_sha,
        "capture_sha256": entry["capture_sha256"],
        "core_tiles_y": entry["core_tiles_y"],
        "core_tiles_x": entry["core_tiles_x"],
        "domain_tiles_y": entry["domain_tiles_y"],
        "domain_tiles_x": entry["domain_tiles_x"],
        "crop_shape_yx": entry["tiff_shape_yx"],
        "worktree": _worktree_identity(),
        "tree_state_before": tree_before,
        "tree_state_after": tree_after,
        "tree_stable": not _tree_moved(tree_before, tree_after),
        "receiver_policy_id": pipeline.policy_id,
        "qualification_status": pipeline.qualification_status.value,
        "hatches": hatches,
        "pin_key": pin_key(pipeline.policy_id, hatches),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "workers": int(_parallel.worker_count())
            if hasattr(_parallel, "worker_count") else "unknown",
            "workers_requested": None if workers is None else int(workers),
        },
        "totals": {
            "certificates": len(certificates),
            "addresses": len({tuple(row) for row in _addresses(certificates)}),
            "by_stream": _by_stream(certificates),
            "barriers": len(state.captures[0].levels),
            "close_status": state.close.status.value,
            "wall_s": round(wall, 1),
            "cpu_s": round(cpu, 1),
            # PROCESS high-water mark, not this specimen's own peak: a
            # `pin`/`compare` sweep runs many specimens in one process, so
            # every row after the first inherits the largest peak so far.
            # Only a standalone `run` reports a per-specimen number.
            "peak_rss_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20),
            "peak_rss_is_process_high_water": True,
            "state_bytes": int(state_bytes),
        },
        "lanes": lane_rows,
        "regions_by_lane": regions.by_lane(),
        "attempts": attempts,
        "certificate_lanes": certificate_lanes,
        "addresses": _addresses(certificates),
        "domain": _domain_check(entry, certificates),
        "gt_slice": _gt_slice_check(entry, truth),
        "certificate_audit": {
            key: value for key, value in audit.items()
            if key != "wrong_certificate_addresses"},
        "wrong_certificate_addresses": audit["wrong_certificate_addresses"],
    }
    path_out = out or (
        corpus.work_dir("patch-runs") / f"{name}-{arm}.json")
    path_out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    if verbose:
        print(json.dumps({
            "name": name, "arm": arm,
            "certificates": report["totals"]["certificates"],
            "by_stream": report["totals"]["by_stream"],
            "core_certified": report["domain"]["core_tiles_certified"],
            "outside_domain": report["domain"]["outside_domain"],
            "agreement": report["certificate_audit"]["agreement"],
            "wall_s": report["totals"]["wall_s"],
            "cpu_s": report["totals"]["cpu_s"],
            "out": str(path_out)}))
    if audit["disagreeing_addresses"]:
        print(f"CAMPAIGN-STOP: {name} certified a cell that disagrees with "
              "ground truth (bar B5)", file=sys.stderr)
    if _tree_moved(tree_before, tree_after):
        print(f"!! {name}: THE TREE MOVED DURING THIS RUN "
              f"(receiver tree {tree_before['receiver_tree_sha256'][:12]}… "
              f"-> {tree_after['receiver_tree_sha256'][:12]}…) — VOID, "
              "re-run it", file=sys.stderr)
    return report


def _outcome(report: dict) -> dict:
    """The pinned, comparable part of a run: sets, not timings."""
    return {
        "certificates": report["totals"]["certificates"],
        "by_stream": report["totals"]["by_stream"],
        "addresses": report["addresses"],
        "lane_certificates": {
            row["lane_id"]: row["certificates"] for row in report["lanes"]},
        "core_tiles_certified": report["domain"]["core_tiles_certified"],
        "outside_domain": report["domain"]["outside_domain"],
        "agreement": report["certificate_audit"]["agreement"],
        "disagreeing_addresses": report["certificate_audit"][
            "disagreeing_addresses"],
    }


def _address_set(outcome: dict) -> set:
    return {tuple(row) for row in outcome["addresses"]}


def diff_outcomes(baseline: dict, candidate: dict) -> dict:
    before, after = _address_set(baseline), _address_set(candidate)
    gained, lost = after - before, before - after
    lanes = sorted(set(baseline["lane_certificates"])
                   | set(candidate["lane_certificates"]))
    return {
        "baseline_certificates": baseline["certificates"],
        "candidate_certificates": candidate["certificates"],
        "gained": len(gained),
        "lost": len(lost),
        "net": len(gained) - len(lost),
        "gained_addresses": sorted(gained),
        "lost_addresses": sorted(lost),
        "identical": not gained and not lost,
        "lane_delta": {
            lane: [baseline["lane_certificates"].get(lane),
                   candidate["lane_certificates"].get(lane)]
            for lane in lanes
            if baseline["lane_certificates"].get(lane)
            != candidate["lane_certificates"].get(lane)},
    }


def cmd_run(args: argparse.Namespace) -> int:
    names = args.name or [row.name for row in patch_corpus.SPECIMENS]
    for name in names:
        run_patch(name, arm=args.arm, workers=args.workers,
                  out=Path(args.out) if args.out else None)
    return 0


def cmd_pin(args: argparse.Namespace) -> int:
    """Run every named specimen and store its outcome as the baseline."""
    names = args.name or [row.name for row in patch_corpus.SPECIMENS]
    manifest = patch_corpus.load_manifest()
    pins = manifest.setdefault("pins", {})
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    for name in names:
        report = run_patch(name, arm=args.arm, workers=args.workers)
        key = report["pin_key"]
        bucket = pins.setdefault(key, {
            "receiver_policy_id": report["receiver_policy_id"],
            "hatches": report["hatches"],
            "specimens": {}})
        bucket["specimens"][name] = {
            "pinned_at": stamp,
            "worktree_head": report["worktree"]["head"],
            "worktree_dirty": report["worktree"]["dirty"],
            # The CONTENT of the tree this baseline was taken on, not just
            # its commit: a shared worktree's uncommitted diff is the code
            # under test, so a pin that does not name it cannot be audited.
            "tree_state": report["tree_state_before"],
            "tree_stable": report["tree_stable"],
            "wall_s": report["totals"]["wall_s"],
            "cpu_s": report["totals"]["cpu_s"],
            "peak_rss_mib": report["totals"]["peak_rss_mib"],
            "outcome": _outcome(report),
        }
        patch_corpus.write_manifest(manifest)
        print(f"pinned {name} under {key}")
    return 0


def _fallback_pin(pins: dict, key: str, name: str) -> tuple[str, dict] | None:
    """The newest OTHER pin carrying this specimen (loud fallback only)."""
    candidates = [
        (bucket["specimens"][name]["pinned_at"], other, bucket)
        for other, bucket in pins.items()
        if other != key and name in bucket.get("specimens", {})]
    if not candidates:
        return None
    _stamp, other, bucket = max(candidates)
    return other, bucket


def cmd_compare(args: argparse.Namespace) -> int:
    """Re-run every specimen and diff against the pin for this policy."""
    names = args.name or [row.name for row in patch_corpus.SPECIMENS]
    pins = patch_corpus.load_manifest().get("pins", {})
    rows = []
    regressions = 0
    for name in names:
        report = run_patch(name, arm=args.arm, workers=args.workers)
        key = report["pin_key"]
        bucket = pins.get(key)
        note = ""
        pinned = None
        if bucket is not None and name in bucket.get("specimens", {}):
            pinned = bucket["specimens"][name]
        else:
            fallback = _fallback_pin(pins, key, name)
            if fallback is None:
                rows.append({"name": name, "status": "NO PIN",
                             "certificates":
                             report["totals"]["certificates"]})
                print(f"!! {name}: NO PIN for policy key {key} and no older "
                      "pin exists — this run pins nothing", file=sys.stderr)
                continue
            other, other_bucket = fallback
            pinned = other_bucket["specimens"][name]
            note = (
                f"!! NO PIN for the current policy key {key}; comparing "
                f"against the older pin {other} "
                f"(policy {other_bucket['receiver_policy_id']}, hatches "
                f"{other_bucket['hatches']}) — the diff below mixes a "
                "policy change with any real regression")
            print(note, file=sys.stderr)
        delta = diff_outcomes(pinned["outcome"], _outcome(report))
        rows.append({
            "name": name,
            "status": "identical" if delta["identical"] else "MOVED",
            "pinned_certificates": delta["baseline_certificates"],
            "certificates": delta["candidate_certificates"],
            "gained": delta["gained"], "lost": delta["lost"],
            "net": delta["net"],
            "lane_delta": delta["lane_delta"],
            "gained_addresses": delta["gained_addresses"][:20],
            "lost_addresses": delta["lost_addresses"][:20],
            "wall_s": [pinned["wall_s"], report["totals"]["wall_s"]],
            "pinned_arm": (pinned.get("tree_state") or {}).get(
                "arm_identity"),
            "run_arm": report["tree_state_before"]["arm_identity"],
            "same_arm_code": (
                (pinned.get("tree_state") or {}).get("arm_identity")
                == report["tree_state_before"]["arm_identity"]),
            "tree_stable": report["tree_stable"],
            "agreement": report["certificate_audit"]["agreement"],
            "wrong_certificates": report["certificate_audit"][
                "disagreeing_addresses"],
            "note": note,
        })
        regressions += bool(delta["lost"]) or bool(
            report["certificate_audit"]["disagreeing_addresses"])
    out = {
        "schema": "color-uplift-patch-compare-1",
        "arm": args.arm,
        "worktree": _worktree_identity(),
        "specimens": rows,
        "specimens_moved": sum(1 for row in rows
                               if row.get("status") == "MOVED"),
        "specimens_with_losses": regressions,
    }
    text = json.dumps(out, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


def arm_verdicts(report: dict) -> dict:
    """Per-lane arm verdicts: WHY two arms agree or differ."""
    out: dict[str, list[dict]] = {}
    for lane, rows in report.get("regions_by_lane", {}).items():
        out[lane] = [{
            "accepted": row.get("color.accepted"),
            "reason": row.get("color.reason"),
            "heldout_sites": row.get("color.heldout_sites"),
            "head_reason": row.get("color.cmy7_head.reason"),
            "head_adopted": row.get("color.cmy7_head.adopted"),
            "head_temperature": row.get("color.cmy7_head.temperature"),
            "head_saturation": row.get(
                "color.cmy7_head.baseline_saturation_fraction"),
            "head_floor": row.get("color.cmy7_head.saturation_floor"),
            # A3's per-region record.  It appears on a `u*-a3` lane and
            # nowhere else since PK-CLEAN made the arm override-only, and
            # its dispersion statistic is RETIRED (MEASUREMENTS §12 R1-R4).
            "a3_reason": row.get("color.window_maps.reason"),
            "a3_accepted": row.get("color.window_maps.accepted"),
            "a3_prior_labels": row.get("color.window_maps.prior_labels"),
        } for row in rows]
    return out


def margin_delta(a: dict, b: dict, lane_prefix: str = "") -> dict:
    """§4.5.1's paired BP-margin statistic, per lane, at patch scale.

    Both arms attempt the same addresses; the honest comparison is the
    PAIRED ``n_iters`` difference over the tiles that certify in BOTH,
    restricted to the tiles that certify at the same stage in both (the
    stage-matched control §4.5.1 also ran).  Lower ``n_iters`` = more
    margin, so a positive mean delta is a TAX on the b arm.
    """
    def index(report: dict) -> dict:
        out: dict[tuple, dict] = {}
        # A run JSON written before attempt retention carries no rows; the
        # statistic is then simply unavailable, never silently empty.
        for row in report.get("attempts", ()):
            if not row["lane_id"].startswith(lane_prefix):
                continue
            key = (row["lane_id"], row["page"], row["tile_yx"][0],
                   row["tile_yx"][1], row["stream_id"])
            # One tile may attempt twice (scan then retry150); the
            # certifying attempt is the one that matters, else the last.
            if row["crc_ok"] or key not in out:
                out[key] = row
        return out

    if not a.get("attempts") or not b.get("attempts"):
        return {"unavailable": "one run carries no attempt rows"}
    left, right = index(a), index(b)
    lanes: dict[str, dict] = {}
    for key in sorted(set(left) & set(right)):
        one, two = left[key], right[key]
        if not (one["crc_ok"] and two["crc_ok"]):
            continue
        lane = lanes.setdefault(key[0], {
            "paired_tiles": 0, "worse": 0, "better": 0, "unchanged": 0,
            "deltas": [], "stage_matched": 0})
        delta = two["n_iters"] - one["n_iters"]
        lane["paired_tiles"] += 1
        lane["deltas"].append(delta)
        lane["stage_matched"] += int(one["stage"] == two["stage"])
        if delta > 0:
            lane["worse"] += 1
        elif delta < 0:
            lane["better"] += 1
        else:
            lane["unchanged"] += 1
    out = {}
    for lane, row in sorted(lanes.items()):
        deltas = sorted(row.pop("deltas"))
        row["median_delta"] = float(np.median(deltas)) if deltas else None
        row["mean_delta"] = (round(float(np.mean(deltas)), 3)
                             if deltas else None)
        row["max_delta"] = max(deltas) if deltas else None
        row["min_delta"] = min(deltas) if deltas else None
        # Two-sided exact sign test over the discordant pairs.
        discordant = row["worse"] + row["better"]
        row["sign_test_p"] = (
            None if not discordant
            else round(_sign_test_p(row["worse"], discordant), 6))
        out[lane] = row
    return out


def _sign_test_p(successes: int, trials: int) -> float:
    """Two-sided exact binomial sign test at p=0.5 (no scipy needed)."""
    from math import comb

    tail = min(successes, trials - successes)
    mass = sum(comb(trials, k) for k in range(tail + 1))
    return min(1.0, 2.0 * mass / float(2 ** trials))


def cmd_diff(args: argparse.Namespace) -> int:
    """Diff two patch run JSONs (the A/B unit at specimen scale)."""
    a = json.loads(Path(args.a).read_text())
    b = json.loads(Path(args.b).read_text())
    if a["name"] != b["name"]:
        raise SystemExit("diff needs two runs of the SAME specimen")
    delta = diff_outcomes(_outcome(a), _outcome(b))
    out = {
        "specimen": a["name"],
        "capture": a["capture"],
        "a": {"arm": a["arm"], "hatches": a["hatches"],
              "certificates": a["totals"]["certificates"],
              "by_stream": a["totals"]["by_stream"],
              "wall_s": a["totals"]["wall_s"],
              "verdicts": arm_verdicts(a)},
        "b": {"arm": b["arm"], "hatches": b["hatches"],
              "certificates": b["totals"]["certificates"],
              "by_stream": b["totals"]["by_stream"],
              "wall_s": b["totals"]["wall_s"],
              "verdicts": arm_verdicts(b)},
        "margin_delta_b_minus_a": margin_delta(a, b),
        **delta,
    }
    text = json.dumps(out, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


def cmd_divergence(args: argparse.Namespace) -> int:
    """Quantify what the patch tier does NOT reproduce.

    A patch run and the archived whole-capture decode are two different
    experiments on the same paper: the patch's region fit sees only the
    patch's own furniture, its scale ladder schedules a different open
    set, and its fountain can never close.  This command measures the
    gap instead of assuming it, by restricting the ARCHIVED state's own
    addresses to the specimen's tile domain and diffing.

    The number it produces bounds what the tier may claim: end-to-end
    regression and pathology development, never a capture-level uplift.
    """
    from . import state_cache

    names = args.name or [row.name for row in patch_corpus.SPECIMENS]
    rows = []
    for name in names:
        entry = patch_corpus.manifest_row(name)
        path = Path(args.run_dir) / f"{name}-{args.arm}.json"
        if not path.is_file():
            print(f"{name}: no run at {path}", file=sys.stderr)
            continue
        report = json.loads(path.read_text())
        capture_row = corpus.capture(entry["capture"])
        cache = state_cache.load(capture_row, verbose=False)
        ty0, ty1 = entry["domain_tiles_y"]
        tx0, tx1 = entry["domain_tiles_x"]
        lane_by_certificate = {}
        for level in cache.levels:
            for identity in level.certificate_ids:
                lane_by_certificate[identity] = level.lane_id
        archived = set()
        archived_lane: dict[tuple, str] = {}
        for record in cache.certificates_by_id.values():
            key = (int(record.page), int(record.tile_yx[0]),
                   int(record.tile_yx[1]), str(record.stream_id))
            if (key[0] == int(entry["page"]) and ty0 <= key[1] < ty1
                    and tx0 <= key[2] < tx1):
                archived.add(key)
                archived_lane[key] = lane_by_certificate.get(
                    record.certificate_id, "?")
        patch = {tuple(row) for row in report["addresses"]}
        both = archived & patch
        lanes = {tuple(row["address"]): row["lane_id"]
                 for row in report.get("certificate_lanes", ())}
        same_lane = (
            None if not lanes
            else sum(int(archived_lane.get(key) == lanes.get(key))
                     for key in both))
        rows.append({
            "name": name,
            "capture": entry["capture"],
            "domain_tiles": [(ty1 - ty0), (tx1 - tx0)],
            "archived_in_domain": len(archived),
            "patch": len(patch),
            "agree": len(both),
            "patch_only": len(patch - archived),
            "archived_only": len(archived - patch),
            "jaccard": (round(len(both) / len(archived | patch), 4)
                        if (archived | patch) else None),
            "same_lane_of_agreeing": same_lane,
            "patch_only_examples": sorted(patch - archived)[:8],
            "archived_only_examples": sorted(archived - patch)[:8],
        })
    out = {"schema": "color-uplift-patch-divergence-1",
           "arm": args.arm, "specimens": rows}
    text = json.dumps(out, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


def _hatch_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--arm", default="head", help="arm label")
    parser.add_argument("--name", action="append", default=[],
                        help="specimen name (repeatable; default all)")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--force-null", action="store_true",
                        help="export HOLO_COLOR_STACK_FORCE_NULL=1")
    parser.add_argument("--window-phot", default=None, metavar="PRIOR",
                        help="REFUSED at this tier (see --ctx)")
    parser.add_argument("--ctx", default=None, metavar="VARIANT",
                        help="REFUSED at this tier: a specimen run drives "
                             "the production run_receive ladder, which "
                             "takes the frozen constants the policy id "
                             "names. Sweep in `replay` or `library` mode.")
    parser.add_argument("--head-satfloor", default=None, metavar="FRACTION",
                        help="REFUSED at this tier (see --ctx)")


def _apply_hatches(args: argparse.Namespace) -> None:
    from holo.receive.color_stack import force_null_enabled

    if getattr(args, "force_null", False):
        os.environ["HOLO_COLOR_STACK_FORCE_NULL"] = "1"
    elif force_null_enabled():
        # The inverse of the export, in this tier's refuse-don't-ignore
        # style: an INHERITED hatch would turn a live specimen run into
        # the null while every artifact it writes says otherwise.
        raise SystemExit(
            "HOLO_COLOR_STACK_FORCE_NULL is set but --force-null was not "
            "requested — unset it or pass --force-null. A specimen run "
            "cannot claim the live arms while the receiver reads the null "
            "hatch.")
    if any(getattr(args, name, None)
           for name in ("window_phot", "head_satfloor", "ctx")):
        # PK-CLEAN: accepting a sweep flag here would silently run the
        # FROZEN constants under a swept label.
        raise SystemExit(
            "sweep flags (--window-phot/--head-satfloor/--ctx) are "
            "REPLAY/LIBRARY-tier only: a specimen run drives the "
            "production run_receive ladder, which has no configuration "
            "seam. Re-run in `replay` or `library` mode, or drop the flag.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.patch_runner", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    item = sub.add_parser("run")
    _hatch_flags(item)
    item.add_argument("--out", default=None)
    item.set_defaults(handler=cmd_run)

    item = sub.add_parser("pin")
    _hatch_flags(item)
    item.set_defaults(handler=cmd_pin)

    item = sub.add_parser("compare")
    _hatch_flags(item)
    item.add_argument("--out", default=None)
    item.set_defaults(handler=cmd_compare)

    item = sub.add_parser("divergence")
    item.add_argument("--arm", default="head")
    item.add_argument("--name", action="append", default=[])
    item.add_argument("--run-dir", default=str(
        corpus.work_dir("patch-runs")))
    item.add_argument("--out", default=None)
    item.set_defaults(handler=cmd_divergence)

    item = sub.add_parser("diff")
    item.add_argument("--a", required=True)
    item.add_argument("--b", required=True)
    item.add_argument("--out", default=None)
    item.set_defaults(handler=cmd_diff)

    args = parser.parse_args(argv)
    _apply_hatches(args)
    return int(args.handler(args))


if __name__ == "__main__":
    from _color_uplift_harness import patch_runner as _module

    raise SystemExit(_module.main())
