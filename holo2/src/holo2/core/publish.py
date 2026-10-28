"""Publishing bytes to a path, once, durably (S2).

The POSIX durability dance — create a temp EXCLUSIVELY in the target's own
directory, write it, ``fsync`` it, publish the NAME, ``fsync`` the
directory — is a storage primitive, not a CLI concept. It lived in
``cli`` because the recovered payload is written there; it lives here
because ``store``'s envelope replace and ``blobs``'s sidecar append are
the other two hand-written spellings of the same dance, and this is the
package whose job is facts, storage and commit.

The publish is ``os.link``, not ``os.replace``: linking is atomic AND it
refuses an existing target, so "holo2 never overwrites a recovered
payload" is the filesystem's guarantee rather than an ``exists()`` check
with a race behind it. (The store's envelope, in contrast, is *meant* to
be replaced, which is why it uses ``os.replace`` and not this.)

``core`` never decides WHAT is published or where — the composition root
does, and catches the refusal.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def publish_once(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically; never overwrite the object.

    The temp file is created exclusively (``mkstemp``) in the target's own
    directory, so two runs sharing one output path cannot publish each
    other's half-written bytes — the old fixed ``<name>.partial`` was not
    merely predictable but shared. It is fsynced before it is named, and
    the final directory fsync is what POSIX requires for the NAME to
    survive a crash; the bytes alone are not enough.

    Raises ``FileExistsError`` when the target already exists.
    """
    handle_fd, raw_temp = tempfile.mkstemp(dir=path.parent,
                                           prefix=path.name + ".",
                                           suffix=".partial")
    temp = Path(raw_temp)
    try:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            raise FileExistsError(
                f"{path} exists; holo2 never overwrites a recovered payload"
            ) from None
    finally:
        temp.unlink(missing_ok=True)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


__all__ = ["publish_once"]
