"""keystream_ref vs numpy: bit-exactness of the covert keystream chain.

Three layers of pinning, from primitive to printed format:
  1. raw Philox-4x64-10 words (BitGenerator.random_raw);
  2. Generator.integers consumption for the two codec dtypes, swept over
     bounds/sizes including every Lemire branch (rejection, full-range,
     rng==0, 32/64-bit routing boundaries, cross-call half-word carry);
  3. every (seed, label, draw-form) the codec actually uses, checked
     function-level against the LIVE modules (modulation/pilots/ldpc/
     fountain/encodings), plus the frozen golden vectors in
     tests/golden_keystream_vectors.json verified on BOTH legs (numpy and
     the pure-Python reference).

A failure in layer 1/2 means numpy changed its stream (the exact liability
keystream_ref.py exists to survive: the reference + vectors stay normative).
A failure in layer 3 or the golden file means a codec label or draw form
changed — that is a printed-format fork: bump layout_version, never edit
the vectors.

Runs under pytest, or standalone (no pytest needed):
  env/bin/python tests/test_keystream_ref.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import encodings, fountain, ldpc, pilots  # noqa: E402
from paperholo import keystream_ref as kref  # noqa: E402
from paperholo.modulation import keystream, rng  # noqa: E402

SEED = b"paper-store/exp016-arch3"  # the e016 volume seed (golden fixture)
GOLDEN = ROOT / "tests" / "golden_keystream_vectors.json"


def _np_gen(key: int) -> np.random.Generator:
    return np.random.Generator(np.random.Philox(key=key))


# ---------------------------------------------------------------------------
# layer 1 — raw bit-generator words
# ---------------------------------------------------------------------------

def test_raw_philox_words():
    for label in (b"\x03\x00\x00\x00\x00", b"pilot-sites-v2",
                  b"pilot-values-v3/K", b"eira-H/restart0", b"e016/data"):
        key = kref.philox_key(SEED, label)
        want = [int(x) for x in np.random.Philox(key=key).random_raw(16)]
        ref = kref.PhiloxRef(key)
        assert [ref.next64() for _ in range(16)] == want, label


# ---------------------------------------------------------------------------
# layer 2 — Generator.integers consumption, all branches
# ---------------------------------------------------------------------------

def test_integers_uint8_sweep():
    for i, (low, high) in enumerate(
            [(0, 2), (0, 6), (0, 7), (0, 8), (0, 17), (1, 7), (0, 255),
             (0, 256), (3, 4)]):
        key = kref.philox_key(b"formsweep-u8", str(i).encode())
        for size in (1, 5, 257):
            got = list(_np_gen(key).integers(low, high, size=size,
                                             dtype=np.uint8))
            ref = kref.GeneratorRef(key).integers(low, high, size,
                                                  dtype="uint8")
            assert got == ref, (low, high, size)
        got = int(_np_gen(key).integers(low, high, dtype=np.uint8))
        assert got == kref.GeneratorRef(key).integers(low, high,
                                                      dtype="uint8")


def test_integers_int64_sweep():
    highs = [2, 3, 6, 7, 29, 64, 65, 100, 1 << 20, 1 << 31, 1 << 32,
             (1 << 32) + 1, 1 << 33, (1 << 40) + 12345, 1 << 63]
    for i, high in enumerate(highs):
        for low in (0, 1):
            key = kref.philox_key(b"formsweep-i64", f"{i}/{low}".encode())
            got = [int(x) for x in _np_gen(key).integers(low, high, size=31)]
            ref = kref.GeneratorRef(key).integers(low, high, 31)
            assert got == ref, (low, high)
            got = int(_np_gen(key).integers(low, high))
            assert got == kref.GeneratorRef(key).integers(low, high)
    # rng == 0: constant fill, consumes nothing
    key = kref.philox_key(b"formsweep-i64", b"rng0")
    g_np, g_ref = _np_gen(key), kref.GeneratorRef(key)
    assert list(g_np.integers(5, 6, size=4)) == g_ref.integers(5, 6, 4)
    assert int(g_np.integers(0, 1 << 20)) == g_ref.integers(0, 1 << 20)


def test_integers_cross_call_state():
    # the Philox half-word carry persists across calls; the uint8 byte
    # buffer must NOT (fresh per call) — interleave dtypes on one generator
    key = kref.philox_key(b"formsweep", b"interleave")
    g_np, g_ref = _np_gen(key), kref.GeneratorRef(key)
    for _ in range(3):
        assert (list(g_np.integers(0, 2, size=5, dtype=np.uint8))
                == g_ref.integers(0, 2, 5, dtype="uint8"))
        assert [int(x) for x in g_np.integers(0, 6, size=7)] \
            == g_ref.integers(0, 6, 7)
        assert int(g_np.integers(0, 3)) == g_ref.integers(0, 3)


# ---------------------------------------------------------------------------
# layer 3 — every codec (seed, label, draw form), against the live modules
# ---------------------------------------------------------------------------

def test_payload_keystream():
    for plane, idx in kref.PLANE_KEYSTREAM_INDEX.items():
        for page in (0, 1, 254):
            want = keystream(SEED, idx, page, (17, 23)).ravel().tolist()
            got = kref.payload_keystream_bits(SEED, idx, page, 17 * 23)
            assert got == want, (plane, page)


def test_pilot_sites_v1_mask():
    shape = (128, 128)
    want = pilots.pilot_sites(shape, SEED)
    off = kref.pilot_site_offsets(SEED, layout_version=1)
    mask = np.zeros(shape, dtype=bool)
    nb = pilots.PERIOD // pilots.BLOCK
    for by in range(nb):
        for bx in range(nb):
            dy, dx = off[(by * nb + bx) * 2], off[(by * nb + bx) * 2 + 1]
            mask[by * pilots.BLOCK + dy::pilots.PERIOD,
                 bx * pilots.BLOCK + dx::pilots.PERIOD] = True
    assert np.array_equal(mask, want)


def test_pilot_sites_v2_positions():
    layout = pilots.PilotLayout(version=2)
    want = pilots.site_positions_tile(layout, SEED)
    off = kref.pilot_site_offsets(SEED, layout_version=2)
    nb = layout.blocks_per_period
    pos = [(by * layout.block_cells + off[(by * nb + bx) * 2],
            bx * layout.block_cells + off[(by * nb + bx) * 2 + 1])
           for by in range(nb) for bx in range(nb)]
    assert pos == [tuple(p) for p in want.tolist()]


def test_pilot_value_keystreams():
    for version in (2, 3, 4):
        layout = pilots.PilotLayout(version=version)
        # v4 words are luma objects: plane always "K" (PILOTS-DESIGN §16.2)
        for plane in (("K",) if version == 4 else ("K", "C", "M", "Y")):
            want = pilots.value_keystream_tile(layout, SEED, plane).tolist()
            got = kref.pilot_value_bits(SEED, version, plane)
            assert got == want, (version, plane)


def test_ldpc_construction_stream():
    spec = ldpc.LDPC_LADDER["r0550"]
    assert spec.seed_label == b"ldpc-v1/r0550"  # kref restates this label
    for restart in (0, 5):
        label = b"eira-H/restart" + str(restart).encode()
        g_np = rng(spec.seed_label, label)
        want_pi = ldpc._fisher_yates(g_np, spec.m_bits)
        g_ref = kref.ldpc_construction_rng("r0550", restart)
        assert kref.fisher_yates(g_ref, spec.m_bits) == want_pi.tolist()
        mb = spec.m_bits // spec.z
        for _ in range(4):  # column-attempt draws continue the same stream
            want = [int(x) for x in g_np.integers(0, mb, size=spec.heavy_deg)]
            assert g_ref.integers(0, mb, spec.heavy_deg) == want
            want = [int(x) for x in g_np.integers(0, spec.z,
                                                  size=spec.heavy_deg)]
            assert g_ref.integers(0, spec.z, spec.heavy_deg) == want


def test_fountain_row():
    for block, i, kb in ((0, 1387, 1387), (2, 9000, 100)):
        label = (fountain.ROW_LABEL + block.to_bytes(4, "little")
                 + i.to_bytes(4, "little"))
        assert label == kref.fountain_row_label(block, i)
        want = [int(x) for x in rng(SEED, label).integers(0, 2, kb)]
        assert kref.fountain_row_bits(SEED, block, i, kb) == want
    # layout_version-4 MLC level byte (n_levels > 1 only; same draw form)
    label = (fountain.ROW_LABEL + bytes([1]) + (0).to_bytes(4, "little")
             + (500).to_bytes(4, "little"))
    assert label == kref.fountain_row_label(0, 500, level=1)
    want = [int(x) for x in rng(SEED, label).integers(0, 2, 64)]
    assert kref.rng_ref(SEED, label).integers(0, 2, 64) == want


def test_dust_streams():
    from paperholo import dust
    # sites: partial Fisher-Yates scalars integers(i, n, dtype=np.int64) —
    # explicit np.int64 must be the same stream as the reference default
    assert dust.DUST_SITES_LABEL == kref.dust_sites_label()
    g_np = rng(SEED, dust.DUST_SITES_LABEL)
    g_ref = kref.rng_ref(SEED, dust.DUST_SITES_LABEL)
    n = 3500
    for i in range(120):
        assert int(g_np.integers(i, n, dtype=np.int64)) \
            == g_ref.integers(i, n), i
    # states: uint8 (0, 8, M) then the quota fix-up FY on the same stream
    label = kref.dust_states_label(0, 7)
    assert label == (dust.DUST_STATES_LABEL + (0).to_bytes(4, "little")
                     + (7).to_bytes(4, "little"))
    g_np = rng(SEED, label)
    g_ref = kref.rng_ref(SEED, label)
    m = 64
    want = list(g_np.integers(0, dust.N_STATES, size=m, dtype=np.uint8))
    assert g_ref.integers(0, dust.N_STATES, m, dtype="uint8") == want
    assert kref.fisher_yates(g_ref, m) == dust._fisher_yates(g_np, m).tolist()


def test_symbol_keystream():
    for enc_id in ("a3-7st-c3", "a4-8st-c4"):
        enc = encodings.get_encoding(enc_id)
        want = encodings.key_symbols(enc, (16, 16), SEED,
                                     page=3).ravel().tolist()
        got = kref.symbol_keystream(SEED, enc_id, 3, 256, enc.n_states)
        assert got == want, enc_id


def test_e016_data_stream():
    want = rng(SEED, b"e016/data").integers(0, 256, 4096,
                                            dtype=np.uint8).tolist()
    g_ref = kref.rng_ref(SEED, b"e016/data")
    assert g_ref.integers(0, 256, 4096, dtype="uint8") == want


# ---------------------------------------------------------------------------
# golden vectors — both legs against the frozen file
# ---------------------------------------------------------------------------

def _key_of(s: dict) -> int:
    key = kref.philox_key(s["seed_ascii"].encode(),
                          bytes.fromhex(s["label_hex"]))
    assert format(key, "032x") == s["philox_key_hex"]
    return key


def test_golden_raw_words():
    streams = json.loads(GOLDEN.read_text())["streams"]
    assert len(streams) == 18
    for name, s in streams.items():
        key = _key_of(s)
        want = [int(w, 16) for w in s["raw_philox_words_hex"]]
        assert [int(x) for x in
                np.random.Philox(key=key).random_raw(4)] == want, name
        ref = kref.PhiloxRef(key)
        assert [ref.next64() for _ in range(4)] == want, name


def test_golden_streams():
    streams = json.loads(GOLDEN.read_text())["streams"]

    def both_legs(s, low, high, n, dtype):
        key = _key_of(s)
        np_dtype = np.uint8 if dtype == "uint8" else np.int64
        a = _np_gen(key).integers(low, high, size=n, dtype=np_dtype).tolist()
        b = kref.GeneratorRef(key).integers(low, high, n, dtype=dtype)
        assert a == b
        return b

    for plane in ("C", "M", "Y", "K"):
        s = streams[f"payload-keystream/{plane}/page0"]
        assert bytes.fromhex(s["label_hex"]) == kref.payload_keystream_label(
            kref.PLANE_KEYSTREAM_INDEX[plane], 0)
        bits = both_legs(s, 0, 2, 256, "uint8")
        assert "".join(map(str, bits)) == s["first_256_bits"], plane

    for name, lv in (("pilot-sites-v1", 1), ("pilot-sites-v2", 3)):
        s = streams[name]
        assert bytes.fromhex(s["label_hex"]) == kref.pilot_sites_label(lv)
        vals = both_legs(s, 0, 6, 200, "int64")
        assert "".join(map(str, vals)) == s["offsets_200"], name

    for version in (2, 3):
        for plane in ("K", "C", "M", "Y"):
            s = streams[f"pilot-values-v{version}/{plane}"]
            assert bytes.fromhex(s["label_hex"]) == kref.pilot_values_label(
                version, plane)
            bits = both_legs(s, 0, 2, 100, "int64")
            assert "".join(map(str, bits)) == s["first_100_bits"]

    s = streams["ldpc/r0550/eira-H-restart0"]
    key = _key_of(s)
    m, mb, z, d = s["m_bits"], s["mb"], s["z"], s["heavy_deg"]
    g_np, g_ref = _np_gen(key), kref.GeneratorRef(key)
    pi_np = ldpc._fisher_yates(g_np, m)
    pi_ref = kref.fisher_yates(g_ref, m)
    assert pi_ref == pi_np.tolist()
    assert hashlib.sha256(" ".join(map(str, pi_ref)).encode()).hexdigest() \
        == s["fisher_yates_perm_sha256"]
    assert [int(x) for x in g_np.integers(0, mb, size=d)] \
        == g_ref.integers(0, mb, d) == s["post_fy_rows_d10"]
    assert [int(x) for x in g_np.integers(0, z, size=d)] \
        == g_ref.integers(0, z, d) == s["post_fy_shifts_d10"]
    # the recorded j-draws pin the FY prefix independent of the perm sha
    g_chk = kref.GeneratorRef(key)
    js = [g_chk.integers(0, i + 1) for i in range(m - 1, m - 65, -1)]
    assert js == s["fisher_yates_first_64_j"]

    s = streams["fountain-v1/row/block0/i1387"]
    assert bytes.fromhex(s["label_hex"]) == kref.fountain_row_label(0, 1387)
    bits = both_legs(s, 0, 2, s["k_block"], "int64")
    assert "".join(map(str, bits[:256])) == s["first_256_bits"]

    s = streams["symks/a3-7st-c3/page0"]
    assert bytes.fromhex(s["label_hex"]) \
        == kref.symbol_keystream_label("a3-7st-c3", 0)
    vals = both_legs(s, 0, 7, 256, "uint8")
    assert "".join(map(str, vals)) == s["first_256_symbols"]


def test_golden_e016_data_full_sha():
    """The certified e016 payload (016.2 hardware-decoded, byte-exact)
    regenerated START TO FINISH by the pure-Python reference."""
    s = json.loads(GOLDEN.read_text())["streams"]["e016/data"]
    key = _key_of(s)
    data = bytes(kref.GeneratorRef(key).integers(0, 256, s["n_bytes"],
                                                 dtype="uint8"))
    assert data[:32].hex() == s["first_32_bytes_hex"]
    assert hashlib.sha256(data).hexdigest() == s["full_sha256"]
    # numpy leg (prefix; the full numpy sha is pinned by test_e016.py already)
    want = _np_gen(key).integers(0, 256, size=4096, dtype=np.uint8).tobytes()
    assert data[:4096] == want


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for n, f in fns:
        f()
        print(f"ok {n}")
    print(f"{len(fns)} checks passed (numpy {np.__version__})")
