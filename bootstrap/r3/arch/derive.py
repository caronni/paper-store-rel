"""Derive the encoder of an arch-mould decoder mechanically from its text, so
encoder and decoder cannot drift (the 10-18 cmmix_ref_enc idea).

The mould (dec_cmmix.py, dec_strong.py, ...):
  def unz(z):
      n, s = int.from_bytes(z[:4], 'big'), z[4:] + bytes(8)     # HEAD
      ... b = bytearray(8 + n) ...                                # BUF
            # CODER ... # /CODER   (the decoder's coder; it defines y)
      return bytes(b[8:])                                         # RET
The encoder replaces HEAD, BUF and RET, swaps the CODER block for the
encoder's (y read from the data, bytes appended to out) and flushes the
shortest tail that lands inside [x1, x2] (the decoder pads zeros)."""
import re

ENC_CODER = """\
y = b[i] >> 7 - j & 1
while (x1 ^ x2) >> 24 == 0:
    out.append(x2 >> 24)
    x1, x2 = x1 << 8 & F, x2 << 8 & F | 255
xm = x1 + (x2 - x1 >> 12) * p
x1, x2 = (x1, xm) if y else (xm + 1, x2)
"""


def _sub(body, old, new):
    assert body.count(old) == 1, old
    return body.replace(old, new)


def make_encoder(dec_path, coder=ENC_CODER):
    text = open(dec_path).read()
    body = text.split("# BEGIN DECODER", 1)[1].split("# END DECODER", 1)[0]
    m = re.search(r"\n( *)# CODER\n.*?\n *# /CODER\n", body, re.S)
    ind = m.group(1)
    body = body[:m.start()] + "\n" + "".join(ind + l + "\n" for l in coder.splitlines()) + body[m.end():]
    body = _sub(body, "def unz(z):\n    n, s = int.from_bytes(z[:4], 'big'), z[4:] + bytes(8)",
                "def unz(data):\n    out, n, s = bytearray(), len(data), b''")
    body = _sub(body, "b = bytearray(8 + n)", "b = bytearray(8) + bytearray(data)")
    body = _sub(body, "return bytes(b[8:])", "return out, x1, x2")
    ns = {}
    exec(compile(body, dec_path + ":enc", "exec"), ns)
    raw = ns["unz"]

    def enc(data):
        out, x1, x2 = raw(data)
        for nb in range(0, 5):
            sh = 32 - 8 * nb
            v = (x1 + (1 << sh) - 1) >> sh << sh if nb < 4 else x1
            if v <= x2:
                tail = v.to_bytes(4, "big")[:nb]
                break
        assert out[:4] == b"\0\0\0\0"
        res = bytes(out[4:]) + tail
        for _ in range(4):
            if not res.endswith(b"\0"):
                break
            res = res[:-1]
        return len(data).to_bytes(4, "big") + res
    return enc
