#!/usr/bin/env python3
"""e018 pre-print recoverability gate (sim-before-toner, CLAUDE.md ground rule).

Proves — BEFORE any print — that a separate confetti session can recover the
archived tar.gz byte-exact:

  1. determinism        : gen reproduces the same data + ps sha
  2. payload integrity  : recovered bytes ARE the tar.gz; `tar xz` -> source
  3. volume recovery    : fountain.volume_decode from certified tiles == data,
                          AND from a fragment-sized SUBSET of tiles (the
                          confetti claim: close from ~half the page)
  4. blind receiver     : clean-channel acquire on a c3 window certifies
                          tiles byte-exact vs the fountain frame
  5. sim channel sanity : c3 genie-footing BER in the measured band

Run:  ../../env/bin/python verify_e018.py   (or PYTHONPATH=../../src python3)
"""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import time
import types
from pathlib import Path

import numpy as np

import gen_e018
from paperholo import acquire, fountain, tilemap
from paperholo.channel import ChannelParams, print_scan
from paperholo.compose import compose_page

EXP = Path(__file__).resolve().parent
SRC = EXP.parents[1] / "src" / "paperholo"


def _frame():
    spec = gen_e018.make_spec()
    vspec = gen_e018.make_vspec()
    data = gen_e018.make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    return spec, vspec, data, framed


def test_determinism() -> None:
    d1 = gen_e018.make_targz()
    d2 = gen_e018.make_targz()
    assert d1 == d2, "tar.gz is not deterministic"
    mf = json.loads((EXP / "build/e018_manifest.json").read_text())
    assert mf["volume"]["data_sha256"] == hashlib.sha256(d1).hexdigest()
    ps_sha = hashlib.sha256((EXP / "build/e018.ps").read_bytes()).hexdigest()
    assert ps_sha == mf["ps_sha256"]
    kn = mf["volume"]["k_over_n"]
    assert 0.45 <= kn <= 0.56, kn
    print(f"  determinism ok; K/N {kn}, data sha {d1.hex()[:0]}"
          f"{hashlib.sha256(d1).hexdigest()[:12]}, {len(d1)} bytes")


def test_payload_is_recoverable_source() -> None:
    """The recovered `data` bytes untar to paperholo's exact source."""
    _, vspec, data, _ = _frame()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        members = {m.name: tf.extractfile(m).read() for m in tf.getmembers()}
    assert set(members) == {f"paperholo/{n}" for n in gen_e018.CORE}, \
        sorted(members)
    for n in gen_e018.CORE:
        assert members[f"paperholo/{n}"] == (SRC / n).read_bytes(), n
    print(f"  payload untars to {len(members)} exact source files "
          f"({len(data)} B tar.gz)")


def _true_symbols(user, gtmap, vspec, tile_yxs):
    """Certified-symbol dict as if the given interior tiles decoded perfectly
    (ground truth: real user bits sliced per tile)."""
    results = []
    for t in tile_yxs:
        off, cap = gtmap[tuple(t)]
        tr = types.SimpleNamespace(ok=True, tile_yx=tuple(t),
                                   payload_bits=user[off:off + cap])
        results.append((0, tr))
    return fountain.tiles_to_symbols(results, vspec)


def test_volume_recovers_full_and_fragment() -> None:
    _, vspec, data, framed = _frame()
    user = np.asarray(fountain.volume_encode(data, vspec).page_user_bits[0])
    gtmap = {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
             for e in framed["per_tile"]}
    interior = [tuple(t) for t in fountain.interior_tiles(vspec.compose_spec)]
    n = len(interior)

    # (a) every interior tile certified -> exact data
    full = fountain.volume_decode(
        _true_symbols(user, gtmap, vspec, interior), vspec)[0]
    assert full == data, "full-volume decode mismatch"

    # (b) the confetti claim: recover from a fragment-sized SUBSET. Sweep
    #     down to find the closing fraction (deterministic shuffle).
    rng = np.random.default_rng(18)
    order = rng.permutation(n)
    closed_at = None
    for frac in (0.75, 0.65, 0.60, 0.55, 0.52, 0.51):
        k = int(np.ceil(frac * n))
        sub = [interior[i] for i in order[:k]]
        got = fountain.volume_decode(
            _true_symbols(user, gtmap, vspec, sub), vspec)[0]
        if got == data:
            closed_at = (frac, k)
        else:
            break
    assert closed_at is not None and closed_at[0] <= 0.60, closed_at
    frac, k = closed_at
    print(f"  volume recovers byte-exact from ALL {n} tiles AND from a "
          f"{k}/{n} = {100*frac:.0f}% random subset "
          f"(K/N {vspec.k_total}/{vspec.n_symbols_total}="
          f"{vspec.k_total/vspec.n_symbols_total:.3f}, "
          f"{vspec.n_blocks} fountain blocks)")


def test_blind_receiver_reads_c3_window() -> None:
    """Clean-channel blind acquire on an interior c3 window certifies tiles
    byte-exact vs the fountain frame (corroborates 012.3 c3 hardware)."""
    spec, vspec, data, framed = _frame()
    cp = compose_page(framed["payload_bits"], spec, vspec.seed, page=0)
    cd = spec.cell_dots                          # 3 for kcell-c3
    y0c, x0c, w = 600, 600, 240                   # interior, tile-aligned (60)
    crop = cp.plane_bits[y0c * cd:(y0c + w) * cd, x0c * cd:(x0c + w) * cd]

    # (5) sim genie-footing BER sanity in the c3 band
    scan = print_scan(crop, ChannelParams(seed=18, scan_seed=19,
                                          geometry=False))
    cells = scan.reshape(w, cd * 2, w, cd * 2).mean((1, 3))
    hard = (cells < np.median(cells)).astype(np.uint8)
    ber = float(np.mean(hard != cp.cell_values[y0c:y0c + w, x0c:x0c + w]))
    assert 0.005 < ber < 0.15, f"sim c3 regime off: {ber}"

    # (4) blind clean-channel decode of the same window
    clean = np.repeat(np.repeat((1.0 - crop).astype(np.float64), 2, 0), 2, 1)
    res = acquire.acquire_and_decode(clean, spec, vspec.seed,
                                     detector="ctx", calibrate=True,
                                     cell_px_nominal=2.0 * cd)
    assert res.ok, res.diagnostics
    pds = tilemap.PageDecodeState(spec, vspec.seed, page=0)
    pds.add_acquire_result("clean", res)
    counts = pds.decode_tiles("r0550", policy="best_scan", min_coverage=0.999)
    assert counts["certified"] >= 4, counts
    user = np.asarray(fountain.volume_encode(data, vspec).page_user_bits[0])
    gtmap = {tuple(e["tile_yx"]): (e["user_offset"], e["user_bits"])
             for e in framed["per_tile"]}
    nb = 0
    for t, st in pds.tiles.items():
        if st.status == "certified" and st.payload_bits is not None:
            off, cap = gtmap[t]
            assert np.array_equal(st.payload_bits,
                                  user[off:off + st.payload_bits.size]), t
            nb += int(st.payload_bits.size)
    print(f"  blind c3 window: {counts['certified']} tiles certified, "
          f"{nb} user bits byte-exact; sim genie BER {100*ber:.2f}%")


if __name__ == "__main__":
    for fn in (test_determinism,
               test_payload_is_recoverable_source,
               test_volume_recovers_full_and_fragment,
               test_blind_receiver_reads_c3_window):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
    print("\nALL GATES PASS — e018.ps is byte-exactly recoverable; "
          "safe to print for a confetti session.")
