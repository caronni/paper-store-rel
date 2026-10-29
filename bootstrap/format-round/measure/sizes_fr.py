#!/usr/bin/env python3
"""sizes_fr.py -- the four texts' sizes, re-measured (never typed):
r2reader/count_reader.py (the typed subset, lines <= 72), the ladder's
convention (diet/w4_ladder.size: primer loader/a.py), and the typed total under
stage 1's primer (r2reader/changeset/size_stage1.py unchanged, its scratch in
build/format-round/sizes/stage1/).  -> build/format-round/sizes/sizes.json
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402

sys.path.insert(0, os.path.join(C.BOOT, 'r2reader', 'changeset'))
sys.path.insert(0, os.path.join(C.BOOT, 'r2reader', 'diet'))

if __name__ == '__main__':
    out = {}
    import w4_ladder as wl
    for k, path in C.READER.items():
        p = subprocess.run([C.PY, os.path.join(C.BOOT, 'r2reader', 'count_reader.py'), path],
                           capture_output=True, text=True)
        out[k] = dict(reader=os.path.relpath(path, C.BOOT), sha256=C.sha(path), count_reader_rc=p.returncode,
                      count_reader=(p.stdout + p.stderr).strip(), ladder=wl.size(path))
        print(k, out[k], flush=True)
    s1 = subprocess.run([C.PY, '-c', (
        "import sys;sys.path.insert(0,%r);import size_stage1 as S;S.OUT=%r;sys.argv=['x']+%r;S.main()")
        % (os.path.join(C.BOOT, 'r2reader', 'changeset'), os.path.join(C.OUT, 'sizes', 'stage1'),
           list(C.READER.values()))], capture_output=True, text=True)
    out['stage1_stdout'] = s1.stdout
    out['stage1_rc'] = s1.returncode
    print(s1.stdout, s1.stderr[-2000:])
    C.jdump(out, os.path.join(C.OUT, 'sizes', 'sizes.json'))
