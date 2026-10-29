"""Pack src/holo/core/ldpc/data/r0550.json into receiver.py's LDPC_TABLE.

One integer in mixed radix, least significant digit first: the interleaver
pi as its Lehmer code (digit i in radix 1856 - i = the index of pi[i] among
the entries not yet used), then per info column block in holo's order (10
heavy, then 25 light) its block rows (radix 29) then its shifts (radix 64).
Rewrites the lines between the LDPC-TABLE markers in receiver.py (hex, 76
digits a line) and checks that the receiver's expansion equals holo's edge
set.  Run from the worktree root:
  PYTHONPATH=src env/bin/python bootstrap/r3/pack_ldpc.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
d = json.loads((ROOT / "src/holo/core/ldpc/data/r0550.json").read_text())
pi = d["pi"]
m = len(pi)
digits = []
pool = list(range(m))
for i in range(m):
    k = pool.index(pi[i])
    pool.pop(k)
    digits.append((k, m - i))
for rows, shifts in ((d["heavy_rows"], d["heavy_shifts"]),
                     (d["light_rows"], d["light_shifts"])):
    for r, s in zip(rows, shifts):
        digits += [(x, 29) for x in r] + [(x, 64) for x in s]
x = 0
for v, radix in reversed(digits):
    assert 0 <= v < radix
    x = x * radix + v
h = format(x, "x")
lines = [h[i:i + 76] for i in range(0, len(h), 76)]
block = "".join(f"    '{ln}'\n" for ln in lines)
src = (HERE / "receiver.py").read_text()
new = re.sub(r"(    # LDPC-TABLE-BEGIN\n).*?(    # LDPC-TABLE-END\n)",
             lambda mo: mo.group(1) + block + mo.group(2), src, flags=re.S)
(HERE / "receiver.py").write_text(new)
print(f"LDPC_TABLE: {x.bit_length()} bits, {len(h)} hex digits, {len(lines)} lines")

# check: the receiver's checks == holo's edges (minus the shortened tail)
check = r"""
import sys, numpy as np
sys.path.insert(0, %r)
import receiver as R
from holo.core.ldpc.construct import load_code
c = load_code('r0550')
mine = sorted((ci, v) for ci, vs in enumerate(R.CHECKS) for v in vs)
ref = sorted((int(a), int(b)) for a, b in zip(c.edge_chk, c.edge_var)
             if not 2140 <= int(b) < 2240)
print('edges', len(mine), len(ref), 'identical' if mine == ref else 'DIFFER')
sys.exit(0 if mine == ref else 1)
""" % str(HERE)
sys.exit(subprocess.run([sys.executable, "-c", check]).returncode)
