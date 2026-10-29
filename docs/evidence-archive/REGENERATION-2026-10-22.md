# Regeneration spans of the paperholo-era evidence — measured 2026-10-22

The question (owner, 2026-10-22, while shaping the public repository): for the
paperholo-era release, which is the earliest and the latest commit that can
generate each published artefact, and can one tree — current main — generate
and, as far as a decode is possible at all, decode everything in it?

**Answer: yes.** Current main (`ba7693da`, 2026-10-18) regenerates every
published job of the paperholo-era release byte-identically, fifteen
families outright and four through one hoop each (§4). The decode drivers
the release names all exist at main, two of them only at main (§5). No old
tree is needed. The published READMEs' instruction to run at the tag
`evidence/main-regen-20261009@53451bc4` can therefore be replaced, when the
metadata is regenerated, by the public repository's own release cut.

## 1. Method

- **Candidates.** Every commit on main's ancestry that touched `src/paperholo`
  or any of the twenty generator scripts (the nineteen `paperholo` rows of
  `measure/evidence_regen/families.py` plus `emit_e025.py`), 68 commits from
  `1ac06a4d` (2026-07-03) to `ba7693da`, plus the three anchors
  `pre-v1-v2-deletion` = `80041d52` (2026-09-04), `main-regen` = `53451bc4`
  (2026-10-09) and main; then every commit between two consecutive candidates
  whose verdicts differed, 16 more; 84 trees in all. The sibling modules the
  generators import (`gen_calpage`, `gen_composite_probe`, `gen_modprobe`,
  `gen_disc1`, `motif_codec`, `e025_common`) have no commits outside that set,
  so the sweep covers each generator's dependency closure. A commit that
  touches none of a family's inputs cannot change its output.
- **Instrument.** `measure/evidence_regen/span_sweep.py` (added with this
  record): one detached worktree per commit, every family regenerated there
  with the main checkout's interpreter, every produced file compared by
  sha256 against `docs/evidence-archive/hashes-retained.tsv` by archived
  path, exactly as `regen` does. Three families the family table has no
  runnable row for were run the same way with one-off step lists (§4).
- **Environment.** `env/` of 2026-10-22: free-threaded CPython 3.14, numpy
  2.5.2. Identity therefore holds for today's environment at those trees;
  that the July bytes come out of today's interpreter is itself the
  measurement.
- **Refutation.** Four Opus refuters, one per load-bearing claim (method,
  e018, e025 -v1, fullpage), and one Sonnet completeness check over the
  release manifest. Every claim survived; the one objection (the fullpage
  manifests) was already settled by the write_gt run of §4.

## 2. Per-family spans

Latest = main means byte-identical at `ba7693da`; `80041d52` and `53451bc4`
agree with main on every family. "Earliest" is the generator's own first
commit in every case but e025 and e018.

| release directory, artefact | files | earliest identical | latest identical | holes in the span |
|---|---:|---|---|---|
| 001 gridtest, linetest, 001_patterns (also 007 altalink-library) | 2+2+2 | `58c79142` 2026-07-04 | main | none |
| 002 calpage, composite probe, overlap2 | 2+2+2 | `f7017d69` 2026-07-04 | main | none |
| 003 modprobe; pilot_viz (007 altalink-library) | 2+1 | `446c3b82` 2026-07-04 | main | none |
| 004 finalists | 3 | `edef6be0` 2026-07-06 | main | none |
| 006 e006bw, e006c | 6 | `66936b16` 2026-07-06 | main | none |
| 007 m281-disc1 | 2 | `019e2936` 2026-07-06 | main | none |
| 007 fullpage pair: PS | 2 | `cb2a8ffb` 2026-07-07 | main | none (§4.3) |
| 008 msel1 | 2 | `cb2a8ffb` 2026-07-07 | main | none |
| 009 ores (3 pcl, pjl, job, manifest) | 6 | `cd5dee51` 2026-07-07 | main | none (§6) |
| 010 motif1 | 2 | `dc60a288` 2026-07-07 | main | none |
| 011 e011; 012 e012 | 2+3 | `46795e6d` 2026-07-08 | main | none |
| 014 e014 | 3 | `50f749bf` 2026-07-08 | main | none |
| 016 e016 | 2 | `66f9bfe2` 2026-07-09 | main | none |
| 017 e017 | 2 | `80a61a01` 2026-07-10 | main | `26f83e82`, a side-branch commit that predates the generator on its own line (not a breakage) |
| 018 e018: page, manifest, payload tar — self-contained | 3 | `eb5174e9` 2026-07-10 | `f8de66eb` 2026-07-10 | none; four trees: `eb5174e9`, `56918373`, `e98346df`, `f8de66eb` |
| 018 e018 — payload tar supplied | 2 | `f3b71a6d` 2026-07-08 | main | none (57 of 63 trees; the six before `f3b71a6d` lack `paperholo.fountain`) |
| 018b c2, c3 — payload supplied | 4 | `eb81e351` 2026-07-16 (the generator's one commit; not swept below main) | main | — |
| 025 bw-01, color-01 | 4 | `dac54673` 2026-07-17 | main | none (`9df37bf1`, `5d8f9fa2`, `bdc9c54b` emit different bytes) |
| 025 bw-v1, color-v1 — self-contained | 4 | `9df37bf1` 2026-07-16 | `45275eda` 2026-07-16 | none (`5d8f9fa2` renames the presets) |
| 025 bw-v1, color-v1 — v1 scripts supplied | 4 | not swept | main | — |

## 3. What this overturns in the record

`measure/evidence_regen/README.md`'s verdict table and `families.py` call
four of these not regenerable. All four are overturned by measurement:

- **e018** ("gen_e018.py tars the CURRENT src/paperholo"): the tar is
  deterministic (mtime 0, sorted, gzip level 9 with mtime 0), and four trees
  of 2026-07-10 reproduce page, manifest and tar exactly; `06a8134c`, the
  commit that then added the generator, changed `formats.py` and `place.py`,
  both in the tar's CORE list, and broke it. The archived page's mtime
  (2026-07-11 10:38) precedes that commit (16:02), which fits.
- **e018b** ("the HEIC payloads were deleted"): the payload is the page's
  content and comes back out of the published PostScript in the clean domain
  (§4.2), after which main re-emits both jobs and manifests exactly.
- **fullpage** ("the caller is lost", later "regenerable at the tag
  `cb2a8ffb`"): the recovered driver reproduces both pages at every tree from
  `cb2a8ffb` through main; manifests and payload arrays too once it writes its
  ground truth (§4.3). The tag is not needed.
- **e025 -v1** ("45275eda-era, sha not pinned anywhere"): the hashes are
  pinned in the print-run table of `45275eda`'s RESULTS.md and in
  `hashes-retained.tsv`; the pair regenerates from its own two trees and,
  with the first script version, at main (§4.4).

## 4. The four hoops

### 4.1 e018 — supply the payload tar

Three independent sources of the tar (sha256
`4c75fe59241499a827293a1c6b9261a306a3936678d46ec78843feea1d17c44d`,
103,195 B): decode the page (the e018 sessions did, byte-exact, e018 log
§018.0); regenerate it from any of the four 2026-07-10 trees (copy main's
`gen_e018.py` in, call `make_targz()`); or keep the file as a fossil beside
the generator. Then at main, with the tar bytes in place of `make_targz()`:

```text
import importlib.util, pathlib
s = importlib.util.spec_from_file_location("gen_e018", "experiments/018-confetti-c3-play/gen_e018.py")
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
data = pathlib.Path("recovered_e018.tar.gz").read_bytes(); m.make_targz = lambda: data; m.main()
```

Page `a691c7d7…` and manifest `f8d6d401…` byte-identical at 57 of 63 swept
trees from `f3b71a6d` (2026-07-08, the commit that added
`paperholo.fountain`) through main. The manifest records the payload's hash
and file list, not its bytes, so it is exact by either route.

### 4.2 e018b — recover the payload from the page

`measure/evidence_regen/clean_decode_e018b.py` (added with this record):
`util/ps_gt` gives the K bitmap of the published job, the compose inverse the
payload stream, a real belief-propagation decode with exact likelihoods the
per-tile codewords (syndrome and CRC-32 gated), the fountain decoder the
bytes; only `data_len_bytes` comes from the manifest, since fountain-v1 does
not carry it in-band. Measured on the published pair:

| profile | interior tiles | fountain rank | recovered | sha == manifest | decode wall |
|---|---:|---:|---:|---|---:|
| c2 | 1,734 / 1,734 | 737 / 737 | 192,160 B | yes (`424e41a2…`) | 28 s |
| c3 | 782 / 782 | 338 / 338 | 88,157 B | yes (`012d9e3a…`) | 7 s |

A repair-only re-solve (every source symbol dropped) reaches rank by
elimination and yields the same bytes. Re-emission at main, the recovered
file named as the manifest's `input_name`, into the generator's default
build directory (so `print_command` is repository-relative):

```text
PYTHONPATH=src:. env/bin/python experiments/018b-payload-sheet/gen_e018b.py emit c2 build/lena_std-192.heic
```

c2 PS `995ef4ab…`, c3 PS `f8c948f9…`, manifests `3b2b4813…` and
`d86861cc…`: all four byte-identical to the published files. The payload is
the Lena test image, withheld from the archive under D1; keep the recovered
file out of git (`build/` is ignored). D1 accepted that the published pages
decode to it; this is what that looks like: under half a minute with the
repository's own modules.

### 4.3 fullpage — write the ground truth

`experiments/007-office-disc/regen_fullpage.py` as committed (`write_gt=False`)
reproduces `fullpage-bw-kcell-c2.ps` (`b3eb7999…`) and
`fullpage-color-a3-7st-c3.ps` (`94c773df…`) at every swept tree from
`cb2a8ffb` through main. Its manifests differ at every tree in one place, the
`fields[0].gt` block, which the archived manifests carry because the original
session wrote its ground truth. With `write_gt=True` at main, manifests
`0e662822…` and `1c290842…` and the two payload arrays (`ed6a766d…`,
`3471a797…`, compared against the release's `emission/` copies, which the
hash table does not list) are byte-identical. The driver's docstring still
says to check out the tag; that instruction is historical, not wrong.

### 4.4 e025 -v1 — run the first script version against main's library

```text
git show 9df37bf1:experiments/025-channel-metrology/emit_e025.py   > build/v1/emit_e025.py
git show 9df37bf1:experiments/025-channel-metrology/e025_common.py > build/v1/e025_common.py
PYTHONPATH=src:. env/bin/python build/v1/emit_e025.py --preset hp-m281-bw-v1    --out build/v1/hp-m281-bw-v1
PYTHONPATH=src:. env/bin/python build/v1/emit_e025.py --preset hp-m281-color-v1 --out build/v1/hp-m281-color-v1
```

PS `88f96b6d…` and `7e9a7edf…`, manifests `8c3f2f6c…` and `5b423f11…`, all
byte-identical. `paperholo/metrology.py` lost 166 lines after `9df37bf1`, but
the `CandidateSpec` and `GridSpec` the v1 scripts import survive unchanged.
These two sheets were printed once on 2026-07-16 (`45275eda`'s print-run
table), never scanned into the record, and superseded the next day by the
physical-metrology layout; nothing decodes them, by design (REASONING-LOG,
2026-07-17: "Git history is the decoder for the already printed atlas pair").

## 5. The decode side

No decode was re-run for this record (receiver runs are hours, and the
archive's decode records stand). What is checked:

- Every decode driver the release's "read by" column names exists at main,
  and `src/paperholo` has not changed since 2026-07-17 (`dd96e7f2`), so a
  driver that ran then runs the same code now.
- **Main is the right tree, not the tag.** The e014 and e016 decode drivers
  (`decode_e014.py`, `campaign_e014.py`, `alone_certify_e016.py`,
  `campaign_e016.py`, …), the e017 probes and the e022 probe were committed
  only after `53451bc4`, by `3c20bd87` and `d2249cb6` (2026-10-09, the D9
  commit set out of `scratch/`), with `--evidence-root` arguments naming the
  published paths. The published READMEs' "run at the tag" cannot reach them.
- The one decode measured today is the clean-domain one of §4.2, which proves
  the e018b jobs are what their manifests say they are. The e018 record
  already holds the equivalent for e018 (§018.0's pre-print gate and the
  scissors sessions).
- Artefacts with nothing to decode: 008, 009, 010 and 011 were never printed
  or are simulations; the fullpage pair and the e025 -v1 pair were printed
  but never scanned; 005 holds records only.

## 6. Completeness over the published job files

The release manifest lists 65 job files (PostScript, PCL, PJL, job manifests,
emission payload arrays). 56 have verdict rows in the sweep; the other nine:

- `009 ores_pspjl1200.job`: made by `gen_ores.py` but absent from
  `hashes-retained.tsv`, so never compared; regenerated at main and equal to
  the release's `MANIFEST.sha256` entry (`fd76f43b…`).
- `001 probe1.ps`: a tracked file, added `58c79142` and never changed; HEAD's
  copy equals the published one (`ca69e189…`). No generator; git carries it.
- `001 test_pattern.ps`: hand-written PostScript, its own source.
- the two fullpage payload arrays: §4.3.
- the four e018b files: §4.2.

## 7. Caveats

- "Latest = main" is measured at `ba7693da`; every later commit that touches
  none of a family's inputs inherits it. The one commit touching
  `src/paperholo` outside main's ancestry, `5bf9847c` (2026-08-06, on
  `origin/pilot-first-receiver` only), was not swept and is irrelevant to it.
- Each family compares the files its row names, and only those in the hash
  table; other outputs of the same generators (pilot_viz's zoom PNGs, gs page
  renders) are not compared.
- The e018 and fullpage hoops combine the commit's `src/paperholo` with main's
  driver; e018b and e025 -v1 use scripts of a single committed version.

## 8. Provenance

The sweep matrices (3,468 + 748 + 816 + 176 rows), the three one-off probe
harnesses (e018, fullpage, e025 -v1), the tar-supplied e018 sweep, the e018b
round trip and the e025 -v1 run were produced in this session's scratchpad on
2026-10-22 and are not retained; this record carries the compact extract, and
`span_sweep.py` regenerates the main matrix from the candidate list in §1 in
about five minutes at six parallel worktrees. The refuters' verdicts and the
completeness check are summarized in §1 and §6.

## 9. Addendum 2026-10-26: sheet J and the local-ab sim at main

The two holo-era families the driver pins at tagged trees (`sheet-j` at
`8260257d`, tag `evidence/sheet-j-generation-20260902`; `local-ab-sim` at
`63126a89`, tag `evidence/local-ab-sim-20260831`) were described in the span
records as "no longer regenerating" after the seed re-key `b8471fc0`
(2026-09-02, FORMAT-SPACE §16). That was wrong as worded. Measured at main
(`bdb8a791`): the re-key changed the derivation of the v2 seed (`holo/v2/` +
the explicit spelling), not the emission. With the FROZEN seed declared, main
emits both byte-identically:

- sheet J (`c2-cmy8-r0547@53x37`, seed `holo/v2/c2-cmy8-r0547@53x37`, the
  row holo3's identity table keeps for decoding it,
  `src/holo/receiver/format/identity.py`): `page000.ps`, `page001.ps` and the
  `duplex.ps` of `experiments/035-sheet-j-confetti/make_duplex.py` match the
  hash table once the `%%Title` line's explicit spelling
  `1i300-cmy8-r0547-p120-v1@53x37` is put back to `c2-cmy8-r0547@53x37`
  (11 bytes per page); `manifest.json` differs in its identity fields only
  (`spec_id`, `format_id`, `coding_id`).
- the local-ab sim (`src/holo/receiver/tests/_h3_sims.py`'s
  `make_color_hard`, seed `holo/v2/c3-cmy8-r0850@10x10`, the contracted
  spelling of its day — the uncontracted `c3-cmy8-r0850x0850x0850@10x10` is
  NOT the old seed): `page000.ps` matches the same way after the same
  substitution; the manifest differs in the same fields.

The payload files were identical at every swept tree. No tree since the
re-key has a door for a frozen v2 seed: the generator's fossil catalogue
(`src/holo/format/fossils.py`) is v1-only, and FORMAT-SPACE §8 rules that it
holds no v2 row (sheet J's lives in holo3's table, for decoding). The recipe
at main is therefore a runtime override, applied after `holo.format.fossils`
has imported (its self-check must run on the unpatched property) and before
the emit:

    from holo.format import descriptor
    from holo.format.resolve import resolve_format_ref   # imports the fossils
    from holo.gen.emit import emit_volume
    spec = resolve_format_ref("c2-cmy8-r0547@53x37")
    descriptor.FormatSpec.seed = property(lambda self: b"holo/v2/c2-cmy8-r0547@53x37")
    payload = bytes(i & 0xFF for i in range(1 << 20))    # e035's counting payload
    emit_volume(spec, payload, 0.686, out / "volume", paper="A4-4mm", engine_dpi=600)

then `make_duplex.py page000.ps page001.ps -o duplex.ps`; the sim the same
way around `make_color_hard(outdir)` with its seed. A generator-side fossil
row for sheet J (the "forward port") was started and dropped on 2026-10-26
under FORMAT-SPACE §8; the driver rows at the two tagged trees remain the
verification of record. [2026-10-27: the tree chosen for the public
history's first snapshot is `80041d52`, `pre-v1-v2-deletion` (PUBLIC-RELEASE
§9, §11 D36), which lies past the re-key and so emits both only with the
seed declared, as main does through the override above; measured at main,
not yet at 80041d52. `8260257d` stays the driver's pin for sheet J.]
