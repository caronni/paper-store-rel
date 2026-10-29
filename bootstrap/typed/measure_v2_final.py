"""measure_v2_final.py -- the finalists of the cm2 v2 round in combination
(masks, adopted for speed, with each order tuple of the frontier, and divmod
against the s=sum(p) line), packed to their own fixed points on the reader
payload, plus the page bundle's bytes per tuple.  Same machinery as
measure_v2.py; appends a 'final' section to its result file.
With --all: THE FRONTIER -- every tuple of measure_v2's two order rounds and
the finalists, in the adopted spelling only (masks + the s=sum(p) line, the
program make_typed builds), each with its typed total, data lines, page
bundle bytes and pages (R2-FORMAT v1: 26-byte chunks, 204 chunks a page);
written as the section 'frontier' (and a table on stdout).
Usage: python measure_v2_final.py [--all] [--reader PATH --n2 N]
                                  [--bundle PATH --primer PATH] [--result PATH]"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_v2 as M  # noqa: E402

TUPLES = [(0, 1, 2, 3, 4, 6), (0, 1, 2, 3, 4, 6, 8, 12), (0, 1, 2, 3, 4, 6, 8, 12, 16),
          (0, 1, 2, 3, 4, 6, 8, 12, 16, 24), (0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32)]
CHUNK, PER_PAGE = 26, 204


def job(args):
    orders, sline = args
    tpl = M.apply(M.with_orders(M.BASE, orders), M.MASKS + (M.SLINE if sline else []))
    r = M.pack(tpl, M.READER['big'], dict(M.SEM, orders=orders))
    r.pop('prog')
    name = f'masks, {orders}, {"x%s and x//s (s line)" if sline else "divmod"}'
    if not sline or '--all' in sys.argv:
        b = (M.V2.encode_int(M.BUNDLE, M.PAGE_PRIMER, orders).bit_length() + 7) // 8
        r['page bytes'] = b
        r['pages'] = -(-(-(-b // CHUNK)) // PER_PAGE)
    return name, orders, r


def main():
    path = M.RESULT
    res = json.load(open(path)) if os.path.exists(path) else {}
    if '--all' in sys.argv:
        tuples = []
        for t in TUPLES + M.ORDERS + M.ORDERS2:
            if t not in tuples:
                tuples.append(t)
        jobs, sec = [(t, True) for t in tuples], 'frontier'
    else:
        jobs, sec = [(o, s) for o in TUPLES for s in (False, True)], 'final'
    rows = []
    with ProcessPoolExecutor(8) as pool:
        for name, orders, r in pool.map(job, jobs):
            res.setdefault(sec, {})[name] = r
            rows.append((orders, r))
            print(name, '|', json.dumps(r), flush=True)
    if sec == 'frontier':
        print(f"{'orders':<40} {'a.py':>5} {'data':>5} {'lines':>5} {'typed':>6} {'page B':>7} {'pages':>5}")
        for orders, r in sorted(rows, key=lambda x: x[1]['typed']):
            print(f"{str(orders):<40} {r['a.py chars']:>5} {r['data chars']:>5} {r['data lines']:>5} "
                  f"{r['typed']:>6} {r['page bytes']:>7} {r['pages']:>5}")
    json.dump(res, open(path, 'w'), indent=1)


if __name__ == '__main__':
    main()
