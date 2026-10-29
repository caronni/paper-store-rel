"""experiments/043-m281-cmy-probe/probe_sheet3.py (docs/CMY-PROBE-M281.md §10): the manifest schema and counts,
every band's lookup and field, the bars in their zones, the lean job, and (gs, HOLO_RUN_GS_TESTS=1) the render is
the plan dot for dot."""
from __future__ import annotations

import importlib.util
import io
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

PROBE3 = Path(__file__).resolve().parents[2] / "experiments" / "043-m281-cmy-probe" / "probe_sheet3.py"

# §10's table: (pitch, C, M (R, B)); Y is (255, 255, 0) throughout
TABLE = ((2, 176, (240, 192)), (3, 176, (240, 192)), (2, 178, (240, 192)), (3, 178, (240, 192)),
         (2, 184, (240, 192)), (3, 184, (240, 192)), (2, 192, (240, 192)), (3, 192, (240, 192)),
         (2, 176, (240, 194)), (3, 176, (240, 194)), (2, 176, (242, 192)), (3, 176, (242, 192)),
         (2, 176, (238, 192)), (2, 176, (240, 192)), (3, 176, (240, 192)))
NINE = [("C", [0, g, 255]) for g in (176, 178, 184, 192)] + [
    ("M", [r, 0, b]) for r, b in ((240, 192), (240, 194), (242, 192), (238, 192))] + [("Y", [255, 255, 0])]
ZONES_DOTS = {"left": (283, 1110), "middle": (2291, 3094), "right": (3732, 4299)}  # 12-47, 97-131, 158-182 mm


def _load() -> ModuleType:
    name = "e043c_probe_sheet3"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, PROBE3)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


@pytest.fixture(scope="module")
def built():
    return _load().build()


def test_manifest_schema_and_counts(built) -> None:
    p, job, man, nb, last_y = built
    assert list(man) == ["tag", "dpi", "page_dots_xy", "seed_cells", "seed_cells_c3", "seed_layout", "lookup",
                         "fiducials", "bands", "bars", "job"]
    assert (man["tag"], man["dpi"], man["page_dots_xy"]) == ("E043c-m281-cmy-probe3", 600, [4960, 7016])
    assert (man["seed_cells"], man["seed_cells_c3"], man["seed_layout"]) == (47, 48, 49)
    assert man["lookup"] == {"W": [255, 255, 255], "C": [0, 176, 255], "M": [240, 0, 192], "Y": [255, 255, 0]}
    assert [f["id"] for f in man["fiducials"]] == ["F0", "F1", "F4", "F2", "F3"]
    assert len(man["bands"]) == 15 and len(man["bars"]) == 30
    band_keys = ["name", "arm", "x_dots", "y_dots", "w_dots", "h_dots", "cell_dots", "rows", "cols", "gt_key",
                 "lookup", "note"]
    assert all(list(b) == band_keys and b["note"] for b in man["bands"])
    assert [(b["name"], b["y_dots"]) for b in man["bands"]] == [(f"B{k + 1}", 283 + k * 384) for k in range(15)]
    assert all((b["arm"], b["x_dots"], b["w_dots"], b["h_dots"], b["rows"] * b["cell_dots"],
                b["cols"] * b["cell_dots"]) == ("mask-a85", 283, 4392, 336, 336, 4392) for b in man["bands"])
    bar_keys = ["id", "kind", "toner", "axis", "rgb", "construct", "x_dots", "y_dots", "w_dots", "h_dots",
                "gt_key", "zone"]
    assert all(list(b) == bar_keys for b in man["bars"])
    assert len({b["id"] for b in man["bars"]}) == 30
    assert last_y <= 6732 and last_y == max(b["y_dots"] + b["h_dots"] for b in man["bars"])
    assert man["job"]["bytes"] == len(job)


def test_every_band_lookup_and_gt_key(built) -> None:
    _, _, man, *_ = built
    for b, (cd, c_g, (m_r, m_b)) in zip(man["bands"], TABLE, strict=True):
        assert (b["cell_dots"], b["gt_key"]) == (cd, f"states_c{cd}")
        assert (b["rows"], b["cols"]) == ((168, 2196) if cd == 2 else (112, 1464))
        assert b["lookup"] == {"W": [255, 255, 255], "C": [0, c_g, 255], "M": [m_r, 0, m_b], "Y": [255, 255, 0]}


def test_fields_are_seeded_and_shared(built) -> None:
    mod = _load()
    p, _, man, nb, _ = built
    gt = np.load(io.BytesIO(nb))
    assert sorted(gt.files) == ["states_c2", "states_c3"]
    ids = mod.s1.PRESENCE_IDS
    assert np.array_equal(gt["states_c2"], ids[np.random.default_rng(47).choice(4, size=(168, 2196))])
    assert np.array_equal(gt["states_c3"], ids[np.random.default_rng(48).choice(4, size=(112, 1464))])
    for key in ("states_c2", "states_c3"):
        assert set(np.unique(gt[key])) == {0, 1, 2, 4}
    assert np.array_equal(mod.build()[0].states["states_c2"], gt["states_c2"])
    page, _ = mod.s1.planned_page(p)
    for b in man["bands"]:
        cd, st = b["cell_dots"], gt[b["gt_key"]]
        for r, c in ((0, 0), (5, 77), (st.shape[0] - 1, st.shape[1] - 1)):
            state = int(st[r, c])
            want = b["lookup"]["WCMY"[(0, 1, 2, None, 3)[state]]]
            assert (page[b["y_dots"] + r * cd, b["x_dots"] + c * cd] == want).all()


def test_bars_in_their_zones(built) -> None:
    _, _, man, *_ = built
    bars = man["bars"]
    for zone, (lo, hi) in ZONES_DOTS.items():
        zb = [b for b in bars if b["zone"] == zone]
        assert len(zb) == 10 and sum(b["kind"] == "white" for b in zb) == 1
        assert sorted((b["toner"], b["rgb"]) for b in zb if b["kind"] == "sweep") == sorted(NINE)
        assert all(lo <= b["x_dots"] and b["x_dots"] + b["w_dots"] <= hi for b in zb)
        assert all((b["w_dots"], b["h_dots"]) == (192, 48) for b in zb)
        xs = {b["x_dots"] for b in zb}
        assert len(xs) > 1 and {(x - min(xs)) % 292 for x in xs} == {0}
    for b in bars:
        mm = round(b["x_dots"] * 25.4 / 600)
        assert b["construct"] == (f"mask-a85@{mm}" if b["kind"] == "sweep" else "none")
        assert b["gt_key"] is None
    assert {b["axis"] for b in bars if b["kind"] == "sweep"} == {"G", "grid", "B"}
    occ = np.zeros((7016, 4960), np.uint8)
    for b in bars:
        occ[b["y_dots"]:b["y_dots"] + 48, b["x_dots"]:b["x_dots"] + 192] += 1
    assert occ.max() == 1
    assert min(b["y_dots"] for b in bars) == man["bands"][-1]["y_dots"] + 336 + 48
    assert {(b["y_dots"] - min(x["y_dots"] for x in bars)) % 72 for b in bars} == {0}


def test_job_is_lean(built) -> None:
    p, job, *_ = built
    text = job.decode("ascii")
    assert text.startswith("%!PS-Adobe-3.0\n%%Title: e043c M281 cmy probe 3 J=")
    assert "PJL" not in text and "\x1b" not in text and "/HP" not in text and " where " not in text
    assert text.count("setpagedevice") == 1 and text.index("setpagedevice") < text.index("%%Page: 1 1")
    assert text.count("showpage") == 1 and text.rstrip().endswith("%%EOF")
    for word in ("RunLengthDecode", "FlateDecode", "LZWDecode", "DCTDecode", "sethalftone", "setscreen",
                 "colorimage", " image\n"):
        assert word not in text
    assert text.count("imagemask") == len(p.paints) == 5 + 15 * 3 + 27
    assert text.count("ASCII85Decode") == 15 * 3 + 27 and text.count("ASCIIHexDecode") == 5


@pytest.mark.skipif(os.environ.get("HOLO_RUN_GS_TESTS") != "1" or shutil.which("gs") is None,
                    reason="gs gate needs HOLO_RUN_GS_TESTS=1 and ghostscript")
def test_gs_render_is_the_plan(built, tmp_path: Path) -> None:
    mod = _load()
    p, job, man, nb, _ = built
    path = tmp_path / "e043c.ps"
    path.write_bytes(job)
    res = mod.check(path, p, job, man, nb)
    assert res["pass"], res
    assert res["second_build_identical"] and res["fastcolor"]["differing_dots_bars"] == 0
