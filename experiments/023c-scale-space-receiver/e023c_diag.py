"""Observer-only diagnostics for the E023c scale-space receiver.

The receiver renders pane images and publishes a small JSON status snapshot.
This module deliberately knows nothing about E021/E022/E023 state classes: it
owns only detached PNG bytes and detached JSON metadata.  Consequently a
diagnostic render, filesystem, or HTTP failure cannot mutate or stop the
receiver.  Disk and HTTP are independent transports: losing one leaves the
other and the detached in-memory frame usable.

Each logical page is displayed as four deterministic panes:

``A`` scan/segmentation, ``B`` placement, ``C`` pilots, and ``D`` payload.

Callers may provide either an already-rendered page image or four individual
pane artifacts.  A pane artifact may be a PIL image, encoded image bytes, a
filesystem path, or ``None`` (rendered as an explicit unavailable pane).
"""
from __future__ import annotations

import io
import json
import os
import re
import threading
import time
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PANE_ORDER = ("A", "B", "C", "D")
PANE_TITLES = {
    "A": "A  scan / segmentation",
    "B": "B  page placement",
    "C": "C  pilot state",
    "D": "D  payload / LDPC",
}
TRANSIENT_META_KEYS = ("window", "ldpc", "context", "pose_refine")

# The registered causal milestones.  The viewer intentionally accepts other
# non-empty event names too, so adding an observer milestone does not require a
# receiver-state migration.
SCALE_EVENTS = (
    "capture_open",
    "level_open",
    "e021_complete",
    "e022_window_progress",
    "e022_region_complete",
    "pilot_level_final",
    "context_region_complete",
    "pose_refine_window_progress",
    "payload_plan",
    "payload_region_emitted",
    "level_owner_frozen",
    "ldpc_attempt",
    "bp_retry_attempt",
    "bp_retry_complete",
    "ldpc_batch",
    "level_complete",
    "fountain_check",
    "capture_committed",
    "session_complete",
)

_FRAME_RE = re.compile(r"^frame_(\d+)_p-?\d+\.png$")
_RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>E023c scale-space receiver</title><style>
body{margin:0;background:#161616;color:#ddd;font-family:-apple-system,
Segoe UI,Roboto,sans-serif;text-align:center}#s,#d,#l{padding:6px;color:#aaa;
font-size:13px}#d{padding-top:0;color:#d6c18f}#l{padding-top:0;color:#8fb6d9}
button{margin:3px;padding:4px 10px;
background:#333;color:#ddd;border:1px solid #666}button.active{border-color:#ddd;
background:#505050}#f{max-width:100%;height:auto;box-shadow:0 0 24px #000}
</style></head><body><div id="s">connecting</div><div id="d"></div><div id="l"></div><div id="p">
</div><img id="f"><script>let n=-1,pg=0;function choose(p){pg=p;n=-1}
function number(v,d){return v===null||v===undefined?'?':Number(v).toFixed(d)}
function levelText(j){const i=j.level_index,tot=j.levels_total;
let x=(i===null||i===undefined)?'scale ?':('scale '+(Number(i)+1)+
(tot?'/'+tot:''));if(j.ppc!==null&&j.ppc!==undefined)x+=' · '+number(j.ppc,2)+
' ppc';if(j.effective_dpi!==null&&j.effective_dpi!==undefined)x+=' @ '+
number(j.effective_dpi,0)+' dpi';return x}async function poll(){try{const r=await
fetch('/status.json',{cache:'no-store'});const j=await r.json();if(
!j.pages.includes(pg))pg=j.pages[0]||0;const tabs=document.getElementById('p');
tabs.replaceChildren();j.pages.forEach(p=>{const b=document.createElement('button');
b.textContent='page '+p;b.className=p===pg?'active':'';b.onclick=()=>choose(p);
tabs.appendChild(b)});const event=j.event||j.phase||'waiting';let s=event+
' · capture '+(j.capture_id||'-')+' · '+levelText(j)+' · regions '+
(j.regions_done||0)+'/'+(j.regions||0)+' · pilots(frame) '+
(j.pilots_solved||0)+
' · certified '+(j.certified||0)+' · attempts '+(j.attempts||0)+
' · frame '+j.frame;const c=j.completion;if(c){s+=' · rank '+
(c.rank===null||c.rank===undefined?'?':c.rank)+' · shortfall '+
(c.shortfall===null||c.shortfall===undefined?'?':c.shortfall)+
' · verified '+Boolean(c.verified)}document.getElementById('s').textContent=s;
document.getElementById('d').textContent=j.detail||'';
const ladder=Array.isArray(j.scale_ladder)?j.scale_ladder:[];
document.getElementById('l').textContent=ladder.map((x,k)=>{const label=
(x.ppc===undefined?('level '+(k+1)):(number(x.ppc,2)+' ppc'));
return label+': '+(x.status||'pending')}).join('  →  ');if(j.frame!==n){n=j.frame;
document.getElementById('f').src='/frame.png?page='+pg+'&t='+Date.now();}}
catch(e){document.getElementById('s').textContent='session idle';}
setTimeout(poll,1000)}poll();</script></body></html>"""


class ProgressThrottle:
    """Wall-clock gate for expensive transient diagnostic renders.

    Status metadata remains free to advance on every observer event; this
    gate controls only image composition and PNG publication.  The supplied
    clock keeps the policy deterministic in tests.
    """

    def __init__(self, interval_s: float = 3.0, *, clock=time.monotonic):
        interval = float(interval_s)
        if not interval >= 0.0:
            raise ValueError("diagnostic interval must be non-negative")
        self.interval_s = interval
        self._clock = clock
        self._last_rendered: float | None = None

    def allow(self, *, force: bool = False) -> bool:
        now = float(self._clock())
        if (force or self._last_rendered is None
                or now - self._last_rendered >= self.interval_s):
            self._last_rendered = now
            return True
        return False

    def mark_rendered(self) -> None:
        """Anchor the next interval at render completion, not render start."""
        self._last_rendered = float(self._clock())


def _read_image(value: Any) -> Image.Image:
    """Load one rendered image into a detached RGB PIL object."""
    if isinstance(value, Image.Image):
        image = value.copy()
        image.load()
        return image.convert("RGB")
    if isinstance(value, (bytes, bytearray, memoryview)):
        source = io.BytesIO(bytes(value))
        with Image.open(source) as opened:
            opened.load()
            return opened.convert("RGB")
    if isinstance(value, (str, os.PathLike)):
        with Image.open(Path(value)) as opened:
            opened.load()
            return opened.convert("RGB")
    raise TypeError(
        "rendered image must be PIL, encoded bytes, a path, or None")


def _pane_values(panes: Mapping[str, Any] | Sequence[Any]) -> tuple[Any, ...]:
    if isinstance(panes, Mapping):
        normalised = {str(key).upper(): value for key, value in panes.items()}
        missing = [key for key in PANE_ORDER if key not in normalised]
        extra = sorted(set(normalised) - set(PANE_ORDER))
        if missing or extra:
            raise ValueError(
                f"four-pane mapping needs exactly A/B/C/D; "
                f"missing={missing}, extra={extra}")
        return tuple(normalised[key] for key in PANE_ORDER)
    if isinstance(panes, Sequence) and not isinstance(
            panes, (str, bytes, bytearray, memoryview)):
        values = tuple(panes)
        if len(values) != 4:
            raise ValueError("four-pane sequence must contain exactly 4 panes")
        return values
    raise TypeError("panes must be an A/B/C/D mapping or four-item sequence")


def compose_four_pane(
    panes: Mapping[str, Any] | Sequence[Any],
    *,
    panel_width: int = 600,
    background: tuple[int, int, int] = (250, 250, 250),
) -> Image.Image:
    """Return a deterministic A/B/C/D canvas made only from rendered panes.

    Every available pane is scaled to exactly ``panel_width`` while retaining
    its aspect ratio.  Shorter panes and unavailable panes are padded to the
    tallest available pane.  No input PIL object is modified.
    """
    width = int(panel_width)
    if width <= 0:
        raise ValueError("panel_width must be positive")
    values = _pane_values(panes)
    scaled: list[Image.Image | None] = []
    default_height = max(1, round(width * 0.75))
    body_height = default_height
    for value in values:
        if value is None:
            scaled.append(None)
            continue
        image = _read_image(value)
        height = max(1, round(image.height * width / image.width))
        resized = image.resize((width, height), _RESAMPLE)
        scaled.append(resized)
        body_height = max(body_height, height)

    title_height = max(24, round(width * 0.055))
    canvas = Image.new(
        "RGB", (4 * width, title_height + body_height), background)
    draw = ImageDraw.Draw(canvas)
    for index, (letter, panel) in enumerate(zip(PANE_ORDER, scaled)):
        x0 = index * width
        draw.rectangle(
            (x0, 0, x0 + width - 1, title_height - 1),
            fill=(232, 235, 238), outline=(175, 180, 185))
        draw.text((x0 + 7, max(2, (title_height - 11) // 2)),
                  PANE_TITLES[letter], fill=(35, 40, 45))
        if panel is None:
            message = f"pane {letter} unavailable"
            draw.text((x0 + 8, title_height + 10), message,
                      fill=(120, 120, 120))
        else:
            canvas.paste(panel, (x0, title_height))
        if index:
            draw.line((x0, 0, x0, canvas.height - 1),
                      fill=(175, 180, 185), width=1)
    return canvas


def _encode_png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False, compress_level=6)
    return stream.getvalue()


def diagnostic_png_bytes(
    panes: Mapping[str, Any] | Sequence[Any],
    *,
    panel_width: int = 600,
) -> bytes:
    """Compose four rendered panes and return deterministic PNG bytes."""
    return _encode_png(compose_four_pane(panes, panel_width=panel_width))


def rendered_png_bytes(value: Any, *, panel_width: int = 600) -> bytes:
    """Detach an already-rendered page or compose a four-pane page."""
    if isinstance(value, Mapping) or (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes, bytearray, memoryview))):
        return diagnostic_png_bytes(value, panel_width=panel_width)
    if value is None:
        raise ValueError("a complete rendered page cannot be None")
    # Always re-encode after decoding.  Besides accepting JPEG and other PIL
    # inputs, this validates PNG input and strips mutable/external metadata.
    return _encode_png(_read_image(value))


def _json_detach(value: Any) -> Any:
    """Return a JSON-only deep copy, rejecting receiver/state objects."""
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return json.loads(encoded)


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(
        f".{path.name}.{threading.get_ident()}.tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class DiagViewer:
    """Persistent page-tab viewer owning only PNG bytes and JSON metadata."""

    def __init__(
        self,
        out_dir: Path,
        port: int,
        *,
        serve: bool = True,
        panel_width: int = 600,
    ):
        # Initialise every isolation primitive before touching either output
        # transport.  In particular, an unwritable/malformed frame directory
        # is an observer capability failure, not a receiver configuration
        # failure, and does not prevent a memory-backed live viewer.
        self._lock = threading.Lock()
        self._publish_lock = threading.Lock()
        self._broken = False
        self._disk_enabled = False
        self._httpd: ThreadingHTTPServer | None = None
        self._served_frame = 0
        self._ever_served = False
        self._frame_no = 0
        try:
            self.out_dir = Path(out_dir)
            self.out_dir.mkdir(parents=True, exist_ok=True)
            existing = []
            for path in self.out_dir.glob("frame_*_p*.png"):
                match = _FRAME_RE.match(path.name)
                if match:
                    existing.append(int(match.group(1)))
            self._frame_no = max(existing) if existing else 0
            self._disk_enabled = True
        except Exception as exc:
            # Keep a printable, inert path even when a hostile __fspath__
            # implementation itself failed.  No write is attempted after
            # this point unless directory discovery completed successfully.
            if not hasattr(self, "out_dir"):
                self.out_dir = Path(".")
            print(
                f"  [diag] frame persistence unavailable: {exc!r}; "
                "live/in-memory diagnostics continue", flush=True)
        self._latest: dict[int, bytes] = {}
        self._meta: dict[str, Any] = {
            "event": "waiting",
            "phase": "waiting",
            "capture_id": "-",
            "view_id": "-",
            "level_index": None,
            "levels_total": 0,
            "ppc": None,
            "effective_dpi": None,
            "scale_ladder": [],
            "regions_done": 0,
            "regions": 0,
            "placements": 0,
            "pilots_solved": 0,
            "certified": 0,
            "attempts": 0,
            "detail": "",
            **{key: None for key in TRANSIENT_META_KEYS},
            "pages": [],
            "frame": self._frame_no,
        }
        self.panel_width = int(panel_width)
        if self.panel_width <= 0:
            raise ValueError("panel_width must be positive")
        try:
            self.port = int(port)
        except Exception as exc:
            self.port = 0
            serve = False
            print(
                f"  [diag] live server unavailable: {exc!r}; "
                "frame persistence continues", flush=True)
        if serve:
            try:
                self._httpd = _serve(self)
                self.port = int(self._httpd.server_address[1])
                persistence = (
                    f"frames -> {self.out_dir}" if self._disk_enabled
                    else "frame persistence unavailable")
                print(
                    f"  [diag] live view at http://localhost:{self.port}/; "
                    f"{persistence}", flush=True)
            except Exception as exc:  # observer startup is non-fatal
                # Serving and frame persistence are independent observer
                # capabilities.  A sandboxed or occupied socket must not
                # suppress useful PNG/JSON diagnostics on disk.
                persistence = (
                    f"frames continue -> {self.out_dir}"
                    if self._disk_enabled else
                    "frame persistence is also unavailable")
                print(
                    f"  [diag] live server unavailable: {exc!r}; "
                    f"{persistence}", flush=True)

    @property
    def broken(self) -> bool:
        with self._lock:
            return self._broken

    @property
    def disk_enabled(self) -> bool:
        """Whether future frames can still be persisted to ``out_dir``."""
        with self._lock:
            return self._disk_enabled

    @property
    def server_enabled(self) -> bool:
        """Whether the optional localhost transport is currently active."""
        return self._httpd is not None

    def status(self) -> dict[str, Any]:
        """Return a detached JSON snapshot of the observer's latest status."""
        with self._lock:
            return _json_detach(self._meta)

    def latest(self, page: int) -> bytes | None:
        """Return detached latest PNG bytes for ``page``, if published."""
        with self._lock:
            value = self._latest.get(int(page))
            return None if value is None else bytes(value)

    def update_status(
        self,
        meta: Mapping[str, Any] | None = None,
        *,
        event: str | None = None,
    ) -> bool:
        """Advance detached live metadata without composing a new frame.

        This is the cheap path for per-window and per-LDPC-attempt events.
        It deliberately does not increment ``frame`` or write a sidecar, so
        a browser can show the exact current operation at high frequency
        while PNG rendering remains throttled.
        """
        with self._lock:
            if self._broken:
                return False
        try:
            raw_meta = {} if meta is None else meta
            if not isinstance(raw_meta, Mapping):
                raise TypeError("diagnostic metadata must be a mapping")
            detached_meta = _json_detach(dict(raw_meta))
            chosen_event = event
            if chosen_event is None:
                chosen_event = detached_meta.get(
                    "event", detached_meta.get("phase", "update"))
            if not isinstance(chosen_event, str) or not chosen_event.strip():
                raise ValueError(
                    "diagnostic event must be a non-empty string")
            chosen_event = chosen_event.strip()
            detached_meta["event"] = chosen_event
            detached_meta["phase"] = chosen_event
            with self._publish_lock:
                with self._lock:
                    if self._broken:
                        return False
                    complete_meta = dict(self._meta)
                    complete_meta.update(
                        {key: None for key in TRANSIENT_META_KEYS})
                    complete_meta["detail"] = ""
                    complete_meta.update(detached_meta)
                    # Frame/page ownership remains with publish().
                    complete_meta["frame"] = self._frame_no
                    complete_meta["pages"] = sorted(self._latest)
                    self._meta = complete_meta
            return True
        except Exception as exc:
            self.disable(exc)
            return False

    def publish(
        self,
        pages: Mapping[int, Any],
        meta: Mapping[str, Any] | None = None,
        *,
        event: str | None = None,
    ) -> bool:
        """Publish one complete event frame; return false on core failure.

        Render/metadata failures disable the observer because no valid frame
        exists.  Disk failures disable only persistence; the detached frame
        and optional HTTP view still advance.
        """
        with self._lock:
            if self._broken:
                return False
        try:
            if not isinstance(pages, Mapping) or not pages:
                raise ValueError("diagnostic pages must be a non-empty mapping")
            detached_pages: dict[int, bytes] = {}
            for raw_page, rendered in pages.items():
                if isinstance(raw_page, bool):
                    raise ValueError("diagnostic page ids must be integers")
                page = int(raw_page)
                if page != raw_page or page < 0:
                    raise ValueError(
                        "diagnostic page ids must be non-negative integers")
                if page in detached_pages:
                    raise ValueError(f"duplicate diagnostic page {page}")
                detached_pages[page] = rendered_png_bytes(
                    rendered, panel_width=self.panel_width)

            raw_meta = {} if meta is None else meta
            if not isinstance(raw_meta, Mapping):
                raise TypeError("diagnostic metadata must be a mapping")
            detached_meta = _json_detach(dict(raw_meta))
            chosen_event = event
            if chosen_event is None:
                chosen_event = detached_meta.get(
                    "event", detached_meta.get("phase", "update"))
            if not isinstance(chosen_event, str) or not chosen_event.strip():
                raise ValueError("diagnostic event must be a non-empty string")
            chosen_event = chosen_event.strip()
            detached_meta["event"] = chosen_event
            detached_meta["phase"] = chosen_event

            with self._publish_lock:
                with self._lock:
                    if self._broken:
                        return False
                    frame = self._frame_no + 1
                    complete_meta = dict(self._meta)
                complete_meta.update(
                    {key: None for key in TRANSIENT_META_KEYS})
                complete_meta["detail"] = ""
                complete_meta.update(detached_meta)
                complete_meta["pages"] = sorted(detached_pages)
                complete_meta["frame"] = frame
                sidecar = json.dumps(
                    complete_meta, sort_keys=True, separators=(",", ":"),
                    allow_nan=False).encode("utf-8") + b"\n"
                with self._lock:
                    persist = self._disk_enabled
                if persist:
                    try:
                        for page, png in sorted(detached_pages.items()):
                            _atomic_write(
                                self.out_dir /
                                f"frame_{frame:05d}_p{page:04d}.png", png)
                        _atomic_write(
                            self.out_dir / f"frame_{frame:05d}.json", sidecar)
                    except Exception as exc:
                        self.disable_disk(exc)
                with self._lock:
                    self._frame_no = frame
                    self._latest = detached_pages
                    self._meta = complete_meta
            return True
        except Exception as exc:
            self.disable(exc)
            return False

    def publish_event(
        self,
        event: str,
        pages: Mapping[int, Any],
        meta: Mapping[str, Any] | None = None,
    ) -> bool:
        """Event-first convenience wrapper used by receiver callbacks."""
        return self.publish(pages, meta, event=event)

    def disable(self, exc: Exception) -> None:
        """Disable rendering/publication after a non-transport failure."""
        with self._lock:
            if self._broken:
                return
            self._broken = True
        print(
            f"  [diag] disabled after error: {exc!r}; receiver continues",
            flush=True)

    def disable_disk(self, exc: Exception) -> None:
        """Disable frame persistence while retaining memory/HTTP service."""
        with self._lock:
            if not self._disk_enabled:
                return
            self._disk_enabled = False
        print(
            f"  [diag] frame persistence disabled after error: {exc!r}; "
            "live/in-memory diagnostics continue", flush=True)

    def close(self, grace_s: float = 10.0) -> None:
        """Best-effort stop of HTTP only; safe and non-fatal when repeated."""
        server = self._httpd
        if server is None:
            return
        deadline = time.monotonic() + max(0.0, float(grace_s))
        while True:
            with self._lock:
                pending = (self._ever_served
                           and self._served_frame < self._frame_no)
            if not pending or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        errors = []
        try:
            server.shutdown()
        except Exception as exc:
            errors.append(exc)
        try:
            server.server_close()
        except Exception as exc:
            errors.append(exc)
        finally:
            self._httpd = None
        if errors:
            print(
                f"  [diag] live server close error: {errors[0]!r}; "
                "receiver continues", flush=True)


def _serve(viewer: DiagViewer) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_body(self, code: int, content_type: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                return self.send_body(
                    200, "text/html; charset=utf-8", _PAGE.encode("utf-8"))
            if parsed.path == "/status.json":
                with viewer._lock:
                    body = json.dumps(
                        viewer._meta, sort_keys=True,
                        separators=(",", ":")).encode("utf-8")
                return self.send_body(200, "application/json", body)
            if parsed.path == "/frame.png":
                query = parse_qs(parsed.query)
                try:
                    requested = int(query.get("page", [0])[0])
                except (TypeError, ValueError):
                    requested = 0
                with viewer._lock:
                    if requested not in viewer._latest and viewer._latest:
                        requested = min(viewer._latest)
                    body = viewer._latest.get(requested, b"")
                    viewer._served_frame = viewer._frame_no
                    viewer._ever_served = True
                if not body:
                    return self.send_body(404, "text/plain", b"no frame")
                return self.send_body(200, "image/png", body)
            return self.send_body(404, "text/plain", b"not found")

    try:
        server = ThreadingHTTPServer(("127.0.0.1", viewer.port), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, name="e023c-diag", daemon=True)
    try:
        thread.start()
    except BaseException:
        server.server_close()
        raise
    return server
