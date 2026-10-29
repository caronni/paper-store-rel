#!/usr/bin/env python3
"""measure.py -- readers x captures, paired (FIX #2 of 2026-10-22; never typed).

Each reader runs as a plain script (python -u) in a fresh temp dir, the
tokens N2 and B2 replaced by the numbers of the case's primer, the primer
copied in under the name r.py (the reader of record reads 'r.py' as its
decompression primer and writes b.py); for the stage-1 pages the script is
the stage-1 loader's definitions + the reader's typed text, as the chain runs
it (see runnable()).  The frames are written to stdin one per line, each after the
previous progress line (so the wall per frame is the reader's own), then an
empty line; feeding stops after a 'done'.  Recorded per frame: the progress
line, bullseyes, blocks accepted, chunks held / needed, wall seconds; per case:
exit code, whether b.py was written and equals the expected bundle, total wall.

Two primers (both read-only, copied):
  S1   the stage-1 pages (build/stage1/lower/r2): primer = the stage-1 build's
       b.py (build/stage1/lower/b.py; N2 55550, B2 2700258880, its own last
       lines); expected = build/bundle/b.py (the bundle of record);
  REC  the phone photos of the print of record (scratch/typed/1-4.pgm):
       primer = scratch/typed/r.py (N2 50533, B2 327353449); expected =
       scratch/typed/b.py (sha256 579e5f1c...).

  python measure.py run [--readers A.py,B.py] [--cases NAME,...] [--jobs N]
                        [--tag TAG]    -> build/axes/measure/TAG.json
  python measure.py sets [--readers ...] [--tag TAG]
        the owner's acceptance sets (diet/w4_sets.py, frames in build/w4/),
        through diet/w4_harness.run_cases with its work dir moved under
        build/axes/measure/ -> build/axes/measure/sets-TAG.json
  python measure.py table TAG.json [...]   the paired table (markdown)
Run from anywhere; paths are absolute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
R2R = os.path.dirname(HERE)
ROOT = os.path.dirname(R2R)                                   # bootstrap/
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "axes", "measure")
PY = "env/bin/python"
S1 = os.path.join(BUILD, "stage1", "lower", "r2")
RND = os.path.join(BUILD, "axes", "renders")
FRM = os.path.join(OUT, "frames")
PHOTOS = "scratch/typed"
sys.path.insert(0, R2R)
import count_reader as CR  # noqa: E402
S1_PREFIX = open(os.path.join(BUILD, "stage1", "lower", "a.py")).read().strip(
    ).encode()[39:599].decode()
READERS = [os.path.join(R2R, "reader_lite_v1.py"), os.path.join(HERE, "fix0.py"),
           os.path.join(HERE, "fix2.py"), os.path.join(HERE, "fix2b.py")]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tail_numbers(path: str) -> tuple[int, int]:
    """(N2, B2) from a typed reader's last lines: d(...,N2,...) and the
    assert b(ou)==B2."""
    t = open(path).read()
    n2 = re.search(r"d\(int\.from_bytes\(dd,'big'\),(\d+),", t)
    b2 = re.search(r"assert b\(ou\)==(\d+)", t)
    assert n2 and b2, path
    return int(n2.group(1)), int(b2.group(1))


PRIMERS: dict[str, dict[str, Any]] = {
    "S1": dict(primer=os.path.join(BUILD, "stage1", "lower", "b.py"),
               expected=os.path.join(BUILD, "bundle", "b.py")),
    "REC": dict(primer=os.path.join(PHOTOS, "r.py"),
                expected=os.path.join(PHOTOS, "b.py")),
}
for _k, _p in PRIMERS.items():
    _p["N2"], _p["B2"] = tail_numbers(_p["primer"])
    _p["expected_sha"] = sha(open(_p["expected"], "rb").read())


def s1(p: int, kind: str) -> str:
    return os.path.join(S1, f"page_p{p}.{kind}")


CASES: dict[str, tuple[str, list[str]]] = {
    "p0 perfect spm2": ("S1", [os.path.join(RND, "page_p0.perfect-s2.pgm")]),
    "p0 perfect spm3": ("S1", [os.path.join(RND, "page_p0.perfect-s3.pgm")]),
    "p0 perfect spm7": ("S1", [os.path.join(RND, "page_p0.perfect-s7.pgm")]),
    "p0 exact raster (P5)": ("S1", [os.path.join(RND, "page_p0.exact600.pgm")]),
    "p0 grid": ("S1", [s1(0, "grid.txt")]),
    "p1 grid": ("S1", [s1(1, "grid.txt")]),
    "p2 grid": ("S1", [s1(2, "grid.txt")]),
    "p0 nominal-b030": ("S1", [s1(0, "nominal-b030.pgm")]),
    "p1 nominal-b030": ("S1", [s1(1, "nominal-b030.pgm")]),
    "p2 nominal-b030": ("S1", [s1(2, "nominal-b030.pgm")]),
    "pool nominal-b030 p0+p1+p2": ("S1", [s1(p, "nominal-b030.pgm") for p in range(3)]),
    "p0 nominal-b045": ("S1", [os.path.join(FRM, "page_p0.nominal-b045.pgm")]),
    "p1 nominal-b045": ("S1", [os.path.join(FRM, "page_p1.nominal-b045.pgm")]),
    "p2 nominal-b045": ("S1", [os.path.join(FRM, "page_p2.nominal-b045.pgm")]),
    "pool nominal-b045 p0+p1+p2": ("S1", [os.path.join(FRM, f"page_p{p}.nominal-b045.pgm")
                                          for p in range(3)]),
    "p0 nominal spm7 b030": ("S1", [os.path.join(RND, "page_p0.nominal-s7-b030.pgm")]),
    **{f"p{p} nominal-b045 seed {s}": ("S1", [os.path.join(FRM, f"page_p{p}.nominal-b045-s{s}.pgm")])
       for p in range(3) for s in (2, 3, 4)},
    **{f"p{p} nominal-b030 seed {s}": ("S1", [os.path.join(FRM, f"page_p{p}.nominal-b030-s{s}.pgm")])
       for p in range(3) for s in (2, 3)},
    **{f"pool nominal-b{b} seed {s} p0+p1+p2": ("S1", [os.path.join(FRM, f"page_p{p}.nominal-b{b}-s{s}.pgm")
                                                       for p in range(3)])
       for b, s in (("030", 2), ("030", 3), ("045", 2), ("045", 3), ("045", 4))},
    "photo 1": ("REC", [os.path.join(PHOTOS, "1.pgm")]),
    "photo 2": ("REC", [os.path.join(PHOTOS, "2.pgm")]),
    "photo 3": ("REC", [os.path.join(PHOTOS, "3.pgm")]),
    "photo 4": ("REC", [os.path.join(PHOTOS, "4.pgm")]),
    "pool photos 1+2+3": ("REC", [os.path.join(PHOTOS, f"{k}.pgm") for k in (1, 2, 3)]),
    "pool photos 1+2+4": ("REC", [os.path.join(PHOTOS, f"{k}.pgm") for k in (1, 2, 4)]),
}

PROG = re.compile(r"(?:(\d+) bullseyes|cannot read), (\d+) blocks accepted, chunks (\d+)"
                  r" / (\S+) (more|done)")


def runnable(reader: str, mode: str, n2: int, b2: int) -> str:
    """REC: the reader file itself (its shared block = the photos' loader d,
    byte-identical to scratch/typed/r.py's), the tokens N2 and B2 replaced.
    S1: as the stage-1 chain runs it -- the stage-1 loader's definitions
    (build/stage1/lower/a.py stripped, bytes 39..599, as a.py writes them
    into b.py: its d with the order tuple (0,1,2,3,4,6,8)) followed by the
    reader's typed text (count_reader.typed_text: region, shared block
    dropped), tokens replaced.  For reader_lite_v1.py this is byte for byte
    the stage-1 build's b.py with 'b.py'/'c.py' read as 'r.py'/'b.py'
    (checked in check_runnable())."""
    t = open(reader).read()
    if mode == "S1":
        t = S1_PREFIX + CR.typed_text(t)
    t2 = re.sub(r"\bN2\b", str(n2), t)
    return re.sub(r"\bB2\b", str(b2), t2)


def check_runnable() -> bool:
    P = PRIMERS["S1"]
    mine = runnable(os.path.join(R2R, "reader_lite_v1.py"), "S1", P["N2"], P["B2"])
    ref = open(P["primer"]).read().replace("open('b.py','rb')", "open('r.py','rb')").replace(
        "open('c.py','wb')", "open('b.py','wb')")
    return mine == ref


def one(reader: str, case: str, timeout: float = 3600.0) -> dict[str, Any]:
    mode, frames = CASES[case]
    P = PRIMERS[mode]
    wd = tempfile.mkdtemp(prefix="axes-measure-")
    try:
        open(os.path.join(wd, "reader.py"), "w").write(runnable(reader, mode, P["N2"],
                                                                     P["B2"]))
        shutil.copyfile(P["primer"], os.path.join(wd, "r.py"))
        t0 = time.time()
        p = subprocess.Popen([PY, "-u", "reader.py"], cwd=wd, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             bufsize=1)
        per: list[dict[str, Any]] = []
        for f in frames:
            t = time.time()
            try:
                p.stdin.write(f + "\n")
                p.stdin.flush()
            except BrokenPipeError:
                break
            ln = p.stdout.readline()
            w = round(time.time() - t, 2)
            if not ln:
                break
            line = ln.split("stops): ", 1)[-1].strip()
            m = PROG.search(line)
            per.append(dict(frame=f, line=line, wall_s=w,
                            bullseyes=int(m.group(1)) if m and m.group(1) else 0,
                            blocks=int(m.group(2)) if m else None,
                            held=int(m.group(3)) if m else None,
                            need=m.group(4) if m else None,
                            status=m.group(5) if m else None))
            if line.endswith("done"):
                break
        try:
            p.stdin.write("\n")
            p.stdin.flush()
        except BrokenPipeError:
            pass
        so, se = p.communicate(timeout=timeout)
        wall = round(time.time() - t0, 2)
        bp = os.path.join(wd, "b.py")
        got = sha(open(bp, "rb").read()) if os.path.exists(bp) else None
        return dict(reader=os.path.relpath(reader, ROOT), case=case, mode=mode,
                    frames=[os.path.basename(f) for f in frames], per_frame=per,
                    rc=p.returncode, stderr=se.strip()[-300:], wall_total_s=wall,
                    bpy_written=got is not None, bpy_sha=got,
                    expected_sha=P["expected_sha"], closed=got == P["expected_sha"])
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def main_run(a: argparse.Namespace) -> None:
    assert check_runnable(), "S1 runnable != the stage-1 build's b.py"
    readers = a.readers.split(",") if a.readers else READERS
    readers = [os.path.abspath(r) for r in readers]
    cases = a.cases.split(",") if a.cases else list(CASES)
    for c in cases:
        for f in CASES[c][1]:
            assert os.path.exists(f), f
    jobs = [(r, c) for c in cases for r in readers]
    res = []
    with ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(lambda j: one(*j), jobs):
            res.append(r)
            last = r["per_frame"][-1] if r["per_frame"] else {}
            print(f"{os.path.basename(r['reader']):20s} {r['case']:28s} "
                  f"{[x['blocks'] for x in r['per_frame']]} {last.get('held')}/"
                  f"{last.get('need')} {last.get('status')} closed={r['closed']} "
                  f"rc={r['rc']} {[x['wall_s'] for x in r['per_frame']]}s "
                  f"total {r['wall_total_s']}s {r['stderr'][-80:]!r}", flush=True)
    os.makedirs(OUT, exist_ok=True)
    meta = dict(s1_runnable_equals_stage1_bpy=check_runnable(), primers={k: dict(primer=v["primer"], N2=v["N2"], B2=v["B2"],
                                 expected=v["expected"], expected_sha=v["expected_sha"])
                         for k, v in PRIMERS.items()},
                readers={os.path.relpath(r, ROOT): sha(open(r, "rb").read()) for r in readers},
                jobs=a.jobs, machine=os.uname().nodename,
                when=time.strftime("%Y-%m-%d %H:%M:%S"))
    fn = os.path.join(OUT, a.tag + ".json")
    json.dump(dict(meta=meta, results=res), open(fn, "w"), indent=1)
    print("->", fn)


def main_sets(a: argparse.Namespace) -> None:
    sys.path.insert(0, os.path.join(R2R, "diet"))
    import w4_harness as wh   # noqa: E402
    import w4_sets as S       # noqa: E402
    wh.OUT = os.path.join(OUT, "w4work")      # run_cases' work dirs, removed per case
    readers = a.readers.split(",") if a.readers else READERS
    cases = {c: fr for st in S.sets().values() for c, fr in st.items()}
    out: dict[str, Any] = {}
    for r in readers:
        r = os.path.abspath(r)
        t0 = time.time()
        res = wh.run_cases("axes-" + os.path.basename(r)[:-3], r, cases)
        v = S.verdict(res)          # no slot pass: set I judged on its whole frames only
        out[os.path.relpath(r, ROOT)] = dict(verdict=v, wall_s=round(time.time() - t0, 1),
                                             cases=res)
        print(os.path.basename(r), json.dumps(v), flush=True)
    shutil.rmtree(wh.OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    fn = os.path.join(OUT, f"sets-{a.tag}.json")
    json.dump(out, open(fn, "w"), indent=1)
    print("->", fn)


def main_table(a: argparse.Namespace) -> None:
    for fn in a.files:
        d = json.load(open(fn))
        R = list(dict.fromkeys(r["reader"] for r in d["results"]))
        by = {(r["reader"], r["case"]): r for r in d["results"]}
        cases = list(dict.fromkeys(r["case"] for r in d["results"]))
        print("| capture | " + " | ".join(os.path.basename(r)[:-3] for r in R) + " |")
        print("|---|" + "---|" * len(R))
        for c in cases:
            cells = []
            for r in R:
                x = by.get((r, c))
                if not x or not x["per_frame"]:
                    cells.append("-")
                    continue
                bl = "+".join(str(f["blocks"]) for f in x["per_frame"])
                last = x["per_frame"][-1]
                ws = sum(f["wall_s"] for f in x["per_frame"])
                cl = "closed" if x["closed"] else ("done, b.py WRONG" if x["bpy_written"]
                                                   else "open")
                cells.append(f"{bl} blk, {last['held']}/{last['need']}, {cl}, {ws:.1f} s")
            print(f"| {c} | " + " | ".join(cells) + " |")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--readers")
    r.add_argument("--cases")
    r.add_argument("--jobs", type=int, default=8)
    r.add_argument("--tag", default="measure")
    s = sub.add_parser("sets")
    s.add_argument("--readers")
    s.add_argument("--tag", default="sets")
    t = sub.add_parser("table")
    t.add_argument("files", nargs="+")
    a = ap.parse_args()
    {"run": main_run, "sets": main_sets, "table": main_table}[a.cmd](a)


if __name__ == "__main__":
    main()
