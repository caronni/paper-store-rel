"""R3 receiver: the archive's black-only pages, read from flatbed scans.

This is c.py, stage 3 of the bootstrap (b.py, the stage-2 reader, writes
it from the R2 pages): one Python file, no imports, run with
`python3 c.py` on a bare interpreter.  It reads printed pages of the holo
archive format (src/holo; docs/HOLO-DESIGN.md, docs/PRINTED-FORMAT.md) for
ONE row only, the most robust black-only row:

    K family (black toner only), cells of CELL_DOTS x CELL_DOTS printer dots
    at 600 dpi (c3; c4 = set CELL_DOTS = 4), LDPC rung r0547, 100 address
    sites per tile (p100), A4 paper with 6 mm margins.  The fountain's
    source fraction (0.5 for the "resilient" profile) is not printed and
    not needed: the volume says its own size on every tile.

Use: it asks for scans, one per line, as `FILE [DPI]`: FILE a greyscale
PGM (P5, 8 or 16 bit) of ONE whole page laid on a flatbed, any quarter
turn, tilted by up to about 10 degrees; DPI the scan resolution (default
1200; read from paper at 600 and 1200 and in simulation at 1200, 2400
untested since the lattice search of 2026-10-23; a print scaled by a few
percent, to fit the paper, is read too; a scan that places no tile at its
DPI is searched again at 600, 1200 and 2400, nearest first, so a DPI given
wrong costs time, not the page).  An empty line ends.  Pages may
come in any order, any number of them, the same page twice is harmless.
While a scan is read, one line says when a cell lattice has placed its
tiles, and one more names each further dpi tried when none placed.
After each scan it prints one line: the page it found, tiles placed, tiles
certified, its volume's symbols held / needed, and `done` or `more`.  When
a volume is complete and its SHA-256 checks, its payload is written to
`payload.bin` (a second volume in the same session to `payload-2.bin`, and
so on) and the program says so; it reads on until the empty line.
Volumes of this row share the seed and all count their tiles from 0, so a
page's metadata bits name its volume: a page of another volume opens a
volume of its own, and a page whose tiles contradict the volume it agrees
with (another volume of the SAME size) is refused whole and named.

The stages, in the order a scan meets them:
  1. the row's constants and the codes' derived tables (sections 1-6);
  2. the scan: the cell lattice (its pitch declared by the dpi and measured,
     with its angle, phase and the scanner's scale), the first tile found by
     its address word, every other tile predicted from its neighbours and
     checked against the address word it must carry (section 7);
  3. per tile: cell brightness -> soft bits calibrated on the tile's own
     address sites, descrambled, put in code order, LDPC-decoded and
     certified by CRC-32 (sections 7 and 9);
  4. the volume: K from the metadata bit every tile carries, the fountain's
     equations reduced over GF(2) as each tile arrives, solved the moment
     their rank reaches K, the envelope checked by SHA-256 (section 8);
  the reader (section 9) drives them scan by scan.
It runs a c3 page in about 40 s on an Apple M1 Max (CPython 3.14), three
quarters of it the payload scramble (one AES block per cell).
The archive (section 10): if a complete volume's payload starts with
b'R3A1', it is an archive container -- the payload.bin is written as
always, then the archive is decoded (a context-mixing decoder, linear in
its length: about 13 minutes for 9.5 MB on the M1 Max, 1.4 GB of memory;
it prints a line at every 5 % of the archive's bytes decoded),
checked by its CRC-32 and unpacked into the current directory: each file
of the tree to ONE flat name, its path with '%' -> '%25' and '/' -> '%2F'
(so `name.replace('%2F', '/').replace('%25', '%')` gives the path back),
and every path is printed.
"""

# ============================================================== 1. the row
CELL_DOTS = 3                 # 3 = c3 (the archive row), 4 = c4
ENGINE_DPI = 600              # every printer in the record is 600 dpi
A4_DOTS = (7016, 4960)        # A4 at 600 dpi, (height, width)
MARGIN_DOTS = 6 * 600 / 25.4  # the A4-6mm paper bundle
TILE = 64                     # a tile is 64 x 64 cells
TILES_Y = int((A4_DOTS[0] - 2 * MARGIN_DOTS) // (TILE * CELL_DOTS))  # 35
TILES_X = int((A4_DOTS[1] - 2 * MARGIN_DOTS) // (TILE * CELL_DOTS))  # 24
# The format id IS the keystream seed; a wrong id reads every page as noise.
# For the archive it is set at print time (like the R2 constants); this one
# is the public test row c3-k-r0547@35x24 (c4: 1i150 ... @26x18).
FORMAT_ID = 'holo/v2/1i%d-k-r0547-p100-v1@%dx%d' % (
    ENGINE_DPI // CELL_DOTS, TILES_Y, TILES_X)
SITES_ID = 'holo/v1/sites/p100'       # the site pattern's own seed
TILES_PER_PAGE = TILES_Y * TILES_X
MAX_PAGES = (1 << 18) // TILES_PER_PAGE   # the tile counter has 18 bits
N_SITES = 100                 # address-word cells per tile
N_CODE, K_INFO = 4096, 2240   # LDPC r0547: n, k (Z = 64)
N_CHECKS = N_CODE - K_INFO    # 1856 parity checks
USER_BITS = K_INFO - 32 - N_SITES  # 2108 = metadata bit + symbol
SYMBOL_BITS = USER_BITS - 1        # 2107 fountain symbol bits per tile
SHORT = (USER_BITS + 32, K_INFO)   # info bits 2140..2239: shortened, zero
SLOTS = N_CODE - N_SITES           # 3996 printed code bits per tile
LDPC_ITERS, LDPC_ALPHA = 50, 0.8   # layered normalised min-sum
WORD_T = 13                   # BCH(100,23) corrects 13 errors
GATE_MISMATCH = 20            # a placed tile shows its word with <= 20 of 100 wrong
OUT_NAME = 'payload.bin'


# ============================================================ 2. SHA-256
def _root_bits(p, k):
    """The first 32 bits of the fraction of p**(1/k) (FIPS 180-4 4.2.2)."""
    n = p << 32 * k
    x = int(n ** (1 / k))
    while x ** k > n:
        x -= 1
    while (x + 1) ** k <= n:
        x += 1
    return x & 0xFFFFFFFF


PRIMES = [n for n in range(2, 312) if all(n % d for d in range(2, n))]
SHA_H0 = [_root_bits(p, 2) for p in PRIMES[:8]]
SHA_K = [_root_bits(p, 3) for p in PRIMES]


def sha256(data):
    M = 0xFFFFFFFF

    def ror(x, n):
        return (x >> n | x << 32 - n) & M
    h = SHA_H0[:]
    n = len(data)
    data = bytes(data) + b'\x80' + bytes((55 - n) % 64) + (8 * n).to_bytes(8, 'big')
    for at in range(0, len(data), 64):
        w = [int.from_bytes(data[at + 4 * i:at + 4 * i + 4], 'big') for i in range(16)]
        for i in range(16, 64):
            x, y = w[i - 15], w[i - 2]
            w.append((w[i - 16] + w[i - 7] + (ror(x, 7) ^ ror(x, 18) ^ x >> 3)
                      + (ror(y, 17) ^ ror(y, 19) ^ y >> 10)) & M)
        a, b, c, d, e, f, g, hh = h
        for i in range(64):
            t1 = hh + (ror(e, 6) ^ ror(e, 11) ^ ror(e, 25)) + (e & f ^ ~e & g) + SHA_K[i] + w[i]
            t2 = (ror(a, 2) ^ ror(a, 13) ^ ror(a, 22)) + (a & b ^ a & c ^ b & c)
            hh, g, f, e, d, c, b, a = g, f, e, (d + t1) & M, c, b, a, (t1 + t2) & M
        h = [(x + y) & M for x, y in zip(h, (a, b, c, d, e, f, g, hh))]
    return b''.join(x.to_bytes(4, 'big') for x in h)


# ==================================================== 3. AES-128 keystream
# FIPS-197 with 32-bit T-tables; the S-box is derived (inverse in GF(2^8)
# then the affine map), not transcribed.
def _xtime(a):
    return (a << 1 ^ (0x11B if a & 0x80 else 0)) & 0xFF


def _sbox():
    exp, log, x = [0] * 255, [0] * 256, 1
    for i in range(255):
        exp[i], log[x] = x, i
        x ^= _xtime(x)                       # times the generator 3
    box = []
    for a in range(256):
        b = exp[-log[a] % 255] if a else 0   # the inverse
        r = 0x63
        for k in range(5):                   # b ^ rotl(b,1..4) ^ 0x63
            r ^= (b << k | b >> 8 - k) & 0xFF
        box.append(r)
    return box


SBOX = _sbox()
TE0 = [_xtime(s) << 24 | s << 16 | s << 8 | _xtime(s) ^ s for s in SBOX]
TE1 = [(t >> 8 | t << 24) & 0xFFFFFFFF for t in TE0]
TE2 = [(t >> 16 | t << 16) & 0xFFFFFFFF for t in TE0]
TE3 = [(t >> 24 | t << 8) & 0xFFFFFFFF for t in TE0]


def aes_key(key):
    """AES-128 key schedule: 44 big-endian words."""
    w = [int.from_bytes(key[i:i + 4], 'big') for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        t = w[i - 1]
        if i % 4 == 0:
            t = (SBOX[t >> 16 & 255] << 24 | SBOX[t >> 8 & 255] << 16
                 | SBOX[t & 255] << 8 | SBOX[t >> 24]) ^ rcon << 24
            rcon = _xtime(rcon)
        w.append(w[i - 4] ^ t)
    return w


def aes_encrypt(k, s0, s1, s2, s3):
    s0, s1, s2, s3 = s0 ^ k[0], s1 ^ k[1], s2 ^ k[2], s3 ^ k[3]
    for i in range(4, 40, 4):
        s0, s1, s2, s3 = (
            TE0[s0 >> 24] ^ TE1[s1 >> 16 & 255] ^ TE2[s2 >> 8 & 255] ^ TE3[s3 & 255] ^ k[i],
            TE0[s1 >> 24] ^ TE1[s2 >> 16 & 255] ^ TE2[s3 >> 8 & 255] ^ TE3[s0 & 255] ^ k[i + 1],
            TE0[s2 >> 24] ^ TE1[s3 >> 16 & 255] ^ TE2[s0 >> 8 & 255] ^ TE3[s1 & 255] ^ k[i + 2],
            TE0[s3 >> 24] ^ TE1[s0 >> 16 & 255] ^ TE2[s1 >> 8 & 255] ^ TE3[s2 & 255] ^ k[i + 3])
    S = SBOX
    return [(S[a >> 24] << 24 | S[b >> 16 & 255] << 16 | S[c >> 8 & 255] << 8 | S[d & 255]) ^ k[40 + i]
            for i, (a, b, c, d) in enumerate(((s0, s1, s2, s3), (s1, s2, s3, s0),
                                              (s2, s3, s0, s1), (s3, s0, s1, s2)))]


def keystream(k, domain, aux, major, u, v):
    """One keystream block: AES of the counter
    [domain:1][aux:1][major:3][u:4][v:4][0:3] (all big-endian)."""
    w = aes_encrypt(k, domain << 24 | aux << 16 | major >> 8, (major & 255) << 24 | u >> 8,
                    (u & 255) << 24 | v >> 8, (v & 255) << 24)
    return b''.join(x.to_bytes(4, 'big') for x in w)


def kdf(seed):
    return aes_key(sha256(b'holo/v1|' + seed.encode())[:16])


ROW_KEY = kdf(FORMAT_ID)
SITES_KEY = kdf(SITES_ID)


def payload_scramble(page, Y0, X0):
    """The payload scramble of one tile: for each of its 64 x 64 cells
    (page cells Y0.., X0.., row-major) the top bit of AES(domain 1, aux 3,
    major page, u Y, v X).  The receiver's hot loop, one AES block per cell,
    so it is cut to what varies: in the counter only Y and X do, and X only
    reaches round 1 through two bytes, so round 1 is per row except one
    term per column (B), round 2 per row except one lookup per word; rounds
    3-8 in full; round 9 only the word that holds byte 0; round 10 only
    byte 0."""
    k, T0, T1, T2, T3, S = ROW_KEY, TE0, TE1, TE2, TE3, SBOX
    k40 = k[40] >> 24
    s0 = (1 << 24 | 3 << 16 | page >> 8) ^ k[0]
    s3 = k[3]                                 # the counter's word 3 is X's low byte, then 0
    B = [T0[(X & 255) ^ s3 >> 24] ^ T3[(X >> 8) ^ k[2] & 255] for X in range(X0, X0 + TILE)]
    bits = []
    for Y in range(Y0, Y0 + TILE):
        s1 = ((page & 255) << 24 | Y >> 8) ^ k[1]
        s2 = (Y & 255) << 24 ^ k[2]           # word 2 without X >> 8 (its low byte, in B)
        t0 = T0[s0 >> 24] ^ T1[s1 >> 16 & 255] ^ T2[s2 >> 8 & 255] ^ T3[s3 & 255] ^ k[4]
        t1 = T0[s1 >> 24] ^ T1[s2 >> 16 & 255] ^ T2[s3 >> 8 & 255] ^ T3[s0 & 255] ^ k[5]
        t2 = T0[s2 >> 24] ^ T1[s3 >> 16 & 255] ^ T2[s0 >> 8 & 255] ^ T3[s1 & 255] ^ k[6]
        a3 = T1[s0 >> 16 & 255] ^ T2[s1 >> 8 & 255] ^ k[7]
        p0 = T0[t0 >> 24] ^ T1[t1 >> 16 & 255] ^ T2[t2 >> 8 & 255] ^ k[8]
        p1 = T0[t1 >> 24] ^ T1[t2 >> 16 & 255] ^ T3[t0 & 255] ^ k[9]
        p2 = T0[t2 >> 24] ^ T2[t0 >> 8 & 255] ^ T3[t1 & 255] ^ k[10]
        p3 = T1[t0 >> 16 & 255] ^ T2[t1 >> 8 & 255] ^ T3[t2 & 255] ^ k[11]
        for b in B:
            t3 = a3 ^ b                          # round 1's word 3
            u0, u1, u2, u3 = (p0 ^ T3[t3 & 255], p1 ^ T2[t3 >> 8 & 255],
                              p2 ^ T1[t3 >> 16 & 255], p3 ^ T0[t3 >> 24])
            for i in range(12, 36, 4):
                u0, u1, u2, u3 = (
                    T0[u0 >> 24] ^ T1[u1 >> 16 & 255] ^ T2[u2 >> 8 & 255] ^ T3[u3 & 255] ^ k[i],
                    T0[u1 >> 24] ^ T1[u2 >> 16 & 255] ^ T2[u3 >> 8 & 255] ^ T3[u0 & 255] ^ k[i + 1],
                    T0[u2 >> 24] ^ T1[u3 >> 16 & 255] ^ T2[u0 >> 8 & 255] ^ T3[u1 & 255] ^ k[i + 2],
                    T0[u3 >> 24] ^ T1[u0 >> 16 & 255] ^ T2[u1 >> 8 & 255] ^ T3[u2 & 255] ^ k[i + 3])
            t = T0[u0 >> 24] ^ T1[u1 >> 16 & 255] ^ T2[u2 >> 8 & 255] ^ T3[u3 & 255] ^ k[36]
            bits.append((S[t >> 24] ^ k40) >> 7)
    return bits


def gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def slot_params(counter):
    """The tile's slot permutation j -> (a j + b) mod 3996 (domain 6):
    16-bit draws below the largest multiple of 3996; a = the first one
    coprime to 3996, b = the next one."""
    limit = 65536 - 65536 % SLOTS
    ab, v = [], 0
    while len(ab) < 2:
        blk = keystream(ROW_KEY, 6, 0, 0, counter, v)
        for i in range(0, 16, 2):
            w = blk[i] << 8 | blk[i + 1]
            if w < limit and len(ab) < 2 and (ab or gcd(w % SLOTS, SLOTS) == 1):
                ab.append(w % SLOTS)
        v += 1
    return ab


# ================================================ 4. the tile's cell layout
def _bounded(u, bound):
    """Domain 4 under the sites seed: the first byte below the largest
    multiple of `bound`, modulo bound."""
    v = 0
    while True:
        for b in keystream(SITES_KEY, 4, 0, 0, u, v):
            if b < 256 - 256 % bound:
                return b % bound
        v += 1


# Site q sits in quota cell (q // 10, q % 10) of a 10 x 10 split of the tile.
EDGES = [i * TILE // 10 for i in range(11)]
SITES = [(EDGES[q // 10] + _bounded(2 * q, EDGES[q // 10 + 1] - EDGES[q // 10]),
          EDGES[q % 10] + _bounded(2 * q + 1, EDGES[q % 10 + 1] - EDGES[q % 10]))
         for q in range(N_SITES)]
_site_set = set(u * TILE + v for u, v in SITES)
NONSITE = [c for c in range(TILE * TILE) if c not in _site_set]   # the 3996 code cells
# The word's printed values are XORed with a scramble that is the same in every tile.
WORD_SCRAMBLE = [keystream(ROW_KEY, 2, 3, 0, i, 0)[0] >> 7 for i in range(N_SITES)]


# =========================================== 5. the address word (BCH)
# BCH(127,50,t=13) over GF(2^7) (x^7+x^3+1), shortened to (100,23): bits
# 0..76 parity, 77..94 the tile counter MSB-first, 95..99 zero.  Only the
# encoder is needed: the receiver checks words, it never has to decode one.
def _bch_generator():
    exp, x = [], 1
    for i in range(127):
        exp.append(x)
        x = x << 1 ^ (0x89 if x & 0x40 else 0)
    log = {e: i for i, e in enumerate(exp)}
    roots = set()
    for r in range(1, 2 * WORD_T + 1):      # the cyclotomic cosets of 1..26
        while r not in roots:
            roots.add(r)
            r = 2 * r % 127
    g = [1]                                  # coefficients, low first
    for r in roots:                          # g *= (x + alpha^r)
        g = [(g[i - 1] if i else 0) ^ (exp[(log[g[i]] + r) % 127] if i < len(g) and g[i] else 0)
             for i in range(len(g) + 1)]
    return sum(c << i for i, c in enumerate(g))   # binary: degree 77


BCH_G = _bch_generator()


def printed_word(counter):
    """The 100 values printed at a tile's sites, bit i = site i."""
    m = sum((counter >> 17 - j & 1) << j for j in range(18))
    r = m << 77
    for d in range(99, 76, -1):
        if r >> d & 1:
            r ^= BCH_G << d - 77
    word = r | m << 77
    return [(word >> i & 1) ^ WORD_SCRAMBLE[i] for i in range(N_SITES)]


# ================================================= 6. LDPC r0547 and CRC
# The e-IRA quasi-cyclic mother code (src/holo/core/ldpc/data/r0547.json),
# packed as ONE integer in mixed radix, least significant first: the
# interleaver pi (1856 entries) as its Lehmer code (digit i in radix
# 1856 - i picks from the entries left), then per info column block
# (10 heavy of degree 10, then 25 light of degree 3) its block rows
# (radix 29) and its circulant shifts (radix 64).
LDPC_TABLE = int(
    # LDPC-TABLE-BEGIN
    '1566e0df6832b9583f676d4bd9b01ccb8a8d9c338e2699b961c1db7cfeb4558160fbf1e1f46f'
    '3f2989acec7f415cfb8155f5325f7edc9b79eb6c670773b239cd81f5a05bac8ade9696ca9a38'
    '62843f3f743dc3f471305156d33757c5b79edc576959d1494f69e350fb6ac57ceb2c2f165c34'
    '043e1415442be74d4b94bd97d5436ee2ffa918df9eed6999763224cecc48f6e39a248fe6c28b'
    '4f8b04de449a0cc80c429250b1d948315b9ad0af434e9541e2c42e2f203170e197a54ee0a2bd'
    '0a54114fc9e6e629f97298f0adbd84489fc3b07b127df24c77985a918758a153c01e47b2c804'
    '1c6d49c3cce6b3c8d237709f9bd5b327bee0d1234ff3fe9a46e78a6b26243833461df09f5a21'
    '690f3f39ba4f4df9e46b84701c4754b5948146b850d20421669b8aeab82b616fd5ae71f3e6fc'
    '8f7fe0083401f447db9a3ecdfffc52da50945eacb1a0c5a26bb53c4ec6484e43e62498f1d865'
    'd02e6a41e1fd0ea40810f1cb92c716cd86af73f9df10cb452bf8fbc543a57cd940edb3cc0f45'
    '9e346cfc5a1a0736d94b9e5bb464cd1efbd519c7ceeac5f93f5770eaa6224c74dbc7b84e795d'
    '14335f82e7f5209acbe3f3395e489b1c6e23412e525d4c6e5a210f9938be54b0e117af4777bb'
    '8c1f8c3d0d6bfbf67d816eee368abf133c24f58e9454222aeb96d105885714acf0298119d1db'
    '0401e502bb1ca7ef6341f4d413b0aa52d461f9ba6b85ac252f160588f26df25433e71145b110'
    '451e44effb32b4d52db4127e39a0f1f33db4dcbe5a94a6714055bd46f323b2895618dc07c325'
    '03c61020679bdb6a83424328e15c602c133e0bb3a63ed1820ef02ef33621e033177943eacb64'
    '04d9ff6d0230ff12c3ff849acb54066b11179a47a2b176ced279582669cf5745023c49e3bbdc'
    'f2bf828cb4813d8f002abfb3ff4d606f077226dbb61b3eb81d933a5572e686497cbbea7315dd'
    '7f620bf7e24a303b33a3756ad7ea5b1bea28f31f461d14e4ac1951b1e03573129a588a0cdcee'
    'e95a7e1648ed44b0a7666dde115408614138648901b3572428b8f3cd17f4078fef4b2d76bf6c'
    '1a178ebfa52965f6da6fc6355c794a2d80bcdab0adb0b258c5689e50abe34e9e4003467f27cf'
    'd1ca8881fe8b49d12f7a48c72f512678f676e720371f3a464968a1e2c2e08b4589a4d463ea09'
    '81923789af601e21b15fed13c92f98e4181356d4520b3361c40b8734f41d3b4a8ed8aa30cd49'
    '6eb5b3cda549df2e29d2c6e8896948ef271e543ea2f59d5e9a431358240c0c60beb37b37cd5d'
    '1d89f465cd588e6ac36a3ea090fa92b51db65cb5362fb0387dcaad7271867b6a8ec168e11246'
    '0e685755ccd1821d1922e67ceb51a247b5812d0ba6ab212080310151751215a12f6f75de2b1b'
    'dbb618643bfeaa2ab84079d8e41271fba76ac3fc7f02c44dd70fe2d78e7bb254a79c19b452cf'
    '8ea5ed38f098e6f8dda651f66e2392ea652f462e101804323b2f2b5c057bfb2773ddf14d105b'
    '513f749cd8fd854cab894c851a9e566c035d3e7719077088b6b87f9e552b5371ae87b38ca72e'
    '6538974546feb9a481911770a72bcc686e04152100fa09dfdf36f117a72c581cb62e933f3cd4'
    'ffc4ae8b5bc9b94b9e48eaf9b7a846fdcfa94e8e6515c26ee589240703acbae9bf9a906262d2'
    'ccde81db870ad70eda2e0c43ef86d42ef8d33b4dd7ac92958092286fa907a4454dd2f7be0235'
    '19876b48ff290088f6a6ed34fc4bfdf10c8a0e3f8e96a4c2e5db82dbf3877dc6cc7b905f0fe8'
    '8f5ca08a0c002d11ee90db2a4002a30c214763fb4406107badcfe618622e9442c5ed3995b415'
    'eaab557569c342655c5235231ed82b5a417e29d89191be21a5a9b0b90f0ee3b9e20bf584c1e2'
    'f8b79a96f07b57ecff2a3d28d29c8a6b56d52f1864995e8f8f06b165c2064c461182bc7b1e2e'
    '3b0abab619cb700bfdec27491e70ad4843d6db22d85317cdc1ad49e086f39d5686e9764cec93'
    '62edd87b51cabbdcd488efdbe11df469d25b8d02711c0e9bcb6f3a168433d45aecdf4ed59af5'
    'b5f33901c403027b48fd716ec6b1aaeca8f2b37cdd5328ac526a1b4cabe19cdc2272ec3aee70'
    '1e69c5122ed91f83aaae8ca5f34f72449e6ecdf8d2b887a1e5f2e42a251cec85d392ca07eb5c'
    'd5a113c70debce5995efecd4752ab386f2ae8bd51f68479237bbb870e54954745b8ac9524c22'
    'b5ddb6c7f509af992d61574e8e3f9ab379d49eecc37b8008455b9321a0f893d7e1179d46d8a8'
    'ead4a4c8736db2868ed5d411bc5f42bdbc1b72b8f6f5b2bb8624f2696989a4137e6520691064'
    'ee69fbb6da8f5e1265edc0ae55348c06d7ff749b33e4526988b1eef336b014e7867dfc1096aa'
    '8249529ad920c517ab8aa3329e5e18a00d092347cf172539d8e82dd48f19335a61eb91075d23'
    'cc14f997373f7b2a37e669493e5b4dde31492fc0eacf84684af550fc2b3a87a4119aeab5d2b7'
    '51eb336d013a5318d0bf2f9973a2b8e3d6bbaa6311244dc6949a0ad736735169b6f40f881997'
    'e998962f90d8516a858e1d563c5debf2637236ac039732e04838d714cb5ee32a088543436c81'
    'ddcbc6db6f7493624dbe0460552208b6ee8a3a6e600fe26fe6184f113fa13e664b3d6f08af1b'
    '4fe9a25a61033563a1ba31a1d8ebebfce39ecd2b7982f867a053d425b87445ad1980928fbf95'
    'b82d654dba42bd92aa1966eac0e4197fbeda7932a3f95df2e55dc94c56445ea34764089d0964'
    'e70f619ab85936e54a416a39714abc8e63580a7b5ec1ad1a1434a492199686658b6a5d30951b'
    '76ab0e804b661c834a888ed6a9a103e91fad444695c4aba5894e34ddb60c4af67fff920603af'
    '0e40abebd695bfadcf5daa21120e47406ea3f2b88d37e4e1db64dd728cd391e557feeadf3cde'
    '2d959483e898f94e17311d6dcf0459dd2ef83e055b9f29b0707dad42b418f1eeaa12a4896f8f'
    '336a9a3ce4a059dd5d5076d7bfcd2b331d5fd10e4184869085418925036d47381c4a793b39ca'
    'b8b3983d4bf0203fbb0f100f7cb9640f0fc52f2bddb7ccebc0521237d5a39898ff2d13cdf077'
    '9d61003f6cef6fba2bb483cc95f4a27f44e77361a790ef6c9f02684ed52490f5dc0acfe3a438'
    '22933127ad0da525932141c2c908b429d24e3567c3bdae5e9e94fb6ad06d5ba7fd5ddfe990d9'
    '2da0915cf6cb16be086caf74de6db2404f1d538507c37fc54de3488d7332497b16a102708a6e'
    '265faa21cc2181dba9f2bd6c5f0c2fbfdd16bdde73bd5c847107b8acee8dd97522d4f2814892'
    'c56e9628e4545424412b9fec4cceb3fcac7c91cfb67a350ad868d77ab477fa6d320a9e8d57bc'
    'f820d861aa10bdb1b388d9439534471bc8539e7ce85dc529681696b9c5fc2cc08331769ef084'
    'f22ce7b8701be0c20668a9a6f15c1e1354576c5db1413b0da07eb39a65'
    # LDPC-TABLE-END
    , 16)


def _ldpc_checks():
    x = LDPC_TABLE

    def take(radix):
        nonlocal x
        x, d = divmod(x, radix)
        return d
    pool = list(range(N_CHECKS))
    pi = [pool.pop(take(N_CHECKS - i)) for i in range(N_CHECKS)]
    checks = [[] for _ in range(N_CHECKS)]
    for j, deg in enumerate([10] * 10 + [3] * 25):
        rows = [take(29) for _ in range(deg)]
        shifts = [take(64) for _ in range(deg)]
        for r, s in zip(rows, shifts):       # circulant I(s): a -> (a + s) mod 64
            for a in range(64):
                checks[pi[r * 64 + a]].append(j * 64 + (a + s) % 64)
    for q in range(N_CHECKS):                # the accumulator: parity q in checks q, q+1
        checks[q] += [K_INFO + q] + ([K_INFO + q - 1] if q else [])
    # the shortened info bits are known zeros: they never change a parity
    return [[v for v in c if not SHORT[0] <= v < SHORT[1]] for c in checks]


CHECKS = _ldpc_checks()


def syndrome_ok(L):
    return all(sum(L[v] < 0 for v in c) % 2 == 0 for c in CHECKS)


def ldpc_decode(L):
    """Layered normalised min-sum.  L: 4096 code-bit LLRs, positive = bit 0.
    Returns the updated LLRs when every check holds, else None."""
    L = L[:]
    if syndrome_ok(L):
        return L
    R = [[0.0] * len(c) for c in CHECKS]
    for _ in range(LDPC_ITERS):
        for vs, Rc in zip(CHECKS, R):
            q = [L[v] - r for v, r in zip(vs, Rc)]
            m1 = m2 = 1e30
            at = neg = 0
            for i, x in enumerate(q):
                if x < 0:
                    neg ^= 1
                    x = -x
                if x < m1:
                    m1, m2, at = x, m1, i
                elif x < m2:
                    m2 = x
            m1, m2 = m1 * LDPC_ALPHA, m2 * LDPC_ALPHA
            for i, v in enumerate(vs):
                x = q[i]
                r = m2 if i == at else m1
                if neg ^ (x < 0):
                    r = -r
                Rc[i] = r
                L[v] = x + r
        if syndrome_ok(L):
            return L
    return None


CRC_TABLE = []
for _n in range(256):
    for _ in range(8):
        _n = _n >> 1 ^ (0xEDB88320 if _n & 1 else 0)
    CRC_TABLE.append(_n)


def crc32(data):
    c = 0xFFFFFFFF
    for b in data:
        c = CRC_TABLE[(c ^ b) & 255] ^ c >> 8
    return c ^ 0xFFFFFFFF


def certify(L):
    """Hard bits of a decoded word -> (metadata bit, symbol) when the
    CRC-32 over the 2108 user bits (MSB-first, zero-padded to 264 bytes)
    equals bits 2108..2139.  A syndrome alone is never enough (r0550,
    r0547's twin, has low-weight codewords)."""
    bits = ''.join('1' if L[i] < 0 else '0' for i in range(SHORT[0]))
    user, crc = int(bits[:USER_BITS], 2), int(bits[USER_BITS:], 2)
    if crc32((user << 4).to_bytes(264, 'big')) != crc:
        return None
    return user >> SYMBOL_BITS, user & ((1 << SYMBOL_BITS) - 1)


# ============================================================ 7. the scan
# The quarter turns: page cell (u, v) of a tile sits at lattice cell
# ROT_T[k] + ROT_M[k] (u, v) inside the tile's 64 x 64 lattice block.
ROT_M = [((1, 0), (0, 1)), ((0, 1), (-1, 0)), ((-1, 0), (0, -1)), ((0, -1), (1, 0))]
ROT_T = [(0, 0), (0, 63), (63, 63), (63, 0)]


class Scan:
    """One greyscale capture.  The cell lattice is (oy, ox, ay, ax, by, bx):
    lattice cell (i, j) has its centre at pixel
    (oy + i ay + j by, ox + i ax + j bx)."""

    def __init__(self, name, dpi):
        raw = open(name, 'rb').read()
        fields, at = [], 2
        if raw[:2] != b'P5':
            raise ValueError('not a binary PGM (P5)')
        while len(fields) < 3:                  # width, height, maxval; '#' comments
            while raw[at] in b' \t\r\n':
                at += 1
            if raw[at] == 35:
                while raw[at] not in b'\r\n':
                    at += 1
                continue
            start = at
            while raw[at] not in b' \t\r\n':
                at += 1
            fields.append(int(raw[start:at]))
        self.W, self.H, maxval = fields
        self.bpp = 2 if maxval > 255 else 1     # 16 bit: the high (first) byte is read
        self.buf, self.off, self.row = raw, at + 1, self.W * self.bpp
        self.pitch = CELL_DOTS * dpi / ENGINE_DPI          # pixels per cell, declared
        self.aperture(self.pitch)

    def aperture(self, p):
        """The box for a cell pitch of p pixels."""
        self.ap = max(2, round(0.7 * p))                    # box aperture, pixels
        self.step = max(1, self.ap // 4)                    # read at most 4 x 4 of it

    def box(self, y, x):
        """Sum of the aperture box centred at pixel (y, x); None off the image."""
        a = self.ap
        y0, x0 = int(y - a / 2 + 0.5), int(x - a / 2 + 0.5)
        if y0 < 0 or x0 < 0 or y0 + a > self.H or x0 + a > self.W:
            return None
        buf, st, bpp = self.buf, self.step, self.bpp
        p = self.off + y0 * self.row + x0 * bpp
        return sum(sum(buf[q:q + a * bpp:st * bpp]) for q in range(p, p + a * self.row, st * self.row))

    def at(self, lat, i, j):
        oy, ox, ay, ax, by, bx = lat
        return self.box(oy + i * ay + j * by, ox + i * ax + j * bx)

    # ---- the lattice: angle, phase, scale
    def phase(self, lat, ci, cj, n, step):
        """The sub-cell offset (di, dj) of the lattice near cell (ci, cj) that
        makes the sampled cells most spread (a box inside a cell reads ink or
        paper, a box across cells reads grey).  Returns (variance, di, dj,
        best/worst variance) or None where too little was on the image."""
        V = [[0.0] * 8 for _ in range(8)]
        for a in range(8):
            for b in range(8):
                vals = [self.at(lat, ci + i + a / 8 - 0.5, cj + j + b / 8 - 0.5)
                        for i in range(-n, n + 1, step) for j in range(-n, n + 1, step)]
                vals = [v for v in vals if v is not None]
                if len(vals) < 20:
                    return None
                mean = sum(vals) / len(vals)
                V[a][b] = sum((v - mean) ** 2 for v in vals) / len(vals)
        best = max((V[a][b], a, b) for a in range(8) for b in range(8))
        _, a, b = best

        def vertex(lo, mid, hi):      # parabola through three samples, 1/8 apart
            den = lo - 2 * mid + hi
            return 0.0 if den >= 0 else max(-0.5, min(0.5, 0.5 * (lo - hi) / den)) / 8
        di = a / 8 - 0.5 + vertex(V[a - 1][b], V[a][b], V[(a + 1) % 8][b])
        dj = b / 8 - 0.5 + vertex(V[a][b - 1], V[a][b], V[a][(b + 1) % 8])
        worst = min(min(r) for r in V)
        return best[0], di, dj, best[0] / max(worst, 1e-9)

    def find_lattice(self):
        """The candidate lattices, one at a time (a generator): the reader
        tries each until one places a tile, so the address word, not a
        contrast floor, says which lattice is the page's.  At a start point
        of the page and a trial pitch (the declared one, then 4 % under and
        over it: a print scaled to fit the paper, a dpi given wrong), the
        coarse angle by search over a small window (17 x 17 cells: it still
        locks with the pitch 4 % off), then the lattice tracked outward on
        rings of doubling radius from 4 cells (8 directions, each with
        sideways fallbacks where a tile is blank), refitted at every ring:
        each ring measures how far the cell phase has drifted from the
        lattice's prediction, so the refit corrects the pitch and the angle
        before the next ring doubles the lever.
        A measurement that lands near half a cell from its prediction could
        be the neighbouring cell and is not used; points off the fit by more
        than 0.3 cell are dropped at the end.  A candidate must rest on at
        least 12 points and be square: both steps within 6 % of the trial
        pitch, 2 degrees of a right angle."""
        for fy, fx in ((0.5, 0.5), (0.35, 0.5), (0.65, 0.5), (0.5, 0.3), (0.5, 0.7),
                       (0.3, 0.3), (0.7, 0.7), (0.3, 0.7), (0.7, 0.3)):
            cy, cx = self.H * fy, self.W * fx
            for f in (1, 0.96, 1.04):
                p = self.pitch * f
                self.aperture(p)
                lat = self.track(cy, cx, p)
                if lat:
                    yield lat

    def track(self, cy, cx, p):
        """The lattice found from pixel (cy, cx) at trial pitch p, or None;
        the box is set to the pitch found."""
        best = None
        for t in range(-20, 21):                  # -10 .. 10 degrees, 0.5 apart
            c, s = cos_sin(t * 0.5)
            lat = (cy, cx, p * c, -p * s, p * s, p * c)
            r = self.phase(lat, 0, 0, 8, 1)
            if r and (best is None or r[0] > best[0][0]):
                best = (r, lat)
        if best and best[0][3] > 1.2:
            (_, di, dj, _), (oy, ox, ay, ax, by, bx) = best
            pts = [(0, 0, oy + di * ay + dj * by, ox + di * ax + dj * bx)]
            lat = (pts[0][2], pts[0][3], ay, ax, by, bx)
            D, misses = 4, 0
            while D < 4000 and misses < 2:            # two empty rings end the walk
                n = len(pts)
                for ui, uj in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    for side in (0, 0.25, -0.25, 0.5, -0.5):
                        i, j = round(D * (ui - uj * side)), round(D * (uj + ui * side))
                        r = self.phase(lat, i, j, 8, 1)
                        if r and r[3] > 1.2 and abs(r[1]) < 0.35 and abs(r[2]) < 0.35:
                            oy, ox, ay, ax, by, bx = lat
                            ii, jj = i + r[1], j + r[2]
                            pts.append((i, j, oy + ii * ay + jj * by, ox + ii * ax + jj * bx))
                            break
                misses = misses + 1 if len(pts) == n else 0
                lat = fit_lattice(pts, lat)
                D *= 2
            oy, ox, ay, ax, by, bx = lat
            pts = [q for q in pts if ((oy + q[0] * ay + q[1] * by - q[2]) ** 2
                                      + (ox + q[0] * ax + q[1] * bx - q[3]) ** 2) < (0.3 * p) ** 2]
            oy, ox, ay, ax, by, bx = lat = fit_lattice(pts, lat)
            la, lb = (ay * ay + ax * ax) ** 0.5, (by * by + bx * bx) ** 0.5
            if (len(pts) >= 12 and abs(la / p - 1) < 0.06 and abs(lb / p - 1) < 0.06
                    and abs(ay * by + ax * bx) < 0.035 * la * lb):
                self.aperture((la + lb) / 2)
                return lat
        return None

    # ---- the first tile: every quarter turn and every cell phase
    def first_tile(self, lat, ci, cj):
        """Hard-read a 192 x 192 block of cells around lattice cell (ci, cj)
        and look in it for a tile whose 100 sites read as a valid address
        word (zero pads, a counter on the archive, <= 13 errors)."""
        N = 192
        vals = [[self.at(lat, ci + i, cj + j) for j in range(N)] for i in range(N)]
        seen = sorted(v for row in vals for v in row if v is not None)
        if len(seen) < N * N // 2:
            return None
        thr = (seen[len(seen) // 10] + seen[len(seen) * 9 // 10]) / 2
        g = [[2 if v is None else int(v < thr) for v in row] for row in vals]   # 1 = ink
        best = None
        for k in range(4):
            (m00, m01), (m10, m11) = ROT_M[k]
            t0, t1 = ROT_T[k]
            off = [(t0 + m00 * u + m01 * v, t1 + m10 * u + m11 * v) for u, v in SITES]
            pads = [(off[i], WORD_SCRAMBLE[i]) for i in range(95, 100)]
            for R in range(N - TILE):
                for C in range(N - TILE):
                    if any(g[R + y][C + x] != s for (y, x), s in pads):
                        continue
                    counter = 0
                    for i in range(77, 95):
                        y, x = off[i]
                        counter = counter << 1 | (g[R + y][C + x] ^ WORD_SCRAMBLE[i]) & 1
                    if counter // TILES_PER_PAGE >= MAX_PAGES:
                        continue
                    word = printed_word(counter)
                    err = sum(g[R + y][C + x] != w for (y, x), w in zip(off, word))
                    if err <= WORD_T and (best is None or err < best[0]):
                        best = (err, k, ci + R, cj + C, counter)
        return best

    # ---- every other tile
    def frame(self, lat, tile, d):
        """Pixel of the tile's page cell (0, 0) and the pixel steps along u
        and v, for a tile with lattice residual d = (di, dj)."""
        oy, ox, ay, ax, by, bx = lat
        (m00, m01), (m10, m11) = ROT_M[self.rot]
        t0, t1 = ROT_T[self.rot]
        dy, dx = TILE * (tile[0] - self.t0[0]), TILE * (tile[1] - self.t0[1])
        i = self.anchor[0] + m00 * dy + m01 * dx + t0 + d[0]
        j = self.anchor[1] + m10 * dy + m11 * dx + t1 + d[1]
        return (oy + i * ay + j * by, ox + i * ax + j * bx,
                m00 * ay + m10 * by, m00 * ax + m10 * bx,
                m01 * ay + m11 * by, m01 * ax + m11 * bx)

    def site_reads(self, lat, tile, d):
        y0, x0, uy, ux, vy, vx = self.frame(lat, tile, d)
        return [self.box(y0 + u * uy + v * vy, x0 + u * ux + v * vx) for u, v in SITES]

    def score(self, lat, tile, d, word):
        """Paper minus ink over the sites, as the word says they should read."""
        s = 0
        for m, w in zip(self.site_reads(lat, tile, d), word):
            if m is None:
                return None
            s += -m if w else m
        return s

    def place(self, lat, tile, d0, word):
        """Search the tile's residual around d0 (coarse 0.25-cell grid, then
        1/8 and a parabola) and accept it if its sites show its word."""
        for span, stp in ((2, 0.25), (5, 0.5)):       # second: a wider net
            best = None
            for a in range(-span, span + 1):
                for b in range(-span, span + 1):
                    d = (d0[0] + a * stp, d0[1] + b * stp)
                    s = self.score(lat, tile, d, word)
                    if s is not None and (best is None or s > best[0]):
                        best = (s, d)
            if best is None:
                return None
            for h in (stp / 2, stp / 4):
                c = best[1]
                for d in ((c[0] - h, c[1]), (c[0] + h, c[1]), (c[0], c[1] - h), (c[0], c[1] + h)):
                    s = self.score(lat, tile, d, word)
                    if s is not None and s > best[0]:
                        best = (s, d)
            d = best[1]
            reads = self.site_reads(lat, tile, d)
            ink = [m for m, w in zip(reads, word) if w]
            paper = [m for m, w in zip(reads, word) if not w]
            thr = (sum(ink) / len(ink) + sum(paper) / len(paper)) / 2
            if sum((m < thr) != w for m, w in zip(reads, word)) <= GATE_MISMATCH:
                return d
        return None

    def tile_llrs(self, lat, tile, d, word):
        """Every cell's soft bit (positive = paper = 0), calibrated on the
        tile's own 100 sites: the Gaussian log-likelihood ratio between the
        paper and ink means with their pooled variance, clipped at 20."""
        y0, x0, uy, ux, vy, vx = self.frame(lat, tile, d)
        box = self.box
        reads = [box(y0 + u * uy + v * vy, x0 + u * ux + v * vx)
                 for u in range(TILE) for v in range(TILE)]
        sites = [(reads[u * TILE + v], w) for (u, v), w in zip(SITES, word)]
        ink = [m for m, w in sites if w]
        paper = [m for m, w in sites if not w]
        mi, mp = sum(ink) / len(ink), sum(paper) / len(paper)
        var = (sum((m - mi) ** 2 for m in ink) + sum((m - mp) ** 2 for m in paper)) / len(sites)
        gain, mid = (mp - mi) / max(var, 1e-9), (mp + mi) / 2
        return [0.0 if m is None else max(-20.0, min(20.0, (m - mid) * gain)) for m in reads]


def cos_sin(deg):
    """cos and sin by their series (no math module); |deg| <= 45."""
    x = deg * 3.141592653589793 / 180
    c = s = 0.0               # cos = 1 - x^2/2! + ..., sin = x - x^3/3! + ...
    t = 1.0
    for n in range(30):
        if n % 4 == 0:
            c += t
        elif n % 4 == 1:
            s += t
        elif n % 4 == 2:
            c -= t
        else:
            s -= t
        t *= x / (n + 1)
    return c, s


def fit_lattice(pts, lat):
    """Least squares (oy, ay, by) and (ox, ax, bx) over the measured
    lattice points (i, j, y, x); the old lattice if they cannot fix it."""
    A = [[0.0] * 3 for _ in range(3)]
    ry, rx = [0.0] * 3, [0.0] * 3
    for i, j, y, x in pts:
        f = (1.0, i, j)
        for r in range(3):
            for c in range(3):
                A[r][c] += f[r] * f[c]
            ry[r] += f[r] * y
            rx[r] += f[r] * x
    sy, sx = solve3(A, ry), solve3(A, rx)
    if sy is None or sx is None:
        return lat
    return sy[0], sx[0], sy[1], sx[1], sy[2], sx[2]


def solve3(A, r):
    def det(M):
        return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1])
                - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
                + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
    D = det(A)
    if abs(D) < 1e-6 * (A[1][1] * A[2][2] + 1):
        return None
    return [det([[r[a] if c == k else A[a][c] for c in range(3)] for a in range(3)]) / D
            for k in range(3)]


# ========================================================== 8. the volume
# Every tile c carries one metadata bit, parity(M & x^c mod (x^24+x^4+x^3+x+1)),
# M the 24-bit word [version 0][K, 18 bits MSB-first][5 zero bits] (bit i of
# M = word position i).  M gives K, and it tells volumes apart: every volume
# of this row shares the seed and counts its tiles from 0, so a page's
# metadata bits are the one thing on it that says which volume it is from.
LFSR = [1]                    # x^c mod the polynomial, for c = 0, 1, ...


def lfsr(c):
    while len(LFSR) <= c:
        s = LFSR[-1]
        LFSR.append((s << 1 & 0xFFFFFF) ^ (0x1B if s & 0x800000 else 0))
    return LFSR[c]


def meta_bit(M, c):
    return bin(M & lfsr(c)).count('1') & 1


def k_of(M):
    return sum((M >> 1 + j & 1) << 17 - j for j in range(18))


def solve_metadata(meta):
    """M from {tile counter: metadata bit}: None below 48 tiles or rank 24."""
    basis = {}                                   # lowest bit -> (row, rhs)
    for c, b in meta.items():
        row = lfsr(c)
        while row:
            low = (row & -row).bit_length() - 1
            if low not in basis:
                basis[low] = (row, b)
                break
            row ^= basis[low][0]
            b ^= basis[low][1]
        if not row and b:
            raise ValueError('metadata bits contradict each other')
    if len(basis) < 24 or len(meta) < 48:
        return None
    M = 0
    for low in sorted(basis, reverse=True):      # back-substitution
        row, b = basis[low]
        M |= (b ^ bin(row & M).count('1') % 2) << low
    K = k_of(M)
    if M & 1 or M >> 19 or not K:
        raise ValueError('metadata: unsupported version or reserved bits set')
    if K > 16384:
        raise ValueError('K = %d: a multi-block volume (> 4.3 MB), not handled here' % K)
    return M


class Conflict(Exception):
    """A scan whose tiles cannot belong to the volume they were put in."""


class Volume:
    """One volume: its certified symbols and the fountain's equations, kept
    in echelon form as they arrive (tile c < K is source symbol c itself,
    tile c >= K a repair row), so the volume closes on the tile that brings
    the rank to K, never later, and a tile that contradicts the others is
    seen the moment it comes."""

    def __init__(self, M, number):
        self.M, self.K, self.number = M, k_of(M), number
        self.symbols = {}         # tile counter -> 2107-bit symbol
        self.rows = {}            # pivot -> (mask, value); mask bit k = source k
        self.scans = []           # the scans that gave it tiles
        self.payload = None
        self.written = None       # the file the payload went to

    def begin(self, name):
        """A scan's tiles go in all or not at all: this is the way back."""
        self.saved = dict(self.symbols), dict(self.rows), self.payload
        self.scans.append(name)

    def rollback(self):
        self.symbols, self.rows, self.payload = self.saved
        self.scans.pop()

    def coefficients(self, c):
        """Repair row c: source k enters iff bit k (MSB-first) of the AES
        blocks (domain 7, aux 0, block 0, u c, v 0, 1, ...) is 1."""
        W = (self.K + 127) // 128
        bits = int.from_bytes(b''.join(keystream(ROW_KEY, 7, 0, 0, c, v)
                                       for v in range(W)), 'big')
        return int(bin(bits | 1 << 128 * W)[3:][::-1], 2) & ((1 << self.K) - 1)

    def add(self, counter, symbol):
        old = self.symbols.get(counter)
        if old is not None:
            if old != symbol:
                raise Conflict('tile %d differs from the one read before' % counter)
            return
        self.symbols[counter] = symbol
        if self.payload is not None:
            return
        mask = 1 << counter if counter < self.K else self.coefficients(counter)
        val = symbol
        while mask:                                  # reduce, lowest pivot first
            low = (mask & -mask).bit_length() - 1
            row = self.rows.get(low)
            if row is None:
                self.rows[low] = (mask, val)
                if len(self.rows) == self.K:
                    self.close()
                return
            mask ^= row[0]
            val ^= row[1]
        if val:
            raise Conflict('tile %d contradicts the tiles read before' % counter)

    def close(self):
        """Rank K: back-substitute, then the envelope's three gates.  A
        wrong SHA-256 at rank K means a tile of another volume of the same
        size is in: the scan that brought the rank to K is refused."""
        K, S = self.K, SYMBOL_BITS
        src = [0] * K
        for low in sorted(self.rows, reverse=True):
            mask, val = self.rows[low]
            rest = mask >> low + 1
            while rest:
                bit = rest & -rest
                val ^= src[low + bit.bit_length()]
                rest ^= bit
            src[low] = val
        stream = 0
        for s in src:
            stream = stream << S | s
        pad = -K * S % 8
        data = (stream << pad).to_bytes((K * S + pad) // 8, 'big')
        n = int.from_bytes(data[32:36], 'big')
        used = 8 * (36 + n)
        if (36 + n > len(data) or -(-used // S) != K or stream & ((1 << K * S - used) - 1)
                or sha256(data[36:36 + n]) != data[:32]):
            raise Conflict('the volume solves, but its SHA-256 is wrong')
        self.payload = data[36:36 + n]

    def state(self):
        return ('volume %d: symbols held %d / needed %d; %s' % (
            self.number, len(self.symbols), self.K,
            'done' if self.payload is not None else 'more'))


# =============================================== 9. the reader: scan by scan
class Receiver:
    def __init__(self):
        self.volumes = []         # in the order they appeared
        self.loose = []           # (scan, tiles) too few to say their volume

    def volume_of(self, tiles):
        """The volume of these certified tiles (counter, metadata bit,
        symbol): the one known volume whose word all their bits agree with,
        once there are 24 (a wrong one agrees with odds 2^-24), else the word
        they solve for themselves (48 tiles), a new volume if it is new."""
        meta = {c: b for c, b, _ in tiles}
        agree = [v for v in self.volumes if all(meta_bit(v.M, c) == b for c, b in meta.items())]
        if len(meta) >= 24 and len(agree) == 1:
            return agree[0]
        M = solve_metadata(meta)
        if M is None:
            return None
        for v in self.volumes:
            if v.M == M:
                return v
        self.volumes.append(Volume(M, len(self.volumes) + 1))
        return self.volumes[-1]

    def enter(self, vol, counter, bit, symbol):
        if meta_bit(vol.M, counter) != bit:
            raise Conflict('tile %d carries another volume\'s metadata' % counter)
        vol.add(counter, symbol)

    def commit(self, name, vol, tiles):
        """Put a scan's tiles into a volume, all or none; the refusal or ''."""
        vol.begin(name)
        try:
            for t in tiles:
                self.enter(vol, *t)
        except Conflict as e:
            vol.rollback()
            return self.refusal(name, vol, e)
        return ''

    def refusal(self, name, vol, why):
        return ('%s REFUSED (%s): it has the size of volume %d but not its '
                'content, so it or one of the scans %s is from another volume of '
                'that size; its tiles are not used' % (name, why, vol.number,
                                                       ', '.join(vol.scans)))

    def read_scan(self, name, dpi):
        """Place and decode one scan; returns its progress line.  A scan that
        places no tile at the dpi given is searched again, whole, at the other
        usual scanner resolutions, nearest first: four searches at most."""
        sc = Scan(name, dpi)
        found = placed = None
        order = [dpi] + [r for _, r in sorted((abs(r - dpi), r) for r in (600, 1200, 2400) if r != dpi)]
        for k, res in enumerate(order):
            if k:
                print('%s: no tile placed at %d dpi, trying %d dpi' % (name, order[k - 1], res))
            sc.pitch = CELL_DOTS * res / ENGINE_DPI    # pixels per cell at that dpi
            for lat in sc.find_lattice():           # until a lattice places a tile
                found = lat
                placed = self.place_page(sc, lat)
                if placed:
                    break
            if placed:
                break
        if found is None:
            return '%s: no cell lattice found at %s dpi (one page, whole?)' % (
                name, ', '.join(map(str, order)))
        if placed is None:
            return ('%s: no tile address found (wrong FORMAT_ID, a mirror-image '
                    'scan, or not this row?)' % name)
        print('%s: cell lattice found, %d tiles placed, decoding' % (name, len(placed)))
        page, tiles, vol, note = self.page, [], None, ''
        tried = 0
        for tile, d in placed.items():
            counter = page * TILES_PER_PAGE + tile[0] * TILES_X + tile[1]
            if vol is not None:
                if vol.payload is not None:          # complete: nothing more to read
                    break
                if counter in vol.symbols:           # this page was read before
                    continue
            tried += 1
            r = self.decode_tile(sc, lat, tile, d, counter)
            if not r:
                continue
            tiles.append((counter,) + r)
            if vol is None:                          # whose page is it?
                vol = self.volume_of(tiles)
                if vol is not None:
                    vol.begin(name)
                    todo = tiles
                else:
                    todo = []
            else:
                todo = tiles[-1:]
            try:
                for t in todo:
                    self.enter(vol, *t)
            except Conflict as e:
                vol.rollback()
                note = '; ' + self.refusal(name, vol, e)
                break
        head = '%s: page %d, turn %d, tiles placed %d/%d, decoded %d, certified %d; ' % (
            name, page, 90 * sc.rot, len(placed), TILES_PER_PAGE, tried, len(tiles))
        if vol is None:
            if tiles:
                self.loose.append((name, tiles))
            return head + 'too few to tell its volume, set aside' + self.place_loose()
        return head + vol.state() + note + self.place_loose()

    def place_loose(self):
        """Scans kept aside, tried again against the volumes known now, or
        pooled, when together they solve a metadata word of their own."""
        out = ''
        try:
            self.volume_of([t for _, ts in self.loose for t in ts])
        except ValueError:                           # the pool mixes volumes
            pass
        for item in self.loose[:]:                   # a thin scan: 8 bits or more,
            name, tiles = item                       # all agreeing with one volume
            agree = [v for v in self.volumes
                     if all(meta_bit(v.M, c) == b for c, b, _ in tiles)]
            if len(agree) == 1 and len(tiles) >= 8:
                self.loose.remove(item)
                out += '; ' + (self.commit(name, agree[0], tiles) or
                               '%s, set aside before, now in %s' % (name, agree[0].state()))
        return out

    def place_page(self, sc, lat):
        """First tile by exhaustive search, then breadth-first over the
        page's tile grid, each tile predicted from its placed neighbours."""
        for ci, cj in ((-96, -96), (-300, -96), (108, -96), (-96, -300), (-96, 108),
                       (-500, -96), (308, -96), (-96, -500), (-96, 308)):
            hit = sc.first_tile(lat, ci, cj)
            if not hit:
                continue
            _, sc.rot, ai, aj, counter = hit
            sc.anchor = (ai, aj)
            self.page, local = divmod(counter, TILES_PER_PAGE)
            sc.t0 = divmod(local, TILES_X)
            # the walk goes on through tiles that fail (blank, torn, smudged):
            # a tile is predicted from the nearest placed ones, not only from
            # its direct neighbours
            placed, failed, queue, seen = {}, [], [sc.t0], {sc.t0}
            while queue:
                tile = queue.pop(0)
                if not self.place_tile(sc, lat, tile, placed):
                    failed.append(tile)
                for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    t = (tile[0] + dy, tile[1] + dx)
                    if 0 <= t[0] < TILES_Y and 0 <= t[1] < TILES_X and t not in seen:
                        seen.add(t)
                        queue.append(t)
            for tile in failed:                    # once more, with every neighbour placed
                self.place_tile(sc, lat, tile, placed)
            if len(placed) >= 3:
                return placed
        return None

    def place_tile(self, sc, lat, tile, placed):
        near = []
        for r in (1, 2, 3, 4):                  # the closest ring that holds placed tiles
            near = [placed[(tile[0] + dy, tile[1] + dx)] for dy in range(-r, r + 1)
                    for dx in range(-r, r + 1) if (tile[0] + dy, tile[1] + dx) in placed]
            if near:
                break
        d0 = (sum(d[0] for d in near) / len(near), sum(d[1] for d in near) / len(near)) if near else (0, 0)
        counter = self.page * TILES_PER_PAGE + tile[0] * TILES_X + tile[1]
        d = sc.place(lat, tile, d0, printed_word(counter))
        if d is not None:
            placed[tile] = d
        return d is not None

    def decode_tile(self, sc, lat, tile, d, counter):
        """The tile's (metadata bit, symbol), or None.  A tile that fails is
        decoded again at its residual moved 1/8 cell either way along each
        axis (four tries at most, each gated by the CRC), the first that
        certifies taken: the scan is not affine within a tile, and the
        residual that fits its address sites best can sit at the edge of
        the window that decodes."""
        word = printed_word(counter)
        scr = payload_scramble(self.page, TILE * tile[0], TILE * tile[1])
        a, b = slot_params(counter)
        for e in ((0, 0), (0.125, 0), (-0.125, 0), (0, 0.125), (0, -0.125)):
            llr = sc.tile_llrs(lat, tile, (d[0] + e[0], d[1] + e[1]), word)
            L = [0.0] * N_CODE
            for j in range(SLOTS):                  # printed bit j -> code position
                cell = NONSITE[(a * j + b) % SLOTS]
                x = llr[cell]
                L[j if j < SHORT[0] else j + SHORT[1] - SHORT[0]] = -x if scr[cell] else x
            L = ldpc_decode(L)
            r = L and certify(L)
            if r:
                return r
        return None

# ======================================================== 10. the archive
# A volume whose payload starts with b'R3A1' carries an archive
# CONTAINER (any other payload is left as payload.bin, nothing more):
#     b'R3A1'   magic, 4 bytes
#     n         the archive's length in bytes, 8 bytes big-endian
#     crc       CRC-32 of the archive (crc32 above, the zlib one), 4 bytes BE
#     z         the coder's bytes (unz)
# The archive is a ustar tar of the tree (files sorted, mtime 0, uid/gid
# 0, no user/group names, regular files only); unpack() writes it.  The
# glue is in main(): it decodes, checks the CRC-32, unpacks.


def unz(z):
    """The archive decoder: z = the container, returns the archive (n bytes).

    A bitwise context-mixing model (the cmmix/lpaq family) drives a binary
    arithmetic decoder of 32-bit bounds, so the cost is linear in n.  Per
    bit, ten predictions: order 0 and order 1 (direct tables), orders 2, 3,
    4 and 7, the current word (letters, digits, '_'), the word bigram, and
    the column context (the byte above in the previous line, the column)
    -- hashed into 16-slot nibble buckets of T with a 16-bit check, each
    slot a 12-bit probability and a 4-bit count (adaptation 1/(count+1.2));
    plus a match model (the last occurrence of the order-7 context, mt; the
    bit it predicts, by match length, U/V).  The stretched predictions are
    mixed by three summed weight sets (chosen by match length, by the last
    byte, by a 12-bit hash of order 2), squashed, refined by two APMs (by
    order 1, by a hash of order 3) and averaged 2:3:3.  Tables of 2^k slots
    (k = 28): about 1.4 GB, whatever n.  The encoder is derived from this
    text mechanically (bootstrap/r3/arch/derive.py, arch_pack.py)."""
    n, s = int.from_bytes(z[4:12], 'big'), z[16:] + bytes(8)
    F, q, k = 2 ** 32 - 1, 1460000, 28
    Q = F * F + F + F
    sq, st, K = [0] * 4096, [0] * 1024, 0x7fffffe87fffffe03ff000000000000
    for x in range(4096):
        sq[x] = q >> 20
        q += q * ((4096 << 20) - q) >> 40
        st[sq[x] >> 2] = x - 2048
    D, A, G, E = 1 << k, 68 - k, 0x9E3779B1, 0x9E3779B97F4A7C15
    T = memoryview(bytearray(b"\x80" * (2 * D + 263168))).cast("H")
    Z = memoryview(bytearray(b"\x80" * 30)).cast("H")
    mt = memoryview(bytearray(D)).cast("I")
    W = memoryview(bytearray(44605440)).cast("i")
    U, V, B = [32768] * 32, [0] * 32, [0] * 9
    R = [655360 // (j * 10 + 12) for j in range(31)]
    AP = [sq[min(4095, j % 33 * 128)] * 16 for j in range(33 * 65536)]
    AQ = AP[:]
    b = bytearray(8 + n)
    x1 = x2 = x = kk = h = wh = wp = mp = ml = 0
    pl = ls = 8
    for i in range(8, n + 8):
        c, c0 = b[i - 1], 1
        h = (h << 8 | c) & Q >> 8
        if K >> c & 1:
            wh = (wh + c + 1) * 773 & F
        elif wh:
            wp, wh = wh, 0
        if c == 10:
            pl, ls = ls, i
        r = b[min(pl + i - ls, ls - 1)] << 8 | min(i - ls, 40)
        H = [0, 0, h & 65535, h & 16777215, h & F, wh, r, h, wh + wp * 31337 + 1]
        ml, mp = (ml + (ml < 15)) * (ml > 0), mp + 1
        o = h * G >> 50 - k & (D >> 2) - 1
        mp = mp if ml else mt[o]
        ml, mt[o] = ml or int(mp > 0), i
        for j in range(8):
            if j == 0 or j == 4:
                B[0], B[1] = D + c0 * 16, D + 512 + c * 512 + c0 * 16
                for q in range(2, 9):
                    z = ((H[q] * 16 + q) * 32 + c0) * E & Q
                    t, cz = z >> A << 4, z >> A - 16 & 65535
                    if T[t] != cz:
                        if T[t ^ 16] == cz:
                            t ^= 16
                        else:
                            if T[t + 1] & 15 > T[t ^ 17] & 15:
                                t ^= 16
                            T[t], T[t + 1:t + 16] = cz, Z
                    B[q] = t
                cn = 1
            X = [t + cn for t in B]
            e = b[mp] >> 7 - j & 1
            mi = ml * 2 + e
            S = [st[T[t] >> 6] for t in X] + [st[U[mi] >> 6]]
            w, u = (c0 + 256 * min(ml, 3)) * 10, (1024 + c * 256 + c0) * 10
            v = (66560 + ((h & 65535) * G >> 20 & 4095) * 256 + c0) * 10
            d = sum([(W[w + q] + W[u + q] + W[v + q] * 2 + 65536) * S[q]
                     for q in range(10)]) >> 18
            dd = max(-2047, min(2047, d)) + 2048
            pm, wa = sq[dd], dd & 127
            a = (c * 256 + c0) * 33 + (dd >> 7)
            a2 = ((h & 16777215) * G >> 16 & 65535) * 33 + (dd >> 7)
            p = 2 * pm + 3 * (AP[a] * (128 - wa) + AP[a + 1] * wa >> 11)
            p = max(1, min(4095, p + 3 * (AQ[a2] * (128 - wa) + AQ[a2 + 1] * wa >> 11) >> 3))
            # CODER
            while (x1 ^ x2) >> 24 == 0:
                x1, x2 = x1 << 8 & F, x2 << 8 & F | 255
                x, kk = x << 8 & F | s[kk], kk + 1
            xm = x1 + (x2 - x1 >> 12) * p
            x1, x2, y = (x1, xm, 1) if x <= xm else (xm + 1, x2, 0)
            # /CODER
            a, a2 = a + (wa >> 6), a2 + (wa >> 6)
            AP[a] += (y << 16) - AP[a] >> 6
            AQ[a2] += (y << 16) - AQ[a2] >> 6
            for t in X:
                pt, nt = T[t] >> 4, T[t] & 15
                pt += ((y << 12) - pt) * R[nt] >> 16
                T[t] = pt << 4 | nt + (nt < 15)
            U[mi] += ((y << 16) - U[mi]) * R[V[mi]] >> 16
            V[mi] += V[mi] < 30
            g = (y << 12) - pm
            for q in range(10):
                dq = S[q] * g >> 11
                W[w + q] += dq
                W[u + q] += dq
                W[v + q] += dq
            c0, cn = c0 + c0 + y, cn + cn + y
            ml = ml * (e == y)
        b[i] = c0 & 255
        if (i - 7) * 20 // n > (i - 8) * 20 // n:    # a heartbeat every 5 %
            print('archive: %d%% decoded' % ((i - 7) * 20 // n * 5))
    return bytes(b[8:])


def unpack(d):
    """A ustar subset: d = the tar.  Every member is taken as a regular
    file (the container's tars carry nothing else: arch_pack.py checks);
    its path is the prefix field (offset 345), '/', the name field, NULs
    dropped; its size is octal at 124; the data is padded to 512 bytes; the
    archive ends at a block whose name is empty."""
    i = 0
    while d[i]:
        h, i = d[i:i + 512], i + 512
        f = (h[345:500] + b'/' + h[:100]).replace(b'\0', b'').lstrip(b'/').decode()
        n = int(h[124:135], 8)
        print(f)
        open(f.replace('%', '%25').replace('/', '%2F'), 'wb').write(d[i:i + n])
        i += n + 511 & -512


def main():
    rx = Receiver()
    while True:
        try:
            line = input('scan (PGM file [dpi]; empty line ends): ').split()
        except EOFError:
            break
        if not line:
            break
        try:
            print(rx.read_scan(line[0], int(line[1]) if len(line) > 1 else 1200))
        except (OSError, ValueError, IndexError) as e:
            print('%s: %s' % (line[0], e))
        for v in rx.volumes:          # each volume, once complete: to its file
            if v.payload is not None and v.written is None:
                n = sum(w.written is not None for w in rx.volumes)
                v.written = OUT_NAME if not n else OUT_NAME.replace('.', '-%d.' % (n + 1))
                open(v.written, 'wb').write(v.payload)
                print('volume %d complete: %d bytes, SHA-256 %s, written to %s' % (
                    v.number, len(v.payload), sha256(v.payload).hex(), v.written))
                if v.payload[:4] == b'R3A1':     # an archive (section 10): decode, check, unpack
                    print('archive: decoding')
                    d = unz(v.payload)
                    if crc32(d) == int.from_bytes(v.payload[12:16], 'big'):
                        unpack(d)
                    else:
                        print('archive: CRC-32 wrong')
    for v in rx.volumes:
        if v.payload is None:
            print('volume %d not complete (scans %s): %s' % (v.number, ', '.join(v.scans), v.state()))
    for name, tiles in rx.loose:
        print('%s: its %d tiles never found their volume' % (name, len(tiles)))
    if not rx.volumes:
        print('no volume found')


if __name__ == '__main__':
    main()
