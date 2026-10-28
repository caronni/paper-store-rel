from __future__ import annotations

import importlib.util
from fractions import Fraction
from types import SimpleNamespace

import pytest

from holo3 import engine, schedule
from holo3.descriptor import KEY_KINDS
from holo3.format import identity
from holo3.tests import _h3_support

SCHEDULE_MD = _h3_support.HOLO3_ROOT / "SCHEDULE.md"

FORMAT_REF = "L:c2-r0700@3392x2368"

LADDER_GOLDEN = (
    (10, "survey", "survey", False, False),
    (15, "calibrate", "calibrate", True, False),
    (15, "color", "calibrate", True, False),
    (15, "ctx", "calibrate", True, False),
    (20, "tiles.retry", "payload", True, False),
    (20, "tiles.scan", "payload", True, False),
    (20, "tiles.union", "payload", True, False),
    (40, "place", "ring", False, False),
    (60, "place", "word_centre", False, False),
    (80, "place", "word_rest", False, False),
    (120, "place", "wide", False, False),
    (160, "color", "color_refit", False, True),
    (170, "color.pooled_ctx", "pooled_ctx", False, True),
    (180, "fields", "fields", False, True),
    (200, "refine", "refine", True, False),
    (200, "refine.color", "refine", True, False),
    (200, "revisit", "refine", True, False),
    (210, "tiles.uplift", "uplift_a3", False, True),
    (220, "tiles.local", "local", True, False),
    (220, "tiles.uplift", "uplift_a4b", True, True),
    (230, "tiles.planek", "planek", False, True),
    (240, "tiles.swim", "swim", False, True),
    (250, "place", "cold_live", False, False),
    (260, "place", "cold_rest", False, False),
)

ESCALATING_GOLDEN = {"color": (160,), "color.pooled_ctx": (170,),
                     "fields": (180,), "tiles.uplift": (210, 220),
                     "tiles.planek": (230,), "tiles.swim": (240,)}

ESCALATION_LINE = "  160*n  color            color_refit"
POOLED_LINE = "  170*n  color.pooled_ctx pooled_ctx"

READ_FAMILIES_GOLDEN = {
    "survey": (),
    "place": ("lattice_seed", "live_pages", "pose_affine"),
    "calibrate": ("pose_affine", "region_pitch"),
    "ctx": ("evidence_fit",),
    "color": ("lane_poses", "page_certs", "plane_field", "pooled_ctx"),
    "color.pooled_ctx": ("color_pop",),
    "fields": ("lane_poses", "page_certs"),
    "tiles.scan": ("color_row", "evidence_fit", "evidence_read"),
    "tiles.union": ("color_row", "evidence_fit", "evidence_read"),
    "tiles.retry": ("color_row", "evidence_fit", "evidence_read"),
    "tiles.local": ("color_row", "evidence_fit", "evidence_read", "tile"),
    "tiles.planek": ("color_row", "plane_field", "tile"),
    "tiles.swim": ("color_row", "lane_poses", "plane_field", "tile"),
    "refine": ("evidence_fit", "evidence_read", "pose_affine",
               "pose_route", "tile"),
    "refine.color": ("plane_field", "pose_affine", "pose_route", "tile"),
    "revisit": ("evidence_fit", "evidence_read", "lane_poses",
                "pose_affine", "region_ctx", "region_pitch", "tile"),
}

FOLD_DISPATCH_GOLDEN = {
    "AttemptFact": "_fold_attempt",
    "Capture": "_fold_capture",
    "CaptureSurvey": "_fold_survey",
    "Certificate": "_fold_certificate",
    "ColorCtxPopulation": "_fold_color_pop",
    "ColorEvidenceRow": "_fold_color_row",
    "ColorLaneFit": "_fold_color_lane_fit",
    "CtxOutcome": "_fold_ctx_outcome",
    "LatticeSeed": "_fold_lattice_seed",
    "PlaceOutcome": "_fold_place_outcome",
    "Placement": "_fold_placement",
    "PlaneField": "_fold_plane_field",
    "PooledColorCtx": "_fold_pooled_ctx",
    "RefineOutcome": "_fold_refine_outcome",
    "Window": "_fold_window",
    "WindowEvidence": "_fold_evidence",
}

WRITE_FAMILIES_GOLDEN = {
    "_fold_attempt": (),
    "_fold_capture": (),
    "_fold_certificate": ("page_certs", "tile"),
    "_fold_color_pop": ("color_pop",),
    "_fold_color_lane_fit": (),
    "_fold_color_row": ("color_row",),
    "_fold_ctx_outcome": ("evidence_fit", "evidence_read", "region_ctx"),
    "_fold_evidence": ("evidence_fit", "evidence_read"),
    "_fold_lattice_seed": ("lattice_seed",),
    "_fold_place_outcome": ("place_stage",),
    "_fold_plane_field": ("plane_field",),
    "_fold_pooled_ctx": ("pooled_ctx",),
    "_fold_placement": ("lane_poses", "live_pages", "place_stage",
                        "pose_affine", "pose_route", "region_pitch"),
    "_fold_refine_outcome": ("lane_poses", "live_pages", "place_stage",
                             "pose_affine", "pose_route", "region_pitch"),
    "_fold_survey": (),
    "_fold_window": (),
}

REWORK_GONE = ("REWORK_FLOOR", "REWORK_SLOPE", "job_price")


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


def test_the_resolved_ladder_is_the_sorted_union_of_the_plugin_literals():
    _h3_support.assert_golden("price ladder",
                              schedule.price_ladder(engine.DESCRIPTORS),
                              LADDER_GOLDEN)


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
        "tiles.local": (0, 0, 0, "main", Fraction(2)),
        "tiles.planek": (0, 0, 0, "Y", Fraction(2)),
        "refine": ("cap", 0, 0, (0, 0, 8, 8)),
        "refine.color": ("cap", 0, 0, (0, 0, 8, 8)),
        "revisit": ("cap", 0, 0, (0, 0, 8, 8)),
    }
    base_rung = SimpleNamespace(union_rung_ordinal=lambda ppc: 0)
    # the colour row's re-fit ordinal is a store cell, not the fire
    # count: a lane that has never fitted still charges the declared
    # first-re-fit price
    unfitted_lane = SimpleNamespace(color_lane_head_fits=lambda lane: 0)
    stores = {"tiles.union": base_rung, "tiles.retry": base_rung,
              "tiles.local": base_rung, "tiles.planek": base_rung,
              "color": unfitted_lane}
    for descriptor in engine.DESCRIPTORS:
        if descriptor.name not in subjects:
            continue
        for stage, price in descriptor.prices:
            checks.equal(
                f"{descriptor.name}/{stage} charges its declared price",
                descriptor.cost(stores.get(descriptor.name),
                                subjects[descriptor.name], stage, 1, 0),
                price)
    checks.assert_clean()


@pytest.mark.parametrize("name", REWORK_GONE)
def test_the_engine_owns_no_pricing_name(name):
    assert not hasattr(engine, name), (
        f"{name} is back: cost is a scheduling function of the plugins, "
        f"nothing the engine determines or influences (ruling 2026-08-29)")


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
    _h3_support.assert_golden(
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


@pytest.mark.parametrize("name", sorted(READ_FAMILIES_GOLDEN))
def test_the_subscription_families_derive_from_the_reads_functions(name):
    _h3_support.assert_golden(
        f"{name} reads",
        schedule.read_families(engine.DESCRIPTOR_BY_NAME[name]),
        READ_FAMILIES_GOLDEN[name])


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
    _h3_support.assert_golden("store fold dispatch", schedule.fold_dispatch(),
                              FOLD_DISPATCH_GOLDEN)
    dispatch = schedule.fold_dispatch()
    produced = {kind.__name__ for descriptor in engine.DESCRIPTORS
                for kind in descriptor.produces}
    assert produced <= set(dispatch), sorted(produced - set(dispatch))


@pytest.mark.parametrize("method", sorted(WRITE_FAMILIES_GOLDEN))
def test_the_write_families_derive_from_the_folds_that_type_each_fact(
        method):
    _h3_support.assert_golden(f"{method} writes",
                              schedule.write_families(method),
                              WRITE_FAMILIES_GOLDEN[method])


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
    _h3_support.assert_golden("SCHEDULE.md generated block",
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
    assert named[0] == f"format {row.row_id}  family K"
    assert named[2:] == bare
