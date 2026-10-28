#!/usr/bin/env python
"""THE PARITY REPORT — rendering, split out of ``parity_k.py`` (W4 fixes).

NOT A TEST and not a driver: import-only, the rendering half of the K
parity harness. ``parity_k.py`` declares the population, measures both
trees and holds every path; this module turns finished rows into
markdown and knows nothing else. Its silent classifiers are pinned in
``tests/holo2_oracles/test_oracle_parity_k.py`` beside the harness's.

WHY IT IS A SEPARATE FILE (2026-08-23). HANDOFF-W4 §6 named this exact
seam — "declaration+measurement versus rendering" — and declined to take
it at 941 lines, when one file was still under the cap. The review fixes
(measured prepared-plane counts, decode-time provenance, the population
split in the bar, the untruncated policy id) put the single file at
1,101 lines, so the seam signal fired and the split is taken rather than
squeezed. The edge it adds is one-directional and carries meaning: this
module imports NOTHING from ``parity_k`` — rows arrive duck-typed, and
the two things it would otherwise reach back for (the dial state read at
decode time, and the refine-off baseline table) are PARAMETERS of
:func:`render_report`. Nothing here can decode, read a state or touch
the corpus.
"""
from __future__ import annotations

import time
from typing import Any, Mapping, Sequence


def _prepared_phrase(side: Any) -> str:
    """"adopted from X (N of M reused, K built by this run)" — MEASURED.

    Review fix, 2026-08-23: the counts decide the sentence, not the
    declaration. ``prepared_after > prepared_before`` means planes were
    built inside the wall, so the wall is solve+prepare and the phrase
    says so; equal counts are the 100%-hit case and only then may a
    reader read the wall as the SOLVE.
    """
    before, after = side.prepared_before, side.prepared_after
    if before is None or after is None:
        return f"{side.prepared} (counts unmeasured — sidecar predates them)"
    built = after - before
    if built <= 0:
        return (f"{side.prepared} — {before} of {after} reused, 0 built by "
                "this run; the wall is the SOLVE")
    return (f"{side.prepared} — {before} of {after} reused, **{built} built "
            "by this run**; the wall is SOLVE + PREPARE, not solve")


def _provenance_phrase(side: Any) -> str:
    """The tree and the dials this row was DECODED under, from its sidecar."""
    prov = side.provenance
    if not prov:
        return "tree and dials NOT RECORDED for this row"
    head = str(prov.get("git_head", "(unavailable)"))
    dirty = " +uncommitted changes" if prov.get("git_dirty") else ""
    dials = ", ".join(f"`{key}` = `{value}`" for key, value in prov.items()
                      if key not in ("git_head", "git_dirty", "backfilled"))
    note = (" — BACKFILLED, inferred from wall-clock ordering against "
            "commit timestamps, not recorded at decode time"
            if prov.get("backfilled") else "")
    return f"tree `{head}`{dirty}, {dials}{note}"


def _mark(value: bool | None) -> str:
    return {True: "yes", False: "**NO**", None: "n/a"}[value]


def _tile_list(keys: Sequence[tuple[int, int, int]], limit: int = 400) -> str:
    if not keys:
        return "(none)"
    shown = ", ".join(f"({p},{ty},{tx})" for p, ty, tx in keys[:limit])
    if len(keys) > limit:
        shown += f", … (+{len(keys) - limit} more)"
    return shown


def render_report(rows: Sequence[Any], *, workers: int,
                  dials: Mapping[str, Any],
                  baselines: Mapping[str, Mapping[str, Any]]) -> str:
    """Rows -> markdown. ``dials`` and ``baselines`` are passed IN.

    The dials are the RENDER-time tree's, quoted for reference only
    (every row prints its own decode-time provenance); the baselines
    are ``parity_k.REFINE_OFF_BASELINE``. Both are parameters so this
    module never imports the harness back (module docstring).
    """
    out: list[str] = []
    out.append("# K parity — v1 against holo2, sheet by sheet (W4)")
    out.append("")
    out.append(f"Generated {time.strftime('%Y-%m-%d %H:%M')} by "
               "`holo2/measure/parity_k.py` on branch `holo2-catchup`.")
    out.append("")
    out.append("**Every holo2 number below carries the tree and the dials it "
               "was DECODED under, printed under its own row from its own "
               "sidecar** (review fix, 2026-08-23 — they used to be read off "
               "the live tree at RENDER time and asserted for rows decoded "
               "hours earlier, so a reprice would have silently relabelled "
               "every adopted row). The shape is the same on every row: the "
               f"CLI operator path `./confetti2.py --format <id> --complete "
               f"--workers {workers}`, default close policy. For reference, "
               "the tree this report was RENDERED on carries "
               + ", ".join(f"`{k}` = `{v}`" for k, v in dials.items())
               + " — a row is only measured under those if its own line "
               "says so. v1's side is READ from its archived state where "
               "one exists (RULING I5) and driven live where it is not; the "
               "table prints the argv each live arm recorded.")
    out.append("")
    out.append("## The table")
    out.append("")
    out.append("| sheet | v1 certs | holo2 certs | Δ | v1 sha == golden | "
               "holo2 sha == golden | holo2 wall (s) | v1 source |")
    out.append("|---|---:|---:|---:|---|---|---:|---|")
    for row in rows:
        # RECORDED, never inferred from the declaration (review fix,
        # 2026-08-23): this column used to print a flag string derived
        # from ``sheet.v1_state is None``, so a live arm whose sidecar
        # was missing still advertised the flags it was supposed to have
        # been driven at. ``V1Side.source`` is the argv the arm actually
        # recorded, or the state it was read from, or the explicit
        # "argv unrecorded" of an arm that predates the sidecar.
        source = ("archived state" if row.sheet.v1_state is not None
                  else f"`{row.v1.source}`")
        out.append(
            f"| {row.sheet.label} | {row.v1.certificates} | "
            f"{row.h2.certificates} | {row.delta:+d} | "
            f"{_mark(row.v1_zero_wrong)} | {_mark(row.h2_zero_wrong)} | "
            f"{row.h2.wall_s:.0f}{'*' if row.h2.adopted else ''} | "
            f"{source} |")
    out.append("")
    out.append("`*` = the wall of the run that wrote the sidecar, adopted "
               "rather than re-decoded (a real sheet is never decoded "
               "twice).")
    out.append("")
    out.extend(_render_bar(rows))
    out.extend(_render_refine_off(rows, baselines))
    for row in rows:
        out.extend(_render_row(row))
    return "\n".join(out)


def _render_bar(rows: Sequence[Any]) -> list[str]:
    """RULING I1's bar, stated per row rather than summarised.

    The bar is "as well or better", i.e. Δ >= 0. It is stated and not
    argued: a row that misses it says so, and the tile list under that
    row is where the missing tiles are named.

    THE POPULATION SPLIT (review fix, 2026-08-23). I1 names "each
    available / parseable K scan, and all synthetic scrap 'scans'" — the
    two printed sheets and the nine-scrap demo, and nothing else. The
    three verdicts fixture pages are an ADDITION this harness made; they
    are worth measuring and they are not the ruled population. A single
    "N of 6 rows meet the bar" mixes them, and the mixed number is the
    one a later package quotes, so the score is printed as two lines.
    """
    out = ["## RULING I1's bar, row by row", ""]
    out.append("The bar is Δ >= 0 — *\"K performs as well or better than "
               "src/holo on each available / parseable K scan, and all "
               "synthetic scrap 'scans'\"*. Nothing below is an excuse for "
               "a row that misses it; the tiles it misses are listed under "
               "that row.")
    out.append("")
    out.append("| sheet | population | Δ | bar |")
    out.append("|---|---|---:|---|")
    for row in rows:
        ruled = row.sheet.kind in ("real", "scrap")
        out.append(f"| {row.sheet.label} | "
                   f"{'RULING I1' if ruled else 'added fixture'} | "
                   f"{row.delta:+d} | "
                   f"{'**MET**' if row.delta >= 0 else '**NOT MET**'} |")
    ruled_rows = [row for row in rows if row.sheet.kind in ("real", "scrap")]
    extra_rows = [row for row in rows if row.sheet.kind not in
                  ("real", "scrap")]
    out.append("")
    for label, group in (("RULING I1's population (K scans + synthetic "
                          "scraps)", ruled_rows),
                         ("Added fixture pages (outside I1)", extra_rows)):
        if not group:
            continue
        met = sum(1 for row in group if row.delta >= 0)
        out.append(f"**{label}: {met} of {len(group)} rows meet the bar.**")
    out.append("")
    out.append("The two lines are not one number on purpose: I1's bar is "
               "about K scans and scrap scans, and the fixture pages are "
               "this harness's own addition. A combined score reads better "
               "than the ruled one and is the number a later package would "
               "quote.")
    out.append("")
    return out


def _render_refine_off(rows: Sequence[Any],
                       baselines: Mapping[str, Mapping[str, Any]],
                       ) -> list[str]:
    """The same rows as they measured with RF1 dialled OFF, where one exists."""
    quoted = [row for row in rows if row.sheet.label in baselines]
    if not quoted:
        return []
    out = ["## Against the refine-off measurement of the same sheet", ""]
    out.append("Quoted from committed records (the `source` column), never "
               "re-derived. **Both real-sheet baselines BUILT their prepared "
               "planes inside their wall while the runs above adopted "
               "theirs**, so the wall column understates this tree's cost "
               "rather than overstating it; and the demo baseline's tree "
               "and flags were never recorded, so it is the only holo2 "
               "number that exists for that page and not a controlled arm. "
               "Δcerts here is refine-ON minus refine-OFF on the SAME "
               "sheet, which is not the parity Δ above.")
    out.append("")
    out.append("| sheet | certs off → on | Δ | commits off → on | "
               "wall off → on (s) | done cells off → on | source |")
    out.append("|---|---|---:|---|---|---|---|")
    for row in quoted:
        base = baselines[row.sheet.label]
        commits = _epilogue_int(row.h2.epilogue, "work ", "commits")
        # The DONE-CELL count is the numerator inside the parentheses on
        # the capture row ("done coverage 97.4% (7823516/8030805 cells)"),
        # so the anchor is the bracket and not the word: anchoring on
        # "coverage" would read the PERCENT's leading digits instead.
        done = _epilogue_int(row.h2.epilogue, "capture ", "(")
        out.append(
            f"| {row.sheet.label} | {base['certificates']} → "
            f"{row.h2.certificates} | "
            f"{row.h2.certificates - base['certificates']:+d} | "
            f"{_or_dash(base['commits'])} → {_or_dash(commits)} | "
            f"{_or_dash(base['wall_s'])} → {row.h2.wall_s:.0f} | "
            f"{_or_dash(base['done_cells'])} → {_or_dash(done)} | "
            f"`{base['source']}` |")
    out.append("")
    return out


def _or_dash(value: Any) -> str:
    return "—" if value is None else f"{value:g}" if isinstance(
        value, float) else str(value)


def _epilogue_int(epilogue: Sequence[str], prefix: str,
                  after: str) -> int | None:
    """The first integer following ``after`` on the epilogue's ``prefix`` row.

    The epilogue is the CLI's own printed summary and the state is the
    record; nothing that decides a verdict is parsed out of it — only
    the two context numbers this table quotes beside the certificates.
    """
    for line in epilogue:
        if not line.startswith(prefix) or after not in line:
            continue
        tail = line.split(after, 1)[1]
        digits = ""
        for char in tail:
            if char.isdigit():
                digits += char
            elif digits:
                break
        if digits:
            return int(digits)
    return None


def _render_row(row: Any) -> list[str]:
    sheet = row.sheet
    out: list[str] = []
    out.append(f"## {sheet.label} — {sheet.note}")
    out.append("")
    out.append(f"- identity: `{sheet.format_ref}`, {sheet.pages} page(s), "
               f"{len(sheet.scans) or '1 (rendered)'} capture(s)")
    out.append(f"- **v1**: {row.v1.certificates} certified, close "
               f"`{row.v1.close_status}`, payload sha "
               f"`{(row.v1.payload_sha or '—')[:12]}…`")
    out.append(f"  - source: {row.v1.source}")
    out.append("  - validated: the state LOADS on the current `src/holo` "
               "(`holo.receive.session.load_session` parsed it; a schema "
               "the tree no longer accepts raises there, so this row "
               "existing is the validation)")
    out.append(f"  - lane kinds declared (the durable record of the "
               f"harvest flags): `{row.v1.lane_kinds}`")
    # The SCHEDULER segment, printed whole (review fix, 2026-08-23): the
    # id's first 60 characters are identical on every K state in the
    # corpus, so a truncated field was decorative and hid a real vintage
    # spread (v2 on the two printed sheets, v4 on the demo, v5 on any v1
    # arm driven today). The full id follows it for the record.
    scheduler = next((seg for seg in row.v1.receiver_policy_id.split(";")
                      if "scheduler=" in seg), "(no scheduler segment)")
    out.append(f"  - receiver policy scheduler: `{scheduler}`")
    out.append(f"  - receiver policy (full): `{row.v1.receiver_policy_id}`")
    out.append(f"  - format row recorded in the state: "
               f"`{row.v1.format_row_id}`")
    out.append(f"- **holo2**: {row.h2.certificates} certified, exit "
               f"{row.h2.returncode}, payload sha "
               f"`{(row.h2.payload_sha or '—')[:12]}…`, wall "
               f"{row.h2.wall_s:.1f} s{' (adopted)' if row.h2.adopted else ''}"
               f", decoded {row.h2.ran_at}")
    out.append(f"  - argv: `{row.h2.argv}`")
    out.append(f"  - measured under: {_provenance_phrase(row.h2)}")
    out.append(f"  - prepared planes: {_prepared_phrase(row.h2)}")
    for line in row.h2.epilogue:
        out.append(f"  - `{line}`")
    out.append(f"- **Δ = {row.delta:+d}** certificates (holo2 − v1); "
               f"zero-wrong v1 {_mark(row.v1_zero_wrong)}, holo2 "
               f"{_mark(row.h2_zero_wrong)} "
               f"(golden `{(row.golden_sha or '—')[:12]}…`)")
    out.append("")
    if row.diff_error:
        out.append(f"Differential REFUSED: `{row.diff_error}`")
        out.append("")
        return out
    if row.diff is None:
        out.append("Differential not run (`--no-differential`).")
        out.append("")
        return out
    diff = row.diff
    v1_only = tuple(item.key for item in diff.v1_only)
    h2_only = tuple(item.key for item in diff.h2_only)
    out.append(f"Tile differential (W1's instrument, "
               f"`tile_differential.run`): both {len(diff.both)}, "
               f"v1-only **{len(v1_only)}**, holo2-only **{len(h2_only)}**, "
               f"neither {diff.neither}, domain {diff.total_tiles}.")
    out.append("")
    out.append(f"- v1 has / holo2 lacks (page,ty,tx): {_tile_list(v1_only)}")
    out.append(f"- holo2 has / v1 lacks (page,ty,tx): {_tile_list(h2_only)}")
    out.append("")
    return out

