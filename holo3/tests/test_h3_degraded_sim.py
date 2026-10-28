from __future__ import annotations

import numpy as np
import pytest

from holo3 import data
from holo3.tests import _h3_support

# the clean sims certify every tile on the first attempt, so refine, the
# retry rung and the mop-up row never fire in them; this capture keeps a
# noisy central block of the K sim and blanks the rest
#
# re-keyed by b8471fc: the one failing tile the retry and mop-up rows
# are born from certified instead.  noise sd (15 to 40) and four seeds
# are inert on this capture, so the keep box's left edge is the only
# lever (0.35 to 0.3625 in conftest).  measured on the one-edge box:
# 0.360 and 0.3625 give the pre-fork shape exactly, (3, 2) failing as
# 3 scan + 3 retry + 2 local; 0.365 gives 6 failed / retry 2.  the outer
# bracket is a mirrored-box reading (both columns moved) and transfers
# for the arm's status only: 0.3575 still certifies, 0.37 falls below
# the attempt floor.  six cells wide; expect to retune at the next fork.
CERTIFIED = 4
CERTIFIED_ADDRESSES = ((0, 2, 3, "main"), (0, 3, 3, "main"),
                       (0, 3, 4, "main"), (0, 4, 3, "main"))
JOB_COUNTS = {"calibrate": 3, "ctx": 3, "place": 29, "refine": 2,
              "survey": 1, "tiles.local": 2, "tiles.retry": 3,
              "tiles.scan": 19}
REFINE_ADOPTIONS = 1
TILE_OUTCOMES = {"attempted_failed": 8, "below_attempt_floor": 12,
                 "certified": 4}
RESCUE_ROWS = ("refine", "tiles.retry", "tiles.local")
FAILING_TILE = (3, 2)
FAILING_TILE_ATTEMPTS = {"tiles/scan": 3, "tiles/retry150": 3,
                         "tiles/local150": 2}
# tiles.local fires here and certifies nothing: this capture blanks
# everything outside a central box, so its residue is evidence-limited,
# not context-limited.  The row's own existence proof is the local-patch
# capture in test_h3_plugins_local_ctx.py.
LOCAL_CERTIFICATES = 0


def _jobs(record: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in record.events:
        if isinstance(event, data.JobDone):
            counts[event.plugin] = counts.get(event.plugin, 0) + 1
    return counts


def _plugin_rows(record: object) -> dict[str, dict]:
    return {row["plugin"]: row
            for row in record.report["scheduler"]["plugins"]}


def test_the_degraded_capture_certifies_the_pinned_addresses_and_no_other(
        decode_k_degraded_w1):
    _h3_support.assert_golden(
        "degraded certificate addresses",
        tuple(sorted(decode_k_degraded_w1.certificates)),
        CERTIFIED_ADDRESSES)
    assert decode_k_degraded_w1.certified == CERTIFIED


def test_the_degraded_capture_leaves_tiles_uncertified_by_construction(
        decode_k_degraded_w1, decode_k_w1):
    assert decode_k_degraded_w1.certified < decode_k_w1.certified, (
        "the degraded capture must leave rescue work on the table, or it "
        "exercises nothing the clean sim does not")


def test_the_run_stays_open_and_publishes_no_payload(decode_k_degraded_w1):
    assert decode_k_degraded_w1.status == "not-verified"
    assert decode_k_degraded_w1.exit_code != 0
    assert decode_k_degraded_w1.payload is None
    assert decode_k_degraded_w1.out_exists is False
    assert decode_k_degraded_w1.report["run_done"]["status"] == "open"


@pytest.mark.parametrize("plugin", RESCUE_ROWS)
def test_the_rescue_rows_actually_fire_on_this_capture(decode_k_degraded_w1,
                                                       plugin):
    assert _jobs(decode_k_degraded_w1).get(plugin, 0) > 0, (
        f"{plugin} fired zero times: the capture is not degraded enough to "
        f"exercise the row it exists for")


def test_the_serial_job_counts_are_exact(decode_k_degraded_w1):
    _h3_support.assert_golden("degraded serial job counts",
                              _jobs(decode_k_degraded_w1), JOB_COUNTS)


def test_refine_adopts_the_pinned_share_of_the_revisions_it_fits(
        decode_k_degraded_w1):
    rows = _plugin_rows(decode_k_degraded_w1)
    _h3_support.assert_golden("refine fires", rows["refine"]["jobs"],
                              JOB_COUNTS["refine"])
    _h3_support.assert_golden("refine adoptions", rows["refine"]["poses"],
                              REFINE_ADOPTIONS)
    assert rows["refine"]["certificates"] == 0, (
        "refine mints poses, never certificates")


def test_the_local_context_row_adds_attempts_and_no_certificates_here(
        decode_k_degraded_w1):
    rows = _plugin_rows(decode_k_degraded_w1)
    _h3_support.assert_golden("tiles.local fires",
                              rows["tiles.local"]["jobs"],
                              JOB_COUNTS["tiles.local"])
    _h3_support.assert_golden("tiles.local certificates",
                              rows["tiles.local"]["certificates"],
                              LOCAL_CERTIFICATES)


def test_the_retry_rung_re_attempts_tiles_the_first_pass_failed(
        decode_k_degraded_w1):
    rows = _plugin_rows(decode_k_degraded_w1)
    _h3_support.assert_golden("tiles.retry fires",
                              rows["tiles.retry"]["jobs"],
                              JOB_COUNTS["tiles.retry"])
    outcomes: dict[str, int] = {}
    for event in decode_k_degraded_w1.events:
        if isinstance(event, data.TileOutcome):
            outcomes[event.result] = outcomes.get(event.result, 0) + 1
    _h3_support.assert_golden("degraded tile outcomes", outcomes,
                              TILE_OUTCOMES)


def test_the_one_failing_tile_fails_as_scan_then_retry_then_local(
        decode_k_degraded_w1):
    failed: dict[tuple[int, int], dict[str, int]] = {}
    for event in decode_k_degraded_w1.events:
        if (isinstance(event, data.TileOutcome)
                and event.result == "attempted_failed"):
            per = failed.setdefault((event.ty, event.tx), {})
            per[event.source] = per.get(event.source, 0) + 1
    _h3_support.assert_golden("failing tiles and their attempts", failed,
                              {FAILING_TILE: FAILING_TILE_ATTEMPTS})


def test_every_certificate_the_degraded_run_mints_agrees_with_the_clean_one(
        decode_k_degraded_w1, decode_k_w1):
    checks = _h3_support.Checks("degraded run zero-wrong")
    for key, certificate in sorted(
            decode_k_degraded_w1.certificates.items()):
        clean = decode_k_w1.certificates.get(key)
        checks.check(f"{key} is an address the clean run also certified",
                     clean is not None)
        if clean is None:
            continue
        checks.check(f"{key} carries the clean run's user bits",
                     np.array_equal(np.asarray(certificate.user_bits),
                                    np.asarray(clean.user_bits)),
                     "a wrong certificate under damage is the one failure "
                     "no rescue tier may ever produce")
    checks.assert_clean()


def test_the_degraded_capture_is_a_derived_stimulus_not_a_frozen_artefact(
        sim_k_degraded, sim_k):
    assert sim_k_degraded.tiff_sha256 != sim_k.tiff_sha256
    assert sim_k_degraded.format_ref == sim_k.format_ref
    assert sim_k_degraded.payload_sha256 == sim_k.payload_sha256
    assert sim_k_degraded.tiff.is_file()
