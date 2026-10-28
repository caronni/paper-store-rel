#!/usr/bin/env python
"""THE CROP HARNESS — both receivers on any crop, scored against the
full-sheet record (HANDOFF-CROP Deliverable B).

    env/bin/python holo2/measure/crop_harness.py                # both sheets
    env/bin/python holo2/measure/crop_harness.py \\
        --manifest scratch/holo2-catchup/crops/e029/cases.json \\
        --case e029-c01 --side h2                               # smoke scale

NOT A TEST and not collectable as one — the same standing as
``parity_k.py`` and every other by-path driver here
(``holo2/measure/README.md``). Its pure logic (the sidecar adoption
predicate, the GT-validation refusal path, the rank vocabulary, the
uplift/control classification) is pinned in
``tests/holo2_oracles/test_oracle_crop_harness.py`` — there and not
under ``holo2/tests`` because this module imports ``holo`` (the
firewall exempts exactly that directory).

WHAT IT IS FOR (HANDOFF-CROP, user intent 2026-08-28): *"the point here
is to go from 13h runs to minutes instead"* / *"or seconds."* Deliverable
A (``crop_cases.py``) cuts crops around every tile of interest out of the
two real K captures and writes a manifest; THIS driver runs BOTH
receivers fresh on any crop, serially, and compares per-tile outcomes and
intermediates against the recorded full-sheet verdicts. The residue lines
(tx=0, F3–F10, toolbox) iterate here, never on full sheets. No full-sheet
decode can be launched from this file — it decodes only the crop files a
manifest names.

THE TWO INVOCATION SHAPES (verified against both ``--help`` texts,
2026-08-28; v1 HAS ``--workers``, so a moderate value is passed):

* v1:  ``confetti.py decode <crop.tiff> --scan-dpi <dpi> --format <ref>
  --state <dir>/v1.state -o <dir>/v1.out --no-close --complete --mopup
  --refine --workers 4`` — the archived full harvests carry
  ordinary+mopup+refine lane kinds, so crops run the same families.
  ``-o`` is refused if it exists, which is one of the reasons a fresh
  decode always starts from a wiped side (below). Expected exit is 2
  (NOT RECOVERED) — under ``--no-close`` nothing ever closes; the exit
  is recorded, never judged.
* h2:  ``confetti2.py --scan <crop.tiff> --dpi <dpi> --format <ref>
  --state-dir <dir>/h2-state --output <dir>/h2.out --no-close
  --workers 4`` — expected exit ``EXIT_OPEN`` = 2, same note.

Execution is SERIAL across cases and sides (memory doctrine: one decode
at a time), wall recorded per run. The h2 arm gets a non-default
``--diag-port`` (8061) so a live production decode's diag (8024/8025)
is never contended.

SIDECAR ADOPTION (the ``parity_k`` rule, sharpened for the inner loop).
Every run writes ``<runs>/<case>/<side>.sidecar.json`` = {argv, crop
sha256, receiver tree hash, receiver dirty-diff sha256, repo HEAD,
wall_seconds, exit, summary}. A re-invocation ADOPTS the sidecar iff the
crop sha AND the tree hash AND the dirty sha all match the current tree;
otherwise it wipes that SIDE's artifacts in the run dir and decodes
fresh. ``--fresh`` forces a re-decode. ONE SHARPENING over the handoff's
letter, in service of its stated intent: the tree component is the
SIDE'S RECEIVER TREE OBJECT (``git rev-parse HEAD:src`` for v1,
``HEAD:holo2/src`` for h2) and the dirty sha is scoped to the same path,
not the repo HEAD — because the handoff's own practical effect ("v1
(frozen tree) decodes each case once EVER; h2 re-decodes exactly when
the receiver changed") is unachievable off the commit id: every holo2
edit moves HEAD, and keying v1's adoption on HEAD would drag ~30 v1
crop decodes into every h2 iteration, which is precisely the loop this
instrument exists to kill. The repo HEAD is still recorded in the
sidecar, informationally. The wipe is SIDE-scoped for the same reason:
the two sides share ``runs/<case_id>/`` and wiping the whole dir on an
h2 mismatch would destroy v1's adopted state. (A caveat the fingerprint
inherits from ``git diff``: an UNTRACKED file under a receiver tree does
not move the dirty sha. New receiver code is `git add`ed in this
workflow before it is trusted, so the gap is recorded, not defended.)
Adoption additionally requires the side's state artifact to exist — a
sidecar whose decode crashed before writing a state is re-run, not
adopted.

GROUND TRUTH lives next door in ``crop_harness_gt.py`` (the second
1,000-line seam; the first carved the report): the golden payload is
re-encoded through src/holo's generation path into per-tile user bits
for the WHOLE identity, and validated against every v1-certified tile
on BOTH archived sheets before any comparison — refusal is exit 3. That
module's docstring carries the trap analysis (make_data drift,
slot-raster ≠ codeword order) and the measured validation record.

WHAT A COMPARISON SAYS. Per target and control tile: the crop-v1
verdict, the crop-h2 rank (``tile_differential``'s vocabulary), the
full-sheet verdicts from the manifest, and a certificate-bits-vs-GT
check for EVERY crop-minted certificate on either side — targets,
controls and halo bystanders alike. A mismatch is a WRONG CERTIFICATE,
reported at the top of the report, loudly; the expected count is zero,
and any other count is one of this harness's two nonzero exits (2).
CONTROL FLIPS ARE REPORTED, NEVER GATED (lead ruling in HANDOFF-CROP:
invented bars are retired; report, we interpret). A crop-h2 certificate
on a ``still_missing_v2`` or ``neither`` target is an UPLIFT row,
flagged distinctly and GT-checked; the symmetric v1-direction flag
exists for ``v1_missing``/``neither`` targets. Absence of uplift is
data, not failure: the exit code reflects harness health only —
0 healthy, 2 wrong certificate(s), 3 GT validation failure.

OUTPUTS, per sheet, beside the manifest: ``crop-battery-<sheet>.md``
(rendered by ``crop_harness_report.py`` — the ``parity_k_report`` seam,
taken up front) and a machine ``results.json`` carrying the same dict
the renderer consumed.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

# Self-locating, like every other by-path driver here (parity_k.py's own
# reason): neither package is pip-installed, and an operator running this
# by path should not also have to spell a PYTHONPATH.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE, _ROOT / "src", _ROOT / "holo2" / "src"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

import numpy as np                                              # noqa: E402

import crop_harness_gt                                          # noqa: E402
import crop_harness_report                                      # noqa: E402
import parity_k                                                 # noqa: E402
import tile_differential                                        # noqa: E402

from holo.format.resolve import resolve_format_ref              # noqa: E402
from holo.receive.session import load_session                   # noqa: E402

from holo2.solve import parse_tile_key                          # noqa: E402

# The GT half (reconstruction + the validation gate: GTValidationError,
# GroundTruth, load_golden_payload, reconstruct_gt, v1_certified_bits,
# validate_gt_bits, validate_gt_against_archives, and the
# GOLDEN_K_SHA/GOLDEN_K_BYTES/GOLDEN_PAYLOAD_CANDIDATES/ARCHIVED_V1_STATES
# constants) lives in crop_harness_gt.py — the second 1,000-line seam
# (its docstring: the dependency arrow runs harness -> gt, never the
# reverse). Referenced below as ``crop_harness_gt.*``, not re-defined —
# one copy.
TileKey = tuple[int, int, int]     # (page, ty, tx) — tile_differential's

#: The four target classes (HANDOFF-CROP "Case classes") — disjoint
#: within a sheet by construction; `control` is per-crop, not a class.
TARGET_CLASSES = ("flipped", "still_missing_v2", "v1_missing", "neither")

SIDES = ("v1", "h2")

#: The per-side receiver tree, the adoption predicate's tree component
#: (module docstring: the sharpening and its reason).
RECEIVER_TREE_PATHS = {"v1": "src", "h2": "holo2/src"}

#: The three sidecar fields the adoption predicate compares.
ADOPTION_KEYS = ("crop_sha256", "receiver_tree", "receiver_dirty_sha")

EXIT_OK = 0
EXIT_WRONG_CERTIFICATE = 2
EXIT_GT_VALIDATION = 3


# --------------------------------------------------------------------
# vocabulary (manifest full_sheet fields -> booleans, no guessing)
# --------------------------------------------------------------------

#: ``full_sheet.h2`` uses tile_differential's rank vocabulary; the
#: manifest schema example spells it lowercase-underscore
#: ("attempted_failed") while ``TileState`` and the differential reports
#: spell it upper ("ATTEMPTED", "ATTEMPTED-FAILED"). All three spellings
#: of each rank normalize to one row here; an UNKNOWN rank raises rather
#: than being guessed at (memory: no invented defaults).
_H2_RANK_CERTIFIED: dict[str, bool] = {
    "unknown": False, "never_addressed": False,
    "addressed": False, "addressed_not_attempted": False,
    "attempted": False, "attempted_failed": False,
    "certified": True,
}


def h2_rank_certified(rank: str) -> bool:
    key = str(rank).strip().lower().replace("-", "_")
    if key not in _H2_RANK_CERTIFIED:
        raise ValueError(
            f"unknown full_sheet.h2 rank {rank!r}; known: "
            f"{sorted(_H2_RANK_CERTIFIED)}")
    return _H2_RANK_CERTIFIED[key]


def v1_verdict_certified(verdict: str) -> bool:
    key = str(verdict).strip().lower()
    if key not in ("certified", "uncertified"):
        raise ValueError(f"unknown full_sheet.v1 verdict {verdict!r}; "
                         f"known: ['certified', 'uncertified']")
    return key == "certified"


# --------------------------------------------------------------------
# sidecar adoption
# --------------------------------------------------------------------


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=str(_ROOT))
    return done.stdout.strip() if done.returncode == 0 else ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def receiver_fingerprint(side: str, crop_sha256: str) -> dict[str, str]:
    """The current tree's answer to the adoption predicate, per side."""
    tree_path = RECEIVER_TREE_PATHS[side]
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--", tree_path],
        capture_output=True, cwd=str(_ROOT))
    dirty = (hashlib.sha256(diff.stdout).hexdigest()
             if diff.returncode == 0 and diff.stdout else "")
    return {"crop_sha256": crop_sha256,
            "receiver_tree": _git("rev-parse", f"HEAD:{tree_path}"),
            "receiver_dirty_sha": dirty,
            "repo_head": _git("rev-parse", "HEAD")}


def adoption_verdict(saved: Mapping[str, Any] | None,
                     current: Mapping[str, Any],
                     fresh: bool) -> tuple[bool, str]:
    """PURE adoption predicate (pinned): match, mismatch-by-name, --fresh."""
    if fresh:
        return False, "--fresh forces a re-decode"
    if saved is None:
        return False, "no sidecar recorded"
    for key in ADOPTION_KEYS:
        if saved.get(key) != current.get(key):
            return False, (f"{key} moved (sidecar {saved.get(key)!r} vs "
                           f"current {current.get(key)!r})")
    return True, "sidecar matches (crop sha, receiver tree, dirty sha)"


# --------------------------------------------------------------------
# the runner
# --------------------------------------------------------------------


def side_paths(run_dir: Path, side: str) -> dict[str, Path]:
    if side == "v1":
        return {"state": run_dir / "v1.state", "out": run_dir / "v1.out",
                "sidecar": run_dir / "v1.sidecar.json"}
    return {"state": run_dir / "h2-state", "out": run_dir / "h2.out",
            "sidecar": run_dir / "h2.sidecar.json"}


def wipe_side(run_dir: Path, side: str) -> None:
    """Remove ONE side's artifacts (side-scoped — module docstring)."""
    prefix = "v1" if side == "v1" else "h2"
    if not run_dir.is_dir():
        return
    for path in sorted(run_dir.glob(prefix + "*")):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def build_argv(side: str, crop_path: Path, scan_dpi: float,
               format_ref: str, run_dir: Path, *, workers: int,
               diag_port: int) -> list[str]:
    """The two verified invocation shapes, verbatim (module docstring)."""
    paths = side_paths(run_dir, side)
    if side == "v1":
        return [sys.executable, str(_ROOT / "confetti.py"), "decode",
                str(crop_path), "--scan-dpi", str(scan_dpi),
                "--format", format_ref, "--state", str(paths["state"]),
                "-o", str(paths["out"]), "--no-close", "--complete",
                "--mopup", "--refine", "--workers", str(workers)]
    return [sys.executable, str(_ROOT / "confetti2.py"),
            "--scan", str(crop_path), "--dpi", str(scan_dpi),
            "--format", format_ref, "--state-dir", str(paths["state"]),
            "--output", str(paths["out"]), "--no-close",
            "--workers", str(workers), "--diag-port", str(diag_port)]


def _summary_lines(side: str, stdout: str, stderr: str) -> list[str]:
    """The sidecar's epilogue/summary field. h2's is the CLI's own
    six-row epilogue via ``parity_k._epilogue_lines`` (one implementation
    in the tree, not two); v1's epilogue shape is not pinned anywhere, so
    the last non-empty lines are recorded verbatim."""
    if side == "h2":
        return list(parity_k._epilogue_lines(stdout, stderr))
    lines = [line.rstrip() for line in (stdout + "\n" + stderr).splitlines()
             if line.strip()]
    return lines[-12:]


def run_case_side(case: Mapping[str, Any], side: str, run_dir: Path,
                  crop_path: Path, crop_sha256: str, *,
                  scan_dpi: float, format_ref: str, workers: int,
                  diag_port: int, timeout: float, fresh: bool,
                  execute: bool) -> dict[str, Any]:
    """One (case, side): adopt the sidecar or decode fresh, serially.

    ``execute=False`` (the side was not selected by ``--side``) never
    decodes: it adopts a matching sidecar or reports the side absent /
    stale, so an h2-only inner-loop iteration still renders v1 columns
    from v1's standing decodes without ever re-running them.
    """
    paths = side_paths(run_dir, side)
    current = receiver_fingerprint(side, crop_sha256)
    saved: dict[str, Any] | None = None
    if paths["sidecar"].is_file():
        saved = json.loads(paths["sidecar"].read_text(encoding="utf-8"))
    ok, reason = adoption_verdict(saved, current, fresh)
    if ok and not paths["state"].exists():
        ok, reason = False, "sidecar matches but the state artifact is " \
                            "absent (the decode did not survive)"
    if ok:
        assert saved is not None
        print(f"crop_harness: {case['case_id']}/{side}: adopting sidecar "
              f"(decoded {saved.get('ran_at', '?')}, "
              f"{saved.get('wall_seconds', 0.0):.1f} s)", file=sys.stderr)
        return {"status": "adopted", "reason": reason, "sidecar": saved}
    if not execute:
        status = "stale" if saved is not None or paths["state"].exists() \
            else "absent"
        return {"status": status, "reason": reason, "sidecar": None}

    wipe_side(run_dir, side)
    run_dir.mkdir(parents=True, exist_ok=True)
    argv = build_argv(side, crop_path, scan_dpi, format_ref, run_dir,
                      workers=workers, diag_port=diag_port)
    print(f"crop_harness: {case['case_id']}/{side}: decoding "
          f"({reason}) …", file=sys.stderr)
    ran_at = time.strftime("%Y-%m-%d %H:%M:%S")
    started = time.perf_counter()
    finished = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, cwd=str(_ROOT))
    wall = time.perf_counter() - started
    sidecar = {
        "argv": " ".join(argv[1:]),
        **current,
        "wall_seconds": wall,
        "exit": finished.returncode,
        "summary": _summary_lines(side, finished.stdout, finished.stderr),
        "ran_at": ran_at,
    }
    paths["sidecar"].write_text(json.dumps(sidecar, indent=2) + "\n",
                                encoding="utf-8")
    print(f"crop_harness: {case['case_id']}/{side}: exit "
          f"{finished.returncode} in {wall:.1f} s", file=sys.stderr)
    return {"status": "ran", "reason": reason, "sidecar": sidecar}


# --------------------------------------------------------------------
# reading the crop states (both via tile_differential's loaders)
# --------------------------------------------------------------------


def read_crop_v1(state_path: Path, tiles_yx: tuple[int, int],
                 tile_user_bits: int) -> dict[str, Any]:
    """Certified bits + retained-evidence summaries of a crop v1 state.

    ``defer_fountain_validation=True`` is what the v1 CLI itself passes
    when reading a ``--no-close`` state; the crop states are OPEN by
    construction.
    """
    state = load_session(state_path, defer_fountain_validation=True)
    index = tile_differential.build_v1_index(state, tiles_yx)
    blocks = {key: [dataclasses.asdict(fact) for fact in facts]
              for key, facts in index.blocks.items()}
    return {"certified_bits": crop_harness_gt.v1_certified_bits(
                state, tile_user_bits),
            "blocks": blocks}


def read_crop_h2(state_dir: Path,
                 facts_tiles: Iterable[TileKey]) -> dict[str, Any]:
    """Certified bits + per-tile facts of a crop h2 state, one store open.

    Certified user bits are the record's own content: ``bits_ref`` holds
    the fountain symbol, ``metadata_bit`` the LDPC metadata bit —
    together exactly the GT tile's user-bit vector.
    """
    certified: dict[TileKey, np.ndarray] = {}
    facts: dict[TileKey, dict[str, Any]] = {}
    with tile_differential.open_h2_store(state_dir) as store:
        h2 = tile_differential.build_h2_index(store)
        for key in h2.store_index.certified_tiles:
            page, ty, tx, stream = parse_tile_key(key)
            if stream != "main":
                continue
            record = h2.store_index.tiles[key]
            symbol = np.asarray(store.read_array(record.bits_ref),
                                np.uint8).ravel()
            certified[(page, ty, tx)] = np.concatenate(
                ([np.uint8(record.metadata_bit)], symbol))
        for tile in facts_tiles:
            page, ty, tx = tile
            state, spends, poses = tile_differential.h2_tile_facts(
                store, h2, page, ty, tx, "main")
            facts[tile] = {
                "rank": state.name,
                "spends": [dataclasses.asdict(spend) for spend in spends],
                "poses": [dataclasses.asdict(pose) for pose in poses],
            }
    return {"certified_bits": certified, "facts": facts}


# --------------------------------------------------------------------
# the comparison (pure over loaded data — the pinned pieces)
# --------------------------------------------------------------------


def target_flags(classes: Iterable[str], v1_certified: bool | None,
                 h2_certified: bool | None) -> list[str]:
    """PURE flag rule (pinned): UPLIFT_H2 on a crop-h2 certificate over a
    ``still_missing_v2``/``neither`` target (the handoff's uplift rows);
    UPLIFT_V1 is the symmetric v1-direction observation."""
    names = set(classes)
    flags: list[str] = []
    if h2_certified and names & {"still_missing_v2", "neither"}:
        flags.append("UPLIFT_H2")
    if v1_certified and names & {"v1_missing", "neither"}:
        flags.append("UPLIFT_V1")
    return flags


def control_agreement(controls: Iterable[TileKey],
                      certified: set[TileKey] | None) -> dict[str, Any]:
    """PURE control tally (pinned): reported, never gated. ``None``
    certified-set = the side is unavailable, and every count is None
    rather than a fake zero (parity_k's three-valued lesson)."""
    tiles = list(controls)
    if certified is None:
        return {"n": len(tiles), "reproduced": None, "flipped": None,
                "flipped_tiles": []}
    flipped = [list(tile) for tile in tiles if tile not in certified]
    return {"n": len(tiles), "reproduced": len(tiles) - len(flipped),
            "flipped": len(flipped), "flipped_tiles": flipped}


def _gt_check(gt: crop_harness_gt.GroundTruth, tile: TileKey,
              bits: np.ndarray) -> tuple[bool, int]:
    expected = gt.user_bits.get(tile)
    if expected is None or bits.shape != expected.shape:
        return False, -1
    n_bad = int(np.count_nonzero(bits != expected))
    return n_bad == 0, n_bad


def _manifest_tile(entry: Any) -> TileKey:
    """Manifest tiles are [a, b] in the pinned convention (page 0 —
    both sheets are single-page volumes; a 3-tuple carries its page)."""
    parts = [int(v) for v in entry]
    if len(parts) == 2:
        return (0, parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2])
    raise ValueError(f"manifest tile {entry!r} is neither [a, b] nor "
                     f"[page, a, b]")


def compare_case(case: Mapping[str, Any], gt: crop_harness_gt.GroundTruth,
                 runs: Mapping[str, Mapping[str, Any]],
                 v1_data: Mapping[str, Any] | None,
                 h2_data: Mapping[str, Any] | None) -> dict[str, Any]:
    """One case's rows: targets, controls, wrong certificates, uplift."""
    v1_certs = (set(v1_data["certified_bits"]) if v1_data is not None
                else None)
    h2_certs = (set(h2_data["certified_bits"]) if h2_data is not None
                else None)

    wrong: list[dict[str, Any]] = []
    checked = {"v1": 0, "h2": 0}
    for side, data in (("v1", v1_data), ("h2", h2_data)):
        if data is None:
            continue
        for tile, bits in sorted(data["certified_bits"].items()):
            match, n_bad = _gt_check(gt, tile, bits)
            checked[side] += 1
            if not match:
                wrong.append({"case_id": case["case_id"], "side": side,
                              "tile": list(tile), "n_bit_mismatch": n_bad})

    rows: list[dict[str, Any]] = []
    uplift: list[dict[str, Any]] = []
    target_tiles: set[TileKey] = set()
    for target in case.get("targets", ()):
        tile = _manifest_tile(target["tile"])
        target_tiles.add(tile)
        classes = list(target.get("classes", ()))
        full = target.get("full_sheet", {})
        v1_cert = (tile in v1_certs) if v1_certs is not None else None
        h2_cert = (tile in h2_certs) if h2_certs is not None else None
        row: dict[str, Any] = {
            "tile": list(tile), "kind": "target", "classes": classes,
            "full_sheet": dict(full),
            "crop": {
                "v1": {"available": v1_data is not None,
                       "certified": v1_cert},
                "h2": {"available": h2_data is not None,
                       "certified": h2_cert},
            },
            "flags": target_flags(classes, v1_cert, h2_cert),
        }
        if h2_data is not None:
            facts = h2_data["facts"].get(tile)
            if facts is not None:
                row["crop"]["h2"]["rank"] = facts["rank"]
                if not h2_cert:
                    row["crop"]["h2"]["spends"] = facts["spends"]
                    row["crop"]["h2"]["poses"] = facts["poses"]
        if v1_data is not None and not v1_cert:
            row["crop"]["v1"]["blocks"] = v1_data["blocks"].get(tile, [])
        for flag in row["flags"]:
            side = "h2" if flag == "UPLIFT_H2" else "v1"
            data = h2_data if side == "h2" else v1_data
            assert data is not None
            gt_ok, _ = _gt_check(gt, tile, data["certified_bits"][tile])
            uplift.append({"case_id": case["case_id"], "tile": list(tile),
                           "classes": classes, "side": side,
                           "gt_ok": gt_ok})
        rows.append(row)

    control_tiles = [_manifest_tile(entry)
                     for entry in case.get("controls", ())]
    for tile in control_tiles:
        rows.append({
            "tile": list(tile), "kind": "control", "classes": [],
            "full_sheet": {"v1": "certified", "h2": "certified"},
            "crop": {
                "v1": {"available": v1_data is not None,
                       "certified": (tile in v1_certs)
                       if v1_certs is not None else None},
                "h2": {"available": h2_data is not None,
                       "certified": (tile in h2_certs)
                       if h2_certs is not None else None},
            },
            "flags": [],
        })

    return {
        "case_id": case["case_id"],
        "runs": {side: {"status": run["status"], "reason": run["reason"],
                        "sidecar": run.get("sidecar")}
                 for side, run in runs.items()},
        "tiles": rows,
        "controls": {
            side: control_agreement(
                control_tiles, v1_certs if side == "v1" else h2_certs)
            for side in SIDES},
        "wrong_certificates": wrong,
        "uplift": uplift,
        "checked_certificates": checked,
    }


def aggregate_cases(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The per-class × side table + battery totals, over finished cases."""
    per_class: dict[str, dict[str, Any]] = {
        name: {"n": 0,
               "v1": {"compared": 0, "crop_certified": 0,
                      "full_sheet_certified": 0},
               "h2": {"compared": 0, "crop_certified": 0,
                      "full_sheet_certified": 0}}
        for name in TARGET_CLASSES}
    wrong: list[dict[str, Any]] = []
    uplift: list[dict[str, Any]] = []
    walls = {"executed_wall_seconds": 0.0, "adopted_wall_seconds": 0.0,
             "runs_executed": 0, "runs_adopted": 0}
    for case in cases:
        wrong.extend(case["wrong_certificates"])
        uplift.extend(case["uplift"])
        for run in case["runs"].values():
            sidecar = run.get("sidecar")
            if sidecar is None:
                continue
            wall = float(sidecar.get("wall_seconds", 0.0))
            if run["status"] == "ran":
                walls["executed_wall_seconds"] += wall
                walls["runs_executed"] += 1
            elif run["status"] == "adopted":
                walls["adopted_wall_seconds"] += wall
                walls["runs_adopted"] += 1
        for row in case["tiles"]:
            if row["kind"] != "target":
                continue
            full = row["full_sheet"]
            for name in row["classes"]:
                bucket = per_class[name]
                bucket["n"] += 1
                for side in SIDES:
                    crop = row["crop"][side]
                    if not crop["available"]:
                        continue
                    bucket[side]["compared"] += 1
                    bucket[side]["crop_certified"] += bool(crop["certified"])
                    if side == "v1":
                        expected = v1_verdict_certified(full.get(
                            "v1", "uncertified"))
                    else:
                        expected = h2_rank_certified(full.get(
                            "h2", "never_addressed"))
                    bucket[side]["full_sheet_certified"] += expected
    return {"per_class": per_class, "wrong_certificates": wrong,
            "uplift": uplift, "walls": walls}


# --------------------------------------------------------------------
# manifests and the CLI
# --------------------------------------------------------------------

DEFAULT_MANIFESTS = (
    _ROOT / "scratch/holo2-catchup/crops/e029/cases.json",
    _ROOT / "scratch/holo2-catchup/crops/xerox/cases.json",
)


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for field in ("sheet", "format_ref", "scan_dpi", "cases"):
        if field not in manifest:
            raise SystemExit(f"crop_harness: manifest {path} lacks "
                             f"{field!r} — not a Deliverable-A manifest")
    manifest["_path"] = path
    return manifest


def process_sheet(manifest: Mapping[str, Any], gt: crop_harness_gt.GroundTruth,
                  gt_validation: Mapping[str, int], *,
                  case_ids: set[str] | None, sides: tuple[str, ...],
                  fresh: bool, v1_workers: int, h2_workers: int,
                  diag_port: int, timeout: float,
                  harness: Mapping[str, Any]) -> dict[str, Any]:
    manifest_path: Path = manifest["_path"]
    sheet = manifest["sheet"]
    format_ref = manifest["format_ref"]
    scan_dpi = float(manifest["scan_dpi"])
    spec = resolve_format_ref(format_ref)
    tiles_yx = spec._tiles_yx

    chosen = [case for case in manifest["cases"]
              if case_ids is None or case["case_id"] in case_ids]
    finished: list[dict[str, Any]] = []
    for case in chosen:
        crop_path = manifest_path.parent / case["crop_file"]
        if not crop_path.is_file():
            print(f"crop_harness: {case['case_id']}: crop file "
                  f"{crop_path} is absent — skipped", file=sys.stderr)
            continue
        crop_sha = _sha256_file(crop_path)
        run_dir = manifest_path.parent / "runs" / case["case_id"]
        runs: dict[str, dict[str, Any]] = {}
        for side in SIDES:
            # --fresh is scoped to the SELECTED side(s) only (bug found
            # in FINISHER verification, 2026-08-28): a bare `fresh=fresh`
            # here poisoned the non-executed side's adoption too — e.g.
            # `--side h2 --fresh` reported v1 "stale"/side-unavailable
            # even though v1 was never touched, contradicting
            # run_case_side's own docstring promise that an h2-only
            # iteration "still renders v1 columns from v1's standing
            # decodes without ever re-running them."
            side_selected = side in sides
            runs[side] = run_case_side(
                case, side, run_dir, crop_path, crop_sha,
                scan_dpi=scan_dpi, format_ref=format_ref,
                workers=v1_workers if side == "v1" else h2_workers,
                diag_port=diag_port, timeout=timeout,
                fresh=fresh and side_selected,
                execute=side_selected)
        target_tiles = [_manifest_tile(t["tile"])
                        for t in case.get("targets", ())]
        v1_paths = side_paths(run_dir, "v1")
        h2_paths = side_paths(run_dir, "h2")
        v1_data = (read_crop_v1(v1_paths["state"], tiles_yx,
                                gt.tile_user_bits)
                   if runs["v1"]["status"] in ("ran", "adopted")
                   and v1_paths["state"].is_file() else None)
        h2_data = (read_crop_h2(h2_paths["state"], target_tiles)
                   if runs["h2"]["status"] in ("ran", "adopted")
                   and h2_paths["state"].is_dir() else None)
        result = compare_case(case, gt, runs, v1_data, h2_data)
        result["crop_file"] = str(crop_path)
        result["crop_sha256"] = crop_sha
        finished.append(result)

    return {
        "sheet": sheet,
        "manifest": str(manifest_path),
        "format_ref": format_ref,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "harness": dict(harness),
        "gt_validation": {
            "payload_sha256": gt.payload_sha256,
            "rule": "every v1-certified tile on both archived sheets "
                    "matches the re-encoded golden payload exactly "
                    "(superset of the both-certified bar)",
            "validated_tiles": dict(gt_validation)},
        "cases": finished,
        "aggregates": aggregate_cases(finished),
    }


def _harness_provenance(argv: list[str]) -> dict[str, Any]:
    return {"argv": " ".join(argv),
            "repo_head": _git("rev-parse", "HEAD"),
            "v1_receiver_tree": _git("rev-parse", "HEAD:src"),
            "h2_receiver_tree": _git("rev-parse", "HEAD:holo2/src")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", action="append", type=Path,
                        default=[],
                        help="a Deliverable-A cases.json (repeatable; "
                             "default: both sheets' manifests, absent "
                             "ones skipped with a note)")
    parser.add_argument("--case", action="append", default=[],
                        help="case_id to run (repeatable; default all)")
    parser.add_argument("--side", choices=("v1", "h2", "both"),
                        default="both",
                        help="which receiver(s) to DECODE; the other "
                             "side's standing sidecars still render")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore matching sidecars and re-decode")
    parser.add_argument("--v1-workers", type=int, default=4,
                        help="v1 --workers (execution-only; moderate "
                             "per HANDOFF-CROP)")
    parser.add_argument("--h2-workers", type=int, default=4,
                        help="holo2 --workers")
    parser.add_argument("--diag-port", type=int, default=8061,
                        help="holo2 diag port for crop decodes (default "
                             "8061 — never the production 8024/8025)")
    parser.add_argument("--timeout", type=float, default=3600.0,
                        help="seconds per subprocess decode")
    args = parser.parse_args(argv)

    if args.manifest:
        manifest_paths = list(args.manifest)
        missing = [path for path in manifest_paths if not path.is_file()]
        if missing:
            raise SystemExit(f"crop_harness: manifest(s) absent: "
                             f"{[str(p) for p in missing]}")
    else:
        manifest_paths = [path for path in DEFAULT_MANIFESTS
                          if path.is_file()]
        for path in DEFAULT_MANIFESTS:
            if not path.is_file():
                print(f"crop_harness: default manifest {path} absent — "
                      f"skipped (Deliverable A generates it)",
                      file=sys.stderr)
        if not manifest_paths:
            raise SystemExit(
                "crop_harness: no manifest found — run "
                "holo2/measure/crop_cases.py first or pass --manifest")

    manifests = [load_manifest(path) for path in manifest_paths]
    case_ids = set(args.case) or None
    if case_ids is not None:
        known = {case["case_id"] for manifest in manifests
                 for case in manifest["cases"]}
        unknown = sorted(case_ids - known)
        if unknown:
            raise SystemExit(f"crop_harness: unknown case id(s) "
                             f"{unknown}; the loaded manifests declare "
                             f"{sorted(known)}")
    sides = SIDES if args.side == "both" else (args.side,)

    # GT FIRST (HANDOFF-CROP step 3): reconstruct, validate on both
    # archived sheets, refuse loudly before any comparison.
    try:
        payload = crop_harness_gt.load_golden_payload()
        format_refs = {manifest["format_ref"] for manifest in manifests}
        if len(format_refs) != 1:
            raise SystemExit(f"crop_harness: manifests disagree on "
                             f"format_ref: {sorted(format_refs)}")
        gt = crop_harness_gt.reconstruct_gt(format_refs.pop(), payload)
        gt_validation = crop_harness_gt.validate_gt_against_archives(gt)
    except crop_harness_gt.GTValidationError as error:
        print(f"crop_harness: {error}", file=sys.stderr)
        return EXIT_GT_VALIDATION
    print("crop_harness: GT validated — "
          + ", ".join(f"{sheet}: {count} tiles"
                      for sheet, count in sorted(gt_validation.items())),
          file=sys.stderr)

    harness = _harness_provenance(sys.argv[1:] if argv is None else argv)
    n_wrong = 0
    for manifest in manifests:
        results = process_sheet(
            manifest, gt, gt_validation, case_ids=case_ids, sides=sides,
            fresh=args.fresh, v1_workers=args.v1_workers,
            h2_workers=args.h2_workers, diag_port=args.diag_port,
            timeout=args.timeout, harness=harness)
        n_wrong += len(results["aggregates"]["wrong_certificates"])
        out_dir = manifest["_path"].parent
        results_path = out_dir / "results.json"
        results_path.write_text(
            json.dumps(results, indent=1, default=str) + "\n",
            encoding="utf-8")
        report_path = out_dir / f"crop-battery-{results['sheet']}.md"
        text = crop_harness_report.render_report(results)
        report_path.write_text(text, encoding="utf-8")
        print(text)
        print(f"crop_harness: wrote {results_path} and {report_path}",
              file=sys.stderr)

    if n_wrong:
        print(f"crop_harness: {n_wrong} WRONG CERTIFICATE(S) — see the "
              f"report top", file=sys.stderr)
        return EXIT_WRONG_CERTIFICATE
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
