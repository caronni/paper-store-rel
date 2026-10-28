"""Reading a folded model out: status rows, advisories, selectors and
the status dict the server polls.

Every function here is `model -> presentation`; nothing mutates and
nothing folds.  File products are `report.py`, pane rasters are
`panes.py` — both sit above this module, never beside it.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

from ..data import FieldFitted, PluginRow
from .model import (PANE_NAMES, TILE_ADDRESSED, TILE_ATTEMPTED,
                    TILE_CERTIFIED, TILE_FLOOR, DiagModel, WindowKey, wkey)


def _window_key(subject: object) -> WindowKey | None:
    if (isinstance(subject, tuple) and len(subject) == 4
            and isinstance(subject[0], str)
            and isinstance(subject[3], tuple) and len(subject[3]) == 4):
        return wkey(subject[0], subject[2], subject[3])
    return None


def _tile_counts(model: DiagModel) -> tuple[int, int, int, int, int]:
    run = model.run
    ty, tx = run.tiles_yx
    total = ty * tx * max(1, len(run.stream_ids)) * max(1, len(page_selectors(model)))
    addressed = floor = attempted = certified = 0
    for arr in model.tile_states.values():
        addressed += int(np.count_nonzero(arr == TILE_ADDRESSED))
        floor += int(np.count_nonzero(arr == TILE_FLOOR))
        attempted += int(np.count_nonzero(arr == TILE_ATTEMPTED))
        certified += int(np.count_nonzero(arr == TILE_CERTIFIED))
    unknown = total - addressed - floor - attempted - certified
    return unknown, addressed, floor, attempted, certified


def plane_cert_counts(model: DiagModel) -> tuple[tuple[str, int], ...]:
    run = model.run
    if run is None:
        return ()
    counts = [0] * len(run.stream_ids)
    for arr in model.tile_states.values():
        certified = arr == TILE_CERTIFIED
        for index in range(min(len(counts), arr.shape[0])):
            counts[index] += int(np.count_nonzero(certified[index]))
    return tuple(zip(run.stream_ids, counts))


def _row_format(model: DiagModel) -> str:
    run = model.run
    if run is None:
        return "format   unavailable before run open"
    ty, tx = run.tiles_yx
    streams = ",".join(run.stream_ids)
    return (f"format   {run.display_id or run.format_id} · {ty}x{tx} tiles"
            f" · {run.pages} possible · streams {streams} · PROVISIONAL")


def _row_capture(model: DiagModel) -> str:
    n = sum(1 for c in model.captures.values() if not c.duplicate)
    if model.ordinals:
        sha = f"{model.ordinals[max(model.ordinals)][:12]}…"
    else:
        sha = "sha unavailable before intake"
    if model.surveys:
        n_regions = sum(s.n_regions for s in model.surveys.values())
        support = sum(int(mark.support_cells)
                      for s in model.surveys.values() for mark in s.regions)
        mid = f"regions {n_regions} · support {support} cells"
    else:
        mid = ("regions unavailable before survey"
               " · support unavailable before survey")
    if model.calibrations:
        adopted = sum(1 for c in model.calibrations.values() if c.adopted)
        cal = f"calibrated {adopted}/{len(model.calibrations)}"
    else:
        cal = "calibrated unavailable before calibrate"
    dup = (f" · {model.duplicates} duplicate folded"
           if model.duplicates else "")
    return f"capture  {n} ingested · {sha} · {mid} · {cal}{dup}"


def _row_frontier(model: DiagModel) -> str:
    stat = model.engine_stat
    if stat is None:
        return "frontier unavailable before the first merge"
    total = sum(count for _plugin, count in stat.queued)
    inner = " · ".join(f"{plugin} {count}"
                       for plugin, count in stat.queued) or "-"
    workers = (str(model.run.workers) if model.run is not None
               else "unavailable before run open")
    return (f"frontier queued {total} [{inner}] · in flight {stat.inflight}"
            f" · workers {workers}")


def _row_work(model: DiagModel) -> str:
    if not model.plugin_rows:
        return "work     unavailable before the first completed job"
    jobs = sum(row.jobs for row in model.plugin_rows.values())
    cpu = sum(row.cpu_seconds for row in model.plugin_rows.values())
    certs = " · ".join(f"{name}:{row.certificates}"
                       for name, row in sorted(model.plugin_rows.items()))
    return f"work     jobs {jobs} · cpu {cpu:.1f}s · certs by plugin [{certs}]"


def replay_line(model: DiagModel) -> str | None:
    """What a `--resume` brought in, for the panes that draw only this
    run's own work.  A replayed certificate has no tile outcome and a
    replayed placement has no pose, so every certificate-derived mark on
    a resumed run's panes is this run's alone — say so rather than let
    an empty grid read as an empty run."""
    replayed = model.replayed
    if replayed is None:
        return None
    facts = " · ".join(f"{name} {count}" for name, count in replayed.facts)
    return (f"snapshot replayed · {facts}"
            " · the marks here are this run's own work")


def _row_tiles(model: DiagModel) -> str:
    run = model.run
    if run is None:
        return "tiles    unavailable before run open"
    unknown, addressed, floor, attempted, certified = _tile_counts(model)
    replayed = ("" if model.replayed is None
                else f"replayed {model.replayed.certified} certificates"
                     " · this run ")
    row = (f"tiles    {replayed}UNKNOWN {unknown} · ADDRESSED {addressed}"
           f" · FLOOR {floor} · ATTEMPTED {attempted}"
           f" · CERTIFIED {certified}")
    if len(run.stream_ids) > 1:
        split = " · ".join(f"{stream_id} {count}"
                           for stream_id, count in plane_cert_counts(model))
        row += f" [{split}]"
    return row


def _row_close(model: DiagModel) -> str:
    close = model.last_close
    done = model.run_done
    if close is None and done is None:
        return "close    unavailable before the first close consult"
    if done is not None and done.status == "verified":
        sha = (done.payload_sha256 or "")[:16]
        word = f"VERIFIED sha {sha}…" if sha else "VERIFIED"
    elif close is not None:
        word = close.status
    else:
        word = done.status
    if close is None:
        return (f"close    {word} · K unavailable before consult"
                " · metadata rank unavailable before consult"
                " · equations unavailable before consult"
                " · blocks unavailable before consult")
    if close.blocks_counting:
        if close.k_total is None:
            k_part = "symbols unavailable before metadata"
        else:
            k_part = f"symbols {close.symbols_used}/{close.k_total}"
        if close.blocks:
            n_ready = sum(1 for row in close.blocks if row.short == 0)
            blocks_part = f"blocks ready {n_ready}/{len(close.blocks)}"
        else:
            blocks_part = "blocks unavailable before metadata"
    elif close.k_total is None and close.symbols_used == 0:
        k_part = "K unavailable before solve"
        blocks_part = "blocks unavailable before solve"
    else:
        k_total = "-" if close.k_total is None else str(close.k_total)
        k_part = f"K {close.symbols_used}/{k_total}"
        solved = sum(1 for row in close.blocks if row.solved)
        blocks_part = (f"blocks {solved}/{len(close.blocks)}"
                       if close.blocks else "blocks unavailable before solve")
    return (f"close    {word} · {k_part}"
            f" · metadata rank {close.metadata_rank}/24"
            f" · equations {close.metadata_n_unique}/48 · {blocks_part}")


def six_row_status(model: DiagModel) -> tuple[str, str, str, str, str, str]:
    return (_row_format(model), _row_capture(model), _row_frontier(model),
            _row_work(model), _row_tiles(model), _row_close(model))


FIELD_ROW_PREFIX = "fields   "


def lane_label(model: DiagModel, capture: str, level_index: int) -> str:
    """`<capture ordinal>.<level>`, falling back to the sha head before
    the capture has an ordinal."""
    ordinal = next((o for o, cid in model.ordinals.items()
                    if cid == capture), None)
    head = capture[:12] if ordinal is None else str(ordinal)
    return f"{head}.{int(level_index)}"


def _plane_phrase(row: object) -> str:
    if not row.fitted:
        return f"{row.plane_name} no fit"
    return (f"{row.plane_name} {row.median_delta_dots:.2f}d"
            f" {row.support_tiles}t"
            f" {'published' if row.published else 'refused'}")


def field_rows(model: DiagModel) -> tuple[str, ...]:
    """The conditional plane-field row (DIAG-DESIGN §1's reserved slot).

    Absent on a K run: there are no per-plane registration fields there,
    which is a different statement from "none measured yet" and must not
    be spelled the same way.  Present on every colour run, saying which
    of the three states it is in — dial off, no fit landed yet, or the
    latest fit's per-plane medians, support and publish verdict.  The
    refusing floor itself is named in the FIELD pane and in
    report.json; the row is the glance.
    """
    run = model.run
    if run is None or len(run.stream_ids) < 2:
        return ()
    if not run.plane_fields:
        return (FIELD_ROW_PREFIX + "off — pass --plane-fields to fit "
                "per-plane registration",)
    latest = model.last_field
    if latest is None:
        return (FIELD_ROW_PREFIX + "unavailable before the first fit",)
    lanes = len(model.field_fits)
    planes = " · ".join(_plane_phrase(row) for row in latest.planes)
    return (f"{FIELD_ROW_PREFIX}lane "
            f"{lane_label(model, latest.capture, latest.level_index)}"
            f" page {latest.page} · {planes}"
            f" · {lanes} lane-page{'' if lanes == 1 else 's'} fitted",)


def all_rows(model: DiagModel) -> tuple[str, ...]:
    """The six fixed rows plus whatever conditional rows apply."""
    return six_row_status(model) + field_rows(model)


def _human_subject(model: DiagModel, subject: object) -> str:
    key = _window_key(subject)
    if key is not None:
        capture, region_index, extent = key
        ordinal = next((o for o, cid in model.ordinals.items()
                        if cid == capture), None)
        label = capture[:12] if ordinal is None else str(ordinal)
        return f"window {label}.{region_index} {extent}"
    return _human_value(model, subject)


def _human_value(model: DiagModel, value: object) -> str:
    if isinstance(value, str):
        ordinal = next((o for o, cid in model.ordinals.items()
                        if cid == value), None)
        return str(value) if ordinal is None else f"capture {ordinal}"
    if isinstance(value, tuple):
        return "(" + ", ".join(_human_value(model, item)
                               for item in value) + ")"
    return str(value)


def now_lines(model: DiagModel) -> list[str]:
    stat = model.engine_stat
    if stat is None:
        return []
    return [f"{plugin} · {_human_subject(model, subject)} · {stage}"
            for plugin, subject, stage in stat.inflight_jobs]


def active_place_windows(model: DiagModel) -> set:
    stat = model.engine_stat
    if stat is None:
        return set()
    keys = set()
    for plugin, subject, _stage in stat.inflight_jobs:
        if plugin != "place":
            continue
        key = _window_key(subject)
        if key is not None:
            keys.add(key)
    return keys


def last_line(model: DiagModel) -> str | None:
    job = model.last_job
    if job is None:
        return None
    return (f"{job.plugin} · {_human_subject(model, job.subject)}"
            f" · +{job.n_certificates} certs · {job.cpu_s:.1f}s")


def close_shortfall_line(model: DiagModel) -> str | None:
    if model.run_done is not None and model.run_done.status == "verified":
        return None
    close = model.last_close
    if close is None:
        return None
    if not close.blocks:
        return f"{close.status} · blocks unavailable before metadata"
    if close.blocks_counting:
        short = [row for row in close.blocks if row.short > 0]
        if not short:
            return f"{close.status} · all blocks count-ready"
    else:
        short = [row for row in close.blocks if not row.solved]
        if not short:
            return f"{close.status} · all blocks solved"
    worst = max(short, key=lambda row: row.short)
    name = (f"{worst.stream_id}#{worst.block}" if worst.stream_id
            else f"#{worst.block}")
    if worst.n_groups == 1:
        return (f"{close.status} · block {name}"
                f" needs {worst.short} more symbols")
    return (f"{close.status} · block {name} short {worst.short} rows in "
            f"{worst.groups_open}/{worst.n_groups} groups")


CHURN_PRICE_FACTOR = 20.0
CHURN_FIRES_PER_SUBJECT = 3.0


def _median(values: list[float]) -> float:
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return 0.5 * (values[middle - 1] + values[middle])


def churn_rows(model: DiagModel) -> tuple[tuple[str, float, float, float],
                                          ...]:
    rows = []
    for plugin, row in sorted(model.plugin_rows.items()):
        subjects = len(model.plugin_subjects.get(plugin, ()))
        if row.jobs <= 0 or subjects <= 0:
            continue
        rows.append((plugin, row.cpu_seconds / row.jobs,
                     model.plugin_price_sum.get(plugin, 0) / row.jobs,
                     row.jobs / subjects))
    return tuple(rows)


def churn_advisory(model: DiagModel) -> str | None:
    if model.run_done is None:
        return None
    rows = churn_rows(model)
    ratios = sorted(cpu_per_fire / price
                    for _plugin, cpu_per_fire, price, _fires in rows
                    if price > 0)
    band = _median(ratios) if ratios else 0.0
    named = []
    for plugin, cpu_per_fire, price, fires in rows:
        dear = (band > 0 and price > 0
                and cpu_per_fire > CHURN_PRICE_FACTOR * band * price)
        if dear or fires > CHURN_FIRES_PER_SUBJECT:
            named.append(f"{plugin}: {cpu_per_fire:.3g} cpu-s/fire at price "
                         f"{price:.0f} · {fires:.1f} fires/subject")
    return "; ".join(named) if named else None


def ladder_isolation_advisory(model: DiagModel) -> str | None:
    ladders = {capture: frozenset(opened.levels_ppc)
               for capture, opened in model.captures.items()
               if not opened.duplicate and opened.levels_ppc}
    if len(ladders) < 2:
        return None
    named = []
    for capture in sorted(ladders):
        others = frozenset().union(
            *(rungs for other, rungs in ladders.items() if other != capture))
        if not ladders[capture] & others:
            rungs = " ".join(sorted(ladders[capture],
                                    key=lambda tag: Fraction(tag)))
            named.append(f"{capture[:12]}… ladder {{{rungs}}} ppc shares "
                         f"no rung with any other capture — "
                         f"certificate-only interaction")
    return "; ".join(named) if named else None


def capture_selectors(model: DiagModel) -> tuple[int, ...]:
    return tuple(sorted(model.ordinals))


def page_selectors(model: DiagModel) -> tuple[int, ...]:
    pages = {0, *model.poses}
    if model.run is None:
        return tuple(sorted(pages))
    return tuple(sorted(p for p in pages if 0 <= p < model.run.pages))


def field_pages(model: DiagModel) -> tuple[int, ...]:
    """Pages the FIELD pane can draw: those a fit has landed on.

    Empty until the first fit, so a run without the arm renders exactly
    the panes it rendered before this one existed — the same rule v1's
    bottom band follows (no snapshot, no band).  The status ROW is the
    other half of the honesty and is always present on a colour run.
    """
    return tuple(sorted(model.field_latest))


def page_field(model: DiagModel, page: int) -> FieldFitted | None:
    """The fit the FIELD pane draws for `page`: the lane-page that fitted
    it most recently.  Others are listed in the pane's own text block and
    in full in report.json."""
    key = model.field_latest.get(int(page))
    return None if key is None else model.field_fits.get(key)


def page_field_lanes(model: DiagModel, page: int) -> tuple[str, ...]:
    """Every lane that has fitted `page`, latest first."""
    latest = model.field_latest.get(int(page))
    keys = [key for key in sorted(model.field_fits) if key[2] == int(page)]
    keys.sort(key=lambda key: key != latest)
    return tuple(lane_label(model, key[0], key[1]) for key in keys)


def status(model: DiagModel) -> dict:
    ordinals = list(capture_selectors(model))
    pages = list(page_selectors(model))
    stat = model.engine_stat
    inflight_by_plugin: dict[str, int] = {}
    for plugin, _subject, _stage in (
            stat.inflight_jobs if stat is not None else ()):
        inflight_by_plugin[plugin] = inflight_by_plugin.get(plugin, 0) + 1
    queued = dict(stat.queued) if stat is not None else {}
    names = sorted(set(queued) | set(model.plugin_rows)
                   | set(inflight_by_plugin))
    plugins = []
    for name in names:
        row = model.plugin_rows.get(name, PluginRow(name))
        plugins.append({
            "plugin": name,
            "queued": int(queued.get(name, 0)),
            "inflight": inflight_by_plugin.get(name, 0),
            "jobs": row.jobs,
            "cpu_s": round(row.cpu_seconds, 3),
            "certificates": row.certificates,
            "poses": row.poses,
            "words": row.words,
        })
    close = model.last_close
    done = model.run_done
    verified = None
    if done is not None and done.status == "verified":
        verified = {"n_bytes": done.n_bytes,
                    "sha16": (done.payload_sha256 or "")[:16]}
    blocks = [] if close is None else [
        {"stream_id": row.stream_id, "block": row.block, "have": row.have,
         "needed": row.needed, "rank": row.rank, "solved": row.solved,
         "short": row.short, "groups_open": row.groups_open,
         "n_groups": row.n_groups}
        for row in close.blocks]
    close_status = (close.status if close is not None
                    else (done.status if done is not None else "open"))
    return {
        "revision": model.cursor,
        "rows": list(all_rows(model)),
        "now": now_lines(model),
        "last": last_line(model),
        "captures": [{"ordinal": ordinal,
                      "sha12": model.ordinals[ordinal][:12]}
                     for ordinal in ordinals],
        "pages": pages,
        "panes": {"capture": ordinals, "page": pages, "payload": pages,
                  "pose": pages, "field": list(field_pages(model))},
        "pane_revs": {pane: model.pane_revs.get(pane, 0)
                      for pane in PANE_NAMES},
        "scheduler": {
            "available": stat is not None,
            "plugins": plugins,
            "attempts_hist": [[label, count] for label, count in
                              (stat.attempts_hist if stat is not None
                               else ())],
            "stale_skips": stat.stale_skips if stat is not None else None,
            "retired": stat.retired if stat is not None else None,
            # which clause retired each PLACE row — `done_covered` here
            # is the done gate's only visible firing count
            "retire_causes": ([[cause, count] for cause, count
                               in stat.retire_causes]
                              if stat is not None else None),
            "wakes": stat.wakes if stat is not None else None,
            "consult_cpu_s": (round(stat.consult_cpu_s, 3)
                              if stat is not None else None),
            "churn": churn_advisory(model),
        },
        "close": {
            "status": close_status,
            "consulted": close is not None,
            "certified": (close.certified if close is not None
                          else (done.certified if done is not None else 0)),
            "symbols_used": close.symbols_used if close is not None else 0,
            "k_total": close.k_total if close is not None else None,
            "metadata_rank": (close.metadata_rank
                              if close is not None else 0),
            "metadata_n_unique": (close.metadata_n_unique
                                  if close is not None else 0),
            "counting": close is not None and close.blocks_counting,
            "blocks": blocks,
            "verified": verified,
        },
        "plane_certs": [[stream_id, count]
                        for stream_id, count in plane_cert_counts(model)],
        "replayed": (None if model.replayed is None else {
            "certified": model.replayed.certified,
            "facts": [[name, count] for name, count in model.replayed.facts],
        }),
        "fold_errors": model.fold_errors,
    }
