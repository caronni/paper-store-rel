"""Regeneration driver for the two 2026-07-07 fullpage pages of experiment 007.

What it is: the verbatim regeneration body recovered 2026-10-10 from the
2026-07-07 session (a Python heredoc run at 18:22 CEST over
paperholo.encodings at commit cb2a8ffb, the payload symbols drawn by
np.random.default_rng(20260707); no os.urandom). This docstring was added
and the --write-gt flag below (2026-10-26); the rest of the code is
unchanged, its first-line comment included (it describes the recovered
body, whose write_gt=False is now the flag's default).

How to run: `python regen_fullpage.py G [--write-gt]`, where G is a
directory holding, at G/regen, a checkout of any tree from cb2a8ffb
(2026-07-07, paperholo.encodings) through main — the pages regenerate
byte-identically at every one of them (measured 2026-10-22,
docs/evidence-archive/REGENERATION-2026-10-22.md §4.3), so no checkout of
the tag evidence/fullpage-20260707@cb2a8ffb is needed; a symlink G/regen
to a worktree serves. The script imports G/regen/src/paperholo (PYTHONPATH
is not needed: it inserts that path into sys.path itself) and writes
G/regen/out/<stem>.ps for each of the two stems (emit_page writes
<stem>_manifest.json beside it; G/regen/out must exist). With --write-gt
emit_page also writes the ground truth, the payload arrays included, and
the manifests carry their fields[0].gt block as the archived ones do;
without it (the recovered body's write_gt=False) the pages are the same and
the manifests differ in that block. Run it with a Python satisfying that
tree's requirements.txt (numpy, scipy, pillow). The flag is the one change
to the body since its recovery (the argv check and `write_gt=write_gt`).

What it reproduces (byte-identical on the 2026-10-10 re-run against
cb2a8ffb's modules, together with both payload arrays; at main with
--write-gt 2026-10-22, manifests included):
  fullpage-bw-kcell-c2.ps      sha256 b3eb799934ca6df42d7a7eabd6131ae64ae9af8435ef47299c4f289ad4337c22
  fullpage-color-a3-7st-c3.ps  sha256 94c773df944d68a6df0ab996e81ec69ae5bbf9b32a29ca137439e80510e6b5c5

The pages were never printed. Record: experiments/007-office-disc.md,
addendum 2026-10-11; docs/EVIDENCE-ARCHIVE-2026-10-08.md §8a.
"""
# Verbatim body of 47e9d5b1 [1605] (2026-07-07T16:22:48Z), output dir redirected, write_gt=False.
import numpy as np, os, sys
G = sys.argv[1]
if sys.argv[2:] not in ([], ["--write-gt"]):
    sys.exit("usage: regen_fullpage.py G [--write-gt]")
write_gt = sys.argv[2:] == ["--write-gt"]
sys.path.insert(0, G + "/regen/src")
from paperholo.encodings import get_encoding, encode_field, emit_page, PlacedField, mm_to_dots, MM_PER_INCH
HW = 600; A4_W_MM, A4_H_MM = 210.0, 297.0
X_MM, Y_MM, RIGHT_MM, BOT_MM = 8.0, 13.0, 8.0, 8.0
max_w = mm_to_dots(A4_W_MM - X_MM - RIGHT_MM, HW)
max_h = mm_to_dots(A4_H_MM - Y_MM - BOT_MM, HW)
jobs = [
    ("kcell-c2",  2, "fullpage-bw-kcell-c2",     b"paper-store/fullpage-bw",
     "paper-store FULL-A4  B1 kcell-c2 (densest usable K, cell=2)  random payload  NO marks (L2 furniture pending)"),
    ("a3-7st-c3", 7, "fullpage-color-a3-7st-c3", b"paper-store/fullpage-color",
     "paper-store FULL-A4  A3 7-state CMY c3 (record color 133.3 b/mm2)  random payload  NO marks"),
]
for enc_id, n_states, stem, seed, header in jobs:
    enc = get_encoding(enc_id); cell = enc.cell_dots
    n_cols, n_rows = max_w // cell, max_h // cell
    sym = np.random.default_rng(20260707).integers(0, n_states, size=(n_rows, n_cols), dtype=np.uint8)
    field = encode_field(enc, sym, seed=seed, page=0)
    man = emit_page([PlacedField(field=field, x_mm=X_MM, y_mm=Y_MM, name=stem)],
                    f"{G}/regen/out/{stem}.ps", header=header, end_sentinel=False,
                    title=f"paperholo full-A4 {enc_id}", write_gt=write_gt)
    print(stem, man['ps_sha256'], man['ps_bytes'])
