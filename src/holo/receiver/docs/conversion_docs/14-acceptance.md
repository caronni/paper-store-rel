# 14 — Acceptance inventory (volumes, scans, shas, closing invocations, sim recipe)

Distilled 2026-08-28 from experiments/029, /032, /033, docs/COLOR-UPLIFT-MEASUREMENTS.md,
docs/PLANE-FIELDS.md, .claude/memories/e029|e030, tests/holo/_color_uplift_harness/provenance.json,
and a disk walk of scratch. Every file below was verified to EXIST at the
listed absolute path and size. Multi-GB tiff sha256s are AS RECORDED IN LOGS (not re-hashed);
payload .bin files (<2 MB) were re-hashed here and MATCH the logged values exactly.

## 1. Purpose, inputs, outputs

Purpose: the ground-truth ledger for holo3 acceptance steps 1–8 (00-plan.md). Not a src/holo/receiver/
module — this drives `_distill/verify/` scripts and manual runs. Inputs: scan tiffs (read-only,
main worktree), emitted-volume dirs (payload-counting.bin, page000_gt.npy, manifest.json).
Outputs: recovered payload bytes; PASS = byte count AND sha256 equal the pinned values.

Capture raster facts (what intake must accept):
- Canon 4800 grey, full platen: single-frame u8 grey TIFF, 2,291,818,718 B.
- Canon 4800 RGB, full platen: single-frame u8 RGB TIFF, 6,875,455,728 B.
- Canon 2400 RGB, full platen: single-frame u8 RGB TIFF, 1,718,864,112 B.
- DPI is OPERATOR-DECLARED TRUTH (`--scan-dpi`), never measured from the page (033.2).
- Payload out: raw payload bytes only — the {sha256}{len:4B BE}{data} envelope is stripped by
  the close; recovered.bin sha == emitted payload-counting.bin sha.

## 2. The acceptance volumes — pinned record

All paths absolute. "closing invocation" = the holo1 command that produced the VERIFIED close
(from e029 log / provenance.json flag reconstruction — holo1 CLI records no argv; provenance's
per-flag evidence is events.jsonl/report.json shapes). Cert counts are tree-dependent; the
byte count + sha are the acceptance bar.

### Vol 2 — e029 HP K (acceptance step 2)
- Spec `c2-r0700@3392x2368` (53x37=1961 tiles, cell=2 dots, K family, q=0.7, K=1356,
  seed `holo/v1/c2-r0700/3392x2368`), hp-m281-ink footing 4.5 mm — NOT in FORMAT_ROWS:
  decode REQUIRES `--coding c2-r0700 --printer hp-m281-ink` (or `--format L:c2-r0700@3392x2368`,
  fossil margin_mm 4.0 — quantization-identical cell matrix).
- Scan (the ONLY e029 scan; Canon 4800 grey, 2026-08-04 21:08):
  `scratch/e028/hp-canon-c2-ink-counting.tiff`
  2,291,818,718 B, sha256 `d9c4e932b904b8173ef0bf08165f384ed2ce644105f58965d2dca14165672c22`.
- Payload: 465,580 B sha `e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af`
  at `scratch/e028/holo-c2-r0700-q07-ink-counting/payload-counting.bin`
  (emit dir also holds page000.ps, page000_gt.npy, manifest.json, receive.state 8.2 MB, recovered.bin).
- Closing invocation (e029 log; full-harvest variant added `--complete --refine`, NO `--page`
  → full 133-page cold domain; provenance: complete=true, refine=true, diag=true, page=null):
  ```
  ./confetti.py decode scratch/e028/hp-canon-c2-ink-counting.tiff --scan-dpi 4800 \
    --coding c2-r0700 --printer hp-m281-ink \
    --state scratch/e028/holo-c2-r0700-q07-ink-counting/receive.state \
    -o .../recovered.bin [--diag] [--complete --refine]
  ```
- holo1 yield 1940/1961 = 98.9% (+5 BP150); PK-FINAL full re-decode: cert-ID set IDENTICAL,
  2,376 s wall / 9,118 s CPU / 41.1 GiB @ workers 8 (no --page). With `--page 0` expect the
  xerox-K class (~1,900 s). Failure geography = HP horizontal banding (rows 20–22 both extreme
  columns, interior row-42 band), NOT margin.

### Vol 3 — xerox c3-cmy7 (step 3)
- Spec `c3-cmy7-p120-v0@2240x1536` (35x24=840 tiles, K=404, q≈0.5, joint pack7 codec, 6 mm,
  emit printer row hp-m281 — decode `--printer hp-m281` regardless of engine, e030 memory).
- Scan: `scratch/in/xerox-canon-c3-cmy7-2400dpi.tiff`
  1,718,864,112 B, sha `20fc40cd483277a4cad81d3299e228b2f89a16058c64666d8953b00ab0b6babf`.
  THE ONLY 2400-dpi capture of the e032 five.
- Payload: 301,600 B sha `4f68dbf932324aa85c1af576b9724504eb5dff85039a66a062ff9c9adc4e50c2`
  at `scratch/e030/holo-c3-cmy7-q05-counting/payload-counting.bin`.
- Closing invocation (provenance flags: page=[0], complete, refine, diag; scan_dpi 2400):
  ```
  ./confetti.py decode scratch/in/xerox-canon-c3-cmy7-2400dpi.tiff --scan-dpi 2400 \
    --coding c3-cmy7-p120-v0 --printer hp-m281 --page 0 --complete --refine --diag \
    --state scratch/in/holo-xerox-c3-cmy7-counting-receive.state \
    -o scratch/in/holo-xerox-c3-cmy7-counting-recovered.bin
  ```
- Yield 720/840=85.7% (holo1 e032) → 810 (uplift PK-FINAL). Resources: 2,073 s wall /
  4,775 s CPU / 12.8 GiB @8 — the CHEAPEST real volume; use it for holo3 smoke and for
  acceptance step 8 (workers 8 vs 1: two runs fit one afternoon).

### Vol 4 — xerox c2-cmy8 (step 4) — first CMY8 from paper
- Spec `c2-cmy8-p120-v0@3328x2304` (52x36=1872 tiles, per-plane independent LDPC C/M/Y,
  cert ceiling ~5616, K=918, q=0.5, 6 mm, -v0 = per-stream fountain, NOT pooled).
- Scan: `scratch/in/xerox-canon-c2-cmy8.tiff`
  6,875,455,728 B, sha `cf6427d0d66a3cb9af0b74f7162f5b163dd2f2f75bcf162940326ef6cc8aec47`.
- Payload: 718,413 B sha `f13c34db6c96796e65c812b7bb99e7618625e49a34640fcee58bc4627e38ecca`
  at `scratch/e030/holo-c2-cmy8-q05-counting/payload-counting.bin`.
- Closing invocation (provenance: page=[0], complete, refine, diag):
  ```
  ./confetti.py decode scratch/in/xerox-canon-c2-cmy8.tiff --scan-dpi 4800 \
    --coding c2-cmy8-p120-v0 --printer hp-m281 --page 0 --complete --refine --diag \
    --state scratch/in/holo-xerox-c2-cmy8-q05-counting-receive.state \
    -o scratch/in/holo-xerox-c2-cmy8-q05-counting-recovered.bin
  ```
- Yield 5370 certs (95.6%) holo1 → 5466 uplift. Resources: 4,180 s / 6,670 s / 41.9 GiB @8.

### Vol 5 — xerox c2-r0700 K (step 5)
- Same spec/payload as Vol 2 (same emitted volume, re-printed on the AltaLink).
- Scan: `scratch/in/xerox-canon-c2-bw.tiff`
  2,291,818,718 B, sha `57a261454cc04e66bd333310df4d17ede867eaa862fe6cff20e5395799d927e3`.
  NOT e031's discovery sheet `xerox-canon-cal-bw.tiff` (sha 65e8bf50…, identical size!).
- Closing invocation (provenance: page=[0], complete, refine, diag):
  ```
  ./confetti.py decode scratch/in/xerox-canon-c2-bw.tiff --scan-dpi 4800 \
    --coding c2-r0700 --printer hp-m281-ink --page 0 --complete --refine --diag \
    --state scratch/in/holo-xerox-c2-counting-receive.state \
    -o scratch/in/holo-xerox-c2-counting-recovered.bin
  ```
- 465,580 B, sha == Vol 2. Yield 1930/1961 = 98.4% (engines within 0.5 pp on K).
  Resources: 1,932 s / 2,390 s / 40.3 GiB @8 (4800 grey full decode is 40-GiB class in holo1).

### Vol 6 — xerox c2-cmy7 (step 6) — the colour-uplift close
- Spec `c2-cmy7-p120-v0@3328x2304` (1872 tiles, K=920, q=0.5, joint base-7 pack across planes,
  symbol_bits 5973). FAILED live in e032 (83 certs, 1789 LDPC failures, addressing HEALTHY:
  99.8% footprint, 1489 word matches); closed 2026-08-10 ONLY by the merged colour-uplift
  receiver (calibrated cmy7 head + satfloor30, multi-state ctx matrix, demapiter3 — CORE holo3
  colour function, not arms).
- Scan: `scratch/in/xerox-canon-c2-cmy7.tiff`
  6,875,455,728 B, sha `01abdd8785c55616faa89958632c84c5d66711492ef643d031af330773f7e426`.
- Payload: 686,859 B sha `5963b9d16abca48d66a05f80eb137ce76624b8fdedb48ce13c3ee0cf8f24c993`
  at `scratch/e030/holo-c2-cmy7-q05-counting/payload-counting.bin`.
  NO archived holo1 recovered.bin predates the campaign; the closing state is
  `scratch/color-uplift/full/xerox-c2-cmy7-pkfinal/receive.state`,
  run JSON `scratch/color-uplift/runs/xerox-c2-cmy7-full-pkfinal.json`.
- Closing invocation: NOT plain CLI — campaign harness at tree 4577652:
  `PYTHONPATH=src:tests/holo HOLO_RECEIVE_WORKERS=8 env/bin/python -m _color_uplift_harness.ab_runner
   full --capture xerox-c2-cmy7 --arm pkfinal --diag --diag-port 8023` (launcher
  `scratch/color-uplift/pkfinal_one.sh`, retired 2026-10-09), archived flags applied: page=[0], --complete, --refine,
  scan-dpi 4800. Post-merge (ce430e3) the equivalent PLAIN invocation on main is the Vol-4
  shape with `--coding c2-cmy7-p120-v0` — reconstructed, never operator-verified verbatim (open Q3).
- Yield 1,559/1,872 = 83.3%, +1,476/−0 strict superset, 0 wrong / 18,595,752 audited cells.
  Resources: 8,962 s wall / 23,423 s CPU / 41.7 GiB @8 — the most expensive acceptance volume.

### Vol 7 — sheet I fossil, pooled CMY8 rung (step 7)
- Spec fossil `L:c2-cmy8-r0700-p120-x1@3392x2368` (53x37=1961 tiles, POOLED fountain: one code
  over esi=counter*3+stream, 3x1961=5883 symbols, K_total 5277, q=0.9, n_filler=20, margin 4 mm,
  seed bytes `holo/v1/c2-cmy8-r0700-p120-x1/3392x2368`, src/holo/format/fossils.py:119,136-141).
  Byte-matched, never parsed.
- Scans (Canon RGB; sha file `scratch/xerox-v1-20260818/scan-shas.txt`; all three platen
  placements distinct; all under scratch/):
  - `xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm-2400dpi.tiff` 1,718,864,112 B
    sha `269d81217ec48a5e57ae5736baf091f0afe3f66dd15539c0f39dfc6cffdea30c`
  - `…-2400dpi-displaced.tiff` 1,718,864,112 B
    sha `a410631d6ff6a8519767a4cdb7c55bd6e5b90b549a7450d017e783064991e8dd`
  - `…-2400dpi-displaced2.tiff` 1,718,864,112 B
    sha `36b90a50f272bb02982286b18657a8630eaa378eb7ac553e3a54461e548d55af`
  - (`…-4800dpi.tiff` 6,875,455,728 B sha `5d24205330ff296534c3330305c84f1abb53c89fb3326d36174ceba7b5c98b0a`
    = the owed MECHANISM scan — never in the acceptance state; separate state only.)
- Payload: 1,798,761 B sha
  `2445b95db5b49bf3e05eb2538e9e247d289a48a4fed2e46eb7ba78ab61e4350b`
  at `scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/payload-counting.bin`
  (dir also holds manifest.json, page000.ps, page000_gt.npy, the archived VERIFIED
  receive.state 3.68 GB + .diag).
- Closing invocation: branch `c4-row` (dropped), fresh state, three 2400 captures, `--refine`;
  on TODAY'S main the validated stock-CLI form (fossil replay bit-identical, 5297 cert
  identities; live post-merge runs used exactly this shape, PLANE-FIELDS §7.4a):
  ```
  ./confetti.py decode \
    scratch/xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm-2400dpi.tiff \
    scratch/xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm-2400dpi-displaced.tiff \
    scratch/xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm-2400dpi-displaced2.tiff \
    --scan-dpi 2400 --scan-dpi 2400 --scan-dpi 2400 \
    --format L:c2-cmy8-r0700-p120-x1@3392x2368 --refine \
    --state <fresh>/receive.state -o recovered.bin
  ```
  (`--format` REPLACES `--coding`/`--printer` — CLI refuses the pair, cli.py:386-393.)
- Certs 5,297 (M 1958 / C 1895 / Y 1444; Y dead bands = MEASURED printer Y x-registration
  sinusoid, 0.83 dot peak, ~100 mm period). Close verified IN-FLIGHT before `--complete`.
  Resources (plane-fields tree, dial ON, 12-level plan x3 captures): 2 h 18 m, ~11.6 GB peak.
  Single capture alone = SHORTFALL 125 (reach 5152/5277) — the three-capture pool is REQUIRED.

### Negative controls on disk (not acceptance, useful for no-false-accept checks)
- `scratch/in/hp-canon-c2-cmy7.tiff` 6,875,455,728 B sha
  `c05354349a4ba844b2c1d0d69686f4b97e3ca1f2c0b2ff4fca84cba7f76c0e32` — M281 print, never
  addressable (60.3% footprint, 47 words, 0 LDPC calls). holo3 must refuse cleanly, not close.
- Every capture/state/GT/payload sha of the 8-capture uplift corpus is pinned in
  `tests/holo/_color_uplift_harness/provenance.json` (both worktrees).

## 3. Sim capture + truth payload (acceptance step 1) — data-producer recipe

Producer = MAIN worktree src/holo (format authority), run from <repo> with
`PYTHONPATH=src env/bin/python`; outputs ONLY under `<checkout>/_distill/verify/sim/`.
Recipe is the proven in-repo e2e (tests/holo/test_lattice_receive.py:61-106 K,
:113-159 colour; constants from tests/holo/_roundtrip_fixture.py: _PAPER=245, _INK=35,
optical PSF = gaussian_filter sigma 0.5).

K sim (format id `c3-k-r0550@7x7`, q=0.5, one page; field 7*64*3=1344 dots square):
```python
# <checkout>/_distill/verify/sim/make_sim_k.py
import hashlib, numpy as np, tifffile
from scipy import ndimage
from holo.format.resolve import resolve_format_ref
from holo.gen.plan import plan_volume
from holo.gen.emit import METADATA_VERSION, source_packed_for
from holo.gen.compose import compose_page_cells, cells_to_dots
from holo.core import fountain
OUT = "<checkout>/_distill/verify/sim"
spec = resolve_format_ref("c3-k-r0550@7x7")
payload = hashlib.sha256(b"holo3-sim-k").digest()          # 32 B truth
plan = plan_volume(spec, len(payload), 0.5)
source = source_packed_for(payload, plan)
code = fountain.VolumeCode(plan.k_total, plan.symbol_bits, spec.seed,
                           tiles_per_page=spec.tiles_per_page)
esis = np.arange(spec.tiles_per_page, dtype=np.int64)
cells = compose_page_cells(spec, 0, code.encode_symbols(source, esis),
                           plan.k_total, version=METADATA_VERSION)
dots = cells_to_dots(cells, spec.cell_dots)
b = 96; h, w = dots.shape
canvas = np.full((h + 2*b, w + 2*b), 245, np.uint8)
canvas[b:b+h, b:b+w] = np.where(dots != 0, 35, 245)
canvas = ndimage.gaussian_filter(canvas.astype(np.float32), 0.5)
tifffile.imwrite(f"{OUT}/sim-k-600dpi.tiff",
                 np.round(np.clip(canvas, 0, 255)).astype(np.uint8))
open(f"{OUT}/sim-k-payload.bin", "wb").write(payload)
```
Run: `cd <repo> && PYTHONPATH=src env/bin/python <script>`.
Decode (holo1 oracle first, then holo3 must match): `--scan-dpi 600 --format c3-k-r0550@7x7
--page 0`. NOTE the u8 quantization of the blurred float canvas is a (tiny) departure from the
in-memory float32 the test feeds — verify the oracle closes it once before pinning (open Q4).

Colour sim (`c3-cmy8-r0550x0550x0547@10x10`, q=0.35, 1200 dpi, the P6-reviewed 273-cert page):
emit via `holo.gen.emit.emit_volume(spec, payload, 0.35, outdir)`; unpack `page000_gt.npy`
(shape (3, field_h, field_w/8), MSB-first packbits per plane) to C/M/Y coverage; pad border
60 dots of zeros; `np.repeat(...,2,axis=0/1)` to 2 px/dot; push through
`holo.qualification.color_synthetic.render_color_scan(source)` (deterministic defaults);
`round(rgb*255)` u8 RGB tiff; decode `--scan-dpi 1200 --format c3-cmy8-r0550x0550x0547@10x10
--page 0` (exact lines: test_lattice_receive.py:121-150). This exercises the pooled path in
miniature ahead of Vol 7. (Its rung triplet is width-classed MIXED — also pins gen-v1 rung parsing.)

## 4. Pooling rules (which captures share a state)

- Vol 7 is the ONLY pooled acceptance decode: the three 2400 sheet-I captures, one state.
  All other volumes: exactly one capture, one state.
- One ordinary state freezes one DPI (e023b physical-evidence invariant): the sheet-I 4800
  scan NEVER enters the 2400 state — fresh state only.
- Never raw + its own decimation in one state (double-counts one physical capture, F1∘F6 law).
- Never captures of DIFFERENT physical sheets of one spec in one state (018b rule) — beware
  `xerox-canon-cal-bw.tiff` vs `xerox-canon-c2-bw.tiff` (same size, different sheets).
- Multi-scan gains require RE-PLACED captures (distinct platen poses) + a de-correlating ctx
  detector; 3–4 scans is the knee. Equal-weight pooling on a global detector LOSES to best-single.
- Scheduling: ONE production decode at a time (64 GB machine; holo1 4800 full decodes peak
  40–42 GiB @ workers 8; 2400 class 11.6–12.8 GiB). Budget holo3 as holo1-class until measured.

## 5. Copy-vs-rewrite

| what | verdict | source |
|---|---|---|
| Fossil catalogue (seed bytes, cells, margins, FossilCoding bundles) | COPY-AND-STRIP verbatim — seed bytes are format law | src/holo/format/fossils.py:79-149 |
| K sim canvas recipe (245/35, border 96, sigma 0.5, 600 dpi) | COPY into verify script (not src/holo/receiver/) | tests/holo/test_lattice_receive.py:61-106; tests/holo/_roundtrip_fixture.py:33-99 |
| Colour sim recipe (emit_volume→GT unpack→repeat 2x→render_color_scan) | COPY into verify script | tests/holo/test_lattice_receive.py:113-159 |
| render_color_scan + ColorChannelParameters defaults | USE AS-IS from main src/holo as data-producer; never port into src/holo/receiver/ | src/holo/qualification/color_synthetic.py:363+ |
| provenance.json sha ledger | READ as data (both worktrees carry it) | tests/holo/_color_uplift_harness/provenance.json |
| holo1 CLI decode flag semantics (--format vs --coding/--printer exclusivity, per-scan --scan-dpi append) | REWRITE lean in holo3 cli.py, same surface | src/holo/cli.py:339-420,849-935 |

## 6. Measured-channel invariants that MUST survive (acceptance-visible)

- Byte-exact close = the only PASS: sha256(recovered) == pinned emit sha (receiver correctness
  is defined by the emitted volume, nothing softer).
- Vol 6 closes ONLY with the uplift colour core (calibrated cmy7 head, multi-state ctx matrix,
  demapiter3) — dropping any of them regresses 1,559→83 certs; this is the acceptance test FOR
  that core.
- Vol 7 closes ONLY with pooled-fountain algebra (esi=counter*3+stream, stream-exact quotas)
  AND three pooled captures (single capture: shortfall 125).
- Vol 4 vs Vol 6 ordering inversion (cmy8 closes where cmy7 dies at c2): per-plane independent
  LDPC + graceful degradation is load-bearing; discovery/channel tiers must never gate decode.
- Sheet-I Y dead bands are printer x-registration (0.83 dot sinusoid), NOT toner/evidence —
  C/M carry the close; holo3 must not require healthy Y to close Vol 7.
- `cell=1 dead`, fixed-600 engines, hygroexpansion etc. are upstream print facts baked into
  these captures — holo3 never "corrects" a declared DPI (033.2: wrong declaration ⇒ clean
  geometry refusal, by design).
- Identical payload independent of worker count (step 8: workers 8 vs 1 byte-identical).

## 7. What to DROP

- Resume/journal/replay: every acceptance run is a fresh disposable run dir. No receive.state
  files, no `--complete`-on-resume semantics, no terminal-ingest guards, no `--no-close`
  (holo1 needed it only because resume re-solved verified closes).
- Discovery mode, DEFAULT_DISCOVERY_ROW_IDS, discovery-state magic dance (cli.py:383-420):
  acceptance always names its format. Keep only --format (incl. L:) and --coding+--printer.
- provenance-verify/tree-fingerprint/gt_score harness machinery — campaign scaffolding.
  Wrong-cert audits in holo3 are a verify-script concern, not production code.
- Diag viewer dependence: acceptance reads printed sha + byte count from the CLI, never
  status.json rows.
- `--source-sha256` enforcement of 6.9 GB tiffs per run (hashing costs minutes): trust path
  + size; identity was pinned once, here.
- The 133-page cold-domain sweep for single-sheet volumes: always pass the page-0 equivalent
  (e029's scheduler lesson; hp-c2-k paid full cold for 2 certificates).
- e016/e018 legacy-receiver doctrine (1600-decimation feeds) — paperholo-era, no holo sheet
  uses it.

## 8. Data-structure needs (src/holo/receiver/data.py)

- Capture: path (str), declared_dpi (float), mode ("grey"|"rgb"), sha256 (str|None, optional
  pin), capture_id (leading-12-hex of sha OR path-stem) — the e032 state-binds-to-sha idea,
  as data only.
- DecodeSpec resolution product: format_ref (str, canonical id or `L:` fossil), seed (bytes),
  family, tiles_yx, cell_dots, pooled (bool), n_streams — everything §2's invocations name.
- CloseResult: payload (bytes), payload_sha256 (str), n_bytes, verified (bool), per-stream
  certificate counts (dict) — the CLI prints sha + bytes (the acceptance interface).
- Certificates carry source tag (plugin id) + stream_id ("main"|"C"|"M"|"Y") so per-plane
  concentration (e030 C620/M43/Y0 class diagnostics) falls out of the ledger for free.
- Per-plugin accounting fields (jobs, cpu_s, certificates) — step 8's speedup evidence.
- Everything above is a FACT record (single-writer merge); nothing here is shared-mutable.

## 9. Pitfalls / incidents

- Misdeclared-dpi (033.2): 2400 raster declared 1200 → pitch-contradiction refusal in seconds.
  Correct behaviour; do not "fix" by measuring pitch (feedback: don't measure known quantities).
- Identical-size different-sheet tiffs (cal-bw vs c2-bw, both 2,291,818,718 B): path typos
  produce clean-looking garbage runs. Check the sha prefix when a K volume mysteriously fails.
- manifest.printer_id lies about the engine (e032: xerox sheets carry hp-m281 rows) — emit-time
  parameter only; never infer engine from manifest.
- e029 fossil margin nuance: fossil says 4.0 mm, physical sheet was 4.5 mm request — same cell
  matrix by tile quantization; both decode routes are valid.
- Sheet-I archived state replay ≠ fresh decode: fossil-route REPLAY is bit-verified on main;
  fresh three-capture decodes on merged main exist but under later trees (5,164 one-capture,
  5,549 dial-ON) — cert counts drift with tree, sha does not.
- Provenance argv gap: holo1 CLI records no argv; §2's flags are evidence-reconstructed
  (events.jsonl close-check shape, report.json page_domain, status.json lane dpi). holo3
  should print its full argv into the run dir (one line, not a journal).
- Memory: three concurrent jobs once killed a production H decode (memory-budget feedback).
  4800 colour @8 workers ≈ 42 GiB in holo1. Run acceptance strictly serially.
- Timing honesty: e029 wall "not cleanly measured"; only PK-FINAL and W6 numbers above are
  clean — cite those, and label holo3's own timings by tree + workers.

## 10. Open questions for the contract author

1. Acceptance runner home: plan says decodes run one at a time — should a tiny serial driver
   script (reads a JSON manifest of §2, runs holo3 CLI, checks shas) live in `_distill/verify/`
   permanently, or is manual invocation the contract?
2. holo3 CLI surface for step 2: `--coding c2-r0700 --printer hp-m281-ink` needs a devices
   registry in holo3; alternative is fossil-only (`L:c2-r0700@3392x2368` covers Vols 2+5).
   Does holo3 carry a printer registry at all, or do fossils + `--format` subsume it?
3. Vol 6 has never been closed by a PLAIN CLI invocation on any tree (harness-only close).
   Is the reconstructed plain invocation (Vol-4 shape, coding c2-cmy7-p120-v0) the accepted
   target, or should holo1-on-main be run once to establish it before holo3 is measured?
4. Sim tiff quantization: pin u8 tiffs (recipe above) after one holo1-oracle confirmation run,
   or mandate float32 tiff support in holo3 intake to match the in-memory tests exactly?
5. Step 8 sheet: recommend Vol 3 (cheapest, 12.8 GiB class) — confirm, or is a colour 4800
   volume required to make the >=3x claim representative?
6. Are cert-count floors part of acceptance (e.g. Vol 7 >= 5,277 reach) or is byte-exact close
   alone the bar? (Counts are tree-dependent; the plan names only bytes.)
7. Negative control: should hp-canon-c2-cmy7 (must NOT close, must refuse cleanly) be added as
   an explicit acceptance step? It is free evidence against false-accept.
