"""H5 P1 pin (a): the applied ctx correction against v1's own code.

The fit arithmetic is character-pinned in ``test_oracle_tiles.py``; what
H5 adds is PLUMBING — the correction applied at decode assembly
(``holo2.solve.ctx_apply.apply_component_context``, called by the
payload fire) instead of v1's per-window evidence rewrite
(``src/holo/receive/_payload_context.apply_region_context``). This file
pins the plumbing's output the only trustworthy way: the reference tensor
is computed by CALLING v1's own code — ``holo.receive.detect``'s
``fit_context`` / ``context_neighbour_counts`` / ``apply_context_offsets``,
with the ``np.where(valid, counts, -1)`` bin idiom lifted verbatim from
``_payload_context.apply_region_context`` — never by retyping numbers
(the e012 keystream lesson: retyped ground truth forks silently).

Both packages may be imported HERE, outside the holo2 tree (the firewall
forbids holo2 importing the original), which is the same standing every
other oracle in this directory has.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from holo.receive import detect as v1_detect
from holo2.solve import detect as h2_detect
from holo2.solve.ctx_apply import apply_component_context

TILE = 64


def _population(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One tile's worth of miscalibrated marginal LLRs and labels.

    The planted bias is additive in the true neighbour-ink count and too
    small to flip a sign, so provisional ink recomputed from the LLR is
    the planted ink and the ordered nine-bin fit has a real monotone
    correction to learn.
    """
    rng = np.random.default_rng(seed)
    ink = rng.random((TILE, TILE)) < 0.45
    kernel = np.ones((3, 3), np.uint8)
    kernel[1, 1] = 0
    counts = ndimage.convolve(ink.astype(np.uint8), kernel,
                              mode="constant", cval=0)
    marginal = ((2.0 * ink.astype(np.float64) - 1.0) * 2.0
                + 0.35 * (counts.astype(np.float64) - 4.0))
    return marginal, ink, counts


def _v1_fitted_offsets(marginal: np.ndarray, ink: np.ndarray,
                       module) -> np.ndarray:
    """A region fit through ``module``'s own carried arithmetic."""
    ys, xs = np.nonzero(np.ones_like(ink))
    cells = np.stack((ys, xs), 1).astype(np.int64)
    flat = marginal[ys, xs]
    counts, valid = module.context_neighbour_counts(cells, flat > 0.0)
    labels = ink[ys, xs]
    heldout = (((131 * ys + 17 * xs) & 1) == 1)
    ids = (ys * TILE + xs).astype(np.int64)
    search = valid & ~heldout
    validation = valid & heldout
    fit = module.fit_context(
        module.ContextObservations("region", flat[search], counts[search],
                                   labels[search], ids[search]),
        module.ContextObservations("region", flat[validation],
                                   counts[validation], labels[validation],
                                   ids[validation]))
    assert fit.adopted, "the planted bias must be learnable"
    return fit.offsets


def test_the_fitted_offsets_are_v1_byte_for_byte() -> None:
    """Identical populations through both trees' fits: identical bytes."""
    marginal, ink, _counts = _population(11)
    v1 = _v1_fitted_offsets(marginal, ink, v1_detect)
    h2 = _v1_fitted_offsets(marginal, ink, h2_detect)
    assert v1.tobytes() == h2.tobytes()


def test_the_applied_tensor_byte_compares_against_v1() -> None:
    """Pin (a): the production apply path vs a v1-computed reference.

    holo2's side is the REAL assembly function the payload fire calls;
    v1's side is v1's own kernel over v1's own bins — the exact
    ``np.where(valid, counts, -1)`` + ``apply_context_offsets`` sequence
    ``apply_region_context`` runs per adopted window. Exercised with an
    unobserved hole (bin −1 territory) and a partial governing mask, so
    the untouched-cell arms are compared too, and the bar is bytes.
    """
    marginal, ink, _counts = _population(23)
    offsets = _v1_fitted_offsets(marginal, ink, v1_detect)

    observed = np.ones((TILE, TILE), bool)
    observed[40:45, 10:18] = False           # an unobserved hole
    tensor = np.where(observed, marginal, 0.0)
    mask = np.zeros((TILE, TILE), bool)
    mask[:, : TILE // 2 + 3] = True          # a partial governing region

    # v1's reference, from v1's own functions on identical inputs.
    ys, xs = np.nonzero(observed)
    flat = tensor[ys, xs]
    counts, valid = v1_detect.context_neighbour_counts(
        np.stack((ys, xs), 1).astype(np.int64), flat > 0.0)
    bins = np.where(valid, counts, -1).astype(np.int8)   # _payload_context's idiom
    bins = np.where(mask[ys, xs], bins, np.int8(-1)).astype(np.int8)
    corrected_flat = v1_detect.apply_context_offsets(flat, bins, offsets)
    reference = tensor.copy()
    reference[ys, xs] = corrected_flat

    lived = apply_component_context(tensor, observed, ((mask, offsets),))
    assert lived.tobytes() == reference.tobytes()
    assert not np.array_equal(lived, tensor), (
        "the fixture must actually correct something")


def test_the_null_correction_is_the_identity_object() -> None:
    """The refused path's bit-for-bit claim, at the kernel's own seam."""
    marginal, _ink, _counts = _population(5)
    observed = np.ones((TILE, TILE), bool)
    assert apply_component_context(marginal, observed, ()) is marginal


def test_a_window_scoped_tile_byte_compares_against_v1() -> None:
    """F1's pin (ruling J2-2, 2026-08-23; added on review).

    The arm above exercises ``bins=None`` — the TILE-scoped derivation
    the freeze bypasses whenever an owning piece carries a halo — so
    until this test the production window-scoped path had no cross-tree
    gate at all, while ``PROVIDERS.md`` CA2 cited this file as its pin.

    Here the reference is v1's own answer for a WHOLE window at a
    non-tile-aligned page origin: v1's ``context_neighbour_counts`` over
    every observed cell of the window, the ``np.where(valid, counts, -1)``
    idiom from ``_payload_context.apply_region_context``, v1's
    ``apply_context_offsets``, then the corrected window SLICED to one
    interior tile. holo2's side is the whole production chain — the
    sampler's halo (``ring_masks`` -> ``pack_piece_observation``), the
    assembly's reconstruction (``unpack_piece_halo`` ->
    ``window_context_bins``) and the applied correction — over that tile
    alone. The bar is bytes: what this catches is a fork in the halo
    layout or in the frame assembly, either of which would silently move
    a cell's bin and with it every certificate at the margin.
    """
    from holo2.solve.ctx_apply import window_context_bins
    from holo2.solve.records import (pack_piece_observation, ring_masks,
                                     unpack_piece_halo)

    rng = np.random.default_rng(19)
    height = width = 200
    origin_y, origin_x = 40, 72              # deliberately not tile-aligned
    observed = rng.random((height, width)) < 0.96      # with unobserved holes
    llr = rng.normal(0.0, 2.0, (height, width))
    ink = np.zeros((height, width), bool)
    ink[observed] = llr[observed] > 0.0
    offsets = np.linspace(-0.6, 0.6, 9)

    # v1's reference: the WHOLE window, v1's kernels, v1's bin idiom.
    ys, xs = np.nonzero(observed)
    counts, valid = v1_detect.context_neighbour_counts(
        np.stack((ys, xs), 1).astype(np.int64), ink[ys, xs])
    bins = np.where(valid, counts, -1).astype(np.int8)
    window = np.zeros((height, width))
    window[ys, xs] = v1_detect.apply_context_offsets(
        llr[ys, xs], bins, offsets)

    compared = 0
    for ty in range(origin_y // TILE, (origin_y + height) // TILE + 1):
        for tx in range(origin_x // TILE, (origin_x + width) // TILE + 1):
            y0, y1 = max(origin_y, ty * TILE), min(origin_y + height,
                                                   (ty + 1) * TILE)
            x0, x1 = max(origin_x, tx * TILE), min(origin_x + width,
                                                   (tx + 1) * TILE)
            if y1 <= y0 or x1 <= x0:
                continue
            rows = slice(y0 - ty * TILE, y1 - ty * TILE)
            cols = slice(x0 - tx * TILE, x1 - tx * TILE)
            seen = np.zeros((TILE, TILE), bool)
            tile_llr = np.zeros((TILE, TILE))
            seen[rows, cols] = observed[y0 - origin_y:y1 - origin_y,
                                        x0 - origin_x:x1 - origin_x]
            tile_llr[rows, cols] = llr[y0 - origin_y:y1 - origin_y,
                                       x0 - origin_x:x1 - origin_x]
            if not seen.any():
                continue
            halo = unpack_piece_halo(pack_piece_observation(
                seen, *ring_masks(observed, ink, (origin_y, origin_x),
                                  ty, tx)))
            lived = apply_component_context(
                tile_llr, seen,
                ((np.ones((TILE, TILE), bool), offsets),),
                window_context_bins(tile_llr, seen, halo))
            reference = np.zeros((TILE, TILE))
            reference[rows, cols] = window[y0 - origin_y:y1 - origin_y,
                                           x0 - origin_x:x1 - origin_x]
            assert lived[seen].tobytes() == reference[seen].tobytes(), (
                f"tile ({ty}, {tx}) forked from v1's window-scoped answer")
            compared += 1
    assert compared == 16, "the fixture must cover a 4x4 block of tiles"
