from __future__ import annotations

import numpy as np

from holo.receiver import data
from holo.receiver.plugins import place
from holo.receiver.tests import _h3_sims, _h3_support
from holo.receiver.tests import _h3_fixture_build
from holo.receiver.tests import test_h3_e2e_sims as sims_pins

K_TILE_DOMAIN = 49
K_EXHAUSTIVE_CERTIFICATES = 49


def certificate_bits(record) -> dict[tuple, bytes]:
    return {key: np.asarray(certificate.user_bits, np.uint8).tobytes()
            for key, certificate in record.certificates.items()}


def close_statuses(record) -> tuple[str, ...]:
    return tuple(event.status for event in record.events
                 if isinstance(event, data.CloseCheck))


#: The k-max-pages-1 decode and its one test retired 2026-09-05 (a whole
#: serial K decode, one consumer): the bounded w1 page domain is pinned on
#: harder material by test_h3_survey_pitch_fallback.py::
#: test_a_capture_that_votes_no_pitch_is_still_read_to_a_verified_close
#: (w1, --max-pages 1, K_PAYLOAD_SHA256, 48 certificates), and decode_k_w1
#: stays the unbounded domain over a 2-page plan whose page 1 is absent.


def test_a_healthy_run_never_schedules_cold_rest(decode_k_w1):
    stages = tuple(event.stage for event in decode_k_w1.events
                   if isinstance(event, data.WorkerSeated)
                   and event.plugin == "place")
    assert place.STAGE_COLD_REST not in stages


def test_worker_count_does_not_change_the_recovered_payload(decode_k_w1,
                                                            decode_k_w8):
    assert decode_k_w1.workers == 1
    assert decode_k_w8.workers == 8
    assert decode_k_w1.payload == decode_k_w8.payload
    assert decode_k_w1.payload_sha256 == decode_k_w8.payload_sha256
    _h3_support.assert_golden("workers-invariant K payload sha256",
                              decode_k_w1.payload_sha256,
                              _h3_sims.K_PAYLOAD_SHA256)
    assert decode_k_w1.exit_code == decode_k_w8.exit_code == 0
    assert decode_k_w1.status == decode_k_w8.status == "verified"


def test_worker_count_never_forks_a_certificate(decode_k_w1, decode_k_w8):
    serial = certificate_bits(decode_k_w1)
    pooled = certificate_bits(decode_k_w8)
    shared = sorted(set(serial) & set(pooled))
    assert len(shared) >= sims_pins.K_SERIAL_CERTIFICATES - 1
    checks = _h3_support.Checks(
        "certificates minted by both the serial and the pooled K run")
    for key in shared:
        checks.equal(f"tile {key} user bits", pooled[key], serial[key])
    checks.assert_clean()
    assert len(serial) == sims_pins.K_SERIAL_CERTIFICATES
    assert len(pooled) >= sims_pins.K_SERIAL_CERTIFICATES
    assert len(set(serial) | set(pooled)) <= K_TILE_DOMAIN


def test_exhaustive_harvest_is_certificate_set_identical_across_workers(
        sim_k, decode_root, decode_k_complete):
    _h3_support.skip_unless_oracle_sweeps(
        "the serial --complete decode (~13 s, the exhaustive C-12 witness)")
    serial = _h3_fixture_build._decode_once(
        "k-complete-w1", sim_k, decode_root, workers=1,
        extra_argv=("--complete", "--max-pages", "1"))
    assert serial.exit_code == decode_k_complete.exit_code == 0
    assert serial.payload == decode_k_complete.payload
    assert set(serial.certificates) == set(decode_k_complete.certificates)
    assert (serial.certificate_signature
            == decode_k_complete.certificate_signature)
    _h3_support.assert_measured("serial exhaustive certificates",
                                serial.certified,
                                K_EXHAUSTIVE_CERTIFICATES)


def test_no_close_never_attempts_a_close_and_publishes_nothing(
        decode_k_no_close):
    assert decode_k_no_close.exit_code == 2
    assert decode_k_no_close.status == "not-verified"
    assert decode_k_no_close.payload is None
    assert not decode_k_no_close.out_exists
    assert not decode_k_no_close.out_path.exists()
    statuses = close_statuses(decode_k_no_close)
    assert statuses
    assert "verified" not in statuses
    assert statuses[-1] == "count_ready"
    assert set(statuses) <= {"open", "count_ready"}
    _h3_support.assert_measured("--no-close certificates",
                                decode_k_no_close.certified,
                                K_EXHAUSTIVE_CERTIFICATES)
    assert "NOT RECOVERED" in decode_k_no_close.stderr


def test_no_close_run_still_reaches_count_readiness(decode_k_no_close):
    closes = [event for event in decode_k_no_close.events
              if isinstance(event, data.CloseCheck)]
    final = closes[-1]
    _h3_support.assert_measured("--no-close close certificates",
                                final.certified,
                                K_EXHAUSTIVE_CERTIFICATES)
    assert final.blocks_counting
    _h3_support.assert_measured("--no-close close symbols used",
                                final.symbols_used,
                                K_EXHAUSTIVE_CERTIFICATES)
    assert final.k_total is not None
    assert final.blocks and all(row.have >= row.needed
                                for row in final.blocks)
    assert all(row.rank is None and not row.solved
               for row in final.blocks)
    _h3_support.assert_measured("--no-close metadata rank",
                                final.metadata_rank,
                                sims_pins.K_METADATA_RANK)
    _h3_support.assert_measured("--no-close metadata equations",
                                final.metadata_n_unique,
                                K_EXHAUSTIVE_CERTIFICATES)


def test_complete_defers_the_close_to_the_end_of_the_harvest(
        decode_k_complete, sim_k):
    statuses = close_statuses(decode_k_complete)
    assert statuses
    assert statuses[-1] == "verified"
    assert statuses.count("verified") == 1
    assert set(statuses[:-1]) == {"deferred"}
    assert decode_k_complete.exit_code == 0
    _h3_support.assert_measured("--complete certificates",
                                decode_k_complete.certified,
                                K_EXHAUSTIVE_CERTIFICATES)
    assert decode_k_complete.certified > sims_pins.K_SERIAL_CERTIFICATES
    assert decode_k_complete.payload == sim_k.payload_data
    _h3_support.assert_golden("--complete recovered payload sha256",
                              decode_k_complete.payload_sha256,
                              _h3_sims.K_PAYLOAD_SHA256)


def test_complete_harvest_covers_every_tile_of_the_page(decode_k_complete,
                                                        sim_k):
    from holo.receiver.format import identity

    row = identity.resolve_format_ref(sim_k.format_ref)
    expected = {(0, ty, tx, "main")
                for ty in range(row.tiles_yx[0])
                for tx in range(row.tiles_yx[1])}
    assert set(decode_k_complete.certificates) == expected
    assert len(expected) == K_TILE_DOMAIN


def test_complete_harvest_mints_zero_wrong_certificates(decode_k_complete,
                                                        sim_k):
    page_cells = (sims_pins.k_page_cells(sim_k)
                  < sims_pins.GT_INK_BELOW).astype(np.uint8)
    checks = sims_pins.audit_k_certificates(decode_k_complete, sim_k,
                                            page_cells)
    _h3_support.assert_measured("--complete certificates audited",
                                checks.n_total,
                                K_EXHAUSTIVE_CERTIFICATES)
    checks.assert_clean()


def test_blank_paper_null_control_certifies_nothing(decode_k_null,
                                                    sim_k_null, sim_k):
    assert sim_k_null.tiff_sha256 != sim_k.tiff_sha256
    assert decode_k_null.exit_code == 2
    assert decode_k_null.status == "not-verified"
    assert decode_k_null.certified == 0
    assert decode_k_null.certificates == {}
    assert decode_k_null.payload is None
    assert not decode_k_null.out_exists
    assert not decode_k_null.out_path.exists()
    assert "NOT RECOVERED" in decode_k_null.stderr


def test_blank_paper_null_control_closes_nothing(decode_k_null):
    statuses = close_statuses(decode_k_null)
    assert statuses == ("open",)
    closes = [event for event in decode_k_null.events
              if isinstance(event, data.CloseCheck)]
    assert closes[-1].metadata_rank == 0
    assert closes[-1].metadata_n_unique == 0
    assert closes[-1].k_total is None
    assert closes[-1].symbols_used == 0
