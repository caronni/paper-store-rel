"""The ledger — JSON lines, the Markdown summary, the maps (DESIGN §9).

One row per (page, ty, tx, stream) with the per-(lane, arm) blind
diagnostics, the per-rule combination summaries and the per-rung results
(each carrying its packed exit hard vector), preceded by a header with
the seed, the knobs and the provenance (run dir, format, captures, where
the targets came from, where the knobs came from, and whether the run
was non-blind).

NOTHING HERE IS SCORED.  Since the 2026-09-04 ruling a ledger is the
blind record of a run: no bits-wrong column, no soft information rate,
no waterfall, and no `wrong`/`false_accept` verdicts.  Those live in
`analyzer score`'s own report, computed offline from this file plus a
payload.  What this module keeps of DESIGN §9 is the attribution, the
stream x band table, the BLIND unsatisfied-check histogram, the exposure
and the close row.

ATTRIBUTION, and what is exact.  The ladder stops at the first
certificate, so a naive "certificates by rung" is a FIRST-SUCCESS
marginal and nothing else.  :func:`summarize` therefore prints three
things and labels them:

* the ORDER-FREE UNION — how many tile-streams certified at all.  This
  is the headline and it does not depend on any order;
* first-success marginals by rule and by rung, in the pinned order;
* leave-one-out values.  Over RULES these are EXACT when the pass ran
  with ``all_rules`` (every rule's ladder is run, so the set of rules
  that would have certified a key is fully observed).  Over RUNGS they
  are an APPROXIMATION from below: a rung after the certifying one was
  never attempted, so it can only be credited where an earlier rung
  failed.  Both are labelled in the output.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

from .types import (LIST_RUNGS, VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST,
                    VERDICT_FALSE_ACCEPT,
                    VERDICT_UNCOVERED, LedgerRow)

HEADER_TYPE = "header"
ROW_TYPE = "row"

#: The buckets both histograms use — the blind one here, the offline
#: bits-wrong one in `analyzer.score`, so the two are read side by side.
HISTOGRAM_EDGES: tuple[int, ...] = (0, 1, 2, 3, 5, 10, 50, 100, 500)


# ------------------------------------------------------------- json-able

def jsonable(value: Any) -> Any:
    """numpy and tuples down to what `json` will take."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        # NaN and +-inf are not JSON; a missing number is `null`, never a
        # token no other reader will parse.
        value = float(value)
        return value if np.isfinite(value) else None
    if isinstance(value, np.ndarray):
        return [jsonable(item) for item in value.tolist()]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        return {str(name): jsonable(item) for name, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(item) for item in value]
    return str(value)


def row_to_dict(row: LedgerRow) -> dict:
    return {
        "type": ROW_TYPE,
        "page": int(row.page), "ty": int(row.ty), "tx": int(row.tx),
        "stream_id": str(row.stream_id), "esi": int(row.esi),
        "covered": bool(row.covered),
        "certified_by_production": bool(row.certified_by_production),
        "source": row.source, "band": row.band, "band_any": row.band_any,
        "neighbours_certified": int(row.neighbours_certified),
        "siblings_certified": list(row.siblings_certified),
        "known_cells_in_halo": int(row.known_cells_in_halo),
        "n_discriminating_labels": int(row.n_discriminating_labels),
        "production_attempts": jsonable(row.production_attempts),
        "metadata_known": bool(row.metadata_known),
        "evidence": jsonable(row.evidence),
        "combined": jsonable(row.combined),
        "rungs": jsonable(row.rungs),
        "verdict": row.verdict,
        "certifying_rung": row.certifying_rung,
        "certifying_rule": row.certifying_rule,
        "generation": row.generation,
        "predecessors": [list(key) for key in row.predecessors],
        "diag": jsonable(row.diag),
        "rank_report": row.rank_report,
        "rank_recomputed": row.rank_recomputed,
    }


def write_rows(path: Path | str, rows: Sequence[LedgerRow],
               header: Mapping[str, Any] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(
            {"type": HEADER_TYPE, **jsonable(dict(header or {}))}) + "\n")
        for row in rows:
            stream.write(json.dumps(row_to_dict(row)) + "\n")
    return path


def read_header(path: Path | str) -> dict:
    """Just the header line — a ledger can be GIGABYTES (sheet H: 2.6-5.8
    GB each), so the scorer reads headers first and rows in a stream."""
    with open(Path(path), "r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            return record if record.get("type") == HEADER_TYPE else {}
    return {}


def iter_rows(path: Path | str) -> Iterator[dict]:
    """Row dicts one at a time, never all of them at once.

    `read_rows` materialises the whole file, which is right for a small
    ledger and impossible for a big one: sheet H's five passes are 18 GB
    of JSON between them, and decoded dicts are several times that.
    """
    with open(Path(path), "r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") != HEADER_TYPE:
                yield record


def read_rows(path: Path | str) -> tuple[dict, list[dict]]:
    header: dict = {}
    rows: list[dict] = []
    with open(Path(path), "r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") == HEADER_TYPE:
                header = record
            else:
                rows.append(record)
    return header, rows


# ------------------------------------------------------------ attribution

def _as_dict(row: Any) -> dict:
    return row if isinstance(row, dict) else row_to_dict(row)


def _certifying_sets(row: dict) -> tuple[set[str], set[str]]:
    """The rules and the rungs that certified this row."""
    rules: set[str] = set()
    rungs: set[str] = set()
    for rule, batch in (row.get("rungs") or {}).items():
        if rule == "user_bits" or not isinstance(batch, list):
            continue
        for item in batch:
            if isinstance(item, dict) and item.get("verdict") in (
                    VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST):
                rules.add(str(rule))
                rungs.add(str(item.get("rung")))
    return rules, rungs


def attribution(rows: Iterable[Any], *, rule_order: Sequence[str] = (),
                rung_order: Sequence[str] = ()) -> dict:
    """Union, first-success marginals and leave-one-out (DESIGN §9)."""
    union = 0
    by_rule_first: Counter = Counter()
    by_rung_first: Counter = Counter()
    rule_sets: list[set[str]] = []
    rung_sets: list[set[str]] = []
    for raw in rows:
        row = _as_dict(raw)
        rules, rungs = _certifying_sets(row)
        if not rules:
            continue
        union += 1
        rule_sets.append(rules)
        rung_sets.append(rungs)
        first_rule = row.get("certifying_rule")
        first_rung = row.get("certifying_rung")
        by_rule_first[str(first_rule)] += 1
        by_rung_first[str(first_rung)] += 1
    seen_rules = sorted({name for item in rule_sets for name in item})
    seen_rungs = sorted({name for item in rung_sets for name in item})
    order_rules = [name for name in rule_order if name in seen_rules]
    order_rules += [name for name in seen_rules if name not in order_rules]
    order_rungs = [name for name in rung_order if name in seen_rungs]
    order_rungs += [name for name in seen_rungs if name not in order_rungs]
    return {
        "union": union,
        "rule_order": order_rules,
        "rung_order": order_rungs,
        "first_success_by_rule": {name: int(by_rule_first.get(name, 0))
                                  for name in order_rules},
        "first_success_by_rung": {name: int(by_rung_first.get(name, 0))
                                  for name in order_rungs},
        "leave_one_out_by_rule": {
            name: int(sum(1 for item in rule_sets if item - {name}))
            for name in order_rules},
        "leave_one_out_by_rung": {
            name: int(sum(1 for item in rung_sets if item - {name}))
            for name in order_rungs},
        "only_by_rule": {
            name: int(sum(1 for item in rule_sets if item == {name}))
            for name in order_rules},
    }


def _histogram(values: Sequence[int], edges: Sequence[int]) -> dict:
    out: dict[str, int] = {}
    values = [int(value) for value in values]
    for low, high in zip(edges, list(edges[1:]) + [None]):
        label = f">={low}" if high is None else (
            f"{low}" if high == low + 1 else f"{low}-{high - 1}")
        out[label] = sum(1 for value in values
                         if value >= low and (high is None or value < high))
    return out


def histograms(rows: Iterable[Any]) -> dict:
    """DESIGN §6's deferral input, BLIND HALF: unsatisfied checks at exit.

    The bits-wrong half is an oracle column and moved to
    `analyzer.score.bits_wrong_histogram`, which reads the same rungs
    through their packed hard vectors.
    """
    unsat: list[int] = []
    for raw in rows:
        row = _as_dict(raw)
        for rule, batch in (row.get("rungs") or {}).items():
            if rule == "user_bits" or not isinstance(batch, list):
                continue
            for item in batch:
                if not isinstance(item, dict):
                    continue
                # A LIST rung's `unsat_at_exit` is the MINIMUM over its
                # candidate decodes (L4's `best_unsat`), not one decode's
                # exit, so it does not belong in the deferral histogram
                # DESIGN §6 reads; `unsat_at_entry` of the same row is the
                # comparable number and it was already counted on the rung
                # L4 entered from (W4 review).
                if str(item.get("rung", "")).split(":")[0] in LIST_RUNGS:
                    continue
                value = item.get("unsat_at_exit")
                if value is not None and int(value) >= 0:
                    unsat.append(int(value))
    return {
        "unsat_at_exit": _histogram(unsat, HISTOGRAM_EDGES),
        "n_unsat_samples": len(unsat),
    }


def agreement_table(rows: Iterable[Any]) -> dict:
    """Leg 4 of the correctness argument, counted (2026-09-04).

    `independent_agreement` on a row is how many of its gate-passing
    certificates rest on DISJOINT physical captures and carry identical
    user bits; `contradiction` says two carried different bits, which
    refused the key.  Rows the pass never certified contribute 0 and are
    reported separately, so `corroborated` is a share of certificates and
    not of targets.
    """
    counts: Counter = Counter()
    contradictions: list[dict] = []
    n_certified = 0
    for raw in rows:
        row = _as_dict(raw)
        diag = row.get("diag") or {}
        verdict = row.get("verdict")
        if verdict in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST):
            n_certified += 1
            counts[int(diag.get("independent_agreement", 0) or 0)] += 1
        if diag.get("contradiction"):
            contradictions.append(
                {"key": [row.get("page"), row.get("ty"), row.get("tx"),
                         row.get("stream_id")],
                 "claims": diag.get("contradicting")})
    return {"n_certified": n_certified,
            "by_independent_agreement": {int(name): int(value)
                                         for name, value
                                         in sorted(counts.items())},
            "n_corroborated": int(sum(value for name, value in counts.items()
                                      if name >= 2)),
            "n_contradictions": len(contradictions),
            "contradictions": contradictions}


def stream_band_table(rows: Iterable[Any]) -> dict:
    table: dict[str, dict[str, dict[str, int]]] = {}
    for raw in rows:
        row = _as_dict(raw)
        stream = str(row.get("stream_id"))
        band = str(row.get("band"))
        cell = table.setdefault(stream, {}).setdefault(
            band, {"n": 0, "certified": 0, "false_accept": 0,
                   "uncovered": 0, "corroborated": 0, "contradicted": 0})
        cell["n"] += 1
        diag = row.get("diag") or {}
        if int(diag.get("independent_agreement", 0) or 0) >= 2:
            cell["corroborated"] += 1
        if diag.get("contradiction"):
            cell["contradicted"] += 1
        verdict = row.get("verdict")
        if verdict == VERDICT_CERTIFIED:
            cell["certified"] += 1
        elif verdict == VERDICT_CERTIFIED_LIST:
            cell["certified"] += 1
            cell["certified_list"] = cell.get("certified_list", 0) + 1
        elif verdict == VERDICT_FALSE_ACCEPT:
            cell["false_accept"] += 1
        elif verdict == VERDICT_UNCOVERED:
            cell["uncovered"] += 1
    return table


# --------------------------------------------------------------- markdown

def _table(headers: Sequence[str], body: Sequence[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(str(name) for name in headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    for line in body:
        lines.append("| " + " | ".join(
            "" if value is None else str(value) for value in line) + " |")
    return "\n".join(lines)


def summarize(rows: Sequence[Any], *, header: Mapping[str, Any] | None = None,
              controls: Mapping[str, Any] | None = None,
              parity: Mapping[str, Any] | None = None,
              close_row: Mapping[str, Any] | None = None,
              null_exposure: Mapping[str, Any] | None = None) -> str:
    """The Markdown report of DESIGN §9."""
    header = dict(header or {})
    dicts = [_as_dict(row) for row in rows]
    attributed = attribution(
        dicts, rule_order=header.get("rules", ()),
        rung_order=header.get("rungs", ()))
    hist = histograms(dicts)
    bands = stream_band_table(dicts)
    agree = agreement_table(dicts)

    parts: list[str] = ["# analyzer ledger", ""]
    parts.append(_table(
        ["field", "value"],
        [["run dir", header.get("run_dir")],
         ["format", header.get("format_ref")],
         ["captures", len(header.get("captures", []) or [])],
         ["seed", header.get("seed")],
         ["workers", header.get("workers")],
         ["targets from", header.get("targets_from")],
         ["knobs from", header.get("knobs_from")],
         ["non-blind", header.get("non_blind")],
         ["arms", ", ".join(header.get("arms", []) or [])],
         ["rules", ", ".join(header.get("rules", []) or [])],
         ["rungs", ", ".join(header.get("rungs", []) or [])],
         ["rows", len(dicts)],
         ["generations run", header.get("generations_run")],
         ["seconds", None if header.get("seconds") is None
          else round(float(header["seconds"]), 1)]]))

    parts += ["", "## Certificates", "",
              f"**Order-free union: {attributed['union']} tile-stream(s)** "
              f"certified by at least one (rule, rung).", ""]
    parts.append(_table(
        ["rule", "first-success", "leave-one-out (EXACT with all_rules)",
         "only this rule"],
        [[name, attributed["first_success_by_rule"].get(name, 0),
          attributed["leave_one_out_by_rule"].get(name, 0),
          attributed["only_by_rule"].get(name, 0)]
         for name in attributed["rule_order"]] or [["—", 0, 0, 0]]))
    parts += ["", "Rung attribution — the ladder STOPS at the first "
              "certificate, so the leave-one-out column below is a LOWER "
              "BOUND (a rung after the certifying one was never "
              "attempted).", ""]
    parts.append(_table(
        ["rung", "first-success", "leave-one-out (LOWER BOUND)"],
        [[name, attributed["first_success_by_rung"].get(name, 0),
          attributed["leave_one_out_by_rung"].get(name, 0)]
         for name in attributed["rung_order"]] or [["—", 0, 0]]))

    parts += ["", "## Stream x band", ""]
    body = []
    for stream in sorted(bands):
        for band in sorted(bands[stream]):
            cell = bands[stream][band]
            body.append([stream, band, cell["n"], cell["certified"],
                         cell["corroborated"], cell["contradicted"],
                         cell["false_accept"], cell["uncovered"]])
    parts.append(_table(["stream", "band", "rows", "certified",
                         "corroborated", "contradicted",
                         "false_accept", "uncovered"], body or [["—"] * 8]))

    parts += ["", "## Independent agreement", "",
              "Leg 4 of the 2026-09-04 correctness argument: certificates "
              "for one key that rest on DISJOINT physical captures and "
              "carry identical user bits corroborate each other; two that "
              "differ are a contradiction and the key was REFUSED, never "
              "minted.  Independence is disjoint captures, not distinct "
              "rules — two rules over the same lanes read the same paper "
              "(DESIGN §0).", ""]
    parts.append(_table(
        ["independent certificates", "certified rows"],
        [[name, value] for name, value
         in agree["by_independent_agreement"].items()] or [["—", 0]]))
    parts += ["", f"corroborated (>=2 independent): "
              f"{agree['n_corroborated']} of {agree['n_certified']} "
              f"certified row(s); contradictions refused: "
              f"{agree['n_contradictions']}", ""]
    if agree["contradictions"]:
        parts.append("```json")
        parts.append(json.dumps(jsonable(agree["contradictions"]), indent=2,
                                sort_keys=True))
        parts.append("```")

    parts += ["", "## Histograms", "",
              f"unsatisfied checks at exit (BLIND, "
              f"{hist['n_unsat_samples']} rung outcomes)", ""]
    parts.append(_table(["bucket", "n"],
                        list(hist["unsat_at_exit"].items())))
    parts += ["", "Bits wrong at exit, the soft information rate and the "
              "waterfall are OFFLINE columns: `analyzer score --ledger "
              "<this file> --payload P` computes them from the packed hard "
              "vectors this ledger carries.", ""]

    parts += ["", "## Exposure", ""]
    parts.append(_table(
        ["ledger", "distinct consultations", "E[false]"],
        [["live", header.get("exposure_distinct"),
          header.get("exposure_expected_false")],
         ["null", None if null_exposure is None
          else null_exposure.get("distinct"),
          None if null_exposure is None
          else null_exposure.get("expected_false")]]))

    parts += ["", "## Controls", ""]
    if controls:
        parts.append("```json")
        parts.append(json.dumps(jsonable(controls), indent=2,
                                sort_keys=True))
        parts.append("```")
    else:
        parts.append("NOT RUN — a run without its controls is not a result "
                     "(DESIGN §8).")

    parts += ["", "## Parity", ""]
    if parity:
        parts.append("```json")
        parts.append(json.dumps(jsonable(parity), indent=2, sort_keys=True))
        parts.append("```")
    else:
        parts.append("NOT RUN.")

    parts += ["", "## Close", ""]
    if close_row:
        parts.append(_table(
            ["field", "value"],
            [[name, jsonable(value)] for name, value in
             sorted(close_row.items()) if name != "analyzer_keys"]))
    else:
        parts.append("NOT RUN.")
    return "\n".join(parts) + "\n"


# ------------------------------------------------------------- the maps

_VERDICT_RGB: dict[str, tuple[int, int, int]] = {
    "uncovered": (60, 60, 60),
    "production": (30, 90, 40),
    "certified": (60, 220, 90),
    "false_accept": (230, 60, 200),
    "wrong": (230, 30, 30),
    "open": (150, 40, 40),
    "untargeted": (20, 20, 20),
}


def render_maps(rows: Sequence[Any], out_dir: Path | str, *,
                tiles_yx: tuple[int, int] | None = None,
                scale: int = 6) -> list[Path]:
    """One PNG per plane: the verdict map.

    The bits-wrong map is an oracle picture and belongs to the offline
    scorer, which draws it beside its own report (`analyzer.score`).
    """
    from PIL import Image

    dicts = [_as_dict(row) for row in rows]
    if not dicts:
        return []
    if tiles_yx is None:
        tiles_yx = (max(int(row["ty"]) for row in dicts) + 1,
                    max(int(row["tx"]) for row in dicts) + 1)
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    streams = sorted({str(row["stream_id"]) for row in dicts})
    for stream in streams:
        verdict = np.full((height, width, 3), _VERDICT_RGB["untargeted"],
                          np.uint8)
        for row in dicts:
            if str(row["stream_id"]) != stream:
                continue
            ty, tx = int(row["ty"]), int(row["tx"])
            name = str(row.get("verdict"))
            if row.get("certified_by_production") and name != "certified":
                name = "production"
            verdict[ty, tx] = _VERDICT_RGB.get(name, _VERDICT_RGB["open"])
        path = out_dir / f"verdict-{stream}.png"
        Image.fromarray(verdict).resize(
            (width * scale, height * scale), Image.NEAREST).save(path)
        written.append(path)
    return written
