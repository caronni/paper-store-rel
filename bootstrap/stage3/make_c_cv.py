"""make_c_cv.py -- make_c.py's generation (c_readable.py -> minify -> M1 -> M2
-> M3 -> static equivalence), scored under an EXPLICIT primer and order tuple
and written to an explicit directory: the c.py step of the convergence of
ruling 60 (2026-10-23).  make_c.py scores under the stand-in stage-1 build's
lower b.py at (0,1,2,3,4,6,8); here the primer is the chain's own b.py (a
stage-1 build with c.py as the content, stage1/chain_v2.py) at the tuple that
build chose, which is what the chain's R2 payload is coded under
(cm2(c.py, b.py, a.py's default tuple)).  Nothing in the tree is written:
bootstrap/stage3/c.py is replaced only by the convergence's final atomic
copy, after which make_c.py itself is not the generator of record of that
text unless its PRIMER/ORDERS follow (CONVERGENCE-2026-10-23.md).

  python bootstrap/stage3/make_c_cv.py --primer B.PY --orders 0,1,2,3,4,6 --out DIR [--workers N]
Writes DIR/c.py, DIR/make_c.json, DIR/make_c.log, DIR/forms/.
"""
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BOOT / 'typed'))


def arg(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


PRIMER = Path(arg('--primer')).resolve()
ORDERS = tuple(int(x) for x in arg('--orders').split(','))
OUT = Path(arg('--out')).resolve()
import make_c as MC  # noqa: E402  (reads --workers)
import cm2_enc  # noqa: E402

MC.ev.Handle.__init__.__defaults__ = (ORDERS,)   # every scorer (Scorer, search2.Searcher) at the chain's tuple
PAGE = 5304


def main():
    t0 = time.time()
    forms = OUT / 'forms'
    forms.mkdir(parents=True, exist_ok=True)
    log = MC.log
    readable = MC.SOURCE.read_text()
    edges = MC.check_edges(MC.SOURCE, MC.ROW_NEW)
    assert edges['identical'] and edges['format_id'] == 'holo/v2/1i200-k-r0547-p100-v1@35x24', edges
    log(f"(b') source c_readable.py {len(readable.encode())} B sha256 {MC.sha(readable)[:16]}: checks == holo "
        f"r0547 edges ({edges['edges']})")
    MC.calibrate_minifier()
    ming = MC.MS.minify(readable, True)
    (forms / 'r0547.minified-g.py').write_text(ming)
    pb = PRIMER.read_bytes()
    sc = MC.Scorer(pb)
    h = MC.ev.Handle(MC.MAXB)
    assert abs(h.bits(ming, pb) - MC.ev.Handle(MC.MAXB, ORDERS).bits(ming, pb)) < 1e-9
    ex = ThreadPoolExecutor(MC.WORKERS)
    log(f'(d) primer {PRIMER} ({len(pb)} B, sha256 {MC.sha(pb)[:16]}), orders {ORDERS}: minified-g '
        f'{len(ming.encode())} B, {sc(ming) / 8:.1f} B ideal')
    m1, r1 = MC.m1_inline(ming, sc, ex)
    (forms / 'r0547.m1.py').write_text(m1)
    assert MC.m1_equivalent(ming, m1, r1['steps'])
    log(f"  M1: {len(r1['steps'])} aliases, {r1['start_bits'] / 8:.1f} -> {r1['end_bits'] / 8:.1f} B ideal; "
        "ast-equivalent")
    m2, r2 = MC.m2_rename(m1, pb)
    (forms / 'r0547.m2.py').write_text(m2)
    e2 = MC.rename_equivalent(m1, m2)
    assert not e2['renamed_attributes']
    log(f"  M2: {r2['end_bits'] / 8:.1f} B ideal; {e2['renamed_bindings']} bindings renamed, bijective")
    m3, r3 = MC.m3_attrs(m2, sc, ex)
    e3 = MC.rename_equivalent(m2, m3)
    assert e3['renamed_attributes'] == r3['map']
    e23 = MC.rename_equivalent(m1, m3)
    log(f"  M3: {len(r3['map'])} attributes, {r3['start_bits'] / 8:.1f} -> {r3['end_bits'] / 8:.1f} B ideal; "
        f"M1 -> c.py {e23['renamed_bindings']} bindings + {len(e23['renamed_attributes'])} attributes, bijective")
    compile(m3, 'c.py', 'exec')
    assert not any(isinstance(n, (MC.ast.Import, MC.ast.ImportFrom)) for n in MC.ast.walk(MC.ast.parse(m3))) \
        and '__import__' not in m3
    (OUT / 'c.py').write_text(m3)
    tree_c = (HERE / 'c.py').read_text()
    z = cm2_enc.encode(m3.encode(), pb, ORDERS)
    pages = math.ceil(len(z) / PAGE)
    rec = dict(primer=dict(path=str(PRIMER), bytes=len(pb), sha256=MC.sha(pb)), orders=list(ORDERS),
               source=dict(bytes=len(readable.encode()), sha256=MC.sha(readable)),
               m1=dict(r1, bytes=len(m1.encode()), sha256=MC.sha(m1)),
               m2=dict(r2, bytes=len(m2.encode()), sha256=MC.sha(m2), equivalence=e2),
               m3=dict(r3, bytes=len(m3.encode()), sha256=MC.sha(m3), equivalence=e3), m1_to_c=e23,
               c_py=dict(bytes=len(m3.encode()), sha256=MC.sha(m3), lines=len(m3.splitlines()),
                         identical_to_tree=m3 == tree_c, tree_sha256=MC.sha(tree_c)),
               cm2=dict(bytes=len(z), pages=pages, headroom=pages * PAGE - len(z)),
               cm2_tree_c=len(cm2_enc.encode(tree_c.encode(), pb, ORDERS)),
               workers=MC.WORKERS, wall_s=round(time.time() - t0, 1))
    (OUT / 'make_c.json').write_text(json.dumps(rec, indent=1) + '\n')
    log(f"c.py {len(m3.encode())} B sha256 {MC.sha(m3)[:16]} ({'IDENTICAL to' if m3 == tree_c else 'new against'} "
        f"the tree's {MC.sha(tree_c)[:16]}); cm2 {len(z)} B ({rec['cm2_tree_c']} B for the tree's c.py under the "
        f"same primer), {pages} pages, headroom {pages * PAGE - len(z)} B; {time.time() - t0:.0f} s")
    (OUT / 'make_c.log').write_text('\n'.join(MC.LOG) + '\n')


if __name__ == '__main__':
    main()
