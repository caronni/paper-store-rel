"""§15.7 repass pre-registered bars on a DEGRADATION FIXTURE (F15).

One large piece (280x280 cells at -8 deg) rendered onto a FROZEN-payload
e018 page (seeded random bytes — NEVER the live gen_e018 tar.gz, whose
self-referential payload re-rolls this fixture on every src edit;
caught in-build when a tilemap.py review fix flipped the outcome), with
a UNIFORM degradation over the whole piece: ink contrast compressed
toward paper (ALPHA=0.41 -> ink 45 -> ~131 grey) + elevated noise
(SIGMA=15 vs the 5.0 base). Mechanism under test: at dA==0 the driver
emits piece_cell_bits ctx LLRs with NO pilot recal (means is None on
that path), so a global level shift leaves its LLR calibration off and
marginal tiles fail; the repass refit (refine_on_sites + dense
2-Gaussian recal on pilot sites UNION certified-cell labels) restores
calibration and converts them.

Frozen from the 2026-07-11 post-review-fix sweep (all deterministic):
  too WEAK  (alpha >= 0.45 at sigma 15): 0-1 failed tiles or 0
    conversions; too STRONG (alpha <= 0.38 at sigma 15, or sigma >= 17
    at alpha 0.40): the anchor chain refuses the piece entirely;
  PLATEAU (alpha 0.39-0.42 x sigma 13-15): 1-3 conversions everywhere;
  FROZEN center ALPHA=0.41, SIGMA=15, render rng seed 3: driver
    certifies 12 / fails 18 piece tiles; repass round 1 converts 3
    failed->certified; round 2 = fixed point; 0 wrong certifications.
Retune against the sweep protocol if upstream segmentation/placement
changes move the balance.

Bars asserted (PILOTS-DESIGN §15.7 build spec + fixture bars):
  (a) driver leaves >= 3 piece tiles status 'failed' (measured 18);
  (b) repass round 1 converts >= 1 failed -> certified (measured 3);
  (c) EVERY certified tile byte-matches the fountain frame GT at every
      stage (0 wrong certifications);
  (d) no certified tile regresses across rounds (R3 monotone);
  (e) round 2 certifies nothing new (fixed point within the <= 3 cap);
  plus the R3 idempotence control: repass on a fully-certified state
  is a no-op (no observation churn, no refits).
"""
import importlib.util
import pickle
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, fountain, segment, tilemap  # noqa: E402
from paperholo.modulation import keystream                 # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# render machinery (constants/canvas helper) + the e018 session driver
sa = _load("repass_render_machinery",
           Path(__file__).resolve().parent / "test_session_anchor.py")
rp = _load("e018_repass_mod",
           ROOT / "experiments/018-confetti-c3-play/repass.py")
sd = sa.sd

# ---- FROZEN payload page (source-independence; measured trap) --------
# sa.CELLS composes gen_e018's LIVE tar.gz — self-referential, so ANY
# edit to a CORE src module reshuffles the page content and re-rolls
# this fixture's tuning (caught in-build: a tilemap.py review fix
# flipped the band outcome). The test page instead carries seeded
# random bytes of the frozen e018 length — valid format, stable
# forever, GT frame derived from the same bytes.
_FROZEN_DATA = np.random.default_rng(1018).integers(
    0, 256, sd.DATA_LEN_BYTES, dtype=np.uint8).tobytes()
_FRAMED = fountain.encode_volume_pages(_FROZEN_DATA, sd.VSPEC)[0]
_CELLS = compose.compose_page(
    _FRAMED["payload_bits"], sd.spec, sd.SEED, page=0
).cell_values.astype(np.uint8)
_EXT = np.zeros((_CELLS.shape[0] + 2 * sa.MARGIN_CELLS,
                 _CELLS.shape[1] + 2 * sa.MARGIN_CELLS), np.uint8)
_EXT[sa.MARGIN_CELLS:-sa.MARGIN_CELLS,
     sa.MARGIN_CELLS:-sa.MARGIN_CELLS] = _CELLS
_REFL = sa.PAPER - _EXT.astype(np.float32) * (sa.PAPER - sa.INK)

# ---- frozen fixture constants (sweep-tuned, see module docstring) ----
PIECE_Y0, PIECE_X0, SIDE = 700, 500, 280   # page-frame cells
ANGLE_DEG = -8.0
BAND_Y0, BAND_Y1 = 0, 3000                 # UNIFORM: whole piece degraded
ALPHA, SIGMA = 0.41, 15.0                  # ink contrast retention, noise
RNG_SEED = 3
DPI, ERODE, POLICY, RATE = 1600.0, 4, "weighted_sum", "r0550"
IMG_NAME = "repass_fixture.png"


def _render_band_piece(gen: np.random.Generator) -> np.ndarray:
    """sa.render_piece with the degraded band: contrast compression
    toward paper (hi' = PAPER - (PAPER-hi)*ALPHA — paper unmoved, ink
    lightened) + extra noise SIGMA on band pixels. Band rows are PAGE
    rows (LDPC-tile aligned); the piece is rotated, so the band crosses
    the rendered image at the piece angle, like a real damage stripe."""
    PPC, PAPER, BACKING = sa.PPC, sa.PAPER, sa.BACKING
    y0, x0 = PIECE_Y0 + sa.MARGIN_CELLS, PIECE_X0 + sa.MARGIN_CELLS
    a = np.deg2rad(ANGLE_DEG)
    SS = 2
    n_out = int(np.ceil(SIDE * (abs(np.cos(a)) + abs(np.sin(a))))) + 2
    N = n_out * PPC * SS
    d = (np.arange(N) + 0.5) / (PPC * SS) - n_out / 2.0
    dv, du = np.meshgrid(d, d, indexing="ij")
    cy, cx = y0 + SIDE / 2.0, x0 + SIDE / 2.0
    yy = cy + (dv * np.cos(a) - du * np.sin(a))
    xx = cx + (dv * np.sin(a) + du * np.cos(a))
    inside = ((yy >= y0) & (yy < y0 + SIDE)
              & (xx >= x0) & (xx < x0 + SIDE))
    iy = np.clip(yy.astype(np.int64), 0, _REFL.shape[0] - 1)
    ix = np.clip(xx.astype(np.int64), 0, _REFL.shape[1] - 1)
    hi = np.where(inside, _REFL[iy, ix], BACKING)
    in_band = inside & (yy >= BAND_Y0 + sa.MARGIN_CELLS) \
        & (yy < BAND_Y1 + sa.MARGIN_CELLS)
    hi = np.where(in_band, PAPER - (PAPER - hi) * np.float32(ALPHA), hi)
    out = hi.reshape(N // SS, SS, N // SS, SS).mean(axis=(1, 3))
    bm = in_band.reshape(N // SS, SS, N // SS, SS).mean(axis=(1, 3)) > 0.5
    out = ndimage.gaussian_filter(out, 2.0, mode="nearest")
    out = out + gen.normal(0.0, 5.0, out.shape).astype(np.float32)
    out = out + np.where(bm, gen.normal(0.0, SIGMA, out.shape),
                         0.0).astype(np.float32)
    return np.clip(out, 0, 255).astype(np.float32)


def _driver_pass(canvas: np.ndarray) -> tilemap.PageDecodeState:
    """The §15.6 anchor chain (test_session_anchor._run_chain footing)
    with repass-compatible scan ids f'{IMG_NAME}/p{i}/w{j}'."""
    imgf = canvas.astype(np.float32)
    pieces = segment.segment_pieces(imgf, cell_px=8.0, dpi=DPI)
    backing = segment.estimate_backing(imgf)
    pds = tilemap.PageDecodeState(sd.spec, sd.SEED, page=0)
    pim = compose.payload_index_map(sd.spec, sd.SEED)
    ks = keystream(sd.SEED, 3, 0, tuple(sd.spec.page_cells_yx))
    pend = {0: np.ones(tuple(sd.spec.page_cells_yx), bool)}
    assert len(pieces) == 1, f"segmentation found {len(pieces)} pieces"
    for i, p in enumerate(pieces):
        res = sd.anchor_place_piece(p, backing, pend, DPI, ERODE)
        assert res is not None, "anchor chain refused the fixture piece"
        dA, bits, mcell, cllr, _means, placed = res
        core_full = sd._core(mcell, ERODE)
        for j, (wy, wx, h, w, pl) in enumerate(placed):
            sd._emit_placed(
                pds, f"{IMG_NAME}/p{i}/w{j}", bits[wy:wy + h, wx:wx + w],
                core_full[wy:wy + h, wx:wx + w],
                cllr[wy:wy + h, wx:wx + w], pl, pim, ks,
                {"mismatch": pl.mismatch, "dA": dA})
    pds.decode_tiles(RATE, policy=POLICY)
    return pds


def _gt_user_bits():
    """Fountain frame GT for the wrong-certification audit — from the
    FROZEN payload (never the live gen_e018 tar.gz, which drifts with
    every source edit; V1's audit trap)."""
    user = np.asarray(fountain.volume_encode(
        _FROZEN_DATA, sd.VSPEC).page_user_bits[0])
    gtmap = {tuple(e["tile_yx"]): e["user_offset"]
             for e in _FRAMED["per_tile"]}
    return user, gtmap


_CACHE: dict = {}


def _fixture():
    """Build once: rendered canvas -> PNG on disk (repass reads glass
    images by path) -> driver decode state (pickled so each test gets
    its own copy) -> GT audit arrays."""
    if not _CACHE:
        gen = np.random.default_rng(RNG_SEED)
        canvas = sa._canvas([_render_band_piece(gen)])
        canvas_u8 = np.clip(np.round(canvas), 0, 255).astype(np.uint8)
        from PIL import Image
        png = Path(tempfile.mkdtemp(prefix="repass_fix_")) / IMG_NAME
        Image.fromarray(canvas_u8).save(png)
        # drive from the PNG-round-tripped pixels — repass_round loads
        # the same file, so both passes see identical glass
        pds = _driver_pass(np.asarray(Image.open(png)))
        _CACHE["png"] = png
        _CACHE["state"] = pickle.dumps((pds, set()))
        _CACHE["gt"] = _gt_user_bits()
    return _CACHE["png"], pickle.loads(_CACHE["state"])[0], _CACHE["gt"]


def _certified(pds) -> set:
    return {t for t, st in pds.tiles.items() if st.status == "certified"}


def _audit_zero_wrong(pds, gt) -> None:
    """(c) every certified tile byte-matches the fountain frame GT."""
    user, gtmap = gt
    n = 0
    for t, st in pds.tiles.items():
        if st.status == "certified":
            assert st.payload_bits is not None, t
            off = gtmap[t]
            assert np.array_equal(
                st.payload_bits, user[off:off + st.payload_bits.size]), (
                f"WRONG CERTIFICATION at tile {t}")
            n += 1
    assert n == len(_certified(pds))


def test_repass_converts_failed_band_fixture():
    png, pds, gt = _fixture()
    # ---- driver leg ----
    piece_tiles = {t for t, st in pds.tiles.items()
                   if st.status in ("certified", "failed")}
    n_failed = sum(1 for t in piece_tiles
                   if pds.tiles[t].status == "failed")
    assert n_failed >= 3, f"(a) piece failed tiles: {n_failed}"
    cert0 = _certified(pds)
    assert len(cert0) >= 3, (      # the in-window label majority exists
        f"driver certified only {len(cert0)} tiles — no label source")
    _audit_zero_wrong(pds, gt)
    failed0 = {t for t, st in pds.tiles.items() if st.status == "failed"}
    failed0_cells = rp.failed_cell_bool(
        pds, compose.payload_index_map(pds.spec, pds.seed))
    # ---- repass round 1: label-refit + dense recal + supersede ----
    stats1 = rp.repass_round(pds, set(), [png], DPI, 1, ERODE, POLICY)
    assert stats1["labels"] >= rp.MIN_LABEL_SITES
    assert stats1["refit_pieces"] >= 1, stats1      # the mechanism engaged
    assert stats1["superseded_obs"] >= 1, stats1    # R2 replace-never-sum
    # v1 semantics guard (018.8 review): the CORRELATION path is
    # unmasked — its refit emission must extend beyond failed tiles
    # (v1.1-a's conditional-trust exclusion applies to word-touched
    # pieces only; leakage onto this path passed the old bars)
    r1 = np.concatenate(
        [obs.payload_cell_index for s, obs in pds.scans.items()
         if s.startswith("repass1/") and not s.startswith("repass1/keep/")])
    assert (~failed0_cells[r1]).any(), (
        "correlation-piece emission was masked to failed tiles — "
        "conditional trust leaked onto the v1 path")
    cert1 = _certified(pds)
    converted = failed0 & cert1
    assert len(converted) >= 1, (
        f"(b) repass converted nothing (round 1 stats {stats1})")
    assert cert0 <= cert1, f"(d) regression: {cert0 - cert1}"
    _audit_zero_wrong(pds, gt)
    # ---- repass round 2: fixed point (R3) ----
    stats2 = rp.repass_round(pds, set(), [png], DPI, 2, ERODE, POLICY)
    cert2 = _certified(pds)
    assert cert2 == cert1, (
        f"(e) round 2 not a fixed point: +{cert2 - cert1} "
        f"-{cert1 - cert2} (stats {stats2})")
    _audit_zero_wrong(pds, gt)


def test_repass_noop_on_fully_certified_state():
    """R3 idempotence control: zero pending tiles -> repass touches
    nothing (no supersede, no refit, no new observations)."""
    png, pds, _gt = _fixture()
    for st in pds.tiles.values():
        st.status = "certified"        # force the fully-certified state
    scan_ids = set(pds.scans)
    status_before = {t: st.status for t, st in pds.tiles.items()}
    stats = rp.repass_round(pds, set(), [png], DPI, 1, ERODE, POLICY)
    assert stats["refit_pieces"] == 0, stats
    assert stats["retried_pieces"] == 0, stats
    assert stats["superseded_obs"] == 0, stats
    assert stats["tiles"]["certified"] == 0, stats   # decoded nothing new
    assert stats["tiles"]["failed"] == 0, stats
    assert set(pds.scans) == scan_ids, "observation churn on a no-op"
    assert {t: st.status for t, st in pds.tiles.items()} == status_before


if __name__ == "__main__":
    test_repass_converts_failed_band_fixture()
    print("PASS repass conversion bars (a)-(e)")
    test_repass_noop_on_fully_certified_state()
    print("PASS repass no-op control")
