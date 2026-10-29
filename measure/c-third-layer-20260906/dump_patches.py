"""Raw red-channel patches around C cells at the arm's pose, 4800-dpi lanes, for the patch-discriminant test.

    dump_patches.py --run-dir RUN --gen-dir GEN --payload PAYLOAD \\
        --cells CELLS.npz --out OUT.npz

Historical record of the third-layer C finding (e036/W8, 2026-09-06); the
H14 inputs named below are in the evidence archive.
(2026-09-06: run H14-union, gen dir H-c2-cmy8r0850-q090-4mm, payload
H14-pass1/payload.bin, cells H14-cells-C.npz, out H14-patches-C.npz.)
"""
import argparse, time, collections
import numpy as np
from analyzer import inputs as inputs_mod, truth as truth_mod, sample as sample_mod
from analyzer import frame as frame_mod, arms as arms_mod, fixedpoint as fp, oracle as oracle_mod
from analyzer.types import AnalyzerConfig
from holo.receiver.plugins import color_sites, color_region_anchor as anchor
from holo.receiver.lib import page_map
REF='L:c2-cmy8-r0850-p120-x1@3392x2368'; ARM='subtract+offset'; HALF=12
parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
for flag in ('--run-dir','--gen-dir','--payload','--cells','--out'): parser.add_argument(flag, required=True)
args=parser.parse_args()
inputs=inputs_mod.load_run(args.run_dir, format_ref=REF)
truth=truth_mod.load_truth(args.gen_dir,args.payload,inputs.row,max(inputs.live_pages)+1,format_ref=REF)
certs=dict(inputs.certificates); config=AnalyzerConfig(); field=truth.fields[0]
bits3=np.stack([np.asarray(field.plane_bits[p]).astype(np.uint8) for p in range(3)])
prev=np.load(args.cells); keys=sorted(set(zip(prev['ty'].tolist(),prev['tx'].tolist(),prev['band'].tolist())))
cell_dots=color_sites.cell_dots_of(inputs.row); bound=max(abs(arms_mod.OFFSET_X_MIN),abs(arms_mod.OFFSET_X_MAX),float(cell_dots))+0.5; halo=fp._halo_for(config,'C')
cols=collections.defaultdict(list); t0=time.time(); rng=np.random.default_rng(7)
for ty,tx,band in keys:
    key=(0,ty,tx,'C'); lanes=[l for l in sample_mod.lanes_for_tile(inputs,0,ty,tx,cover_fraction=config.cover_fraction) if int(l.lane_id[1])==3]
    tfp=frame_mod.tile_footprint(inputs.row,0,ty,tx,halo,geometry=inputs.geometry); bit=inputs_mod.metadata_bit(inputs,key)
    for lane in lanes:
        try:
            knobs=fp._knobs_for(inputs,config,key,bit,None); ev=arms_mod.evidence_for(inputs,certs,key,lane,ARM,halo_cells=halo,knobs=knobs)
            if ev.blind.get('refusal'): continue
            lfp=sample_mod.lane_footprint(lane,tfp); crops=sample_mod.open_crops(lane,lfp,bound_dots=bound,cell_dots=cell_dots)
            off=ev.blind.get('offset_dots_xy',(0.0,0.0)); cells=lfp.tile.page_cells_yx
            delta=np.asarray(((off[0]/crops.cell_dots, off[1]/crops.cell_dots),),np.float64)
            moved=np.full((cells.shape[0],2),np.nan)
            for index in np.unique(lfp.owner_index[lfp.observed]).tolist():
                rows=np.flatnonzero(lfp.owner_index==index); terms=sample_mod._terms_for(crops,int(index),None)
                pts=np.asarray(lfp.points_yx,np.float64)[rows]
                if delta.any(): pts=page_map.raster_points(pts,anchor.pose_linear(terms),delta,1)  # delta in cells: the retired shim's own call
                moved[rows]=pts
            pts=np.asarray(lfp.points_yx,np.float64)[lfp.observed]; pitch=crops.pitch_px_level
            y0,x0,raw=anchor.native_crop(lane.rasters,pts,int(crops.halo_px)+HALF+2); div=anchor.native_divisor((float(np.max(raw)),))
            R=raw[...,0].astype(np.float32)/div
        except Exception as e:
            print('error',key,lane.lane_id,repr(e)[:160],flush=True); continue
        keep=np.asarray(tfp.in_tile,bool)&np.isfinite(moved[:,0])
        cy,cx=cells[keep,0],cells[keep,1]; st=bits3[1,cy,cx]+2*bits3[2,cy,cx]
        # all M+Y cells, plus a 1-in-3 subsample of blank-sibling cells
        take=(st==3)|((st==0)&(rng.random(len(st))<0.34))
        idx=np.flatnonzero(keep)[take]
        for i in idx:
            py,px=moved[i]-np.array((y0,x0)); iy,ix=int(round(py)),int(round(px))
            if iy-HALF<0 or ix-HALF<0 or iy+HALF>=R.shape[0] or ix+HALF>=R.shape[1]: continue
            cols['patch'].append(R[iy-HALF:iy+HALF,ix-HALF:ix+HALF].copy())
            cols['c'].append(bits3[0,cells[i,0],cells[i,1]]); cols['sib'].append(bits3[1,cells[i,0],cells[i,1]]+2*bits3[2,cells[i,0],cells[i,1]])
            cols['band'].append(band); cols['ty'].append(ty); cols['tx'].append(tx); cols['lane'].append(lane.lane_id[0][:12]); cols['pitch'].append(pitch)
            cols['ctx'].append(int(oracle_mod._neighbour_ink(bits3[0],np.array([[cells[i,0],cells[i,1]]]))[0]))
    print('done',key,band,'patches so far',len(cols['c']),'elapsed',round(time.time()-t0),flush=True)
np.savez_compressed(args.out,patch=np.stack(cols['patch']),**{k:np.array(v) for k,v in cols.items() if k!='patch'})
print('wrote',len(cols['c']),'patches',time.time()-t0,flush=True)
