"""check_mirror.py -- the C mirror's ideal bits against stage 1's exact
encoder (cm2_enc.encode_int) on the current reader, stage 1's lowercase primer."""
import common as C
import ev

t = C.typed_of()
p = C.primer()
ib = ev.bits(t, p)
x = C.M.cm2_enc.encode_int(t.encode(), p, ev.ORD)
print('typed bytes', len(t.encode()), 'ideal bits', round(ib, 3), 'exact bits', x.bit_length(),
      'glyphs', -(-x.bit_length() // 5))
assert C.put_back(t) == open(C.READER).read()
print('put_back identity OK')
