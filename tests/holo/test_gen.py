"""Generator stack: descriptor rows, planning arithmetic, the emission
gate (gs render == GT dot-exact, page otherwise ink-free), determinism,
and the CLI surface."""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest


from holo import cli
from holo.format.fossils import resolve_fossil_spec
from holo.format.envelope import source_symbol_count
from holo.gen import emit
from holo.gen.plan import max_payload_bytes, plan_volume

PAYLOAD = hashlib.sha256(b"holo-gen").digest() * 40   # 1,280 bytes


def test_descriptor_design_rows():
    c2 = resolve_fossil_spec("c2-r0550@3328x2304")
    assert c2.layout.cells_yx == (3328, 2304)
    assert c2.layout.tiles_yx == (52, 36)
    assert c2.tiles_per_page == 1872
    assert c2.tile_user_bits == 2108
    assert c2.symbol_bits == 2107
    assert c2.max_pages == 140
    c3 = resolve_fossil_spec("c3-r0550@2240x1536")
    assert c3.layout.tiles_yx == (35, 24)
    assert c3.tiles_per_page == 840
    assert c3.max_pages == 312
    assert c3.n_transmitted_slots == 3996
    # counter round trip through the layout helpers
    c = c2.tile_counter(2, 51, 35)
    assert c2.tile_address(c) == (2, 51, 35)


def test_plan_arithmetic():
    row = resolve_fossil_spec("c3-r0550@2240x1536")
    p = plan_volume(row, 5120, 0.35)
    assert p.n_pages == 1 and p.k_total == 20
    assert p.n_repair == 820
    # page overflow refused
    with pytest.raises(ValueError):
        plan_volume(resolve_fossil_spec("c2-r0550@3328x2304"),
                    80_000_000, 0.5)
    # max payload monotone in pages and positive
    row2 = resolve_fossil_spec("c2-r0550@3328x2304")
    caps = [max_payload_bytes(row2, 0.5, n) for n in (1, 2, 4)]
    assert caps[0] > 0 and caps[0] < caps[1] < caps[2]
    # a 1-page a4-c2 promise at q=0.5: K <= floor(0.5*1872)-16 = 920
    assert caps[0] == (920 * 2107) // 8 - 36


def test_color_plan_uses_aggregate_width_and_stream_union_reserve():
    cmy7 = resolve_fossil_spec("c3-cmy7-p120-v0@2240x1536")
    cmy8 = resolve_fossil_spec("c3-cmy8-p120-v0@2240x1536")
    assert cmy7.stream_symbol_bits == (5973,)
    assert cmy7.aggregate_symbol_bits == 5973
    assert cmy8.stream_symbol_bits == (2087, 2087, 2087)
    assert cmy8.aggregate_symbol_bits == 6261

    payload_bytes = 800_000
    plan7 = plan_volume(cmy7, payload_bytes, 0.5)
    plan8 = plan_volume(cmy8, payload_bytes, 0.5)
    assert plan7.k_total == source_symbol_count(payload_bytes, 5973)
    assert plan8.k_total == source_symbol_count(payload_bytes, 6261)
    assert plan7.n_streams == 1 and plan8.n_streams == 3
    assert plan7.stream_symbol_bits == (5973,)
    assert plan8.stream_symbol_bits == (2087, 2087, 2087)
    assert plan8.aggregate_symbol_bits == 6261

    # The page promise covers three independent CMY8 fountain solves.
    from holo.core import capacity
    assert capacity.page_capacity_sufficient(
        plan8.k_total,
        cmy8.tiles_per_page,
        plan8.n_pages,
        0.5,
        n_streams=3,
    )


def _payload_len_for_k(symbol_bits: int, k_total: int) -> int:
    """Smallest payload byte count whose envelope plans to exact K."""
    envelope_bytes = ((k_total - 1) * symbol_bits) // 8 + 1
    return envelope_bytes - 36


def test_plan_enforces_every_block_whole_page_capacity():
    c2 = resolve_fossil_spec("c2-r0550@3328x2304")
    payload_len = _payload_len_for_k(c2.symbol_bits, 99_083)
    p = plan_volume(c2, payload_len, 0.5)
    assert p.k_total == 99_083 and p.n_pages == 107

    payload_len = _payload_len_for_k(c2.symbol_bits, 157_041)
    p = plan_volume(c2, payload_len, 0.7)
    assert p.k_total == 157_041 and p.n_pages == 121


def test_plan_exact_budget_arithmetic():
    """Regression: float floor(q*N) loses whole symbols at exact rational
    boundaries (floor(0.35*187200) -> 65519 in binary float; exact 65520)
    and made plan_volume crash on whole windows of valid payload sizes."""
    from holo.core import capacity
    assert capacity.source_budget(187200, 0.35) == 65520
    with pytest.raises(ValueError):
        capacity.q_fraction(0.1 + 0.2)   # dirty float dial refused
    # sweep payload sizes across page boundaries at the shipped dials —
    # every plan must construct and honor the promise, never raise
    row = resolve_fossil_spec("c3-r0550@2240x1536")
    for q in (0.35, 0.5, 0.7, 0.75):
        for size in range(1000, 3_000_000, 32_069):
            p = plan_volume(row, size, q)
            assert p.k_total + 16 >= p.k_total  # touch fields


def test_emit_deterministic(tmp_path: Path):
    row = resolve_fossil_spec("c3-r0550@2240x1536")
    v1 = emit.emit_volume(row, PAYLOAD, 0.35, tmp_path / "a")
    v2 = emit.emit_volume(row, PAYLOAD, 0.35, tmp_path / "b")
    assert [p.ps_sha256 for p in v1.pages] == [p.ps_sha256 for p in v2.pages]
    assert [p.gt_sha256 for p in v1.pages] == [p.gt_sha256 for p in v2.pages]
    assert v1.plan.n_pages == 1
    page = v1.pages[0]
    assert page.ps_sha256 == \
        "b3d739f16d21a08d6deebda7e69600e861c2492b3034164e3f1b25c298fba149"
    assert page.gt_sha256 == \
        "a55fcd696d8a91b1fc106f8ab3b48bdbd03b81a99ce7e07a5180bb3c9d7e027c"
    assert hashlib.sha256(page.ps_path.read_bytes()).hexdigest() == \
        page.ps_sha256
    packed_gt = np.load(page.gt_path)
    assert hashlib.sha256(packed_gt.tobytes(order="C")).hexdigest() == \
        page.gt_sha256

    import json
    manifest = json.loads((tmp_path / "a" / "manifest.json").read_text())
    assert hashlib.sha256(
        (tmp_path / "a" / "manifest.json").read_bytes()
    ).hexdigest() == \
        "876d0a99df6a2ea92d525a5b708df7ed7868ba8311af321daab9e8ad2f48c494"
    page_row = manifest["pages"][0]
    assert page_row["ps_sha256"] == page.ps_sha256
    assert page_row["gt_sha256"] == page.gt_sha256
    assert page_row["gt_packed_shape"] == list(packed_gt.shape)
    assert page_row["gt_bitorder"] == "big"


# Two printed-size colour emissions: a fork guard, not per-commit
# feedback (2026-09-20).
@pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the printed-size emission goldens",
)
@pytest.mark.parametrize(
    ("coding_id", "ps_sha", "gt_sha", "plane_sha"),
    [
        (
            "c3-cmy7-p120-v0",
            "a53a977f3d17068e28c583fc3b57066"
            "c30d68e309d7ae5510a95c7d454031e5d",
            "f3460b1ddd799924a6913aa5fdde8708"
            "74c065b27ae2ab6627bf9c9b185cd206",
            (
                "fcfcdd6a21ba04f6033727a87874178e"
                "c48cd4d10c8e190f40980a2ffbe9926c",
                "023fb46162e35c8671d4caae1fc9311e"
                "0bedd142cb1bcc0a394f790b6030112d",
                "d2dcdcdc2ba55226736f12d8acc6d41"
                "b4900d8f796bb5aacd60c93bb8d4a4d00",
            ),
        ),
        (
            "c3-cmy8-p120-v0",
            "a2e988643055f4cd395a762e714c1e71"
            "20cbfba4290781f2a9c6aa9c8c4f87b2",
            "808087ceb52bf076d7cad3c1fbdb8c2b"
            "4d3b931704f4648b41a73525441ab9aa",
            (
                "6e6dd3bb46b9780fcba0eddebc2b94ca"
                "70cb7177b59117e3583426277eb40339",
                "68afedbcee514a8f4dbe18c454121d06"
                "a3bf1b48cd788083bede99cb53f0a747",
                "c279ba0d5f5470c8692acce88b0b3547"
                "83d67396112e02675eed8e5610cc167c",
            ),
        ),
    ],
)
def test_color_emit_is_composite_and_has_plane_ground_truth(
    tmp_path: Path,
    coding_id: str,
    ps_sha: str,
    gt_sha: str,
    plane_sha: tuple[str, str, str],
):
    import json

    row = resolve_fossil_spec(f"{coding_id}@2240x1536")
    vol = emit.emit_volume(
        row, b"color smoke", 0.35, tmp_path / coding_id)
    assert vol.plan.n_pages == 1
    page = vol.pages[0]
    assert page.ps_sha256 == ps_sha
    assert page.gt_sha256 == gt_sha
    assert page.gt_plane_sha256 == plane_sha

    ps = page.ps_path.read_text(encoding="ascii")
    assert "/DeviceCMYK setcolorspace" in ps
    assert ">> image" in ps
    assert "imagemask" not in ps

    packed = np.load(page.gt_path)
    h, w = row.layout.field_dots_yx
    assert packed.shape == (3, h, -(-w // 8))
    assert hashlib.sha256(packed.tobytes(order="C")).hexdigest() == gt_sha
    for plane in range(3):
        assert hashlib.sha256(
            packed[plane].tobytes(order="C")
        ).hexdigest() == plane_sha[plane]

    manifest = json.loads(
        (tmp_path / coding_id / "manifest.json").read_text())
    assert manifest["codec"]["codec_id"] == row.codec_id
    assert [stream["stream_id"]
            for stream in manifest["codec"]["streams"]] == \
        list(row.stream_ids)
    assert manifest["volume"]["stream_symbol_bits"] == \
        list(row.stream_symbol_bits)
    assert manifest["volume"]["aggregate_symbol_bits"] == \
        row.aggregate_symbol_bits
    assert manifest["pages"][0]["gt_axis_order"] == \
        ["plane", "y", "packed_x"]
    assert manifest["pages"][0]["gt_plane_sha256"] == list(plane_sha)


@pytest.mark.skipif(shutil.which("gs") is None, reason="ghostscript missing")
def test_emission_gate_gs_render_equals_gt(tmp_path: Path):
    from PIL import Image
    row = resolve_fossil_spec("c3-r0550@2240x1536")
    vol = emit.emit_volume(row, PAYLOAD, 0.35, tmp_path / "v")
    page = vol.pages[0]
    png = tmp_path / "v.png"
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                    "-sDEVICE=pnggray", "-r600", "-o", str(png),
                    str(page.ps_path)], check=True, timeout=600)
    img = np.asarray(Image.open(png).convert("L")).copy()
    gt = np.unpackbits(np.load(page.gt_path), axis=1)
    oy, ox = row.layout.origin_dots_yx
    h, w = gt.shape[0], row.layout.field_dots_yx[1]
    gt = gt[:, :w]
    got = (img[oy:oy + h, ox:ox + w] < 128).astype(np.uint8)
    assert np.array_equal(got, gt), f"{int((got != gt).sum())} dots differ"
    img[oy:oy + h, ox:ox + w] = 255
    assert not np.any(img < 128), "ink outside the field"


def test_cli_surface(tmp_path: Path, capsys):
    assert cli.main(["registry"]) == 0
    out = capsys.readouterr().out
    assert "c2-r0550" in out and "rocksolid" in out
    assert "BCH" not in out                      # detail is -v only
    assert cli.main(["registry", "-v"]) == 0
    out = capsys.readouterr().out
    assert "BCH(127,50,t=13)" in out             # word internals
    # 2026-10-12 (cmy generator W2b, CMY-DESIGN R21): `registry -v` lost
    # the per-printer "derived geometry" and the profiles' "promise-grade"
    # pricing with make_spec — a printer is an emission engine, never a
    # geometry; the profiles stay listed as documentation.
    assert "derived geometry" not in out and "promise-grade" not in out
    # 2026-10-12 (W2b, R21): `capacity --profile resilient` and `generate
    # --profile rocksolid` became the profile's row as its L: fossil at
    # the profile's dial; `--profile` itself is no option any more.
    assert cli.main(["capacity", "--format", "L:c3-r0550@2240x1536",
                     "--source-fraction", "0.5",
                     "--payload-bytes", "100000"]) == 0
    out = capsys.readouterr().out
    assert "n_pages" in out
    payload_file = tmp_path / "p.bin"
    payload_file.write_bytes(PAYLOAD)
    out_dir = tmp_path / "out"
    rocksolid = ["--format", "L:c3-r0550@2240x1536",
                 "--source-fraction", "0.35"]
    assert cli.main(["generate", *rocksolid, str(payload_file),
                     "-o", str(out_dir)]) == 0
    out = capsys.readouterr().out
    assert "K=" in out and "c3-r0550@2240x1536" in out
    assert (out_dir / "page000.ps").exists()
    assert (out_dir / "manifest.json").exists()
    # existing directory is refused, never overwritten
    with pytest.raises(SystemExit):
        cli.main(["generate", *rocksolid, str(payload_file),
                  "-o", str(out_dir)])
    # manifest records the explicit selection + provisional status
    import json
    man = json.loads((out_dir / "manifest.json").read_text())
    assert man["profile"] == {"name": "custom",
                              "evidence": "none — explicit parameters"}
    assert man["printer_id"] is None
    assert "provisional" in man["v1_status"]
    assert man["volume"]["fountain_version"] == "fountain-v2"


def test_capacity_cli_labels_multistream_repairs_per_stream(capsys) -> None:
    import json

    # 2026-10-12 (W2b, R21): `--coding ID` -> the row's L: fossil.
    assert cli.main([
        "capacity",
        "--format",
        "L:c2-cmy8-p120-v0@3328x2304",
        "--source-fraction",
        "0.5",
        "--payload-bytes",
        "100000",
        "--json",
    ]) == 0
    color = json.loads(capsys.readouterr().out)
    assert "n_repair" not in color
    assert color["n_repair_symbols_per_stream"] > 0

    assert cli.main([
        "capacity",
        "--format",
        "L:c2-r0550@3328x2304",
        "--source-fraction",
        "0.5",
        "--payload-bytes",
        "100000",
        "--json",
    ]) == 0
    k = json.loads(capsys.readouterr().out)
    assert k["n_repair"] > 0
    assert "n_repair_symbols_per_stream" not in k
