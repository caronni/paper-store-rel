"""unit_c.py -- the record's scan-free checks (bootstrap/r3/arch/test_arch.py,
as compressor-exploration/encoder-side/mono_test.py adapted them to a renamed
form) on stage3/c_readable.py (the source of record) and c.py: main()'s own
glue driven with a stand-in Receiver whose one volume closes with a given
payload.  The archive heartbeat's lines ('archive: N% decoded') are messages,
not paths, and pass.
  synthetic  test_arch's ustar (a path over 100 bytes, '%' and spaces, an
             empty file, binary bytes) in a container: every file byte-exact;
  badcrc     the same container, CRC field flipped: 'archive: CRC-32 wrong',
             nothing but payload.bin;
  plain      a payload without the magic: payload.bin only.
The container is encoded by the encoder derived from receiver_arch.py's own
decoder (arch_pack.arch_encoder's construction; the derived decoder text is
written under build/stage3/unit/, not under r3/).  In c.py the names are
found, not assumed: main = the function the `if __name__` line calls, the
Receiver = the class whose methods include read_scan's spelling, the stand-in
objects' attribute names through make_c.json's M3 map.
  env/bin/python bootstrap/stage3/unit_c.py
Writes build/stage3/unit/results.json.
"""
import ast
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOT = HERE.parent
ARCH = BOOT / "r3" / "arch"
OUT = BOOT / "build" / "stage3" / "unit"
sys.path.insert(0, str(ARCH))
import test_arch as TA  # noqa: E402
import arch_pack  # noqa: E402
import derive  # noqa: E402


def encoder():
    text = (ARCH / "receiver_arch.py").read_text()
    end = "    return bytes(b[8:])\n"
    r = text[text.index("\ndef unz(z):\n") + 1:text.index(end) + len(end)]
    q = r.index('    """')
    r = r[:q] + r[r.index('"""\n', q + 7) + 4:]
    assert r.count(arch_pack.HEAD_ARCH) == 1
    r = r.replace(arch_pack.HEAD_ARCH, arch_pack.HEAD_MOULD)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "dec_arch_derived.py"
    p.write_text("# BEGIN DECODER\n" + r + "# END DECODER\n")
    return derive.make_encoder(str(p))


def load(path):
    spec = importlib.util.spec_from_file_location("form_" + Path(path).stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def names_of(path, amap):
    t = ast.parse(Path(path).read_text())
    last = t.body[-1]
    assert isinstance(last, ast.If) and "__name__" in ast.unparse(last.test)
    main = last.body[0].value.func.id
    rs = amap.get("read_scan", "read_scan")
    rx = [n.name for n in t.body if isinstance(n, ast.ClassDef)
          and any(isinstance(s, ast.FunctionDef) and s.name == rs for s in n.body)]
    assert len(rx) == 1, rx
    return rx[0], main


def drive(mod, rx, mainname, payload, work, A):
    g = lambda n: A.get(n, n)  # noqa: E731
    v = type("V", (), {})()
    for k, val in (("number", 1), ("scans", ["fake"]), ("written", None), ("payload", payload)):
        setattr(v, g(k), val)

    def init(self):
        setattr(self, g("volumes"), [])
        setattr(self, g("loose"), [])

    def read_scan(self, name, dpi):
        setattr(self, g("volumes"), [v])
        return "fake scan read"
    fake = type("FakeRx", (), {"__init__": init, g("read_scan"): read_scan})
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    old_rx, old_in, cwd = getattr(mod, rx), sys.stdin, os.getcwd()
    setattr(mod, rx, fake)
    sys.stdin = io.StringIO("fake\n\n")
    out = io.StringIO()
    try:
        os.chdir(work)
        t = time.time()
        with contextlib.redirect_stdout(out):
            getattr(mod, mainname)()
        dt = time.time() - t
    finally:
        os.chdir(cwd)
        setattr(mod, rx, old_rx)
        sys.stdin = old_in
    return out.getvalue(), dt


def main():
    enc = encoder()
    members = TA.synthetic_members()
    tar = TA.synthetic_tar(members)
    arch_pack.check_tar(tar)
    z = enc(tar)
    assert int.from_bytes(z[:4], "big") == len(tar)
    syn = arch_pack.container(tar, z[4:])
    cases = [("synthetic", syn, members),
             ("badcrc", syn[:12] + bytes(b ^ 1 for b in syn[12:16]) + syn[16:], {}),
             ("plain", b"not an archive, just bytes\n" * 50, {})]
    m3 = json.loads((BOOT / "build" / "stage3" / "make_c.json").read_text())["m3"]["map"]
    forms = [(HERE / "c_readable.py", {}), (HERE / "c.py", m3)]
    results = []
    for path, amap in forms:
        rx, mn = names_of(path, amap)
        mod = load(path)
        for case, payload, expect in cases:
            work = OUT / (path.stem + "_" + case)
            text, dt = drive(mod, rx, mn, payload, work, amap)
            got = (work / "payload.bin").read_bytes() == payload
            bad, extra = TA.compare(work, expect, False)
            printed = [ln for ln in text.splitlines() if ln in expect]
            row = dict(form=str(path.relative_to(BOOT)), receiver_class=rx, main=mn, case=case,
                       payload_bin_ok=got, files=len(expect), files_bad=len(bad), extra=extra,
                       paths_printed=len(printed), seconds=round(dt, 1),
                       messages=[ln for ln in text.splitlines() if ln not in expect][:4])
            if case == "badcrc":
                row["refused"] = any("CRC-32 wrong" in ln for ln in text.splitlines()) and not extra
            row["ok"] = got and not bad and not extra and len(printed) == len(expect) and row.get("refused", True)
            results.append(row)
            print(json.dumps(row), flush=True)
            shutil.rmtree(work)
    print("ALL OK" if all(r["ok"] for r in results) else "FAILURES")
    (OUT / "results.json").write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main()
