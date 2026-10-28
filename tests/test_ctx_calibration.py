"""F1+PAVA: the 16-context detector option + isotonic LLR calibration in
acquire, and the F6 adaptive scan-request loop in tilemap (run 014.2).

Discriminating pair for ctx: context-FREE (i.i.d.) cell flips must not
regress vs the global detector (per-context stats == global stats), while
context-STRUCTURED damage (closure of surrounded whites + erosion of
isolated ink — the measured c2 mechanism) must improve materially.
Calibration: PAVA map monotone + calibrated-LLR reliability (predicted
P(correct) tracks empirical) on the structured page.

Runs under pytest, or standalone: env/bin/python tests/test_ctx_calibration.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scipy.ndimage import convolve  # noqa: E402

from paperholo import acquire, compose, tilemap  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

SEED = b"paper-store/test-ctx-cal"

_cache: dict = {}


def _page():
    if "page" not in _cache:
        spec = compose.ComposeSpec(layout_version=3,
                                   pilot=PilotLayout(version=3),
                                   page_cells_yx=(240, 240))
        payload = rng(SEED, b"payload").integers(
            0, 2, compose.payload_capacity(spec), dtype=np.uint8)
        cp = compose.compose_page(payload, spec, SEED)
        _cache["page"] = (spec, cp)
    return _cache["page"]


def _img_from_refl(refl_cells: np.ndarray, r) -> np.ndarray:
    """Float cell reflectances -> 2 px/dot image (+ mild sensor noise so
    the per-context GMMs have finite sigmas, as on real scans)."""
    img = np.kron(refl_cells, np.ones((6, 6)))
    return np.clip(img + r.normal(0, 0.02, img.shape), 0.0, 1.0)


def _structured_damage(cells: np.ndarray, r) -> np.ndarray:
    """The MEASURED c2 mechanism, synthesized faithfully: development is a
    context-conditional CONTINUUM shift (014.2 patch data — whites in inky
    neighbourhoods read progressively darker, inks in white neighbourhoods
    progressively paler), so whole per-context class populations MOVE and
    the extreme contexts cross a single global threshold. This is the shift
    structure the per-context GMM is built to capture. Two earlier drafts
    of this test are instructive negatives, kept on the record: (a) binary
    flips carry NO residual signal — no detector can fix them; (b) damage
    that teleports a SUBSET of a class to a fixed intermediate level makes
    the class bimodal, and the pinned-weight 2-GMM absorbs the shifted
    subset into the other component (measured here: boundary z=0.016,
    nothing recovered) — the GMM models shifts, not within-class splits.
    Terminal real-channel closures are exactly that unrecoverable subset.
    Returns float cell reflectances."""
    k8 = np.ones((3, 3), int)
    k8[1, 1] = 0
    inknbr = convolve((cells == 1).astype(int), k8, mode="constant")
    refl = np.where(cells == 1,
                    0.08 * (8 - inknbr),          # ink pales when isolated
                    1.0 - 0.08 * inknbr)          # white darkens when boxed
    refl = refl + r.normal(0, 0.04, cells.shape)
    return np.clip(refl, 0.0, 1.0)


def test_ctx_pair_free_vs_structured() -> None:
    spec, cp = _page()
    gt = compose.extract_payload(cp.cell_values, spec, SEED, 0)

    def ber(img, detector):
        res = acquire.acquire_and_decode(img, spec, SEED,
                                         detector=detector)
        assert res.ok, res.diagnostics
        return float(np.mean(res.payload_bits
                             != gt[res.payload_cell_index]))

    # context-FREE flips: ctx must not regress (tolerance one detection jot)
    r = rng(SEED, b"iid")
    free = cp.cell_values ^ (r.random(cp.cell_values.shape)
                             < 0.08).astype(np.uint8)
    img_free = _img_from_refl((1.0 - free).astype(np.float64),
                              rng(SEED, b"n1"))
    b_g, b_c = ber(img_free, "global"), ber(img_free, "ctx")
    assert abs(b_c - b_g) < 0.01, (b_g, b_c)
    # context-STRUCTURED damage at intermediate reflectance: ctx must
    # improve materially
    refl = _structured_damage(cp.cell_values, rng(SEED, b"struct"))
    img_s = _img_from_refl(refl, rng(SEED, b"n2"))
    s_g, s_c = ber(img_s, "global"), ber(img_s, "ctx")
    assert s_c < 0.7 * s_g, (s_g, s_c)
    print(f"  iid flips: global {100*b_g:.2f}% ctx {100*b_c:.2f}% (parity); "
          f"structured: global {100*s_g:.2f}% -> ctx {100*s_c:.2f}%")


def test_pava_unit_and_reliability() -> None:
    # unit: PAVA on noisy monotone data is monotone + within tolerance
    r = rng(SEED, b"pava")
    s = np.sort(r.normal(0, 2, 4000))
    p_true = 1.0 / (1.0 + np.exp(-s))
    y = (r.random(4000) < p_true).astype(float)
    ns, np_ = acquire.pava_calibrate(s, y)
    assert np.all(np.diff(np_) >= -1e-12), "PAVA map not monotone"
    pred = np.interp(s, ns, np_)
    assert float(np.mean(np.abs(pred - p_true))) < 0.05
    # end-to-end reliability on the structured page: calibrated LLRs must
    # track empirical accuracy within a loose band per confidence bin
    spec, cp = _page()
    gt = compose.extract_payload(cp.cell_values, spec, SEED, 0)
    refl2 = _structured_damage(cp.cell_values, rng(SEED, b"struct2"))
    res = acquire.acquire_and_decode(_img_from_refl(refl2, rng(SEED, b"n3")),
                                     spec, SEED,
                                     detector="ctx", calibrate=True)
    assert res.ok and res.diagnostics.get("calibrated"), res.diagnostics
    llr = res.payload_llr
    correct = (res.payload_bits == gt[res.payload_cell_index])
    worst = 0.0
    for lo, hi in ((0.5, 1.5), (1.5, 3.0), (3.0, 6.0)):
        m = (np.abs(llr) >= lo) & (np.abs(llr) < hi)
        if m.sum() < 300:
            continue
        p_pred = float(np.mean(1.0 / (1.0 + np.exp(-np.abs(llr[m])))))
        p_emp = float(np.mean(correct[m]))
        worst = max(worst, abs(p_pred - p_emp))
    assert worst < 0.15, f"calibration off by {worst:.3f}"
    print(f"  PAVA monotone + reliable (worst bin gap {worst:.3f}, "
          f"labels {res.diagnostics['n_cal_labels']})")


def test_more_scans_useful_loop() -> None:
    """The F6 controller: asks for scans while they help, stops on full
    certification, stops on diminishing returns."""
    spec, cp = _page()
    pds = tilemap.PageDecodeState(spec, SEED, page=0)
    # synthetic observations: scan1 covers half the page weakly, scan2 the
    # rest, scan3 duplicates scan2 (no gain)
    cap = compose.payload_capacity(spec)
    half = cap // 2
    r = rng(SEED, b"ctrl")
    gt_llr = np.where(r.random(cap) < 0.5, -4.0, 4.0)

    def obs(sid, idx, scale):
        pds.scans[sid] = tilemap.ScanObservation(
            scan_id=sid, payload_cell_index=idx,
            payload_llr=gt_llr[idx] * scale,
            tile_words={(0, 0): 1}, n_windows=1)
        pds.note_scan_added()

    obs("s1", np.arange(0, half, dtype=np.int64), 0.3)   # weak half-coverage
    ok, why = pds.more_scans_useful()
    assert ok, why                        # only one scan -> ask for more
    obs("s2", np.arange(half, cap, dtype=np.int64), 1.0)
    ok, why = pds.more_scans_useful()
    assert ok, why                        # big coverage gain -> more
    obs("s3", np.arange(half, cap, dtype=np.int64), 1.0)
    ok, why = pds.more_scans_useful()
    assert not ok and "diminishing" in why, why
    # full certification always stops
    for st in pds.tiles.values():
        st.status = "certified"
    ok, why = pds.more_scans_useful()
    assert not ok and "certified" in why
    print(f"  controller: ask/ask/stop(diminishing)/stop(done) — correct")


if __name__ == "__main__":
    for fn in (test_ctx_pair_free_vs_structured,
               test_pava_unit_and_reliability,
               test_more_scans_useful_loop):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
