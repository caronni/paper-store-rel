"""Content binding and non-overwriting output helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def file_sha256(path: Path, chunk_bytes: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    # ensure_ascii is load-bearing, not a default: evidence artifacts sit
    # beside an ASCII-only PostScript job and must stay pure ASCII.
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ) + "\n"
    ).encode("utf-8")


def write_new_bytes(path: Path, payload: bytes) -> None:
    """Create a new file and refuse to replace existing evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError as exc:
        raise FileExistsError(
            f"refusing to overwrite existing evidence: {path}"
        ) from exc
