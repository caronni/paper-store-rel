"""A batched belief-propagation decoder in mlx, mirroring ldpc._bp_loop.

The port is structural, not algorithmic: same schedule, same two phases
(offset-min-sum, then sum-product on the failures), same clips and
constants, same stopping rule.  What changes is the layout.

``_bp_loop`` walks the edge list with ``np.add.reduceat`` /
``np.minimum.reduceat``, which needs the edges sorted by check and a
serial segment scan.  Neither maps to a GPU.  So the code's irregular
edge lists are PADDED ONCE into two dense index tensors —
``(m, max_check_degree)`` and ``(n, max_var_degree)``, short rows filled
with a null edge — and every reduction becomes an axis reduction over a
dense gather.  Two consequences worth stating up front:

* No scatter-add, no atomics.  Gather-then-reduce is order-fixed by
  construction, which is what gives the determinism gate a chance.
* The null edge carries the identity of whichever reduction reads it:
  ``+inf`` on the check side (never wins a min, never counts as
  negative, and ``|tanh(clip(inf)/2)| == 1`` so its log-domain term is
  exactly 0) and ``0`` on the variable side.

PRECISION.  mlx computes on the GPU in float32; float64 arrays are
silently demoted at construction.  The CPU decoder is float64
throughout.  This is a real numerical difference, not an implementation
detail to be tidied away, and it is what the equivalence gate is
measuring.

Nothing here is imported by holo3.  It is a measurement artefact.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass

import mlx.core as mx
import numpy as np

from holo3.lib.ldpc import LLR_CLIP, LLR_KNOWN, Code

TANH_CLIP = 40.0
LOG_FLOOR = 1e-300
EXP_HI = -1e-16
EXP_LO = -700.0
ARCTANH_BOUND = 0.999_999_999_999


@dataclass(frozen=True)
class BatchedCode:
    """A code's edge lists, padded into dense gather tensors."""
    rate_id: str
    n_bits: int
    k_bits: int
    n_checks: int
    n_edges: int
    chk_idx: mx.array          # (m, dmax)   edge ids, null = n_edges
    chk_valid: mx.array        # (m, dmax)   float mask, 1.0 on real edges
    var_of_edge: mx.array      # (E,)        variable id per edge
    var_idx: mx.array          # (n, dvmax)  edge ids, null = n_edges
    flat_from_mat: mx.array    # (E,)        matrix-flat position per edge
    col_index: mx.array        # (1, dmax)   column ordinals, for tie-break


def _pad_groups(members: np.ndarray, n_groups: int,
                null: int) -> tuple[np.ndarray, np.ndarray]:
    """Rows of `members` grouped by an already-sorted group key."""
    counts = np.bincount(members, minlength=n_groups)
    width = int(counts.max())
    index = np.full((n_groups, width), null, np.int32)
    valid = np.zeros((n_groups, width), np.float32)
    order = np.argsort(members, kind="stable")
    within = np.arange(members.size) - np.repeat(
        np.concatenate(([0], np.cumsum(counts)[:-1])), counts)
    index[members[order], within] = order.astype(np.int32)
    valid[members[order], within] = 1.0
    return index, valid


def prepare(code: Code) -> BatchedCode:
    chk = np.asarray(code.edge_chk, np.int64)
    var = np.asarray(code.edge_var, np.int64)
    n_edges = int(chk.size)
    n_checks = int(code.n_bits - code.k_bits)
    chk_idx, chk_valid = _pad_groups(chk, n_checks, n_edges)
    var_idx, _var_valid = _pad_groups(var, int(code.n_bits), n_edges)
    width = chk_idx.shape[1]
    flat = np.full(n_edges, -1, np.int64)
    rows, columns = np.nonzero(chk_idx != n_edges)
    flat[chk_idx[rows, columns]] = rows * width + columns
    if np.any(flat < 0):
        raise ValueError("padding lost an edge")
    return BatchedCode(
        rate_id=code.rate_id, n_bits=int(code.n_bits),
        k_bits=int(code.k_bits), n_checks=n_checks, n_edges=n_edges,
        chk_idx=mx.array(chk_idx),
        chk_valid=mx.array(chk_valid),
        var_of_edge=mx.array(var.astype(np.int32)),
        var_idx=mx.array(var_idx),
        flat_from_mat=mx.array(flat.astype(np.int32)),
        col_index=mx.array(
            np.arange(width, dtype=np.float32)[None, :]))


def prepare_llr(llr: np.ndarray) -> np.ndarray:
    """The host-side preamble of ldpc.decode: clip, pin, negate."""
    x = np.asarray(llr, np.float64)
    out = np.clip(x, -LLR_CLIP, LLR_CLIP)
    out[np.isposinf(x)] = LLR_KNOWN
    out[np.isneginf(x)] = -LLR_KNOWN
    return -out


def _check_matrix(edge_values: mx.array, batched: BatchedCode,
                  null: float) -> mx.array:
    """(B, E) edge values -> (B, m, dmax), padding slots set to `null`."""
    batch = edge_values.shape[0]
    padded = mx.concatenate(
        [edge_values, mx.full((batch, 1), null, edge_values.dtype)], axis=1)
    return padded[:, batched.chk_idx]


def _to_edges(matrix: mx.array, batched: BatchedCode) -> mx.array:
    """(B, m, dmax) -> (B, E), undoing the padding."""
    batch = matrix.shape[0]
    return matrix.reshape(batch, -1)[:, batched.flat_from_mat]


def _var_sum(edge_values: mx.array, batched: BatchedCode) -> mx.array:
    batch = edge_values.shape[0]
    padded = mx.concatenate(
        [edge_values, mx.zeros((batch, 1), edge_values.dtype)], axis=1)
    return padded[:, batched.var_idx].sum(axis=2)


def bp_batch(L: mx.array, batched: BatchedCode, max_iters: int,
             alpha: float, sum_product: bool, sync_every: int = 1
             ) -> tuple[mx.array, mx.array, mx.array]:
    """One batched run of the loop in ldpc._bp_loop.

    Returns (hard bits (B, n) uint8, syndrome_ok (B,) bool,
    n_iters (B,) int32).  A tile whose syndrome closes is frozen: its
    Ltot stops moving, so its hard bits are the ones it closed with, and
    its iteration count stops advancing.

    ``sync_every`` only changes how often the host asks whether any tile
    is still live.  Because closed tiles are frozen, a later question
    cannot change any answer — it only costs iterations the batch did
    not need.  Results are invariant; wall time is not.
    """
    batch = L.shape[0]
    c2v = mx.zeros((batch, batched.n_edges), L.dtype)
    Ltot = L
    live = mx.ones((batch,), mx.bool_)
    closed = mx.zeros((batch,), mx.bool_)
    n_iters = mx.zeros((batch,), mx.int32)
    for iteration in range(max_iters + 1):
        hard = (Ltot < 0).astype(mx.float32)
        hard_e = hard[:, batched.var_of_edge]
        parity = _check_matrix(hard_e, batched, 0.0).sum(axis=2) % 2
        clean = parity.max(axis=1) == 0
        closed = mx.logical_or(closed, mx.logical_and(live, clean))
        live = mx.logical_and(live, mx.logical_not(clean))
        if iteration == max_iters:
            break
        if iteration % sync_every == 0:
            mx.eval(live)
            if not bool(mx.any(live).item()):
                break
        n_iters = n_iters + live.astype(mx.int32)
        v2c = Ltot[:, batched.var_of_edge] - c2v
        matrix = _check_matrix(v2c, batched, mx.inf)
        negative = (matrix < 0).astype(mx.float32)
        par_sign = 1.0 - 2.0 * (negative.sum(axis=2) % 2)
        sign = mx.where(matrix < 0, -1.0, 1.0)
        if sum_product:
            t = mx.abs(mx.tanh(mx.clip(matrix, -TANH_CLIP, TANH_CLIP) / 2.0))
            lt = mx.log(mx.clip(t, LOG_FLOOR, 1.0))
            lsum = lt.sum(axis=2)
            ext = mx.exp(mx.clip(lsum[:, :, None] - lt, EXP_LO, EXP_HI))
            product = mx.clip(par_sign[:, :, None] * sign * ext,
                              -ARCTANH_BOUND, ARCTANH_BOUND)
            update = 2.0 * mx.arctanh(product)
        else:
            magnitude = mx.abs(matrix)
            min1 = magnitude.min(axis=2)
            at_min = magnitude == min1[:, :, None]
            first = mx.where(at_min, batched.col_index[None, :, :],
                             float(magnitude.shape[2])).min(axis=2)
            is_first = batched.col_index[None, :, :] == first[:, :, None]
            min2 = mx.where(is_first, mx.inf, magnitude).min(axis=2)
            ext = mx.where(is_first, min2[:, :, None], min1[:, :, None])
            update = alpha * par_sign[:, :, None] * sign * ext
        update = update * batched.chk_valid[None, :, :].astype(update.dtype)
        c2v_next = _to_edges(update, batched)
        c2v = mx.where(live[:, None], c2v_next, c2v)
        Ltot = mx.where(live[:, None], L + _var_sum(c2v, batched), Ltot)
        mx.eval(c2v, Ltot, n_iters, live, closed)
    hard_bits = (Ltot < 0).astype(mx.uint8)
    mx.eval(hard_bits, closed, n_iters)
    return hard_bits, closed, n_iters


def decode_batch(llr_prepared: np.ndarray, code: Code,
                 batched: BatchedCode, max_iters: int, alpha: float = 0.8,
                 sync_every: int = 1, dtype=mx.float32, device=None
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The batched twin of ldpc.decode, on already-prepared LLRs.

    Phase one is offset-min-sum over the whole batch; phase two re-runs
    sum-product over the sub-batch that phase one did not close, exactly
    as ldpc.decode re-runs it for one tile.

    ``dtype``/``device`` exist for ONE reason: the float64 control.  mlx
    refuses float64 on the GPU but honours it on the CPU stream, so
    running the identical padded-layout code at float64 separates "this
    port computes something else" from "float32 computes something
    slightly else".  Production use of that path would be pointless — it
    is slower than numpy — but as a control it is decisive.
    """
    del code
    stream = mx.stream(device) if device is not None else _null_context()
    with stream:
        L = mx.array(np.asarray(llr_prepared, np.float64), dtype=dtype)
        hard, ok, iters = bp_batch(L, batched, max_iters, alpha, False,
                                   sync_every)
        hard_np = np.asarray(hard)
        ok_np = np.asarray(ok)
        iters_np = np.asarray(iters).astype(np.int64)
        if max_iters > 0:
            failed = np.flatnonzero(~ok_np)
            if failed.size:
                retry = mx.array(
                    np.asarray(llr_prepared, np.float64)[failed],
                    dtype=dtype)
                hard2, ok2, iters2 = bp_batch(retry, batched, max_iters,
                                              alpha, True, sync_every)
                hard_np[failed] = np.asarray(hard2)
                ok_np[failed] = np.asarray(ok2)
                iters_np[failed] += np.asarray(iters2).astype(np.int64)
    return hard_np, ok_np, iters_np


@contextlib.contextmanager
def _null_context():
    yield
