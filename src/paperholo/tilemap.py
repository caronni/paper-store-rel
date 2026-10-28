"""PageDecodeState — the 2-D decode map between L2 acquisition and L3/L4.

The acquire-v2 interface object (decoder-axis): every pilot tile (60-cell
grid) and LDPC data tile (64-cell grid) of one printed page, with bits/LLRs
at ABSOLUTE cell coordinates, accumulated across windows and scans, then
decoded, certified, backfilled and iterated by the higher layers.

Keying doctrine (from the acquire-v2 L3/L4 read): the primary domain is the
ABSOLUTE CELL / payload-bijection index — exactly the currency acquire emits
(payload_cell_index) and ldpc.gather_tile_llrs consumes; the 60-cell pilot
view and 64-cell LDPC view are pure derived functions of (spec, seed) and
never stored redundantly.

Feedback edges hosted here (LAYERS.md registry):
- F6 multi-scan accumulation: per-scan observations are stored SEPARATELY
  (never pre-summed) because equal-weight combining is measured-negative
  (012.3 hardware majority loses to best single; 013 naive LLR summation
  loses under slip variance). Merge policies: "best_scan" (default,
  measured winner), "best_per_tile" (the 013/015 tile-level-union interim,
  now weighted by PER-TILE pilot agreement), "weighted_sum" (the designed
  pilot-agreement weights — first implementation), "sum" (the measured-
  negative baseline, kept for comparison).
- F9 CRC certification: a decoded tile's re-encoded transmitted bits are
  pinned +-inf in the certified overlay ("codes certify registration,
  pilots measure it"); known_cell_values() exposes the same knowledge in
  the DETECTION domain (through the payload keystream) for future
  re-registration / F10 detector bootstrap.
- Iteration: pending_tiles() is the worklist; add scans or switch policies
  and re-decode only what is not yet certified.

Per-scan quality: AcquireResult.tile_words (post-fold per-pilot-tile
corrected-error counts) supplies both the page-level scan weight and the
per-LDPC-tile local weight (an LDPC 64-tile overlaps 2x2-ish pilot 60-tiles;
local quality = mean corrected errors over the overlapping pilot tiles).

LEVEL-AWARE (cmy8 / layout_version 4, IMPL-3 — COLOR-DESIGN D2): on a
3-level spec the tile key becomes ((ty, tx), level) and each (tile, level)
certifies independently against its own rate rung (decode_tiles takes 3
rate_ids). One ScanObservation still holds one physical scan: payload_llr
is stored (3, N) sharing the single payload_cell_index (levels share the
index map; the overlap tie-break in extend() uses the mean |LLR| across
levels because all three level LLRs of a cell come from ONE window's
registration — per-level window picks would mix registration classes).
Pilot quality (tile_words) is level-independent — words are luma objects.
certified_results yields (page, level, TileResult) triples, exactly what
fountain.tiles_to_symbols consumes for level-stratified volumes. The K
path (n_levels == 1) is byte-identical to before.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

from paperholo import compose, ldpc
from paperholo.pilots import code_for_layout

PILOT_TILE_CELLS = 60          # p60b6 (frozen forever, PILOTS-DESIGN)
WORD_BITS = 100                # pilot word length (bits per pilot tile)


@dataclass
class ScanObservation:
    """One physical scan's accumulated evidence for one page (possibly from
    many acquire windows — same scan => same registration class, merged)."""

    scan_id: str
    payload_cell_index: np.ndarray        # (N,) int64 absolute bijection idx
    payload_llr: np.ndarray               # (N,) float64, house sign;
    #                                       color pages: (3, N), levels C,M,Y
    tile_words: dict[tuple[int, int], int] = field(default_factory=dict)
    n_windows: int = 0
    meta: dict = field(default_factory=dict)
    fail_errs: float = 13.0    # failed-word pessimism = the LAYOUT's t_full
    #   (13 v3 / 10 v2 — set by PageDecodeState.add_acquire_result; the
    #   true BER at a failed word is unknown but >= t/n)

    def extend(self, idx: np.ndarray, llr: np.ndarray,
               tile_words: dict[tuple[int, int], int]) -> None:
        """Fold another window of the SAME scan in. Overlapping indices keep
        the higher-|LLR| observation (windows re-lock independently; the
        more confident detection wins). Caveat: LLR calibration is
        per-window (quantile+GMM), so the tie-break favors the more
        confidently FITTED window; true mis-registration is excluded
        upstream by Stage-B + the post-fold word gate, not here. Color
        observations ((3, N) llr): the tie-break magnitude is the mean
        |LLR| across levels — one window registration per cell, kept
        consistent across levels."""
        idx_all = np.concatenate([self.payload_cell_index, idx])
        llr_all = np.concatenate([self.payload_llr, llr], axis=-1)
        mag = (np.abs(llr_all) if llr_all.ndim == 1
               else np.abs(llr_all).mean(axis=0))
        order = np.lexsort((-mag, idx_all))
        idx_s, llr_s = idx_all[order], llr_all[..., order]
        keep = np.ones(idx_s.size, bool)
        keep[1:] = idx_s[1:] != idx_s[:-1]
        self.payload_cell_index = np.ascontiguousarray(idx_s[keep])
        self.payload_llr = np.ascontiguousarray(llr_s[..., keep])
        for t, nerr in tile_words.items():
            old = self.tile_words.get(t)
            self.tile_words[t] = nerr if old is None else (
                nerr if (old < 0 or (0 <= nerr < old)) else old)
        self.n_windows += 1

    @property
    def pilot_ber_est(self) -> float:
        """Page-level pilot-site BER estimate from the post-fold word
        decodes: corrected errors / word bits over decoded tiles. Failed
        tiles (nerr < 0) count at the code's correction radius (a floor —
        the true BER there is unknown but >= t/n)."""
        errs = 0.0
        bits = 0
        for nerr in self.tile_words.values():
            errs += nerr if nerr >= 0 else self.fail_errs
            bits += WORD_BITS
        if bits:
            return errs / bits
        # correlation-placed fragments carry no pilot words but DO carry a
        # measured pilot-mismatch from the placer (Placement.mismatch) —
        # without this, every quality-aware merge policy ranks a pristine
        # placed fragment dead-last at the 0.5 no-evidence default and
        # decode_tiles starves it (2026-07-10 review finding, reproduced)
        m = self.meta.get("mismatch")
        return float(m) if m is not None else 0.5

    def tile_quality(self, ldpc_tile_yx: tuple[int, int]) -> float | None:
        """Local pilot-BER estimate for one 64-cell LDPC tile: mean over the
        pilot 60-tiles overlapping it (None if none observed)."""
        ty, tx = ldpc_tile_yx
        y0, y1 = ty * ldpc.TILE_CELLS, (ty + 1) * ldpc.TILE_CELLS - 1
        x0, x1 = tx * ldpc.TILE_CELLS, (tx + 1) * ldpc.TILE_CELLS - 1
        vals = []
        for py in range(y0 // PILOT_TILE_CELLS, y1 // PILOT_TILE_CELLS + 1):
            for px in range(x0 // PILOT_TILE_CELLS,
                            x1 // PILOT_TILE_CELLS + 1):
                nerr = self.tile_words.get((py, px))
                if nerr is None:
                    continue
                vals.append((nerr if nerr >= 0 else self.fail_errs)
                            / WORD_BITS)
        if vals:
            return float(np.mean(vals))
        # placed fragments have no pilot words anywhere: their placer-
        # measured mismatch is the honest local estimate (see pilot_ber_est)
        m = self.meta.get("mismatch")
        return float(m) if m is not None else None


@dataclass
class TileState:
    """One LDPC data tile's decode state (64-cell grid, absolute coords).
    On color pages there is one TileState per (tile, LEVEL) — levels
    certify independently (D2); level is None on K pages."""

    tile_yx: tuple[int, int]
    status: str = "unobserved"   # unobserved|low_coverage|failed|certified|degenerate
    coverage: float = 0.0
    rate_id: str | None = None
    policy: str | None = None
    scan_id: str | None = None   # provenance (best_per_tile / best_scan)
    crc_ok: bool = False
    syndrome_ok: bool = False
    n_iters: int = 0
    payload_bits: np.ndarray | None = None       # certified user bits
    level: int | None = None     # cmy8 level (0..2 = C,M,Y); None on K


def _obs_llr(obs: ScanObservation, level: int | None) -> np.ndarray:
    """The (N,) LLR slice of one observation: the array itself on K pages,
    the level row on color pages."""
    return obs.payload_llr if level is None else obs.payload_llr[level]


class PageDecodeState:
    """The 2-D decode map for one (format, seed, page).

    Tile keys: (ty, tx) on K pages; ((ty, tx), level) on color pages —
    every key-consuming API (pending_tiles, decode_tiles(tiles=...),
    tiles[...]) speaks that key type."""

    def __init__(self, spec: compose.ComposeSpec, seed: bytes, page: int = 0):
        self.spec = spec
        self.seed = seed
        self.page = int(page)
        self.n_levels = int(spec.n_levels)
        self.scans: dict[str, ScanObservation] = {}
        grid_tiles = ldpc.tile_grid(spec.page_cells_yx)
        if self.n_levels == 1:
            self.tiles: dict = {t: TileState(t) for t in grid_tiles}
        else:
            self.tiles = {(t, lv): TileState(t, level=lv)
                          for t in grid_tiles for lv in range(self.n_levels)}
        self._capacity = compose.payload_capacity(spec)
        # F9 certified overlay in the payload-LLR domain (descrambled):
        # +-inf at re-encoded transmitted bits of certified tiles.
        # Color pages keep one overlay PER LEVEL (list index = level).
        if self.n_levels == 1:
            self._cert_idx: np.ndarray = np.empty(0, np.int64)
            self._cert_llr: np.ndarray = np.empty(0, np.float64)
        else:
            self._cert_idx = [np.empty(0, np.int64)
                              for _ in range(self.n_levels)]
            self._cert_llr = [np.empty(0, np.float64)
                              for _ in range(self.n_levels)]

    def copy(self) -> "PageDecodeState":
        """Fresh tile/certification state SHARING the (immutable-by-
        convention) ScanObservation objects — for policy comparisons on the
        same evidence. Mutating an observation after copy() affects every
        copy; use add_acquire_result on each state to diverge."""
        m = PageDecodeState(self.spec, self.seed, page=self.page)
        m.scans = dict(self.scans)
        return m

    # ---- adaptive scan-request loop (F6 "until converged", executable) ---

    WEAK_LLR = 2.0            # |combined LLR| below this counts as weak

    def _confidence_snapshot(self) -> dict:
        """Coverage + weak-cell fraction of the current combined evidence.
        Confidence uses the per-cell MEAN |LLR| over covering scans, not
        the sum: a DUPLICATE scan doubles the sum's magnitude and would
        fake a confidence gain (measured on the 014.2 live demo — the v1
        sum metric asked for more scans after an exact duplicate); the
        mean is invariant to duplicates, so only genuinely new evidence
        moves it."""
        if not self.scans:
            return {"coverage": 0, "weak_frac": 1.0}
        n_lev = self.n_levels
        dense = np.zeros((n_lev, self._capacity), np.float64)
        cnt = np.zeros(self._capacity, np.int32)
        for o in self.scans.values():
            llr2d = np.atleast_2d(o.payload_llr)
            for lv in range(n_lev):
                np.add.at(dense[lv], o.payload_cell_index, llr2d[lv])
            np.add.at(cnt, o.payload_cell_index, 1)
        idx = np.flatnonzero(cnt > 0)
        if not idx.size:
            return {"coverage": 0, "weak_frac": 1.0}
        mean_llr = dense[:, idx] / cnt[idx]
        # per-level weak fraction, averaged (a level-blind mean would let a
        # strong C level mask a starved Y level)
        return {"coverage": int(idx.size),
                "weak_frac": float(np.mean(
                    np.abs(mean_llr) < self.WEAK_LLR))}

    def note_scan_added(self) -> dict:
        """Call after folding one scan's windows in (page_decode does):
        records a confidence snapshot so more_scans_useful can measure the
        marginal utility of the LAST scan."""
        snap = self._confidence_snapshot()
        hist = getattr(self, "_scan_history", [])
        hist.append(snap)
        self._scan_history = hist
        return snap

    def more_scans_useful(self, *, min_coverage_gain: int = 1000,
                          min_weak_drop: float = 0.005
                          ) -> tuple[bool, str]:
        """Should the operator be asked for another scan? True while the
        page is not fully certified AND the last scan still moved the
        needle (coverage or confidence), or while fewer than two scans
        exist (re-placed scans carry measured diversity, 004.0b; combining
        pays after the ctx detector, 014.2). Heuristic v1 — the STOP side
        is load-bearing: pending==0 always stops; a no-gain last scan
        stops and points at the better levers instead.
        Returns (verdict, human-readable reason)."""
        pending = [t for t in self.pending_tiles()
                   if self.tiles[t].status != "degenerate"]
        if not pending:
            return False, "all tiles certified — done"
        hist = getattr(self, "_scan_history", [])
        if len(hist) < 2:
            return True, (f"{len(pending)} tiles uncertified and only "
                          f"{len(hist)} scan(s) folded in — re-placed "
                          f"scans are measured-diverse (004.0b)")
        prev, last = hist[-2], hist[-1]
        cov_gain = last["coverage"] - prev["coverage"]
        weak_drop = prev["weak_frac"] - last["weak_frac"]
        if cov_gain >= min_coverage_gain:
            return True, (f"{len(pending)} tiles uncertified; last scan "
                          f"added {cov_gain} cells of coverage")
        if weak_drop >= min_weak_drop:
            return True, (f"{len(pending)} tiles uncertified; last scan "
                          f"cut the weak-cell fraction by {weak_drop:.3f}")
        return False, (f"{len(pending)} tiles uncertified but the last "
                       f"scan gained <{min_coverage_gain} cells and "
                       f"<{min_weak_drop:.3f} weak-drop — diminishing "
                       f"returns; escalate (ctx detector, lower rate, "
                       f"flatter scan) instead")

    # ---- accumulation (L2 -> map) ---------------------------------------
    # (module-level volume_scans_wanted below hosts the OUTER, volume-level
    #  F6 loop; more_scans_useful above is the INNER per-page loop)

    def _res_llr(self, res) -> np.ndarray:
        """AcquireResult payload_llr -> storage shape ((N,) K / (3, N)
        color); validates the level structure matches the spec."""
        if self.n_levels == 1:
            if isinstance(res.payload_llr, (list, tuple)):
                raise ValueError("K-page map got a per-level LLR list — "
                                 "this result decoded a color format")
            return np.asarray(res.payload_llr, np.float64)
        if (not isinstance(res.payload_llr, (list, tuple))
                or len(res.payload_llr) != self.n_levels):
            raise ValueError(
                "color-page result must carry a list of "
                f"{self.n_levels} per-level LLR arrays (got "
                f"{type(res.payload_llr).__name__}) — was the scan RGB? "
                "(grey scans of color pages carry no payload)")
        return np.stack([np.asarray(l, np.float64)
                         for l in res.payload_llr])

    def add_acquire_result(self, scan_id: str, res) -> None:
        """Fold one ok AcquireResult (one window of one scan) in."""
        if not res.ok or res.payload_cell_index is None:
            raise ValueError("only ok results with payload can be added")
        if res.page != self.page:
            raise ValueError(f"result is page {res.page}, map is page "
                             f"{self.page}")
        llr = self._res_llr(res)
        obs = self.scans.get(scan_id)
        if obs is None:
            obs = ScanObservation(
                scan_id=scan_id,
                payload_cell_index=np.asarray(res.payload_cell_index,
                                              np.int64),
                payload_llr=llr,
                tile_words=dict(res.tile_words), n_windows=1,
                meta={"orientation_k": res.orientation_k,
                      "mirrored": res.mirrored,
                      "stage_b_match_rate": res.stage_b_match_rate,
                      "placement_source": "pilot_words"},
                fail_errs=float(code_for_layout(self.spec.pilot).t_full))
            self.scans[scan_id] = obs
        else:
            obs.extend(np.asarray(res.payload_cell_index, np.int64),
                       llr, dict(res.tile_words))

    def add_placed_fragment(self, scan_id: str, cell_index: np.ndarray,
                            llr: np.ndarray, *,
                            source: str = "correlation",
                            placement_meta: dict | None = None) -> None:
        """Fold a CORRELATION-PLACED fragment's cells in (edge F13).

        Provenance discipline: use a scan_id DISTINCT from any word-certified
        observation of the same physical scan (e.g. "C/frag07") — a
        correlation placement is a lower-trust registration class and must
        stay revocable until its cells certify through LDPC+CRC (F9, the
        unchanged backstop; a mis-placed fragment can waste itself, never
        silently corrupt). meta carries placement_source=source plus the
        placer's margin diagnostics for the merge policies to weigh."""
        if self.n_levels != 1:
            raise ValueError("correlation-placed fragments are a K/luma "
                             "feature (F13); the color placement leg is "
                             "unbuilt — COLOR-DESIGN v1 scope")
        if scan_id in self.scans:
            raise ValueError(
                f"scan_id {scan_id!r} already holds a "
                f"{self.scans[scan_id].meta.get('placement_source')} "
                "observation; placed fragments need their own id")
        meta = {"placement_source": source}
        if placement_meta:
            meta.update(placement_meta)
        self.scans[scan_id] = ScanObservation(
            scan_id=scan_id,
            payload_cell_index=np.asarray(cell_index, np.int64),
            payload_llr=np.asarray(llr, np.float64),
            tile_words={}, n_windows=1, meta=meta,
            fail_errs=float(code_for_layout(self.spec.pilot).t_full))

    # ---- decode-directed re-acquisition (F15, PILOTS-DESIGN §15.7) -------

    def drop_scan(self, scan_id: str) -> bool:
        """Remove one observation — the §15.7 R2 supersede primitive.

        A repass observation re-derives from the SAME pixels as the one
        it improves on; summing correlated evidence is the measured
        F1/F6 failure mode, so the old observation must LEAVE the state
        before the superseding one enters (under its own new scan_id,
        provenance-readable). Certified tiles are untouched: their truth
        lives in TileState.payload_bits + the F9 backfill overlay, never
        in an observation. Returns True iff the scan_id existed."""
        return self.scans.pop(scan_id, None) is not None

    # (the §15.7 R1 label EXPORT already existed: known_cell_values(),
    #  the F10 detection-domain accessor below — repass wraps it)

    # ---- merge policies (F6) ---------------------------------------------

    def _dense(self, obs_weights: list[tuple[ScanObservation, float]],
               level: int | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Weighted-sum dense LLR + sparse (idx, llr) extraction (one level
        slice on color pages — weights are level-independent, pilot quality
        is a luma property)."""
        dense = np.zeros(self._capacity, np.float64)
        seen = np.zeros(self._capacity, bool)
        for obs, w in obs_weights:
            if w <= 0.0:
                continue
            np.add.at(dense, obs.payload_cell_index,
                      w * _obs_llr(obs, level))
            seen[obs.payload_cell_index] = True
        idx = np.flatnonzero(seen)
        return idx, dense[idx]

    def combined_llrs(self, policy: str = "best_scan",
                      tile_yx: tuple[int, int] | None = None,
                      level: int | None = None
                      ) -> tuple[np.ndarray, np.ndarray, str | None]:
        """(payload_cell_index, payload_llr, provenance_scan_id) under a
        merge policy. tile_yx localizes best_per_tile's quality lookup.
        Color pages pass level (0..2); the scan RANKING is level-blind
        (pilot words are luma), only the returned LLR slice differs."""
        if self.n_levels != 1 and level is None:
            raise ValueError("color page: combined_llrs needs level")
        if not self.scans:
            return np.empty(0, np.int64), np.empty(0, np.float64), None
        obs_all = list(self.scans.values())
        if policy == "sum":                      # measured-negative baseline
            idx, llr = self._dense([(o, 1.0) for o in obs_all], level)
            return idx, llr, None
        if policy == "weighted_sum":
            # pilot-agreement weights (PILOTS-DESIGN: per-scan pilot
            # agreement supplies the combining weights). LLR reliability
            # scales ~ (1-2p): weight relative to the best scan. Floored at
            # 0.05: a scan with no decoded pilot tiles estimates p=0.5 and
            # would otherwise be dropped entirely even though it passed
            # acquire's own gates (review finding).
            ps = [o.pilot_ber_est for o in obs_all]
            wbase = [max((1.0 - 2.0 * p) ** 2, 0.05) for p in ps]
            wmax = max(wbase)
            idx, llr = self._dense(
                [(o, w / wmax) for o, w in zip(obs_all, wbase)], level)
            return idx, llr, None
        if policy == "best_per_tile":
            if tile_yx is None:
                raise ValueError("best_per_tile needs tile_yx")

            def key(o: ScanObservation) -> float:
                q = o.tile_quality(tile_yx)
                return q if q is not None else o.pilot_ber_est
            best = min(obs_all, key=key)
            return (best.payload_cell_index, _obs_llr(best, level),
                    best.scan_id)
        if policy != "best_scan":
            raise ValueError(f"unknown policy {policy!r}")
        # best_scan (page-level pilot agreement)
        best = min(obs_all, key=lambda o: o.pilot_ber_est)
        return best.payload_cell_index, _obs_llr(best, level), best.scan_id

    # ---- decode + certification (L3, F9) ----------------------------------

    _POLICIES = ("best_scan", "best_per_tile", "weighted_sum", "sum")

    def decode_tiles(self, rate_id, *, policy: str = "best_scan",
                     min_coverage: float = 0.05,
                     tiles: list | None = None,
                     max_iters: int = 60) -> dict[str, int]:
        """Decode (or re-decode) tiles under a merge policy; certified tiles
        are recorded + backfilled and never demoted. Returns counters.

        Selection under best_scan/best_per_tile is COVERAGE-AWARE (review
        finding, measured): scans are ranked by pilot quality but a scan
        that never observed a tile cannot win it — per tile, the ranked
        scans are tried in order and the first whose gathered coverage
        clears min_coverage is used (falling back to the max-coverage one,
        recorded low_coverage). A pristine-but-tiny fragment therefore
        cannot starve a full-page scan — the 013/015 tile-level-union
        semantics.

        Color pages: rate_id is a SEQUENCE of 3 per-level rate ids (C, M,
        Y — the COLOR-DESIGN P5 rungs); each ((ty, tx), level) key decodes
        that level's LLR slice against its own rung."""
        if policy not in self._POLICIES:
            raise ValueError(f"policy must be one of {self._POLICIES}, "
                             f"got {policy!r}")
        if self.n_levels == 1:
            if not isinstance(rate_id, str):
                raise ValueError("K page: rate_id is one ladder id")
            spec_by_level = {None: ldpc.LDPC_LADDER[rate_id]}
            rate_by_level = {None: rate_id}
        else:
            if isinstance(rate_id, str) or len(rate_id) != self.n_levels:
                raise ValueError(f"color page: rate_id must be "
                                 f"{self.n_levels} per-level ladder ids")
            spec_by_level = {lv: ldpc.LDPC_LADDER[r]
                             for lv, r in enumerate(rate_id)}
            rate_by_level = dict(enumerate(rate_id))
        todo = tiles if tiles is not None else self.pending_tiles()
        counts = {"certified": 0, "failed": 0, "low_coverage": 0,
                  "degenerate": 0, "skipped_certified": 0}
        # summing policies: page-level LLRs computed once (per level)
        if policy in ("weighted_sum", "sum"):
            summed = {lv: self.combined_llrs(policy, level=lv)
                      for lv in spec_by_level}
        for t in todo:
            st = self.tiles[t]
            tyx, lv = (t, None) if self.n_levels == 1 else t
            spec_l = spec_by_level[lv]
            if st.status == "certified":
                counts["skipped_certified"] += 1
                continue
            if policy in ("best_scan", "best_per_tile"):
                # rank candidates by quality (global or tile-local), take
                # the first that actually covers the tile
                if policy == "best_scan":
                    ranked = sorted(self.scans.values(),
                                    key=lambda o: o.pilot_ber_est)
                else:
                    ranked = sorted(
                        self.scans.values(),
                        key=lambda o: (q if (q := o.tile_quality(tyx))
                                       is not None else o.pilot_ber_est))
                llr4096 = mask = None
                cov, prov = -1.0, None
                for obs in ranked:
                    l4, m4, c4 = ldpc.gather_tile_llrs(
                        _obs_llr(obs, lv), obs.payload_cell_index,
                        self.spec, self.seed, tyx)
                    if c4 > cov:
                        llr4096, mask, cov, prov = l4, m4, c4, obs.scan_id
                    if c4 >= min_coverage:
                        break
                if llr4096 is None:          # no scans at all
                    st.status = "low_coverage"
                    counts["low_coverage"] += 1
                    continue
            else:
                idx_p, llr_p, prov = summed[lv]
                llr4096, mask, cov = ldpc.gather_tile_llrs(
                    llr_p, idx_p, self.spec, self.seed, tyx)
            st.coverage = float(cov)
            st.rate_id = rate_by_level[lv]
            st.policy = policy
            st.scan_id = prov
            if ldpc.tile_user_capacity(mask, spec_l) == 0:
                # includes ldpc's CRC-only tiles (k_eff == 32): no payload,
                # so we skip their registration-certificate decode too —
                # interior (fountain-bearing) tiles are never degenerate
                st.status = "degenerate"
                counts["degenerate"] += 1
                continue
            if cov < min_coverage:
                st.status = "low_coverage"
                counts["low_coverage"] += 1
                continue
            tr = ldpc.decode_tile(llr4096, mask, spec_l, tile_yx=tyx,
                                  max_iters=max_iters)
            st.crc_ok = tr.crc_ok
            st.syndrome_ok = tr.syndrome_ok
            st.n_iters = tr.n_iters
            if tr.ok:
                st.status = "certified"
                st.payload_bits = tr.payload_bits
                self._backfill(tyx, tr.payload_bits, mask, spec_l, level=lv)
                counts["certified"] += 1
            else:
                st.status = "failed"
                counts["failed"] += 1
        return counts

    def _backfill(self, tile_yx: tuple[int, int], user_bits: np.ndarray,
                  mask: np.ndarray, spec_l: ldpc.LdpcSpec,
                  level: int | None = None) -> None:
        """F9: pin the certified tile's re-encoded transmitted bits +-inf in
        the (descrambled) payload-LLR domain (per-level overlay on color)."""
        _, tx_bits = ldpc.encode_tile(user_bits, mask, spec_l)
        pidx = ldpc.tile_payload_indices(tile_yx, self.spec, self.seed,
                                         mask)
        llr = np.where(tx_bits.astype(bool), np.inf, -np.inf)
        if level is None:
            self._cert_idx = np.concatenate([self._cert_idx, pidx])
            self._cert_llr = np.concatenate([self._cert_llr, llr])
        else:
            self._cert_idx[level] = np.concatenate(
                [self._cert_idx[level], pidx])
            self._cert_llr[level] = np.concatenate(
                [self._cert_llr[level], llr])

    # ---- exports (L4, diagnostics, iteration) -----------------------------

    def pending_tiles(self) -> list[tuple[int, int]]:
        """Worklist: every tile not yet certified/degenerate."""
        return [t for t, st in self.tiles.items()
                if st.status not in ("certified", "degenerate")]

    def certified_results(self) -> Iterator[tuple]:
        """Stream for fountain.tiles_to_symbols: (page, TileResult) pairs on
        K pages, (page, level, TileResult) triples on color pages — exactly
        the two shapes tiles_to_symbols dispatches on via vspec.n_levels."""
        for t, st in self.tiles.items():
            if st.status != "certified":
                continue
            tr = ldpc.TileResult(
                tile_yx=st.tile_yx, ok=True, crc_ok=True, syndrome_ok=True,
                payload_bits=st.payload_bits, n_iters=st.n_iters,
                n_erased=0, n_measured=0)
            if self.n_levels == 1:
                yield (self.page, tr)
            else:
                yield (self.page, st.level, tr)

    def certified_payload_llrs(self, level: int | None = None
                               ) -> tuple[np.ndarray, np.ndarray]:
        """The F9 overlay: (payload_cell_index, +-inf llr) of every
        certified bit (descrambled domain). Color pages pass level."""
        if self.n_levels == 1:
            if level not in (None, 0):
                raise ValueError("K page has no levels")
            return self._cert_idx.copy(), self._cert_llr.copy()
        if level is None:
            raise ValueError("color page: certified_payload_llrs needs level")
        return self._cert_idx[level].copy(), self._cert_llr[level].copy()

    def known_cell_values(self, level: int | None = None
                          ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Certified knowledge in the DETECTION domain: (cells_y, cells_x,
        printed_bit) — through the payload keystream, for future
        re-registration / F10 detector bootstrap. Color pages pass level
        (that level's plane keystream descrambles it)."""
        if self.n_levels == 1:
            if level not in (None, 0):
                raise ValueError("K page has no levels")
            cert_idx, cert_llr, ks_level = self._cert_idx, self._cert_llr, None
        else:
            if level is None:
                raise ValueError("color page: known_cell_values needs level")
            cert_idx, cert_llr = self._cert_idx[level], self._cert_llr[level]
            ks_level = level
        if cert_idx.size == 0:
            e = np.empty(0, np.int64)
            return e, e, np.empty(0, np.uint8)
        idx_map = compose.payload_index_map(self.spec, self.seed)
        ys, xs = np.nonzero(idx_map >= 0)
        vals = idx_map[idx_map >= 0]
        cy = np.empty(vals.size, np.int64)
        cx = np.empty(vals.size, np.int64)
        cy[vals] = ys
        cx[vals] = xs
        ks = compose.payload_keystream(self.spec, self.seed, self.page,
                                       level=ks_level)
        y, x = cy[cert_idx], cx[cert_idx]
        bits = (cert_llr > 0).astype(np.uint8) ^ ks[y, x]
        return y, x, bits

    def summary(self) -> dict:
        by_status: dict[str, int] = {}
        for st in self.tiles.values():
            by_status[st.status] = by_status.get(st.status, 0) + 1
        return {"page": self.page, "n_scans": len(self.scans),
                "tiles": by_status,
                "certified_bits": int(sum(
                    st.payload_bits.size for st in self.tiles.values()
                    if st.status == "certified"
                    and st.payload_bits is not None))}


def volume_scans_wanted(page_states: dict[int, "PageDecodeState"],
                        vspec) -> list[tuple[int, dict]]:
    """The OUTER F6 loop, volume level: once every page has evidence, ask
    the FOUNTAIN what is still missing and rank the pages whose re-scan is
    most likely to close the rank deficit.

    The inner loop (more_scans_useful) runs while a sheet is on the platen:
    rescan THIS page until it stops paying. This function runs across the
    volume: fountain.volume_decode's per-block diagnostics say how many
    more certified symbols each block needs; any uncertified INTERIOR tile
    is a potential new symbol (geometric ESI round-robin spreads every
    page across all blocks), so pages are ranked by their count of
    uncertified interior tiles. Returns [] when the volume decodes —
    nothing more to ask.
    """
    from paperholo import fountain
    symbols: dict = {}
    for pg, st in page_states.items():
        symbols.update(
            fountain.tiles_to_symbols(st.certified_results(), vspec))
    data, diag = fountain.volume_decode(symbols, vspec)
    if data is not None:
        return []
    deficit = sum(max(0, b["needed"] - b["rank"]) if not b["solved"] else 0
                  for b in diag["blocks"])
    interior = set(fountain.interior_tiles(vspec.compose_spec))
    ranked = []
    for pg, st in page_states.items():
        # color keys are ((ty, tx), level) — an uncertified LEVEL is a
        # missing fountain symbol in its own right (symbol = page,tile,level)
        n_unc = sum(1 for t, ts in st.tiles.items()
                    if ts.tile_yx in interior and ts.status != "certified")
        if n_unc:
            ranked.append((pg, {"uncertified_interior": n_unc,
                                "volume_deficit_symbols": int(deficit)}))
    ranked.sort(key=lambda x: -x[1]["uncertified_interior"])
    return ranked
