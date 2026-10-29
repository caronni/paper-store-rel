"""Volume planning: payload -> (K, pages, repair) under a format spec.

Promise-grade arithmetic throughout (HOLO-DESIGN F8): both the global
fragment budget and every block's worst retained-page quota include the
block-count-scaled fountain rank reserve. Every tile of every page bears one
fountain symbol (ESI = tile counter); there are no fountain-inert tiles in
format v1.  A multistream row carries one symbol per declared stream at the
same physical ESI and uses one common K; its envelope width is n_streams
symbols of the row's one symbol width, while its rank reserve covers every
independent solve.  A pooled row whose streams differ in width is a
column-group pool (docs/CMY8-COLUMN-GROUPS.md): the tiers are weighted by
the groups each stream carries per tile and every (block, group) system
is a solve of its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..core import capacity, fountain
from ..format.descriptor import FormatSpec
from ..format.envelope import OVERHEAD_BYTES, source_symbol_count
from ..format.profiles import Family


@dataclass(frozen=True)
class VolumePlan:
    spec: FormatSpec
    payload_bytes: int
    q: float                      # source fraction dial (promise-grade)
    k_total: int                  # source symbols
    n_pages: int
    n_symbols_total: int          # pages * tiles_per_page (* n_streams
    #                               for a pooled row: symbol units)
    # Repair symbols in each logical stream.  In a -v0 multistream row
    # this is not a count or classification of physical tiles:
    # stream-specific block assignment can make one ESI systematic in one
    # stream and repair in another.  In a pooled row it is the total
    # repair-symbol count of the one fountain.
    n_repair: int
    # Pooled rows only (docs/CMY8-POOLED-FOUNTAIN.md §2.1): the metadata
    # K field value; k_total = n_streams * k_meta.  None for every
    # single-fountain-per-stream row.
    k_meta: int | None = None
    # Pooled rows only: the dead-plane tier's dial-conditional status
    # (ruling 2026-08-14), carried so every report can say it out loud.
    plane_tier: str | None = None

    @property
    def symbol_bits(self) -> int:
        """Common per-stream width (the established K-facing property)."""
        return self.spec.symbol_bits

    @property
    def stream_symbol_bits(self) -> tuple[int, ...]:
        return self.spec.stream_symbol_bits

    @property
    def aggregate_symbol_bits(self) -> int:
        return self.spec.aggregate_symbol_bits

    @property
    def n_streams(self) -> int:
        return len(self.spec.stream_profiles)

    @property
    def effective_k_over_n(self) -> float:
        """Source symbols over emitted symbol-equivalents.  A physical
        symbol of a column-group pool counts as the groups its stream
        carries over the group count; at one group this is
        ``k_total / n_symbols_total``."""
        groups = self.spec.column_groups
        return (self.k_total * groups.n_groups * self.n_streams
                / (self.n_symbols_total * groups.chunks_per_site))

    @property
    def net_area_basis(self) -> str:
        """Which area ``net_bits_per_mm2`` divides by — say it out loud.

        ``media``: the whole sheet (v1 rows, whose identity names media).
        ``field``: the printed field only (v2 rows, whose identity is
        coding x tile matrix and names no media at all — media is an
        emission choice, FORMAT-SPACE §7).  The two numbers are NOT
        comparable: on A4 a full-page field is ~92% of the sheet.
        """
        return "media" if self.spec.media_mm is not None else "field"

    @property
    def net_area_mm2(self) -> float:
        """Per-page area the net density is priced on (see basis)."""
        if self.spec.media_mm is not None:
            w_mm, h_mm = self.spec.media_mm
            return w_mm * h_mm
        cells_y, cells_x = self.spec.cells_yx
        pitch_mm = self.spec.pitch * Fraction(254, 10)   # exact inches -> mm
        return float(cells_y * cells_x * pitch_mm * pitch_mm)

    @property
    def net_bits_per_mm2(self) -> float:
        """Payload bits per mm² over ``net_area_basis`` (per page).

        The field basis is what the experiment record quotes (e029's
        64.7 b/mm² net field, e033-I's 230.7 b/mm² field).
        """
        return self.payload_bytes * 8 / (self.net_area_mm2 * self.n_pages)


def _pooled_dial_policy(spec: FormatSpec, q: float) -> tuple[Fraction, bool]:
    """The pooled dial policy — PLANNER POLICY, deliberately not
    predicate arithmetic (docs/CMY8-POOLED-FOUNTAIN.md §2.3, ruling
    2026-08-14): every legal dial is accepted, but the dead-plane tier
    is DIAL-CONDITIONAL. At or below the row's any-one-plane ceiling —
    (n-1)/n at equal widths, the column groups' heaviest-stream
    ceiling otherwise (docs/CMY8-COLUMN-GROUPS.md §3.7) — it is enforced
    in sizing and the promise is carried; above it, tier 3's budget
    grows with the page count, so enforcing it would only inflate pages
    at ~ceiling fill — it drops out of sizing (the volume fills to the
    true dial) and the plan says so out loud instead."""
    frac = capacity.q_fraction(q)          # exact; refuses dirty floats
    return frac, frac <= spec.column_groups.any_plane_ceiling


def tier_word(spec: FormatSpec) -> str:
    """What one pooled tier-3 death takes out: a plane, or for cmy, whose
    streams are label bits, a stream (dead Y kills lo, dead M kills hi,
    dead C both — docs/CMY-DESIGN.md §2.2, §2.6)."""
    return "stream" if spec.codec_family is Family.CMY else "plane"


def pooled_plane_tier(spec: FormatSpec, q: float) -> str | None:
    """The reported dead-plane tier status of a pooled row at this dial
    (None for every single-fountain-per-stream row).  The ceiling is
    ``(n-1)/n`` at equal widths; a column-group pool's is set by its
    heaviest stream (docs/CMY8-COLUMN-GROUPS.md §3.7)."""
    if not spec.pooled_fountain:
        return None
    _, guaranteed = _pooled_dial_policy(spec, q)
    return ("guaranteed" if guaranteed else
            f"not-at-this-dial (needs q <= "
            f"{spec.column_groups.any_plane_ceiling})")


def _plan_pooled_volume(spec: FormatSpec, payload_len_bytes: int,
                        q: float) -> VolumePlan:
    """Pooled rows: one fountain over n_streams * k_meta source symbols,
    tiers 1+2 always, tier 3 under the dial policy."""
    frac, plane_tier_ok = _pooled_dial_policy(spec, q)
    n = spec.n_streams
    groups = spec.column_groups
    k_meta = source_symbol_count(
        payload_len_bytes, spec.aggregate_symbol_bits)
    k_total = n * k_meta
    tpp = spec.tiles_per_page
    nb = fountain.n_blocks_for(k_total)
    reserve = capacity.rank_reserve_for(
        nb, solves_per_block=groups.n_groups) * nb
    symbols_per_page = tpp * n
    n_needed = max(k_total, -(-((k_total + reserve) * frac.denominator)
                              // frac.numerator))
    n_pages = -(-n_needed // symbols_per_page)
    while (n_pages <= spec.max_pages and
           not capacity.pooled_page_capacity_sufficient(
               k_total, tpp, n_pages, q, n_streams=n,
               enforce_plane_tier=plane_tier_ok, groups=groups)):
        n_pages += 1
    if n_pages > spec.max_pages:
        raise ValueError(
            f"payload needs {n_pages} pages at q={q} but the 18-bit "
            f"counter caps {spec.spec_id} at {spec.max_pages} pages")
    n_total = n_pages * symbols_per_page
    if not capacity.pooled_page_capacity_sufficient(
            k_total, tpp, n_pages, q, n_streams=n,
            enforce_plane_tier=plane_tier_ok, groups=groups):
        raise RuntimeError("pooled whole-page capacity invariant "
                           "violated — planner bug")
    # Repair symbols = the physical symbols past every block's
    # systematic positions (k_total of them at one group).
    code = fountain.VolumeCode(k_total, spec.symbol_bits, spec.seed,
                               tiles_per_page=tpp, n_streams=n,
                               groups=groups)
    n_systematic = sum(code.systematic_positions(block)
                       for block in range(nb))
    return VolumePlan(spec=spec, payload_bytes=payload_len_bytes, q=q,
                      k_total=k_total, n_pages=n_pages,
                      n_symbols_total=n_total,
                      n_repair=n_total - n_systematic, k_meta=k_meta,
                      plane_tier=pooled_plane_tier(spec, q))


def plan_volume(spec: FormatSpec, payload_len_bytes: int, q: float
                ) -> VolumePlan:
    """Smallest whole-page volume storing the payload at source fraction
    <= q with the rank reserve honored. Raises ValueError when the payload
    cannot fit the 18-bit address space at this q."""
    if payload_len_bytes <= 0:
        raise ValueError("empty payload")
    if spec.pooled_fountain:
        return _plan_pooled_volume(spec, payload_len_bytes, q)
    frac = capacity.q_fraction(q)          # exact; refuses dirty floats
    s = spec.aggregate_symbol_bits
    k = source_symbol_count(payload_len_bytes, s)
    tpp = spec.tiles_per_page
    nb = fountain.n_blocks_for(k)
    n_streams = len(spec.stream_profiles)
    reserve = capacity.rank_reserve_for(
        nb, solves_per_block=n_streams) * nb
    # exact ceil((k + reserve) / q) = ceil((k + reserve) * den / num)
    n_needed = max(k, -(-((k + reserve) * frac.denominator)
                        // frac.numerator))
    n_pages = -(-n_needed // tpp)
    while (n_pages <= spec.max_pages and
           not capacity.page_capacity_sufficient(
               k, tpp, n_pages, q, n_streams=n_streams)):
        n_pages += 1
    if n_pages > spec.max_pages:
        raise ValueError(
            f"payload needs {n_pages} pages at q={q} but the 18-bit "
            f"counter caps {spec.spec_id} at {spec.max_pages} pages")
    n_total = n_pages * tpp
    if not capacity.page_capacity_sufficient(
            k, tpp, n_pages, q, n_streams=n_streams):
        raise RuntimeError("whole-page capacity invariant violated — "
                           "planner bug")
    return VolumePlan(spec=spec, payload_bytes=payload_len_bytes, q=q,
                      k_total=k, n_pages=n_pages, n_symbols_total=n_total,
                      n_repair=n_total - k)


def max_payload_bytes(spec: FormatSpec, q: float, n_pages: int) -> int:
    """Largest payload a fixed page count can promise at source fraction
    q (envelope subtracted)."""
    if not 1 <= n_pages <= spec.max_pages:
        raise ValueError(f"n_pages must be in 1..{spec.max_pages}")
    if spec.pooled_fountain:
        _, plane_tier_ok = _pooled_dial_policy(spec, q)
        k_total = capacity.pooled_max_k_for_pages(
            spec.tiles_per_page,
            n_pages,
            q,
            n_streams=spec.n_streams,
            enforce_plane_tier=plane_tier_ok,
            groups=spec.column_groups,
        )
        if k_total <= 0:
            return 0
        k_meta = k_total // spec.n_streams
        return max(
            0, (k_meta * spec.aggregate_symbol_bits) // 8 - OVERHEAD_BYTES)
    k = capacity.max_k_for_pages(
        spec.tiles_per_page,
        n_pages,
        q,
        n_streams=len(spec.stream_profiles),
    )
    if k <= 0:
        return 0
    return max(0, (k * spec.aggregate_symbol_bits) // 8 - OVERHEAD_BYTES)
