from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.fft import irfftn, next_fast_len, rfftn
from scipy.signal import fftconvolve

from .pose import (CandidateScore, ScoreMemo, SearchOutcome,
                   WHOLE_WORD_PARITY, parity_mask, rival_gate)
from .words import ReferenceField


def hypothesis_count(
    fragment_shape: tuple[int, int],
    page_shape: tuple[int, int],
    pages: int,
    allow_overhang: bool = True,
) -> int:
    total = 0
    height, width = page_shape
    for rot_k in range(4):
        frag_height, frag_width = (
            fragment_shape if rot_k % 2 == 0 else fragment_shape[::-1])
        if allow_overhang:
            positions = (height + frag_height - 1) * (width + frag_width - 1)
        else:
            positions = max(0, height - frag_height + 1) * max(
                0, width - frag_width + 1)
        total += positions
    return int(pages) * total


@dataclass(frozen=True)
class _ColdMapGeometry:
    work_sites: np.ndarray
    search_sites: np.ndarray
    soft_kernel: np.ndarray
    weight: np.ndarray
    eligible: np.ndarray
    pad_y: int
    pad_x: int
    fshape: tuple[int, int]
    kernel_rfft: np.ndarray | None


def _cold_map_geometries(
    evidence: np.ndarray,
    mask: np.ndarray,
    sites: np.ndarray,
    min_support: int,
    allow_overhang: bool,
) -> tuple[_ColdMapGeometry | None, ...]:
    evidence = np.asarray(evidence, np.float32)
    mask = np.asarray(mask, bool)
    sites = np.asarray(sites, bool)
    page_parity = parity_mask(
        (int(sites.shape[0]), int(sites.shape[1])), (0, 0), 0)
    base_search_sites = sites & page_parity
    padded_sites: dict[tuple[int, int],
                       tuple[np.ndarray, np.ndarray]] = {}
    geometries: list[_ColdMapGeometry | None] = []
    for rot_k in range(4):
        observed = np.rot90(evidence, rot_k)
        keep = np.rot90(mask, rot_k).astype(np.float32)
        pad_y = pad_x = 0
        if allow_overhang:
            pad_y, pad_x = observed.shape[0] - 1, observed.shape[1] - 1
            padding = (pad_y, pad_x)
            prepared_sites = padded_sites.get(padding)
            if prepared_sites is None:
                prepared_sites = (
                    np.pad(sites, ((pad_y, pad_y), (pad_x, pad_x))),
                    np.pad(base_search_sites,
                           ((pad_y, pad_y), (pad_x, pad_x))))
                padded_sites[padding] = prepared_sites
            work_sites, search_sites = prepared_sites
        elif (observed.shape[0] > sites.shape[0]
              or observed.shape[1] > sites.shape[1]):
            geometries.append(None)
            continue
        else:
            work_sites, search_sites = sites, base_search_sites
        soft_kernel = (observed * keep)[::-1, ::-1]
        weight = fftconvolve(
            search_sites.astype(np.float32),
            (np.abs(observed) * keep)[::-1, ::-1],
            mode="valid")
        search_support = np.rint(fftconvolve(
            search_sites.astype(np.float32), keep[::-1, ::-1],
            mode="valid")).astype(np.int32)
        eligible = (search_support >= min_support) & (weight > 0.0)
        fshape = (
            next_fast_len(
                search_sites.shape[0] + soft_kernel.shape[0] - 1, True),
            next_fast_len(
                search_sites.shape[1] + soft_kernel.shape[1] - 1, True))
        kernel_rfft: np.ndarray | None = None
        if min(soft_kernel.shape) >= 2 and min(search_sites.shape) >= 2:
            kernel_rfft = rfftn(soft_kernel, fshape, axes=(0, 1))
        geometries.append(_ColdMapGeometry(
            work_sites, search_sites, soft_kernel, weight, eligible,
            pad_y, pad_x, fshape, kernel_rfft))
    return tuple(geometries)


def _signed_search_field(values: np.ndarray,
                         geometry: _ColdMapGeometry) -> np.ndarray:
    work_values = np.asarray(values, np.uint8)
    if geometry.pad_y or geometry.pad_x:
        work_values = np.pad(
            work_values,
            ((geometry.pad_y, geometry.pad_y),
             (geometry.pad_x, geometry.pad_x)))
    expected_sign = np.where(
        geometry.work_sites,
        1.0 - 2.0 * work_values.astype(np.float32),
        0.0)
    field: np.ndarray = expected_sign * geometry.search_sites
    return field


def _page_candidate_map(
    values: np.ndarray,
    geometry: _ColdMapGeometry,
    page: int,
    page_transforms: dict[tuple[int, int, int, tuple[int, int]],
                          np.ndarray],
) -> np.ndarray:
    if geometry.kernel_rfft is None:
        soft_corr = fftconvolve(
            _signed_search_field(values, geometry),
            geometry.soft_kernel,
            mode="valid")
    else:
        key = (int(page), geometry.pad_y, geometry.pad_x, geometry.fshape)
        transform = page_transforms.get(key)
        if transform is None:
            transform = rfftn(
                _signed_search_field(values, geometry),
                geometry.fshape, axes=(0, 1))
            page_transforms[key] = transform
        full = irfftn(
            transform * geometry.kernel_rfft, geometry.fshape, axes=(0, 1))
        kernel_height, kernel_width = geometry.soft_kernel.shape
        height, width = geometry.search_sites.shape
        soft_corr = full[kernel_height - 1:height, kernel_width - 1:width]
    with np.errstate(divide="ignore", invalid="ignore"):
        z = soft_corr / np.sqrt(geometry.weight)
    z_map: np.ndarray = np.where(geometry.eligible, z, -np.inf)
    return z_map


@dataclass(frozen=True)
class _MapTop:
    z: float
    page: int
    origin_yx: tuple[int, int]
    rot_k: int


@dataclass(frozen=True)
class _PageSweep:
    tops: tuple[_MapTop, ...]
    best_offset: int
    best_z: np.ndarray | None
    best_peak_yx: tuple[int, int]
    best_pad_yx: tuple[int, int]


def _page_sweep(
    values: np.ndarray,
    geometries: tuple[_ColdMapGeometry | None, ...],
    page: int,
    page_transforms: dict[tuple[int, int, int, tuple[int, int]],
                          np.ndarray],
) -> _PageSweep:
    tops: list[_MapTop] = []
    best_offset = -1
    best_z: np.ndarray | None = None
    best_peak = (0, 0)
    best_pad = (0, 0)
    for rot_k, geometry in enumerate(geometries):
        if geometry is None:
            continue
        z = _page_candidate_map(values, geometry, page, page_transforms)
        if z.size == 0 or not np.isfinite(z).any():
            continue
        flat = int(np.argmax(z))
        peak_y, peak_x = np.unravel_index(flat, z.shape)
        top = _MapTop(
            float(z[peak_y, peak_x]), int(page),
            (int(peak_y) - geometry.pad_y, int(peak_x) - geometry.pad_x),
            rot_k)
        if best_offset < 0 or top.z > tops[best_offset].z:
            best_offset = len(tops)
            best_z = z
            best_peak = (int(peak_y), int(peak_x))
            best_pad = (geometry.pad_y, geometry.pad_x)
        tops.append(top)
    return _PageSweep(tuple(tops), best_offset, best_z, best_peak, best_pad)


def _page_hypotheses(pages: Sequence[int]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(page) for page in pages))


def _refused(hypotheses: int, reason: str) -> SearchOutcome:
    return SearchOutcome(False, None, (), hypotheses, reason)


def correlate_patch(
    evidence: np.ndarray,
    bits: np.ndarray,
    mask: np.ndarray,
    provider: ReferenceField,
    pages: Sequence[int],
    max_hypotheses: int,
    min_support: int,
    memo: ScoreMemo,
    search_true: float,
    validation_true: float,
    rival_decoy: float,
    minimum_gap: float,
    neighbor_radius_cells: int = 3,
    allow_overhang: bool = True,
) -> SearchOutcome:
    domain = _page_hypotheses(pages)
    fragment_shape = (int(np.asarray(mask).shape[0]),
                      int(np.asarray(mask).shape[1]))
    hypotheses = hypothesis_count(
        fragment_shape, provider.cells_yx, len(domain),
        allow_overhang=allow_overhang)
    if hypotheses > max_hypotheses:
        return _refused(hypotheses, "attempt_budget_exceeded")
    raw_tops: list[_MapTop] = []
    winner_index = -1
    winner_z: np.ndarray | None = None
    winner_peak_yx = (0, 0)
    winner_pad_yx = (0, 0)
    page_transforms: dict[tuple[int, int, int, tuple[int, int]],
                          np.ndarray] = {}
    first_reference = provider.page(domain[0])
    geometries = _cold_map_geometries(
        evidence, mask, first_reference.sites, min_support,
        allow_overhang=allow_overhang)
    if not any(
        geometry is not None and bool(geometry.eligible.any())
        for geometry in geometries
    ):
        return _refused(hypotheses, "insufficient_support")
    for page_index, page in enumerate(domain):
        reference = (first_reference if page_index == 0
                     else provider.page(page))
        if (reference.sites is not first_reference.sites
                and not np.array_equal(reference.sites,
                                       first_reference.sites)):
            raise ValueError("v1 reference sites must be page-invariant")
        sweep = _page_sweep(
            reference.values, geometries, page, page_transforms)
        for offset, top in enumerate(sweep.tops):
            if winner_index < 0 or top.z > raw_tops[winner_index].z:
                winner_index = len(raw_tops)
                if offset == sweep.best_offset:
                    winner_z = sweep.best_z
                    winner_peak_yx = sweep.best_peak_yx
                    winner_pad_yx = sweep.best_pad_yx
                else:
                    winner_z = None
            raw_tops.append(top)
    if not raw_tops:
        return _refused(hypotheses, "insufficient_support")
    winner_raw = raw_tops[winner_index]
    radius = neighbor_radius_cells
    peak_y, peak_x = winner_peak_yx
    winner_z[
        max(0, peak_y - radius):peak_y + radius + 1,
        max(0, peak_x - radius):peak_x + radius + 1,
    ] = -np.inf
    winner_second: _MapTop | None = None
    if np.isfinite(winner_z).any():
        flat_second = int(np.argmax(winner_z))
        second_y, second_x = np.unravel_index(flat_second, winner_z.shape)
        winner_second = _MapTop(
            float(winner_z[second_y, second_x]), winner_raw.page,
            (int(second_y) - winner_pad_yx[0],
             int(second_x) - winner_pad_yx[1]),
            winner_raw.rot_k)
    best = memo.candidate(
        evidence, bits, mask, winner_raw.page, winner_raw.origin_yx,
        winner_raw.rot_k, min_support, search_true, validation_true,
        "correlation")
    runners: list[CandidateScore] = []
    seen: set[tuple[int, tuple[int, int], int]] = {
        (best.page, best.origin_yx, best.rot_k)}
    rival_rows: list[_MapTop] = []
    for map_index, top in enumerate(raw_tops):
        if map_index == winner_index:
            if winner_second is not None:
                rival_rows.append(winner_second)
        else:
            rival_rows.append(top)
    for contender in rival_rows:
        identity = (contender.page, contender.origin_yx, contender.rot_k)
        if identity in seen:
            continue
        if (contender.page == best.page and contender.rot_k == best.rot_k
                and max(abs(contender.origin_yx[0] - best.origin_yx[0]),
                        abs(contender.origin_yx[1] - best.origin_yx[1]))
                <= neighbor_radius_cells):
            continue
        seen.add(identity)
        runners.append(memo.candidate(
            evidence, bits, mask, contender.page, contender.origin_yx,
            contender.rot_k, min_support, search_true, validation_true,
            "correlation_runner_up"))
    if not best.passes:
        return SearchOutcome(
            False, best, tuple(runners), hypotheses,
            "winner_failed_heldout_gate")
    if runners:
        rival_mismatch = min(
            memo.parity_score(
                evidence, bits, mask, row.page, row.origin_yx, row.rot_k,
                WHOLE_WORD_PARITY)[0]
            for row in runners)
        best_whole = memo.parity_score(
            evidence, bits, mask, best.page, best.origin_yx, best.rot_k,
            WHOLE_WORD_PARITY)[0]
    else:
        rival_mismatch = 1.0
        best_whole = best.search_mismatch
    accepted = rival_gate(best_whole, rival_mismatch, rival_decoy,
                          minimum_gap)
    return SearchOutcome(
        accepted, best, tuple(runners), hypotheses,
        "accepted" if accepted else "rival_gap_failed")
