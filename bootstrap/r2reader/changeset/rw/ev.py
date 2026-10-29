"""ev.py (changeset copy of compressor-exploration/encoder-side/ev.py, handle API
only) -- ideal cm2 bits of a text under a.py's d() model, C mirror (cm2h.c).
Default orders = stage 1's a.py (0,1,2,3,4,6,8); the shared library is built
into bootstrap/build/changeset/rw/ on first use."""
import ctypes
import os
import subprocess
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))   # bootstrap/
LIB = os.path.join(ROOT, 'build', 'changeset', 'rw', 'cm2h.so')
ORD = (0, 1, 2, 3, 4, 6, 8)


def _load():
    src = os.path.join(HERE, 'cm2h.c')
    if not os.path.exists(LIB) or os.path.getmtime(LIB) < os.path.getmtime(src):
        os.makedirs(os.path.dirname(LIB), exist_ok=True)
        subprocess.run(['cc', '-O2', '-shared', '-fPIC', '-o', LIB, src, '-lm'], check=True)
    h = ctypes.CDLL(LIB)
    h.cm2_new.restype = ctypes.c_void_p
    h.cm2_new.argtypes = [ctypes.c_long, ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    h.cm2_bits.restype = ctypes.c_double
    h.cm2_bits.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_char_p, ctypes.c_long]
    h.cm2_prefix.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long]
    h.cm2_try.restype = ctypes.c_double
    h.cm2_try.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long]
    return h


_h = _load()


class Handle:
    def __init__(s, maxbytes, orders=ORD):
        o = (ctypes.c_int * len(orders))(*orders)
        s.h = _h.cm2_new(maxbytes, o, len(orders))
        s.max = maxbytes

    def bits(s, data, primer):
        if isinstance(data, str):
            data = data.encode()
        if isinstance(primer, str):
            primer = primer.encode()
        assert len(data) + len(primer) <= s.max
        return _h.cm2_bits(s.h, primer, len(primer), data, len(data))

    def prefix(s, p):
        if isinstance(p, str):
            p = p.encode()
        assert len(p) <= s.max
        _h.cm2_prefix(s.h, p, len(p))

    def trybits(s, d):
        if isinstance(d, str):
            d = d.encode()
        return _h.cm2_try(s.h, d, len(d))


_tl = threading.local()


def bits(data, primer, maxbytes=12000):
    h = getattr(_tl, 'h', None)
    if h is None:
        h = _tl.h = Handle(maxbytes)
    return h.bits(data, primer)
