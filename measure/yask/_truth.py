"""Ground truth, from the EMITTED payload and the emitted cell field.

Sheet H's volume has never been recovered (the 2026-08-30 seven-capture
harvest closes at 4,237 of 5,277 symbols, status ``open``), so the
crop-parity route — re-encode the RECOVERED payload — is unavailable
here. The generation record supplies the same thing one step earlier:

* ``payload-counting.bin`` — the exact bytes the sheet was generated
  from, with the manifest's own sha256 checked before anything is read;
* ``page000_gt.npy`` — the emitted PRINTED FIELD, ``packbits``-packed
  ``(plane, dot_y, packed_dot_x)`` at ``cell_dots`` dots per cell, plane
  order C, M, Y.

Two levels of truth, and this module keeps them apart:

* **user bits** — ``crop_parity._gt.reconstruct`` re-encodes the payload
  through ``src/holo``'s generation arithmetic and stops at the user-bit
  boundary. This is what a certificate is checked against, exactly as
  the crop-parity battery checks its own (memory: truth-path
  discipline — no ``make_data``, no slot raster).
* **cell bits** — the emitted field, per plane per cell. This is what
  the DETECTOR is measured against (d', cell error rate), and it is
  never used to make or gate a certificate.

:func:`check_projection_against_field` closes the loop between them: the
per-tile projection built from user bits (the format's own
``certified_projection`` arithmetic) must equal the emitted field cell
for cell. A disagreement means the reconstruction is wrong and nothing
downstream may be reported.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TILE = 64
PLANE_ORDER = ("C", "M", "Y")


@dataclass(frozen=True)
class EmittedField:
    """The emitted printed field, one bit per (plane, cell)."""

    #: (3, cells_y, cells_x) uint8 presence bits, plane order C, M, Y.
    plane_bits: np.ndarray
    cell_dots: int
    sha256: str

    @property
    def cells_yx(self) -> tuple[int, int]:
        return (int(self.plane_bits.shape[1]), int(self.plane_bits.shape[2]))

    def states(self) -> np.ndarray:
        """(cells_y, cells_x) uint8 cell states, C + 2M + 4Y."""
        return (self.plane_bits[0]
                + 2 * self.plane_bits[1]
                + 4 * self.plane_bits[2]).astype(np.uint8)

    def bits_at(self, cells_yx: np.ndarray) -> np.ndarray:
        """(N, 3) presence bits at the given page cells."""
        cells = np.asarray(cells_yx, np.int64)
        return np.stack(
            [self.plane_bits[plane, cells[:, 0], cells[:, 1]]
             for plane in range(3)], axis=1)


def load_payload(directory: Path) -> bytes:
    """The emitted payload, gated on the generation manifest's own sha."""
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    want = str(manifest["payload"]["sha256"])
    want_bytes = int(manifest["payload"]["bytes"])
    data = (directory / "payload-counting.bin").read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != want or len(data) != want_bytes:
        raise SystemExit(
            f"yask: {directory.name}/payload-counting.bin is sha "
            f"{got[:12]}…/{len(data)} B, the manifest declares "
            f"{want[:12]}…/{want_bytes} B")
    return data


def load_emitted_field(directory: Path, page: int = 0) -> EmittedField:
    """Unpack ``page000_gt.npy`` down to one bit per plane per CELL."""
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    record = manifest["pages"][page]
    cell_dots = int(manifest["cell_dots"])
    if list(record["gt_plane_order"]) != list(PLANE_ORDER):
        raise SystemExit(f"yask: unexpected gt plane order "
                         f"{record['gt_plane_order']}")
    if record["gt_bitorder"] != "big":
        raise SystemExit(f"yask: unexpected gt bitorder "
                         f"{record['gt_bitorder']}")
    path = directory / record["gt"]
    packed = np.load(path, mmap_mode="r")
    if tuple(packed.shape) != tuple(record["gt_packed_shape"]):
        raise SystemExit(f"yask: {path.name} shape {packed.shape} != "
                         f"declared {record['gt_packed_shape']}")
    cells_y, cells_x = (int(value) for value in manifest["page_cells_yx"])
    # One dot per cell is enough: the emitter paints a cell as a solid
    # cell_dots x cell_dots block, so the top-left dot IS the cell value.
    rows = np.asarray(packed[:, ::cell_dots, :])
    unpacked = np.unpackbits(rows, axis=-1, bitorder="big")
    bits = np.ascontiguousarray(
        unpacked[:, :cells_y, ::cell_dots][:, :, :cells_x]).astype(np.uint8)
    return EmittedField(plane_bits=bits, cell_dots=cell_dots,
                        sha256=str(record["gt_sha256"]))


def check_field_is_block_constant(directory: Path, field: EmittedField,
                                  page: int = 0, n_probe: int = 4096,
                                  seed: int = 20260830) -> int:
    """The one assumption :func:`load_emitted_field` makes, checked.

    Sample cells and require every dot of the cell's ``cell_dots`` block
    to equal the top-left dot. Returns the number of cells probed.
    """
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    record = manifest["pages"][page]
    packed = np.load(directory / record["gt"], mmap_mode="r")
    dots = field.cell_dots
    cells_y, cells_x = field.cells_yx
    rng = np.random.default_rng(seed)
    ys = rng.integers(0, cells_y, n_probe)
    xs = rng.integers(0, cells_x, n_probe)
    for cy, cx in zip(ys.tolist(), xs.tolist()):
        block = np.unpackbits(
            np.asarray(packed[:, cy * dots:(cy + 1) * dots, :]),
            axis=-1, bitorder="big")[:, :, cx * dots:(cx + 1) * dots]
        if not np.all(block == block[:, :1, :1]):
            raise SystemExit(
                f"yask: emitted field is not block-constant at cell "
                f"({cy}, {cx}) — the one-dot-per-cell read is invalid")
    return int(n_probe)


def check_projection_against_field(row: object, geometry: object,
                                   user_bits: dict, field: EmittedField,
                                   page: int, addresses: list) -> dict:
    """Reconstruction gate: user bits -> cells == the emitted field.

    ``addresses`` are (ty, tx) tile positions. For each, the format's own
    ``certified_projection`` is fed the GT user bits of every stream and
    the result compared to the emitted field over the whole 64x64 tile.
    """
    from holo.receiver.data import Certificate
    from holo.receiver.plugins.color_sites import certified_projection

    n_tiles = 0
    n_cells = 0
    problems: list[str] = []
    for ty, tx in addresses:
        certs = {}
        for fact in row.streams:
            bits = user_bits.get((page, ty, tx, fact.stream_id))
            if bits is None:
                break
            certs[(page, ty, tx, fact.stream_id)] = Certificate(
                page=page, ty=ty, tx=tx, stream_id=fact.stream_id,
                user_bits=np.asarray(bits, np.uint8), source="yask/gt")
        else:
            projection = certified_projection(row, geometry, page, ty, tx,
                                              certs)
            if projection is None:
                problems.append(f"({ty}, {tx}): no projection")
                continue
            bits, known = projection
            emitted = field.plane_bits[
                :, ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE]
            emitted = np.moveaxis(emitted, 0, -1)
            if not known.all():
                problems.append(f"({ty}, {tx}): projection incomplete")
                continue
            bad = int(np.count_nonzero(bits != emitted))
            if bad:
                problems.append(f"({ty}, {tx}): {bad} cell bit(s) differ")
            n_tiles += 1
            n_cells += int(emitted.size)
    if problems:
        raise SystemExit(
            "yask: GROUND TRUTH FAILED its own gate — the payload "
            "re-encoding disagrees with the emitted cell field: "
            + "; ".join(problems[:10]))
    return {"tiles": n_tiles, "cells": n_cells}
