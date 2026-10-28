"""P1 Stage-A/B word-bit rule on color pages (COLOR-DESIGN D3 /
PILOTS-DESIGN §16.4): the pinned-0.5/0.5 2-GMM is fit on the GATHERED
WORD-SITE population (50/50 W/CM by keystream construction), never on all
window cells — P1 measured the all-cells fit at up to 2x word BER on
mostly-ink pages.

SIM-FREE by contract (the test_color_receiver convention): the window is a
LUMA map over compose cell_values — W is the only light state and the 7 ink
states form a BIMODAL pack with CM in its light cluster, so the all-cells
2-GMM locks onto the pack's internal valley ABOVE CM (measured here: ~22%
word-site BER, CM reads "white") while the site fit recovers the oracle
threshold (~0%). This is the constructed twin of P1's measured hazard; a
unimodal ink pack does NOT trip the all-cells fit (the pinned weights fix
the PRIOR, not the mass split — EM still locks onto a separated 12.5% white
cluster), which is why the clean-channel gates passed before the rule was
wired.

Covers:
- payoff: site-fit stage A decodes every window at n_err=0 where the
  all-cells bits scrape at best one window near the t=13 edge;
- FA structure preserved: wrong seed and every rot90 orientation stay clean
  rejects through stage A+B with z_grid; wrong-PHASE site populations
  descramble to ~coin-flip bits;
- e2e: acquire_and_decode on the rendered luma window (grey scan of a color
  page, rgb=None) acquires with diagnostics["word_detector"]="site_fit",
  exact origin, all post-fold words; wrong seed fails cleanly;
- guard: mismatched z_grid shape refused.

K-path byte-identity is proven suite-wide (frozen v2/v3 goldens +
e011/e012/e014/e016 regressions): K specs never construct a z_grid.

Runs under pytest, or standalone: env/bin/python tests/test_color_sitefit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paperholo import acquire, compose, dust, pilots  # noqa: E402
from paperholo.modulation import rng  # noqa: E402

SEED = b"paper-store/test-color-sitefit"
DUST = dust.DustLayout(sites_per_tile=24, pure_quota=3)
# reflectance per state s = C + 2M + 4Y (the dust state convention):
# W alone in the light mode; ink pack bimodal {C,M,Y,CM | CY,MY,CMY} with
# CM (s=3, the word ink state) inside the LIGHT ink cluster
REFL = np.array([1.00,   # 0 W
                 0.62,   # 1 C
                 0.60,   # 2 M
                 0.56,   # 3 CM  <- word bit=1 state
                 0.58,   # 4 Y
                 0.30,   # 5 CY
                 0.28,   # 6 MY
                 0.25])  # 7 CMY
CELL_SIGMA = 0.05        # per-cell mottle on the luma map
OFF = (37, 58)           # window origin in page cells (pure-cells idiom)
WIN = 150                # window size, cells (>= 2 pilot tiles + phases)
PERIOD = 60

_cache: dict = {}


def _page() -> tuple:
    """(spec, s_idx, refl, mask): a 240-cell v4 page, its per-cell state
    index, the noisy mostly-ink luma map, and the pilot-site mask."""
    if "page" not in _cache:
        spec = compose.ComposeSpec(
            layout_version=4, encoding_id="cmy8-c3", plane="CMY",
            pilot=pilots.PilotLayout(version=4), page_cells_yx=(240, 240),
            dust=DUST)
        cap = compose.payload_capacity(spec)
        g = rng(SEED, b"payload")
        payload = [g.integers(0, 2, cap, dtype=np.uint8) for _ in range(3)]
        cp = compose.compose_page(payload, spec, SEED, page=0)
        s_idx = (cp.cell_values[0] + 2 * cp.cell_values[1]
                 + 4 * cp.cell_values[2]).astype(np.int64)
        gn = rng(SEED, b"cell-noise")
        refl = REFL[s_idx] + gn.standard_normal(s_idx.shape) * CELL_SIGMA
        mask = compose._pilot_site_mask((240, 240), spec.pilot, SEED)
        _cache["page"] = (spec, s_idx, refl, mask)
    return _cache["page"]


def _window() -> tuple:
    """(spec, means, z, hard_allcells, site_mask, truth_bits) for the
    OFF/WIN crop."""
    if "win" not in _cache:
        spec, s_idx, refl, mask = _page()
        sl = np.s_[OFF[0]:OFF[0] + WIN, OFF[1]:OFF[1] + WIN]
        means = refl[sl]
        m_win = mask[sl]
        truth = (s_idx[sl][m_win] == 3).astype(np.uint8)   # bit=1 -> CM
        hard_ac, _ = acquire.cell_bits_blind(means)
        z = acquire._z_normalize(means)
        _cache["win"] = (spec, means, z, hard_ac, m_win, truth)
    return _cache["win"]


def test_mostly_ink_payoff() -> None:
    """Site fit ~oracle where the all-cells fit mis-thresholds (P1)."""
    spec, means, z, hard_ac, m_win, truth = _window()
    ber_ac = float((hard_ac[m_win] != truth).mean())
    sites = np.argwhere(m_win)
    hard_sf, _ = acquire._site_fit_cell_bits(means, sites)
    ber_sf = float((hard_sf[m_win] != truth).mean())
    assert ber_ac > 0.10, f"construction lost its bite: all-cells {ber_ac:.3f}"
    assert ber_sf < 0.02, f"site fit off oracle: {ber_sf:.3f}"
    assert ber_ac > 2.0 * max(ber_sf, 0.02), (ber_ac, ber_sf)

    # stage A/B: site-fit words decode clean in EVERY window at the exact
    # injected origin; the all-cells bits at best scrape the t=13 edge
    cands_sf = acquire.stage_a(hard_ac, spec.pilot, SEED, "K",
                               page_tiles_yx=(4, 4), z_grid=z)
    assert len(cands_sf) >= 4, f"only {len(cands_sf)} site-fit candidates"
    n_acc = 0
    for c in cands_sf:
        assert c["n_err"] <= 2, c["n_err"]
        oy = c["message"]["ptile_y"] * PERIOD - c["tile_window_origin"][0]
        ox = c["message"]["ptile_x"] * PERIOD - c["tile_window_origin"][1]
        assert (oy, ox) == OFF, f"origin ({oy},{ox}) != {OFF}"
        if acquire.stage_b(c, hard_ac, spec.pilot, SEED, "K",
                           page_tiles_yx=(4, 4), z_grid=z) is not None:
            n_acc += 1
    assert n_acc == len(cands_sf)

    cands_ac = acquire.stage_a(hard_ac, spec.pilot, SEED, "K",
                               page_tiles_yx=(4, 4))
    assert len(cands_ac) < len(cands_sf)
    assert all(c["n_err"] >= 8 for c in cands_ac), \
        [c["n_err"] for c in cands_ac]
    print(f"  payoff: word-site BER all-cells {ber_ac:.3f} vs site-fit "
          f"{ber_sf:.3f}; stage A {len(cands_sf)}x n_err<=2 (site) vs "
          f"{len(cands_ac)} candidates n_err>=8 (all-cells)")


def test_wrong_hypothesis_clean_reject() -> None:
    """FA structure preserved under per-hypothesis site fits: a wrong seed
    or orientation gathers ~uniform page cells whose 2-GMM bits descramble
    to ~coin flips -> BCH rejects; nothing may accept."""
    spec, means, z, hard_ac, m_win, truth = _window()
    bad = acquire.stage_a(hard_ac, spec.pilot, b"not-the-seed", "K",
                          page_tiles_yx=(4, 4), z_grid=z)
    assert bad == [], f"{len(bad)} wrong-seed candidates"
    for k in (1, 2, 3):
        zr = np.ascontiguousarray(np.rot90(z, k))
        hr = np.ascontiguousarray(np.rot90(hard_ac, k))
        cands = acquire.stage_a(hr, spec.pilot, SEED, "K",
                                page_tiles_yx=(4, 4), z_grid=zr)
        for c in cands:  # any BCH fluke must die in Stage B
            assert acquire.stage_b(c, hr, spec.pilot, SEED, "K",
                                   page_tiles_yx=(4, 4), z_grid=zr) is None
    # wrong-PHASE populations: descrambled site-fit bits are ~coin flips
    pos = pilots.site_positions_tile(spec.pilot, SEED)
    vals, ry, rx = acquire._gather_site_vals(z, (0, 0), pos, PERIOD)
    words = acquire._site_fit_words(vals)
    ksp = pilots.value_keystream_tile(spec.pilot, SEED, "K")
    desc = np.bitwise_xor(words, ksp)
    true_ry = (PERIOD - OFF[0] % PERIOD) % PERIOD
    true_rx = (PERIOD - OFF[1] % PERIOD) % PERIOD
    wrong = ~((ry == true_ry) & (rx == true_rx))
    bal = float(desc[wrong].mean())
    assert abs(bal - 0.5) < 0.05, bal
    print(f"  clean rejects: wrong seed 0 candidates, rot90 x3 no "
          f"acceptance; wrong-phase balance {bal:.3f} "
          f"({int(wrong.sum())} hypotheses)")


def test_e2e_luma_window_site_fit() -> None:
    """Full blind acquire on the rendered mostly-ink luma window (grey scan
    of a color page): the site fit carries Stage A/B AND the post-fold word
    certification; payload stays pending without rgb."""
    spec, s_idx, refl, mask = _page()
    img = np.kron(refl[20:190, 40:210], np.ones((6, 6)))
    img = np.clip(img + rng(SEED, b"px-noise").standard_normal(img.shape)
                  * 0.02, 0.0, 1.0)
    res = acquire.acquire_and_decode(img, spec, SEED)
    assert res.ok, res.diagnostics
    assert res.diagnostics.get("word_detector") == "site_fit"
    assert res.cell_origin_abs_yx == (20, 40)
    assert res.n_tiles_decoded == res.n_tiles_attempted >= 4
    assert res.diagnostics.get("color_payload_pending") is True
    res_bad = acquire.acquire_and_decode(img, spec, b"not-the-seed")
    assert not res_bad.ok
    assert res_bad.diagnostics["failed_stage"] in ("stage_a", "stage_b")
    print(f"  e2e: origin {res.cell_origin_abs_yx}, "
          f"{res.n_tiles_decoded}/{res.n_tiles_attempted} post-fold words, "
          f"word_detector={res.diagnostics['word_detector']}; wrong seed "
          f"failed at {res_bad.diagnostics['failed_stage']}")


def test_z_grid_shape_guard() -> None:
    spec, means, z, hard_ac, m_win, truth = _window()
    try:
        acquire.stage_a(hard_ac, spec.pilot, SEED, "K",
                        page_tiles_yx=(4, 4), z_grid=z[:-1])
        raise AssertionError("mismatched z_grid accepted")
    except ValueError:
        pass


if __name__ == "__main__":
    for fn in sorted(k for k in list(globals()) if k.startswith("test_")):
        globals()[fn]()
        print(f"PASS {fn}")
