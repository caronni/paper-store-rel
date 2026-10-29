# Loader review package, 2026-10-19

Every number was measured from files here. The record (`../a.py`,
`../data.txt`, `../codes.txt`) is untouched; `normal/` reproduces it byte
for byte.

## Variants (stage-1 loader identical but for S, N, C+1, R)

| | raw B | lines | cm2 B | base-58 | data lines | data chars | loader chars | typed | Enter |
|---|---|---|---|---|---|---|---|---|---|
| normal | 7,639 | 192 | 2,313 | 3,159 | 50 | 3,309 | 1,116 | **4,425** | 89 |
| mech | 4,894 | 64 | 2,094 | 2,860 | 45 | 2,995 | 1,116 | **4,111** | 84 |
| hand | 4,713 | 111 | 1,911 | 2,610 | 41 | 2,733 | 1,116 | **3,849** | 80 |

Enter = loader lines + data lines.

- **mech** (`make_mech.py`): python-minifier with every AST-changing
  transform off; tabs → one space. `ast.dump` is identical.
- **hand**: `hand_tpl.py` is the structural pass (merged statements, `EQ`
  inlined, `s//d`, `*L`, `M-c` CRC, one Laplacian expression, a shared
  lambda). `hand_search.py` then picks each binding's name by
  compressed size (primer = the loader), through a scope-exact renamer
  that re-proves every rename (`names.py`). Twenty single edits measured
  after renaming all lost bytes (`edits_named.py`). Nothing is dropped:
  P2, `grid.txt` and every message stay.
- e2e (`e2e_variant.py`, a copy of the record's harness): all three
  variants, both 3.14 interpreters, the 10x3 grid and b030 PGM in a pipe,
  and the grid on a pty: **ALL PASS**.

## Equivalence (`equiv.py`, plain script, stdin = path)

| capture | status | grid.txt |
|---|---|---|
| 10x3 grid | 946/946, 267/267 OK | 20b53466 |
| 10x3 nominal-b030 | 946/946, 267/267 OK | 2b4e41f8 |
| 10x3 hard-b030 | 946/946, 267/267 OK | 54a720ab |
| 10x3 flatbed300 | 946/946, 267/267 OK | 20b53466 |
| 12x2 grid | 626/626, 267/267 OK | e1f2eb72 |
| 12x2 nominal-b030 | 626/626, 267/267 OK | c2a56ccc |
| 12x2 hard-b030 | 626/626, 267/267 OK | e528fed0 |
| 12x2 flatbed300 | 626/626, 267/267 OK | e1f2eb72 |

r2.bin is dba6f077… (= payload.bin) on all eight. mech and hand are
identical to normal in stdout, r2.bin, grid.txt and exit code
(`equiv.json`).

## Experiments (baseline hand: 1,911 B, 3,849 typed)

Each row is a full S/C fixed point, round-tripped through its matching
decoder (`experiments.json`, `c1.json`).

| experiment | cm2 B | loader Δ | typed Δ |
|---|---|---|---|
| C1 fresh names, same structure | 1,950 (+39) | 0 | +57 |
| C1 unrenamed template | 2,074 (+163) | 0 | +236 |
| C1 all 52 letters from hand | no change | 0 | 0 |
| C2 orders (0,1,2,3,4,6,12) | 1,908 (−3) | −2 | **−6** |
| C2 (0,1,2,3,4,6,8), D=8 | 1,913 (+2) | −4 | −2 |
| C2 adding 5, 10 or 16 | +1 to +18 | +2 to +10 | +1 to +35 |
| C3 //2+1, //5+2, //8+2, //3+2 | +1 to +8 | 0 | +2 to +12 |
| C3 //4+1, //3+1, //2+2, //8+1, //4+3 | +16 to +27 | 0 | +24 to +40 |
| C4 clamp 4090–4095 | ±0 | 0 | 0 to +1 |
| C5 3-gram similarity sort | +2 to +7 | 0 | +2 to +11 |
| C5 measured order + swaps | 1,909 (−2) | 0 | −2 |

Naming is the lever: the loader's own names save 39 B over fresh names
on the same code. cm2's counter rule and clamp are already optimal.
Similarity sorting of functions hurts.

## Alphabets (hand payload, 64 + 3 per line)

| alphabet | payload | lines = Enter | data chars | shifted | check space |
|---|---|---|---|---|---|
| base-58 | 2,610 | 41 | 2,733 | 1,141 (42 %) | 195,112 |
| base-40 (34 + `-=[]/;`) | 2,872 | 45 | 3,007 | 0 | 64,000 |
| base-34 | 3,005 | 47 | 3,146 | 0 | 39,304 |
| Crockford 32 | 3,057 | 48 | 3,201 | 0 | 32,768 |

The loader has 253 shifted keys out of 1,116. `typing_test.txt` holds
three lines per alphabet for the stopwatch (checks illustrative, mod B³).

## Not done

- Typing speed is unmeasured.
- The P2 branch is kept but not exercised by any capture.
- The name search finds a local optimum, not a proved one.
- No loaders were rebuilt for the other alphabets.

## Owed rulings

1. Which reader goes on paper. hand saves 576 typed characters over
   normal and 262 over mech, but it is unreadable (one- and two-letter
   names, `for x in x`); reader.py stays the reference.
2. The alphabet: base-58, or base-40 at +274 characters with no shift
   key. Decide after the stopwatch test.
3. The orders tuple: −6 characters, but it changes cm2, the stage-0
   decoder spec. I recommend no.
4. C3 and C4: no change.
