from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Sequence
from urllib.parse import urlparse

from . import model as _model
from . import panes as _panes
from . import readout as _readout

_PANE_NAMES = ("capture", "page", "payload", "pose", "field")
_FINISH_GRACE_S = 6.0
_FINISH_STEP_S = 0.1

_PAGE_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>holo3 diag</title>
<style>
body{font-family:ui-monospace,Menlo,monospace;background:#fff;color:#222;
    margin:12px;font-size:13px}
#head{font-size:15px;font-weight:bold}
#verified{display:none;background:#1a7f37;color:#fff;padding:4px 8px;
    margin:4px 0;font-weight:bold}
pre{margin:6px 0;line-height:1.5}
#now,#last{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#activity{color:#666;margin:2px 0}
#legend{color:#666;font-size:12px;margin-top:6px}
.sel{margin:2px 0}
.sel a{color:#0757ba;margin-right:8px;cursor:pointer}
.sel a.on{font-weight:bold;text-decoration:underline}
#grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;
    margin-top:8px}
#grid img{width:100%;border:1px solid #ccc;display:block}
#img-pose{grid-column:1/3}
#img-field{grid-column:3/5;display:none}
table{border-collapse:collapse;font-size:12px;margin-bottom:4px}
th,td{padding:1px 10px 1px 0;text-align:right;font-weight:normal}
th:first-child,td:first-child{text-align:left}
.cpubar{height:3px;background:#7aa7d6}
.track{display:inline-block;width:90px;height:8px;background:#e6e6e6;
    vertical-align:middle;margin-right:6px}
.fill{height:8px;background:#7aa7d6}
.fill.green{background:#1a7f37}
#spark{border:1px solid #ddd;margin-top:8px;display:block}
</style></head>
<body>
<div id="head">holo3 diag · <span id="fmt">…</span></div>
<div id="verified"></div>
<pre id="rows">waiting for /status</pre>
<div id="now"></div>
<div id="last"></div>
<div id="activity"></div>
<div class="sel" id="selcap"></div>
<div class="sel" id="selpage"></div>
<div id="grid">
<img id="img-capture" alt="capture">
<img id="img-page" alt="page">
<img id="img-payload" alt="payload">
<div><div id="sched"></div><div id="close"></div></div>
<img id="img-pose" alt="pose">
<img id="img-field" alt="field">
</div>
<div id="legend">B: number = word sites seen (0..100), green border =
word decoded here · C: number = decode attempts across all streams,
shown while uncertified · FIELD: appears once a plane-field fit lands on
the selected page (arrow = per-plane registration delta, exaggerated;
black = blind spot, dark green = certified)</div>
<canvas id="spark" width="640" height="48"></canvas>
<script>
var revision = -1;
var paneRevs = {};
var failCount = 0;
var sawStatus = false;
var lastMove = Date.now();
var selCapture = null;
var selPage = null;
var lastStatus = null;
var certHist = [];
function el(id) { return document.getElementById(id); }
function paneUrl(pane, sel) {
    return "/pane/" + pane + "-" + sel + ".png?rev=" + revision;
}
function swap(id, url) {
    var im = new Image();
    im.onload = function () { el(id).src = url; };
    im.src = url;
}
function refreshCapture() {
    if (selCapture !== null) {
        swap("img-capture", paneUrl("capture", selCapture));
    }
}
function refreshPages() {
    if (selPage === null) { return; }
    swap("img-page", paneUrl("page", selPage));
    swap("img-payload", paneUrl("payload", selPage));
    swap("img-pose", paneUrl("pose", selPage));
    refreshField();
}
function fieldPages() {
    var have = (lastStatus && lastStatus.panes) || {};
    return have.field || [];
}
function refreshField() {
    var img = el("img-field");
    if (selPage === null || fieldPages().indexOf(selPage) < 0) {
        img.style.display = "none";
        return;
    }
    img.style.display = "block";
    swap("img-field", paneUrl("field", selPage));
}
function buildSel(target, label, entries, current, pick) {
    var box = el(target);
    box.textContent = "";
    box.appendChild(document.createTextNode(label + " "));
    entries.forEach(function (entry) {
        var link = document.createElement("a");
        link.textContent = entry.text;
        if (entry.value === current) { link.className = "on"; }
        link.onclick = function () { pick(entry.value); };
        box.appendChild(link);
    });
}
function pickCapture(value) {
    selCapture = value;
    renderSelectors();
    refreshCapture();
}
function pickPage(value) {
    selPage = value;
    renderSelectors();
    refreshPages();
}
function renderSelectors() {
    if (!lastStatus) { return; }
    var caps = (lastStatus.captures || []).map(function (c) {
        return {text: c.ordinal + "." + c.sha12, value: c.ordinal};
    });
    buildSel("selcap", "A:", caps, selCapture, pickCapture);
    var panes = lastStatus.panes || {};
    var pages = (panes.page || []).map(function (p) {
        return {text: String(p), value: p};
    });
    buildSel("selpage", "pages:", pages, selPage, pickPage);
}
function renderSched(sched) {
    var box = el("sched");
    box.textContent = "";
    if (!sched || !sched.plugins) { return; }
    var table = document.createElement("table");
    var head = table.insertRow();
    ["plugin", "queued", "inflight", "jobs", "cpu_s", "certs"]
        .forEach(function (name) {
            var cell = document.createElement("th");
            cell.textContent = name;
            head.appendChild(cell);
        });
    var maxCpu = 0;
    sched.plugins.forEach(function (p) {
        if (p.cpu_s > maxCpu) { maxCpu = p.cpu_s; }
    });
    sched.plugins.forEach(function (p) {
        var row = table.insertRow();
        [p.plugin, p.queued, p.inflight, p.jobs,
         Number(p.cpu_s).toFixed(1), p.certificates]
            .forEach(function (value) {
                row.insertCell().textContent = String(value);
            });
        var barRow = table.insertRow();
        var cell = barRow.insertCell();
        cell.colSpan = 6;
        var bar = document.createElement("div");
        bar.className = "cpubar";
        bar.style.width = (maxCpu > 0 ? 100 * p.cpu_s / maxCpu : 0) + "%";
        cell.appendChild(bar);
    });
    box.appendChild(table);
    var line = document.createElement("div");
    if (!sched.available) {
        line.textContent =
            "attempts, stale skips, retired, wakes unavailable "
            + "before the first merge";
        box.appendChild(line);
        return;
    }
    var hist = (sched.attempts_hist || []).map(function (h) {
        return h[0] + ":" + h[1];
    }).join(" ");
    var jobs = (sched.plugins || []).reduce(function (sum, p) {
        return sum + (p.jobs || 0);
    }, 0);
    var wakesPart = jobs > 0
        ? "wakes/job " + (sched.wakes / jobs).toFixed(1)
        : "wakes " + sched.wakes;
    line.textContent = "attempts " + (hist || "none")
        + " · stale skips " + sched.stale_skips
        + " · retired " + sched.retired
        + " · " + wakesPart
        + " · consult cpu " + Number(sched.consult_cpu_s).toFixed(1) + "s";
    box.appendChild(line);
    if (sched.churn) {
        var churn = document.createElement("div");
        churn.textContent = "churn " + sched.churn;
        box.appendChild(churn);
    }
}
function renderClose(close) {
    var box = el("close");
    box.textContent = "";
    if (!close) { return; }
    var head = document.createElement("div");
    if (!close.consulted) {
        head.textContent = "close not consulted"
            + " · certified " + close.certified;
        box.appendChild(head);
        var wait = document.createElement("div");
        wait.textContent =
            "K, metadata, blocks unavailable before the first close consult";
        box.appendChild(wait);
        return;
    }
    var kPart;
    if (close.counting) {
        kPart = (close.k_total === null)
            ? "symbols unavailable before metadata"
            : "symbols " + close.symbols_used + "/" + close.k_total;
    } else if (close.k_total === null && close.symbols_used === 0) {
        kPart = "K unavailable before solve";
    } else {
        kPart = "K " + close.symbols_used + "/"
            + (close.k_total === null ? "-" : close.k_total);
    }
    head.textContent = "close " + close.status
        + (close.counting ? " (counting)" : "")
        + " · certified " + close.certified + " · " + kPart;
    box.appendChild(head);
    var meta = document.createElement("div");
    meta.textContent = "metadata rank " + close.metadata_rank
        + "/24 · equations " + close.metadata_n_unique + "/48";
    box.appendChild(meta);
    if (close.counting && (close.blocks || []).length) {
        var short = 0;
        var shortBlocks = 0;
        close.blocks.forEach(function (b) {
            if (b.have < b.needed) {
                short += b.needed - b.have;
                shortBlocks += 1;
            }
        });
        var gap = document.createElement("div");
        gap.textContent = shortBlocks
            ? short + " symbols short across " + shortBlocks + " block"
                + (shortBlocks === 1 ? "" : "s")
            : "all blocks count-ready";
        box.appendChild(gap);
    }
    if (!(close.blocks || []).length) {
        var none = document.createElement("div");
        none.textContent = "blocks unavailable before metadata";
        box.appendChild(none);
        return;
    }
    (close.blocks || []).forEach(function (b) {
        var row = document.createElement("div");
        var track = document.createElement("div");
        track.className = "track";
        var fill = document.createElement("div");
        fill.className = "fill" + (b.solved ? " green" : "");
        var frac = b.needed > 0 ? Math.min(1, b.have / b.needed) : 1;
        fill.style.width = Math.round(100 * frac) + "%";
        track.appendChild(fill);
        row.appendChild(track);
        var label = (b.stream_id === null ? "" : b.stream_id)
            + "#" + b.block + " " + b.have + "/" + b.needed
            + (b.solved ? " solved"
                : (b.short === 0 ? " ready" : " short " + b.short))
            + (b.rank === null || b.solved ? "" : " rank " + b.rank)
            + (b.n_groups > 1
                ? " groups " + (b.n_groups - b.groups_open) + "/" + b.n_groups
                : "");
        row.appendChild(document.createTextNode(label));
        box.appendChild(row);
    });
}
function drawSpark() {
    if (certHist.length > 1200) {
        certHist = certHist.filter(function (_v, i) { return i % 2 === 0; });
    }
    var canvas = el("spark");
    var ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (certHist.length < 2) { return; }
    var max = Math.max.apply(null, certHist);
    if (max < 1) { max = 1; }
    ctx.strokeStyle = "#1a7f37";
    ctx.beginPath();
    certHist.forEach(function (value, i) {
        var x = 1 + i * (canvas.width - 62) / (certHist.length - 1);
        var y = canvas.height - 1 - (canvas.height - 2) * value / max;
        if (i === 0) { ctx.moveTo(x, y); } else { ctx.lineTo(x, y); }
    });
    ctx.stroke();
    ctx.fillStyle = "#1a7f37";
    ctx.font = "11px ui-monospace";
    ctx.fillText(String(certHist[certHist.length - 1]) + " certified",
                 canvas.width - 58, 12);
}
function render(status) {
    lastStatus = status;
    var rows = status.rows || [];
    el("fmt").textContent = (rows[0] || "").split(/\s+/)[1] || "…";
    if (status.close && status.close.verified) {
        var verified = status.close.verified;
        el("verified").style.display = "block";
        el("verified").textContent = "VERIFIED · "
            + verified.n_bytes + " bytes · sha " + verified.sha16;
    }
    el("rows").textContent = rows.join("\n");
    el("now").textContent = (status.now && status.now.length)
        ? ("now  " + status.now.join(" · "))
        : "now  idle — frontier empty";
    el("last").textContent = "last " + (status.last || "—");
    var panes = status.panes || {};
    if (selCapture === null && (panes.capture || []).length) {
        selCapture = panes.capture[0];
    }
    if (selPage === null && (panes.page || []).length) {
        selPage = panes.page[0];
    }
    renderSelectors();
    renderSched(status.scheduler);
    renderClose(status.close);
    if (status.close) {
        certHist.push(status.close.certified || 0);
        drawSpark();
    }
    if (status.revision !== revision) {
        revision = status.revision;
        lastMove = Date.now();
    }
    var revs = status.pane_revs || {};
    if (revs.capture !== paneRevs.capture) { refreshCapture(); }
    if (revs.page !== paneRevs.page && selPage !== null) {
        swap("img-page", paneUrl("page", selPage));
    }
    if (revs.payload !== paneRevs.payload && selPage !== null) {
        swap("img-payload", paneUrl("payload", selPage));
    }
    if (revs.pose !== paneRevs.pose && selPage !== null) {
        swap("img-pose", paneUrl("pose", selPage));
    }
    if (revs.field !== paneRevs.field) { refreshField(); }
    paneRevs = revs;
}
var stopped = false;
function tick() {
    var ago = Math.max(0, Math.round((Date.now() - lastMove) / 1000));
    var extra = (lastStatus && lastStatus.fold_errors)
        ? " · fold errors " + lastStatus.fold_errors : "";
    el("activity").textContent = (stopped ? "run ended · " : "")
        + "last activity " + ago + "s ago" + extra;
    if (stopped) { return; }
    fetch("/status").then(function (response) {
        return response.json();
    }).then(function (status) {
        sawStatus = true;
        failCount = 0;
        if (status && status.error === undefined) { render(status); }
    }).catch(function () {
        failCount += 1;
        if (failCount >= 3 && sawStatus) { stopped = true; }
    });
}
setInterval(tick, 1000);
tick();
</script>
</body></html>
"""
_PAGE_BYTES = _PAGE_HTML.encode("utf-8")


class FrameCache:

    def __init__(self, events: Sequence[object],
                 board: object | None = None) -> None:
        self._events = events
        self._board = board
        self._lock = threading.Lock()
        self._model = _model.empty()
        self._revision = -1
        self._panes: dict[tuple[str, int, int], bytes] = {}
        self._pinned = False
        self.any_request = False
        self.last_status_revision = -1
        self.panes_wanted: set[tuple[str, int]] = set()
        self.panes_after_pin: set[tuple[str, int]] = set()

    def _inject_board(self) -> None:
        value = None if self._board is None else self._board.value
        if value is not None:
            self._model.engine_stat = value

    def status(self) -> dict:
        with self._lock:
            if not self._pinned:
                self._model = _model.fold(self._model, self._events)
                self._inject_board()
                self._revision = self._model.cursor
            return _readout.status(self._model)

    def pane(self, pane: str, selector: int) -> bytes | None:
        with self._lock:
            if self._pinned:
                png = self._panes.get((pane, selector, -1))
                if png is not None:
                    self.panes_after_pin.add((pane, selector))
                return png
            pane_rev = self._model.pane_revs.get(pane, 0)
            key = (pane, selector, pane_rev)
            cached = self._panes.get(key)
            if cached is None:
                cached = _panes.render_pane(self._model, pane, selector)
                if cached is not None:
                    for stale in [k for k in self._panes
                                  if k[0] == pane and k[1] == selector]:
                        del self._panes[stale]
                    self._panes[key] = cached
            if cached is not None:
                self.panes_wanted.add((pane, selector))
            return cached

    def pin(self) -> dict[tuple[str, int], bytes]:
        with self._lock:
            self._model = _model.fold(self._model, self._events)
            self._inject_board()
            self._revision = self._model.cursor
            pinned = _panes.pin_panes(self._model)
            self._panes = {(pane, selector, -1): png
                           for (pane, selector), png in pinned.items()}
            self._pinned = True
            return pinned

    @property
    def revision(self) -> int:
        return self._revision

    def model(self) -> _model.DiagModel:
        with self._lock:
            if not self._pinned:
                self._model = _model.fold(self._model, self._events)
            return self._model


class _Handler(BaseHTTPRequestHandler):
    cache: FrameCache = None
    protocol_version = "HTTP/1.0"

    def do_GET(self) -> None:
        self.cache.any_request = True
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._respond(200, _PAGE_BYTES, "text/html; charset=utf-8")
            return
        if path == "/status":
            self._status()
            return
        if path.startswith("/pane/") and path.endswith(".png"):
            self._pane(path[len("/pane/"):-len(".png")])
            return
        self._respond(404, b'{"error": "not found"}')

    def _status(self) -> None:
        try:
            payload = self.cache.status()
        except Exception as exc:
            payload = {"error": f"{type(exc).__name__}: {exc}"}
        self._respond(200, json.dumps(payload).encode("utf-8"))
        revision = payload.get("revision")
        if isinstance(revision, int):
            self.cache.last_status_revision = revision

    def _pane(self, name: str) -> None:
        pane, dash, raw_selector = name.rpartition("-")
        if not dash or pane not in _PANE_NAMES:
            self._respond(
                404,
                b"pane path names no pane: "
                b"/pane/<capture|page|payload|pose|field>-<selector>.png",
                "text/plain")
            return
        try:
            selector = int(raw_selector)
        except ValueError:
            message = f"pane {pane} selector must be an integer, " \
                      f"got {raw_selector!r}"
            self._respond(404, message.encode("utf-8"), "text/plain")
            return
        try:
            png = self.cache.pane(pane, selector)
        except Exception as exc:
            message = f"pane failed: {type(exc).__name__}: {exc}"
            self._respond(500, message.encode("utf-8"), "text/plain")
            return
        if png is None:
            message = f"pane {pane} has no selector {selector}"
            self._respond(404, message.encode("utf-8"), "text/plain")
            return
        self._respond(200, png, "image/png")

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
            pass

    def log_message(self, *args: object) -> None:
        pass


class DiagServer:

    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread,
                 cache: FrameCache) -> None:
        self._server = server
        self._thread = thread
        self._cache = cache

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def home(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def pin(self) -> dict[tuple[str, int], bytes]:
        return self._cache.pin()

    def model(self) -> _model.DiagModel:
        return self._cache.model()

    def finish(self) -> None:
        try:
            self._cache.pin()
            if self._cache.any_request:
                final = self._cache.revision
                wanted = set(self._cache.panes_wanted)
                deadline = time.monotonic() + _FINISH_GRACE_S
                while time.monotonic() < deadline:
                    if (self._cache.last_status_revision == final
                            and self._cache.panes_after_pin >= wanted):
                        break
                    time.sleep(_FINISH_STEP_S)
        except Exception:
            pass
        self.stop()

    def stop(self) -> None:
        try:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=5.0)
        except Exception:
            pass


def serve(port: int, events: Sequence[object],
          board: object | None = None) -> DiagServer | None:
    try:
        cache = FrameCache(events, board)
        handler = type("_BoundHandler", (_Handler,), {"cache": cache})
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever,
                                  name="holo3-diag", daemon=True)
        thread.start()
        return DiagServer(httpd, thread, cache)
    except OSError as exc:
        print(f"diag: port {port} unavailable ({exc}); continuing "
              "without the viewer", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"diag: failed to start ({exc}); continuing without "
              "the viewer", file=sys.stderr)
        return None
