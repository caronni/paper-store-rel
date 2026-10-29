"""Read-only system-lens numbers for the low-rung question (2026-09-30)."""
import math, time
from fractions import Fraction
import numpy as np
from holo.core.column_groups import column_groups
from holo.core import capacity
from holo.core.ldpc.construct import LADDER, load_code
from holo.core.ldpc.decode import decode
from holo.format.envelope import OVERHEAD_BYTES

CRC = 32
TILES = 53 * 37                      # 1961
FIELD_MM2 = 3392 * 2368 * (25.4 / 300) ** 2
MEDIA_MM2 = 210 * 297
print(f"field area 53x37@c2 = {FIELD_MM2:.1f} mm2; A4 media = {MEDIA_MM2} mm2")

def rung_name(k): return f"r{k/4096:.3f}".replace("0.", "0")
def width(k, p): return k - p - 33         # symbol width = user_bits - 1

# ---------- 1. column groups at p120 ----------
print("\n== 1. column groups at p120 (S = k - p - 33) ==")
trips = {
 "r0700x0700x0547 (ruled)": (2880, 2880, 2240),
 "r0850x0850x0775 (ruled)": (3520, 3520, 3200),
 "r0700x0700x0313": (2880, 2880, 1280),
 "r0700x0700x0391": (2880, 2880, 1600),
 "r0850x0850x0391": (3520, 3520, 1600),
 "r0850x0850x0313": (3520, 3520, 1280),
 "r0547x0547x0313": (2240, 2240, 1280),
 "r0547x0391x0313": (2240, 1600, 1280),
 "r0700x0391x0313": (2880, 1600, 1280),
 "r0700x0700x0625": (2880, 2880, 2560),
 "r0547x0547x0391": (2240, 2240, 1600),
}
hdr = "triplet | widths | Z | carried | spare/site | dead-Y ceil | any-one ceil | fountain bits/site | uniform@heavy | uniform@light"
print(hdr)
cg_of = {}
for name, ks in trips.items():
    p = 120
    w = tuple(width(k, p) for k in ks)
    cg = column_groups(w)
    cg_of[name] = (ks, cg)
    fb = sum(cg.carried) * Fraction(cg.symbol_bits, cg.n_groups)   # mean carried bits per site
    print(f"{name} | {w} | {cg.n_groups} | {cg.carried} | {float(cg.spare_bits_per_site):.2f} | "
          f"{cg.plane_tier_ceiling(2)} | {cg.any_plane_ceiling} | {float(fb):.1f} | {3*max(w)} | {3*min(w)}")

# ---------- 2. capacity ----------
print("\n== 2. capacity, 53x37 (1961 tiles), A4-4mm field ==")
def k_bytes(k, p, q, n_pages=1):
    s = width(k, p)            # symbol bits (user_bits - 1 metadata)
    K = capacity.max_k_for_pages(TILES, n_pages, q, n_streams=1)
    return K, s, max(0, (K * s) // 8 - OVERHEAD_BYTES)
def cmy8_bytes(ks, p, q, n_pages=1):
    w = tuple(width(k, p) for k in ks)
    cg = column_groups(w)
    frac = capacity.q_fraction(q)
    tier_ok = frac <= cg.any_plane_ceiling
    K = capacity.pooled_max_k_for_pages(TILES, n_pages, q, n_streams=3,
                                         enforce_plane_tier=tier_ok, groups=cg)
    k_meta = K // 3
    agg = 3 * max(w)
    return K, cg, tier_ok, max(0, (k_meta * agg) // 8 - OVERHEAD_BYTES)

print("K family c2 p100 (control: CLI r0547 q=0.8 -> 408722; r0700 -> 532882)")
print("k | rung | user/tile | S | q | K_src | bytes | field b/mm2 | media b/mm2")
for k in (1024, 1280, 1600, 2240, 2560, 2880, 3200, 3520):
    for q in (0.5, 0.8):
        K, s, b = k_bytes(k, 100, q)
        print(f"{k} | {rung_name(k)} | {k-CRC-100} | {s} | {q} | {K} | {b} | {b*8/FIELD_MM2:.1f} | {b*8/MEDIA_MM2:.1f}")

print("\ncmy8 c2 p120 (control: CLI r0547 q=0.8 -> 1223206; r0700 -> 1598326; r0850 -> 1973446; 0700x0700x0547 -> 1470498; 0850x0850x0775 -> 1907790)")
print("triplet | q | Z | tier enforced | K_total | bytes | field b/mm2 | media b/mm2 | vs uniform heavy | vs uniform light")
uni = {}
for k in (1024, 1280, 1600, 2240, 2560, 2880, 3200, 3520):
    for q in (0.5, 0.8):
        K, cg, ok, b = cmy8_bytes((k, k, k), 120, q)
        uni[(k, q)] = b
        print(f"uniform {rung_name(k)} x3 | {q} | 1 | {ok} | {K} | {b} | {b*8/FIELD_MM2:.1f} | {b*8/MEDIA_MM2:.1f} | - | -")
for name, ks in trips.items():
    for q in (0.5, 0.8):
        K, cg, ok, b = cmy8_bytes(ks, 120, q)
        print(f"{name} | {q} | {cg.n_groups} | {ok} | {K} | {b} | {b*8/FIELD_MM2:.1f} | {b*8/MEDIA_MM2:.1f} | "
              f"{b/uni[(max(ks),q)]:.3f} | {b/uni[(min(ks),q)]:.3f}")

# ---------- 4. edges / CPU ----------
print("\n== 4. edge counts (info edges = 64*(heavy_deg*nh + 3*(kb-nh)); parity 2m-1) ==")
def edges(k, heavy_deg=10):
    kb = k // 64; m = 4096 - k; mb = m // 64
    nh = round(0.30 * kb)
    info = 64 * (heavy_deg * nh + 3 * (kb - nh))
    par = 2 * m - 1
    cap = math.ceil((3*(kb-nh) + heavy_deg*nh) / mb) + 1
    return kb, mb, nh, info, par, info + par, cap
ref = edges(2240, 10)[5]
print("k | kb | mb | nh | heavy_deg | info edges | parity edges | E | mean chk deg | rule-d cap | E/E(r0547) | loaded E (data json)")
for k, hd in ((1024,10),(1280,10),(1600,10),(2240,10),(2560,10),(2880,10),(3200,8),(3520,6)):
    kb, mb, nh, info, par, E, cap = edges(k, hd)
    if k == 2240: ref = E
    loaded = ""
    for rid, spec in LADDER.items():
        if spec.k_bits == k and spec.heavy_deg == hd:
            loaded += f"{rid}:{load_code(rid).n_edges} "
    print(f"{k} | {kb} | {mb} | {nh} | {hd} | {info} | {par} | {E} | {E/(4096-k):.2f} | {cap} | {E/ref:.3f} | {loaded}")

print("\nmin-sum timing check on existing codes (random LLR, 60 iters forced no-converge; 5 reps):")
rng = np.random.default_rng(0)
for rid in ("r0547", "r0700", "r0850"):
    code = load_code(rid)
    llr = rng.normal(0, 0.3, 4096)   # garbage -> runs the full budget
    t = []
    for _ in range(5):
        t0 = time.perf_counter(); decode(llr, rid, max_iters=60, alpha=0.8); t.append(time.perf_counter() - t0)
    print(f"  {rid}: E={code.n_edges} median {np.median(t)*1e3:.1f} ms -> {np.median(t)*1e3/code.n_edges*1e6:.2f} ns/edge-iter*60")

# ---------- 5. p-axis ----------
print("\n== 5. user bits per tile, and Z at p120 vs p300 for low-rung triplets ==")
for k, p in ((2240,120),(2240,300),(1600,120),(1280,120),(1024,120)):
    print(f"k={k} p={p}: user bits {k-CRC-p}, symbol {width(k,p)}")
for name, ks in trips.items():
    row = []
    for p in (120, 172, 244, 300):
        cg = column_groups(tuple(width(k, p) for k in ks))
        row.append(f"p{p}: Z{cg.n_groups} {cg.carried} spare {float(cg.spare_bits_per_site):.1f}")
    print(f"{name}: " + " | ".join(row))
