"""R11 — block decodes of the receiver's own LDPC code with LLRs resampled from real cells by true label.

What: a TRIAL draws 3976 states iid uniform over {W, C, M, Y} and, per position, one payload cell of that state
from per-state shuffled pools of one region (overflow drawn with replacement and counted), so a position's hi and
lo LLRs come from the SAME cell (the hi/lo dependence the conditioned decodes need).  Per stream (hi, lo) and
rung (r0700 / r0775 / r0850, bank ((rung, 120),): 3976 transmitted bits, user bits k - 152) random user bits are
encoded (holo.receiver.format.tile_codec.encode_frame), the dither is d = label XOR codeword (random dithers make
the label bits uniform and independent of the codeword, as the keystream does), and the code LLR is
LLR_label x (1 - 2d) (cmy8_decode_stream's un-dither).  Modes: BICM = the stream's marginal form; COND = the
stream given the sibling's TRUE label bit (hi|lo=b, lo|hi=b).  SUCCESS = decode_frame ok (syndrome and CRC) and
the user bits equal; a CRC-passing mismatch is a FALSE ACCEPT.  Failed decodes are re-run at 150 iterations
(tiles.retry150's budget) as a separate column.  Any-stage (R5's both orders):
    hi_cert = hi_B(R_h) or (lo_B(R_l) and hi_C(R_h));  lo_cert = lo_B(R_l) or (hi_B(R_h) and lo_C(R_l))
tile yield = S(R_h) hi_cert + S(R_l) lo_cert, S = k - 153.
Why: the yield proxy closest to certified tiles.  How: every arm of a trial shares its cells, user bits and
codewords; identical code-LLR vectors are decoded once (digest cache); trials run on a thread pool (the
free-threaded interpreter runs the numpy decoder in parallel; the decoder holds no shared state).
"""
from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

import numpy as np

from holo.receiver.format.tile_codec import bank_user_bits, decode_frame, encode_frame
from holo.receiver.plugins.tiles import BASELINE_BP_MAX_ITERS, BP_ALPHA, RETRY_BP_MAX_ITERS
from measure.cmy_calibration.chains import HI, LO
from measure.cmy_calibration.config import FOUNTAIN_BITS, RUNGS, SHORTEN, YIELD_PAIRS

N_TX = 4096 - SHORTEN
STREAMS = ("hi", "lo")
MODES = ("bicm", "cond")


def bank(rung: str) -> tuple[tuple[str, int], ...]:
    return ((rung, SHORTEN),)


@dataclass
class Trial:
    key: tuple[int, ...]
    state: np.ndarray                                   # (3976,) manifest state per position
    users: dict[tuple[str, str], np.ndarray]
    arms: dict[str, np.ndarray] = field(default_factory=dict)   # arm -> (3976, 6) label LLRs (FORMS order)
    overflow: int = 0
    streams: tuple[str, ...] = STREAMS
    modes: tuple[str, ...] = MODES
    rungs: tuple[str, ...] = RUNGS


def draw_positions(rng: np.random.Generator, payload: np.ndarray, payload_state: np.ndarray
                   ) -> tuple[np.ndarray, np.ndarray, int]:
    """(cell index per position, state per position, overflow count): states iid uniform, one payload cell of
    that state per position, without replacement from a shuffled pool, overflow with replacement."""
    state = rng.integers(0, 4, N_TX)
    cells = np.empty(N_TX, np.int64)
    overflow = 0
    for s in range(4):
        pos = np.flatnonzero(state == s)
        pool = rng.permutation(payload[payload_state == s])
        if pool.size == 0:
            raise ValueError(f"region payload has no cell of state {s}")
        take = min(pos.size, pool.size)
        cells[pos[:take]] = pool[:take]
        if pos.size > take:
            cells[pos[take:]] = rng.choice(pool, pos.size - take, replace=True)
            overflow += pos.size - take
    return cells, state, overflow


def draw_users(rng: np.random.Generator, rungs: tuple[str, ...] = RUNGS) -> dict[tuple[str, str], np.ndarray]:
    return {(s, r): rng.integers(0, 2, bank_user_bits(bank(r)), dtype=np.uint8) for s in STREAMS for r in rungs}


def label_llrs(forms: np.ndarray, state: np.ndarray, stream: str, mode: str) -> np.ndarray:
    if mode == "bicm":
        return forms[:, 0 if stream == "hi" else 1]
    if stream == "hi":
        return np.where(LO[state] == 0, forms[:, 2], forms[:, 3])
    return np.where(HI[state] == 0, forms[:, 4], forms[:, 5])


def run_trial(trial: Trial, max_iters: int = BASELINE_BP_MAX_ITERS, retry_iters: int = RETRY_BP_MAX_ITERS,
              alpha: float = BP_ALPHA, retry: bool = True) -> dict[str, dict[tuple[str, str, str], tuple[int, ...]]]:
    """arm -> (stream, mode, rung) -> (success, false_accept, retry_success, n_iters)."""
    cache: dict[bytes, tuple[int, int, int, int]] = {}
    out: dict[str, dict[tuple[str, str, str], tuple[int, ...]]] = {}
    labels = {"hi": HI[trial.state], "lo": LO[trial.state]}
    dith: dict[tuple[str, str], np.ndarray] = {}
    for st in trial.streams:
        for r in trial.rungs:
            cw = encode_frame(trial.users[(st, r)], bank(r))
            dith[(st, r)] = 1.0 - 2.0 * (labels[st] ^ cw).astype(np.float64)
    for arm, forms in trial.arms.items():
        res: dict[tuple[str, str, str], tuple[int, ...]] = {}
        for st in trial.streams:
            for mode in trial.modes:
                lab = np.asarray(label_llrs(forms, trial.state, st, mode), np.float64)
                for r in trial.rungs:
                    code = lab * dith[(st, r)]
                    dig = hashlib.blake2b(code.tobytes() + r.encode(), digest_size=16).digest()
                    if dig not in cache:
                        user = trial.users[(st, r)]
                        got = decode_frame(code, bank(r), max_iters, alpha)
                        ok = bool(got[0]) and np.array_equal(got[4], user)
                        fa = bool(got[0]) and not ok
                        ok150 = 0
                        if not ok and retry:
                            g2 = decode_frame(code, bank(r), retry_iters, alpha)
                            ok150 = int(bool(g2[0]) and np.array_equal(g2[4], user))
                            fa = fa or (bool(g2[0]) and not ok150)
                        cache[dig] = (int(ok), int(fa), int(ok or ok150), int(got[1][0][0]))
                    res[(st, mode, r)] = cache[dig]
        out[arm] = res
    return out


def run_trials(trials: Iterable[Trial], workers: int, batch: int = 32, **kw: Any
               ) -> Iterator[tuple[Trial, dict[str, dict[tuple[str, str, str], tuple[int, ...]]]]]:
    """Yields (trial, result) in order, building trials lazily in batches to bound memory."""
    it = iter(trials)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        while True:
            chunk = [t for _, t in zip(range(batch * max(1, workers)), it)]
            if not chunk:
                return
            for t, res in zip(chunk, pool.map(lambda tr: run_trial(tr, **kw), chunk)):
                yield t, res


# ---------------------------------------------------------------- aggregation

@dataclass
class Outcomes:
    """Per arm: (stream, mode, rung) -> int8 (T,) success / false accept / retry success, and overflow."""
    arms: dict[str, dict[tuple[str, str, str], np.ndarray]] = field(default_factory=dict)
    false_accepts: dict[str, dict[tuple[str, str, str], np.ndarray]] = field(default_factory=dict)
    retry: dict[str, dict[tuple[str, str, str], np.ndarray]] = field(default_factory=dict)
    overflow: list[float] = field(default_factory=list)

    def add(self, trial: Trial, res: dict[str, dict[tuple[str, str, str], tuple[int, ...]]]) -> None:
        self.overflow.append(trial.overflow / N_TX)
        for arm, d in res.items():
            for key, v in d.items():
                self.arms.setdefault(arm, {}).setdefault(key, []).append(v[0])
                self.false_accepts.setdefault(arm, {}).setdefault(key, []).append(v[1])
                self.retry.setdefault(arm, {}).setdefault(key, []).append(v[2])

    def frozen(self) -> "Outcomes":
        def fz(d: dict[str, dict[tuple[str, str, str], Any]]) -> dict[str, dict[tuple[str, str, str], np.ndarray]]:
            return {a: {k: np.asarray(v, np.int8) for k, v in dd.items()} for a, dd in d.items()}
        return Outcomes(fz(self.arms), fz(self.false_accepts), fz(self.retry), list(self.overflow))


def any_stage(o: dict[tuple[str, str, str], np.ndarray], rung_hi: str, rung_lo: str
              ) -> tuple[np.ndarray, np.ndarray]:
    """(hi_cert, lo_cert) per trial for one arm at (R_h, R_l)."""
    hb, lb = o[("hi", "bicm", rung_hi)].astype(bool), o[("lo", "bicm", rung_lo)].astype(bool)
    hc = o.get(("hi", "cond", rung_hi))
    lc = o.get(("lo", "cond", rung_lo))
    hc = np.zeros_like(hb) if hc is None else hc.astype(bool)
    lc = np.zeros_like(lb) if lc is None else lc.astype(bool)
    return hb | (lb & hc), lb | (hb & lc)


def tile_yield(o: dict[tuple[str, str, str], np.ndarray], rung_hi: str, rung_lo: str) -> np.ndarray:
    h, l_ = any_stage(o, rung_hi, rung_lo)
    return FOUNTAIN_BITS[rung_hi] * h.astype(np.float64) + FOUNTAIN_BITS[rung_lo] * l_.astype(np.float64)


def or_outcomes(a: dict[tuple[str, str, str], np.ndarray], b: dict[tuple[str, str, str], np.ndarray]
                ) -> dict[tuple[str, str, str], np.ndarray]:
    return {k: (a[k].astype(bool) | b[k].astype(bool)).astype(np.int8) for k in a if k in b}


def pack_bits(v: np.ndarray) -> str:
    return np.packbits(np.asarray(v, np.uint8)).tobytes().hex()


def unpack_bits(h: str, n: int) -> np.ndarray:
    return np.unpackbits(np.frombuffer(bytes.fromhex(h), np.uint8))[:n].astype(bool)


def yield_pairs_for(rungs: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(p for p in YIELD_PAIRS if p[0] in rungs and p[1] in rungs)


# ---------------------------------------------------------------- timing

def time_decodes(lab_llrs: np.ndarray, state: np.ndarray, stream: str, rungs: tuple[str, ...], n_each: int,
                 rng: np.random.Generator, max_tries: int = 400) -> dict[str, dict[str, Any]]:
    """Median wall (ms) of n_each successful and n_each failed decodes per rung from real label LLRs at random
    positions; when real failures are too rare within max_tries, failures are made by flipping 15 % of the LLR
    signs (a failure costs 2 x max_iters iterations whatever its cause) — recorded as 'fail_source'."""
    out: dict[str, dict[str, Any]] = {}
    labels = (HI if stream == "hi" else LO)[state]
    for r in rungs:
        ok_ms: list[float] = []
        fail_ms: list[float] = []
        tries = 0
        while (len(ok_ms) < n_each or len(fail_ms) < n_each) and tries < max_tries:
            tries += 1
            pick = rng.integers(0, lab_llrs.size, N_TX)
            user = rng.integers(0, 2, bank_user_bits(bank(r)), dtype=np.uint8)
            cw = encode_frame(user, bank(r))
            code = lab_llrs[pick] * (1.0 - 2.0 * (labels[pick] ^ cw))
            t0 = time.perf_counter()
            got = decode_frame(code, bank(r), BASELINE_BP_MAX_ITERS, BP_ALPHA)
            ms = 1e3 * (time.perf_counter() - t0)
            (ok_ms if got[0] and np.array_equal(got[4], user) else fail_ms).append(ms)
        source = "real"
        while len(fail_ms) < n_each:
            source = "sign-flipped"
            pick = rng.integers(0, lab_llrs.size, N_TX)
            user = rng.integers(0, 2, bank_user_bits(bank(r)), dtype=np.uint8)
            cw = encode_frame(user, bank(r))
            code = lab_llrs[pick] * (1.0 - 2.0 * (labels[pick] ^ cw)) * np.where(rng.random(N_TX) < 0.15, -1, 1)
            t0 = time.perf_counter()
            got = decode_frame(code, bank(r), BASELINE_BP_MAX_ITERS, BP_ALPHA)
            ms = 1e3 * (time.perf_counter() - t0)
            if not got[0]:
                fail_ms.append(ms)
        out[r] = {"ok_ms": float(np.median(ok_ms)) if ok_ms else float("nan"),
                  "fail_ms": float(np.median(fail_ms)), "n_ok": len(ok_ms), "n_fail": len(fail_ms),
                  "fail_source": source}
    return out
