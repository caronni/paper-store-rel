"""Layer 2 — page composition: payload + pilot furniture -> one plane bitmap (M1).

compose_page overlays the layout_version-2 pilot lattice (p60b6.v2, PILOTS-DESIGN
§2.1/§8) on a kcell payload field:

  1. pilot sites from the v2 site derivation (one site per 6x6-cell block at a
     seeded in-block offset, offsets repeating with the 60-cell pilot tile —
     exactly 100 sites per tile, density 1/36);
  2. payload bits fill the non-pilot cells in raster order, XOR-scrambled with
     modulation.keystream(seed, "CMYK".index(plane), page, page_cells_yx) at
     their ABSOLUTE cell coords (identical to the encodings kcell binary
     convention, encodings.key_symbols);
  3. pilot cells carry the tile's 100-bit scrambled codeword
     (pilots.encode_word) at site raster order s = by*10 + bx — rendered
     through the SAME constellation as payload (whole known cells);
  4. cells expand to dots via modulation.cells_to_dots (solid cell^2 blocks).

v1 composer scope: kcell-c3, single plane, page_cells exact multiples of the
pilot period (no partial tiles). This is a FORMAT-AXIS module: layout_version 2;
the v1 pilots.pilot_sites / PERIOD=64 pattern is untouched (label separation
via b"pilot-sites-v2").

layout_version 4 (cmy8-c3 color pages, COLOR-DESIGN D1-D7 / PILOTS-DESIGN
§16): three binary LEVELS per cell (level order C, M, Y — one presence bit
per plane), each level XOR-scrambled with its own plane keystream
("CMYK".index of "CMY"[level]); pilot word sites render bit=1 as the
RENDER_DARK ink state (P1-frozen fixed CM, D3) and bit=0 as
all-plane white; a tile-periodic training-DUST population (paperholo.dust)
carries known 8-state cells excluded from the payload bijection. Emission =
ONE put_cmyk_bitmap composite (the characterized overlap-preserving path,
exp-004 idiom; M281 re-screens ~165 lpi ALWAYS, AltaLink honors overlap).

`word_provider` is injectable so composition round-trips without the ECC
(pilots.encode_word may land separately); the default is pilots.encode_word.
The site-mask derivation is likewise taken from paperholo.pilots when the v2
functions exist there, with a local contract-frozen fallback (byte-identical
derivation by construction: same rng label, same offset draw, same raster site
order) so this module works standalone.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import pilots
from .dust import DustLayout, dust_site_mask, dust_states_page
from .encodings import get_encoding
from .modulation import cells_to_dots, keystream, rng
from .psgen import A4_PT, CMYK, PSDoc

LAYOUT_VERSION = 2            # default (frozen v2 surface)
LAYOUT_VERSIONS = (2, 3, 4)   # 3 = p60b6.v3-k18; 4 = cmy8 color (v3 words +
                              # v4 value labels + dust, PILOTS-DESIGN §16)
# v4 pilot-word DARK rendering: planes inked on word bit = 1 (bit = 0 is
# all-plane white). FROZEN BY MEASUREMENT (probe P1, run 017.0; COLOR-DESIGN
# D3): fixed 2-ink CM — the M281 re-screen dilutes per-plane coverage so the
# 3-ink stack prints LIGHTER than CM (W-vs-triple 10.1% vs W-vs-CM 5.8% at
# the Stage-A statistic; AltaLink a tie), CM survives an empty Y cartridge
# unmoved AND a single C-or-M death. FORMAT-AXIS constant, pinned by the
# gen_e017 golden.
RENDER_DARK: str = "CM"
_LEVEL_PLANES = "CMY"         # level index l <-> plane _LEVEL_PLANES[l]
HW_DPI = 600
# Format-axis derivation label (frozen; distinct from v1's b"pilot-sites").
PILOT_SITES_LABEL_V2: bytes = b"pilot-sites-v2"
# A4 = 210 x 297 mm at 600 dpi (cal_core white_model normalization constants).
A4_W_DOTS, A4_H_DOTS = 4960, 7016
# Experiment content bound: 6 mm on all sides (gen_e006/gen_calpage convention,
# stricter than the measured 4 mm printable margin).
CONTENT_MARGIN_MM = 6.0
MM_PER_DOT = 25.4 / HW_DPI


if hasattr(pilots, "PilotLayout"):
    PilotLayout = pilots.PilotLayout
else:  # pilots v2 (module A') not landed yet — contract-identical fallback
    @dataclass(frozen=True)
    class PilotLayout:  # type: ignore[no-redef]
        period_cells: int = 60
        block_cells: int = 6
        version: int = 2


def _blocks_per_period(layout: PilotLayout) -> int:
    p, b = layout.period_cells, layout.block_cells
    if b <= 0 or p % b != 0:
        raise ValueError(f"period_cells {p} must be a positive multiple of block_cells {b}")
    return p // b


def _sites_per_tile(layout: PilotLayout) -> int:
    return _blocks_per_period(layout) ** 2


def _site_positions_tile(layout: PilotLayout, seed: bytes) -> np.ndarray:
    """(sites, 2) int (y_cell, x_cell) within ONE pilot tile, raster site order.

    Prefers pilots.site_positions_tile (module A'); the fallback implements the
    frozen contract derivation: in-block (dy, dx) offsets from
    rng(seed, b"pilot-sites-v2").integers(0, block, size=(blocks, blocks, 2)),
    site index s = by*blocks + bx.
    """
    fn = getattr(pilots, "site_positions_tile", None)
    if fn is not None:
        return np.asarray(fn(layout, seed), dtype=np.int64)
    nb = _blocks_per_period(layout)
    off = rng(seed, PILOT_SITES_LABEL_V2).integers(
        0, layout.block_cells, size=(nb, nb, 2))
    s = np.arange(nb * nb)
    by, bx = s // nb, s % nb
    pos = np.stack([by * layout.block_cells + off[by, bx, 0],
                    bx * layout.block_cells + off[by, bx, 1]], axis=1)
    return pos.astype(np.int64)


def _pilot_site_mask(shape_cells: tuple[int, int], layout: PilotLayout,
                     seed: bytes) -> np.ndarray:
    """Boolean pilot-site mask over a cell grid (periodic with period_cells)."""
    fn = getattr(pilots, "pilot_site_mask", None)
    if fn is not None:
        return np.asarray(fn(shape_cells, layout, seed), dtype=bool)
    p = layout.period_cells
    pos = _site_positions_tile(layout, seed)
    tile = np.zeros((p, p), dtype=bool)
    tile[pos[:, 0], pos[:, 1]] = True
    h, w = shape_cells
    return np.tile(tile, (-(-h // p), -(-w // p)))[:h, :w]


@dataclass(frozen=True)
class ComposeSpec:
    """Format-axis slice owned by the composer (layout_version 2, v1 scope)."""

    layout_version: int = 2
    encoding_id: str = "kcell-c3"       # v1 scope: kcell-c3 only
    plane: str = "K"
    pilot: PilotLayout = PilotLayout()
    page_cells_yx: tuple[int, int] = (2220, 1500)   # multiples of period_cells
    x_dots: int = 230                    # cell (0,0) top-left on A4 (dot frame)
    y_dots: int = 178
    dust: DustLayout | None = None       # v4 training dust; None for v < 4

    def __post_init__(self) -> None:
        if self.layout_version not in LAYOUT_VERSIONS:
            raise ValueError(f"layout_version must be one of {LAYOUT_VERSIONS}, "
                             f"got {self.layout_version}")
        if self.pilot.version != self.layout_version:
            raise ValueError(
                f"pilot layout version {self.pilot.version} inconsistent with "
                f"layout_version {self.layout_version} (pass "
                f"pilot=PilotLayout(version={self.layout_version}))")
        if self.encoding_id not in ("kcell-c3", "kcell-c2", "cmy8-c3"):
            # kcell-c2 admitted 2026-07-08 (e014 office sheet): every
            # downstream path is cell_dots-parameterized; c2 remains
            # ENCODE-side only for now — the blind receiver's c2-class
            # machinery (ctx pilot bits, duplicated words) is unbuilt,
            # deferred by user decision (experiments/014-c2-print.md).
            # cmy8-c3 admitted 2026-07-10 (layout_version 4, COLOR-DESIGN).
            raise ValueError("composer scope is kcell-c3/kcell-c2/cmy8-c3, "
                             f"got {self.encoding_id!r}")
        enc = get_encoding(self.encoding_id)
        if enc.kind == "cell_mlc":
            if self.layout_version != 4:
                raise ValueError(f"{self.encoding_id} is a layout_version-4 "
                                 "encoding (COLOR-DESIGN D7)")
            if self.plane != "".join(enc.planes):
                raise ValueError(
                    f"multi-level plane must be {''.join(enc.planes)!r}, "
                    f"got {self.plane!r}")
            if self.dust is None:
                raise ValueError("layout_version 4 pages carry training dust "
                                 "by definition (D7): pass dust=DustLayout(...)")
        else:
            if self.layout_version == 4:
                raise ValueError("layout_version 4 is defined for cmy8 only "
                                 f"(D7); {self.encoding_id} is v2/v3")
            if self.plane not in enc.planes:
                raise ValueError(f"plane {self.plane!r} not in encoding planes "
                                 f"{enc.planes}")
            if self.dust is not None:
                raise ValueError("dust is a layout_version-4 (cmy8) feature; "
                                 "None for v<4")
        if self.dust is not None:
            free = self.pilot.period_cells ** 2 - _sites_per_tile(self.pilot)
            if self.dust.sites_per_tile > free:
                raise ValueError(
                    f"dust sites_per_tile {self.dust.sites_per_tile} exceeds "
                    f"the {free} non-pilot cells per pilot tile")
        h, w = self.page_cells_yx
        p = self.pilot.period_cells
        _sites_per_tile(self.pilot)  # validates period % block
        if h <= 0 or w <= 0 or h % p or w % p:
            raise ValueError(f"page_cells_yx {self.page_cells_yx} must be "
                             f"positive multiples of period_cells {p} (v1 "
                             "scope: no partial tiles)")
        h_dots, w_dots = h * self.cell_dots, w * self.cell_dots
        margins_dots = (self.y_dots, self.x_dots,
                        A4_H_DOTS - self.y_dots - h_dots,
                        A4_W_DOTS - self.x_dots - w_dots)
        min_margin_mm = min(margins_dots) * MM_PER_DOT
        if min_margin_mm < CONTENT_MARGIN_MM:
            raise ValueError(
                f"content margin {min_margin_mm:.2f} mm < {CONTENT_MARGIN_MM}"
                f" mm bound (field {w_dots}x{h_dots} dots at "
                f"({self.x_dots},{self.y_dots}) on A4 {A4_W_DOTS}x{A4_H_DOTS})")

    @property
    def cell_dots(self) -> int:
        cd = get_encoding(self.encoding_id).cell_dots
        assert cd is not None
        return int(cd)

    @property
    def n_levels(self) -> int:
        """Binary levels per cell: 3 for cmy8 (one per plane, order C,M,Y),
        1 for every single-plane kcell encoding."""
        enc = get_encoding(self.encoding_id)
        return len(enc.planes) if enc.kind == "cell_mlc" else 1

    @property
    def field_dots_yx(self) -> tuple[int, int]:
        h, w = self.page_cells_yx
        return h * self.cell_dots, w * self.cell_dots

    @property
    def page_tiles_yx(self) -> tuple[int, int]:
        h, w = self.page_cells_yx
        p = self.pilot.period_cells
        return h // p, w // p

    @property
    def word_geometry(self) -> dict:
        """encode_word/decode_word geometry kwargs for this page: empty for
        v2 (address fields are explicit), (tiles_x, tiles_per_page) for the
        v3 flat counter."""
        if self.layout_version == 2:
            return {}
        ty, tx = self.page_tiles_yx
        return {"tiles_x": tx, "tiles_per_page": ty * tx}


@dataclass(frozen=True, eq=False)
class ComposedPage:
    spec: ComposeSpec
    seed: bytes
    page: int
    cell_values: np.ndarray        # (H, W) uint8 printed cell grid (pilots
    #                                overlaid); cmy8: (3, H, W), levels C,M,Y
    pilot_mask: np.ndarray         # (H, W) bool
    plane_bits: np.ndarray         # (H*cell, W*cell) uint8, ink = 1;
    #                                cmy8: (3, H*cell, W*cell), planes C,M,Y
    payload_bits: np.ndarray       # the input payload (pre-scramble),
    #                                (capacity,); cmy8: (3, capacity)
    payload_capacity_bits: int
    dust_mask: np.ndarray | None = None   # (H, W) bool for v4, else None


def payload_capacity(spec: ComposeSpec) -> int:
    """Payload bits PER LEVEL per page: cells minus pilot sites (minus dust
    sites on v4 pages). Every level of a cmy8 page shares this capacity and
    the same index map."""
    h, w = spec.page_cells_yx
    p = spec.pilot.period_cells
    per_tile = _sites_per_tile(spec.pilot)
    if spec.dust is not None:
        per_tile += spec.dust.sites_per_tile
    return h * w - (h // p) * (w // p) * per_tile


def _payload_keystream(spec: ComposeSpec, seed: bytes, page: int,
                       level: int | None = None) -> np.ndarray:
    # Identical to the encodings kcell binary convention (encodings.key_symbols):
    # keystream(seed, "CMYK".index(plane), page, shape), indexed at ABSOLUTE
    # cell coords. cmy8 levels use their plane's index ("CMY"[level]).
    if spec.n_levels == 1:
        return keystream(seed, "CMYK".index(spec.plane), page,
                         spec.page_cells_yx)
    if level is None or not 0 <= level < spec.n_levels:
        raise ValueError(f"multi-level spec needs level in [0, "
                         f"{spec.n_levels}), got {level}")
    return keystream(seed, "CMYK".index(_LEVEL_PLANES[level]), page,
                     spec.page_cells_yx)


def _nonpayload_mask(spec: ComposeSpec, seed: bytes) -> np.ndarray:
    """(H, W) bool: cells excluded from the payload bijection (pilot sites,
    plus dust sites on v4 pages)."""
    mask = _pilot_site_mask(spec.page_cells_yx, spec.pilot, seed)
    if spec.dust is not None:
        mask = mask | dust_site_mask(spec.page_cells_yx, spec.pilot,
                                     spec.dust, seed)
    return mask


def compose_page(payload_bits, spec: ComposeSpec, seed: bytes,
                 page: int = 0,
                 word_provider: Callable[[int, int], np.ndarray] | None = None,
                 ) -> ComposedPage:
    """Compose one page: scrambled payload + pilot codewords, cell grid + dots.

    word_provider(ptile_y, ptile_x) -> (sites_per_tile,) uint8 {0,1}; default =
    pilots.encode_word(spec.pilot, seed, spec.plane, page, ty, tx). Injectable
    so composition is testable without the ECC.

    cmy8 (spec.n_levels == 3): payload_bits is a LIST of 3 arrays (levels
    C, M, Y — same (payload_capacity,) shape, same index map); the default
    word_provider draws the LUMA word (plane "K", D3); word bit=1 renders as
    RENDER_DARK ink on the listed planes, bit=0 all-plane white; dust cells
    render their paperholo.dust states. Returns cell_values (3, H, W) and
    plane_bits (3, H*cell, W*cell).
    """
    if spec.n_levels == 3:
        return _compose_page_cmy8(payload_bits, spec, seed, page,
                                  word_provider)
    h, w = spec.page_cells_yx
    capacity = payload_capacity(spec)
    payload = np.asarray(payload_bits)
    if payload.ndim != 1 or payload.size != capacity:
        raise ValueError(f"payload_bits must be 1-D of exactly {capacity} bits, "
                         f"got shape {payload.shape}")
    payload = payload.astype(np.uint8)
    if payload.size and int(payload.max()) > 1:
        raise ValueError("payload_bits must be {0,1}")

    mask = _pilot_site_mask((h, w), spec.pilot, seed)
    ks = _payload_keystream(spec, seed, page)
    cell_values = np.zeros((h, w), dtype=np.uint8)
    nonpilot = ~mask
    # payload bit i <-> i-th non-pilot cell in raster order (C-order boolean
    # indexing), XOR keystream at the cell's absolute coords
    cell_values[nonpilot] = payload ^ ks[nonpilot]

    if word_provider is None:
        encode_word = getattr(pilots, "encode_word", None)
        if encode_word is None:
            raise RuntimeError(
                "pilots.encode_word is not available (pilots v2 not landed); "
                "pass an explicit word_provider")
        geo = spec.word_geometry  # v3 flat counter needs the tile geometry

        def word_provider(ty: int, tx: int) -> np.ndarray:  # noqa: F811
            return encode_word(spec.pilot, seed, spec.plane, page, ty, tx,
                               **geo)

    pos = _site_positions_tile(spec.pilot, seed)
    n_sites = _sites_per_tile(spec.pilot)
    p = spec.pilot.period_cells
    for ty in range(h // p):
        for tx in range(w // p):
            word = np.asarray(word_provider(ty, tx)).astype(np.uint8).ravel()
            if word.shape != (n_sites,):
                raise ValueError(f"word_provider({ty},{tx}) returned shape "
                                 f"{word.shape}, expected ({n_sites},)")
            if word.size and int(word.max()) > 1:
                raise ValueError(f"word_provider({ty},{tx}) bits must be {{0,1}}")
            cell_values[ty * p + pos[:, 0], tx * p + pos[:, 1]] = word

    plane_bits = cells_to_dots(cell_values, spec.cell_dots)
    return ComposedPage(spec=spec, seed=seed, page=page,
                        cell_values=cell_values, pilot_mask=mask,
                        plane_bits=plane_bits, payload_bits=payload,
                        payload_capacity_bits=capacity)


def _validated_word(word_provider: Callable[[int, int], np.ndarray],
                    ty: int, tx: int, n_sites: int) -> np.ndarray:
    word = np.asarray(word_provider(ty, tx)).astype(np.uint8).ravel()
    if word.shape != (n_sites,):
        raise ValueError(f"word_provider({ty},{tx}) returned shape "
                         f"{word.shape}, expected ({n_sites},)")
    if word.size and int(word.max()) > 1:
        raise ValueError(f"word_provider({ty},{tx}) bits must be {{0,1}}")
    return word


def _compose_page_cmy8(payload_bits_per_level, spec: ComposeSpec, seed: bytes,
                       page: int,
                       word_provider: Callable[[int, int], np.ndarray] | None,
                       ) -> ComposedPage:
    """cmy8 composer (see compose_page docstring). Level order C, M, Y."""
    h, w = spec.page_cells_yx
    capacity = payload_capacity(spec)
    if (not isinstance(payload_bits_per_level, (list, tuple))
            or len(payload_bits_per_level) != spec.n_levels):
        raise ValueError("cmy8 payload_bits must be a list of "
                         f"{spec.n_levels} per-level arrays")
    levels: list[np.ndarray] = []
    for lv, arr in enumerate(payload_bits_per_level):
        a = np.asarray(arr)
        if a.ndim != 1 or a.size != capacity:
            raise ValueError(f"level {lv} payload must be 1-D of exactly "
                             f"{capacity} bits, got shape {a.shape}")
        a = a.astype(np.uint8)
        if a.size and int(a.max()) > 1:
            raise ValueError(f"level {lv} payload bits must be {{0,1}}")
        levels.append(a)

    pilot_mask = _pilot_site_mask((h, w), spec.pilot, seed)
    assert spec.dust is not None            # __post_init__ guarantees it
    dmask = dust_site_mask((h, w), spec.pilot, spec.dust, seed)
    payload_cells = ~(pilot_mask | dmask)

    cell_values = np.zeros((3, h, w), dtype=np.uint8)
    for lv in range(3):
        ks = _payload_keystream(spec, seed, page, level=lv)
        cell_values[lv][payload_cells] = levels[lv] ^ ks[payload_cells]

    # training dust: known 8-state cells (values keyed by absolute tile)
    dstates = dust_states_page((h, w), spec.pilot, spec.dust, seed, page)
    for lv in range(3):
        cell_values[lv][dmask] = dstates[lv][dmask]

    # pilot words: LUMA objects (plane "K", D3); bit=1 -> RENDER_DARK planes
    # ink, bit=0 -> all-plane white
    if word_provider is None:
        geo = spec.word_geometry

        def word_provider(ty: int, tx: int) -> np.ndarray:  # noqa: F811
            return pilots.encode_word(spec.pilot, seed, "K", page, ty, tx,
                                      **geo)

    pos = _site_positions_tile(spec.pilot, seed)
    n_sites = _sites_per_tile(spec.pilot)
    p = spec.pilot.period_cells
    for ty in range(h // p):
        for tx in range(w // p):
            word = _validated_word(word_provider, ty, tx, n_sites)
            ys, xs = ty * p + pos[:, 0], tx * p + pos[:, 1]
            for lv in range(3):
                cell_values[lv, ys, xs] = (
                    word if _LEVEL_PLANES[lv] in RENDER_DARK else 0)

    plane_bits = np.stack([cells_to_dots(cell_values[lv], spec.cell_dots)
                           for lv in range(3)])
    return ComposedPage(spec=spec, seed=seed, page=page,
                        cell_values=cell_values, pilot_mask=pilot_mask,
                        plane_bits=plane_bits,
                        payload_bits=np.stack(levels),
                        payload_capacity_bits=capacity, dust_mask=dmask)


def extract_payload(cell_values: np.ndarray, spec: ComposeSpec, seed: bytes,
                    page: int) -> np.ndarray:
    """Exact inverse of compose_page's payload embedding (receiver's last
    step). Single-level (K) pages only — cmy8 uses extract_payload_levels."""
    if spec.n_levels != 1:
        raise ValueError("multi-level spec: use extract_payload_levels")
    h, w = spec.page_cells_yx
    cv = np.asarray(cell_values)
    if cv.shape != (h, w):
        raise ValueError(f"cell_values shape {cv.shape} != page_cells_yx {(h, w)}")
    cv = cv.astype(np.uint8)
    mask = _pilot_site_mask((h, w), spec.pilot, seed)
    ks = _payload_keystream(spec, seed, page)
    nonpilot = ~mask
    return (cv[nonpilot] ^ ks[nonpilot]).astype(np.uint8)


def extract_payload_levels(cell_values: np.ndarray, spec: ComposeSpec,
                           seed: bytes, page: int) -> list[np.ndarray]:
    """Level-aware inverse of _compose_page_cmy8: (3, H, W) cell grid ->
    [3 x (payload_capacity,)] pre-scramble payload arrays (levels C, M, Y).
    The K-path extract_payload signature is untouched."""
    if spec.n_levels != 3:
        raise ValueError("single-level spec: use extract_payload")
    h, w = spec.page_cells_yx
    cv = np.asarray(cell_values)
    if cv.shape != (3, h, w):
        raise ValueError(f"cell_values shape {cv.shape} != (3, {h}, {w})")
    cv = cv.astype(np.uint8)
    payload_cells = ~_nonpayload_mask(spec, seed)
    out: list[np.ndarray] = []
    for lv in range(3):
        ks = _payload_keystream(spec, seed, page, level=lv)
        out.append((cv[lv][payload_cells]
                    ^ ks[payload_cells]).astype(np.uint8))
    return out


def payload_keystream(spec: ComposeSpec, seed: bytes, page: int,
                      level: int | None = None) -> np.ndarray:
    """Public decode-side accessor for the payload scrambler (Wave-2 receiver:
    the acquisition pipeline descrambles at ABSOLUTE cell coords without
    re-deriving the keystream convention). cmy8 pages pass level (0..2 =
    C, M, Y); the K signature/behavior is unchanged."""
    return _payload_keystream(spec, seed, page, level=level)


def payload_index_map(spec: ComposeSpec, seed: bytes) -> np.ndarray:
    """(H, W) int64 map: absolute cell -> raster index into the page payload
    bijection (payload bit i <-> i-th non-pilot cell in raster order), -1 at
    pilot sites (and dust sites on v4 pages — dust never carries payload).
    The map is LEVEL-INDEPENDENT on cmy8 pages: all three levels share it.
    Decode-side inverse bookkeeping of compose_page's embedding:
    a fragment covering absolute cells S recovers payload_bits at indices
    payload_index_map(...)[S] (the receiver's addressing step; extract_payload
    remains the full-page inverse)."""
    h, w = spec.page_cells_yx
    nonpilot = ~_nonpayload_mask(spec, seed)
    idx = np.full((h, w), -1, dtype=np.int64)
    idx[nonpilot] = np.arange(int(nonpilot.sum()), dtype=np.int64)
    return idx


def emit_composed(composed: ComposedPage, out_ps: str | Path, *,
                  title: str = "paperholo e011 pilot page",
                  artifact: str = "e011",
                  experiment: str = "011-pilot-roundtrip",
                  print_command: str | None = None,
                  extra_manifest: dict | None = None) -> dict:
    """Emit an archive-style (R3) page: ONE whole-page imagemask, no furniture.

    Writes <out>.ps + <stem>_manifest.json + <stem>_gt/<plane>__<artifact>_field
    .npy in the calpage manifest convention (cal_core.load_manifest/entry/
    load_gt work unchanged). Deterministic; ps_sha256 gates reuse. The
    artifact/experiment/print_command defaults keep the e011 (layout_version 2)
    output byte-identical — the frozen golden anchors pin them.
    `extra_manifest` entries are merged at manifest top level (e.g.
    word-provider provenance).

    cmy8 pages (plane_bits (3, H, W)): ONE put_cmyk_bitmap composite — the
    characterized overlap-preserving path (exp-004 emission idiom; M281
    re-screens ~165 lpi ALWAYS, Layer-0 freeze; AltaLink honors overlap
    unscreened, 007.6). Per-plane GT .npy files (C/M/Y) and one manifest
    patch entry per plane carrying composite_of + emission="cmyk_image"
    (the e004 manifest convention for composites).
    """
    spec = composed.spec
    is_mlc = spec.n_levels == 3
    out = Path(out_ps)
    out.parent.mkdir(parents=True, exist_ok=True)
    jobid = hashlib.sha256(
        composed.seed + b"/" + artifact.encode()
        + f"/layout{spec.layout_version}".encode()).hexdigest()[:8]

    doc = PSDoc(hw_dpi=HW_DPI, page_size_pt=A4_PT,
                title=f"{title} LAY={spec.layout_version} J={jobid}",
                guard_setpagedevice=True)
    doc.begin_page()
    # NO header, NO sentinel, NO corner marks: archive-style page (DESIGN R3).
    if is_mlc:
        doc.put_cmyk_bitmap(
            {pl: composed.plane_bits[lv] for lv, pl in enumerate(_LEVEL_PLANES)},
            spec.x_dots, spec.y_dots)
    else:
        doc.put_bitmap(composed.plane_bits, spec.x_dots, spec.y_dots,
                       CMYK[spec.plane])
    doc.end_page()
    ps = doc.render()
    sha = hashlib.sha256(ps.encode()).hexdigest()
    out.write_text(ps)

    name = f"{artifact}_field"
    gt_dirname = f"{out.stem}_gt"
    (out.parent / gt_dirname).mkdir(parents=True, exist_ok=True)
    if is_mlc:
        gt_rels = {}
        for lv, pl in enumerate(_LEVEL_PLANES):
            gt_rels[pl] = f"{gt_dirname}/{pl}__{name}.npy"
            np.save(out.parent / gt_rels[pl],
                    composed.plane_bits[lv].astype(np.uint8))
    else:
        gt_rel = f"{gt_dirname}/{spec.plane}__{name}.npy"
        np.save(out.parent / gt_rel, composed.plane_bits.astype(np.uint8))

    try:
        seed_str = composed.seed.decode()
    except UnicodeDecodeError:
        seed_str = composed.seed.hex()
    h_dots, w_dots = composed.plane_bits.shape[-2:]
    params: dict = {
        "cell_dots": spec.cell_dots,
        "pilot_layout": (f"p{spec.pilot.period_cells}"
                         f"b{spec.pilot.block_cells}"
                         f".v{spec.pilot.version}"
                         + ("-k18" if spec.pilot.version in (3, 4) else "")),
        "page_cells_yx": list(spec.page_cells_yx),
        "encoding_id": spec.encoding_id,
        "page": composed.page,
        # v3/v4 flat-counter geometry (decode-side inversion key)
        **({"counter_tiles_x": spec.word_geometry["tiles_x"],
            "counter_tiles_per_page":
                spec.word_geometry["tiles_per_page"],
            "counter_bits": 18}
           if spec.layout_version in (3, 4) else {}),
        # v4 color furniture (format-axis dust + word rendering)
        **({"emission": "cmyk_image",
            "render_dark": RENDER_DARK,
            "dust_sites_per_tile": spec.dust.sites_per_tile,
            "dust_pure_quota": spec.dust.pure_quota}
           if is_mlc else {}),
    }
    if is_mlc:
        # e004 composite-manifest idiom: one patch entry per plane, tied by
        # composite_of (they share the rect — ONE cmyk image on paper)
        patches = [{
            "name": f"{name}_{pl}",
            "kind": "pilot_compose",
            "planes": [pl],
            "x_dots": spec.x_dots,
            "y_dots": spec.y_dots,
            "w_dots": int(w_dots),
            "h_dots": int(h_dots),
            "params": params,
            "gt": gt_rels[pl],
            "composite_of": name,
        } for pl in _LEVEL_PLANES]
    else:
        patches = [{
            "name": name,
            "kind": "pilot_compose",
            "planes": [spec.plane],
            "x_dots": spec.x_dots,
            "y_dots": spec.y_dots,
            "w_dots": int(w_dots),
            "h_dots": int(h_dots),
            "params": params,
            "gt": gt_rel,
        }]
    manifest: dict = {
        "experiment": experiment,
        "layout_version": spec.layout_version,
        "seed": seed_str,
        "jobid": jobid,
        "hw_dpi": HW_DPI,
        "ps_file": out.name,
        "ps_sha256": sha,
        "ps_bytes": len(ps),
        "print_command": (print_command if print_command is not None else
                          f"../../scripts/print_plane.sh build/{out.name}"),
        "content_bounds_mm": [CONTENT_MARGIN_MM, CONTENT_MARGIN_MM,
                              210.0 - CONTENT_MARGIN_MM, 297.0 - CONTENT_MARGIN_MM],
        "page": composed.page,
        "payload_capacity_bits": composed.payload_capacity_bits,
        "patches": patches,
        "infrastructure": [],
        "labels": [],
    }
    if extra_manifest:
        manifest.update(extra_manifest)
    (out.parent / f"{out.stem}_manifest.json").write_text(
        json.dumps(manifest, indent=1))
    return manifest
