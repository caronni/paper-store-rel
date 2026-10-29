#!/usr/bin/env python3
"""build.py -- one command builds today's typed rung and its R2 pages
(the build of R2-FORMAT v1, 2026-10-20, run on today's files).

  python3 bootstrap/build.py [--reader PATH] [--fast] [--record]

--reader PATH  the stage-2 reader the loader carries; default
               r2reader/reader_lite_v1.py, today's typed reader.
--fast         skips the envelope and damage renders and their reads.
--record       also REPLACES the print of record (tracked files) with this
               build: make_typed copies a.py, data.txt and codes.txt into
               loader/ and bakes the print's constants into
               loader_readable.py; pages/leaf3.txt and leaf4.txt are
               rewritten in place; pages/r2/ receives the records of the
               pages (sidecars, payload, bundle, SHA256SUMS; no bitmap, no
               render).  Default off: the files in loader/ and pages/ are the
               print of record of 2026-10-20 and stay as they are.  A --record
               run would replace them with today's build, and its payload.json
               would record build/build-py/ paths where the record says build/.

What it builds: today's chain -- today's reader (--reader), the bundle of
the current R2-FORMAT.md and r2reader/reader.py (60,242 B, 4 pages on
2026-10-23).  Neither the default run nor --record reproduces the 10-20
print: its bundle (55,550 B, 3 pages) holds R2-FORMAT.md as it was on 10-20.

Everything goes to bootstrap/build/build-py/ (gitignored; BUILD below, the
module constant): bundle/, loader/, r2/, the leaves, the PDF, SHA256SUMS;
every later stage reads the typed files from BUILD/loader/ (make_typed
--no-record without --record).  Nothing in bootstrap/build/ outside build-py/
is written: its bundle/, loader/, r2/ and the files beside them are the 10-20 record,
which stage1/make_typed.py, the edge instruments and others read as the
bundle of record; build/w1, w2, w3 (the builders' own work) are never
touched either.  The stage names (ruling 34)
come from the reader's two file literals: today's reader opens its primer as
b.py and writes c.py, so r.py (what the 10-20 a.py writes) is saved as b.py
and c.py is compared with the bundle; a reader with the older literals (r.py,
b.py) is run as before.  Order (the pages' primer is r.py, which needs the
reader's final text):

 1. reader    r2reader/count_reader.py audits the typed text of the stage-2
              reader; a violation stops the build;
 2. bundle    BUILD/bundle/b.py = a module docstring holding R2-FORMAT.md
              (refused unless the docstring gives the text back exactly) +
              the full text of r2reader/reader.py, shared region included,
              so b.py runs as a reader by itself;
 3. typed     loader/make_typed.py (v3) --reader R --bundle b.py --out
              BUILD/loader: a.py, data.txt, codes.txt, r.py (a.py's
              definitions + the reader = the pages' primer, binary),
              build.json, the proofs; then the reader's sizes: raw, the cm2
              v2 state x with a.py as primer (bits, bytes), base-32 glyphs G;
 4. pages     payload = cm2 v2 (typed/cm2_enc.py, orders read from
              typed/cm2_dec.py) of b.py with primer r.py: the state x as
              big-endian bytes, no length prefix (the v1 header carries
              length and CRC-32), round trip through typed/cm2_dec.py;
              r2/gen.py pages -> BUILD/r2/page_p{P}.*; r2/verify_grid.py
              over all pages with the payload and --pbm.  gen.py's contract:
              exit status 3 = the payload's header would also pass its check
              read turned; then one newline is appended to b.py and stages
              2-4 run again (N2 and B2 follow the bundle), at most PAD_TRIES
              times; the pad is recorded in bundle.json and payload.json;
              status 4 (empty) or 5 (> 65,535 B) stops the build;
 5. renders   r2/camera.py, truth sidecar beside every render.  Every page:
              flatbed300, nominal (2 spm) blur .30 and .45, hard (1.5 spm)
              blur .30; the four quarters and the centre at 3 spm blur .45
              persp 2 %, the bottom-right quarter at 2 spm.  Page 0 on
              nominal-b030: rot90 1-3 (rot90 0 is nominal-b030 itself) and
              +-4 deg; the envelope (persp 0/2/4 %, blur .3/.4, spm 1.5/2.0,
              seeds 1-3); the damage set (camera.py --damage, seed 101);
 6. reads     the finder's way: BUILD/loader/r.py copied into a scratch
              directory under the primer name the reader opens (b.py) and run,
              the frames' paths on stdin, one capture set per read; closed =
              c.py (the reader's output) written and byte-identical to
              BUILD/bundle/b.py.  Sets: every whole-page capture alone
              (since the copies went across pages, 2026-10-20 night, a
              page of a 2- or 3-page payload carries every chunk and may
              close alone: counted in a row of its own, never in the
              total; otherwise its chunks held are recorded); every quarter
              and the centre alone (never expected to close); all
              pages per base capture; the four quarters of every page
              pooled; the rot90, +-4 deg and damage captures with the other
              pages' nominal-b030; the loupe grid of page 0 with the other
              pages' nominal-b030, and every page's grid (a reader that
              reads PGM only gets page_p{P}.grid.pgm, the grid through the
              Plate's one-liner r2reader/grid_to_pgm.py).  The bundle is also
              run as a reader on every page's grid, saved as c.py (it carries
              r2reader/reader.py, whose N2 and B2 are never baked: it reads
              the grids and stops at NameError N2, as on 10-20; reported, not
              a check).  -> BUILD/r2/reads.json + reads.md,
              BUILD/bundle/b_as_reader.json;
 7. e2e       loader/e2e_pipe.py --reader R --bundle b.py --out BUILD/loader
              --typed BUILD/loader --page (every page's nominal-b030, in
              order) --done N/N ('done' for a reader that prints the flag):
              a.py and the data typed through pipes on two interpreters and
              a pty, then the typed r.py, saved as b.py, run once on all the
              pages (its last progress line ends with N/N, c.py == the
              bundle) -> BUILD/e2e.txt (its walls masked); 7b: the typed
              chain once, plainly -- BUILD/loader/a.py run as python3 a.py
              on data.txt, its r.py == BUILD/loader/r.py, that r.py as b.py
              on every page's nominal-b030, c.py == the bundle; and the
              negative: the same r.py re-saved with CRLF line ends must exit
              1 at its B2 assert (AssertionError) and write no c.py ->
              BUILD/typed_chain.json;
 8. leaves    pages/compose_leaves.py --loader BUILD/loader --out BUILD --r2
              BUILD/r2 -> BUILD/leaf3.txt, leaf4.txt and
              BUILD/bootstrap-leaves.pdf:
              plate leaves 1, 2, 2b, leaf 3, leaf 4, then every page bitmap
              (its overt leaf header set in type below the grid) followed by
              its nominal-b030 render (--record: pages/leaf3.txt, leaf4.txt
              from loader/, copied to BUILD/);
 9. sums      BUILD/r2/SHA256SUMS; BUILD/SHA256SUMS over every output (with
              --record also the tracked files and pages/r2/, which it then
              writes), compared with the previous run's file.
Deterministic: a second run reproduces every file in SHA256SUMS byte for
byte.  Walls are printed and kept in BUILD/walls/ (with e2e_pipe's raw log),
the one directory outside the sums.
"""
import ast
import concurrent.futures as cf
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zlib

ROOT =os.path.dirname(os.path.abspath(__file__))
# The default run's own output root, never build/ itself: build/bundle, loader/, r2/ and the
# files beside them are the 10-20 record that other instruments read as the bundle of record.
BUILD = os.path.join(ROOT, 'build', 'build-py')
RB = os.path.relpath(BUILD, ROOT)          # 'build/build-py', for records and messages
R2B = os.path.join(BUILD, 'r2')
BUN = os.path.join(BUILD, 'bundle')
LOUT = os.path.join(BUILD, 'loader')
TMP = os.path.join(BUILD, 'tmp')
WALLS = os.path.join(BUILD, 'walls')
REC = os.path.join(ROOT, 'pages', 'r2')
PY = 'env/bin/python'
JOBS = 8
for d in ('typed', 'r2', 'loader'):
    sys.path.insert(0, os.path.join(ROOT, d))
import cm2_dec  # noqa: E402
import cm2_enc  # noqa: E402
import gen  # noqa: E402
import make_typed  # noqa: E402

ORDERS = cm2_enc.orders_of(os.path.join(ROOT, 'typed', 'cm2_dec.py'))
READER = os.path.join(ROOT, 'r2reader', 'reader_lite_v1.py')      # default --reader
BUNDLED = os.path.join(ROOT, 'r2reader', 'reader.py')             # the reader inside b.py
FORMAT_MD = os.path.join(ROOT, 'R2-FORMAT.md')
MINE_DIRS = ('r2', 'bundle', 'loader')
MINE_FILES = ('tools.json', 'readers.json', 'e2e.txt', 'typed_chain.json', 'leaf3.txt',
              'leaf4.txt', 'bootstrap-leaves.pdf')
TOOLS = ('R2-FORMAT.md', 'r2reader/reader.py', 'r2reader/count_reader.py', 'typed/cm2_dec.py',
         'typed/cm2_enc.py', 'loader/make_typed.py', 'loader/e2e_pipe.py', 'r2/gen.py',
         'r2/verify_grid.py', 'r2/camera.py', 'r2/damage.py', 'pages/compose_leaves.py',
         'pages/render_pdf.py', 'build.py')

NOM = ['--preset', 'nominal']
NOM30 = NOM + ['--blur', '0.30']
Q3 = NOM + ['--spm', '3', '--blur', '0.45', '--persp', '0.02']
BASE = [('flatbed300', ['--preset', 'flatbed300']),
        ('nominal-b030', NOM30),
        ('nominal-b045', NOM + ['--blur', '0.45']),
        ('hard-b030', ['--preset', 'hard', '--blur', '0.30'])]
QUARTERS = ('tl', 'tr', 'bl', 'br')
PARTS = [(f'q-{f}', Q3 + ['--frame', f]) for f in QUARTERS] + [
    ('centre', Q3 + ['--frame', 'centre']),
    ('q-br-2spm', NOM + ['--spm', '2', '--blur', '0.45', '--persp', '0.02', '--frame', 'br'])]
TURNS = [(f'rot90-{k}', NOM30 + ['--rot90', str(k)]) for k in (1, 2, 3)] + [
    ('rot+4', NOM30 + ['--rotate', '4']), ('rot-4', NOM30 + ['--rotate', '-4'])]
ENV = [(spm, pe, bl, sd) for spm in ('1.5', '2.0') for pe in ('0', '0.02', '0.04')
       for bl in ('0.3', '0.4') for sd in ('1', '2', '3')]
DAMAGE = ['be:0', 'be:all', 'bt:7', 'blot:3', 'ring-centre', 'ring-bullseye:0',
          'scratch-h-white', 'scratch-d-dark', 'torn:3', 'crop-T']
# One progress line per frame, after the input prompt.  The readable reader:
# 'NAME: NOTE, 615 blocks accepted, chunks 204 / 211 - more frames needed';
# the diet reader (the contract from 2026-10-20 on): 'NAME: 615 blocks
# accepted, chunks 408 / 452 more' or '... done'; the typed reader from
# 2026-10-22 on (ruling 54) 'NAME: 615 blocks, chunks 408 / 452 more', the
# older readers keep 'accepted' (both parse).  NOTE and '- ' optional.
PAD_TRIES = 8              # gen.py orientation refusals tolerated (about 6 in 2**20 each)
PROGRESS = re.compile(r'([^:]*): (?:([^:]*), )?(\d+) blocks(?: accepted)?, chunks (\d+) / (\S+) '
                      r'(?:- )?(done|more frames needed|more)\s*$')
# The typed reader from ruling 56 on (amended 2026-10-22): '9@ 500/557'
# after its prompt -- the seeds found, '@', chunks held / the header's total
# ('?' before a header) -- no name, no blocks count, no flag; 'cannot read'
# alone for a file that fails to load.  The older wordings still parse.
PROGRESS56 = re.compile(r'(?:^|\s)(\d+)@ (\d+)/(\S+)\s*$')
CANNOT56 = re.compile(r'(?:^|\s)cannot read\s*$')
WALL = {}
RECORD = False             # --record: also rewrite the print of record (tracked files)


def progress_lines(stdout, frames):
    """Per frame [name, note, blocks, held, total, flag] from a reader's
    stdout, every wording.  The older lines name the frame and carry the
    blocks and the flag.  The 9@ line (ruling 56) names no frame -- it is
    the frame typed in its turn -- and has no blocks (None) and no flag:
    'done' when held == total (the reader's own done signal is its exit with
    the output written), 'more' otherwise; 'cannot read' alone keeps the
    session's held and total."""
    per = []
    for ln in stdout.split('\n'):
        m = PROGRESS.search(ln)
        if m:
            per.append([m[1].strip(), m[2] or '', int(m[3]), int(m[4]),
                        int(m[5]) if m[5].isdigit() else m[5], m[6]])
            continue
        m, c = PROGRESS56.search(ln), CANNOT56.search(ln)
        if m or c:
            name = frames[len(per)] if len(per) < len(frames) else '?'
            if m:
                held, tot = int(m[2]), int(m[3]) if m[3].isdigit() else m[3]
                per.append([name, m[1] + '@', None, held, tot, 'done' if held == tot else 'more'])
            else:
                held, tot = (per[-1][3], per[-1][4]) if per else (0, '?')
                per.append([name, 'cannot read', None, held, tot, 'more'])
    return per


def sha(b):
    return hashlib.sha256(b).hexdigest()


def rd(p, mode='rb'):
    with open(p, mode) as f:
        return f.read()


def wr(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb' if isinstance(data, bytes) else 'w') as f:
        f.write(data)


def run(argv, ok=(0,), **kw):
    p = subprocess.run(argv, capture_output=True, text=True, **kw)
    if p.returncode not in ok:
        sys.exit(f'FAILED {argv}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}')
    return p


def stage(n, what):
    t = time.time()
    print(f'[{n}] {what}', flush=True)
    return t


def walled(key, t0):
    WALL[key] = round(time.time() - t0, 1)


def stage_names(path):
    """(the primer file the reader opens, the file it writes), read from its
    two file literals: ('r.py', 'b.py') before ruling 34, ('b.py', 'c.py')
    after (the stages named by the program each yields)."""
    s = rd(path).decode()
    p = re.findall(r"open\('(\w\.py)', ?'rb'\)", s)
    w = re.findall(r"open\('(\w\.py)', ?'wb'\)", s)
    assert len(p) == len(w) == 1, (os.path.relpath(path, ROOT), 'primer / output literals', p, w)
    return p[0], w[0]


# ---- 1. reader -------------------------------------------------------------
def stage_audit(reader):
    p = run([PY, os.path.join(ROOT, 'r2reader', 'count_reader.py'), reader], ok=(0, 1))
    line = p.stdout.strip().split('\n')[0]
    print('   ' + p.stdout.strip().replace('\n', '\n   '))
    if p.returncode:
        sys.exit(f'stage-2 reader {os.path.relpath(reader, ROOT)} fails the typed-subset audit')
    return line


# ---- 2. bundle -------------------------------------------------------------
def stage_bundle(pad=0):
    """b.py = the docstring + the readable reader + pad newlines (gen.py's
    contract: each orientation refusal of the payload adds one)."""
    fmt = rd(FORMAT_MD).decode('utf-8')
    src = rd(BUNDLED).decode('utf-8')
    doc = '"""' + fmt + '"""\n'
    tree = ast.parse(doc + src)
    if '"""' in fmt or ast.get_docstring(tree, clean=False) != fmt:
        sys.exit('R2-FORMAT.md does not survive as a docstring (a triple double quote, a '
                 'backslash sequence or a closing double quote): refused')
    compile(doc + src + '\n' * pad, 'b.py', 'exec')
    b = (doc + src + '\n' * pad).encode('utf-8')
    wr(os.path.join(BUN, 'b.py'), b)
    rec = dict(file=f'{RB}/bundle/b.py', bytes=len(b), sha256=sha(b), pad_newlines=pad,
               parts=[dict(what='module docstring: the text of R2-FORMAT.md',
                           file='R2-FORMAT.md', bytes=len(fmt.encode()), sha256=sha(fmt.encode())),
                      dict(what='the full text of the readable reader (shared region included)',
                           file=os.path.relpath(BUNDLED, ROOT), bytes=len(src.encode()),
                           sha256=sha(src.encode()))],
               docstring_check='ast docstring of b.py == R2-FORMAT.md text, exactly')
    wr(os.path.join(BUN, 'bundle.json'), json.dumps(rec, indent=1) + '\n')
    return b, rec


# ---- 3. typed --------------------------------------------------------------
def stage_typed(reader, bpy):
    p = run([PY, os.path.join(ROOT, 'loader', 'make_typed.py'), '--reader', reader,
             '--bundle', bpy, '--out', LOUT] + ([] if RECORD else ['--no-record']))
    print('   ' + p.stdout.strip().replace('\n', '\n   '))
    for f in ('a.py', 'data.txt', 'codes.txt') if RECORD else ():   # make_typed's print of record
        assert rd(os.path.join(ROOT, 'loader', f)) == rd(os.path.join(LOUT, f)), \
            f'loader/{f} differs from {RB}/loader/{f}'
    return rd(os.path.join(LOUT, 'a.py')).decode(), rd(os.path.join(LOUT, 'r.py'))


def stage_sizes(reader, apy, bundle, audit_line):
    """The reader as make_typed types it: N2 = the bundle's length, B2 = its
    CRC-32 (make_typed.bundle_crc's rule, zlib.crc32 of the file's bytes)."""
    n2, b2 = len(bundle), zlib.crc32(bundle)
    text = make_typed.reader_text(reader, n2, b2).encode()
    x = cm2_enc.encode_int(text, apy.strip().encode(), ORDERS)
    G = len(make_typed.b32(x))
    codes = rd(os.path.join(LOUT, 'codes.txt')).decode()
    g, bits = map(int, re.search(r'G (\d+) base-32 glyphs = x of (\d+) bits', codes).groups())
    assert (g, bits) == (G, x.bit_length()), ('x differs from make_typed\'s', g, bits, G)
    al = apy.strip('\n').split('\n')
    dl = rd(os.path.join(LOUT, 'data.txt')).decode().split('\n')[:-1]
    full = rd(reader)
    rec = dict(file=os.path.relpath(reader, ROOT), file_bytes=len(full), file_sha256=sha(full),
               count_reader=audit_line, n2=n2, b2=b2,
               typed_text=dict(what='make_typed.reader_text: region, shared region dropped, N2 replaced',
                               bytes=len(text), sha256=sha(text)),
               cm2_v2=dict(primer='a.py text, stripped', orders=list(ORDERS),
                           x_bits=x.bit_length(), x_bytes=(x.bit_length() + 7) // 8),
               base32_glyphs=G,
               apy=dict(lines=len(al), chars=sum(map(len, al))),
               data=dict(lines=len(dl), chars=sum(map(len, dl))),
               typed_chars=sum(map(len, al)) + sum(map(len, dl)),
               typed_chars_rule='a.py + data.txt characters, newlines not counted')
    assert f"typed chars {rec['typed_chars']}" in codes, 'typed characters differ from codes.txt'
    wr(os.path.join(BUILD, 'readers.json'), json.dumps(rec, indent=1) + '\n')
    return rec


# ---- 4. pages --------------------------------------------------------------
def compress(bundle, rpy):
    """The pages' data: cm2 v2 of the bundle with primer r.py, x as bytes."""
    return cm2_enc.encode(bundle, rpy, ORDERS)


def stage_pages(bundle, rpy, refused=()):
    """-> (payload record, page sidecars), or None when gen.py refuses the
    payload for its orientation (exit status 3; nothing written): the caller
    pads the bundle and comes back.  Any other refusal stops the build."""
    z = compress(bundle, rpy)
    wr(os.path.join(R2B, 'payload.bin'), z)
    npages, cap = gen.n_pages(len(z)), gen.geometry()['capacity_bytes']
    p = run([PY, os.path.join(ROOT, 'r2', 'gen.py'), 'pages', 'payload.bin', 'page'],
            ok=(0, gen.EXIT_ORIENTATION), cwd=R2B)
    if p.returncode == gen.EXIT_ORIENTATION:
        return None, dict(payload_sha256=sha(z), payload_bytes=len(z),
                          gen_stderr=p.stderr.strip().split('\n')[-1][:300])
    print('   ' + p.stdout.strip().replace('\n', '\n   '))
    assert cm2_dec.decode(z, len(bundle), rpy) == bundle, 'cm2 round trip failed'
    grids = [f'page_p{q}.grid.txt' for q in range(npages)]
    v = run([PY, os.path.join(ROOT, 'r2', 'verify_grid.py')] + grids
            + ['--payload', 'payload.bin', '--pbm'], ok=(0, 1), cwd=R2B)
    wr(os.path.join(R2B, 'verify.txt'), v.stdout)
    print('   verify_grid: ' + v.stdout.strip().split('\n')[-1])
    if v.returncode:
        sys.exit('verify_grid FAILED:\n' + v.stdout[-3000:])
    sides = [json.load(open(os.path.join(R2B, f'page_p{q}.json'))) for q in range(npages)]
    rec = dict(format='R2v1', spec='bootstrap/R2-FORMAT.md v1 (2026-10-20)', pages=npages,
               capacity_bytes_per_page=cap, capacity_bytes=cap * npages,
               payload_bytes=len(z), payload_sha256=sha(z), headroom_bytes=cap * npages - len(z),
               chunks=gen.n_chunks(len(z)), chunks_per_page=[s['chunk_count'] for s in sides],
               chunks_on_page=[s['chunks_on_page'] for s in sides],
               band_groups=[[b['group'] for b in s['band_groups']] for s in sides],
               fourth_group=[s['fourth_group'] for s in sides],
               fourth_copies=[s['fourth_copies'] for s in sides],
               white_slots=[s['white_slots'] for s in sides],
               data_crc32=sides[0]['data_crc32'],
               bundle=dict(file=f'{RB}/bundle/b.py', bytes=len(bundle), sha256=sha(bundle)),
               primer=dict(file=f'{RB}/loader/r.py', bytes=len(rpy), sha256=sha(rpy),
                           what="what a.py writes: the loader's definitions + the reader"),
               coder=dict(what='cm2 v2, big-integer rANS (typed/cm2_enc.py)', orders=list(ORDERS)),
               container='the coder state x as big-endian bytes, minimal length, no length '
                         'prefix: the header in the bullseye blocks carries the length and the '
                         'CRC-32',
               round_trip='typed/cm2_dec.py decode(payload, len(b.py), r.py) == b.py',
               bundle_pad_newlines=len(refused),
               refused_by_gen=list(refused),
               refusal_rule='gen.py exit status 3 (the header also passes its check read '
                            'turned): one newline appended to b.py, make_typed again (N2, B2 '
                            'follow the bundle), compress again, gen.py again; at most '
                            f'{PAD_TRIES} tries')
    wr(os.path.join(R2B, 'payload.json'), json.dumps(rec, indent=1) + '\n')
    return rec, sides


# ---- 5. renders ------------------------------------------------------------
def render_list(npages, fast):
    out = []

    def add(p, cls, tag, group, args, seed='1', sub=''):
        out.append(dict(name=f'p{p} {tag}', page=p, cls=cls, tag=tag, group=group,
                        file=f'{sub}page_p{p}.{tag}.pgm', argv=args + ['--seed', seed]))
    for p in range(npages):
        for t, a in BASE:
            add(p, 'base', t, f'p{p} {t}', a)
        for t, a in PARTS:
            add(p, 'part', t, f'p{p} {t}', a)
    for t, a in TURNS:
        add(0, 'turn', t, f'p0 {t}', a)
    if not fast:
        for spm, pe, bl, sd in ENV:
            add(0, 'env', f'env-s{spm}-p{pe}-b{bl}-r{sd}',
                f'p0 envelope spm {spm} persp {float(pe) * 100:g} % blur {bl}',
                NOM + ['--spm', spm, '--persp', pe, '--blur', bl], sd, 'env/')
        for k in DAMAGE:
            add(0, 'damage', 'dmg-' + k.replace(':', ''), f'p0 damage {k}',
                NOM30 + ['--damage', k], '101', 'damage/')
    return out


def stage_renders(rs):
    for d in ('env', 'damage'):
        os.makedirs(os.path.join(R2B, d), exist_ok=True)
    cam = os.path.join(ROOT, 'r2', 'camera.py')

    def one(r):
        p = r['page']
        run([PY, cam, f'page_p{p}.pbm', r['file'], '--sidecar', f'page_p{p}.json'] + r['argv'],
            cwd=R2B)
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(one, rs))
    rec = [dict(name=r['name'], file=r['file'], camera_args=r['argv'],
                sha256=sha(rd(os.path.join(R2B, r['file'])))) for r in rs]
    wr(os.path.join(R2B, 'renders.json'), json.dumps(rec, indent=1) + '\n')


def reads_grid_text(reader):
    """Whether the reader's typed text reads a typed module grid itself (its
    load tests for b'P5'); the readers of the 2026-10-22 change set on read
    P5 PGM only, and the Plate's one-liner turns the grid into one."""
    return "b'P5'" in make_typed.reader_text(reader, 1, 1)


def stage_plate_grids(npages):
    """page_p{P}.grid.pgm: the Plate's one-liner (r2reader/grid_to_pgm.py's
    last line, run as python3 -c LINE in a directory holding the grid as
    grid.txt), the loupe path of a reader that reads PGM only."""
    line = rd(os.path.join(ROOT, 'r2reader', 'grid_to_pgm.py')).decode().rstrip('\n').split('\n')[-1]
    for p in range(npages):
        w = tempfile.mkdtemp(prefix='plate-', dir=TMP)
        shutil.copyfile(os.path.join(R2B, f'page_p{p}.grid.txt'), os.path.join(w, 'grid.txt'))
        run([PY, '-c', line], cwd=w)
        shutil.copyfile(os.path.join(w, 'grid.pgm'), os.path.join(R2B, f'page_p{p}.grid.pgm'))
        shutil.rmtree(w)


# ---- 6. reads --------------------------------------------------------------
def read_sets(rs, npages, grid='txt'):
    by = {r['name']: r for r in rs}
    sets, seen = [], set()

    def add(name, group, frames, pooled, part=False):
        if tuple(frames) not in seen:
            seen.add(tuple(frames))
            sets.append(dict(name=name, group=group, frames=frames, pooled=pooled, part=part))

    def others(p):
        return [by[f'p{q} nominal-b030']['file'] for q in range(npages) if q != p]
    for r in rs:
        if r['cls'] != 'part':
            add('alone: ' + r['name'], r['group'] + ' alone', [r['file']], False)
    for r in rs:
        if r['cls'] == 'part':
            add('alone: ' + r['name'], r['group'] + ' alone', [r['file']], False, True)
    for t, _ in BASE:
        add(f'all pages: {t}', f'all pages: {t}',
            [by[f'p{p} {t}']['file'] for p in range(npages)], True)
    add('all pages: four quarters pooled', 'all pages: four quarters of every page',
        [by[f'p{p} q-{f}']['file'] for p in range(npages) for f in QUARTERS], True)
    for r in rs:
        if r['cls'] in ('turn', 'damage'):
            add(f"{r['name']} + other pages nominal-b030",
                r['group'] + ' + other pages nominal-b030', [r['file']] + others(0), True)
    add('loupe: p0 grid + other pages nominal-b030', 'loupe: p0 grid + other pages nominal-b030',
        [f'page_p0.grid.{grid}'] + others(0), True)
    add('loupe: every page grid', 'loupe: every page grid',
        [f'page_p{p}.grid.{grid}' for p in range(npages)], True)
    return sets


def run_reader(prog, frames, bundle, name, writes):
    """PROG saved as NAME in a scratch directory (nothing else copied there)
    and run as python3 NAME, the frames' paths on stdin and an empty line;
    WRITES = the file whose bytes are compared with BUNDLE afterwards."""
    w = tempfile.mkdtemp(prefix='read-', dir=TMP)
    shutil.copyfile(prog, os.path.join(w, name))
    t0 = time.time()
    p = subprocess.run([PY, name], cwd=w, capture_output=True, text=True, timeout=3600,
                       input=''.join(os.path.join(R2B, f) + '\n' for f in frames) + '\n',
                       env={'PATH': '/usr/bin:/bin'})
    wall = time.time() - t0
    bp = os.path.join(w, writes)
    b = rd(bp) if os.path.exists(bp) else None
    shutil.rmtree(w)
    per = [[os.path.relpath(x[0], R2B)] + x[1:]
           for x in progress_lines(p.stdout, [os.path.join(R2B, f) for f in frames])]
    err = p.stderr.strip().split('\n')[-1].replace(w, '<work>') if p.stderr.strip() else ''
    if b is None:
        out = 'absent'
    elif bundle is None:
        out = f'{len(b)} B'
    elif b == bundle:
        out = 'identical'
    else:
        out = f'differs ({len(b)} B)'
    res = dict(rc=p.returncode, writes=writes, output=out, frames_read=len(per), per_frame=per,
               blocks=None if any(x[2] is None for x in per) else sum(x[2] for x in per),
               held=per[-1][3] if per else 0, need=per[-1][4] if per else '?', err=err)
    if not per:
        res['stdout_tail'] = p.stdout.strip()[-300:].replace(R2B + os.sep, '')
    return res, wall


def page_of(f):
    return int(re.search(r'page_p(\d+)\.', f).group(1))


def stage_reads(sets, bundle, sides, names):
    rpy = os.path.join(LOUT, 'r.py')
    npages = len(sides)
    on = [{c for c in s['slot_chunk'] if c is not None} for s in sides]
    nchunks = gen.n_chunks(sides[0]['data_len'])
    res, walls = {}, {}
    with cf.ThreadPoolExecutor(JOBS) as ex:
        futs = {s['name']: ex.submit(run_reader, rpy, s['frames'], bundle, *names) for s in sets}
    for s in sets:
        r, w = futs[s['name']].result()
        pages = sorted({page_of(f) for f in s['frames']})
        r.update(group=s['group'], frames=s['frames'], pages=pages, closed=r['output'] == 'identical',
                 expect_close=pages == list(range(npages)), part=s.get('part', False),
                 carries_all=len(set().union(*(on[p] for p in pages))) == nchunks)
        if len(pages) == 1:
            r['page_chunks'] = sides[pages[0]]['chunks_on_page']
            r['page_complete'] = r['held'] == r['page_chunks'] if len(pages) < npages else r['closed']
        res[s['name']] = r
        walls[s['name']] = [round(w, 1), len(s['frames'])]
    wr(os.path.join(R2B, 'reads.json'), json.dumps(res, indent=1, sort_keys=True) + '\n')
    wr(os.path.join(R2B, 'reads.md'), reads_table(sets, res, npages))
    # the bundle run as a reader by itself on every page's grid: saved as c.py,
    # the name the reader writes it under (ruling 34); its own output literal
    grids = [f'page_p{p}.grid.txt' for p in range(npages)]
    r, w = run_reader(os.path.join(BUN, 'b.py'), grids, None, 'c.py', stage_names(BUNDLED)[1])
    r['frames'] = grids
    r['note'] = (f"the bundle ({RB}/bundle/b.py) saved as c.py and run as 'python3 c.py' alone "
                 "in a scratch directory (no primer there); output = the file its own reader "
                 "text writes, after the run")
    wr(os.path.join(BUN, 'b_as_reader.json'), json.dumps(r, indent=1, sort_keys=True) + '\n')
    walls['the bundle as a reader: every page grid'] = [round(w, 1), len(grids)]
    return res, walls, r


def span(xs):
    if None in xs:   # the 9@ line prints no blocks (ruling 56)
        return '-'
    xs = sorted(xs)
    return f'{xs[0]}' if xs[0] == xs[-1] else f'{xs[0]}-{xs[-1]}'


def reads_table(sets, res, npages):
    groups = {}
    for s in sets:
        groups.setdefault(s['group'], []).append(res[s['name']])
    out = [f'Reads of {RB}/r2/ ({npages} page{"s" * (npages > 1)}): {RB}/loader/r.py, saved '
           'under the primer name the reader opens, fed the frames; closed = the file the reader '
           f'writes byte-identical to {RB}/bundle/b.py; page complete = every '
           'chunk printed on that page held; the total counts the sets that cover every page. '
           'A page carries the groups of its three bands: for P = 2 or 3 every chunk, so a '
           'whole-page capture of one page may close alone (its own row below the total; '
           'a quarter or the centre alone never closes). Since the copies went across pages '
           '(2026-10-20 night) a page holds ONE placed copy of each of its chunks, so page '
           'complete needs nearly every block of the page read; before, it meant its own 204 '
           'chunks '
           'from three copies each (48/81 on the last build before): not comparable.', '',
           '| capture set | reads | frames | closed | page complete | chunks held / N | '
           'blocks accepted |', '|---|---|---|---|---|---|---|']
    tot = [0, 0, 0, 0]
    for g, rs in groups.items():
        exp = [r for r in rs if r['expect_close']]
        pc = [r for r in rs if 'page_complete' in r]
        closed = f"{sum(r['closed'] for r in rs)}/{len(rs)}"
        if not exp:
            odd = any(r['closed'] and not (r['carries_all'] and not r['part']) for r in rs)
            closed = '-' if not any(r['closed'] for r in rs) else closed + ' (!)' * odd
        pcs = f"{sum(r['page_complete'] for r in pc)}/{len(pc)}" if pc else '-'
        need = sorted({str(r['need']) for r in rs})
        out.append(f"| {g} | {len(rs)} | {len(rs[0]['frames'])} | {closed} | {pcs} | "
                   f"{span([r['held'] for r in rs])} / {'/'.join(need)} | "
                   f"{span([r['blocks'] for r in rs])} |")
        tot[0] += len(exp)
        tot[1] += sum(r['closed'] for r in exp)
        tot[2] += len(pc)
        tot[3] += sum(r['page_complete'] for r in pc)
    out.append(f'| **total** | {len(res)} | | **{tot[1]}/{tot[0]}** closed of the sets that '
               f'cover every page | **{tot[3]}/{tot[2]}** | | |')
    one = [r for r in res.values() if len(r['pages']) == 1 < npages and r['carries_all']
           and not r['part']]
    if one:
        out.append(f"| single whole-page captures of a page that carries every chunk | "
                   f"{len(one)} | 1 | {sum(r['closed'] for r in one)}/{len(one)} (not in the "
                   f"total) | | {span([r['held'] for r in one])} | |")
    return '\n'.join(out) + '\n'


# ---- 7. e2e ----------------------------------------------------------------
def done_text(reader, nchunks):
    """The end of the reader's last progress line when the data closes: 'done'
    for the readers that print the flag, else 'N/N' (the 9@ line of ruling 56)."""
    return 'done' if re.search(r"['\"](- )?done['\"]", rd(reader).decode()) else f'{nchunks}/{nchunks}'


def stage_e2e(reader, bpy, npages, nchunks):
    pages = []
    for p in range(npages):
        pages += ['--page', os.path.join(R2B, f'page_p{p}.nominal-b030.pgm')]
    p = subprocess.run([PY, os.path.join(ROOT, 'loader', 'e2e_pipe.py'), '--reader', reader,
                        '--bundle', bpy, '--out', LOUT, '--typed', LOUT,
                        '--work', os.path.join(TMP, 'e2e')]
                       + pages + ['--done', done_text(reader, nchunks)], capture_output=True,
                       text=True)
    wr(os.path.join(WALLS, 'e2e-raw.log'), p.stdout + '\n--- stderr\n' + p.stderr)
    norm = re.sub(r'\d+\.\d+ s\b', '_ s', p.stdout)
    norm = re.sub(r'(work dir kept: ).*', r'\1<work>', norm)
    wr(os.path.join(BUILD, 'e2e.txt'), norm)
    checks = [ln.strip() for ln in p.stdout.split('\n') if ln.strip().startswith(('PASS', 'FAIL'))]
    return p.returncode, checks, p.stdout


def stage_typed_chain(bundle, npages, names):
    """The typed chain once, plainly (e2e_pipe injects the typing faults):
    BUILD/loader/a.py (== loader/a.py, the print of record, under --record)
    saved as a.py in a scratch directory and run as python3 a.py with
    BUILD/loader/data.txt on stdin; its self-dump == codes.txt, one prompt
    per line, silent exit, and the r.py it writes == BUILD/loader/r.py; then
    THAT r.py (run_reader copies it to a fresh directory, under the primer's
    name the reader opens) on every page's nominal-b030 -> the file the
    reader writes == the bundle."""
    w = tempfile.mkdtemp(prefix='chain-', dir=TMP)
    apy = rd(os.path.join(LOUT, 'a.py'))
    wr(os.path.join(w, 'a.py'), apy)
    data = rd(os.path.join(LOUT, 'data.txt')).decode()
    p = subprocess.run([PY, 'a.py'], cwd=w, input=data, capture_output=True, text=True,
                       timeout=3600, env={'PATH': '/usr/bin:/bin'})
    al = apy.decode().strip().split('\n')
    codes = rd(os.path.join(LOUT, 'codes.txt')).decode().split('\n')[:len(al)]
    out = p.stdout.split('\n')
    C = len(data.split('\n')) - 1
    rpy = os.path.join(w, 'r.py')
    got = rd(rpy) if os.path.exists(rpy) else None
    rec = dict(what=f'python3 a.py ({RB}/loader/a.py) fed {RB}/loader/data.txt; then the r.py '
                    f'it wrote, saved as {names[0]}, fed every page\'s nominal-b030',
               apy_rc=p.returncode, apy_stderr=p.stderr.strip().split('\n')[-1] if p.stderr.strip()
               else '', selfdump_equals_codes=out[:len(al)] == codes,
               prompts_then_silence='\n'.join(out[len(al):]) == ''.join(f'[{n}]' for n in
                                                                       range(1, C + 1)),
               rpy_bytes=len(got) if got else 0,
               rpy_equals_build_loader=got == rd(os.path.join(LOUT, 'r.py')))
    if got is not None:
        frames = [f'page_p{q}.nominal-b030.pgm' for q in range(npages)]
        r, wall = run_reader(rpy, frames, bundle, *names)
        rec['read'] = dict(frames=frames, **r)
        # the negative (ruling B2): the same r.py re-saved with CRLF line ends
        # is another primer; the reader must stop at its B2 assert, no output
        crlf = os.path.join(w, 'r_crlf.py')
        wr(crlf, got.replace(b'\n', b'\r\n'))
        q, wall = run_reader(crlf, frames, bundle, *names)
        rec['crlf_negative'] = dict(
            what=f'r.py with CRLF line ends saved as {names[0]}, the same frames: exit 1 at '
                 f'AssertionError, no {names[1]}',
            rc=q['rc'], err=q['err'], output=q['output'], frames_read=q['frames_read'],
            passed=q['rc'] == 1 and q['err'].startswith('AssertionError') and q['output'] == 'absent')
    shutil.rmtree(w)
    rec['closed'] = bool(rec['apy_rc'] == 0 and rec['selfdump_equals_codes']
                         and rec['prompts_then_silence'] and rec['rpy_equals_build_loader']
                         and rec.get('read', {}).get('output') == 'identical')
    rec['negative_passed'] = bool(rec.get('crlf_negative', {}).get('passed'))
    wr(os.path.join(BUILD, 'typed_chain.json'), json.dumps(rec, indent=1, sort_keys=True) + '\n')
    return rec


# ---- 9. records and sums ---------------------------------------------------
def files_under(d):
    out = []
    for base, _, fs in os.walk(d):
        out += [os.path.join(base, f) for f in fs]
    return sorted(out)


def stage_records(npages):
    keep = {'README.md'}
    copies = {'payload.bin': os.path.join(R2B, 'payload.bin'),
              'bundle.bin': os.path.join(BUN, 'b.py'),
              'payload.json': os.path.join(R2B, 'payload.json')}
    for p in range(npages):
        copies[f'page_p{p}.json'] = os.path.join(R2B, f'page_p{p}.json')
        for t, _ in BASE:
            copies[f'page_p{p}.{t}.json'] = os.path.join(R2B, f'page_p{p}.{t}.json')
    r2s = [f for f in files_under(R2B) if os.path.basename(f) != 'SHA256SUMS']
    sums = ''.join(f'{sha(rd(f))}  {os.path.relpath(f, R2B)}\n' for f in r2s)
    wr(os.path.join(R2B, 'SHA256SUMS'), sums)
    copies['SHA256SUMS'] = os.path.join(R2B, 'SHA256SUMS')
    if not RECORD:
        return [], len(r2s)
    os.makedirs(REC, exist_ok=True)
    gone = []
    for f in sorted(os.listdir(REC)):
        if f not in keep and f not in copies:
            os.remove(os.path.join(REC, f))
            gone.append(f)
    for f, src in copies.items():
        shutil.copyfile(src, os.path.join(REC, f))
    return gone, len(r2s)


def stage_sums():
    files = []
    for d in MINE_DIRS:
        files += files_under(os.path.join(BUILD, d))
    files += [os.path.join(BUILD, f) for f in MINE_FILES]
    if RECORD:                      # the print of record, rewritten by this run
        files += [os.path.join(ROOT, 'loader', f) for f in
                  ('a.py', 'data.txt', 'codes.txt', 'loader_readable.py')]
        files += [os.path.join(ROOT, 'pages', f) for f in ('leaf3.txt', 'leaf4.txt')]
        files += [os.path.join(REC, f) for f in sorted(os.listdir(REC)) if f != 'README.md']
    lines = [f'{sha(rd(f))}  {os.path.relpath(f, ROOT)}' for f in sorted(set(files))]
    wr(os.path.join(BUILD, 'SHA256SUMS'), '\n'.join(lines) + '\n')
    return lines


def load_sums(path):
    if not os.path.exists(path):
        return None
    return dict(ln.split('  ', 1)[::-1] for ln in rd(path).decode().split('\n') if ln)


def clean():
    for d in MINE_DIRS + ('tmp', 'walls'):
        shutil.rmtree(os.path.join(BUILD, d), ignore_errors=True)
    for f in MINE_FILES + ('SHA256SUMS',):
        if os.path.exists(os.path.join(BUILD, f)):
            os.remove(os.path.join(BUILD, f))
    for d in (R2B, BUN, LOUT, TMP, WALLS):
        os.makedirs(d, exist_ok=True)


def bundle_typed_pages(reader, audit_line):
    """Stages 2-4, repeated while gen.py refuses the payload for its
    orientation (status 3): each refusal appends one newline to b.py, which
    moves N2 and B2, so make_typed runs again before the payload is
    compressed again.  At most PAD_TRIES tries, then the build stops."""
    refused = []
    for pad in range(PAD_TRIES):
        t = stage(2, f'bundle {RB}/bundle/b.py' + (f' + {pad} newline(s)' if pad else ''))
        bundle, brec = stage_bundle(pad)
        print(f"   b.py {brec['bytes']} B sha256 {brec['sha256'][:16]}: R2-FORMAT.md "
              f"{brec['parts'][0]['bytes']} B as its docstring + {brec['parts'][1]['file']} "
              f"{brec['parts'][1]['bytes']} B" + (f' + {pad} newline(s)' if pad else ''))
        walled('2 bundle', t)
        t = stage(3, 'typed files (loader/make_typed.py --bundle b.py, N2 = %d, B2 = %d)'
                  % (len(bundle), zlib.crc32(bundle)))
        apy, rpy = stage_typed(reader, os.path.join(BUN, 'b.py'))
        sz = stage_sizes(reader, apy, bundle, audit_line)
        print(f"   reader {sz['file']}: file {sz['file_bytes']} B, typed text "
              f"{sz['typed_text']['bytes']} B raw, cm2 v2 x {sz['cm2_v2']['x_bits']} bits = "
              f"{sz['cm2_v2']['x_bytes']} B (primer a.py), base-32 {sz['base32_glyphs']} "
              f"glyphs; r.py {len(rpy)} B")
        walled('3 typed + sizes', t)
        t = stage(4, 'pages (cm2 of b.py with primer r.py; r2/gen.py pages; verify_grid)')
        pr, sides = stage_pages(bundle, rpy, refused)
        walled('4 pages', t)
        if pr is not None:
            print(f"   payload {pr['payload_bytes']} B on {pr['pages']} page(s), capacity "
                  f"{pr['capacity_bytes_per_page']} B/page = {pr['capacity_bytes']} B, headroom "
                  f"{pr['headroom_bytes']} B; chunks {pr['chunks']} {pr['chunks_per_page']}, "
                  f"fourth copies {pr['fourth_copies']}, white slots {pr['white_slots']}; "
                  f"bundle pad {pr['bundle_pad_newlines']} newline(s)")
            return bundle, brec, apy, rpy, sz, pr, sides
        refused.append(dict(pad_newlines=pad, **sides))
        print(f"   gen.py REFUSED the payload (status {gen.EXIT_ORIENTATION}): "
              f"{sides['gen_stderr'][:160]}\n   -> one more newline on b.py, typed and "
              "compressed again")
    sys.exit(f'gen.py refused {PAD_TRIES} payloads in a row (orientation): build stopped; '
             + json.dumps(refused)[:2000])


# ---- main ------------------------------------------------------------------
def main():
    global RECORD
    a = sys.argv[1:]
    reader = os.path.abspath(a[a.index('--reader') + 1]) if '--reader' in a else READER
    fast = '--fast' in a
    RECORD = '--record' in a
    names = stage_names(reader)
    prev = load_sums(os.path.join(BUILD, 'SHA256SUMS'))
    t00 = time.time()
    clean()
    tool_files = list(TOOLS) + [f for f in [os.path.relpath(reader, ROOT)] if f not in TOOLS]
    wr(os.path.join(BUILD, 'tools.json'), json.dumps(
        {f: sha(rd(os.path.join(ROOT, f))) for f in tool_files}, indent=1) + '\n')
    t = stage(1, 'reader audit (r2reader/count_reader.py) of ' + os.path.relpath(reader, ROOT))
    audit_line = stage_audit(reader)
    walled('1 reader audit', t)
    bundle, brec, apy, rpy, sz, pr, sides = bundle_typed_pages(reader, audit_line)
    npages = pr['pages']
    t = stage(5, 'renders (r2/camera.py)' + (' --fast: no envelope, no damage' if fast else ''))
    rs = render_list(npages, fast)
    stage_renders(rs)
    grid = 'txt' if reads_grid_text(reader) else 'pgm'
    if grid == 'pgm':
        stage_plate_grids(npages)
    print(f'   {len(rs)} renders' + ('; the grids through the Plate\'s one-liner -> page_p*.grid.pgm'
                                  if grid == 'pgm' else ''))
    walled('5 renders', t)
    t = stage(6, f'reads ({RB}/loader/r.py run as python3 {names[0]} in a scratch directory, '
                 f'output {names[1]})')
    sets = read_sets(rs, npages, grid)
    res, rwalls, selfread = stage_reads(sets, bundle, sides, names)
    walled('6 reads', t)
    print('   ' + rd(os.path.join(R2B, 'reads.md')).decode().strip().replace('\n', '\n   '))
    print(f"   the bundle as a reader (c.py) on every page grid: rc {selfread['rc']}, frames read "
          f"{selfread['frames_read']}, chunks {selfread['held']} / {selfread['need']}, "
          f"{selfread['writes']} afterwards {selfread['output']}, stderr: {selfread['err'] or '-'}")
    t = stage(7, 'e2e (loader/e2e_pipe.py)')
    erc, checks, eout = stage_e2e(reader, os.path.join(BUN, 'b.py'), npages, pr['chunks'])
    walled('7 e2e', t)
    npass = sum(c.startswith('PASS') for c in checks)
    print(f"   {'ALL PASS' if erc == 0 else f'FAILED, see {RB}/e2e.txt'}: {npass} PASS, "
          f"{len(checks) - npass} FAIL")
    for ln in eout.split('\n'):
        if ln.startswith(('==', f'   {names[0]}:')) or 'pages:' in ln or ln.strip().startswith('FAIL'):
            print('   ' + ln.strip())
    t = stage('7b', f'typed chain: python3 a.py + data.txt -> r.py (as {names[0]}) -> every page '
                    f'nominal -> {names[1]}')
    chain = stage_typed_chain(bundle, npages, names)
    walled('7b typed chain', t)
    rr = chain.get('read', {})
    print(f"   a.py rc {chain['apy_rc']}, self-dump == codes {chain['selfdump_equals_codes']}, "
          f"prompts then silence {chain['prompts_then_silence']}, r.py == {RB}/loader/r.py "
          f"{chain['rpy_equals_build_loader']}; r.py read: {rr.get('per_frame')}, {names[1]} "
          f"{rr.get('output')} -> {'CLOSED' if chain['closed'] else 'NOT CLOSED'}")
    cn = chain.get('crlf_negative', {})
    print(f"   negative, r.py re-saved with CRLF: rc {cn.get('rc')}, last stderr line "
          f"{cn.get('err')!r}, {names[1]} {cn.get('output')} -> "
          f"{'PASS' if chain['negative_passed'] else 'FAIL'}")
    t = stage(8, 'leaves + PDF (pages/compose_leaves.py)')
    pdf = os.path.join(BUILD, 'bootstrap-leaves.pdf')
    p = run([PY, os.path.join(ROOT, 'pages', 'compose_leaves.py'), '--pdf', pdf, '--r2', R2B]
            + ([] if RECORD else ['--loader', LOUT, '--out', BUILD]),
            cwd=os.path.join(ROOT, 'pages'))
    print('   ' + p.stdout.strip().replace('\n', '\n   '))
    for f in ('leaf3.txt', 'leaf4.txt') if RECORD else ():
        shutil.copyfile(os.path.join(ROOT, 'pages', f), os.path.join(BUILD, f))
    walled('8 leaves', t)
    if erc == 0:
        shutil.rmtree(TMP)
    else:
        print(f'   {RB}/tmp/ kept (e2e_pipe keeps its failed work directories there)')
    t = stage(9, 'records (pages/r2/, --record only) + sums')
    gone, nr2 = stage_records(npages)
    if gone:
        print('   removed from pages/r2/: ' + ', '.join(gone))
    lines = stage_sums()
    walled('9 sums', t)
    WALL['total'] = round(time.time() - t00, 1)
    wr(os.path.join(WALLS, 'walls.json'), json.dumps(dict(stages=WALL, reads=rwalls), indent=1) + '\n')

    print('== summary')
    print(f"reader   {sz['file']}: {audit_line}")
    print(f"         typed text {sz['typed_text']['bytes']} B, cm2 v2 x {sz['cm2_v2']['x_bits']} "
          f"bits = {sz['cm2_v2']['x_bytes']} B (primer a.py), base-32 {sz['base32_glyphs']} "
          f"glyphs; orders {ORDERS}")
    tools = json.load(open(os.path.join(BUILD, 'tools.json')))
    print('tools    ' + ', '.join(f'{f} {h[:12]}' for f, h in tools.items()))
    moved = [f for f in tools if sha(rd(os.path.join(ROOT, f))) != tools[f]]
    if moved:
        print('WARNING  changed on disk during this build: ' + ', '.join(moved))
    print(f"bundle   b.py {brec['bytes']} B (R2-FORMAT.md {brec['parts'][0]['bytes']} + reader.py "
          f"{brec['parts'][1]['bytes']} + 7), sha256 {brec['sha256']}")
    print(f"typed    a.py {sz['apy']['lines']} lines / {sz['apy']['chars']} chars + data.txt "
          f"{sz['data']['lines']} lines / {sz['data']['chars']} chars = {sz['typed_chars']} "
          f"typed characters (newlines not counted); r.py {len(rpy)} B")
    print(f"pages    {npages}; payload {pr['payload_bytes']} B of capacity {pr['capacity_bytes']} B "
          f"({pr['capacity_bytes_per_page']} B/page), headroom {pr['headroom_bytes']} B")
    print(f"reads    {len(res)} capture sets (table above); the bundle alone as a reader: rc "
          f"{selfread['rc']}, {selfread['err'] or 'no error'}")
    print(f"e2e      rc {erc}: {npass} PASS, {len(checks) - npass} FAIL; typed chain "
          f"(a.py -> r.py -> pages -> {names[1]}): {'CLOSED' if chain['closed'] else 'NOT CLOSED'}; "
          f"CRLF r.py negative: {'PASS' if chain['negative_passed'] else 'FAIL'}")
    rw = sorted(w for w, n in rwalls.values())
    print('walls    ' + ', '.join(f'{k} {v:.0f} s' for k, v in WALL.items())
          + f'; per read median {rw[len(rw) // 2]:.1f} s, max {rw[-1]:.1f} s')
    now = load_sums(os.path.join(BUILD, 'SHA256SUMS'))
    if prev is None:
        print(f'sums     {len(lines)} files in {RB}/SHA256SUMS ({nr2} under {RB}/r2/); '
              'no previous run to compare')
    else:
        diff = sorted(k for k in set(prev) | set(now) if prev.get(k) != now.get(k))
        print(f'sums     {len(lines)} files in {RB}/SHA256SUMS ({nr2} under {RB}/r2/); '
              + ('IDENTICAL to the previous run' if not diff else
                 f'{len(diff)} differ from the previous run: ' + ', '.join(diff[:12])
                 + (' ...' if len(diff) > 12 else '')))
    return 0 if erc == 0 and chain['closed'] and chain['negative_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
