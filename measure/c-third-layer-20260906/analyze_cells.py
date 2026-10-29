import sys, numpy as np, collections
d = np.load(sys.argv[1])
c, m, yb = d['c'].astype(int), d['m'].astype(int), d['yb'].astype(int)
R, G, B, llr, ctx, band, lane, level = d['R'], d['G'], d['B'], d['llr'], d['ctx'], d['band'], d['lane'], d['level']
state = c + 2 * m + 4 * yb
NAMES = ['W', 'C', 'M', 'CM', 'Y', 'CY', 'MY', 'CMY']
grp = np.where(np.isin(band, ['dead']), 'dead', np.where(np.isin(band, ['marginal', 'live']), 'open-other', 'certified'))
print('cells', len(R), ' by group', dict(collections.Counter(grp)), ' levels', dict(collections.Counter(level.tolist())))
print('\n1. RED channel by true state (mean / sd / p10 / p50 / p90), per group')
for g in ('dead', 'open-other', 'certified'):
    print(f'-- {g}')
    for s in range(8):
        pick = (grp == g) & (state == s)
        if pick.sum() < 50: continue
        v = R[pick]; q = np.percentile(v, [10, 50, 90])
        print(f'   {NAMES[s]:4s} n={pick.sum():7d}  R mean {v.mean():7.3f} sd {v.std():6.3f}  p10 {q[0]:7.3f} p50 {q[1]:7.3f} p90 {q[2]:7.3f}   G {G[pick].mean():7.3f}  B {B[pick].mean():7.3f}')

def auc(pos, neg):
    allv = np.concatenate([pos, neg]); ranks = allv.argsort().argsort().astype(float) + 1
    rp = ranks[:len(pos)].sum(); return (rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
def bayes_err_1d(pos, neg):
    # equal-prior error of the best single threshold on the pooled sample
    allv = np.concatenate([pos, neg]); lab = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))])
    o = allv.argsort(); lab = lab[o]; cp = np.cumsum(lab); cn = np.cumsum(1 - lab)
    # C is DARK in R: predict C when value <= t  -> errors = neg below t + pos above t
    err = (cn + (len(pos) - cp)) / len(allv); err2 = (cp + (len(neg) - cn)) / len(allv)
    return min(err.min(), err2.min())
def qda_err(X1, X0):
    # 3-channel quadratic discriminant, fit on even rows, test on odd rows
    def fit(X): return X.mean(0), np.cov(X.T) + 1e-9 * np.eye(X.shape[1])
    def ll(X, mu, S): 
        Si = np.linalg.inv(S); r = X - mu; return -0.5 * np.einsum('ni,ij,nj->n', r, Si, r) - 0.5 * np.log(np.linalg.det(S))
    tr1, te1, tr0, te0 = X1[::2], X1[1::2], X0[::2], X0[1::2]
    m1, S1 = fit(tr1); m0, S0 = fit(tr0)
    e1 = (ll(te1, m1, S1) < ll(te1, m0, S0)).mean(); e0 = (ll(te0, m0, S0) < ll(te0, m1, S1)).mean()
    return 0.5 * (e1 + e0)
print('\n2. Separability of the C decision, per sibling state and group: AUC(R), best-threshold error(R), QDA error(RGB), arm error (sign of LLR)')
for g in ('dead', 'open-other', 'certified'):
    print(f'-- {g}')
    for sib, name in ((0, 'siblings blank'), (1, 'M only'), (2, 'Y only'), (3, 'M+Y')):
        pick = (grp == g) & ((m + 2 * yb) == sib)
        pos, neg = pick & (c == 1), pick & (c == 0)
        if pos.sum() < 100 or neg.sum() < 100: continue
        X1 = np.stack([R[pos], G[pos], B[pos]], 1); X0 = np.stack([R[neg], G[neg], B[neg]], 1)
        ok = pick & np.isfinite(llr)
        arm_err = ((llr[ok] > 0) != (c[ok] == 1)).mean()
        print(f'   {name:15s} n={pick.sum():7d}  AUC(R) {auc(-R[pos], -R[neg]):.4f}  thr-err(R) {bayes_err_1d(R[pos], R[neg]):.4f}  QDA(RGB) {qda_err(X1, X0):.4f}  arm {arm_err:.4f}')
print('\n3. M+Y cells only: does the red channel of CMY cells look bimodal?  (fraction of CMY cells above the MY-cell 10th/25th/50th percentile of R)')
for g in ('dead', 'open-other', 'certified'):
    my = (grp == g) & (m == 1) & (yb == 1)
    cmy, mo = R[my & (c == 1)], R[my & (c == 0)]
    if len(cmy) < 100: continue
    q = np.percentile(mo, [10, 25, 50])
    print(f'   {g:11s} CMY n={len(cmy)}: above MY-p10 {(cmy > q[0]).mean():.3f}  above MY-p25 {(cmy > q[1]).mean():.3f}  above MY-p50 {(cmy > q[2]).mean():.3f}   | MY below CMY-p90 {(mo < np.percentile(cmy, 90)).mean():.3f}')
print('\n4. M+Y cells: arm error by same-plane context (number of C-inked 8-neighbours), dead band vs certified')
for g in ('dead', 'certified'):
    my = (grp == g) & (m == 1) & (yb == 1) & np.isfinite(llr)
    line = []
    for k in range(9):
        p = my & (ctx == k)
        if p.sum() < 200: continue
        line.append(f'ctx{k}:{((llr[p] > 0) != (c[p] == 1)).mean():.3f}(n={p.sum()})')
    print(f'   {g:11s}', ' '.join(line))
print('\n5. LLR calibration on the dead band, by sibling state: claimed error vs measured error in |LLR| bins; and information per cell as given vs after a per-state Platt refit')
def info_bits(L, b): return 1 - np.log2(1 + np.exp(-np.abs(np.clip(L * (2 * b - 1), -50, 50)) * np.sign(L * (2 * b - 1)) ))
def info_terms(L, b):
    s = np.clip(L * (2 * b - 1), -60, 60); return 1 - np.log2(1 + np.exp(-s))
def platt(L, b):
    # fit a*L + c by simple grid on log-loss
    best = None
    for a in np.linspace(0.05, 2.0, 40):
        for cc in np.linspace(-1.0, 1.0, 21):
            s = np.clip((a * L + cc) * (2 * b - 1), -60, 60); ll = np.log1p(np.exp(-s)).mean()
            if best is None or ll < best[0]: best = (ll, a, cc)
    return best[1], best[2]
for g in ('dead', 'open-other'):
    print(f'-- {g}')
    tot_given = 0.0; tot_refit = 0.0; tot_n = 0
    for sib, name in ((0, 'blank'), (1, 'M'), (2, 'Y'), (3, 'M+Y')):
        pick = (grp == g) & ((m + 2 * yb) == sib) & np.isfinite(llr)
        L = llr[pick]; b = (c[pick] == 1).astype(float)
        if len(L) < 500: continue
        given = info_terms(L, b).mean()
        a, cc = platt(L, b); refit = info_terms(a * L + cc, b).mean()
        bins = [0, 1, 2, 4, 8, 100]; parts = []
        for lo, hi in zip(bins[:-1], bins[1:]):
            q = (np.abs(L) >= lo) & (np.abs(L) < hi)
            if q.sum() < 100: continue
            claimed = (1 / (1 + np.exp(np.abs(L[q])))).mean(); meas = ((L[q] > 0) != (b[q] > 0)).mean()
            parts.append(f'|L|{lo}-{hi}: claim {claimed:.3f} meas {meas:.3f}')
        print(f'   {name:5s} n={len(L):7d} info/cell given {given:.3f} refit {refit:.3f} (a={a:.2f},c={cc:+.2f})  ', ' ; '.join(parts))
        tot_given += given * len(L); tot_refit += refit * len(L); tot_n += len(L)
    if tot_n: print(f'   ALL   info/cell given {tot_given/tot_n:.3f} refit-per-state {tot_refit/tot_n:.3f}  (r0850 needs ~0.85 active-bit-equivalent)')
print('\n6. Per capture level: M+Y cells, AUC(R) of the C decision, dead band')
for lv in sorted(set(level.tolist())):
    my = (grp == 'dead') & (m == 1) & (yb == 1) & (level == lv)
    pos, neg = my & (c == 1), my & (c == 0)
    if pos.sum() < 100: continue
    print(f'   level {lv}: n={my.sum()}  AUC(R) {auc(-R[pos], -R[neg]):.4f}  thr-err {bayes_err_1d(R[pos], R[neg]):.4f}   siblings-blank AUC {auc(-R[(grp=="dead")&(m==0)&(yb==0)&(level==lv)&(c==1)], -R[(grp=="dead")&(m==0)&(yb==0)&(level==lv)&(c==0)]):.4f}')
