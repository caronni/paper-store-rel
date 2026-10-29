"""Sizes of the R3 monolith in every form, compressed, in R2 pages; the
stdlib-allowed variant; the runtime per page.  Harness only.

Forms of bootstrap/r3/receiver.py (each written to build/r3/forms/):
  raw         the readable file as it stands
  stripped    comments and docstrings removed (ast.unparse: names and code
              unchanged, layout normalised)
  minified    python-minifier (rename locals, remove annotations/docstrings,
              hoist literals, constant folding ...), module names kept
  minified-g  the same with module-level names renamed too (safe: b.py is a
              script nobody imports)
  stdlib-*    the variant that may import the standard library: hashlib
              (SHA-256), zlib (CRC-32), math (cos/sin, gcd) replace the
              receiver's own code; AES, BCH, LDPC, the fountain, the PGM
              reader have no stdlib equivalent
Compression: cm2 v2 (bootstrap/typed/cm2_enc.py, orders from cm2_dec.py) with
the R2 chain's primer r.py (bootstrap/build/loader/r.py = the loader's
definitions + the stage-2 reader, what the finder's machine holds when b.py
is decoded); zlib -9 and lzma (xz, preset 9e) for reference.  R2 pages =
ceil(bytes / 5,304).
Runtime: the per-stage seconds that scan_stats.py wrote to build/r3/stats/.
The byte-exact runs of the minified forms: run_all.py --receiver (tags
_min, _ming, _stdlib) wrote build/r3/runs/summary_<tag>.json.
  PYTHONPATH=src env/bin/python bootstrap/r3/measure.py [--no-cm2-decode]
Writes build/r3/measure.json and prints the tables.
"""
import ast
import json
import lzma
import math
import sys
import time
import zlib
from pathlib import Path

import python_minifier

HERE = Path(__file__).resolve().parent
BOOT = HERE.parents[0]
OUT = BOOT / "build" / "r3"
FORMS = OUT / "forms"
sys.path.insert(0, str(BOOT / "typed"))
import cm2_enc  # noqa: E402
import cm2_dec  # noqa: E402

PAGE = 5304
ORDERS = cm2_enc.orders_of(str(BOOT / "typed" / "cm2_dec.py"))
PRIMER_PATH = BOOT / "build" / "loader" / "r.py"
if PRIMER_PATH.exists():
    PRIMER, PRIMER_NAME = PRIMER_PATH.read_bytes(), "bootstrap/build/loader/r.py"
else:
    a = (BOOT / "loader" / "a.py").read_bytes()
    PRIMER = a[39:608] + (BOOT / "r2reader" / "reader_lite_v1.py").read_bytes()
    PRIMER_NAME = "loader/a.py[39:608] + r2reader/reader_lite_v1.py"


def strip(src):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            b = node.body[0]
            if isinstance(b, ast.Expr) and isinstance(getattr(b, "value", None), ast.Constant) \
                    and isinstance(b.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree) + "\n"


STDLIB_DROP = {"_root_bits", "PRIMES", "SHA_H0", "SHA_K", "sha256", "CRC_TABLE", "crc32",
               "cos_sin", "gcd"}
STDLIB_ADD = '''import hashlib, math, zlib


def sha256(data):
    return hashlib.sha256(data).digest()


crc32, gcd = zlib.crc32, math.gcd


def cos_sin(deg):
    return math.cos(math.radians(deg)), math.sin(math.radians(deg))
'''


def stdlib_variant(src):
    tree = ast.parse(src)
    body = []
    for node in tree.body:
        names = set()
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names = {node.name}
        elif isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "_n":
            names = {"CRC_TABLE"}           # the loop that fills the CRC table
        if names & STDLIB_DROP:
            continue
        body.append(node)
    add = ast.parse(STDLIB_ADD).body
    tree.body = body[:1] + add + body[1:]   # after the module docstring
    return ast.unparse(tree) + "\n"


def minify(src, rename_globals=False):
    return python_minifier.minify(src, remove_literal_statements=True,
                                  rename_globals=rename_globals) + "\n"


def sizes(b, name, decode=False):
    t = time.time()
    x = cm2_enc.encode(b, PRIMER, ORDERS)
    enc_s = time.time() - t
    row = {"form": name, "bytes": len(b), "cm2": len(x), "cm2_encode_s": round(enc_s, 1),
           "zlib9": len(zlib.compress(b, 9)),
           "lzma": len(lzma.compress(b, preset=9 | lzma.PRESET_EXTREME)),
           "r2_pages_cm2": math.ceil(len(x) / PAGE), "r2_pages_raw": math.ceil(len(b) / PAGE)}
    if decode:
        t = time.time()
        back = cm2_dec.decode(x, len(b), PRIMER)
        row["cm2_decode_s"] = round(time.time() - t, 1)
        row["cm2_roundtrip"] = back == b
    return row


def main():
    FORMS.mkdir(parents=True, exist_ok=True)
    src = (HERE / "receiver.py").read_text()
    std = stdlib_variant(src)
    forms = {
        "raw": src,
        "stripped": strip(src),
        "minified": minify(src),
        "minified-g": minify(src, True),
        "stdlib-stripped": strip(std),
        "stdlib-minified-g": minify(std, True),
    }
    files = {"raw": "receiver.py", "stripped": "receiver.stripped.py",
             "minified": "receiver.min.py", "minified-g": "receiver.ming.py",
             "stdlib-stripped": "receiver.stdlib.py", "stdlib-minified-g": "receiver.stdlib.ming.py"}
    rows = []
    for name, text in forms.items():
        (FORMS / files[name]).write_text(text)
        compile(text, files[name], "exec")
        rows.append(sizes(text.encode(), name, decode=name in ("minified-g", "stdlib-minified-g")
                          and "--no-cm2-decode" not in sys.argv))
        r = rows[-1]
        print(f"{name:18s} {r['bytes']:7d} B  cm2 {r['cm2']:6d}  zlib-9 {r['zlib9']:6d}  "
              f"lzma {r['lzma']:6d}  R2 pages (cm2) {r['r2_pages_cm2']}  "
              f"(raw {r['r2_pages_raw']})  enc {r['cm2_encode_s']} s"
              + (f"  dec {r['cm2_decode_s']} s ok={r['cm2_roundtrip']}" if "cm2_decode_s" in r else ""),
              flush=True)
    lines = {n: len(t.splitlines()) for n, t in forms.items()}
    # the LDPC table alone (what no rewrite can shrink)
    tbl = src[src.index("    # LDPC-TABLE-BEGIN"):src.index("    # LDPC-TABLE-END")]
    hexdigits = "".join(c for line in tbl.splitlines()[1:] for c in line.strip().strip("'"))
    table = {"hex_digits": len(hexdigits), "bits": int(hexdigits, 16).bit_length(),
             "bytes_info": math.ceil(int(hexdigits, 16).bit_length() / 8)}
    # marginal compressed cost of each section (cm2 of the stripped prefix)
    st = forms["stripped"]
    anchors = [("row constants", "CELL_DOTS ="), ("SHA-256", "def _root_bits"),
               ("AES + keystream draws", "def _xtime"), ("sites + word scramble", "def _bounded"),
               ("BCH word", "def _bch_generator"), ("LDPC table (data)", "LDPC_TABLE ="),
               ("LDPC expand + decode + CRC", "def _ldpc_checks"),
               ("scan: PGM, lattice, placement, LLRs", "ROT_M ="),
               ("geometry helpers", "def cos_sin"), ("volume: metadata + fountain + envelope", "class Volume"),
               ("reader loop", "class Receiver")]
    cuts = [("\n" + st).index("\n" + a) for _, a in anchors] + [len(st)]
    prev, breakdown = 0, []
    for (name, _), end in zip(anchors, cuts[1:]):
        c = len(cm2_enc.encode(st[:end].encode(), PRIMER, ORDERS))
        breakdown.append({"section": name, "stripped_bytes": end - cuts[anchors.index((name, _))],
                          "cm2_marginal": c - prev})
        prev = c
    print("section breakdown (stripped form, marginal cm2 bytes):")
    for b in breakdown:
        print(f"  {b['section']:40s} {b['stripped_bytes']:6d} B  cm2 +{b['cm2_marginal']}")
    stats = {}
    for p in sorted((OUT / "stats").glob("*.json")):
        stats[p.stem] = json.loads(p.read_text())
    runs = {}
    for p in sorted((OUT / "runs").glob("summary*.json")):
        runs[p.stem] = {k: {"byte_exact": v["byte_exact"], "wall_s": v["wall_s"]}
                        for k, v in json.loads(p.read_text()).items()}
    res = {"primer": PRIMER_NAME, "primer_bytes": len(PRIMER), "orders": list(ORDERS),
           "sizes": rows, "lines": lines, "breakdown": breakdown, "ldpc_table": table, "runtime": stats, "runs": runs}
    (OUT / "measure.json").write_text(json.dumps(res, indent=1))
    print("lines:", lines)
    print("LDPC table:", table)
    for k, v in stats.items():
        print(f"{k:18s}", v["seconds"], "total", v["total_s"])
    for k, v in runs.items():
        print(k, {c: ("YES" if r["byte_exact"] else "NO", r["wall_s"]) for c, r in v.items()})


if __name__ == "__main__":
    main()
