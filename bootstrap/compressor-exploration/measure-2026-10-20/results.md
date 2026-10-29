# Stage-0 public-baseline measurement 2026-10-20

| fixture | bytes | sha256 | pin |
|---|---|---|---|
| T1_8k.py | 8192 | ff63005760a7a4f678f6bbcd5c7ef95d6f08d2aece2553083a1715bd7aec96b4 | no pin (copied from record) |
| T2_16k.py | 16514 | 9a941940ab7ce8b13afc4184100c0dc09fc2e6411e542a3166474841eeabb56b | yes |
| T3_32k.txt | 32768 | 5a0548a05ef44b45325debf9f2e7b4b12ecf26e0aea29b68b7407964af0e4eb5 | no pin (copied from record) |
| T4_805k.txt | 804967 | e8f0dbd15e7bef35bf275e030b79c9ab9ad802f11279ce95cf5379ab3ec45e40 | yes |
| primer.txt | 7406 | 298fdcb74f566821488af17fb0d9361d9b3f3249aa73dfb5c158558b3917d38a | no pin (copied from record) |

| codec | settings | primed | T1 8K | T2 16K | T3 32K | T4 805K | label | decoder source | note |
|---|---|---|---|---|---|---|---|---|---|
| cm2 | record enc.py/dec.py | N | 2884 | 4676 | 7257 | 119866 | MEASURED | 25 lines / 1,010 chars typed Python (count_lines.py MEASURED) | round trip OK all fixtures; sizes exclude out-of-band n; max child RSS 1189 MB; matches results.json exactly |
| cm2 | record enc.py/dec.py, primer=primer.txt+dec.py bytes | Y | 2633 | 4372 | 6914 | 119211 | MEASURED | 25 lines / 1,010 chars typed Python (count_lines.py MEASURED) | round trip OK all fixtures; sizes exclude out-of-band n; max child RSS 1210 MB; matches results.json exactly |
| cmmix | record enc.py/dec.py | N | 2799 | 4513 | 6950 | 114762 | MEASURED | 48 lines / 2,302 chars typed Python (count_lines.py MEASURED) | round trip OK all fixtures; sizes exclude out-of-band n; max child RSS 381 MB; matches results.json exactly |
| cmmix | record enc.py/dec.py, primer=primer.txt+dec.py bytes | Y | 2542 | 4203 | 6629 | 114177 | MEASURED | 48 lines / 2,302 chars typed Python (count_lines.py MEASURED) | round trip OK all fixtures; sizes exclude out-of-band n; max child RSS 384 MB; matches results.json exactly |
| lpaq1 | -9 | N | 2920 | 4666 | 7002 | 110661 | MEASURED | lpaq1.cpp 846 lines / 30,158 B (484 non-comment lines, 11,101 non-ws chars); enc+dec share the model, decoder not separable | sizes INCLUDE lpaq1's 8-byte header (pQ,ver,mem,4B length); subtract 8 to compare with cm2/cmmix (which carry n out of band); round trip OK |
| lpaq1 | -9, primed by difference size(primer.txt||x)-size(primer.txt) | Y | 2585 | 4266 | 6595 | 109994 | MEASURED (difference method) | lpaq1.cpp 846 lines / 30,158 B (484 non-comment lines, 11,101 non-ws chars); enc+dec share the model, decoder not separable | primer.txt alone compresses to 2704; header cancels in the difference; round trip OK |
| lpaq1 | -6 | N | 2919 | 4663 | 6987 | 110726 | MEASURED | same lpaq1.cpp | 8-byte header included; round trip OK |
| lpaq1 | -6, primed by difference size(primer.txt||x)-size(primer.txt) | Y | 2585 | 4263 | 6586 | 110090 | MEASURED (difference method) | same lpaq1.cpp | primer.txt alone compresses to 2704; header cancels in the difference; round trip OK |
| fpaq0 | c | N | 4969 | 9943 | 20073 | 499966 | MEASURED | fpaq0.cpp 202 lines / 5,420 B (131 code lines) | order-0, EOF flag per byte; round trip OK |
| fpaq0 | c, primed by difference size(primer.txt||x)-size(primer.txt) | Y | 4976 | 9974 | 20214 | 500187 | MEASURED (difference method) | fpaq0.cpp 202 lines / 5,420 B (131 code lines) | primer.txt alone compresses to 4467; header cancels in the difference; round trip OK |
| fpaq0f2 | c | N | 4680 | 9188 | 18014 | 448110 | MEASURED | fpaq0f2.cpp 275 lines / 7,864 B (175 code lines) | order-0 + bit history; round trip OK |
| fpaq0f2 | c, primed by difference size(primer.txt||x)-size(primer.txt) | Y | 4621 | 9121 | 17933 | 447996 | MEASURED (difference method) | fpaq0f2.cpp 275 lines / 7,864 B (175 code lines) | primer.txt alone compresses to 4021; header cancels in the difference; round trip OK |
| upkr | -9 | N | 3208 | 5328 | 8561 | 149387 | MEASURED | decoder c_unpacker/unpack.c 160 lines / 5,782 B (86 code lines, both bitstream variants); packer is Rust, 1,891 lines | LZ + rANS, adaptive binary contexts; T1-T3 round trip via the C reference unpacker, T4 via upkr -u; round trip OK |
| upkr | -9, primed by difference size(primer.txt||x)-size(primer.txt) | Y | 3016 | 5093 | 8258 | 148817 | MEASURED (difference method) | decoder c_unpacker/unpack.c 160 lines / 5,782 B (86 code lines, both bitstream variants); packer is Rust, 1,891 lines | primer.txt alone compresses to 2914; header cancels in the difference; round trip OK |
| lpaq1 | -9, primed by difference with the SAME primer as cm2 (primer.txt+cm2 dec.py, 9,282 B) | Y | 2527 | 4194 | 6548 | - | MEASURED (difference method) | lpaq1.cpp 846 lines / 30,158 B (484 non-comment lines, 11,101 non-ws chars); enc+dec share the model, decoder not separable | like-for-like primer with the cm2 primed row; with cmmix's primer (11,138 B): 2523/4196/6553 |
| ppmd7 (pyppmd) | order 16, primed by difference with cm2's primer (9,282 B) | Y | 2672 | 4377 | 6979 | - | MEASURED (difference method) | 7-Zip/PPMd var.H C, not counted | with cmmix's primer: 2673/4381/7015 |
| zlib | level 9 (zlib container, 6 B overhead) | N | 3333 | 5551 | 8880 | 183560 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| zlib | level 9 zdict=primer.txt (zlib container) | Y | 3148 | 5322 | 8591 | 183135 | MEASURED | library decoder (not a small-decoder comparator) | zdict uses only the last 32 KB window; primer is 7,406 B so all of it is used; round trip OK |
| deflate raw | level 9 memLevel 9 wbits -15 | N | 3327 | 5545 | 8874 | 183466 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| deflate raw | level 9 wbits -15 zdict=primer.txt | Y | 3138 | 5312 | 8581 | 183125 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| bzip2 | -9 (python bz2) | N | 3380 | 5473 | 8464 | 142758 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| xz | preset 9|EXTREME (.xz container) | N | 3336 | 5412 | 8544 | 145264 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| lzma2 raw | preset 9e, nice 273, bt4, best of lc/lp/pb (3,0,2),(4,0,0),(3,0,0),(0,0,0),(4,0,2) | N | 3259 | 5327 | 8437 | 144916 | MEASURED | library decoder (not a small-decoder comparator) | best lc/lp/pb per fixture: {"T1": "000", "T2": "300", "T3": "300", "T4": "300"}; round trip OK |
| lzma2 raw | as above, primed by difference method | Y | 2968 | 4999 | 8071 | 144274 | MEASURED (difference method) | library decoder (not a small-decoder comparator) | size(primer||data)-size(primer); python lzma has no preset-dictionary API; ESTIMATE-grade (approximates a preset dict); round trip OK |
| zstd | level 22 (frame w/ content size) | N | 3298 | 5410 | 8578 | 147921 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| zstd | level 22 --long (wlog 27, LDM) | N | 3298 | 5414 | 8578 | 147915 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| zstd | level 22 raw-content dict = primer.txt | Y | 3128 | 5233 | 8372 | 169014 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| brotli | q11 lgwin 24 MODE_TEXT | N | 2940 | 4895 | 7867 | 143755 | MEASURED | library decoder (not a small-decoder comparator) | brotli has a built-in ~120 KB static dictionary in the decoder; round trip OK |
| brotli | q11 lgwin 24 text, primed by difference | Y | 2770 | 4729 | 7676 | 143316 | MEASURED (difference method) | library decoder (not a small-decoder comparator) | python brotli exposes no custom-dictionary API; round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 4 mem 256MB | N | 2967 | 4867 | 7688 | 150868 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 6 mem 256MB | N | 2934 | 4735 | 7386 | 134397 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 8 mem 256MB | N | 2924 | 4698 | 7327 | 127931 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 12 mem 256MB | N | 2920 | 4673 | 7289 | 123399 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 16 mem 256MB | N | 2920 | 4667 | 7278 | 122234 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 24 mem 256MB | N | 2918 | 4668 | 7269 | 121694 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 32 mem 256MB | N | 2919 | 4671 | 7270 | 121618 | MEASURED | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 6 mem 256MB, primed by difference | Y | 2732 | 4505 | 7134 | 134062 | MEASURED (difference method) | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 8 mem 256MB, primed by difference | Y | 2720 | 4463 | 7057 | 127536 | MEASURED (difference method) | library decoder (not a small-decoder comparator) | round trip OK |
| ppmd7 (pyppmd, PPMd var.H) | order 16 mem 256MB, primed by difference | Y | 2718 | 4433 | 6996 | 121806 | MEASURED (difference method) | library decoder (not a small-decoder comparator) | round trip OK |
| cm2 | results.json | N | 2884 | 4676 | 7257 | 119866 | RECORDED |  | results.json |
| cm2 | results.json | Y | 2633 | 4372 | 6914 | 119211 | RECORDED |  | results.json |
| cmmix | results.json | N | 2799 | 4513 | 6950 | 114762 | RECORDED |  | results.json |
| cmmix | results.json | Y | 2542 | 4203 | 6629 | 114177 | RECORDED |  | results.json |
