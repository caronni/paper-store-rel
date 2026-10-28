"""Live view for ``holo decode --diag`` (e023c-style transport).

One :class:`LiveView` instance accompanies one receive session.  It consumes
the runtime's scalar events plus a handful of pass-through snapshots of live
stage products (:mod:`holo.receive._diagnostic_snapshots`), folds them into
small accumulators immediately — no typed mirror, no retained numerical
objects — and drives the operator presentation.

This module owns the event dispatch, the page-space accumulators (panes B,
C and D), and the render orchestration.  The rest lives next door so each
side stays readable alone: :mod:`.scan_model` (pane A — the capture/lane
SCAN-space geometry, the one part of the view that has a coordinate frame
to get wrong), :mod:`.presentation` (palette, browser shell, glyphs, and
the ``PaneRenderer`` that turns model into pixels), :mod:`.rows` (the
six-row status text), and :mod:`.transport` (current files on disk plus
the loopback server).

The presentation is:

- a fixed six-row stats block (format / lane / scraps / address / LDPC /
  fountain), published as text inside ``status.json``;
- ONE composed frame per page (§10.3.1): four equal A4-portrait panes in one
  horizontal row — A scan-space survey regions, B page-space placements,
  C BCH word sites per tile, D payload/LDPC tiles — under fixed headings.

Pane bodies are cached rasters, so a frame is a paste plus four headings and
a page whose panes did not change is never re-encoded.  Transport is the
measured e023c pattern: the browser polls the small ``status.json`` once a
second, refetches ``frame.png`` only when that page's own revision moves, and
scales it to the window.  The current files are atomically replaced in the
diagnostic directory each render tick, so a headless run stays watchable
without the optional loopback HTTP server (``--diag-port``).

Everything here is observer-only: a failure disables the view, never the
receiver.  The caller (:class:`holo.receive.diag.ReceiveDiagnostics`) owns
that isolation.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Callable

import numpy as np

from ...format.profiles import Family
from ..types import RefineAddressPlan, RuntimeEvent
from .field_view import FieldPaneState
from .presentation import (
    _HUES, _PAGE, _TILE_STATE_CERTIFIED, _TILE_STATE_EVIDENCE,
    _TILE_STATE_FAILED, _TILE_STATE_FLOOR, _WORD_CONFLICT,
    _WORD_ERASURE_BUDGET, _WORD_EVIDENCE, _WORD_FAILED, _WORD_FLOOR,
    _WORD_SOLVED, _WORD_VALIDATED, PaneRenderer)
from .rows import close_row, status_rows
from .scan_model import ScanFrame, ScanModel
from .seed import seed_scan_models, seed_words
from .transport import CurrentFiles, serve


# Events whose pass-through snapshot the view consumes.
SNAPSHOT_EVENTS = frozenset((
    "survey.complete", "address.window_progress", "address.region_complete",
    "address.final", "session.open", "barrier.committed", "close.check",
    "session.complete", "payload.owner_frozen", "payload.retry_open",
    "payload.plane_fields",   # W5: the field-band illustration snapshot.
))

# Semantic milestones always render, regardless of the wall-clock throttle.
_MILESTONES = frozenset((
    "session.open", "capture.open", "capture.duplicate", "capture.active",
    "capture.complete", "survey.complete", "address.final", "stage.refused",
    "stage.failed", "run.failed", "barrier.committed", "close.check",
    "session.complete", "payload.owner_frozen", "payload.retry_open",
    "payload.retry_complete", "payload.plane_fields",
))

# Scalar status is unthrottled semantically (§10.6); this only paces the
# physical status.json rewrite against the browser's 1 Hz poll.
_STATUS_INTERVAL_S = 0.5


class LiveView:
    """Accumulate runtime events into the four-pane operator view."""

    SNAPSHOT_EVENTS = SNAPSHOT_EVENTS

    def __init__(
        self,
        directory: str | Path,
        spec: object,
        *,
        page_domain: tuple[int, ...] = (),
        panel_width: int = 600,
        interval_s: float = 3.0,
        port: int | None = None,
        on_server: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        layout = spec.layout  # a real FormatSpec is required for geometry
        self._spec = spec
        self._spec_id = str(spec.spec_id)
        self._cells_yx = tuple(int(v) for v in layout.cells_yx)
        self._tiles_yx = tuple(int(v) for v in layout.tiles_yx)
        self._streams = (
            ("C", "M", "Y") if spec.codec_family is Family.CMY8
            else ("main",))
        self._page_domain = tuple(int(p) for p in page_domain)
        # §10.3.2 mapped footprint: registered PAYLOAD cells only, so the
        # per-family furniture (word sites, and colour dust where the row
        # declares it) is excluded from both numerator and denominator.
        try:
            from .. import tiles as _tiles
            furniture = int(_tiles._geometry(spec).site_mask_yx.sum())
        except Exception:  # pragma: no cover - opaque diagnostic fixtures
            furniture = 0
        self._payload_cells_per_tile = max(
            0, 64 * 64 - furniture)
        self._payload_cells_per_page = (
            self._tiles_yx[0] * self._tiles_yx[1]
            * self._payload_cells_per_tile)
        self._furniture_flat = None
        if furniture:
            self._furniture_flat = np.flatnonzero(
                np.asarray(_tiles._geometry(spec).site_mask_yx, bool).ravel())
        self._directory = Path(directory)
        self._files = CurrentFiles(directory)
        self._clock = clock
        self._interval = float(interval_s)
        self._panes = PaneRenderer(
            self._cells_yx, self._tiles_yx, panel_width)
        self._width = self._panes.width
        self._height = self._panes.height
        self._last_render: float | None = None
        # Pane A (ACQUIRED) is its own capture/lane geometry model.
        self._scan = ScanModel(self._panes)

        # --- model (runtime-thread only) -------------------------------
        self._context: object | None = None
        self._phase = "waiting"
        # v0.33 session-phase driver (D14a): the lane row's phase tail
        # carries the rung/tail announcement beside the stage phase.
        self._session_phase: str | None = None
        # (ppc string, captures total) while a rung phase is active.
        self._phase_rung: tuple[str, int] | None = None
        self._phase_capture_k = 0
        self._policy_id = ""
        self._qualification = ""
        self._capture_sha: str | None = None
        self._captures_seen = 0
        self._captures_requested = 0
        self._captures_retained = 0
        self._prov_rects: list[tuple[int, int, int, int, int]] = []
        # page -> uint16 hue-id-plus-one at pane resolution
        self._placed: dict[int, np.ndarray] = {}
        # page -> bool cell coverage (exact payload-area union)
        self._covered: dict[int, np.ndarray] = {}
        # page -> reached REGISTERED PAYLOAD cells, maintained incrementally
        self._covered_payload: dict[int, int] = {}
        self._painted_patches: set[tuple[str, str, int]] = set()
        # (page, ty, tx) -> observed-site bitmask / word display state
        self._sites: dict[tuple[int, int, int], int] = {}
        self._word_state: dict[tuple[int, int, int], int] = {}
        # page -> uint8 (streams, ty, tx) payload tile states
        self._tiles: dict[int, np.ndarray] = {}
        self._lane_address: dict[tuple[str, str], tuple[int, int, int]] = {}
        self._windows_attempted = 0
        self._windows_accepted = 0
        self._scan.parked_chips: dict[
            tuple[str, str, int, int],
            tuple[tuple[int, int, int, int], str | None]] = {}
        # (page, ty, tx, stream) scheduled for retry150, not yet resolved
        self._retry_pending: set[tuple[int, int, int, str]] = set()
        self._last_status: float | None = None
        self._counters: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._divergences = 0
        self._mopup_dropped = 0
        self._mopup_flips = 0
        self._certs_committed = 0
        self._trans_calls = 0
        self._trans_certs = 0
        self._trans_bp150 = 0
        self._close_row = "close pending"
        self._done = False
        self._field = FieldPaneState()   # W5 band/row state; field_view.py

        # --- pane rasters (runtime-thread only) -------------------------
        # (pane, page) -> uint8 (h, w, 3); pane A uses page -1.  Cached as
        # rasters, not PNGs: the published frame composes them, so a pane
        # that did not change is never re-rendered AND never re-encoded.
        # Cost is ~3 * panel_width^2 * (cy/cx) bytes per REACHED page (6 MB
        # at the 600 default for the single-page runs, ~1.5 MB per further
        # page); the dict is pruned to live pages on every render.
        self._raster: dict[tuple[str, int], np.ndarray] = {}
        self._scan_revision = 0
        self._page_revision: dict[int, int] = {}
        # (scan rev, page rev, field rev): each page owns its own band
        # raster, and the shared field revision rides every page's
        # composed-frame cache key so a new snapshot recomposes them all.
        self._composed: dict[int, tuple[int, int, int]] = {}

        # --- published transport state (lock-guarded) ------------------
        self._lock = threading.Lock()
        self._frame = 0
        # §10.3.1: each page carries its own monotone presentation revision,
        # so a page not re-composed this tick keeps its own bytes+revision
        # pair instead of being served under a newer global number.
        self._page_frame: dict[int, int] = {}
        self._dirty_pages: set[int] = set()
        self._png: dict[int, bytes] = {}
        # The page the browser last asked for; composed alongside the default
        # so selecting a page keeps it live without composing every page.
        self._wanted_page: int | None = None
        self._status_bytes = b'{"frame":0,"pages":[],"page_default":0,"rows":[]}'
        self._served_frame = 0
        self._ever_served = False
        self._httpd: ThreadingHTTPServer | None = None
        self.server_error: str | None = None
        if port is not None:
            # A refused loopback bind degrades to the headless file view.
            try:
                self._httpd = serve(
                    self, int(port), self._shell())
            except OSError as exc:
                self.server_error = (
                    f"live-view server unavailable: {exc}")
            else:
                url = f"http://localhost:{self._httpd.server_address[1]}/"
                if on_server is not None:
                    on_server(url)

    @property
    def serving(self) -> bool:
        return self._httpd is not None

    # ------------------------------------------------------------------
    # event ingestion
    # ------------------------------------------------------------------
    def feed(self, event: RuntimeEvent) -> None:
        name = event.name
        details = {row.name: row.value for row in event.details}
        self._context = event.context
        self._scan.context = event.context
        snapshot = event.snapshot if isinstance(event.snapshot, dict) else None
        # Pane A is capture/lane geometry: every survey, address and capture
        # event may move it, and nothing else can.  Payload-stage frames
        # therefore reuse its raster instead of redrawing the underlay.
        # The v0.33 cold heartbeat moves only the phase text (§10.6), so it
        # deliberately does not dirty the pane-A raster.
        if (name.startswith(("survey.", "address.", "capture."))
                and name != "address.cold_progress"):
            self._scan.dirty = True
        if name == "session.open":
            self._policy_id = event.context.receiver_policy_id or ""
            self._qualification = event.context.qualification_status or ""
            self._captures_requested = int(
                details.get("captures.requested", 0) or 0)
            self._captures_retained = int(
                details.get("captures.retained", 0) or 0)
            self._phase = "session open"
            if snapshot is not None and snapshot.get("kind") == "committed":
                self._ingest_state(snapshot["state"])
                self._seed_committed(snapshot["state"])
        elif name == "capture.open":
            self._scan.stash_capture(self._capture_sha)
            self._captures_seen += 1
            self._capture_sha = event.capture_id
            self._scan.apply(ScanFrame.blank())
            # v0.45: a re-opened capture with committed history starts from
            # its durable-record model instead of the blank reset; the next
            # ordinary lane's live survey replaces it exactly like any
            # prior model.
            self._scan.restore(event.capture_id)
            self._phase = "ingest"
        elif name == "capture.resume":
            # v0.33 mid-phase capture switch: pane A follows the resumed
            # raster by swapping to that capture's retained model — no
            # captures-seen increment, no capture.open-style wholesale
            # clearing (§10.5).
            if event.capture_id != self._capture_sha:
                self._scan.stash_capture(self._capture_sha)
                self._scan.restore(event.capture_id)
                self._capture_sha = event.capture_id
            if self._phase_rung is not None:
                total = self._phase_rung[1]
                self._phase_capture_k += 1
                if total:
                    self._phase_capture_k = min(
                        self._phase_capture_k, total)
                self._session_phase = self._rung_phrase()
        elif name == "session.phase":
            kind = str(details.get("phase.kind", "") or "")
            if kind == "rung":
                ppc = str(details.get("phase.ppc", "?") or "?")
                total = int(details.get("phase.captures", 0) or 0)
                self._phase_rung = (ppc, total)
                # k counts RESUMED slots of this rung.  The scheduler
                # resumes every slot, including the rung's first (measured
                # 2026-08-02), so the announcement starts at zero and the
                # phrase floors at 1 — starting at 1 displayed capture
                # j's whole slot as "capture j+1/N".
                self._phase_capture_k = 0
                self._session_phase = self._rung_phrase()
            elif kind == "tail":
                parked = int(details.get("phase.parked", 0) or 0)
                self._phase_rung = None
                self._session_phase = f"mop-up tail · {parked} parked"
        elif name in ("capture.duplicate", "capture.complete",
                      "capture.active"):
            self._phase = ("capture duplicate" if name == "capture.duplicate"
                          else name.replace(".", " "))
            self._scan.active_window = None
            self._prov_rects.clear()
        elif name == "stage.open":
            self._phase = event.stage.value
        elif name in ("stage.refused", "stage.failed"):
            self._phase = f"{event.stage.value} {name.split('.')[1]}"
        elif name == "run.failed":
            self._phase = "run FAILED"
        elif name == "survey.complete":
            # v0.33: an M-level is an ordinary lane to the observer; its
            # survey carries the base lane id (and zero regions), which is
            # how terminal M-level outcomes retire the base lane's chips.
            mopup_of = details.get("survey.mopup_of")
            self._scan.mopup_base = mopup_of if isinstance(mopup_of, str) else None
            # Same sibling detail for R-levels: both name the lane whose
            # REGION ORDINALS this level's address indices address.
            # PK4.3: a supplemental level says the same thing through
            # ``survey.uplift_of``, and adds the arm it forces.
            refine_of = details.get("survey.refine_of")
            uplift_of = details.get("survey.uplift_of")
            base = refine_of if isinstance(refine_of, str) else uplift_of
            self._scan.refine_base = base if isinstance(base, str) else None
            arm = details.get("survey.uplift_arm")
            self._scan.uplift_arm = arm if isinstance(arm, str) else None
            if snapshot is not None and snapshot.get("kind") == "survey":
                self._scan.ingest_survey(
                    snapshot["survey"], snapshot.get("preview"))
            self._scan.lane_regions = int(details.get("survey.regions", 0) or 0)
            self._scan.survey_seen = True
        elif name == "address.region_open":
            self._scan.set_region_state(
                details.get("address.region"), "active")
            self._scan.queue_total = None
            self._scan.deferred = 0
        elif name == "address.window_planned":
            self._scan.ingest_planned(details)
        elif name == "address.window_resolved":
            self._scan.resolve_window(details, self._capture_sha or "")
        elif name == "address.patch_accepted":
            self._ingest_word_solve(details)
        elif name == "address.cold_deferred":
            self._scan.deferred = int(details.get("address.deferred", 0) or 0)
            self._scan.set_planned_state(details, "parked")
        elif name == "address.word_rest_open":
            self._scan.set_planned_state(details, "rest")
        elif name == "address.word_rest_refused":
            self._scan.set_planned_state(details, "parked")
        elif name == "address.cold_open":
            pages = details.get("address.pages")
            self._phase = (f"cold search · {pages} page(s)"
                           if pages is not None else "cold search")
            self._scan.set_planned_state(details, "active")
        elif name == "address.cold_progress":
            # v0.33 D14c count-bounded heartbeat: phase text only — never a
            # milestone, never snapshot, never a pane-A redraw.
            ordinal = details.get("address.page_ordinal")
            total = details.get("address.pages")
            if ordinal is not None and total is not None:
                self._phase = f"cold {int(ordinal)}/{int(total)}"
        elif name == "address.window_progress":
            total = details.get("address.queue_total")
            if total is not None:
                self._scan.queue_total = int(total)
            self._ingest_window(snapshot, event)
        elif name == "address.region_complete":
            region = details.get("address.region")
            self._scan.set_region_state(
                region, str(details.get("address.state", "unresolved")))
            self._scan.active_window = None
            self._scan.deferred = 0
            if type(region) is int:
                self._scan.planned = {
                    key: row for key, row in self._scan.planned.items()
                    if key[0] != region}
            if snapshot is not None and snapshot.get(
                    "kind") == "address_progress":
                for patch in snapshot["placements"]:
                    self._paint_patch(patch, event)
        elif name == "address.final":
            self._scan.deferred = 0
            self._scan.planned.clear()
            self._ingest_address_final(details, snapshot, event)
        elif name == "payload.owner_frozen":
            if snapshot is not None and snapshot.get(
                    "kind") == "payload_reach":
                self._ingest_payload_reach(snapshot)
        elif name == "payload.retry_open":
            if snapshot is not None and snapshot.get(
                    "kind") == "retry_frontier":
                self._retry_pending = {
                    (int(page), int(ty), int(tx), str(stream))
                    for page, ty, tx, stream in snapshot.get("tiles", ())}
                for row in self._retry_pending:
                    self._touch(row[0])
        elif name == "payload.retry_complete":
            for row in self._retry_pending:
                self._touch(row[0])
            self._retry_pending.clear()
        elif name == "payload.plane_fields":
            # ONE producer vehicle (field_stats.py's docstring): the
            # snapshot AND the plane_fields.* Details ride this event —
            # reading them off stage.complete left the F fold dead.
            self._field.ingest_snapshot(snapshot)     # field_view.py
            self._field.ingest_details(details)       # field_view.py
        elif name in ("payload.attempt", "payload.retry_attempt"):
            # One engine vocabulary (RECEIVE-DESIGN §6.4): K and color both
            # emit these names; the stream detail defaults to "main".
            self._ingest_attempt(
                int(details.get("payload.page", 0) or 0),
                int(details.get("payload.tile_y", 0) or 0),
                int(details.get("payload.tile_x", 0) or 0),
                str(details.get("payload.stream", "main") or "main"),
                str(details.get("payload.attempt_state", "") or ""),
                stage=str(details.get("payload.attempt_stage", "") or ""),
                decoder_invoked=bool(details.get("payload.decoder_invoked")),
                new_certificate=bool(details.get("payload.certificate_is_new")))
        elif name == "barrier.committed":
            if snapshot is not None and snapshot.get("kind") == "barrier":
                delta = snapshot.get("delta")
                if getattr(delta, "certificates", None) is not None:
                    self._ingest_delta(delta, snapshot["state"])
                else:
                    self._ingest_state(snapshot["state"])
                close_value = snapshot.get("close")
                if isinstance(close_value, dict):
                    self._close_row = close_row(close_value)
        elif name == "close.check":
            if snapshot is not None and snapshot.get("kind") == "close":
                self._close_row = close_row(snapshot)
        elif name == "session.complete":
            self._phase = "session complete"
            self._session_phase = None
            self._phase_rung = None
            if snapshot is not None and snapshot.get(
                    "kind") == "session_summary":
                self._ingest_state(snapshot["state"])
                close_value = snapshot.get("close")
                if isinstance(close_value, dict):
                    self._close_row = close_row(close_value)
        self._render(force=name in _MILESTONES)

    # -- pane A (the scan-space model lives in scan_model.py) ----------
    def _seed_committed(self, state: object) -> None:
        """v0.45 declared ruling: seed panes A and C from durable records.

        Runs once, at the ``session.open`` committed bootstrap (the same
        state hand-off pane D already rides), so a resumed invocation
        starts with the prior work's scrap layout and address landscape
        instead of blank panes.  Everything applied here is a faithful
        derivation of committed records (never pixels): pane C gets exact
        sticky conflicts plus the committed-addressed ``_WORD_SEEDED``
        cover, ranked below every live evaluation outcome so this
        invocation's own re-reads paint over it (idempotent by the same
        monotone ladder live ingestion uses); pane-A models install when
        ``capture.open`` re-opens their capture; durable parked chips
        rebuild under their live identity keys, so a live re-park is a
        same-key overwrite and barrier reconciliation retires them
        exactly as before.  Seeded facts never touch the observed-site
        bitmask, the mapped-footprint counter, or the window/attempt
        counters — those stay live-invocation facts.
        """
        for key, value in seed_words(state, self._tiles_yx).items():
            previous = self._word_state.get(key, 0)
            if previous == _WORD_CONFLICT:
                continue
            if value == _WORD_CONFLICT or value > previous:
                self._word_state[key] = value
                self._touch(key[0])
        self._scan.seed_from_records(*seed_scan_models(state, self._panes))

    def _rung_phrase(self) -> str:
        ppc, total = self._phase_rung or ("?", 0)
        return (f"rung {ppc}ppc · capture "
                f"{max(self._phase_capture_k, 1)}/{total or '?'}")

    # v0.33 pane-A model retention across capture switches (§10.5): the
    # fields below are the capture/lane-local model that capture.open
    # resets; capture.resume swaps them instead.
    def _ingest_payload_reach(self, snapshot: dict[str, object]) -> None:
        tiles_x = int(snapshot.get("tiles_x") or self._tiles_yx[1])
        for page, flats in dict(snapshot.get("pages") or {}).items():
            states = self._tile_states(int(page))
            for flat in np.asarray(flats, np.int64).ravel():
                ty, tx = divmod(int(flat), tiles_x)
                if (0 <= ty < self._tiles_yx[0]
                        and 0 <= tx < self._tiles_yx[1]):
                    np.maximum(states[:, ty, tx], _TILE_STATE_EVIDENCE,
                               out=states[:, ty, tx])

    # -- pane B / C ----------------------------------------------------
    def _lane_key(self, event: RuntimeEvent) -> tuple[str, str]:
        return (event.capture_id or "", event.context.lane_id or "")

    def _touch(self, page: int) -> None:
        """Mark one page's panes for the next render (§10.5 laziness)."""
        self._dirty_pages.add(int(page))

    def _placed_canvas(self, page: int) -> np.ndarray:
        canvas = self._placed.get(page)
        if canvas is None:
            canvas = np.zeros((self._height, self._width), np.uint16)
            self._placed[page] = canvas
        self._touch(page)
        return canvas

    def _covered_cells(self, page: int) -> np.ndarray:
        covered = self._covered.get(page)
        if covered is None:
            covered = np.zeros(self._cells_yx, bool)
            self._covered[page] = covered
        return covered

    def _paint_patch(self, patch: object, event: RuntimeEvent) -> None:
        key = (*self._lane_key(event), int(patch.patch_id))
        if key in self._painted_patches:
            return
        self._painted_patches.add(key)
        page = int(patch.candidate.page)
        cells = np.asarray(patch.page_cells_yx, np.int64)
        if cells.ndim != 2 or not len(cells):
            return
        cy, cx = self._cells_yx
        keep = ((cells[:, 0] >= 0) & (cells[:, 0] < cy)
                & (cells[:, 1] >= 0) & (cells[:, 1] < cx))
        cells = cells[keep]
        if not len(cells):
            return
        covered = self._covered_cells(page)
        # Exact §10.3.2 numerator: count only newly reached cells that are
        # registered PAYLOAD cells (per-tile furniture excluded), kept as a
        # running integer so no frame ever rescans a page-sized mask.
        fresh = ~covered[cells[:, 0], cells[:, 1]]
        if fresh.any() and self._payload_cells_per_tile:
            new_cells = cells[fresh]
            if self._furniture_flat is None:
                added = len(new_cells)
            else:
                within = ((new_cells[:, 0] % 64) * 64
                          + (new_cells[:, 1] % 64))
                added = int(np.count_nonzero(
                    ~np.isin(within, self._furniture_flat)))
            self._covered_payload[page] = (
                self._covered_payload.get(page, 0) + added)
        covered[cells[:, 0], cells[:, 1]] = True
        self._touch(page)
        hue = int(patch.region_index) % len(_HUES)
        py = (cells[:, 0] * (self._height / cy)).astype(np.intp)
        px = (cells[:, 1] * (self._width / cx)).astype(np.intp)
        self._placed_canvas(page)[py, px] = hue + 1
        for observation in patch.observations:
            site_key = (int(observation.page), int(observation.tile_yx[0]),
                        int(observation.tile_yx[1]))
            self._sites[site_key] = self._sites.get(site_key, 0) | (
                1 << int(observation.site_index))
            self._word_state.setdefault(site_key, _WORD_EVIDENCE)
            self._touch(site_key[0])
        self._windows_accepted += 1
        self._scan.set_region_state(int(patch.region_index), "accepted")

    def _ingest_window(self, snapshot: dict[str, object] | None,
                       event: RuntimeEvent) -> None:
        if snapshot is None:
            return
        kind = snapshot.get("kind")
        if kind == "window":  # terminal
            self._windows_attempted += 1
            self._scan.active_window = None
            placed = snapshot.get("placed")
            if placed is not None:
                # Accepted footprints become solid immediately.
                self._paint_patch(placed, event)
            return
        if kind != "window_phase":
            return
        window = snapshot.get("window")
        pitch = snapshot.get("pitch_px")
        origin = snapshot.get("region_origin_yx")
        if window is not None and pitch and origin is not None:
            self._scan.ingest_active_window(window, pitch, origin)
        candidate = snapshot.get("candidate")
        if candidate is not None and window is not None:
            hh, ww = window.shape_yx_cells
            if int(candidate.rot_k) % 2:
                hh, ww = ww, hh
            rect = (int(candidate.page), int(candidate.origin_yx[0]),
                    int(candidate.origin_yx[1]), int(hh), int(ww))
            self._prov_rects.append(rect)
            del self._prov_rects[:-6]

    def _ingest_word_solve(self, details: dict[str, object]) -> None:
        """v0.43 pane-C authority tri-state: an ``address.patch_accepted``
        with word-tile details marks the tile whose BCH word the seeder
        decoded — the word decoder itself produced the address (full
        green).  Chain/lower/correlation acceptances carry no such details
        and change no word state; deep red stays contradiction-only, so a
        conflicted tile is never repainted."""
        page = details.get("address.page")
        tile_y = details.get("address.word_tile_y")
        tile_x = details.get("address.word_tile_x")
        if page is None or tile_y is None or tile_x is None:
            return
        key = (int(page), int(tile_y), int(tile_x))
        if self._word_state.get(key) != _WORD_CONFLICT:
            self._word_state[key] = _WORD_SOLVED
            self._touch(key[0])

    def _ingest_address_final(self, details: dict[str, object],
                              snapshot: dict[str, object] | None,
                              event: RuntimeEvent) -> None:
        self._scan.active_window = None
        self._prov_rects.clear()
        if snapshot is None or snapshot.get("kind") != "address":
            return
        result = snapshot["product"].transient
        if result is None:
            return
        if isinstance(result, RefineAddressPlan):
            # An R-level's stage-A ``address.final`` is empty by design:
            # the plan carries the BASE lane's committed poses/regions and
            # the certificate frontier as refinement INPUT, not new
            # placements — those poses were already painted under the base
            # lane's key, and adopted refined poses arrive on this lane's
            # refined re-emission, whose snapshot carries an ordinary
            # ``AddressResult``.  Nothing new is true here, so nothing is
            # ingested (the emitted details are all zero).
            return
        for patch in result.placements:
            self._paint_patch(patch, event)
        for word in result.words:
            key = (int(word.page), int(word.tile_yx[0]),
                   int(word.tile_yx[1]))
            if word.conflict:
                state = _WORD_CONFLICT
            elif word.certified:
                # §5.4 known-position PASS on a placement-addressed tile:
                # read-and-validated (v0.43 lighter green).  A word-route
                # SOLVE already holds the higher _WORD_SOLVED and stands.
                state = _WORD_VALIDATED
            elif word.decoded_counter is not None:
                state = _WORD_VALIDATED
            elif word.erasures > _WORD_ERASURE_BUDGET:
                state = _WORD_FLOOR
            else:
                state = _WORD_FAILED
            previous = self._word_state.get(key, 0)
            if state == _WORD_CONFLICT or state > previous:
                self._word_state[key] = state
                self._touch(key[0])
        self._lane_address[self._lane_key(event)] = (
            int(details.get("address.placements", 0) or 0),
            int(details.get("address.unresolved", 0) or 0),
            int(details.get("address.placements_quarantined", 0) or 0),
        )

    # -- pane D / counters --------------------------------------------
    def _tile_states(self, page: int) -> np.ndarray:
        states = self._tiles.get(page)
        if states is None:
            states = np.zeros((len(self._streams), *self._tiles_yx), np.uint8)
            self._tiles[page] = states
        self._touch(page)
        return states

    def _stream_index(self, stream: str) -> int:
        try:
            return self._streams.index(stream)
        except ValueError:
            return 0

    def _ingest_attempt(self, page: int, ty: int, tx: int, stream: str,
                        state: str, *, stage: str, decoder_invoked: bool,
                        new_certificate: bool) -> None:
        tile_y, tile_x = self._tiles_yx
        if not (0 <= ty < tile_y and 0 <= tx < tile_x):
            return
        # Either terminal retry outcome clears the in-flight highlight.
        self._retry_pending.discard((page, ty, tx, stream))
        code = {"certified": _TILE_STATE_CERTIFIED,
                "attempted_failed": _TILE_STATE_FAILED,
                "below_attempt_floor": _TILE_STATE_FLOOR,
                }.get(state, _TILE_STATE_EVIDENCE)
        states = self._tile_states(page)
        row = states[self._stream_index(stream)]
        if code >= row[ty, tx] or code == _TILE_STATE_CERTIFIED:
            row[ty, tx] = code
        if decoder_invoked:
            self._trans_calls += 1
        if new_certificate:
            self._trans_certs += 1
            if stage == "retry150":
                self._trans_bp150 += 1

    def _paint_certificates(self, rows: object) -> None:
        for row in rows:
            page = int(row.page)
            ty, tx = (int(v) for v in row.tile_yx)
            tile_y, tile_x = self._tiles_yx
            if 0 <= ty < tile_y and 0 <= tx < tile_x:
                states = self._tile_states(page)
                states[self._stream_index(str(row.stream_id)),
                       ty, tx] = _TILE_STATE_CERTIFIED

    def _ingest_delta(self, delta: object, state: object) -> None:
        """Barrier path: fold only the delta's new durable certificates."""
        rows = tuple(getattr(delta, "certificates", ()) or ())
        self._paint_certificates(rows)
        self._certs_committed += len(rows)
        self._trans_certs = 0
        self._trans_bp150 = 0
        self._scan.reconcile_parked(state)
        self._ingest_counters_close(state)

    def _ingest_state(self, state: object) -> None:
        certificates = getattr(state, "certificates", None)
        if certificates is not None:
            self._paint_certificates(certificates)
            self._certs_committed = len(certificates)
            self._trans_certs = 0
            self._trans_bp150 = 0
        self._scan.reconcile_parked(state)
        self._ingest_counters_close(state)

    def _ingest_counters_close(self, state: object) -> None:
        counters = getattr(state, "counters", None)
        if counters is not None:
            tallies = [getattr(counters, stage, None)
                       for stage in ("scan", "union", "retry150")]
            if all(tally is not None for tally in tallies):
                self._counters = (
                    sum(tally.evaluations for tally in tallies),
                    sum(tally.decoder_calls for tally in tallies),
                    sum(tally.crc_ok for tally in tallies),
                    tallies[2].crc_ok,
                )
                self._trans_calls = 0
            self._divergences = int(getattr(counters, "divergences", 0))
            self._mopup_dropped = int(getattr(
                counters, "mopup_dropped_observations", 0))
            self._mopup_flips = int(getattr(
                counters, "mopup_winner_flips", 0))
        close = getattr(state, "close", None)
        status_value = getattr(getattr(close, "status", None), "value", None)
        if status_value == "verified":
            sha = str(getattr(close, "payload_sha256", "") or "")
            length = getattr(close, "payload_length", None)
            self._close_row = (
                f"close VERIFIED · {length} bytes · sha {sha[:16]}…")
        elif status_value is not None and status_value != "open":
            reason = str(getattr(close, "reason", "") or "")
            self._close_row = f"close {status_value}" + (
                f" · {reason}" if reason else "")



    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def _pages(self) -> list[int]:
        pages = set(self._placed) | set(self._tiles)
        pages.update(key[0] for key in self._word_state)
        return sorted(pages)

    def _page_default(self, pages: list[int]) -> int:
        if not pages:
            return self._page_domain[0] if self._page_domain else 0
        # Maintained integers only — no page-sized rescan per frame.
        return max(pages, key=lambda page: (
            self._covered_payload.get(page, 0)
            + int(np.count_nonzero(self._tiles.get(page, ())))))

    def _publish_status(self, force: bool) -> None:
        """Unthrottled scalar channel (§10.6): rows move between frames.

        The pane frame is untouched — the browser refetches PNGs only when
        the integer revision moves, while its 1 Hz poll re-reads the rows.
        """
        now = self._clock()
        if (not force and self._last_status is not None
                and now - self._last_status < _STATUS_INTERVAL_S):
            return
        self._last_status = now
        pages = self._pages()
        default = self._page_default(pages)
        status = {
            "schema": "holo-diag-viewer-1",
            "frame": 0,  # patched under the lock
            "done": self._done,
            "pages": pages or [default],
            "page_default": default,
            "rows": status_rows(self, default),
        }
        with self._lock:
            status["frame"] = self._frame
            status["page_frames"] = {
                str(page): revision
                for page, revision in sorted(self._page_frame.items())}
            data = json.dumps(status, separators=(",", ":")).encode()
            self._status_bytes = data
        self._files.write("status.json", data, [])

    def _render(self, force: bool, compose_all: bool = False) -> None:
        now = self._clock()
        if (not force and self._last_render is not None
                and self._interval > 0.0
                and now - self._last_render < self._interval):
            self._publish_status(force=False)
            return
        pages = self._pages()
        default = self._page_default(pages)
        page_list = pages or [default]
        rows = status_rows(self, default)
        # §10.5: render only pages reached by the current causal snapshot,
        # plus any page not yet materialized.  A page not re-rendered keeps
        # its own earlier bytes AND its own earlier revision, so the
        # browser's (page, revision) key never straddles two frames.
        render_pages = [page for page in page_list
                        if page in self._dirty_pages
                        or (("B", page) not in self._raster)]
        with self._lock:
            png = dict(self._png)
            page_frame = dict(self._page_frame)
            wanted = self._wanted_page
        if self._scan.dirty or ("A", -1) not in self._raster:
            self._raster[("A", -1)] = self._pane_scan()
            self._scan_revision += 1
            self._scan.dirty = False
        for page in render_pages:
            self._raster[("B", page)] = self._pane_placements(page)
            self._raster[("C", page)] = self._pane_words(page)
            self._raster[("D", page)] = self._pane_tiles(page)
            self._page_revision[page] = self._page_revision.get(page, 0) + 1
        live = set(page_list)
        # A composed frame costs one encode of four panes, so compose only
        # the pages someone is actually looking at: the default page, plus
        # whichever page the browser last requested.  Every other live page
        # keeps its own coherent earlier frame (§10.5) until it is selected
        # or the terminal frame composes all of them.  Pane A is shared, so
        # a frame is keyed by BOTH revisions; an unchanged pair is reused.
        targets = (live if compose_all
                   else {default} | ({wanted} & live if wanted is not None
                                     else set()))
        composed: list[int] = []
        for page in page_list:
            if page not in targets or ("B", page) not in self._raster:
                continue
            key = (self._scan_revision, self._page_revision.get(page, 0),
                   self._field.revision)
            if self._composed.get(page) != key or page not in png:
                # W5: the band is page-dependent (P1) and absent until a
                # snapshot lands — see field_view.FieldPaneState.band.
                png[page] = self._panes.compose((
                    self._raster[("A", -1)],
                    self._raster[("B", page)],
                    self._raster[("C", page)],
                    self._raster[("D", page)]),
                    self._field.band(self._panes, page))
                self._composed[page] = key
                composed.append(page)
        png = {page: value for page, value in png.items() if page in live}
        page_frame = {page: revision for page, revision in page_frame.items()
                      if page in live}
        self._raster = {key: value for key, value in self._raster.items()
                        if key[1] < 0 or key[1] in live}
        self._field.retain(live)
        self._composed = {page: key for page, key in self._composed.items()
                          if page in live}
        status = {
            "schema": "holo-diag-viewer-1",
            "frame": 0,  # patched under the lock
            "done": self._done,
            "pages": page_list,
            "page_default": default,
            "rows": rows,
        }
        with self._lock:
            self._frame += 1
            for page in composed:
                page_frame[page] = self._frame
            status["frame"] = self._frame
            status["page_frames"] = {
                str(page): revision
                for page, revision in sorted(page_frame.items())}
            self._png = png
            self._page_frame = page_frame
            self._status_bytes = json.dumps(
                status, separators=(",", ":")).encode()
        self._dirty_pages.clear()
        self._publish_files(default, png)
        # §10.6: the throttle anchors after render/publication completion.
        finished = self._clock()
        self._last_render = finished
        self._last_status = finished

    # ------------------------------------------------------------------
    # pane inputs (model -> renderer; the renderer owns no receiver state)
    # ------------------------------------------------------------------
    def _pane_scan(self) -> np.ndarray:
        return self._scan.pane(self._capture_sha or "")

    def _pane_placements(self, page: int) -> np.ndarray:
        return self._panes.placements(
            self._placed.get(page),
            tuple((oy, ox, hh, ww)
                  for rect_page, oy, ox, hh, ww in self._prov_rects
                  if rect_page == page))

    def _pane_words(self, page: int) -> np.ndarray:
        states = {(ty, tx): state
                  for (word_page, ty, tx), state in self._word_state.items()
                  if word_page == page}
        counts = {key: self._sites.get((page, *key), 0).bit_count()
                  for key in states}
        return self._panes.words(states, counts)

    def _pane_tiles(self, page: int) -> np.ndarray:
        return self._panes.tiles(
            self._tiles.get(page), len(self._streams),
            tuple((ty, tx, self._stream_index(stream))
                  for retry_page, ty, tx, stream in self._retry_pending
                  if retry_page == page))

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------



    def _shell(self) -> bytes:
        """The browser shell.  It declares NO frame geometry.

        The composed PNG carries its own proportions (A-D together are
        the A4 page); the page lets the image size itself.  The former
        CSS ``aspect-ratio`` restated those proportions from a
        separately-computed guess and stretched the image whenever the
        two disagreed -- which the W5 band made routine (2026-08-21).
        """
        return (_PAGE % {}).encode()

    def _publish_files(self, default_page: int, png: dict[int, bytes],
                       all_pages: bool = False) -> list[Path]:
        with self._lock:
            status_bytes = self._status_bytes
        return self._files.publish(
            status_bytes, png, sorted(png) if all_pages else [default_page])

    def finalize(self, state: object) -> list[Path]:
        """Fold the committed state in and publish the terminal frame."""
        self._ingest_state(state)
        self._done = True
        self._prov_rects.clear()
        self._scan.active_window = None
        self._scan.dirty = True
        self._phase = "done"
        self._session_phase = None
        self._phase_rung = None
        self._last_render = None
        # The terminal frame is complete: every retained page re-renders and
        # composes, so any page a browser is watching can acknowledge it.
        self._dirty_pages.update(self._pages())
        self._render(force=True, compose_all=True)
        with self._lock:
            png = dict(self._png)
        pages = self._pages()
        default = self._page_default(pages)
        return self._publish_files(default, png, all_pages=True)

    def close(self, grace_s: float = 2.5) -> None:
        httpd = self._httpd
        if httpd is None:
            return
        self._httpd = None
        deadline = time.monotonic() + max(0.0, grace_s)
        while time.monotonic() < deadline:
            with self._lock:
                if not self._ever_served or self._served_frame >= self._frame:
                    break
            time.sleep(0.05)
        httpd.shutdown()
        httpd.server_close()



__all__ = ["LiveView", "SNAPSHOT_EVENTS"]
