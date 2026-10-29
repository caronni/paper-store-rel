"""experiments/043-m281-cmy-probe/probe_sheet.py: the I-ref band is e041's bytes, the manifest is the
frozen schema the readout reads, the job is lean, and (gs) the render is the plan dot for dot."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import shutil
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from holo.gen.ps import _a85_lines

PROBE = Path(__file__).resolve().parents[2] / "experiments" / "043-m281-cmy-probe" / "probe_sheet.py"
SHEET1_PRINTED_SHA = "d97a683fb63a0db99dbd227c0ebfbb89026f376baa5b4a5ac78de90a75677385"  # e043 §043.1b/p


def _load() -> ModuleType:
    name = "e043_probe_sheet"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, PROBE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


@pytest.fixture(scope="module")
def built():
    return _load().build()


def test_holo_a85_lines_are_e041_a85_lines() -> None:
    s12 = _load().s12
    rng = np.random.default_rng(43)
    blobs = [rng.bytes(n) for n in (1, 2, 3, 4, 5, 127, 128, 129, 20000)]
    blobs += [bytes(64), bytes(7) + b"\xff" * 9, np.arange(256, dtype=np.uint8).tobytes() * 40]
    blobs += [next(b for b in (rng.bytes(4000) for _ in range(200))
                   if any(ln.startswith(" %") for ln in _a85_lines(b)))]
    pct = 0
    for blob in blobs:
        lines = _a85_lines(blob)
        pct += sum(ln.startswith(" %") for ln in lines)
        assert ("\n".join(lines) + "\n").encode("ascii") == s12.a85_lines(blob)
    assert pct > 0, "no line exercised the leading-space rule"


def test_iref_band_is_e041_image_block(built) -> None:
    mod = _load()
    p, job, *_ = built
    assert mod.iref_matches(job.decode("ascii"), p)
    band = next(b for b in p.bands if b["arm"] == "I-ref")
    block = mod.iref_e041_block(band, p.states, p.lookup)
    hexes = "".join(f"{r:02x}{g:02x}{b:02x}" for r, g, b in (p.lookup[k] for k in "WCMY"))   # the registry's values
    assert block.startswith(f"gsave\n[/Indexed /DeviceRGB 3 <{hexes}>] setcolorspace\n")
    assert "\n".join(mod.IREF_PRELUDE) in block and block.endswith("~>\ngrestore\n")


def test_manifest_schema_counts_and_gt(built) -> None:
    mod = _load()
    p, job, man, nb, last_y = built
    assert list(man) == ["tag", "dpi", "page_dots_xy", "seed_cells", "seed_layout", "lookup", "fiducials",
                         "bands", "bars", "job"]
    assert (man["tag"], man["dpi"], man["page_dots_xy"]) == ("E043-m281-cmy-probe", 600, [4960, 7016])
    assert man["lookup"] == {k: list(v) for k, v in mod.registry_lookup().items()}   # the default build follows the registry
    assert [f["id"] for f in man["fiducials"]] == ["F0", "F1", "F4", "F2", "F3"]
    assert all(set(f) == {"id", "x_mm", "y_mm", "w_mm", "h_mm", "x_dots", "y_dots", "w_dots", "h_dots"}
               for f in man["fiducials"])
    assert [(b["name"], b["arm"], b["y_dots"]) for b in man["bands"]] == [
        (f"B{k + 1}", a, 283 + k * 456) for k, a in enumerate(("M-hex", "M-a85", "I-2", "I-8", "I-ref"))]
    assert all((b["x_dots"], b["w_dots"], b["h_dots"], b["rows"], b["cols"], b["cell_dots"], b["gt_key"])
               == (283, 4392, 432, 216, 2196, 2, "states") for b in man["bands"])
    bar_keys = ["id", "kind", "toner", "axis", "rgb", "construct", "x_dots", "y_dots", "w_dots", "h_dots",
                "gt_key"]
    assert all(list(b) == bar_keys for b in man["bars"])
    kinds = {k: sum(b["kind"] == k for b in man["bars"]) for k in
             ("sweep", "registry", "white", "scrambled", "screened")}
    assert kinds == {"sweep": 213, "registry": 15, "white": 4, "scrambled": 2, "screened": 1}
    assert len({b["id"] for b in man["bars"]}) == len(man["bars"]) == 235
    for lad, n in mod.LADDERS:
        assert sum(b["id"].startswith(lad.name + "-") and b["kind"] == "sweep" for b in man["bars"]) == n
    assert {(b["toner"], b["construct"]) for b in man["bars"] if b["kind"] == "registry"} == {
        (t, c) for t in "CMY" for c in mod.CONSTRUCTS}
    assert {(b["x_dots"] - 283) % 221 for b in man["bars"]} == {0}
    assert last_y <= 6732 and last_y == max(b["y_dots"] + b["h_dots"] for b in man["bars"])
    gt = np.load(io.BytesIO(nb))
    assert sorted(gt.files) == ["bar_scrambled-C", "bar_scrambled-M", "states"]
    assert gt["states"].shape == (216, 2196) and set(np.unique(gt["states"])) == {0, 1, 2, 4}
    assert all(gt[b["gt_key"]].shape == (48, 192) for b in man["bars"] if b["gt_key"])
    assert man["job"]["bytes"] == len(job)


def test_job_is_lean(built) -> None:
    _, job, *_ = built
    text = job.decode("ascii")
    assert text.startswith("%!PS-Adobe-3.0\n%%Title: e043 M281 cmy probe J=")
    assert "@PJL" not in text and "\x1b" not in text
    assert text.count("showpage") == 1 and text.rstrip().endswith("%%EOF")
    for word in ("RunLengthDecode", "FlateDecode", "sethalftone", "setscreen"):
        assert word not in text
    for op in ("HPImageNeutralAxis", "ColorSmartImageHalftone", "HPColorTrapping",
               "HPImageAdaptiveHalftoning"):
        assert text.count(f"/{op} where") == 4  # the I-ref band + its three registry bars


def test_legacy_lookup_regenerates_the_printed_sheet_1() -> None:
    p, job, man, *_ = _load().build("legacy-e043a")
    assert hashlib.sha256(job).hexdigest() == man["job"]["sha256"] == SHEET1_PRINTED_SHA
    assert p.lookup["C"] == (0, 208, 255) and len(job) == 8_120_885


@pytest.mark.skipif(shutil.which("gs") is None, reason="ghostscript missing")
def test_gs_render_is_the_plan(built, tmp_path: Path) -> None:
    mod = _load()
    p, job, *_ = built
    path = tmp_path / "e043.ps"
    path.write_bytes(job)
    res = mod.check(path, p)
    assert res["pass"], res
