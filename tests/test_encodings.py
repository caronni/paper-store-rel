"""encodings tests: registry dims math, symbol validation, the format-axis
scramble (determinism + reversibility + the pinned keystream definition), RLL
constraint validity (independently measured runs), emit determinism (sha-
stable pages, manifest + GT integrity), gs pixel-exact render pre-flight, and
measured-simulator round-trips (the M0 gate for this seam).

Round-trip envelopes (documented, loose gates):
- kcell-c3, geometry=False, naive hard decode: simulator reference ~3.6%
  (M0 fidelity anchor vs the 3.74% hardware c3 anchor); measured here
  3.2-4.0% across scan seeds -> gate 0 < BER < 0.10, null ~0.5.
- a3-7st-c3, per-plane screened_composite sims, nearest-class on per-plane
  cell means: ~0.50 symbol error (the simulator's first-order screen model is
  pessimistic vs the hardware QDA-family ~0.35-0.40 at c3); chance = 6/7 =
  0.857 -> gate err < 0.60 with a shifted-prediction null > 0.65.

Runs under pytest, or standalone: python tests/test_encodings.py
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paperholo import encodings as enc
from paperholo.metrics import ber
from paperholo.modulation import dots_to_cells_hard, keystream, rng

SEED = b"paper-store/test-encodings"
ALL_IDS = ["kcell-c2", "kcell-c3", "kcell-c4", "a3-7st-c3", "a4-8st-c4",
           "cmy8-c3", "rll-i2w3"]


def _expect_error(fn, *args, needle: str = "", **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except enc.EncodingError as e:
        assert needle in str(e), f"error lacks {needle!r}: {e}"
        return
    raise AssertionError(f"{getattr(fn, '__name__', fn)} did not raise")


def _cell_means(scan: np.ndarray, cell_px: int) -> np.ndarray:
    h = scan.shape[0] // cell_px * cell_px
    w = scan.shape[1] // cell_px * cell_px
    return scan[:h, :w].reshape(h // cell_px, cell_px,
                                w // cell_px, cell_px).mean(axis=(1, 3))


def _measure_min_runs(a: np.ndarray) -> tuple[int, int]:
    """Independent run scanner (does NOT reuse the module's validator):
    minimum maximal-run length of (ink, white) over rows and columns."""
    min_ink, min_white = a.size, a.size
    for b in (a, a.T):
        for line in b:
            change = np.flatnonzero(np.diff(line.astype(np.int8))) + 1
            starts = np.concatenate(([0], change))
            ends = np.concatenate((change, [line.size]))
            for v, ln in zip(line[starts], ends - starts):
                if v == 1:
                    min_ink = min(min_ink, int(ln))
                else:
                    min_white = min(min_white, int(ln))
    return min_ink, min_white


_SRC = Path(__file__).resolve().parents[1] / "src"


def _cli(*args: str) -> subprocess.CompletedProcess:
    # pin THIS tree's package for the subprocess (the venv's editable
    # install may point at a different checkout; in-process imports already
    # resolve here via the suite's sys.path inserts)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "paperholo.encodings", *args],
                          capture_output=True, text=True, env=env)


# ---------------------------------------------------------------------------

def test_registry_info_dims() -> None:
    assert list(enc.ENCODINGS) == ALL_IDS
    # hand-computed: 21 mm -> round(21/25.4*600) = 496 dots; 30 mm -> 709
    e3 = enc.get_encoding("kcell-c3")
    d = enc.field_dims(e3, 21.0, 30.0)
    assert (d["w_dots"], d["h_dots"]) == (496, 709)
    assert (d["cells_x"], d["cells_y"]) == (165, 236)   # 496//3, 709//3
    assert d["n_cells"] == 38940
    assert abs(d["raw_entropy_bits"] - 38940.0) < 1e-9  # 1 b/cell
    a3 = enc.get_encoding("a3-7st-c3")
    d3 = enc.field_dims(a3, 21.0, 30.0)
    assert d3["n_cells"] == 38940
    assert abs(d3["raw_entropy_bits"] - 38940 * math.log2(7)) < 1e-6
    a4 = enc.get_encoding("a4-8st-c4")
    d4 = enc.field_dims(a4, 21.0, 30.0)
    assert (d4["cells_x"], d4["cells_y"]) == (124, 177)  # 496//4, 709//4
    assert abs(d4["raw_entropy_bits"] - 124 * 177 * 3) < 1e-9
    dr = enc.field_dims(enc.get_encoding("rll-i2w3"), 21.0, 30.0)
    assert dr["n_dots"] == 496 * 709 and "cells_x" not in dr
    d2 = enc.field_dims(enc.get_encoding("kcell-c2"), 21.0, 30.0)
    assert d2["n_cells"] == 248 * 354
    # densities / entropies
    assert abs(e3.cells_per_mm2() - (600 / 25.4 / 3) ** 2) < 1e-9
    assert abs(a3.entropy_bits_per_cell - math.log2(7)) < 1e-12
    assert enc.get_encoding("rll-i2w3").entropy_bits_per_cell is None
    # registry rows carry the LAYERS.md record + requirements
    for e in enc.ENCODINGS.values():
        assert e.record and e.scan_mode and e.sync_note, e.encoding_id
        assert e.emission in ("clean_mask", "composite")


def test_validation_errors() -> None:
    a3 = enc.get_encoding("a3-7st-c3")
    ok = rng(SEED, b"val").integers(0, 7, size=(8, 8), dtype=np.uint8)
    bad_range = ok.copy()
    bad_range[0, 0] = 7
    _expect_error(enc.encode_field, a3, bad_range, SEED,
                  needle="alphabet range")
    _expect_error(enc.encode_field, a3, ok.ravel(), SEED, needle="2-D")
    _expect_error(enc.encode_field, a3, ok.astype(np.float64), SEED,
                  needle="integer")
    _expect_error(enc.encode_field, a3, ok[:0], SEED, needle="empty")
    # rll is seed-only, unmistakably
    _expect_error(enc.encode_field, "rll-i2w3", ok, SEED,
                  needle="NOT IMPLEMENTED")
    _expect_error(enc.scramble_symbols, enc.get_encoding("rll-i2w3"), ok,
                  SEED, needle="NOT IMPLEMENTED")
    _expect_error(enc.generate_rll_field, "kcell-c3", 60, 60, SEED,
                  needle="encode_field")
    _expect_error(enc.get_encoding, "nope", needle="unknown encoding")
    # binary alphabet range enforced too
    bits2 = rng(SEED, b"val2").integers(0, 2, size=(6, 6), dtype=np.uint8)
    bits2[0, 0] = 2
    _expect_error(enc.encode_field, "kcell-c2", bits2, SEED,
                  needle="alphabet range")


def test_scramble_format_determinism_reversibility() -> None:
    # binary: pinned to modulation.keystream XOR (module docstring FORMAT)
    e3 = enc.get_encoding("kcell-c3")
    payload = rng(SEED, b"scr/b").integers(0, 2, size=(40, 50), dtype=np.uint8)
    printed = enc.scramble_symbols(e3, payload, SEED, page=2)
    pinned = np.bitwise_xor(payload, keystream(SEED, 3, 2, payload.shape))
    assert np.array_equal(printed, pinned), "binary scramble != keystream XOR"
    assert np.array_equal(
        enc.descramble_symbols(e3, printed, SEED, page=2), payload)
    assert np.array_equal(printed, enc.scramble_symbols(e3, payload, SEED,
                                                        page=2))
    assert not np.array_equal(printed, payload)
    # alphabet: (payload + U) mod n, reversible, page/seed-sensitive
    a3 = enc.get_encoding("a3-7st-c3")
    sym = rng(SEED, b"scr/a").integers(0, 7, size=(30, 30), dtype=np.uint8)
    scr = enc.scramble_symbols(a3, sym, SEED, page=0)
    assert np.array_equal(enc.descramble_symbols(a3, scr, SEED, page=0), sym)
    assert not np.array_equal(scr, sym)
    assert scr.max() < 7
    assert not np.array_equal(scr, enc.scramble_symbols(a3, sym, SEED, page=1))
    assert not np.array_equal(scr, enc.scramble_symbols(a3, sym, b"other", 0))
    # scrambled field is DC-balanced-ish (keystream uniformity, DESIGN 4.2)
    counts = np.bincount(scr.ravel(), minlength=7)
    assert counts.min() > 0.5 * sym.size / 7


def test_rll_constraints_and_determinism() -> None:
    f = enc.generate_rll_field("rll-i2w3", 240, 320, SEED)
    bits = f.plane_bits["K"]
    assert bits.shape == (240, 320) and set(np.unique(bits)) <= {0, 1}
    min_ink, min_white = _measure_min_runs(bits)
    assert min_ink >= 2, f"ink run {min_ink} < 2"
    assert min_white >= 3, f"white run {min_white} < 3"
    assert 0.2 < bits.mean() < 0.8
    assert 0.0 < f.stats["sampler_entropy_bits_per_dot"] < 1.0
    # deterministic in (seed, page); seed-sensitive
    f2 = enc.generate_rll_field("rll-i2w3", 240, 320, SEED)
    assert np.array_equal(bits, f2.plane_bits["K"])
    f3 = enc.generate_rll_field("rll-i2w3", 240, 320, b"other-seed")
    assert not np.array_equal(bits, f3.plane_bits["K"])
    # transposed path (width > the 900-dot row-DP cap) still constraint-valid
    ft = enc.generate_rll_field("rll-i2w3", 60, 950, SEED)
    assert ft.plane_bits["K"].shape == (60, 950)
    mi, mw = _measure_min_runs(ft.plane_bits["K"])
    assert mi >= 2 and mw >= 3
    assert "transposed" in ft.stats["sampler"]
    _expect_error(enc.generate_rll_field, "rll-i2w3", 950, 950, SEED,
                  needle="both axes")
    _expect_error(enc.generate_rll_field, "rll-i2w3", 3, 320, SEED,
                  needle="too small")


def test_emit_sha_stable_manifest_and_gt() -> None:
    e3 = enc.get_encoding("kcell-c3")
    payload = rng(SEED, b"emit/b").integers(0, 2, size=(60, 60),
                                            dtype=np.uint8)
    fld = enc.encode_field(e3, payload, SEED)
    a3 = enc.get_encoding("a3-7st-c3")
    sym = rng(SEED, b"emit/a").integers(0, 7, size=(40, 40), dtype=np.uint8)
    fla = enc.encode_field(a3, sym, SEED)
    placed = [enc.PlacedField(fld, 15.0, 20.0, name="b"),
              enc.PlacedField(fla, 15.0, 60.0, name="a")]
    shas, texts = [], []
    for _ in range(2):                     # sha-stable across two runs
        with tempfile.TemporaryDirectory() as td:
            mf = enc.emit_page(placed, Path(td) / "page.ps",
                               header="test page", end_sentinel=True)
            ps = (Path(td) / "page.ps").read_text()
            texts.append(ps)
            shas.append(mf["ps_sha256"])
            assert mf["ps_sha256"] == hashlib.sha256(ps.encode()).hexdigest()
            # manifest round-trips through json and matches the field geometry
            mf2 = json.loads(
                (Path(td) / "page_manifest.json").read_text())
            assert mf2["ps_sha256"] == mf["ps_sha256"]
            fe = {f["name"]: f for f in mf2["fields"]}
            assert fe["b"]["w_dots"] == 180 and fe["b"]["h_dots"] == 180
            assert fe["b"]["cells_yx"] == [60, 60]
            assert fe["a"]["n_states"] == 7
            assert fe["b"]["seed_label"] == SEED.decode()
            assert "keystream" in fe["b"]["scramble"]
            assert "mod 7" in fe["a"]["scramble"]
            # GT files: payload + per-plane dots, loadable, exact
            gt = Path(td) / "page_gt"
            assert np.array_equal(np.load(gt / "b_payload.npy"), payload)
            assert np.array_equal(np.load(gt / "b_dots_K.npy"),
                                  fld.plane_bits["K"])
            for p in "CMY":
                assert np.array_equal(np.load(gt / f"a_dots_{p}.npy"),
                                      fla.plane_bits[p])
            # stream order: masks before composites before END sentinel
            i_mask = ps.index("imagemask")
            i_comp = ps.index(">> image")
            i_sent = ps.index("END sentinel")
            assert i_mask < i_comp < i_sent
            assert "imagemask" not in ps[i_sent:]
    assert shas[0] == shas[1] and texts[0] == texts[1]


def test_emit_geometry_errors() -> None:
    e3 = enc.get_encoding("kcell-c3")
    payload = rng(SEED, b"geo").integers(0, 2, size=(60, 60), dtype=np.uint8)
    fld = enc.encode_field(e3, payload, SEED)        # 180 dots = 7.62 mm
    a3 = enc.get_encoding("a3-7st-c3")
    sym = rng(SEED, b"geo/a").integers(0, 7, size=(40, 40), dtype=np.uint8)
    fla = enc.encode_field(a3, sym, SEED)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "p.ps"
        _expect_error(enc.emit_page, [enc.PlacedField(fld, 1.0, 20.0)], out,
                      needle="margin")
        # mask/composite pair closer than the 1.5 mm coexistence clearance
        _expect_error(
            enc.emit_page,
            [enc.PlacedField(fld, 15.0, 20.0),
             enc.PlacedField(fla, 15.0 + 7.62 + 0.5, 20.0)],
            out, needle="002.2")
        # field under the header reservation band
        _expect_error(enc.emit_page, [enc.PlacedField(fld, 15.0, 8.0)], out,
                      header="x", needle="header")
        # >= 1.5 mm apart is legal
        enc.emit_page([enc.PlacedField(fld, 15.0, 20.0),
                       enc.PlacedField(fla, 15.0 + 7.62 + 1.6, 20.0)], out)


def test_roundtrip_sim_kcell_c3() -> None:
    """M0 gate: encode -> measured simulator -> hard decode -> descramble.
    Envelope: sim c3 reference ~3.6% (vs 3.74% hardware anchor); loose gate
    0 < BER < 0.10; shifted-payload null ~0.5."""
    from paperholo.channel import ChannelParams, print_scan

    e3 = enc.get_encoding("kcell-c3")
    payload = rng(SEED, b"rt/kc3").integers(0, 2, size=(60, 60),
                                            dtype=np.uint8)
    fld = enc.encode_field(e3, payload, SEED, page=0)
    p = ChannelParams(seed=7, geometry=False)
    scan = print_scan(fld.plane_bits["K"], p)
    rx_printed = dots_to_cells_hard(scan, 3 * p.scan_oversample)
    rx_payload = enc.descramble_symbols(e3, rx_printed, SEED, page=0)
    b = ber(payload, rx_payload)
    null = ber(np.roll(payload, 1, axis=1), rx_payload)
    print(f"  kcell-c3 sim round-trip BER {b:.4f} (null {null:.4f})")
    assert 0.0 < b < 0.10, b
    assert 0.4 < null < 0.6, null


def test_roundtrip_sim_a3_7st_c3() -> None:
    """M0 gate for the composite track: per-plane screened_composite sims,
    nearest-class on per-plane cell means. Envelope: ~0.50 symbol error
    (first-order screen model, pessimistic vs hardware QDA ~0.35-0.40);
    chance 6/7 = 0.857; shifted-prediction null ~0.73."""
    from paperholo.channel import ChannelParams, print_scan

    a3 = enc.get_encoding("a3-7st-c3")
    sym = rng(SEED, b"rt/a3").integers(0, 7, size=(50, 50), dtype=np.uint8)
    fld = enc.encode_field(a3, sym, SEED, page=0)
    printed = fld.printed_symbols
    feats = []
    for i, plane in enumerate(a3.planes):
        pp = ChannelParams(plane=plane, emission="screened_composite",
                           seed=20 + i, geometry=False)
        scan = print_scan(fld.plane_bits[plane], pp)
        feats.append(_cell_means(scan, 3 * pp.scan_oversample).ravel())
    F = np.stack(feats, axis=1)
    labels = printed.ravel()
    means = np.stack([F[labels == s].mean(axis=0) for s in range(7)])
    pred = np.argmin(((F[:, None, :] - means[None]) ** 2).sum(-1), axis=1)
    err = float(np.mean(pred != labels))
    null = float(np.mean(np.roll(pred.reshape(printed.shape), 1,
                                 axis=0).ravel() != labels))
    # descramble is a per-cell bijection: payload error == printed error
    rx = enc.descramble_symbols(
        a3, pred.reshape(printed.shape).astype(np.uint8), SEED, page=0)
    err_payload = float(np.mean(rx != sym))
    print(f"  a3 sim symbol err {err:.4f} (payload {err_payload:.4f}, "
          f"null {null:.4f})")
    assert 0.0 < err < 0.60, err
    assert null > 0.65, null
    assert abs(err_payload - err) < 1e-12


def test_gs_pixel_exact_kcell_c3() -> None:
    """Pre-flight idiom: gs render at device resolution must reproduce the
    addressed K bitmap pixel-exactly at the manifest position."""
    if shutil.which("gs") is None:
        print("SKIP (no ghostscript)")
        return
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    e3 = enc.get_encoding("kcell-c3")
    payload = rng(SEED, b"gs/kc3").integers(0, 2, size=(80, 80),
                                            dtype=np.uint8)
    fld = enc.encode_field(e3, payload, SEED)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "gs.ps"
        mf = enc.emit_page([enc.PlacedField(fld, 20.0, 40.0)], out,
                           header="gs preflight", end_sentinel=True)
        png = Path(td) / "gs.png"
        subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                        "-sDEVICE=pnggray", "-r600", "-o", str(png),
                        str(out)], check=True, timeout=120)
        img = np.asarray(Image.open(png).convert("L"))
        fe = mf["fields"][0]
        x, y, w, h = (fe["x_dots"], fe["y_dots"], fe["w_dots"], fe["h_dots"])
        crop = (img[y: y + h, x: x + w] < 128).astype(np.uint8)
        gt = fld.plane_bits["K"]
        assert np.array_equal(crop, gt), \
            f"{int((crop != gt).sum())}/{gt.size} px differ"


def test_cli_registry_and_emit() -> None:
    r = _cli("--list")
    assert r.returncode == 0
    for eid in ALL_IDS:
        assert eid in r.stdout
    r = _cli("--info", "rll-i2w3")
    assert r.returncode == 0
    assert "NOT IMPLEMENTED" in r.stdout
    assert "ink run >= 2" in r.stdout and "white run >= 3" in r.stdout
    r = _cli("--info", "a3-7st-c3", "--field-mm", "21x30")
    assert r.returncode == 0
    assert "165x236 cells = 38940 cells" in r.stdout
    assert "133.3" in r.stdout            # measured-record pointer surfaces
    r = _cli("--info", "nope")
    assert r.returncode == 2 and "unknown encoding" in r.stderr
    with tempfile.TemporaryDirectory() as td:
        syms = Path(td) / "syms.npy"
        np.save(syms, rng(SEED, b"cli").integers(0, 2, size=(50, 50),
                                                 dtype=np.uint8))
        out = Path(td) / "out.ps"
        r = _cli("--emit", "kcell-c3", "--symbols", str(syms), "--out",
                 str(out), "--seed-label", "cli-test", "--header", "hi")
        assert r.returncode == 0, r.stderr
        mf = json.loads((Path(td) / "out_manifest.json").read_text())
        assert mf["ps_sha256"] == hashlib.sha256(
            out.read_bytes()).hexdigest()
        assert mf["fields"][0]["seed_label"] == "cli-test"
        # rll refuses symbols, loudly
        r = _cli("--emit", "rll-i2w3", "--symbols", str(syms), "--out",
                 str(out))
        assert r.returncode == 2 and "NOT IMPLEMENTED" in r.stderr
        # rll emits from seed + field size; GT field is constraint-valid
        out2 = Path(td) / "rll.ps"
        r = _cli("--emit", "rll-i2w3", "--field-mm", "20x15", "--out",
                 str(out2))
        assert r.returncode == 0, r.stderr
        bits = np.load(Path(td) / "rll_gt" / "f0_dots_K.npy")
        assert bits.shape == (354, 472)   # round(15/25.4*600), round(20/...)
        mi, mw = _measure_min_runs(bits)
        assert mi >= 2 and mw >= 3


if __name__ == "__main__":
    fns = [test_registry_info_dims,
           test_validation_errors,
           test_scramble_format_determinism_reversibility,
           test_rll_constraints_and_determinism,
           test_emit_sha_stable_manifest_and_gt,
           test_emit_geometry_errors,
           test_roundtrip_sim_kcell_c3,
           test_roundtrip_sim_a3_7st_c3,
           test_gs_pixel_exact_kcell_c3,
           test_cli_registry_and_emit]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
