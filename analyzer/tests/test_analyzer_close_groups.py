"""`analyzer.close` on a COLUMN-GROUP row (uneven cmy8 triplet, 2026-09-04).

The consistency check and the localization run per (block, group), the
way `fountain.Decoder` solves such a row; sheets H/I/J are uniform rows
= the one-group case of the same code path (`test_analyzer_close.py`).
The fixture is holo3's own mixed volume (widths 40/40/30 = four groups
of 10 columns, the narrow plane carrying three of them per tile),
so the certificates were produced by holo3's test-side encoder and the
re-encoding by its decoder's generator rows — two spellings, one answer.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np

from analyzer import close as close_mod
from holo3.tests.test_h3_format_column_groups import _mixed_volume


def _volume(seed_int: int):
    payload = np.random.default_rng(seed_int).integers(
        0, 256, 600, dtype=np.uint8).tobytes()
    _k_meta, k_total, code, certs, row = _mixed_volume(payload)
    assert code.groups.n_groups == 4
    return payload, k_total, code, tuple(certs), row


def _poison(certs, index: int, positions) -> tuple[tuple, tuple]:
    """Flip `positions` of one certificate's SYMBOL (user_bits[1:])."""
    bits = np.asarray(certs[index].user_bits, np.uint8).copy()
    for position in positions:
        bits[1 + int(position)] ^= 1
    out = list(certs)
    out[index] = replace(certs[index], user_bits=bits)
    return tuple(out), close_mod.key_of(certs[index])


def _pick(code, row, certs, *, stream_id: str, repair: bool) -> int:
    """Index of a `stream_id` certificate whose slice sits on a repair
    row (`repair=True`) or a source row (`repair=False`)."""
    for index, cert in enumerate(certs):
        if cert.stream_id != stream_id:
            continue
        tile = code.tile_slots(close_mod.symbol_index(row, cert))
        if not tile.groups:
            continue                           # a straddler carrying nothing
        if (tile.repair_row is not None) == repair:
            return index
    raise AssertionError("no such certificate")


def test_a_mixed_volume_is_consistent_per_block_and_group():
    _payload, k_total, code, certs, row = _volume(41)
    report = close_mod.consistency(certs, row)
    assert report["checked"] and report["ok"] and report["proven"]
    assert report["k_total"] == k_total
    assert report["n_inconsistent"] == 0
    _report, blocks, _key_at = close_mod._consistency(certs, row)
    assert {block.group for block in blocks} == {0, 1, 2, 3}
    bounds = code.groups.bounds
    for block in blocks:
        assert block.n_redundant > 0
        width = bounds[block.group + 1] - bounds[block.group]
        assert block.source.shape == (block.k_bits, width)
        assert all(hi - lo == width for lo, hi in block.slots)


def test_a_poisoned_narrow_repair_symbol_is_localized_and_repaired():
    payload, _k_total, code, certs, row = _volume(42)
    index = _pick(code, row, certs, stream_id="Y", repair=True)
    tile = code.tile_slots(close_mod.symbol_index(row, certs[index]))
    lo, hi = tile.edges[0], tile.edges[1]
    poisoned, key = _poison(certs, index, (lo, lo + 1, hi - 1))
    report = close_mod.consistency(poisoned, row)
    assert report["ok"] is False
    assert report["inconsistent_keys"] == [list(key)]
    found = close_mod.localize(poisoned, row)
    assert found["localized"] is True
    assert found["poisoned_keys"] == [list(key)]
    name = ",".join(str(part) for part in key)
    assert found["corrections"][name]["n_bits_flipped"] == 3
    assert np.array_equal(found["corrected_user_bits"][name],
                          certs[index].user_bits)
    assert found["corrections_verified"]["consistent"] is True
    assert found["close"]["verified"] is True
    assert found["close"]["payload_sha256"] == hashlib.sha256(
        payload).hexdigest()


def test_a_poisoned_source_symbol_is_localized_by_consensus_per_group():
    payload, _k_total, code, certs, row = _volume(43)
    index = _pick(code, row, certs, stream_id="C", repair=False)
    tile = code.tile_slots(close_mod.symbol_index(row, certs[index]))
    # one bit in EACH group slice the symbol carries: every group accuses it
    positions = [lo + 2 for lo in tile.edges[:-1]]
    poisoned, key = _poison(certs, index, positions)
    found = close_mod.localize(poisoned, row)
    assert found["localized"] is True
    assert found["poisoned_keys"] == [list(key)]
    rules = {detail["rule"] for record in found["rounds"]
             for detail in record.get("detail", [])}
    assert "consensus" in rules
    name = ",".join(str(part) for part in key)
    assert found["corrections"][name]["n_bits_flipped"] == len(positions)
    assert np.array_equal(found["corrected_user_bits"][name],
                          certs[index].user_bits)
    assert found["corrections_verified"]["consistent"] is True
    assert found["close"]["payload_sha256"] == hashlib.sha256(
        payload).hexdigest()
