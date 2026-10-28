"""Capacity — promise-grade fountain planning arithmetic (HOLO-DESIGN F8,
§7.2, §13.35; docs/CMY8-COLUMN-GROUPS.md §3.7).

The per-block rank reserve scales with the number of independent solves
so the VOLUME failure bound stays ~2^-16; ``max_k_for`` is the
global-symbol primitive; whole-page planning enforces the worst
retained-page quota of every block (``page_capacity_sufficient`` /
``max_k_for_pages``); pooled rows add the deterministic dead-plane tier
(``pooled_page_capacity_sufficient`` / ``pooled_max_k_for_pages``), all
three tiers weighted per column group when the streams differ in width.
All arithmetic is exact. ``payload_bytes`` is raw symbol space; the
36-byte envelope is the format layer's business.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

from .column_groups import ColumnGroups
from .fountain import BLOCK_K_MAX, n_blocks_for, validated_count

RANK_RESERVE_BASE = 16          # per-block reserve at B = 1 (F8)


def rank_reserve_for(n_blocks: int, *, solves_per_block: int = 1) -> int:
    """Per-block reserve for ``solves_per_block * n_blocks`` independent
    solves — one union bound over the whole volume.

    The default is the frozen fountain-v2 rule ``16 + ceil(log2 B)``:
    one solve per block. A -v0 CMY8 row passes 3 (three per-stream
    solves per block); a column-group pool passes its group count Z
    (one solve per group, ruling 2026-09-04).
    """
    if n_blocks < 1:
        raise ValueError("n_blocks must be >= 1")
    solves_per_block = validated_count(solves_per_block, "solves_per_block")
    return RANK_RESERVE_BASE + (
        n_blocks * solves_per_block - 1).bit_length()


def q_fraction(q: float) -> Fraction:
    """The source-fraction dial as an EXACT rational.

    q dials are human decimals (0.35, 0.5, 0.75); float floor/ceil of
    q*N loses whole symbols at exact boundaries (measured: 0.35*187200
    -> 65519.999...), so all budget arithmetic goes through
    Fraction(str(q)). Dials with more than 4 decimal places (denominator
    > 10000) are refused — they are computed floats, not format inputs.
    """
    frac = Fraction(str(q))
    if frac.denominator > 10_000:
        raise ValueError(f"q={q!r} is not a clean decimal dial "
                         f"(<= 4 decimal places)")
    if not 0 < frac <= 1:
        raise ValueError("q must be in (0, 1]")
    return frac


def source_budget(n_symbols_total: int, q: float) -> int:
    """floor(q * n_symbols_total), computed exactly."""
    if n_symbols_total < 0:
        raise ValueError("n_symbols_total must be >= 0")
    frac = q_fraction(q)
    return (frac.numerator * n_symbols_total) // frac.denominator


def max_k_for(n_symbols_total: int, q: float, *,
              n_streams: int = 1) -> int:
    """Largest K with K + reserve(B(K))*B(K) <= floor(q*n_symbols_total).

    Binary search on the strictly increasing left side; exact arithmetic
    throughout. Returns 0 when nothing fits.
    """
    n_streams = validated_count(n_streams, "n_streams")
    budget = source_budget(n_symbols_total, q)
    lo, hi = 0, budget
    while lo < hi:
        mid = (lo + hi + 1) // 2             # mid >= 1, so n_blocks >= 1
        nb = n_blocks_for(mid)
        if mid + rank_reserve_for(
                nb, solves_per_block=n_streams) * nb <= budget:
            lo = mid
        else:
            hi = mid - 1
    return lo


def retained_pages(n_pages: int, q: float) -> int:
    """ceil(q * n_pages), computed exactly.

    This is the minimum whole-page count in the deterministic promise tier.
    """
    if isinstance(n_pages, (bool, np.bool_)) or not isinstance(
            n_pages, (int, np.integer)):
        raise TypeError("n_pages must be an integer")
    if n_pages < 0:
        raise ValueError("n_pages must be >= 0")
    frac = q_fraction(q)
    return -(-(frac.numerator * int(n_pages)) // frac.denominator)


def page_capacity_sufficient(k_total: int, tiles_per_page: int,
                             n_pages: int, q: float, *,
                             n_streams: int = 1) -> bool:
    """Whether ``K`` satisfies both promise tiers for whole-page loss.

    For ``B = ceil(K / BLOCK_K_MAX)``, ``r = rank_reserve_for(B)`` and
    ``L = ceil(q*P)``, safety requires both::

        K + B*r <= floor(q*P*T)                 (global fragments)
        ceil(K/B) + r <= L * floor(T/B)         (every block)

    The second bound is deliberately pessimistic: every retained page gives
    every block at least ``floor(T/B)`` symbols, independent of which pages
    survive.  It is the frozen Track-1 promise and closes the original
    global-average hole without assuming a favourable retained-page subset.
    """
    n_streams = validated_count(n_streams, "n_streams")
    if isinstance(k_total, (bool, np.bool_)) or not isinstance(
            k_total, (int, np.integer)):
        raise TypeError("k_total must be an integer")
    if isinstance(tiles_per_page, (bool, np.bool_)) or not isinstance(
            tiles_per_page, (int, np.integer)):
        raise TypeError("tiles_per_page must be an integer")
    if int(k_total) < 0:
        raise ValueError("k_total must be >= 0")
    if int(tiles_per_page) < 1:
        raise ValueError("tiles_per_page must be >= 1")
    # retained_pages validates n_pages and q even for the vacuous K=0 case.
    kept_pages = retained_pages(n_pages, q)
    k_total = int(k_total)
    tiles_per_page = int(tiles_per_page)
    n_pages = int(n_pages)
    if k_total == 0:
        return True
    n_blocks = n_blocks_for(k_total)
    reserve = rank_reserve_for(n_blocks, solves_per_block=n_streams)
    global_ok = (
        k_total + n_blocks * reserve
        <= source_budget(n_pages * tiles_per_page, q)
    )
    largest_block = -(-k_total // n_blocks)
    per_block_ok = (
        largest_block + reserve
        <= kept_pages * (tiles_per_page // n_blocks)
    )
    return global_ok and per_block_ok


def max_k_for_pages(tiles_per_page: int, n_pages: int, q: float, *,
                    n_streams: int = 1) -> int:
    """Largest K satisfying both global and every-block page capacity.

    Feasibility is not monotone across changes in ``B``: a new block can
    improve ``T mod B`` enough to restore per-block feasibility.  Therefore
    this enumerates block-count intervals instead of binary-searching K.
    """
    n_streams = validated_count(n_streams, "n_streams")
    if isinstance(tiles_per_page, (bool, np.bool_)) or not isinstance(
            tiles_per_page, (int, np.integer)):
        raise TypeError("tiles_per_page must be an integer")
    if int(tiles_per_page) < 1:
        raise ValueError("tiles_per_page must be >= 1")
    kept_pages = retained_pages(n_pages, q)
    tiles_per_page = int(tiles_per_page)
    n_pages = int(n_pages)
    budget = source_budget(n_pages * tiles_per_page, q)
    best = 0
    for n_blocks in range(1, n_blocks_for(budget) + 1):
        reserve = rank_reserve_for(n_blocks, solves_per_block=n_streams)
        per_block_budget = (
            kept_pages * (tiles_per_page // n_blocks) - reserve
        )
        candidate = min(
            n_blocks * BLOCK_K_MAX,
            budget - n_blocks * reserve,
            n_blocks * per_block_budget,
        )
        interval_low = (n_blocks - 1) * BLOCK_K_MAX + 1
        if candidate >= interval_low:
            best = max(best, candidate)
    return int(best)


def _group_weights(n_streams: int, groups: ColumnGroups | None
                   ) -> tuple[int, tuple[int, ...]]:
    """(Z, carried per stream) of a pooled row — one group carrying one
    chunk per tile when no column groups are declared."""
    if groups is None:
        return 1, (1,) * n_streams
    if len(groups.carried) != n_streams:
        raise ValueError("column groups disagree with the stream count")
    return groups.n_groups, groups.carried


def _grouped_budget(n_pages: int, tiles_per_page: int, q: float,
                    z: int, carried: tuple[int, ...]) -> int:
    """floor(q * P*T * sum(carried) / Z): the global fragment budget in
    symbol-equivalents (``source_budget(P*T*n, q)`` at one group)."""
    frac = q_fraction(q)
    return ((frac.numerator * n_pages * tiles_per_page * sum(carried))
            // (frac.denominator * z))


def pooled_page_capacity_sufficient(k_total: int, tiles_per_page: int,
                                    n_pages: int, q: float, *,
                                    n_streams: int,
                                    enforce_plane_tier: bool = True,
                                    groups: ColumnGroups | None = None
                                    ) -> bool:
    """Whether pooled ``k_total`` satisfies the pooled promise tiers.

    For a pooled multistream row (one fountain over ``T*n`` symbols per
    page under stream-exact quotas), with ``B = ceil(K/16384)``,
    ``r = rank_reserve_for(B)`` (one solve per block) and
    ``L = ceil(q*P)``::

        K + B*r <= floor(q*P*T*n)                (1: global fragments)
        ceil(K/B) + r <= L * n*(T//B)            (2: whole-page loss)
        ceil(K/B) + r <= P * (n-1)*(T//B)        (3: any ONE dead plane,
                                                  all pages present)

    Tier 2 uses the stream-exact strengthening ``n*(T//B)`` (each stream
    contributes at least ``T//B`` per block per page), NOT the weaker
    naive ``floor(n*T/B)`` substitution. Tier 3 is CONDITIONAL on the
    caller: its budget grows with the page count, so enforcing it above
    q = (n-1)/n would satisfy any dial by page inflation at ~(n-1)/n
    fill rather than filling to the dial. Which side of that the caller
    wants is dial POLICY (gen.plan: enforced and reported "guaranteed"
    at or below the ceiling, dropped and reported "not at this dial"
    above) — ``enforce_plane_tier=False`` evaluates tiers 1+2 only, and
    this function stays pure arithmetic either way. The combined
    page+plane tier is intentionally absent (recorded in
    docs/CMY8-POOLED-FOUNTAIN.md §2.3).

    The caller owns the pooled canonical-K law (``k_total`` a multiple
    of ``n_streams``); this predicate evaluates any ``k_total``.

    ``groups`` (a column-group pool, docs/CMY8-COLUMN-GROUPS.md §3.7)
    weights the same three tiers per column group: every solve is one
    (block, group) system and the reserve covers ``B*Z`` of them; a
    page's stream ``s`` contributes ``floor((T//B)*carried[s]/Z)`` rows
    to every group of every block; the global budget is
    ``floor(q*P*T*sum(carried)/Z)``; and the dead plane that binds tier
    3 is the HEAVIEST one. No groups (or one) is the uniform arithmetic
    above, bit for bit.
    """
    n_streams = validated_count(n_streams, "n_streams")
    if n_streams < 2:
        raise ValueError("pooled capacity requires n_streams >= 2")
    if isinstance(k_total, (bool, np.bool_)) or not isinstance(
            k_total, (int, np.integer)):
        raise TypeError("k_total must be an integer")
    if isinstance(tiles_per_page, (bool, np.bool_)) or not isinstance(
            tiles_per_page, (int, np.integer)):
        raise TypeError("tiles_per_page must be an integer")
    if int(k_total) < 0:
        raise ValueError("k_total must be >= 0")
    if int(tiles_per_page) < 1:
        raise ValueError("tiles_per_page must be >= 1")
    z, carried = _group_weights(n_streams, groups)
    kept_pages = retained_pages(n_pages, q)
    k_total = int(k_total)
    tiles_per_page = int(tiles_per_page)
    n_pages = int(n_pages)
    if k_total == 0:
        return True
    n_blocks = n_blocks_for(k_total)
    reserve = rank_reserve_for(n_blocks, solves_per_block=z)
    largest_block = -(-k_total // n_blocks)
    per_page_block_floor = tiles_per_page // n_blocks
    per_stream = [(per_page_block_floor * c) // z for c in carried]
    rows_per_page = sum(per_stream)
    global_ok = (
        k_total + n_blocks * reserve
        <= _grouped_budget(n_pages, tiles_per_page, q, z, carried)
    )
    page_ok = largest_block + reserve <= kept_pages * rows_per_page
    plane_ok = (
        not enforce_plane_tier
        or largest_block + reserve
        <= n_pages * (rows_per_page - max(per_stream))
    )
    return global_ok and page_ok and plane_ok


def pooled_max_k_for_pages(tiles_per_page: int, n_pages: int, q: float, *,
                           n_streams: int,
                           enforce_plane_tier: bool = True,
                           groups: ColumnGroups | None = None) -> int:
    """Largest pooled ``k_total`` (a multiple of ``n_streams``)
    satisfying the pooled tiers for a fixed page count.

    Same non-monotone-across-B structure as ``max_k_for_pages``:
    enumerate block-count intervals; within one, the binding budget is
    the minimum of the global bound and the per-block bounds of tiers
    2 and 3. The result is floored to a multiple of ``n_streams``
    (the pooled canonical-K law: ``k_total = n_streams * k_meta``).
    ``enforce_plane_tier`` is the caller's dial policy and ``groups`` the
    column-group weighting, exactly as in
    :func:`pooled_page_capacity_sufficient`.
    """
    n_streams = validated_count(n_streams, "n_streams")
    if n_streams < 2:
        raise ValueError("pooled capacity requires n_streams >= 2")
    if isinstance(tiles_per_page, (bool, np.bool_)) or not isinstance(
            tiles_per_page, (int, np.integer)):
        raise TypeError("tiles_per_page must be an integer")
    if int(tiles_per_page) < 1:
        raise ValueError("tiles_per_page must be >= 1")
    z, carried = _group_weights(n_streams, groups)
    kept_pages = retained_pages(n_pages, q)
    tiles_per_page = int(tiles_per_page)
    n_pages = int(n_pages)
    budget = _grouped_budget(n_pages, tiles_per_page, q, z, carried)
    best = 0
    for n_blocks in range(1, n_blocks_for(budget) + 1):
        reserve = rank_reserve_for(n_blocks, solves_per_block=z)
        per_page_block_floor = tiles_per_page // n_blocks
        per_stream = [(per_page_block_floor * c) // z for c in carried]
        rows_per_page = sum(per_stream)
        bounds = [kept_pages * rows_per_page]
        if enforce_plane_tier:
            bounds.append(n_pages * (rows_per_page - max(per_stream)))
        per_block_budget = min(bounds) - reserve
        candidate = min(
            n_blocks * BLOCK_K_MAX,
            budget - n_blocks * reserve,
            n_blocks * per_block_budget,
        )
        candidate -= candidate % n_streams
        interval_low = (n_blocks - 1) * BLOCK_K_MAX + 1
        if candidate >= interval_low:
            best = max(best, candidate)
    return int(best)


def payload_bytes(k_total: int, s_bits: int) -> int:
    """Whole bytes carried by K symbols of S bits: (K*S) // 8.

    Raw symbol space only — the 36-byte envelope ({sha256}{len} header,
    HOLO-DESIGN §7.1) is subtracted at the format layer, not here.
    """
    if k_total < 0 or s_bits < 1:
        raise ValueError("need k_total >= 0 and s_bits >= 1")
    return (k_total * s_bits) // 8
