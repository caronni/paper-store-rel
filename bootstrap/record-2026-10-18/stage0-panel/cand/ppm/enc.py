"""Encoder for the stage-0 PPM decoders (mirror of their model).
Usage: python3 enc.py [--d32] IN OUT [PRIMER_FILES...]   (deterministic)
  default: stream for dec.py   (64-bit range coder, no rescale, 25 lines)
  --d32:   stream for dec32.py (32-bit range coder, halve past 60000, 27 lines)
P / P32 must match the constants typed in dec.py / dec32.py; the other
keys are design-exploration switches (see work/)."""
import sys
RB = 32

P = dict(K=6, NEW=2, INC=4, LIM=1 << 62, UPX=1, EXCL=1, E=1, ESC='dm', RB=64)
P32 = dict(P, LIM=60000, RB=32)


class RC:
    """32-bit range encoder, carry propagated into the output buffer."""
    def __init__(self):
        self.low, self.rng, self.out = 0, 1 << RB - 8, bytearray()

    def code(self, a, f, m):
        while self.rng < 1 << RB - 8:
            self.out.append(self.low >> RB - 8)
            self.low = (self.low << 8) & ((1 << RB) - 1)
            self.rng <<= 8
        w = self.rng // m
        self.low += a * w
        self.rng = f * w
        if self.low >> RB:
            self.low &= (1 << RB) - 1
            j = len(self.out) - 1
            while self.out[j] == 255:
                self.out[j] = 0
                j -= 1
            self.out[j] += 1

    def finish(self):
        b = bytes(self.out) + self.low.to_bytes(RB // 8, 'big')
        assert b[0] == 0  # decoder starts at g = 1 and reads RB/8 - 1 bytes
        return b[1:]


def encode(data, primer=b'', P=P, cost=None):
    global RB
    K, NEW, INC, LIM = P['K'], P['NEW'], P['INC'], P['LIM']
    RB = P.get('RB', 32)
    rc = RC()
    o = bytes(primer) + bytes(data)
    T = {b'': dict.fromkeys(range(256), P.get('O0', 1))}
    SEE = {}
    for i in range(len(o)):
        c = o[i]
        if i >= len(primer):
            k, e = K, {}
            while True:
                t = T.get(o[max(0, i - k):i], {})
                L = [z for z in t if z not in e] + [-1]
                if P['ESC'] in ('d', 'see'):
                    d = max(len(t), 1) * P['E'] * (k > 0)
                elif P['ESC'] == 'dm':
                    d = max(2 * len(t) - 1, 1) * (k > 0)
                elif P['ESC'] == 'single':
                    d = (1 + sum([1 for z in t if t[z] <= NEW])) * P['E'] * (k > 0)
                elif P['ESC'] == 'dk':
                    d = max(len(t), 1) * (P['E'] + (k > 2)) * (k > 0)
                m = sum([t.get(z, d) for z in L])
                if P['ESC'] == 'see':
                    ms = m - d
                    bk = P['BK'](k, t, ms)
                    S = SEE.setdefault(bk, list(P['S0']))
                    W = {z: t[z] * S[1] for z in L[:-1]}
                    W[-1] = S[0] * ms + (ms == 0)
                    m = sum(W.values())
                    t0, t = t, W
                a = 0
                hit = False
                for z in L:
                    f = t.get(z, d)
                    if z == c or z == -1:
                        hit = z == c
                        break
                    a += f
                rc.code(a, f, m)
                if cost is not None:
                    import math
                    key = (k, 'hit' if hit else 'esc', len(t) == 0)
                    cost[key] = cost.get(key, 0) - math.log2(f / m)
                if P['ESC'] == 'see':
                    t = t0
                    if ms:
                        S[hit] += P['SI']
                        if S[0] + S[1] > P['SL']:
                            S[0] = S[0] + 1 >> 1
                            S[1] = S[1] + 1 >> 1
                if hit:
                    break
                if P['EXCL']:
                    e.update(t)
                k -= 1
        for k in range(K, -1, -1):
            t = T.setdefault(o[max(0, i - k):i], {})
            t[c] = t.get(c, NEW - INC) + INC
            if sum(t.values()) > LIM:
                t.update({z: t[z] + 1 >> 1 for z in t})
            if P['UPX'] and t[c] > NEW:
                break
    return rc.finish()


if __name__ == '__main__':
    a = sys.argv[1:]
    p = P
    if a[0] == '--d32':
        a, p = a[1:], P32
    data = open(a[0], 'rb').read()
    pr = b''.join(open(f, 'rb').read() for f in a[2:])
    open(a[1], 'wb').write(encode(data, pr, p))
