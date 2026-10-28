"""Layer 2a — pilot lattice with the window property (DESIGN.md §5.2, v0.3).

Pilot SITES follow a seed-fixed pattern of modest period so the decoder can enumerate
site-phase hypotheses (the circularity fix in §5.2a). Pilot VALUES must form a 2-D
window-property position code (perfect map / M-array with BCH protection): any clean
window of pilots decodes to absolute (page, x, y).

v1 (PERIOD=64, `pilot_sites`) is the frozen layout_version-1 site pattern — kept
verbatim, including its known PERIOD%BLOCK != 0 bug (2.44% density; CLAUDE.md).
layout_version 2 (p60b6.v2, M1) lives below: exact 1/36 lattice + the
BCH(100,37) coordinate window code (paperholo.bch), per the M1 pilot contract
(engineered per-tile words supersede the classical M-array plan of PILOTS-DESIGN
v0.1; the code parameters deviate from v0.1 §6.2 — see paperholo/bch.py).

layout_version 3 (p60b6.v3-k18, frozen by the v3 migration contract): SAME
site lattice as v2 (the b"pilot-sites-v2" derivation is deliberately shared —
P=60 keeps Stage-0/phase machinery format-independent; do NOT introduce a
pilot-sites-v3 label), but the VALUE layer moves to BCH(127,50,t=13) ->
(100,23), d>=27, carrying an 18-bit flat tile counter + 5 zero pad bits.
No version field, no plane field: format identity = the b"pilot-values-v3"
scramble label, plane identity = the plane-labeled keystream (wrong label ->
coin flips -> BCH reject; implicit-signaling doctrine). The counter needs the
page tile geometry (tiles_x, tiles_per_page), threaded explicitly through
encode_word/decode_word.

layout_version 4 (cmy8 color pages, PILOTS-DESIGN §16): the v3 machinery
verbatim (sites, code, counter, t=13) with the b"pilot-values-v4" scramble
label as the format identity. The v4 word is a LUMA-channel object — its
keystream plane is always "K"; rendering (all-CMY-ink on bit=1) belongs to
the composer, never to this module.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from . import bch
from .modulation import rng

BLOCK = 6      # one pilot per BLOCK x BLOCK cells  (~2.8% density)
PERIOD = 64    # in-block offset pattern repeats every PERIOD cells


def pilot_sites(shape: tuple[int, int], seed: bytes) -> np.ndarray:
    """Boolean mask of pilot cell sites for a plane of `shape` (cells).

    Deterministic in `seed`; periodic with PERIOD in both axes so acquisition can
    hypothesis-test phases without knowing absolute position first.
    """
    h = hashlib.blake2b(seed + b"pilot-sites", digest_size=16).digest()
    gen = np.random.Generator(np.random.Philox(key=int.from_bytes(h, "little")))
    nby, nbx = PERIOD // BLOCK, PERIOD // BLOCK
    off = gen.integers(0, BLOCK, size=(nby, nbx, 2))  # per-block (dy, dx), one pilot tile
    mask = np.zeros(shape, dtype=bool)
    for by in range(nby):
        for bx in range(nbx):
            dy, dx = off[by, bx]
            mask[by * BLOCK + dy :: PERIOD, bx * BLOCK + dx :: PERIOD] = True
    return mask


# ---------------------------------------------------------------------------
# layout_version 2 — p60b6.v2 pilot lattice + BCH(100,37) window code (M1).
# Format-axis constants FROZEN by the M1 pilot contract. New derivation labels;
# the v1 pattern above is never touched (LAYERS.md format-axis rule).
# ---------------------------------------------------------------------------

PILOT_SITES_LABEL_V2: bytes = b"pilot-sites-v2"
PILOT_VALUES_LABEL_V2: bytes = b"pilot-values-v2"
# layout_version 3 shares the v2 SITE derivation (contract: no pilot-sites-v3);
# only the value scramble label changes — it alone identifies the format.
PILOT_VALUES_LABEL_V3: bytes = b"pilot-values-v3"
# layout_version 4 (cmy8 color pages, PILOTS-DESIGN §16 / COLOR-DESIGN D3):
# same sites (frozen b"pilot-sites-v2" contract), same v3 word code + counter;
# the v4 value-scramble label alone is the format identity. The v4 word is a
# LUMA-channel object: its keystream plane is ALWAYS "K" (rendering = all
# three CMY planes ink on bit=1, all white on bit=0 — compose's job).
PILOT_VALUES_LABEL_V4: bytes = b"pilot-values-v4"
_VALUE_LABELS: dict[int, bytes] = {2: PILOT_VALUES_LABEL_V2,
                                   3: PILOT_VALUES_LABEL_V3,
                                   4: PILOT_VALUES_LABEL_V4}

# plane_id word-field constant. Distinct from the payload-keystream plane index
# "CMYK".index(plane) (K=3 there) — both conventions coexist; the word field is
# frozen here, the keystream index belongs to encodings/modulation.
PLANE_ID: dict[str, int] = {"K": 0, "C": 1, "M": 2, "Y": 3}

_LAYOUT_VERSION_BITS = 4
_PLANE_BITS = 2
_PAGE_BITS = 18
_PTILE_BITS = 6
_MESSAGE_BITS = 36  # + 1 zero pad bit = bch.K_SHORT

# layout_version-3 message layout (frozen): [flat counter c: 18 bits MSB-first]
# [5 zero pad bits] = bch.K_SHORT_V3 = 23 bits; c = page * tiles_per_page +
# ptile_y * tiles_x + ptile_x. All 5 pads must be zero at decode.
V3_COUNTER_BITS = 18
V3_PAD_BITS = 5
V3_MESSAGE_BITS = V3_COUNTER_BITS + V3_PAD_BITS  # == bch.K_SHORT_V3
V3_T_ACQ = 13  # single-stage full-strength search (t_acq = t_full = 13)


@dataclass(frozen=True)
class PilotLayout:
    """p60b6.v2: one pilot per block_cells^2 cells at a seeded in-block offset;
    offsets repeat with the period_cells tile (PILOTS-DESIGN §2.1, amended)."""

    period_cells: int = 60
    block_cells: int = 6
    version: int = 2

    def __post_init__(self) -> None:
        if self.period_cells % self.block_cells != 0:
            raise ValueError(
                f"period_cells {self.period_cells} not divisible by "
                f"block_cells {self.block_cells} (the v1 bug this layout fixes)"
            )
        if self.version not in (2, 3, 4):
            raise ValueError(
                f"only layout versions 2, 3 and 4 are defined here, "
                f"got {self.version}")

    @property
    def blocks_per_period(self) -> int:
        return self.period_cells // self.block_cells  # 10 for p60b6

    @property
    def sites_per_tile(self) -> int:
        return self.blocks_per_period ** 2  # 100 = one BCH(100,37) word

    @property
    def density(self) -> float:
        return 1.0 / (self.block_cells ** 2)  # exactly 1/36 for p60b6


def site_positions_tile(layout: PilotLayout, seed: bytes) -> np.ndarray:
    """(sites_per_tile, 2) int (y_cell, x_cell) within ONE pilot tile.

    Site raster order = word bit order: s = by * blocks_per_period + bx over
    the tile's block grid. In-block offsets (dy, dx) from
    rng(seed, PILOT_SITES_LABEL_V2)."""
    nb = layout.blocks_per_period
    off = rng(seed, PILOT_SITES_LABEL_V2).integers(
        0, layout.block_cells, size=(nb, nb, 2)
    )
    by, bx = np.meshgrid(np.arange(nb), np.arange(nb), indexing="ij")
    y_cells = by * layout.block_cells + off[:, :, 0]
    x_cells = bx * layout.block_cells + off[:, :, 1]
    return np.stack([y_cells.ravel(), x_cells.ravel()], axis=1).astype(np.int64)


def pilot_site_mask(
    shape_cells: tuple[int, int], layout: PilotLayout, seed: bytes
) -> np.ndarray:
    """Boolean pilot-site mask for a plane of shape_cells (exact multiples of
    period_cells — v1 scope, no partial tiles)."""
    h_cells, w_cells = shape_cells
    p = layout.period_cells
    if h_cells % p or w_cells % p:
        raise ValueError(
            f"shape_cells {shape_cells} must be exact multiples of period_cells {p}"
        )
    pos = site_positions_tile(layout, seed)
    tile = np.zeros((p, p), dtype=bool)
    tile[pos[:, 0], pos[:, 1]] = True
    return np.tile(tile, (h_cells // p, w_cells // p))


def value_keystream_tile(layout: PilotLayout, seed: bytes, plane: str) -> np.ndarray:
    """ks_P: (sites_per_tile,) uint8 value scrambler, one per (seed, plane).

    Periodic with the tile => removable under ANY site-phase hypothesis
    (fixes the keystream/address circularity, PILOTS-DESIGN §6.3). The label
    dispatches on layout.version (b"pilot-values-v2/-v3/-v4"): from v3 on
    this label IS the format identity (implicit signaling — same literal
    draw form as v2; the dtype kwarg would change the Philox stream, keep
    the form). v4 words are LUMA objects (design D3): plane must be "K"."""
    if plane not in PLANE_ID:
        raise ValueError(f"unknown plane {plane!r}")
    if layout.version == 4 and plane != "K":
        raise ValueError(
            "v4 pilot words are luma-channel objects: the word keystream "
            f"plane is always 'K' (got {plane!r}) — PILOTS-DESIGN §16.2")
    gen = rng(seed, _VALUE_LABELS[layout.version] + b"/" + plane.encode())
    return gen.integers(0, 2, layout.sites_per_tile).astype(np.uint8)


def pack_message(
    plane: str, page: int, ptile_y: int, ptile_x: int, layout_version: int = 2
) -> np.ndarray:
    """(36,) uint8 MSB-first: [layout_version:4][plane_id:2][page:18][ptile_y:6][ptile_x:6]."""
    if plane not in PLANE_ID:
        raise ValueError(f"unknown plane {plane!r}")
    if not 0 <= layout_version < (1 << _LAYOUT_VERSION_BITS):
        raise ValueError(f"layout_version out of range: {layout_version}")
    if not 0 <= page < (1 << _PAGE_BITS):
        raise ValueError(f"page out of range: {page}")
    if not 0 <= ptile_y < (1 << _PTILE_BITS):
        raise ValueError(f"ptile_y out of range: {ptile_y}")
    if not 0 <= ptile_x < (1 << _PTILE_BITS):
        raise ValueError(f"ptile_x out of range: {ptile_x}")
    val = (
        (layout_version << 32)
        | (PLANE_ID[plane] << 30)
        | (page << 12)
        | (ptile_y << 6)
        | ptile_x
    )
    return np.array(
        [(val >> (_MESSAGE_BITS - 1 - i)) & 1 for i in range(_MESSAGE_BITS)],
        dtype=np.uint8,
    )


def unpack_message(bits36: np.ndarray) -> dict:
    """Inverse of pack_message: (36,) bits -> field dict."""
    b = np.asarray(bits36)
    if b.shape != (_MESSAGE_BITS,):
        raise ValueError(f"expected ({_MESSAGE_BITS},) bits, got {b.shape}")
    val = 0
    for i in range(_MESSAGE_BITS):
        val = (val << 1) | int(b[i]) & 1
    return {
        "layout_version": (val >> 32) & 0xF,
        "plane_id": (val >> 30) & 0x3,
        "page": (val >> 12) & 0x3FFFF,
        "ptile_y": (val >> 6) & 0x3F,
        "ptile_x": val & 0x3F,
    }


def code_for_layout(layout: PilotLayout) -> bch.BCHCode:
    """The BCH window-code instance frozen for this layout version."""
    return bch.code_for_version(layout.version)


def t_acq_for_layout(layout: PilotLayout) -> int:
    """Default Stage-A acquisition radius: 8 for v2 (t_full 10), 13 for
    v3/v4 (single-stage full-strength search; k_eff=18 keeps window-search
    FA at ~5e-5, Stage B remains the certifier)."""
    return 8 if layout.version == 2 else V3_T_ACQ


def _check_v3_geometry(tiles_x: int | None, tiles_per_page: int | None
                       ) -> tuple[int, int]:
    if tiles_x is None or tiles_per_page is None:
        raise ValueError(
            "layout version 3 words need the page tile geometry: pass "
            "tiles_x and tiles_per_page (from ComposeSpec.page_cells_yx)")
    tx, tpp = int(tiles_x), int(tiles_per_page)
    if tx <= 0 or tpp <= 0 or tpp % tx != 0:
        raise ValueError(
            f"tiles_per_page {tpp} must be a positive multiple of "
            f"tiles_x {tx}")
    return tx, tpp


def pack_counter(counter: int) -> np.ndarray:
    """(23,) uint8 MSB-first: [flat counter c: 18 bits][5 zero pad bits]."""
    if not 0 <= counter < (1 << V3_COUNTER_BITS):
        raise ValueError(f"counter out of range: {counter}")
    val = counter << V3_PAD_BITS
    return np.array(
        [(val >> (V3_MESSAGE_BITS - 1 - i)) & 1 for i in range(V3_MESSAGE_BITS)],
        dtype=np.uint8,
    )


def unpack_counter(bits23: np.ndarray) -> int | None:
    """Inverse of pack_counter; None if ANY of the 5 pad bits is nonzero
    (the pad check is a decode-side reject gate, 2^-5 extra FA margin)."""
    b = np.asarray(bits23)
    if b.shape != (V3_MESSAGE_BITS,):
        raise ValueError(f"expected ({V3_MESSAGE_BITS},) bits, got {b.shape}")
    val = 0
    for i in range(V3_MESSAGE_BITS):
        val = (val << 1) | int(b[i]) & 1
    if val & ((1 << V3_PAD_BITS) - 1):
        return None
    return val >> V3_PAD_BITS


def counter_from_address(page: int, ptile_y: int, ptile_x: int, *,
                         tiles_x: int, tiles_per_page: int) -> int:
    """c = page * tiles_per_page + ptile_y * tiles_x + ptile_x, range-checked
    against 2^18 (page cap = (2^18 - 1) // tiles_per_page)."""
    tx_n, tpp = _check_v3_geometry(tiles_x, tiles_per_page)
    tiles_y = tpp // tx_n
    if not 0 <= ptile_x < tx_n:
        raise ValueError(f"ptile_x out of range: {ptile_x}")
    if not 0 <= ptile_y < tiles_y:
        raise ValueError(f"ptile_y out of range: {ptile_y}")
    if page < 0:
        raise ValueError(f"page out of range: {page}")
    c = page * tpp + ptile_y * tx_n + ptile_x
    if c >= (1 << V3_COUNTER_BITS):
        raise ValueError(
            f"counter {c} >= 2^18: page {page} exceeds the page cap "
            f"{((1 << V3_COUNTER_BITS) - 1) // tpp} for {tpp}-tile pages")
    return c


def address_from_counter(counter: int, *, tiles_x: int,
                         tiles_per_page: int) -> tuple[int, int, int]:
    """counter -> (page, ptile_y, ptile_x) given the page tile geometry."""
    tx_n, tpp = _check_v3_geometry(tiles_x, tiles_per_page)
    if not 0 <= counter < (1 << V3_COUNTER_BITS):
        raise ValueError(f"counter out of range: {counter}")
    page, rem = divmod(int(counter), tpp)
    ty, tx = divmod(rem, tx_n)
    return page, ty, tx


def encode_word(
    layout: PilotLayout,
    seed: bytes,
    plane: str,
    page: int,
    ptile_y: int,
    ptile_x: int,
    *,
    tiles_x: int | None = None,
    tiles_per_page: int | None = None,
) -> np.ndarray:
    """(100,) uint8 scrambled pilot values for one pilot tile.

    v(s) = codeword_bit_s XOR ks_P[s]. Dispatches on layout.version:
    v2 message = 36 packed bits + 1 zero pad bit at systematic index 36
    (tiles_x/tiles_per_page ignored); v3/v4 message = 18-bit flat counter +
    5 zero pads, REQUIRES tiles_x/tiles_per_page (Stage-B neighbor
    prediction follows from the counter arithmetic: right neighbor = c+1
    unless ptile_x == tiles_x - 1, below = c + tiles_x). v4 words take
    plane "K" only (luma object)."""
    if layout.version == 2:
        msg36 = pack_message(plane, page, ptile_y, ptile_x,
                             layout_version=layout.version)
        msg37 = np.concatenate([msg36, np.zeros(1, dtype=np.uint8)])
        codeword = bch.encode(msg37)
        return np.bitwise_xor(codeword, value_keystream_tile(layout, seed, plane))
    c = counter_from_address(page, ptile_y, ptile_x,
                             tiles_x=tiles_x, tiles_per_page=tiles_per_page)
    codeword = bch.CODE_V3.encode(pack_counter(c))
    return np.bitwise_xor(codeword, value_keystream_tile(layout, seed, plane))


# decode-side regeneration alias (single implementation — Stage B calls this).
expected_word_bits = encode_word


def decode_word(
    bits100: np.ndarray,
    layout: PilotLayout,
    seed: bytes,
    plane: str,
    max_errors: int,
    *,
    tiles_x: int | None = None,
    tiles_per_page: int | None = None,
    erasures: np.ndarray | None = None,
) -> dict | None:
    """Descramble ks_P + BCH-decode one tile word.

    Returns the unpacked message dict plus "n_errors", or None on any failure.
    v2: BCH reject, nonzero pad bit, layout_version != layout.version, or a
    plane_id inconsistent with the ks_P plane hypothesis (free consistency
    gates on top of the contract's layout_version check).
    v3/v4 (REQUIRES tiles_x/tiles_per_page): BCH reject or ANY nonzero pad
    bit; there is no version/plane field — a wrong plane/format hypothesis
    picks the wrong keystream and the word is coin flips to the BCH gate
    (v4's identity is its value label alone: C_v4 == C_v3 as codes). The dict
    carries page/ptile_y/ptile_x inverted from the flat "counter" (also
    returned) via the page geometry."""
    b = np.asarray(bits100).astype(np.uint8)
    if b.shape != (bch.N_SHORT,):
        raise ValueError(f"expected ({bch.N_SHORT},) bits, got {b.shape}")
    descrambled = np.bitwise_xor(b, value_keystream_tile(layout, seed, plane))
    n_era = 0 if erasures is None else int(np.asarray(erasures).size)

    def _dec(code: "bch.BCHCode") -> tuple[np.ndarray, int] | None:
        # erasures = site indices with UNKNOWN values (partial pilot tile);
        # the XOR descramble is positionwise, so indices carry over. Known-
        # position decoding only — Stage-A search must stay errors-only
        # until the §6.4 FA budget covers reduced-support words.
        if erasures is None:
            return code.decode(descrambled, max_errors)
        return code.decode_erasures(descrambled, erasures, max_errors)

    if layout.version == 2:
        res = _dec(bch.CODE_V2)
        if res is None:
            return None
        corrected, n_errors = res
        msg37 = bch.message_from_word(corrected)
        if msg37[_MESSAGE_BITS] != 0:  # pad bit
            return None
        info = unpack_message(msg37[:_MESSAGE_BITS])
        if info["layout_version"] != layout.version:
            return None
        if info["plane_id"] != PLANE_ID[plane]:
            return None
        info["n_errors"] = int(n_errors)
        info["n_erasures"] = n_era
        return info
    tx_n, tpp = _check_v3_geometry(tiles_x, tiles_per_page)
    res = _dec(bch.CODE_V3)
    if res is None:
        return None
    corrected, n_errors = res
    counter = unpack_counter(bch.CODE_V3.message_from_word(corrected))
    if counter is None:  # nonzero pad bits: reject
        return None
    page, ty, tx = address_from_counter(counter, tiles_x=tx_n,
                                        tiles_per_page=tpp)
    return {"counter": int(counter), "page": page, "ptile_y": ty,
            "ptile_x": tx, "n_errors": int(n_errors), "n_erasures": n_era}


def coordinate_code(
    layout: PilotLayout,
    seed: bytes,
    plane: str,
    page: int,
    ptile_y: int,
    ptile_x: int,
    *,
    tiles_x: int | None = None,
    tiles_per_page: int | None = None,
) -> np.ndarray:
    """Window-property position code for one pilot tile (DESIGN.md §5.2a).

    Thin wrapper over encode_word — keeps the LAYERS.md porting-map seam name."""
    return encode_word(layout, seed, plane, page, ptile_y, ptile_x,
                       tiles_x=tiles_x, tiles_per_page=tiles_per_page)
