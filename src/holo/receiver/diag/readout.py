"""Reading a folded model out: status rows, advisories, selectors and
the status dict the server polls.

Every function here is `model -> presentation`; nothing mutates and
nothing folds.  File products are `report.py`, pane rasters are
`panes.py` — both sit above this module, never beside it.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

from ..data import CloseBlockRow, FieldSolved, PluginRow
from ..format.identity import Family
from .model import (PANE_NAMES, TILE_ADDRESSED, TILE_ATTEMPTED,
                    TILE_CERTIFIED, TILE_FLOOR, DiagModel, WindowKey, wkey)


#: `JobDone.subject` carries the RAW subject value (DIAG-DESIGN §4), so
#: the window shape is sniffed here.  A subject that stops matching
#: returns None and pane A's window marks vanish silently — no error.
def _window_key(subject: object) -> WindowKey | None:
    if (isinstance(subject, tuple) and len(subject) == 4
            and isinstance(subject[0], str)
            and isinstance(subject[3], tuple) and len(subject[3]) == 4):
        return wkey(subject[0], subject[2], subject[3])
    return None


#: The denominator counts LIVE pages x streams, never `run.pages` (the
#: possible count, up to 2621 on a small matrix): UNKNOWN is the
#: residue, so a possible-sized denominator would invent whole pages of
#: unknown tiles on a single-sheet run.  PAGE-DOMAIN §3.
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


def _block_name(row: CloseBlockRow) -> str:
    return f"{row.stream_id}#{row.block}" if row.stream_id else f"#{row.block}"


#: Once a block holds its symbol count and has not solved, the count no
#: longer says which column groups bind (the owner, 2026-10-12): name the
#: open ones with their rows against the rows each needs.  Nothing before
#: the count, on a one-group row (K, uniform cmy8) or on a row carrying
#: no per-group counts.  The viewer shell's JS (server.py) spells the
#: same text again — a change here is two edits.
def scarcest_group(row: CloseBlockRow) -> tuple[int, int] | None:
    """The open group with the fewest rows, (group, rows), under
    `group_counts`' condition -- the needs line names it once, where the
    close row lists every open group."""
    if (row.solved or row.n_groups == 1 or row.have < row.needed
            or not row.group_rows):
        return None
    open_groups = [(rows, group) for group, (rows, solved)
                   in enumerate(zip(row.group_rows, row.group_solved))
                   if not solved]
    if not open_groups:
        return None
    rows, group = min(open_groups)
    return group, rows


def group_counts(row: CloseBlockRow) -> str | None:
    if (row.solved or row.n_groups == 1 or row.have < row.needed
            or not row.group_rows):
        return None
    counts = " ".join(f"{group}:{rows}" for group, (rows, solved)
                      in enumerate(zip(row.group_rows, row.group_solved))
                      if not solved)
    text = (f"groups open {row.groups_open}/{row.n_groups}"
            f" [{counts}]/{row.needed}")
    return text + (f" · scarcest {row.short} short" if row.short else "")


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
    # No solve ran at this consult: the blocks are the persistent decoder's
    # counting projection.  A rank can still stand — one recorded by an
    # EARLIER failed elimination survives until the group gains a row or
    # solves, and `short` derives from it (fountain.BlockStatus.short).
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
    groups = "".join(f" · {_block_name(row)} {text}"
                     for row in close.blocks
                     if (text := group_counts(row)) is not None)
    # 24 = format.metadata.METADATA_BITS, the word's algebraic rank; 48 =
    # MIN_METADATA_EQUATIONS, a TRUST FLOOR and not a denominator, so
    # "equations 200/48" is the healthy reading.  Both literals are spelled
    # again in the viewer shell's JS (server.py) — a format change is two edits.
    return (f"close    {word} · {k_part}"
            f" · metadata rank {close.metadata_rank}/24"
            f" · equations {close.metadata_n_unique}/48 · {blocks_part}"
            f"{groups}")


#: Exactly six rows with fixed prefixes (DIAG-DESIGN §0, §2): a fact
#: becoming known must never move a row, and no row prints a zero for a
#: producer that has not fired — it names it "unavailable before <x>".
#: Conditional rows are `all_rows`'s, never this tuple's.
def six_row_status(model: DiagModel) -> tuple[str, str, str, str, str, str]:
    return (_row_format(model), _row_capture(model), _row_frontier(model),
            _row_work(model), _row_tiles(model), _row_close(model))


FIELD_ROW_PREFIX = "fields   "


def capture_label(model: DiagModel, capture: str) -> str:
    """The capture's ordinal, or the sha head before it has one.

    `lane_label` without the level: a capture-scoped number (the field's
    per-capture residual) has no lane to name.
    """
    ordinal = next((o for o, cid in model.ordinals.items()
                    if cid == capture), None)
    return capture[:12] if ordinal is None else str(ordinal)


def lane_label(model: DiagModel, capture: str, level_index: int) -> str:
    """`<capture ordinal>.<level>`, falling back to the sha head before
    the capture has an ordinal."""
    return f"{capture_label(model, capture)}.{int(level_index)}"


def field_support(solved: FieldSolved) -> float:
    """The share of (tile, plane) cells the page has evidence on.

    One number over the planes the field MEASURES, because that is what
    the glance is for: a page reading 100% has been measured everywhere
    and a page reading 40% has two planes it cannot see.  A plane the
    gauge holds at the pose (`held`, cmy's C) measures nothing, so it is
    in neither count (2026-10-12).  The per-plane split is in the FIELD
    pane and in report.json.
    """
    tiles = int(solved.tiles_yx[0]) * int(solved.tiles_yx[1])
    measured = [row for row in solved.planes if not row.held]
    if not tiles or not measured:
        return 0.0
    return sum(row.support_tiles
               for row in measured) / float(tiles * len(measured))


def plane_name_of(solved: FieldSolved, plane: int) -> str:
    """The stream letter of a plane index, from the event's own rows."""
    for row in solved.planes:
        if int(row.plane) == int(plane):
            return row.plane_name
    return str(plane)


def field_residual(solved: FieldSolved) -> str:
    """The loudest (capture, PLANE) disagreement on this page.

    Per plane and never summed over them, which is R-F and the whole of
    review F11: 100 explained C rows, 100 explained M rows and one Y row
    a dot out give Y a ratio of 8 and the summed report 0.040, so
    healthy word planes hide the poorly supported Y this diagnostic
    exists to expose.  The row is a glance, so it names the loudest one
    and the full table lives in the FIELD pane and in report.json.

    Ties fall back to the event's own order, which is the capture
    ordinal then the plane index: sorting labels as text would put
    capture 10 ahead of capture 2, and a page whose evidence all fits
    has nothing to rank.
    """
    rated = sorted(
        ((energy / expected if expected > 0.0 else 0.0, order, plane)
         for order, (_capture, plane, energy, expected, _count)
         in enumerate(solved.residual_by_capture_plane)),
        key=lambda entry: (-entry[0], entry[1]))
    if not rated:
        return "no evidence"
    ratio, _order, plane = rated[0]
    return f"worst {plane_name_of(solved, plane)} {ratio:.2f}x"


def field_plane_glance(row) -> str:
    """One plane on the status row: its median, its error bar beside it.

    A plane no template could be built for reads UNKNOWN and not zero
    (I13): the two are different statements and a status row that spells
    them the same way is the reason the distinction was invisible.  A
    plane the gauge holds at the pose (cmy's C, R7) reads `0 (gauge)`:
    zero by name, not a measured 0.00±0.00.
    """
    if row.held:
        return f"{row.plane_name} 0 (gauge)"
    if not row.known:
        return f"{row.plane_name} unknown"
    return (f"{row.plane_name} {row.median_delta_dots:.2f}"
            f"±{row.median_uncertainty_dots:.2f}")


def field_rows(model: DiagModel) -> tuple[str, ...]:
    """The conditional page-field rows (DIAG-DESIGN §1's reserved slot),
    ONE PER PAGE.

    Absent on a K run: K has one plane and no differential, which is a
    different statement from "none measured yet" and must not be spelled
    the same way.  The gate is the FAMILY (2026-10-12), never the stream
    count: cmy7 is a colour page with one stream, cmy's two streams are
    label bits, not planes.  Present on every colour run, saying which
    of the two states it is in — no solve landed yet, or, for each page
    a solve has landed on, that page's per-plane medians with their
    error bars, its support, the evidence revision it was fitted at and
    the loudest (capture, plane) disagreement.  Per page because the
    field is per (page, plane): a duplex sheet's two faces carry
    different fields (design §2.2) and a run that printed only the
    latest could not say that.

    The REVISION replaces the trigger ratio the row used to print (W8
    R-D): the page solves because its evidence moved, so the number
    worth a glance is the evidence revision it was solved at, not a
    statistic that decided whether to solve.

    PASSES is the robust loss's own count, and it is on the glance
    because it is the one field number whose ordinary value is small and
    whose large value means something: a page that took its pass ceiling
    is published all the same — the objective is convex, so the last
    iterate is the best one reached — and the row says `capped` beside
    the count rather than leaving the reader to believe it is an
    optimum.
    """
    run = model.run
    if run is None or run.family == Family.K.value:
        return ()
    if not model.field_solves:
        return (FIELD_ROW_PREFIX + "unavailable before the first solve",)
    rows = []
    for page in sorted(model.field_solves):
        solved = model.field_solves[page]
        planes = " ".join(field_plane_glance(row) for row in solved.planes)
        capped = "" if solved.converged else " capped"
        rows.append(f"{FIELD_ROW_PREFIX}page {solved.page} — {planes} dots,"
                    f" support {round(100.0 * field_support(solved))}%"
                    f" · rev {solved.revision}"
                    f" · passes {solved.passes}{capped}"
                    f" · {field_residual(solved)}")
    return tuple(rows)


CONFLICT_ROW_PREFIX = "conflict "


def conflict_rows(model: DiagModel) -> tuple[str, ...]:
    """The address-word alarm, present only once it has fired.

    Absent at zero on purpose: silence is this mechanism's whole
    measured record (v1 ~1,780 known-position reads, holo2 21k evidence
    records, both zero), and a standing `conflict 0` would read as a
    gate that is doing something.  It is not: nothing is quarantined.
    """
    latest = model.last_contradiction
    if not model.contradictions or latest is None:
        return ()
    mine = lane_label(model, latest.capture, latest.window_id[1])
    theirs = lane_label(model, latest.capture, latest.standing_window_id[1])
    return (f"{CONFLICT_ROW_PREFIX}{model.contradictions} address "
            f"contradiction{'' if model.contradictions == 1 else 's'}"
            f" · latest window {mine}.{latest.window_id[2]} page "
            f"{latest.page} tile {latest.tile_yx[0]},{latest.tile_yx[1]}"
            f" vs standing window {theirs}.{latest.standing_window_id[2]}"
            f" page {latest.standing_page} tile "
            f"{latest.standing_tile_yx[0]},{latest.standing_tile_yx[1]}"
            f" · quarantine is not built — the payload is unaffected",)


def all_rows(model: DiagModel) -> tuple[str, ...]:
    """The six fixed rows plus whatever conditional rows apply."""
    return six_row_status(model) + field_rows(model) + conflict_rows(model)


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
    name = _block_name(worst)
    if worst.n_groups == 1:
        return (f"{close.status} · block {name}"
                f" needs {worst.short} more symbols")
    scarcest = scarcest_group(worst)
    if scarcest is not None:
        group, rows = scarcest
        return (f"{close.status} · block {name} groups open "
                f"{worst.groups_open}/{worst.n_groups} · scarcest group "
                f"{group}: {rows}/{worst.needed} ({worst.short} short)")
    return (f"{close.status} · block {name} short {worst.short} rows in "
            f"{worst.groups_open}/{worst.n_groups} groups")


#: The churn advisory's two bars, ruled with the pane (DIAG-DESIGN §5):
#: name a row whose cpu-per-fire exceeds 20x what its price predicts
#: under the run's own median price->cpu scale, or that fires more than
#: 3 times per subject.  Report-only — never a cap, never an exit code.
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


#: Live pages ∪ the page-0 prior, clipped against possible
#: (PAGE-DOMAIN §3): a viewer must never grow `row.max_pages` empty
#: page links — 133 of them on a 53x37 sheet, 2621 at 10x10.
def page_selectors(model: DiagModel) -> tuple[int, ...]:
    pages = {0, *model.poses}
    if model.run is None:
        return tuple(sorted(pages))
    return tuple(sorted(p for p in pages if 0 <= p < model.run.pages))


def field_pages(model: DiagModel) -> tuple[int, ...]:
    """Pages the FIELD pane can draw: those a solve has landed on.

    Empty until the first solve, so a run whose colour never gets that
    far renders exactly the panes it rendered before this band existed.
    The status ROW is the other half of the honesty and is always
    present on a colour run.
    """
    return tuple(sorted(model.field_solves))


def page_field(model: DiagModel, page: int) -> FieldSolved | None:
    """The solve the FIELD pane draws for `page` — there is exactly
    one."""
    return model.field_solves.get(int(page))


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
         "n_groups": row.n_groups,
         "groups": [{"group": group, "rows": rows, "needed": row.needed,
                     "rank": rank, "solved": solved}
                    for group, (rows, rank, solved) in enumerate(zip(
                        row.group_rows, row.group_rank, row.group_solved))]}
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
        # None, never 0, before the first EngineStat; `available` gates the whole
        # line in the shell.  The 2026-08-29 review found this block printing
        # fabricated zeros for producers that had not fired — the one
        # never-print-zero breach this file has had (DIAG-REVIEW-FINDINGS.md:17).
        "scheduler": {
            "available": stat is not None,
            "plugins": plugins,
            "attempts_hist": [[label, count] for label, count in
                              (stat.attempts_hist if stat is not None
                               else ())],
            "stale_skips": stat.stale_skips if stat is not None else None,
            "retired": stat.retired if stat is not None else None,
            # which clause retired each row (DIAG-DESIGN §4, 2026-08-31: without
            # it four real-sheet runs read as "the gate never fires" while it
            # suppressed 157 of sheet-I-first's 164 retirements).  Since
            # 2026-10-03 the done gate suppresses through place's stage and
            # `done_covered` appears only in records before that date.
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
        "contradictions": model.contradictions,
        "replayed": (None if model.replayed is None else {
            "certified": model.replayed.certified,
            "facts": [[name, count] for name, count in model.replayed.facts],
        }),
        "fold_errors": model.fold_errors,
    }
