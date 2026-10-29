"""Vehicles for the format-law tests that used to ride `holo.receive`.

Gate E re-home (src/holo/receiver/docs/retirement_docs-2026-09/GATE-E-BRIEF.md): two
vehicles replace the v1 receiver — generator-side certificates fed to
holo3's format-side close, and holo3's production receiver run on a
rendered page.  No receiver semantics live here; both are thin adapters.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from holo.format.descriptor import FormatSpec
from holo.receiver import data
from holo.receiver.format import identity


def holo3_row(format_ref: str):
    """The holo3 fact row for a format string src/holo also resolves."""
    return identity.resolve_format_ref(format_ref)


def gt_cell_states(gt_path: Path, spec: FormatSpec) -> np.ndarray:
    """A colour page's plane GT back to its presence-id field (cells are
    solid, so one dot per cell carries the state)."""
    packed = np.load(gt_path, allow_pickle=False)
    dots = spec.cell_dots
    width = spec.cells_yx[1] * dots
    planes = np.unpackbits(packed, axis=2, count=width,
                           bitorder="big")[:, ::dots, ::dots]
    return (planes[0] | planes[1] << 1 | planes[2] << 2).astype(np.uint8)


def certificate(row, counter: int, stream_id: str, metadata_bit: int,
                symbol: np.ndarray, *, source: str = "generator"):
    """One generator-side certificate in the shape holo3's close reads.

    ``user_bits`` is the printed tile's payload: the metadata bit first,
    then the fountain symbol — the same order the tile codec carries.
    """
    page, local = divmod(int(counter), row.tiles_per_page)
    ty, tx = divmod(local, row.tiles_yx[1])
    return data.Certificate(
        page=page, ty=ty, tx=tx, stream_id=stream_id,
        user_bits=np.concatenate(
            ([int(metadata_bit)], np.asarray(symbol, np.uint8))
        ).astype(np.uint8),
        source=source)


def generator_certificates(format_ref: str, payload: bytes, q: float, *,
                           counters=None, stream_ids=None):
    """Every printed tile's user bits, straight from the generator.

    The same packing, fountain and metadata word `holo.gen.emit` composes
    onto the page, minted directly — a page and a channel add nothing a
    close can see, and the close is what these laws are about.
    """
    from holo.core import fountain
    from holo.format import metadata, streamset
    from holo.format.resolve import resolve_format_ref
    from holo.gen.plan import plan_volume

    spec = resolve_format_ref(format_ref)
    row = holo3_row(format_ref)
    plan = plan_volume(spec, len(payload), q)
    profiles = [profile for profile in spec.stream_profiles
                if stream_ids is None or profile.stream_id in stream_ids]
    if counters is None:
        counters = range(plan.n_pages * spec.tiles_per_page)
    counters = np.asarray(sorted(counters), dtype=np.int64)
    layout = streamset.StreamSet(tuple(
        (profile.stream_id, profile.symbol_bits)
        for profile in spec.stream_profiles))

    certs = []
    if spec.pooled_fountain:
        k_meta, source = streamset.pooled_pack_payload(payload, layout)
        n = spec.n_streams
        code = fountain.VolumeCode(
            plan.k_total, spec.symbol_bits, spec.seed,
            tiles_per_page=spec.tiles_per_page, n_streams=n,
            groups=spec.column_groups)
        word = metadata.encode_metadata(0, k_meta)
        bound = metadata.max_equation_index(n)
        index_of = {profile.stream_id: index for index, profile
                    in enumerate(spec.stream_profiles)}
        for profile in profiles:
            stream = index_of[profile.stream_id]
            esis = counters * n + stream
            symbols = code.encode_symbols(source, esis)
            for position, counter in enumerate(counters):
                certs.append(certificate(
                    row, int(counter), profile.stream_id,
                    metadata.tile_bit(word, int(esis[position]),
                                      max_index=bound),
                    symbols[position, :profile.symbol_bits]))
        return plan, certs

    packed = streamset.pack_payload(payload, layout)
    sources = {stream.stream_id: stream.rows for stream in packed.streams}
    word = metadata.encode_metadata(0, packed.k_total)
    bits = metadata.tile_bits(word, counters)
    for profile in profiles:
        code = fountain.VolumeCode(
            packed.k_total, profile.symbol_bits, spec.seed,
            tiles_per_page=spec.tiles_per_page,
            **({} if profile.fountain_aux is None else {
                "stream_id": profile.stream_id,
                "fountain_aux": profile.fountain_aux}))
        symbols = code.encode_symbols(sources[profile.stream_id], counters)
        for position, counter in enumerate(counters):
            certs.append(certificate(row, int(counter), profile.stream_id,
                                     int(bits[position]), symbols[position]))
    return plan, certs


@dataclass(frozen=True)
class Holo3Decode:
    """What one `holo3 decode` run says, without reading receiver state."""

    argv: tuple[str, ...]
    exit_code: int
    payload: bytes | None
    report: dict
    run_dir: Path
    stdout: str

    @property
    def status(self) -> str:
        return str(self.report.get("close", {}).get("status", "unknown"))

    @property
    def certified(self) -> int:
        return int(self.report.get("close", {}).get("certified", 0))

    @property
    def plane_certs(self) -> dict[str, int]:
        return {str(name): int(count)
                for name, count in self.report.get("plane_certs", ())}

    @property
    def payload_sha256(self) -> str | None:
        if self.payload is None:
            return None
        return hashlib.sha256(self.payload).hexdigest()


def write_capture(raster, path: Path) -> Path:
    """A raster becomes a TIFF; an existing capture file passes through."""
    if isinstance(raster, (str, Path)):
        return Path(raster)
    import tifffile

    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(path, np.ascontiguousarray(raster))
    return path


def decode_with_holo3(captures, format_ref: str, work_dir: Path, label: str,
                      *, workers: int = 8, max_pages: int | None = 1,
                      extra_argv: tuple[str, ...] = ()) -> Holo3Decode:
    """Run `holo3 decode` on ``(raster, dpi)`` pairs, in process.

    Rasters are written as TIFFs under ``work_dir`` because the CLI is the
    only supported entry point; nothing here interprets receiver state.

    ``max_pages`` declares the page domain the caller already knows it
    presented; ``None`` leaves it undeclared and holo3 searches blind.
    """
    # Every caller here renders ONE page and asserts plan.n_pages == 1, so
    # the blind multi-page search is pure cost: MEASURED 2026-09-05, the
    # dead-plane gate burned 398 of its 406 cpu-s in placement without the
    # declaration.  Bounded and undeclared domains recover the same K sha:
    # src/holo/receiver/tests/test_h3_survey_pitch_fallback.py (w1,
    # --max-pages 1) against test_h3_e2e_sims.py (undeclared).
    from holo.receiver import cli

    base = Path(work_dir) / label
    base.mkdir(parents=True, exist_ok=True)
    scans = [str(write_capture(raster, base / f"capture-{index}.tif"))
             for index, (raster, _dpi) in enumerate(captures)]
    out_path = base / "payload.bin"
    run_dir_base = base / "run"
    argv = ("decode", *scans,
            *(part for _raster, dpi in captures
              for part in ("--dpi", str(int(dpi)))),
            "--format", format_ref, "--out", str(out_path),
            "--workers", str(workers), "--run-dir", str(run_dir_base),
            *(() if max_pages is None
              else ("--max-pages", str(int(max_pages)))),
            *extra_argv)
    run_dir = cli.run_dir_for(run_dir_base)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        exit_code = cli.main(list(argv))
    report_path = run_dir / "report.json"
    report = (json.loads(report_path.read_text(encoding="utf-8"))
              if report_path.is_file() else {})
    payload = out_path.read_bytes() if out_path.is_file() else None
    return Holo3Decode(argv, exit_code, payload, report, run_dir,
                       out.getvalue())
