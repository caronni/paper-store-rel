"""The browser shell: the index page the pane server serves at ``/``.

Carried from the v1 receiver's ``_PAGE`` (RECEIVE-DESIGN §10.7 transport):
status-first polling, double-buffered frame swap so a decoded frame stays
visible until its replacement has loaded, one frame per page, and the
per-page revision as the only cache key.

Stripped: the v1 lane/rung legends, the parked-chip vocabulary, and the
``frame.png?page=`` wanted-page teaching handshake — holo2's frames are
composed **on demand** from the store rather than published on a render
tick, so a page that was never composed is simply composed when asked.

The revision is the store's commit sequence, not a wall clock: the page
refetches a frame exactly when the receiver has committed something. The
poll interval below is the browser's, and no holo2 path reads it.
"""
from __future__ import annotations

PAGE = """<!doctype html><meta charset="utf-8">
<title>holo2 receive</title><style>
body{margin:0;background:#fff;color:#222;
font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:13px}
#rows{white-space:pre;font-family:ui-monospace,Menlo,monospace;
padding:8px 12px;line-height:1.45;border-bottom:1px solid #ddd;
background:#fafafa;overflow:hidden}
#sel{padding:5px 12px;color:#666}
#sel a{color:#06c;text-decoration:none;margin-right:9px;cursor:pointer}
#sel a.on{color:#000;font-weight:600}
#view{padding:10px 12px}
#f{display:block;width:100%;height:auto;background:#fff;
box-shadow:0 0 10px #bbb}
#legs{display:grid;grid-template-columns:repeat(4,1fr);gap:0;
color:#555;font-size:11px;padding:6px 0}
#legs div{padding:0 12px 0 2px}
b{color:#333}
</style>
<div id="rows">connecting…</div>
<div id="sel"></div>
<div id="view"><img id="f"><div id="legs">
<div><b>A CAPTURE</b> — capture-cell space: tint = surveyed region ·
blue edge = support boundary · green wash = §6 done pixels ·
window lattice: gray pending · green posed (committed pose) ·
orange retired · cyan dashed = done-gated (never posed again)</div>
<div><b>B PAGE</b> — the tile map of this page, one chip per work key,
split left-to-right by stream: gray UNKNOWN · pale blue ADDRESSED ·
amber ATTEMPTED · green CERTIFIED · number = observing evidence
pieces</div>
<div><b>C WORKERS</b> — the ready queue and worker population, fires,
wakes per commit, useful re-run ratio, peak fires in flight and
stale discards. Counts come from the orchestrator snapshot only</div>
<div><b>D CLOSE</b> — per (stream, block) have/needed and rank, the
metadata rank, and the verified stop. A bar turns green when its
block solves</div>
</div></div>
<script>
let rev=-1,page=null,cap=null;
function pick(p,c){page=p;cap=c;rev=-1;}
function swap(url){const pre=new Image();
 pre.onload=function(){document.getElementById('f').src=pre.src;};
 pre.src=url;}
function link(p,c,label,on){
 return '<a onclick="pick('+p+','+(c===null?'null':'\\''+c+'\\'')+')" '+
  'class="'+(on?'on':'')+'">'+label+'</a>';}
async function poll(){try{
 const r=await fetch('status',{cache:'no-store'});const j=await r.json();
 document.getElementById('rows').textContent=(j.rows||[]).join('\\n');
 const panes=j.panes||{};const pages=panes.pages||[];
 const caps=panes.captures||[];
 if(page===null||!pages.includes(page))page=pages.length?pages[0]:null;
 let html=pages.map(p=>link(p,cap,'page '+p,p===page)).join('');
 if(caps.length>1){html+=' &nbsp;|&nbsp; '+caps.map(c=>
  link(page,c,c,c===cap)).join('');}
 document.getElementById('sel').innerHTML=html||'&nbsp;';
 const now=panes.revision;
 if(page!==null&&now!==undefined&&now!==rev){rev=now;
  swap('frame/'+page+'.png?rev='+rev+(cap?'&capture='+cap:''));}
 }catch(e){}
 setTimeout(poll,1000);}
poll();
</script>"""

PAGE_BYTES = PAGE.encode("utf-8")

__all__ = ["PAGE", "PAGE_BYTES"]
