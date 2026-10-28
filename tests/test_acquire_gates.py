"""Receiver hardening gates (2026-07-09 e012 scan-forensics items; trace in
scratch/wf/reader-acquire.json):

1. anchor_rounds=0 must truly SKIP the anchor stage (diagnostic/negative-
   control hook) — pre-fix, `range(max(anchor_rounds, 1))` made 0 behave as
   1 and the stage could not be disabled. When it runs, round index 0 always
   uses the wide 8 px one-cell slip hunt (documented, unchanged).
2. Post-fold certification gate: Stage-B acceptance certifies addressing on
   the PRE-fold detection; a bad slip/anchor fold could silently re-address
   the grid afterwards and return ok=True with ~50% payload BER. The full-
   strength post-fold word decode must VETO: a fold that collapses visible-
   tile decodes below half fails the acquisition with
   failed_stage="post_fold_words" instead of emitting payload.

Zero-channel clean images (2 px/dot np.repeat of the composed plane) — the
only failure source in the mis-fold test is the injected fold.

Runs under pytest, or standalone: env/bin/python tests/test_acquire_gates.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import acquire, compose  # noqa: E402
from paperholo.modulation import rng  # noqa: E402

SEED = b"paper-store/test-acquire-gates"

_cache: dict = {}


def _clean_frag() -> tuple[compose.ComposeSpec, compose.ComposedPage,
                           np.ndarray]:
    """240-cell page, zero-channel 2 px/dot image, 480-dot crop at dot
    (90, 90) = cells 30..190 (full tiles (1,1)/(1,2)/(2,1)/(2,2) visible)."""
    if "frag" not in _cache:
        spec = compose.ComposeSpec(page_cells_yx=(240, 240))
        payload = rng(SEED, b"payload").integers(
            0, 2, compose.payload_capacity(spec), dtype=np.uint8)
        composed = compose.compose_page(payload, spec, SEED)
        refl = (1.0 - composed.plane_bits).astype(np.float32)
        img = np.repeat(np.repeat(refl, 2, 0), 2, 1)      # 2 px/dot
        frag = np.ascontiguousarray(img[180:1140, 180:1140])  # 480 dots sq
        _cache["frag"] = (spec, composed, frag)
    return _cache["frag"]


def _ber(res: acquire.AcquireResult, composed: compose.ComposedPage) -> float:
    assert res.payload_bits is not None
    return float(np.mean(
        res.payload_bits != composed.payload_bits[res.payload_cell_index]))


def test_anchor_rounds_zero_skips_anchor_stage() -> None:
    """anchor_rounds=0 = no anchor measurement, no fold, no lock-rate diag;
    the clean fragment must still acquire and read payload at ~0 BER (the
    slip-vote integer fold and everything upstream are unaffected)."""
    spec, composed, frag = _clean_frag()
    res = acquire.acquire_and_decode(frag, spec, SEED, anchor_rounds=0)
    assert res.ok, f"anchor_rounds=0 failed ({res.diagnostics})"
    assert res.diagnostics["anchor_rounds_run"] == 0
    assert "anchor_lock_rate" not in res.diagnostics
    assert res.anchors is None
    ber = _ber(res, composed)
    assert ber < 0.01, f"clean anchor-less BER {ber:.4f}"
    # rounds >= 1 keep the historical behavior: anchors measured + recorded
    res1 = acquire.acquire_and_decode(frag, spec, SEED, anchor_rounds=1)
    assert res1.ok
    assert res1.diagnostics["anchor_rounds_run"] == 1
    assert res1.anchors is not None
    assert "anchor_lock_rate" in res1.diagnostics
    assert _ber(res1, composed) < 0.01
    print(f"  anchor_rounds=0 skipped cleanly (BER {100 * ber:.2f}%), "
          f"rounds=1 unchanged")


def test_post_fold_gate_catches_one_cell_misfold() -> None:
    """Inject a global +1-cell (+3 dot) anchor warp — the mis-fold class the
    2026-07-09 forensics showed would return ok=True with ~50% payload BER
    and perfect-looking PRE-fold acceptance. The post-fold word gate must
    veto it (no payload emitted), not return it."""
    spec, composed, frag = _clean_frag()

    def bad_field(anchors: dict, shape_cells: tuple[int, int]):
        def warp(y_cells: np.ndarray, x_cells: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray]:
            y = np.asarray(y_cells, np.float64)
            x = np.asarray(x_cells, np.float64)
            return (np.full(y.shape, 3.0), np.zeros(x.shape))  # dots
        return warp

    orig = acquire.anchor_warp_field
    acquire.anchor_warp_field = bad_field
    try:
        res = acquire.acquire_and_decode(frag, spec, SEED, anchor_rounds=1)
    finally:
        acquire.anchor_warp_field = orig
    assert not res.ok, "one-cell mis-fold returned ok=True (gate missing)"
    assert res.diagnostics["failed_stage"] == "post_fold_words"
    assert res.payload_bits is None
    att = res.diagnostics["post_fold_tiles_attempted"]
    dec = res.diagnostics["post_fold_tiles_decoded"]
    assert att > 0 and 2 * dec < att
    print(f"  mis-fold vetoed: post-fold tiles {dec}/{att}, "
          f"failed_stage=post_fold_words")
    # control: the un-patched path on the same fragment stays healthy
    res_ok = acquire.acquire_and_decode(frag, spec, SEED, anchor_rounds=1)
    assert res_ok.ok and res_ok.n_tiles_decoded == res_ok.n_tiles_attempted


def test_ber_aware_gate_passes_noisy_correct_page() -> None:
    """The BER-aware post-fold gate (acquire-v2, 014.1 c2 motivation): a
    correctly-addressed page at a high-but-real BER, where pilot tiles start
    failing, must NOT be vetoed. Inject ~12% i.i.d. cell flips: acquisition
    stays ok and payload BER tracks the injected channel (the gate does not
    over-fire). NOTE the gate's prediction floor and the fixed-0.5 bar
    coincide until word failure exceeds 50% (cell BER > ~13.5%); the
    difference bites on LARGER real windows with spatial BER variance
    (Stage-A locks a clean sub-region while distant tiles fail) — the 40 mm
    c2 window regime, not a 4-tile synthetic. Here the gate simply must not
    veto a legitimately noisy page, and the c3-side floor is identical."""
    spec, composed, _ = _clean_frag()
    payload = rng(SEED, b"payload").integers(
        0, 2, compose.payload_capacity(spec), dtype=np.uint8)
    cp = compose.compose_page(payload, spec, SEED)
    flips = rng(SEED, b"noisy-flips").random(cp.cell_values.shape) < 0.12
    cells = cp.cell_values ^ flips.astype(np.uint8)
    dots = np.kron(cells, np.ones((3, 3), np.uint8))
    img = np.repeat(np.repeat((1.0 - dots).astype(np.float32), 2, 0), 2, 1)
    frag = np.ascontiguousarray(img[180:1140, 180:1140])
    res = acquire.acquire_and_decode(frag, spec, SEED)
    assert res.ok, f"noisy-correct page vetoed ({res.diagnostics})"
    gt = compose.extract_payload(cp.cell_values, spec, SEED, 0)
    ber = float(np.mean(res.payload_bits != gt[res.payload_cell_index]))
    assert 0.05 < ber < 0.20, ber            # tracks the injected channel
    print(f"  BER-aware gate passes noisy-correct page: payload BER "
          f"{100*ber:.1f}%, tiles {res.n_tiles_decoded}/"
          f"{res.n_tiles_attempted}")


if __name__ == "__main__":
    for fn in (test_anchor_rounds_zero_skips_anchor_stage,
               test_post_fold_gate_catches_one_cell_misfold,
               test_ber_aware_gate_passes_noisy_correct_page):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
