"""ZPAQ level-2 block ENCODER for zp_dec.py (harness side; may import).

- compile_cfg(text, args): a ZPAQL compiler, a port of libzpaq 7.15's
  Compiler (Compiler::Compiler, compile_comp, next, rtoken; libzpaq.cpp
  2449-2770): config text -> (COMP+HCOMP header bytes, PCOMP bytes).
- disassemble(header): bytes -> config text that recompiles to the same
  bytes (raw jumps).
- make_config(method, args): a port of libzpaq's makeConfig() (libzpaq.cpp
  6887-7517) for the context-model commands c i a w m t s and the
  preprocessing types 0 (none) and 3 (BWT); method_for_level(): the
  default-method expansion of compressBlock() (7543-7700) for levels 3-5.
- compress(data, row): the conforming block: 13-byte locator tag, 'zPQ',
  level 2, type 1, header, one segment (empty filename, the size as the
  comment, as compressBlock writes it), the coded stream, four zero bytes,
  254 (no SHA-1), 255 (end of block).  The coder is NOT a second copy: the
  decoder's generated Python source (zp_dec.zsrc) is rewritten in five
  marked places into an encoder (encoder_source), so the predictor the
  encoder runs is the decoder's, byte for byte.

Derived from libzpaq by Matt Mahoney (public domain, Unlicense)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zp_dec  # noqa: E402

TAG = bytes([0x37, 0x6b, 0x53, 0x74, 0xa0, 0x31, 0x83, 0xd3, 0x8c, 0xb2, 0x28, 0xb0, 0xd3])
COMPNAME = ["", "const", "cm", "icm", "match", "avg", "mix2", "mix", "isse", "sse"]
COMPSIZE = [0, 2, 3, 2, 3, 4, 6, 6, 3, 5]


def _opcodelist():
    X = ["a", "b", "c", "d", "*b", "*c", "*d"]
    L = [""] * 256
    L[0] = "error"
    for x in range(7):
        for o, nm in ((0, "<>a"), (1, "++"), (2, "--"), (3, "!"), (4, "=0")):
            if x or o:
                L[x * 8 + o] = X[x] + nm
    for x in range(4):
        L[x * 8 + 7] = X[x] + "=r"
    L[39], L[47], L[55], L[56], L[57], L[59], L[60], L[63] = "jt", "jf", "r=a", "halt", "out", "hash", "hashd", "jmp"
    for x in range(7):
        for y in range(8):
            L[64 + x * 8 + y] = X[x] + "=" + (X[y] if y < 7 else "")
    for k, op in enumerate(["+=", "-=", "*=", "/=", "%=", "&=", "&~", "|=", "^=", "<<=", ">>=", "==", "<", ">"]):
        for y in range(8):
            L[128 + k * 8 + y] = "a" + op + (X[y] if y < 7 else "")
    L[255] = "lj"
    return L + ["post", "pcomp", "end", "if", "ifnot", "else", "endif", "do", "while", "until", "forever",
                "ifl", "ifnotl", "elsel", ";"]


OPS = _opcodelist()
JT, JF, JMP, LJ = 39, 47, 63, 255
POST, PCOMP, END, IF, IFNOT, ELSE, ENDIF, DO, WHILE, UNTIL, FOREVER, IFL, IFNOTL, ELSEL = range(256, 270)


class _Tok:
    """libzpaq Compiler::next / matchToken / rtoken: a token is read where it
    starts and skipped by the next call (state -1 = inside a word)."""

    def __init__(self, text, args):
        self.t, self.i, self.st, self.args = text, 0, 0, args or [0] * 9

    def next(self):
        t = self.t
        while self.i < len(t):
            ch = t[self.i]
            if ch == "(":
                self.st += 1 + (self.st < 0)
            elif self.st > 0 and ch == ")":
                self.st -= 1
            elif self.st < 0 and ch <= " ":
                self.st = 0
            elif self.st == 0 and ch > " ":
                self.st = -1
                return
            self.i += 1
        raise SyntaxError("unexpected end of config")

    def word(self):
        j = self.i
        while j < len(self.t) and self.t[j] > " " and self.t[j] != "(":
            j += 1
        return self.t[self.i:j].lower()

    def rlist(self, lst):
        self.next()
        w = self.word()
        if w in lst:
            return lst.index(w)
        raise SyntaxError("unexpected token %r" % w)

    def rword(self, s):
        self.next()
        if self.word() != s:
            raise SyntaxError("expected %r, got %r" % (s, self.word()))

    def rnum(self, lo, hi):
        self.next()
        w, r = self.t[self.i:self.i + 40], 0

        def atoi(s):
            k = 1 if s[:1] in "+-" else 0
            while k < len(s) and s[k].isdigit():
                k += 1
            return int(s[:k]) if s[:k] not in ("", "+", "-") else 0
        if w[0] == "$" and "1" <= w[1] <= "9":
            if w[2] == "+":
                r = atoi(w[3:])
            r += self.args[int(w[1]) - 1]
        elif w[0] == "-" or w[0].isdigit():
            r = atoi(w)
        else:
            raise SyntaxError("expected a number at %r" % w[:20])
        if not lo <= r <= hi:
            raise SyntaxError("number %d out of range %d..%d" % (r, lo, hi))
        return r


def _compile_comp(tk):
    code, ifs, dos = [], [], []
    while True:
        op = tk.rlist(OPS)
        if op in (POST, PCOMP, END):
            break
        operand = operand2 = -1
        if op == IF:
            op, operand = JF, 0
            ifs.append(len(code) + 1)
        elif op == IFNOT:
            op, operand = JT, 0
            ifs.append(len(code) + 1)
        elif op in (IFL, IFNOTL):
            code += [JT if op == IFL else JF, 3]
            op, operand, operand2 = LJ, 0, 0
            ifs.append(len(code) + 1)
        elif op in (ELSE, ELSEL):
            if op == ELSE:
                op, operand = JMP, 0
            else:
                op, operand, operand2 = LJ, 0, 0
            a = ifs.pop()
            if code[a - 1] != LJ:
                j = len(code) - a + 1 + (op == LJ)
                if j > 127:
                    raise SyntaxError("IF too big, try IFL, IFNOTL")
                code[a] = j
            else:
                j = len(code) + 2 + (op == LJ)
                code[a], code[a + 1] = j & 255, (j >> 8) & 255
            ifs.append(len(code) + 1)
        elif op == ENDIF:
            a = ifs.pop()
            j = len(code) - a - 1
            if code[a - 1] != LJ:
                if j > 127:
                    raise SyntaxError("IF too big, try IFL, IFNOTL, ELSEL")
                code[a] = j
            else:
                j = len(code)
                code[a], code[a + 1] = j & 255, (j >> 8) & 255
        elif op == DO:
            dos.append(len(code))
        elif op in (WHILE, UNTIL, FOREVER):
            a = dos.pop()
            j = a - len(code) - 2
            if j >= -127:
                op = {WHILE: JT, UNTIL: JF, FOREVER: JMP}[op]
                operand = j & 255
            else:
                j = a
                if op == WHILE:
                    code += [JF, 3]
                if op == UNTIL:
                    code += [JT, 3]
                op, operand, operand2 = LJ, j & 255, j >> 8
        elif op & 7 == 7:
            if op == LJ:
                operand = tk.rnum(0, 65535)
                operand, operand2 = operand & 255, operand >> 8
            elif op in (JT, JF, JMP):
                operand = tk.rnum(-128, 127) & 255
            else:
                operand = tk.rnum(0, 255)
        if 0 <= op <= 255:
            code.append(op)
        if operand >= 0:
            code.append(operand)
        if operand2 >= 0:
            code.append(operand2)
    code.append(0)
    return code, op


def compile_cfg(text, args=None):
    """Config text -> (header bytes = hsize[2] hh hm ph pm n COMP 0 HCOMP 0, PCOMP bytes or b'')."""
    tk = _Tok(text, args)
    tk.rword("comp")
    hd = [tk.rnum(0, 255) for _ in range(5)]
    comp = []
    for i in range(hd[4]):
        tk.rnum(i, i)
        t = tk.rlist(COMPNAME)
        comp += [t] + [tk.rnum(0, 255) for _ in range(COMPSIZE[t] - 1)]
    comp.append(0)
    tk.rword("hcomp")
    code, op = _compile_comp(tk)
    hsize = 5 + len(comp) + len(code)
    header = bytes([hsize & 255, hsize >> 8] + hd + comp + code)
    pcomp = b""
    if op == POST:
        tk.rnum(0, 0)
        tk.rword("end")
    elif op == PCOMP:
        tk.next()
        while tk.i < len(tk.t) and tk.t[tk.i] != ";":
            tk.i += 1
        tk.i += 1
        pc, op = _compile_comp(tk)
        if op != END:
            raise SyntaxError("expected END")
        pcomp = bytes(pc)
    elif op != END:
        raise SyntaxError("expected END or POST 0 END or PCOMP cmd ; ... END")
    return header, pcomp


def _dis_code(code):
    out, i = [], 0
    while i < len(code) - 1:
        o = code[i]
        if o == 255:
            out.append("lj %d" % (code[i + 1] + 256 * code[i + 2]))
            i += 3
        elif o & 7 == 7:
            n = code[i + 1]
            out.append("%s %d" % (OPS[o], (n + 128 & 255) - 128 if o in (JT, JF, JMP) else n))
            i += 2
        else:
            out.append(OPS[o])
            i += 1
    return out


def disassemble(header, pcomp=b""):
    hd = header[2:7]
    lines = ["comp %d %d %d %d %d" % tuple(hd)]
    c = 7
    for i in range(hd[4]):
        t = header[c]
        lines.append("  %d %s %s" % (i, COMPNAME[t], " ".join(str(x) for x in header[c + 1:c + COMPSIZE[t]])))
        c += COMPSIZE[t]
    code = _dis_code(header[c + 1:])
    lines.append("hcomp")
    lines += ["  " + " ".join(code[k:k + 8]) for k in range(0, len(code), 8)]
    if pcomp:
        pc = _dis_code(pcomp)
        lines.append("pcomp ;")
        lines += ["  " + " ".join(pc[k:k + 8]) for k in range(0, len(pc), 8)]
    lines.append("end")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- makeConfig
def _lg(x):
    return x.bit_length()


def _nbits(x):
    return bin(x).count("1")


def _parse_method(method):
    """'x4,0ci1,1,1,1,2awm' -> args[9], [[cmd, N1, N2, ...], ...] (makeConfig's parser)."""
    m, args, k = method[1:], [0] * 9, 0
    i = 0
    while k < len(m) and i < 9 and (m[k].isdigit() or m[k] in ",."):
        if m[k].isdigit():
            args[i] = args[i] * 10 + int(m[k])
        else:
            i += 1
            if i < 9:
                args[i] = 0
        k += 1
    cmds = []
    while k < len(m):
        v = [m[k]]
        k += 1
        if k < len(m) and m[k].isdigit():
            v.append(int(m[k]))
            k += 1
            while k < len(m) and (m[k].isdigit() or m[k] in ",."):
                if m[k].isdigit():
                    v[-1] = v[-1] * 10 + int(m[k])
                else:
                    v.append(0)
                k += 1
        cmds.append(v)
    return args, cmds


IBWT = """pcomp bwtrle c ;
  a> 255 ifnot
    *b=a b++
  elsel
    b-- a=*b
    b-- a<<= 8 a+=*b
    b-- a<<= 8 a+=*b
    b-- a<<= 8 a+=*b c=a r=a 1
    a=b r=a 2
    do
      a=b a> 0 if
        b-- a=*b a++ a&= 255 d=a d! *d++
      forever
    endif
    d=0 d! *d= 1 a=0
    do
      a+=*d *d=a d--
    d<>a a! a> 255 a! d<>a until
    b=0 do
      a=c a>b if
        d=*b d! *d++ d=*d d-- *d=b
      b++ forever
    endif
    b=c b++ c=r 2 do
      a=c a>b if
        d=*b d! *d++ d=*d d-- *d=b
      b++ forever
    endif
"""
IBWT_FAST = """    b=0 do
      a=c a>b if
        d=b a=*d a<<= 8 a+=*b *d=a
      b++ forever
    endif
    d=r 1 b=0 do
      a=d a== 0 ifnot
        a=*d a>>= 8 d=a
 a=*d out
      forever
    endif
  endif
  halt
end
"""
IBWT_SLOW = """    d=r 1 do
      a=d a== 0 ifnot
        d=*d
        b=d a=*b out
      forever
    endif
  endif
  halt
end
"""


def make_config(method):
    """libzpaq makeConfig() for preprocessing 0 (none) or 3 (BWT), no E8E9.
    Returns (config text, args)."""
    args, cmds = _parse_method(method)
    level = args[1] & 3
    if args[1] >= 4 or level in (1, 2):
        raise NotImplementedError("LZ77 and E8E9 preprocessing are not ported")
    if level == 3:
        hdr, pcomp = "comp 9 16 $1+20 $1+20 ", IBWT + (IBWT_FAST if args[0] <= 4 else IBWT_SLOW)
    else:
        hdr, pcomp = "comp 9 16 0 0 ", "end\n"
    ncomp, membits, sb = 0, args[0] + 20, 5
    comp, hcomp = "", "hcomp\nc-- *c=a a+= 255 d=a *d=c\n"
    for v in cmds:
        if ncomp >= 254:
            break
        if v[0] == "c":
            while len(v) < 3:
                v.append(0)
            comp += "%d " % ncomp
            sb = 11 + (_lg(v[2]) if v[2] < 256 else 6)
            for i in range(3, len(v)):
                if v[i] < 512:
                    sb += _nbits(v[i]) * 3 // 4
            sb = min(sb, membits)
            if v[1] % 1000 == 0:
                comp += "icm %d\n" % (sb - 6 - v[1] // 1000)
            else:
                comp += "cm %d %d\n" % (sb - 2 - v[1] // 1000, v[1] % 1000 - 1)
            hcomp += "d= %d *d=0\n" % ncomp
            if 1 < v[2] <= 255:
                if _lg(v[2]) != _lg(v[2] - 1):
                    hcomp += "a=c a&= %d hashd\n" % (v[2] - 1)
                else:
                    hcomp += "a=c a%%= %d hashd\n" % v[2]
            elif 1000 <= v[2] <= 1255:
                hcomp += "a= 255 a+= %d d=a a=*d a-=c a> 255 if a= 255 endif d= %d hashd\n" % (v[2] - 1000, ncomp)
            for i in range(3, len(v)):
                if i == 3:
                    hcomp += "b=c "
                if v[i] == 255:
                    hcomp += "a=*b hashd\n"
                elif 0 < v[i] < 255:
                    hcomp += "a=*b a&= %d hashd\n" % v[i]
                elif 256 <= v[i] < 512:
                    hcomp += ("a=r 1 a> 1 if\n  a=r 2 a< 64 if\n    a=*b " + ("a&= %d" % (v[i] - 256) if v[i] < 511 else "")
                              + " hashd\n  else\n    a>>= 6 hashd a=r 1 hashd\n  endif\nelse\n  a= 255 hashd a=r 2 hashd\nendif\n")
                elif v[i] >= 1256:
                    hcomp += "a= %d a<<= 8 a+= %d a+=b b=a\n" % (((v[i] - 1000) >> 8) & 255, (v[i] - 1000) & 255)
                elif v[i] > 1000:
                    hcomp += "a= %d a+=b b=a\n" % (v[i] - 1000)
                if v[i] < 512 and i < len(v) - 1:
                    hcomp += "b++ "
            ncomp += 1
        if v[0] in "mts" and ncomp > (v[0] == "t"):
            if len(v) <= 1:
                v.append(8)
            if len(v) <= 2:
                v.append(24 + 8 * (v[0] == "s"))
            if v[0] == "s" and len(v) <= 3:
                v.append(255)
            comp += "%d" % ncomp
            sb = 5 + v[1] * 3 // 4
            if v[0] == "m":
                comp += " mix %d 0 %d %d 255\n" % (v[1], ncomp, v[2])
            elif v[0] == "t":
                comp += " mix2 %d %d %d %d 255\n" % (v[1], ncomp - 1, ncomp - 2, v[2])
            else:
                comp += " sse %d %d %d %d\n" % (v[1], ncomp - 1, v[2], v[3])
            if v[1] > 8:
                hcomp += "d= %d *d=0 b=c a=0\n" % ncomp
                while v[1] >= 16:
                    hcomp += "a<<= 8 a+=*b" + (" b++" if v[1] > 16 else "") + "\n"
                    v[1] -= 8
                if v[1] > 8:
                    hcomp += "a<<= 8 a+=*b a>>= %d\n" % (16 - v[1])
                hcomp += "a<<= 8 *d=a\n"
            ncomp += 1
        if v[0] == "i" and ncomp > 0:
            hcomp += "d= %d b=c a=*d d++\n" % (ncomp - 1)
            for i in range(1, len(v)):
                if ncomp >= 254:
                    break
                for j in range(v[i] % 10):
                    hcomp += "hash "
                    if i < len(v) - 1 or j < v[i] % 10 - 1:
                        hcomp += "b++ "
                    sb += 6
                hcomp += "*d=a" + (" d++" if i < len(v) - 1 else "") + "\n"
                sb = min(sb, membits)
                comp += "%d isse %d %d\n" % (ncomp, sb - 6 - v[i] // 10, ncomp - 1)
                ncomp += 1
        if v[0] == "a":
            if len(v) <= 1:
                v.append(24)
            while len(v) < 4:
                v.append(0)
            comp += "%d match %d %d\n" % (ncomp, membits - v[3] - 2, membits - v[2])
            hcomp += "d= %d a=*d a*= %d a+=*c a++ *d=a\n" % (ncomp, v[1])
            sb = 5 + (membits - v[2]) * 3 // 4
            ncomp += 1
        if v[0] == "w":
            for k, d in enumerate([1, 65, 26, 223, 20, 0]):
                if len(v) <= k + 1:
                    v.append(d)
            comp += "%d icm %d\n" % (ncomp, membits - 6 - v[6])
            for i in range(1, v[1]):
                comp += "%d isse %d %d\n" % (ncomp + i, membits - 6 - v[6], ncomp + i - 1)
            hcomp += "a=*c a&= %d a-= %d a&= 255 a< %d if\n" % (v[4], v[2], v[3])
            for i in range(v[1]):
                hcomp += ("  d= %d" % ncomp if i == 0 else "  d++") + " a=*d a*= %d a+=*c a++ *d=a\n" % v[5]
            hcomp += "else\n"
            for i in range(v[1] - 1, 0, -1):
                hcomp += "  d= %d a=*d d++ *d=a\n" % (ncomp + i - 1)
            hcomp += "  d= %d *d=0\nendif\n" % ncomp
            ncomp += v[1] - 1
            sb = membits - v[6]
            ncomp += 1
    return hdr + "%d\n" % ncomp + comp + hcomp + "halt\n" + pcomp, args


def method_for_level(level, data, arg0=None, text=True):
    """compressBlock()'s default-method expansion for levels 3-5 (text type,
    high redundancy assumed: the archiver's 'type' = redundancy*4 + text is
    not reproduced; type >= 640 and odd -> BWT at level 3, type < 900 ->
    the CM chain at level 4)."""
    n = len(data)
    a0 = max(_lg(n + 4095) - 20, 0) if arg0 is None else arg0
    m = "x%d" % a0
    if level == 3:
        return m + ",3ci1"
    if level == 4:
        return m + ",0ci1,1,1,1,2a" + ("w" if text else "") + "m"
    if level == 5:
        m += ",0" + ("w2c0,1010,255i1" if text else "w1i1") + "c256ci1,1,1,1,1,1,2a"
        NR = 1 << 12
        pt, r = [0] * 256, [0] * NR
        for i, ch in enumerate(data):
            k = i - pt[ch]
            if 0 < k < NR:
                r[k] += 1
            pt[ch] = i
        n1 = n - r[1] - r[2] - r[3]
        for _ in range(2):
            period, score, t = 0, 0.0, 0
            for j in range(5, NR):
                if t >= n1:
                    break
                s = r[j] / (256.0 + n1 - t)
                if s > score:
                    score, period = s, j
                t += r[j]
            if period > 4 and score > 0.1:
                m += "c0,0,%d,255i1" % (999 + period)
                if period <= 255:
                    m += "c0,%di1" % period
                n1 -= r[period]
                r[period] = 0
            else:
                break
        return m + "c0,2,0,255i1c0,3,0,0,255i1c0,4,0,0,0,255i1mm16ts19t0"
    raise ValueError(level)


# ------------------------------------------------------------- the encoder
DEC_INIT = "lo=1;hi=F;x=z[q]<<24|z[q+1]<<16|z[q+2]<<8|z[q+3];q+=4"
DEC_LOOP = " while 1:\n  if x<=lo:break\n"
DEC_NORM = "while hi^lo<16777216:hi=hi<<8&F|255;lo=lo<<8&F;lo+=lo==0;x=x<<8&F|z[q];q+=1"
DEC_BIT = "   if x<=m:y=1;hi=m\n   else:y=0;lo=m+1\n"
DEC_RET = " return O\n"
ENC_NORM = "while hi^lo<16777216:W.append(hi>>24);hi=hi<<8&F|255;lo=lo<<8&F;lo+=lo==0"


def encoder_source(src):
    """The decoder's generated source -> an encoder: D(data, 0) returns the
    coded bytes (flushed, without the four trailing zeros)."""
    for a, b, k in ((DEC_INIT, "lo=1;hi=F;W=bytearray()", 1), (DEC_LOOP, " for ch in z:\n", 1),
                    (DEC_NORM, ENC_NORM, 2), (DEC_BIT, "   y=ch>>7&1;ch=ch<<1&255\n   if y:hi=m\n   else:lo=m+1\n", 1),
                    (DEC_RET, " hi=lo\n " + ENC_NORM + "\n return W\n", 1)):
        assert src.count(a) == k, (a, src.count(a))
        src = src.replace(a, b)
    return src


def block_header(hdr, size):
    return TAG + b"zPQ" + bytes([1 + (hdr[6] == 0), 1]) + hdr + b"\x01\x00" + str(size).encode() + b"\x00\x00"


def bwt(data):
    """libzpaq LZBuffer::fill for level 3: the suffix-array BWT, EOS as 255
    at its position, the index appended LSB first."""
    import numpy as np
    n = len(data)
    if n == 0:
        return bytes([255]) + bytes(4)
    s = np.frombuffer(data, dtype=np.uint8).astype(np.int64)
    rank, k = s.copy(), 1
    while True:
        r2 = np.full(n, -1, dtype=np.int64)
        r2[:n - k] = rank[k:]
        sa = np.lexsort((r2, rank))
        key = rank[sa] * (n + 2) + (r2[sa] + 1)
        nr = np.empty(n, dtype=np.int64)
        nr[sa] = np.concatenate(([0], np.cumsum(key[1:] != key[:-1])))
        rank = nr
        if rank.max() == n - 1:
            break
        k *= 2
    out, idx = bytearray([data[-1]]), 0
    prev = np.where(sa > 0, s[sa - 1], 255).astype(np.uint8)
    idx = int(np.nonzero(sa == 0)[0][0]) + 1
    out += prev.tobytes()
    return bytes(out) + idx.to_bytes(4, "little")


def compress(data, row, arg0=None):
    """data -> one conforming ZPAQ block (tag + block) under ROWS[row]."""
    cfg, args = config_for(row, data, arg0)
    hdr, pcomp = compile_cfg(cfg, args)
    head = block_header(hdr, len(data))
    if pcomp:
        body = bwt(data) if (args[1] & 3) == 3 else data
        raw = bytes([1, len(pcomp) & 255, len(pcomp) >> 8]) + pcomp + body
    else:
        raw = b"\x00" + data
    src, g, q, ph, pm = zp_dec.zsrc(head + bytes(8))
    exec(encoder_source(src), g)
    coded = g["D"](raw, 0)
    return head + bytes(coded) + bytes(4) + b"\xfe\xff"


def config_for(row, data=b"", arg0=None):
    r = ROWS[row]
    if r.startswith("level"):
        return make_config(method_for_level(int(r[5]), data, arg0))
    if r.startswith("x"):
        if arg0 is not None:
            r = "x%d" % arg0 + r[r.index(","):]
        return make_config(r)
    return CFG[r], [0] * 9


from zp_configs import CFG, ROWS  # noqa: E402,F401
