"""VERDICT 1 (run channel): the tool works — byte-exact through the real close.

The verdicts' cheapest and most important sentence, and the ONLY one
package hand-off and pre-merge run:

    env/bin/python -m pytest holo2/measure/verdicts/test_roundtrip.py -q

A page emitted by the real ``src/holo`` generator, rendered through the
measured e032 channel with a 2% hard cell error rate, decoded by holo2
through the real composition root — providers, the pull model's placement
source, the real payload chain, the real fountain close — and the volume
comes back byte-exact, or it does not come back. No truth table crosses
into the receiver: it is told the coding, the tile grid and the capture's
DPI, which is all an operator can type.

DESIGN §12's standing bar rides along, because it costs nothing here and
a byte-exact payload does not on its own prove it: every certificate the
run closed on is the emitted truth, and there are no wrong ones.
"""
from __future__ import annotations

import numpy as np

from conftest import PageRun

from holo2.solve import parse_tile_key
from holo2.solve.tilemap import StoreIndex, TileMap


def test_the_volume_comes_back_byte_exact(run_channel: PageRun) -> None:
    """L9: the volume closes VERIFIED and the bytes are the emitted bytes."""
    outcome = run_channel.outcome
    assert outcome.status == "verified", outcome.reason
    assert outcome.payload == run_channel.page.payload
    assert outcome.close is not None
    assert outcome.close["k_total"] == run_channel.page.k_total
    assert outcome.certified >= 48, "the L9 metadata floor was not cleared"


def test_the_close_is_a_durable_verified_stop(run_channel: PageRun) -> None:
    """The verdict is a RECORD, not a return value: it survives the process."""
    import hashlib

    from holo2.core.records import CloseStatus

    with run_channel.open() as session:
        record = session.close_record()
        assert record is not None
        assert record.status is CloseStatus.VERIFIED
        assert record.payload_sha256 == hashlib.sha256(
            run_channel.page.payload).hexdigest()
        assert record.bytes_ref is not None
        assert bytes(session.store.read_blob(
            record.bytes_ref, verify=True)) == run_channel.page.payload
        assert session.terminal


def test_zero_wrong_certificates(run_channel: PageRun) -> None:
    """DESIGN §12, on this run's own certificates. Never relaxed."""
    page = run_channel.page
    with run_channel.open() as session:
        tiles = TileMap(StoreIndex.build(session.store),
                        page.row.stream_ids, page.tiles_yx)
        certified = tiles.certified_keys()
        assert certified
        for key in certified:
            number, ty, tx, _stream = parse_tile_key(key)
            record = tiles.record(key)
            assert number == 0, "a one-sheet volume certified a second page"
            np.testing.assert_array_equal(
                session.store.read_array(record.bits_ref),
                page.truth_bits(ty, tx))
            assert record.metadata_bit == page.truth_metadata_bit(ty, tx)
