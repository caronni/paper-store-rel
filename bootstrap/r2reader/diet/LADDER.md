# Stage-2 reader diet: ablation ladder (2026-10-19, simulation only)

The ladder starts from `reader_hand.py` (r0). Each rung is its parent plus the edits in `build_rungs.py`, which regenerates every file byte for byte. cm2 sizes use the FIXED primer `loader/review/hand/a.py`; b32 = ceil(cm2·8/5). The captures are 10x3 and 12x2, each as grid, flatbed300, nominal-b030 and hard-b030. Pass means r2.bin == payload.bin with exit code 0 (`harness.py`, all runs in `ladder.json`).

|rung|removed / changed|raw|cm2|b32|10x3+12x2|
|---|---|---|---|---|---|
|r0|nothing|4713|1911|3058|4+4|
|r1|P2 input|4643|1887|3020|4+4|
|r2|grid.txt output|4553|1853|2965|4+4|
|r3|multi-capture loop and pooling|4485|1827|2924|4+4|
|r4a|geometry baked to 10x3|4245|1755|2808|4+1 (as expected)|
|r4b|size vote only over the 2 spec geometries|4400|1801|2882|4+4|
|r5|Chase repair|4236|1743|2789|4+4|
|r6|Laplacian equaliser|4103|1691|2706|**3+2 FAIL**|
|r6c|equaliser at one fixed strength|4175|1720|2752|4+4|
|r7|threshold = ring mean (median **FAILS** flatbed)|4160|1713|2741|4+4|
|r8a|walk always from one corner|4065|1671|2674|4+4|
|r8b|2-of-4 bullseye fallback and its print line|3972|1631|2610|4+4|
|r9a–j|simpler prediction; one walk; geometry by bullseye distance; corner-block skip, score gate, magic check and ring template dropped; mean binarisation; 2-way comb|3234|1374|2199|4+4|
|r10|bullseye search (corners = extreme ink points) with the timing vote|2881|1237|1980|**3+3 FAIL** (vote mislocks)|
|r10c|as r10, but walks both geometries and starts bottom-right|2784|1214|1943|4+4|
|r11a|homography replaced by bilinear|2585|1112|1780|**3+2 FAIL**|
|r11b|PGM pixels = last W·H bytes|2770|1211|1938|4+4|
|**f_all8**|r11b, minified, names searched|**2727**|**1168**|**1869**|4+4|
|**f_10x3**|f_all8 with 10x3 baked|**2621**|**1118**|**1789**|4+0|

`r9_*.py`, `p9_*` and `p11_*` are single-edit probes. On the 12x2 grid text, f_10x3 raises IndexError.

## Finer envelope

10x3 page, 2.0 spm, three seeds per cell (`make_env.py`):

|reader|p2 σ.3|p2 σ.4|p2 σ.5|p4 σ.3|p4 σ.4|p4 σ.5|
|---|---|---|---|---|---|---|
|reader_hand|3/3|3/3|1/3|2/3|2/3|0/3|
|f_all8|3/3|3/3|0/3|2/3|2/3|0/3|
|f_10x3|3/3|3/3|0/3|2/3|2/3|0/3|

- **σ 0.5:** the loss comes from dropping Chase (r5).
- **4 % perspective:** different seeds fail. reader_hand misses bullseyes on seed 3. The candidates lose seed 1, where the bottom-left extreme ink point is about 30 modules off.
- **The 4 % failures are not the size vote:** baking the geometry (r4a) does not fix them.
- **Wall time:** f_all8 4–6 s, f_10x3 3–4 s, reader_hand 5–8 s.

## Could not remove (measured)

- **Equaliser:** removing it fails the hard captures. One strength at half weight passes; full weight fails.
- **Bilinear pixel sampling:** nearest-pixel sampling fails.
- **Homography:** the bilinear corner map fails (r11a).
- **Transition bounding box:** without it, camera captures fail on the dark background.

## Findings

- **Top-left corner:** its extreme ink point lands 3–5 modules inside. The white corner module and its timing neighbours wash out, so the bullseye ring becomes the extreme.
- **Walk from bottom-right:** that corner module is ink on both spec pages, so the walk starts there and tracks the top-left error. With this, the reader no longer reads the bullseyes.
- **Checks:** both candidates pass `check_subset.py` (no imports, floats or '/', whitelisted builtins only). Their renames are proved by `loader/review/names.py`. Their stdout matches the pre-rename text on all 26 captures.

## Rulings owed

1. One capture per run, with no pooling (r3).
2. Bake 10x3 (−50 B cm2, −80 b32), or keep both spec geometries.
3. Accept the blur edge moving from σ 0.5 to 0.4.
4. With the bullseyes unread, there is no 2-of-4 tolerance, and all four page corners must be in frame. Do the corner blocks stay furniture?
5. Drop the magic check and the "bullseyes found" line.
