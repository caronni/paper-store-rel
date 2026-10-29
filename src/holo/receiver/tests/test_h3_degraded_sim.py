from __future__ import annotations

import numpy as np

from holo.receiver import data
from holo.receiver.tests import _h3_support
from holo.receiver.tests import test_h3_e2e_sims as sims_pins

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
# the three rows this capture exists for, each pinned where it is read.
# The whole-run job table went with the widened matrix diet 2026-09-20:
# calibrate, ctx, place, survey and tiles.scan are churn on this capture
# and nothing else in the suite read them here.
REFINE_FIRES = 2
RETRY_FIRES = 3
LOCAL_FIRES = 2
REFINE_ADOPTIONS = 1
TILE_OUTCOMES = {"attempted_failed": 8, "below_attempt_floor": 12,
                 "certified": 4}
FAILING_TILE = (3, 2)
FAILING_TILE_ATTEMPTS = {"tiles/scan": 3, "tiles/retry150": 3,
                         "tiles/local150": 2}
# tiles.local fires here and certifies nothing: this capture blanks
# everything outside a central box, so its residue is evidence-limited,
# not context-limited.  The row's own existence proof is the local-patch
# capture in test_h3_plugins_local_ctx.py.
LOCAL_CERTIFICATES = 0


def _plugin_rows(record: object) -> dict[str, dict]:
    return {row["plugin"]: row
            for row in record.report["scheduler"]["plugins"]}


def test_the_degraded_capture_certifies_the_pinned_addresses_and_no_other(
        decode_k_degraded_w1):
    _h3_support.assert_measured(
          "degraded certificate addresses",
          tuple(sorted(decode_k_degraded_w1.certificates)),
          CERTIFIED_ADDRESSES)
    assert decode_k_degraded_w1.certified == CERTIFIED


def test_the_degraded_capture_leaves_tiles_uncertified_by_construction(
        decode_k_degraded_w1):
    # against the clean serial run's pinned count rather than a second
    # decode of it: what this asks is whether the damage still costs
    # certificates, and the clean number is a constant of that sim
    assert decode_k_degraded_w1.certified < sims_pins.K_SERIAL_CERTIFICATES, (
        "the degraded capture must leave rescue work on the table, or it "
        "exercises nothing the clean sim does not")


def test_the_run_stays_open_and_publishes_no_payload(decode_k_degraded_w1):
    assert decode_k_degraded_w1.status == "not-verified"
    assert decode_k_degraded_w1.exit_code != 0
    assert decode_k_degraded_w1.payload is None
    assert decode_k_degraded_w1.out_exists is False
    assert decode_k_degraded_w1.report["run_done"]["status"] == "open"


def test_refine_adopts_the_pinned_share_of_the_revisions_it_fits(
        decode_k_degraded_w1):
    rows = _plugin_rows(decode_k_degraded_w1)
    _h3_support.assert_measured("refine fires", rows["refine"]["jobs"],
                                REFINE_FIRES)
    _h3_support.assert_measured("refine adoptions", rows["refine"]["poses"],
                                REFINE_ADOPTIONS)
    assert rows["refine"]["certificates"] == 0, (
        "refine mints poses, never certificates")


def test_the_local_context_row_adds_attempts_and_no_certificates_here(
        decode_k_degraded_w1):
    rows = _plugin_rows(decode_k_degraded_w1)
    _h3_support.assert_measured("tiles.local fires",
                                rows["tiles.local"]["jobs"],
                                LOCAL_FIRES)
    _h3_support.assert_measured("tiles.local certificates",
                                rows["tiles.local"]["certificates"],
                                LOCAL_CERTIFICATES)


def test_the_retry_rung_re_attempts_tiles_the_first_pass_failed(
        decode_k_degraded_w1):
    rows = _plugin_rows(decode_k_degraded_w1)
    _h3_support.assert_measured("tiles.retry fires",
                                rows["tiles.retry"]["jobs"],
                                RETRY_FIRES)
    outcomes: dict[str, int] = {}
    for event in decode_k_degraded_w1.events:
        if isinstance(event, data.TileOutcome):
            outcomes[event.result] = outcomes.get(event.result, 0) + 1
    _h3_support.assert_measured("degraded tile outcomes", outcomes,
                                TILE_OUTCOMES)


def test_the_one_failing_tile_fails_as_scan_then_retry_then_local(
        decode_k_degraded_w1):
    failed: dict[tuple[int, int], dict[str, int]] = {}
    for event in decode_k_degraded_w1.events:
        if (isinstance(event, data.TileOutcome)
                and event.result == "attempted_failed"):
            per = failed.setdefault((event.ty, event.tx), {})
            per[event.source] = per.get(event.source, 0) + 1
    _h3_support.assert_measured("failing tiles and their attempts", failed,
                                {FAILING_TILE: FAILING_TILE_ATTEMPTS})


def test_every_certificate_the_degraded_run_mints_agrees_with_the_printed_page(
        decode_k_degraded_w1, sim_k):
    """Zero wrong, audited against the PRINTED page rather than a decode.

    It used to read a second decode of the clean sim and compare user
    bits address by address; the page the degraded capture is derived
    from is the stronger and cheaper truth, and it is the same auditor
    test_h3_e2e_modes uses on the exhaustive harvest.  A wrong
    certificate under damage is the one failure no rescue tier may ever
    produce.
    """
    page_cells = (sims_pins.k_page_cells(sim_k)
                  < sims_pins.GT_INK_BELOW).astype(np.uint8)
    checks = sims_pins.audit_k_certificates(decode_k_degraded_w1, sim_k,
                                            page_cells)
    assert checks.n_total == CERTIFIED
    checks.assert_clean()
