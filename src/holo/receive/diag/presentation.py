"""Presentation surface of the live diag view: palette, shell, glyphs.

RECEIVE-DESIGN §10.3.1 (fixed composition and pane headings), §10.3.4
(semantic palette and marks).  Nothing here reads receiver state — these are
the colors, the browser shell, and the drawing primitives the view paints
with, kept apart from the event ingestion and transport in
:mod:`~holo.receive.diag.viewer`.
"""
from __future__ import annotations

import io
import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont


# Operator palette (primaries-on-white, approved 2026-07-31; RECEIVE-DESIGN
# v0.27 §10.3.4 rendering rulings supersede the 2026-07-28 dark view).
_BG = (250, 250, 250)
_TEXT = (34, 34, 34)
_GREEN = (0, 158, 62)         # matching / certified
_ORANGE = (238, 106, 0)       # refused / failed
_BLUE = (0, 94, 224)          # partial / evidence (unseen = background)
_PURPLE = (128, 62, 208)      # transient (dashed)
_CYAN = (0, 168, 200)         # active
_PENDING_OUTLINE = (178, 178, 178)   # planned, not yet attempted window
# v0.33 parked-for-mop-up chip (durable "not yet attempted" — waiting on
# the M-level).  Amber per the §10.3.4 table (insufficient/not attempted);
# a SOLID outline, distinct from the transient purple-dashed in-region
# parked state: this is durable committed state, not work in flight.
_PARKED_MOPUP = (210, 130, 35)


_HUES = (
    (96, 165, 250), (52, 211, 153), (251, 191, 36), (248, 113, 113),
    (167, 139, 250), (45, 212, 191), (251, 146, 60), (232, 121, 249),
    (163, 230, 53), (125, 211, 252), (253, 164, 175), (196, 181, 253),
)

# Word erasure budget: 2e+f <= 26, so an error-free word still needs >= 74
# of its 100 sites.  Display-only classification threshold.
_WORD_ERASURE_BUDGET = 26

_STREAM_HUE = {"main": _TEXT, "C": (60, 200, 255), "M": (255, 80, 200),
               "Y": (240, 220, 60)}

# E022/E023c two-tone tile chips (user declaration 2026-07-31, v0.32): every
# pane-C/D tile is a soft fill paired with a darker same-hue outline, under
# the unchanged §10.3.4 semantic table.  E023's own attempted-failed red is
# deliberately NOT ported: deep red stays reserved for contradiction.
_CHIP_GREEN = ((118, 196, 130), (25, 120, 55))       # solved / certified
# v0.43 lighter green: placement-addressed tile whose final word PASSED the
# §5.4 known-position evaluation (read-and-validated) — same hue family as
# _CHIP_GREEN, lightened the way _CHIP_REACH lightens _CHIP_BLUE.
_CHIP_GREEN_SOFT = ((192, 228, 198), (140, 196, 152))
_CHIP_BLUE = ((120, 175, 225), (30, 105, 175))       # partial / evidence
_CHIP_REACH = ((198, 220, 246), (152, 186, 224))     # reachable only
_CHIP_AMBER = ((250, 198, 110), (210, 130, 35))      # insufficient / floor
# v0.45 durable-seeded pane-C state: tile addressed by a COMMITTED placement
# from a prior invocation/barrier, word evidence not retained in state —
# amber family (observed/addressed, not validated), lightened exactly the
# way _CHIP_REACH lightens _CHIP_BLUE for the weaker claim of the family.
_CHIP_AMBER_SOFT = ((252, 226, 178), (228, 176, 104))
_CHIP_ORANGE = ((245, 152, 96), (196, 88, 16))       # refused / failed
_CHIP_RED = ((228, 118, 124), (170, 0, 34))          # contradiction
_CHIP_UNSEEN = ((238, 238, 238), (216, 216, 216))    # untouched grid cell
_CHIP_NEUTRAL = ((233, 233, 233), (209, 209, 209))   # unseen sibling stream
_CHIP_TEXT = (20, 20, 20)                            # one dark count color

# Payload-tile display states (monotone; certified never downgrades).
(_TILE_STATE_UNSEEN, _TILE_STATE_EVIDENCE, _TILE_STATE_FLOOR,
 _TILE_STATE_FAILED, _TILE_STATE_CERTIFIED) = range(5)
_TILE_CHIPS = {_TILE_STATE_UNSEEN: _CHIP_UNSEEN,
               _TILE_STATE_EVIDENCE: _CHIP_REACH,
               _TILE_STATE_FLOOR: _CHIP_AMBER,
               _TILE_STATE_FAILED: _CHIP_ORANGE,
               _TILE_STATE_CERTIFIED: _CHIP_GREEN}

# Word (BCH) display states; conflict always wins.  v0.43 tri-state on
# address authority (declared operator-presentation ruling): SOLVED = the
# word decoder itself produced the tile's address (the seeder word route,
# full green); VALIDATED = placement-addressed tile whose final word PASSED
# the §5.4 known-position evaluation (lighter green).  SOLVED outranks every
# non-conflict state; deep red stays contradiction-only (v0.32) and is
# never overwritten.  SEEDED (v0.45) is the durable-record resume seed:
# committed-placement tile cover with no retained word evidence — it ranks
# BELOW every live evaluation outcome so this invocation's re-reads
# (validated/refused/floor/solved) always paint over it, and live partial
# observation (EVIDENCE, setdefault-only) never downgrades it.
(_WORD_EVIDENCE, _WORD_SEEDED, _WORD_VALIDATED, _WORD_FAILED, _WORD_FLOOR,
 _WORD_CONFLICT, _WORD_SOLVED) = range(1, 8)
_WORD_CHIPS = {_WORD_EVIDENCE: _CHIP_BLUE, _WORD_SEEDED: _CHIP_AMBER_SOFT,
               _WORD_VALIDATED: _CHIP_GREEN_SOFT,
               _WORD_SOLVED: _CHIP_GREEN,
               _WORD_FAILED: _CHIP_ORANGE, _WORD_FLOOR: _CHIP_AMBER,
               _WORD_CONFLICT: _CHIP_RED}

_REGION_OUTLINE = {"surveyed": _BLUE, "active": _CYAN, "accepted": _GREEN,
                   "redundant": _GREEN, "unresolved": _ORANGE,
                   "pose_refused": _ORANGE,
                   # v0.33 D19: a phase-1 region with parked windows is NOT
                   # unresolved (that word stays bound to
                   # cold-refused-terminal) — it is waiting on its M-level.
                   "parked": _PARKED_MOPUP}

# §10.3.1 pane headings, burned into the composed frame's title bar. Long
# stage names, capture SHAs, and lane identities stay out of the image.
_PANE_TITLES = ("A ACQUIRED", "B PLACED", "C ADDRESS", "D PAYLOAD")
_TITLE_FILL = (238, 240, 243)
_TITLE_RULE = (176, 181, 186)
_TITLE_TEXT = (35, 40, 45)

# W5 field pane (PLANE-FIELDS.md §6.2, user design): a BOTTOM BAND, not a
# fifth same-width pane, so the 4*width frame invariant stays untouched.
# Arrow colours reuse ``_STREAM_HUE``'s existing C/M/Y palette rather than
# inventing a parallel one -- the same cyan/magenta/gold the rest of the
# view already uses for these streams.
_FIELD_TITLE = "E FIELD"
_FIELD_OUTLINE = (214, 214, 214)   # faint page outline
_FIELD_DIM = (150, 150, 150)       # no-data title colour
_FIELD_BODY_BG = (118, 118, 118)   # band plot base: mid-grey (user, 2026-08-21
                                   # — amber shading covered whole sheets and
                                   # read as background; gold arrows drowned)
_FIELD_HOLE = (0, 0, 0)            # NO field data AND still uncertified:
                                   # black — the actionable blind spot
_FIELD_DONE = (26, 62, 44)         # NO field data because the tile is
                                   # fully certified: dark green. The pool
                                   # law gives certified-complete windows
                                   # no anchors and the probe budget is
                                   # finite, so a fully decoded area is
                                   # UNCOVERED too — and must not read as
                                   # a blind spot (user, 2026-08-21)
_FIELD_SHADE = (94, 94, 94)        # >=0.25-dot block shading: darker grey,
                                   # quiet — the arrows carry the message
_FIELD_STAGGER_PX = 3              # per-plane arrow-origin offset
_PLANES = ("C", "M", "Y")          # plane_index 0/1/2, THE PINNED CONTRACT

_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>holo receive</title><style>
body{margin:0;background:#fff;color:#222;
font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:13px}
#rows{white-space:pre;font-family:ui-monospace,Menlo,monospace;
padding:8px 12px;line-height:1.45;height:8.7em;overflow:hidden;
border-bottom:1px solid #ddd;background:#fafafa}
#pages{padding:4px 12px;color:#666}
#pages a{color:#06c; text-decoration:none;margin-right:9px;cursor:pointer}
#pages a.sel{color:#000;font-weight:600}
#view{padding:10px 12px}
/* The frame's proportions are the PNG's own: A-D together are the
   A4 page, and no CSS ratio may restate them.  A declared
   aspect-ratio here stretches the image (object-fit: fill) the
   moment it disagrees with the composed frame -- which is what
   the W5 band introduced and what distorted A-D (2026-08-21). */
#f{display:block;width:100%%;height:auto;
background:#fff;box-shadow:0 0 10px #bbb}
#legs{display:grid;grid-template-columns:repeat(5,1fr);gap:0;
color:#555;font-size:11px;padding:5px 0}
#legs div{padding:0 12px 0 2px}
</style></head><body>
<div id="rows">connecting…</div><div id="pages"></div>
<div id="view"><img id="f"><div id="legs">
<div><b>scan regions</b>: capture underlay · tint = piece · boundary and box:
blue surveyed · cyan active · green placed · orange refused · windows:
gray pending · purple dashed parked · thin cyan rest slots ·
heavy cyan cold sweep · amber = parked for mop-up (digit = plan level)</div>
<div><b>page-space placements</b>: hue = piece · solid = accepted ·
violet dashed = provisional · white = unreached</div>
<div><b>BCH word sites</b> per tile: number = observed sites ·
green word-route solved · light green placement-read + validated ·
blue evidence · amber below budget ·
pale amber committed-addressed (prior work, no count) · orange refused ·
red conflict (double border) · pale gray untouched</div>
<div><b>payload tiles</b> (LDPC), stream segments C/M/Y left to right:
green certified · blue reachable/evidence · amber below floor ·
orange failed · gray unseen · purple dashed = retry in flight</div>
<div><b>plane fields</b> (bottom band, one block per tile): mid gray = field
measured here · darker gray = some plane's delta reaches 0.25 dot ·
BLACK = no field evidence AND still uncertified (the blind spot) ·
DARK GREEN = every stream certified, nothing left to measure ·
arrows = per-plane C/M/Y delta, staggered so they never overlap,
drawn at the exaggeration printed in the band title</div>
</div></div><script>
let rev=-1,page=null;
function pick(p){page=p;rev=-1;}
// §10.3.1 double buffering: the decoded frame stays visible until its
// replacement has loaded, then the node is exchanged.
function swap(url){const pre=new Image();
 pre.onload=function(){document.getElementById('f').src=pre.src;};
 pre.src=url;}
async function poll(){try{
 const r=await fetch('status.json',{cache:'no-store'});const j=await r.json();
 document.getElementById('rows').textContent=j.rows.join('\\n');
 if(page===null||!j.pages.includes(page))page=j.page_default;
 document.getElementById('pages').innerHTML=j.pages.map(p=>
  '<a onclick="pick('+p+')" class="'+(p===page?'sel':'')+'">page '+p+
  '</a>').join('')||'&nbsp;';
 // Each page carries its own presentation revision; ?frame= is the
 // current-presentation cache key, never a historical-frame API.
 const now=(j.page_frames||{})[String(page)];
 if(now===undefined){
  // v0.32 wanted-page contract: a never-composed page materializes only
  // after the browser requests it, so issue the teaching fetch; the 404
  // is expected until the next render composes the page.
  fetch('frame.png?page='+page,{cache:'no-store'}).catch(function(){});
 }else if(now!==rev){rev=now;
  swap('frame.png?page='+page+'&frame='+rev);}
 }catch(e){}
 setTimeout(poll,1000)}poll();
</script></body></html>"""


@lru_cache(maxsize=None)
def _font(size: int):
    """The E022/E023c panel font: DejaVu/Arial truetype, else the default."""
    for name in ("DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


@lru_cache(maxsize=4096)
def _glyph(size: int, text: str):
    """Pre-rendered FreeType mask + offset; identical to ``draw.text``."""
    return _font(size).getmask2(text)


def _blit_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
               fill: tuple[int, int, int], size: int) -> None:
    """Bit-exact ``draw.text`` via the cached mask (measured 30x cheaper)."""
    mask, offset = _glyph(size, text)
    ink = draw._getink(fill)[0]
    if ink is not None:
        draw.draw.draw_bitmap(
            (xy[0] + offset[0], xy[1] + offset[1]), mask, ink)


def _mask_edge(mask: np.ndarray) -> np.ndarray:
    """4-neighbour boundary of a boolean mask (holes stay outlined)."""
    padded = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), bool)
    padded[1:-1, 1:-1] = mask
    inner = (padded[1:-1, 1:-1] & padded[:-2, 1:-1] & padded[2:, 1:-1]
             & padded[1:-1, :-2] & padded[1:-1, 2:])
    return mask & ~inner


def _dashed_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                 color: tuple[int, int, int], dash: int = 4) -> None:
    x0, y0, x1, y1 = box
    for x in range(x0, x1, 2 * dash):
        draw.line((x, y0, min(x + dash, x1), y0), fill=color)
        draw.line((x, y1, min(x + dash, x1), y1), fill=color)
    for y in range(y0, y1, 2 * dash):
        draw.line((x0, y, x0, min(y + dash, y1)), fill=color)
        draw.line((x1, y, x1, min(y + dash, y1)), fill=color)


def _draw_arrow(draw: ImageDraw.ImageDraw, origin: tuple[float, float],
                end: tuple[float, float],
                color: tuple[int, int, int]) -> None:
    """One W5 quiver arrow: a shaft plus a short two-stroke head."""
    x0, y0 = origin
    x1, y1 = end
    draw.line((x0, y0, x1, y1), fill=color)
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1.0:
        return
    ux, uy = dx / length, dy / length
    head = min(4.0, length)
    px, py = -uy, ux
    left = (x1 - ux * head + px * head * 0.5, y1 - uy * head + py * head * 0.5)
    right = (x1 - ux * head - px * head * 0.5, y1 - uy * head - py * head * 0.5)
    draw.line((x1, y1, left[0], left[1]), fill=color)
    draw.line((x1, y1, right[0], right[1]), fill=color)


class RegionView:
    """Pane-A footprint of one surveyed region at pane resolution."""

    __slots__ = ("mask", "box", "hue", "state")

    def __init__(self, mask: np.ndarray, box: tuple[int, int, int, int],
                 hue: int) -> None:
        self.mask = mask          # bool (h, w) at pane scale
        self.box = box            # x0, y0, x1, y1 pane px
        self.hue = hue
        self.state = "surveyed"


class PaneRenderer:
    """Pane geometry and pixels for one format's live view.

    Owns nothing the receiver produced: every render takes the view's
    accumulated model as arguments and returns a raster.  Splitting it from
    :class:`~holo.receive.diag.viewer.LiveView` keeps event ingestion and
    drawing independently readable, and makes the pane geometry (which is a
    pure function of the registered page and tile grids) testable alone.
    """

    def __init__(self, cells_yx: tuple[int, int], tiles_yx: tuple[int, int],
                 panel_width: int) -> None:
        self.cells_yx = cells_yx
        self.tiles_yx = tiles_yx
        self.width = int(panel_width)
        cy, cx = cells_yx
        self.height = max(1, round(self.width * cy / cx))
        # Composed-frame furniture: one title bar per pane (§10.3.1).
        self.title_size = max(9, min(15, round(self.width * 0.032)))
        self.title_height = max(18, self.title_size + 9)
        # W5 field band body height (its own title bar reuses title_height):
        # a fraction of one pane's height, not a fifth equal pane -- the
        # user design is a BOTTOM BAND, so it stays visually subordinate to
        # the four panes it sits beneath.
        self.field_body_height = max(120, round(self.height * 0.64))

    # -- geometry ------------------------------------------------------
    def clip_box(self, box: tuple[int, int, int, int]
                 ) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = box
        return (max(0, min(x0, self.width - 1)),
                max(0, min(y0, self.height - 1)),
                max(1, min(x1, self.width - 1)),
                max(1, min(y1, self.height - 1)))

    def tile_box(self, ty: int, tx: int) -> tuple[int, int, int, int]:
        tile_y, tile_x = self.tiles_yx
        x0 = round(tx * self.width / tile_x)
        y0 = round(ty * self.height / tile_y)
        x1 = round((tx + 1) * self.width / tile_x)
        y1 = round((ty + 1) * self.height / tile_y)
        return x0, y0, max(x0 + 1, x1 - 1), max(y0 + 1, y1 - 1)

    def segment_box(self, box: tuple[int, int, int, int], index: int,
                    n_streams: int) -> tuple[int, int, int, int]:
        """One stream's slice of an INCLUSIVE tile box.

        ``box`` already ends on the tile's last pixel, so the span is
        ``x1 - x0 + 1``; subtracting another pixel from the final segment
        (the pre-v0.32 bug) left one background column per tile column —
        the operator's "white stripes", measured at 3.2% of the pane.
        """
        x0, y0, x1, y1 = box
        span = x1 - x0 + 1
        sx0 = x0 + round(index * span / n_streams)
        sx1 = x0 + round((index + 1) * span / n_streams) - 1
        return sx0, y0, max(sx0, sx1), y1

    def count_font(self) -> int | None:
        """§10.3.3: ONE pane-wide count font, chosen once against the
        smallest registered tile and the widest legal label (``100``).

        A per-label fallback would print ``100`` smaller than ``42`` in the
        same pane, which is exactly what the rule forbids; when even the
        floor size cannot fit the widest label with its inner border, counts
        are omitted for the whole pane instead.
        """
        tile_y, tile_x = self.tiles_yx
        room_x = round(self.width / tile_x) - 4
        room_y = round(self.height / tile_y) - 3
        for size in range(11, 5, -1):
            mask, _offset = _glyph(size, "100")
            if mask.size[0] <= room_x and mask.size[1] <= room_y:
                return size
        return None

    def _tile_grid(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """E023c full-grid base: the untouched tile grid is drawn too, so a
        tile pane always carries the page's shape instead of a formless blob.

        Ruled lines cost O(tiles_y + tiles_x) calls, not one rectangle per
        tile; each line lands on a tile's own last row/column, so a chip
        drawn later replaces it exactly.
        """
        fill, outline = _CHIP_UNSEEN
        image = Image.new("RGB", (self.width, self.height), fill)
        draw = ImageDraw.Draw(image)
        tile_y, tile_x = self.tiles_yx
        for tx in range(tile_x):
            x = self.tile_box(0, tx)[2]
            draw.line((x, 0, x, self.height), fill=outline)
        for ty in range(tile_y):
            y = self.tile_box(ty, 0)[3]
            draw.line((0, y, self.width, y), fill=outline)
        return image, draw

    def scan_views(
        self, regions: "tuple[object, ...]"
    ) -> tuple[tuple[float, float, float],
               tuple[int, int], list[RegionView]]:
        """Pane-A frame and region footprints for one lane's region set.

        ONE implementation serves the live survey ingest and the v0.45
        durable-record resume seed (``survey.region_from_record`` regions),
        so seeded geometry is exactly what the live pass would have drawn:
        the lane-px bounding frame over every region bbox with the 3% pad,
        the ``(scale, y0, x0)`` lane-px -> pane-px transform, and one
        :class:`RegionView` per region in survey order (hue = index).
        Returns ``(transform, (y1, x1), views)``; the caller may feed the
        frame corners to :meth:`underlay` when preview pixels exist.
        """
        boxes = [region.support.bbox for region in regions]
        y0 = min(box[0] for box in boxes)
        x0 = min(box[1] for box in boxes)
        y1 = max(box[0] + box[2] for box in boxes)
        x1 = max(box[1] + box[3] for box in boxes)
        pad_y = max(1, int(0.03 * (y1 - y0)))
        pad_x = max(1, int(0.03 * (x1 - x0)))
        y0, x0, y1, x1 = y0 - pad_y, x0 - pad_x, y1 + pad_y, x1 + pad_x
        scale = min(self.width / max(1, x1 - x0),
                    self.height / max(1, y1 - y0))
        views: list[RegionView] = []
        for index, region in enumerate(regions):
            support = region.support
            by, bx, bh, bw = support.bbox
            w = max(1, round(bw * scale))
            h = max(1, round(bh * scale))
            mask = np.asarray(Image.fromarray(
                np.asarray(support.cells, np.uint8) * 255).resize(
                    (w, h), Image.NEAREST), np.uint8) > 0
            px = round((bx - x0) * scale)
            py = round((by - y0) * scale)
            views.append(RegionView(
                mask, (px, py, px + w, py + h), index % len(_HUES)))
        return (float(scale), float(y0), float(x0)), (y1, x1), views

    # -- panes ---------------------------------------------------------
    def underlay(self, preview: object, y0: float, x0: float, y1: float,
                 x1: float, scale: float) -> np.ndarray | None:
        """Decimated capture luma behind pane A (§10.3.3 preview stretch)."""
        if not isinstance(preview, dict):
            return None
        pixels = preview.get("pixels")
        decim = float(preview.get("decimation") or 0)
        if pixels is None or decim <= 0:
            return None
        pixels = np.asarray(pixels, np.float32)
        if pixels.ndim != 2 or not pixels.size:
            return None
        py0 = max(0, int(y0 / decim))
        px0 = max(0, int(x0 / decim))
        py1 = max(py0 + 1, min(pixels.shape[0], int(np.ceil(y1 / decim))))
        px1 = max(px0 + 1, min(pixels.shape[1], int(np.ceil(x1 / decim))))
        crop = pixels[py0:py1, px0:px1]
        if not crop.size:
            return None
        low, high = np.percentile(crop, (1.0, 99.0))
        span = max(float(high) - float(low), 1e-6)
        # Historical 1/99-percentile stretch, then lightened toward the
        # white shell so region tints and window overlays stay legible on
        # top of dense print texture (underlay is context, not radiometry).
        grey = 0.55 + 0.45 * np.clip((crop - float(low)) / span, 0.0, 1.0)
        target_h = max(1, min(self.height, round((py1 - py0) * decim
                                                 * scale)))
        target_w = max(1, min(self.width, round((px1 - px0) * decim
                                                * scale)))
        resized = np.asarray(Image.fromarray(
            (grey * 255.0).astype(np.uint8)).resize(
                (target_w, target_h), Image.BILINEAR), np.uint8)
        canvas = np.zeros((self.height, self.width, 3), np.uint8)
        canvas[:] = _BG
        oy = min(max(0, round((py0 * decim - y0) * scale)),
                 self.height - resized.shape[0])
        ox = min(max(0, round((px0 * decim - x0) * scale)),
                 self.width - resized.shape[1])
        canvas[oy:oy + resized.shape[0], ox:ox + resized.shape[1]] = (
            resized[..., None])
        return canvas

    def scan(self, regions: "list[RegionView]", underlay: np.ndarray | None,
             planned: "tuple[tuple[tuple[int, int, int, int], str], ...]",
             active_box: tuple[int, int, int, int] | None,
             parked: "tuple[tuple[tuple[int, int, int, int], str | None], ...]"
             = ()) -> np.ndarray:
        """Pane A: capture/lane space — supports, boxes, work in flight."""
        if underlay is not None:
            canvas = underlay.copy()
        else:
            canvas = np.zeros((self.height, self.width, 3), np.uint8)
            canvas[:] = _BG
        for region in regions:
            x0, y0, x1, y1 = region.box
            x0c, y0c = max(0, x0), max(0, y0)
            x1c = min(self.width, x1)
            y1c = min(self.height, y1)
            if x1c <= x0c or y1c <= y0c:
                continue
            hue = np.asarray(_HUES[region.hue], np.float32)
            mask = region.mask[y0c - y0:y1c - y0, x0c - x0:x1c - x0]
            target = canvas[y0c:y1c, x0c:x1c]
            # Identity tint over the capture underlay; the fine mask edge
            # (support boundary INCLUDING enclosed holes) carries state.
            blended = 0.62 * target[mask].astype(np.float32) + 0.38 * hue
            target[mask] = blended.astype(np.uint8)
            target[_mask_edge(mask)] = _REGION_OUTLINE.get(
                region.state, _BLUE)
        image = Image.fromarray(canvas)
        draw = ImageDraw.Draw(image)
        # §10.3.3 tight region box + piece number, standing from detection
        # (survey) through placement and rebuilt on the next lane's survey —
        # the fine mask edge alone left a detected-but-unplaced scrap with no
        # visible boundary for the whole address stage.
        label_size = max(9, min(13, round(self.width * 0.026)))
        for index, region in enumerate(regions):
            color = _REGION_OUTLINE.get(region.state, _BLUE)
            box = self.clip_box(region.box)
            draw.rectangle(box, outline=color,
                           width=2 if region.state == "active" else 1)
            # Piece identity only: the survey estimates no angle, so none is
            # printed rather than invented (§10.1).
            draw.text((box[0] + 2, max(0, box[1] - label_size - 2)),
                      str(index), fill=color, font=_font(label_size),
                      stroke_width=2, stroke_fill=(255, 255, 255))
        # v0.27 work-in-flight window overlay, escalating with the cost of
        # the route in flight: pending gray outline, parked (cold deferred)
        # purple dashed, rest-decoding (v0.29 remaining word slots — the
        # last cheap route) thin cyan, cold sweep heavy cyan; erased on
        # terminal resolution of either outcome.
        for box, state in planned:
            if state == "parked":
                _dashed_rect(draw, box, _PURPLE)
            elif state == "rest":
                draw.rectangle(box, outline=_CYAN)
            elif state == "active":
                draw.rectangle(box, outline=_CYAN, width=2)
            else:
                draw.rectangle(box, outline=_PENDING_OUTLINE)
        # v0.33 parked-for-mop-up chips (§10.3.3 as amended): durable rows
        # riding the barrier snapshot — solid amber, distinct from the
        # transient purple-dashed parked state.  Each chip prints its
        # plan-level digit; a chip too small for the digit omits it
        # per-chip and keeps the outline (the amended one-font rule).
        digit_size = max(8, min(12, round(self.width * 0.022)))
        for box, digit in parked:
            chip = self.clip_box(box)
            draw.rectangle(chip, outline=_PARKED_MOPUP)
            if digit:
                mask, _offset = _glyph(digit_size, str(digit))
                if (mask.size[0] <= chip[2] - chip[0] - 3
                        and mask.size[1] <= chip[3] - chip[1] - 3):
                    _blit_text(draw, (chip[0] + 2, chip[1] + 1),
                               str(digit), _PARKED_MOPUP, digit_size)
        if active_box is not None:
            draw.rectangle(self.clip_box(active_box), outline=_CYAN, width=2)
        return np.asarray(image)

    def placements(self, placed: np.ndarray | None,
                   provisional: "tuple[tuple[int, int, int, int], ...]"
                   ) -> np.ndarray:
        """Pane B: page space — piece-hue support and current proposals."""
        canvas = np.zeros((self.height, self.width, 3), np.uint8)
        canvas[:] = _BG
        if placed is not None:
            table = np.zeros((len(_HUES) + 1, 3), np.uint8)
            table[0] = _BG
            table[1:] = np.asarray(_HUES, np.uint8)
            canvas = table[np.minimum(placed, len(_HUES))]
        image = Image.fromarray(canvas)
        draw = ImageDraw.Draw(image)
        cy, cx = self.cells_yx
        for oy, ox, hh, ww in provisional:
            x0 = round(ox * self.width / cx)
            y0 = round(oy * self.height / cy)
            x1 = x0 + max(2, round(ww * self.width / cx))
            y1 = y0 + max(2, round(hh * self.height / cy))
            _dashed_rect(draw, self.clip_box((x0, y0, x1, y1)), _PURPLE)
        return np.asarray(image)

    def words(self, states: "dict[tuple[int, int], int]",
              counts: "dict[tuple[int, int], int]") -> np.ndarray:
        """Pane C: one chip per tile, with its observed BCH site count."""
        image, draw = self._tile_grid()
        tile_y, tile_x = self.tiles_yx
        font_size = self.count_font()
        for (ty, tx), state in states.items():
            if not (0 <= ty < tile_y and 0 <= tx < tile_x):
                continue
            box = self.tile_box(ty, tx)
            fill, outline = _WORD_CHIPS.get(state, _CHIP_BLUE)
            draw.rectangle(box, fill=fill, outline=outline)
            if state == _WORD_CONFLICT:
                # The retained special treatment: a double border.
                draw.rectangle((box[0] + 2, box[1] + 2,
                                box[2] - 2, box[3] - 2), outline=outline)
            count = counts.get((ty, tx), 0)
            if count and font_size is not None:
                _blit_text(draw, (box[0] + 2, box[1] + 1), str(count),
                           _CHIP_TEXT, font_size)
        return np.asarray(image)

    def tiles(self, states: np.ndarray | None, n_streams: int,
              retry: "tuple[tuple[int, int, int], ...]") -> np.ndarray:
        """Pane D: per-stream payload/LDPC segments, plus retry in flight."""
        image, draw = self._tile_grid()
        if states is not None:
            n_rows = states.shape[0]
            active = np.flatnonzero(states.max(axis=0).ravel())
            tile_x = self.tiles_yx[1]
            # C/M/Y segment order is stated once in the legend, never
            # repeated per tile (§10.3.3); an unseen sibling segment stays
            # visible as neutral so partial stream success never reads as a
            # whole-tile state.
            for flat in active:
                ty, tx = divmod(int(flat), tile_x)
                box = self.tile_box(ty, tx)
                for index in range(n_rows):
                    code = int(states[index, ty, tx])
                    segment = self.segment_box(box, index, n_rows)
                    fill, outline = (
                        _CHIP_NEUTRAL if code == _TILE_STATE_UNSEEN
                        else _TILE_CHIPS.get(code, _CHIP_BLUE))
                    draw.rectangle(segment, fill=fill, outline=outline)
        # v0.27 transient retry in-flight layer: highlighted at retry open
        # from the explicit frontier snapshot, cleared on either outcome.
        for ty, tx, index in retry:
            _dashed_rect(draw, self.segment_box(
                self.tile_box(ty, tx), index, n_streams), _PURPLE)
        return np.asarray(image)

    def field_band(
        self,
        planes: "tuple[tuple[int, int, int, float, float], ...]",
        exaggeration_hint: float,
        threshold_dots: float = 0.25,
        done: "tuple[tuple[int, int], ...]" = (),
    ) -> tuple[np.ndarray, float]:
        """W5 field band (PLANE-FIELDS.md §6.2): one quiver arrow per plane
        per tile-block, staggered so C/M/Y never fully overlap, over a
        faint page outline; a block is shaded where ANY plane's delta
        magnitude reaches ``threshold_dots`` -- the dead-band prediction.
        Returns ``(raster, factor)``; the caller folds ``factor`` into the
        band's own title text so the drawn geometry and the printed number
        are always the same measurement.

        The exaggeration factor is chosen so no drawn arrow reaches beyond
        ~2 tile blocks IN EITHER AXIS -- capped per axis, because the band
        is one page squeezed into a strip and its blocks are anisotropic
        (measured: the 52x36 c2 grid in a 2400x555 band body gives 66.4 x
        10.5 px blocks, 6.3x wider than tall, so the old width-only cap
        drew a 0.9-dot y delta 12.6 tile ROWS long while claiming 2
        blocks; it is 2.0 rows now).  Arrows themselves stay
        isotropic in pixels -- one factor scales both components, so the
        drawn direction is the measured direction -- and this is
        deliberately an illustration, not a metrology overlay, so there is
        no dots-per-pixel physical claim.  ``exaggeration_hint`` (the
        producer's own suggested factor, from its real dots-per-tile
        scale) is honoured as an upper bound when it would not overshoot
        that cap, and is the fallback when there is no delta to normalize
        against.
        """
        width = 4 * self.width
        title_h = self.title_height
        body_h = self.field_body_height
        image = Image.new("RGB", (width, title_h + body_h), _BG)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, title_h - 1),
                       fill=_TITLE_FILL, outline=_TITLE_RULE)
        size = self.title_size
        text_xy = (7, max(1, (title_h - size) // 2 - 1))
        tile_y, tile_x = self.tiles_yx
        pad = 4
        draw.rectangle(
            (pad, title_h + pad, width - 1 - pad, title_h + body_h - 1 - pad),
            fill=_FIELD_BODY_BG, outline=_FIELD_OUTLINE)
        if not planes:
            _blit_text(draw, text_xy, _FIELD_TITLE, _FIELD_DIM, size)
            return np.asarray(image), 0.0
        rows = [
            (int(plane), int(ty), int(tx), float(dx), float(dy))
            for plane, ty, tx, dx, dy in planes
            if 0 <= int(ty) < tile_y and 0 <= int(tx) < tile_x
        ]
        cell_w = (width - 2 * pad) / max(1, tile_x)
        cell_h = (body_h - 2 * pad) / max(1, tile_y)
        hint = float(exaggeration_hint)
        hint = hint if math.isfinite(hint) and hint > 0 else 0.0
        # One cap per axis against that axis' OWN block dimension; the
        # binding one wins.  A field that is mostly x (the measured Y
        # registration sinusoid is) therefore keeps full-length arrows,
        # and a single y outlier is what shortens them, not the grid.
        widest = max((abs(dx) for _p, _ty, _tx, dx, _dy in rows), default=0.0)
        tallest = max((abs(dy) for _p, _ty, _tx, _dx, dy in rows), default=0.0)
        caps = [2.0 * span / delta
                for span, delta in ((cell_w, widest), (cell_h, tallest))
                if delta > 0]
        if caps:
            cap = min(caps)
            factor = min(hint, cap) if hint > 0 else cap
        else:
            factor = hint if hint > 0 else 1.0
        shaded = {
            (ty, tx) for _p, ty, tx, dx, dy in rows
            if math.hypot(dx, dy) >= threshold_dots
        }
        covered = {(ty, tx) for _p, ty, tx, _dx, _dy in rows}
        holes = {
            (ty, tx)
            for ty in range(tile_y) for tx in range(tile_x)
            if (ty, tx) not in covered
        }
        def _block(ty: int, tx: int) -> tuple[int, int, int, int]:
            x0 = pad + round(tx * cell_w)
            x1 = pad + round((tx + 1) * cell_w)
            y0 = title_h + pad + round(ty * cell_h)
            y1 = title_h + pad + round((ty + 1) * cell_h)
            return x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)
        for ty, tx in sorted(shaded):
            draw.rectangle(_block(ty, tx), fill=_FIELD_SHADE)
        # Data-free blocks split by CAUSE: a fully certified tile has
        # nothing left to measure (dark green, benign); anything else
        # is the field's actionable blind spot (black).
        done_set = {(int(ty), int(tx)) for ty, tx in done}
        for ty, tx in sorted(holes):
            draw.rectangle(
                _block(ty, tx),
                fill=_FIELD_DONE if (ty, tx) in done_set else _FIELD_HOLE)
        for plane, ty, tx, dx, dy in rows:
            cx = pad + (tx + 0.5) * cell_w
            cy = title_h + pad + (ty + 0.5) * cell_h
            stagger = (plane % 3 - 1) * _FIELD_STAGGER_PX
            origin = (cx, cy + stagger)
            end = (cx + dx * factor, cy + stagger + dy * factor)
            color = _STREAM_HUE.get(_PLANES[plane % 3], _TEXT)
            _draw_arrow(draw, origin, end, color)
        _blit_text(draw, text_xy, f"{_FIELD_TITLE} x{factor:.0f}",
                   _TITLE_TEXT, size)
        return np.asarray(image), factor

    # -- frame ---------------------------------------------------------
    def encode(self, array: np.ndarray) -> bytes:
        stream = io.BytesIO()
        Image.fromarray(array).save(stream, "PNG")
        return stream.getvalue()

    def compose(self, rasters: "tuple[np.ndarray, ...]",
                band: np.ndarray | None = None) -> bytes:
        """The §10.3.1 frame: four equal panes in one horizontal row, plus
        the optional W5 field band as a fifth BOTTOM band (PLANE-FIELDS.md
        §6.2): frame width stays ``4 * self.width``; canvas height only
        grows when a band raster is supplied, so a run that never sees a
        ``payload.plane_fields`` snapshot composes byte-identical frames to
        before this pane existed (the null proof, campaign-style: dial off
        implies zero output change).

        Pane bodies are cached rasters, so composition is one paste plus the
        four fixed headings — no pane is re-rendered to publish a frame.
        """
        bar = self.title_height
        band_h = 0 if band is None else int(band.shape[0])
        canvas = np.empty(
            (bar + self.height + band_h, 4 * self.width, 3), np.uint8)
        canvas[:] = _BG
        for index, raster in enumerate(rasters):
            x0 = index * self.width
            canvas[bar:bar + self.height, x0:x0 + self.width] = raster
        if band is not None:
            canvas[bar + self.height:, :] = band
        image = Image.fromarray(canvas)
        draw = ImageDraw.Draw(image)
        size = self.title_size
        for index, title in enumerate(_PANE_TITLES):
            x0 = index * self.width
            draw.rectangle((x0, 0, x0 + self.width - 1, bar - 1),
                           fill=_TITLE_FILL, outline=_TITLE_RULE)
            _blit_text(draw, (x0 + 7, max(1, (bar - size) // 2 - 1)),
                       title, _TITLE_TEXT, size)
        return self.encode(np.asarray(image))


__all__ = [
    "_BG", "_TEXT", "_GREEN", "_ORANGE", "_BLUE", "_PURPLE", "_CYAN",
    "_PENDING_OUTLINE", "_PARKED_MOPUP", "_HUES", "_STREAM_HUE",
    "_CHIP_GREEN", "_CHIP_GREEN_SOFT",
    "_CHIP_BLUE", "_CHIP_REACH", "_CHIP_AMBER", "_CHIP_AMBER_SOFT",
    "_CHIP_ORANGE",
    "_CHIP_RED", "_CHIP_UNSEEN", "_CHIP_NEUTRAL", "_CHIP_TEXT",
    "_TILE_STATE_UNSEEN", "_TILE_STATE_EVIDENCE", "_TILE_STATE_FLOOR",
    "_TILE_STATE_FAILED", "_TILE_STATE_CERTIFIED", "_TILE_CHIPS",
    "_WORD_EVIDENCE", "_WORD_SEEDED", "_WORD_VALIDATED", "_WORD_SOLVED",
    "_WORD_FAILED", "_WORD_FLOOR", "_WORD_CONFLICT", "_WORD_CHIPS",
    "_WORD_ERASURE_BUDGET", "_REGION_OUTLINE", "_PANE_TITLES",
    "_TITLE_FILL", "_TITLE_RULE", "_TITLE_TEXT", "_PAGE", "_font",
    "_glyph", "_blit_text", "_mask_edge", "_dashed_rect", "_draw_arrow",
    "_FIELD_TITLE", "_FIELD_OUTLINE", "_FIELD_DIM", "_FIELD_SHADE",
    "_FIELD_HOLE", "_FIELD_DONE", "_FIELD_STAGGER_PX", "_PLANES",
    "PaneRenderer", "RegionView",
]
