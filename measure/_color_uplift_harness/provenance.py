"""Corpus provenance: SHA-256 of every artifact + the archived CLI flags.

``provenance.json`` (committed next to this module) is the campaign's
frozen statement of what was measured.  Every run refuses on a SHA
mismatch, so an accidentally re-scanned or re-decoded artifact can never
enter a comparison table silently.

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.provenance write
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.provenance verify [--capture KEY]

Writing hashes ~44 GB of TIFFs plus ~3.5 GB of states (streamed, never
slurped): about a minute on a warm local SSD.

Flag extraction is evidence-based, never guessed: everything comes from
``<state>.diag/{report,status}.json`` and ``<state>.diag/events.jsonl``.
A fact the archived run did not record is spelled ``"unknown"`` and
listed in ``unknown_flags``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import corpus
from .corpus import CAPTURES, CaptureRow, sha256_file

SCHEMA = "color-uplift-provenance-1"

_LANE_ROW = re.compile(
    r"lane\s+capture\s+(?P<capture>[0-9a-f]+)\s+\(\d+/\d+\)\s+·\s+lane\s+"
    r"(?P<lane>\S+)\s+·\s+level\s+(?P<level>\d+)/(?P<total>\d+)\s+·\s+"
    r"(?P<ppc_num>\d+)/(?P<ppc_den>\d+)\s+ppc\s+·\s+(?P<dpi>[\d.]+)\s+dpi")
_LDPC_ROW = re.compile(
    r"certificates\s+(?P<certificates>\d+)\s+\(\+(?P<bp150>\d+)\s+BP150\)")
_CLOSE_ROW = re.compile(r"fountain\s+(?P<tail>.*)$")


def _artifact(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"missing corpus artifact: {path}")
    stat = path.stat()
    return {
        "path": str(path.relative_to(corpus.corpus_root())),
        "bytes": int(stat.st_size),
        "sha256": sha256_file(path),
    }


def _scan_events(path: Path) -> dict:
    """Stream one events.jsonl for the few facts that pin the flags.

    Only lines carrying the two names we need are parsed; the byte test
    keeps a 736 MB ledger to one linear read.
    """
    lanes: list[str] = []
    ordinals: list[int] = []
    close_rows: list[dict] = []
    ingest: dict | None = None
    if not path.is_file():
        return {"available": False}
    with open(path, "rb") as handle:
        for raw in handle:
            if b'"level.open"' in raw:
                row = json.loads(raw)
                if row.get("name") == "level.open":
                    lanes.append(str(row["details"].get("lane.id")))
                    ordinals.append(int(row["details"].get("level.ordinal")))
            elif b'"close.check"' in raw:
                row = json.loads(raw)
                if row.get("name") == "close.check":
                    close_rows.append(row["details"])
            elif ingest is None and b'"ingest.complete"' in raw:
                row = json.loads(raw)
                if row.get("name") == "ingest.complete":
                    ingest = row["details"]
    # The two close.check shapes are the --complete discriminator: a
    # deferred close emits ONE row carrying close.deferred/close.
    # certificates at the end of the drive; an ordinary close emits one
    # row per barrier carrying close.new_certificates.
    deferred: bool | None = None
    if close_rows:
        deferred = bool(close_rows[-1].get("close.deferred", False))
        per_barrier = any("close.new_certificates" in row
                          for row in close_rows)
        if deferred and per_barrier:
            deferred = None                       # contradictory evidence
    return {
        "available": True,
        "lanes_executed": lanes,
        "level_ordinals_executed": ordinals,
        "close_checks": len(close_rows),
        "close_deferred": deferred,
        "close_status": (close_rows[-1].get("close.status")
                         if close_rows else None),
        "ingest": ingest,
    }


def _status_facts(path: Path) -> dict:
    status = json.loads(path.read_text())
    rows = status.get("rows", [])
    facts: dict = {"rows": rows}
    for row in rows:
        lane = _LANE_ROW.search(row)
        if lane is not None:
            facts["last_lane_id"] = lane.group("lane")
            facts["levels_executed"] = int(lane.group("level"))
            facts["levels_total"] = int(lane.group("total"))
            facts["native_lane_dpi"] = float(lane.group("dpi"))
            facts["capture_id_prefix"] = lane.group("capture")
        ldpc = _LDPC_ROW.search(row)
        if ldpc is not None:
            facts["archived_certificates"] = int(ldpc.group("certificates"))
            facts["archived_retry150_certificates"] = int(ldpc.group("bp150"))
        close = _CLOSE_ROW.search(row.strip())
        if close is not None and row.strip().startswith("fountain"):
            facts["close_row"] = close.group("tail")
    return facts


def _baseline_flags(row: CaptureRow, report: dict, status: dict,
                    events: dict, format_row_id: str) -> dict:
    """Reconstruct the archived ``confetti.py decode`` invocation."""
    from holo.format.registry import FORMAT_ROWS

    unknown: list[str] = []
    sources: dict[str, str] = {}

    pages = tuple(report.get("page_domain", ()))
    spec = corpus.resolve_spec(row, format_row_id)
    if pages == tuple(range(spec.max_pages)):
        page_flag: object = None          # no --page: complete page domain
        sources["page"] = (
            "report.json page_domain == range(max_pages) => --page absent")
    else:
        page_flag = list(pages)
        sources["page"] = "report.json page_domain (explicit subset)"

    lanes = events.get("lanes_executed") or []
    last_lane = (lanes[-1] if lanes else status.get("last_lane_id", ""))
    refine = bool(last_lane.startswith("r"))
    sources["refine"] = (
        "events.jsonl level.open lane ids" if lanes
        else "status.json lane row")

    deferred = events.get("close_deferred")
    if deferred is None:
        complete: object = "unknown"
        unknown.append("complete")
        sources["complete"] = "no (or contradictory) close.check evidence"
    else:
        complete = bool(deferred)
        sources["complete"] = (
            "events.jsonl close.check shape: one deferred row => --complete, "
            "one row per barrier => --complete absent")

    # A state built by more than one invocation keeps only its LAST
    # invocation's events: the earlier flags are unrecoverable.
    ordinals = events.get("level_ordinals_executed") or []
    resumed = bool(ordinals) and min(ordinals) > 0
    if resumed:
        unknown.append("flags of the earlier invocation(s)")

    registry_resolvable = format_row_id in FORMAT_ROWS
    manifest = row.manifest()
    if registry_resolvable:
        coding: object = "unknown"
        printer: object = "unknown"
        unknown.extend(["coding", "printer"])
        sources["coding"] = (
            "state format row IS registry-resolvable, so --coding/--printer "
            "were optional; the CLI records no argv")
    else:
        coding = manifest["coding_id"]
        printer = manifest["printer_id"]
        sources["coding"] = (
            "state format row is NOT in FORMAT_ROWS => --coding/--printer "
            "were REQUIRED; values from the emit manifest")

    dpi = status.get("native_lane_dpi")
    if dpi is not None and abs(float(dpi) - row.scan_dpi) > 1e-6:
        raise SystemExit(
            f"{row.key}: registry scan dpi {row.scan_dpi} disagrees with the "
            f"archived native lane dpi {dpi}")
    sources["scan_dpi"] = "status.json lane row native dpi"

    unknown.extend(["workers", "source_sha256"])
    return {
        "flags": {
            "scans": [str(row.tiff_path())],
            "scan_dpi": [row.scan_dpi],
            "state": str(row.state_path()),
            "out": (str(row.recovered_path())
                    if row.recovered_path() is not None else "unknown"),
            "page": page_flag,
            "coding": coding,
            "printer": printer,
            "complete": complete,
            "mopup": ("implied by --refine (plan-prefix law)" if refine
                      else "unknown"),
            "refine": refine,
            "workers": "unknown",
            "source_sha256": "unknown",
            "diag": row.diag_path().is_dir(),
        },
        "flag_sources": sources,
        "unknown_flags": sorted(set(unknown)),
        "levels_executed": status.get("levels_executed"),
        "levels_total": status.get("levels_total"),
        "last_lane_id": last_lane,
        "lanes_executed": lanes,
        "multi_invocation": resumed,
        "level_ordinals_in_last_invocation": ordinals,
        "archived_certificates": status.get("archived_certificates"),
        "archived_retry150_certificates": status.get(
            "archived_retry150_certificates"),
        "archived_close_row": status.get("close_row"),
        "state_status": report.get("state", {}).get("status"),
        "receiver_policy_id": report.get("receiver_policy_id"),
    }


def _gt_facts(manifest: dict) -> dict:
    """GT facts from the emit manifest.

    ``gt_sha256`` here is the manifest's ARRAY-bytes hash (verified by
    :mod:`gt_score`); ``artifacts.gt.sha256`` is the ``.npy`` FILE hash.
    The two differ by the npy header and are both recorded on purpose.
    """
    page = manifest["pages"][0]
    return {
        "gt_packed_shape": list(page["gt_packed_shape"]),
        "gt_bitorder": page["gt_bitorder"],
        "gt_plane_order": page.get("gt_plane_order"),
        "gt_sha256": page["gt_sha256"],
        "cell_dots": int(manifest["cell_dots"]),
        "page_cells_yx": list(manifest["page_cells_yx"]),
        "tiles_yx": list(manifest["tiles_yx"]),
    }


def build_row(row: CaptureRow) -> dict:
    diag = row.diag_path()
    report = json.loads((diag / "report.json").read_text())
    status = _status_facts(diag / "status.json")
    events = _scan_events(diag / "events.jsonl")
    manifest = row.manifest()
    format_row_id = report["format"]
    baseline = _baseline_flags(row, report, status, events, format_row_id)
    spec = corpus.resolve_spec(row, format_row_id)
    return {
        "key": row.key,
        "engine": row.engine,
        "kind": row.kind,
        "role": row.role,
        "scan_dpi": row.scan_dpi,
        "format_row_id": format_row_id,
        "codec_id": spec.codec_id,
        "stream_ids": list(spec.stream_ids),
        "coding_id": manifest["coding_id"],
        "printer_id": manifest["printer_id"],
        "payload_bytes": int(manifest["payload"]["bytes"]),
        "payload_sha256": manifest["payload"]["sha256"],
        "gt": _gt_facts(manifest),
        "artifacts": {
            "tiff": _artifact(row.tiff_path()),
            "state": _artifact(row.state_path()),
            "manifest": _artifact(row.emit_path() / "manifest.json"),
            "gt": _artifact(row.gt_path()),
            "payload_bin": _artifact(row.payload_bin_path()),
            "recovered": (_artifact(row.recovered_path())
                          if row.recovered_path() is not None else None),
        },
        "baseline": baseline,
        "events_scan": {
            key: value for key, value in events.items() if key != "ingest"},
    }


def build(keys: tuple[str, ...] | None = None) -> dict:
    rows = CAPTURES if keys is None else tuple(
        corpus.capture(key) for key in keys)
    document = {
        "schema": SCHEMA,
        "note": (
            "COLOR-UPLIFT-PLAN v1.3 §4 corpus. Paths are relative to the "
            "READ-ONLY corpus root; hashes are of the exact archived "
            "bytes. Flags are extracted from the archived diagnostics; "
            "'unknown' means the run recorded no evidence for it."),
        "corpus_root_at_write": str(corpus.corpus_root()),
        "captures": {},
    }
    for row in rows:
        print(f"  hashing {row.key} …", file=sys.stderr, flush=True)
        document["captures"][row.key] = build_row(row)
    _cross_check_e030(document)
    return document


def _cross_check_e030(document: dict) -> None:
    """FAIL on any disagreement with the experiment's own SHA record."""
    recorded = dict(corpus.iter_e030_recorded_shas())
    checked = 0
    for key, row in document["captures"].items():
        name = Path(row["artifacts"]["tiff"]["path"]).name
        expected = recorded.get(name)
        if expected is None:
            continue
        checked += 1
        if expected != row["artifacts"]["tiff"]["sha256"]:
            raise SystemExit(
                f"CORPUS INTEGRITY FAILURE: {name} hashes "
                f"{row['artifacts']['tiff']['sha256']} but "
                f"{corpus.E030_TIFF_SHA_FILE} records {expected}")
    document["e030_tiff_sha_cross_check"] = {
        "file": corpus.E030_TIFF_SHA_FILE,
        "rows_recorded": len(recorded),
        "rows_checked": checked,
        "agree": True,
    }


def cmd_write(args: argparse.Namespace) -> int:
    document = build(tuple(args.capture) if args.capture else None)
    if args.capture and corpus.PROVENANCE_PATH.is_file():
        existing = corpus.load_provenance()
        existing["captures"].update(document["captures"])
        document = existing
    corpus.PROVENANCE_PATH.write_text(
        json.dumps(document, indent=1, sort_keys=True) + "\n")
    print(f"wrote {corpus.PROVENANCE_PATH} "
          f"({len(document['captures'])} captures)")
    return 0


def verify(keys: tuple[str, ...] | None = None,
           *, artifacts: tuple[str, ...] | None = None) -> list[str]:
    """Return a list of human-readable mismatches (empty == verified)."""
    document = corpus.load_provenance()
    problems: list[str] = []
    wanted = keys or tuple(document["captures"])
    for key in wanted:
        row = document["captures"].get(key)
        if row is None:
            problems.append(f"{key}: absent from provenance.json")
            continue
        for name, recorded in row["artifacts"].items():
            if recorded is None:
                continue
            if artifacts is not None and name not in artifacts:
                continue
            path = corpus.corpus_root() / recorded["path"]
            if not path.is_file():
                problems.append(f"{key}/{name}: missing at {path}")
                continue
            size = path.stat().st_size
            if size != recorded["bytes"]:
                problems.append(
                    f"{key}/{name}: {size} bytes, recorded "
                    f"{recorded['bytes']}")
                continue
            actual = sha256_file(path)
            if actual != recorded["sha256"]:
                problems.append(
                    f"{key}/{name}: sha {actual[:16]}… != recorded "
                    f"{recorded['sha256'][:16]}…")
    return problems


def cmd_verify(args: argparse.Namespace) -> int:
    problems = verify(
        tuple(args.capture) if args.capture else None,
        artifacts=tuple(args.artifact) if args.artifact else None)
    if problems:
        for line in problems:
            print(f"MISMATCH {line}")
        print(f"provenance verify FAILED ({len(problems)} problems)")
        return 1
    print("provenance verify OK")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    document = corpus.load_provenance()
    for key, row in document["captures"].items():
        if args.capture and key not in args.capture:
            continue
        art = row["artifacts"]
        print(f"{key:15s} {row['format_row_id']:28s} "
              f"dpi={row['scan_dpi']:.0f} "
              f"tiff={art['tiff']['sha256'][:12]} "
              f"state={art['state']['sha256'][:12]} "
              f"certs={row['baseline']['archived_certificates']} "
              f"close={row['baseline']['state_status']}")
        flags = row["baseline"]["flags"]
        print(f"{'':15s} flags: --complete={flags['complete']} "
              f"--refine={flags['refine']} --page={flags['page']} "
              f"--coding={flags['coding']} --printer={flags['printer']} "
              f"unknown={row['baseline']['unknown_flags']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.provenance", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, handler in (("write", cmd_write), ("verify", cmd_verify),
                          ("show", cmd_show)):
        item = sub.add_parser(name)
        item.add_argument("--capture", action="append", default=[],
                          help="restrict to this capture key (repeatable)")
        if name == "verify":
            item.add_argument(
                "--artifact", action="append", default=[],
                help="restrict to this artifact name (tiff/state/gt/…)")
        item.set_defaults(handler=handler)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
