"""The archive container's encoder side (harness only; the finder never runs it).

  container = b'R3A1' + n (8 bytes BE) + CRC-32 of the tar (4 bytes BE) + z
where z is the coder's output minus its own 4-byte length.  The encoder is
derived (derive.make_encoder) from the decoder text IN receiver_arch.py --
its unz() with the docstring dropped and the container head put back to
derive's mould (n at [0:4], z at [4:]) -- so encoder and the shipped
decoder cannot drift.  The tar is checked to hold regular files only (the
unpacker takes every member as one) with flat names of at most 255 bytes.

  env/bin/python bootstrap/r3/arch/arch_pack.py TREE [--reuse] [--commit COMMIT]
TREE = T1 | T2 | T2R (trees.py's selections, built afresh from `git ls-files`
and checked byte-identical to build/r3/arch/TREE.tar when that exists).
--commit selects from `git ls-tree -r COMMIT` and tars the commit's blobs
(the record's T1 = --commit 2115a595, stage3/e2e_c.py T1_COMMIT); the same
bytes as the worktree route where no selected file differs.
--reuse takes the coder's bytes from build/r3/arch/coded/strong2.TREE.tar.z
(the measuring builder's encode of the same tar) instead of encoding again
(13 minutes for T1); the end-to-end decode checks them either way.
Writes build/r3/arch/e2e_arch/TREE/{TREE.tar, container.bin, container.json}.
"""
import hashlib
import json
import sys
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive  # noqa: E402
import trees  # noqa: E402
import io  # noqa: E402
import tarfile  # noqa: E402

OUT = HERE.parents[1] / "build" / "r3" / "arch"
MAGIC = b"R3A1"


def tree_tar(name, commit=None):
    files = trees.pick(name, trees.tracked(commit))
    tar = trees.make_tar(files, commit)
    old = OUT / (name + ".tar")
    same = old.read_bytes() == tar if old.exists() else None
    return files, tar, same


HEAD_ARCH = "    n, s = int.from_bytes(z[4:12], 'big'), z[16:] + bytes(8)\n"
HEAD_MOULD = "    n, s = int.from_bytes(z[:4], 'big'), z[4:] + bytes(8)\n"


def arch_encoder():
    """derive.make_encoder over receiver_arch.py's own unz()."""
    text = (HERE / "receiver_arch.py").read_text()
    end = "    return bytes(b[8:])\n"
    r = text[text.index("\ndef unz(z):\n") + 1:text.index(end) + len(end)]
    q = r.index('    """')
    r = r[:q] + r[r.index('"""\n', q + 7) + 4:]
    assert r.count(HEAD_ARCH) == 1
    r = r.replace(HEAD_ARCH, HEAD_MOULD)
    path = OUT / "e2e_arch" / "dec_arch_derived.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# BEGIN DECODER\n" + r + "# END DECODER\n")
    return derive.make_encoder(str(path))


def check_tar(tar):
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t.getmembers():
            assert m.isreg(), m.name
            assert len(m.name.replace("%", "%25").replace("/", "%2F").encode()) <= 255, m.name


def coder_bytes(tar, cached=None):
    check_tar(tar)
    if cached is not None:
        z = cached.read_bytes()
    else:
        z = arch_encoder()(tar)
    assert int.from_bytes(z[:4], "big") == len(tar)
    return z[4:]


def container(tar, z):
    return MAGIC + len(tar).to_bytes(8, "big") + zlib.crc32(tar).to_bytes(4, "big") + z


def main():
    name = sys.argv[1]
    reuse = "--reuse" in sys.argv
    commit = sys.argv[sys.argv.index("--commit") + 1] if "--commit" in sys.argv else None
    work = OUT / "e2e_arch" / name
    work.mkdir(parents=True, exist_ok=True)
    files, tar, same = tree_tar(name, commit)
    (work / (name + ".tar")).write_bytes(tar)
    (work / (name + ".files")).write_text("\n".join(files) + "\n")
    t = time.time()
    cached = OUT / "coded" / ("strong2.%s.tar.z" % name)
    z = coder_bytes(tar, cached if reuse else None)
    enc_s = None if reuse else round(time.time() - t, 1)
    c = container(tar, z)
    target = work / "container.bin"
    if not reuse and target.exists():      # a re-encode beside a container already in use
        target = work / "container.encoded.bin"
        print("identical to container.bin:", (work / "container.bin").read_bytes() == c)
    target.write_bytes(c)
    info = {"tree": name, "commit": commit, "files": len(files),
            "content_bytes": sum(len(trees.read(f, commit)) for f in files),
            "tar_bytes": len(tar), "tar_sha256": hashlib.sha256(tar).hexdigest(),
            "tar_identical_to_builders": same, "tar_crc32": "%08x" % zlib.crc32(tar),
            "coder_bytes": len(z), "container_bytes": len(c),
            "container_sha256": hashlib.sha256(c).hexdigest(),
            "coder_source": str(cached.relative_to(trees.ROOT)) if reuse else "encoded now",
            "encode_s": enc_s}
    if not reuse and cached.exists():
        info["identical_to_cached_encode"] = cached.read_bytes()[4:] == z
    (work / target.name.replace(".bin", ".json")).write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
