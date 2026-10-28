"""E023 payload-tile decoding: synthetic-e022-state fixtures + one chain.

The primary fixtures construct an e022 v2.2 session state DIRECTLY (known
poses over a rendered coded page) — pinning the ink-positive score
convention, the keystream flip, and the slot-raster mapping byte-exact
against encode-side truth (the 012.3 incident class) without coupling
every test to two upstream stages. Exactly one full-chain test runs
e021 -> e022 -> e023.
"""
from __future__ import annotations

import hashlib
import pickle
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import compose, ldpc, payloaddec, pilotsearch  # noqa: E402
from paperholo.formats import FormatDescriptor  # noqa: E402

INK, PAPER, BACK = 45.0, 205.0, 245.0
PITCH = 8.0


def _descriptor(seed: bytes = b"paper-store/e023-test") -> FormatDescriptor:
    return FormatDescriptor("e023-test", seed, 3, "kcell-c3", (600, 480),
                            ldpc_rate="r0550")


def _coded_page(descriptor: FormatDescriptor, rng: np.random.Generator
                ) -> tuple[np.ndarray, np.ndarray, dict]:
    """(cell_values (H,W) uint8, user_bits, encode accounting)."""
    spec = descriptor.spec()
    ldpc_spec = ldpc.LDPC_LADDER[descriptor.ldpc_rate]
    capacity = ldpc.page_user_capacity(spec, descriptor.seed, ldpc_spec)
    user = rng.integers(0, 2, capacity, dtype=np.uint8)
    framed = ldpc.encode_page(user, spec, descriptor.seed, ldpc_spec)
    composed = compose.compose_page(framed["payload_bits"], spec,
                                    descriptor.seed, page=0)
    return composed.cell_values, user, framed


def _render_cells(values: np.ndarray, rng: np.random.Generator,
                  *, noise: float = 2.0) -> np.ndarray:
    px = int(PITCH)
    img = np.where(np.kron(values, np.ones((px, px), np.uint8)) > 0,
                   INK, PAPER).astype(np.float32)
    img += rng.normal(0.0, noise, img.shape).astype(np.float32)
    return np.clip(img, 0.0, 255.0)


def _placed_window(page_cells: np.ndarray, wy: int, wx: int, h: int, w: int,
                   *, rot_k: int = 0, origin_px: tuple[float, float],
                   scan_id: str = "s000",
                   redundant: bool = False) -> pilotsearch.PlacedWindow:
    """A GT placement: local window covers page cells via forward rot_k
    bookkeeping identical to e022's (pilotsearch._rotated_points)."""
    local = np.stack(np.meshgrid(np.arange(h), np.arange(w),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    rotated = pilotsearch._rotated_points(local, (h, w), rot_k)
    page_yx = rotated + np.array([wy, wx], np.int64)
    inside = ((page_yx[:, 0] >= 0) & (page_yx[:, 0] < page_cells[0])
              & (page_yx[:, 1] >= 0) & (page_yx[:, 1] < page_cells[1]))
    pose = pilotsearch.AffinePose(
        origin_yx=(float(origin_px[0]), float(origin_px[1])),
        jacobian_yx=((PITCH, 0.0), (0.0, PITCH)),
        angle_deg=0.0, pitch_px=PITCH, phase_yx=(0.0, 0.0))
    return pilotsearch.PlacedWindow(
        region_index=0, window=pilotsearch.Window(0, 0, h, w, h * w),
        page=0, origin_yx=(wy, wx), rot_k=rot_k, method="synthetic",
        mismatch=0.0, validation_mismatch=0.0, rival_mismatch=None,
        support=h * w, pose=pose, elapsed_s=0.0, scan_id=scan_id,
        redundant=redundant,
        page_cells_yx=page_yx[inside].astype(np.int32))


def _session_payload(descriptor: FormatDescriptor, scans: list[dict]) -> dict:
    return {
        "magic": "e022-session-v1", "version": 3,
        "format_id": descriptor.format_id, "seed": descriptor.seed,
        "cell_dots": descriptor.cell_dots,
        "page_cells_yx": tuple(descriptor.page_cells_yx),
        "pages": (0,), "dpi": 1600.0, "scans": scans,
    }


def _scan_row(tmp_path: Path, scan_id: str, image: np.ndarray,
              placements: list[pilotsearch.PlacedWindow]) -> dict:
    from PIL import Image
    path = tmp_path / f"{scan_id}.png"
    Image.fromarray(image.astype(np.uint8)).save(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    result = pilotsearch.SearchResult(placements=placements)
    return {"scan_id": scan_id, "source_path": str(path),
            "source_sha256": sha, "source_size": path.stat().st_size,
            "dpi": 1600.0, "region_count": 1, "c_dots": 3,
            "cell_pitch_px": PITCH, "angle_hints": 1, "result": result}


def _grid_windows(page_cells: tuple[int, int], span: int = 200,
                  stride: int = 160) -> list[tuple[int, int, int, int]]:
    hh, ww = page_cells
    ys = sorted({min(y, hh - span) for y in range(0, hh, stride)})
    xs = sorted({min(x, ww - span) for x in range(0, ww, stride)})
    return [(y, x, span, span) for y in ys for x in xs]


def _write_state(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "e022_state.pkl"
    path.write_bytes(pickle.dumps(payload))
    return path


def _per_tile_user(user: np.ndarray, framed: dict
                   ) -> dict[tuple[int, int], np.ndarray]:
    return {tuple(row["tile_yx"]):
            user[row["user_offset"]:row["user_offset"] + row["user_bits"]]
            for row in framed["per_tile"]}


# ---------------------------------------------------------------------------
# geometry pin
# ---------------------------------------------------------------------------

def test_unrotate_points_inverts_e022_forward() -> None:
    rng = np.random.default_rng(2301)
    for k in range(4):
        h, w = 37, 53
        pts = np.stack([rng.integers(0, h, 200), rng.integers(0, w, 200)],
                       axis=1).astype(np.int64)
        fwd = pilotsearch._rotated_points(pts, (h, w), k)
        back = payloaddec.unrotate_points(fwd, (h, w), k)
        assert np.array_equal(back, pts), k


# ---------------------------------------------------------------------------
# the sign/keystream/slot-raster pin: full coverage certifies byte-exact
# ---------------------------------------------------------------------------

def test_full_coverage_certifies_byte_exact(tmp_path: Path) -> None:
    descriptor = _descriptor()
    rng = np.random.default_rng(2302)
    values, user, framed = _coded_page(descriptor, rng)
    image = _render_cells(values, rng)
    placements = [
        _placed_window(np.array(values.shape), y, x, h, w,
                       origin_px=(y * PITCH + PITCH / 2 - 0.5,
                                  x * PITCH + PITCH / 2 - 0.5),
                       redundant=(y, x) == (0, 0) and False)
        for (y, x, h, w) in _grid_windows(values.shape)
    ]
    payload = _session_payload(
        descriptor, [_scan_row(tmp_path, "s000", image, placements)])
    session = payloaddec.load_e022_session(_write_state(tmp_path, payload))
    state = payloaddec.run_session(session, descriptor)

    gt = _per_tile_user(user, framed)
    n_cert = n_deg = 0
    for key, out in state.tiles.items():
        want = gt[out.tile_yx]
        if want.size == 0:
            assert out.state in ("degenerate", "unobserved"), key
            n_deg += 1
            continue
        assert out.state == "certified", (key, out.state)
        assert np.array_equal(out.user_bits, want), key
        n_cert += 1
    assert n_cert >= 60 and n_deg >= 5
    summary = state.summary()
    assert summary["fatal"] == []
    assert summary["divergence_max"] is not None
    assert summary["divergence_max"] < 0.02
    # calibrate-or-refuse never fired on these full windows
    assert all(not row["refused"]
               for s in state.scans for row in s.window_rows)


def test_rot90_window_certifies(tmp_path: Path) -> None:
    """One whole-page window observed through a rot_k=1 scan pins the
    rotation bookkeeping end to end."""
    descriptor = _descriptor(b"paper-store/e023-rot")
    rng = np.random.default_rng(2303)
    values, user, framed = _coded_page(descriptor, rng)
    local_values = np.rot90(values, -1)          # rot90(local, 1) == page
    image = _render_cells(local_values, rng)
    h, w = local_values.shape
    placements = [_placed_window(
        np.array(values.shape), 0, 0, h, w, rot_k=1,
        origin_px=(PITCH / 2 - 0.5, PITCH / 2 - 0.5))]
    payload = _session_payload(
        descriptor, [_scan_row(tmp_path, "s000", image, placements)])
    session = payloaddec.load_e022_session(_write_state(tmp_path, payload))
    state = payloaddec.run_session(session, descriptor)
    gt = _per_tile_user(user, framed)
    certified = [out for out in state.tiles.values()
                 if out.state == "certified"]
    assert len(certified) >= 60
    for out in certified:
        assert np.array_equal(out.user_bits, gt[out.tile_yx])


# ---------------------------------------------------------------------------
# refusal / floor / integrity branches
# ---------------------------------------------------------------------------

def test_calibrate_or_refuse_on_label_starved_window(tmp_path: Path) -> None:
    descriptor = _descriptor(b"paper-store/e023-starve")
    rng = np.random.default_rng(2304)
    values, _user, _framed = _coded_page(descriptor, rng)
    image = _render_cells(values, rng)
    placements = [_placed_window(          # 12x12 cells: ~4 pilot sites
        np.array(values.shape), 96, 96, 12, 12,
        origin_px=(96 * PITCH + PITCH / 2 - 0.5,
                   96 * PITCH + PITCH / 2 - 0.5))]
    payload = _session_payload(
        descriptor, [_scan_row(tmp_path, "s000", image, placements)])
    session = payloaddec.load_e022_session(_write_state(tmp_path, payload))
    state = payloaddec.run_session(session, descriptor)
    rows = state.scans[0].window_rows
    assert rows[0]["refused"] and rows[0]["reason"] == "calibrate_or_refuse"
    assert all(out.state != "certified" for out in state.tiles.values())


def test_attempt_floor_blocks_decode_pre_decode(tmp_path: Path) -> None:
    descriptor = _descriptor(b"paper-store/e023-floor")
    rng = np.random.default_rng(2305)
    values, _user, _framed = _coded_page(descriptor, rng)
    image = _render_cells(values, rng)
    # a 46x46-cell window fully inside tile (2,2): ~2057 informative
    # payload cells < k_eff ~ 2126 (just under the floor), while its ~59
    # pilot sites still clear calibrate-or-refuse
    placements = [_placed_window(
        np.array(values.shape), 137, 137, 46, 46,
        origin_px=(137 * PITCH + PITCH / 2 - 0.5,
                   137 * PITCH + PITCH / 2 - 0.5))]
    payload = _session_payload(
        descriptor, [_scan_row(tmp_path, "s000", image, placements)])
    session = payloaddec.load_e022_session(_write_state(tmp_path, payload))
    state = payloaddec.run_session(session, descriptor)
    touched = [out for out in state.tiles.values()
               if out.n_informative_best > 0]
    assert touched
    for out in touched:
        assert out.state == "below_attempt_floor"
        assert out.attempts == 0                 # gate fired PRE-decode
        assert 0 < out.n_informative_best < out.k_eff
    assert state.n_attempts == 0


def test_e022_version_and_contradiction_refusals(tmp_path: Path) -> None:
    descriptor = _descriptor(b"paper-store/e023-refuse")
    payload = _session_payload(descriptor, [])
    payload["version"] = 2
    with pytest.raises(ValueError, match="STATE_VERSION"):
        payloaddec.load_e022_session(_write_state(tmp_path, payload))

    payload = _session_payload(descriptor, [])
    result = pilotsearch.SearchResult()
    tile = pilotsearch.PilotTileEvidence(
        page=0, tile_y=1, tile_x=1, expected_bits=np.zeros(100, np.uint8))
    tile.bch_ok = False                       # contradictory decoded address
    result.tiles[(0, 1, 1)] = tile
    payload["scans"] = [{"scan_id": "s000", "source_path": "/nonexistent",
                         "source_sha256": "0" * 64, "dpi": 1600.0,
                         "result": result}]
    with pytest.raises(payloaddec.FatalIntegrityError, match="CONTRADICT"):
        payloaddec.load_e022_session(_write_state(tmp_path, payload))


def test_conflicting_certifications_fatal() -> None:
    descriptor = _descriptor(b"paper-store/e023-conflict")
    rng = np.random.default_rng(2306)
    _values, user, framed = _coded_page(descriptor, rng)
    state = payloaddec.DecodeState(descriptor, "r0550", (0,), ())
    spec, seed = state.spec, state.seed
    tile_yx = (2, 2)
    mask = state.shorten_mask(tile_yx)
    gt = _per_tile_user(user, framed)[tile_yx]
    _cw, tx_bits = ldpc.encode_tile(gt, mask, state.ldpc_spec)
    pidx = ldpc._tile_payload_indices(tile_yx, spec, seed, mask)
    llr = (1.0 - 2.0 * tx_bits.astype(np.float64)) * -8.0   # positive = 1
    out = state.outcome(0, tile_yx)
    out.state = "certified"
    out.user_bits = (1 - gt).astype(np.uint8)     # planted wrong payload
    out.certified_by = "s000"
    with pytest.raises(payloaddec.FatalIntegrityError, match="conflicting"):
        state._attempt(out, llr, pidx, "s001")


# ---------------------------------------------------------------------------
# persistence: resume semantics + determinism
# ---------------------------------------------------------------------------

def test_resume_append_only_and_fingerprint(tmp_path: Path) -> None:
    descriptor = _descriptor(b"paper-store/e023-resume")
    rng = np.random.default_rng(2307)
    values, _user, _framed = _coded_page(descriptor, rng)
    image = _render_cells(values, rng)
    windows = _grid_windows(values.shape)[:2]
    rows = [_scan_row(tmp_path, f"s{i:03d}", image, [
        _placed_window(np.array(values.shape), y, x, h, w,
                       origin_px=(y * PITCH + PITCH / 2 - 0.5,
                                  x * PITCH + PITCH / 2 - 0.5),
                       scan_id=f"s{i:03d}")
        for (y, x, h, w) in windows]) for i in range(2)]

    one = payloaddec.load_e022_session(
        _write_state(tmp_path, _session_payload(descriptor, rows[:1])))
    state = payloaddec.run_session(one, descriptor)
    state_path = tmp_path / "e023.pkl"
    payloaddec.save_state(state_path, state)

    both = payloaddec.load_e022_session(
        _write_state(tmp_path, _session_payload(descriptor, rows)))
    resumed = payloaddec.load_state(state_path, descriptor)
    assert payloaddec.resume_check(resumed, both) == 1
    resumed = payloaddec.run_session(both, descriptor, state=resumed)
    assert [s.scan_id for s in resumed.scans] == ["s000", "s001"]

    mutated = payloaddec.load_e022_session(
        _write_state(tmp_path, _session_payload(descriptor, rows[::-1])))
    with pytest.raises(ValueError, match="prefix"):
        payloaddec.resume_check(payloaddec.load_state(state_path, descriptor),
                                mutated)


def test_determinism_and_state_roundtrip(tmp_path: Path) -> None:
    descriptor = _descriptor(b"paper-store/e023-det")
    rng = np.random.default_rng(2308)
    values, _user, _framed = _coded_page(descriptor, rng)
    image = _render_cells(values, rng)
    placements = [
        _placed_window(np.array(values.shape), y, x, h, w,
                       origin_px=(y * PITCH + PITCH / 2 - 0.5,
                                  x * PITCH + PITCH / 2 - 0.5))
        for (y, x, h, w) in _grid_windows(values.shape)[:4]]
    payload = _session_payload(
        descriptor, [_scan_row(tmp_path, "s000", image, placements)])
    path = _write_state(tmp_path, payload)

    session = payloaddec.load_e022_session(path)
    a = payloaddec.run_session(session, descriptor)
    b = payloaddec.run_session(payloaddec.load_e022_session(path),
                               descriptor)
    pa = pickle.dumps(a.to_payload())
    pb = pickle.dumps(b.to_payload())
    assert pa == pb
    restored = payloaddec.DecodeState.from_payload(
        pickle.loads(pa), descriptor)
    assert pickle.dumps(restored.to_payload()) == pa


# ---------------------------------------------------------------------------
# the ONE full-chain integration test: render -> e021 -> e022 -> e023
# ---------------------------------------------------------------------------

def test_full_chain_e021_e022_e023(tmp_path: Path) -> None:
    from PIL import Image
    from scipy import ndimage as ndi

    from paperholo import platen

    descriptor = _descriptor(b"paper-store/e023-chain")
    rng = np.random.default_rng(2309)
    values, user, framed = _coded_page(descriptor, rng)
    piece = values[60:420, 60:420]               # 360x360 cells on backing
    px = int(PITCH)
    field = np.where(np.kron(piece, np.ones((px, px), np.uint8)) > 0,
                     INK, PAPER).astype(np.float32)
    canvas = np.full((field.shape[0] + 320, field.shape[1] + 320), BACK,
                     np.float32)
    canvas[160:160 + field.shape[0], 160:160 + field.shape[1]] = field
    canvas = ndi.gaussian_filter(canvas, 1.1)
    canvas += rng.normal(0.0, 2.0, canvas.shape).astype(np.float32)
    canvas = np.clip(canvas, 0.0, 255.0)

    survey = platen.detect_payload_regions(canvas, dpi=1600.0)
    assert survey.regions, "e021 found no candidate region"
    result = pilotsearch.search_survey(
        canvas, survey, descriptor, pages=(0,), scan_dpi=1600.0,
        config=pilotsearch.SearchConfig(bch_first=False, min_support=20),
        scan_id="s000")
    assert any(state == "accepted" for state in result.region_states.values())

    path = tmp_path / "chain.png"
    Image.fromarray(canvas.astype(np.uint8)).save(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = _session_payload(descriptor, [{
        "scan_id": "s000", "source_path": str(path), "source_sha256": sha,
        "dpi": 1600.0, "result": result}])
    session = payloaddec.load_e022_session(_write_state(tmp_path, payload))
    state = payloaddec.run_session(session, descriptor)

    gt = _per_tile_user(user, framed)
    certified = [out for out in state.tiles.values()
                 if out.state == "certified"]
    assert len(certified) >= 10, payloaddec.full_tile_states(state)
    for out in certified:
        assert np.array_equal(out.user_bits, gt[out.tile_yx]), out.tile_yx
    assert state.summary()["fatal"] == []
