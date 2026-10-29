"""The configs measured (harness data for zp_enc.py).

min / mid / max: Matt Mahoney's classic configs as libzpaq 7.15 carries
them compiled (Compressor::startBlock(level 1/2/3), libzpaq.cpp 2793-2832:
'Model 1 - min.cfg', 'Model 2 - mid.cfg', 'Model 3 - max.cfg').  The text
here is OUR disassembly of those bytes (zp_enc.disassemble, raw jumps);
test_zp.py recompiles it and checks it against the upstream bytes.

level3 / level4 / level5: what libzpaq's compressBlock() generates for
methods 3, 4, 5 on a text block (zp_enc.method_for_level + make_config).

ours: written for this study to approach strong2 (see README.md).

The min / mid / max text is a disassembly of models by Matt Mahoney as
libzpaq 7.15 carries them (public domain, Unlicense); the level and ours
configs are this study's."""

CFG = {}

CFG["min"] = """comp 1 2 0 0 2
  0 icm 16
  1 isse 19 0
hcomp
  *b=a a=0 d=0 hash b-- hash *d=a d++
  b-- hash b-- hash *d=a halt
end
"""

CFG["mid"] = """comp 3 3 0 0 8
  0 icm 5
  1 isse 13 0
  2 isse 17 1
  3 isse 18 2
  4 isse 18 3
  5 isse 19 4
  6 match 22 24
  7 mix 16 0 7 24 255
hcomp
  c++ *c=a b=c a=0 d= 1 hash *d=a b--
  d++ hash *d=a b-- d++ hash *d=a b--
  d++ hash *d=a b-- d++ hash *d=a b--
  d++ hash b-- hash *d=a d++ a=*c a<<= 8
  *d=a halt
end
"""

CFG["max"] = """comp 5 9 0 0 22
  0 const 160
  1 icm 5
  2 isse 13 1
  3 isse 16 2
  4 isse 18 3
  5 isse 19 4
  6 isse 19 5
  7 isse 20 6
  8 match 22 24
  9 icm 17
  10 isse 19 9
  11 icm 13
  12 icm 13
  13 icm 13
  14 icm 14
  15 mix 16 0 15 24 255
  16 mix 8 0 16 10 255
  17 mix2 0 15 16 24 0
  18 sse 8 17 32 255
  19 mix2 8 17 18 16 255
  20 sse 16 19 32 255
  21 mix2 0 19 20 16 0
hcomp
  c++ *c=a b=c a=0 d= 2 hash *d=a b--
  d++ hash *d=a b-- d++ hash *d=a b--
  d++ hash *d=a b-- d++ hash *d=a b--
  d++ hash b-- hash *d=a b-- d++ hash
  *d=a b-- d++ a=*c a&~ 32 a> 64 jf 14 a< 91
  jf 10 d++ hashd d-- *d<>a a+=*d a*= 20 *d=a
  jmp 9 a=*d a== 0 jt 3 d++ *d=a d-- *d=0
  d++ d++ b=c b-- a=0 hash *d=a d++
  b-- a=0 hash *d=a d++ b-- a=0 hash
  *d=a d++ a=b a-= 212 b=a a=0 hash *d=a
  b<>a a-= 216 b<>a a=*b a&= 60 hashd d++ a=*c
  a<<= 9 *d=a d++ d++ d++ d++ d++ *d=a
  halt
end
"""

CFG["ours_v0"] = """(ours_v0, the first attempt: strong2's inputs as a ZPAQ model -- orders 0-4, 6, 7, a match on
 order 7, word and word bigram, the column (byte above, capped column),
 two sparse contexts; three mixers by order 0, 1 and hashed order 2,
 mixed again; SSE by order 1 and by hashed order 2)
comp 5 16 0 0 22
  0 icm 6
  1 isse 16 0
  2 isse 19 1
  3 isse 20 2
  4 isse 20 3
  5 isse 20 4
  6 isse 20 5
  7 match 22 24
  8 icm 18
  9 isse 19 8
  10 icm 18
  11 isse 18 10
  12 icm 17
  13 icm 17
  14 mix 16 0 14 24 255
  15 mix 8 0 14 24 255
  16 mix 16 0 14 24 255
  17 mix 0 14 3 24 0
  18 sse 16 17 32 255
  19 mix2 8 17 18 16 255
  20 sse 18 19 32 255
  21 mix2 0 19 20 16 0
hcomp
  c++ *c=a b=c a=0
  d= 1 hash *d=a b--
  d++ hash *d=a b--
  d++ hash *d=a b--
  d++ hash *d=a b--
  d++ hash b-- hash *d=a b--
  d++ hash *d=a
  d++ *d=a
  (word, and word bigram: 'w2' of libzpaq's makeConfig)
  a=*c a&= 223 a-= 65 a&= 255 a< 26 if
    d= 8 a=*d a*= 20 a+=*c a++ *d=a
    d++ a=*d a*= 20 a+=*c a++ *d=a
  else
    d= 8 a=*d d++ *d=a
    d= 8 *d=0
  endif
  (column: R0 = position of the last LF, R1 = the one before)
  a=*c a== 10 if a=r 0 r=a 1 a=c r=a 0 endif
  b=r 0 a=c a-=b a++ d=a
  b=r 1 a+=b b=r 0 a<b ifnot a=b endif
  b=a a=*b r=a 2
  a=d a> 40 if a= 40 endif
  d= 10 *d=0 hashd a=r 2 hashd
  d++ *d=0 hashd a=*c hashd
  (sparse: byte 2; bytes 3-4)
  d++ *d=0 b=c b-- a=*b hashd
  d++ *d=0 b-- a=*b hashd b-- a=*b hashd
  (mixer and SSE contexts)
  d= 14 a=*c a<<= 8 *d=a
  d++ *d=0
  d++ a=0 d= 2 a=*d d= 16 a>>= 24 a<<= 8 *d=a
  d= 18 a=*c a<<= 8 *d=a
  d= 20 a=0 d= 3 a=*d d= 20 a>>= 22 a<<= 8 *d=a
  halt
end
"""

# max + the column (byte above, capped column) as an ICM and an order-1 ISSE
# on it; M widened to 64 KB so the line above is still in the history.
CFG["maxcol"] = CFG["max"].replace("comp 5 9 0 0 22", "comp 5 16 0 0 24").replace("""  15 mix 16 0 15 24 255
  16 mix 8 0 16 10 255
  17 mix2 0 15 16 24 0
  18 sse 8 17 32 255
  19 mix2 8 17 18 16 255
  20 sse 16 19 32 255
  21 mix2 0 19 20 16 0""", """  15 icm 16
  16 isse 18 15
  17 mix 16 0 17 24 255
  18 mix 8 0 18 10 255
  19 mix2 0 17 18 24 0
  20 sse 8 19 32 255
  21 mix2 8 19 20 16 255
  22 sse 16 21 32 255
  23 mix2 0 21 22 16 0""").replace("""  a<<= 9 *d=a d++ d++ d++ d++ d++ *d=a
  halt""", """  (column: R0 = position of the last LF, R1 = the one before)
  a=*c a== 10 if a=r 0 r=a 1 a=c r=a 0 endif
  b=r 0 a=c a-=b a++ d=a
  b=r 1 a+=b b=r 0 a<b ifnot a=b endif
  b=a a=*b r=a 2
  a=d a> 40 if a= 40 endif
  d= 15 *d=0 hashd a=r 2 hashd
  d++ *d=0 hashd a=*c hashd
  d++ a=*c a<<= 9 *d=a
  d= 22 *d=a
  halt""").replace("a&= 60 hashd d++ a=*c\n", "a&= 60 hashd\n")

# ours: max.cfg grown for T1 -- orders 0-8 (o6 added), the column model of
# maxcol, tables sized for a 9.5 MB block, a full-byte order-1 mixer and SSE,
# and a third SSE stage on hashed order 2.
CFG["ours"] = """comp 5 16 0 0 27
  0 const 160
  1 icm 5
  2 isse 13 1
  3 isse 17 2
  4 isse 20 3
  5 isse 21 4
  6 isse 22 5
  7 isse 22 6
  8 isse 22 7
  9 match 22 24
  10 icm 19
  11 isse 21 10
  12 icm 16
  13 icm 16
  14 icm 16
  15 icm 16
  16 icm 18
  17 isse 19 16
  18 mix 17 0 18 24 255
  19 mix 8 0 19 10 255
  20 mix2 0 18 19 24 0
  21 sse 8 20 32 255
  22 mix2 8 20 21 16 255
  23 sse 17 22 32 255
  24 mix2 8 22 23 16 255
  25 sse 18 24 32 255
  26 mix2 0 24 25 16 0
hcomp
  (orders 1-8 in H2-H9: H9 is the match model's)
  c++ *c=a b=c a=0
  d= 2 hash *d=a b--
  d++ hash *d=a b--
  d++ hash *d=a b--
  d++ hash *d=a b--
  d++ hash *d=a b--
  d++ hash *d=a b--
  d++ hash *d=a b--
  d++ hash *d=a b--
  (word H10 and word bigram H11, max.cfg's code)
  d++ a=*c a&~ 32 a> 64 jf 14 a< 91
  jf 10 d++ hashd d-- *d<>a a+=*d a*= 20 *d=a
  jmp 9 a=*d a== 0 jt 3 d++ *d=a d-- *d=0
  (bytes 2, 3, 4 alone in H12-H14, max.cfg's H15 context)
  d++ d++ b=c b-- a=0 hash *d=a d++
  b-- a=0 hash *d=a d++ b-- a=0 hash
  *d=a d++ a=b a-= 212 b=a a=0 hash *d=a
  b<>a a-= 216 b<>a a=*b a&= 60 hashd
  (column: R0 = position of the last LF, R1 = the one before;
   H16 = byte above + column capped at 40, H17 = byte above + byte 1)
  a=*c a== 10 if a=r 0 r=a 1 a=c r=a 0 endif
  b=r 0 a=c a-=b a++ d=a
  b=r 1 a+=b b=r 0 a<b ifnot a=b endif
  b=a a=*b r=a 2
  a=d a> 40 if a= 40 endif
  d= 16 *d=0 hashd a=r 2 hashd
  d++ *d=0 hashd a=*c hashd
  (mixer and SSE contexts: byte 1 in H18 and H23, hashed order 2 in H25)
  d++ a=*c a<<= 9 *d=a
  d= 23 *d=a
  d= 3 a=*d a>>= 22 a<<= 8 d= 25 *d=a
  halt
end
"""

# ours2 (a 1 MB probe only): ours + an order-12 ISSE on the order-7 chain end,
# a second match model on order 16, and an ICM on the bytes above and
# above-right with byte 1.
CFG["ours2"] = CFG["ours"].replace("comp 5 16 0 0 27", "comp 5 16 0 0 30").replace("""  18 mix 17 0 18 24 255
  19 mix 8 0 19 10 255
  20 mix2 0 18 19 24 0
  21 sse 8 20 32 255
  22 mix2 8 20 21 16 255
  23 sse 17 22 32 255
  24 mix2 8 22 23 16 255
  25 sse 18 24 32 255
  26 mix2 0 24 25 16 0""", """  18 isse 22 8
  19 match 22 24
  20 icm 18
  21 mix 17 0 21 24 255
  22 mix 8 0 22 10 255
  23 mix2 0 21 22 24 0
  24 sse 8 23 32 255
  25 mix2 8 23 24 16 255
  26 sse 17 25 32 255
  27 mix2 8 25 26 16 255
  28 sse 18 27 32 255
  29 mix2 0 27 28 16 0""").replace("""  d++ hash *d=a b--
  (word H10""", """  d++ hash *d=a b--
  hash b-- hash b-- hash b-- hash d= 18 *d=a b--
  hash b-- hash b-- hash b-- hash d= 19 *d=a d= 9
  (word H10""").replace("""  b=a a=*b r=a 2""", """  b=a a=*b r=a 2 b++ a=*b r=a 3""").replace("""  d++ *d=0 hashd a=*c hashd
  (mixer""", """  d++ *d=0 hashd a=*c hashd
  d= 20 *d=0 a=r 2 hashd a=r 3 hashd a=*c hashd
  (mixer""").replace("""  d++ a=*c a<<= 9 *d=a
  d= 23 *d=a
  d= 3 a=*d a>>= 22 a<<= 8 d= 25 *d=a""", """  d= 21 a=*c a<<= 9 *d=a
  d= 26 *d=a
  d= 3 a=*d a>>= 22 a<<= 8 d= 28 *d=a""")

# ours3: ours2 with the long contexts carried further -- ISSEs on orders 12,
# 16 and 24 chained after order 7, match models on orders 16 and 32.
CFG["ours3"] = CFG["ours2"].replace("comp 5 16 0 0 30", "comp 6 16 0 0 33").replace("""  18 isse 22 8
  19 match 22 24
  20 icm 18
  21 mix 17 0 21 24 255
  22 mix 8 0 22 10 255
  23 mix2 0 21 22 24 0
  24 sse 8 23 32 255
  25 mix2 8 23 24 16 255
  26 sse 17 25 32 255
  27 mix2 8 25 26 16 255
  28 sse 18 27 32 255
  29 mix2 0 27 28 16 0""", """  18 isse 22 8
  19 isse 22 18
  20 isse 22 19
  21 match 22 24
  22 match 22 24
  23 icm 18
  24 mix 17 0 24 24 255
  25 mix 8 0 25 10 255
  26 mix2 0 24 25 24 0
  27 sse 8 26 32 255
  28 mix2 8 26 27 16 255
  29 sse 17 28 32 255
  30 mix2 8 28 29 16 255
  31 sse 18 30 32 255
  32 mix2 0 30 31 16 0""").replace("""  hash b-- hash b-- hash b-- hash d= 18 *d=a b--
  hash b-- hash b-- hash b-- hash d= 19 *d=a d= 9""", """  hash b-- hash b-- hash b-- hash d= 18 *d=a b--
  hash b-- hash b-- hash b-- hash d= 19 *d=a d= 21 *d=a b--
  hash b-- hash b-- hash b-- hash b-- hash b-- hash b-- hash b-- hash d= 20 *d=a b--
  hash b-- hash b-- hash b-- hash b-- hash b-- hash b-- hash b-- hash d= 22 *d=a d= 9""").replace(
  "  d= 20 *d=0 a=r 2 hashd a=r 3 hashd a=*c hashd", "  d= 23 *d=0 a=r 2 hashd a=r 3 hashd a=*c hashd").replace("""  d= 21 a=*c a<<= 9 *d=a
  d= 26 *d=a
  d= 3 a=*d a>>= 22 a<<= 8 d= 28 *d=a""", """  d= 24 a=*c a<<= 9 *d=a
  d= 29 *d=a
  d= 3 a=*d a>>= 22 a<<= 8 d= 31 *d=a""")

ROWS = {"min": "min", "mid": "mid", "max": "max", "lvl3": "level3", "lvl4": "level4", "lvl5": "level5", "ours": "ours", "maxcol": "maxcol", "ours_v0": "ours_v0", "ours2": "ours2", "ours3": "ours3"}
