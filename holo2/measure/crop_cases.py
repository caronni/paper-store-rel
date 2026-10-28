#!/usr/bin/env python
"""The crop-case generator + cropper — BY PATH (HANDOFF-CROP Deliverable A).

    env/bin/python holo2/measure/crop_cases.py --sheet all

NOT A TEST and not collectable as one — the same standing as
``tile_differential.py`` and ``parity_k.py`` (``holo2/measure/README.md``:
by-path drivers, not tests). Its pure logic (class sets, clustering +
split, the control rim rule, the manifest schema) is pinned in
``tests/holo2_oracles/test_oracle_crop_cases.py`` — there and not under
``holo2/tests`` because this module imports ``holo`` (it reads v1 states;
the firewall exempts exactly that directory). The census renderer took
the ``parity_k_report.py`` seam into ``crop_cases_report.py``.

WHAT IT PRODUCES, per sheet (HANDOFF-CROP, 2026-08-28 — the user's
purpose verbatim: "the point here is to go from 13h runs to minutes
instead" / "or seconds"):

* ``scratch/holo2-catchup/crops/<sheet>/cases.json`` — the manifest, in
  the EXACT schema HANDOFF-CROP fixes (Deliverable B is coded against it
  in parallel; no key may deviate).
* ``scratch/holo2-catchup/crops/<sheet>/<case_id>.tiff`` — grey crops at
  native capture pixels (no resample, no dtype change), tifffile-written.
* ``scratch/holo2-catchup/crops/<sheet>/cases-census.md`` — the census
  (also printed to stdout): per-class counts with the recorded
  cross-check numbers, the state-discovery record, the affine fit and its
  residuals, and per-case sizes/controls.

THE CASE CLASSES (computed, never hand-listed). Three certificate sets
per sheet — cert_v1 (the archived v1 harvest), cert_h2_pre (holo2 before
the F1/F2 line), cert_h2_f2 (holo2 after it) — give four TARGET classes:

* ``still_missing_v2`` = cert_v1 − cert_h2_f2 (3 e029 / 19 xerox),
* ``v1_missing``       = cert_h2_f2 − cert_v1 (1 / 3),
* ``neither``          = in neither final set (20 / 28),
* ``flipped``          = (cert_h2_f2 − cert_h2_pre) − v1_missing
  (26 / 29).

THE DISJOINTNESS RULING THIS MODULE RECORDS (measured 2026-08-28): the
raw pre→F2 flip set (27 e029 / 32 xerox — HANDOFF-CROP's "≈27, ≈32")
OVERLAPS ``v1_missing`` on every one of its tiles (1 / 3): a tile the
F1/F2 line turned positive that v1 never certified is both "flipped" and
"v1-missing" by the raw definitions. HANDOFF-CROP demands the four
classes disjoint within a sheet, and ``v1_missing`` / ``still`` /
``neither`` carry exact recorded counts while ``flipped`` is the one
approximate class — so ``v1_missing`` WINS the overlap and ``flipped``
is the remainder. The census reports the raw count and the overlap it
resolved; nothing is hidden in the arithmetic.

WHERE THE SETS COME FROM (HANDOFF-CROP: recompute from states where one
exists, parse the recorded markdown where it does not, ALWAYS cross-check
against the markdown headers):

* cert_v1 — the archived ``receive.state``, via ``load_session`` (a plain
  file read; RULING I5's door).
* cert_h2_f2 / cert_h2_pre — candidate state dirs under
  ``scratch/holo2-catchup/real/`` are DISCOVERED and each is VERIFIED
  before trust: its certificate set must equal the set the recorded
  differential markdown implies (headers AND tile lists — the derived set
  is ``(cert_v1 − §B) ∪ §C``). A dir that fails verification is treated
  as absent and the census says so by name. Measured at build time
  (2026-08-28): ``parity-F2/h2-e029``/``h2-xerox`` verify at 1938/1914;
  ``e029-state-complete``/``state-complete`` verify at 1911/1882 against
  the pre markdowns; ``parity/h2-e029`` FAILS at 1910 (its set differs
  from the recorded pre differential at tile (1, 32)) and is skipped.
* Stores are opened through ``tile_differential.open_h2_store`` — the
  read-only door, with its lock caveat: never run this while a decode has
  one of these states open (RULINGS §F "never commit").

CLUSTERING AND SPLITTING are SPEED knobs, not evidence caps (memory: no
ceilings on evidence passes — every target lands in exactly ONE case,
asserted): targets whose tile-space gap is ≤ ``--merge-gap-tiles`` empty
tiles (Chebyshev) merge into one cluster rectangle; a cluster whose long
side exceeds ``--max-span-cells`` splits into segments along that axis
(each segment re-shrunk to its own targets' bounding box). The halo
(``--halo-cells``, default 240 ≈ 1.5 window strides at window 200 /
stride 160) expands each rectangle on all sides, clipped to the page.

THE CELL→PIXEL MAP is ONE global affine per sheet, least-squares fitted
from the v1 state's ``accepted`` committed poses (``PoseRecord.
native_affine`` is the canonical page-cell → native-pixel-centre map;
five sample points per pose window). It absorbs whatever orientation the
scan implies (the xerox capture is 180°-rotated; the crop is the AABB of
the transformed cell rectangle). Local deviation from the global fit is
paper/scan warp, measured at build time as ≤ ~80 px (~5 cells) worst
case — which is why the pixel bbox is padded by ``PX_PAD_CELLS`` = 32
cells' worth of pixels on all sides before clipping to the CAPTURE
bounds (real margin context is part of a page-edge case). The census
reports the fit residuals; the manifest records the affine.

CONTROLS, per case: every both-certified (cert_v1 ∩ cert_h2_f2) tile
whose 64-cell extent lies fully inside the case's cell bbox shrunk by a
``CONTROL_RIM_CELLS`` = 32-cell rim — EXCLUDING the sheet's target tiles:
``flipped`` targets are both-certified in the final sets (they flipped
INTO the shared set), and a tile under study as a target in one case must
not simultaneously read as a stability control in another. Controls are
REPORTED per crop and never gated (lead-approved extension; memory:
invented bars are retired).

READ-ONLY on every input: the captures are memmapped ``mode='r'``, the
states are opened through the read-only doors above, and nothing under
``scratch/holo2-catchup/real/`` or the corpus is ever written. Output
goes to ``scratch/holo2-catchup/crops/`` only (gitignored).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import tifffile

# Self-locating, like every other by-path driver in this directory
# (``parity_k.py``'s pattern verbatim): neither package is pip-installed,
# so a driver the operator runs BY PATH should not also demand a
# ``PYTHONPATH=`` prefix to find the trees it lives beside.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE, _ROOT / "src", _ROOT / "holo2" / "src"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

import crop_cases_report                                        # noqa: E402
import tile_differential                                        # noqa: E402

from holo.format.resolve import resolve_format_ref              # noqa: E402
from holo.receive.session import load_session                   # noqa: E402
from holo.receive.session_model import SessionState             # noqa: E402

from holo2.solve import TileState                               # noqa: E402

#: The repository the archived states and captures live in (parity_k's
#: own constant): this driver runs from the catch-up worktree, whose
#: ``scratch/`` is its own; the physical corpus is the main checkout.
_CORPUS = Path("<repo>")
_REAL = _ROOT / "scratch/holo2-catchup/real"

#: One v1 tile is 64x64 cells — ``tile_differential``'s own constant,
#: reused so the two instruments cannot disagree about tile geometry.
TILE_CELLS = tile_differential._TILE_CELLS

#: HANDOFF-CROP fixed values (mechanics 4 and 5) — not knobs.
PX_PAD_CELLS = 32
CONTROL_RIM_CELLS = 32

#: ``full_sheet.h2`` vocabulary: ``tile_differential``'s rank names
#: (its summary-table prose NEVER-ADDRESSED / ADDRESSED-NOT-ATTEMPTED /
#: ATTEMPTED-FAILED / CERTIFIED), JSON-cased as HANDOFF-CROP's own
#: example spells them ("attempted_failed").
RANK_JSON = {
    TileState.UNKNOWN: "never_addressed",
    TileState.ADDRESSED: "addressed_not_attempted",
    TileState.ATTEMPTED: "attempted_failed",
    TileState.CERTIFIED: "certified",
}

Tile = tuple[int, int]                  # (ty, tx) — as tile_differential prints


@dataclass(frozen=True)
class SheetSpec:
    """One sheet's declared record (HANDOFF-CROP "The record")."""

    label: str
    format_ref: str
    capture_path: Path
    capture_sha_prefix: str
    scan_dpi: int
    v1_state: Path
    pre_md: Path
    f2_md: Path
    #: Candidate holo2 state dirs, in discovery order; each is verified
    #: against the corresponding markdown before trust.
    pre_candidates: tuple[Path, ...]
    f2_candidates: tuple[Path, ...]


SHEETS: tuple[SheetSpec, ...] = (
    SheetSpec(
        label="e029", format_ref="L:c2-r0700@3392x2368",
        capture_path=_CORPUS / "scratch/e028/hp-canon-c2-ink-counting.tiff",
        capture_sha_prefix="d9c4e932b904", scan_dpi=4800,
        v1_state=(_CORPUS / "scratch/e028"
                  / "holo-c2-r0700-q07-ink-counting/receive.state"),
        pre_md=_REAL / "differential-e029.md",
        f2_md=_REAL / "differential-e029-F2.md",
        pre_candidates=(_REAL / "e029-state-complete",
                        _REAL / "parity/h2-e029"),
        f2_candidates=(_REAL / "parity-F2/h2-e029",)),
    SheetSpec(
        label="xerox", format_ref="L:c2-r0700@3392x2368",
        capture_path=_CORPUS / "scratch/in/xerox-canon-c2-bw.tiff",
        capture_sha_prefix="57a261454cc0", scan_dpi=4800,
        v1_state=_CORPUS / "scratch/in/holo-xerox-c2-counting-receive.state",
        pre_md=_REAL / "differential-xerox.md",
        f2_md=_REAL / "differential-xerox-F2.md",
        pre_candidates=(_REAL / "state-complete",
                        _REAL / "parity/h2-xerox"),
        f2_candidates=(_REAL / "parity-F2/h2-xerox",)),
)

SHEETS_BY_LABEL = {sheet.label: sheet for sheet in SHEETS}


# --------------------------------------------------------------------
# the recorded markdown (parsed only to VERIFY states, or to stand in
# for one that did not survive)
# --------------------------------------------------------------------

_TILE_LINE = re.compile(r"^### page (\d+), tile \((\d+), (\d+)\)")
_HEADER_LINE = re.compile(
    r"^- (v1 certified|holo2 certified|both|v1 has, holo2 lacks|"
    r"holo2 has, v1 lacks|neither certifies|total tiles in domain): "
    r"\*\*(\d+)\*\*")


@dataclass(frozen=True)
class RecordedDifferential:
    """One recorded ``differential-*.md``, reduced to its facts."""

    headers: Mapping[str, int]
    v1_only: tuple[Tile, ...]           # §B "v1 has, holo2 lacks"
    h2_only: tuple[Tile, ...]           # §C "holo2 has, v1 lacks"

    def h2_set(self, cert_v1: frozenset[Tile]) -> frozenset[Tile]:
        """The holo2 certificate set the record implies:
        ``(cert_v1 − §B) ∪ §C`` — exact, because §B and §C are the whole
        symmetric difference and everything else v1 certifies is shared.
        """
        return frozenset((cert_v1 - set(self.v1_only)) | set(self.h2_only))


def parse_differential_md(path: Path) -> RecordedDifferential:
    """Parse a ``tile_differential``-rendered report. The ``### page P,
    tile (a, b)`` lines under §B/§C are the record (HANDOFF-CROP); the
    §A header counts are the cross-check. Only page 0 exists on these
    single-capture sheets — asserted, so a multi-page record cannot be
    silently flattened.
    """
    headers: dict[str, int] = {}
    section = ""
    tiles: dict[str, list[Tile]] = {"B": [], "C": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        matched = _HEADER_LINE.match(line)
        if matched:
            headers[matched.group(1)] = int(matched.group(2))
        if line.startswith("## (B)"):
            section = "B"
        elif line.startswith("## (C)"):
            section = "C"
        elif line.startswith("## "):
            section = ""
        matched = _TILE_LINE.match(line)
        if matched and section:
            if int(matched.group(1)) != 0:
                raise ValueError(f"{path}: unexpected page "
                                 f"{matched.group(1)} (single-page record)")
            tiles[section].append((int(matched.group(2)),
                                   int(matched.group(3))))
    for name, count in (("v1 has, holo2 lacks", len(tiles["B"])),
                        ("holo2 has, v1 lacks", len(tiles["C"]))):
        if headers.get(name) != count:
            raise ValueError(
                f"{path}: header says {name} = {headers.get(name)!r}, "
                f"but the section lists {count} tiles")
    return RecordedDifferential(headers=headers,
                                v1_only=tuple(tiles["B"]),
                                h2_only=tuple(tiles["C"]))


# --------------------------------------------------------------------
# certificate sets: v1 read, holo2 discovered-and-verified
# --------------------------------------------------------------------


def v1_certified(state: SessionState, stream: str = "main",
                 ) -> frozenset[Tile]:
    """v1's certificate set as (ty, tx) — ``tile_differential``'s own
    tuple convention (``(cert.page, *cert.tile_yx)``) with the page
    asserted to 0 rather than carried.
    """
    out = set()
    for cert in state.certificates:
        if cert.stream_id != stream:
            continue
        if cert.page != 0:
            raise ValueError(f"unexpected page {cert.page} in v1 state")
        out.add(tuple(cert.tile_yx))
    return frozenset(out)


def h2_certified(state_dir: Path, stream: str = "main") -> frozenset[Tile]:
    """One holo2 state dir's certificate set, via ``tile_differential``'s
    read-only door (lock caveat in that module's docstring)."""
    with tile_differential.open_h2_store(state_dir) as store:
        index = tile_differential.build_h2_index(store)
        keys = tile_differential.h2_certified_tiles(index.store_index,
                                                    stream)
    out = set()
    for page, ty, tx in keys:
        if page != 0:
            raise ValueError(f"unexpected page {page} in {state_dir}")
        out.add((ty, tx))
    return frozenset(out)


@dataclass(frozen=True)
class Discovery:
    """Which state dir (if any) verified against a recorded markdown."""

    chosen: Path | None                 # None = the markdown stands in
    certified: frozenset[Tile]
    #: One line per candidate, for the census: verified / failed-and-why.
    trail: tuple[str, ...]


def discover_h2_state(candidates: Sequence[Path],
                      record: RecordedDifferential,
                      cert_v1: frozenset[Tile]) -> Discovery:
    """First candidate whose certificate set EQUALS the recorded one wins;
    a mismatching dir is treated as absent (HANDOFF-CROP: "VERIFY by
    certificate count before trusting a dir" — sharpened to the full set,
    since the count alone cannot see a swapped tile, and the recorded
    tile lists make the set checkable for free)."""
    expected = record.h2_set(cert_v1)
    if len(expected) != record.headers["holo2 certified"]:
        raise ValueError("recorded markdown is self-inconsistent: derived "
                         f"set {len(expected)} != header "
                         f"{record.headers['holo2 certified']}")
    trail: list[str] = []
    for candidate in candidates:
        if not candidate.is_dir():
            trail.append(f"{candidate}: absent")
            continue
        found = h2_certified(candidate)
        if found == expected:
            trail.append(f"{candidate}: VERIFIED ({len(found)} certificates"
                         " — set equals the recorded differential)")
            return Discovery(chosen=candidate, certified=expected,
                             trail=tuple(trail))
        diff = sorted(found ^ expected)
        trail.append(f"{candidate}: FAILED verification ({len(found)} "
                     f"certificates vs recorded "
                     f"{len(expected)}; set differs at {diff[:4]}"
                     f"{' …' if len(diff) > 4 else ''})")
    trail.append("no candidate verified — the recorded markdown's set "
                 "stands in")
    return Discovery(chosen=None, certified=expected, trail=tuple(trail))


# --------------------------------------------------------------------
# the four target classes (pure; pinned by the oracle test)
# --------------------------------------------------------------------

CLASS_NAMES = ("flipped", "still_missing_v2", "v1_missing", "neither")


@dataclass(frozen=True)
class ClassSets:
    flipped: frozenset[Tile]
    still_missing_v2: frozenset[Tile]
    v1_missing: frozenset[Tile]
    neither: frozenset[Tile]
    #: The raw pre→F2 flip tiles that are classed ``v1_missing`` instead
    #: (the disjointness ruling in the module docstring) — reported.
    raw_flip_overlap: frozenset[Tile]

    @property
    def targets(self) -> frozenset[Tile]:
        return (self.flipped | self.still_missing_v2 | self.v1_missing
                | self.neither)

    def class_of(self, tile: Tile) -> str:
        for name in CLASS_NAMES:
            if tile in getattr(self, name):
                return name
        raise KeyError(tile)


def compute_classes(cert_v1: frozenset[Tile], cert_h2_pre: frozenset[Tile],
                    cert_h2_f2: frozenset[Tile], tiles_yx: tuple[int, int],
                    ) -> ClassSets:
    """The four disjoint target classes (module docstring: ``v1_missing``
    wins the raw-flip overlap). Asserts what HANDOFF-CROP demands —
    disjointness within the sheet — plus the partition arithmetic that
    makes the final-set classes equal the recorded F2 header counts:
    both ⊎ still ⊎ v1_missing ⊎ neither must tile the whole domain.
    Note ``flipped`` ⊆ both-certified by construction (a flipped tile
    flipped INTO the shared set)."""
    tiles_y, tiles_x = tiles_yx
    domain = {(ty, tx) for ty in range(tiles_y) for tx in range(tiles_x)}
    for name, certs in (("v1", cert_v1), ("h2_pre", cert_h2_pre),
                        ("h2_f2", cert_h2_f2)):
        if not certs <= domain:
            raise ValueError(f"cert_{name} has tiles outside the "
                             f"{tiles_y}x{tiles_x} domain")
    v1_missing = cert_h2_f2 - cert_v1
    raw_flipped = cert_h2_f2 - cert_h2_pre
    sets = ClassSets(
        flipped=frozenset(raw_flipped - v1_missing),
        still_missing_v2=frozenset(cert_v1 - cert_h2_f2),
        v1_missing=frozenset(v1_missing),
        neither=frozenset(domain - cert_v1 - cert_h2_f2),
        raw_flip_overlap=frozenset(raw_flipped & v1_missing))
    named = [getattr(sets, name) for name in CLASS_NAMES]
    if sum(len(s) for s in named) != len(sets.targets):
        raise AssertionError("target classes overlap within one sheet")
    both = cert_v1 & cert_h2_f2
    if (len(both) + len(sets.still_missing_v2) + len(sets.v1_missing)
            + len(sets.neither)) != tiles_y * tiles_x:
        raise AssertionError("final-set classes do not partition the domain")
    if not sets.flipped <= both:
        raise AssertionError("flipped must be a subset of both-certified")
    return sets


def crosscheck_headers(cert_v1: frozenset[Tile],
                       cert_h2_pre: frozenset[Tile],
                       cert_h2_f2: frozenset[Tile],
                       pre: RecordedDifferential,
                       f2: RecordedDifferential) -> None:
    """Every recomputed count against the recorded markdown headers
    (HANDOFF-CROP: "ALWAYS cross-check"). A mismatch REFUSES the run —
    it means the inputs are not the recorded record."""
    checks = (
        ("pre: v1 certified", len(cert_v1), pre.headers["v1 certified"]),
        ("pre: holo2 certified", len(cert_h2_pre),
         pre.headers["holo2 certified"]),
        ("pre: v1 has, holo2 lacks", len(cert_v1 - cert_h2_pre),
         pre.headers["v1 has, holo2 lacks"]),
        ("pre: holo2 has, v1 lacks", len(cert_h2_pre - cert_v1),
         pre.headers["holo2 has, v1 lacks"]),
        ("F2: v1 certified", len(cert_v1), f2.headers["v1 certified"]),
        ("F2: holo2 certified", len(cert_h2_f2),
         f2.headers["holo2 certified"]),
        ("F2: v1 has, holo2 lacks", len(cert_v1 - cert_h2_f2),
         f2.headers["v1 has, holo2 lacks"]),
        ("F2: holo2 has, v1 lacks", len(cert_h2_f2 - cert_v1),
         f2.headers["holo2 has, v1 lacks"]),
        ("F2: both", len(cert_v1 & cert_h2_f2), f2.headers["both"]),
    )
    for name, computed, recorded in checks:
        if computed != recorded:
            raise ValueError(f"cross-check FAILED — {name}: computed "
                             f"{computed}, recorded {recorded}")


# --------------------------------------------------------------------
# clustering + splitting (pure; pinned by the oracle test)
# --------------------------------------------------------------------


@dataclass(frozen=True)
class Cluster:
    """One case's tile-space content: its targets and their bounding
    rectangle (half-open tile ranges)."""

    members: tuple[Tile, ...]
    ty0: int
    ty1: int
    tx0: int
    tx1: int

    @staticmethod
    def of(members: Iterable[Tile]) -> "Cluster":
        rows = tuple(sorted(members))
        if not rows:
            raise ValueError("a cluster needs at least one target")
        tys = [ty for ty, _ in rows]
        txs = [tx for _, tx in rows]
        return Cluster(members=rows, ty0=min(tys), ty1=max(tys) + 1,
                       tx0=min(txs), tx1=max(txs) + 1)

    @property
    def span_cells_yx(self) -> tuple[int, int]:
        return ((self.ty1 - self.ty0) * TILE_CELLS,
                (self.tx1 - self.tx0) * TILE_CELLS)


def cluster_targets(targets: Iterable[Tile], merge_gap_tiles: int,
                    ) -> list[Cluster]:
    """Union-find over Chebyshev adjacency: two targets share a cluster
    when the EMPTY-TILE GAP between them is ≤ ``merge_gap_tiles`` — i.e.
    Chebyshev distance ≤ gap + 1 (adjacent tiles have gap 0). Output is
    deterministic: clusters sorted by (ty0, tx0, ty1, tx1), members
    sorted within each."""
    rows = sorted(set(targets))
    parent = {tile: tile for tile in rows}

    def find(tile: Tile) -> Tile:
        while parent[tile] != tile:
            parent[tile] = parent[parent[tile]]
            tile = parent[tile]
        return tile

    reach = merge_gap_tiles + 1
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= reach:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
    grouped: dict[Tile, list[Tile]] = {}
    for tile in rows:
        grouped.setdefault(find(tile), []).append(tile)
    clusters = [Cluster.of(members) for members in grouped.values()]
    return sorted(clusters, key=lambda c: (c.ty0, c.tx0, c.ty1, c.tx1))


def split_clusters(clusters: Sequence[Cluster], max_span_cells: int,
                   ) -> list[Cluster]:
    """Split every cluster whose LONG side exceeds ``max_span_cells``
    into segments along that axis (equal tile buckets, each segment
    re-shrunk to its own members' bounding box), repeated until all fit.
    Terminates because a segment's span is strictly smaller than its
    parent's. Every input target lands in exactly one output cluster —
    asserted here, not hoped."""
    queue = list(clusters)
    done: list[Cluster] = []
    while queue:
        cluster = queue.pop()
        span_y, span_x = cluster.span_cells_yx
        if max(span_y, span_x) <= max_span_cells:
            done.append(cluster)
            continue
        axis = 0 if span_y >= span_x else 1
        lo = cluster.ty0 if axis == 0 else cluster.tx0
        hi = cluster.ty1 if axis == 0 else cluster.tx1
        span_tiles = hi - lo
        pieces = -((max(span_y, span_x)) // -max_span_cells)
        buckets: dict[int, list[Tile]] = {}
        for tile in cluster.members:
            offset = (tile[axis] - lo) * pieces // span_tiles
            buckets.setdefault(offset, []).append(tile)
        for members in buckets.values():
            queue.append(Cluster.of(members))
    result = sorted(done, key=lambda c: (c.ty0, c.tx0, c.ty1, c.tx1))
    wanted = sorted(t for c in clusters for t in c.members)
    got = sorted(t for c in result for t in c.members)
    if wanted != got:
        raise AssertionError("split lost or duplicated targets")
    return result


# --------------------------------------------------------------------
# geometry: halo, the global affine, pixel bboxes, controls (pure)
# --------------------------------------------------------------------


def cell_bbox_for(cluster: Cluster, halo_cells: int,
                  page_cells_yx: tuple[int, int],
                  ) -> tuple[int, int, int, int]:
    """The case's cell rectangle: the cluster rect expanded by the halo
    on all sides, clipped to the page. Returned X-FIRST half-open
    ``(cx0, cy0, cx1, cy1)`` — the manifest's own order."""
    cells_y, cells_x = page_cells_yx
    cy0 = max(0, cluster.ty0 * TILE_CELLS - halo_cells)
    cy1 = min(cells_y, cluster.ty1 * TILE_CELLS + halo_cells)
    cx0 = max(0, cluster.tx0 * TILE_CELLS - halo_cells)
    cx1 = min(cells_x, cluster.tx1 * TILE_CELLS + halo_cells)
    return (cx0, cy0, cx1, cy1)


@dataclass(frozen=True)
class GlobalAffine:
    """One sheet's cell→pixel map, in the manifest's X-FIRST convention:
    ``px_x = a*cx + b*cy + c`` (row 0), ``px_y = d*cx + e*cy + f``
    (row 1) — cx along the 2368-cell axis, cy along the 3392-cell axis,
    px_x the capture COLUMN (numpy axis 1), px_y the ROW (axis 0)."""

    rows: tuple[tuple[float, float, float], tuple[float, float, float]]
    n_poses: int
    residual_median_px: float
    residual_p99_px: float
    residual_max_px: float

    def apply(self, cx: float, cy: float) -> tuple[float, float]:
        (a, b, c), (d, e, f) = self.rows
        return (a * cx + b * cy + c, d * cx + e * cy + f)

    @property
    def px_per_cell(self) -> float:
        (a, b, _), (d, e, _) = self.rows
        return float(np.sqrt(abs(a * e - b * d)))


def fit_global_affine(state: SessionState) -> GlobalAffine:
    """ONE global affine per sheet from the v1 state's committed
    ``accepted`` poses (HANDOFF-CROP mechanic 4): every pose's
    ``native_affine`` (canonical page-cell → native pixel centres,
    ``PoseRecord``'s documented convention) is sampled at its window's
    four corners and centre, and the correspondences are least-squares
    fitted. ``redundant`` poses are dropped — superseded placements, the
    same choice ``tile_differential._v1_pose_coverage`` records."""
    pts_cell: list[tuple[float, float]] = []
    pts_px: list[np.ndarray] = []
    n_poses = 0
    for pose in state.poses:
        if pose.placement_outcome != "accepted":
            continue
        n_poses += 1
        affine = np.asarray(pose.native_affine, np.float64).reshape(2, 3)
        height, width = pose.window_shape_yx_cells
        if pose.rot90 % 2:
            height, width = width, height
        y0, x0 = pose.cell_origin_yx
        for cy, cx in ((y0, x0), (y0, x0 + width), (y0 + height, x0),
                       (y0 + height, x0 + width),
                       (y0 + height / 2, x0 + width / 2)):
            pts_cell.append((cy, cx))
            pts_px.append(affine[:, :2] @ (cy, cx) + affine[:, 2])
    if n_poses < 3:
        raise ValueError("too few accepted poses to fit a global affine")
    cell = np.asarray(pts_cell, np.float64)
    px_yx = np.asarray(pts_px, np.float64)
    design = np.column_stack([cell, np.ones(len(cell))])
    coef, *_ = np.linalg.lstsq(design, px_yx, rcond=None)   # (3, 2): y, x
    residual = np.abs(px_yx - design @ coef)
    # Reorder the (cy, cx) → (py, px) fit into the manifest's x-first rows.
    (ayy, axy), (ayx, axx), (cy_c, cx_c) = coef
    return GlobalAffine(
        rows=((float(axx), float(axy), float(cx_c)),
              (float(ayx), float(ayy), float(cy_c))),
        n_poses=n_poses,
        residual_median_px=float(np.median(residual)),
        residual_p99_px=float(np.percentile(residual, 99)),
        residual_max_px=float(residual.max()))


def px_bbox_for(cell_bbox: tuple[int, int, int, int], affine: GlobalAffine,
                capture_shape_yx: tuple[int, int],
                ) -> tuple[int, int, int, int]:
    """The AABB of the transformed cell rectangle (the affine handles
    rotation — the xerox scan is 180°), padded by ``PX_PAD_CELLS`` worth
    of pixels on all sides, clipped to the CAPTURE (off-page halo keeps
    real margin context). X-first half-open ``(px0, py0, px1, py1)``."""
    cx0, cy0, cx1, cy1 = cell_bbox
    corners = [affine.apply(cx, cy)
               for cx in (cx0, cx1) for cy in (cy0, cy1)]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    pad = PX_PAD_CELLS * affine.px_per_cell
    rows_n, cols_n = capture_shape_yx
    px0 = max(0, int(np.floor(min(xs) - pad)))
    px1 = min(cols_n, int(np.ceil(max(xs) + pad)))
    py0 = max(0, int(np.floor(min(ys) - pad)))
    py1 = min(rows_n, int(np.ceil(max(ys) + pad)))
    if px1 <= px0 or py1 <= py0:
        raise ValueError(f"empty pixel bbox from cell bbox {cell_bbox}")
    return (px0, py0, px1, py1)


def controls_for(cell_bbox: tuple[int, int, int, int],
                 both_certified: frozenset[Tile],
                 targets: frozenset[Tile]) -> tuple[Tile, ...]:
    """Every both-certified tile whose 64-cell extent lies FULLY inside
    the cell bbox shrunk by the 32-cell rim (HANDOFF-CROP mechanic 5) —
    a control touching the crop's outer band would measure boundary
    truncation, not crop-vs-full-sheet agreement. ``targets`` is the
    SHEET's whole target set and is excluded: a ``flipped`` target is
    both-certified in the final sets, and a tile under study in one case
    must not double as a stability control in any case (module
    docstring)."""
    cx0, cy0, cx1, cy1 = cell_bbox
    x_lo, x_hi = cx0 + CONTROL_RIM_CELLS, cx1 - CONTROL_RIM_CELLS
    y_lo, y_hi = cy0 + CONTROL_RIM_CELLS, cy1 - CONTROL_RIM_CELLS
    out = []
    for ty, tx in sorted(both_certified - targets):
        if (y_lo <= ty * TILE_CELLS and (ty + 1) * TILE_CELLS <= y_hi
                and x_lo <= tx * TILE_CELLS
                and (tx + 1) * TILE_CELLS <= x_hi):
            out.append((ty, tx))
    return tuple(out)


# --------------------------------------------------------------------
# the manifest (schema fixed by HANDOFF-CROP — Deliverable B reads it)
# --------------------------------------------------------------------

_MANIFEST_KEYS = frozenset({
    "sheet", "capture_path", "capture_sha256", "scan_dpi", "format_ref",
    "tile_convention", "cell_axes", "affine_cell_to_px", "halo_cells",
    "generator", "cases"})
_GENERATOR_KEYS = frozenset({"tree", "dirty_sha"})
_CASE_KEYS = frozenset({"case_id", "crop_file", "cell_bbox", "px_bbox",
                        "targets", "controls"})
_TARGET_KEYS = frozenset({"tile", "classes", "full_sheet"})
_FULL_SHEET_KEYS = frozenset({"v1", "h2"})

TILE_CONVENTION = (
    "tile [a, b] = (ty, tx) exactly as tile_differential.py prints them: "
    "a = ty in 0..52 along the 3392-cell axis, b = tx in 0..36 along the "
    "2368-cell axis; page is 0 everywhere and omitted.")
CELL_AXES = (
    "cell y runs 0..3392, cell x runs 0..2368; cell_bbox and px_bbox are "
    "x-first half-open [x0, y0, x1, y1]; px x is the capture column "
    "(numpy axis 1) and px y the row (axis 0), so a crop is "
    "capture[py0:py1, px0:px1]; affine_cell_to_px maps px_x = a*cx + "
    "b*cy + c (row 0), px_y = d*cx + e*cy + f (row 1).")


def validate_manifest(manifest: dict) -> None:
    """Exact-schema check, used by the generator on its own output and by
    the oracle test's round-trip: every level carries EXACTLY the keys
    HANDOFF-CROP fixes — no more (Deliverable B is coded against this in
    parallel), no fewer."""
    def _exact(mapping: dict, keys: frozenset[str], where: str) -> None:
        if set(mapping) != keys:
            raise ValueError(f"{where}: keys {sorted(mapping)} != "
                             f"schema {sorted(keys)}")

    _exact(manifest, _MANIFEST_KEYS, "manifest")
    _exact(manifest["generator"], _GENERATOR_KEYS, "generator")
    rows = manifest["affine_cell_to_px"]
    if (len(rows) != 2 or any(len(row) != 3 for row in rows)):
        raise ValueError("affine_cell_to_px must be 2x3")
    for case in manifest["cases"]:
        _exact(case, _CASE_KEYS, f"case {case.get('case_id')}")
        for name in ("cell_bbox", "px_bbox"):
            if len(case[name]) != 4:
                raise ValueError(f"{case['case_id']}: {name} must be "
                                 "[x0, y0, x1, y1]")
        for target in case["targets"]:
            _exact(target, _TARGET_KEYS,
                   f"{case['case_id']} target {target.get('tile')}")
            _exact(target["full_sheet"], _FULL_SHEET_KEYS,
                   f"{case['case_id']} target {target['tile']} full_sheet")
            if len(target["tile"]) != 2:
                raise ValueError("target tile must be [a, b]")
            unknown = set(target["classes"]) - set(CLASS_NAMES)
            if unknown or not target["classes"]:
                raise ValueError(f"bad classes {target['classes']}")
        for control in case["controls"]:
            if len(control) != 2:
                raise ValueError("control must be [a, b]")


def build_case_entry(case_id: str, cluster: Cluster,
                     cell_bbox: tuple[int, int, int, int],
                     px_bbox: tuple[int, int, int, int],
                     classes: ClassSets, controls: tuple[Tile, ...],
                     ranks_h2: Mapping[Tile, str],
                     cert_v1: frozenset[Tile]) -> dict:
    targets = []
    for tile in cluster.members:
        targets.append({
            "tile": [tile[0], tile[1]],
            "classes": [classes.class_of(tile)],
            "full_sheet": {
                "v1": "certified" if tile in cert_v1 else "uncertified",
                "h2": ranks_h2[tile],
            }})
    return {"case_id": case_id, "crop_file": f"{case_id}.tiff",
            "cell_bbox": list(cell_bbox), "px_bbox": list(px_bbox),
            "targets": targets,
            "controls": [[ty, tx] for ty, tx in controls]}


def generator_stamp() -> dict:
    """``{"tree": HEAD, "dirty_sha": sha256(git diff HEAD) or ""}`` —
    the manifest's provenance, in the sidecar spirit of parity_k."""
    def _git(*args: str) -> bytes:
        done = subprocess.run(["git", *args], capture_output=True,
                              cwd=str(_ROOT))
        if done.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: "
                               f"{done.stderr.decode().strip()}")
        return done.stdout
    head = _git("rev-parse", "HEAD").decode().strip()
    diff = _git("diff", "HEAD")
    return {"tree": head,
            "dirty_sha": hashlib.sha256(diff).hexdigest() if diff else ""}


# --------------------------------------------------------------------
# the full-sheet h2 ranks (one store open, read-only)
# --------------------------------------------------------------------


def h2_ranks(state_dir: Path, tiles: Iterable[Tile],
             stream: str = "main") -> dict[Tile, str]:
    """``full_sheet.h2`` per target, in ``tile_differential``'s rank
    vocabulary, read from the verified F2 store in ONE open."""
    wanted = sorted(set(tiles))
    out: dict[Tile, str] = {}
    with tile_differential.open_h2_store(state_dir) as store:
        index = tile_differential.build_h2_index(store)
        for ty, tx in wanted:
            state, _spends, _poses = tile_differential.h2_tile_facts(
                store, index, 0, ty, tx, stream)
            out[(ty, tx)] = RANK_JSON[state]
    return out


# --------------------------------------------------------------------
# capture I/O (windowed; read-only)
# --------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_crops(capture_path: Path, cases: Sequence[dict],
                out_dir: Path) -> dict[str, float]:
    """Windowed reads off a read-only memmap (``mode='r'`` — the capture
    is corpus, never written), one crop at a time; returns MB per case.
    Both real captures are uncompressed contiguous single-strip TIFFs,
    which is what makes the memmap a windowed read rather than a load."""
    sizes_mb: dict[str, float] = {}
    plane = tifffile.memmap(str(capture_path), mode="r")
    try:
        if plane.ndim != 2:
            raise ValueError(f"{capture_path}: expected a grey plane, "
                             f"got shape {plane.shape}")
        for case in cases:
            px0, py0, px1, py1 = case["px_bbox"]
            crop = np.ascontiguousarray(plane[py0:py1, px0:px1])
            path = out_dir / case["crop_file"]
            tifffile.imwrite(str(path), crop, photometric="minisblack")
            sizes_mb[case["case_id"]] = crop.nbytes / 1e6
            del crop
    finally:
        del plane
    return sizes_mb


# --------------------------------------------------------------------
# one sheet, end to end
# --------------------------------------------------------------------


@dataclass
class SheetResult:
    spec: SheetSpec
    manifest: dict
    classes: ClassSets
    pre_discovery: Discovery
    f2_discovery: Discovery
    affine: GlobalAffine
    capture_shape_yx: tuple[int, int]
    sizes_mb: dict[str, float]
    n_both: int
    wall_s: float


def generate_sheet(spec: SheetSpec, out_root: Path, *, merge_gap_tiles: int,
                   max_span_cells: int, halo_cells: int) -> SheetResult:
    started = time.perf_counter()
    fmt = resolve_format_ref(spec.format_ref)
    # spec._tiles_yx: the total resolving property (tile_differential.run's
    # own choice and its reason — the public field is None for fossils).
    tiles_yx = fmt._tiles_yx
    page_cells_yx = (tiles_yx[0] * TILE_CELLS, tiles_yx[1] * TILE_CELLS)

    v1_state = load_session(spec.v1_state)
    cert_v1 = v1_certified(v1_state)
    if len(v1_state.captures) != 1:
        raise ValueError(f"{spec.label}: expected a single capture")
    recorded_sha = v1_state.captures[0].source_sha256
    affine = fit_global_affine(v1_state)

    capture_sha = sha256_file(spec.capture_path)
    if not capture_sha.startswith(spec.capture_sha_prefix):
        raise ValueError(f"{spec.label}: capture sha {capture_sha[:12]} != "
                         f"declared prefix {spec.capture_sha_prefix}")
    if capture_sha != recorded_sha:
        raise ValueError(f"{spec.label}: capture sha differs from the v1 "
                         f"state's authenticated source "
                         f"({capture_sha[:12]} vs {recorded_sha[:12]})")

    pre_record = parse_differential_md(spec.pre_md)
    f2_record = parse_differential_md(spec.f2_md)
    pre = discover_h2_state(spec.pre_candidates, pre_record, cert_v1)
    f2 = discover_h2_state(spec.f2_candidates, f2_record, cert_v1)
    if f2.chosen is None:
        raise SystemExit(f"crop_cases: no F2 state dir verified for "
                         f"{spec.label} — the h2 ranks need the store; "
                         f"trail: {f2.trail}")
    crosscheck_headers(cert_v1, pre.certified, f2.certified,
                       pre_record, f2_record)
    classes = compute_classes(cert_v1, pre.certified, f2.certified, tiles_yx)
    both = frozenset(cert_v1 & f2.certified)

    clusters = split_clusters(
        cluster_targets(classes.targets, merge_gap_tiles), max_span_cells)
    covered = sorted(t for c in clusters for t in c.members)
    if covered != sorted(classes.targets):
        raise AssertionError("cases do not cover every target exactly once")

    ranks = h2_ranks(f2.chosen, classes.targets)

    with tifffile.TiffFile(str(spec.capture_path)) as handle:
        capture_shape = handle.pages[0].shape
    cases = []
    for offset, cluster in enumerate(clusters, start=1):
        case_id = f"{spec.label}-c{offset:02d}"
        cell_bbox = cell_bbox_for(cluster, halo_cells, page_cells_yx)
        px_bbox = px_bbox_for(cell_bbox, affine, capture_shape)
        controls = controls_for(cell_bbox, both, classes.targets)
        cases.append(build_case_entry(case_id, cluster, cell_bbox, px_bbox,
                                      classes, controls, ranks, cert_v1))

    manifest = {
        "sheet": spec.label,
        "capture_path": str(spec.capture_path),
        "capture_sha256": capture_sha,
        "scan_dpi": spec.scan_dpi,
        "format_ref": spec.format_ref,
        "tile_convention": TILE_CONVENTION,
        "cell_axes": CELL_AXES,
        "affine_cell_to_px": [list(row) for row in affine.rows],
        "halo_cells": halo_cells,
        "generator": generator_stamp(),
        "cases": cases,
    }
    validate_manifest(manifest)

    out_dir = out_root / spec.label
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes_mb = write_crops(spec.capture_path, cases, out_dir)
    (out_dir / "cases.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return SheetResult(spec=spec, manifest=manifest, classes=classes,
                       pre_discovery=pre, f2_discovery=f2, affine=affine,
                       capture_shape_yx=(int(capture_shape[0]),
                                         int(capture_shape[1])),
                       sizes_mb=sizes_mb, n_both=len(both),
                       wall_s=time.perf_counter() - started)


# --------------------------------------------------------------------
# the census
# --------------------------------------------------------------------


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet", action="append", default=[],
                        help="a declared sheet label, or 'all' "
                             f"({', '.join(SHEETS_BY_LABEL)})")
    parser.add_argument("--merge-gap-tiles", type=int, default=2,
                        help="targets whose empty-tile gap is <= this "
                             "merge into one cluster (default 2)")
    parser.add_argument("--max-span-cells", type=int, default=768,
                        help="a cluster whose long side exceeds this "
                             "splits into segments (default 768)")
    parser.add_argument("--halo-cells", type=int, default=240,
                        help="context added around every cluster on all "
                             "sides (default 240 ~ 1.5 window strides)")
    parser.add_argument("--out-root", type=Path,
                        default=_ROOT / "scratch/holo2-catchup/crops",
                        help="where <sheet>/cases.json, crops and census "
                             "land")
    args = parser.parse_args(argv)

    labels = args.sheet or ["all"]
    if "all" in labels:
        chosen = list(SHEETS)
    else:
        unknown = [name for name in labels if name not in SHEETS_BY_LABEL]
        if unknown:
            raise SystemExit(f"crop_cases: unknown sheet(s) {unknown}; "
                             f"declared: {sorted(SHEETS_BY_LABEL)}")
        chosen = [SHEETS_BY_LABEL[name] for name in labels]

    for spec in chosen:
        print(f"crop_cases: {spec.label} …", file=sys.stderr)
        result = generate_sheet(spec, args.out_root,
                                merge_gap_tiles=args.merge_gap_tiles,
                                max_span_cells=args.max_span_cells,
                                halo_cells=args.halo_cells)
        census = crop_cases_report.render_census(
            result, merge_gap_tiles=args.merge_gap_tiles,
            max_span_cells=args.max_span_cells, px_pad_cells=PX_PAD_CELLS,
            control_rim_cells=CONTROL_RIM_CELLS)
        print(census)
        census_path = args.out_root / spec.label / "cases-census.md"
        census_path.write_text(census, encoding="utf-8")
        print(f"wrote {args.out_root / spec.label}/cases.json + "
              f"{len(result.manifest['cases'])} crops + cases-census.md",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
