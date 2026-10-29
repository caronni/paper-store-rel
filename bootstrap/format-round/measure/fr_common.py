"""fr_common.py -- shared paths and helpers of the format round's measurement
(2026-10-22, the measurer; never typed).

The eight configurations: kind in record/v3/v1/v2 x rings coarse/dot.  The
record kind is read by the ruled text (r2reader/reader_lite_v1.py), each
variant by its searched text (format-round/reader/reader_KIND_rw.py).
Outputs: bootstrap/build/format-round/.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.dirname(HERE)                         # bootstrap/format-round
BOOT = os.path.dirname(FR)                         # bootstrap/
PY = 'env/bin/python'
OUT = os.path.join(BOOT, 'build', 'format-round')
SETS_OUT = os.path.join(OUT, 'sets')
GEN = os.path.join(FR, 'gen', 'gen_variant.py')
VERIFY = os.path.join(FR, 'gen', 'verify_variant.py')
KINDS = ('record', 'v3', 'v1', 'v2')
RINGS = ('coarse', 'dot')
CONFIGS = [f'{k}-{r}' for k in KINDS for r in RINGS]
READER = {
    'record': os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py'),
    'v3': os.path.join(FR, 'reader', 'reader_v3_rw.py'),
    'v1': os.path.join(FR, 'reader', 'reader_v1_rw.py'),
    'v2': os.path.join(FR, 'reader', 'reader_v2_rw.py'),
}
# the slot pass's / probes' names for the reader's globals, per text
# (ruled: build/changeset/rw/names.json 'names'; variants: their search.json
# applied to the ruled spelling: cb->o, ft->cb, a->i, i->y, o->a)
NAMES = {
    'record': dict(rb='be', ld='cb', fm='ld', wk='v', h='h', j='j', z='z', e='e', dd='dd', a='a',
                   f='f', ou='ou'),
    'v3': dict(rb='be', ld='o', fm='ld', wk='v', h='h', j='j', z='z', e='e', dd='dd', a='i',
               f='f', ou='ou'),
}
NAMES['v1'] = dict(NAMES['v3'])
NAMES['v2'] = dict(NAMES['v3'])
STAGE1_PAGES = os.path.join(OUT, 'pages')          # the generator builder's stage-1 lower sets


def kind_of(cfg):
    return cfg.split('-')[0]


def rings_of(cfg):
    return cfg.split('-')[1]


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def gen_module(kind, rings):
    """gen_variant imported and configured (in process)."""
    sys.path.insert(0, os.path.dirname(GEN))
    import gen_variant as G
    G.configure(kind, rings)
    return G


def jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, 'w'), indent=1)
