from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from holo3 import data
from holo3.format import pilots
from holo3.plugins import place
from holo3.tests import _h3_sims, _h3_support
from holo3.tests import conftest as h3_conftest

FORMAT_REF = _h3_sims.K_FORMAT_REF
THREE_PAGE_BYTES = 12000
THREE_PAGE_TAG = b"holo3-page-domain-3p"
PRESENTED = (0, 2)
GAP = 1
REST_PAGE = 2
THREE_PAGE_BOUND = ("--max-pages", "3")
WORD_ERRORS_PAST_BCH = 24


def _render_k_page(cells: np.ndarray, cell_dots: int) -> np.ndarray:
    from scipy import ndimage

    from holo.gen.compose import cells_to_dots

    dots = cells_to_dots(cells, cell_dots)
    border = _h3_sims.K_BORDER_DOTS
    height, width = dots.shape
    canvas = np.full((height + 2 * border, width + 2 * border),
                     _h3_sims.K_PAPER_LEVEL, np.uint8)
    canvas[border:border + height, border:border + width] = np.where(
        dots != 0, _h3_sims.K_INK_LEVEL, _h3_sims.K_PAPER_LEVEL)
    up = np.repeat(np.repeat(canvas, _h3_sims.UPSAMPLE, axis=0),
                   _h3_sims.UPSAMPLE, axis=1)
    blurred = ndimage.gaussian_filter(up.astype(np.float32),
                                      _h3_sims.K_BLUR_SIGMA_PX)
    return np.round(np.clip(blurred, 0, 255)).astype(np.uint8)


def _punch_word_sites(cells: np.ndarray, family_seed: bytes) -> np.ndarray:
    word = pilots.word_site_cells_yx(family_seed)[:WORD_ERRORS_PAST_BCH]
    tile = pilots.TILE_CELLS
    out = np.array(cells, copy=True)
    for ty in range(out.shape[0] // tile):
        for tx in range(out.shape[1] // tile):
            out[ty * tile + word[:, 0], tx * tile + word[:, 1]] ^= 1
    return out


def _three_page_captures(
        outdir: Path, pages: tuple[int, ...] = PRESENTED, *,
        punch_words: bool = False) -> tuple[
            tuple[_h3_sims.SimCapture, ...], bytes]:
    import tifffile

    from holo.core import fountain
    from holo.format.resolve import resolve_format_ref
    from holo.gen.compose import compose_page_cells
    from holo.gen.emit import METADATA_VERSION, source_packed_for
    from holo.gen.plan import plan_volume

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    spec = resolve_format_ref(FORMAT_REF)
    payload = _h3_sims.det_bytes(THREE_PAGE_TAG, THREE_PAGE_BYTES)
    plan = plan_volume(spec, len(payload), _h3_sims.K_SOURCE_FRACTION)
    if plan.n_pages != 3:
        raise RuntimeError(
            f"3-page probe planned {plan.n_pages} pages, not 3")
    source = source_packed_for(payload, plan)
    tpp = spec.tiles_per_page
    code = fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                               tiles_per_page=tpp)
    payload_path = outdir / "payload.bin"
    payload_path.write_bytes(payload)
    payload_sha = _h3_sims.sha256_file(payload_path)
    captures: list[_h3_sims.SimCapture] = []
    for page in pages:
        esis = np.arange(page * tpp, (page + 1) * tpp, dtype=np.int64)
        cells = compose_page_cells(
            spec, page, code.encode_symbols(source, esis),
            plan.k_total, version=METADATA_VERSION)
        if punch_words:
            cells = _punch_word_sites(cells, spec.family_seed)
        image = _render_k_page(cells, spec.cell_dots)
        tiff = outdir / f"page{page}.tiff"
        tifffile.imwrite(tiff, image)
        captures.append(_h3_sims.SimCapture(
            name=f"k-page{page}", format_ref=FORMAT_REF,
            dpi=_h3_sims.DPI, rot_k=0, tiff=tiff,
            tiff_sha256=_h3_sims.sha256_file(tiff), payload=payload_path,
            payload_sha256=payload_sha, payload_bytes=len(payload),
            emit_dir=None))
    return tuple(captures), payload


def test_word_opens_presented_pages_and_never_allocates_the_gap(
        tmp_path_factory: pytest.TempPathFactory):
    _h3_support.skip_unless_slow_lane("the 3-page word-open sim")
    reason = _h3_sims.producer_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)
    root = tmp_path_factory.mktemp("page-domain-3p")
    captures, payload = _three_page_captures(root / "emit")
    record = h3_conftest._decode_group(
        "k-pages-0-2", captures, root / "decode", workers=1,
        extra_argv=("--complete",) + THREE_PAGE_BOUND, keep_engine=True)
    assert record.exit_code == 0
    assert record.payload == payload
    engine = record.engine
    assert engine.live_pages() == frozenset(PRESENTED)
    assert GAP not in engine.live_pages()
    scramble = getattr(engine.geometry, "_scramble", {})
    assert GAP not in scramble


def test_cold_rest_places_a_page_whose_words_are_past_bch(
        tmp_path_factory: pytest.TempPathFactory):
    _h3_support.skip_unless_slow_lane("the damaged-word rest sim")
    reason = _h3_sims.producer_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)
    root = tmp_path_factory.mktemp("page-domain-rest")
    captures, _payload = _three_page_captures(
        root / "emit", (REST_PAGE,), punch_words=True)
    record = h3_conftest._decode_group(
        "k-page2-punched", captures, root / "decode", workers=8,
        extra_argv=THREE_PAGE_BOUND, keep_engine=True)
    stages = tuple(event.stage for event in record.events
                   if isinstance(event, data.WindowScheduled))
    assert place.STAGE_COLD_REST in stages
    poses = tuple(event for event in record.events
                  if isinstance(event, data.PoseCommitted))
    assert all(event.route != place.ROUTE_WORD for event in poses)
    rest_poses = tuple(event for event in poses
                       if event.route == place.ROUTE_COLD)
    assert rest_poses
    assert all(event.page == REST_PAGE for event in rest_poses)
    engine = record.engine
    assert REST_PAGE in engine.live_pages()
    assert GAP not in engine.live_pages()
