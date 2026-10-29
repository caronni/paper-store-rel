"""Build receiver_arch.py and receiver_arch_os.py (harness only).

receiver_arch.py = bootstrap/r3/receiver.py, every line of it kept, with
three insertions and nothing else:
  1. one paragraph at the end of the module docstring (the archive);
  2. section 10 (the container, the decoder, the unpacker) before main();
  3. the glue in main(), after the line that reports the written payload.
The decoder is dec_strong2.py's region (the measuring builder's winner)
with its head changed (the container carries magic, an 8-byte length and
the CRC-32 in front of the coder's bytes, see section 10) and the NEUTRAL
rewrites below (same computation, fewer compressed bytes); the unpacker is
unp_tarflat.py's ustar subset, trimmed (no type check, one name
expression).  The trims and the short messages are what fits the file in
2 R2 pages (trim_probe.py measured each).
receiver_arch_os.py = receiver_arch.py with `import os` and real
directories (the write line and the docstring sentences change).
Checked here: receiver.py's lines are a subsequence of each file.  The
encoder (arch_pack.py) is derived from the decoder text in
receiver_arch.py itself, so the two cannot drift.
  env/bin/python bootstrap/r3/arch/make_arch.py
"""
import difflib
from pathlib import Path

HERE = Path(__file__).resolve().parent
R3 = HERE.parent

HEAD_OLD = "    n, s = int.from_bytes(z[:4], 'big'), z[4:] + bytes(8)\n"
HEAD_NEW = "    n, s = int.from_bytes(z[4:12], 'big'), z[16:] + bytes(8)\n"

DOC_PARAGRAPH = '''\
The archive (section 10): if a complete volume's payload starts with
b'R3A1', it is an archive container -- the payload.bin is written as
always, then the archive is decoded (a context-mixing decoder, linear in
its length: about 13 minutes for 9.5 MB on the M1 Max, 1.4 GB of memory),
checked by its CRC-32 and unpacked into the current directory: each file
of the tree to ONE flat name, its path with '%' -> '%25' and '/' -> '%2F'
(so `name.replace('%2F', '/').replace('%25', '%')` gives the path back),
and every path is printed.
'''
DOC_PARAGRAPH_OS = DOC_PARAGRAPH.replace(
    "into the current directory: each file\nof the tree to ONE flat name, its path with '%' -> '%25' and '/' -> '%2F'\n"
    "(so `name.replace('%2F', '/').replace('%25', '%')` gives the path back),\n"
    "and every path is printed.\n",
    "into the current directory,\ndirectories made as needed (`import os`, the one import), and every\n"
    "path is printed.\n")

# Rewrites of dec_strong2.py's text that compute the same thing in fewer
# compressed bytes (measured by trim_probe.py; the equivalence is checked by
# re-encoding T1 with the encoder derived from receiver_arch.py's own
# decoder: byte-identical to the builder's dec_strong2 encode).
NEUTRAL = [
    ("    F, Q, q, k = 4294967295, 18446744073709551615, 1460000, 28\n",
     "    F, q, k = 2 ** 32 - 1, 1460000, 28\n    Q = F * F + F + F\n"),
    ("    x1, x2, x, kk, h = 0, 0, 0, 0, 0\n    wh, wp, mp, ml, pl, ls = 0, 0, 0, 0, 8, 8\n",
     "    x1 = x2 = x = kk = h = wh = wp = mp = ml = 0\n    pl = ls = 8\n"),
    ("    for i in range(8, len(b)):\n", "    for i in range(8, n + 8):\n"),
    ("        c, c0, h = b[i - 1], 1, (h << 8 | b[i - 1]) & 0xFFFFFFFFFFFFFF\n",
     "        c, c0 = b[i - 1], 1\n        h = (h << 8 | c) & Q >> 8\n"),
    ("        pl, ls = (ls, i) if c == 10 else (pl, ls)\n", "        if c == 10:\n            pl, ls = ls, i\n"),
    ("                            t = t ^ 16\n                        else:\n"
     "                            if T[t + 1] & 15 > T[t ^ 17] & 15:\n                                t = t ^ 16\n",
     "                            t ^= 16\n                        else:\n"
     "                            if T[t + 1] & 15 > T[t ^ 17] & 15:\n                                t ^= 16\n"),
]

UNZ_DOC = '''\
    """The archive decoder: z = the container, returns the archive (n bytes).

    A bitwise context-mixing model (the cmmix/lpaq family) drives a binary
    arithmetic decoder of 32-bit bounds, so the cost is linear in n.  Per
    bit, ten predictions: order 0 and order 1 (direct tables), orders 2, 3,
    4 and 7, the current word (letters, digits, '_'), the word bigram, and
    the column context (the byte above in the previous line, the column)
    -- hashed into 16-slot nibble buckets of T with a 16-bit check, each
    slot a 12-bit probability and a 4-bit count (adaptation 1/(count+1.2));
    plus a match model (the last occurrence of the order-7 context, mt; the
    bit it predicts, by match length, U/V).  The stretched predictions are
    mixed by three summed weight sets (chosen by match length, by the last
    byte, by a 12-bit hash of order 2), squashed, refined by two APMs (by
    order 1, by a hash of order 3) and averaged 2:3:3.  Tables of 2^k slots
    (k = 28): about 1.4 GB, whatever n.  The encoder is derived from this
    text mechanically (bootstrap/r3/arch/derive.py, arch_pack.py)."""
'''

UNPACK = '''\
def unpack(d):
    """A ustar subset: d = the tar.  Every member is taken as a regular
    file (the container's tars carry nothing else: arch_pack.py checks);
    its path is the prefix field (offset 345), '/', the name field, NULs
    dropped; its size is octal at 124; the data is padded to 512 bytes; the
    archive ends at a block whose name is empty."""
    i = 0
    while d[i]:
        h, i = d[i:i + 512], i + 512
        f = (h[345:500] + b'/' + h[:100]).replace(b'\\0', b'').lstrip(b'/').decode()
        n = int(h[124:135], 8)
        print(f)
        open(f.replace('%', '%25').replace('/', '%2F'), 'wb').write(d[i:i + n])
        i += n + 511 & -512
'''
FLAT_WRITE = "        open(f.replace('%', '%25').replace('/', '%2F'), 'wb').write(d[i:i + n])\n"
OS_WRITE = ("        os.makedirs(os.path.dirname(f) or '.', exist_ok=True)\n"
            "        open(f, 'wb').write(d[i:i + n])\n")

SECTION = '''\
# ======================================================== 10. the archive
# A volume whose payload starts with b'R3A1' carries an archive
# CONTAINER (any other payload is left as payload.bin, nothing more):
#     b'R3A1'   magic, 4 bytes
#     n         the archive's length in bytes, 8 bytes big-endian
#     crc       CRC-32 of the archive (crc32 above, the zlib one), 4 bytes BE
#     z         the coder's bytes (unz)
# The archive is a ustar tar of the tree (files sorted, mtime 0, uid/gid
# 0, no user/group names, regular files only); unpack() writes it.  The
# glue is in main(): it decodes, checks the CRC-32, unpacks.


{decoder}

{unpack}'''

ANCHOR_PRINT = ("                print('volume %d complete: %d bytes, SHA-256 %s, written to %s' % (\n"
                "                    v.number, len(v.payload), sha256(v.payload).hex(), v.written))\n")
GLUE = '''\
                if v.payload[:4] == b'R3A1':     # an archive (section 10): decode, check, unpack
                    print('archive: decoding')
                    d = unz(v.payload)
                    if crc32(d) == int.from_bytes(v.payload[12:16], 'big'):
                        unpack(d)
                    else:
                        print('archive: CRC-32 wrong')
'''
DOC_ANCHOR = "quarters of it the payload scramble (one AES block per cell).\n"


def decoder_region():
    t = (HERE / "dec_strong2.py").read_text()
    r = t.split("# BEGIN DECODER", 1)[1].split("# END DECODER", 1)[0].strip("\n") + "\n"
    assert r.count(HEAD_OLD) == 1 and r.startswith("def unz(z):\n")
    r = r.replace(HEAD_OLD, HEAD_NEW)
    for old, new in NEUTRAL:
        assert r.count(old) == 1, old
        r = r.replace(old, new)
    return r.replace("def unz(z):\n", "def unz(z):\n" + UNZ_DOC, 1)


def build(os_variant):
    src = (R3 / "receiver.py").read_text()
    assert src.count(DOC_ANCHOR) == 1 and src.count(ANCHOR_PRINT) == 1 and src.count("\n\ndef main():") == 1
    unpack = UNPACK.replace(FLAT_WRITE, OS_WRITE) if os_variant else UNPACK
    assert unpack != UNPACK or not os_variant
    out = src.replace(DOC_ANCHOR, DOC_ANCHOR + (DOC_PARAGRAPH_OS if os_variant else DOC_PARAGRAPH))
    if os_variant:
        out = out.replace("one Python file, no imports,", "one Python file, one import (os),", 1)
        out = out.replace('"""\n\n# ====', '"""\nimport os\n\n# ====', 1)
    out = out.replace(ANCHOR_PRINT, ANCHOR_PRINT + GLUE)
    out = out.replace("\n\ndef main():", "\n" + SECTION.format(decoder=decoder_region(), unpack=unpack)
                      + "\n\ndef main():", 1)
    return src, out


def check(src, out, name):
    a, b = src.splitlines(), out.splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    changed = [op for op in ops if op[0] != "insert"]
    added = sum(op[4] - op[3] for op in ops)
    removed = sum(op[2] - op[1] for op in changed)
    compile(out, name, "exec")
    print("%s: %d lines (receiver.py %d), %d inserted / %d replaced lines of receiver.py (%s)" % (
        name, len(b), len(a), added, removed, [(op[0], op[1] + 1) for op in changed]))


def main():
    for os_variant, name in ((False, "receiver_arch.py"), (True, "receiver_arch_os.py")):
        src, out = build(os_variant)
        (HERE / name).write_text(out)
        check(src, out, name)


if __name__ == "__main__":
    main()
