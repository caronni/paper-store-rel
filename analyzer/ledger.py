"""The ledger — what its rows MEAN: the attribution, the summary, the maps.

The lines themselves, the live writer and the readers are
`analyzer.ledgerio`, and every name it defines is re-exported here: a
ledger is one subject with two halves, and the file reached its
1,000-line seam when the streamed writer landed (2026-09-13).  So
`ledger.iter_rows`, `ledger.write_rows`, `ledger.LedgerWriter` and
`ledger.jsonable` all still mean what they meant.

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

A READER HERE TAKES AN ITERABLE, never a list it must hold: `summarize`
and `render_maps` are handed `ledgerio.iter_rows_latest` over a written
ledger, and each keeps only its own projection of a row (`slim_row`,
`_MAP_FIELDS`) — a row is 1.6 MB and a pass has thousands.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

# The one value of `stop_reason` the summary has to react to.  `stopdoor`
# is a leaf too (it reaches `.types` and nothing else at import time; its
# `ledger` import is function-local), so this stays acyclic.
from .stopdoor import STOP_INTERRUPTED

# The on-disk half, re-exported: one import, `ledger`, for every caller.
from .ledgerio import (BACKUP_SUFFIX, FOOTER_TAIL_BYTES, FOOTER_TYPE,
                       HEADER_TYPE, MINTS_NAME, ROW_TYPE, LedgerWriter,
                       ReadStats, iter_rows, iter_rows_latest, jsonable,
                       keep_aside, key_of, mints_beside, read_footer,
                       read_header, read_rows, row_to_dict, write_rows)

from .types import (LIST_RUNGS, VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST,
                    VERDICT_FALSE_ACCEPT,
                    VERDICT_UNCOVERED)

#: The names this module re-exports from `ledgerio`, so that a reader of
#: either file can see the seam — and so a linter knows the imports
#: above are the module's public surface, not dead weight.
_REEXPORTED = (BACKUP_SUFFIX, FOOTER_TAIL_BYTES, FOOTER_TYPE, HEADER_TYPE,
               MINTS_NAME, ROW_TYPE, LedgerWriter, ReadStats, iter_rows,
               iter_rows_latest, jsonable, keep_aside, key_of,
               mints_beside, read_footer, read_header, read_rows,
               row_to_dict, write_rows)


#: The buckets both histograms use — the blind one here, the offline
#: bits-wrong one in `analyzer.score`, so the two are read side by side.
HISTOGRAM_EDGES: tuple[int, ...] = (0, 1, 2, 3, 5, 10, 50, 100, 500)


# ------------------------------------------------------------ attribution

def _as_dict(row: Any) -> dict:
    return row if isinstance(row, dict) else row_to_dict(row)


#: What the REPORT never reads: the per-(lane, arm) blind diagnostics and
#: the per-rule combination summaries.  `evidence` alone is 80-92% of a
#: row — the five per-label arrays of `calibrate` ride it, one set per
#: (lane, arm) (MEASURED 2026-09-13, `analyzer/MEMORY-2026-09-13.md` §1).
_SLIM_DROP = ("evidence", "combined")

#: And what the report reads off a RUNG: `attribution` takes the rung and
#: the verdict, `histograms` takes `unsat_at_exit`.  A pass with
#: `all_rules` writes 410 rung records a row, so the projection matters
#: as much as dropping the evidence does.
_SLIM_RUNG_FIELDS = ("rung", "verdict", "unsat_at_exit")


def slim_row(row: Any) -> dict:
    """A row with the bulk taken out, for a reader that keeps many.

    `summarize` walks its rows five times, so it holds them; on a
    streamed ledger that would put the pass's memory back in the
    reporter.  What the summary reads is the verdict, the key, the band,
    the diag and three fields per rung — never the evidence, the
    combinations or the 683-character packed hard vector, which is the
    offline scorer's alone.  Tens of kilobytes a row instead of 1.6 MB.
    """
    record = _as_dict(row)
    out = {name: value for name, value in record.items()
           if name not in _SLIM_DROP}
    rungs = record.get("rungs")
    if isinstance(rungs, Mapping):
        out["rungs"] = {
            rule: [{name: item.get(name) for name in _SLIM_RUNG_FIELDS}
                   if isinstance(item, Mapping) else item for item in batch]
            for rule, batch in rungs.items()
            if rule != "user_bits" and isinstance(batch, list)}
    return out



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


REROLL_PREFIX = "reroll:"
UNRECORDED_ARM = "(unrecorded)"


def certifying_arms(label: Any) -> tuple[tuple[str, ...], bool]:
    """``certifying_arm`` -> ``(arm names, via_reroll)``.

    The selection's label is the ``|``-joined SET of arms the lanes
    selected (usually one); a re-roll's is ``reroll:<arm>`` and is
    counted under ``<arm>``.  A row written before B1 carries no label
    and is counted under `UNRECORDED_ARM`.
    """
    if label is None:
        return (UNRECORDED_ARM,), False
    text = str(label)
    reroll = text.startswith(REROLL_PREFIX)
    if reroll:
        text = text[len(REROLL_PREFIX):]
    names = tuple(name for name in text.split("|") if name)
    return (names or (UNRECORDED_ARM,)), reroll


def attribution(rows: Iterable[Any], *, rule_order: Sequence[str] = (),
                rung_order: Sequence[str] = (),
                arm_order: Sequence[str] = ()) -> dict:
    """Union, first-success marginals and leave-one-out (DESIGN §9).

    Over ARMS (W8 B1) the ledger knows only which arm's evidence
    certified — the selection's set, or the re-roll's one arm — so the
    arm columns are FIRST-SUCCESS marginals: `first_success_by_arm`
    credits every arm the certifying label names, `only_by_arm` the rows
    whose label names exactly one arm (the certificate rests on that
    arm's evidence alone), `reroll_by_arm` the rows won through the
    re-roll.  There is no leave-one-out over arms: the ladder stops at
    the first certificate and the re-roll runs in battery order.
    """
    union = 0
    by_rule_first: Counter = Counter()
    by_rung_first: Counter = Counter()
    by_arm_first: Counter = Counter()
    only_arm: Counter = Counter()
    reroll_arm: Counter = Counter()
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
        names, via_reroll = certifying_arms(row.get("certifying_arm"))
        for name in names:
            by_arm_first[name] += 1
            if via_reroll:
                reroll_arm[name] += 1
        if len(names) == 1:
            only_arm[names[0]] += 1
    seen_rules = sorted({name for item in rule_sets for name in item})
    seen_rungs = sorted({name for item in rung_sets for name in item})
    seen_arms = sorted(by_arm_first)
    order_rules = [name for name in rule_order if name in seen_rules]
    order_rules += [name for name in seen_rules if name not in order_rules]
    order_rungs = [name for name in rung_order if name in seen_rungs]
    order_rungs += [name for name in seen_rungs if name not in order_rungs]
    order_arms = [name for name in arm_order if name in seen_arms]
    order_arms += [name for name in seen_arms if name not in order_arms]
    return {
        "union": union,
        "rule_order": order_rules,
        "rung_order": order_rungs,
        "arm_order": order_arms,
        "first_success_by_rule": {name: int(by_rule_first.get(name, 0))
                                  for name in order_rules},
        "first_success_by_rung": {name: int(by_rung_first.get(name, 0))
                                  for name in order_rungs},
        "first_success_by_arm": {name: int(by_arm_first.get(name, 0))
                                 for name in order_arms},
        "leave_one_out_by_rule": {
            name: int(sum(1 for item in rule_sets if item - {name}))
            for name in order_rules},
        "leave_one_out_by_rung": {
            name: int(sum(1 for item in rung_sets if item - {name}))
            for name in order_rungs},
        "only_by_rule": {
            name: int(sum(1 for item in rule_sets if item == {name}))
            for name in order_rules},
        "only_by_arm": {name: int(only_arm.get(name, 0))
                        for name in order_arms},
        "reroll_by_arm": {name: int(reroll_arm.get(name, 0))
                          for name in order_arms},
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


def summarize(rows: Iterable[Any], *, header: Mapping[str, Any] | None = None,
              controls: Mapping[str, Any] | None = None,
              parity: Mapping[str, Any] | None = None,
              close_row: Mapping[str, Any] | None = None,
              null_exposure: Mapping[str, Any] | None = None) -> str:
    """The Markdown report of DESIGN §9.

    `rows` is any iterable — `iter_rows_latest` over a written ledger is
    what the CLI hands it — and what is kept per row is `slim_row`.
    """
    header = dict(header or {})
    dicts = [slim_row(row) for row in rows]
    attributed = attribution(
        dicts, rule_order=header.get("rules", ()),
        rung_order=header.get("rungs", ()),
        arm_order=header.get("arms", ()))
    hist = histograms(dicts)
    bands = stream_band_table(dicts)
    agree = agreement_table(dicts)

    fields: list[list[Any]] = [
        ["run dir", header.get("run_dir")],
        ["format", header.get("format_ref")],
        ["captures", len(header.get("captures", []) or [])],
        ["seed", header.get("seed")],
        ["workers", header.get("workers")],
        ["targets from", header.get("targets_from")],
        ["knobs from", header.get("knobs_from")],
        ["halo", f"{header.get('halo_cells')} "
                 f"({header.get('halo_from', 'defaults')})"],
        ["non-blind", header.get("non_blind")],
        ["arms", ", ".join(header.get("arms", []) or [])],
        ["rules", ", ".join(header.get("rules", []) or [])],
        ["rungs", ", ".join(header.get("rungs", []) or [])],
        ["rows", len(dicts)]]
    # A stopped pass has to SAY it stopped.  `ledger.md` is the artefact
    # that gets pasted into an experiment log, and without this row a
    # pass the operator interrupted reads exactly like an exhausted one
    # — a smaller `rows` count and nothing saying why (2026-09-07).  The
    # row appears only when it is set, so an ordinary summary is the one
    # it always was, byte for byte.
    if header.get("stop_reason") == STOP_INTERRUPTED:
        fields.append(["stopped", f"{header['stop_reason']} — "
                       f"{header.get('keys_done')} attempt(s) done, "
                       f"{header.get('keys_skipped')} skipped"])
    fields += [["generations run", header.get("generations_run")],
               ["seconds", None if header.get("seconds") is None
                else round(float(header["seconds"]), 1)]]
    parts: list[str] = ["# analyzer ledger", ""]
    parts.append(_table(["field", "value"], fields))

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
    parts += ["", "Arm attribution — which arm's EVIDENCE certified: the "
              "selection's arm set, or the re-roll's one arm (counted "
              "under that arm).  A FIRST-SUCCESS marginal, not a "
              "leave-one-out: the ladder stops at the first certificate "
              "and the re-roll runs in battery order.", ""]
    parts.append(_table(
        ["arm", "first-success", "only this arm", "via re-roll"],
        [[name, attributed["first_success_by_arm"].get(name, 0),
          attributed["only_by_arm"].get(name, 0),
          attributed["reroll_by_arm"].get(name, 0)]
         for name in attributed["arm_order"]] or [["—", 0, 0, 0]]))

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


#: The six fields a verdict map reads; a row's other megabyte is not
#: a picture.  `page` is one of them since 2026-09-13 (review F14): the
#: two faces of a duplex sheet carry the same tile coordinates, so
#: dropping it merged sheet J's pages into one picture in fold order.
_MAP_FIELDS = ("page", "ty", "tx", "stream_id", "verdict",
               "certified_by_production")


def render_maps(rows: Iterable[Any], out_dir: Path | str, *,
                tiles_yx: tuple[int, int] | None = None,
                live_pages: Sequence[int] | None = None,
                scale: int = 6) -> list[Path]:
    """One PNG per printed face and plane: the verdict map.

    The bits-wrong map is an oracle picture and belongs to the offline
    scorer, which draws it beside its own report (`analyzer.score`).

    Six fields a row, so this streams a ledger without holding one.

    A pass over ONE page keeps the bare `verdict-{stream}.png` the
    sheet-H and sheet-I records name; a duplex pass spells the face,
    because page 0 and page 1 of sheet J are both 53x37 and would
    otherwise overwrite each other tile for tile.

    WHICH PASS IS WHICH is the RUN's question, not the rows' (2026-09-13).
    A duplex pass whose surviving rows all sit on page 1 is still a
    duplex pass, and naming its maps `verdict-C.png` both hid that and
    put them where page 0's belong.  `live_pages` is the run's own
    (`RunInputs.live_pages`) and the CLI hands it over; without it the
    rows decide, and a page above 0 among them is enough to spell every
    face.
    """
    from PIL import Image

    dicts = []
    for row in rows:
        record = _as_dict(row)
        dicts.append({name: record.get(name) for name in _MAP_FIELDS})

    if not dicts:
        return []
    if tiles_yx is None:
        tiles_yx = (max(int(row["ty"]) for row in dicts) + 1,
                    max(int(row["tx"]) for row in dicts) + 1)
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    pages = sorted({int(row.get("page") or 0) for row in dicts}
                   if live_pages is None
                   else {int(page) for page in live_pages})
    one_face = pages == [0]
    faces = sorted({(int(row.get("page") or 0), str(row["stream_id"]))
                    for row in dicts})
    for page, stream in faces:
        verdict = np.full((height, width, 3), _VERDICT_RGB["untargeted"],
                          np.uint8)
        for row in dicts:
            if int(row.get("page") or 0) != page:
                continue
            if str(row["stream_id"]) != stream:
                continue
            ty, tx = int(row["ty"]), int(row["tx"])
            name = str(row.get("verdict"))
            if row.get("certified_by_production") and name != "certified":
                name = "production"
            verdict[ty, tx] = _VERDICT_RGB.get(name, _VERDICT_RGB["open"])
        path = out_dir / (f"verdict-{stream}.png" if one_face
                          else f"verdict-p{page}-{stream}.png")
        Image.fromarray(verdict).resize(
            (width * scale, height * scale), Image.NEAREST).save(path)
        written.append(path)
    return written
