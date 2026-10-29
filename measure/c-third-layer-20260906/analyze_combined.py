"""The combined-lane reading: per-tile even/odd Platt over the summed 4800 lanes.

    analyze_combined.py PATCHES.npz CELLS.npz    (2026-09-06: H14-patches-C2.npz, H14-cells-C.npz)

Historical record of the third-layer C finding (e036/W8, 2026-09-06); the
H14 inputs named below are in the evidence archive.
"""
import sys
import numpy as np, time
if len(sys.argv) != 3: raise SystemExit(__doc__)
T0=time.time()
p=np.load(sys.argv[1]); P=p['patch'].astype(np.float32); pc=p['c'].astype(int); psib=p['sib'].astype(int); pband=p['band']; pty=p['ty'].astype(int); ptx=p['tx'].astype(int); py=p['y'].astype(int); px=p['x'].astype(int); plane=p['lane']; pitch=p['pitch']
n,h,w=P.shape; cy,cx=h//2,w//2; ap=int(round(0.7*float(np.median(pitch))))//2; flat=P.reshape(n,-1)
d0=np.load(sys.argv[2]); d={k:d0[k] for k in ('ty','tx','lane','y','x','level','llr')}
# build a lookup from the cells dump restricted to level-3 lanes
lv3=d['level']==3
idx=np.flatnonzero(lv3)
dty,dtx,dl,dy,dx,dllr=d['ty'][idx],d['tx'][idx],d['lane'][idx].astype(str),d['y'][idx],d['x'][idx],d['llr'][idx]
lut={(int(a),int(b),l,int(c_),int(e)):i for i,(a,b,l,c_,e) in enumerate(zip(dty,dtx,dl,dy,dx))}
arm_llr=np.array([dllr[lut[k]] if k in lut else np.nan for k in zip(pty.tolist(),ptx.tolist(),plane.astype(str).tolist(),py.tolist(),px.tolist())])
print('patches',n,'matched to arm LLRs',np.isfinite(arm_llr).sum(),'t',round(time.time()-T0),flush=True)
def fit_lda(X,y,lam=1e-2):
    mu=X.mean(0); Xs=(X-mu); sd=Xs.std(0)+1e-6; Xs=Xs/sd; t=np.where(y==1,1.0,-1.0)
    w=np.linalg.solve(Xs.T@Xs/len(y)+lam*np.eye(X.shape[1]),Xs.T@t/len(y)); s=Xs@w; return mu,sd,w,0.5*(s[y==1].mean()+s[y==0].mean())
def apply(X,f): mu,sd,w,thr=f; return ((X-mu)/sd)@w-thr
def platt(L,b):
    best=None
    for a in np.linspace(0.05,4.0,60):
        for cc in np.linspace(-1.5,1.5,31):
            sgn=np.clip((a*L+cc)*(2*b-1),-60,60); ll=np.log1p(np.exp(-sgn)).mean()
            if best is None or ll<best[0]: best=(ll,a,cc)
    return best[1],best[2]
def info(L,b):
    s=np.clip(L*(2*b-1),-60,60); return 1-np.log2(1+np.exp(-s))
for g in ('dead','marginal','live'):
    sel=(pband==g)&np.isfinite(arm_llr)
    # patch LDA per (lane, state), CV over tile parity, then Platt (CV) -> LLR
    patch_llr=np.full(n,np.nan)
    for l in np.unique(plane[sel]):
        for st in range(4):
            q=sel&(plane==l)&(psib==st)
            for parity in (0,1):
                tr=q&(pty%2==parity); te=q&(pty%2!=parity)
                if tr.sum()<300 or te.sum()<50: continue
                f=fit_lda(flat[tr],pc[tr]); s_te=apply(flat[te],f); s_tr=apply(flat[tr],f)
                a,cc=platt(s_tr,(pc[tr]==1).astype(float)); patch_llr[te]=a*s_te+cc
    ok=sel&np.isfinite(patch_llr)
    # combine across lanes per cell
    key=(pty[ok].astype(np.int64)*100000000+ptx[ok].astype(np.int64)*1000000+py[ok].astype(np.int64)*1000+px[ok].astype(np.int64))
    o=np.argsort(key,kind='stable'); key=key[o]; uk,start=np.unique(key,return_index=True)
    b=(pc[ok]==1)[o][start].astype(float); s=psib[ok][o][start]; t=(pty[ok].astype(np.int64)*1000+ptx[ok])[o][start]
    nl=np.diff(np.append(start,key.size))
    for name,L in (('arm (4800 lanes)',arm_llr[ok][o]),('patch LDA (4800 lanes)',patch_llr[ok][o])):
        S=np.add.reduceat(np.clip(L,-8,8),start)
        Ss=np.full(S.size,np.nan); Rs=[]
        for tt in np.unique(t):
            q=np.flatnonzero(t==tt)
            for fit,app in ((q[::2],q[1::2]),(q[1::2],q[::2])):
                a,cc=platt(S[fit],b[fit]); Ss[app]=a*S[app]+cc
            inf=info(Ss[q],b[q]); sq=s[q]
            # reweight the state subsample: 1/4 of cells are M+Y, 3/4 the other states
            R=(0.25*inf[sq==3].mean()+0.75*inf[sq!=3].mean())/0.886 if (sq==3).any() and (sq!=3).any() else np.nan
            Rs.append(R)
        errs=' '.join(f"{nm} {((Ss[s==st]>0)!=(b[s==st]>0)).mean():.3f}" for st,nm in ((0,'blank'),(1,'M'),(2,'Y'),(3,'M+Y')))
        print(f"   {g:9s} {name:24s} cells {S.size:6d} lanes/cell {nl.mean():.1f}  err by state: {errs}  | R per tile: median {np.nanmedian(Rs):.3f} min {np.nanmin(Rs):.3f} max {np.nanmax(Rs):.3f}  tiles>=1.0: {int(np.nansum(np.array(Rs)>=1.0))}/{len(Rs)}")
