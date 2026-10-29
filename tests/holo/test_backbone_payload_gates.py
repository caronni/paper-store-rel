"""Task-10(a): honest per-coding real-payload round-trip gates.

Gate E re-home: two vehicles replace the v1 receiver.  The per-coding
net now runs generator-minted certificates through `holo.receiver.format.close`
— the production close — which is where the payload backbone actually
lives; the printed-page half keeps one representative row end to end
through holo3's receiver.

The acceptance net for the stream-generic payload backbone (KISS task 10,
user rescope 2026-07-30): every coding row round-trips a REAL multi-symbol
payload on a compact page.

Why these gates exist: the historical qualification payloads were 32-64
bytes, which collapses the fountain to ~1 source symbol, and an all-zero
payload leaves nearly all source symbols identical — either way the fountain
block assembly and rank machinery went unexercised.  Each gate here pins an
explicit ``k_total`` floor so it cannot silently degrade back to a trivial
fountain, and asserts the full semantic outcome the backbone refactor must
reproduce: recovered bytes, VERIFIED close, the row's own block space.

Identity note: six of the nine CODINGS rows are nameable in the v2
grammar at a compact tile matrix; the two cmy8 ``-v0`` rows are not
(cmy8 requires a rung there), so they ride their own frozen ``L:``
fossils at printed size.  One ref per coding row, all nine covered.
"""
from __future__ import annotations

import hashlib
import os
import warnings
from pathlib import Path

import pytest

from holo.format.descriptor import CODINGS
from holo.format.families import Family
from holo.format.resolve import resolve_format_ref
from holo.gen.emit import emit_volume
from holo.gen.plan import plan_volume
from holo.receiver.format import close

from _colour_gate_render import colour_raster
from _receive_free import decode_with_holo3, generator_certificates, holo3_row

# q=0.8 (the e016 K/N) on the 49-tile K pages: the §13.16 planner's
# 16-symbol fountain reserve leaves k_total ~23 — a real multi-symbol
# fountain (q=0.5 would collapse it to 7).  Color pages carry q=0.5 so the
# fountain rank stays comfortably inside the measured ~72% placement
# coverage.
_Q_K = 0.8
_Q_COLOR = 0.5
_K_FLOOR = 20              # the honest-fountain floor: >= 20 source symbols

# One format reference per CODINGS row, at the compact geometry the gate
# has always used (K 7x7, colour 10x10) where the v2 grammar can name it.
_ROW_REFS = {
    "c3-r0550": "c3-k-r0550@7x7",
    "c2-r0550": "c2-k-r0550@7x7",
    "c2-r0700": "c2-k-r0700@7x7",
    "c2-cmy7-p120-v0": "c2-cmy7@10x10",
    "c3-cmy7-p120-v0": "c3-cmy7@10x10",
    "c2-cmy8-p120-v0": "L:c2-cmy8-p120-v0@3328x2304",
    "c3-cmy8-p120-v0": "L:c3-cmy8-p120-v0@2240x1536",
    "c2-cmy8-p120-v1": "c2-cmy8-r0550@10x10",
    "c3-cmy8-p120-v1": "c3-cmy8-r0550@10x10",
}

# Default suite: one K row + one 3-stream color row; the colour
# representative is the POOLED -v1 row.  The full nine-row net runs with
# HOLO_RUN_SLOW_TESTS=1 and is the mandatory pre/post checkpoint for
# backbone refactors.
_FAST_ROWS = ("c3-r0550", "c3-cmy8-p120-v1")


def test_every_coding_row_has_a_reference() -> None:
    assert tuple(_ROW_REFS) == tuple(CODINGS)


def _rows() -> tuple[str, ...]:
    if os.environ.get("HOLO_RUN_SLOW_TESTS"):
        return tuple(CODINGS)
    return _FAST_ROWS


def _q_for(spec) -> float:
    return _Q_K if spec.codec_family is Family.K else _Q_COLOR


def _real_payload(spec, format_ref: str, q: float) -> bytes:
    """Largest single-page payload — always a multi-symbol fountain."""
    low, high = 1, 512_000
    while low < high:  # largest n with a one-page plan
        mid = (low + high + 1) // 2
        try:
            pages = plan_volume(spec, mid, q).n_pages
        except ValueError:
            pages = 2
        if pages == 1:
            low = mid
        else:
            high = mid - 1
    length = max(1, low)  # full fill: maximum source symbols on one page
    payload = hashlib.shake_256(
        b"holo/backbone-q1/" + format_ref.encode("ascii")).digest(length)
    assert len(set(payload[index:index + 8]
                   for index in range(0, length - 8, 8))) > length // 16
    return payload


@pytest.mark.parametrize("coding_id", _rows())
def test_real_payload_round_trip_closes_every_stream(coding_id: str) -> None:
    format_ref = _ROW_REFS[coding_id]
    spec = resolve_format_ref(format_ref)
    row = holo3_row(format_ref)
    q = _q_for(spec)
    payload = _real_payload(spec, format_ref, q)

    plan, certs = generator_certificates(format_ref, payload, q)
    assert plan.n_pages == 1
    assert plan.k_total >= _K_FLOOR, (
        f"{coding_id}: k_total {plan.k_total} is a trivial fountain")
    assert len(certs) == spec.tiles_per_page * len(spec.stream_ids)
    assert {cert.stream_id for cert in certs} == set(spec.stream_ids)

    result = close.close_volume(certs, row)
    assert result.status == "verified", (
        f"{coding_id}: {result.reason}")
    assert result.payload == payload, f"{coding_id}: recovered bytes differ"
    assert result.k_total == plan.k_total
    assert result.metadata_version == 0
    # The row's own block space: a pooled row carries ONE unattributed
    # pool, a per-stream row labels every block with its stream.
    labels = {block.stream_id for block in result.blocks}
    if spec.pooled_fountain:
        assert labels == {None}
    elif len(spec.stream_ids) > 1:
        assert labels == set(spec.stream_ids)


def test_certified_streams_must_be_declared_by_the_printed_row() -> None:
    """A close reads only the streams its own row declares.

    The v1 gate here checked a session's format against its state; that
    is receiver bookkeeping and went with the receiver.  What the close
    itself can and must refuse is a certificate from a foreign stream —
    the seed binds identity on the PAGE (keystream, pilots), not in a
    close over systematic symbols, so nothing weaker is honest.
    """
    payload = hashlib.shake_256(b"holo/backbone-substitute").digest(4_000)
    _plan, certs = generator_certificates("c3-cmy8-r0550@10x10", payload,
                                          _Q_COLOR)
    assert close.close_volume(certs, holo3_row("c3-cmy8-r0550@10x10")
                              ).payload == payload
    foreign = close.close_volume(certs, holo3_row("c3-k-r0550@7x7"))
    assert foreign.status == "integrity_failure"
    assert foreign.payload is None
    assert "not declared by the printed row" in (foreign.reason or "")


def test_the_pooled_colour_row_decodes_byte_exact_from_a_printed_page(
    tmp_path: Path,
) -> None:
    """The printed-page half: emit, render, and let holo3 read it back.

    Channel: the qualification forward model at nominal defaults.
    Robustness under the measured channel is a separate axis
    (test_measured_channel_gate).
    """
    format_ref = "c3-cmy8-r0550@10x10"
    spec = resolve_format_ref(format_ref)
    payload = hashlib.shake_256(b"holo/backbone-page").digest(20_000)
    plan = plan_volume(spec, len(payload), _Q_COLOR)
    assert plan.n_pages == 1 and plan.k_total >= _K_FLOOR

    volume = emit_volume(spec, payload, _Q_COLOR, tmp_path / "volume")
    raster = colour_raster(spec, volume.pages[0].gt_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        decode = decode_with_holo3(((raster, 1200.0),), format_ref,
                                   tmp_path, "backbone-colour")

    assert decode.exit_code == 0, decode.stdout
    assert decode.payload == payload
    assert decode.status == "verified"
    assert set(decode.plane_certs) == set(spec.stream_ids)
    # Symmetric stream treatment: a pooled stop lands wherever the
    # barrier caught it, but never on one plane alone.  The count SPREAD
    # is not a law: MEASURED 2026-09-05, it is 2 under the blind page
    # search and 2-4 with the page domain declared (a scheduling
    # artifact), so only the non-empty floor is asserted.
    counts = decode.plane_certs
    assert min(counts.values()) > 0
