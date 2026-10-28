"""JOB B step 3 — price the ENCODE-AT-PROPOSE card from measured numbers.

Inputs are the profiler-FREE counters run (`cards-commitcost.json`) plus
the two unprofiled gen-clean anchors already on the record:
  serial 209 s (busy 112.5 s), W4 145 s   [MEASUREMENTS, post-BM row]

The model, deliberately crude and stated as such:
  T  = S + F                serial wall = main-thread-only + fire-side
  S  = T - fire_busy
  k  = F / (T_W4 - S)       the MEASURED fire-side scaling at W4
                            (absorbs GIL, switching tax, everything)
  card removes X from S (and, for the deleted dead digest, from F too)
  T' = S' + F' ; T'_W = S' + F'/k
"""
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
cpu, n = data["cpu"], data["n"]

T_SERIAL = 209.67          # gen-clean serial, post-cards, UNPROFILED
BUSY_SERIAL = 112.5        # fire busy in that run
T_W4 = 145.26              # gen-clean W4, post-cards, UNPROFILED

S = T_SERIAL - BUSY_SERIAL
F = BUSY_SERIAL
k = F / (T_W4 - S)
print(f"anchors: serial {T_SERIAL:.1f}s = S {S:.1f}s (main-thread-only) "
      f"+ F {F:.1f}s (fire side); W4 {T_W4:.1f}s => measured fire scaling "
      f"k = {k:.2f}x  (ceiling today {T_SERIAL / T_W4:.2f}x)")

# scale the counters run's own numbers onto the unprofiled anchor: the
# counters run has its own wall, so report both raw and scaled.
own_wall = data["wall"]
scale = T_SERIAL / own_wall
print(f"counters run wall {own_wall:.1f}s vs anchor {T_SERIAL:.1f}s "
      f"=> instrumentation factor {own_wall / T_SERIAL:.3f}x "
      f"(costs below are scaled by {scale:.3f})")
print()

wall_enc = cpu.get("digest_json.wall", 0.0) + cpu.get("batch.canonical", 0.0) * 0.5
fire_enc = cpu.get("fire.batch_id", 0.0)
commits = data["commits"]
fires = data["fires"]
print(f"MEASURED (raw thread-CPU seconds, serial run, {commits} commits / "
      f"{fires} fires):")
for tag in sorted(cpu, key=lambda t: -cpu[t]):
    print(f"  {cpu[tag]:8.2f} s  n={n[tag]:<7} "
          f"percall {1e3 * cpu[tag] / max(n[tag], 1):7.3f} ms  {tag}")
print()
print(f"  merge settle: same-object {data['merge_same_object']} · "
      f"new-object-but-EQUAL {data['merge_equal']} · "
      f"VALUE-DIFFERS {data['merge_differs']}")
reuse_ok = data["merge_same_object"] + data["merge_equal"]
total_settle = reuse_ok + data["merge_differs"]
print(f"  => the propose-side id is VALID for {reuse_ok}/{total_settle} "
      f"= {100 * reuse_ok / max(total_settle, 1):.1f}% of settles")
print()

# ---- the card ------------------------------------------------------------
# arm 1: delete the dead per-fire batch_id (nothing in production reads it)
# arm 2: wall reuses the propose-side id when the settle preserved the VALUE
X_dead = fire_enc * scale
X_wall = (cpu.get("digest_json.wall", 0.0)
          + cpu.get("wall._settle_merges", 0.0) * 0.0) * scale
frac_reuse = reuse_ok / max(total_settle, 1)
X_wall_eff = X_wall * frac_reuse

for tag, x_s, x_f in (("arm 1 — delete the dead per-fire batch_id",
                       0.0, X_dead),
                      ("arm 2 — wall reuses the propose-side id",
                       X_wall_eff, 0.0),
                      ("arms 1+2 (arm 2 keeps the digest, moves it)",
                       X_wall_eff, X_dead)):
    S2, F2 = S - x_s, F - x_f
    T2 = S2 + F2
    T2_W4 = S2 + F2 / k
    print(f"{tag}:")
    print(f"    serial {T_SERIAL:.1f} -> {T2:.1f} s ({T_SERIAL / T2:.3f}x); "
          f"W4 {T_W4:.1f} -> {T2_W4:.1f} s; "
          f"thread ceiling {T_SERIAL / T_W4:.2f}x -> {T2 / T2_W4:.2f}x")
print()
print(f"per-commit CPU on the wall today: "
      f"{1e3 * cpu.get('wall.CommitEngine.apply', 0) / max(commits, 1):.2f} ms "
      f"(CommitEngine.apply), "
      f"{1e3 * cpu.get('wall._apply(total)', 0) / max(commits, 1):.2f} ms "
      f"including the close consult")
