"""COLOR CHANNEL format axis (layout_version 4, IMPL-1) — write-side gates.

Covers, per the COLOR-DESIGN D1-D7 build contract:
- pilots v4: PilotLayout(version=4) valid; b"pilot-values-v4" label; the v4
  word is a LUMA object (plane "K" enforced); v3<->v4 cross-format rejection
  rides the value scramble ALONE (C_v4 == C_v3 as codes — the C_v3 subset
  C_v2 precedent, verified end-to-end both ways).
- dust: determinism, pilot-site exclusion, tile-periodic positions,
  per-tile pure quota, APERIODIC values across tiles and pages (R3).
- compose cmy8-c3: determinism + a PROVISIONAL page sha (the FINAL golden
  freezes at gen_e017 — if this constant moves before e017 is built, the
  v4 format drifted: bump it CONSCIOUSLY, with a log entry, never silently);
  per-level payload round-trip; pilot sites render dark-ALL-planes/white;
  dust cells render their states; payload index map excludes pilot+dust.
- emission: gs tiffsep per-plane pixel-exact vs the GT npy (e004 precedent);
  put_cmyk_bitmap composite is the only content.
- ldpc: dust-aware shorten mask; 3-level encode/decode clean round-trip.
- fountain: level-stratified volume byte-exact round-trip through the FULL
  write stack (frame -> compose -> extract -> LLR -> decode -> certify ->
  volume_decode); repair-path recovery; K-path guards.

Runs under pytest, or standalone: env/bin/python tests/test_color_format.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paperholo import compose, dust, fountain, ldpc, pilots  # noqa: E402
from paperholo.encodings import EncodingError, get_encoding  # noqa: E402
from paperholo.modulation import rng  # noqa: E402

SEED = b"paper-store/test-color-format"
DUST = dust.DustLayout(sites_per_tile=24, pure_quota=3)
GEO_2X2 = dict(tiles_x=2, tiles_per_page=4)

# PROVISIONAL golden (pinned 2026-07-10 from the IMPL-1 build; the FINAL
# format anchor is gen_e017's page sha). sha256 over cell_values bytes of
# the 120x120 test page below. If this moves, the v4 derivation changed:
# that is a format event even pre-print — bump deliberately, log it.
# BUMPED 2026-07-10 (IMPL-4, deliberate, logged in experiments/017): probe
# P1 froze RENDER_DARK = "CM" (was the a-priori "CMY" triple; old sha
# a29983ef...) — the one word-rendering flip the constant existed for.
PROVISIONAL_CELLS_SHA = (
    "66f72134c0038d46b4579574d8182964579b5fc8ead1964f22a6cf1a7fab518b")


def _spec(page_cells: tuple[int, int] = (120, 120)) -> compose.ComposeSpec:
    return compose.ComposeSpec(
        layout_version=4, encoding_id="cmy8-c3", plane="CMY",
        pilot=pilots.PilotLayout(version=4), page_cells_yx=page_cells,
        dust=DUST)


def _payload(spec: compose.ComposeSpec, label: bytes = b"payload"
             ) -> list[np.ndarray]:
    cap = compose.payload_capacity(spec)
    g = rng(SEED, label)
    return [g.integers(0, 2, cap, dtype=np.uint8) for _ in range(3)]


# ---------------------------------------------------------------------------
# pilots v4
# ---------------------------------------------------------------------------

def test_pilots_v4_layout_and_labels() -> None:
    l4 = pilots.PilotLayout(version=4)
    assert pilots.PILOT_VALUES_LABEL_V4 == b"pilot-values-v4"
    # sites are the SHARED v2 derivation (frozen contract: no new sites label)
    assert np.array_equal(pilots.site_positions_tile(l4, SEED),
                          pilots.site_positions_tile(
                              pilots.PilotLayout(version=2), SEED))
    # v4 word code == the v3 code instance; t_acq = 13 single-stage
    from paperholo import bch
    assert pilots.code_for_layout(l4) is bch.CODE_V3
    assert pilots.t_acq_for_layout(l4) == 13


def test_pilots_v4_word_is_luma_object() -> None:
    l4 = pilots.PilotLayout(version=4)
    for plane in ("C", "M", "Y"):
        try:
            pilots.value_keystream_tile(l4, SEED, plane)
            raise AssertionError(f"v4 keystream accepted plane {plane!r}")
        except ValueError:
            pass
    w = pilots.encode_word(l4, SEED, "K", 0, 1, 1, **GEO_2X2)
    info = pilots.decode_word(w, l4, SEED, "K", 13, **GEO_2X2)
    assert info is not None and info["counter"] == 3
    assert (info["page"], info["ptile_y"], info["ptile_x"]) == (0, 1, 1)


def test_pilots_v3_v4_cross_rejection_value_level() -> None:
    """C_v4 == C_v3 as codes: rejection MUST ride the value scramble alone
    (the C_v3 subset C_v2 precedent). Verified end-to-end both ways on
    every counter of a 2x2 page."""
    l3 = pilots.PilotLayout(version=3)
    l4 = pilots.PilotLayout(version=4)
    for c in range(4):
        ty, tx = divmod(c, 2)
        w4 = pilots.encode_word(l4, SEED, "K", 0, ty, tx, **GEO_2X2)
        w3 = pilots.encode_word(l3, SEED, "K", 0, ty, tx, **GEO_2X2)
        assert not np.array_equal(w3, w4)
        assert pilots.decode_word(w4, l3, SEED, "K", 13, **GEO_2X2) is None, \
            "v3 receiver accepted a v4 word — implicit signaling broken"
        assert pilots.decode_word(w3, l4, SEED, "K", 13, **GEO_2X2) is None, \
            "v4 receiver accepted a v3 word — implicit signaling broken"


def test_pilots_v2_v4_cross_rejection_value_level() -> None:
    """The OTHER nesting cell: C_v4 == C_v3 SUBSET C_v2, so v2<->v4
    rejection must also ride the value scramble alone (same seed, both
    directions, full decode strength — the nesting the original
    C_v3-subset-C_v2 verification covered for v3)."""
    l2 = pilots.PilotLayout(version=2)
    l4 = pilots.PilotLayout(version=4)
    for c in range(4):
        ty, tx = divmod(c, 2)
        w4 = pilots.encode_word(l4, SEED, "K", 0, ty, tx, **GEO_2X2)
        w2 = pilots.encode_word(l2, SEED, "K", 0, ty, tx)
        assert not np.array_equal(w2, w4)
        assert pilots.decode_word(w4, l2, SEED, "K", 10) is None, \
            "v2 receiver accepted a v4 word — implicit signaling broken"
        assert pilots.decode_word(w2, l4, SEED, "K", 13, **GEO_2X2) is None, \
            "v4 receiver accepted a v2 word — implicit signaling broken"


# ---------------------------------------------------------------------------
# dust
# ---------------------------------------------------------------------------

def test_dust_positions_deterministic_and_exclude_pilots() -> None:
    pl = pilots.PilotLayout(version=4)
    pos1 = dust.dust_positions_tile(pl, DUST, SEED)
    pos2 = dust.dust_positions_tile(pl, DUST, SEED)
    assert np.array_equal(pos1, pos2)
    assert pos1.shape == (DUST.sites_per_tile, 2)
    assert pos1.dtype == np.int64
    # raster-sorted canonical order, all in-tile, distinct
    flat = pos1[:, 0] * pl.period_cells + pos1[:, 1]
    assert np.array_equal(flat, np.sort(flat))
    assert np.unique(flat).size == flat.size
    assert pos1.min() >= 0 and pos1.max() < pl.period_cells
    # disjoint from pilot sites
    ppos = pilots.site_positions_tile(pl, SEED)
    pset = {tuple(r) for r in ppos.tolist()}
    assert not (pset & {tuple(r) for r in pos1.tolist()})
    # different seed -> different set (sanity that the seed enters)
    pos3 = dust.dust_positions_tile(pl, DUST, b"other-seed")
    assert not np.array_equal(pos1, pos3)


def test_dust_states_quota_and_aperiodic_values() -> None:
    pl = pilots.PilotLayout(version=4)
    seen = []
    for tile_index in range(8):
        st = dust.dust_states_tile(DUST, SEED, 0, tile_index)
        st2 = dust.dust_states_tile(DUST, SEED, 0, tile_index)
        assert np.array_equal(st, st2)                    # deterministic
        assert st.shape == (DUST.sites_per_tile,)
        assert st.max() < 8
        counts = np.bincount(st, minlength=8)
        for pure in dust.PURE_STATES:                      # per-tile quota
            assert counts[pure] >= DUST.pure_quota, (tile_index, pure)
        seen.append(st)
    # R3: values must NOT repeat across tiles (positions may)
    for i in range(len(seen)):
        for j in range(i + 1, len(seen)):
            assert not np.array_equal(seen[i], seen[j]), (i, j)
    # ... nor across pages at the same tile index
    st_p1 = dust.dust_states_tile(DUST, SEED, 1, 0)
    assert not np.array_equal(seen[0], st_p1)


def test_dust_states_page_layout() -> None:
    pl = pilots.PilotLayout(version=4)
    shape = (120, 120)
    ds = dust.dust_states_page(shape, pl, DUST, SEED, page=0)
    assert ds.shape == (3, 120, 120) and ds.dtype == np.uint8
    mask = dust.dust_site_mask(shape, pl, DUST, SEED)
    assert mask.sum() == 4 * DUST.sites_per_tile          # 2x2 pilot tiles
    assert not ds[:, ~mask].any()                          # zero off-dust
    # per-plane bits at dust cells reproduce the per-tile state draw
    pos = dust.dust_positions_tile(pl, DUST, SEED)
    p = pl.period_cells
    for ty in range(2):
        for tx in range(2):
            st = dust.dust_states_tile(DUST, SEED, 0, ty * 2 + tx)
            for lv in range(3):
                got = ds[lv, ty * p + pos[:, 0], tx * p + pos[:, 1]]
                assert np.array_equal(got, (st >> lv) & 1)


def test_dust_layout_validation() -> None:
    for bad in (dict(sites_per_tile=0, pure_quota=0),
                dict(sites_per_tile=5, pure_quota=2),      # 3q > sites
                dict(sites_per_tile=10, pure_quota=1, version=3)):
        try:
            dust.DustLayout(**bad)
            raise AssertionError(f"DustLayout accepted {bad}")
        except ValueError:
            pass
    # sites_per_tile larger than the tile's non-pilot cells refuses
    pl = pilots.PilotLayout(version=4)
    big = dust.DustLayout(sites_per_tile=3501, pure_quota=0)
    try:
        dust.dust_positions_tile(pl, big, SEED)
        raise AssertionError("3501 dust sites in a 3500-free tile accepted")
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# compose (cmy8-c3)
# ---------------------------------------------------------------------------

def test_compose_spec_v4_validation() -> None:
    pl4 = pilots.PilotLayout(version=4)
    # v4 requires dust
    try:
        compose.ComposeSpec(layout_version=4, encoding_id="cmy8-c3",
                            plane="CMY", pilot=pl4, page_cells_yx=(120, 120))
        raise AssertionError("v4 without dust accepted")
    except ValueError:
        pass
    # dust on a v3/K spec refuses
    try:
        compose.ComposeSpec(layout_version=3,
                            pilot=pilots.PilotLayout(version=3), dust=DUST)
        raise AssertionError("dust on a v3 spec accepted")
    except ValueError:
        pass
    # cmy8 wants plane "CMY"
    try:
        compose.ComposeSpec(layout_version=4, encoding_id="cmy8-c3",
                            plane="K", pilot=pl4, page_cells_yx=(120, 120),
                            dust=DUST)
        raise AssertionError("cmy8 with plane 'K' accepted")
    except ValueError:
        pass
    # kcell at layout_version 4 refuses (D7: v4 is the color format)
    try:
        compose.ComposeSpec(layout_version=4, encoding_id="kcell-c3",
                            pilot=pl4, dust=DUST)
        raise AssertionError("kcell-c3 at v4 accepted")
    except ValueError:
        pass
    spec = _spec()
    assert spec.n_levels == 3 and spec.cell_dots == 3
    k_spec = compose.ComposeSpec()                        # K default intact
    assert k_spec.n_levels == 1 and k_spec.dust is None


def test_compose_determinism_and_provisional_sha() -> None:
    spec = _spec()
    payload = _payload(spec)
    cp1 = compose.compose_page(payload, spec, SEED, page=0)
    cp2 = compose.compose_page([p.copy() for p in payload], spec, SEED, page=0)
    assert np.array_equal(cp1.cell_values, cp2.cell_values)
    assert np.array_equal(cp1.plane_bits, cp2.plane_bits)
    assert cp1.cell_values.shape == (3, 120, 120)
    assert cp1.plane_bits.shape == (3, 360, 360)
    sha = hashlib.sha256(
        np.ascontiguousarray(cp1.cell_values, np.uint8).tobytes()).hexdigest()
    assert sha == PROVISIONAL_CELLS_SHA, (
        f"PROVISIONAL v4 page sha moved: {sha} — the v4 derivation changed. "
        "Pre-e017 this is bumpable, but ONLY deliberately (log it); after "
        "gen_e017 freezes its golden this is a layout_version event.")


def test_compose_payload_roundtrip_all_levels() -> None:
    spec = _spec()
    payload = _payload(spec)
    cp = compose.compose_page(payload, spec, SEED, page=2)
    back = compose.extract_payload_levels(cp.cell_values, spec, SEED, page=2)
    for lv in range(3):
        assert np.array_equal(back[lv], payload[lv]), f"level {lv}"
    # wrong page -> keystream mismatch -> garbage (near-half wrong)
    bad = compose.extract_payload_levels(cp.cell_values, spec, SEED, page=3)
    for lv in range(3):
        frac = float((bad[lv] != payload[lv]).mean())
        assert 0.4 < frac < 0.6, frac
    # levels use DISTINCT plane keystreams: cross-assignment breaks
    swapped = compose.extract_payload_levels(
        cp.cell_values[[1, 0, 2]], spec, SEED, page=2)
    frac = float((swapped[0] != payload[1]).mean())
    assert 0.4 < frac < 0.6, frac


def test_compose_pilot_and_dust_rendering() -> None:
    spec = _spec()
    cp = compose.compose_page(_payload(spec), spec, SEED, page=0)
    # pilot sites: word bit 1 -> the P1-frozen fixed CM 2-ink state (C and M
    # planes ink, Y white); bit 0 -> all-plane white (COLOR-DESIGN D3)
    assert compose.RENDER_DARK == "CM"
    pos = pilots.site_positions_tile(spec.pilot, SEED)
    p = spec.pilot.period_cells
    geo = spec.word_geometry
    for ty in range(2):
        for tx in range(2):
            word = pilots.encode_word(spec.pilot, SEED, "K", 0, ty, tx, **geo)
            got = cp.cell_values[:, ty * p + pos[:, 0], tx * p + pos[:, 1]]
            for lv, pl in enumerate("CMY"):
                expect = word if pl in compose.RENDER_DARK \
                    else np.zeros_like(word)
                assert np.array_equal(got[lv], expect), (ty, tx, lv)
    # dust cells carry their states
    assert cp.dust_mask is not None
    ds = dust.dust_states_page(spec.page_cells_yx, spec.pilot, spec.dust,
                               SEED, 0)
    assert np.array_equal(cp.cell_values[:, cp.dust_mask],
                          ds[:, cp.dust_mask])
    # masks are disjoint; capacity accounting closes exactly
    assert not (cp.pilot_mask & cp.dust_mask).any()
    h, w = spec.page_cells_yx
    assert (compose.payload_capacity(spec)
            == h * w - int(cp.pilot_mask.sum()) - int(cp.dust_mask.sum()))


def test_payload_index_map_excludes_pilot_and_dust() -> None:
    spec = _spec()
    idx = compose.payload_index_map(spec, SEED)
    pm = pilots.pilot_site_mask(spec.page_cells_yx, spec.pilot, SEED)
    dm = dust.dust_site_mask(spec.page_cells_yx, spec.pilot, spec.dust, SEED)
    assert (idx[pm] == -1).all() and (idx[dm] == -1).all()
    live = idx[~(pm | dm)]
    assert live.min() == 0
    assert live.max() == compose.payload_capacity(spec) - 1
    assert np.unique(live).size == live.size
    # K path unchanged: extract_payload refuses multi-level specs
    try:
        compose.extract_payload(np.zeros((3, 120, 120), np.uint8), spec,
                                SEED, 0)
        raise AssertionError("extract_payload accepted a cmy8 spec")
    except ValueError:
        pass


def test_emit_composed_gs_tiffsep_pixel_exact() -> None:
    """The e004 render gate for the v4 composite: gs does not screen, so
    each tiffsep separation must equal the addressed plane bitmap exactly,
    and nothing else may mark the page."""
    from PIL import Image
    spec = _spec()
    cp = compose.compose_page(_payload(spec), spec, SEED, page=0)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "color_fmt.ps"
        mf = compose.emit_composed(cp, out, title="test color page",
                                   artifact="colorfmt", experiment="tests")
        mf2 = compose.emit_composed(cp, Path(td) / "again.ps",
                                    title="test color page",
                                    artifact="colorfmt", experiment="tests")
        assert mf["ps_sha256"] == mf2["ps_sha256"]        # deterministic
        assert len(mf["patches"]) == 3
        assert {p["planes"][0] for p in mf["patches"]} == {"C", "M", "Y"}
        assert all(p["composite_of"] == "colorfmt_field"
                   for p in mf["patches"])
        assert all(p["params"]["emission"] == "cmyk_image"
                   for p in mf["patches"])
        assert mf["patches"][0]["params"]["dust_sites_per_tile"] == 24
        subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                        "-sDEVICE=tiffsep", "-r600",
                        "-o", str(Path(td) / "sep_%d.tif"), str(out)],
                       check=True, capture_output=True)
        for plane, sep_name in (("C", "Cyan"), ("M", "Magenta"),
                                ("Y", "Yellow"), ("K", "Black")):
            img = np.asarray(
                Image.open(Path(td) / f"sep_1({sep_name}).tif")) < 128
            if plane == "K":                     # no K content anywhere
                assert not img.any()
                continue
            e = next(p for p in mf["patches"] if p["planes"] == [plane])
            x, y, w, h = (e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"])
            gt = np.load(Path(td) / e["gt"]).astype(bool)
            crop = img[y:y + h, x:x + w]
            assert np.array_equal(crop, gt), \
                f"{plane}: {int((crop != gt).sum())}/{gt.size} px differ"
            outside = img.copy()
            outside[y:y + h, x:x + w] = False
            assert not outside.any(), f"{plane}: marks outside the field"


# ---------------------------------------------------------------------------
# encodings registry
# ---------------------------------------------------------------------------

def test_encodings_registry_row_cmy8() -> None:
    enc = get_encoding("cmy8-c3")
    assert enc.kind == "cell_mlc"
    assert enc.planes == ("C", "M", "Y")
    assert enc.cell_dots == 3 and enc.n_states == 8
    assert enc.emission == "composite"
    # state integer s: bit l = level l ink (matches dust.PURE_STATES)
    for s, name in enumerate(enc.state_names):
        for lv, pl in enumerate("CMY"):
            assert ((s >> lv) & 1) == int(pl in name), (s, name)
    # the symbol-domain scramble/emitter refuse with a clear message
    from paperholo.encodings import encode_field, key_symbols
    for fn in (lambda: key_symbols(enc, (4, 4), SEED),
               lambda: encode_field(enc, np.zeros((4, 4), np.int64), SEED)):
        try:
            fn()
            raise AssertionError("cmy8 symbol-domain path did not refuse")
        except EncodingError as e:
            assert "compose" in str(e)
    # list/info surfaces work
    from paperholo.encodings import describe, list_table
    assert "cmy8-c3" in list_table()
    assert "--emit refuses" in describe(enc)


# ---------------------------------------------------------------------------
# ldpc (dust-aware shortening + level-aware framing)
# ---------------------------------------------------------------------------

def test_ldpc_shorten_mask_dust_aware() -> None:
    spec = _spec()
    lspec = ldpc.LDPC_LADDER["r0700"]
    # 64-cell tile (0,0) of the 120-cell page: fully on-page
    mask = ldpc.tile_shorten_mask((0, 0), spec, SEED)
    pm = pilots.pilot_site_mask(spec.page_cells_yx, spec.pilot, SEED)
    dm = dust.dust_site_mask(spec.page_cells_yx, spec.pilot, spec.dust, SEED)
    expect = (pm | dm)[:64, :64].ravel()
    assert np.array_equal(mask, expect)
    # K spec unchanged: pilot-only shortening
    k_spec = compose.ComposeSpec(layout_version=3,
                                 pilot=pilots.PilotLayout(version=3))
    k_mask = ldpc.tile_shorten_mask((0, 0), k_spec, SEED)
    k_pm = pilots.pilot_site_mask(k_spec.page_cells_yx, k_spec.pilot, SEED)
    assert np.array_equal(k_mask, k_pm[:64, :64].ravel())
    # v3/v4 share the site derivation -> same pilot pattern; the capacity
    # drop vs the dust-free mask is exactly the in-window dust count
    assert np.array_equal(k_pm[:64, :64], pm[:64, :64])
    assert ldpc.tile_user_capacity(mask, lspec) \
        == ldpc.tile_user_capacity(k_mask, lspec) - int(dm[:64, :64].sum())


def test_ldpc_three_level_page_roundtrip() -> None:
    spec = _spec()
    specs = [ldpc.LDPC_LADDER[r] for r in ("r0550", "r0700", "r0625")]
    caps = [ldpc.page_user_capacity(spec, SEED, s) for s in specs]
    users = [rng(SEED, b"u%d" % i).integers(0, 2, c, dtype=np.uint8)
             for i, c in enumerate(caps)]
    enc = ldpc.encode_page(users, spec, SEED, specs)
    assert [pb.size for pb in enc["payload_bits"]] \
        == [compose.payload_capacity(spec)] * 3
    assert enc["user_capacity_bits"] == caps
    cp = compose.compose_page(enc["payload_bits"], spec, SEED, page=0)
    ext = compose.extract_payload_levels(cp.cell_values, spec, SEED, 0)
    idx = np.arange(ext[0].size, dtype=np.int64)
    llrs = [np.where(e == 1, 8.0, -8.0) for e in ext]
    per_level = ldpc.decode_page_tiles(llrs, idx, spec, SEED, specs)
    assert len(per_level) == 3
    for lv in range(3):
        assert all(t.ok for t in per_level[lv]), lv
        got = np.concatenate([t.payload_bits for t in per_level[lv]])
        assert np.array_equal(got, users[lv]), f"level {lv}"
    # malformed level args refuse
    try:
        ldpc.encode_page(users[:2], spec, SEED, specs)
        raise AssertionError("2-level user list accepted on a 3-level spec")
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# fountain (level-stratified volumes)
# ---------------------------------------------------------------------------

RATES = ("r0550", "r0700", "r0625")


def _vspec(n_pages: int = 2, fill: float = 0.7,
           page_cells: tuple[int, int] = (120, 120)) -> tuple:
    spec = _spec(page_cells)
    probe = fountain.VolumeSpec(n_pages=n_pages, data_len_bytes=1, seed=SEED,
                                compose_spec=spec, n_levels=3,
                                ldpc_rate_ids=RATES)
    cap_bits = sum(probe.source_capacity_bits_level(lv) for lv in range(3))
    data_len = max(1, int(fill * cap_bits) // 8)
    vspec = fountain.VolumeSpec(n_pages=n_pages, data_len_bytes=data_len,
                                seed=SEED, compose_spec=spec, n_levels=3,
                                ldpc_rate_ids=RATES)
    data = rng(SEED, b"vdata").integers(0, 256, data_len,
                                        dtype=np.uint8).tobytes()
    return spec, vspec, data


def test_volume_spec_level_validation() -> None:
    spec = _spec()
    # 3-level volume needs 3 rungs and a 3-level page
    try:
        fountain.VolumeSpec(n_pages=1, data_len_bytes=10, seed=SEED,
                            compose_spec=spec, n_levels=3)
        raise AssertionError("3-level volume without rate rungs accepted")
    except ValueError:
        pass
    try:
        fountain.VolumeSpec(n_pages=1, data_len_bytes=10, seed=SEED,
                            n_levels=3, ldpc_rate_ids=RATES)  # K page
        raise AssertionError("3-level volume on a K page accepted")
    except ValueError:
        pass
    try:
        fountain.VolumeSpec(n_pages=1, data_len_bytes=10, seed=SEED,
                            compose_spec=spec, n_levels=1)
        raise AssertionError("1-level volume on a cmy8 page accepted")
    except ValueError:
        pass
    v = fountain.VolumeSpec(n_pages=1, data_len_bytes=10, seed=SEED,
                            compose_spec=spec, n_levels=3,
                            ldpc_rate_ids=RATES)
    # scalar single-level accessors refuse on stratified volumes
    for attr in ("symbol_bits", "k_total", "n_blocks", "k_per_block",
                 "ldpc_spec", "source_capacity_bits"):
        try:
            getattr(v, attr)
            raise AssertionError(f"scalar {attr} served a 3-level volume")
        except ValueError:
            pass
    # boundaries partition exactly
    b = v.data_byte_boundaries()
    assert b[0] == 0 and b[-1] == v.data_len_bytes
    assert sum(v.data_len_bytes_level(lv) for lv in range(3)) \
        == v.data_len_bytes

    # tiles_to_symbols validates the level BEFORE symbol_bits_level (an
    # out-of-range positive level must be the contracted ValueError, not
    # an IndexError escaping from VolumeSpec.rate_ids[level])
    class _Tr:
        ok = True
        payload_bits = np.zeros(4096, np.uint8)
        tile_yx = (1, 1)
    for bad_lv in (3, -1):
        try:
            fountain.tiles_to_symbols([(0, bad_lv, _Tr())], v)
            raise AssertionError(f"level {bad_lv} accepted")
        except ValueError:
            pass


def test_fountain_level_stratified_full_stack_byte_exact() -> None:
    """The write-side certification gate: frame -> compose -> extract ->
    LLR -> per-level LDPC certify -> tiles_to_symbols -> volume_decode
    byte-exact on the clean channel, fully through the printed format."""
    spec, vspec, data = _vspec()
    framed = fountain.encode_volume_pages(data, vspec)
    assert len(framed) == vspec.n_pages
    specs = [fountain.ldpc.LDPC_LADDER[r] for r in RATES]
    tile_results = []
    for page in range(vspec.n_pages):
        cp = compose.compose_page(framed[page]["payload_bits"], spec, SEED,
                                  page=page)
        ext = compose.extract_payload_levels(cp.cell_values, spec, SEED, page)
        idx = np.arange(ext[0].size, dtype=np.int64)
        llrs = [np.where(e == 1, 8.0, -8.0) for e in ext]
        for lv, results in enumerate(
                ldpc.decode_page_tiles(llrs, idx, spec, SEED, specs)):
            for tr in results:
                tile_results.append((page, lv, tr))
    syms = fountain.tiles_to_symbols(tile_results, vspec)
    out, diag = fountain.volume_decode(syms, vspec)
    assert diag["solved_all"], diag
    assert out == data
    # per-level S differs with the rung: the streams really are stratified
    s = [vspec.symbol_bits_level(lv) for lv in range(3)]
    assert len(set(s)) == 3, s


def test_fountain_repair_recovery_and_esi() -> None:
    # 240-cell page -> 9 interior tiles/page; fill 0.55 -> ~5 source + ~4
    # repair symbols per level (kb big enough that dense-RLF repair rows are
    # not single-coin-flip degenerate; verified deterministic on this seed)
    spec, vspec, data = _vspec(n_pages=1, fill=0.55, page_cells=(240, 240))
    enc = fountain.volume_encode(data, vspec)
    syms = {}
    for lv in range(3):
        nb = vspec.n_blocks_level(lv)
        kt = vspec.k_total_level(lv)
        assert 2 < kt < vspec.n_symbols_total  # real repair headroom
        for t in range(vspec.n_symbols_total):
            b, i = t % nb, t // nb
            key = (lv, b, i)
            # esi_of_tile inverts tile_of_symbol per level
            page, tile_yx = fountain.tile_of_symbol(vspec, b, i, level=lv)
            assert fountain.esi_of_tile(vspec, page, tile_yx, level=lv) \
                == key
            syms[key] = enc.symbol(b, i, level=lv)
        del syms[(lv, 0, 0)]                   # kill two sources per level
        del syms[(lv, 0, 1)]
    out, diag = fountain.volume_decode(syms, vspec)
    assert diag["solved_all"] and out == data
    # dropping ALL of one level's symbols -> under-ranked, honest failure
    syms_bad = {k: v for k, v in syms.items() if k[0] != 1}
    out2, diag2 = fountain.volume_decode(syms_bad, vspec)
    assert out2 is None and not diag2["solved_all"]
    assert "partial_data" in diag2


def test_fountain_k_path_guards_unchanged() -> None:
    """Single-level volumes: labels/keys byte-identical (the e016 golden
    coded round-trip is the deep anchor; this is the cheap in-file spot
    check that the color code path cannot leak into K volumes)."""
    kv = fountain.VolumeSpec(n_pages=1, data_len_bytes=4000, seed=SEED)
    assert kv.n_levels == 1 and kv.rate_ids == ("r0700",)
    # level accessors agree with the scalar path at level 0
    assert kv.symbol_bits_level(0) == kv.symbol_bits
    assert kv.k_per_block_level(0) == kv.k_per_block
    # generator rows: the frozen label (no level byte) — pin one row
    row = fountain.generator_row(kv, 0, kv.k_per_block[0] + 1)
    g = rng(SEED, fountain.ROW_LABEL + (0).to_bytes(4, "little")
            + (kv.k_per_block[0] + 1).to_bytes(4, "little"))
    assert np.array_equal(row,
                          g.integers(0, 2, kv.k_per_block[0]).astype(np.uint8))
    # ldpc_rate_ids on a single-level volume refuses
    try:
        fountain.VolumeSpec(n_pages=1, data_len_bytes=10, seed=SEED,
                            ldpc_rate_ids=("r0700",))
        raise AssertionError("ldpc_rate_ids accepted on a 1-level volume")
    except ValueError:
        pass


if __name__ == "__main__":
    for fn in sorted(k for k in list(globals()) if k.startswith("test_")):
        globals()[fn]()
        print(f"PASS {fn}")
