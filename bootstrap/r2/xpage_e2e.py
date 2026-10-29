#!/usr/bin/env python3
"""End-to-end check of the copies-across-pages amendment (R2-FORMAT v1,
amended 2026-10-20 night; harness only, generator side).

  env/bin/python bootstrap/r2/xpage_e2e.py OUT
      [--seeds [FIRST LAST [TAG ...]] | --nearwhite]

Writes only under OUT (never bootstrap/build/{loader,bundle,r2,tmp,walls});
reads build/bundle/b.py and build/loader/r.py read-only.  The generator
before the amendment (gen.py + placement_stats.py at commit OLD_SHA,
1d309208) is written to OUT/old_r2 by `git show`, and the old-layout
baseline is generated and rendered here (OUT/standin_old), so the harness
re-runs after any build.  Six parts:

  A  the stand-in payload (cm2 v2 of build/bundle/b.py with primer
     build/loader/r.py; 14,472 B, 3 pages on 2026-10-20 night; whether it
     equals build/r2/payload.bin is recorded, not required): gen.py
     pages, verify_grid.py over all pages and over each page alone, every
     render build.py makes (build.render_list, envelope and damage
     included), then every read set build.py makes (build.read_sets: each
     capture alone, all pages per base capture, the four quarters pooled,
     each turn / tilt / damage case and the loupe grid with the other
     pages' nominal-b030, every page's grid) plus each pair of pages'
     nominal-b030 — with the typed reader (the r.py that loader/a.py writes
     from loader/data.txt, step 7b: compared with build/loader/r.py first)
     and with the readable reader (r2reader/reader.py with N2 and B2
     written in, r.py beside it as the primer); the same sets on the old
     renders in build/r2/ with both readers, as the baseline; the typed
     chain once plainly (a.py -> r.py -> the three nominal-b030 -> b.py),
     and its CRLF negative.  Old baseline: the old generator's pages of the
     same payload, rendered with the same arguments (OUT/standin_old).
  B  a 2-page payload: the R3 monolith with its archival layer,
     r3/arch/receiver_arch.py as minified-g (r3/measure.py's minify with
     module names renamed), cm2 v2 with primer build/loader/r.py (10,599 B
     on record): pages, verify_grid, the four base renders of each page,
     each read alone and both pooled, with both readers (their N2 and B2
     written for this content; the primer is still build/loader/r.py).
  C  1-page payloads (the first 1,000 and 5,304 B of the stand-in
     payload): gen.py pages byte-identical to the generator before the
     amendment (OUT/old_r2/gen.py, bootstrap/r2/gen.py at OLD_SHA) —
     grid, PBM and PNG; the sidecars' differing keys listed.
  D  the slot of every placed copy (copy k, page-local index i) for every
     P = 1 .. 13 against the old generator's placement(204) (OUT/old_r2).
  E  (--seeds [FIRST LAST [TAG ...]], run after A) the pooled read of all
     three stand-in pages at nominal-b030, nominal-b045 and hard-b030 (or
     the TAGs), camera seeds 1 .. 10 (or FIRST .. LAST), old pages
     (OUT/standin_old/page_p*.pbm, re-rendered) against new, with the typed
     reader: closes per layout, and the chunks still missing; accumulates
     in OUT/seeds.json.
  F  a near-white page (the coverage the build lost: the stand-in's pages
     carry no white slot since the amendment): a 1-page payload of 45
     chunks (cm2 v2 of a prefix of b.py, primer build/loader/r.py; it uses
     the slots of the old 453-chunk stand-in's last page, ruling 15's set
     I, since a page of 45 chunks lays out the same at P = 1), every render
     and read set build.py makes for one page, typed reader (N2 and B2
     written for the prefix) and readable reader.
Results: OUT/xpage.json and OUT/xpage.md (E: OUT/seeds.json, seeds.md).
At most 4 reads at a time.
"""
import concurrent.futures as cf
import hashlib
import importlib.util
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import build as B  # noqa: E402  (paths, render and read sets; nothing run)
import gen  # noqa: E402

PY = B.PY
JOBS = 4
OUT = os.path.abspath(sys.argv[1])          # [--seeds]
TMPD = os.path.join(OUT, "tmp")
OLD_SHA = "1d309208"                 # the generator before the amendment
OLD_GEN = os.path.join(OUT, "old_r2")
BUNDLE = B.rd(os.path.join(B.BUN, "b.py"))
RPY = os.path.join(B.LOUT, "r.py")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run(argv, cwd=None, ok=(0,)):
    p = subprocess.run(argv, capture_output=True, text=True, cwd=cwd)
    if p.returncode not in ok:
        sys.exit(f"FAILED {argv}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    return p


def readable_reader(path, n2, b2):
    src = B.rd(os.path.join(ROOT, "r2reader", "reader.py")).decode()
    assert src.count("e), N2, open('r.py'") == 1
    assert src.count("assert crc32(out) == B2") == 1
    src = src.replace("e), N2, open('r.py'", f"e), {n2}, open('r.py'")
    src = src.replace("assert crc32(out) == B2", f"assert crc32(out) == {b2}")
    assert f"{n2}, open('r.py'" in src and f"== {b2}" in src
    B.wr(path, src)


def typed_reader_for(path, rpy, n2, b2):
    """The typed r.py with other print-time constants (for part B): run as
    rx.py beside the unchanged r.py, which stays the primer."""
    t = B.rd(rpy)
    old = b",%d,open('r.py','rb')" % len(BUNDLE)
    assert t.count(old) == 1 and t.count(b"==%d" % zlib.crc32(BUNDLE)) == 1
    t = t.replace(old, b",%d,open('r.py','rb')" % n2)
    t = t.replace(b"==%d" % zlib.crc32(BUNDLE), b"==%d" % b2)
    B.wr(path, t)


def read(progs, main, frames, base, want):
    """python3 MAIN in a scratch directory holding PROGS [(name, path)],
    the frames (paths under BASE) on stdin, an empty line."""
    w = tempfile.mkdtemp(prefix="read-", dir=TMPD)
    for name, path in progs:
        shutil.copyfile(path, os.path.join(w, name))
    p = subprocess.run([PY, main], cwd=w, capture_output=True, text=True,
                       timeout=3600, env={"PATH": "/usr/bin:/bin"},
                       input="".join(os.path.join(base, f) + "\n"
                                     for f in frames) + "\n")
    bp = os.path.join(w, "b.py")
    b = B.rd(bp) if os.path.exists(bp) else None
    shutil.rmtree(w)
    per = []
    for ln in p.stdout.split("\n"):
        m = B.PROGRESS.search(ln)
        if m:
            per.append([os.path.relpath(m[1].strip(), base), int(m[3]),
                        int(m[4]), m[5], m[6]])
    err = p.stderr.strip().split("\n")[-1] if p.stderr.strip() else ""
    miss = [ln.split("MISSING", 1)[1].strip() for ln in p.stdout.split("\n")
            if "MISSING" in ln]
    out = "absent" if b is None else "identical" if b == want else \
        f"differs ({len(b)} B)"
    return dict(rc=p.returncode, b_py=out, closed=out == "identical",
                held=per[-1][2] if per else 0, need=per[-1][3] if per else "?",
                blocks=sum(x[1] for x in per), frames_read=len(per), err=err,
                **({"missing": miss[-1]} if miss else {}))


def old_generator():
    """OUT/old_r2/{gen,placement_stats}.py = bootstrap/r2/* at OLD_SHA."""
    os.makedirs(OLD_GEN, exist_ok=True)
    for f in ("gen.py", "placement_stats.py"):
        p = subprocess.run(["git", "-C", ROOT, "show",
                            f"{OLD_SHA}:bootstrap/r2/{f}"],
                           capture_output=True, check=True)
        B.wr(os.path.join(OLD_GEN, f), p.stdout)
    return os.path.join(OLD_GEN, "gen.py")


def pages_of(frames):
    return sorted({B.page_of(f) for f in frames})


def part_a(rec, chain_rpy):
    d = os.path.join(OUT, "standin")
    os.makedirs(os.path.join(d, "env"), exist_ok=True)
    os.makedirs(os.path.join(d, "damage"), exist_ok=True)
    z = B.compress(BUNDLE, B.rd(RPY))
    bp = os.path.join(B.R2B, "payload.bin")
    B.wr(os.path.join(d, "payload.bin"), z)
    g = run([PY, os.path.join(HERE, "gen.py"), "pages", "payload.bin",
             "page"], cwd=d)
    do = os.path.join(OUT, "standin_old")
    for sub in ("env", "damage"):
        os.makedirs(os.path.join(do, sub), exist_ok=True)
    B.wr(os.path.join(do, "payload.bin"), z)
    run([PY, os.path.join(OLD_GEN, "gen.py"), "pages", "payload.bin",
         "page"], cwd=do)
    P = gen.n_pages(len(z))
    sides = [json.load(open(os.path.join(d, f"page_p{q}.json")))
             for q in range(P)]
    grids = [f"page_p{q}.grid.txt" for q in range(P)]
    ver = {}
    for name, gs in [("all pages", grids)] + [(f"page {q} alone", [x])
                                             for q, x in enumerate(grids)]:
        v = run([PY, os.path.join(HERE, "verify_grid.py")] + gs
                + ["--payload", "payload.bin", "--pbm"], cwd=d, ok=(0, 1))
        ver[name] = dict(rc=v.returncode, tail=v.stdout.strip().split("\n")
                         [-3:])
    rec["A"] = dict(payload_bytes=len(z), payload_sha256=sha(z), pages=P,
                    payload_equals_build_r2=os.path.exists(bp)
                    and B.rd(bp) == z,
                    gen=g.stdout.strip().split("\n"), verify=ver,
                    band_groups=[[b["group"] for b in s["band_groups"]]
                                 for s in sides],
                    fourth=[[s["fourth_group"], s["fourth_copies"]]
                            for s in sides],
                    white=[s["white_slots"] for s in sides])
    rs = B.render_list(P, False)
    cam = os.path.join(HERE, "camera.py")

    def one(x):
        r, base = x
        p = r["page"]
        run([PY, cam, f"page_p{p}.pbm", r["file"], "--sidecar",
             f"page_p{p}.json"] + r["argv"], cwd=base)
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(one, [(r, b) for b in (d, do) for r in rs]))
    sets = B.read_sets(rs, P)
    by = {r["name"]: r["file"] for r in rs}
    for a, b in itertools.combinations(range(P), 2):
        sets.append(dict(name=f"pair: p{a} + p{b} nominal-b030",
                         group=f"pair: p{a} + p{b} nominal-b030",
                         frames=[by[f"p{a} nominal-b030"],
                                 by[f"p{b} nominal-b030"]], pooled=True))
    rr = os.path.join(OUT, "rr_standin.py")
    readable_reader(rr, len(BUNDLE), zlib.crc32(BUNDLE))
    on_new = [{c for c in s["slot_chunk"] if c is not None} for s in sides]
    N = gen.n_chunks(len(z))
    jobs = {}
    with cf.ThreadPoolExecutor(JOBS) as ex:
        for s in sets:
            for where, base in (("new", d), ("old", do)):
                jobs[s["name"], where, "typed"] = ex.submit(
                    read, [("r.py", chain_rpy)], "r.py", s["frames"], base,
                    BUNDLE)
                jobs[s["name"], where, "readable"] = ex.submit(
                    read, [("r.py", chain_rpy), ("rr.py", rr)], "rr.py",
                    s["frames"], base, BUNDLE)
    res = {}
    for s in sets:
        pg = pages_of(s["frames"])
        e = dict(group=s["group"], frames=s["frames"], pages=pg,
                 part=s.get("part", False),
                 expect_close_new=len(set().union(*(on_new[p] for p in pg)))
                 == N and not s.get("part", False),
                 expect_close_old=pg == list(range(P)))
        for where in ("new", "old"):
            for rd in ("typed", "readable"):
                e[f"{where} {rd}"] = jobs[s["name"], where, rd].result()
        res[s["name"]] = e
    rec["A"]["reads"] = res
    # the typed table in build.py's format, for the new pages
    tab = {}
    for s in sets:
        r = dict(res[s["name"]]["new typed"])
        pg = res[s["name"]]["pages"]
        r.update(frames=s["frames"], pages=pg, part=s.get("part", False),
                 expect_close=pg == list(range(P)),
                 carries_all=len(set().union(*(on_new[p] for p in pg))) == N)
        if len(pg) == 1:
            r["page_complete"] = r["held"] == len(on_new[pg[0]]) \
                if len(pg) < P else r["closed"]
        tab[s["name"]] = r
    B.wr(os.path.join(OUT, "standin_reads_typed.md"),
         B.reads_table(sets, tab, P))


def chain(rec):
    """Step 7b: loader/a.py + loader/data.txt -> r.py (== build/loader/r.py);
    then that r.py on the three new nominal-b030 -> b.py; the CRLF
    negative."""
    w = os.path.join(OUT, "chain")
    shutil.rmtree(w, ignore_errors=True)
    os.makedirs(w)
    B.wr(os.path.join(w, "a.py"), B.rd(os.path.join(ROOT, "loader", "a.py")))
    data = B.rd(os.path.join(ROOT, "loader", "data.txt")).decode()
    p = subprocess.run([PY, "a.py"], cwd=w, input=data, capture_output=True,
                       text=True, timeout=3600, env={"PATH": "/usr/bin:/bin"})
    rpy = os.path.join(w, "r.py")
    got = B.rd(rpy) if os.path.exists(rpy) else b""
    rec["chain"] = dict(apy_rc=p.returncode, rpy_bytes=len(got),
                        rpy_equals_build_loader=got == B.rd(RPY))
    assert rec["chain"]["rpy_equals_build_loader"], rec["chain"]
    return rpy


def chain_read(rec, rpy):
    d = os.path.join(OUT, "standin")
    frames = [f"page_p{q}.nominal-b030.pgm" for q in range(3)]
    r = read([("r.py", rpy)], "r.py", frames, d, BUNDLE)
    crlf = os.path.join(OUT, "chain", "r_crlf.py")
    B.wr(crlf, B.rd(rpy).replace(b"\n", b"\r\n"))
    q = read([("r.py", crlf)], "r.py", frames, d, BUNDLE)
    rec["chain"].update(read=r, crlf_negative=dict(
        rc=q["rc"], err=q["err"], b_py=q["b_py"],
        passed=q["rc"] == 1 and q["err"].startswith("AssertionError")
        and q["b_py"] == "absent"))


def part_b(rec, chain_rpy):
    spec = importlib.util.spec_from_file_location(
        "r3measure", os.path.join(ROOT, "r3", "measure.py"))
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)
    src = B.rd(os.path.join(ROOT, "r3", "arch", "receiver_arch.py")).decode()
    ming = M.minify(src, True).encode()
    d = os.path.join(OUT, "r3arch")
    os.makedirs(d, exist_ok=True)
    pads = 0
    while True:
        z = B.compress(ming, B.rd(RPY))
        B.wr(os.path.join(d, "payload.bin"), z)
        g = run([PY, os.path.join(HERE, "gen.py"), "pages", "payload.bin",
                 "page"], cwd=d, ok=(0, gen.EXIT_ORIENTATION))
        if g.returncode == 0:
            break
        pads += 1
        ming += b"\n"
        assert pads < 8
    B.wr(os.path.join(d, "content.py"), ming)
    P = gen.n_pages(len(z))
    sides = [json.load(open(os.path.join(d, f"page_p{q}.json")))
             for q in range(P)]
    grids = [f"page_p{q}.grid.txt" for q in range(P)]
    ver = {}
    for name, gs in [("all pages", grids)] + [(f"page {q} alone", [x])
                                             for q, x in enumerate(grids)]:
        v = run([PY, os.path.join(HERE, "verify_grid.py")] + gs
                + ["--payload", "payload.bin", "--pbm"], cwd=d, ok=(0, 1))
        ver[name] = dict(rc=v.returncode, tail=v.stdout.strip().split("\n")
                         [-3:])
    cam = os.path.join(HERE, "camera.py")
    rs = [(q, t, a) for q in range(P) for t, a in B.BASE]
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(lambda x: run(
            [PY, cam, f"page_p{x[0]}.pbm", f"page_p{x[0]}.{x[1]}.pgm",
             "--sidecar", f"page_p{x[0]}.json"] + x[2] + ["--seed", "1"],
            cwd=d), rs))
    rx = os.path.join(OUT, "rx_r3arch.py")
    typed_reader_for(rx, chain_rpy, len(ming), zlib.crc32(ming))
    rr = os.path.join(OUT, "rr_r3arch.py")
    readable_reader(rr, len(ming), zlib.crc32(ming))
    sets = [(f"p{q} {t} alone", [f"page_p{q}.{t}.pgm"]) for q, t, _ in rs]
    sets += [(f"p{q} grid alone", [f"page_p{q}.grid.txt"]) for q in range(P)]
    sets += [("all pages nominal-b030",
              [f"page_p{q}.nominal-b030.pgm" for q in range(P)])]
    jobs = {}
    with cf.ThreadPoolExecutor(JOBS) as ex:
        for name, fr in sets:
            jobs[name, "typed"] = ex.submit(
                read, [("r.py", chain_rpy), ("rx.py", rx)], "rx.py", fr, d,
                ming)
            jobs[name, "readable"] = ex.submit(
                read, [("r.py", chain_rpy), ("rr.py", rr)], "rr.py", fr, d,
                ming)
    rec["B"] = dict(content="r3/arch/receiver_arch.py, minified-g",
                    content_bytes=len(ming), pad_newlines=pads,
                    payload_bytes=len(z), pages=P, verify=ver,
                    gen=g.stdout.strip().split("\n"),
                    band_groups=[[b["group"] for b in s["band_groups"]]
                                 for s in sides],
                    fourth=[[s["fourth_group"], s["fourth_copies"]]
                            for s in sides],
                    white=[s["white_slots"] for s in sides],
                    reads={name: {rd: jobs[name, rd].result()
                                  for rd in ("typed", "readable")}
                           for name, _ in sets})


def part_c(rec):
    z = B.compress(BUNDLE, B.rd(RPY))
    out = {}
    for n in (1000, 5304):
        res = {}
        for which, g in (("new", os.path.join(HERE, "gen.py")),
                         ("old", os.path.join(OLD_GEN, "gen.py"))):
            d = os.path.join(OUT, "onepage", f"{n}-{which}")
            os.makedirs(d, exist_ok=True)
            B.wr(os.path.join(d, "payload.bin"), z[:n])
            run([PY, g, "pages", "payload.bin", "page"], cwd=d)
            res[which] = d
        files = {ext: B.rd(os.path.join(res["new"], "page_p0" + ext))
                 == B.rd(os.path.join(res["old"], "page_p0" + ext))
                 for ext in (".grid.txt", ".pbm", ".png")}
        jn, jo = (json.load(open(os.path.join(res[w], "page_p0.json")))
                  for w in ("new", "old"))
        diff = sorted(k for k in set(jn) | set(jo) if jn.get(k) != jo.get(k))
        pdiff = sorted(k for k in set(jn["placement"]) | set(jo["placement"])
                       if jn["placement"].get(k) != jo["placement"].get(k))
        sdiff = sorted(k for k in set(jn["placement"]["stats"])
                       | set(jo["placement"]["stats"])
                       if jn["placement"]["stats"].get(k)
                       != jo["placement"]["stats"].get(k))
        out[n] = dict(identical=files, sidecar_keys_differ=diff,
                      placement_keys_differ=pdiff, stats_keys_differ=sdiff,
                      grid_sha256=sha(B.rd(os.path.join(res["new"],
                                                        "page_p0.grid.txt"))))
    rec["C"] = out


def part_d(rec):
    spec = importlib.util.spec_from_file_location(
        "oldgen", os.path.join(OLD_GEN, "gen.py"))
    O = importlib.util.module_from_spec(spec)
    sys.path.insert(0, OLD_GEN)
    spec.loader.exec_module(O)
    sys.path.pop(0)
    sl, sc = O.placement(204)
    old = {(i, k): s for s, (i, k) in enumerate(zip(sl, sc)) if k in (0, 1, 2)}
    rows, bad = [], 0
    for P in range(1, 14):
        for N in sorted({204 * (P - 1) + 1, 204 * P}
                        | ({2521} if P == 13 else set())):
            n = 0
            for q in range(P):
                ch, cp = gen.page_placement(q, N)
                for s, (c, k) in enumerate(zip(ch, cp)):
                    if c is not None and k in (0, 1, 2):
                        n += 1
                        bad += old[c % 204, k] != s
            rows.append([P, N, n])
    rec["D"] = dict(placed_copies_checked=sum(r[2] for r in rows),
                    differing_from_old=bad, rows=rows)


def part_f(rec, chain_rpy, chunks=45):
    """A near-white page: a 1-page payload of CHUNKS chunks, every render
    and read set build.py makes for one page, both readers."""
    d = os.path.join(OUT, "nearwhite")
    for sub in ("env", "damage"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    lo, hi = 1, len(BUNDLE)
    size = {}

    def zlen(k):
        if k not in size:
            size[k] = len(B.compress(BUNDLE[:k], B.rd(RPY)))
        return size[k]
    while lo < hi:                       # smallest prefix reaching the count
        m = (lo + hi) // 2
        if gen.n_chunks(zlen(m)) < chunks:
            lo = m + 1
        else:
            hi = m
    content = BUNDLE[:lo]
    pads = 0
    while True:
        z = B.compress(content, B.rd(RPY))
        assert gen.n_chunks(len(z)) == chunks, (len(z), lo)
        B.wr(os.path.join(d, "payload.bin"), z)
        g = run([PY, os.path.join(HERE, "gen.py"), "pages", "payload.bin",
                 "page"], cwd=d, ok=(0, gen.EXIT_ORIENTATION))
        if g.returncode == 0:
            break
        pads += 1
        content = BUNDLE[:lo - pads]
        assert pads < 8
    side = json.load(open(os.path.join(d, "page_p0.json")))
    v = run([PY, os.path.join(HERE, "verify_grid.py"), "page_p0.grid.txt",
             "--payload", "payload.bin", "--pbm"], cwd=d, ok=(0, 1))
    rs = B.render_list(1, False)
    cam = os.path.join(HERE, "camera.py")
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(lambda r: run(
            [PY, cam, "page_p0.pbm", r["file"], "--sidecar", "page_p0.json"]
            + r["argv"], cwd=d), rs))
    sets = B.read_sets(rs, 1)
    rx = os.path.join(OUT, "rx_nearwhite.py")
    typed_reader_for(rx, chain_rpy, len(content), zlib.crc32(content))
    rr = os.path.join(OUT, "rr_nearwhite.py")
    readable_reader(rr, len(content), zlib.crc32(content))
    jobs = {}
    with cf.ThreadPoolExecutor(JOBS) as ex:
        for st in sets:
            jobs[st["name"], "typed"] = ex.submit(
                read, [("r.py", chain_rpy), ("rx.py", rx)], "rx.py",
                st["frames"], d, content)
            jobs[st["name"], "readable"] = ex.submit(
                read, [("r.py", chain_rpy), ("rr.py", rr)], "rr.py",
                st["frames"], d, content)
    rec["F"] = dict(content=f"build/bundle/b.py[:{len(content)}]",
                    content_bytes=len(content), payload_bytes=len(z),
                    chunks=chunks, white_slots=side["white_slots"],
                    fourth_copies=side["fourth_copies"],
                    verify=dict(rc=v.returncode,
                                tail=v.stdout.strip().split("\n")[-3:]),
                    reads={st["name"]: dict(
                        part=st.get("part", False), frames=st["frames"],
                        **{rd: jobs[st["name"], rd].result()
                           for rd in ("typed", "readable")})
                        for st in sets})


def summarize(rec):
    L = ["# Copies across pages: end-to-end (MEASURED)", ""]
    A = rec["A"]
    L.append(f"A. stand-in payload {A['payload_bytes']} B, {A['pages']} "
             f"pages; band groups {A['band_groups']}, fourth [group, copies] "
             f"{A['fourth']}, white {A['white']}")
    for k, v in A["verify"].items():
        L.append(f"   verify_grid {k}: rc {v['rc']}: {' | '.join(v['tail'])}")
    L.append(f"   typed chain: r.py == build/loader/r.py "
             f"{rec['chain']['rpy_equals_build_loader']}; read of the three "
             f"nominal-b030: b.py {rec['chain']['read']['b_py']}, chunks "
             f"{rec['chain']['read']['held']} / {rec['chain']['read']['need']}"
             f"; CRLF negative {'PASS' if rec['chain']['crlf_negative']['passed'] else 'FAIL'}")
    L += ["", "| set | pages | expect close (new / old) | typed new | typed "
          "old | readable new | readable old |", "|---|---|---|---|---|---|---|"]

    def cell(r):
        return (f"{'CLOSED' if r['closed'] else 'open'} {r['held']}/"
                f"{r['need']}")
    reg = []
    for name, e in A["reads"].items():
        L.append(f"| {name} | {e['pages']} | {e['expect_close_new']} / "
                 f"{e['expect_close_old']} | {cell(e['new typed'])} | "
                 f"{cell(e['old typed'])} | {cell(e['new readable'])} | "
                 f"{cell(e['old readable'])} |")
        for rd in ("typed", "readable"):
            o, n = e[f"old {rd}"], e[f"new {rd}"]
            if o["closed"] and not n["closed"]:
                reg.append(f"{name} ({rd})")
    L.append("")
    L.append(f"regressions (closed on the old pages, open on the new): "
             f"{reg or 'none'}")
    for rd in ("typed", "readable"):
        for w in ("new", "old"):
            c = sum(e[f"{w} {rd}"]["closed"] for e in A["reads"].values())
            L.append(f"   {rd} reader, {w} pages: {c} of {len(A['reads'])} "
                     "sets closed")
    Bp = rec["B"]
    L += ["", f"B. R3 monolith + archival layer, minified-g "
          f"{Bp['content_bytes']} B (pad {Bp['pad_newlines']}), payload "
          f"{Bp['payload_bytes']} B, {Bp['pages']} pages; band groups "
          f"{Bp['band_groups']}, fourth {Bp['fourth']}, white {Bp['white']}"]
    for k, v in Bp["verify"].items():
        L.append(f"   verify_grid {k}: rc {v['rc']}: {' | '.join(v['tail'])}")
    L += ["", "| set | typed | readable |", "|---|---|---|"]
    for name, r in Bp["reads"].items():
        L.append(f"| {name} | {cell(r['typed'])} | {cell(r['readable'])} |")
    L += ["", "C. one-page payloads, new vs old generator:"]
    for n, v in rec["C"].items():
        L.append(f"   {n} B: files identical {v['identical']}; sidecar keys "
                 f"differing {v['sidecar_keys_differ']}; placement keys "
                 f"{v['placement_keys_differ']}; stats keys "
                 f"{v['stats_keys_differ']}")
    D = rec["D"]
    L += ["", f"D. placed copies checked against the old generator's "
          f"placement(204): {D['placed_copies_checked']}, differing "
          f"{D['differing_from_old']}"]
    F = rec.get("F")
    if F:
        L += ["", f"F. near-white page: {F['content']} ({F['content_bytes']}"
              f" B), payload {F['payload_bytes']} B, {F['chunks']} chunks, 1 "
              f"page, fourth copies {F['fourth_copies']}, white "
              f"{F['white_slots']} of 615; verify_grid rc {F['verify']['rc']}"
              f": {' | '.join(F['verify']['tail'])}", "",
              "| set | partial | typed | readable |", "|---|---|---|---|"]
        for name, r in F["reads"].items():
            L.append(f"| {name} | {r['part']} | {cell(r['typed'])} | "
                     f"{cell(r['readable'])} |")
        for rd in ("typed", "readable"):
            whole = [r for r in F["reads"].values() if not r["part"]]
            part = [r for r in F["reads"].values() if r["part"]]
            L.append(f"   {rd}: whole-page sets {sum(r[rd]['closed'] for r in whole)}"
                     f"/{len(whole)} closed, partial frames alone "
                     f"{sum(r[rd]['closed'] for r in part)}/{len(part)}")
    return "\n".join(L) + "\n"


def part_e(chain_rpy, first=1, last=10, tags=None):
    """Seeds FIRST .. LAST (1 .. 10) of three whole-page captures (or the
    TAGS among them), all three pages pooled, old layout against new,
    typed reader.  Appends to OUT/seeds.json."""
    cam = os.path.join(HERE, "camera.py")
    conf = [("nominal-b030", B.NOM30), ("nominal-b045", B.NOM + ["--blur",
                                                                 "0.45"]),
            ("hard-b030", ["--preset", "hard", "--blur", "0.30"])]
    conf = [c for c in conf if not tags or c[0] in tags]
    seeds = range(first, last + 1)
    src = {"old": os.path.join(OUT, "standin_old"),
           "new": os.path.join(OUT, "standin")}
    jobs = []
    for lay, base in src.items():
        d = os.path.join(OUT, "seeds", lay)
        os.makedirs(d, exist_ok=True)
        for tag, args in conf:
            for seed in seeds:
                for q in range(3):
                    jobs.append([PY, cam, os.path.join(base, f"page_p{q}.pbm"),
                                 os.path.join(d, f"page_p{q}.{tag}.s{seed}.pgm"),
                                 "--sidecar", os.path.join(base,
                                                           f"page_p{q}.json")]
                                + args + ["--seed", str(seed)])
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(run, jobs))
    diag = os.path.join(OUT, "rdiag.py")
    B.wr(diag, B.rd(chain_rpy) + b"\nprint('MISSING',[k for k in range(n) "
         b"if k not in c])\n")
    futs = {}
    with cf.ThreadPoolExecutor(JOBS) as ex:
        for lay in src:
            d = os.path.join(OUT, "seeds", lay)
            for tag, _ in conf:
                for seed in seeds:
                    fr = [f"page_p{q}.{tag}.s{seed}.pgm" for q in range(3)]
                    futs[lay, tag, seed] = ex.submit(
                        read, [("r.py", chain_rpy), ("rd.py", diag)], "rd.py",
                        fr, d, BUNDLE)
    sj = os.path.join(OUT, "seeds.json")
    res = json.load(open(sj)) if os.path.exists(sj) else {}
    res.update({f"{lay} {tag} s{seed}": f.result()
                for (lay, tag, seed), f in futs.items()})
    B.wr(sj, json.dumps(res, indent=1) + "\n")
    L = ["| capture, all three pages pooled | seeds | old layout: closed "
         "| new layout: closed | old: chunks held (min) | new: chunks held "
         "(min) |", "|---|---|---|---|---|---|"]
    for tag in sorted({k.split()[1] for k in res}):
        ss = sorted(int(k.split()[2][1:]) for k in res
                    if k.startswith(f"old {tag} "))
        o = [res[f"old {tag} s{s}"] for s in ss]
        n = [res[f"new {tag} s{s}"] for s in ss]
        L.append(f"| {tag} | {ss[0]}-{ss[-1]} | {sum(r['closed'] for r in o)}"
                 f"/{len(ss)} | {sum(r['closed'] for r in n)}/{len(ss)} | "
                 f"{min(r['held'] for r in o)} | {min(r['held'] for r in n)} |")
    B.wr(os.path.join(OUT, "seeds.md"), "\n".join(L) + "\n")
    print("\n".join(L))


def main():
    os.makedirs(TMPD, exist_ok=True)
    if "--seeds" in sys.argv:
        a = sys.argv[sys.argv.index("--seeds") + 1:]
        part_e(os.path.join(OUT, "chain", "r.py"), *map(int, a[:2]),
               tags=a[2:]) if a else part_e(os.path.join(OUT, "chain",
                                                         "r.py"))
        return 0
    rec = {}
    old_generator()
    if "--nearwhite" in sys.argv:        # part F alone, after a full run
        rec = json.load(open(os.path.join(OUT, "xpage.json")))
        part_f(rec, chain(rec))
        B.wr(os.path.join(OUT, "xpage.json"), json.dumps(rec, indent=1) + "\n")
        B.wr(os.path.join(OUT, "xpage.md"), summarize(rec))
        print(summarize(rec))
        return 0
    part_d(rec)
    part_c(rec)
    rpy = chain(rec)
    part_a(rec, rpy)
    chain_read(rec, rpy)
    part_b(rec, rpy)
    part_f(rec, rpy)
    B.wr(os.path.join(OUT, "xpage.json"), json.dumps(rec, indent=1) + "\n")
    B.wr(os.path.join(OUT, "xpage.md"), summarize(rec))
    print(summarize(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
