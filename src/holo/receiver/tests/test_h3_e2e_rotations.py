from __future__ import annotations

import inspect
import sys

import numpy as np
import pytest

from holo.receiver.tests import _h3_sims, _h3_support
from holo.receiver.tests import _h3_fixture_build
from holo.receiver.tests import test_h3_e2e_sims as sims_pins

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_the_widened_rotations_are_this_modules_only_oracle_gated_witness`.

# frozen 2026-08-29 from np.rot90 of the frozen rot0 bases; re-frozen
# 2026-09-03 for the b8471fc re-key — pure functions of the bases, the
# array witness below stayed green, plus the TIFF container it cannot see.
K_ROT_TIFF_SHA256 = {
    1: "0dd0726a7bde0e9201958927b621ba36de17074896b4305c3b312cd3c93e8932",
    2: "d5b101893d0a5b98fd6cb05d40d0380e82798b3b71950f14d779e555f486f7d1",
    3: "d26d250d7648b58d7cec4e7fd948125a11e59bf079da0a2871ae4889a057c86d",
}
COLOR_ROT_TIFF_SHA256 = {
    1: "65b9c34967d433413831e6a9f48a19ac56038f458285c5bc2fe66149a01ccc21",
    2: "13b371dfa0784ab40dbaa6456ea74223e02769f46710af53d1cb60d2fe7b96e7",
    3: "9f5bfe7a53320e22b1bebce794cedf721af9754b02d5879977610932d8073273",
}

K_RASTER_SHAPE = (3072, 3072)

SWEEP_LANE_ROTATIONS = ("color-rot2", "color-rot3")


def k_record(rot_k: int, decode_k_w8, decode_k_rot):
    return decode_k_w8 if rot_k == 0 else decode_k_rot(rot_k)


@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_k_sim_decodes_verified_at_every_rotation(rot_k, decode_k_w8,
                                                  decode_k_rot, sim_k):
    record = k_record(rot_k, decode_k_w8, decode_k_rot)
    assert record.rot_k == rot_k
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_k.payload_data
    _h3_support.assert_golden(f"K rot{rot_k} recovered payload sha256",
                              record.payload_sha256,
                              _h3_sims.K_PAYLOAD_SHA256)
    assert len(record.payload) == 6000
    assert record.certified >= sims_pins.K_SERIAL_CERTIFICATES


@pytest.mark.parametrize("rot_k", [1, 2, 3])
def test_rotated_k_rasters_match_their_frozen_shas(rot_k, sim_k_rot, sim_k):
    capture = sim_k_rot(rot_k)
    # the three frames exist and are three different rasters: the pins
    # are per-frame, so the table itself is checked here rather than in a
    # meta-test of its own (retired 2026-09-20)
    assert set(K_ROT_TIFF_SHA256) == {1, 2, 3}
    assert len(set(K_ROT_TIFF_SHA256.values())) == 3
    _h3_support.assert_golden(f"K rot{rot_k} raster sha256",
                              _h3_sims.sha256_file(capture.tiff),
                              K_ROT_TIFF_SHA256[rot_k])
    assert capture.tiff_sha256 == K_ROT_TIFF_SHA256[rot_k]
    assert capture.tiff_sha256 != sim_k.tiff_sha256
    assert capture.format_ref == sim_k.format_ref
    assert capture.payload_sha256 == sim_k.payload_sha256


def test_rot90_of_the_k_base_raster_reproduces_the_frozen_rotations(sim_k,
                                                                    sim_k_rot):
    import tifffile

    base = np.asarray(tifffile.imread(sim_k.tiff))
    assert base.shape == K_RASTER_SHAPE
    for rot_k in (1, 2, 3):
        turned = np.asarray(tifffile.imread(sim_k_rot(rot_k).tiff))
        assert np.array_equal(turned, np.rot90(base, rot_k, axes=(0, 1)))
        assert np.array_equal(np.rot90(turned, 4 - rot_k, axes=(0, 1)), base)


def test_colour_sim_decodes_verified_at_rot1(decode_color_rot1, sim_color):
    assert decode_color_rot1.rot_k == 1
    assert decode_color_rot1.exit_code == 0
    assert decode_color_rot1.status == "verified"
    assert decode_color_rot1.payload == sim_color.payload_data
    _h3_support.assert_golden("colour rot1 recovered payload sha256",
                              decode_color_rot1.payload_sha256,
                              _h3_sims.COLOR_PAYLOAD_SHA256)
    assert len(decode_color_rot1.payload) == 20000
    assert (decode_color_rot1.certified
            >= sims_pins.COLOR_SOURCE_SYMBOLS)


def test_rotated_colour_raster_matches_its_frozen_sha(sim_color_rot,
                                                      sim_color):
    capture = sim_color_rot(1)
    _h3_support.assert_golden("colour rot1 raster sha256",
                              _h3_sims.sha256_file(capture.tiff),
                              COLOR_ROT_TIFF_SHA256[1])
    assert capture.tiff_sha256 != sim_color.tiff_sha256
    assert capture.emit_dir == sim_color.emit_dir


def test_colour_rot1_mints_zero_wrong_certificates(decode_color_rot1,
                                                   sim_color):
    page_bits = sims_pins.colour_page_bits(sim_color)
    assert page_bits.shape[:2] == (640, 640)
    checks, known_total, n_addresses = sims_pins.audit_colour_certificates(
        decode_color_rot1, sim_color, page_bits)
    checks.assert_clean()
    assert n_addresses > 0
    assert known_total == (
        n_addresses * sims_pins.COLOR_PLANES
        * (sims_pins.COLOR_WORD_SITES + sims_pins.COLOR_DUST_SITES)
        + decode_color_rot1.certified * sims_pins.COLOR_PAYLOAD_CELLS)


def test_k_rot2_mints_zero_wrong_certificates(decode_k_rot, sim_k):
    record = decode_k_rot(2)
    page_cells = (sims_pins.k_page_cells(sim_k)
                  < sims_pins.GT_INK_BELOW).astype(np.uint8)
    checks = sims_pins.audit_k_certificates(record, sim_k, page_cells)
    assert checks.n_total == record.certified >= 48
    checks.assert_clean()


@pytest.mark.parametrize("rot_k", [2, 3])
def test_colour_sim_decodes_verified_at_the_widened_rotations(
        rot_k, sim_color, sim_color_rot, decode_root):
    _h3_support.skip_unless_oracle_sweeps(
        f"the colour rot{rot_k} decode (~7 s each, widened matrix)")
    capture = sim_color_rot(rot_k)
    _h3_support.assert_golden(f"colour rot{rot_k} raster sha256",
                              _h3_sims.sha256_file(capture.tiff),
                              COLOR_ROT_TIFF_SHA256[rot_k])
    record = _h3_fixture_build._decode_once(f"color-rot{rot_k}", capture,
                                      decode_root, workers=8)
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_color.payload_data
    _h3_support.assert_golden(f"colour rot{rot_k} recovered payload sha256",
                              record.payload_sha256,
                              _h3_sims.COLOR_PAYLOAD_SHA256)
    checks, _known, addresses = sims_pins.audit_colour_certificates(
        record, sim_color, sims_pins.colour_page_bits(sim_color))
    checks.assert_clean()
    assert addresses > 0


CORE_LANE_WITNESS = {
    "k-rot0": ("test_k_sim_decodes_verified_at_every_rotation",
               "decode_k_w8"),
    "k-rot1": ("test_k_sim_decodes_verified_at_every_rotation",
               "decode_k_rot"),
    "k-rot2": ("test_k_sim_decodes_verified_at_every_rotation",
               "decode_k_rot"),
    "k-rot3": ("test_k_sim_decodes_verified_at_every_rotation",
               "decode_k_rot"),
    "color-rot1": ("test_colour_sim_decodes_verified_at_rot1",
                   "decode_color_rot1"),
}

SWEEP_LANE_WITNESS = "test_colour_sim_decodes_verified_at_the_widened_rotations"

ORACLE_GATE_CALL = "skip_unless_oracle_sweeps"


def _this_module() -> object:
    return sys.modules[__name__]


def _rotation_parameters(function: object) -> tuple:
    for mark in getattr(function, "pytestmark", ()):
        if mark.name == "parametrize" and mark.args[0] == "rot_k":
            return tuple(mark.args[1])
    raise AssertionError(f"{function.__name__} carries no rot_k parametrize")


def test_every_core_lane_rotation_has_an_ungated_decoding_witness():
    module = _this_module()
    checks = _h3_support.Checks("core-lane rotation witnesses")
    for rotation, (test_name, fixture) in sorted(CORE_LANE_WITNESS.items()):
        function = getattr(module, test_name, None)
        if not checks.check(f"{rotation}: {test_name} exists",
                            callable(function)):
            continue
        parameters = inspect.signature(function).parameters
        checks.check(f"{rotation}: {test_name} requests {fixture}",
                     fixture in parameters,
                     f"requests {sorted(parameters)}")
        checks.check(f"{rotation}: {test_name} is not oracle-gated",
                     ORACLE_GATE_CALL not in inspect.getsource(function),
                     "a core-lane rotation behind the sweep gate is a "
                     "silent demotion")
    checks.assert_clean()


def test_the_widened_rotations_are_this_modules_only_oracle_gated_witness():
    """Scoped to THIS module's own witnesses, and the name says so.

    `test_h3_e2e_field_frame.py` puts two more rotation witnesses behind
    the sweeps gate (W3b, 2026-09-08) — deliberately, with the lane
    arithmetic in its docstring — and they are gated by their FIXTURES
    rather than by a call in the test body, so neither this sweep nor a
    repo-wide one would see them.  What this test guards is the demotion
    it can see: a rotation of this module's own witness set moving out
    of the core lane.
    """
    module = _this_module()
    widened = getattr(module, SWEEP_LANE_WITNESS)
    source = inspect.getsource(widened)
    assert ORACLE_GATE_CALL in source
    _h3_support.assert_measured("widened rotation parametrize",
                               _rotation_parameters(widened), (2, 3))
    assert set(SWEEP_LANE_ROTATIONS) == {"color-rot2", "color-rot3"}
    gated = sorted(
        name for name, member in vars(module).items()
        if name.startswith("test_") and callable(member)
        and ORACLE_GATE_CALL in inspect.getsource(member))
    assert gated == [SWEEP_LANE_WITNESS]
