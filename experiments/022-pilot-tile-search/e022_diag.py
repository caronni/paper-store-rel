"""Additive live web viewer for ``session_e022.py --diag``.

The viewer owns no placement state. Callers publish complete PNG bytes and a
small status dictionary; failures disable the observer without affecting the
session. Frames persist across invocations and are also served from localhost.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageDraw
import io


def _placeholder() -> bytes:
    image = Image.new("RGB", (1000, 360), (245, 245, 245))
    ImageDraw.Draw(image).text(
        (24, 170), "E022 session diagnostic: waiting for a scan",
        fill=(80, 80, 80),
    )
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>E022 pilot-field session</title><style>
body{margin:0;background:#161616;color:#ddd;font-family:-apple-system,
Segoe UI,Roboto,sans-serif;text-align:center}#s{padding:7px;color:#aaa;
font-size:13px}#f{max-width:100%%;height:auto;box-shadow:0 0 24px #000}
</style></head><body><div id="s">connecting</div><img id="f"
src="/frame.png"><script>let n=-1;async function poll(){try{const r=await
fetch('/status.json',{cache:'no-store'});const j=await r.json();
document.getElementById('s').textContent='scan '+j.scan_id+' '+j.scan+
' · regions '+j.regions_done+'/'+j.regions+' · session '+j.scans+
' scans, '+j.placements+' placements, '+j.tiles+' tiles · BCH '+
j.bch_matching+'/'+j.bch_contradictory+'/'+j.bch_refused+' · frame '+j.frame;
if(j.frame!==n){n=j.frame;document.getElementById('f').src=
'/frame.png?t='+Date.now();}}catch(e){document.getElementById('s').textContent=
'session process is idle';}setTimeout(poll,1000)}poll();</script></body></html>"""


class DiagViewer:
    def __init__(self, out_dir: Path, port: int):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        existing = [
            int(path.stem.rsplit("_", 1)[1])
            for path in self.out_dir.glob("frame_*.png")
            if path.stem.rsplit("_", 1)[-1].isdigit()
        ]
        self._frame_no = max(existing) if existing else 0
        self._served_frame = 0
        self._ever_served = False
        self._latest_png = _placeholder()
        self._meta = {
            "scan": "(none)", "scan_id": "-", "scans": 0,
            "regions_done": 0, "regions": 0, "placements": 0,
            "tiles": 0, "bch_matching": 0, "bch_contradictory": 0,
            "bch_refused": 0, "frame": self._frame_no,
        }
        self._lock = threading.Lock()
        self._broken = False
        self.port = int(port)
        self._httpd = _serve(self)
        self.port = int(self._httpd.server_address[1])
        print(f"  [diag] live view at http://localhost:{self.port}/; "
              f"frames -> {self.out_dir}", flush=True)

    def publish(self, png: bytes, meta: dict) -> None:
        if self._broken:
            return
        if png[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("diagnostic payload is not PNG")
        try:
            with self._lock:
                self._frame_no += 1
                self._latest_png = bytes(png)
                self._meta.update(meta)
                self._meta["frame"] = self._frame_no
                frame_no = self._frame_no
            (self.out_dir / f"frame_{frame_no:05d}.png").write_bytes(png)
        except Exception as exc:  # observer failure cannot abort placement
            self.disable(exc)

    def disable(self, exc: Exception) -> None:
        if not self._broken:
            self._broken = True
            print(f"  [diag] disabled after error: {exc!r}; session continues",
                  flush=True)

    def close(self, grace_s: float = 10.0) -> None:
        deadline = time.monotonic() + grace_s
        while (self._ever_served and self._served_frame < self._frame_no
               and time.monotonic() < deadline):
            time.sleep(0.1)
        self._httpd.shutdown()
        self._httpd.server_close()


def _serve(viewer: DiagViewer) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_body(self, code: int, content_type: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self.send_body(200, "text/html; charset=utf-8",
                               _PAGE.encode("utf-8"))
            elif path == "/frame.png":
                with viewer._lock:
                    body = viewer._latest_png
                    viewer._served_frame = viewer._frame_no
                    viewer._ever_served = True
                self.send_body(200, "image/png", body)
            elif path == "/status.json":
                with viewer._lock:
                    body = json.dumps(viewer._meta).encode("utf-8")
                self.send_body(200, "application/json", body)
            else:
                self.send_body(404, "text/plain", b"not found")

    try:
        server = ThreadingHTTPServer(("127.0.0.1", viewer.port), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
