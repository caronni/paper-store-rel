"""`analyzer.truth` on a COLUMN-GROUP row (uneven cmy8 triplet).

e046 (2026-10-13) found the offline scorer's reconstruction building the
pooled fountain without the row's column groups and handing every plane
the widest plane's width, so `analyzer score` could not score a grouped
row.  Here the generator's own user bits are recorded as `emit_volume`
composes each tile, and the scorer's door has to return them exactly:
the ruled lever (Y narrow) and e046's triplet (M the widest, C and Y
narrower), both at 10x10.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from analyzer import truth

from ._analyzer_fixtures import det_bytes

GROUPED_REFS = ("c3-cmy8-r0700x0700x0547@10x10",
                "c3-cmy8-r0775x0850x0700@10x10")


@pytest.mark.parametrize("ref", GROUPED_REFS)
def test_the_reconstruction_equals_the_emitted_user_bits(
        ref: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from holo.format.resolve import resolve_format_ref as holo1_resolve
    from holo.gen import color_compose
    from holo.gen.emit import emit_volume
    from holo.receiver.format.identity import resolve_format_ref

    spec = holo1_resolve(ref)
    assert not spec.column_groups.uniform
    emitted: dict[int, tuple[np.ndarray, ...]] = {}
    payload_states = color_compose._payload_states

    def record(spec_, counter, users):
        emitted[int(counter)] = tuple(np.array(user) for user in users)
        return payload_states(spec_, counter, users)

    monkeypatch.setattr(color_compose, "_payload_states", record)
    payload = det_bytes(b"analyzer-truth-groups", 20000)
    payload_path = tmp_path / "payload.bin"
    payload_path.write_bytes(payload)
    emit_volume(spec, payload, 0.35, tmp_path / "emit")
    assert len(emitted) == spec.tiles_per_page

    gt = truth.load_truth(tmp_path / "emit", payload_path,
                          resolve_format_ref(ref), 1, format_ref=ref)
    tiles_y, tiles_x = gt.tiles_yx
    assert len(gt.user_bits) == tiles_y * tiles_x * spec.n_streams
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            users = emitted[spec.tile_counter(0, ty, tx)]
            for stream, user in zip(spec.stream_profiles, users,
                                    strict=True):
                got = gt.user_bits[(0, ty, tx, stream.stream_id)]
                assert got.dtype == np.uint8
                assert got.size == stream.symbol_bits + 1
                assert np.array_equal(got, user), (ty, tx, stream.stream_id)
