"""Additive multi-page live viewer for ``run_e023b.py --diag``."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>E023b receiver</title><style>body{margin:0;background:#161616;color:#ddd;
font-family:-apple-system,Segoe UI,Roboto,sans-serif;text-align:center}#s{padding:
7px;color:#aaa;font-size:13px}button{margin:3px;padding:4px 10px;background:
#333;color:#ddd;border:1px solid #666}#f{max-width:100%%;height:auto;box-shadow:
0 0 24px #000}</style></head><body><div id="s">connecting</div><div id="p">
</div><img id="f"><script>let n=-1,pg=0;function choose(p){pg=p;n=-1}
async function poll(){try{const r=await fetch('/status.json',{cache:'no-store'});
const j=await r.json();if(!j.pages.includes(pg))pg=j.pages[0]||0;
document.getElementById('p').innerHTML=j.pages.map(p=>'<button onclick="choose('+p+
')">page '+p+'</button>').join('');document.getElementById('s').textContent=
j.phase+' · scan '+j.scan_id+' · regions '+j.regions_done+'/'+j.regions+
' · certified '+j.certified+' · attempts '+j.attempts+' · frame '+j.frame;
if(j.frame!==n){n=j.frame;document.getElementById('f').src='/frame.png?page='+pg+
'&t='+Date.now();}}catch(e){document.getElementById('s').textContent='session idle';}
setTimeout(poll,1000)}poll();</script></body></html>"""


class DiagViewer:
    """Owns only rendered bytes/status; never a receiver state object."""

    def __init__(self, out_dir: Path, port: int, *, serve: bool = True):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        existing = [
            int(path.name.split("_", 2)[1])
            for path in self.out_dir.glob("frame_*_p*.png")
            if path.name.split("_", 2)[1].isdigit()
        ]
        self._frame_no = max(existing) if existing else 0
        self._latest: dict[int, bytes] = {}
        self._meta = {
            "phase": "waiting", "scan_id": "-", "regions_done": 0,
            "regions": 0, "certified": 0, "attempts": 0,
            "pages": [], "frame": self._frame_no,
        }
        self._lock = threading.Lock()
        self._broken = False
        self._served_frame = 0
        self._ever_served = False
        self._httpd = None
        self.port = int(port)
        if serve:
            self._httpd = _serve(self)
            self.port = int(self._httpd.server_address[1])
            print(f"  [diag] live view at http://localhost:{self.port}/; "
                  f"frames -> {self.out_dir}", flush=True)

    def publish(self, pages: dict[int, bytes], meta: dict) -> None:
        if self._broken:
            return
        if not pages or any(value[:8] != b"\x89PNG\r\n\x1a\n"
                            for value in pages.values()):
            raise ValueError("diagnostic pages must be PNG bytes")
        try:
            with self._lock:
                self._frame_no += 1
                frame = self._frame_no
                self._latest = {int(page): bytes(png)
                                for page, png in pages.items()}
                self._meta.update(meta)
                self._meta["pages"] = sorted(self._latest)
                self._meta["frame"] = frame
            for page, png in sorted(pages.items()):
                (self.out_dir / f"frame_{frame:05d}_p{page:04d}.png").write_bytes(
                    png)
        except Exception as exc:
            self.disable(exc)

    def disable(self, exc: Exception) -> None:
        if not self._broken:
            self._broken = True
            print(f"  [diag] disabled after error: {exc!r}; session continues",
                  flush=True)

    def close(self, grace_s: float = 10.0) -> None:
        if self._httpd is None:
            return
        deadline = time.monotonic() + grace_s
        while (self._ever_served and self._served_frame < self._frame_no
               and time.monotonic() < deadline):
            time.sleep(0.1)
        self._httpd.shutdown()
        self._httpd.server_close()


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
            except BrokenPipeError:
                pass

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                return self.send_body(
                    200, "text/html; charset=utf-8", _PAGE.encode())
            if parsed.path == "/status.json":
                with viewer._lock:
                    body = json.dumps(viewer._meta).encode()
                return self.send_body(200, "application/json", body)
            if parsed.path == "/frame.png":
                query = parse_qs(parsed.query)
                requested = int(query.get("page", [0])[0])
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
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
