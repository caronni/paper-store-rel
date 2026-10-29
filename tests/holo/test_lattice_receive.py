"""FORMAT-SPACE P5: the receiver on the v2 lattice.

Gate E re-home: the resolver half never touched a receiver and is
unchanged; the two decode halves now drive holo3 — the production
receiver — through `_receive_free.decode_with_holo3`, on the same
rendered page and the same one format string.

Two things are proven here:

1. ``resolve_format_ref`` is total over every identity class the decode
   path can meet (L: fossils, bare legacy ids, catalog rows, v2 ids),
   and a canonical spec id resolves back to its own seed — what a
   resume (or ``--format``) does.
2. A v2-seeded sheet decodes END TO END byte-exactly with its identity
   supplied as one format string — the ``--format`` contract.
"""
from __future__ import annotations

import hashlib
import warnings

import numpy as np
import pytest
from scipy import ndimage

from holo.core import fountain
from holo.format.fossils import FOSSILS
from holo.format.resolve import resolve_format_ref
from holo.gen.compose import cells_to_dots, compose_page_cells
from holo.gen.emit import METADATA_VERSION, source_packed_for
from holo.gen.plan import plan_volume

from _receive_free import decode_with_holo3

_PAPER = np.uint8(245)
_INK = np.uint8(35)


def test_resolver_routes() -> None:
    fossil = resolve_format_ref("L:c2-cmy8-r0700-p120-x1@3392x2368")
    assert fossil.seed == b"holo/v1/c2-cmy8-r0700-p120-x1/3392x2368"
    bare = resolve_format_ref("c2-cmy8-r0700-p120-x1@3392x2368")
    assert bare.seed == fossil.seed
    catalog = resolve_format_ref("c2-r0700@3328x2304")
    assert catalog.seed == b"holo/v1/c2-r0700/3328x2304"
    v2 = resolve_format_ref("c2-cmy8-r0700@53x37")
    assert v2.seed == b"holo/v2/1i300-cmy8-r0700-p120-v1@53x37"
    normalized = resolve_format_ref("c2-cmy8-r0700x0700x0700-p120-v1@53x37")
    assert normalized.spec_id == "1i300-cmy8-r0700-p120-v1@53x37"
    assert normalized.display_id == "c2-cmy8-r0700@53x37"
    # The canonical spec id is itself a resolvable identity — the round
    # trip a persisted state (or a --format resume) relies on.
    spec = resolve_format_ref("c3-k-r0550@7x7")
    assert spec.spec_id == "1i200-k-r0550-p100-v1@7x7"
    assert resolve_format_ref(spec.spec_id).seed == spec.seed
    with pytest.raises(ValueError, match="neither a fossil"):
        resolve_format_ref("c2-bogus@1x1")


def test_resolver_covers_every_fossil() -> None:
    for spec_id, fossil in FOSSILS.items():
        assert resolve_format_ref(spec_id).seed == fossil.seed
        assert resolve_format_ref("L:" + spec_id).seed == fossil.seed


def _k_sheet(spec, payload: bytes) -> np.ndarray:
    """The proven roundtrip optical model: ink/paper + 0.5px Gaussian."""
    plan = plan_volume(spec, len(payload), 0.5)
    assert plan.n_pages == 1
    source = source_packed_for(payload, plan)
    code = fountain.VolumeCode(
        plan.k_total, plan.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page,
    )
    esis = np.arange(spec.tiles_per_page, dtype=np.int64)
    symbols = code.encode_symbols(source, esis)
    cells = compose_page_cells(
        spec, 0, symbols, plan.k_total, version=METADATA_VERSION)
    dots = cells_to_dots(cells, spec.cell_dots)

    border = 96
    height, width = dots.shape
    canvas = np.full((height + 2 * border, width + 2 * border),
                     _PAPER, np.uint8)
    canvas[border:border + height, border:border + width] = np.where(
        dots != 0, _INK, _PAPER)
    blurred = ndimage.gaussian_filter(canvas.astype(np.float32), 0.5)
    return np.round(np.clip(blurred, 0, 255)).astype(np.uint8)


def test_v2_sheet_decodes_byte_exact_via_format_ref(tmp_path) -> None:
    """One format string -> emitted sheet -> receiver -> byte-exact."""
    format_ref = "c3-k-r0550@7x7"
    spec = resolve_format_ref(format_ref)
    payload = hashlib.sha256(b"holo-format-space-v2-e2e").digest()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        decode = decode_with_holo3(
            ((_k_sheet(spec, payload), 600.0),), format_ref, tmp_path,
            "v2-e2e")

    assert decode.exit_code == 0, decode.stdout
    assert decode.payload == payload
    assert decode.status == "verified"
    # holo3's verified stop preempts, so the last tile of a 49-tile page
    # need not be certified; the floor that must hold is metadata trust.
    assert decode.certified >= 48
    assert decode.report["close"]["metadata_rank"] == 24
    assert decode.report["run_done"]["payload_sha256"] == hashlib.sha256(
        payload).hexdigest()

