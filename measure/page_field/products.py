"""What the field harness reports: the records, the tables, the figures.

The three records that BECOME a block of `fields.json` are here with the
product they become: `Declaration` is its `source`, `Counts` its
`counts`, `PageField` an entry of its `pages`.  (`Archive`, the fourth
record the harness fills in, stays with the identity gate that reads it:
the driver, not this module, turns it into the rest of the `source`
block.)  Nothing here calls back into `estimate.py`, so the import runs
one way — `estimate.py` imports this module, never the reverse — and
nothing here does the driver's work: no raster is opened, no capture
ingested, no job scheduled.  The two tables DO read the store, for rows
it has already published (`field_observations`, `evidence_revision`) and
nothing else.

`column_profile` is read back out of `fields.json` by `compare.py` and
`lane_gauge.py`, which is why it is a function beside the figure that
draws it rather than a step inside the figure: there is one definition
of the profile the sinusoid is scored on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from holo.receiver import data, store as store_module
from holo.receiver.diag import fields_pane, panes
from holo.receiver.format import identity
from holo.receiver.lib import plane_field

#: Pixels per tile in the per-plane field PNG.  Full tile resolution,
#: not the diag event's 24-block cap: the harness holds the whole grid
#: and the sinusoid is a per-column shape.  A page with few tiles is
#: drawn at bigger tiles rather than in a pane narrower than its own
#: caption (`tile_px`).
TILE_PX: int = 16
MIN_PANE_W: int = 360
FOOTER_LINES: int = 4
#: Cross-section plot box.
CROSS_H: int = 260
CROSS_PAD: int = 44


def tile_px(tiles_x: int) -> int:
    return max(TILE_PX, -(-MIN_PANE_W // max(1, int(tiles_x))))


@dataclass(frozen=True)
class Declaration:
    """The captures a run was given, and the identity it was given them
    under — everything `intake` needs and the store's row."""

    scans: tuple[Path, ...]
    dpis: tuple[float, ...]
    format_ref: str
    max_pages: int | None


@dataclass(frozen=True)
class PageField:
    """One page's solve, as the harness reports it.

    `solved` is the producer's own event, so the residuals per (capture,
    plane), the per-plane uncertainty and the evidence revision are the
    numbers the run itself publishes and not a re-derivation beside
    them.  `rows` is that event's per-plane rows with their three grid
    columns swapped for the FACT's full-resolution ones: the event pools
    its grids to the diag cap and the harness draws one arrow per tile.
    """

    page: int
    tiles_yx: tuple[int, int]
    captures: tuple[str, ...]
    facts: tuple[data.PlaneField, ...]
    rows: tuple[data.FieldPlaneRow, ...]
    solved: data.FieldSolved


@dataclass(frozen=True)
class Counts:
    """What the harness did, in the units B6 asks about.

    `captures` counts DISTINCT captures, not declared scans: a source
    declared twice is one capture, as it is in a production run.
    """

    captures: int
    pages: int
    collections: int
    pages_solved: int
    lane_page_fits: int
    collect_cpu_s: float
    solve_cpu_s: float


# ---------------------------------------------------- the reported rows

def full_resolution_rows(event: data.FieldSolved,
                         facts: tuple[data.PlaneField, ...],
                         ) -> tuple[data.FieldPlaneRow, ...]:
    """The event's own per-plane rows, redrawn at TILE resolution.

    Every scalar — the medians, the uncertainty, `known`, the counts —
    is the producer's and is copied, not recomputed; only the three grid
    columns are replaced, because the event pools them to the diag cap
    (`fields.DIAG_GRID_MAX`) and this harness draws one arrow per tile
    of a 37-column sinusoid.
    """
    return tuple(
        replace(row,
                delta_grid_dots_xy=np.asarray(fact.delta_dots_xy,
                                              np.float32),
                magnitude_grid_dots=np.hypot(
                    np.asarray(fact.delta_dots_xy)[..., 0],
                    np.asarray(fact.delta_dots_xy)[..., 1]).astype(
                        np.float32),
                has_data=np.asarray(fact.support, np.float64) > 0.0)
        for row, fact in zip(event.planes, facts, strict=True))


# ----------------------------------------------------------- the tables

def _residual_rows(page: PageField, plane: int) -> list[dict]:
    """This plane's residual energy per capture, never summed with the
    others' (design §2.6, W8 R-F)."""
    return [{"capture_id": capture, "energy": float(energy),
             "expected": float(expected), "n_observations": int(count)}
            for capture, row_plane, energy, expected, count
            in page.solved.residual_by_capture_plane
            if int(row_plane) == int(plane)]


def _source_census(store: store_module._Store, page: int) -> list[dict]:
    """How many observations each TEMPLATE SOURCE bought, per plane.

    Design §7.1 owes this number: no product in this record splits a
    page's support by source, so what the certified template reaches
    against what the furniture reaches has never been measured on a real
    sheet — and that is the number the blind tier's retirement would be
    re-opened on.
    """
    rows: dict[tuple[int, int], int] = {}
    for fact in store.field_observations(page):
        planes = np.asarray(fact.plane, np.int64)
        sources = np.asarray(fact.source, np.int64)
        for plane, source in zip(planes.tolist(), sources.tolist()):
            rows[(plane, source)] = rows.get((plane, source), 0) + 1
    return [{"plane": plane, "plane_name": identity.CMY_PLANE_ORDER[plane],
             "source": source,
             "source_name": plane_field.SOURCE_NAMES[source],
             "n_observations": count}
            for (plane, source), count in sorted(rows.items())]


def fields_json(declaration: Declaration, source: dict,
                solved: tuple[PageField, ...], counts: Counts,
                store: store_module._Store) -> dict:
    return {
        "source": {**source,
                   "format_ref": declaration.format_ref,
                   "scans": [str(path) for path in declaration.scans],
                   "dpis": list(declaration.dpis),
                   "max_pages": declaration.max_pages},
        "counts": {"captures": counts.captures, "pages": counts.pages,
                   "collections": counts.collections,
                   "pages_solved": counts.pages_solved,
                   "lane_page_fits": counts.lane_page_fits,
                   "collect_cpu_s": round(counts.collect_cpu_s, 3),
                   "solve_cpu_s": round(counts.solve_cpu_s, 3)},
        "field_noise_dots": plane_field.FIELD_NOISE_DOTS,
        "pages": [{
            "page": page.page,
            "tiles_yx": list(page.tiles_yx),
            "captures": list(page.captures),
            "field_revision": page.solved.revision,
            "passes": page.solved.passes,
            "converged": page.solved.converged,
            "evidence_revision_by_capture": {
                capture: store.evidence_revision(capture, page.page)
                for capture in page.captures},
            "support_by_source": _source_census(store, page.page),
            "planes": [{
                "plane": row.plane,
                "plane_name": row.plane_name,
                "known": row.known,
                "median_delta_dots": row.median_delta_dots,
                "median_uncertainty_dots": row.median_uncertainty_dots,
                "support_tiles": row.support_tiles,
                "n_observations": row.n_observations,
                "n_captures": row.n_captures,
                "delta_dots_xy": np.asarray(
                    page.facts[row.plane].delta_dots_xy).tolist(),
                "support": np.asarray(
                    page.facts[row.plane].support).tolist(),
                "uncertainty_dots": np.asarray(
                    page.facts[row.plane].uncertainty_dots).tolist(),
                "residual_by_capture": _residual_rows(page, row.plane),
            } for row in page.rows],
        } for page in solved],
    }


# ---------------------------------------------------------- the figures

def field_png(page: PageField, row: data.FieldPlaneRow) -> bytes:
    """One plane's field at TILE resolution, in the band's vocabulary.

    The diag band pools three planes into at most 24 blocks per axis and
    draws them staggered; this draws ONE plane at one arrow per tile,
    which is what a 37-column sinusoid needs.  Everything else — the
    exaggeration, the hues, the noise-scale shading, the black blind
    tile — is `diag/fields_pane`'s, so the harness's picture and the
    run's own band read the same way.
    """
    tiles_y, tiles_x = page.tiles_yx
    step = tile_px(tiles_x)
    width, body_h = tiles_x * step, tiles_y * step
    blocks, deltas, magnitudes = fields_pane._live_blocks(row)
    factor = fields_pane.exaggeration(((row, blocks, deltas, magnitudes),),
                                      float(step), float(step))
    top = fields_pane.TITLE_H
    pane = panes.Pane(width, top + body_h + 8
                      + FOOTER_LINES * fields_pane.TEXT_STEP)
    pane.rect((0, 0, width - 1, top - 1), fill=fields_pane.TITLE_FILL,
              outline=fields_pane.TITLE_RULE)
    pane.text((6, 4), f"FIELD x{factor:.4g} · page {page.page} · plane "
                      f"{row.plane_name} · arrow = registration delta",
              fields_pane.TITLE_TEXT, fields_pane.TEXT_SIZE)
    pane.rect((0, top, width - 1, top + body_h - 1),
              fill=fields_pane.BODY_BG, outline=fields_pane.BODY_OUTLINE)
    hue = fields_pane.PLANE_HUE[row.plane_name]
    support = np.asarray(row.has_data, bool)
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            box = (tx * step, top + ty * step,
                   (tx + 1) * step - 1, top + (ty + 1) * step - 1)
            if not support[ty, tx]:
                pane.rect(box, fill=fields_pane.HOLE)
            elif (float(np.hypot(*np.asarray(row.delta_grid_dots_xy,
                                             np.float64)[ty, tx]))
                    >= plane_field.FIELD_NOISE_DOTS):
                pane.rect(box, fill=fields_pane.SHADE)
    for (ty, tx), delta in zip(blocks, deltas):
        centre = ((tx + 0.5) * step, top + (ty + 0.5) * step)
        fields_pane.draw_arrow(
            pane.draw, centre,
            (centre[0] + factor * delta[0], centre[1] + factor * delta[1]),
            hue)
    pane.rows(6, top + body_h + 4, (
        f"median |delta| {row.median_delta_dots:.4f} dots · support "
        f"{row.support_tiles}/{tiles_y * tiles_x} tiles",
        f"observations {row.n_observations} · captures pooled "
        f"{row.n_captures}",
        f"shaded at |delta| >= {plane_field.FIELD_NOISE_DOTS:.2f} dots · "
        f"black = no evidence",
        ("plane unknown — no template on any tile" if not row.known else
         f"median uncertainty {row.median_uncertainty_dots:.4f} dots · "
         f"per-tile bars in fields.json"),
    ), size=fields_pane.TEXT_SIZE)
    return panes.encode_png(pane.array())


def column_profile(delta_dots_xy: np.ndarray,
                   support: np.ndarray) -> np.ndarray:
    """Per column, the x delta with the row direction taken out.

    The sinusoid view: e033 measured the AltaLink's Y plane as a
    function of the page's x axis, and the analyzer reports the same
    shape as a 37-long profile.  The column effects of an additive
    row-plus-column least squares over the tiles WITH EVIDENCE, which
    is the plain column mean wherever a column's support is complete
    and does not read missing rows as signal where it is not: a column
    that lost its bottom rows otherwise reports the mean of the rows it
    kept against neighbours that kept all of theirs, and a field that
    varies down the page turns that into a peak (measured: the W5 sim's
    Y profile peaks at 0.72 dots that way against a true column mean
    near zero, and at 0.15 like this).  A column no evidence reached
    reads zero, which is what the field itself reads there.  Arrays
    rather than a fact, because `compare.py` reads them back out of
    `fields.json` and there is one definition of this profile.
    """
    delta = np.asarray(delta_dots_xy, np.float64)[..., 0]
    live = np.asarray(support, np.float64) > 0.0
    tiles_y, tiles_x = live.shape
    ys, xs = np.nonzero(live)
    if not ys.size:
        return np.zeros(tiles_x, np.float64)
    design = np.zeros((ys.size, tiles_y + tiles_x), np.float64)
    design[np.arange(ys.size), ys] = 1.0
    design[np.arange(ys.size), tiles_y + xs] = 1.0
    effects, *_ = np.linalg.lstsq(design, delta[live], rcond=None)
    profile = effects[tiles_y:] + effects[:tiles_y][live.any(axis=1)].mean()
    return np.where(live.any(axis=0), profile, 0.0)


def column_coverage(support: np.ndarray) -> np.ndarray:
    """Per column, the tiles with evidence — what the profile rests on."""
    return (np.asarray(support, np.float64) > 0.0).sum(axis=0)


def cross_section_png(page: PageField) -> bytes:
    """The three planes' column profiles on one axis.

    Y is the measurement the sinusoid lives in; C and M are on the same
    axes as the control — the gauge drops their common mode, so a page
    whose planes are in register draws them flat along the zero line.
    """
    profiles = {row.plane_name: column_profile(
        page.facts[row.plane].delta_dots_xy, page.facts[row.plane].support)
        for row in page.rows}
    tiles_x = page.tiles_yx[1]
    width = max(2 * CROSS_PAD + tiles_x * TILE_PX, MIN_PANE_W)
    span = max(0.05, max(float(np.abs(values).max())
                         for values in profiles.values()))
    top = fields_pane.TITLE_H
    pane = panes.Pane(width, top + CROSS_H + 8
                      + FOOTER_LINES * fields_pane.TEXT_STEP)
    pane.rect((0, 0, width - 1, top - 1), fill=fields_pane.TITLE_FILL,
              outline=fields_pane.TITLE_RULE)
    pane.text((6, 4), f"FIELD cross-section · page {page.page} · x delta "
                      f"per tile column · +-{span:.3f} dots",
              fields_pane.TITLE_TEXT, fields_pane.TEXT_SIZE)
    pane.rect((0, top, width - 1, top + CROSS_H - 1),
              fill=fields_pane.BODY_BG, outline=fields_pane.BODY_OUTLINE)
    zero = top + CROSS_H / 2.0
    pane.draw.line((CROSS_PAD, zero, width - CROSS_PAD, zero),
                   fill=fields_pane.BODY_OUTLINE)
    step = (width - 2 * CROSS_PAD) / max(1, tiles_x - 1)
    for name, values in profiles.items():
        points = [(CROSS_PAD + index * step,
                   zero - value / span * (CROSS_H / 2.0 - 8))
                  for index, value in enumerate(values)]
        pane.draw.line(points, fill=fields_pane.PLANE_HUE[name], width=2)
    coverage = {row.plane_name: column_coverage(page.facts[row.plane].support)
                for row in page.rows}
    pane.rows(6, top + CROSS_H + 4, tuple(
        [f"{name} peak {float(np.abs(values).max()):.4f} dots · "
         f"span {float(values.max() - values.min()) / 2.0:.4f} half-p2p · "
         f"thinnest column {int(coverage[name].min())}/{page.tiles_yx[0]}"
         for name, values in profiles.items()]
        + [f"columns {tiles_x} · zero line = sample at the pose"]),
        size=fields_pane.TEXT_SIZE)
    return panes.encode_png(pane.array())


def write_products(out: Path, payload: dict,
                   solved: tuple[PageField, ...]) -> tuple[str, ...]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "fields.json").write_text(json.dumps(payload, indent=1))
    written = ["fields.json"]
    for page in solved:
        for row in page.rows:
            name = f"field-page{page.page}-{row.plane_name}.png"
            (out / name).write_bytes(field_png(page, row))
            written.append(name)
        name = f"cross-section-page{page.page}.png"
        (out / name).write_bytes(cross_section_png(page))
        written.append(name)
    return tuple(written)

