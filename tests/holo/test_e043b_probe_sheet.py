"""experiments/043-m281-cmy-probe/probe_sheet2.py (docs/CMY-PROBE-M281.md §9): the manifest schema and counts,
every swept value in both constructs, the checkerboard and band ground truth, the lean job, and (gs) the render
is the plan dot for dot."""
from __future__ import annotations

import importlib.util
import io
import shutil
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from holo.devices.registry import PRINTERS

PROBE2 = Path(__file__).resolve().parents[2] / "experiments" / "043-m281-cmy-probe" / "probe_sheet2.py"


def _load() -> ModuleType:
    name = "e043b_probe_sheet2"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, PROBE2)
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
                         "fiducials", "bands", "checkerboards", "bars", "dots", "job"]
    assert (man["tag"], man["dpi"], man["page_dots_xy"]) == ("E043b-m281-cmy-probe2", 600, [4960, 7016])
    solid = PRINTERS["hp-m281"].rgb_solid
    assert man["lookup"] == {"W": [255, 255, 255], **{t: list(v) for t, v in zip("CMY", solid)}}
    assert [f["id"] for f in man["fiducials"]] == ["F0", "F1", "F4", "F2", "F3"]
    assert [(b["name"], b["arm"], b["cell_dots"], b["gt_key"], b["y_dots"]) for b in man["bands"]] == [
        (f"B{k + 1}", a, c, f"states_c{c}", 283 + k * 456) for k, (a, c) in enumerate(
            (("mask-a85", 2), ("I-2", 2), ("I-8", 2), ("I-ref", 2), ("mask-a85", 3), ("I-2", 3)))]
    assert all((b["x_dots"], b["w_dots"], b["h_dots"], b["rows"] * b["cell_dots"], b["cols"] * b["cell_dots"])
               == (283, 4392, 432, 432, 4392) for b in man["bands"])
    bar_keys = ["id", "kind", "toner", "axis", "rgb", "construct", "x_dots", "y_dots", "w_dots", "h_dots",
                "gt_key"]
    assert all(list(b) == bar_keys for b in man["bars"])
    kinds = {k: sum(b["kind"] == k for b in man["bars"]) for k in
             ("sweep", "registry", "white", "scrambled", "screened")}
    assert kinds == {"sweep": 72, "registry": 6, "white": 4, "scrambled": 2, "screened": 1}
    assert len({b["id"] for b in man["bars"]}) == len(man["bars"]) == 85
    assert {(b["x_dots"] - 283) % 221 for b in man["bars"]} == {0}
    assert {b["axis"] for b in man["bars"] if b["kind"] == "sweep"} == {"G", "grid", "B"}
    assert {(b["toner"], b["construct"], tuple(b["rgb"])) for b in man["bars"] if b["kind"] == "registry"} == {
        (t, c, v) for t, v in zip("CMY", solid) for c in ("I-8", "I-ref")}
    assert len(man["checkerboards"]) == 12 and len(man["dots"]) == 15
    assert all(set(c) == {"id", "pair", "cell_dots", "construct", "x_dots", "y_dots", "w_dots", "h_dots"}
               for c in man["checkerboards"])
    assert all(set(d) == {"id", "toner", "pattern", "x_dots", "y_dots", "w_dots", "h_dots"} for d in man["dots"])
    assert last_y <= 6732 and last_y == max(d["y_dots"] + d["h_dots"] for d in man["dots"])
    assert man["job"]["bytes"] == len(job)


def test_every_swept_value_in_both_constructs(built) -> None:
    _, _, man, *_ = built
    sweeps = [b for b in man["bars"] if b["kind"] == "sweep"]
    by_value: dict[tuple, set[str]] = {}
    for b in sweeps:
        by_value.setdefault((b["toner"], tuple(b["rgb"])), set()).add(b["construct"])
    assert set(map(frozenset, by_value.values())) == {frozenset({"mask-a85", "I-2"})}
    assert sorted(v[1] for t, v in by_value if t == "C") == list(range(176, 191, 2))
    assert sorted((v[0], v[2]) for t, v in by_value if t == "M") == [
        (r, b) for r in (236, 238, 240, 242) for b in range(188, 199, 2)]
    assert sorted(v for t, v in by_value if t == "Y") == [(255, 255, b) for b in (0, 8, 16, 24)]
    assert all(v[0] == 0 and v[2] == 255 for t, v in by_value if t == "C")


def test_checkerboard_ground_truth_alternates(built) -> None:
    mod = _load()
    p, *_ = built
    for c in p.checkerboards:
        cd = c["cell_dots"]
        st = mod.checker_states("".join(c["pair"]), c["h_dots"] // cd, c["w_dots"] // cd)
        a, b = (mod.STATE_OF[t] for t in c["pair"])
        assert st[0, 0] == a and st[0, 1] == b and st[1, 0] == b and st[1, 1] == a
        assert (st[:, 1:] != st[:, :-1]).all() and (st[1:, :] != st[:-1, :]).all()
    page, _ = mod.s1.planned_page(p)
    chk = next(c for c in p.checkerboards if c["pair"] == ["C", "M"] and c["cell_dots"] == 3)
    patch = page[chk["y_dots"]:chk["y_dots"] + 6, chk["x_dots"]:chk["x_dots"] + 6]
    assert (patch[:3, :3] == p.lookup["C"]).all() and (patch[:3, 3:] == p.lookup["M"]).all()
    assert (patch[3:, :3] == p.lookup["M"]).all() and (patch[3:, 3:] == p.lookup["C"]).all()


def test_band_fields_and_gt(built) -> None:
    mod = _load()
    p, _, man, nb, _ = built
    gt = np.load(io.BytesIO(nb))
    dot_ids = sorted(d["id"] for d in man["dots"])
    assert sorted(gt.files) == sorted(["states_c2", "states_c3", "bar_scrambled-C", "bar_scrambled-M", *dot_ids])
    assert gt["states_c2"].shape == (216, 2196) and gt["states_c3"].shape == (144, 1464)
    for key in ("states_c2", "states_c3"):
        assert set(np.unique(gt[key])) == {0, 1, 2, 4}
    sheet1 = mod.s1.cell_field(np.random.default_rng(43))
    assert np.array_equal(gt["states_c2"], sheet1)
    assert np.array_equal(gt["states_c3"], mod.s1.PRESENCE_IDS[np.random.default_rng(45).choice(4, size=(144, 1464))])
    for d in man["dots"]:
        assert gt[d["id"]].shape == (96, 96) and 0 < gt[d["id"]].mean() <= 0.5


def test_job_is_lean(built) -> None:
    p, job, *_ = built
    text = job.decode("ascii")
    assert text.startswith("%!PS-Adobe-3.0\n%%Title: e043b M281 cmy probe 2 J=")
    assert "@PJL" not in text and "\x1b" not in text
    assert text.count("showpage") == 1 and text.rstrip().endswith("%%EOF")
    for word in ("RunLengthDecode", "FlateDecode", "LZWDecode", "DCTDecode", "sethalftone", "setscreen"):
        assert word not in text
    n_iref = sum(b["arm"] == "I-ref" for b in p.bands) + sum(b["construct"] == "I-ref" for b in p.bars)
    assert n_iref == 4
    for op in ("HPImageNeutralAxis", "ColorSmartImageHalftone", "HPColorTrapping",
               "HPImageAdaptiveHalftoning"):
        assert text.count(f"/{op} where") == n_iref
    assert text.count(" where ") == 4 * n_iref
    assert _load().iref_matches(text, p)


@pytest.mark.skipif(shutil.which("gs") is None, reason="ghostscript missing")
def test_gs_render_is_the_plan(built, tmp_path: Path) -> None:
    mod = _load()
    p, job, *_ = built
    path = tmp_path / "e043b.ps"
    path.write_bytes(job)
    res = mod.check(path, p)
    assert res["pass"], res
    assert res["fastcolor"]["differing_dots_checkerboards"] == res["fastcolor"]["differing_dots_dots"] == 0
