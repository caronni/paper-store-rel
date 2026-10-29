"""The score column — ground truth, and nothing else (DESIGN §0, §7).

Every number here is computed AFTER the blind path has finished: the
evidence, the combination and the ladder never see this module, and an
import-set test pins that.  What lives here is the measurement the
instrument exists for:

* the SOFT INFORMATION RATE ``R`` per (tile-stream, arm) with a seeded
  bootstrap upper bound — DESIGN §1's corrected converse.  ``R < 1``
  with the bound below 1 says the evidence cannot carry the code's
  active bits, whatever the decoder; hard cell error says no such thing
  (a BSC converse at 8.4% would refuse columns that certify at 0.855);
* hard cell error, DESCRIPTIVE, at two named decisions — the calibrated
  MAP decision (sign of the LLR) and the median threshold — so a reader
  can never mistake one for the other;
* ``d'`` and ROC AUC on the LLR, the detector's own separation;
* WHERE the wrong cells are: by true sibling state (from the emitted
  field) crossed with whether the frame knew those siblings, by context
  bin (the true 8-neighbour ink count of the target plane), by their
  clustering inside the tile, and by whether the other captures are
  wrong at the same cell (print-frozen vs capture noise);
* per rung, bits wrong against the GT mother codeword with all four
  denominators named (mother / transmitted / active / user) — the
  histogram DESIGN §6's deferral rule reads;
* the empirical waterfall ``P(certify | R)`` per stream and rung.

THE VERDICT ADJUDICATION LIVES HERE NOW.  It used to live in
`analyzer.ladder.score_rung`, one function deep inside the blind path
holding a GT vector; the 2026-09-04 ruling took it out of the run, so
`verdict_against_truth` below is the whole of it: a certificate that
disagrees with the payload is `wrong` on a direct rung (nothing priced
it) and `false_accept` on a list rung (the exposure bound paid for it).
Nothing in this module ever runs during a decode — an import-set test
pins that no module a run command can reach imports it.
"""

from __future__ import annotations

import base64
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from holo.receiver.format import tile_codec
from holo.receiver.lib import ldpc, pava
from holo.receiver.lib.ldpc import CODES
from holo.receiver.plugins.tiles import stream_fact

from . import ladder as ladder_mod
from . import mother as mother_mod
from .types import (DIRECT_RUNGS, VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST,
                    VERDICT_FALSE_ACCEPT, VERDICT_UNSCOREABLE, VERDICT_WRONG,
                    Evidence, Key, KnownFrame, LaneFootprint, Mother, Truth)

TILE_CELLS = 64

#: Bootstrap resamples behind the 95% upper bound on R.
BOOTSTRAP_DRAWS = 400
BOOTSTRAP_LEVEL = 0.95


class OracleError(RuntimeError):
    """Ground truth does not cover what was asked of it."""


# ------------------------------------------------------- the truth vectors

def true_sequential(truth: Truth, row: Any, key: Key) -> np.ndarray | None:
    """The AS-PRINTED sequential bits of one tile-stream (PLAN §1.3).

    ``encode_frame(user, bank) ^ cmy8_dither_bits`` — byte for byte what
    ``color_sites.certified_projection`` writes onto the cells, so a
    positive LLR at sequential index ``s`` is claiming ``1`` here.
    """
    user = truth.user_bits.get(key)
    if user is None:
        return None
    bank = stream_fact(row, key[3]).rung_children
    printed = tile_codec.encode_frame(np.asarray(user, np.uint8), bank)
    printed = printed ^ mother_mod.dither_of(row, key)
    printed.setflags(write=False)
    return printed


def true_codeword(truth: Truth, key: Key, mother: Mother) -> np.ndarray | None:
    """The GT MOTHER codeword: ``ldpc.encode(user ‖ crc ‖ 0, code)``."""
    user = truth.user_bits.get(key)
    if user is None:
        return None
    code = CODES[mother.rate_id]
    info = np.zeros(code.k_bits, np.uint8)
    user = np.asarray(user, np.uint8)
    info[:mother.active] = np.concatenate(
        (user, tile_codec.crc32_bits(user)))
    return ldpc.encode(info, code)


def sequential_cells(row: Any, key: Key) -> np.ndarray:
    """(payload_cells, 2) TILE-LOCAL cell of every sequential position.

    `analyzer.ladder` already derives this for L7b's run erasure; it is
    the same permutation inverse and forking it would be the classic bug.
    """
    return ladder_mod._cell_grid(row, key)


# ---------------------------------------------------------- the statistics

def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    ones = np.asarray(labels, bool)
    n1 = int(np.count_nonzero(ones))
    n0 = int(ones.size - n1)
    if n0 == 0 or n1 == 0:
        return float("nan")
    order = np.argsort(scores, kind="stable")
    ranks = np.empty(scores.size, np.float64)
    sorted_scores = scores[order]
    start = 0
    while start < sorted_scores.size:
        stop = start + 1
        while (stop < sorted_scores.size
               and sorted_scores[stop] == sorted_scores[start]):
            stop += 1
        ranks[order[start:stop]] = 0.5 * (start + stop - 1) + 1.0
        start = stop
    return float((ranks[ones].sum() - n1 * (n1 + 1) / 2.0) / (n0 * n1))


def _d_prime(values: np.ndarray, labels: np.ndarray) -> float:
    ones = np.asarray(labels, bool)
    if not np.any(ones) or np.all(ones):
        return float("nan")
    a, b = values[ones], values[~ones]
    var = 0.5 * (float(np.var(b, ddof=1) if b.size > 1 else 0.0)
                 + float(np.var(a, ddof=1) if a.size > 1 else 0.0))
    if var <= 0.0:
        return float("nan")
    return float((a.mean() - b.mean()) / math.sqrt(var))


def _information_terms(llr: np.ndarray, bits: np.ndarray) -> np.ndarray:
    """Per-cell soft information in BITS: ``1 − log2(1 + exp(−L·(2b−1)))``.

    NOTE ON DESIGN §1's SPELLING.  The design writes the exponent as
    ``−LLR·(1−2b)``.  That is the right formula under the convention
    "positive LLR claims 0"; holo3's convention is the opposite
    (`tile_codec`: positive = bit 1, PLAN §1.3), so the aligned quantity
    is ``L·(2b−1)`` and the design's sign is a transcription slip, not a
    different statistic.  Written the design's way, a confidently
    CORRECT cell would score −57 bits instead of +1 (pinned by
    `test_information_rate_is_one_bit_per_cell_when_the_llr_is_certain`).
    """
    signed = np.asarray(llr, np.float64) * (
        2.0 * np.asarray(bits, np.float64) - 1.0)
    # log2(1 + exp(-x)) computed stably for both signs of x.
    x = -signed
    penalty = np.where(x > 0.0, x + np.log1p(np.exp(-np.abs(x))),
                       np.log1p(np.exp(-np.abs(x)))) / math.log(2.0)
    return 1.0 - penalty


def soft_information_rate(llr: np.ndarray, bits: np.ndarray,
                          active_bits: int, *, seed: int = 0,
                          draws: int = BOOTSTRAP_DRAWS) -> dict:
    """``R = Î·n_observed / active_bits`` with a bootstrap upper bound.

    ``Î`` is the mean per-cell information over the OBSERVED cargo cells
    only, so the count that multiplies it is the same count it was
    averaged over.  The bound is the ``BOOTSTRAP_LEVEL`` quantile of the
    resampled mean; the draw is a hash of the seed (DESIGN §0).
    """
    terms = _information_terms(llr, bits)
    n = int(terms.size)
    if n == 0 or active_bits <= 0:
        return {"information_bits_per_cell": None, "R": None,
                "R_upper": None, "n_observed": n,
                "active_bits": int(active_bits)}
    mean = float(terms.mean())
    rate = mean * n / float(active_bits)
    rng = np.random.default_rng(np.uint64(seed) & np.uint64((1 << 63) - 1))
    picks = rng.integers(0, n, size=(int(draws), n))
    means = terms[picks].mean(axis=1)
    upper = float(np.quantile(means, BOOTSTRAP_LEVEL)) * n / float(active_bits)
    return {"information_bits_per_cell": mean, "R": float(rate),
            "R_upper": upper, "R_bootstrap_draws": int(draws),
            "n_observed": n, "active_bits": int(active_bits)}


def _clustering(cells_yx: np.ndarray, n_candidates: int) -> dict:
    """Mean nearest-wrong distance against the uniform expectation.

    For ``n`` points thrown uniformly over an area ``A`` the mean
    nearest-neighbour distance is ``0.5·sqrt(A/n)``; the ratio below 1
    says the wrong cells cluster (L7b's premise), above 1 that they
    repel.  This is L7b's SCORER, never its input (DESIGN §7).
    """
    points = np.asarray(cells_yx, np.float64)
    n = int(points.shape[0])
    if n < 2 or n_candidates <= 0:
        return {"n_wrong": n, "mean_nearest_wrong": None,
                "uniform_expectation": None, "clustering_ratio": None}
    delta = points[:, None, :] - points[None, :, :]
    dist = np.sqrt((delta ** 2).sum(axis=2))
    np.fill_diagonal(dist, np.inf)
    nearest = float(dist.min(axis=1).mean())
    expected = 0.5 * math.sqrt(float(n_candidates) / n)
    return {"n_wrong": n, "mean_nearest_wrong": nearest,
            "uniform_expectation": expected,
            "clustering_ratio": nearest / expected if expected else None}


# ------------------------------------------------------------- the splits

def _footprint_row_of_cell(lfp: LaneFootprint) -> dict[int, int]:
    cells = np.asarray(lfp.tile.page_cells_yx, np.int64)
    return {int(y) * (1 << 20) + int(x): index
            for index, (y, x) in enumerate(cells)}


def _neighbour_ink(field_bits: np.ndarray, cells_yx: np.ndarray) -> np.ndarray:
    """True 8-neighbour ink count of one plane at the given page cells."""
    height, width = field_bits.shape
    ys = np.asarray(cells_yx[:, 0], np.int64)
    xs = np.asarray(cells_yx[:, 1], np.int64)
    total = np.zeros(ys.size, np.int64)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = ys + dy, xs + dx
            inside = (ny >= 0) & (ny < height) & (nx >= 0) & (nx < width)
            take = np.zeros(ys.size, np.int64)
            take[inside] = field_bits[ny[inside], nx[inside]]
            total += take
    return total


def _group_error(wrong: np.ndarray, groups: np.ndarray) -> dict:
    out: dict[str, dict] = {}
    for value in np.unique(groups):
        mask = groups == value
        out[str(int(value))] = {
            "n": int(np.count_nonzero(mask)),
            "cell_error": float(np.mean(wrong[mask])),
        }
    return out


# --------------------------------------------------------- score_evidence

def score_evidence(evidence: Evidence, truth: Truth, frame: KnownFrame,
                   lfp: LaneFootprint, row: Any, key: Key, *,
                   others: Sequence[Evidence] = (), seed: int = 0,
                   bootstrap_draws: int = BOOTSTRAP_DRAWS) -> dict:
    """Everything DESIGN §7 asks of one (tile-stream, lane, arm) row.

    `others` are the SAME key's other lanes; when there are any, the
    capture-agreement column says what fraction of them are wrong at the
    cells this lane got wrong (print-frozen error looks like agreement,
    capture noise does not).
    """
    page, ty, tx, stream_id = key
    plane = {"C": 0, "M": 1, "Y": 2}[str(stream_id)]
    bits = true_sequential(truth, row, key)
    if bits is None:
        return {"scoreable": False, "reason": "address outside the GT domain",
                "arm": evidence.arm, "lane": (evidence.lane[0][:12],
                                              int(evidence.lane[1]))}
    llr = np.asarray(evidence.llr_sequential, np.float64)
    observed = np.asarray(evidence.observed, bool)
    out: dict[str, Any] = {
        "scoreable": True,
        "arm": evidence.arm,
        "lane": (evidence.lane[0][:12], int(evidence.lane[1])),
        "n_observed": int(np.count_nonzero(observed)),
    }
    if not np.any(observed):
        out["reason"] = "no observed cargo cell"
        return out

    values = llr[observed]
    labels = bits[observed].astype(np.uint8)
    wrong_map = (values > 0.0) != (labels > 0)
    median = float(np.median(values))
    wrong_median = (values > median) != (labels > 0)
    out.update({
        "cell_error_map": float(np.mean(wrong_map)),
        "cell_error_median_threshold": float(np.mean(wrong_median)),
        "median_llr": median,
        "d_prime": _d_prime(values, labels),
        "auc": _auc(values, labels),
        "true_ones_fraction": float(np.mean(labels)),
    })
    bank = stream_fact(row, str(stream_id)).rung_children
    out.update(soft_information_rate(
        values, labels, tile_codec.bank_active_bits(bank),
        seed=seed, draws=bootstrap_draws))

    # --- where the wrong cells are -------------------------------------
    grid = sequential_cells(row, key)                    # tile-local (y, x)
    seq_index = np.flatnonzero(observed)
    local = grid[seq_index]
    page_cells = np.stack((local[:, 0] + int(ty) * TILE_CELLS,
                           local[:, 1] + int(tx) * TILE_CELLS), axis=1)

    field = truth.fields.get(int(page))
    if field is not None:
        sibling_planes = [index for index in range(3) if index != plane]
        sib = field.plane_bits[sibling_planes[0]][page_cells[:, 0],
                                                  page_cells[:, 1]].astype(int)
        sib = sib + 2 * field.plane_bits[sibling_planes[1]][
            page_cells[:, 0], page_cells[:, 1]].astype(int)
        lookup = _footprint_row_of_cell(lfp)
        rows = np.array([lookup.get(int(y) * (1 << 20) + int(x), -1)
                         for y, x in page_cells], np.int64)
        known_sib = np.zeros(rows.size, bool)
        inside = rows >= 0
        known_sib[inside] = np.asarray(frame.siblings, bool)[rows[inside]]
        by_state: dict[str, dict] = {}
        for flag, name in ((True, "certified"), (False, "uncertified")):
            pick = known_sib == flag
            if not np.any(pick):
                continue
            for state, stats in _group_error(wrong_map[pick],
                                             sib[pick]).items():
                by_state[f"{state}/{name}"] = stats
        out["by_sibling_state"] = by_state
        out["by_context_bin"] = _group_error(
            wrong_map, _neighbour_ink(field.plane_bits[plane], page_cells))
    else:
        out["by_sibling_state"] = {}
        out["by_context_bin"] = {}

    out["clustering"] = _clustering(local[wrong_map],
                                    TILE_CELLS * TILE_CELLS)

    # --- capture agreement on the wrong cells --------------------------
    peers = [item for item in others if item.lane != evidence.lane]
    if peers and np.any(wrong_map):
        wrong_seq = seq_index[wrong_map]
        agree: list[float] = []
        for cell in wrong_seq:
            seen = 0
            same = 0
            for peer in peers:
                if not bool(np.asarray(peer.observed, bool)[cell]):
                    continue
                seen += 1
                decision = float(peer.llr_sequential[cell]) > 0.0
                if decision != bool(bits[cell]):
                    same += 1
            if seen:
                agree.append(same / seen)
        out["capture_agreement_on_wrong"] = (
            float(np.mean(agree)) if agree else None)
        out["n_peer_lanes"] = len(peers)
    else:
        out["capture_agreement_on_wrong"] = None
        out["n_peer_lanes"] = len(peers)
    return out


# ------------------------------------------------------------- score_rung

def is_direct(rung: str) -> bool:
    """Is this a DIRECT rung (one proposal) or a LIST rung?"""
    base = str(rung).split(":")[0].split(".")[0]
    return any(base.startswith(name) for name in DIRECT_RUNGS)


def verdict_against_truth(rung: str, verdict: str, n_bad: int | None) -> str:
    """The scored verdict of a gate-passing certificate (DESIGN §0).

    `n_bad` is how many user bits disagree with the payload, or `None`
    when the comparison could not be made.  A non-certificate keeps its
    blind verdict untouched — this function only ever downgrades.
    """
    if verdict not in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST):
        return verdict
    if n_bad is None:
        return VERDICT_UNSCOREABLE
    if n_bad == 0:
        return verdict
    return VERDICT_WRONG if is_direct(rung) else VERDICT_FALSE_ACCEPT


def _get(item: Any, name: str, default: Any = None) -> Any:
    """One reader for both shapes a rung arrives in.

    A live `RungResult` (a control, a test) and a ledger's rung dict
    (the offline scorer's own input) carry the same columns under the
    same names; only the access differs.
    """
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def packed_hard(item: Any) -> bytes | None:
    """The rung's exit hard vector, from either carrier.

    `RungResult.detail["hard_packed"]` is raw bytes; the ledger stores
    the same 512 bytes base64 under `hard_packed_b64`, because JSON has
    no bytes and hex would be half again as large.
    """
    detail = _get(item, "detail", {}) or {}
    packed = detail.get("hard_packed")
    if packed is not None:
        return bytes(packed)
    encoded = detail.get("hard_packed_b64")
    return None if encoded is None else base64.b64decode(str(encoded))


def score_rung(rung_result: Any, truth: Truth, key: Key,
               mother: Mother | None = None, *,
               user_bits: Any = None) -> dict:
    """Bits wrong at exit with all four denominators, plus the verdict.

    `rung_result` is a live `RungResult` or a ledger rung dict.  The
    bits-wrong columns need the exit hard vector, which the ladder packs
    under `keep_hard` (ON by default in the driver) and the ledger
    carries base64; without it the row still carries the blind
    `unsat_at_exit` and, for a certifying rung, the user-bit comparison.

    `user_bits` is the certificate this rung minted.  A `RungResult`
    carries its own; a ledger rung dict does not (only the ROW does), so
    the offline scorer passes the row's bits in for the certifying rung.
    """
    truth_bits = truth.user_bits.get(key)
    bits = _get(rung_result, "user_bits") if user_bits is None else user_bits
    verdict = str(_get(rung_result, "verdict"))
    n_bad: int | None = None
    if bits is not None:
        bits = np.asarray(bits, np.uint8).ravel()
        if truth_bits is not None and bits.size == np.asarray(
                truth_bits).size:
            n_bad = int(np.count_nonzero(
                np.asarray(truth_bits, np.uint8).ravel() != bits))
    rung = str(_get(rung_result, "rung"))
    out: dict[str, Any] = {
        "rung": rung,
        "blind_verdict": verdict,
        # A rung with no bits in hand is not a certificate to adjudicate:
        # it keeps the blind verdict the gate gave it.
        "verdict": (verdict_against_truth(rung, verdict, n_bad)
                    if bits is not None else verdict),
        "unsat_at_exit": int(_get(rung_result, "unsat_at_exit", -1)),
        "n_iters": int(_get(rung_result, "n_iters", 0)),
        "seconds": float(_get(rung_result, "seconds", 0.0)),
        "crc_consults_distinct": int(
            _get(rung_result, "crc_consults_distinct", 0)),
        "gt_bits_wrong_user": n_bad,
    }
    packed = packed_hard(rung_result)
    if packed is None or mother is None or truth_bits is None:
        return out
    code = CODES[mother.rate_id]
    hard = np.unpackbits(np.frombuffer(packed, np.uint8),
                         count=code.n_bits).astype(np.uint8)
    codeword = true_codeword(truth, key, mother)
    if codeword is None:
        return out
    diff = hard != codeword
    active = int(mother.active)
    user_bit_count = active - tile_codec.CRC_BITS
    out.update({
        "bits_wrong_mother": int(np.count_nonzero(diff)),
        "bits_wrong_transmitted": int(np.count_nonzero(
            diff[np.asarray(mother.transmitted, np.int64)])),
        "bits_wrong_active": int(np.count_nonzero(diff[:active])),
        "bits_wrong_user_frame": int(np.count_nonzero(diff[:user_bit_count])),
        "denominators": {"mother": int(code.n_bits),
                         "transmitted": int(mother.transmitted.size),
                         "active": active, "user": int(user_bit_count)},
    })
    return out


# ------------------------------------------------------------- waterfall

def _r05_r50(values: np.ndarray, certified: np.ndarray
             ) -> tuple[float | None, float | None, list]:
    """Isotonic ``P(certify | R)`` and the R at which it crosses .05/.50."""
    if values.size < 4 or len(np.unique(certified)) < 2:
        return None, None, []
    knots, probs = pava._pava_nodes(values, certified.astype(np.float64))
    curve = [(float(k), float(p)) for k, p in zip(knots, probs)]
    out: list[float | None] = []
    for level in (0.05, 0.50):
        if probs[-1] < level or probs[0] > level:
            out.append(None)
            continue
        out.append(float(np.interp(level, probs, knots)))
    return out[0], out[1], curve


def waterfall(rows: Iterable[Mapping[str, Any]]) -> dict:
    """``P(certify | R)`` per stream and rung, with R05 and R50.

    Each input row is ``{"stream_id", "R", "rung", "certified"}`` — the
    flattened side table the ledger already holds, one entry per
    (tile-stream, rung) that was actually attempted.
    """
    buckets: dict[tuple[str, str], list[tuple[float, bool]]] = {}
    for row in rows:
        rate = row.get("R")
        if rate is None:
            continue
        buckets.setdefault(
            (str(row.get("stream_id")), str(row.get("rung"))), []).append(
                (float(rate), bool(row.get("certified"))))
    out: dict[str, Any] = {}
    for (stream_id, rung), items in sorted(buckets.items()):
        values = np.array([value for value, _ok in items], np.float64)
        certified = np.array([ok for _v, ok in items], bool)
        r05, r50, curve = _r05_r50(values, certified)
        out[f"{stream_id}/{rung}"] = {
            "n": int(values.size),
            "n_certified": int(np.count_nonzero(certified)),
            "R_median": float(np.median(values)),
            "R05": r05, "R50": r50, "curve": curve,
        }
    return out
