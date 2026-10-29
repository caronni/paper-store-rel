"""Ground truth: the golden payload re-encoded through holo1 generation.

Per-tile expected USER BITS for the whole identity, re-encoded from the
volume's recovered payload through the MAIN tree's ``src/holo``
generation arithmetic, stopped at the user-bit boundary. Every crop
certificate on either side is checked against it — a mismatch is a WRONG
CERTIFICATE, which is a correctness failure of the receiver that minted
it, not a yield fact.

THE TWO RECORDED TRAPS are avoided by construction (memory:
truth-path discipline): no ``make_data`` is consulted (the payload is
the sha-verified recovered bin), and no slot raster is touched (the
comparison lives at USER BITS, upstream of the tile encoder's slot
permutation and of the colour cell permutation).

THE THREE FAMILIES, each following its own emitter exactly:

* **K** — ``gen/compose.compose_page_cells``: ``user[0] =
  metadata.tile_bits(encode_metadata(0, k_total))``, ``user[1:] =
  VolumeCode(k_total, symbol_bits, seed).encode_symbols(pack_source(
  envelope.wrap(payload), ...))``.
* **CMY7 / non-pooled CMY8** — ``gen/emit._emit_color_volume``'s
  per-stream branch: ``streamset.pack_payload`` sources, one
  ``VolumeCode`` per stream (with its ``stream_id`` and
  ``fountain_aux``), one shared metadata bit per tile.
* **pooled CMY8 (-v1)** — the pooled branch: ONE fountain over
  ``esi = counter*n + stream`` with the row's ``column_groups``, sliced
  stream-minor and cut to each stream's own width, and one DISTINCT
  metadata equation per stream at ``equation_index(counter, s, n)``.
  A uniform row is one group under the frozen order and the cut is
  the whole symbol, so it reconstructs bit-identically either way.

All three are q-independent: q only sizes the page count in
``plan_volume``, and the page count is an input here (1 for every
declared volume).

THE GATE. :func:`validate_against_state` checks every certificate in
the volume's archived holo1 state against the reconstruction, exactly —
a superset of the both-certified bar, and strictly harder. Measured
green 2026-08-29: e029 1,940/1,940, xerox-c2-cmy7 1,559/1,559,
xerox-c2-cmy8 5,370/5,370, all zero mismatches. Any mismatch raises
:class:`GTValidationError` and the battery reports nothing.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

Address = tuple[int, int, int, str]


class GTValidationError(Exception):
    """Ground truth failed validation — nothing may be reported."""


@dataclass(frozen=True)
class GroundTruth:
    format_ref: str
    payload_sha256: str
    tiles_yx: tuple[int, int]
    streams: tuple[str, ...]
    #: (page, ty, tx, stream) -> uint8 user bits: [0] metadata, [1:] symbol.
    user_bits: dict[Address, np.ndarray]


def load_payload(path: Path, expect_sha: str, expect_bytes: int) -> bytes:
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != expect_sha or len(data) != expect_bytes:
        raise GTValidationError(
            f"golden payload {path}: sha {sha[:12]}…/{len(data)} B, "
            f"want {expect_sha[:12]}…/{expect_bytes} B")
    return data


def reconstruct(format_ref: str, payload: bytes,
                pages: int = 1) -> GroundTruth:
    """Re-encode the payload through holo1's generation arithmetic."""
    from holo.core import fountain
    from holo.format import envelope, metadata, streamset
    from holo.format.envelope import source_symbol_count
    from holo.format.profiles import Family
    from holo.format.resolve import resolve_format_ref
    from holo.gen.emit import METADATA_VERSION

    spec = resolve_format_ref(format_ref)
    # spec._tiles_yx over the public field for tile_differential's own
    # documented reason: the public tiles_yx is None on a layout-derived
    # fossil identity, which is exactly what these volumes decode as.
    tiles_y, tiles_x = spec._tiles_yx
    tpp = spec.tiles_per_page
    counters_of = lambda page: np.array(                    # noqa: E731
        [spec.tile_counter(page, ty, tx)
         for ty in range(tiles_y) for tx in range(tiles_x)], dtype=np.int64)
    out: dict[Address, np.ndarray] = {}

    if spec.codec_family is Family.K:
        k_total = source_symbol_count(len(payload),
                                      spec.aggregate_symbol_bits)
        source = fountain.pack_source(envelope.wrap(payload), k_total,
                                      spec.symbol_bits)
        code = fountain.VolumeCode(k_total, spec.symbol_bits, spec.seed,
                                   tiles_per_page=tpp)
        word = metadata.encode_metadata(METADATA_VERSION, k_total)
        for page in range(pages):
            symbols = code.encode_symbols(
                source,
                np.arange(page * tpp, (page + 1) * tpp, dtype=np.int64))
            meta_bits = metadata.tile_bits(word, counters_of(page))
            for index in range(tpp):
                ty, tx = index // tiles_x, index % tiles_x
                user = np.empty(spec.tile_user_bits, dtype=np.uint8)
                user[0] = meta_bits[index]
                user[1:] = symbols[index]
                user.setflags(write=False)
                out[(page, ty, tx, "main")] = user
        return GroundTruth(format_ref=format_ref,
                           payload_sha256=hashlib.sha256(payload).hexdigest(),
                           tiles_yx=(tiles_y, tiles_x), streams=("main",),
                           user_bits=out)

    if spec.codec_family not in (Family.CMY7, Family.CMY8):
        raise GTValidationError(
            f"{format_ref}: no ground-truth path for codec family "
            f"{spec.codec_family}")

    layout = streamset.StreamSet(tuple(
        (stream.stream_id, stream.symbol_bits)
        for stream in spec.stream_profiles))
    n_streams = spec.n_streams
    if spec.pooled_fountain:
        k_meta, pooled_source = streamset.pooled_pack_payload(payload, layout)
        pooled_code = fountain.VolumeCode(
            n_streams * k_meta, spec.symbol_bits, spec.seed,
            tiles_per_page=tpp, n_streams=n_streams,
            groups=spec.column_groups)
        metadata_k = k_meta
    else:
        packed = streamset.pack_payload(payload, layout)
        sources = {source.stream_id: source.rows for source in packed.streams}
        codes = {stream.stream_id: fountain.VolumeCode(
            packed.k_total, stream.symbol_bits, spec.seed,
            tiles_per_page=tpp, stream_id=stream.stream_id,
            fountain_aux=stream.fountain_aux)
            for stream in spec.stream_profiles}
        metadata_k = packed.k_total
    word = metadata.encode_metadata(METADATA_VERSION, metadata_k)

    for page in range(pages):
        counters = counters_of(page)
        if spec.pooled_fountain:
            spp = tpp * n_streams
            pooled = pooled_code.encode_symbols(
                pooled_source,
                np.arange(page * spp, (page + 1) * spp, dtype=np.int64))
            symbols = {stream.stream_id: pooled[index::n_streams,
                                                :stream.symbol_bits]
                       for index, stream in enumerate(spec.stream_profiles)}
            bound = metadata.max_equation_index(n_streams)
            meta_bits = np.stack([
                metadata.tile_bits(
                    word,
                    np.array([metadata.equation_index(int(counter), index,
                                                      n_streams)
                              for counter in counters], dtype=np.int64),
                    max_index=bound)
                for index in range(n_streams)], axis=1)
        else:
            esis = np.arange(page * tpp, (page + 1) * tpp, dtype=np.int64)
            symbols = {stream.stream_id: codes[stream.stream_id
                                               ].encode_symbols(
                sources[stream.stream_id], esis)
                for stream in spec.stream_profiles}
            base = metadata.tile_bits(word, counters)
            meta_bits = np.stack([base] * n_streams, axis=1)
        for index in range(tpp):
            ty, tx = index // tiles_x, index % tiles_x
            for position, stream_id in enumerate(spec.stream_ids):
                symbol = symbols[stream_id][index]
                user = np.empty(symbol.size + 1, dtype=np.uint8)
                user[0] = meta_bits[index, position]
                user[1:] = symbol
                user.setflags(write=False)
                out[(page, ty, tx, stream_id)] = user
    return GroundTruth(format_ref=format_ref,
                       payload_sha256=hashlib.sha256(payload).hexdigest(),
                       tiles_yx=(tiles_y, tiles_x),
                       streams=tuple(spec.stream_ids), user_bits=out)


def check_bits(gt: GroundTruth, address: Address,
               bits: np.ndarray) -> tuple[bool, int]:
    """(matches, n_bit_mismatch); ``-1`` = outside the GT domain or a
    length disagreement, which is a reconstruction bug, not a data fact."""
    expected = gt.user_bits.get(address)
    if expected is None:
        return False, -1
    if bits.shape[0] < expected.shape[0]:
        return False, -1
    return (bool(np.array_equal(bits[:expected.size], expected)),
            int(np.count_nonzero(bits[:expected.size] != expected)))


def validate_bits(gt: GroundTruth, observed: Mapping[Address, np.ndarray],
                  label: str) -> int:
    """PURE gate core: every observed address must match exactly."""
    problems: list[str] = []
    for address in sorted(observed):
        match, n_bad = check_bits(gt, address, observed[address])
        if not match:
            problems.append(f"{address}: "
                            + ("outside the GT domain / wrong width"
                               if n_bad < 0 else f"{n_bad} bit(s) differ"))
    if problems:
        raise GTValidationError(
            f"GT validation FAILED on {label}: {len(problems)} "
            f"address(es) disagree with the re-encoded golden payload — "
            "refusing to report anything. " + "; ".join(problems[:20])
            + ("; …" if len(problems) > 20 else ""))
    return len(observed)


def validate_against_state(gt: GroundTruth,
                           certified_bits: Mapping[Address, np.ndarray],
                           label: str) -> int:
    """The gate: the archived holo1 state's certificates, exactly."""
    if not certified_bits:
        raise GTValidationError(
            f"{label}: the archived holo1 state has no certificates — "
            "cannot validate ground truth")
    return validate_bits(gt, certified_bits, label)
