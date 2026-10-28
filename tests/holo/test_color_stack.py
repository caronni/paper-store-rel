"""PK2: the region stack, the KnownField carrier, and the sampling leaf.

PK2 is a BYTE-IDENTICAL refactor — it moves three things out of
``color_payload``/``color_anchoring`` and must change nothing a decode
sees.  These tests pin that claim three ways:

1. ``color_stack.fit_region_stack`` reproduces the historical inline arm
   logic EXACTLY, on real region inputs recorded from
   ``collect_color_evidence`` (the oracle below is the pre-PK2 code,
   copied verbatim).  Both gate outcomes are exercised and the fixtures
   pin that they stay exercised.
2. Refusal is a bit-exact null: a non-adopted arm returns the
   predecessor's OWN tuple and array objects, never an identity transform
   (RECEIVE-DESIGN §6.2a, risk R3).
3. ``known_field.build_known_rows`` reproduces the legacy
   reference-states derivation and is the single enforcement point of the
   §6.2a provenance law — its validator refuses a fabricated label, a
   half-known furniture site, and an unattributed one.

The cross-refactor guarantee itself (pre-PK2 evidence bytes == post-PK2
evidence bytes on these same fixtures) was measured out of tree with the
snapshot pair; what is committed here is the in-process baseline the
suite can re-derive at any time.
"""
from __future__ import annotations

import numpy as np
import pytest

from _color_stack_fixtures import FIXTURE_KEYS, build_fixture
from holo.receive import (
    color_anchoring,
    color_payload,
    color_refine,
    color_sampling,
    color_stack,
    known_field,
)
from holo.receive.color_fitting import _fit_detector
from holo.receive.color_payload import collect_color_evidence
from holo.receive.known_field import (
    PROVENANCE_CERTIFIED,
    PROVENANCE_DUST,
    PROVENANCE_UNKNOWN,
    PROVENANCE_WORD,
    KnownFieldError,
    build_known_rows,
)


# The pre-PK2 inline arm logic (color_payload.py:819-853 at e554ca9),
# copied verbatim.  It is the oracle, so it must NOT be refactored to
# share code with the implementation under test.
def _historical_arms(spec, selection, base_tuple, corrected):
    baseline_fit = None
    selected_fit = None
    selected_features = base_tuple
    adopted = False
    reason = ""
    try:
        baseline_fit = _fit_detector(spec, selection, base_tuple)
    except ValueError as exc:
        reason = str(exc)
    try:
        candidate_fit = (
            None if corrected is None
            else _fit_detector(spec, selection, corrected)
        )
    except ValueError:
        candidate_fit = None
    if baseline_fit is not None:
        selected_fit = baseline_fit
    if candidate_fit is not None and (
        selected_fit is None
        or (
            candidate_fit.heldout_loss + 1e-9 < selected_fit.heldout_loss
            and candidate_fit.word_heldout_loss
            <= selected_fit.word_heldout_loss + 1e-9
            and candidate_fit.dust_heldout_loss
            <= selected_fit.dust_heldout_loss + 1e-9
        )
    ):
        selected_fit = candidate_fit
        selected_features = corrected
        adopted = True
    return baseline_fit, selected_fit, selected_features, adopted, reason


def _record_stack(monkeypatch) -> list[dict]:
    """Run the real stack and keep every region's inputs and outcome."""
    calls: list[dict] = []
    original = color_stack.fit_region_stack

    def recording(spec, selection, row_tuple, arms, residuals, **kwargs):
        # PK4.1: the ladder CONSUMES the holder (it drops the tuples no
        # arm can still select), so the oracle's copies of the inputs are
        # taken BEFORE the call — which is also the only way this test can
        # still compare against the historical arms.
        base, corrected = arms.base, arms.corrected
        result = original(
            spec, selection, row_tuple, arms, residuals, **kwargs)
        calls.append({
            "spec": spec, "selection": selection, "rows": row_tuple,
            "base": base, "corrected": corrected, "arms": arms,
            "residuals": residuals,
            "emission_masks": kwargs["emission_masks"],
            "arm_override": kwargs.get("arm_override"),
            "result": result,
        })
        return result

    monkeypatch.setattr(color_payload, "fit_region_stack", recording)
    return calls


def _fit_facts(fit) -> tuple:
    return (
        float(fit.heldout_loss),
        float(fit.word_heldout_loss),
        float(fit.dust_heldout_loss),
        int(fit.n_train),
        int(fit.n_heldout),
        tuple(fit.class_counts),
        int(fit.calibration_labels),
        tuple(fit.component_supported),
        tuple(fit.component_support_reasons),
    )


@pytest.mark.parametrize("key", FIXTURE_KEYS)
def test_region_stack_reproduces_the_historical_inline_arms(
    key: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PK3 added arm A4 above these two, so the pre-PK2 oracle is now the
    # FORCE-NULL ladder by definition (color_stack: "A0/A1 only, no head
    # ever fitted").  Setting it explicitly is the point of the escape
    # hatch — without it this pin would depend on the cmy7 fixtures
    # happening to starve A4's floors, which is an accident, not a law.
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    fixture = build_fixture(key)
    calls = _record_stack(monkeypatch)
    evidence = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    assert len(calls) == len(evidence.regions) == 1
    call = calls[0]
    result = call["result"]

    (baseline, selected, features, adopted, reason) = _historical_arms(
        call["spec"], call["selection"], call["base"], call["corrected"])

    assert result.adopted is adopted
    assert result.selected_features is features
    assert (result.selected_fit is None) == (selected is None)
    assert (result.baseline_fit is None) == (baseline is None)
    assert result.refusal_reason == ("" if selected is not None else reason)
    assert _fit_facts(result.selected_fit) == _fit_facts(selected)
    assert _fit_facts(result.baseline_fit) == _fit_facts(baseline)
    # The chosen model must not merely score the same: the evidence it
    # emits for real cells has to be bit-identical.
    probe = call["base"][0]
    assert np.array_equal(
        np.asarray(result.selected_fit.evidence(probe), np.float32),
        np.asarray(selected.evidence(probe), np.float32))
    # ...and the region really did emit through it.
    assert evidence.regions[0].accepted
    assert evidence.regions[0].registration_adopted is adopted


@pytest.mark.parametrize("key", FIXTURE_KEYS)
def test_refused_arm_passes_the_same_array_objects(
    key: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R3: a non-adopted arm is a bit-exact null, not a copy."""
    fixture = build_fixture(key)
    calls = _record_stack(monkeypatch)
    collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    call = calls[0]
    result = call["result"]
    # PK4: A3 sits above this choice and would legitimately replace the
    # feature tuple, so the R3 claim is about the A0/A1 arms only — pin
    # that these fixtures still exercise it rather than leaving that to
    # luck (they are clean channels; A3's per-window gate refuses every
    # window, measured in test_color_locality).
    assert result.window_photometry.adopted is False
    expected = call["corrected"] if result.adopted else call["base"]
    assert result.selected_features is expected
    assert all(
        got is want for got, want
        in zip(result.selected_features, expected, strict=True))


def test_the_ladder_consumes_its_feature_tuples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PK4.1 (memory): no arm tuple outlives the gate that could pick it.

    A region's feature tuples are the color path's largest transient, and
    PK4 measured what holding a third one costs: +34% peak RSS on both
    cmy8 captures (COLOR-UPLIFT-MEASUREMENTS §5.7).  The ladder therefore
    takes them as OWNED memory and clears each slot as soon as no arm can
    still select it; the caller's own references are dropped at the call
    site.  What is checkable here is the contract: the holder comes back
    empty and the survivor is the selected tuple.
    """
    fixture = build_fixture("cmy7-residual")
    calls = _record_stack(monkeypatch)
    collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    call = calls[0]
    assert call["arms"].base is None and call["arms"].corrected is None
    survivor = call["result"].selected_features
    assert survivor is (call["corrected"] if call["result"].adopted
                        else call["base"])


def test_both_gate_outcomes_stay_exercised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fixtures are only useful while they cover both verdicts."""
    outcomes = set()
    for key in FIXTURE_KEYS:
        fixture = build_fixture(key)
        calls = _record_stack(monkeypatch)
        collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec)
        outcomes.add(bool(calls[0]["result"].adopted))
    assert outcomes == {False, True}


def test_known_rows_reproduce_the_legacy_reference_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_fixture("cmy8-clean")
    calls = _record_stack(monkeypatch)
    collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec)
    rows = calls[0]["rows"]
    assert len(rows) == 9
    spec = fixture.spec
    for row in rows:
        cells = np.asarray(row.page_cells_yx, np.int64)
        known = build_known_rows(spec, 0, cells, {}, {})
        # The legacy derivation with no certificates IS the format truth.
        states, kinds = color_anchoring.color_reference_states(
            spec, 0, cells)
        assert np.array_equal(known.states, states)
        assert known.states.dtype == states.dtype
        assert np.array_equal(known.furniture_kind, kinds)
        assert known.dependency_certificate_ids == ()
        # ...and it is exactly what the window row carries.
        assert np.array_equal(row.states, known.states)
        assert np.array_equal(row.furniture_kind, known.furniture_kind)
        assert np.array_equal(row.known_component_bits, known.component_bits)
        assert np.array_equal(row.known_component_mask, known.component_mask)

        furniture = kinds >= 0
        assert np.array_equal(known.component_mask.all(axis=1), furniture)
        assert not np.any(known.component_bits[~known.component_mask])
        assert np.array_equal(known.provenance[furniture], kinds[furniture])
        assert np.all(known.provenance[~furniture] == PROVENANCE_UNKNOWN)
        assert np.array_equal(
            known.provenance == PROVENANCE_WORD, kinds == 0)
        assert np.array_equal(
            known.provenance == PROVENANCE_DUST, kinds == 1)
        assert not np.any(known.provenance == PROVENANCE_CERTIFIED)
        cells_y, cells_x = spec.layout.cells_yx
        page = 0
        assert np.array_equal(
            known.site_keys,
            page * cells_y * cells_x + cells[:, 0] * cells_x + cells[:, 1])
        assert known.site_keys.dtype == np.int64
        assert np.unique(known.site_keys).size == known.site_keys.size
        for array in (known.states, known.component_bits,
                      known.component_mask, known.provenance,
                      known.site_keys):
            assert not array.flags.writeable


def _lawful_field(n: int = 4):
    states = np.full(n, -1, np.int8)
    bits = np.zeros((n, 3), np.uint8)
    mask = np.zeros((n, 3), np.bool_)
    kinds = np.full(n, -1, np.int8)
    provenance = np.full(n, PROVENANCE_UNKNOWN, np.int8)
    certified = np.zeros(n, np.bool_)
    return states, bits, mask, kinds, provenance, certified


def test_provenance_law_refuses_a_fabricated_payload_label() -> None:
    """A payload cell may be labelled only by certificate authority."""
    states, bits, mask, kinds, provenance, certified = _lawful_field()
    mask[0, 0] = True
    bits[0, 0] = 1
    provenance[0] = PROVENANCE_CERTIFIED
    with pytest.raises(KnownFieldError, match="certificate authority"):
        known_field._validate(
            states, bits, mask, kinds, provenance, certified)
    # The same field WITH the tile's certificate authority is lawful.
    certified[0] = True
    known_field._validate(states, bits, mask, kinds, provenance, certified)


def test_provenance_law_refuses_half_known_furniture() -> None:
    states, bits, mask, kinds, provenance, certified = _lawful_field()
    kinds[1] = 0
    mask[1, :2] = True
    provenance[1] = 0
    with pytest.raises(KnownFieldError, match="partially known"):
        known_field._validate(
            states, bits, mask, kinds, provenance, certified)


def test_provenance_law_refuses_an_unattributed_label() -> None:
    states, bits, mask, kinds, provenance, certified = _lawful_field()
    mask[2] = True
    bits[2] = (1, 0, 1)
    states[2] = 5
    certified[2] = True
    with pytest.raises(KnownFieldError, match="name its authority"):
        known_field._validate(
            states, bits, mask, kinds, provenance, certified)


def test_provenance_law_refuses_a_state_without_all_components() -> None:
    states, bits, mask, kinds, provenance, certified = _lawful_field()
    states[3] = 2
    with pytest.raises(KnownFieldError, match="resolved exactly when"):
        known_field._validate(
            states, bits, mask, kinds, provenance, certified)


def test_sampling_leaf_has_exactly_one_implementation() -> None:
    """Every color raster read resolves to color_sampling itself."""
    assert color_anchoring._native_crop is color_sampling.native_crop
    assert color_anchoring._points_crop is color_sampling.points_crop
    assert color_refine._window_crop is color_sampling.window_crop
    assert color_refine._LocalCrop is color_sampling.LocalCrop
    assert color_payload.window_raw_crops is color_sampling.window_raw_crops
    assert color_payload.crop_features is color_sampling.crop_features


def test_crop_features_equals_filter_then_sample() -> None:
    fixture = build_fixture("cmy7-clean")
    patch = fixture.address.placements[0]
    pitch_px = fixture.pitch_px
    crops = color_sampling.window_raw_crops(
        fixture.raster, (patch,), pitch_px)
    crop = crops[int(patch.patch_id)]
    points = patch.segment.segment.pose.points(
        np.asarray(patch.segment.audited_cells_yx, np.float64))
    got = color_sampling.crop_features(crop, points, pitch_px, 255.0)
    filtered = color_sampling.filtered_crop(*crop, pitch_px, 255.0)
    want = color_sampling.sample(filtered.filtered, filtered, points)
    assert np.array_equal(got, want)
