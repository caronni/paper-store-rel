"""make_qr.py -- the two QR codes of the for-print sheets (ruling 62), made
ONCE: segno encodes, zxingcpp decodes back to the exact bytes, the module
matrices go to qr-a.pbm / qr-d.pbm (1 pixel per module, no quiet zone; P4)
and their inputs' shas to qr.json, which stage1/print_sheets.py checks so
the print build needs no QR library.  Neither library is in the venv:

  PYTHONPATH=QRLIBS env/bin/python bootstrap/stage1/qr/make_qr.py [--s1 DIR]

QRLIBS: a directory holding segno (1.6.6) and zxingcpp (3.1.1); --s1 the
stage-1 build (default bootstrap/build/sheets/stage1), its upper case read.
"""
import hashlib
import json
import os
import sys
from importlib.metadata import version

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE1 = os.path.dirname(HERE)
BOOT = os.path.dirname(STAGE1)
sys.path.insert(0, STAGE1)
import print_sheets as PS  # noqa: E402
import segno  # noqa: E402
import zxingcpp  # noqa: E402

ZXING = version('zxing-cpp')    # the module has no __version__
SOURCES = {'qr-a': 'a.py', 'qr-d': 'data.txt'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    a = sys.argv
    s1 = os.path.abspath(a[a.index('--s1') + 1] if '--s1' in a else os.path.join(BOOT, 'build', 'sheets', 'stage1'))
    upper = os.path.join(s1, 'upper')
    meta = {}
    for name, data in PS.qr_inputs(upper).items():
        q = segno.make(data, error='l', mode='byte', boost_error=False, micro=False)
        dark = np.array(q.matrix, dtype=bool)
        n = 17 + 4 * q.version
        assert dark.shape == (n, n) and q.error == 'L' and q.mode == 'byte'
        p = os.path.join(HERE, name + '.pbm')
        Image.fromarray(~dark).save(p)
        back = ~np.array(Image.open(p).convert('1'))
        assert (back == dark).all()
        img = Image.fromarray(np.where(np.kron(np.pad(dark, 4), np.ones((4, 4), bool)), 0, 255).astype(np.uint8))
        res = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode)
        assert len(res) == 1 and res[0].bytes == data, name
        src = os.path.join(upper, SOURCES[name])
        meta[name] = dict(name=name, source=f'build/sheets/stage1/upper/{SOURCES[name]}',
                          source_sha256=sha(open(src, 'rb').read()), input_bytes=len(data),
                          input_sha256=sha(data), version=q.version, error='L', mode='byte', mask=q.mask,
                          modules=n, pbm_sha256=sha(open(p, 'rb').read()),
                          decode=f'zxingcpp {ZXING}: {len(res[0].bytes)} B, equal to the input',
                          encoder=f'segno {segno.__version__}')
        print(name, json.dumps(meta[name]))
    open(os.path.join(HERE, 'qr.json'), 'w').write(json.dumps(meta, indent=1, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
