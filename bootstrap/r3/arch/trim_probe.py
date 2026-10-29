"""Probe: cm2 cost of trims of receiver_arch.py (harness only).  Each
variant is built in memory from make_arch.build() by string replacement,
minified-g as bootstrap/r3/measure.py does it, cm2 v2 with the r.py primer;
the 2-page line is 10,608 B.  The probes were run against make_arch.py as it
stood at each step (the first sets against the untrimmed build, which the
replacements expect), so today only --dec3 and --os still apply cleanly:
  PYTHONPATH=src env/bin/python bootstrap/r3/arch/trim_probe.py [--more|--more2|--msgs|--dec3|--os]
What they measured (cm2 of minified-g; the untrimmed build was 10,670):
  progress line 'archive of %d bytes: decoding' -> 'archive: decoding' about
  -15 (dropping it: -23), failure message short
  -11, the one-expression name -5, no tar type check -10, the NEUTRAL
  decoder rewrites -17, the magic inlined about -4 (together 10,599, kept);
  dropping the prefix field -19 and an assert instead of the CRC message
  -15 (not taken); `import os` +21..23 over the flat build whatever the
  makedirs spelling (10,618..10,623: 3 R2 pages); 'if not j & 3' and
  'while x1 ^ x2 < 1 << 24' -1 each (not taken).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import measure as M  # noqa: E402
import make_arch as A  # noqa: E402

PROGRESS = "                    print('archive of %d bytes: decoding' % int.from_bytes(v.payload[4:12], 'big'))\n"
FAIL = "print('archive CRC-32 wrong: nothing unpacked')"
NAME_OLD = "        f = ((h[345:500].rstrip(b'\\0') + b'/' if h[345] else b'') + h[:100].rstrip(b'\\0')).decode()\n"
NAME_NEW = "        f = (h[345:500] + b'/' + h[:100]).replace(b'\\0', b'').lstrip(b'/').decode()\n"
TYPE_OLD = "        if h[156] in b'0\\0':\n            print(f)\n            open("
TYPE_NEW = "        if 1:\n            print(f)\n            open("
GLUE_IF = ("                    if crc32(d) == int.from_bytes(v.payload[12:16], 'big'):\n"
           "                        unpack(d)\n"
           "                    else:\n"
           "                        print('archive CRC-32 wrong: nothing unpacked')\n")

DEC = [
    ("        pl, ls = (ls, i) if c == 10 else (pl, ls)\n", "        if c == 10:\n            pl, ls = ls, i\n"),
    ("        c, c0, h = b[i - 1], 1, (h << 8 | b[i - 1]) & 0xFFFFFFFFFFFFFF\n",
     "        c, c0 = b[i - 1], 1\n        h = (h << 8 | c) & Q >> 8\n"),
    ("    x1, x2, x, kk, h = 0, 0, 0, 0, 0\n    wh, wp, mp, ml, pl, ls = 0, 0, 0, 0, 8, 8\n",
     "    x1 = x2 = x = kk = h = wh = wp = mp = ml = 0\n    pl = ls = 8\n"),
    ("    for i in range(8, len(b)):\n", "    for i in range(8, n + 8):\n"),
    ("                            t = t ^ 16\n                        else:\n                            if T[t + 1] & 15 > T[t ^ 17] & 15:\n                                t = t ^ 16\n",
     "                            t ^= 16\n                        else:\n                            if T[t + 1] & 15 > T[t ^ 17] & 15:\n                                t ^= 16\n"),
]
PREFIX = (NAME_OLD, "        f = h[:100].rstrip(b'\\0').decode()\n")
ASSERT = (GLUE_IF, "                    assert crc32(d) == int.from_bytes(v.payload[12:16], 'big')\n                    unpack(d)\n")

DEC2 = [("    F, Q, q, k = 4294967295, 18446744073709551615, 1460000, 28\n",
         "    F, q, k = 2 ** 32 - 1, 1460000, 28\n    Q = F * F + F + F\n")]
MAGIC_INLINE = [("ARCH_MAGIC = b'R3A1'\n", ""), ("if v.payload[:4] == ARCH_MAGIC:", "if v.payload[:4] == b'R3A1':")]


def variant(steps, os_variant=False):
    _, out = A.build(os_variant)
    for old, new in steps:
        assert out.count(old) == 1, old
        out = out.replace(old, new)
    return out


def cost(text):
    ming = M.minify(text, True)
    compile(ming, "v", "exec")
    return len(M.cm2_enc.encode(ming.encode(), M.PRIMER, M.ORDERS)), len(ming)


def main():
    p = (PROGRESS, "")
    p2 = (PROGRESS, PROGRESS.replace("'archive of %d bytes: decoding' % int.from_bytes(v.payload[4:12], 'big')",
                                     "'decoding the archive'"))
    f = (FAIL, "print('archive: bad CRC')")
    nm = (NAME_OLD, NAME_NEW)
    ty = (TYPE_OLD, TYPE_NEW)
    g2 = (GLUE_IF, "                    unpack(d) if crc32(d) == int.from_bytes(v.payload[12:16], 'big') "
                   "else print('archive: bad CRC')\n")
    cases = {"A as built": [], "B no progress": [p], "C B + short fail": [p, f],
             "D C + name expr": [p, f, nm], "E D + no type check": [p, f, nm, ty],
             "F D + short progress": [p2, f, nm], "G F one-line if": [p2, nm, g2],
             "H G no progress": [p, nm, g2], "I F + no type check": [p2, f, nm, ty]}
    if "--more" in sys.argv:
        e = [p, f, nm, ty]
        cases = {"E": e, "E+dec": e + DEC, "D+dec": [p, f, nm] + DEC, "E noprefix": [p, f, PREFIX, ty],
                 "E assert": [p, nm, ty, ASSERT], "F+dec (short progress)": [p2, f, nm] + DEC,
                 "E noprefix+dec": [p, f, PREFIX, ty] + DEC}
    if "--more2" in sys.argv:
        base = [f, nm, ty] + DEC + MAGIC_INLINE
        cases = {"X0 no progress": [p] + base, "X1 short progress": [p2] + base,
                 "X1+DEC2": [p2] + base + DEC2, "X0+DEC2": [p] + base + DEC2,
                 "X1 full progress +DEC2": base + DEC2}
    if "--msgs" in sys.argv:
        base = [f, nm, ty] + DEC + MAGIC_INLINE + DEC2
        P = "'archive of %d bytes: decoding' % int.from_bytes(v.payload[4:12], 'big')"
        def pr(m):
            return (PROGRESS, PROGRESS.replace(P, m))
        def fl(m):
            return (FAIL, "print(%s)" % m)
        cases = {}
        for a in ["'decoding the archive'", "'archive: decoding'", "'decoding'", "'archive: decoding, minutes'"]:
            for b in ["'archive: bad CRC'", "'archive: CRC-32 wrong'", "'bad CRC'"]:
                cases[a + " / " + b] = [pr(a), (FAIL, "print(%s)" % b), nm, ty] + DEC + MAGIC_INLINE + DEC2
    if "--dec3" in sys.argv:
        J = ("            if j == 0 or j == 4:\n", "            if not j & 3:\n")
        W = ("            while (x1 ^ x2) >> 24 == 0:\n", "            while x1 ^ x2 < 1 << 24:\n")
        MP = ("        mp = mp if ml else mt[o]\n", "        if not ml:\n            mp = mt[o]\n")
        L = "        os.makedirs(os.path.dirname(f) or '.', exist_ok=True)\n"
        B = ("        os.makedirs(os.path.dirname(f) or '.', exist_ok=True)\n", "        os.makedirs('./' + f[:f.rfind('/') + 1], exist_ok=True)\n")
        for osv in (False, True):
            for name, steps in {"none": [], "J": [J], "W": [W], "MP": [MP], "J+W": [J, W], "J+W+MP": [J, W, MP]}.items():
                st = steps + ([B] if osv else [])
                c, n = cost(variant(st, osv))
                print(f"{'os' if osv else 'flat'} {name:10s} minified-g {n} B  cm2 {c}  {'fits 2, spare %d' % (2 * M.PAGE - c) if c <= 2 * M.PAGE else 'over by %d' % (c - 2 * M.PAGE)}", flush=True)
        return
    if "--os" in sys.argv:
        L = "        os.makedirs(os.path.dirname(f) or '.', exist_ok=True)\n"
        alts = {"as built": L, "b slice": "        os.makedirs('./' + f[:f.rfind('/') + 1], exist_ok=True)\n",
                "c dirname ./": "        os.makedirs(os.path.dirname('./' + f), exist_ok=True)\n",
                "c exist_ok=1": "        os.makedirs(os.path.dirname('./' + f), exist_ok=1)\n",
                "b exist_ok=1": "        os.makedirs('./' + f[:f.rfind('/') + 1], exist_ok=1)\n"}
        for name, line in alts.items():
            text = variant([(L, line)] if line != L else [], True)
            c, n = cost(text)
            print(f"os {name:20s} minified-g {n} B  cm2 {c}  {'fits 2' if c <= 2 * M.PAGE else 'over by %d' % (c - 2 * M.PAGE)}", flush=True)
        return
    for name, steps in cases.items():
        c, n = cost(variant(steps))
        print(f"{name:24s} minified-g {n} B  cm2 {c}  {'fits 2' if c <= 2 * M.PAGE else 'over by %d' % (c - 2 * M.PAGE)}",
              flush=True)


if __name__ == "__main__":
    main()
