# record-2026-10-18/ — the two panels' working material (provenance copy)

Copied from the cloud session's scratchpad before the container was
abandoned, so the numbers in RECORD.md and REVIEW-2026-10-18.md can be
reproduced. Bulky derived files (camera renders, 805 KB fixtures, run
logs) are NOT here; their SHA-256 and the scripts that derive them are.

- stage0-panel/: the stage-0 decompressor panel — STAGE0-DECOMPRESSOR-MEMO.md
  (synthesizer), STAGE0-CRITIQUE.md (critic), cand/<key>/ = each builder's
  enc.py / dec*.py / NOTES.md / results.json and the refuter's harness notes
  (cm2, cmmix, bwt, ppm, lzdict). cm2 and cmmix also live in bootstrap/typed
  and bootstrap/stage1 as the working copies.
- fixtures/: T1_8k.py (first 8,192 B of src/paperholo/keystream_ref.py),
  T2_16k.py (the whole file), T3_32k.txt (first 32,768 B of the stripped
  receiver core), primer.txt (the Plate stand-in: ASCII table + keywords +
  builtins + 6 KB of util/scrap_pack.py). T4_805k.txt = the stripped
  receiver core (804,967 B) is derived: scripts/closure.py (the import
  closure of src/holo/receiver) + scripts/strip.py (ast.unparse without
  docstrings) over the tree at main 2fa8fd5, concatenated with '### path'
  headers; SHA256SUMS-derived pins it.
- scripts/: closure.py, strip.py (the corpus derivation), bench_pip.py
  (zlib/bz2/xz/zstd/brotli/ppmd baselines; at tag
  bootstrap-pre-thinning-2026-10-23), cm2b_enc.py (cm2 with a hashed,
  bounded context map — the +6 % / +57 % measurement).
- refute-typed/, refute-r2/: the two build-panel refuters' harnesses and
  notes (typer.py, mutate.py, kat.py, the degradation-matrix scripts and
  their JSON/CSV results); the PGM/PBM renders they ran on are regenerable
  from bootstrap/r2/gen.py + camera.py with the parameters in their notes.
