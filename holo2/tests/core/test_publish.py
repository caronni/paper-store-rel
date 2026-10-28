"""Publishing an object once, durably (S2).

The durability primitive moved out of ``cli`` and into ``core``, next to
the store's envelope replace and the sidecar's append: it takes a path
and bytes, it knows nothing about arguments, requests or providers, and
the composition root keeps only the decision of WHAT to publish. This is
where the no-overwrite guarantee is pinned; ``tests/test_cli_surface.py``
pins the exit code the CLI turns a refusal into.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from holo2.core.publish import publish_once


def test_publish_writes_the_bytes(tmp_path: Path) -> None:
    target = tmp_path / "recovered.bin"
    publish_once(target, b"payload")
    assert target.read_bytes() == b"payload"


def test_publish_refuses_an_existing_object_and_leaves_it_alone(
        tmp_path: Path) -> None:
    """No-overwrite is ``os.link``'s guarantee, not a checked precondition."""
    target = tmp_path / "recovered.bin"
    publish_once(target, b"payload")
    with pytest.raises(FileExistsError, match="never overwrites"):
        publish_once(target, b"other")
    assert target.read_bytes() == b"payload"


def test_a_refused_publish_leaves_no_half_written_sibling(
        tmp_path: Path) -> None:
    """S2: the temp is exclusively created in the target's own directory."""
    target = tmp_path / "recovered.bin"
    publish_once(target, b"payload")
    with pytest.raises(FileExistsError):
        publish_once(target, b"other")
    assert not list(tmp_path.glob("*.partial"))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["recovered.bin"]
