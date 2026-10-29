"""cm2 v2 stage-0 decoder (2026-10-20): the cm2 count-mixing model with a
big-integer rANS decoder.  Usage: python3 cm2_dec.py IN OUT N [PRIMER...]
(IN = x as big-endian bytes, N = the output length, OUT = the n decoded
bytes; the 10-18 range coder is kept as cm2_v1_dec.py).
The whole coded message is ONE integer x.  For every bit the model gives two
weights p0, p1 (s = p0 + p1); bit 0 owns the slots [0, p0) of x % s, bit 1
the slots [p0, s).  Decoding a bit: slot = x % s, y = slot >= p0, then
x = x // s * p_y + slot - (p0 if y else 0).  x only shrinks, and it reaches 0
exactly when the message ends.  Nothing is clamped or windowed: the weights
are used as they are, and x has as many digits as the message needs.
The model: before the output come the primer's bytes (decoded from the
primer itself, they only train the model).  For every bit, one counter pair
per order k: the key is (the last k bytes as one integer, the bits of the
current byte so far with a leading 1); p_y = 1 + sum over the orders (index
w) of count_y << (w + [count_other == 0]); after the bit, count_y += 1 and
count_other = min(count_other, count_other // 4 + 2).  Two orders whose keys
coincide (the last bytes are 0, as at the start) share one counter pair, and
it is updated once for each.  Everything is exact integer arithmetic."""
import sys
# BEGIN DECODER
def decode(x, n, primer):
  ms = [256 ** o - 1 for o in (0, 1, 2, 3, 4, 6, 8, 12, 16)]
  m, t, h = len(primer), {}, 0
  for i in range(m + n):
    c0 = 1
    for j in range(8):
      cs = [t.setdefault((h & q, c0), [0, 0]) for q in ms]
      p = [1 + sum(c[y] << w + (c[1 - y] == 0) for w, c in enumerate(cs)) for y in (0, 1)]
      if i < m:
        y = primer[i] >> 7 - j & 1
      else:
        f, slot = divmod(x, p[0] + p[1])
        y = slot >= p[0]
        x = f * p[y] + slot - p[0] * y
      for c in cs:
        c[y], c[1 - y] = c[y] + 1, min(c[1 - y], c[1 - y] // 4 + 2)
      c0 = c0 * 2 + y
    h = h << 8 | c0 & 255
  return h.to_bytes(m + n, 'big')[m:]
# END DECODER
_decode = decode


def decode(x, n, primer):
  """The harness's door: x may come as big-endian bytes (the page's container)."""
  if isinstance(x, (bytes, bytearray)):
    x = int.from_bytes(x, 'big')
  return _decode(x, n, primer)


if __name__ == '__main__':
  z = open(sys.argv[1], 'rb').read()
  pr = b''.join(open(f, 'rb').read() for f in sys.argv[4:])
  open(sys.argv[2], 'wb').write(decode(z, int(sys.argv[3]), pr))
