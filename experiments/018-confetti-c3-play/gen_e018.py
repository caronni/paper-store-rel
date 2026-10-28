#!/usr/bin/env python3
"""e018 — CONFETTI-C3-PLAY: a c3 K-plane coded volume for a confetti session.

A companion to e016 (the coded c2 archive), but on the HOME engine's strong
plane: one A4 kcell-c3 page (frozen e012 geometry, hardware-validated in
012.3) whose payload is a single-page fountain volume tuned for FRAGMENT
recovery:

  data (a deterministic tar.gz of paperholo's own encode/format/confetti
  source — self-referential: the code that wrote the page) -> fountain-v1
  at K/N ~ 0.5 (HALF the 782 interior 64-cell tiles are repair symbols;
  ANY ~50% of the page's certified tiles recovers ALL data — the whole
  point of a confetti play sheet) -> per-tile LDPC r0550 + CRC-32 (the
  confetti pipeline's measured-proven rung, 016.5-016.7) -> compose_page
  -> one archive-style imagemask (no furniture, DESIGN R3).

Volume seed b"paper-store/exp018-confetti-c3" keys EVERYTHING (pilots,
LDPC, fountain rows, payload scramble). Deterministic + sha-recorded.

The payload is the current on-disk bytes of the CORE modules (below); the
manifest records data_sha256 + the file list. Regeneration is byte-exact
iff those source files are unchanged (a play sheet, not a frozen golden
format — the coding stack itself is what carries the golden guarantees).

DECODE (in a separate session): reconstruct the vspec via
gen_e018.make_vspec(), then drive the confetti session receiver
(experiments/016-arch3-c2-volume/session_decode.py, defaults =
weighted_sum + erode-4 + refine chain) or the whole-page page_decode.
Recovered `data` bytes ARE the tar.gz verbatim: `tar xzf recovered.bin`.

Print (home M281, raw 9100, AFTER in-session user confirmation per
.claude/rules/hardware.md):
  scripts/print_plane.sh experiments/018-confetti-c3-play/build/e018.ps
Scan: Canon 4800 grey (the measured c3 footing), re-placed scans; the
tile map's more_scans_useful() says when to stop.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from paperholo import fountain
from paperholo.compose import ComposeSpec, compose_page, emit_composed
from paperholo.pilots import PilotLayout

SEED = b"paper-store/exp018-confetti-c3"
OUT = Path(__file__).resolve().parent / "build"
SRC = Path(__file__).resolve().parents[2] / "src" / "paperholo"
PS_BUDGET_BYTES = 30_000_000
RATE = "r0550"                       # confetti pipeline's measured rung
KN_LO, KN_HI = 0.45, 0.56            # confetti-friendly K/N envelope guard

# The self-referential payload: paperholo's encode/format/confetti CORE.
# acquire.py (the 128 KB receiver) is excluded for size — it does not fit
# the K/N~0.5 c3 budget and is not needed to appreciate the archived format.
CORE = [
    "__init__.py", "modulation.py", "keystream_ref.py", "encodings.py",
    "pilots.py", "bch.py", "compose.py", "ldpc.py", "fountain.py",
    "tilemap.py", "scannorm.py", "formats.py", "segment.py", "place.py",
    "dust.py", "sync.py", "metrics.py", "psgen.py",
]


def make_spec() -> ComposeSpec:
    """Frozen e012 page geometry (kcell-c3, v3 words, >=6 mm margins)."""
    return ComposeSpec(layout_version=3, pilot=PilotLayout(version=3))


def make_targz() -> bytes:
    """Deterministic tar.gz of the CORE source (mtime=0, sorted, gzip -9,
    no gzip name/timestamp) — byte-exact for a given source snapshot."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tf:
        for name in sorted(CORE):
            payload = (SRC / name).read_bytes()
            ti = tarfile.TarInfo(name=f"paperholo/{name}")
            ti.size = len(payload)
            ti.mtime = 0
            ti.mode = 0o644
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            tf.addfile(ti, io.BytesIO(payload))
    return gzip.compress(raw.getvalue(), compresslevel=9, mtime=0)


def make_data(vspec: "fountain.VolumeSpec | None" = None) -> bytes:
    """The archived payload = the CORE tar.gz verbatim (no padding).

    `tar xzf <recovered>` yields paperholo/*.py. The optional vspec arg
    keeps the (vspec, data) call shape shared with e016's test harness."""
    data = make_targz()
    if vspec is not None:
        assert len(data) == vspec.data_len_bytes, (
            f"payload {len(data)} != vspec {vspec.data_len_bytes} "
            "(source changed between make_vspec and make_data?)")
    return data


def make_vspec() -> fountain.VolumeSpec:
    """Single-page c3 volume; data_len = the CORE tar.gz size, so K/N floats
    onto ~0.5 (guarded to the confetti envelope)."""
    data_len = len(make_targz())
    vspec = fountain.VolumeSpec(n_pages=1, data_len_bytes=data_len,
                                seed=SEED, ldpc_rate_id=RATE,
                                compose_spec=make_spec())
    kn = vspec.k_total / vspec.n_symbols_total
    assert KN_LO <= kn <= KN_HI, (
        f"K/N {kn:.3f} outside confetti envelope [{KN_LO}, {KN_HI}] — "
        f"the CORE payload ({data_len} B) drifted; re-curate the file list")
    return vspec


def main() -> int:
    t0 = time.time()
    spec = make_spec()
    vspec = make_vspec()
    data = make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    composed = compose_page(framed["payload_bits"], spec, SEED, page=0)

    OUT.mkdir(parents=True, exist_ok=True)
    kn = vspec.k_total / vspec.n_symbols_total
    mf = emit_composed(
        composed, OUT / "e018.ps",
        title="paperholo e018 confetti-c3 play volume",
        artifact="e018",
        experiment="018-confetti-c3-play",
        print_command=("scripts/print_plane.sh "
                       "experiments/018-confetti-c3-play/build/e018.ps"),
        extra_manifest={
            "artifact": "e018",
            "run": "018.0",
            "payload": "tar.gz of paperholo CORE source (self-referential)",
            "payload_files": CORE,
            "volume": {
                "n_pages": 1,
                "data_len_bytes": vspec.data_len_bytes,
                "data_sha256": hashlib.sha256(data).hexdigest(),
                "ldpc_rate_id": RATE,
                "k_total": vspec.k_total,
                "n_symbols_total": vspec.n_symbols_total,
                "symbol_bits": vspec.symbol_bits,
                "k_over_n": round(kn, 4),
            },
        })
    assert mf["ps_bytes"] <= PS_BUDGET_BYTES

    print(f"wrote build/e018.ps ({mf['ps_bytes'] / 1e6:.2f} MB)")
    print(f"volume: {vspec.data_len_bytes} data bytes (CORE tar.gz) = "
          f"{vspec.k_total} source + "
          f"{vspec.n_symbols_total - vspec.k_total} repair symbols "
          f"x {vspec.symbol_bits} bits; K/N {kn:.3f}, {RATE}; "
          f"{vspec.n_symbols_total} interior tiles")
    print(f"data sha256 {hashlib.sha256(data).hexdigest()}")
    print(f"ps   sha256 {mf['ps_sha256']}")
    print(f"({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
