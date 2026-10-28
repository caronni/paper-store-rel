"""Diag: the observer surface (DESIGN §10.3, L12).

Strictly downstream, strictly disposable, strictly state-inert. Nothing
here can touch receiver state: the provider only *reads* what the run
published to it and the durable store, the HTTP endpoint only serves the
resulting bytes, and every failure on this side is swallowed rather than
raised into the receiver.

Three pieces:

* :class:`StatusProvider` — the run's own published instants, served as
  JSON. Status-first by construction (the v1 measured lesson: status
  publish 0.3-0.5 ms vs 61-118 ms rendered frames).
* :class:`FrameCache` — the pane frames of :mod:`holo2.diag.panes`, composed
  **on demand** and cached per ``(page, capture, revision)``. A revision
  is the store's commit sequence: a frame is recomposed exactly when the
  receiver has committed something, so the throttle is work-counted and
  the status channel never waits behind a render.
* :func:`serve` — a daemon-thread endpoint on the request's
  ``--diag-port``, always started; a port that will not bind returns
  ``None`` and the run proceeds. Routes: ``/`` the browser shell,
  ``/status`` the JSON surface, ``/frame/<page>.png`` a composed frame.

**PUSH, not pull.** The orchestrator mints one frozen ``RunSnapshot`` on
the MAIN thread — at a commit boundary, and only when a viewer has asked
for one — and pushes it here; this side only ever formats a value it was
handed. The pull it replaces ran the whole derivation on the HTTP thread,
over the scheduler's live dicts and through the plane's committer-owned
caches, which is a race the observer had no business taking. The
counting goes the same way: the run hands over ONE commit ledger and
every commit in the session is counted there, ingest's included, so the
stream's totals and the run's own subset can no longer disagree.

**How the observer finds the run.** No receiver module knows the pane
server exists: the composition root calls :meth:`StatusProvider.bind_plane`
with the session's derived plane. If nothing is bound, panes A and B say
so and the rest of the surface is unaffected.

**No clocks anywhere, even here.** The trace, the counters and the frame
revision are ordered by commit sequence, never by wall time, and the HTTP
responses are emitted with ``send_response_only`` precisely so the stdlib
does not stamp a ``Date`` header — a headless run and an observed run read
the same number of clocks: zero. Wall time is what an attached observer
*adds*, and H3 measures it from outside.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..core import CommitResult, canonical_json_bytes
from ..engine import RunOutcome
from . import panes as _panes


class FrameCache:
    """Composed pane frames, keyed by ``(page, capture, revision)``.

    On demand and never eager: a frame is composed when a viewer asks for
    it and the store has moved since the last composition of that view.
    The revision is ``store.commit_seq``, so the cache key is the
    receiver's own work counter — no clock, and no frame is ever
    recomposed for a session that did nothing.
    """

    def __init__(self, source) -> None:
        self._source = source
        self._lock = threading.Lock()
        self._revision = -1
        self._frames: dict[tuple[int, str | None], bytes] = {}
        self._pinned = False
        self.compositions = 0

    @property
    def source(self):
        """The bound pane source, for callers that want the model itself."""
        return self._source

    @property
    def pinned(self) -> bool:
        return self._pinned

    def catalog(self) -> dict:
        return self._source.catalog()

    def frame(self, page: int, capture: str | None,
              snapshot: dict | None) -> bytes | None:
        """The PNG for one view, composed at most once per revision."""
        key = (int(page), capture)
        with self._lock:
            if self._pinned:
                # After the terminal publish the frames ARE the answer: the
                # session behind them is closed, and a viewer polling in the
                # moment before the endpoint stops must get the done frame,
                # not a recomposition against a shut store.
                return (self._frames.get(key)
                        or self._frames.get((int(page), None)))
            revision = self._source.revision
            if revision != self._revision:
                self._frames.clear()
                self._revision = revision
            cached = self._frames.get(key)
        if cached is not None:
            return cached
        png = self._compose(page, capture, snapshot)
        with self._lock:
            if revision == self._revision and not self._pinned:
                self._frames[key] = png
            self.compositions += 1
        return png

    def _compose(self, page: int, capture: str | None,
                 snapshot: dict | None) -> bytes:
        model = self._source.build(page, capture, snapshot)
        return _panes.render_frame(model, self._source)

    def finalize(self, snapshot: dict | None
                 ) -> tuple[dict[int, bytes], tuple[str, ...]]:
        """Compose the terminal frame of every posed page and PIN it.

        The v1 termination pattern (``LiveView.finalize``): every retained
        page re-renders and composes once, so whichever page a browser is
        watching can still acknowledge the done frame. Pinning is holo2's
        half of it — frames outlive the session that produced them, which
        is what lets the endpoint answer between the last commit and its
        own shutdown.

        Returns the frames AND the per-page failures: one call, one
        answer, so a caller cannot read the failures of a different run.
        """
        frames: dict[int, bytes] = {}
        failures: list[str] = []
        for page in self._source.posed_pages():
            try:
                frames[int(page)] = self._compose(page, None, snapshot)
                self.compositions += 1
            except Exception as exc:        # one bad page is not all pages
                failures.append(f"frame p{page}: {type(exc).__name__}: {exc}")
        with self._lock:
            self._frames = {(page, None): png for page, png in frames.items()}
            self._pinned = True
        return frames, tuple(failures)


class StatusProvider:
    """Observer-side status: the run's published instants, served as JSON.

    Holds no counter and derives no receiver fact. The run hands it (a) a
    commit ledger, which is the one owner of every commit count in the
    session, and (b) a frozen snapshot per commit a viewer asked for. The
    only work left here is formatting, which happens on the reader's own
    thread — the main thread pays for the derivation, never for the JSON.
    """

    def __init__(self) -> None:
        self._ledger = None                 # the run's, adopted at its start
        self._parked: list[CommitResult] = []
        self._latest = None                 # the last published RunSnapshot
        self._error: str | None = None
        self._wanted = False
        self._frames: FrameCache | None = None
        self._final: dict | None = None
        self._lock = threading.Lock()

    # -- feeds -------------------------------------------------------------

    def note_commit(self, result: CommitResult) -> None:
        """Ingest's feed: the commits that land before a run exists.

        Parked, not counted: capture ingest commits inside the session
        assembly, before the orchestrator that owns the ledger has been
        built, and a second tally here is exactly the drift this design
        removed. :meth:`adopt_ledger` replays what is parked, so the
        totals are whole from the first published instant.
        """
        with self._lock:
            if self._ledger is None:
                self._parked.append(result)
                return
            ledger = self._ledger
        ledger.note(result, scheduled=False)

    def adopt_ledger(self, ledger) -> None:
        """Take the run's commit ledger — the ONE owner of these counts."""
        with self._lock:
            parked, self._parked = self._parked, []
            self._ledger = ledger
        for result in parked:
            ledger.note(result, scheduled=False)

    def publish(self, snapshot=None, *, error: str | None = None) -> None:
        """Accept one frozen instant (or the reason there is not one)."""
        with self._lock:
            self._wanted = False
            if snapshot is not None:
                self._latest = snapshot
            self._error = error

    def wants_snapshot(self) -> bool:
        """Has anyone asked to see the run since the last instant landed?

        The run reads this at a commit boundary, so an unwatched decode
        derives nothing at all and a watched one derives once per poll.
        """
        return self._wanted

    def bind_plane(self, ctx: object) -> bool:
        """Bind a derived plane read-only for the panes. Never raises."""
        try:
            self._frames = FrameCache(_panes.PaneSource(ctx))
        except Exception:                   # observer binding is optional
            self._frames = None
        return self._frames is not None

    # -- reads -------------------------------------------------------------

    @property
    def frames(self) -> FrameCache | None:
        return self._frames

    def status(self) -> dict:
        """The whole observer story, as plain JSON-able data.

        Deliberately cheap (v1's status-first doctrine): the last
        published instant rendered to JSON, plus the pane *catalog*,
        which is attribute reads over the frozen session assembly.
        Nothing here builds an index, touches a blob, composes a frame,
        or calls back into the receiver.

        Asking is also how a viewer *requests* the next instant: the run
        mints one at its next commit. So a status is the run as of the
        last commit — declared staleness in place of a race.

        After :meth:`finalize` this returns the FROZEN terminal status —
        the run is over, so there is nothing further to report, and a
        viewer polling between the last commit and the endpoint's
        shutdown must see the done state, not a re-derivation against a
        closed session.
        """
        with self._lock:
            if self._final is not None:
                return self._final
            self._wanted = True
            latest, error, parked = self._latest, self._error, self._parked
        status: dict = {"provisional": True}
        if latest is not None:
            status.update(latest.to_json())
        else:
            # No run has adopted these yet: report what is held, and say
            # nothing about a session that has not published one.
            status["commit_stream"] = {"commits": len(parked)}
        if error is not None:
            status["session_error"] = error
        if self._frames is not None:
            try:
                status["panes"] = self._frames.catalog()
            except Exception as exc:            # observer failure is inert
                status["panes_error"] = f"{type(exc).__name__}: {exc}"
        try:
            status["rows"] = status_rows(status)
        except Exception as exc:                # observer failure is inert
            status["rows"] = [f"rows unavailable: {type(exc).__name__}: {exc}"]
        return status

    def finalize_publish(self) -> tuple[dict, dict[int, bytes], tuple[str, ...]]:
        """The terminal publish: freeze the status, compose the last frames.

        Idempotent and inert. Called once at run termination, BEFORE the
        endpoint stops, so a browser polling in that moment retains the
        done pane rather than a stale one (v1's ``diag.finalize`` effect;
        v1 had no linger and no grace period, and neither does this).
        """
        status = self.status()
        frames: dict[int, bytes] = {}
        failures: list[str] = []
        cache = self._frames
        if cache is not None:
            try:
                frames, frame_failures = cache.finalize(status.get("session"))
                failures.extend(frame_failures)
            except Exception as exc:            # observer failure is inert
                failures.append(f"frames: {type(exc).__name__}: {exc}")
        with self._lock:
            if self._final is None:
                self._final = status
        return status, frames, tuple(failures)


def _compose(by_family: dict | None) -> str:
    if not by_family:
        return ""
    inner = ",".join(f"{name}:{count}" for name, count in sorted(
        by_family.items()))
    return f"[{inner}]"


def status_rows(status: dict) -> list[str]:
    """The fixed six-row operator block (v1 RECEIVE-DESIGN §10.3.2 shape).

    Two of v1's rules are carried and are easy to break by accident:
    never print zero where the fact is *unavailable* (an unbound session
    says so), and keep the block exactly six rows of fixed shape, so a
    value becoming known must not move a pane.
    """
    stream = status.get("commit_stream") or {}
    session = status.get("session") or {}
    catalog = status.get("panes") or {}
    ready = session.get("ready") or {}
    workers = session.get("workers") or {}
    counters = session.get("counters") or {}
    tiles = session.get("tiles") or {}
    close = session.get("close") or {}
    coverage = session.get("done_coverage") or {}

    if catalog:
        pages = catalog.get("pages") or []
        fmt = (f"format   {catalog.get('row_id', '-')}"
               f" · codec {catalog.get('codec_id', '-')}"
               f" · {len(pages)} page domain"
               f" · streams {','.join(catalog.get('streams') or ['-'])}"
               f" · PROVISIONAL")
        captures = catalog.get("captures") or []
    else:
        fmt = "format   unavailable — no session bound to the observer"
        captures = []

    done = supported = 0
    for regions in coverage.values():
        for region in regions.values():
            done += int(region.get("done_cells", 0))
            supported += int(region.get("supported_cells", 0))
    footprint = (f"{done / supported:.1%} ({done}/{supported} cells)"
                 if supported else "unavailable before survey")
    capture_row = (f"capture  {len(captures)} ingested"
                   + (f" · {captures[0]}…" if captures else "")
                   + f" · done coverage {footprint}")

    if session:
        queue = (f"queue    ready {ready.get('depth', 0)}"
                 f"{_compose(ready.get('by_family'))}"
                 f" · running {len(workers.get('running') or ())}"
                 f" · sleeping {workers.get('sleeping', 0)}"
                 f" · retired {workers.get('retired', 0)}"
                 f" · declined {workers.get('declined', 0)}"
                 f" (re-offerable {workers.get('declined_pending', 0)})"
                 f" · pool {session.get('pool_size', 1)}"
                 f"/{session.get('mode', 'free')}")
    else:
        queue = "queue    unavailable — no orchestrator snapshot is bound"

    # Two numbers, two names, ONE owner: the stream counts every commit of
    # the session (ingest's included), the parenthetical is the run's own
    # subset, and the wake ratio is taken from the same tally as the count
    # it divides. The row used to print one owner's numerator over the
    # other's denominator, which is how 471 and 472 both meant "commits".
    fires = (f"work     commits {stream.get('commits', 0)}"
             f" (scheduled {counters.get('commits', 0)})"
             f" · fires {counters.get('fires', 0)}"
             f" · wakes/commit {float(stream.get('wakes_per_commit', 0.0)):.2f}"
             f" · useful {float(counters.get('useful_rerun_ratio', 0.0)):.2f}"
             f" · peak {counters.get('peak_inflight', 0)}"
             f" · stale {counters.get('stale_discards', 0)}")

    if tiles:
        # The CRC exposure rides the certificate row because it is what a
        # certificate COSTS in L5's budget: one CRC-bearing attempt, one
        # spend, so the number is counted and never estimated.
        exposure = session.get("crc_exposure") or {}
        tile_row = ("tiles    " + " · ".join(
            f"{name} {tiles.get(name, 0)}"
            for name in ("UNKNOWN", "ADDRESSED", "ATTEMPTED", "CERTIFIED"))
            + (f" · crc exposure {exposure['spends']} spends"
               f"/{exposure['attempts']} attempts" if exposure else ""))
    else:
        tile_row = "tiles    unavailable — the tile map has not been read"

    if close:
        blocks = close.get("blocks") or []
        solved = sum(1 for row in blocks if row.get("solved"))
        close_row = (f"close    {close.get('status', 'not_consulted')}"
                     f" · certified {close.get('certified', 0)}"
                     f" · K {close.get('symbols_used', '-')}"
                     f"/{close.get('k_total', '-')}"
                     f" · metadata rank {close.get('metadata_rank', '-')}/24"
                     + (f" · blocks {solved}/{len(blocks)}" if blocks else ""))
    else:
        close_row = "close    not consulted"
    return [fmt, capture_row, queue, fires, tile_row, close_row]


_LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


class _Handler(BaseHTTPRequestHandler):
    """The pane endpoint. No Date header, no logging — hence no clocks."""

    provider: StatusProvider = None            # type: ignore[assignment]
    protocol_version = "HTTP/1.0"

    def do_GET(self) -> None:                  # noqa: N802 (stdlib name)
        if not self._host_allowed():
            # Loopback-only, and the exact loopback Host: a foreign Host
            # header (DNS rebinding) is refused, as in v1's §10.7.
            self._respond(403, b"forbidden host", "text/plain")
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._respond(200, _panes.PAGE_BYTES, "text/html; charset=utf-8")
            return
        if path == "/status":
            self._respond(200, self._status_bytes())
            return
        if path.startswith("/frame/") and path.endswith(".png"):
            self._frame(path[len("/frame/"):-len(".png")], parsed.query)
            return
        self._respond(404, canonical_json_bytes({"error": "not found"}))

    # -- routes ------------------------------------------------------------

    def _status_bytes(self) -> bytes:
        try:
            return canonical_json_bytes(self.provider.status())
        except Exception as exc:               # never raise into the server
            return canonical_json_bytes(
                {"error": f"{type(exc).__name__}: {exc}"})

    def _frame(self, raw_page: str, query: str) -> None:
        frames = self.provider.frames
        if frames is None:
            self._respond(404, b"no session bound to the observer",
                          "text/plain")
            return
        try:
            page = int(raw_page)
        except ValueError:
            self._respond(404, b"frame path names no page", "text/plain")
            return
        capture = (parse_qs(query).get("capture") or [None])[0]
        try:
            # A frame is a *view* of the run, so it carries the same
            # orchestrator snapshot the status channel published.
            snapshot = self.provider.status().get("session")
            png = frames.frame(page, capture, snapshot)
        except Exception as exc:               # a failed frame is a 500 —
            message = f"frame failed: {type(exc).__name__}: {exc}"
            self._respond(500, message.encode("utf-8"), "text/plain")
            return                             # never a run difference
        if png is None:
            self._respond(404, b"no frame", "text/plain")
            return
        self._respond(200, png, "image/png")

    # -- plumbing ----------------------------------------------------------

    def _host_allowed(self) -> bool:
        header = (self.headers.get("Host") or "").strip()
        if not header:                         # HTTP/1.0 clients may omit it
            return True
        bound_host, bound_port = (self.server.server_address[0],
                                  self.server.server_address[1])
        allowed = {f"{name}:{bound_port}" for name in _LOOPBACK}
        allowed.add(f"{bound_host}:{bound_port}")
        allowed.update(_LOOPBACK)
        allowed.add(bound_host)
        return header in allowed

    def _respond(self, code: int, body: bytes,
                 content_type: str = "application/json") -> None:
        self.send_response_only(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass                               # a viewer that walked away

    def log_message(self, *args: object) -> None:
        """Silence the stdlib logger — it stamps a wall-clock timestamp."""


class DiagServer:
    """A daemon-thread status endpoint whose failure cannot reach state."""

    def __init__(self, server: ThreadingHTTPServer,
                 thread: threading.Thread) -> None:
        self._server = server
        self._thread = thread

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/status"

    @property
    def home(self) -> str:
        """Where an operator points a browser to watch the decode."""
        return f"http://127.0.0.1:{self.port}/"

    def frame_url(self, page: int = 0) -> str:
        return f"http://127.0.0.1:{self.port}/frame/{int(page)}.png"

    def stop(self) -> None:
        try:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=5.0)
        except Exception:                       # observer teardown is inert
            pass


@dataclass(frozen=True)
class Finalized:
    """What the terminal publish left behind. Never an error, ever."""

    directory: Path | None = None
    written: tuple[Path, ...] = ()
    frames: tuple[int, ...] = ()
    failures: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures

    def notice(self) -> str:
        """One line an operator can read. Never mentions the run's fate."""
        if self.failures:
            return ("diag finalize incomplete (" + self.failures[0]
                    + (f"; +{len(self.failures) - 1} more"
                       if len(self.failures) > 1 else "")
                    + "); the run is unaffected.")
        return (f"diag artifacts in {self.directory} "
                f"({len(self.written)} file(s))")


def finalize(provider: StatusProvider, state_dir, *,
             outcome: RunOutcome | None = None) -> Finalized:
    """Terminal publish: freeze the live view, then write the sibling dir.

    Order is the whole point (the v1 pattern): the live endpoint is
    updated FIRST — status frozen, final frames composed and pinned — and
    only then are the current files replaced in ``<state-dir>.diag/``.
    The caller stops the server afterwards, so a browser polling during
    the teardown gets the done frame instead of a connection refusal
    against a half-finished one.

    L12 in full: this cannot raise, cannot change an outcome, and cannot
    change an exit code. Every failure comes back as text.
    """
    failures: list[str] = []
    try:
        status, frames, publish_failures = provider.finalize_publish()
        failures.extend(publish_failures)
    except Exception as exc:                    # observer failure is inert
        return Finalized(failures=(f"publish: {type(exc).__name__}: {exc}",))
    try:
        directory = _panes.diag_directory(Path(state_dir))
        report = _panes.build_report(status, outcome, tuple(failures))
        written, write_failures = _panes.write_artifacts(
            directory, status=status, frames=frames, report=report)
    except Exception as exc:                    # observer failure is inert
        return Finalized(frames=tuple(sorted(frames)),
                         failures=tuple(failures)
                         + (f"write: {type(exc).__name__}: {exc}",))
    return Finalized(directory=directory, written=written,
                     frames=tuple(sorted(frames)),
                     failures=tuple(failures) + tuple(write_failures))


def serve(port: int, provider: StatusProvider) -> DiagServer | None:
    """Start the pane endpoint on loopback, or None if it cannot start."""
    try:
        handler = type("_BoundHandler", (_Handler,), {"provider": provider})
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever,
                                  name="holo2-diag", daemon=True)
        thread.start()
        return DiagServer(server, thread)
    except Exception:                           # a busy port is not an error
        return None


__all__ = ["DiagServer", "Finalized", "FrameCache",
           "StatusProvider", "finalize", "serve", "status_rows"]
