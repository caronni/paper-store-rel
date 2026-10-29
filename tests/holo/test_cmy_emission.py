"""cmy emission on both routes (docs/CMY-GENERATOR-PLAN.md W2a;
docs/CMY-DESIGN.md §2.8, §11 G6/G11): the goldens, the job, the manifest
record, and what an emitted page's GT says about the format law.

Four families:

* EMISSION GOLDENS — the six ruled rows at 10x10 (payload bytes(i % 251)
  of 20,000 B, q 0.5, A4-4mm), ``cmyk1`` under the AltaLink row and
  ``rgb`` under a TEST-LOCAL engine whose triple is not the registry's, so
  a registry edit moves no golden (test_registry_emission alone pins the
  registry); the two printed-size rows on both routes in the slow lane.
  GT and plane digests are route-independent; the PS digest is the
  route's.  Movement = format fork (GT) or route fork (PS alone).
* the JOB — ``rgb`` is three single-colour imagemasks through ASCII85 and
  nothing else, ``cmyk1`` one composite image; ``rgb`` refuses every
  family with overlap states; the CLI's ``--printer`` beside ``--format``;
* the MANIFEST — the engine, the route and its three values, the cmy law;
  without an engine, today's ``cmyk1`` renderer block and a null printer;
* the GT — the alphabet, the word rule, the balance-law dust re-derived
  over every tile, W0's literal tiles found on the page, the ``rgb`` job's
  masks read back in numpy; and the pooled reserve at k_meta 8,192 /
  8,193 / 10,000.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from holo import cli
from holo.core import capacity, channel, fountain, keystream
from holo.devices.registry import PRINTERS, Printer
from holo.format import pilots
from holo.format.lattice import parse_format_id
from holo.gen.emit import emit_volume
from holo.gen.plan import plan_volume

from _receive_free import gt_cell_states
from _cmy_vectors import TILES, ids

PAYLOAD = bytes(i % 251 for i in range(20_000))
Q = 0.5
PAPER = "A4-4mm"
TEST_RGB = Printer(
    printer_id="test-rgb", name="test-local rgb engine", usable_dpi=600,
    media_ids=("a4",), payload_safe_margin_mm=6.0, margin_footing="test",
    bw="test", color="test", print_path="test", color_route="rgb",
    rgb_solid=((10, 160, 245), (230, 20, 180), (245, 240, 15)))
ENGINES = {"cmyk1": PRINTERS["xerox-altalink-c8245"], "rgb": TEST_RGB}
W, C, M, Y = (int(s) for s in (channel.CMYState.W, channel.CMYState.C,
                               channel.CMYState.M, channel.CMYState.Y))
CMYK1_RENDERER = {"color_space": "DeviceCMYK", "bits_per_component": 1,
                  "plane_order": ["C", "M", "Y"], "K": "zero",
                  "operation": "one composite image"}

# Frozen 2026-10-11 (W2a).  Per row: GT, the C/M/Y plane digests, then
# (PS, manifest) per route.  The job sizes: 3,715,830 B cmyk1 / 1,689,241
# B rgb at c3, 1,651,830-835 B / 768,409-769,384 B at c2.
EMIT_GOLDENS = {
    "c3-cmy-r0850@10x10": (
        "77dee11846ba81afe4c57fbf030e12654fcac79cad06c55edf03c58cfdd33a3d",
        ("587ccabf4646d889e6b01d33b00a6465ae4c3c6c69c6a749cf23b4e71933bac0",
         "9c792e9e7095f44c094a363d10f3e87a07cb835a03adc8f0c6381b5452870ec8",
         "2f1b72539cf78d765a144be92bc008c8e3fbb104f64be55092eb0e2111ccec31"),
        {"cmyk1": (
            "eb903ce97c65a3ac9e1f0fcc572bf20f8608560377f225dc0cdf3efc089ddb8a",
            "b8155a3dd6685ec50b343733c8f0252f02c78004ee0ec502bb5fcea32e6d38a2"),
         "rgb": (
            "96d69a31f6e01ec6fc0de3a17ec78090011ffa56d32f1f0be839564880c6d715",
            "210ac21cccbad6cba29a29ca0f05cd9c3219ffc713dd45a5532cbffff1d9775b")},
    ),
    "c2-cmy-r0700@10x10": (
        "ef9db9a6e0560d0c6deb1aa4eaa1f28eec04c7e325faccbbcffd0a0b8430e10d",
        ("8f208fac491ed0af6d84d71904ffad4a5c97270df3d18c824c40aed8cacb4b45",
         "0a19ee3be2b75d6ed34584fcef5cf19dc96ab06cd84c7ec37c8945f4338b739e",
         "51ec34c1f49e575886772c989779a76a0865126c9caf48dfa55db08c02f75bc6"),
        {"cmyk1": (
            "7548deed61df9ee480d09b60ea0a6f85b9b4969d32b4112e1ee03a66c712b7b9",
            "2c27a1368afc9d888f40406bbe472bbd98c68126fdcff437d588ec0654a26cb2"),
         "rgb": (
            "3ef3942a30eb9af24345a76fcc2b09ae41b69c17bcafce1f6c84aaeb8b25d19c",
            "c48f07346bcaa4bdd2ed9effeb6313cd984b049fc896be8a5e7392e2a1fc2c44")},
    ),
    "c2-cmy-r0700x0625@10x10": (
        "61c9493f88937c43b03c9fae0059d75bca4b01a6d43615d73d53c0c7fd78e23f",
        ("7a9d68c63dc5eb09d5caf7b561b968a9e671a2603b9ccc42dfaa6bf3b0474304",
         "d6b1a9314a4107106d96465e8103ae5a97027802c4d69c4f8895721ba6790743",
         "fb28d0f38c466fc0076090b51dff531bfa73fba117f384fa6720e254554499f5"),
        {"cmyk1": (
            "de5b780665844156031662da03bca39965c278ca49c30d71f4c8b08e5bb2e266",
            "abaeac7944902a187ee73ec063662ec97e0ddf9f075fdb31cc6dae3f34fc05da"),
         "rgb": (
            "dc183494dc3b3e400724aca04d6a02181a33370ab7b0ad53d2865de5adc8416c",
            "f7e84e56a44649b1cb30dc2a950d7685b95cc38ed9b4b7301e5a84629e589bc2")},
    ),
    "c2-cmy-r0775x0700@10x10": (
        "c5f88ab3d1c67b224ee42ea843a3b743fd3940dbf29671f044ac44aeb22d717c",
        ("e49fc001df90701970fd7c25c7c0f832232a75b985bf425b44363c093e2d1097",
         "5d3f9d86a6e303043ea9eb8e30d71a00e134d44a8a5a0af74192cfc4e9487801",
         "fb2540bb8c6615f38ec57792079d075ed8f152ed4107ce06048cb93e88a1ab14"),
        {"cmyk1": (
            "ea6ed569350d99ec19e3f06ad283801868e40117ff4b16d0c2c0cbf5ee820503",
            "583f2bfbd18ec3bcc226e1a708e657f487683f7abef586199c4021d90d6ed564"),
         "rgb": (
            "9fa334a420f36b55dca4c8f61ac35713e4e5b1b2ee09876f3b6a39f3bada296b",
            "2258418ec46d1a2b8dff0866cb6934bfcbeae5ce6aed9f2d88d1a070b602ccff")},
    ),
    "c2-cmy-r0850x0700@10x10": (
        "551c37e4ad4ace8010999804ac0e10b85a40b0ac15da33bd350c0a82df8c8581",
        ("5b7dd5a5b4c0e393388f479e969fd6d31c3f8d8197b51a5d504d3afa29451dc4",
         "7815c4fc47d50e8ab579d91719161936ac7b98848d80e5a5c753bf4ab938352b",
         "911b169eac4cfbd01ba8724f386af87f2e9ce4a0f7e13c1275a15bc4163015a4"),
        {"cmyk1": (
            "5b4e8eaf8028fb14a16d58f7a90178efbdbc5464a1fcb85d7828d611f11cab77",
            "aa67eb8b2e13f5ffe91dc91944945e5e974f8cb1e8d10ab8cc0f5c747fc3a55b"),
         "rgb": (
            "b7f3ea3a0f69b89375c4043c6fe877e4b26726813e4dfe52b80cf745068f7658",
            "c7850016228bd8323558b7ec28a31fd28ba4d7a932c80320b128bbe12281f2e3")},
    ),
    "c2-cmy-r0700-p300@10x10": (
        "fff1c4016e9127a074128c9bf4c0150b20178a1c8e415813ca01b98c143efdaf",
        ("5f50fc5662b7da753a5f43cd2e128d221002eab5ed814c40b9ca8f54c4dcf284",
         "1d8270a4711f424f00880d6a4b39483efc91356da561e56d448cc8568cd77430",
         "d9c6bdabb7e374bcc80a48ecc0be6a2a4290860bf236b14a31c45ae9052a4402"),
        {"cmyk1": (
            "efd4836c9cb14af573135e46dd691872f4d0020689e8ef7b2d3ad58ad873cb00",
            "0e2e4cb2c53fa98f17d5a1f3bb41e2edfab1ce2a1627a8407c999859f4f14e21"),
         "rgb": (
            "d5c5e5a692a425c6163fdac1b24be8721a6da357db793db2a0d83682809a354a",
            "9083123696948bd997b95c5bb4606e4e4b20f4f6b59b6f2abd05ac1f2caf8a29")},
    ),
}
ROWS = tuple(EMIT_GOLDENS)


@pytest.fixture(scope="module")
def emitted(tmp_path_factory) -> dict[tuple[str, str], tuple]:
    """(row, route) -> (spec, volume, volume directory), emitted once."""
    base = tmp_path_factory.mktemp("cmy-emission")
    out = {}
    for ref in ROWS:
        spec = parse_format_id(ref)
        for route, engine in ENGINES.items():
            out_dir = base / f"{ref}-{route}"
            out[(ref, route)] = (spec, emit_volume(
                spec, PAYLOAD, Q, out_dir, paper=PAPER, printer=engine),
                out_dir)
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "manifest.json").read_text())


# ------------------------------------------------------------- goldens

@pytest.mark.parametrize("route", sorted(ENGINES))
@pytest.mark.parametrize("ref", ROWS)
def test_emission_goldens(ref: str, route: str, emitted) -> None:
    gt_sha, plane_sha, by_route = EMIT_GOLDENS[ref]
    _spec, vol, out_dir = emitted[(ref, route)]
    assert vol.plan.n_pages == 1
    page = vol.pages[0]
    assert (page.ps_sha256, _sha(out_dir / "manifest.json")) == \
        by_route[route]
    assert page.gt_sha256 == gt_sha
    assert page.gt_plane_sha256 == plane_sha
    assert len(set(plane_sha)) == 3
    assert _sha(page.ps_path) == page.ps_sha256
    packed = np.load(page.gt_path)
    assert hashlib.sha256(packed.tobytes(order="C")).hexdigest() == gt_sha


# Printed size, both routes: a fork guard, not per-commit feedback.  Jobs
# (2026-10-11): c3@35x24 31,208,308 B cmyk1 / 14,184,230 B rgb;
# c2-r0775x0700@53x37 32,380,665 B cmyk1 / 15,061,180 B rgb (ASCII85
# masks, under cmy8's ASCIIHex composite).
PRINTED_GOLDENS = {
    "c3-cmy-r0850@35x24": (200_000, (
        "1a9fdf3b3b6c9500b5d8d83066eb4c7f9383a63b3e2480e018b5e27f232eec65",
        ("e192bd323ebfb383624e25a46af3be176c6b9201ee88be679a175108ac9db0fb",
         "607c323de366afef5d5ce602c235e9d42f3e277b07a239d88159e541a75712da",
         "7dbf95136b85080852966d4d3d2e9d08035218eefce825d123f76f1da6633c50"),
        {"cmyk1":
            "4c8bc5513eb54981e137fdf15489c50b6fd8e5eb825544e6dc6907cfb1d7a373",
         "rgb":
            "055836cba9ac0bd30895fc4e4cf4d43b60e63788530ed2ffdf174b8fc0772d6b"},
    )),
    "c2-cmy-r0775x0700@53x37": (500_000, (
        "20c133b59edf2e3a8fb78fb1eac64e428fd37d1dfdf634e4de9d1ad735f91347",
        ("8e3c30924d8a3183c4f2c093ac77d191c32f02e9830021c6b38fb4f2c8a2e5b3",
         "49031073d250f4ff3da14225dafd68e6839f45af008c48435059a147595accf3",
         "012b474dc4076fde2f02ff36fcd24cb0fe148f37194fe7cc9f0e6a81fc6c3e0a"),
        {"cmyk1":
            "a3582d00da0a68b18c936317f98f8896d4d8cbdc7f472ec9c239c4b3ae88e41f",
         "rgb":
            "c9a47246f499b2c595f901368fcc374748ba4c18a9514c86093527574f5b517c"},
    )),
}


@pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the printed-size emission goldens",
)
@pytest.mark.parametrize("route", sorted(ENGINES))
@pytest.mark.parametrize("ref", sorted(PRINTED_GOLDENS))
def test_printed_size_emission_goldens(ref: str, route: str,
                                       tmp_path: Path) -> None:
    n_bytes, (gt_sha, plane_sha, ps_sha) = PRINTED_GOLDENS[ref]
    vol = emit_volume(parse_format_id(ref),
                      bytes(i % 251 for i in range(n_bytes)), Q,
                      tmp_path / "v", paper=PAPER, printer=ENGINES[route])
    assert vol.plan.n_pages == 1
    page = vol.pages[0]
    assert page.ps_sha256 == ps_sha[route]
    assert page.gt_sha256 == gt_sha
    assert page.gt_plane_sha256 == plane_sha


# ----------------------------------------------------------------- job

@pytest.mark.parametrize("ref", ROWS)
def test_rgb_is_three_colour_masks_and_cmyk1_one_composite(
        ref: str, emitted) -> None:
    rgb = emitted[(ref, "rgb")][1].pages[0].ps_path.read_text("ascii")
    cmyk1 = emitted[(ref, "cmyk1")][1].pages[0].ps_path.read_text("ascii")
    assert rgb.count("imagemask") == 3
    assert rgb.count("/ASCII85Decode filter imagemask") == 3
    assert rgb.count("setrgbcolor") == 3
    for banned in ("setcmykcolor", "DeviceCMYK", "@PJL", "Indexed",
                   " image\n"):
        assert banned not in rgb
    assert "imagemask" not in cmyk1 and "setrgbcolor" not in cmyk1
    assert cmyk1.count("/DeviceCMYK setcolorspace") == 1


@pytest.mark.parametrize("engine", [TEST_RGB, PRINTERS["hp-m281"]],
                         ids=lambda e: e.printer_id)
@pytest.mark.parametrize("ref", ["c2-cmy8-r0700@10x10", "c2-cmy7@10x10"])
def test_the_rgb_route_refuses_overlap_families(ref: str, engine: Printer,
                                                tmp_path: Path) -> None:
    spec = parse_format_id(ref)
    with pytest.raises(ValueError,
                       match=rf"{engine.printer_id}: the rgb route .* "
                             rf"{spec.codec_family.name} has overlap"):
        emit_volume(spec, PAYLOAD, Q, tmp_path / "v", paper=PAPER,
                    printer=engine)
    assert list(tmp_path.iterdir()) == []


# 2026-10-12 (W2b, R21; the W2a refuter's carry): `--printer default`
# beside a colour format emitted cmyk1 silently — an engine without a
# colour record now refuses every colour family, v2 and fossil alike.
@pytest.mark.parametrize("ref", ["c2-cmy-r0700@10x10", "c2-cmy8-r0700@10x10",
                                 "c2-cmy7@10x10"])
def test_an_engine_without_a_colour_record_refuses_colour(
        ref: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="default: no colour record"):
        emit_volume(parse_format_id(ref), PAYLOAD, Q, tmp_path / "v",
                    paper=PAPER, printer=PRINTERS["default"])
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(SystemExit, match="default: no colour record"):
        cli.main(["capacity", "--format", ref, "--source-fraction", "0.5",
                  "--printer", "default"])


# The retained recipes' door (`--coding`, W2b ii) refuses the same engine
# on a colour coding; its K codings and the recipes' engines are untouched.
def test_the_coding_door_refuses_colour_on_an_engine_without_a_record(
        tmp_path: Path) -> None:
    payload = tmp_path / "p.bin"
    payload.write_bytes(PAYLOAD)
    with pytest.raises(SystemExit, match="default: no colour record"):
        cli.main(["generate", "--coding", "c3-cmy8-p120-v1", "--printer",
                  "default", "--source-fraction", "0.5", str(payload),
                  "-o", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


def test_the_engine_names_a_fossil_route_too(capsys) -> None:
    head = ["capacity", "--format", "L:c2-cmy8-p120-v0@3328x2304",
            "--source-fraction", "0.5", "--json"]
    assert cli.main([*head, "--printer", "xerox-altalink-c8245"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["printer"], out["color_route"]) == ("xerox-altalink-c8245",
                                                    "cmyk1")
    for engine in ("hp-m281", "default"):
        with pytest.raises(SystemExit):
            cli.main([*head, "--printer", engine])


def test_k_ignores_the_route_and_records_the_engine(tmp_path: Path) -> None:
    spec = parse_format_id("c3-k-r0550@10x10")
    plain = emit_volume(spec, PAYLOAD[:1024], Q, tmp_path / "a", paper=PAPER)
    named = emit_volume(spec, PAYLOAD[:1024], Q, tmp_path / "b", paper=PAPER,
                        printer=PRINTERS["hp-m281"])
    assert plain.pages[0].ps_sha256 == named.pages[0].ps_sha256
    assert plain.pages[0].gt_sha256 == named.pages[0].gt_sha256
    assert _manifest(tmp_path / "a")["printer_id"] is None
    assert _manifest(tmp_path / "b")["printer_id"] == "hp-m281"
    with pytest.raises(ValueError, match="name the printer once"):
        emit_volume(spec, PAYLOAD[:1024], Q, tmp_path / "c", paper=PAPER,
                    printer=PRINTERS["hp-m281"], printer_id="hp-m281")


def test_cli_printer_beside_format(tmp_path: Path, capsys) -> None:
    payload = tmp_path / "p.bin"
    payload.write_bytes(PAYLOAD)
    head = ["--format", "c2-cmy-r0700@10x10", "--source-fraction", "0.5",
            "--paper", PAPER]
    assert cli.main(["generate", *head, "--printer", "hp-m281",
                     str(payload), "-o", str(tmp_path / "rgb")]) == 0
    assert "engine hp-m281 (rgb route)" in capsys.readouterr().out
    man = _manifest(tmp_path / "rgb")
    assert man["printer_id"] == "hp-m281"
    assert man["codec"]["renderer"]["rgb_solid"] == {
        plane: list(rgb) for plane, rgb in
        zip("CMY", PRINTERS["hp-m281"].rgb_solid)}
    assert (tmp_path / "rgb" / "page000.ps").read_text(
        "ascii").count("imagemask") == 3
    assert cli.main(["generate", *head, str(payload),
                     "-o", str(tmp_path / "cmyk1")]) == 0
    capsys.readouterr()
    assert _manifest(tmp_path / "cmyk1")["printer_id"] is None
    assert _manifest(tmp_path / "cmyk1")["codec"]["renderer"] == \
        CMYK1_RENDERER

    assert cli.main(["capacity", *head, "--printer", "hp-m281",
                     "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["printer"], out["color_route"]) == ("hp-m281", "rgb")
    assert out["stream_tier"] == "guaranteed" and "plane_tier" not in out
    for refused in (
            ["--format", "c2-cmy8-r0700@10x10", "--printer", "hp-m281"],
            ["--format", "c2-cmy-r0700@10x10", "--printer", "no-such"]):
        with pytest.raises(SystemExit):
            cli.main(["capacity", *refused, "--source-fraction", "0.5"])


# ------------------------------------------------------------ manifest

@pytest.mark.parametrize("ref,stream_tier", [
    ("c2-cmy-r0700@10x10", "guaranteed"),
    ("c2-cmy-r0775x0700@10x10", "not-at-this-dial (needs q <= 17/36)"),
])
def test_the_manifest_records_the_engine_route_and_cmy_law(
        ref: str, stream_tier: str, emitted) -> None:
    rgb = _manifest(emitted[(ref, "rgb")][2])
    cmyk1 = _manifest(emitted[(ref, "cmyk1")][2])
    assert rgb["printer_id"] == "test-rgb"
    assert cmyk1["printer_id"] == "xerox-altalink-c8245"
    assert rgb["codec"]["renderer"] == {
        "route": "rgb", "color_space": "DeviceRGB",
        "plane_order": ["C", "M", "Y"],
        "rgb_solid": {"C": [10, 160, 245], "M": [230, 20, 180],
                      "Y": [245, 240, 15]},
        "W": "unpainted paper", "operation": "three imagemasks, one per toner",
        "filter": "ASCII85"}
    assert cmyk1["codec"]["renderer"] == CMYK1_RENDERER
    for man in (rgb, cmyk1):
        codec = man["codec"]
        assert codec["state_ids"] == [W, C, M, Y]
        assert codec["word_states"] == [W, C]
        assert codec["word_zero_rule"] == \
            "domain 9, u = n_dust + site, MSB → Y"
        assert codec["dust_law"] == "balance"
        pooled = man["pooled_fountain"]
        assert pooled["stream_tier"] == stream_tier
        assert "plane_tier" not in pooled
    groups = rgb["pooled_fountain"].get("column_groups")
    if ref == "c2-cmy-r0775x0700@10x10":
        assert groups["dead_stream_ceiling"] == {"hi": "17/36",
                                                 "lo": "19/36"}
        assert "dead_plane_ceiling" not in groups
    else:
        assert groups is None


# ------------------------------------------------------------------ GT

def _tile(field: np.ndarray, spec, counter: int) -> np.ndarray:
    _page, ty, tx = spec.tile_address(counter)
    return field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]


def _furniture(spec, tile: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    word = pilots.word_site_cells_yx(spec.family_seed)
    dust = pilots.dust_site_cells_yx(spec.family_seed, spec.n_dust)
    return tile[word[:, 0], word[:, 1]], tile[dust[:, 0], dust[:, 1]]


def _balance_fill(word_states: np.ndarray, n_dust: int) -> list[int]:
    """Design §2.5, R3 as amended: each dust site to the lowest running
    total from the tile's own word states, ties M, Y, W, C."""
    totals = Counter({state: 0 for state in (M, Y, W, C)})
    totals.update(int(s) for s in word_states)
    fill = []
    for _ in range(n_dust):
        state = min((M, Y, W, C), key=lambda s: totals[s])
        fill.append(state)
        totals[state] += 1
    return fill


@pytest.mark.parametrize("ref", ROWS)
def test_the_page_speaks_the_alphabet_word_rule_and_balance_law(
        ref: str, emitted) -> None:
    spec, vol, _ = emitted[(ref, "cmyk1")]
    field = gt_cell_states(vol.pages[0].gt_path, spec)
    assert set(np.unique(field).tolist()) == set(channel.CMY_STATE_IDS)
    counters = range(spec.tiles_per_page)
    values = pilots.word_values(spec.seed, list(counters), pilots.PLANE_K)
    for counter in counters:
        words, dust = _furniture(spec, _tile(field, spec, counter))
        yellow = keystream.color_word_zero_mask(spec.seed, counter,
                                                spec.n_dust)
        np.testing.assert_array_equal(
            words, np.where(values[counter] == 1, C, np.where(yellow, Y, W)))
        assert pilots.decode_color_word(words, spec.seed, spec.codec) \
            == counter
        fill = np.asarray(_balance_fill(words, spec.n_dust), np.uint8)
        np.testing.assert_array_equal(dust, fill[
            keystream.color_dust_permutation(spec.seed, counter,
                                             spec.n_dust)])


@pytest.mark.parametrize("key", sorted(TILES))
def test_the_w0_vector_tiles_are_on_the_emitted_page(key, emitted) -> None:
    ref, counter = key
    spec, vol, _ = emitted[(ref, "rgb")]
    words, dust = _furniture(spec, _tile(
        gt_cell_states(vol.pages[0].gt_path, spec), spec, counter))
    assert words.tolist() == ids(TILES[key]["words"])
    assert dust.tolist() == ids(TILES[key]["dust"])


_MASK = re.compile(
    r"(\S+) (\S+) translate\n\S+ \S+ scale\n(\S+) (\S+) (\S+) setrgbcolor\n"
    r"(\d+) (\d+) true \[[^\]]*\]\n"
    r"currentfile /ASCII85Decode filter imagemask\n(.*?)~>", re.S)


@pytest.mark.parametrize("ref", ROWS)
def test_the_rgb_job_reads_back_to_the_plane_gt(ref: str, emitted) -> None:
    """The three masks decoded in numpy: each sits at the field origin in
    its engine colour and IS its plane's GT; painted over white and each
    pixel thresholded to the nearest of W/C/M/Y, the page is the GT."""
    spec, vol, out_dir = emitted[(ref, "rgb")]
    man = _manifest(out_dir)
    oy, ox = man["origin_dots_yx"]
    page_h_dots = man["page_dots_xy"][1]
    packed = np.load(vol.pages[0].gt_path)
    h = packed.shape[1]
    w = spec.cells_yx[1] * spec.cell_dots
    gt = np.unpackbits(packed, axis=2, count=w, bitorder="big")
    masks = _MASK.findall(vol.pages[0].ps_path.read_text("ascii"))
    assert len(masks) == 3
    canvas = np.full((h, w, 3), 255, np.int32)
    for plane, (x_pt, y_pt, r, g, b, mw, mh, data) in enumerate(masks):
        assert (int(mw), int(mh)) == (w, h)
        assert (float(x_pt), float(y_pt)) == pytest.approx(
            (ox * 72 / 600, (page_h_dots - oy - h) * 72 / 600), abs=1e-6)
        rgb = TEST_RGB.rgb_solid[plane]
        assert (r, g, b) == tuple(f"{c / 255:.6f}" for c in rgb)
        rows = np.frombuffer(base64.a85decode(data.encode("ascii")),
                             np.uint8).reshape(h, -(-w // 8))
        bits = np.unpackbits(rows, axis=1, count=w)
        np.testing.assert_array_equal(bits, gt[plane])
        canvas[bits == 1] = rgb
    palette = np.asarray(((255, 255, 255), *TEST_RGB.rgb_solid), np.int32)
    nearest = np.argmin(
        ((canvas[..., None, :] - palette) ** 2).sum(axis=-1), axis=-1)
    for plane in range(3):
        np.testing.assert_array_equal(nearest == plane + 1, gt[plane] == 1)


# ------------------------------------------------------------- reserve

# Design §2.6: blocks and reserve count the POOL — B = ceil(2 k_meta /
# 16384), reserve 16 + bit_length(B * Z - 1).
@pytest.mark.parametrize("ref,reserves", [
    ("c2-cmy-r0700@53x37", (16, 17, 17)),
    ("c2-cmy-r0775x0700@53x37", (21, 22, 22)),
])
def test_the_reserve_counts_the_pooled_blocks(ref: str,
                                              reserves: tuple) -> None:
    spec = parse_format_id(ref)
    z = spec.column_groups.n_groups
    for k_meta, blocks, reserve in zip((8_192, 8_193, 10_000), (1, 2, 2),
                                       reserves):
        envelope_bytes = ((k_meta - 1) * spec.aggregate_symbol_bits) // 8 + 1
        plan = plan_volume(spec, envelope_bytes - 36, Q)
        assert (plan.k_meta, plan.k_total) == (k_meta, 2 * k_meta)
        assert fountain.n_blocks_for(plan.k_total) == blocks
        assert fountain.VolumeCode(
            plan.k_total, spec.symbol_bits, spec.seed,
            tiles_per_page=spec.tiles_per_page, n_streams=2,
            groups=spec.column_groups).n_blocks == blocks
        assert capacity.rank_reserve_for(blocks, solves_per_block=z) \
            == reserve
