#!/usr/bin/env python
"""Solve a printed page's per-plane registration field from an archived run.

    cd <repo>
    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate self-check
    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate run \\
        RUN_DIR --out OUT_DIR
    PYTHONPATH=src:. env/bin/python -m measure.page_field.estimate archive \\
        EXTRACT_DIR --out OUT_DIR --format REF \\
        --scan A.tiff --dpi 2400 --scan B.tiff --dpi 2400

The receiver's own collector and solver, driven over archived facts
instead of by the scheduler: `fields_collect.prepare_collect` measures
one capture's view of one page and `fields.prepare_fields` solves the
page, both off a real `holo.receiver.store` populated from the run's
placements and certificates.  There is no estimator here and there is no
second pooling; what this module owns is the ORDER (every capture
collected, then one solve per page) and the raster lifetime (one capture
in memory at a time).  What it REPORTS — the records that become
`fields.json`, the tables and the figures — is `products.py`, beside it.

Two fact routes, one store.  `run` reads a post-W3 snapshot through
`holo.receiver.snapshot.read` and takes the captures from the run dir's
own `argv`; `archive` reads the pre-W2 npz files
`measure/page_field/extract.py` wrote — W2 re-keyed `PlaneField`, so
`snapshot.read` raises on those — and takes the captures from the
command line, because an extract carries no argv.  Both fold exactly
`Placement` and `Certificate`, which with the declared captures is
everything a collection reads.

WHAT THIS COSTS.  Sheet H's 4800-dpi captures are 6.9 GB tiffs and the
receiver's intake writes one npy per plane per decimation level, so
every capture is ingested, collected and DELETED before the next one is
opened.  The solve then runs off the observation tables alone, which are
kilobytes.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from holo.receiver import cli, data, snapshot, store as store_module
from holo.receiver.format import identity
from holo.receiver.lib import plane_field
from holo.receiver.lib.geometry import compose_from_native
from holo.receiver.plugins import fields, fields_collect, intake

from . import extract as extract_module
from .products import (Counts, Declaration, PageField, column_profile,
                       fields_json, full_resolution_rows, write_products)

#: The route an archived placement is folded under.  `extract.py` does
#: not keep `Placement.route` and nothing a collection reads depends on
#: it: the fold uses it for a wake key, and the ordinal only asks
#: whether it is `refine`.  Naming it here rather than borrowing a
#: production spelling keeps an archived pose from claiming a route it
#: was not placed by.
ARCHIVED_ROUTE: str = "archive"


# ------------------------------------------------------- the two routes

@dataclass(frozen=True)
class Archive:
    """The facts' source, and the identity that source attests.

    `identity` is `extract.run_identity`'s record — the ROW ID the run
    opened with — or `None` where nothing in the archive attests one.
    """

    route: str
    where: Path
    identity: dict | None

    def source(self) -> dict:
        return {"route": self.route, "source": str(self.where),
                "archived_identity": self.identity}


def declaration_from_argv(run_dir: Path) -> Declaration:
    """The scans, DPIs and format a run dir's `argv` line declares.

    Parsed by the receiver's OWN parser, so a `--coding`/`--printer`
    pair, a fossil `L:` reference and a v2 identity all resolve the way
    the run resolved them.  That parser is THIS tree's: an archived argv
    naming a flag the tree has retired (`--plane-fields`, W2) or renamed
    (`--pages` -> `--max-pages`) is refused, which is why the `archive`
    route spells its captures on the command line.  The engine writes
    the vector unquoted, so a scan path with a space in it is not
    recoverable — none is.
    """
    tokens = shlex.split((run_dir / "argv").read_text())
    args = cli._build_parser().parse_args(tokens[1:])
    if len(args.dpi) != len(args.scans):
        raise ValueError(f"{run_dir}/argv: {len(args.scans)} scans and "
                         f"{len(args.dpi)} --dpi values")
    return Declaration(scans=tuple(args.scans),
                       dpis=tuple(float(value) for value in args.dpi),
                       format_ref=cli._format_ref(args),
                       max_pages=args.max_pages)


def snapshot_facts(facts_path: Path) -> tuple[object, ...]:
    return tuple(snapshot.read(facts_path))


def run_dir_archive(run_dir: Path) -> Archive:
    """A run dir, and the identity that run recorded for itself.

    Not from the snapshot: `snapshot.FAMILIES` does not hold `RunOpen`,
    so `snapshot.read` never returns one and a fact file cannot say what
    it was decoded under (measured 2026-09-08 on all five archives this
    harness reads).  Every run does write it, as line 1 of its own
    `events.jsonl`, which `operator._diag_products` dumps at RunDone.
    """
    events = extract_module.sibling_events(run_dir / snapshot.NAME)
    if events is None:
        return Archive("snapshot", run_dir, None)
    opened, _captures = extract_module.events_head(events)
    return Archive("snapshot", run_dir,
                   {"format_id": str(opened["format_id"]),
                    "attested_by": str(events)})


def extract_archive(extract_dir: Path) -> Archive:
    """An `extract.py` directory, and the identity it recorded.

    A `captures.json` written before the gate carries no `identity` key
    at all; that is not an archive attesting nothing, it is an archive
    that was never asked, and it is refused with the same force.
    """
    captures = json.loads((extract_dir / "captures.json").read_text())
    if "identity" not in captures:
        raise ValueError(
            f"{extract_dir}/captures.json predates the identity gate: "
            f"re-extract it (measure.page_field.extract extract …)")
    return Archive("extract", extract_dir, captures["identity"])


def archived_seed(format_id: str) -> bytes:
    """The AES seed a run that opened under this ROW ID was reading.

    The canonical v2 format id IS the seed payload (FORMAT-SPACE §16),
    so the seed follows from the row id `RunOpen` recorded, and NOT from
    resolving that string again here: `c2-cmy8-r0547@53x37` was a
    canonical row id when sheet J was printed and decoded, and the
    2026-09-02 re-key made it a DISPLAY name for a different row, so
    resolving it today returns a seed the sheet was never encoded under.
    Fossil ids carry frozen seed bytes and are matched, never parsed.
    """
    if format_id.startswith(identity.L_PREFIX):
        return identity.resolve_format_ref(format_id).seed
    return identity.SEED_NAMESPACE + format_id.encode()


def check_identity(archive: Archive, format_ref: str) -> None:
    """Refuse a declared format the archive was not decoded under.

    The tile codec's keystream and its slot permutation are functions of
    the seed, so a run replayed under the wrong one correlates every
    certified template against the wrong known bits and measures its own
    null.  Nothing downstream can see that: the furniture tiers are
    seeded separately (`sites_seed`) and go on working, so the products
    look ordinary.  Hence a gate, before any raster is opened.
    """
    if archive.identity is None:
        raise ValueError(
            f"{archive.where} attests no RunOpen identity, so there is "
            f"nothing to check {format_ref!r} against; a declared "
            f"reference is not evidence of what was decoded.  Re-extract "
            f"with --events pointing at the run's own events.jsonl")
    archived = str(archive.identity["format_id"])
    seed = archived_seed(archived)
    declared = identity.resolve_format_ref(format_ref)
    if seed != declared.seed:
        raise ValueError(
            f"{archive.where} was decoded as {archived!r}, seed "
            f"{seed.decode()!r} (attested by "
            f"{archive.identity['attested_by']}); --format {format_ref!r} "
            f"resolves to {declared.row_id!r}, seed "
            f"{declared.seed.decode()!r}")


def extracted_facts(extract_dir: Path) -> tuple[object, ...]:
    """`extract.py`'s placements and certificates, as the fact classes.

    The CSR ragged fields are sliced back into per-fact arrays; the
    window id is rebuilt from the four columns `extract.py` checked it
    against.
    """
    facts: list[object] = []
    with np.load(extract_dir / "placements.npz") as held:
        offsets = held["cell_offsets"]
        cells = held["local_cells_yx"]
        for index in range(held["page"].shape[0]):
            extent = tuple(int(v) for v in held["extent_cells"][index])
            capture_id = str(held["capture_id"][index])
            level_index = int(held["level_index"][index])
            region_index = int(held["region_index"][index])
            facts.append(data.Placement(
                window_id=(capture_id, level_index, region_index, extent),
                capture_id=capture_id, level_index=level_index,
                region_index=region_index,
                patch_ordinal=int(held["patch_ordinal"][index]),
                page=int(held["page"][index]),
                rot_k=int(held["rot_k"][index]),
                page_origin_yx=tuple(
                    int(v) for v in held["page_origin_yx"][index]),
                native_affine=tuple(
                    float(v) for v in held["native_affine"][index]),
                pitch_px=float(held["pitch_px"][index]),
                route=ARCHIVED_ROUTE,
                local_cells_yx=np.asarray(
                    cells[offsets[index]:offsets[index + 1]], np.int64)))
    with np.load(extract_dir / "certificates.npz") as held:
        offsets = held["bit_offsets"]
        bits = held["user_bits"]
        for index in range(held["page"].shape[0]):
            facts.append(data.Certificate(
                page=int(held["page"][index]),
                ty=int(held["ty"][index]), tx=int(held["tx"][index]),
                stream_id=str(held["stream_id"][index]),
                user_bits=np.asarray(bits[offsets[index]:
                                          offsets[index + 1]], np.uint8),
                source=ARCHIVED_ROUTE))
    return tuple(facts)


# ------------------------------------------------------------ the store

def open_store(declaration: Declaration,
               work_dir: Path) -> store_module._Store:
    request = data.DecodeRequest(
        scans=declaration.scans, dpis=declaration.dpis,
        format_ref=declaration.format_ref,
        max_pages=declaration.max_pages, workers=1, complete=False,
        no_close=False, diag_port=None, run_dir=work_dir)
    return store_module._Store(request, [])


def fold_evidence(store: store_module._Store,
                  facts: tuple[object, ...]) -> dict[str, int]:
    """Fold the placements and the certificates, and report the rest.

    Those two families plus the declared captures are the whole input of
    a collection: `prepare_collect` reads the lane's placed windows, the
    page's certificates and the capture's levels, and nothing else.  The
    archived `PlaneField` facts are deliberately NOT folded — this run
    re-derives them, and a standing field would silence the trigger this
    harness reports.
    """
    counts: dict[str, int] = {}
    for fact in facts:
        name = type(fact).__name__
        counts[name] = counts.get(name, 0) + 1
        if isinstance(fact, (data.Placement, data.Certificate)):
            store._fold(fact)
    return counts


def _install_rasters(store: store_module._Store,
                     rasters: tuple[data.PlaneRaster, ...]) -> None:
    store._rasters = store._rasters + rasters
    for raster in rasters:
        lane = (raster.capture_id, raster.level_index)
        store._planes_by_lane.setdefault(lane, {})[raster.plane] = raster


def _drop_rasters(store: store_module._Store, capture: data.Capture) -> None:
    store._rasters = tuple(raster for raster in store._rasters
                           if raster.capture_id != capture.capture_id)
    for lane in [key for key in store._planes_by_lane
                 if key[0] == capture.capture_id]:
        del store._planes_by_lane[lane]
    shutil.rmtree(capture.plane_dir, ignore_errors=True)


def pages_of(store: store_module._Store) -> tuple[int, ...]:
    return tuple(sorted({int(store.placement(wid).page)
                         for wid in store.placements()}))


def _check_captures(store: store_module._Store,
                    declared: set[str]) -> None:
    placed = {wid[0] for wid in store.placements()}
    missing = sorted(placed - declared)
    if missing:
        raise ValueError(
            "the declared scans do not carry every capture the facts "
            f"name: {len(missing)} missing, first {missing[0][:12]}")


def capture_ids(declaration: Declaration) -> tuple[str, ...]:
    """The capture identity of every declared scan, in order.

    Production's own identity (`intake.sha256_file`), read before a
    raster is opened: it costs one pass over each tiff — sheet H's seven
    are 24.5 GB and 45 s of it — and it buys the two answers a
    per-capture ingest loop cannot get from `ingest_captures`, which
    sees one path at a time.  A scan set that does not carry the facts'
    captures is refused for the price of a hash rather than of the whole
    ingest, and a scan declared twice is recognised as one capture.
    """
    return tuple(intake.sha256_file(path) for path in declaration.scans)


# ----------------------------------------------------- collect and solve

def collect_captures(store: store_module._Store,
                     declaration: Declaration,
                     work_dir: Path) -> tuple[int, int, float]:
    """One capture at a time: ingest, collect every page, drop.

    The collection is `fields.collect`'s own job, prepared off the store
    exactly as the scheduler prepares it.  A capture whose scan the
    facts never placed on a page simply has no subject and no job.

    THE TWO GUARDS `ingest_captures` CANNOT KEEP HERE.  It dedupes and
    refuses over the paths of ONE call; this loop calls it once per
    scan, so both guards are kept against the declared shas instead: a
    scan declared twice is ingested and collected once (production
    records a duplicate `CaptureOpen` and reuses the standing capture;
    counting it twice would inflate exactly the collection count B6
    asks for), and one source declared at two DPIs is refused rather
    than silently installing a second level ladder under the first
    one's lane keys.
    """
    row = store.row
    pages = pages_of(store)
    collections = 0
    cpu_s = 0.0
    declared = capture_ids(declaration)
    _check_captures(store, set(declared))
    standing: dict[str, float] = {}
    for capture_id, scan, dpi in zip(declared, declaration.scans,
                                     declaration.dpis):
        if capture_id in standing:
            if float(dpi) != standing[capture_id]:
                raise ValueError(
                    f"{scan} sha {capture_id[:12]} is declared at "
                    f"{standing[capture_id]} and at {float(dpi)} dpi — "
                    "intake's Q2 refusal, which a per-capture ingest "
                    "loop has to keep for itself")
            continue
        standing[capture_id] = float(dpi)
        captures, rasters, _events = intake.ingest_captures(
            (scan,), (dpi,), row.pitch_in, row.family, work_dir)
        capture, = captures
        store._fold(capture)
        _install_rasters(store, rasters)
        for page in pages:
            if not fields_collect.placed_on(store, capture.capture_id, page):
                continue
            job = fields_collect.prepare_collect(
                store, (capture.capture_id, page),
                fields_collect.STAGE_COLLECT)
            if job is None:
                continue
            result = job()
            cpu_s += float(result.cpu_s)
            for fact in result.facts:
                store._fold(fact)
            collections += 1
        _drop_rasters(store, capture)
    return len(standing), collections, cpu_s


def solve_pages(store: store_module._Store,
                ) -> tuple[tuple[PageField, ...], float]:
    """One solve per page, over every capture's observations.

    Unconditional: the harness holds every capture's collection already
    and solves each page once, which is its own order and not what
    production would schedule (bar B6).  What production schedules ON is
    the page's evidence REVISION, and that number is reported beside the
    field rather than re-derived here.
    """
    solved: list[PageField] = []
    cpu_s = 0.0
    tiles_yx = store.row.tiles_yx
    for page in pages_of(store):
        job = fields.prepare_fields(store, page, fields.STAGE_SOLVE)
        if job is None:
            continue
        _observations, captures = fields.page_observations(store, page)
        result = job()
        cpu_s += float(result.cpu_s)
        for fact in result.facts:
            store._fold(fact)
        facts = tuple(store.page_plane_fields(page))
        if any(fact is None for fact in facts):
            raise ValueError(f"page {page} published no field for every "
                             "plane, which I6 forbids")
        event, = [one for one in result.events
                  if isinstance(one, data.FieldSolved)]
        solved.append(PageField(
            page=page, tiles_yx=tiles_yx, captures=captures, facts=facts,
            rows=full_resolution_rows(event, facts), solved=event))
    return tuple(solved), cpu_s


def lane_page_fits(store: store_module._Store) -> int:
    """Fields keyed by anything but (page, plane).

    Zero by construction — the cell IS keyed (page, plane) — and counted
    rather than asserted because B6's claim is about what a replay
    schedules, and a number a reader can see is the claim.
    """
    return sum(1 for key in store._plane_fields
               if len(key) != 2 or not all(isinstance(v, int) for v in key))


def estimate(declaration: Declaration, archive: Archive,
             facts: tuple[object, ...], out: Path) -> dict:
    """The whole harness: gate, fold, collect capture by capture, solve,
    write."""
    check_identity(archive, declaration.format_ref)
    started = time.monotonic()
    work_dir = out / "planes"
    store = open_store(declaration, work_dir)
    folded = fold_evidence(store, facts)
    captures, collections, collect_cpu_s = collect_captures(
        store, declaration, work_dir)
    solved, solve_cpu_s = solve_pages(store)
    counts = Counts(captures=captures,
                    pages=len(pages_of(store)), collections=collections,
                    pages_solved=len(solved),
                    lane_page_fits=lane_page_fits(store),
                    collect_cpu_s=collect_cpu_s, solve_cpu_s=solve_cpu_s)
    payload = fields_json(declaration,
                          {**archive.source(), "folded_facts": folded},
                          solved, counts, store)
    payload["counts"]["wall_s"] = round(time.monotonic() - started, 2)
    written = write_products(out, payload, solved)
    shutil.rmtree(work_dir, ignore_errors=True)
    return {"out": str(out), "written": list(written),
            "counts": payload["counts"],
            "pages": [{"page": page.page,
                       "planes": {row.plane_name: round(
                           row.median_delta_dots, 4) for row in page.rows}}
                      for page in solved]}


# --------------------------------------------------------- the self-check

SELF_FORMAT_REF: str = "c3-cmy8-r0550x0550x0547@3x3"
SELF_PITCH_PX: float = 6.0
SELF_BLUR_PX: float = 1.5
#: The window spans the WHOLE page, so every tile of the 3x3 grid
#: carries evidence and the smoother is never asked to extrapolate: what
#: the check reads is the collection and the pooling, not the kernel's
#: reach, which `test_h3_plane_field_lib` owns.
SELF_SPAN_TILES: int = 3
SELF_PLANTED_DOTS_XY: tuple[float, float] = (1.0, 0.0)
SELF_PLANE: int = 2


class _HeldRaster:
    """A `PlaneRaster` the self-check holds in memory rather than on
    disk: the collector only ever calls `open`."""

    def __init__(self, image: np.ndarray) -> None:
        self._image = image

    def open(self) -> np.ndarray:
        return self._image


def _paint(row: object, geometry: object, window: object,
           page_linear: np.ndarray,
           planted_dots_xy: tuple[float, float]) -> tuple[_HeldRaster, ...]:
    """The window's own printed truth, one plane displaced on the PAGE.

    THE STIMULUS, not the estimator: the cells the format itself fixes
    are painted at the window pose's own sample points, ink dark, and
    the planted plane's ink is moved by a page-axis vector carried into
    pixels through the page map — the geometry the printer acts in.  One
    dot of blur, because a hard-edged raster has a flat optimum a cell
    wide and a channel with no MTF is not a channel.
    """
    from scipy import ndimage

    from holo.receiver.plugins import color_region

    rows = color_region.build_window_rows(row, geometry, window, {}, {})
    known = np.asarray(rows.known_component_mask, bool)
    bits = np.asarray(rows.known_component_bits, np.uint8).copy()
    cells = np.asarray(rows.page_cells_yx, np.int64)
    pattern = ((cells[:, 0] * 131 + cells[:, 1] * 17) % 8).astype(np.uint8)
    for plane in range(fields.N_PLANES):
        blank = ~known[:, plane]
        bits[blank, plane] = (pattern[blank] >> plane) & 1
    points = np.asarray(window.scan_points_yx, np.float64)
    cell_dots = color_region.cell_dots_of(row)
    pixel_delta = page_linear @ (
        np.asarray(planted_dots_xy, np.float64)[::-1] / cell_dots)
    size = int(SELF_SPAN_TILES * 64 * SELF_PITCH_PX)
    half = SELF_PITCH_PX / 2.0
    painted = []
    for plane in range(fields.N_PLANES):
        image = np.ones((size, size), np.float32)
        moved = points + (pixel_delta if plane == SELF_PLANE else 0.0)
        for (py, px), value in zip(moved, bits[:, plane]):
            y0, x0 = int(round(py - half)), int(round(px - half))
            image[max(0, y0):y0 + int(SELF_PITCH_PX),
                  max(0, x0):x0 + int(SELF_PITCH_PX)] = 1.0 - float(value)
        painted.append(_HeldRaster(ndimage.gaussian_filter(image,
                                                           SELF_BLUR_PX)))
    return tuple(painted)


def self_check(work: Path) -> None:
    """The estimator over a synthetic store, with a planted delta.

    No tiff, no decode and no scheduler: one placement of a window
    spanning a whole 3x3-tile page, the Y plane printed one dot along page
    +x, collected and solved by the production rows this module drives.
    What it pins is the harness's OWN contract — the planted vector
    comes back on Y and on Y alone, the field is keyed (page, plane),
    and the two products are written.
    """
    from fractions import Fraction

    from holo.receiver.tests import _h3_facts, _h3_fixture_geometry

    # THE IDENTITY GATE, on the two references sheet J is actually
    # replayed under.  Its runs recorded the row id `c2-cmy8-r0547@53x37`
    # and the 2026-09-02 re-key gave that spelling to a different row, so
    # the fossil is the accepted reference and the name the operator
    # would reach for first is refused.
    printed = Archive("extract", Path("sheet-J"),
                      {"format_id": "c2-cmy8-r0547@53x37",
                       "attested_by": "self-check"})
    check_identity(printed, "L:c2-cmy8-r0547@53x37")
    extract_module.refuses(
        lambda: check_identity(printed, "c2-cmy8-r0547@53x37"),
        "the re-keyed display name was accepted for sheet J")
    extract_module.refuses(
        lambda: check_identity(Archive("extract", Path("nowhere"), None),
                               "L:c2-cmy8-r0547@53x37"),
        "an archive attesting no identity was replayed")
    fossil = "L:c2-cmy8-r0700-p120-x1@3392x2368"
    sheet_i = Archive("snapshot", Path("sheet-I"),
                      {"format_id": fossil, "attested_by": "self-check"})
    check_identity(sheet_i, fossil)
    extract_module.refuses(
        lambda: check_identity(sheet_i,
                               "L:c2-cmy8-r0850-p120-x1@3392x2368"),
        "sheet H's fossil was accepted for sheet I's archive")

    # THE TWO ROUTES `main` takes, which the gate above does not reach:
    # the identity comes from the run's own `RunOpen` and from the
    # extract's recorded key, never from anything the operator declared.
    # A run dir whose argv says one row and whose journal says another
    # must read the journal, or a route that took the identity from argv
    # would pass every check by construction.
    run_dir = work / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "argv").write_text(
        "holo3 decode a.tiff --dpi 2400 --out out "
        "--format c2-cmy8-r0547@53x37")
    assert declaration_from_argv(run_dir).format_ref == \
        "c2-cmy8-r0547@53x37", "the argv fixture stopped saying the other row"
    extract_module.write_journal(run_dir / "events.jsonl",
                            "L:c2-cmy8-r0547@53x37", ("cap",))
    assert run_dir_archive(run_dir).identity["format_id"] == \
        "L:c2-cmy8-r0547@53x37", "the run route did not read RunOpen"
    ungated = work / "ungated"
    ungated.mkdir(parents=True, exist_ok=True)
    (ungated / "captures.json").write_text(json.dumps({"captures": []}))
    extract_module.refuses(
        lambda: extract_archive(ungated),
        "a captures.json written before the gate was replayed")

    row = identity.resolve_format_ref(SELF_FORMAT_REF)
    geometry = _h3_fixture_geometry.memoised_site_geometry(row)
    capture_id = _h3_facts.CAPTURE_ID
    span = SELF_SPAN_TILES * 64
    wid = (capture_id, 0, 0, (0, 0, span, span))
    native_affine = _h3_fixture_geometry.page_native_affine(SELF_PITCH_PX,
                                                            0.0)
    placement = _h3_fixture_geometry.window_placement(
        wid, native_affine, _h3_facts.tile_cells(span), page=0, rot_k=0)
    window = _h3_fixture_geometry.window_pose(row, placement)
    page_linear = np.asarray(
        compose_from_native(native_affine, Fraction(1)),
        np.float64).reshape(2, 3)[:, :2]

    work.mkdir(parents=True, exist_ok=True)
    store = open_store(
        Declaration(scans=(Path("self-check.tiff"),), dpis=(1200.0,),
                    format_ref=SELF_FORMAT_REF, max_pages=1),
        work / "planes")
    store._fold(_h3_facts.capture())
    store._fold(placement)
    store._planes_by_lane[(capture_id, 0)] = dict(zip(
        ("r", "g", "b"),
        _paint(row, geometry, window, page_linear, SELF_PLANTED_DOTS_XY)))

    job = fields_collect.prepare_collect(store, (capture_id, 0),
                                         fields_collect.STAGE_COLLECT)
    assert job is not None, "a placed capture-page prepared no collection"
    for fact in job().facts:
        store._fold(fact)
    solved, _cpu_s = solve_pages(store)
    assert len(solved) == 1, solved
    page = solved[0]
    assert lane_page_fits(store) == 0
    assert set(store._plane_fields) == {(0, plane) for plane in range(3)}

    measured = {row.plane: row for row in page.rows}
    planted = np.asarray(SELF_PLANTED_DOTS_XY, np.float64)
    grid = np.asarray(page.facts[SELF_PLANE].delta_dots_xy, np.float64)
    support = np.asarray(page.facts[SELF_PLANE].support, np.float64) > 0.0
    error = np.linalg.norm(grid[support] - planted, axis=1)
    assert float(np.median(error)) < plane_field.FIELD_NOISE_DOTS, (
        f"the planted {planted.tolist()} came back "
        f"{np.median(grid[support], axis=0).tolist()}")
    # I5 on the MEASUREMENT.  The word planes are asked here and not on
    # the published grid because C's anchor tier reaches five of the
    # nine tiles on a page this small, and what the smoother then draws
    # across the other four is its own linear reach — the library
    # module's subject, measured there, not a coupling this page can
    # speak to.
    rows, _captures = fields.page_observations(store, 0)
    plane_column = np.asarray(rows.plane, np.int64)
    deltas = np.asarray(rows.delta_dots_xy, np.float64)
    word = {plane: np.median(deltas[plane_column == plane], axis=0)
            for plane in (0, 1)}
    for plane, median in word.items():
        assert float(np.abs(median).max()) < plane_field.FIELD_NOISE_DOTS, (
            f"plane {plane} measured {median.tolist()} while the delta "
            f"was planted on plane {SELF_PLANE}, which I5 forbids")
    assert measured[SELF_PLANE].known, (
        "the planted plane was measured and must not read unknown (I13)")
    for plane in range(fields.N_PLANES):
        counted = sum(int(count) for _capture, row_plane, _energy,
                      _expected, count in
                      page.solved.residual_by_capture_plane
                      if int(row_plane) == plane)
        assert counted == measured[plane].n_observations, (
            f"plane {plane} residual counted {counted} of "
            f"{measured[plane].n_observations} observations")

    payload = fields_json(
        Declaration(scans=(Path("self-check.tiff"),), dpis=(1200.0,),
                    format_ref=SELF_FORMAT_REF, max_pages=1),
        {"source": "self-check"}, solved,
        Counts(1, 1, 1, 1, 0, 0.0, 0.0), store)
    written = write_products(work / "out", payload, solved)
    assert set(written) == {"fields.json", "field-page0-C.png",
                            "field-page0-M.png", "field-page0-Y.png",
                            "cross-section-page0.png"}, written
    profile = column_profile(page.facts[SELF_PLANE].delta_dots_xy,
                             page.facts[SELF_PLANE].support)
    assert profile.shape == (row.tiles_yx[1],)
    print(f"page_field.estimate self-check OK — planted "
          f"{planted.tolist()} dots on plane {SELF_PLANE}, solved "
          f"{np.median(grid[support], axis=0).round(3).tolist()} over "
          f"{int(support.sum())} tiles at revision "
          f"{page.solved.revision}; C/M measured "
          f"{word[0].round(3).tolist()}/{word[1].round(3).tolist()} and "
          f"published {measured[0].median_delta_dots:.3f}/"
          f"{measured[1].median_delta_dots:.3f} over "
          f"{measured[0].support_tiles}/{measured[1].support_tiles} tiles, "
          f"median uncertainty "
          f"{measured[SELF_PLANE].median_uncertainty_dots:.3f} dots")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="a post-W3 run dir (facts.npz + argv)")
    run.add_argument("run_dir", type=Path)
    run.add_argument("--out", type=Path, required=True)
    archive = sub.add_parser("archive",
                             help="extract.py's npz files (pre-W2 facts)")
    archive.add_argument("extract_dir", type=Path)
    archive.add_argument("--out", type=Path, required=True)
    archive.add_argument("--scan", type=Path, action="append", required=True)
    archive.add_argument("--dpi", type=float, action="append", required=True)
    archive.add_argument("--format", dest="format_ref", required=True)
    archive.add_argument("--max-pages", dest="max_pages", type=int,
                         default=None)
    checker = sub.add_parser("self-check", help="pure, no corpus")
    checker.add_argument("--work", type=Path, default=None,
                         help="scratch directory (default: a fresh temp dir)")
    args = parser.parse_args()
    # The gate before the FACT LOAD, not just before the raster: sheet
    # H's snapshot is 1.87 GB and a wrong --format has no business
    # paying for it.  `estimate` keeps its own check as its precondition.
    if args.command == "run":
        declaration = declaration_from_argv(args.run_dir)
        archive = run_dir_archive(args.run_dir)
        check_identity(archive, declaration.format_ref)
        print(json.dumps(estimate(
            declaration, archive,
            snapshot_facts(args.run_dir / snapshot.NAME),
            args.out), indent=1))
    elif args.command == "archive":
        if len(args.scan) != len(args.dpi):
            raise SystemExit("exactly one --dpi per --scan")
        declaration = Declaration(
            scans=tuple(args.scan),
            dpis=tuple(float(value) for value in args.dpi),
            format_ref=args.format_ref, max_pages=args.max_pages)
        archive = extract_archive(args.extract_dir)
        check_identity(archive, declaration.format_ref)
        print(json.dumps(estimate(
            declaration, archive,
            extracted_facts(args.extract_dir), args.out), indent=1))
    else:
        work = args.work or Path(tempfile.mkdtemp(prefix="estimate-self-"))
        print(f"self-check work dir: {work}")
        self_check(work)


if __name__ == "__main__":
    main()
