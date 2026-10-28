#!/usr/bin/env python
"""Live diagnostic viewer for the e018 confetti session decoder (--diag).

An ADDITIVE observer hook for experiments/018-confetti-c3-play/session_decode.py:
the driver calls DiagViewer's methods ONLY when --diag is enabled, so the
default decode path (and its session_state.pkl / fountain result) is
byte-identical with and without the flag.

Two spatial panels, refreshed PER PIECE (watch each scrap land):

  ACTIVE GLASS (left) — the current scan, downsampled once, with every
    piece drawn in its TILTED (de-rotated) frame as it is processed, coloured
    by live status, an angle-estimate label, and — for placer pieces — the
    pilot SITES the receiver sampled, dotted in the PIECE'S OWN ROTATED
    LATTICE FRAME (place.fragment_pilot_sites -> the piece's de-rotation
    geometry -> glass pixels). Boxes/dots accumulate on a persistent overlay
    so the glass fills in as the scan is worked; the piece currently in
    flight is outlined transiently in amber.

  REFERENCE PAGE (right) — the absolute archive page from PageDecodeState
    alone: draw_decode_map's panel B (per-piece payload footprint), panel C
    (LDPC tile status) and panel D (acquired pilot tiles), composited and
    refreshed per piece. LDPC status (C) only advances when the driver runs
    decode_tiles at a scan boundary, so it steps forward at end_scan; B and D
    fill in continuously.

Headless by design (no display in this env, no matplotlib): the "live
window" is a LOCAL WEB VIEW. A stdlib http.server thread serves an
auto-refreshing page at http://localhost:<port>/ that polls the latest
composite PNG (also written, numbered, to the --diag DIR as a durable
record). Fully testable headlessly — start the server, GET /, GET
/frame.png, check the bytes (tests/test_diag.py).

GEOMETRY NOTE (honest): a fragment cell (i, j) is mapped to glass by
scaling the cell grid across the de-rotated piece rectangle and applying
segment.rotate_transform (the exact inverse of the ndimage.rotate that
de-rotated the piece) + the glass bbox offset. The intra-cell grid phase
(dy0/dx0, < 1 cell) is NOT threaded out of the sampler — it is dropped, so
dots are cell-centre-accurate, i.e. sub-pixel at the viewer's downsampled
scale. This is a visualization (lattice orientation + coverage), not a
measurement; the receiver's own numbers live in the decode log.
"""
from __future__ import annotations

import io
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))            # sibling draw_decode_map

from paperholo import place, segment          # noqa: E402
import draw_decode_map as ddm                  # noqa: E402  (panels B/C/D)

Image.MAX_IMAGE_PIXELS = None

# live status -> colour (RGB). The v1 enum the user chose.
STATUS_COL = {
    "in_progress": (255, 179, 0),     # amber  — currently being worked
    "word": (44, 160, 44),            # green  — word/tiled path decoded
    "placed": (31, 119, 180),         # blue   — correlation-placed
    "failed": (214, 39, 40),          # red    — refused / nothing emitted
}
SITE_COL = (255, 92, 231)             # magenta pilot-site dots
LABEL_BG = (24, 24, 24)

GLASS_W = 760                         # target width of each panel column
REF_W = 620


# --------------------------------------------------------------------------
# geometry: fragment cell grid -> glass pixels (see module GEOMETRY NOTE)
# --------------------------------------------------------------------------
def _derot_to_glass(pts_oyox: np.ndarray, piece: "segment.Piece",
                    angle_deg: float) -> np.ndarray:
    """(N, 2) de-rotated-frame (oy, ox) pixels -> (N, 2) full-glass (y, x).

    Uses segment.rotate_transform(piece.img_glass.shape, angle_deg) — the
    exact output->input affine of the ndimage.rotate that created the
    piece — then adds the piece's glass bbox origin."""
    M, off, _ = segment.rotate_transform(piece.img_glass.shape, angle_deg)
    g = (M @ pts_oyox.T).T + off              # -> glass-CROP (y, x)
    y0, x0, _, _ = piece.bbox_glass
    g[:, 0] += y0
    g[:, 1] += x0
    return g


def _cells_to_glass(cells_ij: np.ndarray, bits_shape: tuple[int, int],
                    piece: "segment.Piece", angle_deg: float) -> np.ndarray:
    """(N, 2) fragment cell (i, j) -> (N, 2) glass (y, x), cell-centre
    accurate. The cell grid is scaled across the de-rotated rectangle so the
    mapping is robust to which sampling path produced `bits` (normalize,
    glass-resample, or refine)."""
    _, _, out_shape = segment.rotate_transform(piece.img_glass.shape,
                                               angle_deg)
    ncy, ncx = bits_shape
    oy = (cells_ij[:, 0] + 0.5) / max(ncy, 1) * out_shape[0]
    ox = (cells_ij[:, 1] + 0.5) / max(ncx, 1) * out_shape[1]
    return _derot_to_glass(np.stack([oy, ox], 1), piece, angle_deg)


def _tilted_box_glass(piece: "segment.Piece") -> np.ndarray:
    """The 4 glass-frame corners of the piece's TIGHT tilted frame — the
    bounding box of the de-rotated mask (not the full circumscribing
    rectangle, which over-covers into backing), mapped back to glass at the
    segmenter angle the mask lives in."""
    m = piece.mask
    ys = np.flatnonzero(m.any(axis=1))
    xs = np.flatnonzero(m.any(axis=0))
    if ys.size == 0 or xs.size == 0:
        _, _, (h, w) = segment.rotate_transform(piece.img_glass.shape,
                                                piece.angle_deg)
        y0, x0, y1, x1 = 0, 0, h, w
    else:
        y0, y1, x0, x1 = ys[0], ys[-1], xs[0], xs[-1]
    corners = np.array([[y0, x0], [y0, x1], [y1, x1], [y1, x0]], np.float64)
    return _derot_to_glass(corners, piece, piece.angle_deg)


def _piece_site_cells(placed, bits, core, seed: bytes, spec):
    """Union of pilot-site cells (full-piece frame) the receiver sampled
    across the placed windows — exactly place.fragment_pilot_sites, offset
    by each window origin. Returns (M, 2) int array (may be empty)."""
    if placed is None or bits is None or core is None:
        return np.zeros((0, 2), np.int64)
    out = []
    for (wy, wx, h, w, pl) in placed:
        sij, _sv = place.fragment_pilot_sites(
            pl, (h, w), core[wy:wy + h, wx:wx + w], spec, seed)
        if sij.shape[0]:
            out.append(sij + np.array([wy, wx], np.int64))
    return np.concatenate(out) if out else np.zeros((0, 2), np.int64)


# --------------------------------------------------------------------------
# the observer hook
# --------------------------------------------------------------------------
def _safe(fn):
    """Review fix (018.3 diag round): the viewer must NEVER abort a real
    decode — any internal error disables it with a warning and the
    session continues (the 'additive observer' contract, enforced)."""
    def wrap(self, *a, **k):
        if getattr(self, "_broken", False):
            return
        try:
            return fn(self, *a, **k)
        except Exception as e:                      # noqa: BLE001
            self._broken = True
            print(f"  [diag] viewer disabled after error in "
                  f"{fn.__name__}: {e!r} (decode continues)", flush=True)
    return wrap


class DiagViewer:
    """Additive per-piece observer. Construct once (starts the web server),
    call begin_scan / on_piece / end_scan from the driver behind `--diag`,
    close() at the end. All methods are read-only w.r.t. the decode state.
    Hook methods are exception-proof: an internal error disables the viewer
    and never propagates into the decode."""

    def __init__(self, out_dir: Path, port: int, spec, seed: bytes,
                 dpi: float, title: str = "e018 confetti decode — live"):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.spec = spec
        self.seed = seed
        self.dpi = float(dpi)
        self.title = title
        self._lock = threading.Lock()
        self._latest_png: bytes = _placeholder_png(title)
        # CONTINUE numbering past any frames already in the dir instead of
        # overwriting from 1 — a resumed session (fresh DiagViewer, same
        # --diag dir) otherwise clobbered the prior run's durable record
        # (2026-07-12). No per-run subdir: tests/test_diag globs the dir
        # non-recursively.
        existing = [int(p.stem.split("_")[1]) for p in
                    self.out_dir.glob("frame_*.png")
                    if p.stem.split("_")[-1].isdigit()]
        self._frame_no = max(existing) if existing else 0
        self._served_frame = 0        # highest frame number served over HTTP
        self._ever_served = False     # has any client fetched a frame?
        self._meta = {"scan": "(none)", "pieces": 0, "done": 0,
                      "word": 0, "placed": 0, "failed": 0, "frame": 0}
        # per-scan glass state
        self._base: Image.Image | None = None       # RGBA downsampled scan
        self._overlay: Image.Image | None = None     # RGBA accumulator
        self._down = 1
        self._n_pieces = 0
        # server (port 0 => OS-assigned ephemeral; self.port reflects it)
        self.port = int(port)
        self._httpd = _serve(self)
        self.port = self._httpd.server_address[1]
        host = f"http://localhost:{self.port}/"
        print(f"  [diag] live view at {host} · frames -> "
              f"{self.out_dir}", flush=True)

    # ---- scan boundaries ------------------------------------------------
    @_safe
    def begin_scan(self, image_path, image: np.ndarray,
                   pieces: list, pds) -> None:
        """Set up the glass base for a new scan (fresh overlay) and render
        an initial frame (outlines land as each piece is processed)."""
        arr = np.asarray(image, np.float32)
        self._down = max(1, int(round(arr.shape[1] / GLASS_W)))
        d = self._down
        pv = arr[::d, ::d]
        lo, hi = float(pv.min()), float(pv.max())
        pv8 = np.clip((pv - lo) / (hi - lo + 1e-6) * 255, 0, 255
                      ).astype(np.uint8)
        self._base = Image.fromarray(pv8).convert("RGBA")
        self._overlay = Image.new("RGBA", self._base.size, (0, 0, 0, 0))
        self._n_pieces = len(pieces)
        self._meta.update({"scan": Path(image_path).name,
                           "pieces": len(pieces), "done": 0,
                           "word": 0, "placed": 0, "failed": 0})
        self._render(pds, active=None)

    @_safe
    def end_scan(self, image_path, pds) -> None:
        """Render the final frame of a scan — panel C (LDPC) has now
        advanced through the driver's end-of-scan decode_tiles."""
        self._render(pds, active=None)

    # ---- per piece ------------------------------------------------------
    @_safe
    def on_piece(self, piece, sid: str, route: str, angle_est: float,
                 placed, bits, core, pds) -> None:
        """One processed piece. route in {in_progress, word, placed, failed}.
        For placer pieces pass (placed, bits, core) so the sampled pilot
        sites can be drawn; pass None for the word/tiled/failed paths."""
        if route == "in_progress":
            # transient amber outline of the piece currently in flight;
            # not committed to the persistent overlay
            self._render(pds, active=(piece, angle_est, sid))
            return
        self._draw_piece(piece, sid, route, angle_est, placed, bits, core)
        key = "word" if route in ("word", "tiled") else (
            "placed" if route in ("placed", "refined") else "failed")
        self._meta[key] = self._meta.get(key, 0) + 1
        self._meta["done"] = self._meta.get("done", 0) + 1
        self._render(pds, active=None)

    # ---- rendering ------------------------------------------------------
    def _draw_piece(self, piece, sid, route, angle_est,
                    placed, bits, core) -> None:
        """Commit one piece's box + label + pilot-site dots to the overlay."""
        assert self._overlay is not None
        if piece.img_glass is None:      # geometry needs the glass crop
            return
        col = STATUS_COL.get(route, STATUS_COL["placed"])
        dr = ImageDraw.Draw(self._overlay)
        box = _tilted_box_glass(piece) / self._down
        dr.polygon([(x, y) for y, x in box], outline=col + (255,), width=2)
        # angle-estimate label at the box's top-left-most corner
        ci = int(np.argmin(box[:, 0] + box[:, 1]))
        ly, lx = box[ci]
        pidx = ddm.piece_index(sid, sid.split("/")[0])
        tag = pidx if pidx is not None else "?"
        _label(dr, lx, ly - 12, f"{tag} {angle_est:+.0f}°", col)
        # pilot sites the receiver sampled, in the piece's rotated frame
        if bits is not None:
            cells = _piece_site_cells(placed, bits, core, self.seed,
                                      self.spec)
            if cells.shape[0]:
                g = _cells_to_glass(cells, bits.shape, piece, angle_est)
                g = g / self._down
                H, W = self._overlay.size[1], self._overlay.size[0]
                ok = ((g[:, 0] >= 0) & (g[:, 0] < H)
                      & (g[:, 1] >= 0) & (g[:, 1] < W))
                pts = [(x, y) for y, x in g[ok]]
                if pts:
                    dr.point(pts, fill=SITE_COL + (255,))

    def _render(self, pds, active) -> None:
        glass = self._compose_glass(active)
        ref = _compose_reference(pds, REF_W)
        frame = _side_by_side(glass, ref, self._meta, self.title)
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        data = buf.getvalue()
        with self._lock:
            self._frame_no += 1
            self._meta["frame"] = self._frame_no
            self._latest_png = data
        (self.out_dir / f"frame_{self._frame_no:05d}.png").write_bytes(data)

    def _compose_glass(self, active) -> Image.Image:
        if self._base is None:
            return _placeholder_img("(waiting for scan)", (GLASS_W, 400))
        comp = Image.alpha_composite(self._base, self._overlay)
        if active is not None and active[0].img_glass is not None:
            piece, ang, _sid = active
            dr = ImageDraw.Draw(comp)
            box = _tilted_box_glass(piece) / self._down
            dr.polygon([(x, y) for y, x in box],
                       outline=STATUS_COL["in_progress"] + (255,), width=3)
        return comp.convert("RGB")

    def close(self, grace_s: float = 10.0) -> None:
        # Grace: decode_tiles runs and the FINAL frame renders only at
        # end_scan, ~10 ms before the process would exit — a browser
        # polling at 1 s almost never fetched it (measured 0/40, 2026-07-12),
        # so panel C looked frozen a frame behind. If a client has been
        # watching, keep serving until it has fetched the newest frame (or
        # grace_s elapses). No effect when nobody connected (tests, headless).
        import time as _time
        deadline = _time.monotonic() + grace_s
        while (self._ever_served and self._served_frame < self._frame_no
               and _time.monotonic() < deadline):
            _time.sleep(0.1)
        try:
            self._httpd.shutdown()
            self._httpd.server_close()   # release the listening socket
        except Exception:
            pass


# --------------------------------------------------------------------------
# reference-page compositing (reuses draw_decode_map panels B/C/D)
# --------------------------------------------------------------------------
def _compose_reference(pds, width: int) -> Image.Image:
    reasm = ddm.panel_reassembly(pds, width)
    ldpc, nstat = ddm.panel_ldpc(pds, width // 2 - 4)
    pilot, n_pilot, n_placed_tiles = ddm.panel_pilot(pds, width // 2 - 4)
    f = ddm._font(13)
    th = 20
    row2_h = max(ldpc.height, pilot.height)
    H = th + reasm.height + 8 + th + row2_h + 6
    canvas = Image.new("RGB", (width, H), (255, 255, 255))
    dr = ImageDraw.Draw(canvas)
    cert = nstat.get("certified", 0)
    dr.text((0, 2), "B · page reassembly (per-piece payload)",
            fill=(0, 0, 0), font=f)
    canvas.paste(reasm, (0, th))
    y2 = th + reasm.height + 8
    dr.text((0, y2), f"C · LDPC  cert {cert} / fail "
            f"{nstat.get('failed', 0)}", fill=(0, 0, 0), font=f)
    dr.text((width // 2 + 4, y2), f"D · pilot tiles  {n_pilot} words "
            f"+ {n_placed_tiles} placed", fill=(0, 0, 0), font=f)
    canvas.paste(ldpc, (0, y2 + th))
    canvas.paste(pilot, (width // 2 + 4, y2 + th))
    return canvas


def _side_by_side(glass: Image.Image, ref: Image.Image, meta: dict,
                  title: str) -> Image.Image:
    f22, f14 = ddm._font(24), ddm._font(15)
    pad, top = 24, 78
    body_h = max(glass.height, ref.height)
    W = pad * 3 + glass.width + ref.width
    canvas = Image.new("RGB", (W, top + body_h + pad), (250, 250, 250))
    dr = ImageDraw.Draw(canvas)
    dr.text((pad, 16), title, fill=(0, 0, 0), font=f22)
    dr.text((pad, 50),
            f"scan {meta['scan']} · piece {meta['done']}/"
            f"{meta['pieces']} · word {meta.get('word', 0)} "
            f"placed {meta.get('placed', 0)} failed "
            f"{meta.get('failed', 0)} · frame {meta['frame']}",
            fill=(90, 90, 90), font=f14)
    dr.text((pad, top - 18),
            "A · active glass  (green=word  blue=placed  red=failed "
            " amber=working · magenta=pilot sites)",
            fill=(0, 0, 0), font=ddm._font(13))
    canvas.paste(glass, (pad, top))
    canvas.paste(ref, (pad * 2 + glass.width, top))
    return canvas


# --------------------------------------------------------------------------
# small image helpers
# --------------------------------------------------------------------------
def _label(dr: ImageDraw.ImageDraw, x: float, y: float, text: str,
           col) -> None:
    f = ddm._font(13)
    try:
        b = dr.textbbox((x, y), text, font=f)
        dr.rectangle([b[0] - 2, b[1] - 1, b[2] + 2, b[3] + 1],
                     fill=LABEL_BG + (210,))
    except Exception:
        pass
    dr.text((x, y), text, fill=col + (255,), font=f)


def _placeholder_img(msg: str, size: tuple[int, int]) -> Image.Image:
    img = Image.new("RGB", size, (245, 245, 245))
    ImageDraw.Draw(img).text((16, size[1] // 2), msg, fill=(120, 120, 120),
                             font=ddm._font(16))
    return img


def _placeholder_png(title: str) -> bytes:
    buf = io.BytesIO()
    _placeholder_img(f"{title}\n(waiting for the first piece…)",
                     (900, 300)).save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------
# web view (stdlib http.server, background thread)
# --------------------------------------------------------------------------
_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>%(title)s</title><style>
 body{margin:0;background:#141414;color:#ddd;font-family:-apple-system,
 Segoe UI,Roboto,sans-serif;text-align:center}
 #f{max-width:100%%;height:auto;box-shadow:0 0 24px #000}
 #s{padding:6px;font-size:13px;color:#9a9a9a}</style></head>
<body><div id="s">connecting…</div>
<img id="f" src="/frame.png"><script>
let n=-1;
async function poll(){
 try{
  const r=await fetch('/status.json',{cache:'no-store'});
  const j=await r.json();
  document.getElementById('s').textContent=
   'scan '+j.scan+' · piece '+j.done+'/'+j.pieces+
   ' · word '+j.word+' placed '+j.placed+' failed '+j.failed+
   ' · frame '+j.frame;
  if(j.frame!==n){n=j.frame;
   document.getElementById('f').src='/frame.png?t='+Date.now();}
 }catch(e){document.getElementById('s').textContent='(decoder idle)';}
 setTimeout(poll,1000);
}
poll();
</script></body></html>"""


def _serve(viewer: "DiagViewer") -> ThreadingHTTPServer:
    import json

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):        # quiet
            pass

        def _send(self, code, ctype, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
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
                html = (_PAGE % {"title": viewer.title}).encode("utf-8")
                self._send(200, "text/html; charset=utf-8", html)
            elif path == "/frame.png":
                with viewer._lock:
                    png = viewer._latest_png
                    viewer._served_frame = viewer._frame_no
                    viewer._ever_served = True
                self._send(200, "image/png", png)
            elif path == "/status.json":
                with viewer._lock:
                    body = json.dumps(dict(viewer._meta)).encode("utf-8")
                self._send(200, "application/json", body)
            else:
                self._send(404, "text/plain", b"not found")

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", viewer.port), Handler)
    except OSError:                       # port taken: never block a decode
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
