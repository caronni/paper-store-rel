"""FORMAT-SPACE P5: the receiver on the v2 lattice.

Two things are proven here:

1. ``resolve_format_ref`` is total over every identity class the decode
   path can meet (L: fossils, bare legacy ids, catalog rows, v2 ids).
2. A v2-seeded sheet decodes END TO END byte-exactly with its identity
   supplied as one format string — the ``--format`` contract.  The
   fixture mirrors ``_roundtrip_fixture`` (same 7x7-tile matrix, same
   optical model) but the identity, seed and keystream are the v2
   lattice's own (``holo/v2/c3-k-r0550@7x7``).
"""
from __future__ import annotations

import hashlib
import os
import warnings
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

from holo.core import fountain
from holo.format.fossils import FOSSILS
from holo.format.resolve import resolve_format_ref
from holo.gen.compose import cells_to_dots, compose_page_cells
from holo.gen.emit import METADATA_VERSION, source_packed_for
from holo.gen.plan import plan_volume
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.session import SessionStatus
from holo.receive.types import CaptureInput

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
    with pytest.raises(ValueError, match="neither a fossil"):
        resolve_format_ref("c2-bogus@1x1")


def test_resolver_covers_every_fossil() -> None:
    for spec_id, fossil in FOSSILS.items():
        assert resolve_format_ref(spec_id).seed == fossil.seed
        assert resolve_format_ref("L:" + spec_id).seed == fossil.seed


def test_v2_sheet_decodes_byte_exact_via_format_ref(tmp_path) -> None:
    """One format string -> emitted sheet -> receiver -> byte-exact."""
    spec = resolve_format_ref("c3-k-r0550@7x7")
    payload = hashlib.sha256(b"holo-format-space-v2-e2e").digest()
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
    canvas = np.ascontiguousarray(ndimage.gaussian_filter(
        canvas.astype(np.float32), 0.5))
    canvas.setflags(write=False)

    request = ReceiveRequest(
        spec,
        (CaptureInput(canvas, 600.0),),
        state_path=tmp_path / "v2-e2e.state",
        page_hypotheses=(0,),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("always", ProvisionalReceiverWarning)
        result = run_receive(request, pipeline=production_pipeline(request))

    state = result.state
    assert state.status is SessionStatus.VERIFIED
    assert state.format_row_id == "1i200-k-r0550-p100-v1@7x7"
    assert len(state.certificates) == spec.tiles_per_page
    assert state.close is not None
    assert state.close.payload_sha256 == hashlib.sha256(payload).hexdigest()
    # The persisted identity round-trips through the resolver alone —
    # what a resume (or --format) does.
    assert resolve_format_ref(state.format_row_id).seed == spec.seed


@pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the v2 colour e2e",
)
def test_v2_pooled_colour_sheet_decodes_byte_exact(tmp_path: Path) -> None:
    """A v2 pooled CMY8 mixed-triplet sheet closes byte-exact end to end.

    The colour twin of the K e2e above, on the synthetic colour scan
    model of the dead-plane gate (same 10x10 c3 matrix, v2 identity and
    seed).  First measured by the P6 adversarial review (273
    certificates, C/M/Y 91/91/91); pinned here in the slow lane.
    """
    from holo.gen.emit import emit_volume
    from holo.qualification.color_synthetic import render_color_scan

    spec = resolve_format_ref("c3-cmy8-r0550x0550x0547@10x10")
    payload = hashlib.sha256(b"holo-format-space-v2-colour-e2e").digest()
    volume = emit_volume(spec, payload, 0.35, tmp_path / "volume")

    packed = np.load(volume.pages[0].gt_path, allow_pickle=False)
    assert packed.shape[0] == 3
    field_h = spec.cells_yx[0] * spec.cell_dots
    field_w = spec.cells_yx[1] * spec.cell_dots
    coverage = np.stack([
        np.unpackbits(packed[plane], axis=1, count=field_w,
                      bitorder="big").astype(np.float64)
        for plane in range(3)
    ], axis=-1)
    border = 60
    padded = np.zeros((field_h + 2 * border, field_w + 2 * border, 3),
                      np.float64)
    padded[border:-border, border:-border] = coverage
    source = np.repeat(np.repeat(padded, 2, axis=0), 2, axis=1)
    scan = render_color_scan(source)
    rgb = np.clip(np.asarray(scan.rgb), 0.0, 1.0)
    raster = np.ascontiguousarray(
        np.round(rgb * 255.0).astype(np.uint8))

    request = ReceiveRequest(
        spec, (CaptureInput(raster, 1200.0),),
        state_path=tmp_path / "v2-colour.state",
        page_hypotheses=(0,))
    with warnings.catch_warnings():
        warnings.simplefilter("always", ProvisionalReceiverWarning)
        result = run_receive(request, pipeline=production_pipeline(request))

    assert result.payload == payload
    state = result.state
    assert state.status is SessionStatus.VERIFIED
    assert state.close.payload_sha256 == hashlib.sha256(payload).hexdigest()
    assert {row.stream_id for row in state.certificates} == {"C", "M", "Y"}
