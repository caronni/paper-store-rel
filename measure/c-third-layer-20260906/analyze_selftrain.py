"""The user's proposal in miniature: halo-trained filter, then segment the tile's OWN M+Y population (no target labels), then a decoder-feedback proxy.

    analyze_selftrain.py PATCHES.npz    (2026-09-06: H14-patches-C2.npz, from dump_patches2.py)

Historical record of the third-layer C finding (e036/W8, 2026-09-06); the
H14 inputs named below are in the evidence archive.
"""
import sys
import numpy as np, collections
if len(sys.argv) != 2: raise SystemExit(__doc__)
p=np.load(sys.argv[1]); P=p['patch'].astype(np.float32); c=p['c'].astype(int); sib=p['sib'].astype(int); band=p['band']; ty=p['ty'].astype(int); tx=p['tx'].astype(int); y=p['y'].astype(int); x=p['x'].astype(int); lane=p['lane'].astype(str); pitch=p['pitch']
n,h,w=P.shape; cy,cx=h//2,w//2; ap=int(round(0.7*float(np.median(pitch))))//2; flat=P.reshape(n,-1); box=P[:,cy-ap:cy+ap,cx-ap:cx+ap].mean((1,2))
def fit_lda(X,yv,wt=None,lam=1e-2):
    wt=np.ones(len(yv)) if wt is None else wt; wt=wt/wt.sum()
    mu=(wt[:,None]*X).sum(0); Xs=X-mu; sd=np.sqrt((wt[:,None]*Xs**2).sum(0))+1e-6; Xs=Xs/sd; t=np.where(yv==1,1.0,-1.0)
    A=(Xs*wt[:,None]).T@Xs+lam*np.eye(X.shape[1]); wv=np.linalg.solve(A,(Xs*wt[:,None]).T@t); s=Xs@wv
    thr=0.5*((wt*(yv==1)*s).sum()/(wt*(yv==1)).sum()+(wt*(yv==0)*s).sum()/(wt*(yv==0)).sum()); return mu,sd,wv,thr
def apply(X,f): mu,sd,wv,thr=f; return ((X-mu)/sd)@wv-thr
def err(s,yv): return ((s>0)!=(yv==1)).mean()
def platt(L,b):
    best=None
    for a in np.linspace(0.05,4.0,40):
        for cc in np.linspace(-1.5,1.5,21):
            sgn=np.clip((a*L+cc)*(2*b-1),-60,60); ll=np.log1p(np.exp(-sgn)).mean()
            if best is None or ll<best[0]: best=(ll,a,cc)
    return best[1],best[2]
rng=np.random.default_rng(1)
dead_tiles=sorted(set(zip(ty[band=='dead'].tolist(),tx[band=='dead'].tolist())))
lanes=sorted(set(lane[band=='dead'].tolist()))
print('dead tiles',len(dead_tiles),'4800 lanes',len(lanes))
res=collections.defaultdict(list); cell_scores=collections.defaultdict(dict)   # (variant) -> {(tile,lane): (scores, labels, keys)}
for l in lanes:
    halo=(band=='cert-edge')&(lane==l)&(sib==3)           # the certified neighbours' three-ink cells: the halo's labels
    if halo.sum()<300: continue
    f0=fit_lda(flat[halo],c[halo])
    # permutation control: shuffled halo labels
    fperm=fit_lda(flat[halo],rng.permutation(c[halo]))
    for T in dead_tiles:
        q=(band=='dead')&(lane==l)&(sib==3)&(ty==T[0])&(tx==T[1])
        if q.sum()<200: continue
        X=flat[q]; yv=c[q]
        s_box=-(box[q]-np.median(box[q]))                      # box mean, tile-median threshold (blind)
        s0=apply(X,f0); res['halo-trained'].append(err(s0,yv)); res['box(tile median)'].append(err(s_box,yv)); res['permutation control'].append(err(apply(X,fperm),yv))
        # self-training: segment the tile's own M+Y population, iterate
        s=s0.copy()
        for it in range(4):
            conf=np.abs(s)>=np.percentile(np.abs(s),40)          # the 60% most confident cells become pseudo-labels
            Xa=np.concatenate([flat[halo],X[conf]]); ya=np.concatenate([c[halo],(s[conf]>0).astype(int)]); wa=np.concatenate([np.ones(halo.sum()),2.0*np.ones(conf.sum())])
            f=fit_lda(Xa,ya,wa); s=apply(X,f)
        res['self-trained x4'].append(err(s,yv))
        # decoder-feedback proxy: 25% of the tile's cells get their TRUE bit as a label (what BP would hand back when it is on track)
        fb=rng.random(len(yv))<0.25
        Xa=np.concatenate([flat[halo],X[fb]]); ya=np.concatenate([c[halo],yv[fb]]); wa=np.concatenate([np.ones(halo.sum()),3.0*np.ones(fb.sum())])
        f=fit_lda(Xa,ya,wa); sfb=apply(X,f); res['decoder-feedback proxy (25%)'].append(err(sfb[~fb],yv[~fb]))
        keys=(y[q].astype(np.int64)*1000+x[q]); 
        for name,sc in (('box',s_box),('halo',s0),('self',s),('fb',np.where(fb,np.nan,sfb))):
            cell_scores[name][(T,l)]=(sc,yv,keys)
print('\nSingle 4800 lane, dead-band M+Y cells, per-tile error (mean over tiles x lanes):')
for k,v in res.items(): print(f'   {k:32s} {np.mean(v):.3f}   (n={len(v)})')
# combine lanes per cell (Platt per (lane) on the halo... use per-tile even/odd Platt as before)
print('\nCombined over the 4800 lanes (clipped sum of per-lane Platt LLRs, Platt fitted on the halo tiles for halo/self, tile even/odd for box):')
for name in ('box','halo','self','fb'):
    S=collections.defaultdict(float); B={}; cnt=collections.defaultdict(int)
    for (T,l),(sc,yv,keys) in cell_scores[name].items():
        ok=np.isfinite(sc)
        # calibrate this lane's scores on the OTHER dead tiles of the same lane (stand-in for halo-calibrated), never on this tile
        others=[v for (T2,l2),v in cell_scores[name].items() if l2==l and T2!=T]
        so=np.concatenate([v[0][np.isfinite(v[0])] for v in others]); bo=np.concatenate([v[1][np.isfinite(v[0])] for v in others])
        a,cc=platt(so,bo)
        L=np.clip(a*sc[ok]+cc,-8,8)
        for kk,ll,bb in zip((T[0]*100000000+T[1]*1000000+keys[ok]).tolist(),L.tolist(),yv[ok].tolist()): S[kk]+=ll; B[kk]=bb; cnt[kk]+=1
    ks=list(S); Sv=np.array([S[k] for k in ks]); Bv=np.array([B[k] for k in ks]); nl=np.mean([cnt[k] for k in ks])
    print(f'   {name:5s} cells {len(ks):6d} lanes/cell {nl:.1f}  M+Y error {((Sv>0)!=(Bv==1)).mean():.3f}')
