"""e2e_c.py -- the R3 record's end to end (bootstrap/r3/arch/e2e_arch.py) for
stage 3's c.py at the r0547 row.  Harness only (numpy, scipy, ghostscript,
src/holo); c.py itself never imports anything.

What it reuses unchanged: e2e_arch.py's mtv_for() (make_test_volume.py's own
volume() and simulate(), its two channel variants 'arch' and 'arch40', their
seeds), its timing split, its /usr/bin/time -l peak memory.  What differs:
  - the row: make_test_volume's FORMAT is set to c3-k-r0547@35x24 (ruling 36);
    the record's was c3-k-r0550@35x24;
  - the container is the RECORD's (build/r3/arch/e2e_arch/T1/container.bin,
    sha256 78d9a4b4..., T1 = 321 files), copied, not re-encoded (the archive
    layer is row-independent); where that directory lacks it, prepare() makes
    it again: T1.tar from the blobs of T1_COMMIT (arch_pack.py --commit), the
    container by arch_pack's derived encoder (13 min, 1.4 GB; the same bytes,
    CONTROL-REBUILD-2026-10-23 §1.3), and the shas are checked as for a copy;
  - truth for the unpacked files is the record's T1.tar itself (three of its
    321 files have since changed in the worktree, so the worktree is not the
    truth; at T1_COMMIT all 321 are the tar's);
  - outputs under bootstrap/build/stage3/e2e/T1/.

  PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py volume
  PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py scans arch arch40
  env/bin/python bootstrap/stage3/e2e_c.py run VARIANT RECEIVER TAG
  PYTHONPATH=src env/bin/python bootstrap/stage3/e2e_c.py holo3 VARIANT [WORKERS]
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
import tarfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOT = HERE.parent
ROOT = BOOT.parent
REC = BOOT / "build" / "r3" / "arch" / "e2e_arch" / "T1"
OUT = BOOT / "build" / "stage3" / "e2e"
TREE = "T1"
FORMAT = "c3-k-r0547@35x24"
CONTAINER_SHA = "78d9a4b461923351ec0aa3bfd670104cb6c2def1e207a5db813fa4110c90168e"
TAR_SHA = "d1aaf1ddd2c1007fefa315320eeef570c1e4677f24f070f8af4d9be191785846"
T1_COMMIT = "2115a595ecd5792bbd2dc68bad46377d7e84b9a8"   # 2115a595, the archival-layer commit of ruling 28


def e2e_arch():
    spec = importlib.util.spec_from_file_location("e2e_arch", BOOT / "r3" / "arch" / "e2e_arch.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.OUT = OUT
    return m


def regenerate():
    """The record's T1.tar and container.bin into REC, from T1_COMMIT and
    receiver_arch.py (arch_pack.py T1 --commit T1_COMMIT, without its json)."""
    sys.path.insert(0, str(BOOT / "r3" / "arch"))
    import arch_pack
    REC.mkdir(parents=True, exist_ok=True)
    if not (REC / "T1.tar").exists():
        files, tar, _ = arch_pack.tree_tar(TREE, T1_COMMIT)
        (REC / "T1.tar").write_bytes(tar)
        (REC / "T1.files").write_text("\n".join(files) + "\n")
    if not (REC / "container.bin").exists() and not (OUT / TREE / "container.bin").exists():
        tar = (REC / "T1.tar").read_bytes()
        assert hashlib.sha256(tar).hexdigest() == TAR_SHA, "T1.tar"
        print("e2e_c: encoding the T1 container (strong2, about 13 min, 1.4 GB)", file=sys.stderr, flush=True)
        (REC / "container.bin").write_bytes(arch_pack.container(tar, arch_pack.coder_bytes(tar)))


def prepare():
    work = OUT / TREE
    work.mkdir(parents=True, exist_ok=True)
    if not all((work / n).exists() or (REC / n).exists() for n in ("container.bin", "T1.tar")):
        regenerate()
    for name, sha in (("container.bin", CONTAINER_SHA), ("T1.tar", TAR_SHA)):
        dst = work / name
        if not dst.exists():
            shutil.copyfile(REC / name, dst)
        assert hashlib.sha256(dst.read_bytes()).hexdigest() == sha, name
    return work


def mtv():
    prepare()
    m = e2e_arch().mtv_for(TREE)
    m.FORMAT = FORMAT
    return m


def truth_files():
    t = tarfile.open(OUT / TREE / "T1.tar")
    return [(m.name, t.extractfile(m).read()) for m in t.getmembers()]


def flat(p):
    return p.replace("%", "%25").replace("/", "%2F")


def run(variant, receiver, tag):
    """e2e_arch.run with the truth from T1.tar (flat names, no --os)."""
    work = OUT / TREE
    rdir = work / ("run_" + tag)
    if rdir.exists():
        shutil.rmtree(rdir)
    rdir.mkdir(parents=True)
    pages = sorted(work.glob("%s_p*.pgm" % variant), key=lambda p: int(p.stem.rsplit("_p", 1)[1]))
    order = pages[:]
    random.Random(tag).shuffle(order)
    stdin = "".join("%s 1200\n" % p for p in order) + "\n"
    env = dict(os.environ)          # -I ignores PYTHON* variables, so -u unbuffers (the timing split)
    env.pop("PYTHONPATH", None)
    t0 = time.time()
    proc = subprocess.Popen(["/usr/bin/time", "-l", sys.executable, "-I", "-u", str(Path(receiver).resolve())],
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
    truth = truth_files()
    names = [n for n, _ in truth]
    printed = [(t, l) for t, l in lines if l in set(names)]
    t_close = next((t for t, l in lines if "complete:" in l and l.lstrip().startswith(("volume", "scan"))
                    and "written to" in l), None)
    t_dec = next((t for t, l in lines if l == "archive: decoding"), None)
    bad, sizes = [], 0
    for n, data in truth:
        q = rdir / flat(n)
        if not q.is_file() or q.read_bytes() != data:
            bad.append(n)
        else:
            sizes += len(data)
    found = {q.name for q in rdir.iterdir()}
    extra = sorted(found - {flat(n) for n in names} - {"payload.bin"})
    container = (work / "container.bin").read_bytes()
    got = (rdir / "payload.bin").read_bytes() if (rdir / "payload.bin").exists() else b""
    rss = re.search(r"(\d+)\s+maximum resident set size", err)
    foot = re.search(r"(\d+)\s+peak memory footprint", err)
    res = {"tree": TREE, "variant": variant, "format": FORMAT,
           "receiver": str(Path(receiver).resolve().relative_to(ROOT)),
           "receiver_sha256": hashlib.sha256(Path(receiver).read_bytes()).hexdigest(),
           "tag": tag, "pages": len(pages), "order": [p.stem for p in order], "returncode": proc.returncode,
           "payload_bin_byte_exact": got == container, "payload_sha256": hashlib.sha256(got).hexdigest(),
           "files": len(names), "files_byte_exact": len(names) - len(bad), "files_bad": bad[:20],
           "extra_files": extra[:20], "bytes_restored": sizes,
           "paths_printed": len(printed), "paths_in_tar_order": [l for _, l in printed] == names,
           "crc_wrong_printed": any(l == "archive: CRC-32 wrong" for _, l in lines),
           "wall_s": round(wall, 1), "receiving_s": t_close,
           "decode_crc_s": round(printed[0][0] - t_dec, 1) if printed and t_dec else None,
           "unpack_s": round(printed[-1][0] - printed[0][0], 2) if printed else None,
           "after_unpack_s": round(wall - printed[-1][0], 1) if printed else None,
           "scans_before_close": sum(1 for t, l in lines if l.startswith("scan (PGM") and "): " in l
                                     and l.split("): ", 1)[1] and t_close is not None and t <= t_close),
           "max_rss_mb": round(int(rss.group(1)) / 2 ** 20, 1) if rss else None,
           "peak_footprint_mb": round(int(foot.group(1)) / 2 ** 20, 1) if foot else None,
           "scan_lines": [l for _, l in lines if l.startswith("scan (PGM")],
           "other_lines": [l for _, l in lines if not l.startswith("scan (PGM") and l not in set(names)]}
    res["ok"] = (res["payload_bin_byte_exact"] and not bad and not extra and res["paths_printed"] == len(names)
                 and proc.returncode == 0)
    (work / ("result_%s.json" % tag)).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k not in ("scan_lines", "order")}, indent=1))


def holo3(variant, workers="4"):
    """holo's own receiver (python -m holo.receiver decode) on every page of the
    variant at the declared row: does the format authority's reader agree that
    these pages are c3-k-r0547 and close the same volume?  (The record's
    holo3_crosscheck.py ran one scan of the 2-page r0550 volume, stopped at 15
    min; this runs all pages, uncapped.)"""
    work = OUT / TREE
    rd = work / ("holo3_" + variant)
    if rd.exists():
        shutil.rmtree(rd)
    rd.mkdir(parents=True)
    pages = sorted(work.glob("%s_p*.pgm" % variant), key=lambda p: int(p.stem.rsplit("_p", 1)[1]))
    payload = rd / "payload.bin"
    cmd = [sys.executable, "-m", "holo.receiver", "decode", *map(str, pages)]
    for _ in pages:
        cmd += ["--dpi", "1200"]
    cmd += ["--format", FORMAT, "--out", str(payload), "--workers", workers, "--run-dir", str(rd / "rundir")]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    t = time.time()
    with open(rd / "log.txt", "w") as log:
        cp = subprocess.run(["/usr/bin/time", "-l"] + cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
    wall = time.time() - t
    got = payload.read_bytes() if payload.exists() else b""
    container = (work / "container.bin").read_bytes()
    res = {"variant": variant, "format": FORMAT, "workers": workers, "exit": cp.returncode,
           "wall_s": round(wall, 1), "payload_byte_exact": got == container,
           "payload_sha256": hashlib.sha256(got).hexdigest() if got else None, "cmd": cmd}
    (work / ("holo3_%s.json" % variant)).write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


def main():
    cmd = sys.argv[1]
    if cmd == "volume":
        mtv().volume()
    elif cmd == "scans":
        mtv().scans(sys.argv[2:])
    elif cmd == "run":
        prepare()
        run(*sys.argv[2:5])
    elif cmd == "holo3":
        holo3(*sys.argv[2:4])


if __name__ == "__main__":
    main()
