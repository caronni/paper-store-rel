"""Pure certified-color versus compact-evidence comparison kernel.

This leaf is exactly the per-codec comparison kernel consumed by the ONE
divergence pairing loop (:func:`holo.receive.records.certificate_divergence`)
and by the barrier's replay of durable divergence counters — nothing else
lives here:

* CMY8 compares the named certificate stream with the sign of that evidence
  column; and
* CMY7 compares the exact reconstructed seven-state tile with
  ``argmax([W=0, C..MY relative scores])``.

K keeps its established scalar kernel inline in the records pairing loop.
"""
from __future__ import annotations

import numpy as np

from ..core import channel
from ..format.descriptor import FormatSpec
from ..format.profiles import Family
from .color_projection import project_certified_color_tile
from .evidence import TileCertificateRecord
from .evidence_blocks import EvidenceBlock


def _expected_kind(spec: FormatSpec) -> str:
    if not isinstance(spec, FormatSpec):
        raise TypeError("color divergence requires a FormatSpec")
    if spec.codec_family is Family.CMY7:
        return "cmy7"
    if spec.codec_family is Family.CMY8:
        return "cmy8"
    raise ValueError(
        f"{spec.codec_id}: color divergence accepts only CMY7/CMY8 rows")


def color_divergence_counts(
    block: EvidenceBlock,
    certificate: TileCertificateRecord,
    spec: FormatSpec,
) -> tuple[int, int]:
    kind = _expected_kind(spec)
    if not isinstance(block, EvidenceBlock):
        raise TypeError("color divergence contains a foreign evidence block")
    if not isinstance(certificate, TileCertificateRecord):
        raise TypeError("color divergence contains a foreign certificate")
    if block.kind != kind:
        raise ValueError(
            f"{spec.spec_id}: {block.kind} evidence cannot drive "
            f"{kind} divergence")
    address = (certificate.page, *certificate.tile_yx)
    if block.address != address:
        raise ValueError(
            "color divergence certificate and evidence addresses differ")

    projection = project_certified_color_tile(
        (certificate,), spec, address)
    flat = block.observed_flat().astype(np.int64, copy=False)
    n_observed = int(flat.size)
    if n_observed < 1:
        raise ValueError(
            "color divergence needs at least one observed evidence cell")

    values = block.printed_llr()
    projected_bits = projection.component_bits.reshape(4096, 3)[flat]
    projected_known = projection.known_mask.reshape(4096, 3)[flat]
    if kind == "cmy7":
        if certificate.stream_id != "main":
            raise ValueError("CMY7 divergence requires stream 'main'")
        if not projected_known.all():
            raise ValueError(
                "CMY7 certificate does not reconstruct observed cells")
        scores = np.concatenate(
            (np.zeros((n_observed, 1), np.float32), values),
            axis=1,
        )
        observed = np.argmax(scores, axis=1)
        expected = channel.planes_to_states(projected_bits)
    else:
        try:
            plane = spec.stream_ids.index(certificate.stream_id)
        except ValueError as exc:
            raise ValueError(
                "CMY8 divergence certificate has an unknown stream") from exc
        if not projected_known[:, plane].all():
            raise ValueError(
                "CMY8 certificate does not reconstruct its observed component")
        observed = values[:, plane] > 0.0
        expected = projected_bits[:, plane].astype(bool, copy=False)

    return n_observed, int(np.count_nonzero(observed != expected))


__all__ = [
    "color_divergence_counts",
]
