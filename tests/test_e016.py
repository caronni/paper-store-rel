"""e016 ARCH-3 preflight (sim-before-toner, CLAUDE.md ground rule).

Gates: byte-identical regeneration + frozen sha; gs render pixel-exact vs
the GT bitmap; simulated-channel window certify (blind acquire -> tile map
-> LDPC r0550 CRC certification, user bits byte-exact vs the fountain
frame); volume bookkeeping sane (K/N 0.80, symbol geometry).

Runs under pytest, or standalone: env/bin/python tests/test_e016.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
EXP = Path(__file__).resolve().parent.parent / "experiments/016-arch3-c2-volume"
sys.path.insert(0, str(EXP))

from paperholo import acquire, fountain, tilemap  # noqa: E402
from paperholo.channel import ChannelParams, print_scan  # noqa: E402
import gen_e016  # noqa: E402

GOLD_PS_SHA = ("796f26094fef1b09220fcc184e86d5930bea11613649981ce249a19f5"
               "7eb5053")
GOLD_DATA_SHA = ("412b9256829ece06243f16ab0456e4a817b1459d64625f28dd09eae2"
                 "6059bb90")

_cache: dict = {}


def _built() -> dict:
    if "mf" not in _cache:
        if not (EXP / "build/e016.ps").exists():
            r = subprocess.run([sys.executable, str(EXP / "gen_e016.py")],
                               capture_output=True, text=True, timeout=600,
                               cwd=str(EXP))
            assert r.returncode == 0, r.stdout + r.stderr
        _cache["mf"] = json.loads(
            (EXP / "build/e016_manifest.json").read_text())
    return _cache["mf"]


def test_determinism_and_golden_sha() -> None:
    mf = _built()
    ps_sha = hashlib.sha256((EXP / "build/e016.ps").read_bytes()).hexdigest()
    assert ps_sha == mf["ps_sha256"] == GOLD_PS_SHA, \
        "e016.ps does not match the frozen golden sha — layout bump needed"
    vspec = gen_e016.make_vspec()
    data = gen_e016.make_data(vspec)
    assert hashlib.sha256(data).hexdigest() == GOLD_DATA_SHA
    assert abs(mf["volume"]["k_over_n"] - 0.80) < 0.001
    assert vspec.k_total == 1387 and vspec.n_symbols_total == 1734
    print(f"  golden sha ok; volume {vspec.data_len_bytes} bytes, "
          f"K/N {vspec.k_total}/{vspec.n_symbols_total}")


def test_gs_render_pixel_exact() -> None:
    """The printed file's dots ARE the composed page (gs-as-printer)."""
    mf = _built()
    png = EXP / "build/e016_render600.png"
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                    "-sDEVICE=pnggray", "-r600", "-o", str(png),
                    str(EXP / "build/e016.ps")], check=True, timeout=600)
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    img = np.asarray(Image.open(png).convert("L"))
    (e,) = [q for q in mf["patches"] if q["name"] == "e016_field"]
    bits = (img[e["y_dots"]:e["y_dots"] + e["h_dots"],
                e["x_dots"]:e["x_dots"] + e["w_dots"]] < 128).astype(np.uint8)
    gt = np.load(EXP / "build" / e["gt"])
    assert np.array_equal(bits, gt), "render differs from GT bitmap"
    print(f"  gs render pixel-exact ({gt.shape} dots)")


def test_window_certifies_byte_exact_and_sim_sanity() -> None:
    """M0 gate, scope-DECLARED (e014 precedent): the sim's c2 channel is
    a known-pessimistic closure floor no blind receiver passes (the suite
    asserts sim-c2 fails CLEAN elsewhere), while the c2 receiver is
    hardware-proven (014.1/014.2). So the pre-toner gate here is (a) the
    CODED machinery byte-exact on the clean channel: blind acquire ->
    tile map -> r0550 CRC certify -> user bits match the fountain frame;
    (b) sim genie-footing BER sanity in the known c2 regime band."""
    vspec = gen_e016.make_vspec()
    data = gen_e016.make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    from paperholo.compose import compose_page
    cp = compose_page(framed["payload_bits"], vspec.compose_spec,
                      vspec.seed, page=0)
    y0c, x0c = 900, 600                       # interior region, cells
    crop = cp.plane_bits[y0c * 2:(y0c + 200) * 2, x0c * 2:(x0c + 200) * 2]
    # (b) sim genie-footing sanity (e014 smoke idiom)
    scan = print_scan(crop, ChannelParams(seed=16, scan_seed=17,
                                          geometry=False))
    cells = scan.reshape(200, 4, 200, 4).mean((1, 3))
    hard = (cells < np.median(cells)).astype(np.uint8)
    ber = float(np.mean(hard != cp.cell_values[y0c:y0c + 200,
                                               x0c:x0c + 200]))
    assert 0.02 < ber < 0.30, f"sim c2 regime off: {ber}"
    # (a) clean-channel coded round-trip, fully blind
    clean = np.repeat(np.repeat((1.0 - crop).astype(np.float64), 2, 0),
                      2, 1)
    res = acquire.acquire_and_decode(clean, vspec.compose_spec, vspec.seed,
                                     detector="ctx", calibrate=True,
                                     cell_px_nominal=4.0)
    assert res.ok, res.diagnostics
    pds = tilemap.PageDecodeState(vspec.compose_spec, vspec.seed, page=0)
    pds.add_acquire_result("sim", res)
    counts = pds.decode_tiles("r0550", policy="best_scan",
                              min_coverage=0.999)
    assert counts["certified"] >= 4, counts
    gt = {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
          for e in framed["per_tile"]}
    user = np.concatenate(
        [fountain.volume_encode(data, vspec).page_user_bits[0]])
    n_bits = 0
    for t, st in pds.tiles.items():
        if st.status == "certified" and st.payload_bits is not None:
            off, cap = gt[t]
            assert np.array_equal(st.payload_bits, user[off:off + cap]), t
            n_bits += int(st.payload_bits.size)
    print(f"  clean-channel coded window: {counts['certified']} tiles "
          f"certified, {n_bits} user bits byte-exact; sim genie BER "
          f"{100*ber:.1f}% (known c2 regime)")


if __name__ == "__main__":
    for fn in (test_determinism_and_golden_sha,
               test_gs_render_pixel_exact,
               test_window_certifies_byte_exact_and_sim_sanity):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
