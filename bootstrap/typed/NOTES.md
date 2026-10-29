# typed/ — checker, typist, finder_sim (key `checker`, 2026-10-18)

## Built
- `checker.py`: the hand-typed checker, **12 lines, 496 chars (468 without
  indent), longest 70**; no imports, floats, `/`, `;`, `~`, `@`. Uses
  `open`/`input`/`exec` (the spec needs them). Run it in an empty folder:
  prints `OK n` = type line n next or
  `BAD n` = retype line n. Accepted payloads go to `s.txt`, one per line, as
  they pass; restart = run it again (resumes). `RUN` writes the code section to `a.py` and execs it in
  the checker's globals, stdin attached.
- `typist.py` (`enc`/`dec`), `finder_sim.py` (docstrings say how).

## Measured
- `finder_sim.py 1..12`: 12/12 PASS; per seed 113–151 lines typed for 76,
  every mishap kind 2–17×, 0 lucky passes, two kill -9 + resume, a.py exact,
  the exec'd program decoded R2-FORMAT.md (4,966 B, cm2 → 2,183 B) from
  `t[1]` with primer `t[0]` and echoed 3 post-RUN lines.
- Plate test and self-test (checker accepts its own 12 printed lines) PASS.
- Guarantee (arithmetic): one substitution changes the sum by i·d, |i·d| ≤
  64·94 = 6016 < 32768; a transposition by k·d ≤ 5922 → always caught.

## Plate known-answer lines (fresh folder)
- reject first: `if 1:~@print(24)~snk` → `BAD 1`
- accept: `if 1:~@print(42)~snk` → `OK 2`; then `RUN` → prints `42`.
  Delete `s.txt` and `a.py` afterwards.

## Hand-worked check, payload `if 1:~@print(42)~`, line 1
Σ i·ord: 1·105=105, 2·102=204 (309), 3·32=96 (405), 4·49=196 (601),
5·58=290 (891), 6·126=756 (1647), 7·64=448 (2095), 8·112=896 (2991),
9·114=1026 (4017), 10·105=1050 (5067), 11·110=1210 (6277),
12·116=1392 (7669), 13·40=520 (8189), 14·52=728 (8917), 15·50=750 (9667),
16·41=656 (10323), 17·126=2142 (12465).
n·1000003 = 1000003 ≡ 16963 (mod 32768; hint: 1000003 − 30·32768).
16963 + 12465 = 29428. 29428 = 28·1024 + 756; 756 = 23·32 + 20.
Digits 28, 23, 20 → `s n k`. (The swap 42→24 changes the sum by −2 → `snm`.)

## Checker listing check codes (n = line, over the line exactly as printed,
leading spaces included): 1 m59, 2 fbi, 3 r0j, 4 0c6, 5 kkf, 6 rvl, 7 5of,
8 cqn, 9 0kq, 10 tg5, 11 r9o, 12 u5v.

## Decisions / spec questions
1. `###` is its own checked line (payload `###`), so data starts on a fresh
   line; the stream text is identical either way.
2. The shared stream variable is `t = stream.split('###')`: `t[0]` = code
   as typed (cm2's primer), `t[1]` = data base-32. Glue must use this.
   `A` (alphabet) is also visible to the glue.
3. No 64-char length check in the checker (a >64 payload passes only at
   1/32768); typist enforces width.
4. cm2_dec.py uses 2-space indents: typist encodes leading spaces as one
   `@` per 4 + remainder spaces (exact round trip), so cm2 types as
   `  ms = ...` / `@for ...`. Recommend cm2 re-indented to 4 before print.
5. Code may not contain `###` (typist refuses).
6. Relies on CPython closing un-named files at once (refcount) for the
   append and a.py; a non-refcounting Python needs `.close()` lines.
7. CRLF input (pipes) makes every line BAD; terminals are fine. Invalid
   UTF-8 → BAD under surrogateescape (measured), may raise under strict.

## cm2 v2 — the rANS coder (2026-10-20 night)
- `cm2_dec.py` / `cm2_enc.py` are v2 since 2026-10-20: cm2's count model
  (the same counts and update) with a big-integer rANS coder — the coded
  message is one integer x, decoded bit by bit (`slot = x % s`, `y = slot >=
  p0`, `x = x // s * p_y + slot - cum_y`), no window, no renormalisation, no
  12-bit clamp; contexts are masks of the whole history, orders
  (0,1,2,3,4,6,8,12,16). `encode` returns x as big-endian bytes, `decode`
  takes x as an int or bytes (the harness's door outside the region).
- The 10-18 range coder is kept verbatim as `cm2_v1_dec.py` / `cm2_v1_enc.py`;
  `finder_sim.py` (the 10-18 harness) now imports those.
- KAT vectors: `kat_v2.json` (`kat_v2.py` derives them; `--check` compares).
- The measurements behind the choices (orders, keys, spellings, timing, v1
  against v2): `measure_v2.py`, `measure_v2_final.py`, `measure_v2-result.json`.
