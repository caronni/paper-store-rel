from __future__ import annotations

import importlib.util
from fractions import Fraction
from types import SimpleNamespace

from holo.receiver import engine, schedule
from holo.receiver.descriptor import KEY_KINDS
from holo.receiver.format import identity
from holo.receiver.format.identity import Family
from holo.receiver.tests import _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_the_escalating_rows_are_derived_from_their_own_cost_functions`,
# `test_the_fold_dispatch_types_every_fact_the_rows_produce`,
# `test_the_rendered_table_is_what_schedule_md_carries`.
# 2026-10-12 (CMY-RECEIVER-PLAN A6): SCHEDULE.md's generated block
# regenerated for `tiles.cond` -- one descriptor row, one ladder line at
# 20 beside the three payload peers, and the row in the `tile` and
# `attempt` families' readers; no price and no escalation moved.
# 2026-10-18 (the owner's price balance, measure/sched_trace/
# YIELD-OVER-CPU-2026-10-18.md §5-6): `tiles.local` ESCALATES -- the
# residue rows pay base + base x earlier fires, so a row pays its base
# once and local's re-fires (the dearest minting work on every colour
# sheet) no longer pop ahead of planek's and swim's first fires; the
# ladder gains `220*n tiles.local` and the generated block follows.
# Literals unchanged.
# 2026-10-18 (the owner's price balance, YIELD-OVER-CPU-2026-10-18.md §2):
# the cmy retry is priced into the residue band -- `tiles.retry` declares
# a second stage `retry_cmy` at 241 (one above swim's first fire, under
# cold placement), so the ladder gains `241 tiles.retry retry_cmy` and
# the generated block follows; the descriptor rows and every other price
# unchanged, `tiles.cond` stays at the scan's 20.

SCHEDULE_MD = _h3_support.HOLO3_ROOT / "docs" / "SCHEDULE.md"

#: One small declared row: the header line is a property of the
#: format, not of the sheet, and a 10x10 identity carries it.
FORMAT_REF = "c3-k-r0550@10x10"

ESCALATING_GOLDEN = {"color": (160,), "color.pooled_ctx": (170,),
                     "fields.collect": (180,), "tiles.uplift": (210, 220),
                     "tiles.local": (220,),
                     "tiles.planek": (230,), "tiles.swim": (240,)}

ESCALATION_LINE = "  160*n  color            color_refit"
POOLED_LINE = "  170*n  color.pooled_ctx pooled_ctx"

FOLD_DISPATCH_GOLDEN = {
    "AttemptFact": "_fold_attempt",
    "Capture": "_fold_capture",
    "CaptureSurvey": "_fold_survey",
    "Certificate": "_fold_certificate",
    "ColorCtxPopulation": "_fold_color_pop",
    "ColorEvidenceRow": "_fold_color_row",
    "ColorLaneFit": "_fold_color_lane_fit",
    "CtxOutcome": "_fold_ctx_outcome",
    "EvidenceRevision": "_fold_evidence_revision",
    "FieldObservations": "_fold_field_observations",
    "LatticeSeed": "_fold_lattice_seed",
    "PlaceOutcome": "_fold_place_outcome",
    "Placement": "_fold_placement",
    "PlaneField": "_fold_plane_field",
    "PooledColorCtx": "_fold_pooled_ctx",
    "RefineOutcome": "_fold_refine_outcome",
    "Window": "_fold_window",
    "WindowEvidence": "_fold_evidence",
}

def _fenced_block(text: str) -> tuple[str, ...]:
    lines = text.splitlines()
    fences = [index for index, line in enumerate(lines)
              if line.startswith("```")]
    assert len(fences) == 2, (
        "SCHEDULE.md must carry exactly one fenced block: the generated "
        "table")
    return tuple(lines[fences[0] + 1:fences[1]])


def test_every_declared_price_is_a_positive_int():
    checks = _h3_support.Checks("declared prices")
    for descriptor in engine.DESCRIPTORS:
        checks.check(f"{descriptor.name} declares at least one price",
                     bool(descriptor.prices))
        for stage, price in descriptor.prices:
            checks.check(f"{descriptor.name}/{stage} price is a positive int",
                         isinstance(price, int)
                         and not isinstance(price, bool) and price > 0)
            checks.check(f"{descriptor.name}/{stage} names a stage",
                         isinstance(stage, str) and bool(stage))
    checks.assert_clean()


def _rendered_ladder_block(lines: tuple[str, ...]) -> tuple[str, ...]:
    start = next(index for index, line in enumerate(lines)
                 if line.startswith("price ladder"))
    return lines[start + 1:lines.index("", start)]


def test_every_ladder_row_is_the_line_the_rendered_block_carries():
    # SCHEDULE.md pins the RENDERING byte for byte (below); this pins the
    # structured return against it, so a row that changed price or stage
    # without the doc moving is a failure here and not a silent re-spell.
    ladder = schedule.price_ladder(engine.DESCRIPTORS)
    block = _rendered_ladder_block(schedule.render(engine.DESCRIPTORS))
    checks = _h3_support.Checks("price_ladder rows vs rendered block")
    checks.equal("one rendered line per ladder row", len(block), len(ladder))
    for (price, name, stage, shared, ordinal), line in zip(ladder, block):
        label = f"{price}{schedule.ESCALATION}" if ordinal else str(price)
        checks.equal(
            f"{name}/{stage} at {price} is rendered", tuple(line.split()),
            (label, name, stage) + ((schedule.COLLISION,) if shared else ()))
    checks.assert_clean()


def test_the_ladder_is_sorted_and_marks_exactly_the_shared_prices():
    ladder = schedule.price_ladder(engine.DESCRIPTORS)
    assert [row[0] for row in ladder] == sorted(row[0] for row in ladder)
    shared = {price for price, _n, _s, mark, _e in ladder if mark}
    counts = {price: sum(1 for row in ladder if row[0] == price)
              for price, _n, _s, _m, _e in ladder}
    assert shared == {price for price, n in counts.items() if n > 1}, (
        "a same-price collision is a deliberate round-robin peer set: the "
        "table must mark exactly those")


def test_a_declared_price_is_what_the_row_charges_on_its_first_fire():
    checks = _h3_support.Checks("declared price == cost() at rung 0, fire 1")
    subjects = {
        "survey": "capture",
        "calibrate": ("cap", 0, 0, (0, 0, 8, 8)),
        "ctx": ("cap", 0, 0),
        "color": ("cap", 0, 0),
        "color.pooled_ctx": (0, "8"),
        "fields": ("cap", 0, 0),
        "tiles.scan": (0, 0, 0, "cap", 0),
        "tiles.union": (0, 0, 0, Fraction(2)),
        "tiles.retry": ("scan", 0, 0, 0, "main", 0, "cap"),
        "tiles.cond": ("scan", 0, 0, 0, "lo", 0, "cap"),
        "tiles.local": (0, 0, 0, Fraction(2)),
        "tiles.planek": (0, 0, 0, "Y", Fraction(2)),
        "refine": ("cap", 0, 0, (0, 0, 8, 8)),
        "refine.color": ("cap", 0, 0, (0, 0, 8, 8)),
    }
    base_rung = SimpleNamespace(union_rung_ordinal=lambda ppc: 0)
    # the colour row's re-fit ordinal is a store cell, not the fire
    # count: a lane that has never fitted still charges the declared
    # first-re-fit price
    unfitted_lane = SimpleNamespace(color_lane_head_fits=lambda lane: 0)
    # the retry's price follows the row's family: its payload stage is
    # checked on a K store, its cmy stage on a cmy store (2026-10-18)
    k_rung = SimpleNamespace(union_rung_ordinal=lambda ppc: 0,
                             row=SimpleNamespace(family=Family.K))
    cmy_rung = SimpleNamespace(union_rung_ordinal=lambda ppc: 0,
                               row=SimpleNamespace(family=Family.CMY))
    stores = {"tiles.union": base_rung, "tiles.retry": k_rung,
              "tiles.cond": base_rung,
              "tiles.local": base_rung, "tiles.planek": base_rung,
              "color": unfitted_lane}
    stage_stores = {("tiles.retry", "retry_cmy"): cmy_rung}
    for descriptor in engine.DESCRIPTORS:
        if descriptor.name not in subjects:
            continue
        # the FIRST fire is `attempts == 0`: the engine counts a fire
        # only after it happened (engine._fill), and since 2026-10-18 a
        # residue row's second fire (attempts 1) already adds its base.
        # The one row whose first fire is deliberately FREE is the
        # pooled colour context (PRICING-ESCALATION §7.3 / ruling 9,
        # measured on sheet J): its declared 170 is its second fire's.
        attempts = 1 if descriptor.name == "color.pooled_ctx" else 0
        for stage, price in descriptor.prices:
            checks.equal(
                f"{descriptor.name}/{stage} charges its declared price",
                descriptor.cost(stage_stores.get(
                                    (descriptor.name, stage),
                                    stores.get(descriptor.name)),
                                subjects[descriptor.name], stage,
                                attempts, 0),
                price)
    checks.assert_clean()


def test_the_push_price_is_the_descriptor_cost_and_nothing_else():
    source = (_h3_support.HOLO3_ROOT / "engine.py").read_text()
    assert ("cost = descriptor.cost(self, worker.subject, stage, "
            "worker.attempts," in source)
    assert "worker.last_cost = cost" in source
    assert "job_price" not in source and "REWORK" not in source


def test_the_escalating_rows_are_derived_from_their_own_cost_functions():
    found = {descriptor.name: tuple(sorted(
        schedule.escalating_prices(descriptor)))
        for descriptor in engine.DESCRIPTORS}
    _h3_support.assert_measured(
        "rows that re-price by fire ordinal",
        {name: prices for name, prices in found.items() if prices},
        ESCALATING_GOLDEN)


def test_the_ladder_prints_the_escalation_instead_of_a_flat_lie():
    assert ESCALATION_LINE in schedule.ladder_rows(engine.DESCRIPTORS)
    assert POOLED_LINE in schedule.ladder_rows(engine.DESCRIPTORS), (
        "the ladder columns are derived from the widest row: a fixed "
        "width silently ran the name into the stage")
    rendered = schedule.render(engine.DESCRIPTORS)
    assert ESCALATION_LINE in rendered
    assert any(line.startswith("price ladder")
               and schedule.ESCALATION in line for line in rendered), (
        "the ladder legend must say what the mark means")


def test_every_derived_family_belongs_to_the_closed_vocabulary():
    for descriptor in engine.DESCRIPTORS:
        assert set(schedule.read_families(descriptor)) <= set(KEY_KINDS)


def test_the_derivation_follows_a_helper_the_reads_function_calls():
    scan = schedule.read_families(engine.DESCRIPTOR_BY_NAME["tiles.scan"])
    union = schedule.read_families(engine.DESCRIPTOR_BY_NAME["tiles.union"])
    assert scan == union, (
        "tiles.union reads through _scan_reads: a derivation that stops at "
        "the declared function body would report nothing here")


def test_the_fold_dispatch_types_every_fact_the_rows_produce():
    _h3_support.assert_measured("store fold dispatch",
                               schedule.fold_dispatch(), FOLD_DISPATCH_GOLDEN)
    dispatch = schedule.fold_dispatch()
    produced = {kind.__name__ for descriptor in engine.DESCRIPTORS
                for kind in descriptor.produces}
    assert produced <= set(dispatch), sorted(produced - set(dispatch))


def test_a_fold_that_delegates_carries_the_delegate_families():
    assert set(schedule.write_families("_fold_evidence")) <= set(
        schedule.write_families("_fold_ctx_outcome")), (
        "_fold_ctx_outcome folds evidence rows through _fold_evidence: the "
        "derivation must follow the call")


def test_the_key_derivation_still_detects_a_planted_subscription(tmp_path):
    planted = tmp_path / "h3_planted_reads.py"
    planted.write_text(
        "KEY_TILE = 'tile'\n"
        "def _helper():\n"
        "    return (KEY_TILE,)\n"
        "def _reads():\n"
        "    return _helper()\n")
    spec = importlib.util.spec_from_file_location("h3_planted_reads",
                                                  planted)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert schedule._key_constants(module, "_reads") == ("tile",)
    assert schedule._key_constants(module, "_absent") == ()


def test_the_rendered_table_is_what_schedule_md_carries():
    _h3_support.assert_measured("SCHEDULE.md generated block",
                               _fenced_block(SCHEDULE_MD.read_text()),
                               schedule.render(engine.DESCRIPTORS))


def test_the_rendered_table_names_every_row_and_every_key_family():
    lines = schedule.render(engine.DESCRIPTORS)
    checks = _h3_support.Checks("rendered coverage")
    for descriptor in engine.DESCRIPTORS:
        checks.check(f"row {descriptor.name} is rendered",
                     any(line.startswith(descriptor.name) for line in lines))
    for kind in KEY_KINDS:
        checks.check(f"family {kind} is rendered",
                     any(line.startswith(kind) for line in lines))
    checks.assert_clean()


def test_a_declared_format_only_adds_its_header_line():
    row = identity.resolve_format_ref(FORMAT_REF)
    bare = schedule.render(engine.DESCRIPTORS)
    named = schedule.render(engine.DESCRIPTORS, row)
    assert named[0] == f"format {row.display_id}  family K"
    assert named[2:] == bare
