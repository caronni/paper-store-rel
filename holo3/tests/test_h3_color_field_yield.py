"""The plane field's reason to exist, end to end.

One emitted top-rung colour page, rendered twice: every plane in
register, and plane Y displaced along x by a rounded sinusoid (3 dots
peak, one full cycle down the page — the AltaLink's measured
Y-registration defect in miniature).  Both carry the same seeded noise,
so the difference between them is the displacement and nothing else.
`tiles.swim` is held out of all three decodes; the ruling and the
condition that expires it are the last two sections here.

THIS STIMULUS HAS NOW ROTTED THREE TIMES, EVERY TIME BECAUSE THE
RECEIVER GOT BETTER.  The rot looks the same each time: the displaced
page starts certifying everything the control does, `costs_certificates`
fails on its own "no longer exercises the mechanism" message, and the
field has nothing left to buy back.  WHEN THAT HAPPENS THE REPAIR IS TO
RE-HARDEN THE STIMULUS AND RE-PIN — never to loosen a pin, never to
delete the module.  What is protected here is the question, not the
numbers.

EPISODE 1, written 2026-08-30, 2-dot peak: dial off 284/300, the 16
losses all Y; dial on 300/300, byte-identical to the control.

EPISODE 2, 2026-08-31.  Same stimulus, dial off, 300/300 — nothing left
to buy, because `tiles.local`'s COLOUR arm had landed and minted ten
certificates it had never had the chance to mint here.  (The first
reading of that blamed `tiles.planek`, whose blind ±2.0-dot sampling
search matched the injected amplitude; `--drop` refuted it — planek
never fired at two dots.  A plausible mechanism that matches the
numbers is still a hypothesis; that one cost an afternoon.)  The repair
was HEIGHT: three dots, the first whole dot above planek's blind search
and above what the colour head's local re-fit absorbs.  Width was
measured in the same pass and rejected — widening the crests makes the
page EASIER, because a locally constant per-plane offset is exactly what
the head's own {1, y} residual eats.

EPISODE 3, 2026-08-31, hours later.  Three dots, dial off, every row
live: 300/300 AGAIN.  `tiles.swim` — the per-plane local-affine rescue —
landed after episode 2's re-pin and recovers this page unaided.
Measured on this tree at workers 1, `--complete`:

    dial off, every row live   300/300, ledger
                               {'tiles.local': 86, 'tiles.planek': 5,
                                'tiles.scan': 202, 'tiles.swim': 7}
                               against episode 2's
                               {'tiles.local': 84, 'tiles.planek': 1,
                                'tiles.scan': 202} — seven minted by the
                               new row and six more out of the frontier
                               it opened.  With the row in the schedule
                               the dial then buys nothing at all: 300
                               against 300, and `tiles.retry` fires 208
                               times with the field and 208 without.

AND THIS TIME THERE IS NO FOURTH DOT.  Episode 2's repair was to climb
one dot; episode 3 went looking for the next rung and measured that the
ladder has exactly one at c3.

WHY: `tiles.swim`'s translation bound is ONE PRINTED CELL measured from
the standing field's value (`swim.translation_bound_dots` is literally
`cell_dots_of(row)`).  This is a c3 page, so that bound is 3.000 dots —
EXACTLY the injected peak, and exactly a point on the search's own
coarse grid (`local_affine.COARSE_STEPS_PER_SIDE` = 2, so the first pass
evaluates ±bound and ±bound/2).  With the dial off the hint is zero and
the row searches ±3 dots around zero: the stimulus is inside its reach
with no margin at all.  The next whole dot up is
`test_h3_swim_existence`'s own stimulus (`STEEP_AMPLITUDE_DOTS` = 4),
where the field is the row that comes up short.  Four dots was measured
here anyway, with every row live, because a repair has to be rejected on
numbers: dial OFF the page loses the WHOLE Y plane (200/300, zero Y)
with NO rescue row firing at all — Y falls under the informative floor
and a rescue row can only help a tile the receiver still tries — and
dial ON it closes 300/300 with `tiles.swim` minting 23 of them.  So four
dots would satisfy the yield tests, and it is refused for three measured
reasons: the render is byte-identical to the swim module's own stimulus,
the dial-off arm exercises NO rescue row at all (a worse loss of
coexistence than holding one row out), and the close is the field's and
the swim's jointly, which is not this module's question.  The field's
usable band and the swim's blind band are the same band, one dot wide,
both ends are already taken, and the displacement is whole dots by
construction (`_h3_sims.plane_x_shift_dots` — a fractional shift would
have to be interpolated, and interpolation blurs the plane as well as
moving it, which is two changes at once).

FOUR OTHER DIRECTIONS WERE MEASURED AND ALL FAILED.  They are recorded
so nobody spends the afternoon again:

  SHAPE — the one that looked most promising, and the one CLOSED BY
  MEASURING THE OPERATORS THEMSELVES.  The standing proposal is
  curvature at the window scale: the field is a per-tile translation
  pooled over a two-tile Gaussian, the swim a six-parameter affine over
  a 200-cell window, and since a window is 3.125 tiles against a
  bandwidth of 2.0 the field's own resolution is FINER than the window —
  so a displacement curving inside one window ought to be the field's to
  express and not the affine's.  Run against the real
  `plane_field.solve` and the real `geometry.window_starts` on this
  page at 3 dots (commit d86feab, "field-yield e3: the curvature
  direction, closed by measuring the operators"; the instrument runs in
  about a second and moves by itself if either operator is repaired):

      cycles   field response   field residual   affine residual
        0.5        0.915             0.96          0.38 max / 0.25 mean
        1.0        0.769             1.07          0.37 / 0.33
        1.5        0.718             1.70          0.92 / 0.55
        2.0        0.549             2.58          1.34 / 1.08
        3.0        0.309             3.14          1.83 / 1.21

  The affine's residual is the SMALLER one at every frequency and the
  gap WIDENS with frequency, and neither side is handicapped — the field
  gets ideal noiseless anchor-form equations, the affine gets the exact
  unbounded least-squares fit, so both halves are upper bounds for their
  own side.  Frequency is not free to choose either: a non-integer cycle
  count leaves the displacement a nonzero mean (1.932 dots at half a
  cycle, exactly 0 at 1, 2 and 3), and a mean is what the colour lane's
  own {1, y} page-fraction residual absorbs before any rescue tier is
  reached.  A separate model over the bounded affine and the clamped,
  bilinearly read-back field agrees shape for shape — sine 3 dots 1
  cycle field 1.05 / affine 0.46, 1.5 cycles 1.75 / 0.92, 2 cycles 2.54
  / 1.34, triangle 0.82 / 0.32, dither-rounded 1.03 / 0.51, 4 dots 2.00
  / 0.67 — the affine smaller on every shape and in every tile row.  It
  has to be: the field's advantage is pooled evidence and never
  resolution, and its ridge, clamp and bandwidth make it the coarser
  model.  Raising the frequency hurts the FIELD first, which is episode
  2's "height bites, width doesn't" seen from the other side.  DO NOT
  BUILD A CURVATURE STIMULUS.

  EVIDENCE — sensor noise, on the theory that six parameters fitted per
  window degrade faster than two per tile pooled over a page.  Measured,
  dial off, every row live, same 3-dot displacement: sd 12 -> 300/300,
  sd 24 -> 300/300, sd 36 -> 300/300.  Tripling the noise costs the
  displaced page NOTHING; the residue tier just works harder
  (`tiles.local` 298 -> 367 -> 376 fires).  The in-register control
  certifies 300/300 at sd 36 too, all of it on `tiles.scan`.  And the
  direction is BACKWARDS: at sd 24 the FIELD's own Y fit falls from the
  1.1-2.0 dots it reads at sd 12 to 0.52 and refuses to publish, while
  the page still closes off the residue tier.  The pooled estimator is
  the one that loses.

  STARVING THE ROW'S LABELS — the precondition-starving family, and the
  one architectural difference that really does separate the two rows:
  the swim's objective floor is PER WINDOW (`MIN_OBJECTIVE_CELLS` = 64
  proven cells, `MIN_LIVE_STATES` = 2, `MIN_STATE_CELLS` = 8 each) where
  the field's level table is fitted over the whole page's measuring
  pass.  Unreachable from a stimulus, and by a wide margin: this format
  lays 120 furniture cells per tile (100 word + 20 dust), a window
  covers 9.77 tiles, so a window carries about 1,172 address-derived
  proven cells — 18x the floor — before a single tile has certified.
  Furniture is a pure function of the address, `_swim_eligible` has no
  certified-neighbour clause on purpose, and working on furniture alone
  in a band where nothing has certified is the regime the row was built
  for.  Starving it means taking the INK away, which is a contrast
  problem rather than a registration one, and the field cannot fix that
  either.  (Starving the certified COLLAR does deny `tiles.local` and
  `tiles.planek`, which need certified neighbours — but not the row that
  is actually absorbing this stimulus.)

  AN ABSOLUTE OFFSET — a page-constant or {1, y} ramp on the displaced
  plane, to push the swim past its bound while the lane's own residual
  eats the extra.  Settled in the source without spending a decode:
  `color_region_anchor.features_with_page_fraction` takes an offsets
  override INSTEAD of the page-fraction residual, not on top of it, and
  `fields.measure_window` samples at the standing field (None -> zero)
  on its first pass.  The field is absolute from the committed pose too,
  with 2.0 dots of clamp to spend (`plane_field.MAX_DELTA_DOTS`), so
  anything added to the absolute displacement is charged to the field's
  budget before the swim's.

THE REPAIR, 2026-08-31: hold `tiles.swim` out of all three decodes
(`conftest.FIELD_YIELD_HELD_OUT`), and pin the hold-out to the constant
that forces it rather than leaving it a habit.

Dropping a row is the weakest repair available here — it stops testing
that row's coexistence with the field — so it is taken only for the ONE
row whose licence covers this stimulus completely, and only after the
alternatives above were measured rather than argued.  The other four
rescue rows stay in the schedule and keep working the page:
`tiles.retry`, `tiles.local`, `tiles.planek` and `refine.color` all fire
in both arms, `tiles.local` and `tiles.planek` mint in both, and their
exact counts are pinned below.  The whole-tier drop that `test_h3_plugins_local_ctx` uses would
also delete this module's second product, so the minimum is the right
cut.  This is the day's standing ruling applied, not a new one: "no
stimulus retains certificate headroom against the residue arms, measured
four independent ways" (conversion_docs/RULINGS-2026-08-31.md), and the
local-ctx repair of the same morning — re-scope to the measured truth,
and pin the restoration condition.

Held out, and measured at workers 1 (`--complete`) on this tree:

    in register, dial off      300/300 certificates, payload byte-exact,
                               all 300 minted by `tiles.scan`
    displaced,   dial off      287/300 — the 13 losses are ALL Y and
                               form one contiguous band: tile row 2
                               columns 6-9, and nine of tile row 3's ten
    displaced,   dial on       299/300 — twelve of the thirteen bought
                               back, no address the control did not
                               certify, and the one it misses is
                               Y (3, 0)

and the hold-out costs exactly that tile and nothing else: with
`tiles.swim` PUT BACK and the dial on, the same page closes 300/300 with
the row minting ONE certificate — Y (3, 0) — and every other count
identical (`tiles.local` 86 certificates from 369 fires either way,
`tiles.planek` 11 from 14).  So the row's whole marginal value here,
once the field is running, is the single tile the field leaves; with the
field OFF it is the entire stimulus.  That asymmetry is the ruling.

TWELVE OF THIRTEEN, not thirteen, and that changed with the anchortier
merge rather than with this stimulus.  The 2026-08-31 median-publication
ruling ("publish p - median(all three planes)") took the plane-COMMON
part out of what the field publishes, and on this page that common part
— ~0.97 dots of pose-versus-ink bias, visible on all three planes of the
clean sim — was doing most of the ordinary read's work.  Episode 2's
dial-on ledger had `tiles.scan` minting 288 of 300; on this tree it
mints 202, exactly what the dial-off run mints, and the field's whole
gain now arrives through the rows that RE-READ — `tiles.planek` 1 -> 11
and `tiles.local` 84 -> 86, which is the twelve, exactly.  The ruling is
right and stands; the price it
charged on this page had not been read by anything until now.  That is
also why the work pins below no longer collapse: the field converts
thirteen hopeless tiles into twelve rescuable ones, and each rescue pays
a full local head fit, so `tiles.local` and `refine.color` RISE with the
dial on while the two rows that undo a registration error blind —
`tiles.planek`'s ±2-dot search and plain `tiles.retry` — recede.

EPISODE 4, 2026-09-03, the page moved, not the receiver.  The
canonical-identity merge (b8471fc) made the canonical
id — which is the AES row seed — the explicit spelling, so the emitted
page re-keyed.  Nothing in holo3/plugins changed.  Re-measured, all
three arms, same argv and hold-out:

    control 300, dial off 290, dial on 300.  The displacement costs
    TEN (all Y, floor 8), and the field buys back all ten — the
    dial-on page is the control's page exactly, so the shortfall
    above is now EMPTY and "twelve of thirteen" is ten of ten.
    Dial-off ledger {local 81, planek 9, scan 200} against episode
    3's {84, 1, 202}; dial-on {90, 10, 200}.  Rescue jobs keep the
    episode-3 shape: local 435 -> 513 and refine.color 470 -> 539
    rise with the dial, planek 67 -> 30 and retry 220 -> 210 recede.

The stimulus still discriminates — the floor holds with margin — so this
is a re-measure of the same question, not a fourth rot and not a loosened
pin.  DIAL_ON_SHORTFALL stays a golden, at empty, so losing ground fails
as loudly as gaining it did; the case is renamed off the count.  The
edge tile the field could not reach was not "the field growing" — it is
a different tile on a re-drawn page.

WHAT WAS NOT DONE, deliberately: the overlap witness is not a fourth
decode.  `test_h3_plugins_local_ctx` keeps its substitution measured
with an extra arm; this lane cannot afford one, so the witness is the
episode-3 ledger recorded above — and it is the FIRST thing to
re-measure when this module next fails (done 2026-09-03, episode 4).

WHY THIS LANE: the degraded capture is the most expensive decode in the
tree — its rescue tiers grind for tens of minutes of CPU at workers 1
against a 140 s budget for the entire slow lane.  Three decodes cannot
live there.  Run it with

    HOLO3_RUN_SLOW_TESTS=1 HOLO3_RUN_ORACLE_SWEEPS=1 \\
        python -m pytest holo3/tests/test_h3_color_field_yield.py -q

or drive the same three decodes without pytest through
`measure/h3_plane_fields.py` (`--drop tiles.swim` reproduces the arms).
"""

from __future__ import annotations

import numpy as np

from holo3 import data
from holo3.plugins import fields
from holo3.tests import _h3_sims, _h3_support

DISPLACED_STREAM = "Y"
PLANE_STREAMS = ("C", "M", "Y")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
Y_PLANE = 2

# Every rescue row, named, including the two that fire zero times here —
# because a zero is a verdict.  `tiles.uplift` never fires on this page
# at all.  `tiles.planek` is named because episode 2 was lost to
# assuming it did the rescuing when at two dots it never fired either —
# at three it does, 56 times for one certificate.  `tiles.swim` is named
# because episode 3 HOLDS IT OUT (`conftest.FIELD_YIELD_HELD_OUT`), so
# its zero below is the hold-out itself, pinned as behaviour rather than
# as configuration.
RESCUE_ROWS = ("tiles.retry", "tiles.local", "tiles.uplift",
               "tiles.planek", "tiles.swim", "refine.color")

# The rows that undo a registration error BLIND, and are therefore the
# ones the field is entitled to spare.  `tiles.local` and `refine.color`
# are deliberately not here: see the docstring's episode 3 — with the
# plane-common part no longer published, the field's gain arrives by
# making hopeless tiles rescuable, and each rescue pays a full local
# head fit, so those two RISE with the dial on.
SPARED_ROWS = ("tiles.retry", "tiles.planek")

# The one address the field cannot buy back on this page, pinned rather
# than tolerated: the page-EDGE tile of the steepest band, and exactly
# the kind of tile `test_h3_swim_existence` proves the held-out
# `tiles.swim` exists for.  If this set empties, the field has grown and
# the module should say so; if it grows, something has regressed.
#
# EMPTY since 2026-09-03 (episode 4): the field buys back all ten.  A
# non-empty set here now means the field has lost ground.
DIAL_ON_SHORTFALL: list[tuple[int, int, int, str]] = []

# The floor the re-hardened stimulus has to clear.  A FLOOR, not a
# golden: the dial-off page may certify more than it did the day this
# was measured — that is the receiver getting better — but not so much
# more that the field has nothing left to buy back.  Measured 13; the
# floor sits below that so an ordinary scheduling wobble reports itself
# through the exact ledgers rather than through this message, and a real
# collapse still trips it.  When it trips, the receiver has outgrown the
# stimulus a FOURTH time and the drill is in the module docstring —
# which now also records the three re-hardening directions that are
# already spent, so start by reading those.
MIN_LOST_TO_THE_DISPLACEMENT: int = 8

# WHICH ROWS MINT THIS PAGE'S CERTIFICATES — the pin episode 2 teaches.
# The module rotted silently because a row that had never minted a
# certificate here started minting ten, and nothing was reading the
# ledger; the yield tests only ever saw a total.  A row appearing,
# vanishing or moving in these tables is the loud version of that.  It
# is not a printed-format fork and not a number to quietly refresh: it
# is the signal to re-measure the stimulus and then decide whether it
# still discriminates at all.
#
# Re-measured 2026-09-03 (episode 4); the decision above was taken on
# evidence — the floor still holds — so this is the same question re-read.
CERTIFICATES_BY_ROW_DIAL_OFF: dict[str, int] = {
    "tiles.local": 81, "tiles.planek": 9, "tiles.scan": 200}
CERTIFICATES_BY_ROW_DIAL_ON: dict[str, int] = {
    "tiles.local": 90, "tiles.planek": 10, "tiles.scan": 200}

# The field's SECOND product, which no test read until episode 2, and
# which episode 3 had to restate.  Until the median-publication ruling
# the dial COLLAPSED these counts (`tiles.local` 251 -> 20,
# `refine.color` 494 -> 44) because the field's plane-common part made
# the ordinary read succeed outright.  With that part no longer
# published, the field instead makes hopeless tiles RESCUABLE, so the
# rows that pay for a rescue rise and only the blind registration rows
# recede.  Same drill as above when these move: re-measure, then decide
# whether the stimulus still discriminates.
# Re-measured 2026-09-03 (episode 4); the shape described above is intact.
RESCUE_JOBS_DIAL_OFF: dict[str, int] = {
    "tiles.retry": 220, "tiles.local": 435, "tiles.uplift": 0,
    "tiles.planek": 67, "tiles.swim": 0, "refine.color": 470}
RESCUE_JOBS_DIAL_ON: dict[str, int] = {
    "tiles.retry": 210, "tiles.local": 513, "tiles.uplift": 0,
    "tiles.planek": 30, "tiles.swim": 0, "refine.color": 539}


def _field_row(record: object) -> str:
    rows = [row for row in record.report["rows"]
            if row.startswith("fields   ")]
    assert len(rows) == 1, record.report["rows"]
    return rows[0]


def _medians(record: object, plane: int) -> list[float]:
    return [lane["planes"][plane]["median_delta_dots"]
            for lane in record.report["plane_fields"]
            if lane["planes"][plane]["median_delta_dots"] is not None]


def _streams(record: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in record.certificates:
        counts[key[3]] = counts.get(key[3], 0) + 1
    return counts


def _jobs(record: object) -> dict[str, int]:
    """Fires per row, counted from the run's own events.

    Deliberately NOT read out of `report["scheduler"]["plugins"]`: that
    list is the union of the queued, the ran and the in-flight, so a row
    that fires zero times is simply ABSENT from it.  In episode 2 the
    dial-on run stopped firing `refine.color` altogether — the very
    outcome the work test exists to celebrate — and the test died on a
    KeyError instead of passing.  Counting events makes a silent row a
    zero, which is a verdict.
    """
    counts: dict[str, int] = {}
    for event in record.events:
        if isinstance(event, data.JobDone):
            counts[event.plugin] = counts.get(event.plugin, 0) + 1
    return counts


def _rescue_jobs(record: object) -> dict[str, int]:
    jobs = _jobs(record)
    return {row: jobs.get(row, 0) for row in RESCUE_ROWS}


def _certificates_by_row(record: object) -> dict[str, int]:
    """Which rows minted this run's certificates, zero-rows omitted."""
    return {row["plugin"]: row["certificates"]
            for row in record.report["scheduler"]["plugins"]
            if row["certificates"]}


def test_the_in_register_control_certifies_the_whole_page(
        decode_hard_control):
    assert decode_hard_control.exit_code == 0
    assert _streams(decode_hard_control) == {name: 100
                                             for name in PLANE_STREAMS}
    assert (decode_hard_control.payload_sha256
            == _h3_sims.HARD_PAYLOAD_SHA256)


def test_displacing_one_plane_costs_certificates_in_that_plane_alone(
        decode_hard_control, decode_hard_shifted_off):
    lost = (set(decode_hard_control.certificates)
            - set(decode_hard_shifted_off.certificates))
    assert len(lost) >= MIN_LOST_TO_THE_DISPLACEMENT, (
        f"the degraded capture lost {len(lost)} certificates, under the "
        f"{MIN_LOST_TO_THE_DISPLACEMENT} this stimulus was hardened to "
        f"cost: the receiver has outgrown it again and the field has "
        f"nothing left to buy back. Re-harden and re-pin — see the "
        f"module docstring; do not lower this floor")
    assert {key[3] for key in lost} == {DISPLACED_STREAM}, sorted(lost)
    assert not (set(decode_hard_shifted_off.certificates)
                - set(decode_hard_control.certificates))


def test_the_field_buys_back_what_the_displacement_costs(
        decode_hard_control, decode_hard_shifted_off,
        decode_hard_shifted_on):
    """Every one of them, on this page — and the shortfall still pinned.

    RE-SCOPED 2026-08-31 (episode 3), and the stimulus is not what
    changed.  Until the median-publication ruling this arm certified the
    control's page exactly, because the field published a ~0.97-dot
    plane-COMMON pose bias along with Y's own displacement and that bias
    carried the ordinary read.  The ruling took the common part out — it
    is a pose correction and the field has no business carrying one —
    and the page then stopped one tile short.  So the claim became the
    measured one: no address the control did not certify, twelve of the
    thirteen losses bought back, and the thirteenth PINNED rather than
    tolerated.

    RENAMED 2026-09-03, because the count in the old name stopped being
    true and a case named off a number it no longer has is the rot this
    module exists to prevent.  After the b8471fc re-key the displacement
    costs 10 (all Y, floor 8) and the field buys back all 10: dial on is
    the control's page exactly.  The claim is now what the name says —
    the field buys back what the displacement costs — and the shortfall
    stays pinned, at empty, so losing ground fails this case as loudly as
    gaining it used to.
    """
    off = set(decode_hard_shifted_off.certificates)
    on = set(decode_hard_shifted_on.certificates)
    control = set(decode_hard_control.certificates)
    assert on > off, (
        f"dial on certified {len(on)}, dial off {len(off)}: the field "
        f"bought nothing back")
    assert not (on - control), sorted(on - control)
    _h3_support.assert_golden(
        "dial-on shortfall against the control",
        sorted(tuple(key) for key in control - on),
        [tuple(key) for key in DIAL_ON_SHORTFALL])


def test_the_recovered_certificates_carry_the_control_s_own_bits(
        decode_hard_control, decode_hard_shifted_on):
    checks = _h3_support.Checks("field-corrected zero-wrong")
    for key, certificate in sorted(
            decode_hard_shifted_on.certificates.items()):
        control = decode_hard_control.certificates.get(key)
        checks.check(f"{key} is an address the control also certified",
                     control is not None)
        if control is None:
            continue
        checks.check(
            f"{key} carries the control's user bits",
            np.array_equal(np.asarray(certificate.user_bits),
                           np.asarray(control.user_bits)),
            "a field may move evidence; it may never mint a certificate "
            "the in-register page disagrees with")
    checks.assert_clean()


def test_the_fields_row_fires_and_the_blind_registration_rows_recede(
        decode_hard_shifted_off, decode_hard_shifted_on):
    """The field's second product, restated at episode 3.

    It used to read "the rescue tiers stop thrashing", and until the
    median-publication ruling they did — `tiles.local` 251 fires -> 20,
    `refine.color` 494 -> 44 — because the field's plane-common part made
    the ordinary read succeed and no rescue was needed at all.  With that
    part no longer published, the field's gain arrives by making hopeless
    tiles RESCUABLE, and a rescue costs a full local head fit, so those
    two rows now rise with the dial on.  What still recedes, and is what
    this test is entitled to claim, are the rows that undo a registration
    error BLIND: `tiles.planek`'s ±2-dot sampling search and the plain
    re-attempt.  The field answers the question they were guessing at.

    The exact counts, in both directions, are pinned separately.
    """
    on = _jobs(decode_hard_shifted_on)
    off = _jobs(decode_hard_shifted_off)
    assert on.get("fields", 0) > 0, (
        "the fields row never fired with the dial on")
    for rescue in SPARED_ROWS:
        assert on.get(rescue, 0) < off.get(rescue, 0), (
            f"{rescue} fired {on.get(rescue, 0)} with the dial on "
            f"against {off.get(rescue, 0)} without it: the field is "
            f"supposed to spare the blind registration rows, not add to "
            f"them")


def test_which_rows_mint_this_page_s_certificates_is_pinned(
        decode_hard_shifted_off, decode_hard_shifted_on):
    """The ledger episode 2 taught this module to keep.

    The module rotted silently because a row that had never minted a
    certificate on this page started minting dozens, and nothing here
    was reading the ledger — the yield tests only saw a total.  A row
    appearing, vanishing or moving in these tables is the loud version
    of that.  It is not a printed-format fork and not a number to
    quietly refresh: it is the signal to re-measure, and then to decide
    whether the stimulus still discriminates at all.
    """
    _h3_support.assert_golden(
        "dial-off certificates by row",
        _certificates_by_row(decode_hard_shifted_off),
        CERTIFICATES_BY_ROW_DIAL_OFF)
    _h3_support.assert_golden(
        "dial-on certificates by row",
        _certificates_by_row(decode_hard_shifted_on),
        CERTIFICATES_BY_ROW_DIAL_ON)


def test_the_rescue_rows_fire_the_pinned_number_of_times(
        decode_hard_shifted_off, decode_hard_shifted_on):
    """What the dial costs and saves in WORK, exactly, both ways.

    Same drill as the ledger above when it moves.  The direction is
    tested separately and robustly; these are the exact counts, so a
    receiver that changes the WORK without changing the YIELD still says
    so out loud — which is precisely how episode 3 found the
    median-publication ruling's bill.  `tiles.swim`'s zero on both sides
    IS the hold-out, pinned here as behaviour rather than as
    configuration: if the row ever fires in these arms, someone has
    changed the fixtures and this test says so before any yield test
    quietly stops discriminating.
    """
    _h3_support.assert_golden("dial-off rescue fires",
                              _rescue_jobs(decode_hard_shifted_off),
                              RESCUE_JOBS_DIAL_OFF)
    _h3_support.assert_golden("dial-on rescue fires",
                              _rescue_jobs(decode_hard_shifted_on),
                              RESCUE_JOBS_DIAL_ON)


def test_both_runs_recover_the_payload_byte_for_byte(
        decode_hard_shifted_off, decode_hard_shifted_on):
    assert (decode_hard_shifted_off.payload_sha256
            == _h3_sims.HARD_PAYLOAD_SHA256)
    assert (decode_hard_shifted_on.payload_sha256
            == _h3_sims.HARD_PAYLOAD_SHA256)


def test_the_pair_is_one_emit_rendered_twice(sim_color_hard):
    control, shifted = sim_color_hard
    assert control.format_ref == shifted.format_ref
    assert control.payload_sha256 == shifted.payload_sha256
    assert control.tiff_sha256 != shifted.tiff_sha256
    assert control.emit_dir == shifted.emit_dir


def test_the_injected_displacement_is_whole_dots_and_mean_zero():
    shift = _h3_sims.plane_x_shift_dots(1920,
                                        _h3_sims.SHIFTED_AMPLITUDE_DOTS,
                                        _h3_sims.SHIFTED_CYCLES)
    assert shift.dtype == np.int64
    assert int(np.abs(shift).max()) == 3
    assert abs(int(shift.sum())) <= 2
    assert set(np.unique(shift).tolist()) == {-3, -2, -1, 0, 1, 2, 3}


def test_the_displacement_clears_the_blind_search_that_would_undo_it():
    """Three dots is a bound, not a taste.

    `tiles.planek` is the one row that searches a window's sampling
    offset BLIND, and it searches x — the axis this stimulus displaces —
    over a closed interval.  A displacement inside that interval is a
    page planek can undo without any field, which is how episode 2's
    successor would have started.  Pinning the relation, not just the
    number, means a widened search moves this test instead of silently
    dissolving the stimulus.
    """
    from holo3.plugins import plane_k

    assert (_h3_sims.SHIFTED_AMPLITUDE_DOTS
            > plane_k.SHIFT_MAX_DOTS), (
        f"the injected peak {_h3_sims.SHIFTED_AMPLITUDE_DOTS} dots no "
        f"longer clears tiles.planek's blind search "
        f"(+-{plane_k.SHIFT_MAX_DOTS} dots): the rescue tier can undo "
        f"this displacement on its own again")
    assert (_h3_sims.SHIFTED_AMPLITUDE_DOTS
            > abs(plane_k.SHIFT_MIN_DOTS))


def test_the_held_out_row_could_undo_this_stimulus_unaided():
    """Why `tiles.swim` is not in these three decodes — and when to stop.

    The row searches a full per-plane local affine whose translation
    bound is ONE PRINTED CELL, measured from the standing field's own
    value.  This is a c3 page, so that bound is 3.000 dots — exactly the
    injected peak, and exactly a point on the search's own coarse grid.
    With the dial off the hint is zero, so the stimulus sits inside the
    row's blind reach with no margin at all, which is what episode 3
    measured: 300/300 with the field switched off, seven certificates
    minted by the row and six more from the frontier it opened.

    PINNING THE RELATION RATHER THAN THE DECISION means the hold-out
    expires by itself.  The day this bound stops covering the injected
    peak, the row can no longer undo the stimulus and belongs back in
    the schedule.  The other end is watched from
    `test_h3_swim_existence`, whose licence case fails first if the
    field ever grows enough to buy back a four-dot page unaided — at
    which point this module can climb the dot and take the row back.
    Between the two, the ruling cannot go stale quietly.
    """
    from holo3.format.identity import resolve_format_ref
    from holo3.plugins import swim

    row = resolve_format_ref(_h3_sims.HARD_FORMAT_REF)
    bound_dots = swim.translation_bound_dots(row)
    assert _h3_sims.SHIFTED_AMPLITUDE_DOTS <= bound_dots, (
        f"the injected peak {_h3_sims.SHIFTED_AMPLITUDE_DOTS} dots no "
        f"longer sits inside tiles.swim's blind translation bound "
        f"({bound_dots} dots): the row can no longer undo this stimulus "
        f"on its own, so the hold-out in the fixtures has expired — put "
        f"the row back and re-pin")
    assert _h3_sims.STEEP_AMPLITUDE_DOTS > bound_dots, (
        "test_h3_swim_existence's stimulus is supposed to sit OUTSIDE "
        "that bound; if it does not, the two modules are asking the "
        "same question")
    assert _h3_sims.STEEP_AMPLITUDE_DOTS > _h3_sims.SHIFTED_AMPLITUDE_DOTS, (
        "the two stimuli sit either side of the swim's bound; the steep "
        "one is re-derived whenever the field changes (the per-row shift "
        "is whole dots by construction, the amplitude is not)")


def test_the_clean_colour_sim_is_unmoved_by_the_dial(
        decode_color_w1, decode_color_w1_fields):
    assert (decode_color_w1_fields.payload_sha256
            == decode_color_w1.payload_sha256)
    _h3_support.assert_golden(
        "dial-on clean colour certificate set",
        sorted(decode_color_w1_fields.certificates),
        sorted(decode_color_w1.certificates))


# -- the FIELD band on a real capture --------------------------------
#
# The rendering gate: the band exists as a run-dir product, it reports
# the fitted magnitude of the plane that was actually displaced, and the
# in-register control's own band says so instead of claiming a field.


def test_the_dial_off_run_says_off_and_draws_no_band(
        decode_hard_shifted_off):
    assert _field_row(decode_hard_shifted_off).startswith("fields   off")
    assert decode_hard_shifted_off.report["plane_fields"] == []
    assert not (decode_hard_shifted_off.run_dir
                / "pane-field-0.png").exists()


def test_the_band_lands_as_a_run_dir_product_with_the_dial_on(
        decode_hard_shifted_on):
    pane = decode_hard_shifted_on.run_dir / "pane-field-0.png"
    assert pane.is_file(), sorted(
        p.name for p in decode_hard_shifted_on.run_dir.iterdir())
    assert pane.read_bytes()[:8] == PNG_MAGIC


def test_the_band_reports_the_displacement_it_was_given(
        decode_hard_shifted_on):
    lanes = decode_hard_shifted_on.report["plane_fields"]
    assert lanes, "the dial-on run reported no fit at all"
    published = [lane for lane in lanes
                 if lane["planes"][Y_PLANE]["published"]]
    assert published, (
        f"no lane published a {DISPLACED_STREAM} field on the page whose "
        f"{DISPLACED_STREAM} plane was displaced; medians "
        f"{_medians(decode_hard_shifted_on, Y_PLANE)}")
    assert max(_medians(decode_hard_shifted_on, Y_PLANE)) >= (
        fields.MIN_DELTA_DOTS)
    row = _field_row(decode_hard_shifted_on)
    assert row.startswith("fields   lane ")
    assert f"{DISPLACED_STREAM} " in row and "published" in row


def test_the_in_register_control_reads_the_same_field_on_all_three_planes(
        decode_color_w1_fields, decode_hard_shifted_on):
    """The control's three planes agree, and now they agree at zero.

    THE OPEN RULING THIS DOCSTRING CARRIED IS CLOSED, and the numbers
    moved with it.  It used to record 0.973 / 0.974 / 0.975 dots on
    C / M / Y — one plane-COMMON field on all three planes, nearly 4x
    the 0.25-dot publish floor — and called what to do about that an
    open question, because a pose-versus-ink bias is not a per-plane
    registration and the field had no business publishing one.  The
    median-publication ruling (publish `p - median(all three)`) settled
    it, and re-measured on this tree the same page reads
    0.012 / 0.025 / 0.004 dots and publishes nothing at all.  The
    plane-common part is cancelled exactly, which is what that form is
    for.

    (Both readings are in honest dots.  The 0.287 / 0.283 / 0.287 this
    docstring carried before either was the SAME physical reading in the
    wrong unit — the fitter measured in cells and the schema called them
    dots, so a c3 page under-reported itself by cell_dots.)

    THE PRICE IS RECORDED IN THE MODULE DOCSTRING, because it is not
    free: on the displaced page that ~0.97-dot common part was carrying
    the ordinary read, and without it the dial-on arm stops one tile
    short and the rescue rows do more work, not less.  The ruling stands;
    the bill is now read by tests instead of by nobody.

    So the control's claim here is the shape: three planes that agree
    with each other, and a smaller field than the page whose Y plane was
    actually displaced.
    """
    lanes = decode_color_w1_fields.report["plane_fields"]
    assert lanes, "the fields row never fitted the in-register page"
    per_plane = [max(_medians(decode_color_w1_fields, plane), default=None)
                 for plane in range(3)]
    assert all(value is not None for value in per_plane), per_plane
    assert max(per_plane) - min(per_plane) < 0.10, (
        f"the in-register page's three planes disagree ({per_plane}): "
        f"that is not one plane-common bias")
    assert max(per_plane) < max(_medians(decode_hard_shifted_on, Y_PLANE)), (
        "the in-register page's field is as large as the displaced "
        "page's: the band would be reporting noise, not registration")
    row = _field_row(decode_color_w1_fields)
    assert row.startswith("fields   lane ")
    published = [plane["plane_name"] for lane in lanes
                 for plane in lane["planes"] if plane["published"]]
    assert ("published" in row) is bool(published), (row, published)
