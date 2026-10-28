"""The trace: sampled honesty digests, observer-side, off by default.

The trace used to carry the commit ORDERING. It does not any more: the
journal does (F-16), where one line per commit costs 65 bytes and is
fsynced at the commit, instead of 17 MB of keys and wakes nobody read
back. What is left here is the one thing the journal deliberately does
not carry — the **sampled content digest**, the L11 canary that says a
commit's inputs and outputs were what the run claimed — and it is
instrumentation: ``sample_every=0`` (the default) writes no file at all.

Two hard rules, both structural:

- **The store never depends on the trace.** Nothing in this module is
  imported by ``store``; deleting the file loses observability and
  nothing else. (§10.4 rules out event-sourced state — and now that the
  ordering lives in the journal, an event log is not even representable
  here.)
- **No clocks.** Lines carry no wall reading; the commit sequence number
  is the only ordering datum. Headless runs read no clocks (L12).

Sampling: ``N>0`` samples every Nth commit. The engine asks
``should_sample(seq)`` before paying for a digest, so an unsampled commit
costs nothing at all — not even a line.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .codec import canonical_json_bytes, parse_json_bytes

_EVENT_FIELDS = frozenset({"seq", "batch_id", "input_sha256", "output_sha256"})

#: Commits between sampled digests when nobody says otherwise (0 = never
#: sample). One name, for the same reason ``store.DEFAULT_SNAPSHOT_EVERY``
#: has one: the sampling cadence is a ruling to be made in one place, not
#: a literal repeated down every signature that relays it.
DEFAULT_TRACE_SAMPLE_EVERY = 0


class TraceError(ValueError):
    """A malformed trace line. Never fatal to the store — only to a reader."""


@dataclass(frozen=True)
class TraceEvent:
    """One SAMPLED commit: what went in, what came out."""

    seq: int
    batch_id: str
    input_sha256: str
    output_sha256: str

    def to_json(self) -> dict[str, Any]:
        return {"seq": self.seq, "batch_id": self.batch_id,
                "input_sha256": self.input_sha256,
                "output_sha256": self.output_sha256}

    @classmethod
    def from_json(cls, raw: Any) -> "TraceEvent":
        if not isinstance(raw, dict) or set(raw) != _EVENT_FIELDS:
            raise TraceError(f"malformed trace event {raw!r}")
        return cls(seq=raw["seq"], batch_id=raw["batch_id"],
                   input_sha256=raw["input_sha256"],
                   output_sha256=raw["output_sha256"])


class TraceWriter:
    """Append-only JSONL writer. Observer-side; failures never touch state."""

    def __init__(self, path: Path, *,
                 sample_every: int = DEFAULT_TRACE_SAMPLE_EVERY) -> None:
        self._path = path
        self._sample_every = max(0, sample_every)

    @property
    def path(self) -> Path:
        return self._path

    def should_sample(self, seq: int) -> bool:
        """Whether commit ``seq`` pays for content digests."""
        return self._sample_every > 0 and seq % self._sample_every == 0

    def append(self, event: TraceEvent) -> None:
        with open(self._path, "ab") as handle:
            handle.write(canonical_json_bytes(event.to_json()) + b"\n")


class TraceReader:
    """Reads the sampled digests back."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def samples(self) -> tuple[TraceEvent, ...]:
        """Every sampled commit, in file order.

        A final line without its newline is a crash-torn tail and is
        dropped: the trace is disposable, so its tail is not an integrity
        fact.
        """
        if not self._path.is_file():
            return ()
        events: list[TraceEvent] = []
        with open(self._path, "rb") as handle:
            for line in handle:
                if not line.endswith(b"\n"):
                    break
                stripped = line.strip()
                if stripped:
                    events.append(
                        TraceEvent.from_json(parse_json_bytes(stripped)))
        return tuple(events)
