"""common.py -- the search's inputs: the reader's typed text (stage 1's
reader_text: region minus the shared block, N2/B2 the bundle's), stage 1's
lowercase primer (the changeset build's a.py, .strip()), and the way back from
a searched typed text to reader_lite_v1.py (shared block and N2/B2 tokens
restored, everything outside the markers untouched)."""
import io
import os
import sys
import tokenize
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))   # bootstrap/
sys.path.insert(0, os.path.join(ROOT, 'stage1'))
import make_typed as M   # noqa: E402

READER = os.path.join(ROOT, 'r2reader', 'reader_lite_v1.py')
OUT = os.path.join(ROOT, 'build', 'changeset', 'rw')
PRIMER = os.path.join(ROOT, 'build', 'changeset', 'stage1', 'lower', 'a.py')
BEGIN, END = '# BEGIN READER\n', '# END READER'


def bundle_consts():
    b = open(M.BUNDLE, 'rb').read()
    return len(b), zlib.crc32(b)


def typed_of(path=READER):
    n2, b2 = bundle_consts()
    return M.reader_text(path, n2, b2)


def primer():
    return M.primer_of(open(PRIMER).read())


def numeral_tokens(s, value):
    return [t for t in tokenize.generate_tokens(io.StringIO(s).readline)
            if t.type == tokenize.NUMBER and t.string == str(value)]


def put_back(typed, path=READER):
    """the file text with its typed region replaced by `typed` (the shared block
    re-inserted where it stood: at the region's head; N2/B2 tokens restored)."""
    n2, b2 = bundle_consts()
    s = typed
    for name, val in (('N2', n2), ('B2', b2)):
        toks = numeral_tokens(s, val)
        assert len(toks) == 1, (name, val, len(toks))
        (row, c0), (_, c1) = toks[0].start, toks[0].end
        lines = s.splitlines(keepends=True)
        lines[row - 1] = lines[row - 1][:c0] + name + lines[row - 1][c1:]
        s = ''.join(lines)
    f = open(path).read()
    head, rest = f.split(BEGIN, 1)
    region, tail = rest.split(END, 1)
    sh0 = region.index(M.SHARED_BEGIN)
    sh1 = region.index(M.SHARED_END) + len(M.SHARED_END) + 1
    assert sh0 == 0, 'the shared block is expected at the region head'
    new = head + BEGIN + region[sh0:sh1] + s + END + tail
    assert typed_of_text(new) == typed
    return new


def typed_of_text(text):
    p = os.path.join(OUT, '_probe.py')
    open(p, 'w').write(text)
    return typed_of(p)
