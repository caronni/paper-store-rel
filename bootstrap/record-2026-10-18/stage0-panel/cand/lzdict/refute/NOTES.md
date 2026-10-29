# Refutation of lzdict: CONFIRMED (every claimed number reproduces exactly)

Harness: encrun.py / decrun.py (import only enc.py / dec*.py), run_all.sh
under PYTHONHASHSEED 0 and 4242; plate_main.py / plate_raw.py are second
decoders written from the plate items alone.

- count_lines: dec.py 20 lines / 739 chars, dec_raw.py 15 / 496, 0 violations.
- All 16 sizes per variant + both KAVs reproduce to the byte; 20/20
  round trips byte-exact, both seeds; compressed bytes identical across
  seeds. Greedy-vs-optimal table reproduces.
- Timings consistent (T4 primed decode 1.7-2.0 s main, 0.3 s raw; encode
  T4 ~122 s main, ~18 s raw).
- Plate-only reimplementation decodes everything: the main spec is
  sufficient for bit-exact output. Bounds asserted and held.

Spec gaps / caveats (none changes a number):
1. Primer bytes are not canonicalized. The measured primer is the WHOLE
   dec.py (header comments + untyped harness, 1285 B), not the 20 typed
   lines. A primed stream decoded with a primer differing by any byte
   silently yields garbage (no error, no check). Priming with only the
   typed region costs +10 B (T1) / +27 B (T3). The Plate must print the
   primer's exact byte recipe (which text, LF, trailing newline).
2. Raw variant plate item is ambiguous: "interleaved gamma" polarity
   (1 = continue, then data bit) is not stated, and "Exp-Golomb order 9
   minus 512 plus 1" conflicts with the standard EG-k (whose value is
   already d-1) and EG's non-interleaved prefix. Needs spelling out.
3. Memory: P is sparse in Python; a fixed-width port needs a table of
   ~4160 + 2^ceil(log2 window) entries (2^21 for T4).
4. Behaviour on a match crossing n, or d > len(out), is undefined
   (encoder never emits it).
5. xz comparison includes xz's ~60 B container; raw LZMA2 payloads are
   3277/5354/8486, so main is +0.9 % / +0.7 % behind on T2/T3.
6. NOTES.md says raw is "7 % (T3)" bigger; unprimed it is 9.2 % (7.3 %
   primed). Cosmetic.
