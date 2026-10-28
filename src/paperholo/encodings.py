"""Encoding registry + 2-D bitstream page emitter — the L1-encode / L0-emit seam.

This module is the lowest-layer OUTPUT tool of the retrieval stack: it turns a
2-D symbol array (or, for the free-form RLL entry, a seed) into (a) per-plane
dot-resolution PlaneBitmaps and (b) a raw PostScript page emitted through
paperholo.psgen, together with a manifest (sha-gated) and ground-truth arrays.
The registry rows carry the measured record of docs/LAYERS.md §3 so the CLI can
answer "what encodings exist, at what measured rate, with what requirements"
without opening the experiment logs.

ARCHITECTURE (single binary vs multi-layer — answered): LIBRARY-LAYERED with
thin CLIs. This module owns the L1-encode + L0-emit seam ONLY: payload field(s)
plus a minimal page skeleton (optional header line, optional END sentinel;
corner marks / registration furniture are OFF — no fiducials here). Pilot
lattices, sync strips, training bands and tile furniture are FORMAT-axis
furniture that belongs to the next layer up (the L2 page composer), which calls
this module's Python API in-process — `encode_field()` / `generate_rll_field()`
return EncodedField objects and `emit_page()` places any number of them, so the
composer composes fields + furniture on one page without ever shelling out.
The CLI here is a thin wrapper for bench use, not a component boundary.

FORMAT DEFINITION — symbol-domain scramble (format axis, LAYOUT_VERSION 1).
Every data-bearing encoding is scrambled before printing (DC balance +
whiteness, DESIGN.md §4.2); the scramble is part of the printed format and is
deterministic + reversible from (seed, encoding_id, page, shape) alone:

- binary encodings (n_states == 2, single plane P):
      printed = payload XOR modulation.keystream(seed, plane_index(P), page)
  with plane_index = the plane's index in "CMYK" (K = 3). Since
  (a + k) mod 2 == a XOR k, this is the n=2 specialization of the rule below,
  keyed exactly like the existing §4 keystream convention.
- alphabet encodings (n_states = n > 2):
      printed = (payload + U) mod n
      U = modulation.rng(seed, b"symks/" + encoding_id + b"/pg" + page_le32)
              .integers(0, n)            # page_le32 = page.to_bytes(4,"little")
  Descramble: payload = (printed - U) mod n.
- rll-i2w3 (free-form, NOT data-bearing): there is no payload. The field is a
  constraint-valid sample drawn from
      modulation.rng(seed, b"rll/" + encoding_id + b"/pg" + page_le32)
  via the exp-003 row-DP sampler. A data-bearing bit -> constrained-field
  mapping is NOT IMPLEMENTED (no measured encoder exists; trellis/motif
  mapping is a bounded-upside open item, 004.0a) — the API and CLI refuse
  symbols for this encoding and take a seed instead.

Any change to the rules above (or to a registry row's printed geometry) is a
layout_version bump, never a hotfix (LAYERS.md §0: printed sheets are
immutable).

Emission discipline (Layer-0 freeze, 002.0-003.0): clean_mask encodings emit
single-plane `imagemask` (bit-faithful on both measured engines); composite
encodings emit ONE `put_cmyk_bitmap` DeviceCMYK image (M281 re-screens it
~165 lpi ALWAYS — the screen is part of that channel; AltaLink honors overlap
unscreened). Stream order on a page: labels, all imagemasks, all composites,
END sentinel last (002.2/003.0 idiom). Mask and composite regions must keep
>= 1.5 mm clearance (002.2 measured coexistence condition) — enforced here.

CLI:
  python -m paperholo.encodings --list
  python -m paperholo.encodings --info <id> [--field-mm WxH]
  python -m paperholo.encodings --emit <id> --symbols <npy> --out <ps>
                                [--seed-label S] [--page N] [--header TEXT]
                                [--x-mm X --y-mm Y] [--end-sentinel]
  python -m paperholo.encodings --emit rll-i2w3 --field-mm WxH --out <ps> ...
                                (seed-driven; --symbols is refused)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path

import numpy as np

from .modulation import cells_to_dots, keystream, rng
from .psgen import A4_PT, CMYK, PSDoc

MM_PER_INCH = 25.4
HW_DPI_DEFAULT = 600
LAYOUT_VERSION = 1
# Measured printable-margin bound, BOTH engines (disc1 probes: margins <= 4 mm;
# CAL-1's <= 7.4 was never probed lower). Fields must stay inside this.
MARGIN_MM = 4.0
# Measured mask/composite coexistence clearance (002.2 region-disjointness).
CROSS_PATH_GAP_MM = 1.5
_ROW_DP_MAX_W = 900  # gen_modprobe row-DP float-count cap (counts < 2**w)


class EncodingError(ValueError):
    """Invalid symbols or misuse of an encoding (shape, alphabet, constraint)."""


def mm_to_dots(v_mm: float, hw_dpi: int = HW_DPI_DEFAULT) -> int:
    return round(v_mm / MM_PER_INCH * hw_dpi)


def _plane_index(plane: str) -> int:
    return "CMYK".index(plane)


def _page_label(prefix: bytes, encoding_id: str, page: int) -> bytes:
    return prefix + b"/" + encoding_id.encode() + b"/pg" + page.to_bytes(4, "little")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RLLConstraint:
    min_ink_run_dots: int
    min_white_run_dots: int

    def describe(self) -> str:
        return (f"2-D run-length limits, BOTH axes, border runs included: every"
                f" maximal ink run >= {self.min_ink_run_dots} dots, every"
                f" maximal white run >= {self.min_white_run_dots} dots")


@dataclass(frozen=True)
class Encoding:
    """One format-axis constellation row (LAYERS.md §3 contract subset)."""

    encoding_id: str
    kind: str                       # cell_binary | cell_alphabet | freeform_rll
    planes: tuple[str, ...]
    emission: str                   # "clean_mask" | "composite"
    emission_note: str
    scan_mode: str                  # scan-mode requirement (measured)
    sync_note: str                  # sync class needed (LAYERS.md §8)
    record: str                     # one-line measured-record pointer (§3 rows)
    cell_dots: int | None = None    # None for free-form
    state_names: tuple[str, ...] | None = None
    constraint: RLLConstraint | None = None

    @property
    def data_bearing(self) -> bool:
        return self.kind != "freeform_rll"

    @property
    def n_states(self) -> int | None:
        return len(self.state_names) if self.state_names is not None else None

    @property
    def entropy_bits_per_cell(self) -> float | None:
        """Raw alphabet entropy per cell; None for free-form (b/dot is
        field-dependent — the sampler measures it into the emit manifest)."""
        return math.log2(self.n_states) if self.data_bearing else None

    def cells_per_mm2(self, hw_dpi: int = HW_DPI_DEFAULT) -> float | None:
        if self.cell_dots is None:
            return None
        return (hw_dpi / MM_PER_INCH / self.cell_dots) ** 2

    def dots_per_mm2(self, hw_dpi: int = HW_DPI_DEFAULT) -> float:
        return (hw_dpi / MM_PER_INCH) ** 2


_B_STATES = ("W", "K")
_A3_STATES = ("W", "C", "M", "Y", "CM", "CY", "MY")   # 002.0c winning alphabet
_A4_STATES = _A3_STATES + ("K",)                       # {7+K}, mixtures excluded

_GREY_SCAN = ("grey 1200 dpi, uncompressed (grey beats color ~1 pp at c2, "
              "004.0b; JPEG scan paths erase <5-dot features and break the "
              "context detector, 007.2)")
_COLOR_SCAN = ("color 1200 dpi, uncompressed (color REQUIRED; modes are "
               "separate transport passes - never mix within one combine)")
_CLEAN_NOTE = "single-plane K imagemask - bit-faithful on both measured engines"
_COMP_NOTE = ("put_cmyk_bitmap DeviceCMYK image - M281 re-screens ~165 lpi "
              "ALWAYS (Layer-0 freeze, no PS escape); AltaLink honors overlap "
              "unscreened (007.6)")

_ALL_ENCODINGS: tuple[Encoding, ...] = (
    Encoding(
        encoding_id="kcell-c2", kind="cell_binary", planes=("K",),
        emission="clean_mask", emission_note=_CLEAN_NOTE, scan_mode=_GREY_SCAN,
        sync_note=("strips required (marks-affine +/-2 dots insufficient at "
                   "c2); between-strip refinement engine-conditional (007.7); "
                   "pilots supersede at M1"),
        record=("B1 row: AltaLink ctx 5.48% recal 0.760 b/cell = 106.1 b/mm2 "
                "genie (007.6); home day-1 109 (003.0a); multi-sheet 93-109 "
                "genie / 68-95 legal; day-FRAGILE on M281 (white-cell "
                "closure, 004.0); c2 = the channel canary"),
        cell_dots=2, state_names=_B_STATES),
    Encoding(
        encoding_id="kcell-c3", kind="cell_binary", planes=("K",),
        emission="clean_mask", emission_note=_CLEAN_NOTE, scan_mode=_GREY_SCAN,
        sync_note=("strips or marks + local refinement; payload self-clock "
                   "viable on interior tiles (dd_warp, 004.0a)"),
        record=("K ladder anchor: c3 2.5-3.7% raw hard BER cross-engine "
                "(001/007.1/007.6); best-sheet 2.0-2.2% (001.4); simulator "
                "reference ~3.6% (M0 fidelity anchor)"),
        cell_dots=3, state_names=_B_STATES),
    Encoding(
        encoding_id="kcell-c4", kind="cell_binary", planes=("K",),
        emission="clean_mask", emission_note=_CLEAN_NOTE, scan_mode=_GREY_SCAN,
        sync_note=("strips or marks + local refinement; payload self-clock "
                   "viable on interior tiles (dd_warp, 004.0a)"),
        record=("K ladder: c4 robust on both engines (001, 007.1 DISC-1 blind "
                "rediscovery); B-track robust anchor - no standalone MI row "
                "in LAYERS.md §3"),
        cell_dots=4, state_names=_B_STATES),
    Encoding(
        encoding_id="a3-7st-c3", kind="cell_alphabet", planes=("C", "M", "Y"),
        emission="composite", emission_note=_COMP_NOTE, scan_mode=_COLOR_SCAN,
        sync_note=("strips are K-plane - transfer needs per-plane offset "
                   "solving; M281 self-clock BROKEN (165 lpi screen, 004.0a); "
                   "per-plane pilots by design (DESIGN §5.4); receiver = "
                   "furniture-QDA (~2% training bands = genie parity, 006.2), "
                   "NO EM from stale priors"),
        record=("A3 row: AltaLink cross-tile 2.150 b/cell = 133.3 b/mm2 "
                "RECORD (007.6); home 1.896 = 117.6 (004.0); multi-sheet "
                "92-133; Y-entangled (starved-Y 47.7, 006.2)"),
        cell_dots=3, state_names=_A3_STATES),
    Encoding(
        encoding_id="a4-8st-c4", kind="cell_alphabet",
        planes=("C", "M", "Y", "K"),
        emission="composite", emission_note=_COMP_NOTE, scan_mode=_COLOR_SCAN,
        sync_note=("strips are K-plane - transfer needs per-plane offset "
                   "solving; per-plane pilots by design (DESIGN §5.4); "
                   "receiver = furniture-QDA, NO EM from stale priors"),
        record=("A4 row: AltaLink cross-page 2.685 b/cell = 93.6 b/mm2 "
                "(007.6); home 2.458 = 85.7 (004.0); multi-sheet ~69-98; "
                "AltaLink K<->CM confusion 9-10%"),
        cell_dots=4, state_names=_A4_STATES),
    Encoding(
        # cmy8-c3 (layout_version 4, COLOR-DESIGN D1): NOT an alphabet row —
        # three independent binary LEVELS per cell (one presence bit per
        # plane, PID-MLC per D2), composed by paperholo.compose with
        # per-level plane keystreams. The symbol-domain mod-8 scramble does
        # NOT apply (see key_symbols guard); state_names order = the state
        # integer s with bit l = level l ink (C + 2M + 4Y).
        encoding_id="cmy8-c3", kind="cell_mlc", planes=("C", "M", "Y"),
        emission="composite", emission_note=_COMP_NOTE, scan_mode=_COLOR_SCAN,
        sync_note=("p60b6 v4 pilots, LUMA word channel (all-CMY dark marks) "
                   "+ tile-periodic training dust for the 8-class detector, "
                   "per-plane registration and PAVA labels (PILOTS-DESIGN "
                   "§16); receiver = dust-QDA, NO EM"),
        record=("8-state composite c3: AltaLink MI 2.208 (007.6), home 1.76 "
                "(002.0c: best-7 beats best-8 by 0.09 b/cell — priced into "
                "the per-level rungs, D1); A3-class fields 112-133 b/mm2 "
                "raw across engines; coded net = ESTIMATE 45-110 b/mm2 "
                "(COLOR-DESIGN §3, P5 refines)"),
        cell_dots=3,
        state_names=("W", "C", "M", "CM", "Y", "CY", "MY", "CMY")),
    Encoding(
        encoding_id="rll-i2w3", kind="freeform_rll", planes=("K",),
        emission="clean_mask", emission_note=_CLEAN_NOTE,
        scan_mode=("grey 1200 dpi, uncompressed; >= 2 px/dot sampling floor "
                   "(dot lattice at scan Nyquist)"),
        sync_note=("strips or pilots REQUIRED - payload self-clock IMPOSSIBLE "
                   "at 2 px/dot (004.0a)"),
        record=("B2 row: 0.167 b/dot = 93.3 b/mm2 best (004.0b 4-scan); "
                "82-86 b/mm2 CROSS-ENGINE band = the rate-ladder anchor "
                "(007.6); trellis gain ~zero (004.0a), motif-emission upside "
                "bounded ~98"),
        constraint=RLLConstraint(min_ink_run_dots=2, min_white_run_dots=3)),
)

ENCODINGS: dict[str, Encoding] = {e.encoding_id: e for e in _ALL_ENCODINGS}

_RLL_NOT_DATA_BEARING = (
    "is not data-bearing: a bit -> constrained-field mapping is NOT "
    "IMPLEMENTED (no measured encoder exists; trellis/motif mapping is a "
    "bounded-upside open item, 004.0a). Emit takes a SEED, not symbols: use "
    "generate_rll_field() / --field-mm, which draws a constraint-VALID field "
    "deterministically from the seed.")


def get_encoding(encoding_id: str) -> Encoding:
    try:
        return ENCODINGS[encoding_id]
    except KeyError:
        raise EncodingError(
            f"unknown encoding {encoding_id!r}; available: "
            + ", ".join(ENCODINGS)) from None


def field_dims(enc: Encoding, width_mm: float, height_mm: float,
               hw_dpi: int = HW_DPI_DEFAULT) -> dict:
    """Dims math for a WxH mm field: dots always; cells + raw entropy for
    cell-mapped encodings (free-form b/dot is sampler-measured per field)."""
    w_dots, h_dots = mm_to_dots(width_mm, hw_dpi), mm_to_dots(height_mm, hw_dpi)
    d: dict = {"w_dots": w_dots, "h_dots": h_dots, "n_dots": w_dots * h_dots}
    if enc.cell_dots is not None:
        nx, ny = w_dots // enc.cell_dots, h_dots // enc.cell_dots
        d.update(cells_x=nx, cells_y=ny, n_cells=nx * ny,
                 raw_entropy_bits=nx * ny * (enc.entropy_bits_per_cell or 0.0))
    return d


# ---------------------------------------------------------------------------
# Scramble (format axis — see module docstring) and symbol validation
# ---------------------------------------------------------------------------

_MLC_USE_COMPOSE = (
    "is a multi-level (per-plane binary) encoding: its printed format is "
    "three per-LEVEL plane keystreams composed with v4 pilots + training "
    "dust by paperholo.compose.compose_page — the symbol-domain scramble "
    "and this emitter do NOT apply (a mod-8 symbol scramble would be a "
    "DIFFERENT printed format). Use the L2 composer / gen_e017.")


def key_symbols(enc: Encoding, shape: tuple[int, int], seed: bytes,
                page: int = 0) -> np.ndarray:
    """Keystream-derived symbol array over [0, n_states) — the scramble key.
    Binary encodings use modulation.keystream verbatim (§4 convention)."""
    if enc.kind == "cell_mlc":
        raise EncodingError(f"{enc.encoding_id} {_MLC_USE_COMPOSE}")
    n = enc.n_states
    if n is None:
        raise EncodingError(f"{enc.encoding_id} {_RLL_NOT_DATA_BEARING}")
    if n == 2:
        return keystream(seed, _plane_index(enc.planes[0]), page, shape)
    g = rng(seed, _page_label(b"symks", enc.encoding_id, page))
    return g.integers(0, n, size=shape, dtype=np.uint8)


def validate_symbols(enc: Encoding, symbols: np.ndarray) -> None:
    if enc.kind == "cell_mlc":
        raise EncodingError(f"{enc.encoding_id} {_MLC_USE_COMPOSE}")
    if not enc.data_bearing:
        raise EncodingError(f"{enc.encoding_id} {_RLL_NOT_DATA_BEARING}")
    if not isinstance(symbols, np.ndarray) or symbols.ndim != 2:
        raise EncodingError(
            f"{enc.encoding_id}: symbols must be a 2-D numpy array, got "
            + (f"shape {symbols.shape}" if isinstance(symbols, np.ndarray)
               else type(symbols).__name__))
    if symbols.size == 0:
        raise EncodingError(f"{enc.encoding_id}: empty symbol array")
    if not np.issubdtype(symbols.dtype, np.integer):
        raise EncodingError(
            f"{enc.encoding_id}: symbols must be integer-typed, got "
            f"{symbols.dtype}")
    lo, hi = int(symbols.min()), int(symbols.max())
    if lo < 0 or hi >= enc.n_states:
        raise EncodingError(
            f"{enc.encoding_id}: symbols outside alphabet range "
            f"[0, {enc.n_states}): got [{lo}, {hi}]")


def scramble_symbols(enc: Encoding, payload: np.ndarray, seed: bytes,
                     page: int = 0) -> np.ndarray:
    """printed = (payload + key) mod n_states (== XOR for binary)."""
    validate_symbols(enc, payload)
    ks = key_symbols(enc, payload.shape, seed, page)
    return ((payload.astype(np.int16) + ks) % enc.n_states).astype(np.uint8)


def descramble_symbols(enc: Encoding, printed: np.ndarray, seed: bytes,
                       page: int = 0) -> np.ndarray:
    """payload = (printed - key) mod n_states. Inverse of scramble_symbols."""
    validate_symbols(enc, printed)
    ks = key_symbols(enc, printed.shape, seed, page)
    return ((printed.astype(np.int16) - ks) % enc.n_states).astype(np.uint8)


def symbols_to_planes(enc: Encoding, printed_symbols: np.ndarray
                      ) -> dict[str, np.ndarray]:
    """Cell states -> per-plane dot bitmaps (1 = ink), solid cells."""
    assert enc.state_names is not None and enc.cell_dots is not None
    planes: dict[str, np.ndarray] = {}
    for p in enc.planes:
        member = np.array([int(p in s) for s in enc.state_names], np.uint8)
        planes[p] = cells_to_dots(member[printed_symbols], enc.cell_dots)
    return planes


# ---------------------------------------------------------------------------
# Encoded fields
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EncodedField:
    """One encoded payload region: per-plane dot bitmaps + provenance.
    This is the composition currency: the L2 composer places several of these
    (plus furniture) on one page via emit_page()."""

    encoding: Encoding
    plane_bits: dict[str, np.ndarray]     # dot grid, uint8, 1 = ink
    seed: bytes
    page: int
    payload_symbols: np.ndarray | None = None   # pre-scramble (None for rll)
    printed_symbols: np.ndarray | None = None   # post-scramble cell states
    stats: dict = dc_field(default_factory=dict)

    @property
    def shape_dots(self) -> tuple[int, int]:
        return next(iter(self.plane_bits.values())).shape


def encode_field(enc: Encoding | str, payload_symbols: np.ndarray, seed: bytes,
                 page: int = 0) -> EncodedField:
    """Validate + scramble a payload symbol array and map it to PlaneBitmaps.
    Raises EncodingError for free-form encodings (see module docstring)."""
    if isinstance(enc, str):
        enc = get_encoding(enc)
    printed = scramble_symbols(enc, payload_symbols, seed, page)
    return EncodedField(
        encoding=enc, plane_bits=symbols_to_planes(enc, printed), seed=seed,
        page=page, payload_symbols=payload_symbols.astype(np.uint8),
        printed_symbols=printed)


# -- free-form 2-D RLL sampler ------------------------------------------------
# Port of experiments/003-modulation-probes/gen_modprobe.py `_sample_row` /
# `assert_run_lengths` and the exp-004/006 rectangular + transpose wrapper
# (pure functions, validated in 003.0/004.0/006.1; seeded by the caller here).

def _sample_row(prev_forced: np.ndarray, min_white: int, min_ink: int,
                gen: np.random.Generator) -> tuple[np.ndarray, float]:
    """One row, uniform over {rows whose maximal runs satisfy white>=min_white,
    ink>=min_ink (border runs included) AND matching the forced positions}.

    forced[i] in {-1 free, 0 white, 1 ink}. Returns (bits, log2 #valid rows).
    Completion counts stay < 2**w <= float max for w <= 900 (no rescaling).
    """
    w = int(prev_forced.size)
    assert w <= _ROW_DP_MAX_W, "row DP float counts would overflow"
    nw, ni = min_white, min_ink
    ns = nw + ni
    cont = [min(r + 1, nw) - 1 for r in range(1, nw + 1)] + \
           [nw + min(r + 1, ni) - 1 for r in range(1, ni + 1)]
    wcap, icap = nw - 1, ns - 1
    forced = prev_forced.tolist()
    N: list[list[float]] = [[0.0] * ns for _ in range(w + 1)]
    N[w][wcap] = 1.0
    N[w][icap] = 1.0
    for i in range(w - 1, 0, -1):
        prev = N[i + 1]
        f = forced[i]
        if f < 0:
            cur = [prev[cont[k]] for k in range(ns)]
            cur[wcap] += prev[nw]   # white cap may flip to ink run 1
            cur[icap] += prev[0]    # ink cap may flip to white run 1
        elif f == 0:
            cur = [prev[cont[k]] if k < nw else 0.0 for k in range(ns)]
            cur[icap] = prev[0]
        else:
            cur = [prev[cont[k]] if k >= nw else 0.0 for k in range(ns)]
            cur[wcap] = prev[nw]
        N[i] = cur
    w_white = N[1][0] if forced[0] in (-1, 0) else 0.0
    w_ink = N[1][nw] if forced[0] in (-1, 1) else 0.0
    total = w_white + w_ink
    assert total > 0.0, "row DP dead end (copy-previous-row invariant violated)"
    bits = np.zeros(w, dtype=np.uint8)
    if w_white > 0.0 and w_ink > 0.0:
        b = 1 if gen.random() * total < w_ink else 0
    else:
        b = 1 if w_ink > 0.0 else 0
    bits[0] = b
    state = nw if b else 0
    for i in range(1, w):
        prev = N[i + 1]
        f = forced[i]
        c = 1 if state >= nw else 0
        w_cont = prev[cont[state]] if f in (-1, c) else 0.0
        w_flip = 0.0
        if f in (-1, 1 - c):
            if state == wcap:
                w_flip = prev[nw]
            elif state == icap:
                w_flip = prev[0]
        if w_cont > 0.0 and w_flip > 0.0:
            flip = gen.random() * (w_cont + w_flip) < w_flip
        else:
            flip = w_flip > 0.0
        if flip:
            state = 0 if c else nw
            bits[i] = 1 - c
        else:
            state = cont[state]
            bits[i] = c
    return bits, math.log2(total)


def assert_run_lengths(a: np.ndarray, min_ink: int, min_white: int) -> None:
    """Every maximal run in every row AND column (borders included) obeys
    ink >= min_ink, white >= min_white."""
    for axis_name, b in (("rows", a), ("cols", a.T)):
        for i, line in enumerate(b):
            change = np.flatnonzero(np.diff(line.astype(np.int8))) + 1
            starts = np.concatenate(([0], change))
            ends = np.concatenate((change, [line.size]))
            vals, lens = line[starts], ends - starts
            bad_i = lens[vals == 1] < min_ink
            bad_w = lens[vals == 0] < min_white
            assert not bad_i.any() and not bad_w.any(), \
                f"run-length violation in {axis_name}[{i}]"


def _constrained_field_rect(h_dots: int, w_dots: int, min_ink: int,
                            min_white: int, gen: np.random.Generator
                            ) -> tuple[np.ndarray, dict]:
    """Rectangular 2-D RLL field. Fields wider than the DP's 900-dot row cap
    are sampled transposed (rows along the short axis) — the constraint set is
    symmetric, so a transposed sample is a valid field (exp-006 idiom)."""
    if min(h_dots, w_dots) < min_ink + min_white:
        raise EncodingError(
            f"rll field {h_dots}x{w_dots} dots too small for the constraint "
            f"(need >= {min_ink + min_white} dots on the short axis)")
    transposed = w_dots > _ROW_DP_MAX_W
    ny, nx = (w_dots, h_dots) if transposed else (h_dots, w_dots)
    if nx > _ROW_DP_MAX_W:
        raise EncodingError(
            f"rll field {h_dots}x{w_dots} dots: both axes exceed the row-DP "
            f"cap ({_ROW_DP_MAX_W} dots) — band the field at the composer "
            "level")
    minr = np.array([min_white, min_ink], dtype=np.int64)
    a = np.zeros((ny, nx), dtype=np.uint8)
    col_color = np.zeros(nx, dtype=np.int64)
    col_run = np.zeros(nx, dtype=np.int64)
    log2_total = 0.0
    for y in range(ny):
        if y == 0:
            forced = np.full(nx, -1, dtype=np.int64)
        else:
            must_cont = (col_run < minr[col_color]) | \
                        (ny - y < minr[1 - col_color])
            forced = np.where(must_cont, col_color, -1)
        bits, l2 = _sample_row(forced, min_white, min_ink, gen)
        log2_total += l2
        a[y] = bits
        if y == 0:
            col_color = bits.astype(np.int64)
            col_run = np.ones(nx, dtype=np.int64)
        else:
            same = bits.astype(np.int64) == col_color
            col_run = np.where(same, col_run + 1, 1)
            col_color = bits.astype(np.int64)
    if transposed:
        a = np.ascontiguousarray(a.T)
    assert_run_lengths(a, min_ink, min_white)
    stats = {
        "min_ink_run_dots": min_ink,
        "min_white_run_dots": min_white,
        "sampler": "exp-003 row-DP (rectangular wrapper"
                   + (", transposed" if transposed else "") + ")",
        "sampler_entropy_bits_per_dot": round(log2_total / (h_dots * w_dots), 6),
        "ink_fraction": round(float(a.mean()), 6),
    }
    return a, stats


def generate_rll_field(enc: Encoding | str, h_dots: int, w_dots: int,
                       seed: bytes, page: int = 0) -> EncodedField:
    """Draw a constraint-VALID free-form field deterministically from the
    seed. This is NOT a data encoder (see module docstring / registry)."""
    if isinstance(enc, str):
        enc = get_encoding(enc)
    if enc.kind != "freeform_rll":
        raise EncodingError(
            f"{enc.encoding_id} is cell-mapped and data-bearing: use "
            "encode_field() with a symbol array")
    assert enc.constraint is not None
    gen = rng(seed, _page_label(b"rll", enc.encoding_id, page))
    bits, stats = _constrained_field_rect(
        h_dots, w_dots, enc.constraint.min_ink_run_dots,
        enc.constraint.min_white_run_dots, gen)
    return EncodedField(encoding=enc, plane_bits={enc.planes[0]: bits},
                        seed=seed, page=page, stats=stats)


# ---------------------------------------------------------------------------
# Page emission
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlacedField:
    field: EncodedField
    x_mm: float
    y_mm: float
    name: str = ""      # defaults to f"f{i}" at emit time


def _rects_gap_mm(a: tuple[float, float, float, float],
                  b: tuple[float, float, float, float]) -> float:
    """Axis-aligned gap between two (x0, y0, x1, y1) mm rects (<0 = overlap)."""
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    return max(dx, dy)


def _ps_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _sentinel_lines(page_size_pt: tuple[int, int], text: str) -> list[str]:
    """END sentinel: small K square + label, guarded, LAST in the stream
    (002.2/003.0 idiom) — proves the whole job reached the interpreter."""
    def pt(v_mm: float) -> float:
        return v_mm / MM_PER_INCH * 72.0
    h_pt = page_size_pt[1]
    page_h_mm = h_pt / 72.0 * MM_PER_INCH
    y_bot_mm = page_h_mm - MARGIN_MM - 1.0     # rect bottom edge, page frame
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "mark { initmatrix 0 0 0 1 setcmykcolor",
        f"  {pt(15.0):.2f} {h_pt - pt(y_bot_mm):.2f} {pt(2.5):.2f}"
        f" {pt(2.5):.2f} rectfill",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {pt(19.5):.2f} {h_pt - pt(y_bot_mm - 0.4):.2f} moveto"
        f" ({_ps_escape(text)}) show }} stopped cleartomark",
    ]


def _scramble_spec(enc: Encoding, page: int) -> str:
    if not enc.data_bearing:
        return (f"no payload: constraint-valid field from rng(seed, "
                f"b'rll/{enc.encoding_id}/pg' + page_le32), page={page}")
    if enc.n_states == 2:
        return (f"printed = payload XOR modulation.keystream(seed, plane="
                f"{_plane_index(enc.planes[0])}, page={page})")
    return (f"printed = (payload + U) mod {enc.n_states}; U = rng(seed, "
            f"b'symks/{enc.encoding_id}/pg' + page_le32).integers(0, "
            f"{enc.n_states}), page={page}")


def emit_page(placed: list[PlacedField], out_ps: str | Path, *,
              hw_dpi: int = HW_DPI_DEFAULT,
              page_size_pt: tuple[int, int] = A4_PT,
              header: str | None = None, end_sentinel: bool = False,
              title: str = "paperholo.encodings emit",
              guard_setpagedevice: bool = True,
              write_gt: bool = True) -> dict:
    """Emit placed EncodedFields as one raw-path PostScript page + manifest
    (+ GT arrays). Minimal skeleton only: optional header line and END
    sentinel; NO registration furniture (marks/strips/pilots belong to the L2
    composer). Returns the manifest dict; writes <out>_manifest.json and
    <out>_gt/*.npy alongside the .ps. Deterministic: identical inputs give a
    byte-identical page (sha256 in the manifest gates reuse)."""
    out_ps = Path(out_ps)
    page_w_mm = page_size_pt[0] / 72.0 * MM_PER_INCH
    page_h_mm = page_size_pt[1] / 72.0 * MM_PER_INCH

    items: list[dict] = []
    names: set[str] = set()
    for i, pf in enumerate(placed):
        name = pf.name or f"f{i}"
        if name in names:
            raise EncodingError(f"duplicate field name {name!r}")
        names.add(name)
        h, w = pf.field.shape_dots
        w_mm, h_mm = w / hw_dpi * MM_PER_INCH, h / hw_dpi * MM_PER_INCH
        rect = (pf.x_mm, pf.y_mm, pf.x_mm + w_mm, pf.y_mm + h_mm)
        if (rect[0] < MARGIN_MM or rect[1] < MARGIN_MM
                or rect[2] > page_w_mm - MARGIN_MM
                or rect[3] > page_h_mm - MARGIN_MM):
            raise EncodingError(
                f"field {name!r} at {rect} mm violates the measured printable "
                f"margin ({MARGIN_MM} mm, both engines)")
        items.append({"pf": pf, "name": name, "rect": rect,
                      "x_dots": mm_to_dots(pf.x_mm, hw_dpi),
                      "y_dots": mm_to_dots(pf.y_mm, hw_dpi),
                      "w_dots": w, "h_dots": h})

    for i, a in enumerate(items):           # pairwise geometry checks
        for b in items[i + 1:]:
            gap = _rects_gap_mm(a["rect"], b["rect"])
            ea, eb = a["pf"].field.encoding, b["pf"].field.encoding
            if ea.emission != eb.emission:
                if gap < CROSS_PATH_GAP_MM:
                    raise EncodingError(
                        f"{a['name']} (emission {ea.emission}) within "
                        f"{CROSS_PATH_GAP_MM} mm of {b['name']} (emission "
                        f"{eb.emission}) - 002.2 coexistence clearance")
            elif gap < 0:
                raise EncodingError(f"fields {a['name']} and {b['name']} "
                                    "overlap")
    reserved = []
    if header is not None:
        reserved.append(("header line", (0.0, 6.0, page_w_mm, 12.0)))
    if end_sentinel:
        reserved.append(("END sentinel",
                         (13.0, page_h_mm - 9.0, 80.0, page_h_mm - 4.0)))
    for label, rr in reserved:
        for a in items:
            if _rects_gap_mm(a["rect"], rr) < 0:
                raise EncodingError(f"field {a['name']} overlaps the {label} "
                                    f"band {rr} mm")

    seed_digest = hashlib.sha256(b"|".join(
        it["pf"].field.seed + it["pf"].field.encoding.encoding_id.encode()
        + it["pf"].field.page.to_bytes(4, "little") for it in items))
    jobid = seed_digest.hexdigest()[:8]

    doc = PSDoc(hw_dpi=hw_dpi, page_size_pt=page_size_pt,
                title=f"{title} LAY={LAYOUT_VERSION} J={jobid}",
                guard_setpagedevice=guard_setpagedevice)
    doc.begin_page()
    if header is not None:
        doc.put_label(header, mm_to_dots(12.0, hw_dpi),
                      mm_to_dots(10.0, hw_dpi), CMYK["K"], size_pt=6.0)
    doc.put_raw(["% ==== single-plane imagemask content (clean path) ===="])
    for it in items:
        f = it["pf"].field
        if f.encoding.emission != "clean_mask":
            continue
        doc.put_raw([f"% ---- {it['name']} {f.encoding.encoding_id} ----"])
        for plane in f.encoding.planes:
            doc.put_bitmap(f.plane_bits[plane], it["x_dots"], it["y_dots"],
                           CMYK[plane])
    doc.put_raw(["% ==== put_cmyk_bitmap composites ===="])
    for it in items:
        f = it["pf"].field
        if f.encoding.emission != "composite":
            continue
        doc.put_raw([f"% ---- {it['name']} {f.encoding.encoding_id} ----"])
        doc.put_cmyk_bitmap(f.plane_bits, it["x_dots"], it["y_dots"])
    if end_sentinel:
        doc.put_raw(_sentinel_lines(page_size_pt,
                                    f"END {jobid} paperholo.encodings"))
    doc.end_page()

    ps = doc.render()
    sha = hashlib.sha256(ps.encode()).hexdigest()
    out_ps.parent.mkdir(parents=True, exist_ok=True)
    out_ps.write_text(ps)

    gt_dir = out_ps.with_name(out_ps.stem + "_gt")
    field_entries: list[dict] = []
    for it in items:
        f: EncodedField = it["pf"].field
        gt: dict = {"payload": None, "dots": {}}
        if write_gt:
            gt_dir.mkdir(parents=True, exist_ok=True)
            if f.payload_symbols is not None:
                np.save(gt_dir / f"{it['name']}_payload.npy",
                        f.payload_symbols)
                gt["payload"] = f"{gt_dir.name}/{it['name']}_payload.npy"
            for plane in f.encoding.planes:
                np.save(gt_dir / f"{it['name']}_dots_{plane}.npy",
                        f.plane_bits[plane].astype(np.uint8))
                gt["dots"][plane] = f"{gt_dir.name}/{it['name']}_dots_{plane}.npy"
        try:
            seed_utf8: str | None = f.seed.decode()
        except UnicodeDecodeError:
            seed_utf8 = None
        cells = (None if f.printed_symbols is None
                 else [int(f.printed_symbols.shape[0]),
                       int(f.printed_symbols.shape[1])])
        field_entries.append({
            "name": it["name"], "encoding_id": f.encoding.encoding_id,
            "kind": f.encoding.kind, "planes": list(f.encoding.planes),
            "emission": f.encoding.emission,
            "seed_label": seed_utf8, "seed_hex": f.seed.hex(),
            "page": f.page,
            "x_mm": it["pf"].x_mm, "y_mm": it["pf"].y_mm,
            "x_dots": it["x_dots"], "y_dots": it["y_dots"],
            "w_dots": it["w_dots"], "h_dots": it["h_dots"],
            "cell_dots": f.encoding.cell_dots,
            "n_states": f.encoding.n_states,
            "cells_yx": cells,
            "scramble": _scramble_spec(f.encoding, f.page),
            "gt": gt, "stats": f.stats,
        })

    manifest = {
        "tool": "paperholo.encodings",
        "layout_version": LAYOUT_VERSION,
        "jobid": jobid,
        "hw_dpi": hw_dpi,
        "page_size_pt": list(page_size_pt),
        "ps_file": out_ps.name,
        "ps_sha256": sha,
        "ps_bytes": len(ps),
        "header": header,
        "end_sentinel": bool(end_sentinel),
        "stream_order": "labels, single-plane imagemasks, cmyk composites, "
                        "END sentinel last",
        "fields": field_entries,
    }
    out_ps.with_name(out_ps.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=1))
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _rate_cell(enc: Encoding) -> str:
    if enc.data_bearing:
        return f"{enc.entropy_bits_per_cell:.3f} b/cell"
    return "field-measured b/dot"


def list_table() -> str:
    rows = [("id", "kind", "planes", "cell", "states", "raw rate", "emission",
             "data-bearing")]
    for e in _ALL_ENCODINGS:
        rows.append((
            e.encoding_id, e.kind, "".join(e.planes),
            f"{e.cell_dots}x{e.cell_dots}" if e.cell_dots else "free",
            str(e.n_states) if e.n_states else "-",
            _rate_cell(e), e.emission,
            "yes" if e.data_bearing else "SEED-ONLY (encoder not implemented)"))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
             for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    lines.append("")
    lines.append("details: python -m paperholo.encodings --info <id> "
                 "[--field-mm WxH]")
    return "\n".join(lines)


def describe(enc: Encoding, field_mm: tuple[float, float] | None = None,
             hw_dpi: int = HW_DPI_DEFAULT) -> str:
    out = [
        f"encoding : {enc.encoding_id}",
        f"kind     : {enc.kind}"
        + ("" if enc.data_bearing else "  (NOT data-bearing - see status)"),
        f"planes   : {','.join(enc.planes)}",
    ]
    if enc.cell_dots is not None:
        cpi = hw_dpi / enc.cell_dots
        out.append(f"cell     : {enc.cell_dots}x{enc.cell_dots} dots"
                   f" ({cpi:.0f} cpi at {hw_dpi} dpi)")
        assert enc.state_names is not None
        out.append(f"alphabet : {enc.n_states} states "
                   "{" + ",".join(enc.state_names) + "}")
        bpc = enc.entropy_bits_per_cell or 0.0
        dens = enc.cells_per_mm2(hw_dpi) or 0.0
        out.append(f"entropy  : {bpc:.3f} b/cell raw; {dens:.1f} cells/mm2 -> "
                   f"{bpc * dens:.1f} b/mm2 raw ceiling (measured rates are "
                   "lower - see record)")
    else:
        assert enc.constraint is not None
        out.append(f"constraint: {enc.constraint.describe()}")
        out.append("entropy  : field-dependent b/dot (sampler-measured, "
                   "written to the emit manifest); measured decode record "
                   "0.147-0.167 b/dot")
    out += [
        f"emission : {enc.emission} ({enc.emission_note})",
        f"scan mode: {enc.scan_mode}",
        f"sync     : {enc.sync_note}",
        f"record   : {enc.record}",
    ]
    if not enc.data_bearing:
        out.append(
            "status   : constraint-VALID field generation from a seed IS "
            "supported; data-bearing bit->constrained-field mapping NOT "
            "IMPLEMENTED (no measured encoder exists; trellis/motif mapping "
            "= bounded-upside open item). --emit takes --field-mm + "
            "--seed-label, NOT --symbols.")
    if enc.kind == "cell_mlc":
        out.append(
            "status   : composed pages only — --emit refuses (the printed "
            "format is per-LEVEL plane keystreams + v4 pilots + dust via "
            "paperholo.compose, not the symbol-domain scramble)")
    if field_mm is not None:
        w_mm, h_mm = field_mm
        d = field_dims(enc, w_mm, h_mm, hw_dpi)
        line = (f"field {w_mm:g}x{h_mm:g} mm: {d['w_dots']}x{d['h_dots']} dots"
                f" = {d['n_dots']} dots")
        if enc.cell_dots is not None:
            line += (f"; {d['cells_x']}x{d['cells_y']} cells = {d['n_cells']}"
                     f" cells -> {d['raw_entropy_bits']:.0f} raw symbol-"
                     "entropy bits")
        out.append(line)
    return "\n".join(out)


def _parse_field_mm(text: str) -> tuple[float, float]:
    try:
        w_s, h_s = text.lower().split("x")
        w, h = float(w_s), float(h_s)
    except ValueError:
        raise EncodingError(f"--field-mm expects WxH (e.g. 21x30), got "
                            f"{text!r}") from None
    if w <= 0 or h <= 0:
        raise EncodingError(f"--field-mm dims must be positive, got {text!r}")
    return w, h


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m paperholo.encodings",
        description="Encoding registry + 2-D bitstream page emitter "
                    "(L1-encode/L0-emit seam). See module docstring for the "
                    "scramble format definition.")
    ap.add_argument("--list", action="store_true",
                    help="table of registered encodings")
    ap.add_argument("--info", metavar="ID", help="datasheet for one encoding")
    ap.add_argument("--emit", metavar="ID", help="emit a .ps page")
    ap.add_argument("--field-mm", metavar="WxH",
                    help="field size in mm (dims for --info; REQUIRED for "
                         "rll --emit, which is seed-driven)")
    ap.add_argument("--symbols", metavar="NPY",
                    help="2-D payload symbol array (.npy) for --emit of "
                         "data-bearing encodings")
    ap.add_argument("--out", metavar="PS", help="output .ps path for --emit")
    ap.add_argument("--seed-label", metavar="S", default="paperholo/emit",
                    help="scramble/sampler seed label (default "
                         "'paperholo/emit')")
    ap.add_argument("--page", type=int, default=0,
                    help="page index for keystream derivation (default 0)")
    ap.add_argument("--x-mm", type=float, default=15.0,
                    help="field left edge (default 15)")
    ap.add_argument("--y-mm", type=float, default=20.0,
                    help="field top edge (default 20)")
    ap.add_argument("--header", metavar="TEXT", default=None,
                    help="optional header label line (scratch sheets only)")
    ap.add_argument("--end-sentinel", action="store_true",
                    help="append the END sentinel (last element in stream)")
    args = ap.parse_args(argv)

    try:
        if args.list:
            print(list_table())
            return 0
        if args.info:
            fm = _parse_field_mm(args.field_mm) if args.field_mm else None
            print(describe(get_encoding(args.info), fm))
            return 0
        if args.emit:
            enc = get_encoding(args.emit)
            if not args.out:
                raise EncodingError("--emit requires --out <ps>")
            seed = args.seed_label.encode()
            if enc.data_bearing:
                if args.symbols is None:
                    raise EncodingError(
                        f"{enc.encoding_id} is data-bearing: --emit requires "
                        "--symbols <npy> (2-D symbol array)")
                if args.field_mm is not None:
                    raise EncodingError(
                        "--field-mm sets no field size for data-bearing "
                        "encodings (dims come from the symbol array); it is "
                        "for --info and for rll --emit")
                symbols = np.load(args.symbols)
                fld = encode_field(enc, symbols, seed, page=args.page)
            else:
                if args.symbols is not None:
                    raise EncodingError(f"{enc.encoding_id} "
                                        + _RLL_NOT_DATA_BEARING)
                if args.field_mm is None:
                    raise EncodingError(
                        f"{enc.encoding_id} --emit is seed-driven: pass "
                        "--field-mm WxH (+ --seed-label)")
                w_mm, h_mm = _parse_field_mm(args.field_mm)
                fld = generate_rll_field(enc, mm_to_dots(h_mm),
                                         mm_to_dots(w_mm), seed,
                                         page=args.page)
            manifest = emit_page(
                [PlacedField(fld, args.x_mm, args.y_mm, name="f0")], args.out,
                header=args.header, end_sentinel=args.end_sentinel)
            fe = manifest["fields"][0]
            print(f"wrote {args.out} ({manifest['ps_bytes']} bytes)")
            print(f"sha256 {manifest['ps_sha256']}")
            dims = f"{fe['w_dots']}x{fe['h_dots']} dots"
            if fe["cells_yx"]:
                dims += (f", {fe['cells_yx'][1]}x{fe['cells_yx'][0]} cells of "
                         f"{fe['cell_dots']} dots")
            print(f"f0: {fe['encoding_id']} {dims} at "
                  f"({fe['x_mm']:g}, {fe['y_mm']:g}) mm; manifest + GT "
                  "alongside")
            if fld.stats:
                print(f"stats: {fld.stats}")
            return 0
        ap.print_help()
        return 2
    except EncodingError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
