"""Scan-free checks of receiver_arch.py / receiver_arch_os.py (harness only).

main()'s own glue is driven with a stand-in Receiver whose one volume holds
a given payload (so the code that runs after a close is the file's own):
  synthetic   a small ustar (tarfile) with a path over 100 bytes (prefix
              field), a '%' and spaces in a name, an empty file, binary
              bytes -> container -> both receivers -> files compared (no
              directory member: arch_pack.check_tar refuses one, checked);
  badcrc      the same container with its CRC field flipped: nothing unpacked;
  plain       a payload without the magic: payload.bin only;
  T2          build/r3/arch/e2e_arch/T2/container.bin (arch_pack.py) -> both
              receivers -> every file compared with the worktree.
  env/bin/python bootstrap/r3/arch/test_arch.py [synthetic badcrc plain T2]
Work directories under build/r3/arch/unit/ (emptied first).
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tarfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import arch_pack  # noqa: E402

ROOT = HERE.parents[2]
OUT = HERE.parents[1] / "build" / "r3" / "arch"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), HERE / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def drive(mod, payload, work):
    """Run mod.main() in `work` with one fake scan whose volume closes with `payload`."""
    class V:
        number, scans, written = 1, ["fake"], None

    v = V()
    v.payload = payload

    class FakeRx:
        def __init__(self):
            self.volumes, self.loose = [], []

        def read_scan(self, name, dpi):
            self.volumes = [v]
            return "fake scan read"

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    old_rx, old_in, cwd = mod.Receiver, sys.stdin, os.getcwd()
    mod.Receiver, sys.stdin = FakeRx, io.StringIO("fake\n\n")
    out = io.StringIO()
    try:
        os.chdir(work)
        t = time.time()
        with contextlib.redirect_stdout(out):
            mod.main()
        dt = time.time() - t
    finally:
        os.chdir(cwd)
        mod.Receiver, sys.stdin = old_rx, old_in
    return out.getvalue(), dt


def flat(p):
    return p.replace("%", "%25").replace("/", "%2F")


def compare(work, members, os_variant):
    """members: {path: bytes}; every file must be there byte-exact, nothing else."""
    bad = []
    for p, data in members.items():
        q = work / (p if os_variant else flat(p))
        if not q.is_file() or q.read_bytes() != data:
            bad.append(p)
    if os_variant:
        found = {str(q.relative_to(work)) for q in work.rglob("*") if q.is_file()}
    else:
        found = {q.name for q in work.iterdir()}
        members = {flat(p): 0 for p in members}
    extra = sorted(found - set(members) - {"payload.bin"})
    return bad, extra


def synthetic_members():
    long_dir = "d" * 60 + "/" + "e" * 50
    return {
        long_dir + "/" + "f" * 40 + ".txt": b"a path over 100 bytes: the ustar prefix field\n",
        "odd/50%off and spaces.md": b"percent and spaces\n",
        "odd/empty": b"",
        "bin/all-bytes": bytes(range(256)) * 9,
        "top.txt": b"top level\n" * 1000,
    }


def synthetic_tar(members, with_dir=False):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        if with_dir:
            d = tarfile.TarInfo("odd")
            d.type, d.mode = tarfile.DIRTYPE, 0o755
            t.addfile(d)
        for p in sorted(members):
            ti = tarfile.TarInfo(p)
            ti.size, ti.mtime, ti.mode = len(members[p]), 0, 0o644
            t.addfile(ti, io.BytesIO(members[p]))
    return buf.getvalue()


def main():
    cases = sys.argv[1:] or ["synthetic", "badcrc", "plain", "T2"]
    mods = {"flat": load("receiver_arch.py"), "os": load("receiver_arch_os.py")}
    results = []
    members = synthetic_members()
    tar = synthetic_tar(members)
    syn = None
    try:
        arch_pack.check_tar(synthetic_tar(members, with_dir=True))
        print("check_tar accepted a directory member: FAIL")
        results.append({"case": "dir member refused", "ok": False})
    except AssertionError:
        results.append({"case": "dir member refused", "ok": True})
    for case in cases:
        if case in ("synthetic", "badcrc"):
            syn = syn or arch_pack.container(tar, arch_pack.coder_bytes(tar))
            payload = syn if case == "synthetic" else syn[:12] + bytes(b ^ 1 for b in syn[12:16]) + syn[16:]
            expect = members if case == "synthetic" else {}
        elif case == "plain":
            payload, expect = b"not an archive, just bytes\n" * 50, {}
        else:
            payload = (OUT / "e2e_arch" / case / "container.bin").read_bytes()
            files = (OUT / "e2e_arch" / case / (case + ".files")).read_text().split()
            expect = {f: (ROOT / f).read_bytes() for f in files}
        for kind, mod in mods.items():
            work = OUT / "unit" / ("%s_%s" % (case, kind))
            text, dt = drive(mod, payload, work)
            got_payload = (work / "payload.bin").read_bytes() == payload
            bad, extra = compare(work, expect, kind == "os")
            printed = [l for l in text.splitlines() if l in expect]
            row = {"case": case, "receiver": kind, "payload_bin_ok": got_payload,
                   "files": len(expect), "files_bad": len(bad), "extra": extra,
                   "paths_printed": len(printed), "seconds": round(dt, 1),
                   "messages": [l for l in text.splitlines() if l not in expect][:6]}
            if case == "badcrc":
                row["refused"] = any("CRC-32 wrong" in l for l in text.splitlines()) and not extra
            ok = got_payload and not bad and not extra and len(printed) == len(expect) and row.get("refused", True)
            row["ok"] = ok
            results.append(row)
            print(json.dumps(row), flush=True)
    (OUT / "unit" / "results.json").write_text(json.dumps(results, indent=1))
    print("ALL OK" if all(r["ok"] for r in results) else "FAILURES")


if __name__ == "__main__":
    main()
