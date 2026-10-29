# v2-lab-strong2: a.py's integer tricks applied to strong2 (2026-10-20, this container)

Labels: MEASURED (run here), RECORDED (repo file), ESTIMATE. Timing walls ran under load 4-5.5
on 4 CPUs, so they are noisy; the coder-only CPU numbers (process_time) are the solid comparison.

## Baselines
- R2: receiver_arch.py minified-g 24,460 B, cm2 (primer r.py) 10,599 = 9 B spare (MEASURED here; matches RECORDED).
- strong2 on this checkout's T1 prefixes: 1 MB 255,569 B, 2 MB 492,414 B (MEASURED). The owner's prefixes
  were RECORDED at 245,555 and 470,169; the trees differ.
- Typed: a.py 826 + 2,876 glyphs + 48x4 = 3,894 (MEASURED; matches RECORDED).

## (1) strong2-rans (big-int rANS on the 12-bit p, slot = x % 4096, y=1 slots first)
Replacement in receiver_arch.py's unz: head `n = int.from_bytes(z[4:12], 'big')`;
`x = int.from_bytes(z[16:], 'big')` replaces `x1 = x2 = x = kk = ` (it must come AFTER the
`for x in range(4096)` squash loop, which reuses x; the first try had that bug, and the round trip caught it). CODER (form C):
    o = x % 4096
    y = o < p
    x = x // 4096 * (p if y else 4096 - p) + o - p + p * y
- R2 (MEASURED): A 10,568 / B (if/else) 10,565 / C 10,566 => saves 31-34 B. Minified bytes -53 to -74.
- Bytes (MEASURED): 1 MB rans 255,436 (-133 vs the AC; ideal 255,430). The 32-bit coder's precision loss is 0.05 %.
- Decode, coder only (MEASURED CPU us/byte): rANS 75 (64K), 132 (128K), 241 (256K), so the per-byte cost grows
  linearly with n and the total is quadratic. The AC is 2.1 us/byte at every n.
  1 MB is about 960 us/byte, T1 about 23 h of coder alone (ESTIMATE). Full decode walls: rans 256K 108 s vs strong2 39 s.
- BLOCK RESET (x restarted every 2^B output bytes, model continuous, each block = 3-byte length + its integer):
  inserted before `for j in range(8):`
        if i % 65536 == 8:
            o = kk + 3 + int.from_bytes(s[kk:kk + 3], 'big')
            x, kk = int.from_bytes(s[kk + 3:o], 'big'), o
  Bytes at 1 MB: blk14 255,725 (+156), blk16 255,504 (-65), blk18 255,452 (-117). At 2 MB: blk16 492,286 (-128). All MEASURED.
  Coder CPU: blk14 15.8, blk16 54.5 (1 MB) / 51.8 (2 MB), blk18 203 us/byte (MEASURED, linear).
  The real blk16 1 MB decode round-trips in 297 s wall (strong2 315 s, same noisy box).
  R2: 10,598 (C form) / 10,603 (B form) => the saving is GONE (-1..+4 B).
- Verdict: the one-integer coder saves about 33 B of R2 but is quadratic, so it is unusable at archive scale.
  The linear block form costs exactly the bytes it saved. Its archive effect is a wash
  (T1 blk16 about -240 B, blk14 about +1.8 KB, ESTIMATE; 15 pages either way). Its decode cost is +10-35 %.
  It is not worth taking.

## (2) strong2-exact (the nibble buckets replaced by ONE dict with exact keys; mixers/APMs kept)
    X = [c0, 256 + c * 256 + c0] + [(H[q] * 16 + q << 8 | c0) << 17 for q in range(2, 9)]
    S = [st[T.get(t, 32896) >> 6] for t in X] + [st[U[mi] >> 6]]
    ...  pt = T.get(t, 32896); pt, nt = pt >> 4, pt & 15
(the bucket search, the T/Z memoryviews, A, E, B and cn are deleted). Variants: exact2 also makes the match table a dict keyed by h (order 7).
exact3 keys it by h % 2**48, which is what strong2's hash h*G>>22 & (2^26-1) actually depends on (order 6).
- R2 (MEASURED): exact 10,458 (-141), exact3 10,428, exact2 10,421 (-178); with the rANS coder 10,407 / 10,384 / 10,380 (-219).
- Bytes (MEASURED): 256K: s2 75,208, exact 75,197, exact3 75,217, exact2 75,270.
  1 MB: s2 255,569, exact 255,542 (-27 = collisions cost 0.01 %), exact2 255,862 (+293: the order-7 match is a model change, not exactness).
- Memory (MEASURED decode RSS): exact2 171 MB (8K), 621 MB (256K), 1,326 MB (1 MB). strong2 is 1,035 MB fixed.
  T1 9.5 MB: 5-11 GB (ESTIMATE, power-law vs linear fit). The record's cm2 exact dict took 25 GB (RECORDED).
- R2-size payloads (MEASURED, primed as enc(r.py+x)-enc(r.py)): monolith strong2 10,319 = exact 10,319, b.py 15,173 vs 15,171.
  At these sizes there are no collisions, so exactness buys nothing in ratio.
- Verdict: in R2 bytes the exact dict saves 141-219 B. For the archive it is a loss: memory grows with n
  (unbounded, several GB at T1) for -0.01 % of bytes. Not for the archive.

## (3) Ship the decoder inside the archive (exec route), measured on receiver_arch.py here
- exec route R2 = 9,655 (240 B over the receiver; RECORDED 214 was on measure_r2's base) = 953 B spare (MEASURED).
- What the spare buys (MEASURED): +import os 9,682; +os + the untrimmed messages ('archive of %d bytes', long CRC message) and the
  NAME_OLD path form 9,709 (899 spare); flat + untrimmed 9,682. All stay at 2 pages with ~900 B to spare.
- The 'd copy' route (the monolith carries a.py's d() and the archive carries the decoder cm2-packed):
  R2 9,825 (+170, because the minifier renames d's locals so the primer match is lost). It saves only about 950 B of archive.
- Archive cost of the shipped source (MEASURED, minified standalone): strong2 2,133 (RECORDED reproduced) / receiver form 2,075.
  ransB 2,024, rblk16C 2,076, exact2 1,676, exact2+rans 1,611. cm2-packed strong2 is 1,127.
  Each extra 1 KB of decoder source costs 0.06 % of T1's archive (15 pages: about 6.3 KB of headroom, RECORDED limit).

## (4) cmmix-exact as the TYPED decoder (cmx_d.txt, a.py-style, round-trip PASS)
- d() 767 chars vs a.py's 423; new a.py 1,170 chars. typed_reader.bin 1,796.9 B ideal / 1,798.0 exact => 2,877 glyphs, 48 lines.
- TOTAL TYPED 4,239 = +345 vs 3,894 (MEASURED). At 4.5 KB the mixer learns too little to beat cm2's count mixing.
- Lab screens (MEASURED ideal): plain cmmix variants 1,812-1,885 B. An APM on cm2's p is at best -5 B, for >= 100 chars (ESTIMATE).
- Side effect if d() became cmx: the R2 monolith would be 10,463 B ideal (-136 vs cm2's 10,599), the receiver 9,300. Still 2 pages.
