import sys, json, numpy as np
from paperholo import ldpc
k=int(sys.argv[1]); mode=sys.argv[2]; trials=100
spec=ldpc.LdpcSpec(f"x{k}h10f0.3", k); code=ldpc.build_code(spec); n=4096; m=n-k
def hl(b,mag=4.0): return mag*(2.0*b.astype(float)-1.0)
out={"k":k,"mode":mode}
if mode=="iters":
    res=[]
    for p in (0.12,0.13,0.14,0.15):
        for mi in (60,150,300):
            f=0
            for t in range(trials):
                g=np.random.default_rng(90_000+t); info=g.integers(0,2,k).astype(np.uint8)
                cw=ldpc.encode(info,spec); rx=cw^(g.random(n)<p)
                hard,ok,it=ldpc.decode(hl(rx),spec,max_iters=mi)
                f+=int(not(ok and np.array_equal(hard,cw)))
            res.append(dict(p=p,max_iters=mi,bler=f/trials))
    out["res"]=res
else:
    S=120
    # shortened: info tail S known-0 (-inf), transmit [0,k-S)+[k,n)
    # punctured: all k info transmitted, S parity positions spread evenly over the chain NOT transmitted (llr 0)
    punct=np.round(np.linspace(0,m-1,S+2)[1:-1]).astype(int)+k
    res=[]
    for p in (0.10,0.115,0.13,0.14,0.15):
        fs=fp=0
        for t in range(trials):
            g=np.random.default_rng(91_000+t)
            info=g.integers(0,2,k).astype(np.uint8); info[k-S:]=0
            cw=ldpc.encode(info,spec); flip=g.random(n)<p
            # shortened
            llr=hl(cw^flip); llr[k-S:k]=-np.inf
            hard,ok,_=ldpc.decode(llr,spec); fs+=int(not(ok and np.array_equal(hard,cw)))
            # punctured (same channel draw, random info everywhere)
            info2=g.integers(0,2,k).astype(np.uint8); cw2=ldpc.encode(info2,spec)
            llr2=hl(cw2^flip); llr2[punct]=0.0
            hard,ok,_=ldpc.decode(llr2,spec); fp+=int(not(ok and np.array_equal(hard,cw2)))
        res.append(dict(p=p,bler_shorten120=fs/trials,bler_puncture120=fp/trials))
    out["res"]=res
print(json.dumps(out))
