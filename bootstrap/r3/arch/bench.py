"""Bench one archival codec on one tree (harness only).

  env/bin/python bootstrap/r3/arch/bench.py CODEC TREE [PREFIX_BYTES] [--no-decode]

CODEC names a pair in this directory: dec_CODEC.py (the decoder, pure Python,
no imports; its region between '# BEGIN DECODER' and '# END DECODER' is what
the monolith carries; it defines unz(z) -> bytes) and enc_CODEC.py (defines
enc(data) -> z; may import anything).  TREE = T1 | T2 | T2R | a .tar/.shar
path; PREFIX_BYTES cuts the input (for the linearity checks).
Encodes (timed), decodes in a fresh process (timed, peak RSS), compares.
Prints one JSON line and appends it to bootstrap/build/r3/arch/bench.jsonl;
the coded bytes go to build/r3/arch/coded/CODEC.TREE[.PREFIX].z."""
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "build" / "r3" / "arch"

CHILD = r'''
import sys, time, resource, importlib.util
spec = importlib.util.spec_from_file_location("d", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
z = open(sys.argv[2], "rb").read()
t = time.time(); out = m.unz(z); dt = time.time() - t
open(sys.argv[3], "wb").write(out)
print(dt, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
'''


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    codec, tree = a[0], a[1]
    prefix = int(a[2]) if len(a) > 2 else None
    src = Path(tree) if "/" in tree else OUT / (tree + ".tar")
    data = src.read_bytes()
    if prefix:
        data = data[:prefix]
    tag = "%s.%s%s" % (codec, src.name, "" if prefix is None else ".%d" % prefix)
    (OUT / "coded").mkdir(parents=True, exist_ok=True)
    enc = load(HERE / ("enc_%s.py" % codec))
    t = time.time()
    z = enc.enc(data)
    enc_s = time.time() - t
    zp = OUT / "coded" / (tag + ".z")
    zp.write_bytes(z)
    row = {"codec": codec, "input": src.name, "prefix": prefix, "raw": len(data), "coded": len(z),
           "ratio": round(len(z) / len(data), 5), "enc_s": round(enc_s, 1)}
    if "--no-decode" not in sys.argv:
        op = OUT / "coded" / (tag + ".out")
        r = subprocess.run([sys.executable, "-c", CHILD, str(HERE / ("dec_%s.py" % codec)), str(zp), str(op)],
                           capture_output=True, text=True)
        if r.returncode:
            row["error"] = r.stderr[-2000:]
        else:
            dt, rss = r.stdout.split()
            row.update(dec_s=round(float(dt), 1), dec_rss_mb=round(int(rss) / 1048576, 1),
                       roundtrip=op.read_bytes() == data,
                       us_per_byte=round(float(dt) * 1e6 / max(1, len(data)), 2))
            os.remove(op)
    print(json.dumps(row), flush=True)
    with open(OUT / "bench.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
