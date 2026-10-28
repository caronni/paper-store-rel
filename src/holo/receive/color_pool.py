"""The color §8.2 POOL LAW primitives: who is a cargo cell, who is open.

Four pure functions, extracted from :mod:`holo.receive.color_payload`
verbatim (PK3.1, mechanical — no behaviour change) because that module
reached the 1000-line ceiling.  They belong together: each answers one
membership question the pool law asks, from format truth or certificate
authority alone, with no raster, no detector, and no evidence in sight.

* :func:`_payload_site_mask` / :func:`_payload_cell_mask` — which slots of
  a 64x64 tile carry color cargo (a pure function of the family seed);
* :func:`fully_certified_color_addresses` — which tile addresses have
  EVERY required stream certified (the color NeedMap complement);
* :func:`_emission_mask` — which of a window's cells still sit in a tile
  where at least one stream remains open.
"""
from __future__ import annotations

from functools import cache
from typing import Iterable

import numpy as np

from ..format import pilots
from ..format.descriptor import FormatSpec
from .color_anchoring import _readonly
from .evidence import TileCertificateRecord, certificate_work_index


@cache
def _payload_site_mask(family_seed: bytes) -> np.ndarray:
    """Immutable 4096-slot color cargo mask per family seed.

    Color analog of the K geometry caches (color-payload:04): a pure
    function of the family seed, previously rebuilt on every freeze and
    every payload-cell-mask call.
    """
    mask = np.zeros(4096, bool)
    mask[pilots.color_payload_cell_indices(family_seed)] = True
    return _readonly(mask, np.bool_)


def fully_certified_color_addresses(
    certificates: Iterable[TileCertificateRecord],
    spec: FormatSpec,
) -> frozenset[tuple[int, int, int]]:
    """Tile addresses whose EVERY required stream is certified.

    The color NeedMap complement (K's ``_certified_k_addresses`` analog):
    derived from the certificate authority alone, failing closed on a
    same-stream contradiction through ``certificate_work_index``.
    """
    certificate_work = certificate_work_index(certificates)
    return frozenset(
        address_key for address_key in {
            work_key[:3] for work_key in certificate_work
        }
        if all(
            (*address_key, stream_id) in certificate_work
            for stream_id in spec.stream_ids
        )
    )


def _emission_mask(
    spec: FormatSpec,
    page: int,
    page_cells_yx: np.ndarray,
    suppressed_codes_by_page: dict[int, np.ndarray],
) -> np.ndarray:
    """Keep payload evidence only where at least one stream remains open."""
    cells = np.asarray(page_cells_yx, np.int64)
    tile_codes = (
        (cells[:, 0] // 64) * spec.layout.tiles_yx[1]
        + cells[:, 1] // 64
    )
    return ~np.isin(
        tile_codes,
        suppressed_codes_by_page.get(page, np.empty(0, np.int64)),
        assume_unique=False,
    )


def _payload_cell_mask(
    spec: FormatSpec,
    page_cells_yx: np.ndarray,
) -> np.ndarray:
    """Return the exact color cargo-site mask for absolute page cells."""
    cells = np.asarray(page_cells_yx, np.int64)
    local = (cells[:, 0] % 64) * 64 + cells[:, 1] % 64
    return _payload_site_mask(spec.family_seed)[local]


__all__ = ["fully_certified_color_addresses"]
