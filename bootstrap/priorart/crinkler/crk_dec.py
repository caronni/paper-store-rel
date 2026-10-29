"""crk_dec.py -- Crinkler's 4k and 1k decompressors transliterated to pure
Python (no imports).

ALTERED VERSION.  This is not Crinkler.  It is a Python transliteration,
made 2026-10-20 for the paper-store bootstrap study, of the decompression
model and arithmetic decoder of Crinkler (https://github.com/runestubbe/
Crinkler), Copyright (c) 2005-2026 Aske Simon Christensen and Rune L. H.
Stubbe, distributed under the zlib licence (see the README of this
directory for the licence text).  The originals are x86 assembly
(source/Crinkler/modules/header30.asm for 4k, header22_1k.asm for 1k); this
file reproduces what they compute, not how: no PE header, no imports, no
call transform, and our own container instead of Crinkler's in-header
model tables.  Two extensions that Crinkler does not have are marked
EXTENSION: an optional primer (bytes that only train the model) and the
container.

4k model (header30.asm:199-305, CompressionStream.cpp:95-167):
  for every bit, every model m of the current part hashes
    h = crc32c(hashinit_m, u), then crc32c(h, byte k back) for every set bit
    of the model's mask byte (bit 7 = 1 byte back ... bit 0 = 8 bytes back),
  where u = the bits of the current byte so far behind a leading 1 (u = 0 for
  the start bit) and hashinit_m = mask_m | (the weight mask left-shifted past
  model m's weight bits) & 0xFFFFFF00; crc32c = the SSE4.2 crc32 instruction
  (Castagnoli, reflected, no inversion).  Slot = h % HN in a table of HN
  pairs of 8-bit counters (HN prime, no check bits: collisions are shared).
  p_b = 10 + sum over models of c_b << (w_m + 2 if c_0 == 0 or c_1 == 0);
  after the bit: c_bit += 1 (wraps at 256, or stays at 255 with saturate),
  c_other >>= 1 if c_other > 1.
1k model (header22_1k.asm, Compressor.cpp:487-649): exact contexts (the asm
  scans every earlier position; a dict gives the same counts), masks = the
  set bits of the model mask (model k = byte mask k, bit i = byte i+1 back),
  counters unbounded, c_bit += 1, c_other = (c_other + 1) >> 1,
  n_b = sum of c_b * (boost if c_0 == 0 or c_1 == 0 else 1),
  P(1) : P(0) = n_1 + b0 : n_0 + b1.
Coder (AritCode.cpp, header30.asm:69-180): 32-bit interval, bit 1 owns the
  low part threshold = size * P1 // (P0 + P1), renormalise while size < 2^31,
  the packed bits read LSB-first within each byte (x86 bt).
"""
# BEGIN DECODER

CRC = []
for _i in range(256):
    _c = _i
    for _k in range(8):
        _c = _c >> 1 ^ (0x82F63B78 if _c & 1 else 0)
    CRC.append(_c)


def weights_of(wm):
    """ModelList4k::SetFromModelsAndMask / CompressionStream.cpp:51-60: the
    32-bit weight mask read from the top: 1 = weight += 1, 0 = one model at
    the current weight.  Returns [(weight, hash high bits)] and the
    terminate flag (parity)."""
    out, w, v = [], wm & 0xFFFFFFFF, 0
    par = bin(w & 255).count('1') & 1          # x86 parity flag of the low byte
    while True:
        while w & 0x80000000:
            v += 1
            w = w << 1 & 0xFFFFFFFF
        w = w << 1 & 0xFFFFFFFF
        if not w:
            break
        out.append((v, w & 0xFFFFFF00))
    return out, par


class Bits:
    """The arithmetic decoder of header30.asm (AritDecode*): ecx = code,
    eax = interval size, ebp = bit position into the packed data."""

    def __init__(self, z):
        self.z, self.pos, self.code, self.size = z, 0, 0, 1

    def bit(self, p1, p0):
        z, code, size, pos = self.z, self.code, self.size, self.pos
        while size < 0x80000000:
            b = z[pos >> 3] >> (pos & 7) & 1 if pos >> 3 < len(z) else 0
            code = code << 1 | b
            size <<= 1
            pos += 1
        t = size * p1 // (p0 + p1)
        if code < t:
            y, size = 1, t
        else:
            y, code, size = 0, code - t, size - t
        self.code, self.size, self.pos = code, size, pos
        return y


def unpack4k(z, parts, hn, saturate=False, primer=b'', baseprob=10):
    """parts = [(n_bytes, weight mask, mask bytes)], hn = hash table entries
    (Crinkler's _HashTableSize = hashsize / 2).  primer: EXTENSION."""
    ar = Bits(z)
    tab = bytearray(2 * hn)
    hist = bytearray(8)                         # the zeros before _UnpackedData
    out = bytearray()
    lim = 255 if saturate else 256
    first = True
    for n, wm, masks in parts:
        tab[:] = bytes(2 * hn)                  # _ClearHash: rep stosw
        ws, _ = weights_of(wm)
        models = [(w, hi | masks[i], masks[i]) for i, (w, hi) in enumerate(ws)]
        todo = []
        if first:
            todo.append((None, 1))              # the start bit, u = 0
            todo += [(b, 0) for b in primer]    # EXTENSION: train only
        first = False
        todo += [(None, 2)] * n
        for byte, kind in todo:
            u = 0 if kind == 1 else 1
            for j in range(1 if kind == 1 else 8):
                p0 = p1 = baseprob
                slots = []
                for w, h0, mk in models:
                    h = CRC[(h0 ^ u) & 255] ^ h0 >> 8
                    k = len(hist)
                    while mk:
                        k -= 1
                        if mk & 128:
                            h = CRC[(h ^ hist[k]) & 255] ^ h >> 8
                        mk = mk << 1 & 255
                    s = h % hn * 2
                    slots.append(s)
                    c0, c1 = tab[s], tab[s + 1]
                    sh = w + 2 if not c0 or not c1 else w
                    p0 += c0 << sh
                    p1 += c1 << sh
                if kind == 0:
                    y = byte >> 7 - j & 1
                elif kind == 1:
                    y = ar.bit(p1, p0)          # always 1 for a valid stream
                else:
                    y = ar.bit(p1, p0)
                for s in slots:                 # sequential, like the asm
                    o = s + 1 - y
                    if tab[o] > 1:
                        tab[o] >>= 1
                    v = tab[s + y] + 1
                    tab[s + y] = v if v < lim else (v & 255 if lim == 256 else 255)
                u = u << 1 | y
            if kind != 1:
                hist.append(u & 255)
                if kind == 2:
                    out.append(u & 255)
                if len(hist) > 64:
                    del hist[:-8]
    return bytes(out)


def unpack1k(z, n, modelmask, boost, b0, b1, primer=b''):
    """The 1k (TINYHEADER) model.  Model index k (0..32) is the byte mask
    (k - 1) & 255 over the 8 previous bytes (bit i = i + 1 bytes back);
    index 32 (mask 31) is always on.  The asm (and the compressor) start at
    byte position -1, a zero byte that only trains.  primer: EXTENSION."""
    ar = Bits(z)
    ms = [(k - 1) & 255 for k in range(33) if k == 32 or modelmask >> k & 1]
    tabs = [{} for _ in ms]
    buf = bytearray(33)                         # zeros; buf[-1] is position -1
    out = bytearray()
    seq = [(0, 0)] + [(b, 0) for b in primer] + [(None, 1)] * n
    for idx, (byte, coded) in enumerate(seq):
        back = 2 if idx == 0 else 1             # position -1 is already in buf
        ctxs = [bytes(buf[-back - i] if mk >> i & 1 else 0 for i in range(8)) for mk in ms]
        cur = 0
        for j in range(8):
            n0 = n1 = 0
            ents = []
            for c, t in zip(ctxs, tabs):
                key = (j, cur, c)
                e = t.get(key)
                if e is None:
                    e = t[key] = [0, 0]
                    ents.append((e, True))
                else:
                    f = boost if not e[0] or not e[1] else 1
                    n0 += e[0] * f
                    n1 += e[1] * f
                    ents.append((e, False))
            y = ar.bit(n1 + b0, n0 + b1) if coded else byte >> 7 - j & 1
            for e, new in ents:
                if new:
                    e[y], e[1 - y] = 1, 0
                else:
                    e[y], e[1 - y] = e[y] + 1, e[1 - y] + 1 >> 1
            cur = cur << 1 | y
        if idx:
            buf.append(cur)
            if coded:
                out.append(cur)
            if len(buf) > 4096:
                del buf[:-64]
    return bytes(out)

# END DECODER


def parse(c):
    """EXTENSION, our container: 'C4' | HN (4) | saturate (1) | nparts (1) |
    per part: n (4), weight mask (4), mask bytes (one per model) | packed;
    or 'C1' | n (4) | modelmask (4) | boost | b0 | b1 | packed."""
    if c[:2] == b'C1':
        n, mm = int.from_bytes(c[2:6], 'big'), int.from_bytes(c[6:10], 'big')
        return ('1k', n, mm, c[10], c[11], c[12], c[13:])
    hn, sat, np_ = int.from_bytes(c[2:6], 'big'), c[6], c[7]
    k, parts = 8, []
    for _ in range(np_):
        n, wm = int.from_bytes(c[k:k + 4], 'big'), int.from_bytes(c[k + 4:k + 8], 'big')
        nm = len(weights_of(wm)[0])
        parts.append((n, wm, c[k + 8:k + 8 + nm]))
        k += 8 + nm
    return ('4k', hn, bool(sat), parts, c[k:])


def unz(c, primer=b''):
    p = parse(c)
    if p[0] == '1k':
        _, n, mm, bo, b0, b1, z = p
        return unpack1k(z, n, mm, bo, b0, b1, primer)
    _, hn, sat, parts, z = p
    return unpack4k(z, parts, hn, sat, primer)

