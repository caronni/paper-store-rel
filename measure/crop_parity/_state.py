"""Reading a holo1 ``receive.state`` cheaply — certificates and poses.

WHY NOT ``load_session``. A holo1 state is ONE canonical-JSON file
(sorted keys, no whitespace, evidence blocks inlined as base64(zlib)).
``load_session`` decompresses every evidence block — measured ~7x the
file size in RAM, which sheet I's 2.85 GB state does not survive
alongside a decode. We need only two top-level arrays, so we mmap the
file and bracket-scan just those.

THE MARKER IS UNAMBIGUOUS (``extract_holo1_certs.py``'s argument,
reused): neither the base64 alphabet nor a hex string can contain a
quote or a colon, so ``"certificates":[`` / ``"poses":[`` cannot occur
inside a value. The scan is string-aware anyway, and the longest
matching array wins.

MEASURED CROSS-CHECK (2026-08-29, e029 state): against a real
``load_session`` this slice path produces the IDENTICAL certificate
address list, the IDENTICAL pose list (placement outcome, cell origin,
native affine), and — the part ``extract_holo1_certs`` never needed —
IDENTICAL certified user bits. ``--crosscheck`` on the cases entry
re-runs that comparison on demand; it is how this module earns the
right to skip ``load_session`` on the big states.
"""
from __future__ import annotations

import hashlib
import json
import mmap
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_INTERESTING = (0x22, 0x5C, 0x5B, 0x7B, 0x5D, 0x7D)     # " \ [ { ] }
_CHUNK = 1 << 24


def _scan_container(buf: mmap.mmap, start: int) -> tuple[int, int]:
    """(start, end) byte offsets of the JSON container opening at start.

    Vectorised: numpy finds the structurally interesting bytes in each
    16 MiB block and the Python loop visits only those, which is what
    makes a multi-GB state tolerable.
    """
    if buf[start:start + 1] not in (b"[", b"{"):
        raise ValueError("value does not open a JSON container")
    depth = 0
    index = start
    total = len(buf)
    in_string = False
    escape = False
    while index < total:
        block = np.frombuffer(buf[index:index + _CHUNK], dtype=np.uint8)
        marks = np.flatnonzero(np.isin(block, _INTERESTING))
        for offset in marks:
            byte = int(block[offset])
            if in_string:
                if escape:
                    escape = False
                elif byte == 0x5C:
                    escape = True
                elif byte == 0x22:
                    in_string = False
                continue
            if byte == 0x22:
                in_string = True
            elif byte in (0x5B, 0x7B):
                depth += 1
            elif byte in (0x5D, 0x7D):
                depth -= 1
                if depth == 0:
                    return start, index + int(offset) + 1
        index += len(block)
    raise ValueError("unterminated JSON container")


def slice_array(path: Path, key: str) -> list:
    """The longest top-level ``"<key>":[...]`` array in a holo1 state."""
    marker = f'"{key}":['.encode()
    with open(path, "rb") as handle:
        buf = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            best: list | None = None
            at = buf.find(marker)
            while at >= 0:
                lo, hi = _scan_container(buf, at + len(marker) - 1)
                rows = json.loads(bytes(buf[lo:hi]).decode("utf-8"))
                if isinstance(rows, list) and (best is None
                                               or len(rows) > len(best)):
                    best = rows
                at = buf.find(marker, hi)
        finally:
            buf.close()
    if best is None:
        raise ValueError(f"no {key!r} array found in {path}")
    return best


@dataclass(frozen=True)
class StateFacts:
    """What this package needs out of one holo1 state."""

    path: Path
    #: (page, ty, tx, stream) -> certified user bits, uint8 0/1.
    certified_bits: dict[tuple[int, int, int, str], np.ndarray]
    #: The accepted committed poses, one dict each (raw JSON rows).
    poses: tuple[dict, ...]

    @property
    def addresses(self) -> frozenset[tuple[int, int, int, str]]:
        return frozenset(self.certified_bits)


def _bits(hex_text: str, n_bits: int | None) -> np.ndarray:
    raw = np.frombuffer(bytes.fromhex(hex_text), dtype=np.uint8)
    bits = np.unpackbits(raw, bitorder="little")     # v1 packs LSB-first
    return bits if n_bits is None else bits[:n_bits]


def read_state(path: Path, user_bits: int | None = None) -> StateFacts:
    """Certificates (with bits) and accepted poses, by slice-parse."""
    certs = slice_array(path, "certificates")
    poses = slice_array(path, "poses")
    bits: dict[tuple[int, int, int, str], np.ndarray] = {}
    for row in certs:
        key = (int(row["page"]), int(row["tile_yx"][0]),
               int(row["tile_yx"][1]), str(row.get("stream_id", "main")))
        bits[key] = _bits(row["packed_user_bits"], user_bits)
    accepted = tuple(pose for pose in poses
                     if pose.get("placement_outcome") == "accepted")
    return StateFacts(path=path, certified_bits=bits, poses=accepted)


def crosscheck_with_load_session(path: Path, facts: StateFacts,
                                 user_bits: int) -> dict:
    """Re-read the SAME state through holo1's own ``load_session``.

    Only for small states — this is the measurement that licenses the
    slice path, not a per-run gate (``--crosscheck`` on the cases entry).
    """
    from holo.receive.session import load_session          # main tree

    state = load_session(path, defer_fountain_validation=True)
    ref_bits = {}
    for cert in state.certificates:
        key = (int(cert.page), int(cert.tile_yx[0]), int(cert.tile_yx[1]),
               str(cert.stream_id))
        ref_bits[key] = np.unpackbits(
            np.frombuffer(cert.packed_user_bits, np.uint8),
            bitorder="little")[:user_bits]
    # The slice keeps the FULL unpacked byte-multiple bit vector while
    # load_session truncates to the identity's user-bit width, so the
    # comparison truncates too — the trailing pad bits are not a claim
    # either side makes.
    same_addresses = set(ref_bits) == set(facts.certified_bits)
    same_bits = same_addresses and all(
        np.array_equal(ref_bits[key],
                       facts.certified_bits[key][:ref_bits[key].size])
        for key in ref_bits)
    ref_poses = sorted(
        (str(pose.placement_outcome), tuple(pose.cell_origin_yx),
         tuple(round(float(v), 9) for v in pose.native_affine))
        for pose in state.poses if pose.placement_outcome == "accepted")
    mine_poses = sorted(
        (str(pose["placement_outcome"]), tuple(pose["cell_origin_yx"]),
         tuple(round(float(v), 9) for v in pose["native_affine"]))
        for pose in facts.poses)
    return {"state": str(path),
            "load_session_certificates": len(ref_bits),
            "slice_certificates": len(facts.certified_bits),
            "addresses_identical": bool(same_addresses),
            "bits_identical": bool(same_bits),
            "accepted_poses_identical": bool(ref_poses == mine_poses),
            "load_session_accepted_poses": len(ref_poses),
            "slice_accepted_poses": len(mine_poses)}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file_cached(path: Path, cache_dir: Path) -> str:
    """Capture shas are 2.3 GB reads; key the cache on (size, mtime)."""
    stat = path.stat()
    cache_dir.mkdir(parents=True, exist_ok=True)
    token = f"{path.name}-{stat.st_size}-{int(stat.st_mtime)}.sha256"
    cached = cache_dir / token
    if cached.is_file():
        return cached.read_text(encoding="utf-8").strip()
    digest = sha256_file(path)
    cached.write_text(digest + "\n", encoding="utf-8")
    return digest
