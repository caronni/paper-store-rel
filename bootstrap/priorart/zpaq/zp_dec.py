"""A minimal pure-Python ZPAQ level-2 block decoder (no imports).

Reads ONE ZPAQ block with ONE segment (optional 13-byte locator tag, then
'zPQ' level 1|2, type 1, the COMP/HCOMP header, segment header, the
arithmetic-coded data, end of segment) and returns the decoded bytes.
Every component of the standard (CONST CM ICM MATCH AVG MIX2 MIX ISSE SSE)
is implemented, and so are the ZPAQL machine (HCOMP) and the post-processor
(PCOMP), following libzpaq 7.15's interpreted reference (Predictor::init,
predict0, update0, find; ZPAQL::execute; Decoder::decode/decompress;
PostProcessor::write; Decompresser).  Model tables are computed, not
stored: the bit-history state table from the generating rules of the older
libzpaq StateTable constructor, squash/stretch from their defining
formulas (each checked against libzpaq's stored tables, test_zp.py).

Speed: the block's model and its ZPAQL program are translated to Python
source and executed (a 'JIT to Python', like libzpaq's x86 JIT): one
straight-line function per block, every component unrolled with its
constants inlined; ZPAQL basic blocks become `if k==addr:` arms.  xrun() is the builtin exec
spelled so that python-minifier keeps renaming globals (measure_r2_zp.py).

Omitted (a declared subset): the journaling archive format (jDC blocks,
fragment tables, dedup) and anything beyond the first segment of the first
block; unmodeled (n = 0, stored) blocks; the SHA-1 in the segment trailer
is not checked (the R3A1 container carries a CRC-32); malformed input is
not diagnosed (a bad program may raise or loop).  Assumes a valid stream.

Derived from libzpaq by Matt Mahoney (public domain, Unlicense; see
README.md for the pointers).  `unz(z) -> bytes`; the region between the
markers is what an R3 monolith would carry."""
# BEGIN DECODER
def xrun(s, g):
    type(lambda: 0)(compile(s, '', 'exec'), g)()


def zpm(c, hb, mb):
    hm, mm, I, L, i = (1 << hb) - 1, (1 << mb) - 1, [], {0}, 0
    X = ('a', 'b', 'c', 'd', 'M[b&%d]' % mm, 'M[c&%d]' % mm, 'H[d&%d]' % hm)
    while i < len(c):
        o = c[i]
        n = 3 if o == 255 else 1 + (o & 7 == 7)
        t = -1
        if o in (39, 47, 63):
            t = i + 2 + (c[i + 1] + 128 & 255) - 128
        if o == 255:
            t = c[i + 1] + 256 * c[i + 2]
        I.append((i, o, c[i + 1] if n > 1 else 0, t))
        i += n
        if t >= 0 or o == 56:
            L |= {t, i}
    s = ['def R(a,S=S,M=M,H=H,Q=Q,O=O,F=4294967295):', ' b,c,d,f=S;k=0', ' while 1:']
    for i, o, N, t in I:
        if i in L:
            s.append('  if k==%d:' % i)
        x, y, j = o >> 3, o & 7, i + 1 + (o & 7 == 7) + (o == 255)
        if o in (39, 47, 63, 255):
            f = ('k=%d' if t > i else 'k=%d;continue') % t
            e = '' if o > 50 else 'f' if o == 39 else 'not f'
            u = f if not e else ('k=%d if %s else %d' % (t, e, j) if t > i else 'if %s:%s\n   k=%d' % (e, f, j))
        elif o == 56:
            u = 'S[:]=b,c,d,f;return'
        elif o == 57:
            u = 'O.append(a&255)'
        elif o == 59:
            u = 'a=(a+%s+512)*773&F' % X[4]
        elif o == 60:
            u = '%s=(%s+a+512)*773&F' % (X[6], X[6])
        elif o < 56 and 0 < y < 5 or o < 56 and y == 0 < x:
            v, w = X[x], '255' if 3 < x < 6 else 'F'
            u = ('a,V=V,a', 'V=V+1&W', 'V=V-1&W', 'V^=W', 'V=0')[y].replace('V', v).replace('W', w)
            if y == 0 and 3 < x < 6:
                u = 'a,V=a&~255|V,a&255'.replace('V', v)
        elif o < 56 and y == 7:
            u = 'Q[%d]=a' % N if x == 6 else '%s=Q[%d]' % (X[x], N)
        elif 63 < o < 120:
            u = '%s=%s' % (X[x - 8], X[y] if y < 7 else N) + '&255' * (11 < x < 14)
        elif 127 < o < 240:
            u = ('a=a+Y&F', 'a=a-Y&F', 'a=a*Y&F', 'a=a//Y if Y else 0', 'a=a%Y if Y else 0', 'a&=Y',
                 'a&=~Y', 'a|=Y', 'a^=Y', 'a=a<<(Y&31)&F', 'a>>=Y&31', 'f=a==Y', 'f=a<Y', 'f=a>Y')[x - 16]
            u = u.replace('Y', X[y] if y < 7 else str(N))
        else:
            u = '0/0'
        s.append('   ' + u)
        if j in L and not (o in (39, 47, 63, 255, 56)):
            s.append('   k=%d' % j)
    g = {'S': [0] * 4, 'M': bytearray(1 << mb), 'H': ar('I', [0], 1 << hb), 'Q': [0] * 256, 'O': bytearray()}
    xrun('\n'.join(s), g)
    return g


def ar(t, v, n):
    e = memoryview(bytearray(8 * len(v))).cast(t)
    for j, x in enumerate(v):
        e[j] = x
    return memoryview(bytearray(e.tobytes()[:e.itemsize * len(v)] * n)).cast(t)


def zfind(T, b, x):
    c, h = x >> b & 255, x * 16 & len(T) - 16
    for r in (h, h ^ 16, h ^ 32):
        if T[r] == c:
            return r
    r = h if T[h + 1] <= T[h ^ 17] and T[h + 1] <= T[h ^ 33] else h ^ 16 if T[h ^ 17] < T[h ^ 33] else h ^ 32
    T[r:r + 16] = bytes(16)
    T[r] = c
    return r


def zsrc(z):
    p = z.find(b'zPQ') + 5
    hh, hm, ph, pm, n = z[p + 2:p + 7]
    e = p + 2 + z[p] + 256 * z[p + 1]
    E = 2.718281828459045
    SQ = [int(32768 / (1 + E ** (-i / 64))) for i in range(-2048, 2048)]
    SQ = SQ[2048:] + SQ[:2048]
    ST, x = [0] * 32768, 16384
    for i in range(712):
        v = E ** ((i + .5) / 64)
        while x < 32768 and x < (32767.5 * v - .5) / (1 + v):
            ST[x], ST[32767 - x], x = i, -i, x + 1
    B, T, NS, k = (20, 48, 15, 8, 6, 5), {}, [0] * 1024, 0

    def ns(a, b):
        a, b = max(a, b), min(a, b)
        return 0 if b > 5 or a > B[b] else 1 + (b > 0 and a + b < 18)

    def nx(a, b, y):
        if a < b:
            b, a = nx(b, a, 1 - y)
            return a, b
        if y:
            a, b = sum(a >= q for q in (1, 2, 3, 4, 5, 7, 8)), b + 1
        else:
            a, b = a + 1, sum(b >= q for q in (1, 2, 3, 4, 5, 7, 8))
        while not ns(a, b):
            a, b = (a - 1, b) if b < 2 else ((a * (b - 1) + b // 2) // b, b - 1)
        return a, b
    for i in range(50):
        for b in range(i + 1):
            if ns(i - b, b):
                T[i - b, b], k = (k, k + ns(i - b, b) - 1), k + ns(i - b, b)
    for (a, b), t in T.items():
        for y in range(ns(a, b)):
            NS[t[y] * 4:t[y] * 4 + 4] = T[nx(a, b, 0)][0], T[nx(a, b, 1)][1], a, b
    CI = [((NS[4 * k + 3] * 2 + 1) << 22) // (NS[4 * k + 2] + NS[4 * k + 3] + 1) for k in range(256)]
    g = {'SQ': SQ, 'ST': ST, 'DT': [(1 << 17) // (i * 2 + 3) * 2 for i in range(1024)],
         'D2': [i and 2048 // i for i in range(256)], 'NS': NS, 'zfind': zfind}
    P, U, C, q = [], [], p + 7, z.index(0, z.index(0, e + 1) + 1) + 2
    for i in range(n):
        t, a = z[C], z[C + 1:C + 6]
        C += (0, 2, 3, 2, 3, 4, 6, 6, 3, 5)[t]
        K, s, r = (1 << a[0]) - 1, '', ''
        if t == 1:
            r = 'p@=%d' % ((a[0] - 128) * 4)
        if t in (2, 9):
            s = 'v=C@[x@];n=v&1023;C@[x@]=v+((y*32767-(v>>17))*DT[n]&-1024)+(n<%d)&F' % (a[(t > 2) * 2 + 1] * 4)
            g['C%d' % i] = ar('I', [SQ[j * 64 - 992] << 17 | a[2] for j in range(32)], 1 << a[0]) if t > 2 else ar('I', [1 << 31], 1 << a[0])
        if t == 2:
            r = 'x@=(h@^hm)&%d;p@=ST[C@[x@]>>17]' % K
        if t in (3, 8):
            g['T%d' % i] = bytearray(64 << a[0])
            r = 'if f:r@=zfind(T@,%d,h@+16*c8&F)\nx@=T@[r@+k];' % (a[0] + 2)
            s = 'T@[r@+k]=NS[x@*4+y]'
        if t == 3:
            g['P%d' % i] = CI[:]
            r += 'p@=ST[P@[x@]>>8]'
            s += ';P@[x@]+=y*32767-(P@[x@]>>8)>>2'
        if t == 4:
            g['I%d' % i], g['B%d' % i] = ar('I', [0], 1 << a[0]), bytearray(1 << a[1])
            g['B%d' % i][0], N = 1, (1 << a[1]) - 1
            r = 'if l@:b@=B@[j@-o@&%d]>>7-u@&1;p@=ST[D2[l@]*(1-2*b@)&32767]\nelse:p@=0' % N
            s = ('if b@!=y:l@=0\nB@[j@]=B@[j@]*2+y&255\nu@+=1\nif u@>7:\n u@=0;j@=j@+1&N\n if l@:l@+=l@<255\n'
                 ' else:\n  o@=j@-I@[h@&K]\n  if o@&N:\n   while l@<255 and B@[j@-l@-1&N]==B@[j@-l@-o@-1&N]:l@+=1\n'
                 ' I@[h@&K]=j@').replace('N', str(N)).replace('K', str(K))
        if t == 5:
            r = 'p@=p%d*%d+p%d*%d>>8' % (a[0], a[2], a[1], 256 - a[2])
        if t == 6:
            g['W%d' % i] = ar('H', [32768], 1 << a[0])
            r = 'x@=h@+(c8&%d)&%d;w=W@[x@];p@=w*p%d+(65536-w)*p%d>>16' % (a[4], K, a[1], a[2])
            s = ('e=(y*32767-SQ[p@])*%d>>5;w=W@[x@]+(e*(p%d-p%d)+4096>>13);'
                 'W@[x@]=0 if w<0 else 65535 if w>65535 else w' % (a[3], a[1], a[2]))
        if t == 7:
            g['W%d' % i] = ar('i', [65536 // a[2]], a[2] << a[0])
            r = 'x@=(h@+(c8&%d)&%d)*%d;t=(%s)>>8;p@=-2048 if t<-2048 else 2047 if t>2047 else t' % (
                a[4], K, a[2], '+'.join('(W@[x@+%d]>>8)*p%d' % (j, a[1] + j) for j in range(a[2])))
            s = 'e=(y*32767-SQ[p@])*%d>>4' % a[3] + ''.join(
                ';v=W@[x@+%d]+(e*p%d+4096>>13);W@[x@+%d]=-524288 if v<-524288 else 524287 if v>524287 else v'
                % (j, a[1] + j, j) for j in range(a[2]))
        if t == 8:
            g['W%d' % i] = [max(-524288, min(524287, ST[CI[j // 2] >> 8] * 1024)) if j & 1 else 32768 for j in range(512)]
            r += 't=W@[2*x@]*p%d+W@[2*x@+1]*64>>16;p@=-2048 if t<-2048 else 2047 if t>2047 else t' % a[1]
            s = ('e=y*32767-SQ[p@];v=W@[2*x@]+(e*p%d+4096>>13);W@[2*x@]=-524288 if v<-524288 else 524287 if v>524287'
                 ' else v;v=W@[2*x@+1]+(e+16>>5);W@[2*x@+1]=-524288 if v<-524288 else 524287 if v>524287 else v;' % a[1]) + s
        if t == 9:
            r = ('v=p%d+992;v=0 if v<0 else 1983 if v>1983 else v;w=v&63;x@=(h@+c8)*32+(v>>6)&%d;'
                 'p@=ST[(C@[x@]>>10)*(64-w)+(C@[x@+1]>>10)*w>>13];x@+=w>>5' % (a[1], (32 << a[0]) - 1))
        P.append(r.replace('@', str(i)))
        U.append(s.replace('@', str(i)))
    g.update(zpm(z[C + 1:e], hh, hm))
    V = [v for v in g if v[0] in 'CTPIBW' and v[1:].isdigit()] + ['R', 'H', 'SQ', 'ST', 'DT', 'D2', 'NS', 'zfind']
    o = ('def D(z,q,%s):\n F=4294967295\n lo=1;hi=F;x=z[q]<<24|z[q+1]<<16|z[q+2]<<8|z[q+3];q+=4\n'
         ' O=bytearray();c8=1;hm=1\n %s=0\n while 1:\n  if x<=lo:break\n  lo+=1\n  NORM\n  while c8<256:\n   k=hm&15;f=c8==1 or c8&240==16\n'
         '%s\n   m=lo+((hi-lo)*(SQ[p%d]*2+1)>>16)\n   if x<=m:y=1;hi=m\n   else:y=0;lo=m+1\n   NORM\n%s\n'
         '   c8+=c8+y\n   if 15<c8<32:hm=(hm&15)<<5|y<<4|1\n   else:hm=hm&496|(hm&15)*2+y&15\n'
         '  c8-=256;O.append(c8);R(c8)\n  %s\n  c8=1;hm=1\n return O\n') % (
        ','.join(v + '=' + v for v in V), '='.join(v + str(i) for i in range(n) for v in 'hxrplobuj'),
        '\n'.join('   ' + l for v in P for l in v.split('\n')), n - 1,
        '\n'.join('   ' + l for v in U if v for l in v.split('\n')), ';'.join('h%d=H[%d]' % (i, i & (1 << hh) - 1) for i in range(n)))
    return o.replace('NORM', 'while hi^lo<16777216:hi=hi<<8&F|255;lo=lo<<8&F;lo+=lo==0;x=x<<8&F|z[q];q+=1'), g, q, ph, pm


def unz(z):
    s, g, q, ph, pm = zsrc(z + bytes(8))
    xrun(s, g)
    r = g['D'](z + bytes(8), q)
    if not r[0]:
        return bytes(r[1:])
    n = r[1] + 256 * r[2]
    m = zpm(r[3:3 + n], ph, pm)
    for c in r[3 + n:]:
        m['R'](c)
    m['R'](4294967295)
    return bytes(m['O'])
# END DECODER
