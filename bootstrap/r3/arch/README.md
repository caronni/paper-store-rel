# bootstrap/r3/arch: the archival layer of the R3 monolith (2026-10-20, machine 1)

*2026-10-26: the R2 margin is no longer thin (c.py leaves 475 B spare, CONVERGENCE-2026-10-23b.md); the 6.4 KB archive margin stands for T1 at 2115a595. On paper the release restored byte-exact but did not run: T1 carries no LDPC tables and no requirements file (bootstrap/FINDINGS.md §16).*

The owner's proposal (RECORD-2026-10-20 ruling 26): "a simple archival
function with a cmmix decoder (optimized for space) and an unpacker (shar
style, or very simple subset of untar) in a couple of lines". At this rung
archive pages cost (about 110 KB of payload each at source fraction 0.5) and
R2 bytes are cheap, so a strong compressor in b.py pays for itself.

`receiver_arch.py` is `bootstrap/r3/receiver.py`, every line of it kept, plus:

- section 10: the container, a context-mixing decoder (`unz`) and a ustar
  unpacker (`unpack`);
- three glue lines in `main()`;
- one paragraph in the docstring.

When a volume closes and its SHA-256 checks, `payload.bin` is written as
before. If the payload starts with `R3A1`, the program then:

1. decodes the archive;
2. checks its CRC-32;
3. unpacks the tar into the current directory, each file under one flat
   name, printing every original path.

Any other payload is left as `payload.bin`. Like the receiver, the file is
pure Python with no imports.

`receiver_arch_os.py` is the same file with `import os`, so the tree is
written with real directories. The diff is the import, two lines in the
unpacker and the docstring.

Nothing here is printed or scanned: simulation only, no promotion.
`receiver.py`, `src/` and `docs/` are untouched.

## Files

**The integration round** (this README):

| file | what |
|---|---|
| `receiver_arch.py` | The monolith: receiver.py + section 10 + glue. Import-free. **Built by `make_arch.py`, never edited by hand.** |
| `receiver_arch_os.py` | The same with `import os` and real directories. |
| `make_arch.py` | Builds both from `receiver.py` + `dec_strong2.py`'s region. Checks that receiver.py's lines are a subsequence of each (151 / 153 inserted, 0 / 1 replaced). |
| `arch_pack.py` | The encoder side: tree → ustar → container. The encoder is derived from `receiver_arch.py`'s own decoder. `--commit COMMIT` tars that commit's blobs (the record's T1: `--commit 2115a595`). |
| `test_arch.py` | Scan-free checks of the glue, the CRC refusal, plain payloads, a synthetic tar and T2. |
| `e2e_arch.py` | Volume, scans and runs (above). `show_e2e.py` prints the results (at tag `bootstrap-pre-thinning-2026-10-23`). |
| `measure_arch.py` | Sizes of every form (`measure.py`'s method). |
| `trim_probe.py` | The measured cost of each trim. |

**The measuring builder's round:**

- the codec candidates `dec_*.py` / `enc_*.py`, with `derive.py`,
  `derive_cm2.py` and `gen_cm2fam.py`;
- the unpacker candidates `unp_*.py`;
- the harness: `trees.py`, `refs.py`, `pages.py`, `bench.py`, `runq.py`,
  `measure_r2.py`, `test_unpack.py`, `e2e.py`, `stdlib_time.py`,
  `summary.py`, `show.py`;
- the experiment generators.

Its outputs are in `build/r3/arch/` (`bench.jsonl`, `r2.jsonl`,
`summary.json` …).

## How to run

As the finder runs it (Python 3, nothing else):

```
mkdir out && cd out
python3 ../receiver_arch.py
scan (PGM file [dpi]; empty line ends): page07.pgm 1200
...
volume 1 complete: 1648660 bytes, SHA-256 78d9a4b4..., written to payload.bin
archive: decoding                              (about 13 minutes for T1 on an M1 Max)
CLAUDE.md
docs/BOOTSTRAP-DESIGN.md
...
```

**Flat names:** the path with `%` → `%25`, then `/` → `%2F`. The original
path comes back with `name.replace('%2F', '/').replace('%25', '%')`, and
every path is printed in tar order. A shell rebuilds the tree in one line:

```
for f in *%*; do p=$(printf %s "$f" | sed 's/%2F/\//g; s/%25/%/g'); mkdir -p "$(dirname "$p")"; mv "$f" "$p"; done
```

**The harness**, from the worktree root. Generation needs ghostscript and
src/holo.

```
env/bin/python bootstrap/r3/arch/make_arch.py                       # builds receiver_arch.py + _os from receiver.py
env/bin/python bootstrap/r3/arch/arch_pack.py T1 [--reuse]          # container of T1 (13 min; --reuse: the builder's encode)
env/bin/python bootstrap/r3/arch/test_arch.py                       # scan-free: synthetic tar, bad CRC, plain payload, T2
PYTHONPATH=src env/bin/python bootstrap/r3/arch/measure_arch.py     # every form's size, cm2 + R2 pages
PYTHONPATH=src env/bin/python bootstrap/r3/arch/e2e_arch.py volume T1
PYTHONPATH=src env/bin/python bootstrap/r3/arch/e2e_arch.py scans T1 arch      # and arch40
env/bin/python bootstrap/r3/arch/e2e_arch.py run T1 arch bootstrap/r3/arch/receiver_arch.py T1_arch
env/bin/python bootstrap/r3/arch/e2e_arch.py run T1 arch40 bootstrap/r3/arch/receiver_arch.py T1_arch40
env/bin/python bootstrap/r3/arch/e2e_arch.py run T1 arch bootstrap/build/r3/arch/forms_arch/receiver_arch.minified-g.py T1_arch_ming
env/bin/python bootstrap/r3/arch/e2e_arch.py run T1 arch bootstrap/r3/arch/receiver_arch_os.py T1_arch_os --os
```

Outputs go to the gitignored `bootstrap/build/r3/arch/`:

- `e2e_arch/T1/`: the volume, the scans, `run_*` directories,
  `result_*.json` and timestamped `stdout_*.txt`;
- `forms_arch/`, `measure_arch.json` and `unit/`.

## The container

| bytes | field |
|---|---|
| 0–3 | `R3A1`, the magic |
| 4–11 | n, the tar's length, big-endian |
| 12–15 | CRC-32 of the tar (the zlib/PNG polynomial; the receiver's own `crc32`), big-endian |
| 16– | the coder's bytes |

- **The tar.** ustar, files sorted by path, mode 0644, mtime 0, uid/gid 0,
  empty user/group names. It holds regular files only, with no directory
  members, padded to tarfile's 10,240-byte record. Built by `trees.py`
  from `git ls-files`.
- **What `arch_pack.py` refuses:** any non-regular member, and any flat name
  over 255 bytes.
- **The decoder** is `dec_strong2.py`, the measuring builder's winner. It is
  a bitwise context-mixing model driving a binary arithmetic coder with
  32-bit bounds, so it is linear in n.
  - **Contexts:** orders 0–4 and 7, the current word, the word bigram, and
    the column (the byte above). These sit in 16-slot nibble buckets with
    a 16-bit check.
  - **Match model:** on the order-7 context.
  - **Mixing:** three summed weight sets, then two APMs.
  - **Memory:** tables of 2^28 slots, 1.4 GB whatever n.
- **What changed against `dec_strong2.py`:**
  - the head reads the container's fields: `n` at [4:12], the coder's
    bytes at [16:];
  - six NEUTRAL rewrites that compute the same thing in fewer compressed
    bytes (`make_arch.py`).
- **The encoder** is derived mechanically from the decoder text inside
  `receiver_arch.py` (`arch_pack.arch_encoder` → `derive.py`), so the two
  cannot drift.
- **The rewrites are neutral:** re-encoding T2 and T1 with that encoder
  gives bytes identical to the builder's `dec_strong2` encodes.

## What was trimmed to stay at 2 R2 pages

The first build was 10,670 B: 62 B over the 2-page line of 10,608. The
trims, each measured by `trim_probe.py` (cm2 of minified-g):

| trim | cm2 |
|---|---|
| progress line `archive of N bytes: decoding` → `archive: decoding` (dropping it: −23) | about −15 |
| failure message → `archive: CRC-32 wrong` | −11 |
| unpacker: no tar type check; every member is a regular file, which `arch_pack.py` guarantees | −10 |
| unpacker: the path as one expression (prefix + '/' + name, NULs dropped, leading '/' stripped) | −5 |
| decoder: six neutral rewrites | −17 |
| magic inlined in the glue | about −4 |
| **together** | **10,599 = 2 R2 pages, 9 B spare** |

Two further trims were measured and not taken:

- **Dropping the ustar prefix field** (−19). Paths over 100 bytes would then
  come out wrong. T1's longest path is 84 bytes; the all-files tree has
  211.
- **An `assert` in place of the CRC message** (−15). It ends the session
  with a traceback.

## End to end (T1, 15 archive pages)

**The volume:**

- **Container:** T1's tar under strong2 = 1,648,660 B (sha256 `78d9a4b4…`).
  The 15-page limit is 1,655,012 B, so the margin is 6,352 B.
- **Generator:** `holo generate --format c3-k-r0550@35x24 --source-fraction
  0.5`, A4-6mm.
- **Shape:** K = 6,260 symbols, N = 12,600 (15 × 840), K/N 0.497.
- **Rasterising:** every page through gs bitcmyk's K plane, which equals the
  generator's GT, with 0 ink outside the field.

**The scans:** `make_test_volume.py`'s `simulate()`, 1200 dpi.

| | |
|---|---|
| tilt | 0.5° |
| scale | +0.4 % |
| seams | Canon-like (+0.84 dot every 18.288 mm) |
| blur | 0.5 dot |
| paper / ink grey | 220 / 60 |
| noise | σ 12 |
| `arch40` only | 40 % of each page's tiles whited out, seeded |

**The runs:** all 15 pages fed in one session, pooled, in a seeded
shuffled order. The four runs ran concurrently with the T1 re-encode (five
heavy processes on 10 cores), so walls are under load.

| run | receiver | scans | pages read to the close | payload.bin | files byte-exact | receiving | decode + CRC | unpack | rest of the scans | wall | peak RSS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1_arch | `receiver_arch.py` | arch | 8 (7 × 840 + 380 certified → rank 6,260) | byte-exact | **321 / 321** (9,275,981 B) | 362 s | 788 s | 0.03 s | 57 s (7 pages, 24 tiles each) | 1,207 s | 1,512 MB |
| T1_arch40 | `receiver_arch.py` | arch40 | 13 (12 × 504 + 217) | byte-exact | **321 / 321** | 632 s | 780 s | 0.03 s | 46 s (2 pages) | 1,459 s | 1,512 MB |
| T1_arch_ming | minified-g form | arch | 8 | byte-exact | **321 / 321** | 360 s | 789 s | 0.03 s | 57 s | 1,206 s | 1,512 MB |
| T1_arch_os | `receiver_arch_os.py` (real directories) | arch | 8 | byte-exact | **321 / 321** | 362 s | 788 s | 0.03 s | 57 s | 1,206 s | 1,512 MB |

- **What every run did:**
  - every placed tile certified, 0 failures;
  - 840/840 tiles placed per page (arch), 504/840 = every non-blank tile
    (arch40);
  - every path printed, in tar order;
  - no file other than `payload.bin` and the tree's.
- **The time split:**
  - **Receiving** runs from the start to the `volume 1 complete` line,
    about 45 s a page, and 49 s a page with 40 % of the tiles blank.
  - **Decode + CRC** runs from `archive: decoding` to the first path. It is
    the whole cost of the layer: 13.1 min for 9.5 MB, matching the
    builder's 785 s standalone.
  - **Peak RSS** is the decoder's 1.4 GB tables plus one scan (`/usr/bin/time
    -l`).
- **Scan-free checks** (`test_arch.py`, all pass; both receivers, driving
  `main()`'s own glue through a stand-in volume):
  - a synthetic ustar with a 156-byte path (prefix field), `%` and spaces in
    a name, an empty file and binary data;
  - the same container with its CRC flipped, which prints `archive: CRC-32
    wrong` and writes nothing but `payload.bin`;
  - a payload without the magic, which gives `payload.bin` only;
  - T2 (38 files, 36 s);
  - a tar with a directory member, which `arch_pack.py` refuses.
- **The T2 smoke run on scans:** 1 page, `receiver_arch.py`, 38/38
  byte-exact, 54 s, 1,361 MB.
- **Encoder determinism and neutrality:** T1 re-encoded with the encoder
  derived from `receiver_arch.py` (840 s, under load) gives bytes identical
  to the builder's `dec_strong2` encode. T2 likewise.

## Sizes (`measure_arch.py`)

The method is `bootstrap/r3/measure.py`'s:

- forms: raw, stripped (ast.unparse), python-minifier, and minified-g
  (module names renamed too);
- compression: cm2 v2 primed with `bootstrap/build/loader/r.py`;
- R2 pages = ceil(cm2 / 5,304).

| file | form | lines | bytes | cm2 | R2 pages | spare / over | over `receiver.py`'s same form |
|---|---|---|---|---|---|---|---|
| receiver.py | raw | 1,100 | 51,106 | 15,341 | 3 | | |
| receiver.py | minified-g | 446 | 22,011 | 9,415 | 2 | 1,193 spare | |
| **receiver_arch.py** | raw | 1,251 | 58,348 | 17,583 | 4 | | +2,242 |
| receiver_arch.py | stripped | 886 | 40,834 | 11,746 | 3 | | +1,289 |
| receiver_arch.py | minified | 469 | 26,810 | 10,891 | 3 | 283 over 2 | +1,193 |
| **receiver_arch.py** | **minified-g** | 488 | 24,460 | **10,599** | **2** | **9 spare** | +1,184 |
| receiver_arch.py | stdlib-minified-g (hashlib/zlib/math) | 451 | 23,463 | 10,221 | 2 | 387 spare | +1,178 |
| receiver_arch_os.py | raw | 1,252 | 58,286 | 17,573 | 4 | | +2,232 |
| receiver_arch_os.py | stripped | 888 | 40,866 | 11,771 | 3 | | +1,314 |
| receiver_arch_os.py | minified | 470 | 26,831 | 10,914 | 3 | | +1,216 |
| receiver_arch_os.py | minified-g | 489 | 24,480 | 10,622 | **3** | 14 over 2 | +1,207 |

The R2 page for the cm2 bytes is 5,304 B, so two pages hold 10,608.

The cm2 round trip (`cm2_dec.decode`, the finder's code) recovers both
minified-g forms byte-identically (3.6 / 3.7 s).

## How the codec was chosen (the measuring builder's record, condensed)

**Archive pages** for T1 (9,523,200 B tar, 321 files) at q 0.5, from holo's
planner:

| codec | T1 bytes | archive pages | R2 cost of decoder + unpacker | leaves (R2 + archive) | decode T1 | peak memory |
|---|---|---|---|---|---|---|
| **strong2** (this file) | 1,648,648 | **15** | ≈ 1,184 | **17** | 13.1 min | 1.36 GB |
| strong (k = 24) | 1,705,470 | 16 | 1,175 | 18 | 12.6 min | 263 MB |
| cm1 k = 24 (the 10-18 bounded cmmix) | 1,738,544 | 16 | 1,038 | 18 | 10.2 min | 136 MB |
| cmmix | 1,785,845 | 17 | 795 | 19 | 11.2 min | 964 MB |
| cm2 orders + range coder, exact dict | 1,761,165 | 16 | 399 | 18 | 8.7 min | 25 GB, grows with n |
| xz -9e (stdlib `lzma` / `tarfile`) | 2,149,928 | 20 | 24–153 | 22 | 0.3 s | — |

- Every pure-Python decoder is linear in n. The cm2 v2 big-integer rANS is
  quadratic and was not a candidate.
- **The extrapolated row** (EXTRAPOLATION, not measured): every tracked text
  file, 69.3 MB tar, xz 9,698,512 B = 88 pages (measured). Taking T1's
  strong2/xz ratio gives ≈ 7.44 MB ≈ 68 pages and ≈ 95 min of decoding.
- That tree exceeds one volume, so the receiver would need several (its
  single-block limit is 4,315,100 B). It would therefore need several
  containers, compressed apart, which costs ratio.

## Deviations from the task as set

- **The unpacker is variant (i) trimmed**, to fit 2 R2 pages:
  - no type check, so a directory member would be written as an empty
    file; `arch_pack.py` refuses such a tar;
  - the path is one expression.

  The builder's winner had the shar-style unpacker (73 B spare). With the
  ustar unpacker the untrimmed form was 62 B over, so it was trimmed to 9 B
  spare instead.
- **Two printed messages** (`archive: decoding`, `archive: CRC-32 wrong`)
  and the CRC check were added. The CRC check is the task's; the messages
  are mine, because 13 minutes of silence would look like a hang.
- **The decoder carries six neutral rewrites** of `dec_strong2.py`. The
  T1/T2 re-encodes are identical to the builder's, so the computation is
  unchanged.
- **`receiver_arch_os.py` is 3 R2 pages** (10,622 B, 14 B over). `import os`
  costs 21–23 B whatever the spelling of the makedirs line.
- **The tree is T1 as defined** (src/holo `.py` + docs `.md` without
  docs/archive + CLAUDE.md). The task's "T2 ≈ 0.95 MB" is T2R in
  `trees.py`; T2 here is the literal 0.41 MB selection, used only for the
  smoke and unit tests.

## Open rulings for the owner

1. **Which tree.**
   - T1 = 15 archive pages + 2 R2 = 17 leaves. Its margin is thin on both
     sides: 6.4 KB under the 15-page line (0.4 %), and 9 B under the
     2-page R2 line. Any change to `receiver.py` moves the second.
   - T2R (src/holo without the receiver) = 2 archive pages under xz.
   - Every tracked file needs several volumes (see above).
2. **`import os`.** Real directories cost a third R2 page by 14 B. Flat
   names cost the finder one shell line (above).
3. **stdlib / lzma.**
   - With `import tarfile` (or `lzma` + this unpacker) the decode takes
     0.3 s instead of 13 min, and R2 stays at 2 pages (the builder's
     measurement: `tarfile.open(...).extractall()` adds 24–26 B to the
     receiver's 9,043 / 9,415 B).
   - The stdlib receiver (hashlib, zlib, math) carrying this pure-Python
     archive layer is 10,221 B (387 B spare). With `import os` and real
     directories it is 10,238 B, still 2 R2 pages (measured in this round,
     one-off, not in `measure_arch.py`).
   - But T1 then costs 20 archive pages instead of 15: 5 pages of toner and
     paper against an unbounded deep-time dependency on the stdlib's xz.
4. **ustar or shar.** shar is 2.3 KB smaller on T1 under strong2 and its
   unpacker is about 60 B cheaper in R2. That would buy back the
   untrimmed messages, or room for `import os`. ustar is what any tar
   reads once the archive is decoded.
5. **The trims.** Accept the no-type-check unpacker and the short messages,
   or pay a third R2 page for the long ones.

## The refuter's corrections (panel in REVIEW-2026-10-20.md; none a blocker)

- With the container glue kept, the shar unpacker is 26 B cheaper in R2 than
  the ustar one, not about 60; and with shar the `import os` variant still
  fits 2 R2 pages. Both open rulings should be read with that.
- Corrupted containers never write anything beyond payload.bin, but only a
  wrong CRC field ends in the CRC message; a flipped coder byte, a truncated
  container or a wrong length ends in a traceback (IndexError, MemoryError).
  A flipped magic byte is read as a plain payload.
- The `_os` variant follows `..` components: `../evil.txt` is written
  outside the working directory. The flat variant cannot leave the working
  directory. Names `.` and `..` crash both after earlier files were written.
- On a case-insensitive file system (machine 1's APFS) `README.md` and
  `readme.md`, or NFC and NFD forms of one name, collapse to one file
  silently; a member named payload.bin overwrites the volume's. The real
  trees (T1, the refuter's tree R, every tracked text file) have no such
  collision, no `%`, newline or leading `-` in a name, longest flat name
  229 B.
- Directory, symlink and hard-link members are refused by the packer; if
  such a tar reached the receiver, the flat unpacker would write an empty
  file and `_os` would crash.
- The checker: README's "three glue lines" is a count of the glue, not of
  the diff (151 inserted lines); the trim table's figures should be
  re-derived from trim_probe.py after any change.

