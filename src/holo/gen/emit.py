"""The generation driver: payload bytes -> printable PS pages (+GT).

One PS file per page (pages print independently); a sidecar manifest for
convenience — nothing in it is required for decoding (HOLO-DESIGN §7.1:
sheets are self-describing). A volume is one DIRECTORY, staged completely
and published by a single atomic rename; existing targets are refused,
never overwritten (mixing pages of two volumes on paper is a detected
receiver-side fatal, but the print run would already be wasted).
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..core import fountain
from ..format import envelope, streamset
from ..format.descriptor import FormatSpec
from ..format.profiles import Family
from .color_compose import (
    color_cells_to_dot_planes,
    compose_color_page_cells,
)
from .compose import cells_to_dots, compose_page_cells
from .manifest import write_manifest
from .plan import VolumePlan, plan_volume
from .ps import HW_DPI, PSDoc
from .sheet import DEFAULT_ENGINE_DPI, DEFAULT_PAPER, SheetLayout, sheet_layout

METADATA_VERSION = 0     # fountain-v2 payload interpretation


@dataclass(frozen=True)
class EmittedPage:
    page: int
    ps_path: Path
    ps_sha256: str
    gt_path: Path
    gt_sha256: str       # canonical packed dot bytes, not the .npy container
    gt_plane_sha256: tuple[str, str, str] | None = None


@dataclass(frozen=True)
class EmittedVolume:
    plan: VolumePlan
    payload_sha256: str
    pages: tuple[EmittedPage, ...]


def source_packed_for(payload: bytes, plan: VolumePlan) -> np.ndarray:
    """K envelope as row-packed source symbols,
    (K, ceil(S/8)) uint8.

    Bit mapping (format-axis, HOLO-DESIGN §7.1): the wrapped stream's
    bytes unpack MSB-first per byte into one flat bit string, zero-padded
    to K*S bits and sliced row-major — source symbol k = bits
    [k*S, (k+1)*S). The decoder inverts with MSB-first packbits over the
    row-major-flattened (K, S) matrix before envelope.unwrap. Built in
    bounded chunks (fountain.pack_source); never a full unpacked matrix.
    """
    if plan.spec.codec_family is not Family.K:
        raise ValueError(
            "source_packed_for is the established single-stream K leaf")
    return fountain.pack_source(envelope.wrap(payload), plan.k_total,
                                plan.symbol_bits)


def page_dot_bitmap(spec: FormatSpec, page: int, symbols: np.ndarray,
                    k_total: int, cell_dots: int | None = None
                    ) -> np.ndarray:
    """One page's dot bitmap; ``cell_dots`` defaults to the 600 grid."""
    cells = compose_page_cells(spec, page, symbols, k_total,
                               version=METADATA_VERSION)
    return cells_to_dots(
        cells, spec.cell_dots if cell_dots is None else cell_dots)


@dataclass(frozen=True)
class _Placement:
    """Where one emission puts the field, and on which engine grid.

    v1 rows read it off the derived FieldLayout (media x margin, 600 dpi
    always); v2 rows get it from a paper profile + engine grid, which are
    emission facts and never identity (FORMAT-SPACE §7/§9).
    """

    page_dots_xy: tuple[int, int]
    origin_dots_yx: tuple[int, int]
    field_dots_yx: tuple[int, int]
    dots_per_cell: int
    engine_dpi: int
    sheet: SheetLayout | None      # v2 only


def _placement(spec: FormatSpec, paper: str | None,
               engine_dpi: int | None) -> _Placement:
    if spec.coding.namespace == "v1":
        if paper is not None or engine_dpi is not None:
            raise ValueError(
                f"{spec.spec_id}: paper/dpi selection is the v2 emission "
                f"path; a v1 row derives its page from the printer "
                f"registry (media x margin) at 600 dpi")
        lay = spec.layout
        return _Placement(page_dots_xy=lay.page_dots_xy,
                          origin_dots_yx=lay.origin_dots_yx,
                          field_dots_yx=lay.field_dots_yx,
                          dots_per_cell=lay.cell_dots,
                          engine_dpi=HW_DPI, sheet=None)
    sheet = sheet_layout(
        spec,
        DEFAULT_PAPER if paper is None else paper,
        DEFAULT_ENGINE_DPI if engine_dpi is None else engine_dpi)
    return _Placement(page_dots_xy=sheet.page_dots_xy,
                      origin_dots_yx=sheet.origin_dots_yx,
                      field_dots_yx=sheet.field_dots_yx,
                      dots_per_cell=sheet.dots_per_cell,
                      engine_dpi=sheet.engine_dpi, sheet=sheet)


def default_out_dir(spec: FormatSpec, payload: bytes) -> Path:
    """Content-addressed volume directory: build/holo-<spec>-<sha12>."""
    sha12 = hashlib.sha256(payload).hexdigest()[:12]
    return Path("build") / f"holo-{spec.spec_id}-{sha12}"


def emit_volume(spec: FormatSpec, payload: bytes, q: float,
                out_dir: Path, *, profile=None,
                printer_id: str | None = None,
                paper: str | None = None,
                engine_dpi: int | None = None) -> EmittedVolume:
    """Plan, encode and write the complete volume into out_dir:
    pageNNN.ps + pageNNN_gt.npy per page + manifest.json.

    ``paper``/``engine_dpi`` place a v2 field on real paper (defaults
    A4-6mm at 600 dpi); a v1 row refuses them — its page comes from the
    printer registry.

    Everything is written into a staging directory and published by one
    atomic rename — a crash leaves no partial volume, and an existing
    out_dir is refused (delete it deliberately or pick another; volumes
    are never overwritten)."""
    if spec.codec_family is not Family.K:
        return _emit_color_volume(
            spec,
            payload,
            q,
            out_dir,
            profile=profile,
            printer_id=printer_id,
            paper=paper,
            engine_dpi=engine_dpi,
        )

    # Established K leaf.  Keep this path numerically and physically exact:
    # in particular, its source mapping and fountain domains remain 7/8,
    # and its PostScript operation remains the frozen K imagemask.
    place = _placement(spec, paper, engine_dpi)
    plan = plan_volume(spec, len(payload), q)
    if out_dir.exists():
        raise FileExistsError(
            f"{out_dir} exists — volumes are never overwritten; "
            f"delete it deliberately or choose another directory")
    staging = out_dir.with_name(out_dir.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    src = source_packed_for(payload, plan)
    vc = fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                             tiles_per_page=spec.tiles_per_page)
    tpp = spec.tiles_per_page
    pages: list[EmittedPage] = []
    for page in range(plan.n_pages):
        esis = np.arange(page * tpp, (page + 1) * tpp, dtype=np.int64)
        symbols = vc.encode_symbols(src, esis)
        dots = page_dot_bitmap(spec, page, symbols, plan.k_total,
                               place.dots_per_cell)
        doc = PSDoc(page_dots_xy=place.page_dots_xy,
                    jobid=_jobid(spec, page, payload),
                    title=f"holo {spec.spec_id} p{page:03d}",
                    engine_dpi=place.engine_dpi)
        oy, ox = place.origin_dots_yx
        doc.begin_page()
        doc.put_bitmap(dots, x_dots=ox, y_dots=oy)
        doc.end_page()
        ps_bytes = doc.render().encode("ascii")
        ps_name = f"page{page:03d}.ps"
        gt_name = f"page{page:03d}_gt.npy"
        (staging / ps_name).write_bytes(ps_bytes)
        packed_gt = np.packbits(dots, axis=1, bitorder="big")
        np.save(staging / gt_name, packed_gt)
        pages.append(EmittedPage(
            page=page, ps_path=out_dir / ps_name,
            ps_sha256=hashlib.sha256(ps_bytes).hexdigest(),
            gt_path=out_dir / gt_name,
            gt_sha256=hashlib.sha256(
                packed_gt.tobytes(order="C")).hexdigest()))
    vol = EmittedVolume(plan=plan,
                        payload_sha256=hashlib.sha256(payload).hexdigest(),
                        pages=tuple(pages))
    write_manifest(staging / "manifest.json", vol, profile=profile,
                   printer_id=printer_id, sheet=place.sheet)
    staging.rename(out_dir)
    return vol


def _emit_color_volume(
    spec: FormatSpec,
    payload: bytes,
    q: float,
    out_dir: Path,
    *,
    profile=None,
    printer_id: str | None = None,
    paper: str | None = None,
    engine_dpi: int | None = None,
) -> EmittedVolume:
    """Emit one provisional CMY7/CMY8 volume as composite DeviceCMYK."""
    if spec.codec_family not in (Family.CMY7, Family.CMY8):
        raise ValueError(f"unsupported color codec {spec.codec_id!r}")
    place = _placement(spec, paper, engine_dpi)
    plan = plan_volume(spec, len(payload), q)
    if out_dir.exists():
        raise FileExistsError(
            f"{out_dir} exists — volumes are never overwritten; "
            f"delete it deliberately or choose another directory")
    staging = out_dir.with_name(out_dir.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    stream_layout = streamset.StreamSet(tuple(
        (stream.stream_id, stream.symbol_bits)
        for stream in spec.stream_profiles
    ))
    if spec.pooled_fountain:
        # Pooled -v1 rows (docs/CMY8-POOLED-FOUNTAIN.md §2.1): ONE
        # fountain over esi = counter*n + stream on the K domains; the
        # compose seam is unchanged — the pooled symbol matrix is sliced
        # back into per-stream page views (stream-minor within tile),
        # each cut to its stream's width (the widest stream's tile IS
        # the symbol; a narrower stream's tile carries column groups
        # of it, left-aligned — docs/CMY8-COLUMN-GROUPS.md).
        k_meta, pooled_source = streamset.pooled_pack_payload(
            payload, stream_layout)
        if k_meta != plan.k_meta \
                or plan.k_total != spec.n_streams * k_meta:
            raise AssertionError(
                "pooled source mapping and volume planner disagree on K")
        pooled_code = fountain.VolumeCode(
            plan.k_total,
            spec.symbol_bits,
            spec.seed,
            tiles_per_page=spec.tiles_per_page,
            n_streams=spec.n_streams,
            groups=spec.column_groups,
        )
        sources = codes = None
        metadata_k = k_meta
    else:
        packed = streamset.pack_payload(payload, stream_layout)
        if packed.k_total != plan.k_total:
            raise AssertionError(
                "color source mapping and volume planner disagree on K")
        sources = {
            source.stream_id: source.rows for source in packed.streams
        }
        codes = {
            stream.stream_id: fountain.VolumeCode(
                plan.k_total,
                stream.symbol_bits,
                spec.seed,
                tiles_per_page=spec.tiles_per_page,
                stream_id=stream.stream_id,
                fountain_aux=stream.fountain_aux,
            )
            for stream in spec.stream_profiles
        }
        pooled_code = pooled_source = None
        metadata_k = plan.k_total

    tpp = spec.tiles_per_page
    pages: list[EmittedPage] = []
    for page in range(plan.n_pages):
        if spec.pooled_fountain:
            assert pooled_code is not None and pooled_source is not None
            spp = tpp * spec.n_streams
            pooled_symbols = pooled_code.encode_symbols(
                pooled_source,
                np.arange(page * spp, (page + 1) * spp, dtype=np.int64),
            )
            symbols = {
                stream.stream_id: pooled_symbols[
                    stream_idx::spec.n_streams, :stream.symbol_bits]
                for stream_idx, stream in enumerate(spec.stream_profiles)
            }
        else:
            assert codes is not None and sources is not None
            esis = np.arange(page * tpp, (page + 1) * tpp, dtype=np.int64)
            symbols = {
                stream.stream_id: codes[stream.stream_id].encode_symbols(
                    sources[stream.stream_id], esis)
                for stream in spec.stream_profiles
            }
        states = compose_color_page_cells(
            spec, page, symbols, metadata_k, version=METADATA_VERSION)
        dots = color_cells_to_dot_planes(states, place.dots_per_cell)
        doc = PSDoc(
            page_dots_xy=place.page_dots_xy,
            jobid=_jobid(spec, page, payload),
            title=f"holo {spec.spec_id} p{page:03d}",
            engine_dpi=place.engine_dpi,
        )
        oy, ox = place.origin_dots_yx
        doc.begin_page()
        doc.put_cmyk_bitmap(dots, x_dots=ox, y_dots=oy)
        doc.end_page()
        ps_bytes = doc.render().encode("ascii")
        ps_name = f"page{page:03d}.ps"
        gt_name = f"page{page:03d}_gt.npy"
        (staging / ps_name).write_bytes(ps_bytes)

        # Plane-major makes each separation's packed bytes contiguous and
        # gives the sidecar unambiguous C/M/Y audit digests.  K remains
        # implicit and exactly zero in the composite renderer.
        packed_gt = np.packbits(
            np.moveaxis(dots, -1, 0), axis=2, bitorder="big")
        np.save(staging / gt_name, packed_gt)
        plane_sha = tuple(
            hashlib.sha256(
                packed_gt[plane].tobytes(order="C")
            ).hexdigest()
            for plane in range(3)
        )
        pages.append(EmittedPage(
            page=page,
            ps_path=out_dir / ps_name,
            ps_sha256=hashlib.sha256(ps_bytes).hexdigest(),
            gt_path=out_dir / gt_name,
            gt_sha256=hashlib.sha256(
                packed_gt.tobytes(order="C")).hexdigest(),
            gt_plane_sha256=plane_sha,  # type: ignore[arg-type]
        ))
    vol = EmittedVolume(
        plan=plan,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        pages=tuple(pages),
    )
    write_manifest(
        staging / "manifest.json",
        vol,
        profile=profile,
        printer_id=printer_id,
        sheet=place.sheet,
    )
    staging.rename(out_dir)
    return vol


def _jobid(spec: FormatSpec, page: int, payload: bytes) -> str:
    return hashlib.sha256(spec.seed + b"/" + str(page).encode() + b"/"
                          + hashlib.sha256(payload).digest()).hexdigest()[:8]
