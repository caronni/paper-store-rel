"""The first cmy page through the receiver: read on R (CMY-RECEIVER-PLAN A2),
scored and attempted (A3), known and closed (A4), read out of register
through the page field (A5), read with every row on over a faint M band
(A7), and calibrated by the hi-first chain (A8).

cmy lays its furniture for the R channel (R7, R24): word '1' prints C,
word '0' the keyed W or Y, the dust M-first by the balance law, so in R the
dark sites are the C ones and `words.ADDRESSING_DARK[Family.CMY]` is {C}.
Placement and addressing read the R plane alone (`place_pass._window_crop`
hands `planes[:1]` to the one-plane crop, the platen backing is read in R),
split at `words.addressing_split`; the survey keeps luma.

What this module states, on `_h3_sims_cmy`'s c3 page in register: the
receiver's reference IS the rendered page binarized in R at every word and
dust site; the luma survey accepts the page; with the colour row dropped,
every tile is placed at its true counter; the colour job, run on the
page's true pose, reads every payload cell's state (A3's measured pin);
a tile of the generator's GT, corrupted in score space, certifies both
label streams as the generator wrote them, and a mangled lo fails while
hi certifies.  Knowledge (A4): one certified label stream knows only
true zeros, never a plane as 1, and both know the state; the whole
decode closes VERIFIED byte-exact, every certificate the generator's
label bits and every projection the GT planes; and the one consistency
rule leaves cmy8's projection byte-identical under every subset of the
cmy8 decode's certified planes.  The page field (A5): one label stream
gives no plane a certified template and both give every plane one,
weighted by the cross-talk table, as the furniture templates are; the
colour job reads the offset page at pose + F_p through its corrected arm;
the offset page -- M and Y a dot right of C -- closes VERIFIED byte-exact with
every certificate the generator's, and its field publishes C as the zero
field and M and Y at their displacement from C (a measured pin).  The
residue decode (A7): the faint page -- M faded over a band of rows, in
register -- closes VERIFIED byte-exact with every row on, every certificate
the generator's; every colour row one capture can reach seats a cmy
subject but `tiles.uplift`; and a real cmy status block reads `streams hi,lo · PROVISIONAL`, counts hi
and lo, and spells C, held at the pose, `0 (gauge)`.  The chain (A8): at the
render's pose every map qualifies in register and out of it; the three-way
gate keeps the raw scores in register and wears the chain out of it, in the
head slot, never as a detector, and the emitted bound then binds on no cell.

LEDGER 2026-10-12 (A2), a record, not a test: the whole decode at one
worker refused at `fit_detector` with 1 placement standing (the word
route, level 1), in 5.3 s.
2026-10-12 (A3), a record: the whole decode at one worker, `--max-pages
1`, fitted the colour lane (accepted) and ran `tiles.scan` on 16 tiles x
2 streams -- hi 9 and lo 9 certified, every one equal to the generator's
user bits, 7 + 7 below the attempt floor, 0 failed -- then the colour
lane's assembly job for the next window refused at `certified_projection`
(KeyError(Family.CMY), via `build_window_rows`), in 6.6 s.
2026-10-12 (A3): `cmy page state reads` pinned at (0, 0, 0) wrong of
the page's 397,600 payload cells (state, hi sign, lo sign) -- the clean
in-register page through the colour job's raw fallback (no context head
adopted, nothing erased, the L-infinity bound binding at 20).
2026-10-12 (A4), a record: the whole decode at one worker, `--max-pages
1`, ran survey 1, place 36, colour 4 and `tiles.scan` 50 -- hi 25 and lo
25 certified, 11 + 11 below the attempt floor, 0 failed -- and closed
VERIFIED byte-exact at 50 certificates against the close's 48 source
symbols, metadata rank 24/24, in 6.5 s (5.4 cpu-s); `fields.collect` and
`refine.color` were queued and never fired before the close.  At eight
workers (`decode_cmy_w8`) the count moves run to run: five runs certified
54-62 (hi = lo, 27-31 each), 0-5 per stream below the floor, 0 failed,
VERIFIED in 3.8-4.1 s, and in the two cached records every certified
tile carries both streams.  The cmy8 colour decode those same lanes
cached certifies every tile on all three planes, so the byte-identity
pin withholds planes to reach the partial cases.  In the cached
`cmy-w8` record `refine.color` ran 6 jobs and `fields.collect` 1 before
the close (`fields` unsolved).  No row that fired raised on cmy and no
family gate was taken.  A noisy SCRATCH decode, not a stimulus of
record (the same page with noise sd 30 and a blur of sigma 3 px over
x 55-80 %, 1 worker, `--complete`, 76 s), fired `fields.collect` 3,
`fields` 3, `refine.color` 34 (11 poses adopted), `tiles.retry` 30,
`tiles.local` 1 and `tiles.swim` 8 for cmy without raising; 124
certificates, all from `tiles.scan`; VERIFIED byte-exact; field medians
C 0.11+-1.11, M 0.11+-1.11, Y 0.22+-1.50 dots; fold_errors 0.
2026-10-12 (A5), a record: the gauge follows the pose's ink, read off the
row's word '1' (`row.word_states[1]`, `lib/field_gauge`) as its proxy --
cmy's addressing reads R (`words.ADDRESSING_ON_R`), where the word's C is
the one dark ink, so the pose is C's -- and cmy's field holds C at zero and
measures M and Y from it.  The offset page
(`_h3_sims_cmy.CMY_OFFSET_PAGE_PX`, M and Y +1.0 dot in x) decoded at eight
workers (`decode_cmy_offset_w8`, `--max-pages 1`) closed VERIFIED
byte-exact in all three lane runs on fresh caches, every certificate the
generator's label bits, and the path moved between them: 48 certificates
(hi 24, lo 24 -- the close's 48 source symbols), 1,006 attempts failed, 54
below the floor, 43.1 s of wall and 276.9 cpu-s with the machine shared
with other lanes, survey 1, place 121, colour 17, `tiles.scan` 657,
`tiles.retry` 1,068, `refine.color` 89, `tiles.local` 40, `fields.collect`
2, `fields` 2, 4 certificates from `tiles.scan` before the first solve and
44 from `tiles.local` after it; then 49 (hi 25, lo 24), 857 failed, 84
below the floor, 19.9 s and 123.4 cpu-s, place 121, colour 18, `tiles.scan`
459, `tiles.retry` 504, `tiles.swim` 20, `fields.collect` 1, `fields` 1,
nothing certified before the solve and all 49 from `tiles.scan` after the
colour lane's two refits; then 51 (hi 25, lo 26) in 38.5 s.  Before the
first solve the decode certifies almost nothing: 4, 0 and 6 certificates in
the three runs, 2,148, 1,044 and 2,130 failed attempt outcomes before it
against 38, 45 and 44 after (the records' `TileOutcome` events, one per
stream attempt), and 236.6 of 276.9 and 113.6 of 123.4 cpu-s of the first
two runs went before it -- `fields.collect`'s first fire is priced at 180
and waits behind every colour, scan and retry job (at one worker, 165 s: 36
colour windows certified nothing, then the field, two colour refits, and
every scan certified two).  What fails there is the score lane, not the
registration.  MEASURED the same day by the A5 refuter's scratch probe (the
colour job over the whole page at the render's own pose, as `_page_reads`,
per true state): reading M and Y at C's pose, no field, mis-reads 42 of the
397,600 payload states yet flips the hi label of 100 % of the M cells and
the lo label of 100 % of the Y cells; through the planted field the flips
move to 100 % of the W cells' hi and the C cells' lo; through the inherited
gauge's field (below) none flip; and with
`color_region_head.CMY7_RELATIVE_SCORE_BOUND` lifted, in the probe's
process only, no read flips any.  The raw QDA scores reach ~6.6e8 against
minor scores ~3e3, and the per-cell divisor
(`color_region_head.py:350-357`) squeezes the minor ones to ~1e-4, so the
label demap's signs come out wrong on whole states.  The pre-field failures
are therefore crush failures of A3's score lane (inferred from the render's
pose; the decode's own poses were not probed), and the field unblocks the
decode by perturbing the read out of the divisor's squeeze, not by
registering it.  The field's VALUE stands (below); the defect is A8's and
gates M1 (CMY-RECEIVER-PLAN A8), and the 85-92 % of CPU before the field is
confounded by it -- re-measured after A8 before any pricing line.  The
first run's last solve published C as the zero field, known; M at a page
mean of (+0.879, +0.014) and Y at (+0.910, -0.195) dots against the plant's
(+1.0, 0) each, the second's (+0.876, +0.018) and (+0.907, -0.194), the
third's (+0.876, +0.012) and (+0.910, -0.173); over the first and four
scratch decodes (three at eight workers, one at one) the mean errors
spanned M x -0.119..-0.124 and y -0.019..+0.018, Y x -0.086..-0.093 and y
-0.173..-0.195, which is why the pin reads them at the plant's half-dot
quantum; Y's y sits 0.055 dots inside that quantum's -0.25 rounding
boundary, a plateau artefact of this render that A9's blurred stimulus is
expected to move.  This blur-free render's correlation peaks are plateaus a
dot wide, so a template's reading walks along its plateau with any tilt;
the cross-talk table (`field_tiers.CROSS_TALK_STATES`) carries C out of Y's
templates beside the design's two weights because of it.  At the inherited
gauge (HEAD 894b3852) the same page also closed, one worker, 158 s, its
field reading C -0.63, M +0.63 (-C, M unmeasured) and Y +0.63, so F_M - F_C
and F_Y - F_C at +1.27: the decode did not need the new gauge, the field's
meaning did.  The corrected arm reads the page at pose + F_p exactly (the
test checks the sampler's offsets), but its state pin -- 42 wrong with no
field, 0 through the plant, the arm adopted -- does not tell the field from
a wrong one: M -1.0, M 0 with Y +1, and (0.5, 0.5) each read 0 wrong and
adopt the arm too (the same probe).  The in-register record after A5:
VERIFIED, 60, 54 and 54 certificates in the three runs, neither field row
fired before the close; the placement-only record solves the in-register
page's field three times, M (+0.050, +0.009) and Y (+0.038, +0.003) dots.
2026-10-12 (A7), a record: the faint page (`_h3_sims_cmy.make_cmy_faint`,
the in-register emission with M at `_h3_sims.FAINT_SCALE` 0.30 of its ink
over dot rows 30-70 %) decoded at eight workers, `--complete --max-pages 1`
(`decode_cmy_faint_w8`), closed VERIFIED byte-exact, every certificate the
generator's, in 9.6 s and 46.9 cpu-s: lo on all 100 tiles by `tiles.scan`,
hi on none by scan -- it failed on every tile, in the band and out (104
failed and 24 below-floor scan outcomes, 101 failed retries) -- and on all
100 by `tiles.cond`, hi given lo; a scratch decode before it and the second
lane run (9.4 s; scan 134, retry 95) split the same way.  Fired: survey 1,
place 283, color 12, `tiles.scan` 128, `tiles.retry` 101, `tiles.cond`
100.  Seated and never fired: `tiles.local`, `tiles.swim` and
`tiles.planek` 100 subjects each, retired certified -- cond, priced as a
scan, takes every hi before 220-240 come up -- `refine.color` 16 (reach
exhausted), `fields.collect` 1 (page done), so `fields` is not born here
(it is in the offset record).  `tiles.uplift` never seated.  Minted: scan
(lo) and cond (hi) only.  Scratch probes, not records: with `tiles.cond`
dropped the field solved twice and the colour refit (18 colour fires)
certified hi by scan on every tile, local, swim and planek seated 200 each
and fired none; with `tiles.cond`, `fields`, `fields.collect` and
`refine.color` dropped the refit alone certified hi -- this clean page
hands no residue row a tile in any configuration, and the label read's
proof on pixels is `test_h3_cmy_residue`'s synthetic page.  The offset
record re-decoded on this tree, two lane runs on fresh caches: VERIFIED,
50 certificates (scan 24, local 25, cond 1), `tiles.planek` seated 479
subjects beside `tiles.swim` 240 and neither fired before the close; then
VERIFIED, 54 (scan 36, local 6, and `tiles.swim` 6 jobs minting 12 -- hi
6, lo 6, every one the generator's: swim's four-state table at work),
planek seated 488 and fired none.  The first run's status block
reads `C 0 (gauge) M 0.89±1.40 Y 0.95±1.40 dots, support 100%` and `planes
certified [hi:25 · lo:25]`, and its D1 alarm fired 3 times (diagnostic,
nothing quarantined).
2026-10-12 (A8), a record: the hi-first chain (`plugins/color_chain`, R11)
in the head slot.  At the render's own pose (the whole page one region,
`_page_stack`) every map qualifies on all three pages, 2,700 fit and 2,900
validation rows.  The gate's legs (total, word, dust 4-state NLL, raw ->
chain): in register 8.1e-6, 8.6e-6, 3.3e-6 -> 1.7e-3, 1.6e-3, 3.0e-3, raw kept
(separable reads, more confident than PAVA's 1/(n+2) clamp); faint 0.2166,
0.1619, 0.6902 -> 0.2170, 0.1623, 0.6909, raw kept; offset 0.580, 0.521,
1.099 -> 0.0999, 0.0323, 0.686, the chain worn, and the emitted bound binds
on 0 % of the offset page's cells against 100 % on the raw pages.  The
squeeze A5 measured at that pose (no field: hi wrong on 99,563 = every M
cell, lo on 98,631 = every Y, 42 states; through the plant: hi on 99,722 =
every W, lo on 99,684 = every C, 0 states) is replaced, not lifted: with the
context head off the chain flips no label on any state in either read, but
the maps' PAVA nodes are block CENTROIDS, every map on this render is
separable (two blocks and E017.6's zero node), and within a class one
state's raw statistic sits four orders of magnitude past the other's (hi
through the plant: W -3.5e3 vs Y -8.3e7, C +3.4e3 vs M +9.3e7), so the
louder state sets the centroid and the quieter one's L_hi lands at 6e-4
(W, C through the plant) or 2e-6 (M, no field); W ties M or C, and the
context head adopted on top breaks the ties -- no field M hi 52,160, M lo
3,471, W lo 51 wrong, 43,502 states; through the plant 99,185 states, W read
as C 62,094 and C as W 37,091 (the pin above).  On paper neither squeeze is
reached (scores are tens, maps many blocks:
measure/cmy_calibration/RESULTS-2026-10-12-scorelane.md).  Decodes: at one
worker the in-register page certified the same 50 keys as before A8 (hi
25, lo 25; the chain refused at its lane fit); at eight workers the three
records VERIFIED byte-exact in three runs -- in register 54 each, offset 48
(hi 24, lo 24: scan 27, local 20, cond 1), 50 (scan 44, swim 6) and 51
(scan 5, local 46), faint 200 each (lo by scan, hi by cond).  The A7
input, hi by scan on the faint page outside the band: no -- in two scratch
decodes (one and eight workers) the faint page's lone lane fit refused the
chain (total 0.2133 vs 0.2230, 0.2283 vs 0.2381) and scan failed hi on all
100 tiles, as the one-worker decode does on the tree before A8; at the
render's pose the raw lane's hi |LLR| medians are W 4.3e-4 and M 2.0e-3
(the divisor's squeeze), which the chain's centroids do not lift.  One
eight-worker decode before A8 certified hi by scan on the 60 tiles outside
the band (run variance).
2026-10-12 (A8 refuter), measured on this tree: the moved pin counts
signs on near-zero LLRs; the measure is each label stream's information,
1 - E[log2(1 + e^(-s L))] bit/cell against the GT labels
(`_label_information_bits`), pinned beside the signs at three decimals.
Offset page, render's pose, raw scores (the chain forced off by a probe's
runtime patch = the emission before A8; a ledger number, no production
hook) -> A8: no field hi 0.311 -> 0.740, lo 0.314 -> 0.929; through the
plant 0.455 -> 0.498 and 0.461 -> 0.498 (0.31129, 0.31363 -> 0.74032,
0.92900; 0.45525, 0.46121 -> 0.49788, 0.49759) -- the chain loses
information to the raw scores in neither read.  Raw through the plant,
every W's hi is wrong at median |L| 0.39; A8's wrong labels sit at median
|L| 0.12 (M hi) and 0.063 (M lo) with no field, 0.017 (W) and 0.051 (C)
through the plant, W's 51 wrong lo at 1.3.  The squeeze is the
EVALUATOR's, and scale-free: every QDA score divided by 1e6 reproduces the
planted 99,185 x 3 exactly (PAVA and its interpolation scale with the
statistic); a noiseless render's collapsed per-state covariances put one
state orders past the other inside a class (no field C 3.6e7 vs M 4.8).
SCRATCH probes, the refuter's, runtime patches, not built: BLOCK-EDGE
nodes -- each PAVA block's first and last training score, joined in
logit, E017.6's zero node kept, the same blocks and probabilities as
`fit_component_pava` -- read the offset page hi 0.9995, lo 0.9986 (no
field) and 0.9995, 0.9985 (plant), 0 wrong in both reads, and the faint
page's chain, refused on a tie with centroid nodes (0.2170 vs 0.2166),
adopts, hi 0.4986 -> 0.9995; ASINH of the statistic reads the plant
0.9950, 0.9940 and the faint hi 0.9925, with a knee at |s| ~ 1 that
compresses paper's tens.  A paper-like emulation (Gaussian sd 0.06 on the
three features before the QDA; held-out max |s| p99 97-105, paper's
45-122): offset, no field, raw 0.772 / 0.717, chain 0.9145 / 0.8718, asinh
0.9168 / 0.8741, block-edge 0.9145 / 0.8717; through the plant and in
register the raw read is lossless and the gate refuses the chain; at sd
0.04 (p99 192) the gap to block-edge reopens, chain 0.902 / 0.922 vs 0.966
/ 0.941 -- paper's first-fire p99 reaches 122 (emulation, not paper).  So
the plan's "the fix of the squeeze itself stays A8's" is NOT delivered on
clean sims, and A8's exit holds in part: every map qualifies, and the
one-worker certificates contain A4's only because the gate refuses the
chain in register.  OWED to the owner, a RULING: an amendment to R11's
evaluator clause (probability -> logit was the first), block-edge nodes
preferred over asinh (no unit constant), re-measured as one arm in
measure/cmy_calibration/followup.py on the existing extract (its ldpc
stage optional).  The fit/validation split (`head_sub_split`, `&2` of
`site_hash` = 131 y + 17 x) sends whole in-tile site positions to one
side, so the M dust divides 594 / 296 on every page -- deterministic,
cmy7's idiom.  The refit's certified cells reach the chain's population
only in the decode records; a unit pin of that plumbing is owed.
2026-10-12 (the lead, after the diag lanes): `decode_cmy_offset_w8` runs
`--complete` from here on -- on a fresh cache the eight-worker close
landed before the field solved and the two field-reading tests of this
module found no FieldSolved event (a timing flake the A5 ledger's
run-to-run numbers already showed); every row drains now, so the
record always carries a solve.  The A4-A8 ledger numbers above for the
offset record (48-62 certificates, which rows minted before and after
the field) describe the non-complete runs and stay as history.
"""
from __future__ import annotations

import itertools

import numpy as np
import pytest

from types import SimpleNamespace

from holo.receiver import data, engine, operator
from holo.receiver.diag import model as diag_model
from holo.receiver.diag import readout
from holo.receiver.format import identity, keystream, pilots, tile_codec
from holo.receiver.lib import page_map
from holo.receiver.plugins import (color_chain, color_model, color_region,
                                   color_region_head, color_sites,
                                   field_tiers, tiles, words)
from holo.receiver.tests import (_h3_fixture_geometry, _h3_sims,
                                 _h3_sims_cmy, _h3_support)

BORDER_PX = _h3_sims.COLOR_BORDER_DOTS * _h3_sims.UPSAMPLE


def _page_geometry(capture: _h3_sims.SimCapture) -> tuple[identity.FormatRow,
                                                           int]:
    row = identity.resolve_format_ref(capture.format_ref)
    return row, int(row.pitch_in * capture.dpi)


def _true_offset_px(native_affine: tuple[float, ...],
                    cells_yx: np.ndarray, pitch_px: int) -> np.ndarray:
    """Placed minus printed pixel of each page cell's top-left corner.

    `native_affine` maps the page's cell index to native pixels in the
    pixel-centre frame; the render prints cell c at BORDER_PX + pitch * c
    in the pixel-edge frame, half a pixel later.
    """
    affine = np.asarray(native_affine, np.float64).reshape(2, 3)
    placed = cells_yx @ affine[:, :2].T + affine[:, 2]
    return placed - (BORDER_PX - 0.5 + pitch_px * cells_yx)


def _centre_offset_px(page_origin_yx: tuple[int, int],
                      shape_yx: tuple[int, int],
                      native_affine: tuple[float, ...],
                      pitch_px: int) -> float:
    centre = (np.asarray(page_origin_yx, np.float64)
              + np.asarray(shape_yx, np.float64) / 2.0)
    return float(np.abs(_true_offset_px(native_affine, centre[None, :],
                                        pitch_px)).max())


def _r_cell_centres(capture: _h3_sims.SimCapture) -> np.ndarray:
    import tifffile

    row, pitch_px = _page_geometry(capture)
    red = np.asarray(tifffile.imread(capture.tiff)[..., 0], np.float32)
    cells_y, cells_x = row.cells_yx
    crop = red[BORDER_PX:BORDER_PX + cells_y * pitch_px,
               BORDER_PX:BORDER_PX + cells_x * pitch_px]
    blocks = crop.reshape(cells_y, pitch_px, cells_x, pitch_px)
    half = pitch_px // 2
    return blocks[:, half - 1:half + 1, :, half - 1:half + 1].mean(axis=(1, 3))


@pytest.mark.parametrize("shift, agrees", [(0, True), (1, False)])
def test_the_cmy_reference_is_the_render_binarized_in_r_at_every_site(
        sim_cmy, shift, agrees):
    row, _pitch_px = _page_geometry(sim_cmy)
    bars = _h3_sims_cmy.e043c_sheet3_bars()
    cyan_r = bars.toner_rgb[0][0]
    light_r = min(bars.paper_rgb[0], bars.toner_rgb[1][0],
                  bars.toner_rgb[2][0])
    dark = (_r_cell_centres(sim_cmy) < 0.5 * (cyan_r + light_r)
            ).astype(np.uint8)
    reference = words.reference_page(row, 0)
    sites = reference.sites
    assert int(sites.sum()) == row.tiles_per_page * row.n_sites
    height, width = sites.shape
    read = dark[shift:, shift:][:height - shift, :width - shift]
    expected = reference.values[:height - shift, :width - shift]
    mask = sites[:height - shift, :width - shift]
    agree = int(np.count_nonzero(read[mask] == expected[mask]))
    if agrees:
        assert agree == int(mask.sum())
    else:
        assert agree < int(mask.sum())


def test_the_luma_survey_accepts_the_cmy_page(decode_cmy_place_w8, sim_cmy):
    row, pitch_px = _page_geometry(sim_cmy)
    surveys = [event for event in decode_cmy_place_w8.events
               if isinstance(event, data.SurveyDone)]
    assert len(surveys) == 1
    survey = surveys[0]
    assert survey.pitch_class == str(row.pitch_in)
    assert survey.n_regions == 1
    region = survey.regions[0]
    assert region.pitch_px == pytest.approx(pitch_px, rel=0.01)
    assert all(side >= cells for side, cells in zip(region.shape_cells,
                                                    row.cells_yx))


def test_every_cmy_tile_is_placed_at_its_true_counter(decode_cmy_place_w8,
                                                      sim_cmy):
    record = decode_cmy_place_w8
    row, pitch_px = _page_geometry(sim_cmy)
    assert record.certified == 0
    poses = [event for event in record.events
             if isinstance(event, data.PoseCommitted)]
    assert poses
    for event in poses:
        assert (event.page, event.rot_k) == (0, 0)
        assert _centre_offset_px(event.page_origin_yx, event.shape_yx,
                                 event.native_affine, pitch_px) < pitch_px / 2
    covered = {(event.page, ty, tx) for event in record.events
               if isinstance(event, data.AddressCoverage)
               for ty, tx, _sites in event.tiles}
    assert covered == {(0, ty, tx) for ty in range(row.tiles_yx[0])
                       for tx in range(row.tiles_yx[1])}
    for event in record.events:
        if isinstance(event, data.WordOutcome):
            assert event.page == 0
            assert 0 <= event.ty < row.tiles_yx[0]
            assert 0 <= event.tx < row.tiles_yx[1]
            assert event.sites >= words.STAGE_A_MIN_VISIBLE_SITES


def _gt_states(capture: _h3_sims.SimCapture,
               row: identity.FormatRow) -> np.ndarray:
    """The emitter's GT page as presence ids, one per cell."""
    planes = np.unpackbits(_h3_sims.load_emit_gt(capture), axis=-1)
    cells_y, cells_x = row.cells_yx
    step = planes.shape[1] // cells_y
    cells = planes[:, step // 2::step, step // 2::step][:, :cells_y,
                                                         :cells_x]
    return tile_codec.planes_to_states(np.moveaxis(cells, 0, -1))


def _true_window(row: identity.FormatRow,
                 pitch_px: int) -> color_region.RegionWindow:
    """The whole page as one window at the render's own pose: cell c
    starts at BORDER_PX + pitch * c in the pixel-edge frame, half a pixel
    later than the pixel-centre frame a native affine maps into."""
    cells_y, cells_x = row.cells_yx
    placement = _h3_fixture_geometry.window_placement(
        ("sim-cmy", 0, 0, (0, 0, cells_y, cells_x)),
        _h3_fixture_geometry.page_native_affine(pitch_px, BORDER_PX - 0.5),
        _h3_fixture_geometry.grid_cells((0, 0), (cells_y, cells_x)))
    return _h3_fixture_geometry.window_pose(row, placement)


def _page_planes(capture: _h3_sims.SimCapture) -> tuple[SimpleNamespace,
                                                         ...]:
    import tifffile

    image = tifffile.imread(capture.tiff)
    return tuple(SimpleNamespace(open=lambda channel=channel:
                                 image[..., channel])
                 for channel in range(3))


def _label_information_bits(llrs: np.ndarray, bits: np.ndarray) -> float:
    """Mutual information, bit/cell, of one label stream's LLRs against
    the GT bits under a uniform prior: 1 - E[log2(1 + e^(-s L))], s = +1
    on a 1 and -1 on a 0 (the A8 refuter's measure)."""
    signs = np.where(bits, 1.0, -1.0)
    return float(1.0 - np.mean(np.logaddexp(0.0, -signs * llrs))
                 / np.log(2.0))


def _page_reads(capture: _h3_sims.SimCapture,
                plane_fields: tuple[data.PlaneField, ...] | None = None,
                ) -> tuple[tuple[int, int, int], tuple[float, float], bool]:
    """The colour job over the whole page at the render's own pose:
    wrong payload reads (state, hi sign, lo sign), each label stream's
    information in bit/cell, and whether its head adopted the
    field-corrected arm."""
    row, pitch_px = _page_geometry(capture)
    geometry = identity.build_site_geometry(row)
    planes = _page_planes(capture)
    result = color_region.region_job(
        row, geometry, (_true_window(row, pitch_px),), (), planes, {},
        color_region_head.StackConfig(), "sim-cmy", 0,
        plane_fields=plane_fields)
    (evidence,) = [fact for fact in result.facts
                   if isinstance(fact, data.ColorEvidenceRow)]
    (fit,) = [fact for fact in result.facts
              if isinstance(fact, color_region_head.ColorLaneFit)]
    cells = np.asarray(evidence.page_cells_yx, np.int64)
    cargo = color_sites.cargo_row_indices(geometry, cells)
    values = np.asarray(evidence.values, np.float64)[cargo]
    truth = _gt_states(capture, row)[cells[cargo, 0], cells[cargo, 1]]
    read = np.asarray(row.state_ids)[np.argmax(np.concatenate(
        (np.zeros((values.shape[0], 1)), values), axis=1), axis=1)]
    labels = color_model.CMY_COLUMN_LABEL_BITS[
        color_region_head.state_columns(row.state_ids, truth)]
    llrs = [tile_codec.cmy_soft_demap(values, stream) for stream in range(2)]
    wrong = (int(np.count_nonzero(read != truth)),) + tuple(
        int(np.count_nonzero((llr > 0.0) != labels[:, stream]))
        for stream, llr in enumerate(llrs))
    information = tuple(_label_information_bits(llr, labels[:, stream])
                        for stream, llr in enumerate(llrs))
    assert cargo.size == row.tiles_per_page * row.payload_cells
    return wrong, information, bool(fit.head.corrected)


def test_the_colour_job_reads_every_payload_state_of_the_cmy_page(sim_cmy):
    wrong, _information, _corrected = _page_reads(sim_cmy)
    _h3_support.assert_measured("cmy page state reads", wrong, (0, 0, 0))


def _page_stack(capture: _h3_sims.SimCapture
                ) -> tuple[color_region_head.StackResult, float]:
    """The colour stack over the whole page at the render's own pose, and
    the share of emitted payload cells whose L-infinity divisor binds."""
    row, pitch_px = _page_geometry(capture)
    inputs = color_region.build_region_inputs(
        row, identity.build_site_geometry(row),
        (_true_window(row, pitch_px),), (), _page_planes(capture), {},
        "sim-cmy", 0)
    stack = color_region_head.fit_region_stack(
        row, inputs.selection, inputs.row_tuple, inputs.base_tuple,
        inputs.corrected, inputs.emission_by_row,
        color_region_head.StackConfig())
    binds = []
    for ordinal, emit in enumerate(inputs.emission_by_row):
        bins = (None if stack.context_bins is None
                else stack.context_bins[ordinal][emit])
        _values, divisor = color_region_head.evidence_with_divisor(
            stack.selected, stack.features[ordinal][emit], bins)
        binds.append(np.asarray(divisor).ravel() > 1.0)
    return stack, float(np.mean(np.concatenate(binds)))


@pytest.mark.parametrize("page, adopted, bound_share", [
    ("sim_cmy", False, 1.0), ("sim_cmy_offset", True, 0.0)],
    ids=["in-register", "offset"])
def test_every_chain_map_qualifies_and_the_gate_decides_the_chain(
        request, page, adopted, bound_share):
    """R11's chain over the whole page at the render's own pose (A8):
    every map qualifies on both pages; the three-way gate keeps the raw
    scores in register -- separable reads, more confident than PAVA's
    1/(n+2) clamp -- and adopts the chain on the offset page, where the
    per-cell divisor squeezes them; the chain sits in the head slot, never
    as a detector, and once it is worn the emitted bound binds on no cell
    (CMY-DESIGN §2.7: 0.0-0.1 %).  What it reads there is the ledger's
    (A8): the squeeze moves into the maps' centroids."""
    stack, share = _page_stack(request.getfixturevalue(page))
    chain = stack.chain
    assert chain.map_reasons == ("adopted",) * 3
    assert (chain.reason == "adopted") is adopted
    assert (chain.candidate_nll[0] < chain.incumbent_nll[0]) is adopted
    assert stack.selected.detector is None
    assert isinstance(stack.selected.head, color_chain.CmyChain) is adopted
    _h3_support.assert_measured(f"cmy {page} emitted bound share", share,
                                bound_share)


def _planted_fields(row: identity.FormatRow) -> tuple[data.PlaneField, ...]:
    """The offset page's plant as a standing field: C zero, M and Y at
    `_h3_sims_cmy.CMY_OFFSET_PAGE_PX`, on every tile."""
    out = []
    for plane, offset_px in enumerate(_h3_sims_cmy.CMY_OFFSET_PAGE_PX):
        delta = np.zeros(row.tiles_yx + (2,), np.float64)
        delta[...] = np.asarray(offset_px, np.float64) / _h3_sims.UPSAMPLE
        out.append(data.PlaneField(
            page=0, plane=plane, delta_dots_xy=delta,
            support=np.ones(row.tiles_yx), uncertainty_dots=np.zeros(
                row.tiles_yx), n_observations=1, n_captures=1, ordinal=1))
    return tuple(out)


def test_the_colour_job_reads_the_offset_page_at_pose_plus_the_field(
        sim_cmy_offset, monkeypatch):
    """The corrected arm IS the field-corrected read (CMY-RECEIVER-PLAN
    A5): with no field there is no corrected read, and with the plant
    standing the sampler is handed, at every cell it reads, exactly what
    the one mapping evaluates there (`page_map.plane_delta_dots`) -- C
    zero, M and Y the planted (+1.0, 0) dot -- which lands G and B exactly
    2 px right of R's points, where the render put M and Y.  Exact, no
    tolerance: a constant tile field evaluates bilinearly to itself, and
    1.0 dot at 3 dots and 6 px a cell is 2.0 px in binary floating point.
    The read pin beside it -- wrong payload (state, hi sign, lo sign) at the
    render's pose with no field and through the plant -- shows only that
    an arm is adopted: before A8 it read 42 and 0 wrong states, and M
    -1.0, M 0 with Y +1, and (0.5, 0.5) also read 0 and adopt it (the
    ledger, A5).  Since A8 the chain is worn in both reads and the label
    signs are pinned beside the states: the divisor binds on no cell, and
    what flips is the chain's centroid squeeze on this separable render,
    tipped by the context head (the ledger, A8).  Signs counted on
    near-zero LLRs are not the measure -- A8's wrong labels sit at median
    |L| 0.017-0.12 -- information is: each label stream's bit/cell
    against the GT labels, pinned beside the signs at three decimals, no
    field hi 0.740 lo 0.929 and through the plant 0.498 each, where the
    raw scores (the chain forced off) read 0.311 / 0.314 and 0.455 /
    0.461 (the ledger, A8): in neither read does the chain lose
    information to the raw scores."""
    row, _pitch_px = _page_geometry(sim_cmy_offset)
    fields = _planted_fields(row)
    handed: list[tuple[data.WindowRows, np.ndarray, int,
                       tuple[np.ndarray | None, ...]]] = []
    features_at = color_region.anchor.features_at

    def sampler(planes: tuple[np.ndarray, ...], rows: data.WindowRows,
                page_linear: np.ndarray,
                offsets: tuple[np.ndarray | None, ...], cell_dots: int,
                *rest: float) -> np.ndarray | None:
        handed.append((rows, page_linear, cell_dots, offsets))
        return features_at(planes, rows, page_linear, offsets, cell_dots,
                           *rest)

    monkeypatch.setattr(color_region.anchor, "features_at", sampler)
    unfielded, unfielded_info_bits, unfielded_corrected = _page_reads(
        sim_cmy_offset)
    assert not handed and not unfielded_corrected
    fielded, fielded_info_bits, fielded_corrected = _page_reads(
        sim_cmy_offset, fields)
    assert handed and fielded_corrected
    for rows, page_linear, cell_dots, offsets in handed:
        for plane, (offset, field) in enumerate(zip(offsets, fields)):
            planted_px = np.asarray(_h3_sims_cmy.CMY_OFFSET_PAGE_PX[plane],
                                    np.float64)
            assert np.array_equal(offset, page_map.plane_delta_dots(
                field, rows.page_cells_yx))
            assert np.array_equal(offset, np.broadcast_to(
                planted_px / _h3_sims.UPSAMPLE, offset.shape))
            moved_px = page_map.raster_points(
                rows.scan_points_yx, page_linear, offset,
                cell_dots) - rows.scan_points_yx
            assert np.array_equal(moved_px, np.broadcast_to(
                planted_px[::-1], moved_px.shape))
    _h3_support.assert_measured(
        "cmy offset page wrong (state, hi, lo) reads (no field, planted)",
        (unfielded, fielded), ((43502, 52160, 3522), (99185, 99185, 99185)))
    _h3_support.assert_measured(
        "cmy offset page (hi, lo) information, bit/cell (no field, planted)",
        tuple(tuple(round(bits, 3) for bits in info_bits)
              for info_bits in (unfielded_info_bits, fielded_info_bits)),
        ((0.740, 0.929), (0.498, 0.498)))


#: Score-space tile stimulus: each cell's true state carries log-
#: likelihood AMPLITUDE over the other three, plus unit Gaussian noise;
#: CORRUPT_FRACTION of the cells score as a random wrong state.
AMPLITUDE = 4.0
CORRUPT_FRACTION = 0.005
TILE_ADDRESS = (0, 4, 6)


def _tile_cut(states_flat: np.ndarray, seed: int) -> tiles.TileCut:
    rng = np.random.default_rng(seed)
    columns = color_region_head.state_columns(
        tile_codec.CMY_STATE_IDS, states_flat)
    corrupt = rng.random(columns.size) < CORRUPT_FRACTION
    columns[corrupt] = (columns[corrupt]
                        + rng.integers(1, 4, int(corrupt.sum()))) % 4
    loglik = (AMPLITUDE * np.eye(4)[columns]
              + rng.normal(0.0, 1.0, (columns.size, 4)))
    page, ty, tx = TILE_ADDRESS
    return tiles.TileCut(
        capture_id="score-space", level_index=0, page=page, ty=ty, tx=tx,
        values=(loglik[:, 1:] - loglik[:, :1]).astype(np.float32),
        observed_flat=np.arange(tile_codec.N_CELLS, dtype=np.uint16))


def _gt_tile(capture, row, geometry) -> tuple[np.ndarray, np.ndarray]:
    """The GT tile's states flat (4,096) and its payload states in the
    codec's sequential order."""
    page, ty, tx = TILE_ADDRESS
    tile = _gt_states(capture, row)[ty * 64:(ty + 1) * 64,
                                    tx * 64:(tx + 1) * 64].ravel()
    counter = row.tile_counter(page, ty, tx)
    sequential = np.empty(row.payload_cells, np.uint8)
    sequential[keystream.color_cell_permutation(
        row.seed, counter, row.payload_cells)] = tile[geometry.payload_flat]
    return tile, sequential


def _label_stream_of(row, fact, user_bits: np.ndarray,
                     address: tuple[int, int, int] = TILE_ADDRESS
                     ) -> np.ndarray:
    page, ty, tx = address
    counter = row.tile_counter(page, ty, tx)
    return (tile_codec.encode_frame(np.asarray(user_bits, np.uint8),
                                    fact.rung_children)
            ^ keystream.cmy8_dither_bits(
                row.seed, fact.dither_aux, counter,
                tile_codec.bank_transmitted_bits(fact.rung_children)))


def test_a_generator_tile_corrupted_in_score_space_certifies_both_streams(
        sim_cmy):
    row, _pitch_px = _page_geometry(sim_cmy)
    geometry = identity.build_site_geometry(row)
    tile, sequential = _gt_tile(sim_cmy, row, geometry)
    labels = color_model.CMY_COLUMN_LABEL_BITS[
        color_region_head.state_columns(row.state_ids, sequential)]
    cut = _tile_cut(tile, seed=19)
    for fact in row.streams:
        result = tiles.attempt_tile(row, geometry, (cut,), fact.stream_id,
                                    tiles.STAGE_SCAN)
        assert result.fact.outcome == tiles.OUTCOME_CERTIFIED
        assert np.array_equal(
            _label_stream_of(row, fact, result.certificate.user_bits),
            labels[:, fact.label_index])


def test_a_mangled_lo_stream_fails_while_hi_certifies(sim_cmy):
    row, _pitch_px = _page_geometry(sim_cmy)
    geometry = identity.build_site_geometry(row)
    tile, sequential = _gt_tile(sim_cmy, row, geometry)
    # A third of the cells read as their lo partner (W<->Y, M<->C): the
    # lo bit is wrong there, the hi bit untouched.
    partner = {0: 4, 4: 0, 2: 1, 1: 2}
    mangled = tile.copy()
    flip = np.random.default_rng(23).random(tile.size) < 1.0 / 3.0
    mangled[flip] = [partner[int(state)] for state in tile[flip]]
    cut = _tile_cut(mangled, seed=19)
    hi = tiles.attempt_tile(row, geometry, (cut,), "hi", tiles.STAGE_SCAN)
    lo = tiles.attempt_tile(row, geometry, (cut,), "lo", tiles.STAGE_SCAN)
    assert lo.fact.outcome == tiles.OUTCOME_FAILED
    assert lo.certificate is None
    assert hi.fact.outcome == tiles.OUTCOME_CERTIFIED
    labels = color_model.CMY_COLUMN_LABEL_BITS[
        color_region_head.state_columns(row.state_ids, sequential)]
    assert np.array_equal(
        _label_stream_of(row, row.streams[0], hi.certificate.user_bits),
        labels[:, 0])


def _random_certificates(row, address, streams: tuple[str, ...],
                         seed: int) -> dict:
    rng = np.random.default_rng(seed)
    page, ty, tx = address
    return {(page, ty, tx, fact.stream_id): data.Certificate(
                page, ty, tx, fact.stream_id,
                rng.integers(0, 2, fact.user_bits, dtype=np.uint8), "t")
            for fact in row.streams if fact.stream_id in streams}


def _payload_label_bits(row, address, fact, certificate) -> np.ndarray:
    """A certified stream's label bit at each `payload_flat` cell: the
    generator's frame, dithered, through the tile's cell permutation."""
    counter = row.tile_counter(*address)
    return _label_stream_of(row, fact, certificate.user_bits, address)[
        keystream.color_cell_permutation(row.seed, counter,
                                         row.payload_cells)]


def _payload_projection(row, geometry, address, certificates
                        ) -> tuple[np.ndarray, np.ndarray]:
    projection = color_sites.certified_projection(row, geometry, *address,
                                                  certificates)
    assert projection is not None
    bits, known = projection
    flat = np.asarray(geometry.payload_flat, np.int64)
    return (bits.reshape(-1, 3)[flat], known.reshape(-1, 3)[flat])


#: What ONE certified label bit says about a cell's planes (C, M, Y):
#: only true zeros (CMY-DESIGN §7 (d)) -- the planes every state with
#: that bit leaves uninked.
ONE_LABEL_BIT_KNOWS = {
    ("hi", 0): (True, True, False), ("hi", 1): (False, False, True),
    ("lo", 0): (True, False, True), ("lo", 1): (False, True, False)}


@pytest.mark.parametrize("stream_id", ["hi", "lo"])
def test_one_cmy_label_stream_knows_no_plane_as_one(stream_id):
    row = identity.resolve_format_ref(_h3_sims_cmy.CMY_FORMAT_REF)
    geometry = identity.build_site_geometry(row)
    address = (0, 3, 5)
    certificates = _random_certificates(row, address, (stream_id,), 41)
    fact = tiles.stream_fact(row, stream_id)
    label = _payload_label_bits(row, address, fact,
                                certificates[(*address, stream_id)])
    bits, known = _payload_projection(row, geometry, address, certificates)
    expected = np.asarray([ONE_LABEL_BIT_KNOWS[(stream_id, int(bit))]
                           for bit in label])
    assert np.array_equal(known, expected)
    assert not bits.any()


def test_both_cmy_label_streams_know_the_state():
    row = identity.resolve_format_ref(_h3_sims_cmy.CMY_FORMAT_REF)
    geometry = identity.build_site_geometry(row)
    address = (0, 3, 5)
    certificates = _random_certificates(row, address, ("hi", "lo"), 43)
    hi, lo = (_payload_label_bits(row, address, fact,
                                  certificates[(*address, fact.stream_id)])
              for fact in row.streams)
    bits, known = _payload_projection(row, geometry, address, certificates)
    states = np.asarray(tile_codec.CMY_LABEL_TO_STATE)[(hi << 1) | lo]
    assert known.all()
    assert np.array_equal(bits, tile_codec.states_to_planes(states))


def test_the_cmy_sim_decode_is_verified_and_byte_exact(decode_cmy_w8,
                                                       sim_cmy):
    _assert_verified_byte_exact(decode_cmy_w8, sim_cmy)


def test_the_offset_cmy_sim_decode_is_verified_and_byte_exact(
        decode_cmy_offset_w8, sim_cmy_offset):
    _assert_verified_byte_exact(decode_cmy_offset_w8, sim_cmy_offset)


def _assert_verified_byte_exact(record: object,
                                sim_cmy: _h3_sims.SimCapture) -> None:
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_cmy.payload_data
    _h3_support.assert_golden("recovered cmy payload sha256",
                              record.payload_sha256,
                              _h3_sims_cmy.CMY_PAYLOAD_SHA256)
    final = [event for event in record.events
             if isinstance(event, data.CloseCheck)][-1]
    assert final.status == "verified"
    _h3_support.assert_measured("cmy close k_total", final.k_total, 48)
    assert final.certified == record.certified


def test_every_cmy_certificate_is_the_generators_and_projects_the_gt(
        decode_cmy_w8, sim_cmy):
    _assert_certificates_are_the_gt(decode_cmy_w8, sim_cmy)


def test_every_offset_cmy_certificate_is_the_generators_and_projects_the_gt(
        decode_cmy_offset_w8, sim_cmy_offset):
    _assert_certificates_are_the_gt(decode_cmy_offset_w8, sim_cmy_offset)


def test_the_faint_cmy_sim_decode_is_verified_and_byte_exact(
        decode_cmy_faint_w8, sim_cmy_faint):
    _assert_verified_byte_exact(decode_cmy_faint_w8, sim_cmy_faint)


def test_every_faint_cmy_certificate_is_the_generators_and_projects_the_gt(
        decode_cmy_faint_w8, sim_cmy_faint):
    _assert_certificates_are_the_gt(decode_cmy_faint_w8, sim_cmy_faint)


def _assert_certificates_are_the_gt(record: object,
                                    sim_cmy: _h3_sims.SimCapture) -> None:
    row, _pitch_px = _page_geometry(sim_cmy)
    geometry = identity.build_site_geometry(row)
    gt = _gt_states(sim_cmy, row)
    gt_planes = tile_codec.states_to_planes(gt)
    flat = np.asarray(geometry.payload_flat, np.int64)
    checks = _h3_support.Checks(f"{record.label}: cmy certificates vs GT")
    for key in sorted(record.certificates):
        page, ty, tx, stream_id = key
        tile = gt[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64].ravel()
        fact = tiles.stream_fact(row, stream_id)
        label = _payload_label_bits(row, (page, ty, tx), fact,
                                    record.certificates[key])
        truth = color_model.CMY_COLUMN_LABEL_BITS[
            color_region_head.state_columns(row.state_ids, tile[flat])
        ][:, fact.label_index]
        checks.equal(f"{key} label bits wrong",
                     int(np.count_nonzero(label != truth)), 0)
    for page, ty, tx in sorted({key[:3] for key in record.certificates}):
        bits, known = color_sites.certified_projection(
            row, geometry, page, ty, tx, record.certificates)
        printed = gt_planes[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
        checks.equal(f"({page},{ty},{tx}) known bits wrong",
                     int(np.count_nonzero((bits != printed) & known)), 0)
        if all((page, ty, tx, fact.stream_id) in record.certificates
               for fact in row.streams):
            checks.check(f"({page},{ty},{tx}) both streams know every cell",
                         bool(known.all()))
    streams = {key[3] for key in record.certificates}
    assert streams == {fact.stream_id for fact in row.streams}
    checks.assert_clean()


def _pre_a4_cmy8_projection(row, geometry, page, ty, tx, certificates
                            ) -> tuple[np.ndarray, np.ndarray] | None:
    """`certified_projection`'s cmy8 arithmetic before the one rule:
    each certified plane written from its own re-encoded frame."""
    present = tuple(fact for fact in row.streams
                    if (page, ty, tx, fact.stream_id) in certificates)
    if not present:
        return None
    counter = row.tile_counter(page, ty, tx)
    bits = np.zeros((64, 64, 3), np.uint8)
    known = np.zeros((64, 64, 3), np.bool_)
    sites = np.concatenate((geometry.word_cells_yx, geometry.extra_cells_yx))
    states = np.concatenate((
        pilots.color_word_states(row.seed, (counter,), row)[0],
        pilots.dust_state_values(row.seed, (counter,), row)[0]))
    bits[sites[:, 0], sites[:, 1]] = tile_codec.states_to_planes(states)
    known[sites[:, 0], sites[:, 1]] = True
    flat = np.asarray(geometry.payload_flat, np.int64)
    order = keystream.color_cell_permutation(row.seed, counter,
                                             row.payload_cells)
    flat_bits = bits.reshape(-1, 3)
    flat_known = known.reshape(-1, 3)
    for fact in present:
        n_transmitted = tile_codec.bank_transmitted_bits(fact.rung_children)
        sequential = tile_codec.encode_frame(
            np.asarray(certificates[(page, ty, tx, fact.stream_id)].user_bits,
                       np.uint8), fact.rung_children)
        sequential ^= keystream.cmy8_dither_bits(
            row.seed, fact.dither_aux, counter, n_transmitted)
        flat_bits[flat, fact.plane] = sequential[order]
        flat_known[flat, fact.plane] = True
    return bits, known


def test_the_one_rule_keeps_cmy8s_projection_byte_identical(
        decode_color_w8, sim_color):
    """Every certified tile of the cmy8 sim under every non-empty subset
    of its certified planes: the decode certifies whole tiles, so the
    partial-knowledge cases are its certificates with planes withheld."""
    row = identity.resolve_format_ref(sim_color.format_ref)
    geometry = identity.build_site_geometry(row)
    certificates = decode_color_w8.certificates
    addresses = sorted({key[:3] for key in certificates})
    assert addresses
    for address in addresses:
        streams = tuple(fact.stream_id for fact in row.streams
                        if (*address, fact.stream_id) in certificates)
        for size in range(1, len(streams) + 1):
            for subset in itertools.combinations(streams, size):
                view = {(*address, stream_id):
                        certificates[(*address, stream_id)]
                        for stream_id in subset}
                new = color_sites.certified_projection(row, geometry,
                                                       *address, view)
                old = _pre_a4_cmy8_projection(row, geometry, *address, view)
                assert new[0].dtype == old[0].dtype, (address, subset)
                assert new[1].dtype == old[1].dtype, (address, subset)
                assert np.array_equal(new[0], old[0]), (address, subset)
                assert np.array_equal(new[1], old[1]), (address, subset)


@pytest.mark.parametrize("stream_id", ["hi", "lo"])
def test_one_cmy_label_stream_gives_no_plane_a_certified_template(stream_id):
    """A certified template needs its plane known on all 4,096 cells, and
    one label stream knows no plane anywhere it reads 1."""
    row = identity.resolve_format_ref(_h3_sims_cmy.CMY_FORMAT_REF)
    geometry = identity.build_site_geometry(row)
    page, ty, tx = address = (0, 3, 5)
    certificates = _random_certificates(row, address, (stream_id,), 41)
    for plane in range(3):
        assert field_tiers.certified_template(
            row, geometry, page, (ty, tx), plane, certificates) is None


def _cross_talk_zeros(states: np.ndarray, plane: int) -> np.ndarray:
    return np.isin(states, sorted(
        field_tiers.CROSS_TALK_STATES[identity.Family.CMY][plane]))


def test_both_cmy_label_streams_give_every_plane_a_weighted_template():
    row = identity.resolve_format_ref(_h3_sims_cmy.CMY_FORMAT_REF)
    geometry = identity.build_site_geometry(row)
    page, ty, tx = address = (0, 3, 5)
    certificates = _random_certificates(row, address, ("hi", "lo"), 43)
    bits, _known = color_sites.certified_projection(row, geometry, *address,
                                                    certificates)
    states = tile_codec.planes_to_states(bits.reshape(-1, 3))
    for plane in range(3):
        template = field_tiers.certified_template(
            row, geometry, page, (ty, tx), plane, certificates)
        assert np.array_equal(template.bits, bits[..., plane].ravel())
        assert np.array_equal(template.weights == 0.0,
                              _cross_talk_zeros(states, plane))


def test_a_cmy_furniture_template_weights_out_the_other_inks_that_read_on_it():
    """M's template drops the C words (C darkens G), Y's the C words and
    the M dust (both darken B), and what is left still clears both anchor
    floors -- M's ones are its dust alone; cmy8's templates carry no
    weights."""
    row = identity.resolve_format_ref(_h3_sims_cmy.CMY_FORMAT_REF)
    geometry = identity.build_site_geometry(row)
    for plane in range(3):
        template = field_tiers.furniture_template(row, geometry, 0, (3, 5),
                                                  plane)
        states, _kinds = color_model.reference_states(
            row, geometry, 0, template.page_cells_yx)
        assert np.array_equal(template.weights == 0.0,
                              _cross_talk_zeros(states, plane))
        live = template.bits[template.weights > 0.0]
        assert live.size >= field_tiers.ANCHOR_MIN_SITES
        assert (field_tiers.minority_class(live)
                >= field_tiers.ANCHOR_MIN_PER_CLASS)
    cmy8 = identity.resolve_format_ref("c3-cmy8-r0550@10x10")
    assert field_tiers.furniture_template(
        cmy8, identity.build_site_geometry(cmy8), 0, (3, 5), 2).weights is None


def test_the_offset_pages_field_holds_c_at_zero_and_moves_m_and_y_from_c(
        decode_cmy_offset_w8):
    """F_C = 0 by name (R7): C publishes the zero field, known; M and Y
    publish their displacement from C.  The pin is each plane's page-mean
    (F_p - F_C) - planted, x and y, in dots, at the plant's own half-dot
    quantum (`_h3_sims_cmy.CMY_OFFSET_PAGE_PX`): eight workers move the
    last solve's revision and refine.color's poses run to run, and on this
    blur-free render a template's correlation peak is a plateau a dot
    wide, so the field moves with them by hundredths (the ledger, A5)."""
    solved = [event for event in decode_cmy_offset_w8.events
              if isinstance(event, data.FieldSolved)][-1]
    assert solved.block_tiles_yx == (1, 1)
    planes = {row.plane: row for row in solved.planes}
    assert planes[0].known
    zero = np.asarray(planes[0].delta_grid_dots_xy, np.float64)
    assert not np.any(zero)
    errors = []
    for plane in (1, 2):
        assert planes[plane].has_data.all()
        planted = (np.asarray(_h3_sims_cmy.CMY_OFFSET_PAGE_PX[plane],
                              np.float64) / _h3_sims.UPSAMPLE)
        error = (np.asarray(planes[plane].delta_grid_dots_xy, np.float64)
                 - zero).reshape(-1, 2).mean(axis=0) - planted
        errors.append(tuple(float(value) + 0.0
                            for value in np.round(2.0 * error) / 2.0))
    _h3_support.assert_measured(
        "cmy offset page mean (F_p - F_C) - planted, half dots (M, Y)",
        tuple(errors), ((0.0, 0.0), (0.0, 0.0)))


#: The colour rows a ONE-capture page cannot reach: `tiles.union` sums
#: two lanes at one footing, `color.pooled_ctx` pools two captures behind
#: its own request flag.  Neither REFUSES cmy at birth by the code (union
#: has no family test, pooled refuses K only, `color_pooled.py:176`), but
#: neither is SHOWN to seat a cmy subject here -- that proof is A9's
#: two-capture decode.  K's own: calibrate, ctx, refine.
UNREACHED_ON_ONE_CAPTURE = ("tiles.union", "color.pooled_ctx")
K_ONLY_ROWS = ("calibrate", "ctx", "refine")


def test_every_cmy8_row_is_born_for_cmy_but_uplift(decode_cmy_faint_w8,
                                                   decode_cmy_offset_w8):
    """A7's exit off the records' own events: every colour row one
    capture can reach seats a subject on a cmy page -- planek and swim
    translated, local as it stands, cond as cmy's A4b -- but
    `tiles.uplift`, whose arm table holds nothing for cmy (`color_arms`).
    Which rows FIRE and MINT moves run to run and is the ledger's, not
    this test's."""
    seated = {event.plugin
              for record in (decode_cmy_faint_w8, decode_cmy_offset_w8)
              for event in record.events
              if isinstance(event, data.WorkerSeated)}
    rows = {descriptor.name for descriptor in engine.DESCRIPTORS}
    assert "tiles.uplift" not in seated
    assert rows - seated == {"tiles.uplift", *UNREACHED_ON_ONE_CAPTURE,
                             *K_ONLY_ROWS}


def test_the_cmy_readout_reads_hi_lo_provisional_and_c_at_the_gauge(
        decode_cmy_offset_w8):
    """The status block of a real cmy decode, folded from its events: the
    format row names the label streams and ends PROVISIONAL, the planes
    line counts hi and lo, and the field row spells C, held at the pose
    by the gauge (R7), as `0 (gauge)` -- M and Y as measured."""
    events = list(decode_cmy_offset_w8.events)
    rows = operator.status_rows(events)
    assert rows[0].startswith(
        f"format   {_h3_sims_cmy.CMY_FORMAT_REF} · 10x10 tiles")
    assert rows[0].endswith(" · streams hi,lo · PROVISIONAL")
    model = diag_model.fold(diag_model.empty(), events)
    split = dict(readout.plane_cert_counts(model))
    assert sum(split.values()) == decode_cmy_offset_w8.certified
    assert (f"planes   certified [hi:{split['hi']} · lo:{split['lo']}]"
            in rows)
    field, = (row for row in rows if row.startswith("fields   page 0 — "))
    assert field.startswith("fields   page 0 — C 0 (gauge) M "), field
