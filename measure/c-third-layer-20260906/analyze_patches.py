"""The patch-discriminant test over a C-plane patch dump.

    analyze_patches.py PATCHES.npz    (2026-09-06: H14-patches-C.npz, from dump_patches.py)

Historical record of the third-layer C finding (e036/W8, 2026-09-06); the
H14 inputs named below are in the evidence archive.
"""
import sys
import numpy as np, collections
if len(sys.argv) != 2: raise SystemExit(__doc__)
d=np.load(sys.argv[1]); P=d['patch'].astype(np.float32); c=d['c'].astype(int); sib=d['sib'].astype(int); band=d['band']; ty=d['ty']; tx=d['tx']; ctx=d['ctx'].astype(int); pitch=d['pitch']
n,h,w=P.shape; print('patches',n,'shape',(h,w),'pitch px/cell',np.unique(np.round(pitch,1)),'by band',dict(collections.Counter(band.tolist())),'sib',dict(collections.Counter(sib.tolist())))
cy,cx=h//2,w//2; yy,xx=np.mgrid[0:h,0:w]; rr=np.sqrt((yy-cy+0.5)**2+(xx-cx+0.5)**2)
ap=int(round(0.7*float(np.median(pitch))))//2
box=P[:,cy-ap:cy+ap,cx-ap:cx+ap].mean((1,2))                    # the production aperture mean (0.7 cell box)
rings=np.stack([P[:,(rr>=r0)&(rr<r1)].mean(1) for r0,r1 in ((0,3),(3,5),(5,7),(7,9),(9,11),(11,13))],1)
flat=P.reshape(n,-1)
def fit_lda(X,y,lam=1e-2):
    mu=X.mean(0); Xs=X-mu; sd=Xs.std(0)+1e-6; Xs=Xs/sd
    t=np.where(y==1,1.0,-1.0)
    XtX=Xs.T@Xs/len(y)+lam*np.eye(X.shape[1]); w=np.linalg.solve(XtX,Xs.T@t/len(y))
    s=Xs@w; # threshold: midpoint of class means of the score
    thr=0.5*(s[y==1].mean()+s[y==0].mean())
    return mu,sd,w,thr
def apply(X,f):
    mu,sd,w,thr=f; return ((X-mu)/sd)@w-thr
def err(score,y): return ((score>0)!=(y==1)).mean()
def auc(s,y):
    r=s.argsort().argsort().astype(float)+1; npos=(y==1).sum(); return (r[y==1].sum()-npos*(npos+1)/2)/(npos*(len(y)-npos))
print('\nFeature sets: box = 0.7-cell aperture mean (what the arm sees); rings = 6 radial means; patch = all %d px' % (h*w))
for st,name in ((3,'M+Y cells'),(0,'blank-sibling cells')):
    print(f'\n== {name}')
    for train_name,train_sel in (('certified tiles',np.isin(band,['cert-edge','cert-healthy'])),('marginal+live open',np.isin(band,['marginal','live']))):
        tr=train_sel&(sib==st); te=(band=='dead')&(sib==st)
        if tr.sum()<500 or te.sum()<500: continue
        line=[]
        for fname,X in (('box',box[:,None]),('rings',rings),('patch',flat)):
            f=fit_lda(X[tr],c[tr],lam=1e-2 if fname!='box' else 0.0); s=apply(X[te],f)
            line.append(f"{fname}: err {err(s,c[te]):.3f} AUC {auc(-s if fname=='box' else s,c[te]) if fname!='box' else auc(-s,c[te]):.3f}")
        print(f'   train {train_name:20s} -> test dead band (n={te.sum()}):  '+' | '.join(line))
    # within dead band, cross-validated over tiles (even ty train, odd ty test and vice versa)
    dead=(band=='dead')&(sib==st); res=collections.defaultdict(list)
    for parity in (0,1):
        tr=dead&(ty%2==parity); te=dead&(ty%2!=parity)
        for fname,X in (('box',box[:,None]),('rings',rings),('patch',flat)):
            f=fit_lda(X[tr],c[tr],lam=1e-2 if fname!='box' else 0.0); s=apply(X[te],f); res[fname].append(err(s,c[te]))
    print('   within dead band, tile-parity CV:   '+' | '.join(f"{k}: err {np.mean(v):.3f}" for k,v in res.items()))
    # by context, dead band, patch vs box (CV)
    dead=(band=='dead')&(sib==st)
    for fname,X in (('box',box[:,None]),('patch',flat)):
        s_all=np.full(n,np.nan)
        for parity in (0,1):
            tr=dead&(ty%2==parity); te=dead&(ty%2!=parity); f=fit_lda(X[tr],c[tr],lam=1e-2 if fname!='box' else 0.0); s_all[te]=apply(X[te],f)
        parts=[]
        for k0,k1 in ((0,2),(2,4),(4,6),(6,9)):
            q=dead&(ctx>=k0)&(ctx<k1)
            if q.sum()>200: parts.append(f"ctx{k0}-{k1-1}: {err(s_all[q],c[q]):.3f}")
        print(f'   {fname:5s} by C-neighbour count (dead, CV): '+'  '.join(parts))
# what does the discriminant look like for M+Y? (radial profile of the weight vector)
tr=(band=='dead')&(sib==3); f=fit_lda(flat[tr],c[tr],lam=1e-2); wmap=f[2].reshape(h,w)
prof=[wmap[(rr>=r0)&(rr<r1)].mean() for r0,r1 in ((0,2),(2,4),(4,6),(6,8),(8,10),(10,13))]
print('\nM+Y patch discriminant, mean weight by radius (px) 0-2,2-4,4-6,6-8,8-10,10-13:', ' '.join(f'{v:+.4f}' for v in prof))
tr=(band=='dead')&(sib==0); f=fit_lda(flat[tr],c[tr],lam=1e-2); wmap=f[2].reshape(h,w)
prof=[wmap[(rr>=r0)&(rr<r1)].mean() for r0,r1 in ((0,2),(2,4),(4,6),(6,8),(8,10),(10,13))]
print('blank-sibling patch discriminant, same:                                 ', ' '.join(f'{v:+.4f}' for v in prof))
# mean patches: CMY vs MY in the dead band, radial profile of the red channel
for st,nm in ((3,'M+Y'),(0,'blank')):
    for cb in (1,0):
        q=(band=='dead')&(sib==st)&(c==cb); mp=P[q].mean(0)
        prof=[mp[(rr>=r0)&(rr<r1)].mean() for r0,r1 in ((0,2),(2,4),(4,6),(6,8),(8,10),(10,13))]
        print(f'mean red profile dead {nm:5s} C={cb}:', ' '.join(f'{v:.3f}' for v in prof))
