#!/usr/bin/env python
"""Scrap/fragment decode scenario — a MANUAL, occasional driver, RUN BY PATH.

    env/bin/python holo2/measure/scrap_decode.py --seed 1 --output-dir OUT

NOT A TEST and not collectable as one: no ``test_`` name, no pytest
fixtures, a ``__main__`` entry point, and it lives outside ``testpaths``
(``holo2/measure`` is not in ``pyproject.toml``'s ``testpaths``). It is
NEVER imported by anything, and it is not a gate. The user's ruling that
this file exists to honour, verbatim (H4-W3-PLAN, "the open items,
RULED", item 3): *"a manual / very occasional measurement, not automated
tooling that gets run over and over."*

WHAT IT DOES. Builds one real page through the real ``src/holo`` generator
(``verdicts/_fixtures.py``'s own ``build_page`` — the exact builder the
verdicts use, reused rather than reinvented), cuts ``--fragment-count``
rectangular scraps out of its real dot field at cell offsets that are
deliberately NOT tile-aligned (``TILE_CELLS`` = 64), renders each one
through the real print/scan pipeline (``_fixtures.render``, the same warp
and cell-error machinery every verdict decode runs through), pastes the
renders onto one or more synthetic "platen" captures (a plain left-to-right
shelf, backing colour outside the scraps), and drives the REAL holo2
composition root (``holo2.cli.decode``, the same call the verdicts and the
CLI skin make) over the platen(s). It then prints an honest report of what
the receiver did: window placement outcomes (placed / retired-by-reason),
grouped by the region each window's own record says it belongs to (one
region is, ideally, one scrap), plus certificate counts, close status and
wall time.

WHY A FRAGMENT EDGE IS THE STRESSOR. A window whose extent straddles a
scrap's paper edge sees real payload texture on one side and backing (or
nothing) on the other — the same shape a window straddling a scissors cut
sees on a real confetti sheet (experiments 018/019/021). Subdivision
(H4-W3-PLAN item 2, PL5) is the wave that teaches such a window to retry
smaller; it is not built yet, so today those windows retire or never
place at all. This driver exists to look at that honestly, before and
after subdivision lands — a question, not a gate.

WHAT IT DOES NOT MODEL, on purpose (kept simple for a by-hand tool): no
whole-fragment rotation (real scraps land at arbitrary angles; this one
keeps every scrap upright, so the stressor here is the CUT EDGE, not
orientation search) and no 2-D bin packing (fragments on one platen sit in
a single row, not a shelf-wrapped or jumbled layout). Both are candidates
for a future revision if a question demands them — not invented here.

DETERMINISTIC under ``--seed`` alone: one ``numpy.random.Generator`` seeds
every fragment's cut offset and its render noise seed, in a fixed order.
``_fixtures.build_page`` itself draws no randomness at all (its payload is
a SHA-256 digest, its symbols a keystream keyed off the format spec), so
the printed CONTENT never depends on ``--seed`` — only where the scissors
fall and the print/scan noise do. No clock, no unseeded RNG anywhere in
this file.

SELF-LOCATING, like ``./confetti.py``: neither ``holo`` nor ``holo2`` is
pip-installed (env honesty), and a driver run BY PATH should not also
demand a ``PYTHONPATH=`` prefix to find the tree it lives in.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE / "verdicts", _ROOT / "src", _ROOT / "holo2" / "src"):
    sys.path.insert(0, str(_path))

from _fixtures import (PageFixture, Render, SPINE_FORMAT,  # noqa: E402
                       build_page, render)

from holo.format import pilots as h_pilots                         # noqa: E402

from holo2 import cli                                            # noqa: E402
from holo2.cli import real_providers, real_source                  # noqa: E402
from holo2.core import publish_once                                # noqa: E402
from holo2.engine.recipe import RECIPE_V1                          # noqa: E402
from holo2.solve import WindowStatus                                # noqa: E402
from holo2.solve.geometry import TILE_CELLS                        # noqa: E402
from holo2.solve.place_admission import E022_MIN_WINDOW_CELLS      # noqa: E402

Scans = tuple[tuple[Path, float], ...]


# --------------------------------------------------------------- the cut

@dataclass(frozen=True)
class Fragment:
    """One scrap: a real crop of the page's own dot field, and its origin."""

    index: int
    y0_cells: int
    x0_cells: int
    span_cells: int
    dots: np.ndarray


def cut_fragments(page: PageFixture, *, count: int, span_cells: int,
                  rng: np.random.Generator) -> tuple[Fragment, ...]:
    """Crop ``count`` scraps out of the page's real dot field.

    Offsets are uniform over the whole printed cell grid and deliberately
    NOT tile-aligned: the honest subdivision stressor is a fragment edge
    that cuts through the middle of a window (and often a tile), exactly
    as scissors do, never conveniently along a lattice line.
    """
    cells_yx = (page.tiles_yx[0] * TILE_CELLS, page.tiles_yx[1] * TILE_CELLS)
    span = min(span_cells, cells_yx[0], cells_yx[1])
    if span < span_cells:
        print(f"scrap_decode: --fragment-span-cells clamped {span_cells} -> "
              f"{span} (the printed field is only {cells_yx} cells)")
    d = page.cell_dots
    fragments = []
    for index in range(count):
        y0 = int(rng.integers(0, cells_yx[0] - span + 1))
        x0 = int(rng.integers(0, cells_yx[1] - span + 1))
        crop = np.array(
            page.dots[y0 * d:(y0 + span) * d, x0 * d:(x0 + span) * d],
            copy=True)
        fragments.append(Fragment(index, y0, x0, span, crop))
    return tuple(fragments)


def render_fragments(fragments: Sequence[Fragment], page: PageFixture,
                     out_dir: Path, *, px_per_dot: int, margin_cells: int,
                     cell_error_rate: float, print_noise_sigma: float,
                     rng: np.random.Generator) -> tuple[Render, ...]:
    """Render every fragment through the real print/scan pipeline.

    Reuses ``_fixtures.render`` unmodified — the same warp, cell-error
    injection and disk cache every verdict decode already runs through.
    Each fragment gets its own paper-white margin (``margin_cells``), the
    honest picture of a scrap's own uncut border.
    """
    margin_px = margin_cells * page.cell_dots * px_per_dot
    renders = []
    for frag in fragments:
        noise_seed = int(rng.integers(0, 2**31 - 1))
        renders.append(render(
            frag.dots, out_dir / f"frag{frag.index:02d}.png",
            px_per_dot=px_per_dot, cell_dots=page.cell_dots,
            margin_px=margin_px, noise_sigma=print_noise_sigma,
            cell_error_rate=cell_error_rate, noise_seed=noise_seed))
    return tuple(renders)


# --------------------------------------------------------- word-dead knobs
#
# H4-W4-PLAN ruling 3 (2026-08-18): cold's real customers are WORD-DEAD
# material — windows whose ADDRESS WORDS are defeated while the cell
# structure stays correlatable — and the recorded 4/12 baseline never
# produced that shape. ``_fixtures.render``'s own damage knobs
# (``damage_ring_tiles``, ``cell_error_band``) run PRE-render, on the dot
# field, and hit a whole tile (or a whole column band) at once: word AND
# payload cells alike. The mechanism that matters here — read off that
# file, not copied from it — is narrower: a tile's BCH(127,50,t=13) word
# lives at exactly 100 deterministic SITE cells per tile
# (``holo.format.pilots.word_site_cells_yx``, periodic — every tile carries
# the same 100-site pattern), and flipping enough of THOSE alone (more
# than t=13 of the 100) kills the word while every other cell in the tile
# — payload, LDPC, survey support — stays exactly as printed. That is the
# SLOT-targeted variant: strictly narrower than a ring or a band, and
# applied POST-render (pixel damage on the fragment PNG ``render_fragments``
# already wrote) rather than pre-render on the dot field, since the ask is
# an instrument gap in THIS driver, not a new ``_fixtures.render`` knob.


def word_damage_sites(frag: Fragment, page: PageFixture) -> np.ndarray:
    """Every address-word SITE cell, in fragment-local cell coordinates.

    A tile's 100 sites are periodic (same pattern in every tile of the
    row's family), so every tile whose 64-cell block overlaps the
    fragment contributes its own copy, offset by that tile's own origin.
    A site is kept iff the site cell ITSELF lands inside the fragment's
    crop — a tile the scissors only partly caught still hands over
    whichever of its 100 sites survived the cut, exactly as a real
    fragment edge would.
    """
    site_offsets = h_pilots.word_site_cells_yx(page.spec.family_seed)  # (100, 2)
    y0, x0, span = frag.y0_cells, frag.x0_cells, frag.span_cells
    ty0, ty1 = y0 // TILE_CELLS, (y0 + span - 1) // TILE_CELLS
    tx0, tx1 = x0 // TILE_CELLS, (x0 + span - 1) // TILE_CELLS
    sites = []
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            tile_sites = site_offsets + np.array([ty * TILE_CELLS,
                                                   tx * TILE_CELLS])
            inside = ((tile_sites[:, 0] >= y0) & (tile_sites[:, 0] < y0 + span)
                     & (tile_sites[:, 1] >= x0) & (tile_sites[:, 1] < x0 + span))
            sites.append(tile_sites[inside])
    all_sites = (np.concatenate(sites, axis=0) if sites
                else np.zeros((0, 2), dtype=np.int64))
    return all_sites - np.array([y0, x0])  # page cells -> fragment-local


def damage_word_slots(render_obj: Render, frag: Fragment, page: PageFixture,
                      *, rate: float, rng: np.random.Generator) -> int:
    """Invert a ``rate`` fraction of the fragment's word-site cells, in place.

    Pixel-level, on the already-rendered PNG (``render_obj.path``), not
    dot-level: each selected site cell's printed block is inverted
    (``255 - value``), the hard post-print flip a threshold-based word
    decode reads as the opposite bit — the same observable effect a hard
    cell error has upstream of it, landed downstream instead because the
    ask is a fragment-image knob, not a dot-field one. No rotation or
    anisotropic scale is ever in play for this driver's renders (every
    call uses ``render``'s identity pose), so a site cell's four corners
    map to an axis-aligned pixel rectangle via ``render_obj``'s own
    affine — the same truth the receiver itself would use, not a
    reimplementation of it.

    Returns the number of site cells actually hit, for the report.
    """
    if rate <= 0.0:
        return 0
    local_sites = word_damage_sites(frag, page)
    if local_sites.size == 0:
        return 0
    hit = rng.random(len(local_sites)) < rate
    local_sites = local_sites[hit]
    if len(local_sites) == 0:
        return 0
    arr = np.asarray(Image.open(render_obj.path), dtype=np.uint8).copy()
    for cy, cx in local_sites:
        y0f, x0f = render_obj.predicted_native(float(cy), float(cx))
        y1f, x1f = render_obj.predicted_native(float(cy + 1), float(cx + 1))
        y0, y1 = sorted((int(round(y0f)), int(round(y1f))))
        x0, x1 = sorted((int(round(x0f)), int(round(x1f))))
        y0, x0 = max(y0, 0), max(x0, 0)
        y1, x1 = min(y1, arr.shape[0]), min(x1, arr.shape[1])
        if y1 > y0 and x1 > x0:
            arr[y0:y1, x0:x1] = 255 - arr[y0:y1, x0:x1]
    Image.fromarray(arr).save(render_obj.path)
    return len(local_sites)


# ----------------------------------------------------------- the platen

def pack_platen_row(fragment_paths: Sequence[Path], *, backing_level: float,
                    gap_px: int, border_px: int, out_path: Path) -> None:
    """Paste rendered scraps left-to-right onto one backing sheet.

    Deliberately the simplest layout that still produces several disjoint
    payload-textured regions on one shared capture — a single row, not
    2-D bin packing or rotation — good enough for a by-hand tool and easy
    to read by eye against the saved PNG.
    """
    arrays = [np.asarray(Image.open(path), dtype=np.uint8)
             for path in fragment_paths]
    inner_h = max(a.shape[0] for a in arrays)
    height = inner_h + 2 * border_px
    width = (sum(a.shape[1] for a in arrays) + gap_px * (len(arrays) - 1)
            + 2 * border_px)
    canvas = np.full((height, width), np.uint8(np.clip(backing_level, 0, 255)))
    x = border_px
    for a in arrays:
        h, w = a.shape
        y = border_px + (inner_h - h) // 2
        canvas[y:y + h, x:x + w] = a
        x += w + gap_px
    Image.fromarray(canvas).save(out_path)


def build_platens(fragments: Sequence[Fragment], renders: Sequence[Render],
                  out_dir: Path, *, platen_count: int, backing_level: float,
                  gap_px: int, border_px: int,
                  ) -> list[tuple[Path, float, list[int]]]:
    """Distribute fragments round-robin over ``platen_count`` captures.

    Returns, per platen actually used, its path, its declared DPI (the
    same for every platen — one ``--px-per-dot`` for the whole run) and
    the fragment indices it carries, so the report can say which scrap
    landed where.
    """
    groups: list[list[int]] = [[] for _ in range(platen_count)]
    for i in range(len(fragments)):
        groups[i % platen_count].append(i)
    dpi = renders[0].dpi
    platens = []
    for p, indices in enumerate(groups):
        if not indices:
            continue
        path = out_dir / f"platen{p:02d}.png"
        pack_platen_row([renders[i].path for i in indices],
                        backing_level=backing_level, gap_px=gap_px,
                        border_px=border_px, out_path=path)
        platens.append((path, dpi, indices))
    return platens


# ------------------------------------------------------------ the decode

def run_decode(row: Any, scans: Scans, *, state_dir: Path, output: Path,
               workers: int) -> tuple[Any, Any, float]:
    """Drive the real composition root, exactly as the verdicts do."""
    request = cli.DecodeRequest(
        scans=scans, workers=workers, diag_port=0, state_dir=state_dir,
        output=output, complete=False)
    started = time.perf_counter()
    outcome, observer = cli.decode(
        request, row, real_providers(row, request.scans),
        fsync=False, snapshot_every=16)
    return outcome, observer, time.perf_counter() - started


def reopen(row: Any, scans: Scans, state_dir: Path, output: Path) -> Any:
    """Re-open the finished state to read what it holds. Commits nothing."""
    request = cli.DecodeRequest(
        scans=scans, workers=1, diag_port=0, state_dir=state_dir,
        output=output, complete=False)
    return cli.open_receiver(
        request, row, recipe=RECIPE_V1,
        providers=real_providers(row, request.scans),
        source=real_source(row), fsync=False)


# ------------------------------------------------------------- the census

def window_census(session: Any) -> tuple[Counter, dict[Any, Counter], int, int]:
    """Placement outcomes: overall, and grouped by each window's region.

    A region is, ideally, one scrap (the survey emits one per connected
    payload-textured blob it finds on a platen) — so the by-region split
    is the "per-fragment" half of the report. Grouping is on the window
    record's own ``region_id`` field, never re-derived from geometry.

    ``WindowRecord`` is written on the two OUTCOMES only (placed or
    retired) — a window whose every pass so far refused writes nothing
    durable at all, so it is invisible to the loop above. The fourth
    return value closes that gap: the total window PLAN population, read
    off the plane the same way the pull scheduler itself does
    (``footing_ids`` / ``window_plans``), so "never resolved within this
    run's budget" is a number the report states rather than a silence.
    """
    overall: Counter = Counter()
    by_region: dict[Any, Counter] = defaultdict(Counter)
    region_records = 0
    for key, record in session.store.records().items():
        if key.kind == "region":
            region_records += 1
            continue
        if key.kind != "window":
            continue
        label = ("placed" if record.status is WindowStatus.ACTIVE
                 else (record.retired_reason or "retired"))
        overall[label] += 1
        by_region[record.region_id][label] += 1
    planned = sum(len(session.plane.window_plans(footing_id))
                 for footing_id in session.plane.footing_ids("all"))
    return overall, by_region, region_records, planned


def format_counter(counter: Counter) -> str:
    return ", ".join(f"{label}={count}" for label, count in
                     sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


def close_lines(outcome: Any) -> list[str]:
    lines = [f"status: {outcome.status}"
            + (f" (reason={outcome.reason})" if outcome.reason else "")]
    lines.append(f"certified tiles: {outcome.certified}")
    lines.append(f"commits: {outcome.commits}  fires: {outcome.fires}  "
                f"exhausted: {outcome.exhausted}")
    if outcome.close:
        c = outcome.close
        wanted = ("status", "reason", "k_total", "symbols_used",
                 "metadata_rank", "metadata_counters", "certified")
        lines.append("close: " + ", ".join(
            f"{k}={c[k]}" for k in wanted if k in c))
    return lines


# ---------------------------------------------------------------- report

def describe_damage_regime(*, word_damage_rate: float, sites_damaged: int,
                           span_cells: int) -> str:
    """One line naming the damage regime, so a baseline is self-describing.

    H4-W4-PLAN ruling 3, exit criterion 2: a run's ran-out-of-ladder count
    means nothing without stating, in the same report, whether it came
    from slot-targeted word damage, a sub-word fragment span, both, or
    neither (the old 4/12 baseline's real bug — it stopped naming what
    made it 4/12 as the driver grew lanes around it).
    """
    if word_damage_rate > 0.0:
        word_bit = (f"word_damage_rate={word_damage_rate:.2f} "
                   f"({sites_damaged} site cell(s) inverted, slot-targeted "
                   "post-render)")
    else:
        word_bit = "word_damage_rate=0.00 (off)"
    if span_cells < E022_MIN_WINDOW_CELLS:
        span_bit = (f"fragment_span_cells={span_cells} (SUB-WORD: below "
                   f"the {E022_MIN_WINDOW_CELLS}-cell word-viability floor "
                   "E022_MIN_WINDOW_CELLS -- no window laid on this "
                   "fragment can ever complete a word decode)")
    else:
        span_bit = (f"fragment_span_cells={span_cells} (>= the "
                   f"{E022_MIN_WINDOW_CELLS}-cell word-viability floor "
                   "E022_MIN_WINDOW_CELLS)")
    return f"damage regime: {word_bit} | {span_bit}"


def print_report(*, page: PageFixture, fragments: Sequence[Fragment],
                 platens: Sequence[tuple[Path, float, list[int]]],
                 outcome: Any, overall: Counter,
                 by_region: dict[Any, Counter], region_records: int,
                 planned_windows: int, timings: dict[str, float],
                 damage_regime: str) -> None:
    print("=" * 72)
    print(f"scrap_decode: {page.format_ref} {page.tiles_yx[0]}x"
         f"{page.tiles_yx[1]} tiles ({page.tiles_per_page} total), "
         f"k_total={page.k_total}")
    print(f"  {len(fragments)} fragment(s) cut, {len(platens)} platen "
         f"capture(s)")
    print(f"  {damage_regime}")
    for frag in fragments:
        print(f"  frag{frag.index:02d}: {frag.span_cells}x{frag.span_cells} "
             f"cells @ (y={frag.y0_cells}, x={frag.x0_cells})")
    for path, dpi, indices in platens:
        print(f"  {path.name}: dpi={dpi:.0f}, fragments="
             f"{['frag%02d' % i for i in indices]}")

    print("-" * 72)
    resolved = overall.total()  # Python >=3.11: Counter.total() always exists
    print(f"window placement outcomes ({resolved} of {planned_windows} planned "
         "windows resolved; a window with no outcome yet never placed and "
         "never retired — it just ran out of run budget mid-ladder):")
    print(f"  {format_counter(overall) or '(no window ever fired)'}")
    print(f"regions detected: {region_records} "
         f"(fragments generated: {len(fragments)})")
    for label, region_id in sorted(
            ((str(region_id), region_id) for region_id in by_region),
            key=lambda pair: pair[0]):
        counts = by_region[region_id]
        print(f"  region {label}: {format_counter(counts)}")

    print("-" * 72)
    for line in close_lines(outcome):
        print(line)

    print("-" * 72)
    print("wall time:")
    for stage, seconds in timings.items():
        print(f"  {stage}: {seconds:.2f}s")
    print("=" * 72)


# ------------------------------------------------------------------ CLI

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="scrap_decode.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, required=True,
                    help="deterministic seed for fragment geometry and "
                         "print/scan noise (the printed CONTENT never "
                         "depends on it — only where the scissors fall)")
    ap.add_argument("--output-dir", type=Path, required=True,
                    help="directory for the rendered fragments/platens and "
                         "the decode's durable state; refused if it "
                         "already contains anything, so a run's evidence "
                         "is never silently mixed with an earlier one")
    # ONE FLAG, THE WHOLE IDENTITY (C4, RULINGS G5, 2026-08-22; it was
    # ``--coding`` + ``--tiles-y`` + ``--tiles-x``).  The tile matrix IS
    # the geometry half of a v2 format id (FORMAT-SPACE §7), so three
    # arguments that had to agree with each other became one string that
    # cannot disagree with itself — and the same flag reaches a printed
    # sheet through its ``L:`` line, which the trio never could.
    ap.add_argument("--format", default=SPINE_FORMAT, dest="format_ref",
                    metavar="ID",
                    help=f"format reference — a v2 identity or an L: "
                         f"fossil line (default {SPINE_FORMAT}, the H4 "
                         f"architecture-spine fixture's own)")
    ap.add_argument("--fragment-count", type=int, default=4,
                    help="how many scrap fragments to cut (default 4)")
    ap.add_argument("--fragment-span-cells", type=int, default=160,
                    help="each fragment's (square) side length, in cells, "
                         "before its paper margin (default 160 = 2.5 "
                         "tiles; clamped to the printed field's own size). "
                         f"Below {E022_MIN_WINDOW_CELLS} cells "
                         "(E022_MIN_WINDOW_CELLS, the word-decode "
                         "viability floor) no window laid on the fragment "
                         "can ever reach a full word slot — the sub-word "
                         "regime H4-W4-PLAN ruling 3 asks for")
    ap.add_argument("--word-damage-rate", type=float, default=0.0,
                    help="fraction of each in-fragment tile's 100 "
                         "address-word site cells to invert post-render, "
                         "slot-targeted so payload/LDPC cells are never "
                         "touched (default 0.0, off; BCH(127,50,t=13) "
                         "corrects up to 13 of the 100 sites, so a rate "
                         "above ~0.13 defeats a hit tile's word decode "
                         "outright — the H4-W4-PLAN ruling 3 knob)")
    ap.add_argument("--fragment-margin-cells", type=int, default=8,
                    help="paper-white margin cells rendered around each "
                         "fragment's printed field — the scrap's own "
                         "uncut border (default 8)")
    ap.add_argument("--fragment-gap-px", type=int, default=80,
                    help="native-pixel gap between neighbouring scraps on "
                         "one platen row (default 80)")
    ap.add_argument("--platen-count", type=int, default=1,
                    help="how many separate platen captures to spread the "
                         "fragments across, round-robin (default 1)")
    ap.add_argument("--platen-border-px", type=int, default=60,
                    help="native-pixel backing border around each platen "
                         "row (default 60)")
    ap.add_argument("--platen-backing-level", type=float, default=40.0,
                    help="platen backing grey level outside the scraps, "
                         "0-255 (default 40.0, a dark backing sheet — the "
                         "e018/e019 confetti-scan convention)")
    ap.add_argument("--px-per-dot", type=int, default=2,
                    help="capture pixels per printed dot (default 2, a "
                         "1200 dpi capture of a 600 dpi print — the "
                         "verdicts' own convention)")
    ap.add_argument("--cell-error-rate", type=float, default=0.0,
                    help="hard cell-flip rate injected before rendering, "
                         "0-1 (default 0.0, a clean channel; the measured "
                         "c2 envelope is 2-5%%)")
    ap.add_argument("--print-noise-sigma", type=float, default=1.0,
                    help="gaussian sensor-noise sigma added after warping "
                         "(default 1.0, the verdicts' CLEAN_DITHER)")
    ap.add_argument("--workers", type=int, default=1,
                    help="decode worker count (default 1, serial — the "
                         "reference lane; see the verdicts' own ruling on "
                         "why serial is the default everywhere in this "
                         "tree)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    out_dir: Path = args.output_dir
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"scrap_decode: {out_dir} already exists and is not empty — "
             "pick a fresh directory so this run's evidence is never "
             "mixed with an earlier one.", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    page = build_page(args.format_ref)
    fragments = cut_fragments(
        page, count=args.fragment_count, span_cells=args.fragment_span_cells,
        rng=rng)
    renders = render_fragments(
        fragments, page, out_dir, px_per_dot=args.px_per_dot,
        margin_cells=args.fragment_margin_cells,
        cell_error_rate=args.cell_error_rate,
        print_noise_sigma=args.print_noise_sigma, rng=rng)
    timings["build + render fragments"] = time.perf_counter() - t0

    # SAME rng, continuing the fixed draw order the module docstring
    # promises: cut offsets, then render noise seeds, then (only when the
    # knob is armed) which word sites get hit. At the default rate 0.0 no
    # draw happens at all, so an unarmed run's RNG stream is byte-for-byte
    # what it always was.
    t0 = time.perf_counter()
    sites_damaged = 0
    if args.word_damage_rate > 0.0:
        for frag, render_obj in zip(fragments, renders):
            sites_damaged += damage_word_slots(
                render_obj, frag, page, rate=args.word_damage_rate, rng=rng)
    timings["damage word slots"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    platens = build_platens(
        fragments, renders, out_dir, platen_count=args.platen_count,
        backing_level=args.platen_backing_level, gap_px=args.fragment_gap_px,
        border_px=args.platen_border_px)
    timings["pack platen(s)"] = time.perf_counter() - t0

    scans: Scans = tuple((path, dpi) for path, dpi, _indices in platens)
    state_dir = out_dir / "state"
    output_path = out_dir / "recovered.bin"
    outcome, _observer, decode_seconds = run_decode(
        page.row, scans, state_dir=state_dir, output=output_path,
        workers=args.workers)
    timings["decode"] = decode_seconds

    t0 = time.perf_counter()
    with reopen(page.row, scans, state_dir, output_path) as session:
        overall, by_region, region_records, planned_windows = window_census(
            session)
    timings["re-open + census"] = time.perf_counter() - t0
    timings["total"] = sum(
        v for k, v in timings.items() if k != "total")

    if outcome.verified and outcome.payload is not None:
        try:
            publish_once(output_path, outcome.payload)
        except FileExistsError:
            pass

    span_cells_used = (fragments[0].span_cells if fragments
                      else args.fragment_span_cells)
    damage_regime = describe_damage_regime(
        word_damage_rate=args.word_damage_rate, sites_damaged=sites_damaged,
        span_cells=span_cells_used)

    print_report(page=page, fragments=fragments, platens=platens,
                outcome=outcome, overall=overall, by_region=by_region,
                region_records=region_records, planned_windows=planned_windows,
                timings=timings, damage_regime=damage_regime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
