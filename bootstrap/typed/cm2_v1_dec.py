"""cm2 stage-0 decoder: order-0..12 count-mixing CM + carry-less binary
arithmetic decoder (lpaq style).  Usage: python3 dec.py IN OUT [PRIMER...]
IN = 4-byte big-endian n + coder bytes (harness container; the counted
decode() takes the coder bytes and n separately, per the stage-0 contract).
Masks a fixed-width reimplementer needs: a, b, x are 32-bit (M); counts are
unbounded in principle but stay < 2^32 for any input < 512 MiB; s0+s1 fits
in 64 bits; the context map is EXACT (key = order sentinel + context bytes
+ partial byte), so any collision-free map works -- no hash to specify."""
import sys
# BEGIN DECODER
def decode(s, n, primer):
  ms = [(1 << 8 * o) - 1 for o in (0, 1, 2, 3, 4, 6, 8, 12)]
  m, s, D, t, M = len(primer), s + bytes(4), 12, {}, 0xFFFFFFFF
  buf = bytearray(D) + primer + bytes(n)
  a, b, x, k = 0, M, int.from_bytes(s[:4], 'big'), 4
  for i in range(m + n):
    c0, h = 1, int.from_bytes(buf[i:i + D], 'big')
    for j in range(8):
      cs = [t.setdefault((h & q | q + 1) << 8 | c0, [0, 0]) for q in ms]
      s1 = 1 + sum(c[1] << (c[0] == 0) << w for w, c in enumerate(cs))
      s0 = 1 + sum(c[0] << (c[1] == 0) << w for w, c in enumerate(cs))
      p = s1 * 4094 // (s0 + s1) + 1
      if i < m:
        y = buf[D + i] >> 7 - j & 1
      else:
        xm = a + (b - a >> 12) * p
        y = x <= xm
        a, b = (a, xm) if y else (xm + 1, b)
        while a >> 24 == b >> 24:
          a, b, x, k = a << 8 & M, b << 8 & M | 255, x << 8 & M | s[k], k + 1
      for c in cs:
        c[y], c[1 - y] = c[y] + 1, min(c[1 - y], c[1 - y] // 4 + 2)
      c0 = c0 * 2 + y
    buf[D + i] = c0 & 255
  return bytes(buf[D + m:])
# END DECODER
if __name__ == '__main__':
  z = open(sys.argv[1], 'rb').read()
  pr = b''.join(open(f, 'rb').read() for f in sys.argv[3:])
  open(sys.argv[2], 'wb').write(decode(z[4:], int.from_bytes(z[:4], 'big'), pr))
