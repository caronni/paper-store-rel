"""The six-row operator status block (RECEIVE-DESIGN §10.3.2).

Pure text projection of an accumulated :class:`~holo.receive.diag.viewer.
LiveView` model: it reads the view's counters and prints them, and it never
computes a receiver fact.  Two rules from §10.3.2 are load-bearing here and
easy to break by accident:

* never print zero where the fact is unavailable — an unsurveyed lane says
  so, and a deferred close names what is deferred; and
* the block is exactly six rows of fixed height, so a value becoming known,
  changing width, or going away must not move a pane.
"""
from __future__ import annotations

import numpy as np

from .presentation import (
    _TILE_STATE_CERTIFIED, _TILE_STATE_FAILED, _TILE_STATE_FLOOR,
    _WORD_CONFLICT, _WORD_FAILED, _WORD_FLOOR, _WORD_SOLVED,
    _WORD_VALIDATED)


def metadata_phrase(metadata: object) -> str | None:
    """The certified-metadata trust phrase, shared by both close paths."""
    if metadata is None:
        return None
    if metadata.inconsistent:
        return "metadata INCONSISTENT"
    if metadata.rank_shortfall == 0 and metadata.check_shortfall == 0:
        return "metadata trusted"
    return (f"metadata rank {metadata.rank}/24"
            f" · +{metadata.check_shortfall} checks to trust")


def close_row(snapshot: dict[str, object]) -> str:
    """The fountain row's text for one close snapshot.

    §10.3.2: the K/fountain row is causal.  `--complete` does not suspend
    that (v0.32) — K is the certified metadata word, so it prints as soon as
    the metadata is trusted, beside the §10.4 count-only block reach; only
    rank and solved state, which a deferred barrier genuinely does not
    compute, are reported as deferred, and never as zero.
    """
    record = snapshot.get("record")
    status = str(getattr(getattr(record, "status", None), "value", "open"))
    progress = snapshot.get("progress")
    if snapshot.get("deferred_counts"):
        blocks = getattr(progress, "blocks", ()) or ()
        k_total = getattr(progress, "k_total", None)
        parts = [
            f"received {getattr(progress, 'symbols_used', 0)}"
            + (f"/{k_total} K" if k_total is not None
               else " · K unavailable")]
        if blocks:
            needed = sum(row.needed for row in blocks)
            parts.append(f"reach {sum(row.have for row in blocks)}"
                         f"/{needed} over {len(blocks)} block(s)")
        phrase = metadata_phrase(getattr(progress, "metadata", None))
        if phrase is not None:
            parts.append(phrase)
        parts.append("close deferred · rank/solve deferred")
        return " · ".join(parts)
    parts = []
    if progress is not None:
        k_total = progress.k_total
        parts.append(
            f"received {progress.symbols_used}"
            + (f"/{k_total} K" if k_total is not None
               else " · K unavailable"))
        blocks = progress.blocks
        if blocks:
            solved = sum(1 for row in blocks if row.solved)
            rank = sum(row.rank for row in blocks)
            needed = sum(row.needed for row in blocks)
            parts.append(f"rank {rank}/{needed}"
                         f" · blocks {solved}/{len(blocks)}")
        phrase = metadata_phrase(progress.metadata)
        if phrase is not None:
            parts.append(phrase)
    if status == "verified" and record is not None:
        sha = str(getattr(record, "payload_sha256", "") or "")
        parts.append(f"VERIFIED · {getattr(record, 'payload_length', '?')}"
                     f" bytes · sha {sha[:16]}…")
    else:
        parts.append(f"close {status}")
    return " · ".join(parts)


def _lane_row(view: object) -> str:
    context = view._context
    ordinal = getattr(context, "level_ordinal", None)
    level = ("-" if ordinal is None else
             f"{ordinal + 1}/"
             f"{getattr(context, 'levels_total', None) or '?'}")
    ppc_value = getattr(context, "ppc", None)
    ppc = "-" if ppc_value is None else f"{ppc_value[0]}/{ppc_value[1]}"
    dpi_value = getattr(context, "effective_dpi", None)
    dpi = "-" if dpi_value is None else f"{dpi_value:.0f}"
    # v0.33 D14a: the phase tail carries the session phase driver's
    # rung/tail announcement beside the stage phase ("rung 2ppc ·
    # capture 2/3", "mop-up tail · 14 parked").
    phase = view._phase
    session_phase = getattr(view, "_session_phase", None)
    if session_phase:
        phase = f"{phase} · {session_phase}"
    # PK4.3: a supplemental lane forces a campaign arm.  Its lane id
    # already spells that out; the tag makes it unmissable, because the
    # one thing an operator must not do is read a u-lane's numbers as the
    # standard receiver's.
    arm = getattr(view._scan, "uplift_arm", None)
    lane_id = getattr(context, "lane_id", None) or "-"
    lane_text = f"{lane_id} [uplift {arm}]" if arm else lane_id
    return (f"lane     capture {(view._capture_sha or '-')[:12]}"
            f" ({view._captures_seen}/{view._captures_requested or '?'})"
            f" · lane {lane_text}"
            f" · level {level} · {ppc} ppc · {dpi} dpi · {phase}")


def _scraps_row(view: object, default: int) -> str:
    if not view._scan.survey_seen:
        # §10.3.2: cold/no-op region classification is unavailable — never
        # reconstructed from placement rows, never printed as zero.
        return "scraps   region states unavailable before survey"
    located = len(view._scan.regions)
    placed = sum(1 for row in view._scan.regions
                 if row.state in ("accepted", "redundant"))
    working = sum(1 for row in view._scan.regions
                  if row.state in ("surveyed", "active"))
    covered = view._covered_payload.get(default, 0)
    registered = view._payload_cells_per_page
    footprint = (f"{covered / registered:.1%} ({covered}/{registered} cells)"
                 if registered else "unavailable")
    return (f"scraps   {located} located · {placed} placed ·"
            f" {max(0, located - placed - working)} unresolved ·"
            f" mapped footprint {footprint} on page {default}")


def _address_row(view: object) -> str:
    placements = sum(row[0] for row in view._lane_address.values())
    unresolved = sum(row[1] for row in view._lane_address.values())
    quarantined = sum(row[2] for row in view._lane_address.values())
    tally: dict[int, int] = {}
    for state in view._word_state.values():
        tally[state] = tally.get(state, 0) + 1
    total = view._scan.queue_total
    windows = (f"windows {view._windows_attempted}"
               + (f"/{total}" if total is not None else "")
               + f" · deferred {view._scan.deferred}")
    # v0.43: "match" spans both green authorities — a word-route SOLVE is a
    # matching decode by construction — so the row text is unchanged by the
    # pane-C tri-state split.
    matched = tally.get(_WORD_SOLVED, 0) + tally.get(_WORD_VALIDATED, 0)
    return (f"address  {windows} ·"
            f" placements {placements} accepted, {unresolved} unresolved,"
            f" {quarantined} quarantined ·"
            f" words {matched} match,"
            f" {tally.get(_WORD_FLOOR, 0)} insufficient,"
            f" {tally.get(_WORD_FAILED, 0)} refused,"
            f" {tally.get(_WORD_CONFLICT, 0)} conflict")


def _plane_split(view: object) -> str:
    """P1 (docs/INDEPENDENT-PLANES.md §6): certified/slots PER PLANE.

    A colour row's whole-run certificate total hides the only asymmetry
    that matters on this engine — every Y-vs-C question in the 2026-08
    campaign needed a multi-GB state load to answer.  Returns "" for a
    one-stream row (K, and the packed cmy7 rows), so those rows read
    exactly as before, and "" before any payload work, since the slot
    denominator is the pages actually reached, never a guess.
    """
    streams = tuple(getattr(view, "_streams", ()) or ())
    if len(streams) < 2 or not view._tiles:
        return ""
    tile_y, tile_x = view._tiles_yx
    slots = len(view._tiles) * tile_y * tile_x
    certified = np.zeros(len(streams), np.int64)
    for states in view._tiles.values():
        certified += (states == _TILE_STATE_CERTIFIED).sum(axis=(1, 2))
    return ", ".join(
        f"{stream} {int(count)}/{slots}"
        for stream, count in zip(streams, certified))


def _ldpc_row(view: object) -> str:
    failed_tiles = floor_tiles = 0
    for states in view._tiles.values():
        counts = np.bincount(states.ravel(), minlength=5)
        failed_tiles += int(counts[_TILE_STATE_FAILED])
        floor_tiles += int(counts[_TILE_STATE_FLOOR])
    evaluations, calls, _crc_ok, bp150 = view._counters
    # The per-plane split rides the payload row (it IS a payload count),
    # not a seventh row: the block is fixed at six.  It sits right after
    # the total it qualifies, not at the end, so the one row that can
    # outgrow a narrow window does not clip it away.
    planes = _plane_split(view)
    # The D5 drop tally rides beside divergences: both are committed-
    # truth consistency counters (2026-08-02 ruling), and a new pane
    # row would violate the fixed six-row block.  Flips carry the
    # two-view signal; drops alone are expected overlap geometry.
    return (f"LDPC     calls {calls + view._trans_calls}"
            f" ({evaluations} attempts folded) ·"
            f" certificates {view._certs_committed + view._trans_certs}"
            f" (+{bp150 + view._trans_bp150} BP150)"
            + (f" [{planes}]" if planes else "")
            + f" · {failed_tiles} failed · {floor_tiles} low"
            f" · divergences {view._divergences}"
            f" · mop-up drops {view._mopup_dropped}"
            f" (flips {view._mopup_flips})")


def _field_phrase(view: object) -> str:
    """W5 (PLANE-FIELDS.md §6.2): the format row's compact ``F ...`` fold,
    delegated to the view's ``FieldPaneState`` (field_view.py) -- "" while
    no plane_fields Details have arrived, so the row then reads exactly as
    it did before this feature existed."""
    state = getattr(view, "_field", None)
    return state.phrase() if state is not None else ""


def status_rows(view: object, default: int) -> list[str]:
    """Six rows, §10.3.2 order (v0.27): format/lane/scraps/address/LDPC/
    fountain — scraps are lane-scoped, so lane context precedes.

    The format row is the least-loaded and most stable of the six (set
    once at session.open, unlike the others which grow through the run),
    so it is where W5's compact plane-field phrase folds in when there is
    one -- appended, never replacing anything, so the row reads exactly as
    before whenever no plane_fields Details have arrived."""
    domain = (f"{len(view._page_domain)} page domain"
              if view._page_domain else "open page domain")
    format_row = (
        f"format   {view._spec_id} · policy {view._policy_id or '-'}"
        f" · {view._qualification or '-'} · {domain}")
    field_text = _field_phrase(view)
    if field_text:
        format_row += f" · {field_text}"
    return [
        format_row,
        _lane_row(view),
        _scraps_row(view, default),
        _address_row(view),
        _ldpc_row(view),
        f"fountain {view._close_row}",
    ]


__all__ = ["close_row", "metadata_phrase", "status_rows", "_field_phrase"]
