"""The swim's reason to exist, end to end, against the field itself.

One emitted top-rung colour page rendered twice: every plane in
register, and plane Y displaced along x by a mean-zero sinusoid of
FOUR dots, one cycle down the page.  Same emit, same shape,
same period and the same noise draw as the two-dot pair
`test_h3_color_field_yield` uses — the ONE variable is the amplitude,
and the field is given its best shot: `--plane-fields` is ON in both
degraded arms, so the swim is asked for exactly the tiles the field,
running, still missed.

RE-DERIVED TWICE, and the history is the point rather than an
embarrassment.  The first version ran at three dots against a field
that applied a ninth of what it fitted; the units fix made the field
honest and that residue VANISHED.  Re-bracketed at 3.5, and then the
anchortier line's median-across-planes publication took the
plane-common part out, left Y a cleaner differential, and THAT residue
vanished too.  Each repair to the field pushed the number up, which is
exactly what this row's licence says should happen: the swim's job is
whatever the field of the day still cannot express, so the stimulus is
re-derived whenever the field changes.

The band has a ceiling as well as a floor, and the ceiling is worth
naming because it bounds every residue row and not just this one: on
the pre-anchortier tree four dots put the Y stream below the
informative floor, so no tile was ever ATTEMPTED, no `AttemptFact` was
emitted, and no residue row was born at all.  A rescue row can only
help a tile the receiver still tries.  The better field puts Y back
inside that floor at four dots, which is how this bracket exists.

WHY AMPLITUDE, AND NOT SHARPNESS.  A step looks like the better
separator on paper — the field pools over a two-tile Gaussian truncated
at 3.5 sigma, a seven-tile reach on a ten-tile page, so it cannot
follow an edge.  MEASURED 2026-08-31, and it is not: a two-dot,
one-cycle SQUARE WAVE costs this page exactly ONE certificate with the
field switched off (299/300, payload byte-exact), because a one-cycle
square wave has a large linear component and the colour lane's own
{1, y} per-plane page-fraction residual absorbs it before any rescue
tier is reached.  Only a mean-zero full-cycle SINUSOID is orthogonal to
that residual, which is why the sinusoid is the stimulus of record here
and in the two-dot pair.  `test_only_a_full_cycle_hides_from_the_page_
fraction_residual` below pins the arithmetic behind that.

Amplitude, in contrast, separates the swim from the whole standing
stack at once and by construction: the window pose search reaches a
quarter cell (`refine.PHASE_LIMIT_CELLS`, 0.75 dots here), the field
clamps at `plane_field.MAX_DELTA_DOTS` (2.0 dots) and beyond that clamp
its linearised fit degrades rather than saturating, while the swim's
bound is a full cell measured FROM the field's own number.

Three decodes, all at workers 1 with `--complete`.  MEASURED
2026-08-31 on the merged tree, and pinned below:

    steep-control       in register, swim dropped   300/300, byte-exact
                        (since 2026-09-03 the two-dot pair's own control
                        decode, shared — same raster, argv and hold-out)
    steep-fields        field ON, swim dropped      299/300, byte-exact
    steep-fields-swim   field ON, swim ON           300/300, byte-exact

The one the field missed is Y at (2, 4), and it survived ALL THREE
cheaper rescue rows — the field-only arm spent 45 `tiles.local`, 19
`tiles.planek` and 9 `tiles.retry` certificates' worth of grinding and
still could not have it.  The swim recovers exactly that tile, and its
certificate signature (every address AND every user-bit vector) is
BYTE-IDENTICAL to the in-register control's: `c31d3d1453c0ac71…`,
against the field-only arm's `afa1d7eb1646e744…`.

WHAT THE FIELD REPAIRS CHANGED, since this row predates both.  The
swim now composes with a working field instead of standing in for a
broken one: median correction 0.375 dots on the in-register planes and
0.562 on Y, with Y reaching the full 3.000-dot bound where the hint
needs the most help.  That is the designed composition — the field
carries the bulk and the bound is measured from it.

COST, honestly, because it moved the wrong way: 137 jobs and 662.7 s,
20% of that run's 3,320 s, against 2.7% at the previous bracket.  A
harder page means more residue tiles, each paying a full local head fit
plus the search, and the row converts 23 certificates for it.  It is
the dearest row in the tree and at this amplitude it looks it.

WORKERS, measured on the previous bracket and not re-run here (a fourth
decode does not fit the lane): at workers 8 the swim fires more jobs
and mints more certificates than the serial run while `tiles.local`
mints fewer — the schedule differs, so which row reaches a tile first
differs, and the rows trade work between them.  The run still reaches
the control's count with the payload AND the whole certificate
signature identical to the serial run's.  The standing law asks only
for payload bytes at w8; this clears the stronger bar, and the trade is
the clearest evidence that these rescue rows are interchangeable on the
easy tiles and only the swim reaches the hard one.

BROKEN BY THE b8471fc RE-KEY, 2026-09-03, AND THE AMPLITUDE LADDER IS
EXHAUSTED.  Read this before touching anything here.

`test_every_rescued_certificate_was_minted_by_the_swim_itself` fails,
and it is right to.  Measured on the re-keyed page, same argv and
hold-out as the fixtures:

    field alone         299/300      field + swim   300/300
    rescued             ONE address, Y at (9, 3)
    minted by           tiles/local150 — NOT THE SWIM
    swim-run by source  local150 61, planek150 4, scan 217, swim150 18

The swim still mints 18 certificates, but every one of them is an
address the field-only arm ALSO certified: its MARGINAL contribution on
this stimulus is now ZERO, and its presence only changes which row
reaches a tile first.  That is exactly the coincidence
`test_every_rescued_certificate_was_minted_by_the_swim_itself` exists to
catch, so there is nothing here to re-pin.

WHAT ACTUALLY MOVED, precisely: not the row, not the field — nothing in
holo3/plugins changed in that merge — and not even the COUNT.  The field
still misses exactly one tile, 299/300, as it did above.  It is a
DIFFERENT tile.  The old one was Y at (2, 4), which survived all three
cheaper rescue rows; the re-key redrew the page and the tile the field
now misses, Y at (9, 3), is inside `tiles.local`'s reach.  The stimulus
stopped separating the swim from the cheaper rows.

THE INTEGER-PEAK LADDER IS CLOSED BY MEASUREMENT; the amplitude itself
is not whole-dot bound.  `_h3_sims.plane_x_shift_dots` rounds the
sinusoid PER ROW — no interpolation at any amplitude; this constant was
3.5 until b928312 through that same function.  What held
`STEEP_AMPLITUDE_DOTS` at 4.0 was two fast-lane pins: this module's own
`peak == 4` and `test_h3_color_field_yield`'s `STEEP == SHIFTED + 1.0`;
5.0 fails both, 4.5 the second.  The next whole PEAK above four is
five.  Measured 2026-09-03 at five dots, both
arms, same argv (`scratchpad`-driven, `_h3_sims.render_hard_pair` at the
new amplitude, nothing in this tree edited):

    field alone 200/300   field + swim 200/300   rescued 0
    every certificate from tiles/scan; the ONLY row that fires is
    tiles.scan — tiles.swim, tiles.local, tiles.planek and tiles.retry
    all fire ZERO times

That is the ceiling this docstring already names, hit exactly: Y drops
under the informative floor, no tile is attempted, no AttemptFact is
emitted, and no residue row is born at all.  A rescue row can only help
a tile the receiver still tries.  So the ladder has three rungs and all
three are taken — three dots is `test_h3_color_field_yield`'s stimulus
(the swim recovers that page unaided), four no longer separates, five is
past the floor.  Fractional amplitudes between them are renderable —
4.5 rounds to a wider ±4 plateau, 4.51 to 4.99 to a narrowing 5-dot band
— and 4.5 is MEASURED SEPARATELY BELOW; episode 2's width rejection was
at two dots with the dial off, an expectation and not a closure.

    4.5 dots: field alone 200/300 — Y = 0, but NOT under the floor as
    at five: tiles.retry, tiles.local and tiles.planek each fire 100
    jobs — the count of Y tiles — and certify none (confirming run,
    2026-09-04).  Field + swim 297/300: the swim mints 20 Y tiles; the
    other 77 land through tiles.local (73) and scan (4).  The swim is
    causal for 97 certificates and the source test above would count
    20 of them.  A live rung — for a stronger claim than this module
    made ("without the swim the plane is dead"): same axis, different
    assertion.

RE-DERIVED TO 4.5, 2026-09-04, by the yield principle.  4.5 is where
the swim buys the most: with the field running and the swim dropped the
whole Y plane is lost — 200/300, its tiles attempted by retry, local and
planek (100 jobs each, the count of Y tiles) and every attempt failed —
and with the swim in the schedule it comes back to 297/300.  The swim
mints 20 of the 97; the other 77 arrive through tiles.local (73) and
plain scan (4).  So the claim this module now makes is the causal one,
not the per-certificate one: every rescued address exists only with the
swim in the schedule, because without it a hundred attempts fail and
none certifies.  The exact-page audit below keeps its zero-wrong half
(every certificate the swim arm mints is the control's, bit for bit)
and drops completeness, which 4.0 had by luck: 297 of 300 at 4.5.

ORACLE-SWEEP gated for the same reason the two-dot pair is: the
degraded capture is the most expensive decode in the tree and this
adds three more.  Run them with

    HOLO3_RUN_SLOW_TESTS=1 HOLO3_RUN_ORACLE_SWEEPS=1 \\
        python -m pytest holo3/tests/test_h3_swim_existence.py -q

or drive the same arms, plus the field-hint ablation, without pytest
through `measure/h3_swim.py sweep`.
"""

from __future__ import annotations

import numpy as np

from holo3 import data
from holo3.plugins import tiles
from holo3.tests import _h3_sims, _h3_support

# the top-rung colour sim is a c3 page: three printed dots to a cell
CELL_DOTS = 3
DISPLACED_STREAM = "Y"
PLANE_STREAMS = ("C", "M", "Y")
SWIM_SOURCE = tiles.source_tag(tiles.STAGE_SWIM150)
RESCUE_ROWS = ("tiles.swim", "tiles.local", "tiles.planek", "tiles.retry")
# measured 2026-09-04 at 4.5 dots (see the docstring)
RESCUED_BY_SOURCE = {SWIM_SOURCE: 20,
                     tiles.source_tag(tiles.STAGE_LOCAL150): 73,
                     tiles.source_tag(tiles.STAGE_SCAN): 4}
FIELD_ONLY_RESCUE_JOBS = {"tiles.swim": 0, "tiles.local": 100,
                          "tiles.planek": 100, "tiles.retry": 100}
SWIM_ARM_CERTIFIED = 297


def _jobs(record: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in record.events:
        if isinstance(event, data.JobDone):
            counts[event.plugin] = counts.get(event.plugin, 0) + 1
    return counts


def _addresses(record: object) -> set:
    return set(record.certificates)


def test_the_pair_is_one_emit_rendered_twice(sim_color_hard_steep):
    control, shifted = sim_color_hard_steep
    assert control.format_ref == shifted.format_ref
    assert control.payload_sha256 == shifted.payload_sha256
    assert control.tiff_sha256 != shifted.tiff_sha256


def test_the_injected_peak_is_past_every_standing_correction():
    """The amplitude's derivation, in the constants that bound it."""
    from holo3.lib import plane_field
    from holo3.plugins import refine

    shift = _h3_sims.plane_x_shift_dots(1920,
                                        _h3_sims.STEEP_AMPLITUDE_DOTS,
                                        _h3_sims.SHIFTED_CYCLES)
    assert shift.dtype == np.int64
    peak = int(np.abs(shift).max())
    assert peak == 4, "the rounded sinusoid's peak, in whole dots"
    assert abs(int(shift.sum())) <= peak

    pose_reach_dots = refine.PHASE_LIMIT_CELLS * CELL_DOTS
    assert peak > 4.0 * pose_reach_dots, (
        f"the peak must be well past the window pose search's own reach "
        f"({pose_reach_dots} dots), or the standing machinery absorbs it "
        f"before any rescue tier sees the page")
    assert _h3_sims.STEEP_AMPLITUDE_DOTS > plane_field.MAX_DELTA_DOTS, (
        "and past the field's clamp, which is the constant that says "
        "what the field structurally cannot express")
    assert _h3_sims.STEEP_AMPLITUDE_DOTS <= (
        plane_field.MAX_DELTA_DOTS + CELL_DOTS), (
        "and inside what the swim can reach FROM that clamp: its bound "
        "is one cell measured from the hint, so a displacement further "
        "out than clamp + cell is nobody's to rescue")


def _within_window_swing(shift: np.ndarray, window_dots: int) -> float:
    """The largest peak-to-peak swing inside one window's own span."""
    windows = np.lib.stride_tricks.sliding_window_view(
        shift.astype(np.float64), window_dots)
    return float((windows.max(axis=1) - windows.min(axis=1)).max())


def test_a_step_is_absorbed_because_it_is_flat_inside_a_window():
    """Why the stimulus of record is a sinusoid and not a step.

    MEASURED 2026-08-31 on this page with the field OFF: a two-dot
    one-cycle SQUARE WAVE costs exactly ONE certificate (299/300,
    payload byte-exact) where the two-dot one-cycle SINUSOID costs
    sixteen.  The structural reason is below and needs no decode: a
    square wave is CONSTANT inside every window that does not straddle
    its edge, and a displacement constant over a window is precisely
    what the standing per-window pose refinement expresses.  A full-cycle
    sinusoid swings by dots inside a single window, which no rigid
    per-window pose can follow — so it survives to be the registration
    problem the field and the swim exist for.
    """
    from holo3.lib import geometry

    dots_h = 1920
    window_dots = geometry.WINDOW_CELLS * 3
    # The recorded measurement this test explains was made at TWO dots
    # (docstring above); the module's stimulus of record has since moved
    # to three (the 2026-08-31 re-hardening), but the structural argument
    # is amplitude-independent, so the test pins its own recorded
    # amplitude rather than tracking the drifting constant.
    recorded_amplitude_dots = 2.0
    sine = _h3_sims.plane_x_shift_dots(
        dots_h, recorded_amplitude_dots, _h3_sims.SHIFTED_CYCLES)
    step = _h3_sims.plane_x_step_dots(
        dots_h, recorded_amplitude_dots, _h3_sims.SHIFTED_CYCLES)
    assert set(np.unique(step).tolist()) == {-2, 2}
    assert int(step.sum()) == 0, "the square wave is mean-zero too"
    assert int(np.count_nonzero(np.diff(step))) == 1
    assert _within_window_swing(sine, window_dots) >= 2.0
    assert _within_window_swing(step, window_dots) == 4.0
    edges = int(np.count_nonzero(np.diff(step)))
    flat = dots_h - window_dots + 1 - edges * window_dots
    assert flat > 0.4 * (dots_h - window_dots + 1), (
        "most window positions see a CONSTANT displacement, which is "
        "why the square wave never reaches a rescue tier")


def test_the_in_register_control_certifies_the_whole_page(
        decode_steep_control):
    assert decode_steep_control.exit_code == 0
    counts: dict[str, int] = {}
    for key in decode_steep_control.certificates:
        counts[key[3]] = counts.get(key[3], 0) + 1
    assert counts == {name: 100 for name in PLANE_STREAMS}
    assert (decode_steep_control.payload_sha256
            == _h3_sims.HARD_PAYLOAD_SHA256)


def test_the_field_running_still_misses_tiles_the_control_certified(
        decode_steep_control, decode_steep_fields):
    """The swim's licence: what the field, given its best shot, leaves."""
    missed = _addresses(decode_steep_control) - _addresses(decode_steep_fields)
    assert missed, (
        "the field rescued the whole step: this stimulus no longer "
        "separates a smoothed translation statistic from a local affine, "
        "and the existence proof below would be vacuous")
    assert {key[3] for key in missed} == {DISPLACED_STREAM}, sorted(missed)
    assert not (_addresses(decode_steep_fields)
                - _addresses(decode_steep_control))


def test_the_swim_certifies_tiles_the_field_could_not(
        decode_steep_fields, decode_steep_fields_swim):
    field_only = _addresses(decode_steep_fields)
    with_swim = _addresses(decode_steep_fields_swim)
    assert with_swim > field_only, (
        f"field alone {len(field_only)}, field+swim {len(with_swim)}: the "
        f"swim bought nothing the field had not already got")
    rescued = with_swim - field_only
    assert {key[3] for key in rescued} == {DISPLACED_STREAM}, sorted(rescued)


def test_without_the_swim_the_displaced_plane_stays_dead(
        decode_steep_fields, decode_steep_fields_swim):
    """Causation, not coincidence.

    A residue row that merely re-runs the receiver with a frontier it
    did not have the first time gains certificates for a reason that is
    NOT the row (the lesson `test_h3_uplift_existence` records from
    COLOR-UPLIFT-MEASUREMENTS 10.6).  Here the claim is causal: with
    the swim dropped, retry, local and planek attempt the displaced
    plane and certify none of it; with the swim in the schedule 97
    tiles return, 20 minted by the swim itself and the rest by rows
    that failed without it — the split by minting source is pinned.
    """
    rescued = (_addresses(decode_steep_fields_swim)
               - _addresses(decode_steep_fields))
    assert rescued
    assert {key[3] for key in rescued} == {DISPLACED_STREAM}
    # without the swim the plane is attempted and lost: retry, local and
    # planek each fire 100 jobs — the count of Y tiles — and certify none
    field_jobs = _jobs(decode_steep_fields)
    _h3_support.assert_golden(
        "rescue rows fired with the swim dropped",
        {row: field_jobs.get(row, 0) for row in RESCUE_ROWS},
        FIELD_ONLY_RESCUE_JOBS)
    assert not any(key[3] == DISPLACED_STREAM
                   for key in _addresses(decode_steep_fields))
    by_source: dict[str, int] = {}
    for key in rescued:
        source = str(decode_steep_fields_swim.certificates[key].source)
        by_source[source] = by_source.get(source, 0) + 1
    _h3_support.assert_golden("rescued Y tiles by minting source",
                              by_source, RESCUED_BY_SOURCE)


def test_the_swim_arm_certifies_a_pinned_sub_page_of_the_control(
        decode_steep_control, decode_steep_fields_swim):
    """The exact-page audit as it stands at 4.5 dots.

    Every certificate the swim arm mints is one the undisplaced capture
    certified, address for address and bit for bit, and the count is
    pinned: 297 of the control's 300.  The whole page, which 4.0 had by
    luck, is the three it misses (module docstring).
    """
    swim = decode_steep_fields_swim.certificates
    control = decode_steep_control.certificates
    assert set(swim) <= set(control), sorted(set(swim) - set(control))
    for key, certificate in sorted(swim.items()):
        assert np.array_equal(np.asarray(certificate.user_bits),
                              np.asarray(control[key].user_bits)), key
    _h3_support.assert_golden("swim arm certificates", len(swim),
                              SWIM_ARM_CERTIFIED)
    assert len(control) == 300


def test_the_swim_never_mints_a_certificate_the_control_disputes(
        decode_steep_control, decode_steep_fields_swim):
    checks = _h3_support.Checks("swim zero-wrong")
    for key, certificate in sorted(
            decode_steep_fields_swim.certificates.items()):
        control = decode_steep_control.certificates.get(key)
        checks.check(f"{key} is an address the control also certified",
                     control is not None)
        if control is None:
            continue
        checks.check(
            f"{key} carries the control's user bits",
            np.array_equal(np.asarray(certificate.user_bits),
                           np.asarray(control.user_bits)),
            "a rescue tier may move where evidence is sampled; it may "
            "never mint a certificate the in-register page disagrees with")
    checks.assert_clean()


def test_both_degraded_arms_recover_the_payload_byte_for_byte(
        decode_steep_fields, decode_steep_fields_swim):
    assert (decode_steep_fields.payload_sha256
            == _h3_sims.HARD_PAYLOAD_SHA256)
    assert (decode_steep_fields_swim.payload_sha256
            == _h3_sims.HARD_PAYLOAD_SHA256)


def test_the_swim_row_fired_and_the_field_row_did_too(
        decode_steep_fields_swim):
    rows = {row["plugin"]: row for row in
            decode_steep_fields_swim.report["scheduler"]["plugins"]}
    assert rows.get("fields", {}).get("jobs", 0) > 0, (
        "the field must be running: the swim is measured against what "
        "the field leaves, not against the field's absence")
    assert rows.get("tiles.swim", {}).get("jobs", 0) > 0
