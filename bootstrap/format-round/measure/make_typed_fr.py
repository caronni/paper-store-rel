#!/usr/bin/env python3
"""make_typed_fr.py -- stage1/make_typed.py unchanged, the reader it copies
into the build (READER_SRC) pointed at the format-round text of FR_KIND
(record = r2reader/reader_lite_v1.py, v3 / v1 / v2 = format-round/reader/
reader_KIND_rw.py).  Same arguments as make_typed.py; give --build
build/format-round/stage1/KIND (stage1/e2e.py --build, through e2e_fr.py,
reads that build and runs the copy it holds, reader_e2e.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402

sys.path.insert(0, os.path.join(C.BOOT, 'stage1'))
import make_typed as M   # noqa: E402

KIND = os.environ['FR_KIND']
M.READER_SRC = C.READER[KIND]

if __name__ == '__main__':
    assert '--build' in sys.argv, 'give --build (the default build/stage1/ is the paper-test set)'
    M.main()
