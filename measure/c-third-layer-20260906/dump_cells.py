"""Per-cell dump for sheet H's C plane: RGB at the default arm's pose, true state, context, LLR.

    dump_cells.py ARM OUT.npz [KNOBS-JSON] --run-dir RUN --gen-dir GEN \\
        --payload PAYLOAD --score SCORE.jsonl

Historical record of the third-layer C finding (e036/W8, 2026-09-06); the
H14 inputs named below are in the evidence archive.
(2026-09-06: run H14-union, gen dir H-c2-cmy8r0850-q090-4mm, payload
H14-pass1/payload.bin, score H14-score-full/score.jsonl.)

W8 B3: argv[3] is a JSON object of analyzer knobs — e.g.
'{"branches":"state","ctx_state":true,"patch_selftrain_rounds":4}' — handed
to AnalyzerConfig(knobs=...).  The key "halo_cells" is lifted out of that
object into the config FIELD of the same name (an int, or a per-stream
map), because the halo is not a knob.  This is the S9 route of
APPROACHES §3: dump one arm's per-lane LLRs, then combine them with
combine_blind.py, which is the only estimator that produces a
COMBINED-lane number (the `score` tool is per lane by design).
"""
import argparse, json, time, collections
import numpy as np
from pathlib import Path
from analyzer import inputs as inputs_mod, truth as truth_mod, sample as sample_mod
from analyzer import frame as frame_mod, arms as arms_mod, fixedpoint as fp, oracle as oracle_mod
from analyzer.types import AnalyzerConfig
from holo.receiver.plugins import color_sites

REF = 'L:c2-cmy8-r0850-p120-x1@3392x2368'
parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument('arm')
parser.add_argument('out', type=Path)
parser.add_argument('knobs', nargs='?', default='{}')
parser.add_argument('--run-dir', required=True)
parser.add_argument('--gen-dir', required=True)
parser.add_argument('--payload', required=True)
parser.add_argument('--score', required=True)
args = parser.parse_args()
ARM = args.arm
OUT = args.out
t0 = time.time()
inputs = inputs_mod.load_run(args.run_dir, format_ref=REF)
print('loaded run', time.time() - t0, flush=True)
pages = max(inputs.live_pages) + 1
truth = truth_mod.load_truth(args.gen_dir, args.payload, inputs.row, pages,
                             format_ref=REF)
certs = dict(inputs.certificates)
knobs = json.loads(args.knobs)
halo_knob = knobs.pop('halo_cells', None)
halo_cells = ({str(s): int(halo_knob) for s in 'CMY'} if isinstance(halo_knob, int)
              else {str(k): int(v) for k, v in halo_knob.items()} if halo_knob else None)
config = AnalyzerConfig(knobs=knobs, halo_cells=halo_cells)
print('arm', ARM, 'knobs', knobs, 'halo', halo_cells, flush=True)
field = truth.fields[0]
bits3 = np.stack([np.asarray(field.plane_bits[p]).astype(np.uint8) for p in range(3)])  # (3, H, W)

# --- key selection from the full score: open C rows by band, plus certified references
rows = collections.defaultdict(list)
with open(args.score) as f:
    next(f)
    for l in f:
        d = json.loads(l)
        if d.get('type') != 'row' or d['stream_id'] != 'C' or d['verdict'] != 'open': continue
        rows[d['band']].append((d['ty'], d['tx']))
rng = np.random.default_rng(20260906)
def pick(lst, n):
    lst = sorted(set(lst)); idx = rng.choice(len(lst), size=min(n, len(lst)), replace=False); return [lst[i] for i in sorted(idx)]
keys = [(0, ty, tx, 'C', band) for band, n in (('dead', 14), ('marginal', 8), ('live', 8)) for ty, tx in pick(rows[band], n)]
cert_c = [(k[1], k[2]) for k in certs if k[3] == 'C' and k[0] == 0]
healthy = [(ty, tx) for ty, tx in cert_c if 12 <= tx <= 24]
edge = [(ty, tx) for ty, tx in cert_c if tx in (29, 32)]
keys += [(0, ty, tx, 'C', 'cert-healthy') for ty, tx in pick(healthy, 8)]
keys += [(0, ty, tx, 'C', 'cert-edge') for ty, tx in pick(edge, 6)]
print('keys', len(keys), flush=True)

cell_dots = color_sites.cell_dots_of(inputs.row)
bound = max(abs(arms_mod.OFFSET_X_MIN), abs(arms_mod.OFFSET_X_MAX), float(cell_dots)) + 0.5
halo = fp._halo_for(config, 'C')
cols = collections.defaultdict(list)
for page, ty, tx, sid, band in keys:
    key = (page, ty, tx, sid)
    lanes = sample_mod.lanes_for_tile(inputs, page, ty, tx, cover_fraction=config.cover_fraction)
    tfp = frame_mod.tile_footprint(inputs.row, page, ty, tx, halo, geometry=inputs.geometry)
    bit = inputs_mod.metadata_bit(inputs, key)
    grid = oracle_mod.sequential_cells(inputs.row, key)      # tile-local (y, x) per sequential index
    for lane in lanes:
        try:
            knobs = fp._knobs_for(inputs, config, key, bit, None)
            ev = arms_mod.evidence_for(inputs, certs, key, lane, ARM, halo_cells=halo, knobs=knobs)
            if ev.blind.get('refusal'): print('refused', key, lane.lane_id, ev.blind['refusal'], flush=True); continue
            lfp = sample_mod.lane_footprint(lane, tfp)
            crops = sample_mod.open_crops(lane, lfp, bound_dots=bound, cell_dots=cell_dots)
            off = ev.blind.get('offset_dots_xy', (0.0, 0.0))
            read = sample_mod.read_rgb(crops, lfp, offset_dots_xy=tuple(off), arm='dump')
            if read.refusal: print('read refused', key, lane.lane_id, read.refusal, flush=True); continue
        except Exception as e:
            print('error', key, lane.lane_id, repr(e)[:200], flush=True); continue
        cells = tfp.page_cells_yx; vals = read.values_rgb
        keep = np.asarray(tfp.in_tile, bool) & np.isfinite(vals[:, 0])
        cy, cx = cells[keep, 0], cells[keep, 1]
        # LLR per page cell from the sequential vector
        llr_map = {}
        for i in np.flatnonzero(np.asarray(ev.observed, bool)):
            llr_map[(int(grid[i, 0]) + ty * 64, int(grid[i, 1]) + tx * 64)] = float(ev.llr_sequential[i])
        llr = np.array([llr_map.get((int(y), int(x)), np.nan) for y, x in zip(cy, cx)])
        ctx = oracle_mod._neighbour_ink(bits3[0], np.stack((cy, cx), 1))
        n = int(keep.sum())
        cols['ty'].append(np.full(n, ty, np.int16)); cols['tx'].append(np.full(n, tx, np.int16))
        cols['band'].append(np.full(n, band, dtype='U12')); cols['lane'].append(np.full(n, lane.lane_id[0][:12], dtype='U12'))
        cols['level'].append(np.full(n, int(lane.lane_id[1]), np.int8))
        cols['y'].append(cy.astype(np.int16)); cols['x'].append(cx.astype(np.int16))
        cols['c'].append(bits3[0, cy, cx]); cols['m'].append(bits3[1, cy, cx]); cols['yb'].append(bits3[2, cy, cx])
        cols['R'].append(vals[keep, 0].astype(np.float32)); cols['G'].append(vals[keep, 1].astype(np.float32)); cols['B'].append(vals[keep, 2].astype(np.float32))
        cols['llr'].append(llr.astype(np.float32)); cols['ctx'].append(ctx.astype(np.int8))
        cols['offx'].append(np.full(n, off[0], np.float32)); cols['offy'].append(np.full(n, off[1], np.float32))
    print('done', key, band, 'lanes', len(lanes), 'elapsed', round(time.time() - t0), flush=True)
np.savez_compressed(OUT, **{k: np.concatenate(v) for k, v in cols.items()})
print('wrote', OUT, sum(len(a) for a in cols['R']), 'cells', time.time() - t0, flush=True)
