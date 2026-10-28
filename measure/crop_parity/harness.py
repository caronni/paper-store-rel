#!/usr/bin/env python
"""THE CROP HARNESS — both receivers on any crop, scored against the
full-sheet parity record.

    cd <checkout>
    PYTHONPATH=. env314t/bin/python -m measure.crop_parity.harness \\
        --volume e029                                    # every case
    PYTHONPATH=. env314t/bin/python -m measure.crop_parity.harness \\
        --volume e029 --case e029-c01 --side holo3       # inner loop

WHAT IT IS FOR: turning a full-sheet parity question (11 minutes to
1h52m of decode, tens of GiB) into a crop question (seconds to a
minute, hundreds of MB). ``cases.py`` cuts the crops; this driver runs
BOTH receivers on them, serially, and compares per-address outcomes
against ground truth and against the recorded full-sheet verdicts.

THE TWO INVOCATION SHAPES:

* **holo1** — the MAIN tree's receiver, run by the main tree's own
  interpreter, verbatim as the holo2 crop harness ran it:
  ``confetti.py decode <crop…> --scan-dpi D … --format REF --state
  <run>/holo1.state -o <run>/holo1.out --no-close --complete --mopup
  --refine --workers N``. Expected exit 2 (NOT RECOVERED) — under
  ``--no-close`` nothing ever closes; the exit is recorded, never judged.
* **holo3** — this worktree, through ``_h3run`` (its docstring says
  why not the bare CLI): ``decode <crop…> --dpi D … --format REF
  --no-close --workers N --run-dir <run>/holo3-run --out …``.

THE ADDRESS FRAME NEEDS NO RECONCILIATION, and that is a property of
the format, not an accident: a printed tile carries its own absolute
address word (C1, an 18-bit flat counter under BCH), so a receiver that
locks onto a crop recovers the same (page, ty, tx) the full sheet
would. The crop's page origin is thus never shifted by hand — it is
READ. The manifest still records each case's cell bbox and the
cell→pixel affine, which is what lets this harness CHECK the property
instead of assuming it: every certificate either side mints on a crop
must fall inside the case's cell bbox (asserted per case, reported as
``out_of_bbox``), and ``_selfcheck`` proves the same on a synthetic
crop where the full-page answer is known.

SIDECAR ADOPTION (the holo2 harness's rule, kept): every run writes
``<runs>/<case>/<side>.sidecar.json`` = {argv, crop sha, receiver tree
hash, receiver dirty sha, wall, exit, summary}. A re-invocation ADOPTS
it iff the crop sha AND the side's receiver tree AND its dirty sha all
match — so holo1 (a frozen tree) decodes each case once EVER while
holo3 re-decodes exactly when the holo3 receiver moved. The wipe is
SIDE-scoped: the two sides share a run dir. ``--fresh`` forces a
re-decode of the SELECTED side only.

WHAT A COMPARISON SAYS. Per target and control address: the crop-holo1
verdict, the crop-holo3 verdict, the recorded full-sheet verdicts, and
a bits-vs-GT check for EVERY crop-minted certificate on either side —
targets, controls and halo bystanders alike. A mismatch is a WRONG
CERTIFICATE, reported at the top, loudly; the expected count is zero.
CONTROL FLIPS ARE REPORTED, NEVER GATED (invented bars are retired).
Exit: 0 healthy, 2 wrong certificate(s), 3 ground truth refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from . import _geometry, _gt, _paths, _report, _state, _volumes

_paths.install_holo1_src()

Address = tuple[int, int, int, str]

SIDES = ("holo1", "holo3")
ADOPTION_KEYS = ("crop_sha256", "receiver_tree", "receiver_dirty_sha")

#: The per-side receiver tree the adoption predicate keys on. Scoped to
#: the RECEIVER, not the repo HEAD: every instrument edit moves HEAD, and
#: keying holo1's adoption on HEAD would drag every holo1 crop decode
#: into every holo3 iteration — precisely the loop this thing kills.
RECEIVER_TREES = {"holo1": (_paths.MAIN_TREE, "src"),
                  "holo3": (_paths.WORKTREE, "holo3")}

EXIT_OK = 0
EXIT_WRONG_CERTIFICATE = 2
EXIT_GT = 3


# --------------------------------------------------------------------
# provenance and adoption
# --------------------------------------------------------------------


def _git(tree: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=str(tree))
    return done.stdout.strip() if done.returncode == 0 else ""


def receiver_fingerprint(side: str, crop_sha256: str) -> dict[str, str]:
    tree, path = RECEIVER_TREES[side]
    diff = subprocess.run(["git", "diff", "HEAD", "--", path],
                          capture_output=True, cwd=str(tree))
    dirty = (hashlib.sha256(diff.stdout).hexdigest()
             if diff.returncode == 0 and diff.stdout else "")
    return {"crop_sha256": crop_sha256,
            "receiver_tree": _git(tree, "rev-parse", f"HEAD:{path}"),
            "receiver_dirty_sha": dirty,
            "repo_head": _git(tree, "rev-parse", "HEAD")}


def adoption_verdict(saved: Mapping[str, Any] | None,
                     current: Mapping[str, Any],
                     fresh: bool) -> tuple[bool, str]:
    """PURE adoption predicate: match, mismatch-by-name, or --fresh."""
    if fresh:
        return False, "--fresh forces a re-decode"
    if saved is None:
        return False, "no sidecar recorded"
    for key in ADOPTION_KEYS:
        if saved.get(key) != current.get(key):
            return False, (f"{key} moved (sidecar {saved.get(key)!r} vs "
                           f"current {current.get(key)!r})")
    return True, "sidecar matches (crop sha, receiver tree, dirty sha)"


def crop_set_sha(paths: Iterable[Path]) -> str:
    """One sha over the ordered crop set — the adoption key's data half."""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(_state.sha256_file(path).encode("ascii"))
    return digest.hexdigest()


# --------------------------------------------------------------------
# the two invocations
# --------------------------------------------------------------------


def side_paths(run_dir: Path, side: str) -> dict[str, Path]:
    if side == "holo1":
        return {"state": run_dir / "holo1.state",
                "out": run_dir / "holo1.out",
                "sidecar": run_dir / "holo1.sidecar.json"}
    return {"state": run_dir / "holo3-run",
            "certs": run_dir / "holo3-certs.json",
            "out": run_dir / "holo3.out",
            "sidecar": run_dir / "holo3.sidecar.json"}


def wipe_side(run_dir: Path, side: str) -> None:
    if not run_dir.is_dir():
        return
    for path in sorted(run_dir.glob(side + "*")):
        shutil.rmtree(path) if path.is_dir() else path.unlink()


def build_command(side: str, crops: list[Path], dpis: list[float],
                  format_ref: str, run_dir: Path, *, workers: int,
                  ) -> tuple[list[str], Path, dict[str, str]]:
    """(argv, cwd, extra env) for one side — the verified shapes.

    Every path is made absolute: the two sides run with DIFFERENT
    working directories (holo1 in the main tree, holo3 here), so a
    relative crop path would mean two different files.
    """
    crops = [path.resolve() for path in crops]
    run_dir = run_dir.resolve()
    paths = side_paths(run_dir, side)
    if side == "holo1":
        argv = [str(_paths.HOLO1_PYTHON), str(_paths.HOLO1_CLI), "decode"]
        argv += [str(path) for path in crops]
        for dpi in dpis:
            argv += ["--scan-dpi", str(dpi)]
        argv += ["--format", format_ref,
                 "--state", str(paths["state"]), "-o", str(paths["out"]),
                 "--no-close", "--complete", "--mopup", "--refine",
                 "--workers", str(workers)]
        return argv, _paths.MAIN_TREE, {"PYTHONPATH": str(_paths.HOLO1_SRC)}
    argv = [str(_paths.HOLO3_PYTHON), "-m", "measure.crop_parity._h3run",
            "--certs-out", str(paths["certs"]), "--",
            "decode"] + [str(path) for path in crops]
    for dpi in dpis:
        argv += ["--dpi", str(dpi)]
    argv += ["--format", format_ref, "--no-close",
             "--workers", str(workers), "--run-dir", str(paths["state"]),
             "--out", str(paths["out"])]
    return argv, _paths.WORKTREE, {"PYTHONPATH": str(_paths.WORKTREE)}


def _summary_lines(stdout: str, stderr: str) -> list[str]:
    lines = [line.rstrip() for line in (stdout + "\n" + stderr).splitlines()
             if line.strip()]
    return lines[-12:]


def run_case_side(case: Mapping[str, Any], side: str, run_dir: Path,
                  crops: list[Path], dpis: list[float], crop_sha: str, *,
                  format_ref: str, workers: int, timeout: float,
                  fresh: bool, execute: bool) -> dict[str, Any]:
    """One (case, side): adopt the sidecar, or decode fresh, serially."""
    paths = side_paths(run_dir, side)
    current = receiver_fingerprint(side, crop_sha)
    saved: dict[str, Any] | None = None
    if paths["sidecar"].is_file():
        saved = json.loads(paths["sidecar"].read_text(encoding="utf-8"))
    ok, reason = adoption_verdict(saved, current, fresh)
    if ok and not paths["state"].exists():
        ok, reason = False, ("sidecar matches but the state artifact is "
                             "absent (the decode did not survive)")
    if ok and side == "holo3" and not paths["certs"].is_file():
        ok, reason = False, "sidecar matches but the certs sidecar is absent"
    if ok:
        assert saved is not None
        print(f"crop_parity: {case['case_id']}/{side}: adopting sidecar "
              f"(decoded {saved.get('ran_at', '?')}, "
              f"{saved.get('wall_seconds', 0.0):.1f} s)", file=sys.stderr)
        return {"status": "adopted", "reason": reason, "sidecar": saved}
    if not execute:
        status = ("stale" if saved is not None or paths["state"].exists()
                  else "absent")
        return {"status": status, "reason": reason, "sidecar": None}

    wipe_side(run_dir, side)
    run_dir.mkdir(parents=True, exist_ok=True)
    argv, cwd, extra = build_command(side, crops, dpis, format_ref, run_dir,
                                     workers=workers)
    print(f"crop_parity: {case['case_id']}/{side}: decoding ({reason}) …",
          file=sys.stderr)
    environ = dict(os.environ)
    environ.update(extra)
    ran_at = time.strftime("%Y-%m-%d %H:%M:%S")
    started = time.perf_counter()
    finished = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, cwd=str(cwd), env=environ)
    wall = time.perf_counter() - started
    sidecar = {"argv": " ".join(argv), "cwd": str(cwd), **current,
               "wall_seconds": wall, "exit": finished.returncode,
               "summary": _summary_lines(finished.stdout, finished.stderr),
               "ran_at": ran_at}
    paths["sidecar"].write_text(json.dumps(sidecar, indent=2) + "\n",
                                encoding="utf-8")
    print(f"crop_parity: {case['case_id']}/{side}: exit "
          f"{finished.returncode} in {wall:.1f} s", file=sys.stderr)
    return {"status": "ran", "reason": reason, "sidecar": sidecar}


# --------------------------------------------------------------------
# reading what a side produced
# --------------------------------------------------------------------


def read_holo1(state_path: Path) -> dict[Address, np.ndarray]:
    return _state.read_state(state_path).certified_bits


def read_holo3(certs_path: Path) -> tuple[dict[Address, np.ndarray], bool]:
    record = json.loads(certs_path.read_text(encoding="utf-8"))
    bits: dict[Address, np.ndarray] = {}
    for row in record.get("certificates", ()):
        page, ty, tx, stream = row["address"]
        raw = np.frombuffer(bytes.fromhex(row["bits"]), dtype=np.uint8)
        bits[(int(page), int(ty), int(tx), str(stream))] = np.unpackbits(
            raw, bitorder="little")[:int(row["n_bits"])]
    return bits, bool(record.get("bits_available", False))


# --------------------------------------------------------------------
# the comparison (pure over loaded data)
# --------------------------------------------------------------------


def _address(entry: Iterable) -> Address:
    page, ty, tx, stream = entry
    return (int(page), int(ty), int(tx), str(stream))


#: Slack on the frame check: the crop's PIXEL box is the cell
#: rectangle's AABB plus ``PX_PAD_CELLS`` of pad, so a tile straddling
#: the (never tile-aligned) cell-rectangle edge can be fully present in
#: the crop and legitimately certify. One pad plus one tile is the
#: widest that can happen. This check is the coarse net for a frame
#: SHIFT — the exact detector is the bits-vs-GT audit, which fails on a
#: shift of even one tile.
FRAME_SLACK_CELLS = _geometry.PX_PAD_CELLS + _geometry.TILE_CELLS


def _in_cell_bbox(address: Address, cell_bbox: list[int],
                  slack_cells: int = FRAME_SLACK_CELLS) -> bool:
    """A crop certificate must address a tile inside the case's cell
    rectangle, widened by the pad the crop actually carries."""
    cx0, cy0, cx1, cy1 = cell_bbox
    _page, ty, tx, _stream = address
    return (cy0 - slack_cells <= ty * 64
            and (ty + 1) * 64 <= cy1 + slack_cells
            and cx0 - slack_cells <= tx * 64
            and (tx + 1) * 64 <= cx1 + slack_cells)


def rim_depth_cells(address: Address, cell_bbox: list[int]) -> int:
    """How deep inside the case's cell rectangle a tile sits, in cells.

    MEASURED 2026-08-29 on e029-c01 and reported because it is the
    difference between a confusing number and an interpretable one: a
    crop's control reproduction is a GRADIENT in this depth, nearly
    identical on both receivers (16/30 flipped in the outer 64 cells,
    0/2 in the deepest ring). Targets sit at halo depth by construction,
    which is the reproducing end of that gradient; the rim controls are
    context-starved, not evidence about either receiver.
    """
    cx0, cy0, cx1, cy1 = cell_bbox
    _page, ty, tx, _stream = address
    return int(min(ty * 64 - cy0, cy1 - (ty + 1) * 64,
                   tx * 64 - cx0, cx1 - (tx + 1) * 64))


def control_tally(controls: list[Address], certified: set[Address] | None,
                  cell_bbox: list[int]) -> dict[str, Any]:
    """Reported, never gated. ``None`` = the side is unavailable, and
    every count is None rather than a fake zero."""
    if certified is None:
        return {"n": len(controls), "reproduced": None, "flipped": None,
                "flipped_addresses": [], "by_rim_depth": {}}
    flipped = [a for a in controls if a not in certified]
    buckets: dict[str, list[int]] = {}
    for address in controls:
        band = rim_depth_cells(address, cell_bbox) // 64
        row = buckets.setdefault(f"{band * 64}-{band * 64 + 63}", [0, 0])
        row[1] += 1
        if address in flipped:
            row[0] += 1
    return {"n": len(controls), "reproduced": len(controls) - len(flipped),
            "flipped": len(flipped),
            "flipped_addresses": [list(a) for a in flipped],
            "by_rim_depth": {key: {"flipped": value[0], "n": value[1]}
                             for key, value in sorted(
                                 buckets.items(),
                                 key=lambda item: int(
                                     item[0].split("-")[0]))}}


def compare_case(case: Mapping[str, Any], truth: _gt.GroundTruth,
                 runs: Mapping[str, Mapping[str, Any]],
                 data: Mapping[str, dict[Address, np.ndarray] | None],
                 bits_available: Mapping[str, bool]) -> dict[str, Any]:
    certs = {side: (set(rows) if rows is not None else None)
             for side, rows in data.items()}
    wrong: list[dict[str, Any]] = []
    checked = {side: 0 for side in SIDES}
    outside: list[dict[str, Any]] = []
    for side in SIDES:
        rows = data.get(side)
        if rows is None:
            continue
        for address, bits in sorted(rows.items()):
            if not bits_available.get(side, True):
                continue
            match, n_bad = _gt.check_bits(truth, address, bits)
            checked[side] += 1
            if not match:
                wrong.append({"case_id": case["case_id"], "side": side,
                              "address": list(address),
                              "n_bit_mismatch": n_bad})
        for address in sorted(rows):
            if not _in_cell_bbox(address, case["cell_bbox"]):
                outside.append({"case_id": case["case_id"], "side": side,
                                "address": list(address)})

    rows_out: list[dict[str, Any]] = []
    for target in case["targets"]:
        address = _address(target["address"])
        verdicts = {side: ((address in certs[side])
                           if certs[side] is not None else None)
                    for side in SIDES}
        rows_out.append({
            "address": list(address), "kind": "target",
            "classes": list(target["classes"]),
            "full_sheet": dict(target["full_sheet"]),
            "crop": {side: {"available": data.get(side) is not None,
                            "certified": verdicts[side]}
                     for side in SIDES},
            "agree": (None if None in verdicts.values()
                      else verdicts["holo1"] == verdicts["holo3"]),
            "reproduces_full_sheet": {
                side: (None if verdicts[side] is None else
                       verdicts[side] == (target["full_sheet"][side]
                                          == "certified"))
                for side in SIDES}})

    controls = [_address(entry) for entry in case["controls"]]
    return {
        "case_id": case["case_id"],
        "cell_bbox": list(case["cell_bbox"]),
        "runs": {side: {"status": run["status"], "reason": run["reason"],
                        "sidecar": run.get("sidecar")}
                 for side, run in runs.items()},
        "n_certificates": {side: (len(certs[side])
                                  if certs[side] is not None else None)
                           for side in SIDES},
        "bits_available": dict(bits_available),
        "targets": rows_out,
        "controls": {side: control_tally(controls, certs[side],
                                         list(case["cell_bbox"]))
                     for side in SIDES},
        "wrong_certificates": wrong,
        "out_of_bbox": outside,
        "checked_certificates": checked,
    }


def aggregate(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    per_class: dict[str, dict[str, Any]] = {}
    wrong: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    walls = {"executed_wall_seconds": {side: 0.0 for side in SIDES},
             "runs_executed": 0, "runs_adopted": 0,
             "adopted_wall_seconds": 0.0}
    agree = {"agree": 0, "disagree": 0, "undetermined": 0}
    for case in cases:
        wrong.extend(case["wrong_certificates"])
        outside.extend(case["out_of_bbox"])
        for side, run in case["runs"].items():
            sidecar = run.get("sidecar")
            if sidecar is None:
                continue
            wall = float(sidecar.get("wall_seconds", 0.0))
            if run["status"] == "ran":
                walls["executed_wall_seconds"][side] += wall
                walls["runs_executed"] += 1
            elif run["status"] == "adopted":
                walls["adopted_wall_seconds"] += wall
                walls["runs_adopted"] += 1
        for row in case["targets"]:
            for name in row["classes"]:
                bucket = per_class.setdefault(
                    name, {"n": 0, "holo1_crop_certified": 0,
                           "holo3_crop_certified": 0,
                           "holo1_compared": 0, "holo3_compared": 0,
                           "reproduces_full_sheet": {"holo1": 0,
                                                     "holo3": 0}})
                bucket["n"] += 1
                for side in SIDES:
                    crop = row["crop"][side]
                    if not crop["available"]:
                        continue
                    bucket[f"{side}_compared"] += 1
                    bucket[f"{side}_crop_certified"] += bool(
                        crop["certified"])
                    if row["reproduces_full_sheet"][side]:
                        bucket["reproduces_full_sheet"][side] += 1
            if row["agree"] is None:
                agree["undetermined"] += 1
            elif row["agree"]:
                agree["agree"] += 1
            else:
                agree["disagree"] += 1
    return {"per_class": per_class, "wrong_certificates": wrong,
            "out_of_bbox": outside, "walls": walls, "agreement": agree}


# --------------------------------------------------------------------
# driving one volume
# --------------------------------------------------------------------


def process_volume(manifest_path: Path, *, case_ids: set[str] | None,
                   sides: tuple[str, ...], fresh: bool, workers: int,
                   timeout: float, harness: Mapping[str, Any],
                   ) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    volume = _volumes.VOLUMES_BY_KEY[manifest["volume"]]
    payload = _gt.load_payload(volume.payload, volume.payload_sha256,
                               volume.payload_bytes)
    truth = _gt.reconstruct(manifest["format_ref"], payload)
    archived = _state.read_state(volume.holo1_state)
    validated = _gt.validate_against_state(
        truth, archived.certified_bits,
        f"{volume.key} archived holo1 state {volume.holo1_state}")
    del archived

    dpis = [float(capture["dpi"]) for capture in manifest["captures"]]
    chosen = [case for case in manifest["cases"]
              if case_ids is None or case["case_id"] in case_ids]
    finished: list[dict[str, Any]] = []
    for case in chosen:
        crops = [manifest_path.parent / crop["crop_file"]
                 for crop in case["crops"]]
        missing = [str(path) for path in crops if not path.is_file()]
        if missing:
            print(f"crop_parity: {case['case_id']}: crop file(s) absent "
                  f"{missing} — skipped", file=sys.stderr)
            continue
        crop_sha = crop_set_sha(crops)
        run_dir = manifest_path.parent / "runs" / case["case_id"]
        runs: dict[str, dict[str, Any]] = {}
        for side in SIDES:
            runs[side] = run_case_side(
                case, side, run_dir, crops, dpis, crop_sha,
                format_ref=manifest["format_ref"], workers=workers,
                timeout=timeout, fresh=fresh and side in sides,
                execute=side in sides)
        data: dict[str, dict[Address, np.ndarray] | None] = {}
        bits_available = {"holo1": True, "holo3": True}
        holo1_paths = side_paths(run_dir, "holo1")
        holo3_paths = side_paths(run_dir, "holo3")
        data["holo1"] = (
            read_holo1(holo1_paths["state"])
            if runs["holo1"]["status"] in ("ran", "adopted")
            and holo1_paths["state"].is_file() else None)
        if (runs["holo3"]["status"] in ("ran", "adopted")
                and holo3_paths["certs"].is_file()):
            rows, available = read_holo3(holo3_paths["certs"])
            data["holo3"] = rows
            bits_available["holo3"] = available
        else:
            data["holo3"] = None
        result = compare_case(case, truth, runs, data, bits_available)
        result["crops"] = [str(path) for path in crops]
        result["crop_sha256"] = crop_sha
        finished.append(result)

    return {
        "volume": volume.key, "label": volume.label,
        "colour": volume.colour,
        "manifest": str(manifest_path),
        "format_ref": manifest["format_ref"],
        "classes": manifest["classes"],
        "gap_counts": manifest["gap_counts"],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "harness": dict(harness),
        "gt": {"payload_sha256": truth.payload_sha256,
               "validated_certificates": validated,
               "rule": "every certificate in the archived holo1 state "
                       "matches the re-encoded golden payload exactly"},
        "cases": finished,
        "aggregates": aggregate(finished),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--volume", action="append", default=[],
                        help="a declared volume key, or 'all'")
    parser.add_argument("--case", action="append", default=[],
                        help="case_id to run (repeatable; default all)")
    parser.add_argument("--side", choices=("holo1", "holo3", "both"),
                        default="both",
                        help="which receiver(s) to DECODE; the other "
                             "side's standing sidecars still render")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore matching sidecars and re-decode")
    parser.add_argument("--workers", type=int, default=1,
                        help="worker threads per decode (default 1 — one "
                             "decode at a time, memory light)")
    parser.add_argument("--timeout", type=float, default=3600.0,
                        help="seconds per subprocess decode")
    parser.add_argument("--out-root", type=Path, default=_paths.SCRATCH)
    args = parser.parse_args(argv)

    _paths.refuse_if_absent()
    volumes = _volumes.resolve_volumes(args.volume)
    manifests = [args.out_root / volume.key / "cases.json"
                 for volume in volumes]
    present = [path for path in manifests if path.is_file()]
    for path in manifests:
        if not path.is_file():
            print(f"crop_parity: manifest {path} absent — run "
                  f"measure.crop_parity.cases first", file=sys.stderr)
    if not present:
        raise SystemExit("crop_parity: no manifest to run")

    case_ids = set(args.case) or None
    sides = SIDES if args.side == "both" else (args.side,)
    harness = {"argv": " ".join(sys.argv[1:] if argv is None else argv),
               "worktree_head": _git(_paths.WORKTREE, "rev-parse", "HEAD"),
               "holo3_tree": _git(_paths.WORKTREE, "rev-parse",
                                  "HEAD:holo3"),
               "holo1_tree": _git(_paths.MAIN_TREE, "rev-parse", "HEAD:src")}

    n_wrong = 0
    for path in present:
        try:
            results = process_volume(
                path, case_ids=case_ids, sides=sides, fresh=args.fresh,
                workers=args.workers, timeout=args.timeout,
                harness=harness)
        except _gt.GTValidationError as error:
            print(f"crop_parity: {error}", file=sys.stderr)
            return EXIT_GT
        n_wrong += len(results["aggregates"]["wrong_certificates"])
        (path.parent / "results.json").write_text(
            json.dumps(results, indent=1, default=str) + "\n",
            encoding="utf-8")
        text = _report.render(results)
        (path.parent / f"crop-battery-{results['volume']}.md").write_text(
            text, encoding="utf-8")
        print(text)
        print(f"crop_parity: wrote {path.parent}/results.json and "
              f"crop-battery-{results['volume']}.md", file=sys.stderr)
    if n_wrong:
        print(f"crop_parity: {n_wrong} WRONG CERTIFICATE(S) — see the "
              f"report top", file=sys.stderr)
        return EXIT_WRONG_CERTIFICATE
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
