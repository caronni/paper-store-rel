"""Deterministic paper trees for the archival layer (harness only).

T1  src/holo/**/*.py + docs/**/*.md (not docs/archive/) + CLAUDE.md
T2  src/holo/{format,core,gen}/**/*.py + src/holo/*.py (the task's literal T2, 0.41 MB)
T2R src/holo/**/*.py without receiver/ (the 0.95 MB row of RECORD-2026-10-20 ruling 25)
ALL every tracked text file (no NUL byte, valid UTF-8) -- for the xz anchor of
    the extrapolation only.
Files come from `git ls-files` of the worktree, sorted (byte order of the
path); with a commit (tracked(commit), make_tar(files, commit)) from
`git ls-tree -r COMMIT` and the bytes from the commit's blobs, the same
construction (arch_pack.py --commit; tracked() and make_tar() only --
pick('ALL') and make_shar() read the worktree).  Two containers per tree:
  .tar   ustar (POSIX 1988), regular files only (no directory members: the
         unpacker makes parents), mode 0644, mtime 0, uid/gid 0, empty
         user/group names, end = two zero blocks, padded to 10240 (tarfile's
         record) -- the same as `tar --format=ustar` with those options
  .shar  per file: path '\n' decimal size '\n' the bytes; nothing at the end
Writes bootstrap/build/r3/arch/{T1,T2,ALL}.{tar,shar} and trees.json.
  env/bin/python bootstrap/r3/arch/trees.py
"""
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "bootstrap" / "build" / "r3" / "arch"


def tracked(commit=None):
    cmd = ["ls-files", "-z"] if commit is None else ["ls-tree", "-r", "--name-only", "-z", commit]
    r = subprocess.run(["git", "-C", str(ROOT)] + cmd, capture_output=True, check=True)
    return sorted(p for p in r.stdout.decode().split("\0") if p)


def read(f, commit=None):
    if commit is None:
        return (ROOT / f).read_bytes()
    return subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", "%s:%s" % (commit, f)],
                          capture_output=True, check=True).stdout


def pick(name, files):
    if name == "T1":
        return [f for f in files if (f.startswith("src/holo/") and f.endswith(".py"))
                or (f.startswith("docs/") and not f.startswith("docs/archive/") and f.endswith(".md"))
                or f == "CLAUDE.md"]
    if name == "T2":
        return [f for f in files if f.endswith(".py") and (
            f.count("/") == 2 and f.startswith("src/holo/")
            or any(f.startswith("src/holo/%s/" % d) for d in ("format", "core", "gen")))]
    if name == "T2R":
        return [f for f in files if f.startswith("src/holo/") and f.endswith(".py")
                and not f.startswith("src/holo/receiver/")]
    out = []
    for f in files:
        p = ROOT / f
        if not p.is_file() or p.is_symlink():
            continue
        b = p.read_bytes()
        if b"\0" in b:
            continue
        try:
            b.decode("utf-8")
        except UnicodeDecodeError:
            continue
        out.append(f)
    return out


def make_tar(files, commit=None):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for f in files:
            data = read(f, commit)
            ti = tarfile.TarInfo(f)
            ti.size, ti.mtime, ti.mode = len(data), 0, 0o644
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def make_shar(files):
    out = bytearray()
    for f in files:
        data = (ROOT / f).read_bytes()
        out += f.encode() + b"\n" + str(len(data)).encode() + b"\n" + data
    return bytes(out)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = tracked()
    info = {}
    for name in ("T1", "T2", "T2R", "ALL"):
        sel = pick(name, files)
        tar, shar = make_tar(sel), make_shar(sel)
        (OUT / (name + ".tar")).write_bytes(tar)
        (OUT / (name + ".shar")).write_bytes(shar)
        (OUT / (name + ".files")).write_text("\n".join(sel) + "\n")
        info[name] = {"files": len(sel), "content_bytes": sum((ROOT / f).stat().st_size for f in sel),
                      "tar_bytes": len(tar), "shar_bytes": len(shar),
                      "longest_path": max(len(f) for f in sel)}
        print(name, info[name], flush=True)
    (OUT / "trees.json").write_text(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
