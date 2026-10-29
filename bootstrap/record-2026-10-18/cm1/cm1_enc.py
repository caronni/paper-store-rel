"""cm1 encoder: derived mechanically from a decoder file's counted region
(the '# CODER' block is swapped for the encoder's), so encoder and decoder
cannot drift.  Usage: cm1_enc.py [dec.py] IN OUT [PRIMER] [k]"""
import re
import sys
import time

ENC_CODER = """\
while (x1 ^ x2) >> 24 == 0:
    out.append(x2 >> 24)
    x1, x2 = x1 << 8 & F, x2 << 8 & F | 255
xm = x1 + (x2 - x1 >> 12) * p
x1, x2 = (x1, xm) if y else (xm + 1, x2)
"""


def make_encoder(dec_path, k=None):
    text = open(dec_path).read()
    body = text.split("# BEGIN DECODER", 1)[1].split("# END DECODER", 1)[0]
    m = re.search(r"\n( *)# CODER\n.*?\n *# /CODER\n", body, re.S)
    ind = m.group(1)
    enc = "".join(ind + l + "\n" for l in ENC_CODER.splitlines())
    body = body[: m.start()] + "\n" + enc + body[m.end():]
    body, c1 = re.subn(r"def decode\(src, n, primer(.*?)\):",
                       r"def encode(src, n, primer\1):\n    out = bytearray()",
                       body)
    body = body.replace("primer + bytearray(n)", "primer + bytearray(src)")
    body, c2 = re.subn(r"\n    return bytes\(b\[lp:\]\)\n",
                       "\n    return out, x1, x2\n", body)
    assert c1 == 1 and c2 == 1
    ns = {}
    exec(compile(body, dec_path + ":enc", "exec"), ns)
    raw = ns["encode"]

    def encode(data, primer=b""):
        if not data:
            return b""  # n = 0: the decoder reads nothing
        if k is None:
            out, x1, x2 = raw(data, len(data), primer)
        else:
            out, x1, x2 = raw(data, len(data), primer, k)
        # flush: shortest tail t with x1 <= t.00.. <= x2 (decoder pads zeros)
        for nb in range(0, 5):
            sh = 32 - 8 * nb
            v = (x1 + (1 << sh) - 1) >> sh << sh if nb < 4 else x1
            if v <= x2:
                tail = v.to_bytes(4, "big")[:nb]
                break
        assert out[:4] == b"\0\0\0\0"  # the zero-start registers' bytes
        res = bytes(out[4:]) + tail
        # trailing zero bytes are implied by the decoder's zero padding
        nz = 0
        while nz < 4 and res.endswith(b"\0"):
            res = res[:-1]
            nz += 1
        return res
    return encode


if __name__ == "__main__":
    a = sys.argv[1:]
    dec = a.pop(0) if a[0].endswith("_dec.py") else __file__.replace(
        "_enc.py", "_dec.py")
    data = open(a[0], "rb").read()
    pr = open(a[2], "rb").read() if len(a) > 2 and a[2] != "-" else b""
    kb = int(a[3]) if len(a) > 3 else None
    t = time.time()
    c = make_encoder(dec, kb)(data, pr)
    open(a[1], "wb").write(c)
    print(len(data), len(c), round(time.time() - t, 2), file=sys.stderr)
