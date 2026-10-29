"""cmmix encoder: derived mechanically from a decoder file's counted region, so
encoder and decoder can never drift. Usage: enc.py [dec.py] in out [primer]"""
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


def make_encoder(dec_path):
    text = open(dec_path).read()
    body = text.split("# BEGIN DECODER", 1)[1].split("# END DECODER", 1)[0]
    m = re.search(r"\n( *)# CODER\n.*?\n *# /CODER\n", body, re.S)
    ind = m.group(1)
    enc = "".join(ind + l + "\n" for l in ENC_CODER.splitlines())
    body = body[: m.start()] + "\n" + enc + body[m.end():]
    body = body.replace("def decode(src, n, primer):",
                        "def encode(src, n, primer):\n    out = bytearray()")
    body = body.replace("primer + bytearray(n)",
                        "primer + bytearray(src)")
    body = re.sub(r"\n    return bytes\(b\[lp:\]\)\n",
                  "\n    return out, x1, x2\n", body)
    ns = {}
    exec(compile(body, dec_path + ":enc", "exec"), ns)
    raw = ns["encode"]

    def encode(data, primer=b""):
        out, x1, x2 = raw(data, len(data), primer)
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
        k = 0
        while k < 4 and res.endswith(b"\0"):
            res = res[:-1]
            k += 1
        return res
    return encode


if __name__ == "__main__":
    a = sys.argv[1:]
    dec = a.pop(0) if a[0].endswith(".py") and len(a) > 2 and a[1] != "" else "dec.py"
    data = open(a[0], "rb").read()
    pr = open(a[2], "rb").read() if len(a) > 2 else b""
    t = time.time()
    c = make_encoder(dec)(data, pr)
    open(a[1], "wb").write(c)
    print(len(data), len(c), round(time.time() - t, 2), file=sys.stderr)
