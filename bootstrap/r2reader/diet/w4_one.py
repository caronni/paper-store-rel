"""w4_one.py -- one reader on a few frames, sequentially (never typed).
Usage: python w4_one.py READER FRAME [FRAME ...]   (frames pooled in order)
Frame names: a build/w1 render name (one.q-tl), a build/w4/env file name
(one.cu-b0.pgm), or a path.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import w4_harness as wh  # noqa: E402


def path(f):
    for p in (f, wh.w1(f), os.path.join(wh.ENV, f)):
        if os.path.exists(p):
            return os.path.abspath(p)
    raise SystemExit('no frame ' + f)


if __name__ == '__main__':
    rd, frames = sys.argv[1], [path(f) for f in sys.argv[2:]]
    t = time.time()
    lines, secs, rc, se = wh.run(wh.rpy_of(rd), frames,
                                 os.path.join(wh.OUT, 'runs', 'one', str(os.getpid())))
    for f, l, s in zip(frames, lines, secs):
        print(f'{s:6.2f}s {os.path.basename(f)}: {l}')
    print('exit', rc, se[-1500:])
