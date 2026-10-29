"""Candidate D ("strong"): cm1 (stage1/cm1_dec.py, cmmix's model with bounded
CHECKED tables) plus three measured additions, each kept because it paid on
both samples (T2 and a 1 MB docs slice of T1; dexp2_template.py variants):
  - a word-bigram context (current word hash + the previous word's): -0.5 %
    on T2, -0.3 % on docs;
  - two APM/SSE stages after the mixer (33-bucket interpolation over the
    mixer's stretch, contexts: order 1 + partial byte, and a hashed order 3
    + partial byte), final p = (2 p + 3 apm1 + 3 apm2) / 8: -0.4 / -0.7 %;
  - the mixer's learning rate halved (S * err >> 11): -0.3 / -0.9 %.
  Together -1.0 % on T2, -1.6 % on docs.  Refused (measured worse): order 5/6
  contexts, a sparse context, slower counter rates, a faster mixer rate.
Contexts (nibble-hashed into 16-slot buckets with a 16-bit check, 2-way,
low-count eviction): orders 0-1 direct; orders 2, 3, 4, the word, the
line-above (byte above + column), the last 7 bytes, the word bigram; plus a
match model (last 6-byte hash -> position).  Three weight sets summed (by
partial byte + match flag, by order 1, by hashed order 2).  Coder: cmmix's
carry-less 32-bit binary arithmetic coder, 12-bit probability.
Memory: T 2^25 B + 0.5 MB, mt 16 MB, W 5.3 MB, two APMs 2 x 2.16 M list
slots (~35 MB) -- bounded, independent of n.  Container: 4-byte n + coder
bytes (encoder: enc_strong.py, derived from this text)."""
# BEGIN DECODER
def unz(z):
    n, s = int.from_bytes(z[:4], 'big'), z[4:] + bytes(8)
    F, Q, q, k = 4294967295, 18446744073709551615, 1460000, 24
    sq, st, K = [0] * 4096, [0] * 1024, 0x7fffffe87fffffe03ff000000000000
    for x in range(4096):
        sq[x] = q >> 20
        q += q * ((4096 << 20) - q) >> 40
        st[sq[x] >> 2] = x - 2048
    D, A, G, E = 1 << k, 68 - k, 0x9E3779B1, 0x9E3779B97F4A7C15
    T = memoryview(bytearray(b"\x80" * (2 * D + 263168))).cast("H")
    Z = memoryview(bytearray(b"\x80" * 30)).cast("H")
    mt = memoryview(bytearray(D)).cast("I")
    W = memoryview(bytearray(5263360)).cast("i")
    U, V, B = [32768] * 32, [0] * 32, [0] * 9
    R = [655360 // (j * 10 + 12) for j in range(31)]
    AP = [sq[min(4095, j % 33 * 128)] * 16 for j in range(33 * 65536)]
    AQ = AP[:]
    b = bytearray(8 + n)
    x1, x2, x, kk, h = 0, 0, 0, 0, 0
    wh, wp, mp, ml, pl, ls = 0, 0, 0, 0, 8, 8
    for i in range(8, len(b)):
        c, c0, h = b[i - 1], 1, (h << 8 | b[i - 1]) & 0xFFFFFFFFFFFFFF
        if K >> c & 1:
            wh = (wh + c + 1) * 773 & F
        elif wh:
            wp, wh = wh, 0
        pl, ls = (ls, i) if c == 10 else (pl, ls)
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
                            t = t ^ 16
                        else:
                            if T[t + 1] & 15 > T[t ^ 17] & 15:
                                t = t ^ 16
                            T[t], T[t + 1:t + 16] = cz, Z
                    B[q] = t
                cn = 1
            X = [t + cn for t in B]
            e = b[mp] >> 7 - j & 1
            mi = ml * 2 + e
            S = [st[T[t] >> 6] for t in X] + [st[U[mi] >> 6]]
            w, u = (c0 + 256 * (ml > 0)) * 10, (512 + c * 256 + c0) * 10
            v = (66048 + ((h & 65535) * G >> 24 & 255) * 256 + c0) * 10
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
    return bytes(b[8:])
# END DECODER
