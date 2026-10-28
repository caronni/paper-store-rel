"""Invocation-local scalar event log for receive diagnostics.

The log is an operational aid, not receiver state and not a recovery ledger.
Each runtime invocation starts at sequence zero and replaces any earlier log
in the selected diagnostic directory.  Rows appended during that invocation
remain useful for troubleshooting without creating receipts, epochs, or a
second crash-consistency protocol.
"""
from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

from ..types import RuntimeEvent
from .filesystem import (
    DirectoryIdentity,
    atomic_write as _atomic_write,
    bind_directory,
    open_child,
)


_SCHEMA = 5
def _json_bytes(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ) + "\n").encode("utf-8")


class JsonlDiagnostics:
    """Write scalar events for the current invocation.

    Construction is deliberately lazy so merely enabling an observer does not
    mutate the filesystem before the runtime emits its first event.  A failure
    is allowed to escape this callable; :class:`~holo.receive.observer.EventSink`
    contains it and disables the observer without affecting receiver work.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        directory_identity: DirectoryIdentity | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.events_path = self.directory / "events.jsonl"
        self._lock = threading.RLock()
        self._directory_identity = directory_identity
        self._next_sequence = 0

    def _bind(self) -> DirectoryIdentity:
        if self._directory_identity is None:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._directory_identity = bind_directory(self.directory)
        return self._directory_identity

    def __call__(self, event: RuntimeEvent) -> None:
        with self._lock:
            self._append(event)

    def _append(self, event: RuntimeEvent) -> None:
        if not isinstance(event, RuntimeEvent):
            raise TypeError("diagnostic observer needs a RuntimeEvent")
        if event.sequence == 0:
            self._next_sequence = 0
        if event.sequence != self._next_sequence:
            raise ValueError("diagnostic runtime sequence is not contiguous")
        row = event.to_dict()
        row["diagnostic_schema"] = _SCHEMA
        data = _json_bytes(row)
        identity = self._bind()
        if event.sequence == 0:
            _atomic_write(
                self.events_path, data, durable=False,
                directory_identity=identity)
        else:
            descriptor = open_child(
                self.events_path,
                os.O_WRONLY | os.O_APPEND | os.O_NONBLOCK,
                directory_identity=identity)
            try:
                opened = os.fstat(descriptor)
                if (not stat.S_ISREG(opened.st_mode)
                        or opened.st_nlink != 1):
                    raise ValueError(
                        "diagnostic event log is not a private regular file")
                with os.fdopen(descriptor, "ab") as stream:
                    descriptor = -1
                    stream.write(data)
                    stream.flush()
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        self._next_sequence += 1


__all__ = ["JsonlDiagnostics"]
