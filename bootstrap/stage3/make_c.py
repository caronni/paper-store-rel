"""make_c.py -- stage 3 of the bootstrap: c.py GENERATED from its source of
record, stage3/c_readable.py (the owner's ruling of 2026-10-22, ruling 35's
shape: the long form is the source, the short form proven generated).
ONE scripted generation; re-runnable, byte-identical.

c_readable.py is the R3 monolith receiver with its archival layer
(bootstrap/r3/arch/receiver_arch.py) retargeted to the r0547 row, plus the
documented hand edits (2026-10-22: the c.py naming and the progress lines;
2026-10-23: the lattice search and the per-tile retry, RESULTS-2026-10-22.md
"The repair of 2026-10-23", then its third pass: LDPC alpha 0.8, the
neighbouring-dpi fallback, one progress line); `--provenance` proves that
link (below).

THE GENERATION (no argument):
  (b') the source's expanded parity checks are compared with holo's own r0547
      edge set (holo.core.ldpc.construct.load_code, the shortened tail
      dropped), its FORMAT_ID with the row's seed;
  (c) MINIFY as the record's 'minified-g' form was made (r3/measure.py's
      minify(src, True): python-minifier, module names renamed too); the
      calibration: receiver_arch.py's own minified-g reproduces the
      record's 24,460 B form byte for byte;
  (d) the MONOLITH PIPELINE (compressor-exploration LEVERS §4; the
      encoder-side lab, copied in stage3/lab/ with the reader changeset's
      orders): M1 undo the minifier's module aliases (lab/mono_inline.py,
      greedy best-first), M2 scope-exact local renames (search2.Searcher,
      window 1500, the lower+upper pool, module scope excluded, ONE sweep as
      recorded), M3 the program's own attribute names (attr_greedy.py's
      rule, longest first), every score the ideal cm2 bits under the
      CHAIN's primer (since the convergence of ruling 60, 2026-10-23,
      bootstrap/CONVERGENCE-2026-10-23.md): b.py of the stage-1 build with
      the tree's c.py itself as the content (stage1/chain_v2.py make upper,
      the frozen spelling, rebuilt on every run into
      build/stage3/stage1_chain/) at the tuple that build chose,
      (0,1,2,3,4,6) -- the primer and tuple the chain's R2 payload is coded
      under.  At the fixed point the c.py in the tree gives itself; a new
      c_readable.py (or reader, or spelling) re-opens the convergence,
      since b.py bakes c.py's length and CRC.  (Before: the stand-in
      build's lower b.py at (0,1,2,3,4,6,8).)  -> bootstrap/stage3/c.py,
      written (atomically) only when it differs;
  (d') THE TWO-CYCLE (2026-10-23, the re-run of the convergence,
      bootstrap/CONVERGENCE-2026-10-23b.md): the pipeline is greedy, and
      its output under the chain of c.py A can be a c.py X whose own chain
      gives A back (measured: the 24,163 B c0ffe2a5 and the 24,176 B
      b4f7de22 generate each other).
      So when X differs from A, the chain is built again with X as the
      content (chain_v2.py make upper --bundle, into
      build/stage3/stage1_chain_partner/) and the pipeline run under ITS
      b.py; if that gives A back, A and X are a two-cycle and the member
      whose own chain is the smaller print is kept -- the upper case's
      exact typed total, then its R2 payload bytes (cm2(c.py, its own
      b.py), what the R2 pages carry), A on a tie -- so make_c.py run on
      either member writes the same c.py; otherwise X is written as before
      (the convergence goes on).  Twice the wall when c.py moves;
  (e) EQUIVALENCE, static: M1 by ast (every removed alias line's name
      replaced by its value gives the pre-M1 tree), M2 + M3 by a parallel
      ast walk (same node types, same constants and operators; the binding
      map old -> new a bijection by names2's scope resolution, builtins
      unchanged; the attribute map a bijection); dynamic = e2e_c.py (both
      forms on the same scans).

THE PROVENANCE (--provenance; seconds, writes build/stage3/ only):
  (a) receiver_arch.py, rebuilt in memory by bootstrap/r3/arch/make_arch.py's
      own build() from r3/receiver.py + dec_strong2.py's region and checked
      byte-identical to r3/arch/receiver_arch.py (nothing is written to r3/);
  (b) RETARGET to r0547 (ruling 36): the FORMAT_ID string, the LDPC_TABLE
      lines packed from src/holo/core/ldpc/data/r0547.json by
      bootstrap/r3/pack_ldpc.py's algorithm (re-implemented here, because
      pack_ldpc.py rewrites r3/receiver.py; the packer is calibrated by
      re-packing r0550.json to the table receiver_arch.py carries), five
      comment / docstring mentions of the rung; nothing else; its edges
      checked as in (b'); its minified-g differs from the record's in
      exactly the two row literals -> build/stage3/c_retarget.py;
  (f) the diff c_retarget.py -> stage3/c_readable.py, printed hunk by hunk
      (no context) and held to the documented changes: PROVENANCE_HUNKS = 20
      hunks.  Five inside the module docstring: the stale b.py naming ->
      c.py, the progress lines described (10-22), the dpi sentence and
      stage 2's lattice clause (10-23).  Fifteen in code: ONE at module
      level, the LDPC_ALPHA literal 0.75 -> 0.8 and nothing else on its line
      (ALPHA_LINE, rulings 63 and 65: holo's value); every other changed
      line (old side and new) inside one of the REPAIRED functions or the
      one pure insertion in unz (the 5 % heartbeat): Scan.__init__ and the
      new Scan.aperture (the box from a pitch), Scan.find_lattice (now a
      generator of candidates over three trial pitches) and the new
      Scan.track (the 17 x 17-cell lock, the floors 1.2, the walk from 4
      cells, the box at the pitch found), Receiver.read_scan (the candidate
      loop inside the neighbouring-dpi fallback, its progress line and the
      fallback's), Receiver.decode_tile (the retry at +-1/8 cell,
      CRC-gated); exactly three print calls added (the progress line, the
      fallback's line, the heartbeat), none removed; and the two trees
      equal as ast once the docstrings, the heartbeat and the six repaired
      functions are dropped and the retarget's alpha set to 0.8.
      -> build/stage3/provenance.{diff,json}.
Exact sizes (cm2_enc.encode, the chain's coder) are measured by
sizes_c.py, not here.  Outputs: bootstrap/stage3/c.py and build/stage3/
(forms/, make_c.json, make_c.log).

  env/bin/python bootstrap/stage3/make_c.py [--workers N]
  env/bin/python bootstrap/stage3/make_c.py --provenance
"""
import ast
import difflib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import time
import tokenize
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOT = HERE.parent
ROOT = BOOT.parent
BUILD = BOOT / "build" / "stage3"
FORMS = BUILD / "forms"
sys.path.insert(0, str(HERE / "lab"))
sys.path.insert(0, str(BOOT / "r3"))
import ev  # noqa: E402
import names2 as nm  # noqa: E402
import search2 as S  # noqa: E402
import measure as MS  # noqa: E402  (r3/measure.py: minify; it reads build/loader/r.py, never writes at import)

PY = "env/bin/python"
WORKERS = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 6
ORDERS = (0, 1, 2, 3, 4, 6)                # the chain build's tuple (asserted in primer())
ev.Handle.__init__.__defaults__ = (ORDERS,)   # every scorer (Scorer, search2.Searcher) at that tuple
MAXB = 48000
RECORD_ARCH = BOOT / "r3" / "arch" / "receiver_arch.py"
SOURCE = HERE / "c_readable.py"            # the source of record
PROVENANCE_HUNKS = 20                      # docstring 5 + code 15 (README, provenance)
ALPHA_LINE = ("LDPC_ITERS, LDPC_ALPHA = 50, 0.75  # layered normalised min-sum",   # the one code
              "LDPC_ITERS, LDPC_ALPHA = 50, 0.8   # layered normalised min-sum")   # hunk outside
REPAIRED = {"Scan.__init__", "Scan.aperture", "Scan.find_lattice", "Scan.track",   # 2026-10-23: the
            "Receiver.read_scan", "Receiver.decode_tile"}   # lattice search, the per-tile retry
RECORD_MING = BOOT / "build" / "r3" / "arch" / "forms_arch" / "receiver_arch.minified-g.py"
CHAIN = BUILD / "stage1_chain"
PRIMER = CHAIN / "upper" / "b.py"
PARTNER = BUILD / "stage1_chain_partner"     # (d'): the chain of the pipeline's output
ROW_OLD, ROW_NEW = "r0550", "r0547"
LOG = []


def log(m):
    LOG.append(m)
    print(m, flush=True)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---- (a) ---------------------------------------------------------------------
def receiver_arch():
    ma = load("make_arch", BOOT / "r3" / "arch" / "make_arch.py")
    _, out = ma.build(False)
    assert out == RECORD_ARCH.read_text(), "make_arch.build(False) != r3/arch/receiver_arch.py"
    return out


# ---- (b) ---------------------------------------------------------------------
def pack_table(row):
    """bootstrap/r3/pack_ldpc.py's packing, verbatim in effect: one integer in
    mixed radix, least significant digit first (pi as its Lehmer code, then per
    info column block, 10 heavy then 25 light, its block rows radix 29 and
    shifts radix 64), hex, 76 digits a line.  -> (block text, record)."""
    d = json.loads((ROOT / "src" / "holo" / "core" / "ldpc" / "data" / (row + ".json")).read_text())
    pi = d["pi"]
    m = len(pi)
    assert (d["n_bits"], d["k_bits"], d["z"]) == (4096, 2240, 64) and m == 4096 - 2240, row
    assert d["heavy_deg"] == 10 and len(d["heavy_rows"]) == 10 and len(d["light_rows"]) == 25, row
    assert all(len(r) == 10 for r in d["heavy_rows"] + d["heavy_shifts"]), row
    assert all(len(r) == 3 for r in d["light_rows"] + d["light_shifts"]), row
    assert sorted(pi) == list(range(m)), row
    digits, pool = [], list(range(m))
    for i in range(m):
        k = pool.index(pi[i])
        pool.pop(k)
        digits.append((k, m - i))
    for rows, shifts in ((d["heavy_rows"], d["heavy_shifts"]), (d["light_rows"], d["light_shifts"])):
        for r, s in zip(rows, shifts):
            digits += [(x, 29) for x in r] + [(x, 64) for x in s]
    x = 0
    for v, radix in reversed(digits):
        assert 0 <= v < radix, (row, v, radix)
        x = x * radix + v
    h = format(x, "x")
    lines = [h[i:i + 76] for i in range(0, len(h), 76)]
    return "".join(f"    '{ln}'\n" for ln in lines), dict(
        row=row, bits=x.bit_length(), hex_digits=len(h), lines=len(lines), n=d["n_bits"], k=d["k_bits"],
        z=d["z"], heavy=len(d["heavy_rows"]), light=len(d["light_rows"]), gap_min=d.get("gap_min"))


TABLE_BEGIN, TABLE_END = "    # LDPC-TABLE-BEGIN\n", "    # LDPC-TABLE-END\n"


def table_of(src):
    a = src.index(TABLE_BEGIN) + len(TABLE_BEGIN)
    return a, src.index(TABLE_END, a)


# every non-table line that names the rung (each must occur exactly once)
TEXT_EDITS = [
    ("    at 600 dpi (c3; c4 = set CELL_DOTS = 4), LDPC rung r0550, 100 address\n",
     "    at 600 dpi (c3; c4 = set CELL_DOTS = 4), LDPC rung r0547, 100 address\n"),
    ("# is the public test row c3-k-r0550@35x24 (c4: 1i150 ... @26x18).\n",
     "# is the public test row c3-k-r0547@35x24 (c4: 1i150 ... @26x18).\n"),
    ("FORMAT_ID = 'holo/v2/1i%d-k-r0550-p100-v1@%dx%d' % (\n",
     "FORMAT_ID = 'holo/v2/1i%d-k-r0547-p100-v1@%dx%d' % (\n"),
    ("N_CODE, K_INFO = 4096, 2240   # LDPC r0550: n, k (Z = 64)\n",
     "N_CODE, K_INFO = 4096, 2240   # LDPC r0547: n, k (Z = 64)\n"),
    ("# ================================================= 6. LDPC r0550 and CRC\n",
     "# ================================================= 6. LDPC r0547 and CRC\n"),
    ("# The e-IRA quasi-cyclic mother code (src/holo/core/ldpc/data/r0550.json),\n",
     "# The e-IRA quasi-cyclic mother code (src/holo/core/ldpc/data/r0547.json),\n"),
    ("    equals bits 2108..2139.  A syndrome alone is never enough (r0550 has\n"
     "    low-weight codewords).\"\"\"\n",
     "    equals bits 2108..2139.  A syndrome alone is never enough (r0550,\n"
     "    r0547's twin, has low-weight codewords).\"\"\"\n"),
]


def retarget(src):
    blk_old, rec_old = pack_table(ROW_OLD)
    a, z = table_of(src)
    assert src[a:z] == blk_old, "the packer does not reproduce receiver_arch.py's r0550 table"
    blk_new, rec_new = pack_table(ROW_NEW)
    out = src[:a] + blk_new + src[z:]
    for old, new in TEXT_EDITS:
        assert out.count(old) == 1, old
        out = out.replace(old, new)
    assert ROW_OLD not in out.replace("(r0550,\n    r0547's twin", ""), "an r0550 mention left"
    return out, rec_old, rec_new


def check_edges(path, row):
    """The receiver's expanded checks == holo's edge set (minus the shortened
    tail), in a subprocess with src/ on the path (pack_ldpc.py's check)."""
    code = r"""
import importlib.util, sys, json
spec = importlib.util.spec_from_file_location('c_readable', %r)
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
from holo.core.ldpc.construct import load_code
c = load_code(%r)
mine = sorted((ci, v) for ci, vs in enumerate(R.CHECKS) for v in vs)
ref = sorted((int(a), int(b)) for a, b in zip(c.edge_chk, c.edge_var) if not R.SHORT[0] <= int(b) < R.SHORT[1])
print(json.dumps(dict(edges=len(mine), holo_edges=len(ref), identical=mine == ref, format_id=R.FORMAT_ID,
                      n=R.N_CODE, k=R.K_INFO)))
""" % (str(path), row)
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def literal_diff(a, b):
    """Token streams of two programs: the (old, new) pairs where they differ;
    raises if the streams have different lengths or kinds."""
    ta = [t for t in tokenize.generate_tokens(io.StringIO(a).readline)]
    tb = [t for t in tokenize.generate_tokens(io.StringIO(b).readline)]
    assert len(ta) == len(tb), (len(ta), len(tb))
    out = []
    for x, y in zip(ta, tb):
        assert x.type == y.type, (x, y)
        if x.string != y.string:
            out.append((x.string, y.string))
    return out


# ---- (d) ---------------------------------------------------------------------
class Scorer:
    def __init__(self, primer):
        self.primer, self.tl = primer, threading.local()

    def __call__(self, text):
        h = getattr(self.tl, "h", None)
        if h is None:
            h = self.tl.h = ev.Handle(MAXB)
        return h.bits(text, self.primer)


def m1_inline(src, sc, ex):
    """compressor-exploration/encoder-side/mono_inline.py's main loop (its
    candidates() as written there, copied in lab/)."""
    mi = load("mono_inline", HERE / "lab" / "mono_inline.py")
    cur, best = src, sc(src)
    start, steps = best, []
    while True:
        cands = list(mi.candidates(cur))
        res = sorted(ex.map(lambda c: (sc(c[1]), c[0], c[1]), cands), key=lambda r: r[0])
        if not res or res[0][0] >= best - 1e-9:
            break
        b, lab, txt = res[0]
        steps.append(dict(label=lab, delta_bits=round(b - best, 3)))
        log(f"  M1 {lab} {b - best:+.1f} bits")
        best, cur = b, txt
    return cur, dict(start_bits=start, end_bits=best, steps=steps)


def m2_rename(src, primer):
    se = S.Searcher(primer, MAXB, workers=WORKERS, window=1500, log=lambda m: log("  M2 " + m))
    cur, best = se.run(src, S.LOWER + S.UPPER, sweeps=1, only=lambda b: b[0] != 0)
    return cur, dict(end_bits=best, tries=se.ntry, full_evals=se.nfull)


def builtin_attrs():
    B = set()
    for t in (str, bytes, list, dict, set, int, float, tuple, memoryview, bytearray, io.BufferedReader,
              io.BufferedWriter, io.FileIO, Exception, ValueError, OSError, object):
        B |= set(dir(t))
    B.discard("close")
    return B


def own_attrs(tree, B):
    own = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            own |= {st.name for st in n.body if isinstance(st, ast.FunctionDef)}
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store):
            own.add(n.attr)
    return {a for a in own if a not in B and not a.startswith("__")}


def attr_build(src, old, new):
    """attr_greedy.py's build(): every ast.Attribute .old and every method def
    `old` in a class body respelled `new`."""
    tree = ast.parse(src)
    T = src.encode()
    lines = T.split(b"\n")
    offs = [0]
    for L in lines:
        offs.append(offs[-1] + len(L) + 1)
    sp = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr == old:
            e = offs[n.end_lineno - 1] + n.end_col_offset
            assert T[e - len(old):e] == old.encode()
            sp.append((e - len(old), e))
        if isinstance(n, ast.ClassDef):
            for st in n.body:
                if isinstance(st, ast.FunctionDef) and st.name == old:
                    c = offs[st.lineno - 1] + st.col_offset + 4
                    assert T[c:c + len(old)] == old.encode()
                    sp.append((c, c + len(old)))
    o, last = [], 0
    for a, b in sorted(sp):
        o.append(T[last:a])
        o.append(new.encode())
        last = b
    o.append(T[last:])
    r = b"".join(o).decode()
    ast.parse(r)
    return r


def m3_attrs(src, sc, ex):
    """attr_greedy.py's loop: own attribute / method names, longest first, each
    to the best single letter not used as any attribute name and not a builtin
    type's attribute; kept only when it lowers the score."""
    banned = ("getattr", "setattr", "hasattr", "__dict__", "vars(")
    assert not any(b in src for b in banned), "dynamic attribute access in the program"
    B = builtin_attrs()
    cur, best = src, sc(src)
    start, mp = best, {}
    letters = [chr(c) for c in range(97, 123)] + [chr(c) for c in range(65, 91)]
    for a in sorted(own_attrs(ast.parse(src), B), key=lambda x: (-len(x), x)):
        t = ast.parse(cur)
        used = {n.attr for n in ast.walk(t) if isinstance(n, ast.Attribute)} | {
            st.name for n in ast.walk(t) if isinstance(n, ast.ClassDef) for st in n.body
            if isinstance(st, ast.FunctionDef)}
        cands = [c for c in letters if c not in used and c not in B]
        res = sorted(ex.map(lambda c: (sc(attr_build(cur, a, c)), c), cands))
        if res and res[0][0] < best - 1e-9:
            log(f"  M3 {a} -> {res[0][1]} {(res[0][0] - best) / 8:+.1f} B")
            best, cur = res[0][0], attr_build(cur, a, res[0][1])
            mp[a] = res[0][1]
    return cur, dict(start_bits=start, end_bits=best, map=mp)


# ---- (e) ---------------------------------------------------------------------
IDENT = {ast.Name: "id", ast.arg: "arg", ast.FunctionDef: "name", ast.ClassDef: "name",
         ast.Attribute: "attr", ast.ExceptHandler: "name", ast.Nonlocal: "names"}


def m1_equivalent(pre, post, steps):
    """post == pre with each inlined alias's line removed and its name replaced
    by its value, as ast dumps (the labels name the alias and its value)."""
    occ, _, _ = nm.bindings(pre)          # the module-scope occurrences only (scope 0)
    tree = nm._ROOT[0]
    sub = {}
    for s in steps:
        name, val = s["label"][len("inline "):].split("=", 1)
        sub[name] = ast.parse(val, mode="eval").body
    body = [st for st in tree.body if not (isinstance(st, ast.Assign) and len(st.targets) == 1
                                           and isinstance(st.targets[0], ast.Name)
                                           and st.targets[0].id in sub)]
    assert len(tree.body) - len(body) == len(sub), "an alias line not found once"
    tree.body = body
    at = {id(node) for node, kind, name, b in occ if kind == "name" and b == (0, name) and name in sub}

    class Sub(ast.NodeTransformer):
        def visit_Name(self, n):
            if id(n) in at:
                assert isinstance(n.ctx, ast.Load), n.id
                return ast.copy_location(sub[n.id], n)
            return n
    tree = Sub().visit(tree)
    return ast.dump(tree) == ast.dump(ast.parse(post))


def rename_equivalent(pre, post):
    """A parallel ast walk: identical node types and non-identifier fields;
    identifiers related by (i) a bijection between names2's bindings (scope,
    name) of the two texts, builtins mapped to themselves, and (ii) a
    bijection between attribute / method names.  Returns the two maps."""
    ta, tb = ast.parse(pre), ast.parse(post)
    na, nb = list(ast.walk(ta)), list(ast.walk(tb))
    assert len(na) == len(nb)
    attr = {}
    for x, y in zip(na, nb):
        assert type(x) is type(y), (type(x), type(y))
        for f in x._fields:
            vx, vy = getattr(x, f), getattr(y, f)
            if isinstance(vx, ast.AST) or (isinstance(vx, list) and vx and isinstance(vx[0], ast.AST)):
                continue
            if IDENT.get(type(x)) == f:
                if isinstance(x, ast.Attribute):
                    assert attr.setdefault(vx, vy) == vy, ("attribute map not a function", vx)
                continue
            assert vx == vy, (type(x).__name__, f, vx, vy)
    assert len(set(attr.values())) == len(attr), "attribute map not injective"
    for x, y in zip(na, nb):            # a method's name follows its attribute's
        if isinstance(x, ast.ClassDef):
            for u, v in zip(x.body, y.body):
                if isinstance(u, ast.FunctionDef) and not u.name.startswith("__"):
                    assert attr.get(u.name, u.name) == v.name, ("method vs attribute", u.name, v.name)
    oa, _, _ = nm.bindings(pre)
    ob, _, _ = nm.bindings(post)
    assert len(oa) == len(ob)
    fwd, back = {}, {}
    for (n1, k1, s1, b1), (n2, k2, s2, b2) in zip(oa, ob):
        assert k1 == k2 and type(n1) is type(n2)
        if b1[0] == "builtin" or b2[0] == "builtin":
            assert b1 == b2 and s1 == s2, ("builtin moved", b1, b2)
            continue
        assert fwd.setdefault(b1, b2) == b2, ("binding map not a function", b1)
        assert back.setdefault(b2, b1) == b1, ("binding map not injective", b2)
    ren = {f"{b[0]}:{b[1]}": c[1] for b, c in fwd.items() if b[1] != c[1]}
    return dict(bindings=len(fwd), renamed_bindings=len(ren), attributes=len(attr),
                renamed_attributes={a: b for a, b in attr.items() if a != b})


# ---- the run -----------------------------------------------------------------
def primer(bundle=None, chain=CHAIN):
    """b.py of the chain: stage1/chain_v2.py make upper (the tree's template,
    frozen spelling, reader and c.py -- or BUNDLE as the content, into CHAIN),
    rebuilt every run so it is never stale."""
    bundle = Path(bundle or HERE / "c.py")
    log(f"primer: stage1/chain_v2.py make upper --out {chain} (c.py {sha(bundle.read_bytes())[:16]})")
    subprocess.run([PY, str(BOOT / "stage1" / "chain_v2.py"), "make", "upper", "--out", str(chain),
                    "--bundle", str(bundle)], cwd=BOOT / "stage1", check=True, stdout=subprocess.DEVNULL)
    b = json.loads((chain / "upper" / "build.json").read_text())
    assert tuple(b["orders"]) == ORDERS, b["orders"]
    assert b["n2"] == len(bundle.read_bytes()), "the primer does not carry the bundle"
    return (chain / "upper" / "b.py").read_bytes(), b


def sha(t):
    return hashlib.sha256(t.encode() if isinstance(t, str) else t).hexdigest()


def calibrate_minifier():
    """minify(receiver_arch.py) == the record's 24,460 B minified-g form."""
    ming_old = MS.minify(RECORD_ARCH.read_text(), True)
    if RECORD_MING.exists():
        assert ming_old == RECORD_MING.read_text(), "minify(receiver_arch) != the record's minified-g"
    assert len(ming_old.encode()) == 24460, len(ming_old.encode())
    return ming_old


def module_doc_lines(tree):
    d = tree.body[0]
    assert isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant) and isinstance(d.value.value, str)
    return d.lineno, d.end_lineno


def drop_lines(node, lines):
    """Remove every statement (in any body) whose first line is in lines,
    not descending into a removed one; returns how many were removed."""
    gone = 0
    for f, v in ast.iter_fields(node):
        if isinstance(v, list):
            keep = []
            for x in v:
                if isinstance(x, ast.stmt) and x.lineno in lines:
                    gone += 1
                    continue
                if isinstance(x, ast.AST):
                    gone += drop_lines(x, lines)
                keep.append(x)
            setattr(node, f, keep)
        elif isinstance(v, ast.AST):
            gone += drop_lines(v, lines)
    return gone


def spans(tree):
    """{qualified function name: (first line, last line)}, methods as Class.name."""
    out = {}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            out[n.name] = (n.lineno, n.end_lineno)
        elif isinstance(n, ast.ClassDef):
            out.update({f"{n.name}.{m.name}": (m.lineno, m.end_lineno) for m in n.body
                        if isinstance(m, ast.FunctionDef)})
    return out


def owner(sp, line):
    return next((f for f, (a, b) in sp.items() if a <= line <= b), None)


def drop_functions(tree, names):
    """Remove the named functions and methods; returns how many."""
    gone = 0
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            keep = [m for m in n.body if not (isinstance(m, ast.FunctionDef) and f"{n.name}.{m.name}" in names)]
            gone += len(n.body) - len(keep)
            n.body = keep
    keep = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name in names)]
    gone += len(tree.body) - len(keep)
    tree.body = keep
    return gone


def provenance():
    t0 = time.time()
    BUILD.mkdir(parents=True, exist_ok=True)
    arch = receiver_arch()
    log(f"(a) receiver_arch.py rebuilt by make_arch.build(False): byte-identical to the record "
        f"({len(arch.encode())} B, sha256 {sha(arch)[:16]})")
    ret, t_old, t_new = retarget(arch)
    (BUILD / "c_retarget.py").write_text(ret)
    edges = check_edges(BUILD / "c_retarget.py", ROW_NEW)
    assert edges["identical"] and edges["format_id"] == "holo/v2/1i200-k-r0547-p100-v1@35x24", edges
    ming_old = calibrate_minifier()
    ld = literal_diff(ming_old, MS.minify(ret, True))
    assert len(ld) == 2 and "r0550" in ld[0][0] and "r0547" in ld[0][1], [(a[:40], b[:40]) for a, b in ld]
    log(f"(b) retarget: table {t_old['hex_digits']} -> {t_new['hex_digits']} hex digits "
        f"({t_old['lines']} -> {t_new['lines']} lines); checks == holo r0547 edges ({edges['edges']}); "
        f"FORMAT_ID {edges['format_id']}; minified-g against the record's: {len(ld)} literals differ "
        f"-> build/stage3/c_retarget.py ({len(ret.encode())} B, sha256 {sha(ret)[:16]})")
    src = SOURCE.read_text()
    a, b = ret.splitlines(keepends=True), src.splitlines(keepends=True)
    diff = list(difflib.unified_diff(a, b, "build/stage3/c_retarget.py", "bootstrap/stage3/c_readable.py", n=0))
    hunks, cur = [], None
    for ln in diff[2:]:
        if ln.startswith("@@"):
            o, nw = ln.split()[1:3]
            o0, oc = (o[1:].split(",") + ["1"])[:2]
            n0, nc = (nw[1:].split(",") + ["1"])[:2]
            cur = dict(head=ln.rstrip("\n"), old=(int(o0), int(oc)), new=(int(n0), int(nc)), minus=[], plus=[])
            hunks.append(cur)
        elif ln.startswith("-"):
            cur["minus"].append(ln[1:].rstrip("\n"))
        elif ln.startswith("+"):
            cur["plus"].append(ln[1:].rstrip("\n"))
    log(f"(f) c_retarget.py -> stage3/c_readable.py: {len(hunks)} hunks")
    for h in hunks:
        log("  " + h["head"])
        for x in h["minus"]:
            log("  -" + x)
        for x in h["plus"]:
            log("  +" + x)
    assert len(hunks) == PROVENANCE_HUNKS, (len(hunks), PROVENANCE_HUNKS)
    ta, tb = ast.parse(ret), ast.parse(src)
    da, db = module_doc_lines(ta), module_doc_lines(tb)
    doc = [h for h in hunks if db[0] <= h["new"][0] and h["new"][0] + h["new"][1] - 1 <= db[1]]
    code = [h for h in hunks if h not in doc]
    assert len(doc) == 5 and len(code) == 15, (len(doc), len(code))
    assert all(da[0] <= h["old"][0] <= da[1] for h in doc)
    assert "`python3 c.py`" in tb.body[0].value.value and "b.py`" not in tb.body[0].value.value
    # every changed code line inside a repaired function (old and new side) or the
    # heartbeat, a pure insertion in unz; a deletion's anchor line counts as changed
    sa, sb = spans(ta), spans(tb)
    src_lines = src.splitlines()
    alpha = [h for h in code if (h["minus"], h["plus"]) == ([ALPHA_LINE[0]], [ALPHA_LINE[1]])]
    assert len(alpha) == 1 and owner(sa, alpha[0]["old"][0]) is None and owner(sb, alpha[0]["new"][0]) is None
    alpha[0]["functions"], where = [], {"LDPC_ALPHA (module level)": 1}
    for h in code:
        if h is alpha[0]:
            continue
        (o0, oc), (n0, nc) = h["old"], h["new"]
        old = [owner(sa, o0 + k) for k in range(oc)]
        new = [owner(sb, n0 + k) for k in range(nc) if src_lines[n0 + k - 1].strip()] or [owner(sb, n0)]
        h["functions"] = sorted({f for f in old + new if f})
        assert set(old + new) <= REPAIRED | {"unz"}, (h["head"], old, new)
        assert "unz" not in old + new or (not h["minus"] and set(new) == {"unz"}), h["head"]
        for f in h["functions"]:
            where[f] = where.get(f, 0) + 1
    beat = [h for h in code if "unz" in h["functions"]]
    assert len(beat) == 1, len(beat)
    added = [x for h in code for x in h["plus"]]
    assert sum(x.count("print(") for x in added) == 3, added      # progress, dpi fallback, heartbeat
    assert not any("print(" in x for h in code for x in h["minus"])
    assert not any("print(" in x for h in doc for x in h["plus"] + h["minus"])
    for t in (ta, tb):
        t.body = t.body[1:]
    removed = drop_lines(tb, {beat[0]["new"][0] + k for k in range(beat[0]["new"][1])})
    assert removed == 1, removed                   # the heartbeat's if
    gone = drop_functions(ta, REPAIRED), drop_functions(tb, REPAIRED)
    assert gone == (4, 6), gone                    # aperture and track are new
    for t, v in ((ta, 0.75), (tb, 0.8)):            # the alpha: the one literal changed outside
        a_ = [n for n in t.body if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "(LDPC_ITERS, LDPC_ALPHA)"]
        assert len(a_) == 1 and ast.literal_eval(a_[0].value) == (50, v), ast.dump(a_[0].value)
        a_[0].value.elts[1].value = 0.8
    assert ast.dump(ta) == ast.dump(tb), "the source differs from the retarget outside the repaired functions"
    log(f"  docstring hunks {len(doc)}, code hunks {len(code)} by function "
        f"{', '.join(f'{f} {n}' for f, n in sorted(where.items()))}; {len(added)} lines added, 3 print calls; "
        f"with the docstrings, the heartbeat and the {len(REPAIRED)} repaired functions dropped and the "
        f"retarget's alpha 0.75 set to 0.8 the two trees are ast-identical; {time.time() - t0:.0f} s")
    (BUILD / "provenance.diff").write_text("".join(diff))
    (BUILD / "provenance.json").write_text(json.dumps(dict(
        arch=dict(bytes=len(arch.encode()), sha256=sha(arch)), table_r0550=t_old, table_r0547=t_new,
        edges=edges, literal_diff=len(ld), retarget=dict(bytes=len(ret.encode()), sha256=sha(ret)),
        source=dict(path=str(SOURCE.relative_to(ROOT)), bytes=len(src.encode()), sha256=sha(src)),
        hunks=hunks, docstring_hunks=len(doc), code_hunks=len(code), code_hunks_by_function=where,
        repaired_functions=sorted(REPAIRED), statements_inserted_outside=removed, alpha_hunk=alpha[0]["head"],
        ast_identical_otherwise=True), indent=1) + "\n")
    (BUILD / "provenance.log").write_text("\n".join(LOG) + "\n")


def pipeline(ming, pb, pbuild, ex, tag="r0547"):
    """(d) under the primer PB: M1, M2, M3 and the static checks of (e); the
    forms into build/stage3/forms/TAG.*.  -> (c.py text, its record)."""
    sc = Scorer(pb)
    log(f"(d) primer ({len(pb)} B, sha256 {sha(pb)[:16]}, orders {tuple(pbuild['orders'])}, "
        f"N2 {pbuild['n2']} B2 {pbuild['b2']}): r0547 minified-g {sc(ming) / 8:.1f} B ideal")
    m1, r1 = m1_inline(ming, sc, ex)
    (FORMS / f"{tag}.m1.py").write_text(m1)
    assert m1_equivalent(ming, m1, r1["steps"])
    log(f"  M1: {len(r1['steps'])} aliases inlined, {r1['start_bits'] / 8:.1f} -> {r1['end_bits'] / 8:.1f} B "
        f"ideal; ast-equivalent")
    m2, r2 = m2_rename(m1, pb)
    (FORMS / f"{tag}.m2.py").write_text(m2)
    e2 = rename_equivalent(m1, m2)
    assert not e2["renamed_attributes"]
    log(f"  M2: {r2['end_bits'] / 8:.1f} B ideal; {e2['renamed_bindings']} bindings renamed, bijective")
    m3, r3 = m3_attrs(m2, sc, ex)
    e3 = rename_equivalent(m2, m3)
    assert e3["renamed_attributes"] == r3["map"], (e3["renamed_attributes"], r3["map"])
    e23 = rename_equivalent(m1, m3)
    log(f"  M3: {len(r3['map'])} attributes renamed, {r3['start_bits'] / 8:.1f} -> {r3['end_bits'] / 8:.1f} B "
        f"ideal; M1 -> c.py: {e23['renamed_bindings']} bindings + {len(e23['renamed_attributes'])} attributes, "
        "bijective")
    compile(m3, "c.py", "exec")
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(ast.parse(m3))) \
        and "__import__" not in m3, "an import in c.py"
    return m3, dict(primer=dict(bytes=len(pb), sha256=sha(pb), orders=list(ORDERS), n2=pbuild["n2"],
                                b2=pbuild["b2"], typed_total=pbuild["typed_total"],
                                r2_payload_bytes=pbuild["r2_payload_bytes"]),
                    m1=dict(r1, bytes=len(m1.encode()), sha256=sha(m1)),
                    m2=dict(r2, bytes=len(m2.encode()), sha256=sha(m2), equivalence=e2),
                    m3=dict(r3, bytes=len(m3.encode()), sha256=sha(m3), equivalence=e3), m1_to_c=e23)


def main():
    t0 = time.time()
    FORMS.mkdir(parents=True, exist_ok=True)
    rec = {}
    readable = SOURCE.read_text()
    edges = check_edges(SOURCE, ROW_NEW)
    assert edges["identical"] and edges["format_id"] == "holo/v2/1i200-k-r0547-p100-v1@35x24", edges
    log(f"(b') source stage3/c_readable.py ({len(readable.encode())} B, sha256 {sha(readable)[:16]}): "
        f"checks == holo r0547 edges ({edges['edges']}); FORMAT_ID {edges['format_id']}")
    rec.update(edges=edges, readable=dict(path=str(SOURCE.relative_to(ROOT)), bytes=len(readable.encode()),
                                          sha256=sha(readable)))
    ming_old = calibrate_minifier()
    ming = MS.minify(readable, True)
    (FORMS / "r0550.minified-g.py").write_text(ming_old)
    (FORMS / "r0547.minified-g.py").write_text(ming)
    log(f"(c) minified-g: r0550 {len(ming_old.encode())} B (== the record's form), r0547 {len(ming.encode())} B")
    rec.update(minified_r0550=dict(bytes=len(ming_old.encode()), sha256=sha(ming_old),
                                  record_form=str(RECORD_MING.relative_to(ROOT))),
               minified_r0547=dict(bytes=len(ming.encode()), sha256=sha(ming)))
    ex = ThreadPoolExecutor(WORKERS)
    out = HERE / "c.py"
    prev = out.read_text()
    pb, pbuild = primer()
    m3, rp = pipeline(ming, pb, pbuild, ex)
    rec.update(rp, primer=dict(rp["primer"], path=str(PRIMER.relative_to(ROOT))))
    cycle = None
    if m3 != prev:                                # (d'): is the tree's c.py the output's own output?
        tmp = BUILD / "c_partner.py"
        tmp.write_text(m3)
        qb, qbuild = primer(tmp, PARTNER)
        back, rq = pipeline(ming, qb, qbuild, ex, "r0547.partner")
        rank = lambda b: (b["typed_total"], b["r2_payload_bytes"])   # noqa: E731
        cycle = dict(found=back == prev, back_sha256=sha(back), back_bytes=len(back.encode()),
                     tree=dict(sha256=sha(prev), typed_total=pbuild["typed_total"],
                               r2_payload_bytes=pbuild["r2_payload_bytes"]),
                     output=dict(sha256=sha(m3), typed_total=qbuild["typed_total"],
                                 r2_payload_bytes=qbuild["r2_payload_bytes"]),
                     partner_pipeline=rq)
        if back == prev:
            keep = "output" if rank(qbuild) < rank(pbuild) else "tree"
            cycle["kept"] = keep
            log(f"(d') two-cycle: the output {sha(m3)[:16]} (its chain: typed {qbuild['typed_total']}, R2 "
                f"{qbuild['r2_payload_bytes']} B) generates the tree's {sha(prev)[:16]} (typed "
                f"{pbuild['typed_total']}, R2 {pbuild['r2_payload_bytes']} B); kept: the {keep}'s")
            if keep == "tree":               # r0547.* = the kept c.py's own lineage, the output's partner.*
                m3 = prev
                for k in ("m1", "m2"):
                    a, b = FORMS / f"r0547.{k}.py", FORMS / f"r0547.partner.{k}.py"
                    ta, tb = a.read_text(), b.read_text()
                    a.write_text(tb)
                    b.write_text(ta)
                rec.update({k: rq[k] for k in ("m1", "m2", "m3", "m1_to_c")},
                           primer=dict(rq["primer"], path=str((PARTNER / "upper" / "b.py").relative_to(ROOT))))
                cycle["partner_pipeline"] = rp
        else:
            log(f"(d') no two-cycle: the output's own chain gives {sha(back)[:16]}, not the tree's; the output "
                "is written")
    same = prev == m3
    if not same:                                  # atomically: another job may be reading c.py
        tmp = HERE / ".c.py.make_c-tmp"
        tmp.write_text(m3)
        os.replace(tmp, out)
    rec.update(two_cycle=cycle, c_py=dict(bytes=len(m3.encode()), sha256=sha(m3), lines=len(m3.splitlines()),
                                          identical_to_previous=same),
               workers=WORKERS, wall_s=round(time.time() - t0, 1))
    (BUILD / "make_c.json").write_text(json.dumps(rec, indent=1) + "\n")
    (BUILD / "make_c.log").write_text("\n".join(LOG) + "\n")
    log(f"c.py {len(m3.encode())} B, sha256 {sha(m3)[:16]} ({'identical to' if same else 'new against'} the "
        f"previous c.py); {time.time() - t0:.0f} s")


if __name__ == "__main__":
    provenance() if "--provenance" in sys.argv else main()
