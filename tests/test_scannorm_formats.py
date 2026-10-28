"""acquire-v2 front end: scan normalization + blind format identification.

Covers the decoder-axis generalization (2026-07-09): arbitrary-resolution
input (px/cell ladder incl. harmonic disambiguation on oversampled scans and
refusal below the floor), RGB reduction, and FormatDescriptor hypothesis
testing — including the FIRST blind c2 acquisition (the e014 receiver leg;
the printed format needed none of the M-P6 machinery, per PILOTS-DESIGN
§13.1 word-tail numbers).

Zero-channel images except the one geometry=True c2 point (the honest new
territory). Runs under pytest, or standalone:
env/bin/python tests/test_scannorm_formats.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import compose, formats, scannorm  # noqa: E402
from paperholo.channel import ChannelParams, print_scan  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

SEED = b"paper-store/test-scannorm"

_cache: dict = {}


def _page(encoding_id: str) -> tuple[compose.ComposeSpec,
                                     compose.ComposedPage]:
    key = f"page-{encoding_id}"
    if key not in _cache:
        spec = compose.ComposeSpec(layout_version=3,
                                   encoding_id=encoding_id,
                                   pilot=PilotLayout(version=3),
                                   page_cells_yx=(240, 240))
        payload = rng(SEED, f"payload-{encoding_id}".encode()).integers(
            0, 2, compose.payload_capacity(spec), dtype=np.uint8)
        _cache[key] = (spec, compose.compose_page(payload, spec, SEED))
    return _cache[key]


def _emul(refl: np.ndarray, num: int, den: int) -> np.ndarray:
    """Emulate px/dot = num/den from a 1 px/dot bitmap: np.repeat (exact
    aperture) then box means (exact aperture) — the sound options per the
    acquire-v2 sim read; no spline anywhere."""
    img = np.repeat(np.repeat(refl, num, 0), num, 1) if num > 1 else refl
    if den > 1:
        h = (img.shape[0] // den) * den
        w = (img.shape[1] // den) * den
        img = img[:h, :w].reshape(h // den, den, w // den, den).mean((1, 3))
    return img


def _candidates() -> list[formats.FormatDescriptor]:
    """Registry rows reshaped to the 240-cell test pages."""
    return [formats.FormatDescriptor(f.format_id, SEED, f.layout_version,
                                     f.encoding_id, (240, 240), f.plane,
                                     dust=f.dust)
            for f in formats.FORMAT_REGISTRY]


def test_pitch_ladder_and_refusal() -> None:
    """Pitch measurement across the ladder: fundamentals found through the
    harmonic forest on oversampled scans; sub-floor input refused. (The
    3rd harmonic OUT-CONTRASTS the fundamental at 24 px/cell — measured
    435 vs 110 during the build — so this guards the integer-ratio
    selection rule, not just happy paths.)"""
    _, cp = _page("kcell-c3")
    refl = (1.0 - cp.plane_bits).astype(np.float64)
    for num, den, want in ((1, 1, 3.0), (3, 2, 4.5), (2, 1, 6.0),
                           (4, 1, 12.0), (8, 1, 24.0)):
        pm = scannorm.measure_cell_pitch(_emul(refl, num, den))
        assert abs(pm.pitch_px / want - 1.0) < 0.02, \
            f"{num}/{den}: measured {pm.pitch_px} want {want}"
        ns = scannorm.normalize_to_canonical(_emul(refl, num, den),
                                             pm.pitch_px, 3)
        err = min(abs(ns.cell_px_est / t - 1.0)
                  for t in scannorm.CANONICAL_CELL_PX)
        assert err <= scannorm.CAPTURE_BAND, (want, ns.cell_px_est)
        assert ns.marginal == (want < 4.0)
    # 1.5 px/cell (a 300 dpi scan of a 600 dpi c3 print) must refuse
    try:
        scannorm.measure_cell_pitch(_emul(refl, 1, 2))
        raise AssertionError("1.5 px/cell was not refused")
    except scannorm.ScanRefused:
        pass
    print("  pitch ladder 3/4.5/6/12/24 px/cell exact; 1.5 refused")


def test_reduce_plane_rgb_and_16bit() -> None:
    """RGB + 16-bit inputs reduce to the 2-D footing; K = luma."""
    _, cp = _page("kcell-c3")
    refl = (1.0 - cp.plane_bits).astype(np.float64)
    rgb8 = np.repeat((refl[..., None] * 255).astype(np.uint8), 3, axis=2)
    grey16 = (refl * 65535).astype(np.uint16)
    for arr in (rgb8, grey16):
        out = scannorm.reduce_plane(arr, "K")
        assert out.ndim == 2 and out.dtype == np.float64
        assert 0.0 <= out.min() and out.max() <= 1.0
    # channel selection: C hypothesis takes R
    rgb8[..., 0] = 0
    assert float(scannorm.reduce_plane(rgb8, "C").max()) == 0.0
    print("  RGB/16-bit reduction + plane channel selection ok")


def test_blind_format_identification_c3_and_c2() -> None:
    """The registry identifies BOTH printed formats blind — including the
    first blind c2 acquisition — at two resolutions each, with payload
    byte-exact on clean images and no cross-format false accepts."""
    cands = _candidates()
    for encoding_id, fid in (("kcell-c3", "e012-v3-c3"),
                             ("kcell-c2", "e014-v3-c2")):
        spec, cp = _page(encoding_id)
        refl = (1.0 - cp.plane_bits).astype(np.float64)
        gt = compose.extract_payload(cp.cell_values, spec, SEED, 0)
        for ppd in (2, 4):
            r = formats.acquire_scan(_emul(refl, ppd, 1), candidates=cands,
                                     scan_dpi=600.0 * ppd)
            assert r.ok, (encoding_id, ppd, r.tried, r.diagnostics)
            assert r.fmt.format_id == fid
            idx = r.result.payload_cell_index
            ber = float(np.mean(r.result.payload_bits != gt[idx]))
            assert ber == 0.0, f"{fid}@{ppd}px/dot BER {ber}"
            assert r.geometry_confirmed
        # NO-dpi path (review finding: the true pitch must not be evicted
        # by low-pitch harmonic hypotheses when scan_dpi is unknown).
        # Registry doctrine modeled honestly: DISTINCT seeds per row — the
        # scramble is pitch-blind, so same-seed rows differing only in
        # cell_dots are cell-domain identical and CANNOT be told apart
        # without absolute pitch (they decode the same payload either way).
        cands_nodpi = [formats.FormatDescriptor(
            f.format_id,
            SEED if f.format_id == fid else b"other/" + f.format_id.encode(),
            f.layout_version, f.encoding_id, (240, 240), f.plane,
            dust=f.dust)
            for f in formats.FORMAT_REGISTRY]
        r = formats.acquire_scan(_emul(refl, 4, 1), candidates=cands_nodpi)
        assert r.ok and r.fmt.format_id == fid, (fid, r.tried)
    print("  blind identification c3+c2 at 2/4 px/dot (+no-dpi), "
          "payload exact")


def test_blind_c2_at_word_budget() -> None:
    """The receiver leg of the e014 deferral, at the FORMAT'S OWN error
    budget: a c2 page with 8% i.i.d. cell flips (PILOTS-DESIGN 13.1's
    c2-ctx worst-day rate, word tail 2.8% at t=13) must blind-identify and
    decode. This is what 'plain t=13 c2 words need no duplication on a
    good channel' means in executable form."""
    spec, cp = _page("kcell-c2")
    gt = compose.extract_payload(cp.cell_values, spec, SEED, 0)
    flips = rng(SEED, b"c2-flips").random(cp.cell_values.shape) < 0.08
    cells = cp.cell_values ^ flips.astype(np.uint8)
    dots = np.kron(cells, np.ones((2, 2), np.uint8))
    img = _emul((1.0 - dots).astype(np.float64), 4, 1)   # 8 px/cell native
    r = formats.acquire_scan(img, candidates=_candidates(),
                             scan_dpi=2400.0)
    assert r.ok, (r.tried, r.diagnostics)
    assert r.fmt.format_id == "e014-v3-c2"
    idx = r.result.payload_cell_index
    ber = float(np.mean(r.result.payload_bits != gt[idx]))
    null = float(np.mean(r.result.payload_bits
                         != gt[(idx + 7919) % gt.size]))
    assert 0.05 < ber < 0.11 and abs(null - 0.5) < 0.03, (ber, null)
    print(f"  blind c2 at 8% budget: BER {100*ber:.2f}% null {null:.3f} "
          f"tiles {r.result.n_tiles_decoded}/{r.result.n_tiles_attempted} "
          f"werr {r.result.n_word_errors_corrected}")


def test_blind_c2_sim_channel_fails_clean() -> None:
    """The measured simulator's c2 regime sits ABOVE the word budget
    (~26% blind detection at 8 px/cell — the known-pessimistic white-
    closure floor, sim 15.0% vs hardware 11.1% genie, M0 TODO): blind
    acquisition must fail CLEANLY (all formats rejected, zero false
    accepts), not mis-certify. The hardware verdict for blind c2 belongs
    to the e014 sheet's Canon scan, where the channel is measured kinder
    than the sim."""
    _, cp = _page("kcell-c2")
    from dataclasses import replace as dc_replace
    p = ChannelParams(seed=77, scan_seed=78, geometry=True)
    p = dc_replace(p, scanner=dc_replace(p.scanner, oversample=4))
    scan = print_scan(cp.plane_bits, p)
    r = formats.acquire_scan(scan, candidates=_candidates(),
                             scan_dpi=2400.0)
    assert not r.ok
    # either clean-failure signature is correct: "pitch" (no credible
    # lattice line above the contrast floor) or "all_formats_rejected"
    # (lines found, every BCH-gated hypothesis rejected) — which one fires
    # is borderline on this heavily-degraded channel; false accepts never.
    assert r.diagnostics["failed_stage"] in ("pitch",
                                             "all_formats_rejected"), \
        r.diagnostics
    print(f"  sim-c2 closure floor: clean rejection at "
          f"{r.diagnostics['failed_stage']} ({len(r.tried)} tried, "
          f"0 false accepts)")


def test_wrong_seed_rejects_all_formats() -> None:
    """Negative control: right pitch, wrong seed -> every hypothesis
    cleanly rejected (the 0/200k FA word gate)."""
    _, cp = _page("kcell-c3")
    refl = (1.0 - cp.plane_bits).astype(np.float64)
    r = formats.acquire_scan(_emul(refl, 2, 1), candidates=_candidates(),
                             seed=b"paper-store/WRONG", scan_dpi=1200.0)
    assert not r.ok
    assert r.diagnostics["failed_stage"] == "all_formats_rejected"
    print(f"  wrong seed: all formats rejected ({len(r.tried)} tried)")


if __name__ == "__main__":
    for fn in (test_pitch_ladder_and_refusal,
               test_reduce_plane_rgb_and_16bit,
               test_blind_format_identification_c3_and_c2,
               test_blind_c2_at_word_budget,
               test_blind_c2_sim_channel_fails_clean,
               test_wrong_seed_rejects_all_formats):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
