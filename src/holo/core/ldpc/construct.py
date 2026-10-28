"""Frozen e-IRA LDPC mother codes for holo format v1 (HOLO-DESIGN §3 F5).

PROVENANCE: ported from src/paperholo/ldpc.py, whose module docstring is
the normative construction record (QC H_d with mixed info column weights
{heavy_deg, 3}, heavy columns first; IRA interleaver Pi; bit-level
dual-diagonal accumulator H_a; acceptance rules (a)-(d); the restart
discipline). holo never re-runs that construction: the six winning draws
live in data/<rate_id>.json as TRANSPARENT block descriptions and ARE the
code — this module only expands them to bit-level edges and validates
their structure. NO RNG, NO restarts, NO construction draw.

Each json carries: pi (m,) interleaver, heavy_rows/heavy_shifts
(nh, heavy_deg), light_rows/light_shifts (kb-nh, 3), restart, and the
geometry fields — plain integer arrays, readable and diffable.
PROVENANCE + REGENERATION: util/regen_holo_ldpc_data.py reruns
paperholo's live seeded construction (whose ldpc.py docstring is the
normative record, including the measured falsification history of the
textbook variants), verifies it against paperholo's golden anchors, and
rewrites these files byte-identically — demonstrated 2026-07-19 (all six
rungs MATCH, restart 0). FORMAT IDENTITY is pinned externally and
independently: golden digests over the canonical little-endian ('<i4')
lexsorted edge arrays live in tests/holo/test_holo_ldpc.py,
bump-don't-edit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

N_BITS = 4096
Z = 64
_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class LdpcSpec:
    """One rate-ladder rung (format-axis constants; load_code cross-checks
    every field against the frozen data geometry)."""

    rate_id: str
    k_bits: int
    n_bits: int = N_BITS
    z: int = Z
    gap_min: int = 24            # rule (b) single-column parity-weight floor
    heavy_deg: int = 10          # heavy info column weight (8 at r0775,
                                 # 6 at r0850 — mb feasibility, see paperholo)

    def __post_init__(self) -> None:
        if self.n_bits % self.z or self.k_bits % self.z:
            raise ValueError("n_bits and k_bits must be multiples of z")
        if not (0 < self.k_bits < self.n_bits):
            raise ValueError("need 0 < k_bits < n_bits")

    @property
    def m_bits(self) -> int:
        return self.n_bits - self.k_bits

    @property
    def rate(self) -> float:
        return self.k_bits / self.n_bits


# k_bits identical to paperholo.ldpc.LDPC_LADDER (Z-quantized rates).
# r0547 targets 0.547 which snaps to the same k=2240 as r0550; it is a
# distinct code (independent construction draw), kept for ladder parity.
LADDER: dict[str, LdpcSpec] = {
    "r0547": LdpcSpec("r0547", 2240),
    "r0550": LdpcSpec("r0550", 2240),   # 0.547 = round(4096*0.55) snapped
    "r0625": LdpcSpec("r0625", 2560),   # 0.625
    "r0700": LdpcSpec("r0700", 2880),   # 0.703
    "r0775": LdpcSpec("r0775", 3200, heavy_deg=8),   # 0.781 (mb = 14)
    "r0850": LdpcSpec("r0850", 3520, heavy_deg=6),   # 0.859 (mb = 9)
}


@dataclass(frozen=True, eq=False)
class Code:
    """Loaded mother code: bit-level edge arrays in decode order (lexsorted
    by (check, variable)) + reduceat segment starts + encode-side info-edge
    segments (paperholo build_code post-draw structures)."""

    spec: LdpcSpec
    edge_chk: np.ndarray         # (E,) int32, lexsorted by (chk, var)
    edge_var: np.ndarray         # (E,) int32
    chk_starts: np.ndarray       # (m,) int64 reduceat starts (all checks used)
    var_order: np.ndarray        # (E,) int64: edge ids sorted by variable
    var_starts: np.ndarray       # (n,) int64 reduceat starts over var_order
    enc_info_col: np.ndarray     # info edges sorted by row: info col 0..k-1
    enc_rows: np.ndarray         # rows that have >= 1 info edge, ascending
    enc_row_starts: np.ndarray   # reduceat starts into enc_info_col

    @property
    def n_edges(self) -> int:
        return int(self.edge_chk.size)


def _expand_edges(pi: np.ndarray, heavy_rows: np.ndarray,
                  heavy_shifts: np.ndarray, light_rows: np.ndarray,
                  light_shifts: np.ndarray, spec: LdpcSpec
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Block description + interleaver + accumulator -> bit-level
    (chk, var) edge arrays (paperholo ldpc._expand_edges, verbatim).
    Circulant convention: I(s)[a, b] = 1 iff b == (a + s) mod Z."""
    z, k, m = spec.z, spec.k_bits, spec.m_bits
    a = np.arange(z, dtype=np.int64)
    chk_l: list[np.ndarray] = []
    var_l: list[np.ndarray] = []
    j = 0
    for rows, shifts in ((heavy_rows, heavy_shifts),
                         (light_rows, light_shifts)):
        for c in range(rows.shape[0]):
            for r, s in zip(rows[c], shifts[c]):
                chk_l.append(pi[int(r) * z + a])
                var_l.append(j * z + (a + int(s)) % z)
            j += 1
    # H_a: bit-level dual diagonal — parity bit j sits in checks j and j+1
    jj = np.arange(m, dtype=np.int64)
    chk_l.append(jj)
    var_l.append(k + jj)
    chk_l.append(jj[1:])
    var_l.append(k + jj[:-1])
    return (np.concatenate(chk_l).astype(np.int32),
            np.concatenate(var_l).astype(np.int32))


_CODE_CACHE: dict[str, Code] = {}


def load_code(rate_id: str, *, data_dir: Path | None = None) -> Code:
    """Load (cached) one frozen mother code from its json.

    Runtime validation is STRUCTURAL only: geometry fields against the
    LADDER spec, well-formed block description (shapes, value ranges,
    pi a permutation), and expanded-H sanity (no degree-1 checks, no
    unused variables). Format identity is pinned EXTERNALLY by the
    golden edge digests in tests/holo/test_holo_ldpc.py — a self-stored
    hash next to the data it protects guards against nothing
    (2026-07-19 review). data_dir overrides the package data directory
    (test seam; the cache serves the default directory only).
    """
    if rate_id not in LADDER:
        raise ValueError(f"unknown rate_id {rate_id!r}; "
                         f"ladder = {sorted(LADDER)}")
    use_cache = data_dir is None
    if use_cache and rate_id in _CODE_CACHE:
        return _CODE_CACHE[rate_id]
    spec = LADDER[rate_id]
    path = (_DATA_DIR if data_dir is None else Path(data_dir)) \
        / f"{rate_id}.json"
    d = json.loads(path.read_text())
    for field in ("n_bits", "z", "k_bits", "gap_min", "heavy_deg"):
        if int(d[field]) != getattr(spec, field):
            raise ValueError(
                f"{rate_id}: data {field}={int(d[field])} != ladder "
                f"{getattr(spec, field)} — data/spec mismatch")
    pi = np.asarray(d["pi"], dtype=np.int64)
    heavy_rows = np.asarray(d["heavy_rows"], dtype=np.int64)
    heavy_shifts = np.asarray(d["heavy_shifts"], dtype=np.int64)
    light_rows = np.asarray(d["light_rows"], dtype=np.int64)
    light_shifts = np.asarray(d["light_shifts"], dtype=np.int64)
    kb = spec.k_bits // spec.z
    mb = spec.m_bits // spec.z
    if (pi.shape != (spec.m_bits,)
            or heavy_rows.shape != heavy_shifts.shape
            or light_rows.shape != light_shifts.shape
            or heavy_rows.shape[1] != spec.heavy_deg
            or light_rows.shape[1] != 3
            or heavy_rows.shape[0] + light_rows.shape[0] != kb):
        raise ValueError(f"{rate_id}: block-description shapes malformed")
    if not np.array_equal(np.sort(pi), np.arange(spec.m_bits)):
        raise ValueError(f"{rate_id}: pi is not a permutation")
    for name, arr, hi in (("heavy_rows", heavy_rows, mb),
                          ("light_rows", light_rows, mb),
                          ("heavy_shifts", heavy_shifts, spec.z),
                          ("light_shifts", light_shifts, spec.z)):
        if arr.size and (int(arr.min()) < 0 or int(arr.max()) >= hi):
            raise ValueError(f"{rate_id}: {name} out of range")
    chk, var = _expand_edges(pi, heavy_rows, heavy_shifts,
                             light_rows, light_shifts, spec)
    order = np.lexsort((var, chk))
    chk, var = chk[order], var[order]
    m, n, k = spec.m_bits, spec.n_bits, spec.k_bits
    chk_counts = np.bincount(chk, minlength=m)
    if int(chk_counts.min()) < 2:
        raise ValueError(f"{rate_id}: degree-1 check in expanded H")
    chk_starts = np.concatenate(([0], np.cumsum(chk_counts)[:-1]))
    var_order = np.argsort(var, kind="stable")
    var_counts = np.bincount(var, minlength=n)
    if int(var_counts.min()) < 1:
        raise ValueError(f"{rate_id}: unused variable in expanded H")
    var_starts = np.concatenate(([0], np.cumsum(var_counts)[:-1]))
    # encode-side: info edges only (var < k), sorted by row
    is_info = var < k
    ic, iv = chk[is_info].astype(np.int64), var[is_info].astype(np.int64)
    io = np.argsort(ic, kind="stable")
    ic, iv = ic[io], iv[io]
    enc_rows, first = np.unique(ic, return_index=True)
    code = Code(spec=spec, edge_chk=chk, edge_var=var,
                chk_starts=chk_starts.astype(np.int64),
                var_order=var_order.astype(np.int64),
                var_starts=var_starts.astype(np.int64),
                enc_info_col=iv, enc_rows=enc_rows,
                enc_row_starts=first.astype(np.int64))
    if use_cache:
        _CODE_CACHE[rate_id] = code
    return code
