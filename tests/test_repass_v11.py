"""§15.7 repass v1.1-a — CONDITIONAL TRUST machinery on a WORD-PATH fixture.

v1 (test_repass.py) validates the label-refit CONVERSION mechanism on a
correlation-placed piece. v1.1-a un-gates repass to WORD-PATH pieces —
the population that structurally starved v1 on the try_2 real-scan
state (46:3 word:correlation observations, 0 conversions; 95 of 134
covered-failed tiles marginal, clustered confident-wrong = the refit
class) — under the 018.6 conditional-trust rule: word evidence is
higher-trust WHERE IT CERTIFIED; inside FAILED tiles it is
measured-bad, so the label-refit supersedes there and ONLY there.

WHAT THIS FIXTURE CAN AND CANNOT MEASURE (2026-07-12 sweep, 018 log
018.8): on the synthetic channel the word path's ctx+PAVA calibrates
away every uniform contrast/noise degradation tried (pilot BER 0.000
at alpha 0.41 / sigma 10 — per-pixel noise averages out over the 64
px/cell footing; the v1 fixture only converts because the driver's
dA==0 path emits UNCALIBRATED LLRs, a gap acquire does not have). The
real v1.1 target class — within-window drift read confidently wrong —
does not exist in a rigid synth render. So this test asserts the
v1.1-a MACHINERY exhaustively (trust boundary, trim algebra, keep
quality, lineage matcher, monotonicity, honesty), while the
CONVERSION bar (>0 failed->certified on a word-path state) is
measured on the REAL e018 session state — the 018.8 A/B — per the
project rule that rate/conversion claims come from real scans.

Fixture: one large clean piece at an 8 deg lattice angle on the
FROZEN-payload e018 page (never the live gen_e018 tar.gz —
test_repass.py's measured trap). The word path decodes it (8 windows),
certifying the interior; the piece-boundary partial tiles FAIL
(coverage-bound — unconvertible by construction, but real members of
the failed set), giving the conditional-trust machinery a live
word-path piece with failed tiles under it.

Bars asserted:
  (a) the driver leaves a word-path observation with >= 3 failed
      tiles under it, >= 6 certified (the label source);
  (b) repass ENGAGES the piece as a word piece (word_pieces >= 1,
      superseded_obs >= 1) and its emission overlaps the word
      observation's failed-tile cells (the supersede is real);
  (c) 0 wrong certifications at every stage (GT = the frozen payload);
  (d) CONDITIONAL TRUST boundary: every round-r emission lands inside
      round-r-start FAILED-tile cells; word-observation cells OUTSIDE
      failed tiles survive the trim verbatim (never superseded);
  (e) gotcha (ii): the trimmed word observation's keep re-add
      preserves tile_words/fail_errs/meta — pilot_ber_est unchanged
      (an add_placed_fragment re-add would weight-floor it to 0.05);
  (f) gotcha (iii): the related-sids matcher finds `repassN/keep/<base>`
      keeps of single-sid (word) pieces in later rounds;
  (g) monotone (no certified regression) + fixed point within the
      <= 3 round cap.
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

from paperholo import compose, formats, segment, tilemap  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# frozen-payload page + GT audit + render machinery, shared with the v1
# test (ONE frozen payload across both repass fixtures)
tr = _load("repass_v1_mod", Path(__file__).resolve().parent
           / "test_repass.py")
sa, rp, sd = tr.sa, tr.rp, tr.sd

# ---- frozen fixture constants (2026-07-12 sweep; clean channel — see
# module docstring for why degradation levers are inert here) ----
PIECE_Y0, PIECE_X0, SIDE = 700, 500, 300   # page-frame cells
ANGLE_DEG = 8.0                            # rendered lattice angle
RNG_SEED = 3
DPI, CELL_PX = 1600.0, 8.0
ERODE, POLICY, RATE = tr.ERODE, tr.POLICY, tr.RATE
IMG_NAME = "repass_v11_fixture.png"


def _render_piece() -> np.ndarray:
    """Direct supersampled sampling of the frozen extended field at a
    deliberate lattice angle (the test_repass renderer, clean channel)."""
    gen = np.random.default_rng(RNG_SEED)
    PPC, BACKING = sa.PPC, sa.BACKING
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
    iy = np.clip(yy.astype(np.int64), 0, tr._REFL.shape[0] - 1)
    ix = np.clip(xx.astype(np.int64), 0, tr._REFL.shape[1] - 1)
    hi = np.where(inside, tr._REFL[iy, ix], BACKING)
    out = hi.reshape(N // SS, SS, N // SS, SS).mean(axis=(1, 3))
    out = ndimage.gaussian_filter(out, 2.0, mode="nearest")
    out = out + gen.normal(0.0, 5.0, out.shape).astype(np.float32)
    return np.clip(out, 0, 255).astype(np.float32)


def _driver_word_pass(png: Path) -> tuple[tilemap.PageDecodeState, str]:
    """The session driver's WORD path verbatim (session_decode._run's
    tiled branch, anchor-chain kwargs) on the fixture piece."""
    from PIL import Image
    imgf = np.asarray(Image.open(png)).astype(np.float32)
    pieces = segment.segment_pieces(imgf, cell_px=CELL_PX, dpi=DPI)
    assert len(pieces) == 1, f"segmentation found {len(pieces)} pieces"
    p = pieces[0]
    pds = tilemap.PageDecodeState(sd.spec, sd.SEED, page=0)
    sid = f"{png.name}/p0"
    yy = np.flatnonzero(p.mask.any(axis=1))
    xx = np.flatnonzero(p.mask.any(axis=0))
    long_mm = max(yy[-1] - yy[0], xx[-1] - xx[0]) / (DPI / 25.4)
    assert (p.area_mm2 >= sd.WORD_PATH_MIN_MM2
            and long_mm >= sd.TILE_PATH_MIN_MM), "fixture not word-routed"
    crop = np.ascontiguousarray(p.img[yy[0]:yy[-1] + 1, xx[0]:xx[-1] + 1])
    mask = np.ascontiguousarray(p.mask[yy[0]:yy[-1] + 1, xx[0]:xx[-1] + 1])
    ident, _ = formats.page_decode(
        crop, scan_id=sid, state=pds, candidates=[sd.FMT], scan_dpi=DPI,
        window_cells=sd.WINDOW_CELLS, overlap_cells=sd.OVERLAP_CELLS,
        id_window_px=int(round(sd.WINDOW_CELLS * CELL_PX)),
        detector="ctx", calibrate=True,
        mask=mask, mask_min_cov=0.65, id_retry=3, fold_id_window=True)
    assert ident.ok and sid in pds.scans, "word path failed on the fixture"
    assert int(ident.diagnostics.get("n_windows_ok", 0)) >= 2, \
        ident.diagnostics.get("n_windows_ok")
    assert pds.scans[sid].meta.get("placement_source") == "pilot_words"
    pds.decode_tiles(RATE, policy=POLICY)
    return pds, sid


_CACHE: dict = {}


def _fixture():
    if not _CACHE:
        canvas = sa._canvas([_render_piece()])
        canvas_u8 = np.clip(np.round(canvas), 0, 255).astype(np.uint8)
        from PIL import Image
        png = Path(tempfile.mkdtemp(prefix="repass_v11_")) / IMG_NAME
        Image.fromarray(canvas_u8).save(png)
        pds, sid = _driver_word_pass(png)
        _CACHE["png"] = png
        _CACHE["sid"] = sid
        _CACHE["state"] = pickle.dumps((pds, set()))
        _CACHE["gt"] = tr._gt_user_bits()
    return (_CACHE["png"], pickle.loads(_CACHE["state"])[0],
            _CACHE["sid"], _CACHE["gt"])


def test_related_sids_matcher():
    """Gotcha (iii): keeps of single-sid pieces have NO trailing segment;
    the endswith arm must find them, without false-matching prefixes."""
    base = "x.png/p1"
    scans = ["x.png/p1", "x.png/p1/w0", "repass1/x.png/p1/w2",
             "repass1/keep/x.png/p1",
             "repass2/keep/repass1/keep/x.png/p1",
             "repass1/keep/x.png/p1/w0",
             # must NOT match:
             "x.png/p11", "repass1/keep/x.png/p11", "y.png/p1/w0",
             "repass1/y.png/p1x/w0"]
    got = rp.related_sids(scans, base)
    assert got == ["x.png/p1", "x.png/p1/w0", "repass1/x.png/p1/w2",
                   "repass1/keep/x.png/p1",
                   "repass2/keep/repass1/keep/x.png/p1",
                   "repass1/keep/x.png/p1/w0"], got


def test_readd_trimmed_preserves_quality():
    """Gotcha (ii): the keep re-add must copy tile_words/fail_errs/meta —
    pilot_ber_est is a derived property; losing tile_words weight-floors
    kept word evidence to 0.05 in every quality-aware merge policy."""
    # fail_errs deliberately NON-default (10.0 = the v2 layout's t_full;
    # the dataclass default is 13.0): a dropped fail_errs copy in
    # _readd_trimmed must FAIL here, not coast on the default
    # (review 018.8 discrimination fix)
    obs = tilemap.ScanObservation(
        scan_id="a/p0",
        payload_cell_index=np.arange(10, dtype=np.int64),
        payload_llr=np.linspace(-3.0, 3.0, 10),
        tile_words={(0, 0): 2, (0, 1): -1}, n_windows=4,
        meta={"placement_source": "pilot_words"}, fail_errs=10.0)

    class _P:
        scans: dict = {}
    pds = _P()
    keep = np.ones(10, bool)
    keep[3:6] = False
    rp._readd_trimmed(pds, "repass1/keep/a/p0", obs, keep, 1)
    k = pds.scans["repass1/keep/a/p0"]
    assert k.tile_words == obs.tile_words
    assert k.fail_errs == 10.0
    assert k.n_windows == 4
    assert abs(k.pilot_ber_est - obs.pilot_ber_est) < 1e-15
    assert k.meta["placement_source"] == "pilot_words"
    assert k.meta["trimmed_by_round"] == 1
    assert np.array_equal(k.payload_cell_index,
                          np.array([0, 1, 2, 6, 7, 8, 9]))
    assert np.array_equal(k.payload_llr, obs.payload_llr[keep])
    try:
        rp._readd_trimmed(pds, "repass1/keep/a/p0", obs, keep, 1)
        raise AssertionError("keep sid collision not caught")
    except ValueError:
        pass


def test_repass_v11_word_path_machinery():
    png, pds, wsid, gt = _fixture()
    pim = compose.payload_index_map(pds.spec, pds.seed)
    # ---- (a) driver leg: word obs with failed tiles under it ----
    wobs0 = pds.scans[wsid]
    widx0 = wobs0.payload_cell_index.copy()
    wwords0 = dict(wobs0.tile_words)
    wber0 = wobs0.pilot_ber_est
    failed0_cells = rp.failed_cell_bool(pds, pim)
    n_fail0 = sum(1 for st in pds.tiles.values() if st.status == "failed")
    n_cert0 = len(tr._certified(pds))
    assert n_fail0 >= 3, f"(a) failed tiles under the word piece: {n_fail0}"
    assert n_cert0 >= 6, f"(a) label source too thin: {n_cert0} certified"
    assert failed0_cells[widx0].any(), "(a) word obs covers no failed cell"
    tr._audit_zero_wrong(pds, gt)
    cert_prev = tr._certified(pds)
    protected0 = widx0[~failed0_cells[widx0]]
    assert protected0.size > 0, "fixture degenerate: nothing to protect"
    # ---- repass rounds: machinery bars per round ----
    stats_hist = []
    r1_idx = np.empty(0, np.int64)
    converged = False
    last_r = 0
    for r in (1, 2, 3):
        failed_r = rp.failed_cell_bool(pds, pim)   # this round's boundary
        # this round's PROTECTED set: word-evidence cells outside its
        # failed tiles (all word-source obs, incl. keeps of keeps)
        wp = [o.payload_cell_index for o in pds.scans.values()
              if o.meta.get("placement_source") == "pilot_words"]
        prot_r = (np.concatenate(wp) if wp else np.empty(0, np.int64))
        prot_r = np.unique(prot_r[~failed_r[prot_r]])
        stats = rp.repass_round(pds, set(), [png], DPI, r, ERODE, POLICY)
        stats_hist.append(stats)
        last_r = r
        cert_now = tr._certified(pds)
        assert cert_prev <= cert_now, f"(g) regression in round {r}"
        # (d) no emission of this round touches ITS protected cells —
        # word evidence outside failed tiles is never superseded
        for s, obs in pds.scans.items():
            if (s.startswith(f"repass{r}/")
                    and not s.startswith(f"repass{r}/keep/")):
                hit = np.isin(obs.payload_cell_index, prot_r)
                assert not hit.any(), (
                    f"(d) round-{r} emission {s} covers "
                    f"{int(hit.sum())} protected word cells")
        if r == 1:
            # capture NOW — round 2's refit legitimately supersedes
            # round-1 emissions out of the state
            r1 = [obs.payload_cell_index
                  for s, obs in pds.scans.items()
                  if s.startswith("repass1/")
                  and not s.startswith("repass1/keep/")]
            r1_idx = (np.concatenate(r1) if r1
                      else np.empty(0, np.int64))
        tr._audit_zero_wrong(pds, gt)                       # (c)
        if cert_now == cert_prev and r > 1:
            converged = True
            break
        cert_prev = cert_now
    assert stats_hist[0]["word_pieces"] >= 1, (
        f"(b) word piece not engaged: {stats_hist[0]}")
    assert stats_hist[0]["superseded_obs"] >= 1, stats_hist[0]
    # ---- (b) the supersede was real: round-1 emission overlapped the
    # word observation's failed-tile cells
    assert np.isin(r1_idx, widx0[failed0_cells[widx0]]).any(), (
        "(b) repass emission never overlapped the word obs' failed cells")
    # ---- (d)+(e): the word observation's trim honored conditional trust
    assert wsid not in pds.scans, "word obs never superseded — no trim ran"
    lineage = [s for s in pds.scans if s.endswith("/" + wsid)]
    assert lineage, "trimmed word obs left no keep"
    kept_idx = np.concatenate(
        [pds.scans[s].payload_cell_index for s in lineage])
    missing = protected0[~np.isin(protected0, kept_idx)]
    assert missing.size == 0, (
        f"(d) {missing.size} protected word cells (outside round-1 failed "
        "tiles) were trimmed")
    # trim REMOVAL direction (review 018.8: a keep-everything no-op trim
    # — the R2 correlated-summing violation — must fail here): no word
    # keep retains a cell the round-1 emission superseded
    assert not np.isin(kept_idx, r1_idx).any(), (
        "R2 violation: keeps retain cells the repass emission superseded")
    for s in lineage:                                       # (e)
        assert pds.scans[s].tile_words == wwords0, "(e) tile_words lost"
        assert abs(pds.scans[s].pilot_ber_est - wber0) < 1e-12, (
            "(e) keep quality drifted — pilot_ber_est must ride tile_words")
    # ---- (f): the matcher finds the keep lineage in a later round
    base = f"{png.name}/p0"
    rel = rp.related_sids(pds.scans, base)
    for s in lineage:
        assert s in rel, f"(f) matcher missed keep {s}"
    # ---- (g) real fixed point: the loop converged AND one further
    # round certifies nothing new (review 018.8: len<=cap was a
    # tautology under a 3-iteration loop)
    assert converged, f"(g) no fixed point within 3 rounds ({stats_hist})"
    cert_before_extra = tr._certified(pds)
    rp.repass_round(pds, set(), [png], DPI, last_r + 1, ERODE, POLICY)
    assert tr._certified(pds) == cert_before_extra, (
        "(g) post-fixed-point round changed the certified set")
    tr._audit_zero_wrong(pds, gt)


def test_repass_v11_reinvocation_resumes_rounds():
    """018.8 MAJOR regression: a second CLI invocation must number its
    rounds past any surviving repassN/ sids. Invocation 1 = one round
    (main()'s fixed-point break saves exactly this shape: repass1/*
    emissions intact); a fresh counter would re-derive the same sids
    and add_placed_fragment raises mid-round (reproduced pre-fix,
    state-wedging). The resume rule must engage cleanly instead."""
    png, pds, _wsid, gt = _fixture()
    rp.repass_round(pds, set(), [png], DPI, 1, ERODE, POLICY)
    pds2 = pickle.loads(pickle.dumps((pds, set())))[0]
    surviving = [s for s in pds2.scans if s.startswith("repass1/")
                 and not s.startswith("repass1/keep/")]
    assert surviving, "invocation 1 left no surviving emissions"
    r0 = rp.resume_round(pds2.scans)
    assert r0 == 1, r0
    # invocation 2 at the resumed round: no sid collision, clean run
    rp.repass_round(pds2, set(), [png], DPI, r0 + 1, ERODE, POLICY)
    tr._audit_zero_wrong(pds2, gt)


def test_repass_v11_stakeless_word_piece_skipped():
    """Stakeless-skip coverage (review 018.8: the branch was executed by
    no test — its deletion or weakening passed the whole suite): a word
    piece with no observation cell in any failed tile is skipped
    outright — no re-placement, no supersede, no observation churn —
    while the page still has OTHER pending tiles (so the round does not
    no-op before the per-piece loop)."""
    png, pds, _wsid, _gt = _fixture()
    # flip every failed tile to certified: the piece keeps its word
    # observation but loses its stake; the rest of the page stays
    # unobserved/low_coverage -> pending remains non-empty
    for st in pds.tiles.values():
        if st.status == "failed":
            st.status = "certified"
    assert pds.pending_tiles(), "fixture page unexpectedly fully decoded"
    scan_ids = set(pds.scans)
    stats = rp.repass_round(pds, set(), [png], DPI, 1, ERODE, POLICY)
    assert stats["stakeless_skipped"] == 1, stats
    assert stats["refit_pieces"] == 0, stats
    assert stats["word_pieces"] == 0, stats
    assert stats["superseded_obs"] == 0, stats
    assert set(pds.scans) == scan_ids, "stakeless skip churned the state"


if __name__ == "__main__":
    test_related_sids_matcher()
    print("PASS matcher (gotcha iii)")
    test_readd_trimmed_preserves_quality()
    print("PASS trim re-add quality (gotcha ii)")
    test_repass_v11_word_path_machinery()
    print("PASS v1.1-a word-path machinery bars (a)-(g)")
    test_repass_v11_reinvocation_resumes_rounds()
    print("PASS re-invocation round resume")
    test_repass_v11_stakeless_word_piece_skipped()
    print("PASS stakeless-skip branch")
