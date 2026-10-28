"""The append-only content-addressed blob sidecar (DESIGN §5.6)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from holo2.core.blobs import BlobError, BlobSidecar, MAGIC
from holo2.core.codec import sha256_hex
from holo2.core.records import BlobRef


def _sidecar(tmp_path: Path) -> BlobSidecar:
    return BlobSidecar.open(tmp_path / "blobs.bin", fsync=False)


def test_put_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    """Counters are gone (W-B/B3); the file itself says nothing was appended."""
    path = tmp_path / "blobs.bin"
    sidecar = _sidecar(tmp_path)
    first = sidecar.put(b"same bytes")
    size_after_first = path.stat().st_size
    second = sidecar.put(b"same bytes")
    assert first == second
    assert sidecar.contains(first.sha256)
    assert path.stat().st_size == size_after_first    # nothing appended twice


def test_arrays_round_trip_with_dtype_and_shape(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    array = np.arange(12, dtype=np.float32).reshape(3, 4)
    ref = sidecar.put_array(array)
    assert ref.shape == (3, 4)
    read_back = sidecar.read_array(ref, verify=True)
    assert np.array_equal(read_back, array)
    assert not read_back.flags.writeable            # durable values are read-only


def test_reads_survive_appends_after_mapping(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    first = sidecar.put_array(np.arange(4, dtype=np.uint8))
    held = sidecar.read_array(first)
    second = sidecar.put_array(np.arange(8, dtype=np.uint8))
    assert np.array_equal(sidecar.read_array(second), np.arange(8, dtype=np.uint8))
    assert np.array_equal(held, np.arange(4, dtype=np.uint8))


def test_payload_offsets_are_eight_byte_aligned(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    refs = [sidecar.put(bytes(range(length))) for length in (1, 7, 8, 9, 33)]
    reopened = BlobSidecar.open(tmp_path / "blobs.bin", fsync=False)
    for ref in refs:
        offset, _length = reopened._index[ref.sha256]   # noqa: SLF001 (layout pin)
        assert offset % 8 == 0


def test_index_rebuilds_by_scanning_on_reopen(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    refs = [sidecar.put(f"payload-{index}".encode()) for index in range(5)]
    sidecar.close()
    reopened = BlobSidecar.open(tmp_path / "blobs.bin", fsync=False)
    for index, ref in enumerate(refs):
        assert reopened.contains(ref.sha256)
        assert bytes(reopened.read(ref, verify=True)) == f"payload-{index}".encode()


def test_torn_tail_is_discarded_and_earlier_blobs_survive(tmp_path: Path) -> None:
    path = tmp_path / "blobs.bin"
    lost = b"payload lost to a crash mid-append"
    sidecar = BlobSidecar.open(path, fsync=False)
    keeper = sidecar.put(b"committed payload")
    good_size = path.stat().st_size
    sidecar.put(lost)
    sidecar.close()
    with open(path, "r+b") as handle:               # crash mid-append
        handle.truncate(good_size + 24)
    reopened = BlobSidecar.open(path, fsync=False)
    assert not reopened.contains(sha256_hex(lost))
    assert bytes(reopened.read(keeper, verify=True)) == b"committed payload"
    assert path.stat().st_size == good_size         # tail truncated at open
    fresh = reopened.put(b"work that re-armed")
    assert bytes(reopened.read(fresh)) == b"work that re-armed"


def test_missing_blob_refuses_and_says_the_state_is_incomplete(
        tmp_path: Path) -> None:
    """F-13 residue: an absent address is an honest, actionable refusal.

    It names the address and states the cache doctrine's verdict —
    nothing was damaged, a derivable value is simply absent, so the
    remedy is re-derivation and never repair.
    """
    sidecar = _sidecar(tmp_path)
    with pytest.raises(BlobError) as caught:
        sidecar.read(BlobRef("ab" * 32, 4))
    message = str(caught.value)
    assert "ab" * 32 in message
    assert "INCOMPLETE, not corrupt" in message
    assert "decode again from the scans" in message


def test_wrong_length_in_ref_refuses(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    ref = sidecar.put(b"four")
    with pytest.raises(BlobError, match="bytes"):
        sidecar.read(BlobRef(ref.sha256, 99))


def test_opaque_blob_is_not_an_array(tmp_path: Path) -> None:
    sidecar = _sidecar(tmp_path)
    ref = sidecar.put(b"opaque")
    with pytest.raises(BlobError, match="opaque"):
        sidecar.read_array(ref)


def test_foreign_file_refused(tmp_path: Path) -> None:
    path = tmp_path / "blobs.bin"
    path.write_bytes(b"NOTHOLO2" + MAGIC)
    with pytest.raises(BlobError, match="not a holo2 blob sidecar"):
        BlobSidecar.open(path, fsync=False)
