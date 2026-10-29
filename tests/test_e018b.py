"""E018b generic payload-sheet encoder preflight.

Gates the reusable C3/C2 emitter without creating a new printed format:
profile equality to E018/E016, fixed decoder-known keys, exact K/N<=0.5
capacity, near-half fountain recovery, and archive-style PS/manifest/GT output.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
EXP = ROOT / "experiments" / "018b-payload-sheet"

# 2026-09-06: every test here reads a build that a test regenerates in place;
# test_e016.py writes the same directory.  One xdist worker per build directory
# (pyproject: --dist loadgroup).
pytestmark = pytest.mark.xdist_group("build-016-018")
sys.path.insert(0, str(EXP))

from paperholo import formats, fountain, ldpc  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

import gen_e018b  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _max_pilot_sites_exhaustive() -> int:
    """Adversarially maximize p60b6 sites in every 64x64 phase.

    Each pilot site's in-block (dy, dx) choice is independent, so maximizing
    each 6x6 block separately is an exact upper bound over all possible seeds.
    """
    layout = PilotLayout(version=3)
    period = layout.period_cells
    block = layout.block_cells
    blocks = period // block
    tile = ldpc.TILE_CELLS
    best = 0
    for y0 in range(period):
        ymult = np.bincount(
            np.arange(y0, y0 + tile) % period, minlength=period
        )
        ymax = np.array(
            [
                ymult[by * block:(by + 1) * block].max()
                for by in range(blocks)
            ]
        )
        for x0 in range(period):
            xmult = np.bincount(
                np.arange(x0, x0 + tile) % period, minlength=period
            )
            xmax = np.array(
                [
                    xmult[bx * block:(bx + 1) * block].max()
                    for bx in range(blocks)
                ]
            )
            best = max(best, int(np.outer(ymax, xmax).sum()))
    return best


def test_profiles_equal_e018_and_e016_geometry() -> None:
    e018 = _load_script(
        "_e018_gen_for_e018b",
        ROOT / "experiments/018-confetti-c3-play/gen_e018.py",
    )
    e016 = _load_script(
        "_e016_gen_for_e018b",
        ROOT / "experiments/016-arch3-c2-volume/gen_e016.py",
    )
    assert gen_e018b.make_spec("c3") == e018.make_spec()
    assert gen_e018b.make_spec("c2") == e016.make_spec()


def test_capacity_bound_and_numbers() -> None:
    assert _max_pilot_sites_exhaustive() == 144
    assert gen_e018b.MAX_PILOT_SITES_PER_INTERIOR_TILE == 144
    assert gen_e018b.PROVEN_MIN_SYMBOL_BITS == 2064

    c3 = gen_e018b.capacity_for("c3")
    c2 = gen_e018b.capacity_for("c2")
    assert (
        c3.symbol_bits,
        c3.n_symbols_total,
        c3.max_source_symbols,
        c3.payload_bytes,
    ) == (
        2090,
        782,
        391,
        102_148,
    )
    assert (
        c2.symbol_bits,
        c2.n_symbols_total,
        c2.max_source_symbols,
        c2.payload_bytes,
    ) == (
        2087,
        1734,
        867,
        226_178,
    )

    for profile in gen_e018b.PROFILE_ORDER:
        cap = gen_e018b.capacity_for(profile)
        sheet = gen_e018b.get_profile(profile)
        vspec = fountain.VolumeSpec(
            n_pages=1,
            data_len_bytes=1,
            seed=sheet.seed,
            ldpc_rate_id=gen_e018b.LDPC_RATE_ID,
            compose_spec=gen_e018b.make_spec(profile),
        )
        assert vspec.symbol_bits == cap.symbol_bits
        assert vspec.symbol_bits >= gen_e018b.PROVEN_MIN_SYMBOL_BITS
        assert cap.max_source_symbols * vspec.symbol_bits // 8 == (
            cap.payload_bytes
        )


def test_fixed_keys_and_size_refusal() -> None:
    c3 = gen_e018b.get_profile("c3")
    c2 = gen_e018b.get_profile("c2")
    assert c3.seed == b"paper-store/018b-c3-r0550-0.5"
    assert c2.seed == b"paper-store/018b-c2-r0550-0.5"
    assert c3.seed != c2.seed

    registry = {fd.format_id: fd for fd in formats.FORMAT_REGISTRY}
    assert registry["e018b-v3-c3"].seed == c3.seed
    assert registry["e018b-v3-c3"].ldpc_rate == "r0550"
    assert registry["e018b-v3-c3"].encoding_id == "kcell-c3"
    assert registry["e018b-v3-c2"].seed == c2.seed
    assert registry["e018b-v3-c2"].ldpc_rate == "r0550"
    assert registry["e018b-v3-c2"].encoding_id == "kcell-c2"

    # Payload bytes and hashes never enter the profile key.
    assert gen_e018b.plan_payload("c3", b"first").seed == c3.seed
    assert gen_e018b.plan_payload("c3", b"second").seed == c3.seed
    assert gen_e018b.plan_payload("c2", b"first").seed == c2.seed

    for profile in gen_e018b.PROFILE_ORDER:
        cap = gen_e018b.capacity_for(profile)
        plan = gen_e018b.plan_payload(profile, bytes(cap.payload_bytes))
        assert plan.vspec.k_total <= cap.max_source_symbols
        assert plan.vspec.k_total / plan.vspec.n_symbols_total <= 0.5
        with pytest.raises(ValueError, match="above the fixed-key"):
            gen_e018b.plan_payload(
                profile, bytes(cap.payload_bytes + 1)
            )
    with pytest.raises(ValueError, match="non-empty"):
        gen_e018b.plan_payload("c3", b"")


@pytest.mark.parametrize("profile", gen_e018b.PROFILE_ORDER)
def test_fountain_recovers_near_half_at_full_capacity(profile: str) -> None:
    """At the advertised limit, a deterministic K+16 subset closes exactly."""
    cap = gen_e018b.capacity_for(profile)
    data = np.arange(cap.payload_bytes, dtype=np.uint32).astype(
        np.uint8
    ).tobytes()
    plan = gen_e018b.plan_payload(profile, data)
    enc = fountain.volume_encode(data, plan.vspec)

    rng = np.random.default_rng(1802 if profile == "c3" else 1803)
    take = min(
        plan.vspec.n_symbols_total,
        plan.vspec.k_total + 16,
    )
    selected = rng.permutation(plan.vspec.n_symbols_total)[:take]
    symbols = {}
    for t in selected:
        block = int(t % plan.vspec.n_blocks)
        index = int(t // plan.vspec.n_blocks)
        symbols[(block, index)] = enc.symbol(block, index)
    recovered, diag = fountain.volume_decode(symbols, plan.vspec)
    assert diag["solved_all"], diag
    assert recovered == data


@pytest.mark.parametrize("profile", gen_e018b.PROFILE_ORDER)
def test_emit_writes_complete_deterministic_artifact(
    tmp_path: Path, profile: str
) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes((f"e018b-{profile}-payload".encode() * 17) + b"\0")
    out = tmp_path / f"sheet-{profile}.ps"

    first = gen_e018b.emit_sheet(payload, profile, output_path=out)
    ps_first = out.read_bytes()
    mf_path = out.with_name(out.stem + "_manifest.json")
    stored = json.loads(mf_path.read_text())

    assert stored == first
    assert hashlib.sha256(ps_first).hexdigest() == first["ps_sha256"]
    assert first["profile"] == profile
    assert first["format"]["encoding_id"] == f"kcell-{profile}"
    assert first["format"]["plane"] == "K"
    assert first["seed"] == gen_e018b.get_profile(profile).seed.decode()
    assert first["format"]["seed"] == first["seed"]
    assert first["seed_policy"] == "fixed public profile constant"
    assert first["volume"]["fountain_version"] == fountain.FOUNTAIN_VERSION
    assert first["volume"]["ldpc_rate_id"] == "r0550"
    assert first["volume"]["k_over_n"] <= 0.5
    assert first["payload"]["data_sha256"] == hashlib.sha256(
        payload.read_bytes()
    ).hexdigest()
    (patch,) = first["patches"]
    gt = out.parent / patch["gt"]
    assert gt.exists()
    gt_bits = np.load(gt, mmap_mode="r")
    assert gt_bits.shape == gen_e018b.make_spec(profile).field_dots_yx

    # Repository-standard emission gate: Ghostscript's addressed dots are
    # exactly the generated bitmap, with no furniture elsewhere on the page.
    render = tmp_path / f"sheet-{profile}.png"
    subprocess.run(
        [
            "gs",
            "-dNOPAUSE",
            "-dBATCH",
            "-dQUIET",
            "-sDEVICE=pnggray",
            "-r600",
            "-o",
            str(render),
            str(out),
        ],
        check=True,
        timeout=600,
    )
    page = np.asarray(Image.open(render).convert("L")).copy()
    y = patch["y_dots"]
    x = patch["x_dots"]
    h = patch["h_dots"]
    w = patch["w_dots"]
    rendered_bits = (page[y:y + h, x:x + w] < 128).astype(np.uint8)
    assert np.array_equal(rendered_bits, gt_bits)
    page[y:y + h, x:x + w] = 255
    assert not np.any(page < 128), "archive page has ink outside the field"

    # The manifest contains enough public data to reconstruct VolumeSpec.
    seed = first["seed"].encode()
    rebuilt = fountain.VolumeSpec(
        n_pages=first["volume"]["n_pages"],
        data_len_bytes=first["volume"]["data_len_bytes"],
        seed=seed,
        ldpc_rate_id=first["volume"]["ldpc_rate_id"],
        compose_spec=gen_e018b.make_spec(profile),
    )
    assert rebuilt.k_total == first["volume"]["k_total"]
    assert rebuilt.symbol_bits == first["volume"]["symbol_bits"]

    # Re-emission is byte-identical for the same payload/profile/seed.
    second = gen_e018b.emit_sheet(payload, profile, output_path=out)
    assert out.read_bytes() == ps_first
    assert second["ps_sha256"] == first["ps_sha256"]


def test_capacity_cli_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert gen_e018b.main(["capacity", "c3", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profiles"] == [
        gen_e018b.capacity_for("c3").as_dict()
    ]
