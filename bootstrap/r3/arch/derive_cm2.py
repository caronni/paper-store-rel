"""Derive the encoder of a cm2-family decoder (gen_cm2fam.py) from its text:
the model lines are run as they stand; the '# CODER' block is swapped for one
that records what the coder needs; the coder then runs here (range coder:
inline; rANS: in reverse after the forward pass)."""
import re

ENC = {
    "rc": "xm = a + (b - a >> 12) * (s1 * 4094 // (s0 + s1) + 1)\n"
          "y = buf[D + i] >> 7 - j & 1\n"
          "a, b = (a, xm) if y else (xm + 1, b)\n"
          "while a >> 24 == b >> 24:\n"
          "  out.append(b >> 24)\n"
          "  a, b = a << 8 & M, b << 8 & M | 255\n",
    "rans": "y = buf[D + i] >> 7 - j & 1\n"
            "out.append(y << 12 | s1 * 4094 // (s0 + s1) + 1)\n",
    "blk": "y = buf[D + i] >> 7 - j & 1\n"
           "out += (y, s0, s1)\n",
}
L_RANS = 1 << 23
BLOCK = 65536


def _sub(body, old, new):
    assert body.count(old) == 1, old
    return body.replace(old, new)


def make_encoder(dec_path, coder):
    text = open(dec_path).read()
    body = text.split("# BEGIN DECODER", 1)[1].split("# END DECODER", 1)[0]
    m = re.search(r"\n( *)# CODER\n.*?\n *# /CODER\n", body, re.S)
    ind = m.group(1)
    body = body[:m.start()] + "\n" + "".join(ind + l + "\n" for l in ENC[coder].splitlines()) + body[m.end():]
    body = _sub(body, "def unz(s):\n  n, s, D = int.from_bytes(s[:4], 'big'), s[4:] + bytes(4),",
                "def unz(data):\n  out = []\n  n, s, D = len(data), bytes(8),")
    body = _sub(body, "buf = bytearray(D + n)", "buf = bytearray(D) + bytearray(data)")
    body = _sub(body, "return bytes(buf[D:])", "return out, a" if coder == "rc" else "return out, 0")
    ns = {}
    exec(compile(body, dec_path + ":enc", "exec"), ns)
    raw = ns["unz"]

    def enc(data):
        out, a = raw(data)
        head = len(data).to_bytes(4, "big")
        if coder == "rc":
            return head + bytes(out) + bytes([(a >> 24) + 1])
        if coder == "rans":
            x, z = L_RANS, bytearray()
            for v in reversed(out):
                y, p = v >> 12, v & 4095
                f = p if y else 4096 - p
                while x >= (L_RANS >> 12 << 8) * f:
                    z.append(x & 255)
                    x >>= 8
                x = (x // f << 12) + x % f + (0 if y else p)
            z.reverse()
            return head + x.to_bytes(4, "big") + bytes(z)
        res = bytearray(head)
        per = 3 * 8 * BLOCK
        for st in range(0, len(out), per):
            x = 0
            blk = out[st:st + per]
            for e in range(len(blk) - 3, -1, -3):
                y, s0, s1 = blk[e], blk[e + 1], blk[e + 2]
                py = s1 if y else s0
                x = x // py * (s0 + s1) + (s0 if y else 0) + x % py
            xb = x.to_bytes((x.bit_length() + 7) // 8, "big")
            res += len(xb).to_bytes(3, "big") + xb
        return bytes(res)
    return enc
