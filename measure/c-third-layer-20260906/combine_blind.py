"""S9: the COMBINED-lane reading of any arm's per-lane LLR dump (W8 B3).

    combine_blind.py CELLS.npz [LEVEL]    (2026-09-06: S9-cells.npz)

Historical record of the third-layer C finding (e036/W8, 2026-09-06); the
H14 inputs named below are in the evidence archive.

TRUTH-READING, offline, outside the analyzer package on purpose (DESIGN
§0.1): it scores a dump against the emitted bits the dump carries.

WHY IT EXISTS.  `analyzer score` scores each LANE on its own — that is
its contract (`score.evidence_for_row`), and every per-lane number of
MEASUREMENTS-2026-09-06 came through it.  The combined-lane numbers of
MEAS §5/§5b did not: they came from `analyze_combined.py`, which sums the
lanes and asks whether the TILE crosses R = 1.  This script is that
estimator, applied to a blind arm's own calibrated LLRs
(`dump_cells.py <arm> <out.npz> '<knobs>'`) instead of to an offline LDA:

  * keep the lanes of one level (default 3 = the 4800 captures, MEAS
    §4/§5b's population);
  * per cell, SUM the per-lane LLRs clipped at +-8 (the clip is
    `analyze_combined.py`'s: one lane may not carry a cell alone);
  * per TILE, fit a Platt (a, c) on the even cells and apply it to the
    odd ones and back — the same cross-fit the measurement used, so no
    tile is calibrated on itself;
  * report the error by sibling state and R per tile, where R is the
    state-REWEIGHTED mean information (0.25 M+Y / 0.75 the rest, the
    payload's own mix) over 0.886, and count the tiles at R >= 1.

Read the numbers against MEAS §5's dead-band 0.062 / R median 0.956 and
say which estimator produced which — they are the same estimator only if
this script is the one that produced both.
"""
import sys
import numpy as np

if len(sys.argv) < 2:
    raise SystemExit(__doc__)
PATH = sys.argv[1]
LEVEL = int(sys.argv[2]) if len(sys.argv) > 2 else 3
CLIP = 8.0
STATE_NAMES = ((0, 'blank'), (1, 'M'), (2, 'Y'), (3, 'M+Y'))


def platt(llr, bit):
    """`analyze_combined.platt`: the grid the measurement searched."""
    best = None
    for a in np.linspace(0.05, 4.0, 60):
        for c in np.linspace(-1.5, 1.5, 31):
            sgn = np.clip((a * llr + c) * (2 * bit - 1), -60, 60)
            loss = np.log1p(np.exp(-sgn)).mean()
            if best is None or loss < best[0]:
                best = (loss, a, c)
    return best[1], best[2]


def info(llr, bit):
    s = np.clip(llr * (2 * bit - 1), -60, 60)
    return 1 - np.log2(1 + np.exp(-s))


d = np.load(PATH, allow_pickle=False)
level = d['level'].astype(int)
keep = (level == LEVEL) & np.isfinite(d['llr'])
ty, tx, y, x = (d[k][keep].astype(np.int64) for k in ('ty', 'tx', 'y', 'x'))
band = d['band'][keep].astype(str)
c = d['c'][keep].astype(int)
state = d['m'][keep].astype(int) + 2 * d['yb'][keep].astype(int)
llr = np.clip(d['llr'][keep].astype(np.float64), -CLIP, CLIP)
print(f'{PATH}: {keep.sum()} of {keep.size} cell-lane rows at level {LEVEL}',
      flush=True)

key = ((ty * 100000000 + tx * 1000000 + y * 1000 + x))
order = np.argsort(key, kind='stable')
key, llr = key[order], llr[order]
uniq, start = np.unique(key, return_index=True)
summed = np.add.reduceat(llr, start)
bit = c[order][start]
sib = state[order][start]
tile = (ty * 1000 + tx)[order][start]
grp = band[order][start]
lanes_per_cell = np.diff(np.append(start, key.size))
print(f'cells {summed.size}  lanes/cell {lanes_per_cell.mean():.1f}',
      flush=True)

for name in sorted(set(grp.tolist())):
    sel = grp == name
    calibrated = np.full(summed.size, np.nan)
    ratios = []
    for one in np.unique(tile[sel]):
        q = np.flatnonzero(sel & (tile == one))
        if q.size < 8:
            continue
        for fit, app in ((q[::2], q[1::2]), (q[1::2], q[::2])):
            a, cc = platt(summed[fit], bit[fit])
            calibrated[app] = a * summed[app] + cc
        gain = info(calibrated[q], bit[q])
        mine = sib[q]
        if (mine == 3).any() and (mine != 3).any():
            ratios.append((0.25 * gain[mine == 3].mean()
                           + 0.75 * gain[mine != 3].mean()) / 0.886)
    ok = sel & np.isfinite(calibrated)
    errs = ' '.join(
        f'{label} {((calibrated[ok & (sib == s)] > 0) != (bit[ok & (sib == s)] > 0)).mean():.3f}'
        f'({int((ok & (sib == s)).sum())})'
        for s, label in STATE_NAMES if (ok & (sib == s)).any())
    if ratios:
        ratios = np.asarray(ratios, float)
        band_r = (f'R per tile: median {np.nanmedian(ratios):.3f} '
                  f'min {np.nanmin(ratios):.3f} max {np.nanmax(ratios):.3f} '
                  f'tiles>=1.0: {int(np.nansum(ratios >= 1.0))}/{ratios.size}')
    else:
        band_r = 'R per tile: (no tile carried both state groups)'
    print(f'   {name:12s} cells {int(ok.sum()):6d}  err by state: {errs}'
          f'  | {band_r}', flush=True)
