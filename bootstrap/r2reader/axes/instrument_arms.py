#!/usr/bin/env python3
"""instrument_arms.py -- instrument.py's unread-by-direction method for ANY
reader variant (the fix arms of 2026-10-22), without restating its walk.

instrument.py re-states the reader of record's wk statement for statement;
an arm whose wk differs cannot use it.  Here the arm's own definitions are
exec'd (the region between BEGIN READER and its main loop, as instrument.py's
load_reader) and only rb is wrapped: the arm's wk calls rb(s) with the final
pose of every walked non-seed block, so the wrapper records the visit's key
(seed, a, b), the pose read with, the 256 hard bits (instrument.hard_bits),
the read chunk, and the timing-frame soundness of that pose (the reader's own
statement: 5 sum(a b) >= 3 sum|a - g|; every arm leaves that test as is).
The truth and the tables are instrument.py's (Truth, seed_blocks, analyse,
summarize, page_neighbour_summary, img_diag_summary), imported unchanged.
A visit's "class" = its walk key relative to its seed, the first processed
visit of a page block decides; read = any visit's CRC closed; bullseye blocks
and chunk-less slots excluded (instrument.py's definitions).  The accepted
count is checked against the plain arm's progress line by the caller.

  instrument_arms.py run CAPTURE --reader R.py --page P.json --grid G.txt
        --kind KIND [--sidecar CAM.json] --name NAME [--out DIR]
  instrument_arms.py table DIR/*.json
(photos: no genie fit here -- block identity and misread counts only.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import instrument as I  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "build", "axes", "measure",
                   "instr")


def load_arm(path: str) -> dict[str, Any]:
    src = open(path).read()
    body = src.split("# BEGIN READER", 1)[1]
    body = body.split("\nc,e,i,n={},b'',0,'?'", 1)[0]
    ns: dict[str, Any] = {}
    exec(compile(body, path, "exec"), ns)
    return ns


def main_run(a: argparse.Namespace) -> None:
    R = load_arm(a.reader)
    page = json.load(open(a.page))
    grid = open(a.grid).read().split()
    truth = I.Truth(page, grid)
    img, fmt = I.load_capture(R, a.capture, a.kind)
    log: list = []
    rb0 = R["rb"]
    v, sp, fr = R["v"], R["sp"], R["fr"]

    def rb(s: list) -> Any:
        x = rb0(s)
        bits, thr, dark = I.hard_bits(R, s)
        r = [(v(*sp(s, xx, yy)), 1 - 2 * (k ^ s[4])) for xx, yy, k in fr]
        g = sum(p for p, _ in r) // 68
        sc1, sc2 = 5 * sum(p * t for p, t in r), 3 * sum(abs(p - g) for p, _ in r)
        log.append(dict(key=list(s[5]), refined=[s[0], s[1]], axes=[list(s[2]), list(s[3])],
                        pred=[s[0], s[1]], inh=[list(s[2]), list(s[3])], flip=s[4],
                        bits="".join(map(str, bits)), thr=thr, dark=dark,
                        read=int.from_bytes(x[:2], "big") if x else -1,
                        sound=sc1 >= sc2, sound_margin=sc1 - sc2))
        return x
    R["rb"] = rb
    t0 = time.time()
    R["e"] = b""
    o, e = R["fm"]()
    R["e"] = e
    seeds = [list(s) for s in o[1]]
    chunks = R["wk"](o[0], [list(s) for s in o[1]]) if e else []
    t_wk = time.time() - t0
    md = page["module_dots"]
    if a.kind == "render":
        cam = json.load(open(a.sidecar))
        Hd = np.array(cam["homography_page_dots_to_px"], float)
        g2d = np.array([[md, 0, page["x0_dots"]], [0, md, page["y0_dots"]], [0, 0, 1]], float)
        truth.set_h(Hd @ g2d)
    elif a.kind == "raster":
        truth.set_h(np.array([[md, 0, page["x0_dots"]], [0, md, page["y0_dots"]], [0, 0, 1]],
                             float))
    elif a.kind == "grid":
        truth.set_h(np.array([[3, 0, 12], [0, 3, 12], [0, 0, 1]], float))
    for rec in log:
        q, ka, kb = rec["key"]
        if (ka, kb) in I.DIAG:
            A, B = seeds[q][2], seeds[q][3]
            dx, dy = kb * A[0] + ka * B[0], kb * A[1] + ka * B[1]
            rec["img_dir"] = (("up" if dy < 0 else "down") + "-"
                              + ("left" if dx < 0 else "right"))
    slot_of_chunk: dict[int, list] = {}
    chunk_at: dict[tuple[int, int], int] = {}
    for blk, ch in zip(page["slot_block"], page["slot_chunk"]):
        if ch is None or ch < 0:
            continue
        slot_of_chunk.setdefault(ch, []).append(tuple(blk))
        chunk_at[tuple(blk)] = ch
    sb = I.seed_blocks(page, log, slot_of_chunk, len(seeds))
    I.analyse(truth, R, log, sb, chunk_at)
    bull = {tuple(bz["block"]) for bz in page["bullseyes"]}
    wrong = sum(1 for r in log if r.get("read_correct") is False)
    out = dict(capture=a.capture, reader=a.reader, name=a.name, kind=a.kind, fmt=fmt,
               bullseyes=len(seeds), accepted_blocks=len(chunks),
               chunks_distinct=len({int.from_bytes(x[:2], "big") for x in chunks}),
               seeds_placed=len(sb), wrong_reads=wrong, walls_s=dict(fm_wk=t_wk),
               img_diag=I.img_diag_summary(log, bull), summary=I.summarize(log, bull),
               page_neighbour=I.page_neighbour_summary(log, bull), log=log)
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, a.name + ".json")
    json.dump(out, open(fn, "w"), default=lambda x: x.item() if isinstance(x, np.generic)
              else x)
    print(f"{a.name}: {len(seeds)} bullseyes, {len(chunks)} blocks accepted, chunks "
          f"{out['chunks_distinct']}; seeds placed {len(sb)}; wrong reads {wrong}; "
          f"fm+wk {t_wk:.1f}s -> {fn}")


def main_table(a: argparse.Namespace) -> None:
    order = ("up-left", "up-right", "down-left", "down-right", "axial", "other")
    print("| capture | arm | accepted | chunks | wrong | unread (sound) by walk key "
          "UL / UR / DL / DR / axial / other | ALL unread (sound) | by page relation "
          "UL/UR/DL/DR | by image direction UL/UR/DL/DR | far corner mean / max, all "
          "blocks | far corner of unread mean / max | axis err A / B mean (%) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for fn in a.files:
        d = json.load(open(fn))
        S = d["summary"]
        key = " / ".join(f"{S[c]['unread']}({S[c]['unread_sound']})" for c in order)
        pg = "/".join(str(d["page_neighbour"].get(c, [0, 0])[1]) for c in order[:4])
        im = "/".join(str(d["img_diag"].get(c, [0, 0])[1]) for c in order[:4])
        Al = S["ALL"]

        def f(x: Any, k: int = 2) -> str:
            return "-" if x is None else f"{x:.{k}f}"
        print(f"| {d['name'].split('@')[0]} | {os.path.basename(d['reader'])[:-3]} | "
              f"{d['accepted_blocks']} | {d['chunks_distinct']} | {d['wrong_reads']} | {key} | "
              f"{Al['unread']}({Al['unread_sound']}) / {Al['blocks']} | {pg} | {im} | "
              f"{f(Al['far_mean'])} / {f(Al['far_max'])} | {f(Al['unread_far_mean'])} / "
              f"{f(Al['unread_far_max'])} | "
              f"{f(None if Al['axA_mean'] is None else 100 * Al['axA_mean'])} / "
              f"{f(None if Al['axB_mean'] is None else 100 * Al['axB_mean'])} |")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("capture")
    r.add_argument("--reader", required=True)
    r.add_argument("--page", required=True)
    r.add_argument("--grid", required=True)
    r.add_argument("--kind", required=True, choices=("render", "raster", "grid", "photo"))
    r.add_argument("--sidecar")
    r.add_argument("--name", required=True)
    r.add_argument("--out", default=OUT)
    t = sub.add_parser("table")
    t.add_argument("files", nargs="+")
    a = ap.parse_args()
    main_run(a) if a.cmd == "run" else main_table(a)


if __name__ == "__main__":
    main()
