"""End to end for receiver_arch.py (harness only): a holo volume whose payload
is an archive container (arch_pack.py), simulated flatbed scans of all its
pages, the receiver run as the finder would (a fresh directory, the scan
names on stdin, all pages pooled in a shuffled order), then every unpacked
file compared with the worktree's (flat names mapped back).

  PYTHONPATH=src env/bin/python bootstrap/r3/arch/e2e_arch.py volume TREE
  PYTHONPATH=src env/bin/python bootstrap/r3/arch/e2e_arch.py scans TREE VARIANT
  env/bin/python bootstrap/r3/arch/e2e_arch.py run TREE VARIANT RECEIVER TAG [--os]

volume  make_test_volume.py's own volume(): `holo generate --format
        c3-k-r0550@35x24 --source-fraction 0.5` (A4-6mm) of
        build/r3/arch/e2e_arch/TREE/container.bin, each page's PostScript
        rasterised by ghostscript's bitcmyk K plane (never pbmraw) and
        checked equal to the generator's GT.
scans   make_test_volume.py's simulate() with two variants of its own:
          arch    1200 dpi, 0.5 degree tilt, scale +0.4 %, Canon-like seams,
                  blur 0.5 dot, paper 220 / ink 60 grey, noise sigma 12
          arch40  the same with 40 % of each page's tiles whited out (seeded)
run     RECEIVER = a path (receiver_arch.py, a minified form ...); the
        pages in a shuffled order (seeded by TAG); /usr/bin/time -l for the
        peak memory; every stdout line timestamped, which splits the wall
        into receiving (start -> the 'volume 1 complete' line), decoding +
        CRC ('archive: decoding' -> the first path), unpacking (first ->
        last path) and the scans read after the close.  --os = the
        receiver writes real directories (receiver_arch_os.py).
Outputs in build/r3/arch/e2e_arch/TREE/ (run_TAG/ is emptied first;
result_TAG.json, stdout_TAG.txt).
"""
import hashlib
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE.parents[1] / "build" / "r3" / "arch" / "e2e_arch"
CHANNEL = dict(blur=0.5, paper=220.0, ink=60.0, noise=12.0)
VARIANTS = {"arch": (1200, 0.5, 1.004, True, 0.0), "arch40": (1200, 0.5, 1.004, True, 0.4)}


def mtv_for(tree):
    argv, sys.argv = sys.argv, [sys.argv[0]]
    spec = importlib.util.spec_from_file_location("mtv", HERE.parent / "make_test_volume.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    sys.argv = argv
    work = OUT / tree
    coded = (work / "container.bin").read_bytes()
    m.OUT = work
    m.make_payload = lambda: coded
    m.PAYLOAD_BYTES = len(coded)
    m.VARIANTS.update(VARIANTS)
    for v in VARIANTS:
        m.ROUGH[v] = dict(CHANNEL)
    return m


def flat(p):
    return p.replace("%", "%25").replace("/", "%2F")


def run(tree, variant, receiver, tag, os_variant):
    work = OUT / tree
    rdir = work / ("run_" + tag)
    if rdir.exists():
        shutil.rmtree(rdir)
    rdir.mkdir(parents=True)
    pages = sorted(work.glob("%s_p*.pgm" % variant), key=lambda p: int(p.stem.rsplit("_p", 1)[1]))
    order = pages[:]
    random.Random(tag).shuffle(order)
    stdin = "".join("%s 1200\n" % p for p in order) + "\n"
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    t0 = time.time()
    proc = subprocess.Popen(["/usr/bin/time", "-l", sys.executable, str(Path(receiver).resolve())],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=rdir, env=env, text=True, bufsize=1)
    proc.stdin.write(stdin)
    proc.stdin.close()
    lines = []
    for line in proc.stdout:
        lines.append((round(time.time() - t0, 2), line.rstrip("\n")))
    err = proc.stderr.read()
    proc.wait()
    wall = time.time() - t0
    (work / ("stdout_%s.txt" % tag)).write_text(
        "".join("%9.2f  %s\n" % (t, l) for t, l in lines) + "--- stderr\n" + err)
    files = (work / (tree + ".files")).read_text().split()
    printed = [(t, l) for t, l in lines if l in set(files)]
    t_close = next((t for t, l in lines if "complete:" in l and l.lstrip().startswith(("volume", "scan"))
                    and "written to" in l), None)
    t_dec = next((t for t, l in lines if l == "archive: decoding"), None)
    bad, sizes = [], 0
    for f in files:
        q = rdir / (f if os_variant else flat(f))
        if not q.is_file() or q.read_bytes() != (ROOT / f).read_bytes():
            bad.append(f)
        else:
            sizes += q.stat().st_size
    if os_variant:
        found = {str(q.relative_to(rdir)) for q in rdir.rglob("*") if q.is_file()}
        want = set(files)
    else:
        found = {q.name for q in rdir.iterdir()}
        want = {flat(f) for f in files}
    extra = sorted(found - want - {"payload.bin"})
    container = (work / "container.bin").read_bytes()
    got = (rdir / "payload.bin").read_bytes() if (rdir / "payload.bin").exists() else b""
    rss = re.search(r"(\d+)\s+maximum resident set size", err)
    foot = re.search(r"(\d+)\s+peak memory footprint", err)
    scan_lines = [l.replace("scan (PGM file [dpi]; empty line ends): ", "") for _, l in lines
                  if l.startswith("scan (PGM") and l.strip() != "scan (PGM file [dpi]; empty line ends):"]
    res = {"tree": tree, "variant": variant, "receiver": str(Path(receiver).resolve().relative_to(ROOT)),
           "tag": tag, "os_variant": os_variant, "pages": len(pages),
           "order": [p.stem for p in order], "returncode": proc.returncode,
           "payload_bin_byte_exact": got == container, "payload_sha256": hashlib.sha256(got).hexdigest(),
           "files": len(files), "files_byte_exact": len(files) - len(bad), "files_bad": bad[:20],
           "extra_files": extra[:20], "bytes_restored": sizes,
           "paths_printed": len(printed), "paths_in_tar_order": [l for _, l in printed] == files,
           "wall_s": round(wall, 1),
           "receiving_s": t_close,
           "decode_crc_s": round(printed[0][0] - t_dec, 1) if printed and t_dec else None,
           "unpack_s": round(printed[-1][0] - printed[0][0], 2) if printed else None,
           "after_unpack_s": round(wall - printed[-1][0], 1) if printed else None,
           "scans_before_close": sum(1 for t, l in lines if l.startswith("scan (PGM") and "): " in l
                                     and l.split("): ", 1)[1] and t_close is not None and t <= t_close),
           "max_rss_mb": round(int(rss.group(1)) / 2 ** 20, 1) if rss else None,
           "peak_footprint_mb": round(int(foot.group(1)) / 2 ** 20, 1) if foot else None,
           "scan_lines": scan_lines,
           "other_lines": [l for _, l in lines if not l.startswith("scan (PGM") and l not in set(files)]}
    res["ok"] = (res["payload_bin_byte_exact"] and not bad and not extra and res["paths_printed"] == len(files)
                 and proc.returncode == 0)
    (work / ("result_%s.json" % tag)).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k not in ("scan_lines", "order")}, indent=1))


def main():
    cmd, tree = sys.argv[1], sys.argv[2]
    if cmd == "volume":
        mtv_for(tree).volume()
    elif cmd == "scans":
        mtv_for(tree).scans(sys.argv[3:])
    elif cmd == "run":
        variant, receiver, tag = sys.argv[3:6]
        run(tree, variant, receiver, tag, "--os" in sys.argv)


if __name__ == "__main__":
    main()
