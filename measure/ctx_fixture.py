from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from holo3.plugins.color_model import (
    Cmy8Detector,
    QdaModel,
    fit_cmy8_detector,
    fit_qda,
)
from holo3.plugins.color_region_ctx import ContextConfig, Population


@dataclass(frozen=True)
class RegionFixture:
    model: QdaModel
    detector: Cmy8Detector | None
    known_features: np.ndarray
    known_bins: np.ndarray
    states: np.ndarray
    kinds: np.ndarray
    search: np.ndarray
    config: ContextConfig


def _features(rng: np.random.Generator, states: np.ndarray,
              n_states: int, n_features: int,
              separation: float) -> np.ndarray:
    centres = rng.normal(0.0, separation, (n_states, n_features))
    noise = rng.normal(0.0, 1.0, (states.size, n_features))
    return centres[states] + noise


def make_region_fixture(n_labels: int, n_states: int, seed: int = 20260829,
                        separation: float = 1.1,
                        n_features: int = 6,
                        dead_fraction: float = 0.05) -> RegionFixture:
    rng = np.random.default_rng(seed)
    weights = rng.uniform(0.6, 1.4, n_states)
    weights /= weights.sum()
    states = rng.choice(n_states, size=n_labels, p=weights).astype(np.int64)
    features = _features(rng, states, n_states, n_features, separation)
    bins = np.empty((n_labels, 3), np.int8)
    for plane in range(3):
        draw = rng.binomial(8, 0.25 + 0.08 * plane, n_labels)
        dead = rng.random(n_labels) < dead_fraction
        bins[:, plane] = np.where(dead, np.int8(-1), draw.astype(np.int8))
    kinds = (rng.random(n_labels) < 0.35).astype(np.int8)
    search = rng.random(n_labels) < 0.5
    detector: Cmy8Detector | None = None
    if n_states == 8:
        half = n_labels // 2
        detector = fit_cmy8_detector(
            features[:half], states[:half],
            features[half:], states[half:])
        model = detector.qda
    else:
        model = fit_qda(features, states, n_states)
    return RegionFixture(
        model=model,
        detector=detector,
        known_features=features,
        known_bins=bins,
        states=states,
        kinds=kinds,
        search=search,
        config=ContextConfig(),
    )


def make_populations(fixture: RegionFixture) -> tuple[Population,
                                                      Population]:
    from holo3.plugins.color_model import qda_log_scores
    from holo3.plugins.color_region_ctx import augment

    cmy8 = fixture.detector is not None
    scores = qda_log_scores(fixture.model, fixture.known_features)
    if not cmy8:
        scores = augment(scores[:, 1:] - scores[:, :1])
    search = fixture.search
    heldout = ~search
    return (
        Population(scores[search], fixture.states[search],
                    fixture.known_bins[search], fixture.kinds[search]),
        Population(scores[heldout], fixture.states[heldout],
                    fixture.known_bins[heldout], fixture.kinds[heldout]),
    )
