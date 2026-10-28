"""Publication of the live view: current files on disk, loopback HTTP.

RECEIVE-DESIGN §10.7.  Two independent consumers read the same published
frames — a headless run watches the atomically replaced files in the
diagnostic directory, and an optional `--diag-port` browser polls the small
`status.json` and refetches `frame.png` when its page's revision moves;
requesting a not-yet-composed page returns 404 while teaching the viewer
the wanted page, which the next render then composes.
Neither may reach into the receiver: everything here consumes already
composed bytes.
"""
from __future__ import annotations

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .filesystem import DirectoryIdentity, atomic_write, bind_directory


class CurrentFiles:
    """The operational output directory: current files, never accumulated.

    The directory is bound lazily on first write, and a file whose bytes did
    not change is not rewritten (§10.6: the revision may advance, but a clean
    file is not touched).
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self._identity: DirectoryIdentity | None = None
        self._digests: dict[str, bytes] = {}

    def _bind(self) -> DirectoryIdentity:
        if self._identity is None:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._identity = bind_directory(self.directory)
        return self._identity

    def write(self, name: str, data: bytes, written: list[Path]) -> None:
        digest = hashlib.blake2s(data, digest_size=16).digest()
        path = self.directory / name
        if self._digests.get(name) != digest:
            atomic_write(path, data, durable=False,
                         directory_identity=self._bind())
            self._digests[name] = digest
        written.append(path)

    def publish(self, status_bytes: bytes, frames: dict[int, bytes],
                pages: list[int]) -> list[Path]:
        """Replace `status.json` plus one `frame_pNNN.png` per named page."""
        written: list[Path] = []
        self.write("status.json", status_bytes, written)
        for page in pages:
            data = frames.get(page)
            if data is not None:
                self.write(f"frame_p{page:03d}.png", data, written)
        return written


def serve(view: object, port: int, page_html: bytes) -> ThreadingHTTPServer:
    """Start the loopback view server on a daemon thread.

    ``view`` supplies the lock-guarded published state only: status bytes,
    composed frames, per-page revisions, and the acknowledgement fields.
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):  # noqa: N802 - stdlib name
            pass

        def _send(self, code: int, content_type: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):  # noqa: N802 - stdlib name
            # §10.7: bind loopback only AND require the exact loopback
            # host — a foreign Host header (DNS rebinding) is refused.
            bound = self.server.server_address[1]
            host = (self.headers.get("Host") or "").strip()
            if host not in (f"127.0.0.1:{bound}", f"localhost:{bound}"):
                return self._send(403, "text/plain", b"forbidden host")
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                return self._send(200, "text/html; charset=utf-8", page_html)
            if parsed.path == "/status.json":
                with view._lock:
                    body = view._status_bytes
                return self._send(200, "application/json", body)
            if parsed.path == "/frame.png":
                query = parse_qs(parsed.query)
                try:
                    page = int(query.get("page", ["0"])[0])
                except ValueError:
                    page = 0
                with view._lock:
                    view._wanted_page = page
                    # §10.5: an unmaterialized page is reported unavailable
                    # — NEVER another page's image under a 200, which would
                    # misattribute page geometry.
                    body = view._png.get(page, b"")
                    if body:
                        # §10.3.1: acknowledge the revision paired with the
                        # bytes actually returned, never the caller-supplied
                        # query number, and never a 404.
                        view._served_frame = max(
                            view._served_frame,
                            view._page_frame.get(page, 0))
                        view._ever_served = True
                if not body:
                    return self._send(404, "text/plain", b"no frame")
                return self._send(200, "image/png", body)
            return self._send(404, "text/plain", b"not found")

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


__all__ = ["CurrentFiles", "serve"]
