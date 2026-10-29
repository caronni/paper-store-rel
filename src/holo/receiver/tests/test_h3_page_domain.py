from __future__ import annotations

import pytest

from holo.receiver import data
from holo.receiver.plugins import place
from holo.receiver.tests import _h3_sims, _h3_support
from holo.receiver.tests import _h3_fixture_build

PRESENTED = _h3_sims.PAGE_DOMAIN_PRESENTED
GAP = 1
REST_PAGE = 2

#: The 3-page emit and its render moved to _h3_sims.py 2026-09-05 and are
#: content-cached by conftest as `sim_k_pages_0_2`; the punched single-
#: page variant has no second consumer, so it stays built here from the
#: same two _h3_sims helpers — but through the same two caches, so this
#: module pays its 22.3 s once per tree rather than once per worker per
#: lane run (2026-09-20).  Its frozen table lives here because nothing
#: else materialises it; it is the ordinary `_h3_sims.verify` contract,
#: and a mismatch is generator drift, never a receiver regression.
EXPECTED_PUNCHED: dict[str, str] = {
    _h3_sims.PAGE_DOMAIN_PAYLOAD_NAME: (
        "8671ddae8f557ccd73bad9c1c8e0e10a8389149dc454a76cd0f0440c14e7134d"),
    f"page{REST_PAGE}.tiff": (
        "331a19baf5da227b33ce243e6eca10aeeee6772be975db62f1a7f03e11a91f67"),
}


def test_word_opens_presented_pages_and_never_allocates_the_gap(
        decode_k_pages_0_2, sim_k_pages_0_2):
    record = decode_k_pages_0_2
    assert record.exit_code == 0
    assert record.payload == sim_k_pages_0_2[0].payload_data
    engine = record.engine
    assert engine.live_pages() == frozenset(PRESENTED)
    assert GAP not in engine.live_pages()
    scramble = getattr(engine.geometry, "_scramble", {})
    assert GAP not in scramble


def test_cold_rest_places_a_page_whose_words_are_past_bch(
        tmp_path_factory: pytest.TempPathFactory):
    _h3_support.skip_unless_slow_lane("the damaged-word rest sim")
    reason = _h3_sims.producer_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)
    root = tmp_path_factory.mktemp("page-domain-rest")
    emit = _h3_fixture_build._materialise(
        "k-page2-punched",
        lambda staging: _h3_sims.make_k_pages(staging, (REST_PAGE,),
                                              punch_words=True),
        EXPECTED_PUNCHED, root / "emit")
    captures = _h3_sims.capture_k_pages(emit, (REST_PAGE,))
    record = _h3_fixture_build._decode_group(
        "k-page2-punched", captures, root / "decode", workers=8,
        extra_argv=_h3_sims.PAGE_DOMAIN_BOUND)
    stages = tuple(event.stage for event in record.events
                   if isinstance(event, data.WorkerSeated)
                   and event.plugin == "place")
    assert place.STAGE_COLD_REST in stages
    poses = tuple(event for event in record.events
                  if isinstance(event, data.PoseCommitted))
    assert all(event.route != place.ROUTE_WORD for event in poses)
    rest_poses = tuple(event for event in poses
                       if event.route == place.ROUTE_COLD)
    assert rest_poses
    assert all(event.page == REST_PAGE for event in rest_poses)
    assert REST_PAGE in record.live_pages
    assert GAP not in record.live_pages
