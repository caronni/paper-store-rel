"""dec_crkpy.py -- Crinkler's 4k model, optimised for Python, as an archival
decoder (the r3/arch harness's shape: unz(z) -> bytes, pure Python, no
imports, linear in n, fixed memory).

ALTERED VERSION of Crinkler's decompressor (Crinkler (c) 2005-2026 Aske
Simon Christensen and Rune L. H. Stubbe, zlib licence; see README): the
model is Crinkler's -- per model a context mask over the preceding bytes
(here up to 24 bytes, Crinkler 8), a weight, a pair of 8-bit counters per
context (saturating: Crinkler's /SATURATE), p_b = 10 + sum c_b << (w + 2 if
a counter is 0), c_bit += 1, c_other >>= 1 if > 1 -- and the coder is
Crinkler's 32-bit arithmetic coder (AritCode.cpp / header30.asm, bits LSB
first).  What changed for Python: the CRC32C hash becomes one integer
multiply-and-modulo of the masked history (deterministic integer
arithmetic, no table, no dependence on Python's hash()), the table has
P = 262,143,977 slots (prime: Crinkler's default table, HASHSIZE 500 MB; 67,108,859 measured 0.3147 on 1 MB of T1, collisions), and the model list is in the container.

Container: n (4, big-endian) | k (1) | k x (subset bitmap over the last 24
bytes, 3 bytes; weight, 1 byte) | packed bits."""
# BEGIN DECODER
def unz(s):
  n, k = int.from_bytes(s[:4], 'big'), s[4]
  ms, ws = [], []
  for i in range(k):
    b = int.from_bytes(s[5 + 4 * i:8 + 4 * i], 'big')
    ms.append(sum(255 << 8 * j for j in range(24) if b >> j & 1))
    ws.append(s[8 + 4 * i])
  z, P = s[5 + 4 * k:], 262143977
  L = len(z) * 8
  t = bytearray(2 * P)
  out = bytearray(n)
  h, top = 0, (1 << 192) - 1
  pos, code, size = 0, 0, 1
  mw = list(zip(range(k), ms, ws))
  for i in range(n):
    u = 1
    for j in range(8):
      p0 = p1 = 10
      sl = []
      for m, M, w in mw:
        q = (((h & M) << 8 | u) * 2654435761 + m) % P * 2
        sl.append(q)
        c0, c1 = t[q], t[q + 1]
        if c0 and c1:
          p0 += c0 << w
          p1 += c1 << w
        else:
          p0 += c0 << w + 2
          p1 += c1 << w + 2
      while size < 2147483648:
        code = code << 1 | (z[pos >> 3] >> (pos & 7) & 1 if pos < L else 0)
        size <<= 1
        pos += 1
      x = size * p1 // (p0 + p1)
      if code < x:
        y, size = 1, x
        for q in sl:
          if t[q] > 1:
            t[q] >>= 1
          if t[q + 1] < 255:
            t[q + 1] += 1
      else:
        y, code, size = 0, code - x, size - x
        for q in sl:
          if t[q + 1] > 1:
            t[q + 1] >>= 1
          if t[q] < 255:
            t[q] += 1
      u = u << 1 | y
    out[i] = u & 255
    h = (h << 8 | u & 255) & top
  return bytes(out)
# END DECODER
