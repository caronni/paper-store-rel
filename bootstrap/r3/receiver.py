"""R3 receiver: the archive's black-only pages, read from flatbed scans.

This is the R2 pages' b.py: one Python file, no imports, run with
`python3 b.py` on a bare interpreter.  It reads printed pages of the holo
archive format (src/holo; docs/HOLO-DESIGN.md, docs/PRINTED-FORMAT.md) for
ONE row only, the most robust black-only row:

    K family (black toner only), cells of CELL_DOTS x CELL_DOTS printer dots
    at 600 dpi (c3; c4 = set CELL_DOTS = 4), LDPC rung r0550, 100 address
    sites per tile (p100), A4 paper with 6 mm margins.  The fountain's
    source fraction (0.5 for the "resilient" profile) is not printed and
    not needed: the volume says its own size on every tile.

Use: it asks for scans, one per line, as `FILE [DPI]`: FILE a greyscale
PGM (P5, 8 or 16 bit) of ONE whole page laid on a flatbed, any quarter
turn, tilted by up to about 10 degrees; DPI the scan resolution (default
1200; 1200 and 2400 are the tested ones).  An empty line ends.  Pages may
come in any order, any number of them, the same page twice is harmless.
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
  2. the scan: the cell lattice (pitch is known, only its angle, phase and
     the scanner's scale are measured), the first tile found by its address
     word, every other tile predicted from its neighbours and checked
     against the address word it must carry (section 7);
  3. per tile: cell brightness -> soft bits calibrated on the tile's own
     address sites, descrambled, put in code order, LDPC-decoded and
     certified by CRC-32 (sections 7 and 9);
  4. the volume: K from the metadata bit every tile carries, the fountain's
     equations reduced over GF(2) as each tile arrives, solved the moment
     their rank reaches K, the envelope checked by SHA-256 (section 8);
  the reader (section 9) drives them scan by scan.
It runs a c3 page in about 40 s on an Apple M1 Max (CPython 3.14), three
quarters of it the payload scramble (one AES block per cell).
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
# is the public test row c3-k-r0550@35x24 (c4: 1i150 ... @26x18).
FORMAT_ID = 'holo/v2/1i%d-k-r0550-p100-v1@%dx%d' % (
    ENGINE_DPI // CELL_DOTS, TILES_Y, TILES_X)
SITES_ID = 'holo/v1/sites/p100'       # the site pattern's own seed
TILES_PER_PAGE = TILES_Y * TILES_X
MAX_PAGES = (1 << 18) // TILES_PER_PAGE   # the tile counter has 18 bits
N_SITES = 100                 # address-word cells per tile
N_CODE, K_INFO = 4096, 2240   # LDPC r0550: n, k (Z = 64)
N_CHECKS = N_CODE - K_INFO    # 1856 parity checks
USER_BITS = K_INFO - 32 - N_SITES  # 2108 = metadata bit + symbol
SYMBOL_BITS = USER_BITS - 1        # 2107 fountain symbol bits per tile
SHORT = (USER_BITS + 32, K_INFO)   # info bits 2140..2239: shortened, zero
SLOTS = N_CODE - N_SITES           # 3996 printed code bits per tile
LDPC_ITERS, LDPC_ALPHA = 50, 0.75  # layered normalised min-sum
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


# ================================================= 6. LDPC r0550 and CRC
# The e-IRA quasi-cyclic mother code (src/holo/core/ldpc/data/r0550.json),
# packed as ONE integer in mixed radix, least significant first: the
# interleaver pi (1856 entries) as its Lehmer code (digit i in radix
# 1856 - i picks from the entries left), then per info column block
# (10 heavy of degree 10, then 25 light of degree 3) its block rows
# (radix 29) and its circulant shifts (radix 64).
LDPC_TABLE = int(
    # LDPC-TABLE-BEGIN
    '2150898b671630317eaa5161f85f0174eeb56819a8155067dee11d5b0373f07699951294430c'
    'b08d2054e5a639bc880e7a3f4a197bfd1d6b2efe6b70020831185390bda4a5184aaf22f47016'
    'd2cad4ded00f97387b1335b05eefafe8931598703e8cb2a5c9d3bab317ee81b8f7d615f44534'
    '0f3394f3b56bfa147f3e949911418e9c407a6a7e2c3ee098899dd85b4aba873551ae13d1a392'
    '938da3a152c4b3eec8ea496455f26723213ae4612554535a167140402a5267cc5ec5dce0d585'
    'fc9b84da68ebdd5fa7a0a401eb1d9dba4447cfecc9de3bd744029dcebbc0ca78b0426371ff92'
    '8675b89413c35939773d8afd34fdcb85d1c573f04b5312f46ae7f5423e86fec13ddda43e4ade'
    '2f0b063e92d582d23ca74053b4b8264d1c7466d4769cd9dafbadd098caabfbe04a55fbffbdf7'
    'b87d1fa5fd1c13cdaaec16e73ac93263dbf0a7f3798786054afb04bc3c5927170113091ca922'
    '6d5eb1047132c4e38a423a115b0f28b086288439729e1c12c46f9034ff3fbd2b1c0560c71287'
    '2e7207af1c3caa5a39ffc540a4fa7a2a388c5827f82706f3368d53d24bf803d9451d8bb85794'
    '7965ff9d199d1793eb1d348c0f9126949a25661a1368310c73e65868ed7dea4f17ad2f71d3e5'
    'b274ee9df1a8098d55b7977468fe9c9aaec9a8f9bd20f8f4396c135866394eee34ac9c8e0444'
    '0acce230e831200e5886abe3387894b1ec40e6f70f70c5cc4b452088eb02c0fcaa1c6950be80'
    '2b20820c838fec71f0ac457ba1248cf9c28c5d2026cace9477fbedf1f8dc8b50a2b7a8bfcfe8'
    'bfc431bfbec50fe4418e9d9abe32c2e2b019403c5020dae9968bd5d5af92b6b35443f60f321a'
    '1138728d550f787469fdcc7dd14dc0984967b629852713ae95e57ebee2c16ed6467356619b82'
    'a9c88681092a5e304a9e43591123e721890be2352553da00e6faea7fe304c1d6a169d5d9a150'
    'be29046b12220757001c21f49ae3642a8a48f2e889f4a8eb4e7ae91ee65335166e187b43d3f1'
    '0bad65329983e0c32fe448053db1670c137f873ea3aa0bacc36bf1db7ed5bb292e259960de79'
    '8b368872df2183717b4c0ce5c3007e381c551898f50691781556c0ef9facd045dacb6d62eaed'
    '65e6bb7ffd3176b99cec9997ab71feaf80d2c79cc70b85de670ba7b1ff7d5ccaa0541efbc98c'
    '3577b28b3553a93bed1e64b90d2a2b297aaf5409b1e0dac7590e2f1eadcf1fbeae75102abdfc'
    'e4b90f324ccebb9aacb8b67101651b7fef43e6d995c31fe6895f01859391f9904276735f55cb'
    '353aca972f080744c3546d2ee772e7610be000a199f7d6c7db497cc8dc558303381e26552dc3'
    '052b2b0a1ed4df29db4b4a5983a58f58a79003183c5b7d71341d0c9d7addff1dc94e5520a000'
    'b23a31a14ee777a0b2b8b53fdd95c3914cba7e42d74aa699018e324e5e5a74258b3821de5e28'
    '01a149fd18814b929924a492568902a8fe4fa7f7c6106f3c9cba1ebd8e3eb2a59bc07e13952f'
    '86d05f1717a73e8ed378b8eb08e432f33d405307c21334a5114b185a3840df80de3ce77f5b91'
    'c08865d3816b3bc0cfcfaf652c4f99f89f3d79e567f30ed1494fc7091d962977d980fae6bcd9'
    '4072431d2633ccb2bbaed2dece0b68d4227667aefd9db05c64f2c084e80bb15736cb9585610c'
    '597a5564ae2f79d7ad2cc63f0eacb8ed0733d8d30fd78020cfe1a2a4377e5fb01332b1c4eb4c'
    '139d156cf1bcde2aad959e652f99297c1eea9cf9ed302e9dfb50dff26bee06a2c60b6ac46b2a'
    'd817afcc5a26cc43e2e3bb329ebb3cd24086a3111bdff2d578d3576808c9d4c15a456d13db13'
    '169ee19bf0a1c588ba19df23f7f8beb98d8fd17b6b6c1f3925b96445e3991a47abaf1e83eb39'
    'cd0f6bc353dd0e67ed3aa7d699696e8ca9d2909686081ec33d919c24e855e35d290b4fea229e'
    'e6cb4006384395ada359a3654fb00113d6de1f02b4dd445b44986a8ea5c7b07285ab4c11354e'
    '4f3ccc21a35159357b86997b8dd46d6c59f4f11ec93e561080c24d08f7fe859ed7d8ea3dfdce'
    'f96c104f1a4659a6a7d0ab8d15b492c26f23a4918d30debec2a54eeb002468c53755fb187a7d'
    '76614bb371cd586d18ccf045f2bd36b0b46d2f931b56e169a72f5993df5328fd4573f0dbe5a3'
    'd314ef0155aaba0808d5f43e08e2f2468100060a12c84daa79092de294fc835ed78f7b95921c'
    'e8ef62176b152fd7cc9eeebf5523c58afc44cf3c26b3b668e18ae3d57ad8331991369762e337'
    'faaad27e09f38a6bc1fde4fb7f8a1ed65effd23155fc0ba3aecf7efc5ee5ef096a772c57ae22'
    '0b9900ad987fbfe87437b7091fa0937f252e65da47338f315d9d3fde5924d61a2083a80cee17'
    '103d17586e5a028fbe382c485a8bd07b0608a8803a4c4c8365fa86963bc0891e3179169022e5'
    'cc50f4d1d7cba1ddb7a9640e9ee2bdbfe45464dcdec98160a4e98f6c3b8e9e13745cf58bcecc'
    'c8e282add2b226e9ac19baa50f434c4db5fac1839d82f660c92680d743990885b5fe2eacd978'
    '02840a1d0112c1b01afbfbe796132c7afa6ad4246932794c4148714015a2be7e719571c214c6'
    'e014ad703a78ce14ece3d42f5a69f9bb89da396191f53b2169845628ec0f19f3d451c87b0dc2'
    'c45a0ac5f7f7c57fcc360fb23e83e1193818199459dfbfcd44be0f017a834776dac8180964ba'
    '954bb6d8b3a2f54ea9e01112a2583dad46f6d1c4407884de5f979ff34ef1e4ab14457a8bc249'
    'c720a09b958f1a54347b68b8f0175a16571671be8769fb0e2842353290298ef7035812eebdbd'
    '47a5fae2027ff620d89aa3b3ae3abc4b0b470493927c0370682571737fcddfd3b0a4facdc26a'
    'ad3b63236d2a6f1936aa40458f5a59b7f8784188be5a77c0faddd64748c28d75e1d72a2a7564'
    'd42d2c593040f09041441f0b74a5a3baa52340652edcc2aa89054d2051576daba3be39cac12f'
    'ddfa46ab09b0123df60d9810b542ba189910a85abcf61eaaba9818fc5361edbdc6ad860f3ab2'
    '97db897619e0d4783b63cf060a3b4714769864b249037ce65c041d570ad7eb7021e2f32395ea'
    'd5e4b1c17fa836dcecb77584335a2d74e87807257dd6239e3dc62629830b207b0e3d6448c978'
    '9c98ba284241556e8dfb88fbec760a3794a4e9fc16cb71efd592764714af435298c32686a7c8'
    'cca08017af4298a8178406c00f59618437fec5241716397e6344d62f5493bd8a64eac8dd80fc'
    'bb11fae1568a3211298d69da11000b6f43c1552d0d9fe9ef63eb6ae37fc1ba7ed6b1f042eee5'
    'e327996409d4817f00371a03a00b54e92f9980453dbc61acae26d527aaa9fab86980f683854d'
    'f3c84dc4a6de3c86f6f99107f40cba952280d7597477092b46b38a72d33947a91f052e6d8286'
    '78e096a03cfb7c6793a2b37b821cf0889ab00afef2a8ddd8249d2006eb'
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
    equals bits 2108..2139.  A syndrome alone is never enough (r0550 has
    low-weight codewords)."""
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
        self.ap = max(2, round(0.7 * self.pitch))           # box aperture, pixels
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
        """Coarse angle by search at a point of the page, then the lattice
        tracked outward on rings of doubling radius (8 directions, each with
        sideways fallbacks where a tile is blank), refitted at every ring.
        A measurement that lands near half a cell from its prediction could
        be the neighbouring cell and is not used; points off the fit by more
        than 0.3 cell are dropped at the end.  The result must rest on at
        least 12 points and be square: both steps within 6 % of the declared
        pitch, 2 degrees of a right angle; else the next start point."""
        p = self.pitch
        for fy, fx in ((0.5, 0.5), (0.35, 0.5), (0.65, 0.5), (0.5, 0.3), (0.5, 0.7),
                       (0.3, 0.3), (0.7, 0.7), (0.3, 0.7), (0.7, 0.3)):
            cy, cx = self.H * fy, self.W * fx
            best = None
            for t in range(-20, 21):              # -10 .. 10 degrees, 0.5 apart
                c, s = cos_sin(t * 0.5)
                lat = (cy, cx, p * c, -p * s, p * s, p * c)
                r = self.phase(lat, 0, 0, 24, 3)
                if r and (best is None or r[0] > best[0][0]):
                    best = (r, lat)
            if not best or best[0][3] < 2.0:
                continue
            (_, di, dj, _), (oy, ox, ay, ax, by, bx) = best
            pts = [(0, 0, oy + di * ay + dj * by, ox + di * ax + dj * bx)]
            lat = (pts[0][2], pts[0][3], ay, ax, by, bx)
            D, misses = 8, 0
            while D < 4000 and misses < 2:            # two empty rings end the walk
                n = len(pts)
                for ui, uj in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    for side in (0, 0.25, -0.25, 0.5, -0.5):
                        i, j = round(D * (ui - uj * side)), round(D * (uj + ui * side))
                        r = self.phase(lat, i, j, 8, 1)
                        if r and r[3] > 2.0 and abs(r[1]) < 0.35 and abs(r[2]) < 0.35:
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
        """Place and decode one scan; returns its progress line."""
        sc = Scan(name, dpi)
        lat = sc.find_lattice()
        if lat is None:
            return '%s: no cell lattice found (dpi %d right? one page, whole?)' % (name, dpi)
        placed = self.place_page(sc, lat)
        if placed is None:
            return ('%s: no tile address found (wrong FORMAT_ID, a mirror-image '
                    'scan, or not this row?)' % name)
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
        word = printed_word(counter)
        llr = sc.tile_llrs(lat, tile, d, word)
        scr = payload_scramble(self.page, TILE * tile[0], TILE * tile[1])
        a, b = slot_params(counter)
        L = [0.0] * N_CODE
        for j in range(SLOTS):                      # printed bit j -> code position
            cell = NONSITE[(a * j + b) % SLOTS]
            x = llr[cell]
            L[j if j < SHORT[0] else j + SHORT[1] - SHORT[0]] = -x if scr[cell] else x
        L = ldpc_decode(L)
        return L and certify(L)


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
    for v in rx.volumes:
        if v.payload is None:
            print('volume %d not complete (scans %s): %s' % (v.number, ', '.join(v.scans), v.state()))
    for name, tiles in rx.loose:
        print('%s: its %d tiles never found their volume' % (name, len(tiles)))
    if not rx.volumes:
        print('no volume found')


if __name__ == '__main__':
    main()
