"""Ground truth for UNCERTIFIED tiles, from the volume that already closed.

The swim's oracle is the certificate gate, and a gate that never fires
tells you nothing about WHY.  Sheet I's volume is VERIFIED — the recovered
payload's SHA-256 equals the emitted one — so the exact printed cells of
EVERY tile, including the ones no certificate covers, are recoverable by
re-running the generator on the recovered payload.  That turns a silent
negative into a measurement: per-plane CELL error rate as a function of
the sampling offset, on the tiles the swim could not certify.

TRUTH-PATH DISCIPLINE (the standing rule): this reconstruction is
VALIDATED on CERTIFIED tiles before it is believed anywhere else —
:func:`validate_against_certificates` compares it cell for cell with
``project_certified_color_tile`` on a sample of certified addresses, and
a single mismatch stops the caller.  It is a DIAGNOSTIC only: it never
enters the decode path, and no certificate anywhere depends on it.
"""
from __future__ import annotations

import numpy as np

from holo.core import channel, fountain
from holo.format import streamset
from holo.gen.color_compose import compose_color_page_cells
from holo.gen.emit import METADATA_VERSION
from holo.gen.plan import plan_volume


def page_component_bits(spec, payload: bytes, q: float, page: int
                        ) -> tuple[np.ndarray, dict]:
    """``(cells_y, cells_x, 3)`` printed presence for one whole page.

    The generator's own composition path, re-run on the CLOSED payload:
    ``plan_volume`` -> pooled/per-stream fountain encode -> the exact
    ``compose_color_page_cells`` the emission used.  Nothing here is a
    re-implementation; the only harness decision is which ``q`` to plan
    at, which :func:`validate_against_certificates` then proves or
    refutes against real certificates.
    """
    plan = plan_volume(spec, len(payload), q)
    layout = streamset.StreamSet(tuple(
        (stream.stream_id, stream.symbol_bits)
        for stream in spec.stream_profiles))
    tiles_per_page = spec.tiles_per_page
    if spec.pooled_fountain:
        k_meta, pooled_source = streamset.pooled_pack_payload(payload, layout)
        code = fountain.VolumeCode(
            plan.k_total, spec.symbol_bits, spec.seed,
            tiles_per_page=tiles_per_page, n_streams=spec.n_streams)
        per_page = tiles_per_page * spec.n_streams
        pooled = code.encode_symbols(
            pooled_source,
            np.arange(page * per_page, (page + 1) * per_page,
                      dtype=np.int64))
        symbols = {
            stream_id: pooled[index::spec.n_streams]
            for index, stream_id in enumerate(spec.stream_ids)}
        metadata_k = k_meta
    else:
        packed = streamset.pack_payload(payload, layout)
        esis = np.arange(page * tiles_per_page, (page + 1) * tiles_per_page,
                         dtype=np.int64)
        symbols = {
            stream.stream_id: fountain.VolumeCode(
                plan.k_total, stream.symbol_bits, spec.seed,
                tiles_per_page=tiles_per_page, stream_id=stream.stream_id,
                fountain_aux=stream.fountain_aux,
            ).encode_symbols(
                {row.stream_id: row.rows
                 for row in packed.streams}[stream.stream_id], esis)
            for stream in spec.stream_profiles}
        metadata_k = plan.k_total
    states = compose_color_page_cells(
        spec, page, symbols, metadata_k, version=METADATA_VERSION)
    bits = channel.states_to_planes(states.reshape(-1)).reshape(
        (*states.shape, 3))
    return np.ascontiguousarray(bits, np.uint8), {
        "q": q, "k_total": plan.k_total, "k_meta": plan.k_meta,
        "n_pages": plan.n_pages, "pooled": bool(spec.pooled_fountain),
        "payload_bytes": len(payload)}


def validate_against_certificates(bits, spec, certificates, *, sample: int,
                                  seed: int = 20260821) -> dict:
    """Cell-for-cell agreement with certificates.  A mismatch is fatal.

    A wrong ``q`` (or page, or version) changes the fountain symbols and
    the composed cells with it, so exact agreement on real certified
    tiles is a complete proof that the reconstruction is the printed
    field — the only proof available for tiles no certificate covers.
    """
    from holo.receive.color_projection import project_certified_color_tile

    grouped: dict[tuple[int, int, int], list] = {}
    for record in certificates:
        grouped.setdefault(
            (int(record.page), *(int(v) for v in record.tile_yx)),
            []).append(record)
    full = [address for address, rows in grouped.items()
            if {row.stream_id for row in rows} == set(spec.stream_ids)]
    if not full:
        return {"checked": 0, "mismatched_cells": None,
                "reason": "no fully certified tile"}
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(full), size=min(sample, len(full)), replace=False)
    mismatched = 0
    checked = 0
    for pick in picks:
        page, tile_y, tile_x = full[int(pick)]
        if page != 0:
            continue
        projection = project_certified_color_tile(
            grouped[(page, tile_y, tile_x)], spec, (page, tile_y, tile_x))
        truth = bits[tile_y * 64:(tile_y + 1) * 64,
                     tile_x * 64:(tile_x + 1) * 64, :]
        mismatched += int(np.count_nonzero(
            np.asarray(projection.component_bits, np.uint8) != truth))
        checked += 1
    return {"checked": checked, "mismatched_cells": mismatched,
            "cells_per_tile": 64 * 64 * 3,
            "exact": checked > 0 and mismatched == 0}


def tile_truth(bits, address, plane: int, spec) -> tuple[np.ndarray, np.ndarray]:
    """One tile's payload-cell truth for one plane, in CELL RASTER order.

    Returns ``(payload_flat_indices, truth_bits)`` where the indices are
    the format's own payload-site order over the tile's 4096 cells — the
    same order ``TileAttemptView`` exposes.
    """
    from holo.format import pilots

    _page, tile_y, tile_x = address
    block = bits[tile_y * 64:(tile_y + 1) * 64,
                 tile_x * 64:(tile_x + 1) * 64, plane].reshape(4096)
    payload = pilots.color_payload_cell_indices(spec.family_seed)
    return payload, block[payload].astype(np.uint8)


def hard_decision_ber(view, payload_indices, truth, plane: int,
                      *, ink_is_positive: bool) -> dict:
    """Cell error rate of the union LLRs against the printed truth."""
    values = view.llr_cells_f64.reshape(4096, view.arity)[
        payload_indices][:, plane]
    observed = view.observed_cells().reshape(4096)[payload_indices]
    if not observed.any():
        return {"observed": 0, "ber": None}
    decided = (values > 0.0) if ink_is_positive else (values < 0.0)
    errors = int(np.count_nonzero(
        decided[observed] != truth[observed].astype(bool)))
    total = int(np.count_nonzero(observed))
    return {"observed": total, "errors": errors, "ber": errors / total,
            "mean_abs_llr": float(np.abs(values[observed]).mean())}


__all__ = ["hard_decision_ber", "page_component_bits", "tile_truth",
           "validate_against_certificates"]
