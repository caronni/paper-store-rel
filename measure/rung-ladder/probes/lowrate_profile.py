"""Read-only analytic profile of the frozen e-IRA recipe at candidate low-rate k."""
import math
N=4096; Z=64; HEAVY_FRAC=0.30
def prof(k, heavy_deg=10):
    kb=k//Z; mb=(N-k)//Z; m=N-k
    nh=round(HEAVY_FRAC*kb)
    E=3*(kb-nh)+heavy_deg*nh          # info block-edges
    mean=E/mb
    cap=math.ceil(E/mb)+1
    p0=math.exp(-mean)                # Poisson approx: block row with zero info edges
    # bit-level check degree = 2 (accumulator; row0 has 1) + info edges of its block row
    return dict(k=k,rate=k/N,kb=kb,mb=mb,nh=nh,nh_frac=nh/kb,E=E,mean_info_per_blockrow=round(mean,2),
                cap=cap,p_zero_rows=round(p0,4),exp_zero_blockrows=round(p0*mb,2),
                deg2_var_frac=round(m/N,3),chk_deg_range=f"2..{2+cap}",
                min_check_deg_nominal=2+math.floor(mean)-2, info_cols_per_check_mean=round(mean,2))
for k in (1024,1216,1280,1600,1664,1920,2240,2560,2880,3200,3520):
    hd={3200:8,3520:6}.get(k,10)
    print(prof(k,hd))
