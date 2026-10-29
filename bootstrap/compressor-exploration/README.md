# bootstrap/compressor-exploration — cm2, cmmix and strong2 examined from outside (2026-10-20/21)

Two cloud sessions of Claude Code (session
<conversation>), run against
this branch at a7c0453 and then 7dd8a9a6, asked by the owner: are cm2 and
cmmix self-invented, is anything public better at their size, how do they
work and what limits them; then: can cm2 compress better without more
typing, can cmmix/strong2 shrink by the same integer tricks and perform
better, what a "perfect" decoder-plus-payload would be per rung, and which
encoder-side investments pay. Everything here is SIMULATION and
MEASUREMENT on text; nothing was printed; NO promotion; nothing in the
record outside this directory was changed (the build of record was
reproduced for its payloads and the working tree then reverted).

Every number in the two reports carries a label: MEASURED (run in this
container), RECORDED (a repo file, named), PUBLISHED (a URL) or ESTIMATE.
The two reports are the deliverables; everything else is their evidence.

## Reading order

1. `LEVERS-2026-10-21.md` — the four questions of 2026-10-20 answered on the
   record: cm2 at the typed rung (the model is at a local optimum; the
   payload text is the lever: a renamed and rewritten reader types 3,788
   against 3,894, 3,778 with the short order tuple), strong2 with the
   big-integer rANS and exact dicts (R2 bytes only; quadratic at the
   archive, exact dicts unbounded), the archive to 14 pages (no measured
   strong2 arm reaches it; paq8l does at minus 8.94 % but in a day of pure
   Python), the two-part-code framing and the literature, the encoder-side
   levers ranked (monolith 10,599 → 9,876 B; path order already best; dedupe
   nothing; shar minus 2.3 KB). Closing table of every lever.
2. `ASSESSMENT-2026-10-20.md` — the first session: lineage (cm2 = PAQ1's
   count mixing with lpaq1's coder, its zero-count boost first explicit in
   Crinkler; cmmix = lpaq1's parts), the public axes that measure small
   decoders (demoscene bytes, source lines, size-inclusive benchmarks,
   decoder-plus-data golf), public codecs run on the exact T1–T4 fixtures
   (lpaq1, paq8l, PPMd, fpaq0, upkr, xz, zstd, brotli; cm2 ties PPMd
   primed and is 4–6 % behind lpaq1 primed; paq8l 13–20 % ahead), how the
   two decoders work line by line, and their limitations by cause.
3. The labs' `RESULTS.md` files (below) for every arm, number and caveat,
   then `workflows/agent-results/` for each worker's full return.

Both reports postdate the owner's own measurements on the branch
(loader/review, typed/measure_v2, priorart/ Crinkler and ZPAQ, r3/arch
strong2) and cite them as RECORDED rather than repeating them. The second
report was written against RECORD ruling 31.

## What is where

| path | what |
|---|---|
| `LEVERS-2026-10-21.md` | report 2 (6,450 words), the final editor's output after two refuters applied 41 corrections |
| `ASSESSMENT-2026-10-20.md` | report 1 (5,400 words), after three refuters |
| `harness/cm2lab.py` | the exact mirror of `loader/a.py`'s `d()`, parametrised (orders, boost, update, shift, prior, tag); ideal bits and the exact big-integer rANS size; `decode_ref` runs the owner's `d()` verbatim from an a.py text. Verified: x identical to `build/loader/data.txt`'s integer |
| `typed-arms/` | lab: about 70 model arms at the typed rung in a.py's style, each round-tripped through the modified `d()`; `RESULTS.md`, `results.json`, `arms.py`, `final.py`, `typesim.py` (a stage-1 typing simulation), `sim_*/` the finalists' a.py + data.txt |
| `encoder-side/` | lab: the compression-aware rename and rewrite of the typed reader (`reader_v2_encoder.py`, `a_rw2.py`, `data_rw2.txt`, `r_rw2.py`), the monolith pipeline (`mono_final.py`, `names*.py`, `rewrites.py`, `mono_test_results.json`), primer composition (`primer_ideal.json`), a C re-implementation of cm2's ideal bits for speed (`cm2h.c`, `cm2c.c`, `cm2lib.c`; matches the Python harness to 1e-9) |
| `strong2-integer-tricks/` | lab: strong2 with the one-integer rANS (`dec_s2rans.py`), block reset (`dec_s2rblk{14,16,18}.py`), exact dicts (`dec_s2exact*.py`), the coder timing (`coder_bench.*`, `dt.*`), R2 costs (`arch_dec_cost.*`, `r2_exec.*`), cmmix-exact as a typed decoder (`cmx_d.a.py`) |
| `archive-14-pages/` | lab: strong2 arms (`arm_*.py`, `diffs/`), the ceilings (`ceil/*.log`: paq8l, lpaq1, xz on T1), file order (`orders.*`), dedupe (`dedupe*.*`), decoder-in-archive costs (`inarch.*`), `r2cost.jsonl` |
| `measure-2026-10-20/` | session 1's measurement runner: public codecs on T1–T4 and the primers (`results.md`, `results.json`, `scripts/`, `out/*.json`) |
| `literature/order.py` | the literature worker's file-order proxy script; its findings are in `workflows/agent-results/03-lab-v2/04-lit_gap-fill.json` |
| `refuters/` | the refuters' and the editor's own re-runs: `v2-code-measurement/` (a second harness `h.py`, `s2full.py` = strong2 on the whole T1 of this checkout), `v3-logic-record-literature/`, `v4-editor/`, and session 1's `session1-code/`, `session1-logic/` (the PAQ1-rule probes), `session1-crinkler-probes/` |
| `workflows/` | the three workflow scripts as run (prompts, model per agent, phases) and `agent-results/`: every worker's structured return, verbatim, with its model and phase (`02-…STOPPED` was abandoned when the branch was force-updated; no results) |
| `MANIFEST.sha256` | SHA-256 of every file here |

## How it was done

- Workers per `.claude/rules/workers.md`: every reader, researcher,
  builder, synthesizer, refuter and editor an Opus agent with the model
  pinned in the script; no Sonnet or Haiku stage was needed except the
  final audit of this directory. The prompts are the scripts.
- Machine: a cloud container, Debian, system CPython 3.13.16 (not the
  repo's `env/` 3.14t; the integer-only models cannot differ, the walls
  can), 4 CPUs, 15 GB, two agents at a time.
- The build of record was reproduced with `python3 bootstrap/build.py`
  after a shim for its hardcoded interpreter path
  (`env/bin/python`, `build.py:107`), then every
  tracked change it made (the print of record: a.py's constants, the data
  lines, the leaves, the page sidecars) was reverted. Its gitignored
  products are the payloads below.
- `bootstrap/r3/measure.py` and `bootstrap/r3/arch/measure_arch.py` produced the minified
  monolith forms (10,599 cm2 bytes, 9 B spare: identical to the record).

## The payloads and fixtures (regenerable; pinned, not committed)

| file | bytes | sha256 | how |
|---|---|---|---|
| a.py (print of record) | 855 | 70f51b9e3b7cff292634c25ed3e7da7962778622f39547d17bfc913bae32b7e1 | `bootstrap/loader/a.py` at 7dd8a9a6 (`d(v,4564,a)`, `y98y`) |
| a_build.py | 855 | 73e6c37c207fbdbdd64c599b21a5112ce58e0da73ae597ed95bcbf026df84466 | `bootstrap/build/loader/a.py` of this checkout's build (`4565`, `kw86`): the primer of every typed-rung number here |
| typed_reader.bin | 4,565 | e1da84de0ecf1c9f9ecb8a2ad6409ac969c07b008b29ec2ea238b3a01350ecd5 | `build/loader/r.py[569:]`; with a_build.py as primer: 1,797.125 B, 2,876 glyphs, 48 lines, x == data.txt |
| r.py | 5,134 | 75e25f93e0249ef97c479aa5c45057acd899a2a56d5e5f0c6715eeeab135a64d | `build/loader/r.py`, the R2 primer |
| data.txt | 3,116 | fa6b52e7d4e354f96a86c2f6063bc89c08b9b51ef581a04325aa37caa3c09bb0 | `build/loader/data.txt` |
| b.py | 55,550 | c8ee5267fd93eaf9cbc92dfee29e59ce2d9ca3fc3176095f5cd83662f0db1a9c | `build/bundle/b.py` (R2-FORMAT.md + readable reader): 15,776 B, 3 pages |
| monolith_ming.py | 24,460 | d7b76ed910f25c61f714b3556ccfad5ea80802cf522d8ca708589068a60cdb35 | `build/r3/arch/forms_arch/receiver_arch.minified-g.py`: 10,599 B |
| receiver_ming.py | 22,011 | a5e73c846de1fd311741f7465493a50e85fe662dbd05e1a814d40672e744a14d | `…/receiver.minified-g.py`: 9,415 B |
| T1.tar | 9,533,440 | c516744c73b1ec32877f2113fba6f7f81b8e9726708a5912caff37786aa72c98 | `bootstrap/r3/arch/trees.py` on this checkout (321 files; machine 1's was 9,523,200) |
| T1.shar | 9,295,466 | b75132d9cd758f36a57c5ad19e06a63185c76a3e00c5dbd25a45d0be3f651caa | same |
| T1_1MB.tar, T1_2MB.tar | 1,048,576 / 2,097,152 | 13a01975cfcea3920da583a2cdab7dfbd451e2c535d64d69b3679216d91bae65 / 0bd3fea06f0c5d7a43266f109c7e77b74a52a653131f108a84de4d20616f713f | `head -c` of T1.tar |
| T1_8k.py, T3_32k.txt | 8,192 / 32,768 | ff630057… / 5a0548a0… | `bootstrap/record-2026-10-18/fixtures/` |
| bundle.bin, reader.py (session 1 stand-ins) | 24,987 / 8,177 | 1f1099b7… / 2db40d2a… | `git show a7c0453:bootstrap/pages/r2/bundle.bin` and `git show a7c0453:bootstrap/r2reader/reader.py` (neither is in the tree at 7dd8a9a6) |

## Excluded from this directory, and why

- Compiled public codecs (lpaq1, paq8l, paq1, fpaq0, fpaq0f2, upkr) and
  their sources (mattmahoney.net, github.com/exoticorn/upkr, Crinkler's
  CompressionState.cpp, DCE, the LTCB page): third-party; cited by URL in
  the reports and the agent results.
- Compressed outputs (`coded/`, `ceil/*.paq8l|lpaq9|xz`, the public codecs'
  `.o/.z` files), the five 9.5 MB re-ordered tars of the order experiment,
  the Canterbury files, the 2 MB block-reset stream: derived, large,
  regenerable from the scripts.
- The venvs, the python-minifier wheel, the checkout of 2fa8fd5 used to
  rebuild T4: tooling.
- The payloads above: build products of `bootstrap/build.py`.
- The abandoned first lab run (`workflows/02-…STOPPED`): its two partial
  directories held no results.

## Caveats the owner should carry

- Two refuters (41 corrections, applied) and one editor; several claims
  remain unrefuted and are so marked in the report.
- The rw2 reader (3,788 typed) passed the stage-1 chain and reads the
  build's pages identically to the record reader on 11 frames plus b.py;
  the record's 57-capture `xpage_e2e` set was NOT run on it.
- The monolith pipeline (10,599 → 9,876 B) passed `test_arch`'s scan-free
  cases; the scan path was not exercised.
- Archive extrapolations are the ratio on a 1–2 MB prefix applied to
  9,533,440 B; strong2's lead grows with n, so they are ESTIMATES.
- The typed-rung numbers use this build's a.py (4565/kw86), one glyph
  from the print of record (4564/y98y): 3,894 against 3,895.
- Nothing here is adopted. The rw2 reader, the short order tuple, the
  Crinkler masks, the monolith pipeline, the exec route, CRH cap 8 vs 11
  and the three archive A/Bs are rulings owed to the owner (LEVERS
  §§1–4 and its table).
