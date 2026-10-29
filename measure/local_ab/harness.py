#!/usr/bin/env python
"""The battery: one crop decode, then both arms over its frozen store.

    PYTHONPATH=src:. <python> -m measure.local_ab.harness --case I-tl \\
        --workers 4 --decode-diag 8026 \\
        --evidence-root <evidence> --out build/local-ab

Order of operations, and why:

1. **Ground truth first.** The emitted payload is sha-gated against the
   generation manifest and re-encoded through ``src/holo``'s own
   generation arithmetic into per-tile user bits
   (``crop_parity._gt.reconstruct``, the pooled-CMY8 branch). Nothing is
   reported if that refuses.
2. **One decode**, in process, over the case's three crops — the CLI's
   own parser, the CLI's own request, ``engine._Engine(...).run()``. The
   engine IS the store (``class _Engine(_Store)``), so after ``run()``
   the covering lanes, placements, colour rows and standing certificates
   are all still there.
3. **The decode's own certificates are audited** against ground truth
   before the A/B is allowed to start. A wrong certificate here is a
   receiver correctness failure and voids the battery (exit 2).
4. **The A/B**, over a store nothing further mutates. Both arms and the
   null run on identical components; see ``_ab.py``.
5. **Every A/B certificate is audited** the same way.

REPLAY MODE (``--replay``, added 2026-08-31 with the hybrid row) runs
both arms AND ``local_ctx.prepare_local`` ITSELF — the union-then-lanes
row as it now stands — on every subject, and reports two things that
must not be confused:

* the hybrid's DEFINING property, which is store-independent: the row
  certifies exactly where ``union or per_origin`` does, by the same lane;
* PARITY with what this measurement recorded, which is only meaningful
  on subjects both runs had. A decode at more than one worker is
  path-dependent, so a tile the ordinary rows have since certified is
  absent from the population rather than failed.

Steps 1-3 are unchanged; the recorded report is read, never rewritten,
and the replay lands beside it as ``<case>-replay.json/.md``.

EXIT CODES: 0 healthy · 2 a wrong certificate (an arm, the row, the
decode, or a null that certified) · 3 ground truth refused validation ·
4 the row is not the arms' union — a row defect · 5 a subject both runs
had did not reproduce its recorded verdict.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np

from holo.receiver.descriptor import PluginDescriptor
from holo.receiver.plugins import local_ctx

from measure import _evidence

from . import _ab, _cases, _paths


def _reconstruct_gt():
    """The emitted payload, sha-gated, re-encoded to per-tile user bits."""
    _paths.install_src()
    from measure.crop_parity import _gt

    payload = _gt.load_payload(_cases.evidence(_cases.PAYLOAD), _cases.PAYLOAD_SHA256,
                               _cases.PAYLOAD_BYTES)
    return _gt, _gt.reconstruct(_cases.FORMAT_REF, payload, pages=1)


def _audit(gt_module, gt, observed: dict, label: str) -> dict:
    """Every observed address must equal the re-encoded emitted payload."""
    wrong: list[dict] = []
    for address in sorted(observed):
        match, n_bad = gt_module.check_bits(gt, address, observed[address])
        if not match:
            wrong.append({"address": list(address), "n_bits_differ": n_bad})
    return {"label": label, "n_checked": len(observed), "n_wrong": len(wrong),
            "wrong": wrong[:20]}


def _without_local_row(engine) -> tuple[PluginDescriptor, ...]:
    """The standing descriptor set minus the row under test.

    THIS IS THE EXPERIMENT'S CONTROL, not an optimisation. `tiles.local`
    IS the union arm. If the decode runs it, every tile the union would
    win is certified before the A/B starts and is then excluded from the
    subject population by `has_certificate` — so the measurement would
    show the union winning nothing and the per-origin arm winning
    whatever it could pick out of the union's leftovers. That is a
    guaranteed bias in the challenger's favour.

    Detaching the row leaves the population EXACTLY what production arms
    it on — `ARMING_STAGES` is (scan, union, retry150), all of which
    still run — and lets both arms start from the same store.

    What it costs, stated: in production a local certificate can feed
    the next tile's local head through `store.certificates()`. Neither
    arm gets that here. It is withheld from both equally.
    """
    return tuple(descriptor for descriptor in engine.DESCRIPTORS
                 if descriptor.name != local_ctx.PLUGIN)


def _decode(case: _cases.Case, record: dict, run_dir: Path, workers: int,
            diag_port: int | None,
            budget_s: float) -> tuple[object, list, object, float, bool]:
    """The CLI's own decode path, with the store kept and the row detached.

    ``budget_s`` stops the engine loop after that many wall seconds and
    keeps the store. It exists because this instrument shares a machine:
    measured 2026-08-31 at load 75, the `I-tl` decode advanced 34 seconds
    of job CPU in 28 wall minutes, with its remaining queue almost
    entirely `place`/`refine.color`/`revisit`. Without a budget there is
    no measurement on such a machine.

    It is NOT a cap on evidence. Both arms share one store, so a less
    converged store moves the two arms together and leaves the
    comparison alone; and `_ab.armed_addresses` keeps the population
    honest by admitting only addresses an ordinary attempt has actually
    FAILED on, never ones the decode simply had not reached.
    """
    import os
    import signal
    import threading

    from holo.receiver import cli, engine

    def _stop() -> None:
        # A REAL SIGINT, not ``_thread.interrupt_main``. Measured
        # 2026-08-31: with ``interrupt_main`` the `I-tl` decode ran nine
        # minutes past a 2400 s budget without stopping — the engine's
        # main thread sits in ``concurrent.futures.wait`` and never took
        # the simulated interrupt. ``os.kill`` delivers to the process,
        # the runtime hands it to the main thread, and the wait returns.
        os.kill(os.getpid(), signal.SIGINT)

    argv = ["decode"]
    for key in sorted(record["crops"]):
        argv.append(record["crops"][key]["path"])
    for key in sorted(record["crops"]):
        argv += ["--dpi", str(record["crops"][key]["dpi"])]
    argv += ["--format", _cases.FORMAT_REF, "--no-close",
             "--out", str(run_dir / "payload.bin"),
             "--run-dir", str(run_dir), "--workers", str(workers)]
    if diag_port is not None:
        argv += ["--diag", str(diag_port)]
    args = cli._build_parser().parse_args(argv)
    request = cli._request(args)
    events: list = []
    started = time.perf_counter()
    standing = engine.DESCRIPTORS
    engine.DESCRIPTORS = _without_local_row(engine)
    timer = threading.Timer(budget_s, _stop) if budget_s > 0 else None
    truncated = False
    store = engine._Engine(request, events)
    result = None
    try:
        if timer is not None:
            timer.start()
        result = store.run()
    except KeyboardInterrupt:
        truncated = True
        print(f"local_ab: decode stopped at the {budget_s:.0f} s budget; "
              f"{store.n_certificates()} certificates standing", flush=True)
    finally:
        if timer is not None:
            timer.cancel()
        engine.DESCRIPTORS = standing
    return (store, events, result, time.perf_counter() - started, truncated)


def _decode_certificates(store: object) -> dict:
    return {key: np.asarray(certificate.user_bits)
            for key, certificate in store.certificates().items()}


def _agrees(row: dict, outcome: _ab.SubjectResult) -> bool:
    """Is the row's verdict the two arms' verdict?

    Since the hybrid landed (2026-08-31) `tiles.local` attempts the
    union FIRST and, on its failure, each covering lane alone. So the
    row's standard is `union or per_origin` — the either column — not
    the union alone. Before the hybrid this was the union alone, and
    the recorded reports were produced under that rule.
    """
    return bool(row.get("certified")) == bool(
        outcome.union.certified or outcome.per_origin.certified)


# --- the replay: the CHANGED row against the recorded verdict ----------


def _recorded(case: _cases.Case, out: Path) -> dict:
    """The measurement's own per-subject verdicts, keyed by subject.

    Read-only, and never rewritten: the recorded reports are the record
    the hybrid was ruled from, so a replay compares ITSELF to them
    rather than restating them.
    """
    path = out / "reports" / f"{case.case_id}.json"
    if not path.is_file():
        raise SystemExit(f"local_ab: no recorded report at {path}; the "
                         f"replay compares against the measurement")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {(row["ty"], row["tx"], row["stream"], row["ppc"]): row
            for row in payload["subjects"]}


def _expected(row: dict) -> tuple[bool, str | None]:
    """What the hybrid should do on a recorded subject, and who wins.

    The union goes first, so a subject the union took is a union win
    however well the lanes would also have done; only where the union
    failed does a lane get to answer. That is the row's order, and it
    is what makes the expectation a prediction rather than a summary.
    """
    if row["union_certified"]:
        return True, f"union:{row['n_components']}"
    if row["per_origin_certified"]:
        return True, row["per_origin_winner"]
    return False, None


def _replay_case(store: object, found: tuple, case: _cases.Case,
                 out: Path) -> tuple[list[dict], dict, dict, dict]:
    """The two arms AND the changed row, on one store, per subject.

    Both halves are needed, and for different reasons.

    THE ARMS give the hybrid's DEFINING property, and it holds whatever
    store this run happens to land on: the row must certify exactly
    where `union or per_origin` does, and by the same lane. That is
    store-independent, so it is the test that cannot be spoiled by a
    decode converging differently from the measurement's.

    THE RECORD comparison is the parity to the measurement itself, and
    it is only meaningful on subjects BOTH runs had. A decode at more
    than one worker is path-dependent — an early certificate suppresses
    windows through done-geometry, so two exhaustive runs can stop at
    different fixed points — and a tile the ordinary rows have since
    certified is no longer residue at all. Those subjects are reported
    as absent, never as failures: the row cannot be blamed for not
    replaying a subject that no longer exists.
    """
    recorded = _recorded(case, out)
    rows: list[dict] = []
    minted: dict = {}
    null_minted: dict = {}
    for index, subject in enumerate(found, 1):
        key = (subject.ty, subject.tx, subject.stream_id, str(subject.ppc))
        components, build_cpu = _ab.build_components(store, subject)
        union = _ab.run_union(store, subject, components)
        per_origin = _ab.run_per_origin(store, subject, components)
        null = _ab.run_null(store, subject, components)
        outcome = _ab.run_row(store, subject)
        for arm in (union, per_origin):
            if arm.bits is not None:
                minted[subject.address] = arm.bits
        if outcome is not None and outcome.bits is not None:
            minted[subject.address] = outcome.bits
        if null.bits is not None:
            null_minted[null.address] = null.bits
        arms_certified = union.certified or per_origin.certified
        arms_winner = (f"union:{len(components)}" if union.certified
                       else per_origin.winner)
        got_certified = bool(outcome is not None and outcome.certified)
        winner = None if outcome is None else outcome.winner
        prior = recorded.get(key)
        want_certified, want_winner = (
            (None, None) if prior is None else _expected(prior))
        rows.append({
            "ty": subject.ty, "tx": subject.tx,
            "stream": subject.stream_id, "ppc": str(subject.ppc),
            "n_lanes": len(subject.lanes), "n_components": len(components),
            "prepared": outcome is not None,
            "n_attempts": 0 if outcome is None else len(outcome.attempts),
            "certified": got_certified, "winner": winner,
            "union_certified": union.certified,
            "per_origin_certified": per_origin.certified,
            "per_origin_winner": per_origin.winner,
            "null_certified": null.certified,
            "row_is_arms_union": (got_certified == arms_certified
                                  and (not got_certified
                                       or winner == arms_winner)),
            "recorded_in_measurement": prior is not None,
            "expected_certified": want_certified,
            "expected_winner": want_winner,
            "matches_record": (prior is not None
                               and got_certified == want_certified
                               and (not got_certified
                                    or winner == want_winner)),
            "build_cpu_s": round(build_cpu, 3),
            "cpu_s": 0.0 if outcome is None else round(outcome.cpu_seconds, 3),
        })
        print(f"  [{index}/{len(found)}] ({subject.ty:2d},{subject.tx:2d}) "
              f"{subject.stream_id} ppc={subject.ppc} -> row "
              f"{'CERT ' + str(winner) if got_certified else 'none'} | arms "
              f"{'CERT ' + str(arms_winner) if arms_certified else 'none'} | "
              f"record "
              f"{want_winner if want_certified else
                 ('none' if prior is not None else 'ABSENT')}", flush=True)
    shared = [row for row in rows if row["recorded_in_measurement"]]
    summary = {
        "n_subjects": len(rows),
        "n_shared_with_measurement": len(shared),
        "n_certified": sum(1 for row in rows if row["certified"]),
        "n_union_wins": sum(1 for row in rows if row["certified"]
                            and str(row["winner"]).startswith("union:")),
        "n_lane_wins": sum(1 for row in rows if row["certified"]
                           and not str(row["winner"]).startswith("union:")),
        "arms_union_adds": sum(1 for row in rows if row["union_certified"]),
        "arms_per_origin_adds": sum(1 for row in rows
                                    if row["per_origin_certified"]),
        "arms_either_adds": sum(1 for row in rows
                                if row["union_certified"]
                                or row["per_origin_certified"]),
        "row_equals_arms": sum(1 for row in rows if row["row_is_arms_union"]),
        "null_certificates": sum(1 for row in rows if row["null_certified"]),
        "n_shared_matching": sum(1 for row in shared
                                 if row["matches_record"]),
        "n_shared_expected": sum(1 for row in shared
                                 if row["expected_certified"]),
        "attempts_made": sum(row["n_attempts"] for row in rows),
        "row_cpu_seconds": round(sum(row["cpu_s"] for row in rows), 1),
        "build_cpu_seconds": round(sum(row["build_cpu_s"] for row in rows), 1),
    }
    return rows, summary, minted, null_minted


def _rows(results: list[_ab.SubjectResult]) -> list[dict]:
    out: list[dict] = []
    for result in results:
        subject = result.subject
        out.append({
            "page": subject.page, "ty": subject.ty, "tx": subject.tx,
            "stream": subject.stream_id, "ppc": str(subject.ppc),
            "n_lanes": len(subject.lanes), "n_components": result.n_components,
            "class": _ab.classify(result),
            "union_certified": result.union.certified,
            "per_origin_certified": result.per_origin.certified,
            "per_origin_winner": result.per_origin.winner,
            "null_certified": result.null.certified,
            "recorded_local150": result.recorded,
            "build_cpu_s": round(result.build_cpu_seconds, 3),
            "union_cpu_s": round(result.union.cpu_seconds, 3),
            "per_origin_cpu_s": round(result.per_origin.cpu_seconds, 3),
            "null_cpu_s": round(result.null.cpu_seconds, 3),
            "union_attempts": [list(row) for row in result.union.attempts],
            "per_origin_attempts": [list(row)
                                    for row in result.per_origin.attempts],
        })
    return out


def _first_cert_cpu(result: _ab.SubjectResult) -> float:
    """Per-origin CPU if the schedule stopped at the first certificate.

    Summed from the per-attempt thread seconds, never prorated: a
    below-floor lane costs almost nothing and a 150-iteration failure
    costs the most, so a proportional split would misprice both.
    """
    rows = result.per_origin.attempts
    if not rows or result.per_origin.winner is None:
        return result.per_origin.cpu_seconds
    index = next(i for i, row in enumerate(rows)
                 if row[0] == result.per_origin.winner)
    return sum(row[3] for row in rows[:index + 1])


def _summary(results: list[_ab.SubjectResult]) -> dict:
    classes = {"both": 0, "union_only": 0, "per_origin_only": 0,
               "neither": 0}
    for result in results:
        classes[_ab.classify(result)] += 1
    union_adds = sum(1 for r in results if r.union.certified)
    per_origin_adds = sum(1 for r in results if r.per_origin.certified)
    either = sum(1 for r in results
                 if r.union.certified or r.per_origin.certified)
    agree = [r for r in results if r.recorded is not None]
    agree_ok = sum(
        1 for r in agree
        if (r.recorded == "certified") == r.union.certified)
    winners: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    for result in results:
        if result.per_origin.winner is not None:
            winners[result.per_origin.winner] = (
                winners.get(result.per_origin.winner, 0) + 1)
        for _label, outcome, _iters, _cpu in result.per_origin.attempts:
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        for _label, outcome, _iters, _cpu in result.union.attempts:
            outcomes["union/" + outcome] = (
                outcomes.get("union/" + outcome, 0) + 1)
    return {
        "n_subjects": len(results),
        "n_tiles": len({(r.subject.ty, r.subject.tx) for r in results}),
        "classes": classes,
        "per_origin_winning_lane": dict(sorted(winners.items())),
        "attempt_outcomes": dict(sorted(outcomes.items())),
        "lane_counts": dict(sorted(
            {str(len(r.subject.lanes)): sum(
                1 for x in results
                if len(x.subject.lanes) == len(r.subject.lanes))
             for r in results}.items())),
        "union_adds": union_adds,
        "per_origin_adds": per_origin_adds,
        "either_adds": either,
        "null_certificates": sum(1 for r in results if r.null.certified),
        "cpu_seconds": {
            "component_build_shared": round(
                sum(r.build_cpu_seconds for r in results), 1),
            "union_attempts": round(
                sum(r.union.cpu_seconds for r in results), 1),
            "per_origin_attempts_exhaustive": round(
                sum(r.per_origin.cpu_seconds for r in results), 1),
            "per_origin_attempts_first_cert_stop": round(
                sum(_first_cert_cpu(r) for r in results), 1),
            "null_attempts": round(sum(r.null.cpu_seconds for r in results),
                                   1),
        },
        "recorded_local150_comparable": len(agree),
        "recorded_local150_agree": agree_ok,
    }


def _markdown(case: _cases.Case, payload: dict) -> str:
    record = payload
    summary = payload["summary"]
    classes = summary["classes"]
    cpu = summary["cpu_seconds"]
    lines = [
        f"# local_ab — {case.case_id}",
        "",
        f"*{case.note}*",
        "",
        f"- format `{_cases.FORMAT_REF}`, "
        f"{len(record['crops'])} crops (one per 2400 dpi capture)",
        f"- crop cell rectangle `{record['cell_bbox']}` (x-first, "
        f"half-open), halo {case.halo_cells} cells",
        f"- decode: {payload['decode']['n_certificates']} certificates in "
        f"{payload['decode']['wall_seconds']:.0f} s wall "
        f"({payload['decode']['workers']} workers)",
        f"- ground truth: {payload['audits'][0]['n_checked']} decode "
        f"certificates checked, {payload['audits'][0]['n_wrong']} wrong",
        "",
        "## Verdict",
        "",
        "| arm | certificates | share of subjects |",
        "|---|---:|---:|",
    ]
    n = max(1, summary["n_subjects"])
    lines += [
        f"| union (as landed) | {summary['union_adds']} | "
        f"{100 * summary['union_adds'] / n:.1f}% |",
        f"| per-origin (one attempt per lane) | "
        f"{summary['per_origin_adds']} | "
        f"{100 * summary['per_origin_adds'] / n:.1f}% |",
        f"| either | {summary['either_adds']} | "
        f"{100 * summary['either_adds'] / n:.1f}% |",
        f"| **N0 null** (wrong address) | **{summary['null_certificates']}** "
        f"| — |",
        "",
        "| both | union only | per-origin only | neither |",
        "|---:|---:|---:|---:|",
        f"| {classes['both']} | {classes['union_only']} | "
        f"{classes['per_origin_only']} | {classes['neither']} |",
        "",
        f"{summary['n_subjects']} subjects over "
        f"{summary['n_tiles']} tile positions.",
        "",
        "## CPU",
        "",
        "| item | thread seconds |",
        "|---|---:|",
        f"| component build (SHARED by both arms) | "
        f"{cpu['component_build_shared']} |",
        f"| union attempts | {cpu['union_attempts']} |",
        f"| per-origin attempts, every lane | "
        f"{cpu['per_origin_attempts_exhaustive']} |",
        f"| per-origin attempts, stop at first certificate | "
        f"{cpu['per_origin_attempts_first_cert_stop']} |",
        f"| null attempts | {cpu['null_attempts']} |",
        "",
        "## Audits",
        "",
        "| audit | checked | wrong |",
        "|---|---:|---:|",
    ]
    for audit in payload["audits"]:
        lines.append(f"| {audit['label']} | {audit['n_checked']} | "
                     f"{audit['n_wrong']} |")
    lines.append("")
    if summary["recorded_local150_comparable"]:
        lines += [
            "The decode itself ran `tiles.local` on "
            f"{summary['recorded_local150_comparable']} of these attempts "
            "with an identical component signature; the union arm "
            f"reproduced its verdict on "
            f"{summary['recorded_local150_agree']}.", ""]
    verified = payload.get("row_verification", [])
    agree = sum(1 for row in verified if row.get("agrees"))
    lines += [
        f"`local_ctx.prepare_local` — the callable the engine would have "
        f"dispatched — was run on {len(verified)} of the same subjects and "
        f"agreed with the union arm on **{agree}**.",
        "",
        "## Subject census",
        "",
        "Why residue did not arm, per rung.",
        "",
        "| rung (px/cell) | uncertified | never attempted | no lane | "
        "one lane | no certified neighbour | **armed** |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for ppc, counts in payload["subject_census"].items():
        lines.append(
            f"| {ppc} | {counts['uncertified']} | "
            f"{counts['never_attempted']} | {counts['no_lane']} | "
            f"{counts['one_lane']} | "
            f"{counts['ineligible_no_certified_neighbour']
               + counts['ineligible_empty_reach']} | "
            f"**{counts['kept']}** |")
    lines.append("")
    outcomes = summary.get("attempt_outcomes", {})
    if outcomes:
        lines += ["Per-attempt outcomes (a `below_attempt_floor` row is a "
                  "lane whose own observed set does not reach the code's "
                  "support floor — something the union's combined "
                  "observation can clear):", "",
                  "| attempt outcome | count |", "|---|---:|"]
        for name, count in outcomes.items():
            lines.append(f"| `{name}` | {count} |")
        lines.append("")
    winners = summary.get("per_origin_winning_lane", {})
    if winners:
        lines += ["| per-origin winning lane | wins |", "|---|---:|"]
        for name, count in winners.items():
            lines.append(f"| `{name}` | {count} |")
        lines.append("")
    disagree = [row for row in payload["subjects"]
                if row["class"] in ("union_only", "per_origin_only")]
    if disagree:
        lines += ["## Where the arms disagree", "",
                  "| tile | stream | rung | lanes | class | winner |",
                  "|---|---|---:|---:|---|---|"]
        for row in disagree:
            lines.append(
                f"| ({row['ty']}, {row['tx']}) | {row['stream']} | "
                f"{row['ppc']} | {row['n_lanes']} | {row['class']} | "
                f"{row['per_origin_winner'] or '—'} |")
        lines.append("")
    return "\n".join(lines)


def _replay_markdown(case: _cases.Case, payload: dict) -> str:
    summary = payload["replay_summary"]
    decode = payload["decode"]
    lines = [
        f"# local_ab — {case.case_id}, REPLAY of the hybrid row",
        "",
        "*`tiles.local` after the union-then-lanes hybrid landed, run "
        "through `local_ctx.prepare_local` on the subjects the "
        "measurement scored, and compared to what the measurement "
        "recorded.*",
        "",
        f"- decode: {decode['n_certificates']} certificates in "
        f"{decode['wall_seconds']:.0f} s wall ({decode['workers']} "
        f"workers), status `{decode['status']}`",
        f"- ground truth: {payload['audits'][0]['n_checked']} decode "
        f"certificates checked, {payload['audits'][0]['n_wrong']} wrong",
        "",
        "## The hybrid's defining property, on this store",
        "",
        "Store-independent: whatever this decode converged to, the row "
        "must certify exactly where `union or per-origin` does, by the "
        "same lane.",
        "",
        "| item | count |",
        "|---|---:|",
        f"| subjects | {summary['n_subjects']} |",
        f"| union arm | {summary['arms_union_adds']} |",
        f"| per-origin arm | {summary['arms_per_origin_adds']} |",
        f"| either arm | {summary['arms_either_adds']} |",
        f"| **the row** | **{summary['n_certified']}** |",
        f"| **subjects where row == either arm, same lane** | "
        f"**{summary['row_equals_arms']} / {summary['n_subjects']}** |",
        f"| won by the row's union attempt | {summary['n_union_wins']} |",
        f"| won by the row's lane pass | {summary['n_lane_wins']} |",
        f"| **N0 null certificates** | "
        f"**{summary['null_certificates']}** |",
        f"| attempts the row made | {summary['attempts_made']} |",
        f"| row CPU, build included | {summary['row_cpu_seconds']} s |",
        f"| of which component build | {summary['build_cpu_seconds']} s |",
        "",
        "## Parity with the recorded measurement",
        "",
        "Only subjects BOTH runs had. A decode at more than one worker "
        "is path-dependent, so a tile the ordinary rows have since "
        "certified is simply no longer residue — absent, not failed.",
        "",
        "| item | count |",
        "|---|---:|",
        f"| subjects shared with the measurement | "
        f"{summary['n_shared_with_measurement']} of "
        f"{summary['n_subjects']} |",
        f"| of those, certificates the measurement predicts | "
        f"{summary['n_shared_expected']} |",
        f"| **matching the measurement (verdict AND winner)** | "
        f"**{summary['n_shared_matching']} / "
        f"{summary['n_shared_with_measurement']}** |",
        "",
        "## Audits",
        "",
        "| audit | checked | wrong |",
        "|---|---:|---:|",
    ]
    for audit in payload["audits"]:
        lines.append(f"| {audit['label']} | {audit['n_checked']} | "
                     f"{audit['n_wrong']} |")
    lines += ["", "## Every certificate", "",
              "| tile | stream | rung | row's winner | union arm | "
              "per-origin arm | measured |", "|---|---|---:|---|---|---|---|"]
    for row in payload["subjects"]:
        if not row["certified"] and not row["expected_certified"]:
            continue
        lines.append(
            f"| ({row['ty']}, {row['tx']}) | {row['stream']} | "
            f"{row['ppc']} | {row['winner'] or '—'} | "
            f"{'yes' if row['union_certified'] else 'no'} | "
            f"{row['per_origin_winner'] or 'no'} | "
            f"{row['expected_winner'] if row['recorded_in_measurement']
               else 'ABSENT'} |")
    lines.append("")
    broken = [row for row in payload["subjects"]
              if not row["row_is_arms_union"]]
    if broken:
        lines += ["## Subjects where the row is NOT the arms' union", "",
                  "| tile | stream | rung | row | union | per-origin |",
                  "|---|---|---:|---|---|---|"]
        for row in broken:
            lines.append(
                f"| ({row['ty']}, {row['tx']}) | {row['stream']} | "
                f"{row['ppc']} | {row['winner'] or 'none'} | "
                f"{'yes' if row['union_certified'] else 'no'} | "
                f"{row['per_origin_winner'] or 'no'} |")
        lines.append("")
    stale = [row for row in payload["subjects"]
             if row["recorded_in_measurement"] and not row["matches_record"]]
    if stale:
        lines += ["## Shared subjects that did NOT reproduce", "",
                  "| tile | stream | rung | got | measured |",
                  "|---|---|---:|---|---|"]
        for row in stale:
            lines.append(
                f"| ({row['ty']}, {row['tx']}) | {row['stream']} | "
                f"{row['ppc']} | {row['winner'] or 'none'} | "
                f"{row['expected_winner'] or 'none'} |")
        lines.append("")
    return "\n".join(lines)


def run_case(case: _cases.Case, workers: int, diag_port: int | None,
             fresh: bool, verify: int, budget_s: float,
             out: Path, replay: bool = False) -> tuple[int, dict]:
    gt_module, gt = _reconstruct_gt()
    record = _cases.prepare(case, out / "crops")
    run_dir = out / "runs" / case.case_id
    if fresh and run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    store, events, result, wall, truncated = _decode(
        case, record, run_dir, workers, diag_port, budget_s)
    audits = [_audit(gt_module, gt, _decode_certificates(store),
                     "decode certificates")]
    if audits[0]["n_wrong"]:
        return 2, {"audits": audits, "case": case.case_id}

    armed = _ab.armed_addresses(events)
    found, census = _ab.subjects(store, case.target_positions, armed)
    if replay:
        rows, summary, minted, null_minted = _replay_case(store, found, case,
                                                          out)
        audits.append(_audit(gt_module, gt, minted, "replay certificates"))
        audits.append(_audit(gt_module, gt, null_minted,
                             "N0 null certificates"))
        payload = {
            "case": case.case_id, "mode": "replay",
            "format_ref": _cases.FORMAT_REF,
            "decode": {"wall_seconds": wall, "workers": workers,
                       "status": ("truncated" if truncated
                                  else str(result.status)),
                       "n_certificates": store.n_certificates(),
                       "budget_seconds": budget_s,
                       "stopped_at_budget": truncated,
                       "n_armed_addresses": len(armed),
                       "local_row_in_decode": False,
                       "run_dir": str(run_dir)},
            "subject_census": census,
            "replay_summary": summary,
            "audits": audits,
            "subjects": rows,
        }
        code = 0
        if audits[1]["n_wrong"] or summary["null_certificates"]:
            code = 2
        if summary["row_equals_arms"] != summary["n_subjects"]:
            # The hybrid's defining property broke. This one is on the
            # row, and it does not depend on which store the decode
            # landed on.
            code = 4
        if summary["n_shared_matching"] != summary["n_shared_with_measurement"]:
            # Parity to the recorded measurement broke on a subject BOTH
            # runs had. Reported separately from the property above,
            # because a store that converged differently is not a row
            # defect and must not be read as one.
            code = 5
        return code, payload

    verified: list[dict] = []
    results: list[_ab.SubjectResult] = []
    minted: dict = {}
    null_minted: dict = {}
    for index, subject in enumerate(found, 1):
        outcome = _ab.measure(store, subject)
        results.append(outcome)
        for arm in (outcome.union, outcome.per_origin):
            if arm.bits is not None:
                minted[subject.address] = arm.bits
        if outcome.null.bits is not None:
            null_minted[outcome.null.address] = outcome.null.bits
        if index <= verify:
            row = _ab.verify_row(store, subject)
            row.update({"ty": subject.ty, "tx": subject.tx,
                        "stream": subject.stream_id,
                        "ppc": str(subject.ppc),
                        "arm_certified": (outcome.union.certified
                                          or outcome.per_origin.certified),
                        "agrees": _agrees(row, outcome)})
            verified.append(row)
        print(f"  [{index}/{len(found)}] ({subject.ty:2d},{subject.tx:2d}) "
              f"{subject.stream_id} ppc={subject.ppc} "
              f"lanes={len(subject.lanes)} -> {_ab.classify(outcome)}",
              flush=True)

    audits.append(_audit(gt_module, gt, minted, "A/B certificates"))
    audits.append(_audit(gt_module, gt, null_minted, "N0 null certificates"))
    payload = {
        "case": case.case_id, "note": case.note,
        "format_ref": _cases.FORMAT_REF,
        "cell_bbox": record["cell_bbox"],
        "crops": record["crops"],
        "production_residue_in_target": len(
            record["production_residue_in_target"]),
        "decode": {"wall_seconds": wall, "workers": workers,
                   "status": ("truncated" if truncated
                              else str(result.status)),
                   "n_certificates": store.n_certificates(),
                   "budget_seconds": budget_s,
                   "stopped_at_budget": truncated,
                   "n_armed_addresses": len(armed),
                   "local_row_in_decode": False,
                   "run_dir": str(run_dir)},
        "subject_census": census,
        "row_verification": verified,
        "summary": _summary(results),
        "audits": audits,
        "subjects": _rows(results),
    }
    code = 0
    if audits[1]["n_wrong"] or payload["summary"]["null_certificates"]:
        code = 2
    if any(not row.get("agrees") for row in verified):
        code = 2                      # the arm is not the row: void
    return code, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True,
                        help=f"one of {sorted(_cases.CASES_BY_ID)}")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--decode-diag", type=int, default=None,
                        metavar="PORT",
                        help="serve the live decode viewer on this port")
    parser.add_argument("--decode-seconds", type=float, default=0.0,
                        help="stop the decode after this many wall "
                             "seconds and measure the store as it "
                             "stands (0 = run to exhaustion)")
    parser.add_argument("--verify", type=int, default=6,
                        help="subjects on which local_ctx.prepare_local "
                             "itself is run and compared to the union arm")
    parser.add_argument("--fresh", action="store_true",
                        help="delete the run dir before decoding")
    parser.add_argument("--replay", action="store_true",
                        help="run local_ctx.prepare_local itself on every "
                             "subject and compare to the recorded report "
                             "instead of running the two arms")
    _evidence.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True,
                        help="artefact directory (crops/, runs/, reports/)")
    args = parser.parse_args(argv)
    _paths.use_evidence_root(args.evidence_root)
    _paths.evidence_root()
    if args.case not in _cases.CASES_BY_ID:
        raise SystemExit(f"local_ab: unknown case {args.case!r}; declared: "
                         f"{sorted(_cases.CASES_BY_ID)}")
    case = _cases.CASES_BY_ID[args.case]
    try:
        code, payload = run_case(case, args.workers, args.decode_diag,
                                 args.fresh, args.verify,
                                 args.decode_seconds, args.out,
                                 args.replay)
    except Exception as exc:                          # GT refusal included
        from measure.crop_parity._gt import GTValidationError

        if isinstance(exc, GTValidationError):
            print(f"local_ab: {exc}")
            return 3
        raise
    out_dir = args.out / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    # A replay NEVER overwrites the recorded report: the measurement is
    # the record the hybrid was ruled from, and a replay is evidence
    # about the row, not a re-issue of that record.
    stem = f"{case.case_id}-replay" if args.replay else case.case_id
    (out_dir / f"{stem}.json").write_text(
        json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8")
    if args.replay and "replay_summary" in payload:
        text = _replay_markdown(case, payload)
        (out_dir / f"{stem}.md").write_text(text, encoding="utf-8")
        print()
        print(text)
    elif "summary" in payload:
        text = _markdown(case, payload)
        (out_dir / f"{stem}.md").write_text(text, encoding="utf-8")
        print()
        print(text)
    if code:
        print(f"\nlocal_ab: REFUSING — exit {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
