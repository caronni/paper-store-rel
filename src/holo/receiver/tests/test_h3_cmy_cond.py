"""`tiles.cond`, the conditioned label stream as a priced tile stage, and
gate G13 (CMY-RECEIVER-PLAN A6; CMY-DESIGN §7 (e), R5, §11 G13).

Every ordinary stage decodes cmy's two label streams independently
(BICM).  With one stream certified the other is read GIVEN the sibling's
label bits -- `tile_codec.cmy_soft_demap(scores, stream, sibling)`: hi
given lo is s_C - s_Y where lo is 1 and s_M where it is 0, lo given hi
s_C - s_M or s_Y -- which keeps what the marginal throws away.  R5 makes
that a priced stage of the tile row: `tiles.cond`, the retry's subject,
priced as the scan of its lane (the cmy retry sits at 241 since
2026-10-18), its baseline floor the retry's widened to a below-floor read
(F2 below), born by the stream's own failed or below-floor ordinary
verdict and the sibling's certificate, whichever lands second,
at most once per tile-lane generation, its one attempt at the retry's
BP budget (`tiles.STAGE_COND150`).

What this module states.  The row: born in both orders -- a failure
with the sibling already certified, a sibling certificate with the
failure already standing -- reading exactly the retry's key and the
sibling's tile key; never born without the sibling certified, nor in a
toner family (K, cmy8); priced as the scan of its lane.  On the
in-memory engine with the three tile rows and one real tile: the
conditioned certificate minted in both orders, equal to the truth;
where the stream never certifies, one conditioned attempt per
generation, a generation bump buying exactly one more, and the frontier
draining.  G13 (slow lane, score space, the A3 idiom): per order and per
e043c c2 confusion, 32 fresh tiles through the scaled channel -- the
sibling certifies plainly, BICM fails at the retry's budget, the
conditioned attempt certifies the stimulus's user bits; on the tiles that
need the sibling, another tile's sibling certifies nothing and the
sibling with 10 % of its bits flipped is pinned; no arm certifies bits
that are not the stimulus's.

The G13 channel is this module's (`g13_tile`), and
measure/cmy_calibration/cond_gate.py imports it: the hard-decision
channel C_alpha = (1 - alpha) I + alpha C_hat over a measured state
confusion, each cell scored by the channel's exact W-relative
log-likelihood ratios.  `G13_ROWS` and `G13_ALPHA` are that instrument's
pick, made on its own seeds before this test ran (provenance at the
constants); the analyzer's A5 reads the same constants from here.

LEDGER 2026-10-12 (A6), records, not tests.  The (R*, alpha*) table came
out of cond_gate's three stages on machine 1 (RESULTS-2026-10-12-cond.md):
hi given lo `c2-cmy-r0700x0547@10x10` at alpha 1.875, lo given hi
`c2-cmy-r0547x0625@10x10` at 2.0 -- the windows about 1/8 in alpha wide,
a first confirm at the refine's 1.90625 missing the sibling criterion on
B14 (15/256), so alpha* reads the confirm's whole window.  G13 then
measured, on this module's root: of 128 tiles, 124 certify through the
conditioned attempt alone; B1 hi given lo tile 10 (sibling failed), B1 lo
given hi tile 2 and B14 hi given lo tile 31 (BICM certified) are the
pinned exceptions; another tile's sibling minted nothing in 125 attempts
and never reached the CRC; the sibling with 10 % flipped minted one
certificate, the true bits (B1 lo given hi tile 12, 420 of 3,976 bits
flipped) -- the plan's "certify nothing" for that arm does not hold, and
no negative arm minted a wrong certificate.  The G13 parameters ran 14 to
15 s each at -n 8 in their own xdist groups (17 s for the module).  The
cmy e2e records on a fresh cache, the first lane after A6: `cmy-w8`
VERIFIED, 56 certificates, all `tiles/scan`, `tiles.cond` never born;
`cmy-offset-w8` VERIFIED, 50 certificates (4 `tiles/scan`, 46
`tiles/local150`), `tiles.cond` seated 67 times and fired 0: `tiles.local`
mints both streams of a tile in one job, so the first stream's certificate
births the second's conditioned attempt, which stays seated until its POP
and is retired there (`certified`, 64 times; retire is consulted at the
pop, engine.py:627-634, as the retries are -- the A6 refuter's probe);
3 stood in the frontier when the close preempted the run.  On paper, where the gate measurement saw
768-800 of 840 with a field, one stream certified beside a failed sibling
is the case the row is for.

LEDGER 2026-10-12 (the cmy implementation review, F2).  The row's
baseline was the retry's -- an ordinary verdict `failed` -- so a
below-floor read never conditioned, though a zero marginal can be
decisive given the sibling (the review's probe: joint scores separating
{W, C} from {M, Y}, the hi marginal exactly zero, hi certified given lo;
the engine fired the scan alone).  Now `tiles_sched.COND_BASELINES` =
failed or below the floor, in birth, eligibility and preparation, at
most once per generation as before; the retry keeps `failed` alone, and
the conditioned attempt floors the CONDITIONAL LLRs
(`tiles._attempt_stream` counts supported cells on
`stream_llrs(..., sibling)`).  On paper it buys latency, not yield (the
lead's count over machine 4 runs' events): sheet A, 140 tile-streams read
below the floor after their sibling certified, 139 certified later by
other rows, one never (tile (19, 0) hi); sheet B, 91, all certified later.
"""
from __future__ import annotations

import dataclasses
from concurrent.futures import Future
from types import SimpleNamespace

import numpy as np
import pytest

from holo.receiver import data, engine
from holo.receiver.descriptor import KEY_ATTEMPT, KEY_TILE, RETIRE_CERTIFIED
from holo.receiver.format import identity, keystream, tile_codec
from holo.receiver.plugins import color_sites, tiles, tiles_sched
from holo.receiver.tests import _h3_facts, _h3_support

CAPTURE_ID = _h3_facts.CAPTURE_ID
LANE = (CAPTURE_ID, 0)
ORDERS = ("hi|lo", "lo|hi")
TARGET_OF = {"hi|lo": ("hi", "lo"), "lo|hi": ("lo", "hi")}
SHAPES = ("B1", "B14")

#: e043c sheet 3's state confusions of the two c2 bands G13 is scaled
#: from (true W C M Y x read W C M Y, counts; the M281 probe read at 2400
#: dpi, scratch2/e043c/readout/summary.json, bands B1 and B14).
E043C_CONFUSION_COUNTS: dict[str, tuple[tuple[int, ...], ...]] = {
    "B1": ((79381, 4663, 3225, 4922), (411, 90859, 345, 214),
           (905, 1567, 89897, 254), (1462, 1963, 828, 88032)),
    "B14": ((78698, 4181, 2981, 6331), (304, 90897, 337, 291),
            (597, 1524, 90336, 166), (1486, 2243, 1007, 87549)),
}
#: G13's construction constants, the (R*, alpha*) table: per order the
#: row (the target's rung above the sibling's) and alpha*, picked by
#: measure/cmy_calibration/cond_gate.py on its own seeds (sweep 2026101213,
#: refine 2026101215, confirm 2026101214; RESULTS-2026-10-12-cond.md,
#: artefacts scratch2/e043c/cond/), disjoint from `G13_SEED_ROOT`.  At
#: alpha*, 256 confirm trials per shape (BLER: sibling at 60, BICM at
#: 150, conditioned at 150): hi|lo B1 0.012 / 0.996 / 0.008, B14 0.031 /
#: 0.926 / 0.000; lo|hi B1 0.000 / 0.969 / 0.008, B14 0.000 / 1.000 /
#: 0.031.
G13_ROWS: dict[str, str] = {"hi|lo": "c2-cmy-r0700x0547@10x10",
                             "lo|hi": "c2-cmy-r0547x0625@10x10"}
G13_ALPHA: dict[str, float] = {"hi|lo": 1.875, "lo|hi": 2.0}
G13_SEED_ROOT = 2026101206
G13_TILES = 32
G13_FLIP_FRACTION = 0.1
#: Label (hi << 1 | lo) -> the alphabet's column (W C M Y).
LABEL_TO_COLUMN = np.asarray([tile_codec.CMY_STATE_IDS.index(state)
                              for state in tile_codec.CMY_LABEL_TO_STATE],
                             np.int64)


@dataclasses.dataclass(frozen=True)
class G13Tile:
    address: tuple[int, int, int]
    users: dict[str, np.ndarray]
    labels: dict[str, np.ndarray]
    cut: tiles.TileCut


def g13_channel(shape: str, alpha: float) -> np.ndarray:
    counts = np.asarray(E043C_CONFUSION_COUNTS[shape], np.float64)
    scaled = ((1.0 - alpha) * np.eye(4)
              + alpha * counts / counts.sum(axis=1, keepdims=True))
    if np.any(scaled <= 0.0):
        raise ValueError(f"alpha {alpha} leaves a channel entry <= 0")
    return scaled


def g13_address(index: int, row: identity.FormatRow) -> tuple[int, int, int]:
    return (0, (index // row.tiles_yx[1]) % row.tiles_yx[0],
            index % row.tiles_yx[1])


def g13_label_bits(row: identity.FormatRow, address: tuple[int, int, int],
                   users: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Each stream's label bits in the codec's sequential order: the
    frame XOR the stream's dither, as the generator lays them."""
    counter = row.tile_counter(*address)
    return {fact.stream_id: tile_codec.encode_frame(
                users[fact.stream_id], fact.rung_children)
            ^ keystream.cmy8_dither_bits(
                row.seed, fact.dither_aux, counter,
                tile_codec.bank_transmitted_bits(fact.rung_children))
            for fact in row.streams}


def g13_scores(columns: np.ndarray, uniforms: np.ndarray,
               channel: np.ndarray) -> np.ndarray:
    """Each cell read through the channel at its uniform (inverse CDF),
    scored by the channel's exact log-likelihood ratios against W."""
    read = np.minimum((uniforms[:, None] > np.cumsum(
        channel[columns], axis=1)).sum(axis=1), 3)
    loglik = np.log(channel[:, read].T)
    return loglik[:, 1:] - loglik[:, :1]


def g13_cut(row: identity.FormatRow, geometry: identity.SiteGeometry,
            address: tuple[int, int, int],
            scores: np.ndarray) -> tiles.TileCut:
    """Sequential payload scores onto the tile's payload cells, the
    inverse of `tiles._sequential_payload`; furniture reads 0."""
    page, ty, tx = address
    order = keystream.color_cell_permutation(
        row.seed, row.tile_counter(page, ty, tx), row.payload_cells)
    values = np.zeros((tile_codec.N_CELLS, 3), np.float32)
    values[np.asarray(geometry.payload_flat, np.int64)] = scores[order]
    return tiles.TileCut(
        capture_id="g13", level_index=0, page=page, ty=ty, tx=tx,
        values=values,
        observed_flat=np.arange(tile_codec.N_CELLS, dtype=np.uint16))


def g13_tile(row: identity.FormatRow, geometry: identity.SiteGeometry,
             address: tuple[int, int, int], channel: np.ndarray,
             entropy: tuple[int, ...],
             garbage: str | None = None) -> G13Tile:
    """One fresh tile: random user bits per stream from
    `entropy + (0,)`, one uniform per cell from `entropy + (1,)` (shared
    by every channel a caller reads the same tile through).  `garbage`
    replaces that stream's label bits by coin flips -- a stream no stage
    can certify."""
    rng = np.random.default_rng(entropy + (0,))
    users = {fact.stream_id: rng.integers(0, 2, fact.user_bits,
                                          dtype=np.uint8)
             for fact in row.streams}
    labels = g13_label_bits(row, address, users)
    if garbage is not None:
        labels[garbage] = rng.integers(0, 2, labels[garbage].size,
                                       dtype=np.uint8)
    columns = LABEL_TO_COLUMN[(labels["hi"].astype(np.int64) << 1)
                              | labels["lo"]]
    uniforms = np.random.default_rng(entropy + (1,)).random(columns.size)
    return G13Tile(address, users, labels, g13_cut(
        row, geometry, address, g13_scores(columns, uniforms, channel)))


# ------------------------------------------------------------- the row


def _rows(monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...]) -> None:
    rows = tuple(engine.DESCRIPTOR_BY_NAME[name] for name in names)
    monkeypatch.setattr(engine, "DESCRIPTORS", rows)
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        {row.name: row for row in rows})


def _engine(format_ref: str, push: bool = False) -> engine._Engine:
    instance = engine._Engine(dataclasses.replace(
        _h3_facts.new_engine()._request, format_ref=format_ref), [])
    if not push:
        instance._push_worker = lambda worker: None
    instance._ingest(_h3_facts.capture())
    return instance


def _verdict(stream_id: str, outcome: str = tiles.OUTCOME_FAILED,
             stage: str = tiles.STAGE_SCAN,
             generation: int = 0) -> data.AttemptFact:
    return dataclasses.replace(
        _h3_facts.attempt(outcome), stream_id=stream_id, stage=stage,
        components=(LANE,), generation=generation)


def _certificate(row: identity.FormatRow, stream_id: str,
                 ty: int = 0, tx: int = 0) -> data.Certificate:
    fact = tiles.stream_fact(row, stream_id)
    return data.Certificate(page=0, ty=ty, tx=tx, stream_id=stream_id,
                            user_bits=np.zeros(fact.user_bits, np.uint8),
                            source="tiles/scan")


def _cond_subject(stream_id: str) -> tuple:
    return (tiles.STAGE_SCAN, 0, 0, 0, stream_id, 0, CAPTURE_ID)


def _cond_bookmarks(instance: engine._Engine) -> dict:
    return {subject: worker for (plugin, subject), worker
            in instance._bookmarks.items() if plugin == tiles_sched.PLUGIN_COND}


CMY_REF = "c2-cmy-r0775x0700@10x10"


@pytest.mark.parametrize("target", ("hi", "lo"))
@pytest.mark.parametrize("first", ("failure", "certificate"))
def test_cond_is_born_by_whichever_of_failure_and_sibling_lands_second(
        monkeypatch, first, target):
    _rows(monkeypatch, (tiles_sched.PLUGIN_COND,))
    instance = _engine(CMY_REF)
    sibling = "lo" if target == "hi" else "hi"
    failure = _verdict(target)
    certificate = _certificate(instance.row, sibling)
    arrivals = ((failure, certificate) if first == "failure"
                else (certificate, failure))
    instance._ingest(arrivals[0])
    assert not _cond_bookmarks(instance), "born before both have landed"
    instance._ingest(arrivals[1])
    worker = _cond_bookmarks(instance)[_cond_subject(target)]
    assert set(_cond_bookmarks(instance)) == {_cond_subject(target)}
    assert worker.reads == (
        (KEY_ATTEMPT, 0, 0, 0, target, tiles.STAGE_SCAN, LANE),
        (KEY_TILE, 0, 0, 0, sibling))
    assert tiles_sched.COND_DESCRIPTOR.eligible(instance,
                                                _cond_subject(target))


def test_cond_is_never_born_without_the_sibling_certified(monkeypatch):
    """Inverted 2026-10-12 (the review's F2): a below-floor read IS a
    conditioned baseline, born the moment its sibling certifies."""
    _rows(monkeypatch, (tiles_sched.PLUGIN_COND,))
    instance = _engine(CMY_REF)
    instance._ingest(_verdict("hi"))
    instance._ingest(_verdict("lo", tiles.OUTCOME_BELOW_FLOOR))
    instance._ingest(_certificate(instance.row, "hi", tx=1))
    assert not _cond_bookmarks(instance), (
        "a failure with no certified sibling, a below-floor read with no "
        "certified sibling, and a certificate on another tile birth nothing")
    instance._ingest(_certificate(instance.row, "hi"))
    assert set(_cond_bookmarks(instance)) == {_cond_subject("lo")}, (
        "hi's certificate births lo's attempt off the below-floor read")
    assert tiles_sched.COND_DESCRIPTOR.eligible(instance,
                                                _cond_subject("lo"))


@pytest.mark.parametrize("format_ref", (_h3_facts.FORMAT_REF,
                                        "c3-cmy8-r0550x0550x0547@10x10"))
def test_cond_is_never_born_in_a_toner_family(monkeypatch, format_ref):
    _rows(monkeypatch, (tiles_sched.PLUGIN_COND,))
    instance = _engine(format_ref)
    streams = tuple(fact.stream_id for fact in instance.row.streams)
    for stream_id in streams:
        assert tiles_sched._label_sibling(instance.row, stream_id) is None
    for stream_id in streams:
        instance._ingest(_verdict(stream_id))
    instance._ingest(_certificate(instance.row, streams[0]))
    for stream_id in streams[1:]:
        instance._ingest(_verdict(stream_id, generation=1))
    assert not _cond_bookmarks(instance), (
        "a toner stream's failure beside a certified plane, and that "
        "plane's certificate beside the failures, birth nothing")


def test_cond_is_priced_as_the_scan_of_its_lane():
    store = SimpleNamespace(union_rung_ordinal=lambda ppc: 3)
    cond = tiles_sched.COND_DESCRIPTOR
    assert cond.prices == tiles_sched.SCAN_DESCRIPTOR.prices
    for attempts in (0, 1, 5):
        for level_index in (0, 2):
            scan_subject = (0, 1, 2, CAPTURE_ID, level_index)
            cond_subject = (tiles.STAGE_SCAN, 0, 1, 2, "lo", level_index,
                            CAPTURE_ID)
            assert (cond.cost(store, cond_subject, "payload", attempts, 0)
                    == tiles_sched.SCAN_DESCRIPTOR.cost(
                        store, scan_subject, "payload", attempts, 0))
        union_subject = (0, 1, 2, "ppc")
        cond_union = (tiles.STAGE_UNION, 0, 1, 2, "hi", "ppc", None)
        assert (cond.cost(store, cond_union, "payload", attempts, 0)
                == tiles_sched.UNION_DESCRIPTOR.cost(
                    store, union_subject, "payload", attempts, 0))
    assert tiles.max_iters_for(tiles.STAGE_COND150) \
        == tiles.RETRY_BP_MAX_ITERS


# ------------------------------------------- the row on the engine


class _ImmediateExecutor:

    def submit(self, job: object) -> Future:
        future: Future = Future()
        future.set_result(job())
        return future


def _drain(instance: engine._Engine) -> None:
    executor = _ImmediateExecutor()
    while instance._frontier:
        instance._fill(executor)
        for future in list(instance._inflight):
            instance._merge(future)


def _fires(instance: engine._Engine) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in instance._events:
        if isinstance(event, data.JobDone):
            counts[event.plugin] = counts.get(event.plugin, 0) + 1
    return counts


def _colour_row(cut: tiles.TileCut, scale: float = 1.0
                ) -> data.ColorEvidenceRow:
    """The tile's cut as the colour row of the window over tile (0, 0):
    `_h3_facts.tile_cells` enumerates that tile's cells in the cut's
    flat order."""
    return dataclasses.replace(_h3_facts.color_row(),
                               values=np.asarray(cut.values * scale,
                                                 np.float32))


def _tile_engine(monkeypatch: pytest.MonkeyPatch, order: str,
                 tile: G13Tile) -> engine._Engine:
    _rows(monkeypatch, (tiles_sched.PLUGIN_SCAN, tiles_sched.PLUGIN_RETRY,
                        tiles_sched.PLUGIN_COND))
    instance = _engine(G13_ROWS[order], push=True)
    instance._ingest(_h3_facts.window(
        wid=(CAPTURE_ID, 0, 0, _h3_facts.EXTENT), ordinal=0))
    instance._ingest(_colour_row(tile.cut))
    return instance


def _engine_tile(order: str, garbage: str | None = None) -> G13Tile:
    row = identity.resolve_format_ref(G13_ROWS[order])
    geometry = identity.build_site_geometry(row)
    return g13_tile(row, geometry, (0, 0, 0),
                    g13_channel("B1", G13_ALPHA[order]),
                    (G13_SEED_ROOT, 99, ORDERS.index(order)), garbage)


@pytest.mark.parametrize("order", ORDERS)
def test_the_engine_mints_the_conditioned_certificate_in_both_orders(
        monkeypatch, order):
    """hi given lo: scan fails hi before lo certifies in the same job, so
    lo's CERTIFICATE births hi's attempt; lo given hi: hi certifies
    first, so lo's failed VERDICT does.  Either way the conditioned
    attempt certifies the true bits -- and since 2026-10-18 (the owner's
    price balance) the cmy retry, priced 241 above cond's 20, never
    fires: cond's certificate retires it at its seat."""
    target, sibling = TARGET_OF[order]
    tile = _engine_tile(order)
    instance = _tile_engine(monkeypatch, order, tile)
    _drain(instance)
    certificates = instance.certificates()
    assert certificates[(0, 0, 0, sibling)].source == "tiles/scan"
    minted = certificates[(0, 0, 0, target)]
    assert minted.source == tiles.source_tag(tiles.STAGE_COND150)
    assert np.array_equal(minted.user_bits, tile.users[target])
    assert _fires(instance) == {tiles_sched.PLUGIN_SCAN: 1,
                                tiles_sched.PLUGIN_COND: 1}
    assert any(isinstance(event, data.WorkerRetired)
               and event.plugin == tiles_sched.PLUGIN_RETRY
               and event.cause == RETIRE_CERTIFIED
               for event in instance._events), (
        "the cmy retry is retired by cond's certificate, unfired")
    worker = _cond_bookmarks(instance)[_cond_subject(target)]
    assert worker.seat_seq < 0 and not worker.inflight
    assert tiles_sched.COND_DESCRIPTOR.retire(
        instance, _cond_subject(target)) == RETIRE_CERTIFIED


def test_cond_fires_once_per_generation_and_drains_where_nothing_certifies(
        monkeypatch):
    """lo carries coin flips: hi certifies by scan, lo fails every
    stage.  One conditioned attempt at the first generation; the same
    colour row again changes nothing and buys nothing; a refit of the
    row moves the generation, the scan re-reads lo, and the conditioned
    attempt runs exactly once more.  The frontier drains each time and
    nothing re-births the row."""
    order = "lo|hi"
    tile = _engine_tile(order, garbage="lo")
    instance = _tile_engine(monkeypatch, order, tile)
    _drain(instance)
    assert instance.has_certificate((0, 0, 0, "hi"))
    assert not instance.has_certificate((0, 0, 0, "lo"))
    first = _fires(instance)
    assert first == {tiles_sched.PLUGIN_SCAN: 1, tiles_sched.PLUGIN_RETRY: 1,
                     tiles_sched.PLUGIN_COND: 1}
    instance._ingest(_colour_row(tile.cut))
    _drain(instance)
    assert _fires(instance) == first
    generation = instance.tile_lane_generation((0, 0, 0, CAPTURE_ID, 0))
    instance._ingest(_colour_row(tile.cut, scale=1.01))
    assert instance.tile_lane_generation(
        (0, 0, 0, CAPTURE_ID, 0)) == generation + 1
    _drain(instance)
    assert _fires(instance) == {tiles_sched.PLUGIN_SCAN: 2,
                                tiles_sched.PLUGIN_RETRY: 2,
                                tiles_sched.PLUGIN_COND: 2}
    worker = _cond_bookmarks(instance)[_cond_subject("lo")]
    assert not instance._frontier and not instance._inflight
    assert worker.seat_seq < 0 and not worker.inflight
    assert not tiles_sched.COND_DESCRIPTOR.eligible(instance,
                                                    _cond_subject("lo"))
    assert instance.attempt_verdict(
        0, 0, 0, "lo", tiles.STAGE_COND150, LANE) == (
        tiles.OUTCOME_FAILED, generation + 1)


def _xor_tile(seed: int = 947) -> tuple[np.ndarray, tiles.TileCut]:
    """The review's F2 probe tile on `CMY_REF`: joint scores that tell
    {W, C} from {M, Y} at 12 nats and nothing else, so BOTH label
    marginals are exactly zero and either stream given the other is
    decisive.  Returns (hi's user bits, lo's user bits) and the cut."""
    row = identity.resolve_format_ref(CMY_REF)
    geometry = identity.build_site_geometry(row)
    rng = np.random.default_rng(seed)
    users = {fact.stream_id: rng.integers(0, 2, fact.user_bits,
                                          dtype=np.uint8)
             for fact in row.streams}
    labels = g13_label_bits(row, (0, 0, 0), users)
    scores = np.zeros((row.payload_cells, 3))
    scores[:, 1:] = np.where((labels["hi"] ^ labels["lo"])[:, None],
                             12.0, -12.0)
    return users, g13_cut(row, geometry, (0, 0, 0), scores)


def _floor_engine(monkeypatch: pytest.MonkeyPatch,
                  cut: tiles.TileCut) -> engine._Engine:
    _rows(monkeypatch, (tiles_sched.PLUGIN_SCAN, tiles_sched.PLUGIN_RETRY,
                        tiles_sched.PLUGIN_COND))
    instance = _engine(CMY_REF, push=True)
    instance._ingest(_h3_facts.window(
        wid=(CAPTURE_ID, 0, 0, _h3_facts.EXTENT), ordinal=0))
    instance._ingest(_colour_row(cut))
    return instance


def _lo_certificate(users: dict[str, np.ndarray]) -> data.Certificate:
    return data.Certificate(0, 0, 0, "lo", users["lo"], "tiles/scan")


@pytest.mark.parametrize("first", ("certificate", "read"))
def test_cond_certifies_off_a_below_floor_baseline_in_both_orders(
        monkeypatch, first):
    """The review's F2 probe on the engine: hi's marginal is exactly zero
    (scan reads it below the floor), and given lo's certificate the
    conditioned attempt certifies the true hi bits -- whether lo's
    certificate lands before the below-floor read or after it.  No
    retry: a below-floor read is not the retry's baseline."""
    users, cut = _xor_tile()
    row = identity.resolve_format_ref(CMY_REF)
    geometry = identity.build_site_geometry(row)
    assert tiles.attempt_tile(row, geometry, (cut,), "hi",
                              tiles.STAGE_SCAN).fact.outcome \
        == tiles.OUTCOME_BELOW_FLOOR
    instance = _floor_engine(monkeypatch, cut)
    if first == "certificate":
        instance._ingest(_lo_certificate(users))
        _drain(instance)
    else:
        _drain(instance)
        assert instance.attempt_verdict(
            0, 0, 0, "hi", tiles.STAGE_SCAN, LANE) == (
            tiles.OUTCOME_BELOW_FLOOR,
            instance.tile_lane_generation((0, 0, 0, CAPTURE_ID, 0)))
        assert not _cond_bookmarks(instance)
        instance._ingest(_lo_certificate(users))
        _drain(instance)
    minted = instance.certificates()[(0, 0, 0, "hi")]
    assert minted.source == tiles.source_tag(tiles.STAGE_COND150)
    assert np.array_equal(minted.user_bits, users["hi"])
    assert _fires(instance) == {tiles_sched.PLUGIN_SCAN: 1,
                                tiles_sched.PLUGIN_COND: 1}
    assert set(_cond_bookmarks(instance)) == {_cond_subject("hi")}


def test_cond_fires_once_on_an_uninformative_below_floor_baseline(
        monkeypatch):
    """All-zero scores: no marginal and no conditional information.  The
    scan reads both streams below the floor; lo's certificate births
    hi's conditioned attempt, which runs ONCE, mints nothing (its own
    floor refuses the zero conditional LLRs) and is not born again at
    the same generation -- the same colour row and a second sibling
    certificate fold buy nothing."""
    users, cut = _xor_tile()
    instance = _floor_engine(monkeypatch, dataclasses.replace(
        cut, values=np.zeros_like(cut.values)))
    _drain(instance)
    instance._ingest(_lo_certificate(users))
    _drain(instance)
    first = _fires(instance)
    assert first == {tiles_sched.PLUGIN_SCAN: 1, tiles_sched.PLUGIN_COND: 1}
    assert not instance.has_certificate((0, 0, 0, "hi"))
    assert instance.attempt_verdict(
        0, 0, 0, "hi", tiles.STAGE_COND150, LANE) == (
        tiles.OUTCOME_BELOW_FLOOR,
        instance.tile_lane_generation((0, 0, 0, CAPTURE_ID, 0)))
    assert not tiles_sched.COND_DESCRIPTOR.eligible(instance,
                                                    _cond_subject("hi"))
    instance._ingest(_colour_row(dataclasses.replace(
        cut, values=np.zeros_like(cut.values))))
    instance._ingest(_lo_certificate(users))
    _drain(instance)
    assert _fires(instance) == first
    assert not instance._frontier and not instance._inflight


def test_a_below_floor_baseline_births_no_retry(monkeypatch):
    """The retry keeps its rule (F2's adjustment is the conditioned
    attempt's alone): a below-floor ordinary read, with or without its
    sibling certified, is no retry subject and no retry is eligible on
    it."""
    _rows(monkeypatch, (tiles_sched.PLUGIN_RETRY, tiles_sched.PLUGIN_COND))
    instance = _engine(CMY_REF)
    instance._ingest(_certificate(instance.row, "lo"))
    below = _verdict("hi", tiles.OUTCOME_BELOW_FLOOR)
    instance._ingest(below)
    assert tiles_sched._retry_subjects(instance, below) == ()
    assert not tiles_sched.RETRY_DESCRIPTOR.eligible(instance,
                                                     _cond_subject("hi"))
    assert not any(plugin == tiles_sched.PLUGIN_RETRY
                   for plugin, _subject in instance._bookmarks)
    assert set(_cond_bookmarks(instance)) == {_cond_subject("hi")}


# ------------------------------------------------------------------ G13

#: One tile's outcome, (sibling plain at the scan's budget, target BICM
#: at the retry's, target conditioned at cond150): C certified, F failed,
#: B below the attempt floor, - not attempted (no sibling certificate to
#: condition on).  CFC is a tile that needs its sibling and gets it.
NEEDS_THE_SIBLING = "CFC"
#: The two negative arms, run on every tile that needs its sibling:
#: another tile's certified sibling, and the sibling's own bits with
#: `G13_FLIP_FRACTION` of them flipped.
NEGATIVE_ARMS: tuple[str, ...] = ("other tile", "flipped")
#: Measured 2026-10-12 (the ledger): per (shape, order) the tiles whose
#: outcome is not CFC, and per negative arm (certificates, CRC consults,
#: syndrome-valid CRC refusals).
G13_PINNED: dict[tuple[str, str],
                 tuple[dict[int, str], dict[str, tuple[int, int, int]]]] = {
    ("B1", "hi|lo"): ({10: "FF-"}, {"other tile": (0, 0, 0),
                                    "flipped": (0, 0, 0)}),
    ("B1", "lo|hi"): ({2: "CCC"}, {"other tile": (0, 0, 0),
                                   "flipped": (1, 1, 0)}),
    ("B14", "hi|lo"): ({31: "CCC"}, {"other tile": (0, 0, 0),
                                     "flipped": (0, 0, 0)}),
    ("B14", "lo|hi"): ({}, {"other tile": (0, 0, 0), "flipped": (0, 0, 0)}),
}


def _outcome_letter(result: tiles.TileAttemptResult | None) -> str:
    if result is None:
        return "-"
    return {tiles.OUTCOME_CERTIFIED: "C", tiles.OUTCOME_FAILED: "F",
            tiles.OUTCOME_BELOW_FLOOR: "B"}[result.fact.outcome]


def _g13_run(shape: str, order: str
             ) -> tuple[dict[int, str], dict[str, tuple[int, int, int]]]:
    row = identity.resolve_format_ref(G13_ROWS[order])
    geometry = identity.build_site_geometry(row)
    channel = g13_channel(shape, G13_ALPHA[order])
    target, sibling = TARGET_OF[order]
    sibling_fact = tiles.stream_fact(row, sibling)

    def entropy(index: int) -> tuple[int, ...]:
        return (G13_SEED_ROOT, SHAPES.index(shape), ORDERS.index(order),
                index)

    cases = [g13_tile(row, geometry, g13_address(index, row), channel,
                      entropy(index)) for index in range(G13_TILES)]
    plain = [tiles.attempt_tile(row, geometry, (case.cut,), sibling,
                                tiles.STAGE_SCAN) for case in cases]
    sibling_bits = [
        None if result.certificate is None
        else color_sites.certified_stream_bits(
            row, sibling_fact, row.tile_counter(*case.address),
            result.certificate)
        for result, case in zip(plain, cases)]
    deviations: dict[int, str] = {}
    negatives = {arm: [0, 0, 0] for arm in NEGATIVE_ARMS}
    for index, case in enumerate(cases):
        bicm = tiles.attempt_tile(row, geometry, (case.cut,), target,
                                  tiles.STAGE_RETRY150)
        cond = None
        wrongs: list[tiles.TileAttemptResult] = []
        bits = sibling_bits[index]
        if bits is not None:
            cond = tiles.attempt_tile(row, geometry, (case.cut,), target,
                                      tiles.STAGE_COND150, sibling=bits)
        if bits is not None and bicm.certificate is None:
            other = next(sibling_bits[(index + step) % G13_TILES]
                         for step in range(1, G13_TILES)
                         if sibling_bits[(index + step) % G13_TILES]
                         is not None)
            flipped = bits ^ (np.random.default_rng(entropy(index) + (2,))
                              .random(bits.size) < G13_FLIP_FRACTION)
            wrongs = [tiles.attempt_tile(
                row, geometry, (case.cut,), target, tiles.STAGE_COND150,
                sibling=wrong) for wrong in (other, flipped.astype(np.uint8))]
            for arm, attempt in zip(NEGATIVE_ARMS, wrongs):
                negatives[arm][0] += attempt.certificate is not None
                negatives[arm][1] += attempt.fact.crc_ok is not None
                negatives[arm][2] += attempt.fact.crc_ok is False
        for result, stream_id in ((plain[index], sibling), (bicm, target),
                                  (cond, target), *((attempt, target)
                                                    for attempt in wrongs)):
            if result is not None and result.certificate is not None:
                assert np.array_equal(result.certificate.user_bits,
                                      case.users[stream_id]), (
                    f"tile {index}: {result.fact.stage} certified bits "
                    f"that are not the generator's")
        code = "".join(_outcome_letter(result)
                       for result in (plain[index], bicm, cond))
        if code != NEEDS_THE_SIBLING:
            deviations[index] = code
    return deviations, {arm: tuple(tally) for arm, tally in negatives.items()}


@pytest.mark.parametrize("shape, order", [
    pytest.param(shape, order, id=f"{shape}-{order.replace('|', '-given-')}",
                 marks=pytest.mark.xdist_group(
                     f"g13-{shape}-{order.replace('|', '-given-')}"))
    for shape in SHAPES for order in ORDERS])
def test_g13_the_conditioned_attempt_certifies_where_bicm_fails(shape,
                                                                 order):
    """G13 (CMY-DESIGN §11, R19): per seed the outcome is fixed by the
    stimulus.  No arm mints a certificate that is not the generator's
    bits, the negative arms included; on every tile that needs its
    sibling (the sibling certified, BICM failed) another tile's sibling
    mints nothing; and the tiles that are NOT "the sibling certifies,
    BICM fails, the conditioned attempt certifies" are the measured pin,
    with each negative arm's certificates and CRC exposure beside it.
    The flipped arm is pinned, not asserted empty: a sibling 90 % right
    still carries most of the conditioning, and on these seeds it once
    reaches the true bits (the ledger).  Each parameter is its own xdist
    group: 32 tiles of up to five decodes, most failing at 150
    iterations, are the slow lane's longest chain on one worker."""
    _h3_support.skip_unless_slow_lane(
        "G13's 32 conditioned tiles per shape and order")
    deviations, negatives = _g13_run(shape, order)
    assert negatives["other tile"][0] == 0, (
        "another tile's sibling minted a certificate")
    _h3_support.assert_measured(
        f"G13 {shape} {order}: tiles off {NEEDS_THE_SIBLING}, per negative "
        f"arm (certificates, CRC consults, CRC refusals)",
        (deviations, negatives), G13_PINNED[(shape, order)])
