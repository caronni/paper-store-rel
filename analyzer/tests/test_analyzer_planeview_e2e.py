"""The driver's command line, and the whole plane view end to end.

The fast tests here are about the command line the harness hands holo3.
The slow one is the qualification: a real cmy8 volume is emitted by the
production generator, its C plane alone is rendered as an ordinary grey
page, and the PRODUCTION receiver decodes it through the plane-view row
and the seven seams.  MEASURED 2026-09-03 on `c3-cmy8-r0550@7x7`:
49/49 tile-streams certified, every one byte-exact against the emitted
user bits, metadata rank 24/24 over the true POOLED equations, ~4 minutes
wall at 4 workers, holo3 exit 2 (the close is deferred).  It is behind `HOLO_RUN_SLOW_TESTS=1` because of that
wall, not because it is flaky.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from analyzer.planeview import drive as drive_mod

H_REF = "L:c2-cmy8-r0850-p120-x1@3392x2368"
SMALL_REF = "c3-cmy8-r0550@7x7"

slow = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="the synthetic plane-view decode takes ~4 minutes "
           "(HOLO_RUN_SLOW_TESTS=1)")


def test_the_argv_is_a_holo3_decode_with_no_close():
    argv = drive_mod.build_argv(
        "PV:x/C", [Path("a.tiff"), Path("b.tiff")], [2400.0, 4800.0],
        out=Path("/tmp/out.bin"), run_dir=Path("/tmp/run"), workers=8,
        diag_port=8023)
    assert argv[0] == "decode"
    assert argv[1:3] == ("a.tiff", "b.tiff")
    assert argv.count("--dpi") == 2
    assert "--no-close" in argv
    assert argv[argv.index("--format") + 1] == "PV:x/C"
    assert argv[argv.index("--workers") + 1] == "8"
    assert argv[argv.index("--diag") + 1] == "8023"


def test_one_dpi_per_scan_is_required():
    with pytest.raises(ValueError):
        drive_mod.build_argv("PV:x/C", [Path("a.tiff")], [2400.0, 4800.0],
                             out=Path("/tmp/o"), run_dir=Path("/tmp/r"))
    with pytest.raises(ValueError):
        drive_mod.build_argv("PV:x/C", [], [], out=Path("/tmp/o"),
                             run_dir=Path("/tmp/r"))


@pytest.mark.parametrize("token", ["--no-close", "--format", "--out",
                                   "--run-dir", "--dpi=1200"])
def test_a_pass_through_may_not_re_set_what_the_harness_sets(token):
    with pytest.raises(ValueError):
        drive_mod.build_argv("PV:x/C", [Path("a.tiff")], [2400.0],
                             out=Path("/tmp/o"), run_dir=Path("/tmp/r"),
                             extra=[token])


def test_a_pass_through_option_survives():
    argv = drive_mod.build_argv(
        "PV:x/C", [Path("a.tiff")], [2400.0], out=Path("/tmp/o"),
        run_dir=Path("/tmp/r"), extra=["--max-pages", "1"])
    assert argv[-2:] == ("--max-pages", "1")


def test_the_plan_checks_the_row_before_it_builds_a_command_line():
    plan = drive_mod.plan(H_REF, "C", [Path("a.tiff")], [2400.0],
                          out=Path("/tmp/o"), run_dir=Path("/tmp/r"))
    assert plan.plane_ref == f"PV:{H_REF}/C"
    assert plan.source_ref == H_REF
    assert plan.row_report["extra_cells_same_set"] is True
    assert "--no-close" in plan.argv


# --------------------------------------------------------------- the e2e

def _generation_reason() -> str | None:
    import importlib

    for module_name in ("holo.format.resolve", "holo.gen.emit"):
        try:
            importlib.import_module(module_name)
        except Exception as error:                  # pragma: no cover
            return f"src/holo generator unavailable: {module_name}: {error!r}"
    return None


@slow
def test_the_plane_view_certifies_a_synthetic_page_byte_exactly(tmp_path):
    reason = _generation_reason()
    if reason is not None:                          # pragma: no cover
        pytest.skip(reason)
    import shutil

    import tifffile
    from scipy import ndimage

    from holo.format.resolve import resolve_format_ref as holo_resolve
    from holo.gen.emit import emit_volume
    from holo3 import snapshot
    from holo3.format import identity

    from analyzer import truth as truth_mod

    spec = holo_resolve(SMALL_REF)
    payload = bytes((index * 37 + 11) % 256 for index in range(4000))
    emit_dir = tmp_path / "emit"
    if emit_dir.is_dir():                           # pragma: no cover
        shutil.rmtree(emit_dir)
    emit_volume(spec, payload, 0.5, emit_dir)
    (tmp_path / "payload.bin").write_bytes(payload)

    planes = np.unpackbits(np.load(emit_dir / "page000_gt.npy"), axis=-1)
    dots_y = spec.layout.cells_yx[0] * spec.cell_dots
    dots_x = spec.layout.cells_yx[1] * spec.cell_dots
    cyan = planes[0, :dots_y, :dots_x]
    border = 96
    canvas = np.full((dots_y + 2 * border, dots_x + 2 * border), 245,
                     np.uint8)
    canvas[border:border + dots_y, border:border + dots_x] = np.where(
        cyan != 0, 35, 245)
    upsampled = np.repeat(np.repeat(canvas, 2, axis=0), 2, axis=1)
    image = np.round(np.clip(ndimage.gaussian_filter(
        upsampled.astype(np.float32), 1.0), 0, 255)).astype(np.uint8)
    capture = tmp_path / "planeC-1200dpi.tiff"
    tifffile.imwrite(capture, image)

    run_dir = tmp_path / "run"
    code = drive_mod.run(SMALL_REF, "C", [capture], [1200.0],
                         out=tmp_path / "out.bin", run_dir=run_dir,
                         workers=4)
    # holo3 reports NOT RECOVERED (2) because --no-close defers the
    # close by construction; that is this harness's success code.
    assert code == drive_mod.EXPECTED_NO_CLOSE_CODE
    built = sorted(tmp_path.glob("run.*"))
    assert built, "holo3 wrote no run dir"
    facts = snapshot.read(built[-1] / snapshot.NAME)
    certificates = [fact for fact in facts
                    if type(fact).__name__ == "Certificate"]
    row = identity.resolve_format_ref(SMALL_REF)
    assert len(certificates) == row.tiles_per_page == 49
    assert {cert.stream_id for cert in certificates} == {"C"}
    assert all(cert.source.startswith("planeview/")
               for cert in certificates)

    truth = truth_mod.load_truth(emit_dir, tmp_path / "payload.bin", row, 1,
                                 format_ref=SMALL_REF)
    for cert in certificates:
        key = (int(cert.page), int(cert.ty), int(cert.tx), "C")
        want = truth.user_bits.get(key)
        assert want is not None, key
        assert np.array_equal(np.asarray(cert.user_bits),
                              np.asarray(want)), key
