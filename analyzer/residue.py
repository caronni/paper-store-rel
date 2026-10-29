"""Stage 0 — census and targeting, with no pixels (DESIGN §3).

One :class:`~analyzer.types.LedgerRow` per (page, ty, tx, stream), in a
pinned order so attribution is reproducible.  Everything here is either
format arithmetic or a count over the run's own facts; nothing opens a
raster.

THE THREE COLUMNS THAT NEED SAYING OUT LOUD:

* **covered** — some accepted placement's page footprint (through
  ``calibrate.window_page_cells``) intersects the tile.  Uncovered tiles
  get the verdict ``uncovered`` and are never targets: J's argv declares
  100 pages and the confetti fragments touch a few hundred tiles.

* **band** — per stream, over COVERED columns only.  A column with fewer
  than :data:`MIN_COVERED_PER_COLUMN` covered tiles is ``unclassified``.
  ``dead`` is the EVIDENCE-BACKED class: the exact (Clopper-Pearson)
  one-sided upper bound on the column's certified fraction must fall
  below 0.25.  Everything else below 0.75 is ``marginal`` and 0.75 and
  above is ``live``.  (DESIGN §3 spells the three classes as
  "upper bound < 0.25 / fraction in [0.25, 0.75) / else live", which
  routes a 0.1-fraction column with only 12 covered tiles into `live`;
  reading the residual as `marginal` is the only order that keeps `dead`
  conservative.  Recorded as an interpretation, not a silent change.)
  ``band_any`` is the cross-stream union: C, M and Y fail in the same
  columns on sheet H.

* **n_discriminating_labels** — the corrected label arithmetic (DESIGN
  §1 [R]).  Every WORD site renders state 0 or 3, so C == M and Y == 0
  at all 100 of them: the word field is not a C-vs-M separation set.
  Only DUST cells discriminate, and only some of them — of the 6-cycle
  (1, 2, 4, 5, 6, 7), states {1, 2, 5, 6} have C != M and states
  {4, 5, 6, 7} have Y == 1, so ~13 of 20 per tile per target.  A
  certified NEIGHBOUR of the same stream contributes its whole payload
  (and, for C/M, only where the sibling stream is certified too).  The
  target tile's OWN payload never counts, whether or not it is certified
  — that is §4.5's target-key exclusion, applied uniformly so the number
  means the same thing on a residue row and on a parity row.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy import stats as scipy_stats

from holo.receiver.format import close as fmt_close
from holo.receiver.format import fountain
from holo.receiver.plugins import color_sites

from .close import slot_items
from .inputs import TILE_CELLS, page_tile_coverage
from .types import (BAND_DEAD, BAND_LIVE, BAND_MARGINAL, BAND_UNCLASSIFIED,
                    Key, LedgerRow, PLANE_OF, RunInputs,
                    VERDICT_OPEN, VERDICT_UNCOVERED)

#: Below this many covered tiles a column carries no band verdict.
MIN_COVERED_PER_COLUMN = 12

#: Clopper-Pearson one-sided level for the `dead` bound.
BAND_ALPHA = 0.05
BAND_DEAD_BOUND = 0.25
BAND_LIVE_FLOOR = 0.75

#: DESIGN §4.3: 32 cells of halo for Y, 16 for C and M.
HALO_CELLS: dict[str, int] = {"C": 16, "M": 16, "Y": 32}

_BAND_ORDER = (BAND_DEAD, BAND_MARGINAL, BAND_LIVE, BAND_UNCLASSIFIED)


# ------------------------------------------------------------ the frame

def _projection_page(inputs: RunInputs, page: int
                     ) -> tuple[np.ndarray, np.ndarray]:
    """(bits, known) over the whole page, from furniture + certificates.

    TARGET-INCLUSIVE, and therefore a COUNTING aid only: every certified
    stream's own payload is laid down here, so a KnownFrame (W1b, DESIGN
    §4.5) must never be cut out of this array or its cache — the target
    key's exclusion is per-target and belongs to `frame.py`.  The counts
    below subtract the target tile's own payload explicitly.

    `color_sites.certified_projection` is CALLED per tile — it already
    lays the word and dust furniture and every certified stream's payload
    and is the format's own arithmetic.  A tile with no certificate still
    contributes its 120 furniture sites, so the frame is built by hand in
    that case from the same call on a one-tile certificate view.
    """
    cache = inputs._cache.setdefault("projection_page", {})
    hit = cache.get(page)
    if hit is not None:
        return hit
    tiles_y, tiles_x = inputs.tiles_yx
    cells_y, cells_x = inputs.cells_yx
    bits = np.zeros((cells_y, cells_x, 3), np.uint8)
    known = np.zeros((cells_y, cells_x, 3), np.bool_)
    certificates = inputs.certificates
    for ty in range(tiles_y):
        y0 = ty * TILE_CELLS
        for tx in range(tiles_x):
            projection = color_sites.certified_projection(
                inputs.row, inputs.geometry, page, ty, tx, certificates)
            if projection is None:
                projection = _furniture_only(inputs, page, ty, tx)
            tile_bits, tile_known = projection
            x0 = tx * TILE_CELLS
            bits[y0:y0 + TILE_CELLS, x0:x0 + TILE_CELLS] = tile_bits
            known[y0:y0 + TILE_CELLS, x0:x0 + TILE_CELLS] = tile_known
    bits.setflags(write=False)
    known.setflags(write=False)
    cache[page] = (bits, known)
    return bits, known


def _furniture_only(inputs: RunInputs, page: int, ty: int, tx: int
                    ) -> tuple[np.ndarray, np.ndarray]:
    """The 120 furniture sites of a tile with no certificate at all.

    `certified_projection` returns None when no stream of the tile is
    certified, so the word/dust half of its own body is reproduced here
    from the same two calls it makes.
    """
    from holo.receiver.format import pilots, tile_codec
    row, geometry = inputs.row, inputs.geometry
    counter = row.tile_counter(page, ty, tx)
    bits = np.zeros((TILE_CELLS, TILE_CELLS, 3), np.uint8)
    known = np.zeros((TILE_CELLS, TILE_CELLS, 3), np.bool_)
    word = geometry.word_cells_yx
    dust = geometry.extra_cells_yx
    word_states = pilots.color_word_states(row.seed, (counter,), row)[0]
    dust_states = pilots.dust_state_values(row.seed, (counter,), row)[0]
    bits[word[:, 0], word[:, 1]] = tile_codec.states_to_planes(word_states)
    bits[dust[:, 0], dust[:, 1]] = tile_codec.states_to_planes(dust_states)
    known[word[:, 0], word[:, 1]] = True
    known[dust[:, 0], dust[:, 1]] = True
    return bits, known


def discriminating_mask(bits: np.ndarray, known: np.ndarray,
                        stream_id: str) -> np.ndarray:
    """Cells that separate the target plane from its confusable sibling.

    C and M: cells where the two differ (they are each other's only
    confusion — the word field holds C == M everywhere).  Y: cells where
    Y == 1, the scarce class (Y is 0 at every word site).
    """
    if stream_id in ("C", "M"):
        return known[..., 0] & known[..., 1] & (bits[..., 0] != bits[..., 1])
    if stream_id == "Y":
        return known[..., 2] & (bits[..., 2] == 1)
    raise ValueError(f"unknown stream {stream_id!r}")


def payload_cell_mask(inputs: RunInputs) -> np.ndarray:
    """(64, 64) True at the tile's payload cells (not word, not dust)."""
    cached = inputs._cache.get("payload_cell_mask")
    if cached is None:
        cached = np.zeros((TILE_CELLS, TILE_CELLS), np.bool_)
        cached.reshape(-1)[
            np.asarray(inputs.geometry.payload_flat, np.int64)] = True
        cached.setflags(write=False)
        inputs._cache["payload_cell_mask"] = cached
    return cached


def _own_payload_counts(inputs: RunInputs, page: int, ty: int, tx: int,
                        stream_id: str) -> tuple[int, int]:
    """(known, discriminating) the TARGET tile's own payload contributes.

    Subtracted from every halo count so the target key never labels
    itself (DESIGN §4.5, minor m1).
    """
    key: Key = (page, ty, tx, stream_id)
    if key not in inputs.certificates:
        return 0, 0
    bits, known = _projection_page(inputs, page)
    y0, x0 = ty * TILE_CELLS, tx * TILE_CELLS
    tile_bits = bits[y0:y0 + TILE_CELLS, x0:x0 + TILE_CELLS]
    tile_known = known[y0:y0 + TILE_CELLS, x0:x0 + TILE_CELLS]
    payload = payload_cell_mask(inputs)
    plane = PLANE_OF[stream_id]
    n_known = int(np.count_nonzero(tile_known[..., plane] & payload))
    n_disc = int(np.count_nonzero(
        discriminating_mask(tile_bits, tile_known, stream_id) & payload))
    return n_known, n_disc


def halo_label_counts(inputs: RunInputs, page: int, ty: int, tx: int,
                      stream_id: str, *, halo_cells: int | None = None
                      ) -> tuple[int, int]:
    """(known_cells_in_halo, n_discriminating_labels) for one target."""
    if halo_cells is None:
        halo_cells = HALO_CELLS[stream_id]
    bits, known = _projection_page(inputs, page)
    cells_y, cells_x = inputs.cells_yx
    y0 = max(0, ty * TILE_CELLS - halo_cells)
    y1 = min(cells_y, (ty + 1) * TILE_CELLS + halo_cells)
    x0 = max(0, tx * TILE_CELLS - halo_cells)
    x1 = min(cells_x, (tx + 1) * TILE_CELLS + halo_cells)
    sub_bits = bits[y0:y1, x0:x1]
    sub_known = known[y0:y1, x0:x1]
    plane = PLANE_OF[stream_id]
    n_known = int(np.count_nonzero(sub_known[..., plane]))
    n_disc = int(np.count_nonzero(
        discriminating_mask(sub_bits, sub_known, stream_id)))
    own_known, own_disc = _own_payload_counts(inputs, page, ty, tx,
                                              stream_id)
    return n_known - own_known, n_disc - own_disc


# ---------------------------------------------------------------- bands

def _clopper_pearson_upper(k: int, n: int, alpha: float) -> float:
    """Exact one-sided upper bound on a binomial proportion."""
    if n <= 0:
        return 1.0
    if k >= n:
        return 1.0
    return float(scipy_stats.beta.ppf(1.0 - alpha, k + 1, n - k))


def column_bands(inputs: RunInputs, page: int, covered: np.ndarray
                 ) -> dict[str, np.ndarray]:
    """Per-column band class for each stream, plus the union `any`.

    `covered` is the (tiles_y, tiles_x) boolean coverage of the page.
    """
    tiles_y, tiles_x = inputs.tiles_yx
    out: dict[str, np.ndarray] = {}
    streams = [fact.stream_id for fact in inputs.row.streams]
    for stream_id in streams:
        classes = np.full(tiles_x, BAND_UNCLASSIFIED, dtype=object)
        for tx in range(tiles_x):
            column = covered[:, tx]
            n = int(np.count_nonzero(column))
            if n < MIN_COVERED_PER_COLUMN:
                continue
            k = sum(1 for ty in range(tiles_y)
                    if column[ty]
                    and (page, ty, tx, stream_id) in inputs.certificates)
            fraction = k / n
            upper = _clopper_pearson_upper(k, n, BAND_ALPHA)
            if fraction < BAND_DEAD_BOUND and upper < BAND_DEAD_BOUND:
                classes[tx] = BAND_DEAD
            elif fraction < BAND_LIVE_FLOOR:
                classes[tx] = BAND_MARGINAL
            else:
                classes[tx] = BAND_LIVE
        out[stream_id] = classes
    union = np.full(tiles_x, BAND_UNCLASSIFIED, dtype=object)
    for tx in range(tiles_x):
        seen = {out[stream_id][tx] for stream_id in streams}
        for name in _BAND_ORDER:
            if name in seen:
                union[tx] = name
                break
    out["any"] = union
    return out


def band_runs(classes: Sequence[str]) -> tuple[tuple[str, int, int], ...]:
    """Maximal runs of equal class as (class, first_tx, last_tx)."""
    runs: list[tuple[str, int, int]] = []
    for tx, name in enumerate(classes):
        if runs and runs[-1][0] == name and runs[-1][2] == tx - 1:
            runs[-1] = (name, runs[-1][1], tx)
        else:
            runs.append((str(name), tx, tx))
    return tuple(runs)


# --------------------------------------------------------------- census

def _attempts(events: Mapping[Key, Sequence[dict]] | None,
              key: Key) -> dict:
    if events is None:
        return {}
    rows = events.get(key)
    if not rows:
        return {"n": 0, "results": {}, "run_mint": False}
    results: dict[str, int] = {}
    iters: list[int] = []
    for row in rows:
        result = str(row.get("result"))
        results[result] = results.get(result, 0) + 1
        if row.get("bp_iters") is not None:
            iters.append(int(row["bp_iters"]))
    return {"n": len(rows), "results": results,
            "run_mint": bool(results.get("certified")),
            "max_bp_iters": max(iters) if iters else None}


def census(inputs: RunInputs, *,
           events: Mapping[Key, Sequence[dict]] | None = None,
           pages: Sequence[int] | None = None,
           halo_cells: Mapping[str, int] | None = None,
           check_rank: bool = False) -> list[LedgerRow]:
    """One LedgerRow per (page, ty, tx, stream), order pinned (DESIGN §3)."""
    tiles_y, tiles_x = inputs.tiles_yx
    streams = [fact.stream_id for fact in inputs.row.streams]
    halos = dict(HALO_CELLS if halo_cells is None else halo_cells)
    live = tuple(inputs.live_pages if pages is None else pages)
    ranks = rank_check(inputs) if check_rank else {}
    metadata_known = inputs.metadata_word is not None

    rows: list[LedgerRow] = []
    for page in live:
        coverage = page_tile_coverage(inputs, page)
        covered_map = coverage > 0
        bands = column_bands(inputs, page, covered_map)
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                covered = bool(covered_map[ty, tx])
                certified_here = {
                    stream_id
                    for stream_id in streams
                    if (page, ty, tx, stream_id) in inputs.certificates}
                for stream_id in streams:
                    key: Key = (page, ty, tx, stream_id)
                    certificate = inputs.certificates.get(key)
                    if covered:
                        known_halo, n_disc = halo_label_counts(
                            inputs, page, ty, tx, stream_id,
                            halo_cells=halos[stream_id])
                    else:
                        known_halo, n_disc = 0, 0
                    # `unscoreable` (an address outside the GT domain)
                    # was the third verdict here; it is a scoring
                    # question and left with truth on 2026-09-04 — the
                    # offline scorer reports it against its own payload.
                    verdict = (VERDICT_UNCOVERED if not covered
                               else VERDICT_OPEN)
                    rows.append(LedgerRow(
                        page=page, ty=ty, tx=tx, stream_id=stream_id,
                        esi=inputs.esi(key),
                        covered=covered,
                        certified_by_production=certificate is not None,
                        source=None if certificate is None
                        else str(certificate.source),
                        band=str(bands[stream_id][tx]),
                        band_any=str(bands["any"][tx]),
                        neighbours_certified=_neighbours_certified(
                            inputs, page, ty, tx, stream_id),
                        siblings_certified=tuple(
                            sorted(certified_here - {stream_id})),
                        known_cells_in_halo=known_halo,
                        n_discriminating_labels=n_disc,
                        production_attempts=_attempts(events, key),
                        metadata_known=metadata_known,
                        verdict=verdict,
                        # rank_report is free (report.json); only the
                        # cross-check costs a GF(2) elimination.
                        rank_report=inputs.rank_report,
                        rank_recomputed=ranks.get("rank_recomputed"),
                    ))
    return rows


def _neighbours_certified(inputs: RunInputs, page: int, ty: int, tx: int,
                          stream_id: str) -> int:
    tiles_y, tiles_x = inputs.tiles_yx
    total = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = ty + dy, tx + dx
            if 0 <= ny < tiles_y and 0 <= nx < tiles_x:
                total += int((page, ny, nx, stream_id)
                             in inputs.certificates)
    return total


def residue_rows(rows: Sequence[LedgerRow]) -> list[LedgerRow]:
    """`--targets residue` = covered and uncertified (DESIGN §3)."""
    return [row for row in rows
            if row.covered and not row.certified_by_production]


def _atom(spec: str) -> Callable[[LedgerRow], bool]:
    """One target atom -> the predicate it means (W8 B5).

    `band:<class>`, `stream:<S>`, `siblings:<S,...>` (the row's OTHER
    streams already certified, as a SET — `siblings:M,Y` is the
    population where every per-sibling-state mechanism can fire, and
    `siblings:` alone is the population where none can).
    """
    name, separator, want = spec.partition(":")
    if not separator:
        raise ValueError(f"unknown target spec {spec!r}")
    if name == "band":
        return lambda row: row.band == want
    if name == "stream":
        return lambda row: row.stream_id == want
    if name == "siblings":
        wanted = frozenset(part.strip() for part in want.split(",")
                           if part.strip())
        return lambda row: frozenset(row.siblings_certified) == wanted
    raise ValueError(f"unknown target spec {spec!r}")


def target_rows(rows: Sequence[LedgerRow], spec: str) -> list[LedgerRow]:
    """residue | band:dead | stream:C | siblings:M,Y, joined by `+`.

    DESIGN §3, extended in W8 B5 with the CONJUNCTION: `band:dead+stream:C`
    is the dead band's open C rows and `stream:C+siblings:M,Y` the open C
    rows whose two sibling planes are both certified.  Every atom is
    ANDed over the residue (covered, uncertified); order does not matter;
    an unknown atom raises exactly as an unknown spec always did.
    """
    base = residue_rows(rows)
    if spec == "residue":
        return base
    tests = [_atom(part) for part in spec.split("+") if part.strip()]
    if not tests:
        raise ValueError(f"unknown target spec {spec!r}")
    return [row for row in base if all(test(row) for test in tests)]


# ------------------------------------------------------------ rank cross-check

def rank_check(inputs: RunInputs) -> dict:
    """`report.json`'s close rank, and the same rank re-derived.

    DESIGN §1 [R]: the close's GF(2) rank is READ, never re-derived as a
    yield claim; this recomputation is a cross-check column only and a
    disagreement is a finding.
    """
    out: dict[str, Any] = {
        "rank_report": inputs.rank_report,
        "k_total": inputs.k_total,
        "rank_recomputed": None,
        "agree": None,
    }
    row = inputs.row
    if inputs.k_total is None or not row.pooled_fountain:
        out["reason"] = ("metadata word untrusted" if inputs.k_total is None
                         else "non-pooled fountain: not implemented")
        return out
    # holo3's own code construction (it carries an uneven triplet's column
    # groups); the rank is per (block, group) as the decoder solves it,
    # and a block's rank is its scarcest group's, which is what the run's
    # report.json publishes.
    code = fmt_close._pooled_volume_code(row, int(inputs.k_total))
    decoder = fountain.Decoder(code)
    buckets = slot_items(code, (inputs.esi(key)
                                for key in inputs.certificates))
    per_group: dict[tuple[int, int], int] = {}
    for (block, group), items in sorted(buckets.items()):
        rows_packed = decoder._packed_generator_rows(block, items)
        values = np.zeros((len(items), 1), np.uint8)
        rank, _solved = fountain._ge_solve_gf2(
            rows_packed, values, code.k_per_block[block])
        per_group[(block, group)] = int(rank)
    per_block: dict[int, int] = {}
    for (block, _group), rank in per_group.items():
        per_block[block] = min(rank, per_block.get(block, rank))
    total = sum(per_block.values())
    out["rank_recomputed"] = total
    out["rank_per_block"] = per_block
    out["n_groups"] = int(code.groups.n_groups)
    if code.groups.n_groups > 1:
        out["rank_per_group"] = {f"{block}:{group}": rank
                                 for (block, group), rank
                                 in sorted(per_group.items())}
    out["agree"] = (inputs.rank_report is None
                    or int(inputs.rank_report) == total)
    return out
