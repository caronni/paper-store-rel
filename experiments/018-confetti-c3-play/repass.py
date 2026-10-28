#!/usr/bin/env python
"""e018 decode-directed re-acquisition — the §15.7 "repass" post-pass
(F15; feedback-repass branch). Takes a saved session state + the ORIGINAL
glass images and runs certified-supervised re-acquisition rounds:

  certified tiles -> dense printed-domain truth labels (F9 overlay XOR
  keystream — the overlay is TX-domain; refine/recal live in the ink
  domain) -> per piece: re-run the §15.6 anchor chain, then per placed
  window refit (angle, sub-cell phase) on pilot sites UNION truth labels
  (refine_on_sites is label-source-agnostic) -> re-sample from glass ->
  dense-label recal -> SUPERSEDE the piece's old observations (R2:
  replace, never sum — correlated evidence) -> decode_tiles -> repeat
  until a round certifies nothing new (R3; hard cap --rounds).

Failed pieces (no prior observation) get a free second chance through
the anchor chain under the updated pending set. Certified tiles are
never touched (R1 labels only from CRC-certified tiles; R4 gates+CRC
stay in charge). Repass on a fully-certified state is a no-op.

v1.1-a CONDITIONAL TRUST (018.6 close-out design record; built after
the try_2 verdict — v1's correlation-only gate reached 0 of the 95
measured marginal tiles, which all sit under WORD-PATH pieces):
word-path pieces are no longer skipped. Word evidence is higher-trust
WHERE IT CERTIFIED and measured-bad inside FAILED tiles (018.7: the
marginal class fails on clustered confident-wrong cells, wrong-cell
|LLR| > right-cell), so for word-touched pieces the label-refit
emission EXCLUDES the piece's PROTECTED word cells — word-covered
cells outside failed tiles (frozen at round start) — and the word
observations are therefore trimmed on exactly their failed-tile
cells; everywhere else the word evidence survives verbatim.
(018.8 review refinement of the 018.6 sketch: the record's
failed-tile INCLUDE mask also discarded fresh refit coverage on
never-observed gap cells under word pieces — no word evidence exists
there for trust to protect, and the loss was measured >=17
low_coverage tiles on the real 4-scan state. The exclusion form
keeps the trust rule bit-identical on word-covered cells and frees
the gap cells.) The trim re-add copies tile_words/fail_errs/meta
directly (pilot_ber_est is a derived property; an
add_placed_fragment re-add would weight-floor kept word evidence to
0.05 — the recorded silent killer). Word-touched pieces with no
observation cell in any failed tile are skipped outright (nothing to
convert; re-placing a mostly-certified piece against the PRUNED
pending set risks searching with its true pose excluded). No
anchor-pose constructor: the global placer search finds word-piece
poses (018.2, p5). Correlation-only pieces keep v1 semantics
unchanged. Rounds RESUME from the highest repassN/ in the state
(018.8 review: a fresh counter collides with surviving prior-round
emission sids and wedges the state — reproduced pre-fix).

Usage:
  env/bin/python repass.py <img> [<img> ...] --dpi D --state PATH
      [--rounds 3] [--policy weighted_sum] [--emit-erode-cells 4]
  (feed the SAME image files the session driver ingested — piece
  identity is (filename, segment index))
"""
from __future__ import annotations

import argparse
import importlib.util
import pickle
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, fountain, ldpc, place, segment, tilemap  # noqa
from paperholo.modulation import keystream                        # noqa

_sd_spec = importlib.util.spec_from_file_location(
    "e018_session_decode", Path(__file__).resolve().parent
    / "session_decode.py")
sd = importlib.util.module_from_spec(_sd_spec)
_sd_spec.loader.exec_module(sd)

MIN_LABEL_SITES = 40      # below this a window's refit adds nothing over
#                           the pilot-only refine the driver already ran


def truth_grid(pds) -> np.ndarray:
    """Printed-domain truth over the page grid: -1 unknown, else the
    printed cell bit of a certified cell (R1 label source). Thin wrapper
    over tilemap.known_cell_values — the F10 export that anticipated
    exactly this loop (review-verified identical semantics)."""
    H, W = pds.spec.page_cells_yx
    grid = np.full((H, W), -1, np.int8)
    y, x, bits = pds.known_cell_values()
    grid[y, x] = bits.astype(np.int8)
    return grid


def related_sids(scan_ids, base: str) -> list[str]:
    """Every observation sid belonging to one physical piece: the
    driver's own ids (`<base>` word obs, `<base>/wJ` placer windows)
    plus repass lineage (`repassN/<base>/wJ` emissions and
    `repassN/keep/...` trims). The endswith arm is load-bearing (v1.1
    gotcha iii): the keep of a SINGLE-SID observation — every word-path
    piece — is `repassN/keep/<base>` with no trailing segment, which the
    v1 `/<base>/` containment test missed; round 2 would then treat the
    piece as unobserved and re-emit its evidence as if new."""
    return [s for s in scan_ids
            if s == base or s.startswith(base + "/")
            or (s.startswith("repass")
                and (f"/{base}/" in s or s.endswith("/" + base)))]


def resume_round(scan_ids) -> int:
    """Highest repassN/ round already present in a state (0 if none).
    A new invocation numbers its rounds from here + 1: a fresh counter
    re-derives the SAME emission sids for any piece a prior invocation
    refit (deterministic given unchanged labels/glass), and
    add_placed_fragment raises on the collision mid-round, wedging the
    state (018.8 review, reproduced pre-fix)."""
    r0 = 0
    for s in scan_ids:
        m = re.match(r"repass(\d+)/", s)
        if m:
            r0 = max(r0, int(m.group(1)))
    return r0


def failed_cell_bool(pds, pim: np.ndarray) -> np.ndarray:
    """Dense bool over the payload bijection: True at cells of tiles
    whose status is 'failed' — the v1.1-a conditional-trust page-mask
    (word evidence is measured-bad exactly there, 018.7 tile study;
    everywhere else it is either certified-good or unmeasured and
    therefore kept). Frozen once per round: statuses only move at the
    round-end decode_tiles."""
    fp = np.zeros(tuple(pds.spec.page_cells_yx), bool)
    for key, st in pds.tiles.items():
        if st.status != "failed":
            continue
        (ty, tx) = key if pds.n_levels == 1 else key[0]
        fp[ty * ldpc.TILE_CELLS:(ty + 1) * ldpc.TILE_CELLS,
           tx * ldpc.TILE_CELLS:(tx + 1) * ldpc.TILE_CELLS] = True
    out = np.zeros(compose.payload_capacity(pds.spec), bool)
    sel = fp & (pim >= 0)
    out[pim[sel]] = True
    return out


def _readd_trimmed(pds, new_sid: str, obs, keep: np.ndarray,
                   r: int) -> None:
    """Re-add the un-superseded remainder of one observation under a
    keep sid, PRESERVING its quality channel (v1.1 gotcha ii:
    pilot_ber_est is a PROPERTY derived from tile_words + fail_errs +
    meta — an add_placed_fragment re-add loses tile_words and
    weight-floors kept word evidence to 0.05, silently erasing it).
    tile_words stay whole: they are true measurements of this scan's
    pilot-word decodes and remain the honest quality estimate for the
    kept cells (same registration class as the trimmed ones)."""
    if new_sid in pds.scans:
        raise ValueError(f"keep sid collision: {new_sid!r}")
    pds.scans[new_sid] = tilemap.ScanObservation(
        scan_id=new_sid,
        payload_cell_index=np.ascontiguousarray(
            obs.payload_cell_index[keep]),
        payload_llr=np.ascontiguousarray(obs.payload_llr[..., keep]),
        tile_words=dict(obs.tile_words),
        n_windows=obs.n_windows,
        meta={**obs.meta, "trimmed_by_round": r},
        fail_errs=obs.fail_errs)


def fragment_truth_sites(pl, kmask: np.ndarray, truth: np.ndarray
                         ) -> tuple[np.ndarray, np.ndarray]:
    """Certified-label sites inside a placed fragment, in the FRAGMENT's
    own grid frame — the dense twin of place.fragment_pilot_sites (same
    proven rot/clip algebra; source = the truth grid, not the predicted
    pilot field). Pilot sites and truth sites are disjoint by
    construction (pilots live on pilot-layer cells, payload_index_map
    < 0 there)."""
    kr = np.rot90(kmask, pl.rot_k)
    sl = place.overlap_slices(pl.origin_yx, kr.shape, truth.shape)
    if sl is None:
        return np.zeros((0, 2), np.int64), np.zeros(0, np.uint8)
    pys, pxs, fys, fxs = sl
    sub = truth[pys, pxs]
    sel = np.zeros(kr.shape, bool)
    sel[fys, fxs] = (sub >= 0) & kr[fys, fxs]
    ys, xs = np.nonzero(sel)
    vfull = np.zeros(kr.shape, np.uint8)
    vfull[fys, fxs] = np.maximum(sub, 0).astype(np.uint8)
    v = vfull[ys, xs]
    vi = np.full(kr.shape, -1, np.int64)
    vi[ys, xs] = np.arange(ys.size)
    vb = np.rot90(vi, -pl.rot_k)
    iy, ix = np.nonzero(vb >= 0)
    order = vb[iy, ix]
    return np.stack([iy, ix], 1), v[order]


def refit_window(p, backing: float, dpi: float, ang_deg: float,
                 wy: int, wx: int, h: int, w: int, pl,
                 core_win: np.ndarray, truth: np.ndarray, pend):
    """Label-augmented refit of one placed window: refine (angle, phase)
    on pilots UNION truth labels, re-sample from glass, gate-verify the
    pose, dense recal. Returns (bits, core, llr, pl') or None (falls
    back to the driver's own emission — R4: repass never emits past a
    failed gate)."""
    glass, gm = p.img_glass, p.mask_glass
    if glass is None or gm is None:
        return None
    try:
        from paperholo import scannorm
        pitch = float(scannorm.measure_cell_pitch(p.img).pitch_px)
    except Exception:
        pitch = dpi / 600.0 * sd.CD
    im = np.where(gm, glass, np.float32(backing))
    mid = float(np.median(im[gm])) if gm.any() else 128.0
    M, off, oshape = segment.rotate_transform(im.shape, ang_deg)
    ph = segment.phase_scan_glass(im, gm.astype(np.float32), mid, backing,
                                  M, off, oshape, pitch)
    if ph is None:
        return None
    _, dy0, dx0 = ph
    # sites in the WINDOW's fragment frame, then shifted to the full
    # piece grid for glass sampling (the window is a slice of the piece)
    sij_p, sv_p = place.fragment_pilot_sites(pl, (h, w), core_win,
                                             sd.spec, sd.SEED)
    sij_t, sv_t = fragment_truth_sites(pl, core_win, truth)
    if sij_t.shape[0] < MIN_LABEL_SITES:
        return None            # nothing beyond what the driver already had
    sij = np.concatenate([sij_p, sij_t], 0)
    sv = np.concatenate([sv_p, sv_t], 0)
    # raster-sort the union: recal_llrs_from_labels pairs values against
    # means[label_sel], which numpy extracts in ROW-MAJOR order — concat
    # order would scramble ~half the labels (review-confirmed blocker)
    order = np.lexsort((sij[:, 1], sij[:, 0]))
    sij, sv = sij[order], sv[order]
    sij_glass = sij + np.array([wy, wx])
    ang, dyf, dxf, _meta = segment.refine_on_sites(
        glass, gm, backing, ang_deg, pitch, dy0, dx0, sij_glass, sv)
    got = segment.sample_cells_at(glass, gm, backing, ang, pitch,
                                  dyf, dxf, ref_angle_deg=ang_deg)
    if got is None:
        return None
    means, kmask, mid_f = got
    if means.shape[0] < wy + h or means.shape[1] < wx + w:
        return None            # refined grid shrank past the window
    wbits = (means[wy:wy + h, wx:wx + w] < mid_f).astype(np.uint8)
    wkm = kmask[wy:wy + h, wx:wx + w]
    wcore = wkm & core_win
    pl_r = place.place_fragment(wbits, sd.spec, sd.SEED, mask=wcore,
                                pending_cell_mask=pend,
                                gate_true=0.20, gate_decoy=0.20,
                                allow_overhang=True)
    if not (pl_r.ok and (pl_r.rival_mismatch - pl_r.mismatch) >= 0.08
            and pl_r.rot_k == pl.rot_k):
        return None
    lsel = np.zeros((h, w), bool)
    lsel[sij[:, 0], sij[:, 1]] = True
    llr = segment.recal_llrs_from_labels(
        means[wy:wy + h, wx:wx + w], lsel, sv)
    if llr is None:
        return None
    return wbits, wcore, llr, pl_r


def repass_round(pds, done_imgs, images, dpi: float, r: int,
                 erode: int, policy: str) -> dict:
    """One §15.7 round over every image. Returns counters."""
    truth = truth_grid(pds)
    n_labels = int((truth >= 0).sum())
    pim = compose.payload_index_map(pds.spec, pds.seed)
    ks = keystream(pds.seed, "CMYK".index(pds.spec.plane), pds.page,
                   tuple(pds.spec.page_cells_yx))
    cell_px = dpi / 600.0 * sd.CD
    failed_cell = failed_cell_bool(pds, pim)   # trust boundary, frozen
    #                                            at round start (R3)
    n_refit = n_retry = n_super = n_word = n_stakeless = 0
    for img_path in images:
        img = sd.load_img(img_path)
        imgf = np.asarray(img, np.float32)
        pieces = segment.segment_pieces(imgf, cell_px=cell_px, dpi=dpi)
        backing = segment.estimate_backing(imgf)
        pm = np.zeros(tuple(pds.spec.page_cells_yx), bool)
        for key in pds.pending_tiles():
            (ty, tx) = key if pds.n_levels == 1 else key[0]
            pm[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = True
        if not pm.any():
            continue               # R3: fully certified — no-op
        pend = {0: pm}
        for i, p in enumerate(pieces):
            base = f"{img_path.name}/p{i}"
            related = related_sids(pds.scans, base)
            # v1.1-a CONDITIONAL TRUST (018.6 design record): word-path
            # evidence (ctx window decodes, per-window internal
            # geometry) is higher-trust than a placer re-derivation
            # WHERE IT CERTIFIED — but inside FAILED tiles it is
            # measured-bad (018.7: clustered confident-wrong), so a
            # word-touched piece is refit with its emission EXCLUDING
            # the protected word cells; the trim below then supersedes
            # its word evidence on exactly the failed-tile cells and
            # nowhere else. Correlation-only pieces keep v1 semantics
            # (no exclusion).
            word_sids = [s for s in related
                         if pds.scans[s].meta.get("placement_source")
                         == "pilot_words"]
            protected = None
            if word_sids:
                # PROTECTED = word-covered cells OUTSIDE failed tiles
                # (certified-good or unmeasured word evidence). Emission
                # excludes exactly these, so the trim below supersedes
                # word evidence only inside failed tiles; never-observed
                # gap cells under the piece stay emittable (018.8
                # review refinement — see module docstring).
                prot = np.concatenate(
                    [pds.scans[s].payload_cell_index
                     for s in word_sids])
                protected = np.unique(prot[~failed_cell[prot]])
                if not any(
                        failed_cell[pds.scans[s].payload_cell_index].any()
                        for s in related):
                    # no stake: nothing to convert, and re-placing a
                    # mostly-certified piece against the PRUNED pending
                    # set searches with its true pose excluded — skip
                    # rather than lottery the gate
                    n_stakeless += 1
                    continue
            old_sids = related
            # anchor chain (deterministic; failed pieces get their free
            # retry under the shrunken pending set)
            res = sd.anchor_place_piece(p, backing, pend, dpi, erode)
            if res is None:
                continue
            dA, bits, mcell, cllr, means, placed = res
            core_full = sd._core(mcell, erode)
            new_obs = []
            for j, (wy, wx, h, w, pl) in enumerate(placed):
                core_win = core_full[wy:wy + h, wx:wx + w]
                ref = refit_window(p, backing, dpi, p.angle_deg + dA,
                                   wy, wx, h, w, pl, core_win, truth,
                                   pend)
                if ref is not None:
                    wbits, wcore, wllr, pl_use = ref
                elif not old_sids:
                    # RETRIED piece (no prior evidence): every placed
                    # window is new information — emit the anchor-chain
                    # observation as-is
                    wbits = bits[wy:wy + h, wx:wx + w]
                    wcore = core_win
                    wllr = cllr[wy:wy + h, wx:wx + w]
                    pl_use = pl
                else:
                    # observed piece, window did not improve: keep the
                    # driver's evidence for it (review finding — the
                    # fallback would supersede refine-chain LLRs with
                    # plain anchor-chain quality)
                    continue
                new_obs.append((f"repass{r}/{base}/w{j}", wbits, wcore,
                                wllr, pl_use,
                                {"repass_round": r,
                                 "refit": ref is not None,
                                 "conditional_trust": bool(word_sids),
                                 "mismatch": pl_use.mismatch,
                                 "dA": dA}))
            if not new_obs:
                continue
            # emit FIRST (drop-before-emit could strand a piece with no
            # evidence if every emission lands empty — review finding),
            # collect the covered cells, then trim/supersede the old
            covered = []
            emitted_sids = []
            for (nsid, wbits, wcore, wllr, pl_use, meta) in new_obs:
                if sd._emit_placed(pds, nsid, wbits, wcore, wllr,
                                   pl_use, pim, ks, meta,
                                   exclude_idx=protected) > 0:
                    covered.append(pds.scans[nsid].payload_cell_index)
                    emitted_sids.append(nsid)
            if not emitted_sids:
                continue
            cov = np.unique(np.concatenate(covered))
            # R2 at CELL granularity: remove exactly the superseded
            # cells from old observations; evidence for windows that
            # did not refit survives verbatim (review finding). For a
            # word-touched piece, cov excludes the protected cells, so
            # word evidence is trimmed ONLY inside failed tiles (v1.1-a).
            for s in old_sids:
                obs = pds.scans[s]
                keep = ~np.isin(obs.payload_cell_index, cov)
                pds.drop_scan(s)
                n_super += 1
                if keep.any():
                    _readd_trimmed(pds, f"repass{r}/keep/{s}", obs,
                                   keep, r)
            if old_sids:
                n_refit += 1
                n_word += bool(word_sids)
            else:
                n_retry += 1
    counts = pds.decode_tiles(sd.LDPC_RATE, policy=policy)
    return {"round": r, "labels": n_labels, "refit_pieces": n_refit,
            "word_pieces": n_word, "stakeless_skipped": n_stakeless,
            "retried_pieces": n_retry, "superseded_obs": n_super,
            "tiles": counts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--dpi", type=float, required=True)
    ap.add_argument("--state", type=Path, required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--policy", default="weighted_sum")
    ap.add_argument("--emit-erode-cells", type=int, default=4)
    args = ap.parse_args()

    pds, done = pickle.loads(args.state.read_bytes())
    if pds.spec != sd.spec or pds.seed != sd.SEED:
        print("state is not an e018 session state", file=sys.stderr)
        return 2
    # §15.7 A/B-ability: preserve the pre-repass state once (the
    # exists-guard keeps a re-invocation from clobbering the true
    # pre-repass snapshot with a mid-repass one) — review finding
    prepass = args.state.with_suffix(args.state.suffix + ".prepass")
    if not prepass.exists():
        import shutil
        shutil.copy2(args.state, prepass)
        print(f"  pre-repass snapshot: {prepass}", flush=True)
    before = sum(1 for st in pds.tiles.values()
                 if st.status == "certified")
    r0 = resume_round(pds.scans)
    print(f"repass: {before} certified tiles in, "
          f"{len(pds.scans)} observations"
          + (f", resuming at round {r0 + 1}" if r0 else ""), flush=True)
    for r in range(r0 + 1, r0 + args.rounds + 1):
        stats = repass_round(pds, done, args.images, args.dpi, r,
                             args.emit_erode_cells, args.policy)
        now = sum(1 for st in pds.tiles.values()
                  if st.status == "certified")
        print(f"  round {r}: labels {stats['labels']}, refit "
              f"{stats['refit_pieces']} pieces ({stats['word_pieces']} "
              f"word-path, +{stats['retried_pieces']} retried, "
              f"{stats['stakeless_skipped']} stakeless skipped, "
              f"{stats['superseded_obs']} obs superseded) | "
              f"certified {now} (+{now - before})", flush=True)
        sd._save_state(args.state, pds, done)
        if now == before:
            # R3: no new certifications this round — fixed point (the
            # round is deterministic given the label set, and the label
            # set only grows with certifications)
            print("  fixed point — stopping (R3)", flush=True)
            break
        before = now
    syms = fountain.tiles_to_symbols(pds.certified_results(), sd.VSPEC)
    data_out, diag = fountain.volume_decode(syms, sd.VSPEC)
    print(f"  fountain symbols {diag['n_symbols_received']}"
          f"/{sd.VSPEC.k_total} needed", flush=True)
    if data_out is not None:
        return sd._verdict(data_out)
    print("session open — feed more images or scans", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
