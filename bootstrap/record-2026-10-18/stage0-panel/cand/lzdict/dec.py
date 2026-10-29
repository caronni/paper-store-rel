# lzdict stage-0 decoder: LZ77 over a primed window, adaptive binary range
# coder (LZMA-style, 12-bit probabilities), integers as Elias-gamma trees.
# Fixed width: r, x, t < 2**32; P[c] in [16, 4081]; keys c < 2**22.
# Usage (harness, not typed): python3 dec.py SRC N OUT [PRIMER ...]
import sys
# BEGIN DECODER
def decode(src, n, primer):
    o, P, s, src, l = bytearray(primer), {}, [1, 0, 0], src + bytes(8), 0
    def bit(c):
        while s[0] < 1 << 24:
            s[0:3] = s[0] << 8, s[1] << 8 | src[s[2]], s[2] + 1
        t = (s[0] >> 12) * P.setdefault(c, 2048)
        y = int(s[1] >= t)
        s[0:2] = [t, s[0] - t][y], s[1] - t * y
        P[c] += ((1 - y << 12) - P[c] >> 4 + (c > 4095)) + y
        return y
    def num(b):
        v = k = 1
        while bit(b + k):
            v, k = v * 2 + bit(b + 64 + v), k + 1
        return v
    while len(o) < len(primer) + n:
        l = num(min(l, 2) << 9)
        x = len(o) - (l > 1 and num(4096))
        o += (o[x:x + l] * l)[:l] if l > 1 else bytes([num(1536) - 256])
    return bytes(o[len(primer):])
# END DECODER
if __name__ == '__main__':
    pr = b''.join(open(f, 'rb').read() for f in sys.argv[4:])
    out = decode(open(sys.argv[1], 'rb').read(), int(sys.argv[2]), pr)
    open(sys.argv[3], 'wb').write(out)
