"""Wave-2 P7 verification: holo3/plugins/tiles.py.

Run from the worktree root:
  PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_tiles.py

Proves, in one process:
  * end-to-end mini loops for K / CMY8 / CMY7 (format encode -> evidence ->
    attempt -> certificate == truth user bits), incl. below-floor refusal,
    corrupted evidence failing syndrome/CRC and arming retry150,
    the conflicting-mint raise, and printed_cells_for reproducing the
    emitted page slice with the known-site check exercised pass AND fail;
  * ORACLE PARITY of the copied attempt chains against src/holo (v1):
    holo.receive.payload.attempt_k_tile and
    holo.receive.color_attempts.attempt_color_tile over the same evidence;
  * the ownership freeze against a dense reference walk;
  * tilemap helpers (unresolved streams, sparse done grid, done projection,
    covers) against direct references.
"""
from __future__ import annotations

import sys
import traceback

import numpy as np

# ---- holo3 (the code under test) -----------------------------------------
from holo3.data import Certificate, IntegrityError, TileEvidence
from holo3.format.identity import build_site_geometry, resolve_format_ref
from holo3.format.keystream import color_cell_permutation
from holo3.format.tile_codec import states_to_planes
from holo3.plugins import tiles as h3

# ---- oracles (v1 = the numerics authority) --------------------------------
from holo.format import metadata as v1_metadata
from holo.format.resolve import resolve_format_ref as v1_resolve
from holo.gen.color_compose import _metadata_bits_for_tile, compose_color_tile
from holo.gen.compose import compose_page_cells
from holo.receive import tiles as v1_tiles
from holo.receive.color_attempts import attempt_color_tile
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.evidence_blocks import (
    EvidenceOrigin,
    OwnedPageRows,
    blocks_from_owner_pages,
    tile_attempt_view,
)
from holo.receive.payload import attempt_k_tile

RNG = np.random.default_rng(20260828)
MAG = 6.0
FAILURES: list[str] = []
CHECKS = [0]


def check(name: str, condition: bool, detail: str = "") -> None:
    CHECKS[0] += 1
    if condition:
        print(f"  ok   {name}")
    else:
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL {name} {detail}")


def raises(name: str, exc: type[BaseException], fn) -> None:
    try:
        fn()
    except exc:
        check(name, True)
        return
    except BaseException as other:  # noqa: BLE001
        check(name, False, f"raised {type(other).__name__}: {other}")
        return
    check(name, False, "no exception raised")


def evidence_from_dense(capture_id: str, page: int, ty: int, tx: int,
                        values: np.ndarray, observed: np.ndarray,
                        epoch: int = 0) -> TileEvidence:
    flat = np.flatnonzero(observed).astype(np.uint16)
    return TileEvidence(capture_id, 0, page, ty, tx,
                        np.asarray(values[flat], np.float32), flat,
                        h3.CORE_ARM, epoch)


def cells_to_llr(cells: np.ndarray) -> np.ndarray:
    return ((2.0 * cells.astype(np.float64) - 1.0) * MAG).reshape(-1, 1)


# ============================================================ K family ======

def verify_k() -> None:
    print("\n[K] c3-k-r0550@7x7 end-to-end + oracle parity")
    ref = "c3-k-r0550@7x7"
    row = resolve_format_ref(ref, n_pages=1)
    geom = build_site_geometry(row)
    spec = v1_resolve(ref)
    check("K identity: seed matches v1", row.seed == spec.seed)
    check("K identity: user bits match v1",
          row.streams[0].user_bits == spec.tile_user_bits)

    n_tiles = row.tiles_per_page
    symbol_bits = row.streams[0].symbol_bits
    k_total = 137
    symbols = RNG.integers(0, 2, (n_tiles, symbol_bits), dtype=np.uint8)
    page_cells = compose_page_cells(spec, 0, symbols, k_total)
    counters = np.asarray([row.tile_counter(0, ty, tx)
                           for ty in range(row.tiles_yx[0])
                           for tx in range(row.tiles_yx[1])], np.int64)
    meta_bits = v1_metadata.tile_bits(
        v1_metadata.encode_metadata(0, k_total), counters)
    truth = {}
    for index, counter in enumerate(counters):
        ty, tx = index // row.tiles_yx[1], index % row.tiles_yx[1]
        truth[(ty, tx)] = np.concatenate(
            (np.asarray([meta_bits[index]], np.uint8), symbols[index]))
        del counter

    # ---- printed_cells_for reproduces the emitted page slice -------------
    same = True
    for (ty, tx), user in truth.items():
        field = h3.printed_cells_for(row, geom, 0, ty, tx, user)
        slice_ = page_cells[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
        same = same and np.array_equal(field, slice_)
    check("printed_cells_for == emitted page slice (all 49 tiles)", same)

    ty, tx = 3, 4
    user = truth[(ty, tx)]
    tile_cells = page_cells[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]

    # ---- clean scan attempt ---------------------------------------------
    values = cells_to_llr(tile_cells)
    observed = np.ones(4096, bool)
    block = evidence_from_dense("sha-a", 0, ty, tx, values, observed)
    result = h3.attempt_tile(row, geom, (block,), "main", h3.STAGE_SCAN)
    check("K clean scan certifies",
          result.fact.outcome == h3.OUTCOME_CERTIFIED)
    check("K certificate == truth user bits",
          result.certificate is not None
          and np.array_equal(result.certificate.user_bits, user))
    check("K certificate source tag", result.certificate.source == "tiles/scan")
    check("K n_informative excludes sites",
          result.fact.n_informative == 4096 - row.n_sites,
          str(result.fact.n_informative))

    # ---- oracle parity: v1 attempt_k_tile over the same LLR field --------
    llr_cells = values[:, 0].reshape(64, 64)
    o_record, o_cert = attempt_k_tile(
        llr_cells, spec, (0, ty, tx), AttemptStage.SCAN,
        source_sha256="a" * 64, lane_id="lane", component_block_ids=("b" * 64,))
    check("K oracle parity: state",
          (o_record.state is AttemptState.CERTIFIED)
          == (result.fact.outcome == h3.OUTCOME_CERTIFIED))
    check("K oracle parity: n_informative",
          o_record.n_informative == result.fact.n_informative)
    check("K oracle parity: n_iters",
          o_record.n_iters == result.fact.n_iters,
          f"{o_record.n_iters} vs {result.fact.n_iters}")
    o_user = np.unpackbits(np.frombuffer(o_cert.packed_user_bits, np.uint8),
                           bitorder="little")[:row.streams[0].user_bits]
    check("K oracle parity: user bits",
          np.array_equal(o_user, result.certificate.user_bits))
    check("K oracle parity: printed cells",
          np.array_equal(
              v1_tiles._reencode_printed_cells(
                  spec, int(counters[ty * row.tiles_yx[1] + tx]), 0, ty, tx,
                  user, int(geom.slot_a[counters[ty * row.tiles_yx[1] + tx]]),
                  int(geom.slot_b[counters[ty * row.tiles_yx[1] + tx]])),
              h3.printed_cells_for(row, geom, 0, ty, tx, user)))

    # ---- noisy but recoverable ------------------------------------------
    noisy = values.copy()
    flip = RNG.choice(4096, 60, replace=False)
    noisy[flip] = -noisy[flip]
    noisy_block = evidence_from_dense("sha-a", 0, ty, tx, noisy, observed)
    noisy_result = h3.attempt_tile(row, geom, (noisy_block,), "main",
                                   h3.STAGE_SCAN)
    check("K noisy scan still certifies",
          noisy_result.fact.outcome == h3.OUTCOME_CERTIFIED
          and np.array_equal(noisy_result.certificate.user_bits, user),
          noisy_result.fact.outcome)
    o_noisy, _ = attempt_k_tile(
        noisy[:, 0].reshape(64, 64), spec, (0, ty, tx), AttemptStage.SCAN,
        source_sha256="a" * 64, lane_id="lane", component_block_ids=("b" * 64,))
    check("K oracle parity: noisy n_iters",
          o_noisy.n_iters == noisy_result.fact.n_iters,
          f"{o_noisy.n_iters} vs {noisy_result.fact.n_iters}")

    # ---- corrupted: decoded, failed, arms retry150 -----------------------
    broken = values.copy()
    flip = RNG.choice(4096, 1400, replace=False)
    broken[flip] = -broken[flip]
    broken_block = evidence_from_dense("sha-a", 0, ty, tx, broken, observed)
    broken_result = h3.attempt_tile(row, geom, (broken_block,), "main",
                                    h3.STAGE_SCAN)
    check("K corrupted scan fails",
          broken_result.fact.outcome == h3.OUTCOME_FAILED
          and broken_result.certificate is None,
          broken_result.fact.outcome)
    check("K corrupted fails syndrome or CRC",
          not (broken_result.fact.syndrome_ok and broken_result.fact.crc_ok))
    check("K failed attempt arms retry150 (v2 gate law: always)",
          h3.arms_retry(broken_result.fact, certified=False))
    retry = h3.attempt_tile(row, geom, (broken_block,), "main",
                            h3.STAGE_RETRY150)
    check("K retry150 uses 150 iterations",
          h3.max_iters_for(h3.STAGE_RETRY150) == 150
          and retry.fact.stage == h3.STAGE_RETRY150)
    o_retry, _ = attempt_k_tile(
        broken[:, 0].reshape(64, 64), spec, (0, ty, tx),
        AttemptStage.RETRY150, source_sha256="a" * 64, lane_id="lane",
        component_block_ids=("b" * 64,))
    check("K oracle parity: retry150 outcome + iters",
          o_retry.n_iters == retry.fact.n_iters
          and (o_retry.state is AttemptState.CERTIFIED)
          == (retry.fact.outcome == h3.OUTCOME_CERTIFIED),
          f"{o_retry.n_iters}/{o_retry.state} vs "
          f"{retry.fact.n_iters}/{retry.fact.outcome}")

    # ---- below the attempt floor ----------------------------------------
    k_eff = h3.k_eff_bits(row)
    check("K k_eff matches v1", k_eff == v1_tiles.k_eff_bits(spec))
    keep = np.zeros(4096, bool)
    site_flat = np.asarray(geom.shorten_flat, np.int64)
    non_site = np.setdiff1d(np.arange(4096), site_flat)
    keep[non_site[:k_eff - 1]] = True
    starved = evidence_from_dense("sha-a", 0, ty, tx, values, keep)
    starved_result = h3.attempt_tile(row, geom, (starved,), "main",
                                     h3.STAGE_SCAN)
    check("K below floor refuses without decoding",
          starved_result.fact.outcome == h3.OUTCOME_BELOW_FLOOR
          and starved_result.fact.n_iters == 0
          and starved_result.fact.syndrome_ok is None
          and starved_result.fact.crc_ok is None)
    check("K below floor never arms retry150",
          not h3.arms_retry(starved_result.fact, certified=False))
    o_starved, _ = attempt_k_tile(
        (values[:, 0] * keep).reshape(64, 64), spec, (0, ty, tx),
        AttemptStage.SCAN, source_sha256="a" * 64, lane_id="lane",
        component_block_ids=("b" * 64,))
    check("K oracle parity: below-floor state + count",
          o_starved.state is AttemptState.BELOW_ATTEMPT_FLOOR
          and o_starved.n_informative == starved_result.fact.n_informative)

    # ---- union over two captures ----------------------------------------
    half_a = np.zeros(4096, bool)
    half_b = np.zeros(4096, bool)
    half_a[non_site[0::2]] = True
    half_b[non_site[1::2]] = True
    weak = values * 0.5
    block_a = evidence_from_dense("sha-b", 0, ty, tx, weak, half_a)
    block_b = evidence_from_dense("sha-a", 0, ty, tx, weak, half_b)
    scan_a = h3.attempt_tile(row, geom, (block_a,), "main", h3.STAGE_SCAN)
    union = h3.attempt_tile(row, geom, (block_a, block_b), "main",
                            h3.STAGE_UNION)
    check("K half evidence alone is below floor",
          scan_a.fact.outcome == h3.OUTCOME_BELOW_FLOOR, scan_a.fact.outcome)
    check("K union certifies", union.fact.outcome == h3.OUTCOME_CERTIFIED
          and np.array_equal(union.certificate.user_bits, user))
    check("K union source tag", union.certificate.source == "tiles/union")
    check("K union arms only with two distinct captures",
          h3.arms_union((block_a, block_b)) and not h3.arms_union((block_a,)))
    check("scan arms on one unresolved capture only",
          h3.arms_scan((block_a,), certified=False)
          and not h3.arms_scan((block_a,), certified=True)
          and not h3.arms_scan((block_a, block_b), certified=False))
    swapped = h3.attempt_tile(row, geom, (block_b, block_a), "main",
                              h3.STAGE_UNION)
    check("K union sum is capture-sha ordered (argument order irrelevant)",
          np.array_equal(swapped.certificate.user_bits,
                         union.certificate.user_bits))

    # ---- conflict law ----------------------------------------------------
    certs: dict[tuple[int, int, int, str], Certificate] = {}
    check("merge_certificate admits", h3.merge_certificate(
        certs, union.certificate))
    check("merge_certificate duplicate is a no-op",
          not h3.merge_certificate(certs, result.certificate)
          and certs[(0, ty, tx, "main")].source == "tiles/union")
    forged_bits = union.certificate.user_bits.copy()
    forged_bits[7] ^= 1
    forged = Certificate(0, ty, tx, "main", forged_bits, "tiles/scan")
    raises("conflicting mint raises IntegrityError", IntegrityError,
           lambda: h3.merge_certificate(certs, forged))

    # ---- known-site agreement, pass and fail -----------------------------
    check("known-site agreement passes on a true re-encode",
          h3.printed_cells_for(row, geom, 0, 1, 1, truth[(1, 1)]).shape
          == (64, 64))
    forked = type(geom)(
        word_cells_yx=(geom.word_cells_yx + np.asarray([[1, 1]])) % 64,
        extra_cells_yx=geom.extra_cells_yx,
        shorten_flat=geom.shorten_flat,
        payload_flat=geom.payload_flat,
        slot_a=geom.slot_a,
        slot_b=geom.slot_b,
        scramble_planes=geom.scramble_planes)
    raises("known-site agreement fails on a forked site draw",
           IntegrityError,
           lambda: h3.printed_cells_for(row, forked, 0, 1, 1, truth[(1, 1)]))

    # ---- non-finite evidence is refused ----------------------------------
    poisoned = values.copy()
    poisoned[11] = np.inf
    poisoned_block = evidence_from_dense("sha-a", 0, ty, tx, poisoned,
                                         observed)
    raises("non-finite LLR refused (C-7)", IntegrityError,
           lambda: h3.attempt_tile(row, geom, (poisoned_block,), "main",
                                   h3.STAGE_SCAN))

    # ---- job wrapper ------------------------------------------------------
    job = h3.attempt_job(row, geom, (block,), "main", h3.STAGE_SCAN)
    check("attempt_job returns fact+certificate and one event",
          len(job.facts) == 2 and len(job.events) == 1
          and job.events[0].result == h3.OUTCOME_CERTIFIED
          and job.cpu_s >= 0.0)
    return row, geom, truth


# ========================================================= colour helpers ===

def color_truth(spec, counter: int, k_total: int,
                symbols: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    word = v1_metadata.encode_metadata(0, k_total)
    bits = _metadata_bits_for_tile(spec, word, counter)
    return {stream.stream_id: np.concatenate(
        (np.asarray([bits[index]], np.uint8), symbols[stream.stream_id]))
        for index, stream in enumerate(spec.stream_profiles)}


def color_view(spec, page: int, ty: int, tx: int, values: np.ndarray,
               observed: np.ndarray, kind: str):
    cells = np.stack(np.divmod(np.flatnonzero(observed), 64), axis=1)
    cells[:, 0] += ty * 64
    cells[:, 1] += tx * 64
    rows = OwnedPageRows(page, cells.astype(np.int64),
                         np.asarray(values[np.flatnonzero(observed)],
                                    np.float32),
                         np.zeros(int(observed.sum()), np.int64))
    blocks = blocks_from_owner_pages(
        "c" * 64, "lane", (rows,),
        (EvidenceOrigin("placement", 0, 0.25),), kind=kind)
    return tile_attempt_view(blocks)


# ========================================================== CMY8 ============

def verify_cmy8() -> None:
    print("\n[CMY8] c2-cmy8-r0550@3x3 end-to-end + oracle parity")
    ref = "c2-cmy8-r0550@3x3"
    row = resolve_format_ref(ref, n_pages=1)
    geom = build_site_geometry(row)
    spec = v1_resolve(ref)
    check("CMY8 identity: seed matches v1", row.seed == spec.seed)
    check("CMY8 payload cells", row.payload_cells == spec.payload_cells)

    ty, tx = 1, 2
    counter = row.tile_counter(0, ty, tx)
    k_total = 96
    symbols = {stream.stream_id:
               RNG.integers(0, 2, stream.symbol_bits, dtype=np.uint8)
               for stream in spec.stream_profiles}
    truth = color_truth(spec, counter, k_total, symbols)
    states = compose_color_tile(spec, counter, symbols, k_total)
    planes = states_to_planes(states.reshape(-1)).astype(np.float64)
    values = (2.0 * planes - 1.0) * MAG
    observed = np.ones(4096, bool)
    block = evidence_from_dense("sha-a", 0, ty, tx, values, observed)

    for stream_id in ("C", "M", "Y"):
        result = h3.attempt_tile(row, geom, (block,), stream_id,
                                 h3.STAGE_SCAN)
        check(f"CMY8 {stream_id} certifies == truth",
              result.fact.outcome == h3.OUTCOME_CERTIFIED
              and np.array_equal(result.certificate.user_bits,
                                 truth[stream_id]),
              result.fact.outcome)
        view = color_view(spec, 0, ty, tx, values, observed, "cmy8")
        oracle = attempt_color_tile(view, spec, stream_id, AttemptStage.SCAN,
                                    source_sha256="c" * 64, lane_id="lane")
        o_user = np.unpackbits(
            np.frombuffer(oracle.certificate.packed_user_bits, np.uint8),
            bitorder="little")[:spec.stream_profile(stream_id).user_bits]
        check(f"CMY8 {stream_id} oracle parity (bits/iters/informative)",
              np.array_equal(o_user, result.certificate.user_bits)
              and oracle.record.n_iters == result.fact.n_iters
              and oracle.record.n_informative == result.fact.n_informative,
              f"{oracle.record.n_iters} vs {result.fact.n_iters}")

    # dead Y plane: graceful per-plane degradation
    dead = values.copy()
    dead[:, 2] = 0.0
    dead_block = evidence_from_dense("sha-a", 0, ty, tx, dead, observed)
    outcomes = {stream_id: h3.attempt_tile(row, geom, (dead_block,),
                                           stream_id, h3.STAGE_SCAN)
                for stream_id in ("C", "M", "Y")}
    check("CMY8 dead Y: C and M still certify",
          all(outcomes[s].fact.outcome == h3.OUTCOME_CERTIFIED
              for s in ("C", "M")))
    check("CMY8 dead Y: Y refuses below floor",
          outcomes["Y"].fact.outcome == h3.OUTCOME_BELOW_FLOOR
          and outcomes["Y"].fact.n_iters == 0,
          outcomes["Y"].fact.outcome)
    check("CMY8 dead Y never arms retry150",
          not h3.arms_retry(outcomes["Y"].fact, False))

    # corrupted stream fails and arms retry
    broken = values.copy()
    flip = RNG.choice(4096, 900, replace=False)
    broken[flip, 0] = -broken[flip, 0]
    broken_block = evidence_from_dense("sha-a", 0, ty, tx, broken, observed)
    broken_result = h3.attempt_tile(row, geom, (broken_block,), "C",
                                    h3.STAGE_SCAN)
    check("CMY8 corrupted C fails syndrome/CRC",
          broken_result.fact.outcome == h3.OUTCOME_FAILED
          and not (broken_result.fact.syndrome_ok
                   and broken_result.fact.crc_ok),
          broken_result.fact.outcome)
    check("CMY8 corrupted C arms retry150",
          h3.arms_retry(broken_result.fact, False))
    view = color_view(spec, 0, ty, tx, broken, observed, "cmy8")
    oracle = attempt_color_tile(view, spec, "C", AttemptStage.SCAN,
                                source_sha256="c" * 64, lane_id="lane")
    check("CMY8 oracle parity: corrupted iters/state",
          oracle.record.n_iters == broken_result.fact.n_iters
          and oracle.record.state is AttemptState.ATTEMPTED_FAILED,
          f"{oracle.record.n_iters} vs {broken_result.fact.n_iters}")

    # unresolved streams / done grid
    certs: dict[tuple[int, int, int, str], Certificate] = {}
    for stream_id in ("C", "M"):
        h3.merge_certificate(certs, h3.attempt_tile(
            row, geom, (block,), stream_id, h3.STAGE_SCAN).certificate)
    check("unresolved_streams reports only Y",
          h3.unresolved_streams(row, certs, 0, ty, tx) == ("Y",))
    check("tile not done with Y open",
          not h3.tile_done(row, certs, 0, ty, tx)
          and not h3.done_tile_grid(row, certs, 0)[ty, tx])
    h3.merge_certificate(certs, h3.attempt_tile(
        row, geom, (block,), "Y", h3.STAGE_SCAN).certificate)
    grid = h3.done_tile_grid(row, certs, 0)
    check("done grid marks the completed tile only",
          grid[ty, tx] and int(grid.sum()) == 1
          and h3.unresolved_streams(row, certs, 0, ty, tx) == ())
    close_rows = h3.close_input(certs)
    check("close_input is key-sorted and complete",
          len(close_rows) == 3
          and [c.stream_id for c in close_rows] == ["C", "M", "Y"]
          and all(np.array_equal(c.user_bits, truth[c.stream_id])
                  for c in close_rows))


# ========================================================== CMY7 ============

def verify_cmy7() -> None:
    print("\n[CMY7] L:c3-cmy7-p120-v0@2240x1536 end-to-end + oracle parity")
    ref = "L:c3-cmy7-p120-v0@2240x1536"
    row = resolve_format_ref(ref, n_pages=1)
    geom = build_site_geometry(row)
    spec = v1_resolve(ref)
    check("CMY7 identity: seed matches v1", row.seed == spec.seed)
    check("CMY7 identity: user bits match v1",
          row.streams[0].user_bits == spec.tile_user_bits)
    check("CMY7 payload_flat matches v1 colour payload cells",
          np.array_equal(np.asarray(geom.payload_flat, np.int64),
                         __import__("holo.format.pilots", fromlist=["x"])
                         .color_payload_cell_indices(spec.family_seed)))

    ty, tx = 2, 5
    counter = row.tile_counter(0, ty, tx)
    k_total = 421
    symbols = {"main": RNG.integers(0, 2, spec.stream_profiles[0].symbol_bits,
                                    dtype=np.uint8)}
    truth = color_truth(spec, counter, k_total, symbols)["main"]
    states = compose_color_tile(spec, counter, symbols, k_total).reshape(-1)

    values = np.full((4096, 6), -MAG, np.float64)
    hot = states.astype(np.int64) - 1
    live = np.flatnonzero(hot >= 0)
    values[live, hot[live]] = MAG
    observed = np.ones(4096, bool)
    block = evidence_from_dense("sha-a", 0, ty, tx, values, observed)

    result = h3.attempt_tile(row, geom, (block,), "main", h3.STAGE_SCAN)
    check("CMY7 clean scan certifies == truth",
          result.fact.outcome == h3.OUTCOME_CERTIFIED
          and np.array_equal(result.certificate.user_bits, truth),
          result.fact.outcome)
    check("CMY7 n_informative = observed payload cells",
          result.fact.n_informative == row.payload_cells,
          str(result.fact.n_informative))

    view = color_view(spec, 0, ty, tx, values, observed, "cmy7")
    oracle = attempt_color_tile(view, spec, "main", AttemptStage.SCAN,
                                source_sha256="c" * 64, lane_id="lane")
    o_user = np.unpackbits(
        np.frombuffer(oracle.certificate.packed_user_bits, np.uint8),
        bitorder="little")[:spec.tile_user_bits]
    check("CMY7 oracle parity (bits/iters/informative)",
          np.array_equal(o_user, result.certificate.user_bits)
          and oracle.record.n_iters == result.fact.n_iters
          and oracle.record.n_informative == result.fact.n_informative,
          f"{oracle.record.n_iters} vs {result.fact.n_iters}")

    # structural pack gate: erase one cell of most packs
    payload_flat = np.asarray(geom.payload_flat, np.int64)
    order = color_cell_permutation(row.seed, counter, row.payload_cells)
    # sequential[order] = physical, so physical index of sequential slot s:
    physical_of_sequential = np.empty(row.payload_cells, np.int64)
    physical_of_sequential[order] = np.arange(row.payload_cells,
                                              dtype=np.int64)
    starved_observed = observed.copy()
    drop_sequential = np.arange(0, 900 * 4, 4, dtype=np.int64)
    starved_observed[payload_flat[physical_of_sequential[drop_sequential]]] \
        = False
    starved = evidence_from_dense("sha-a", 0, ty, tx, values,
                                  starved_observed)
    starved_result = h3.attempt_tile(row, geom, (starved,), "main",
                                     h3.STAGE_SCAN)
    check("CMY7 structural pack gate refuses below floor",
          starved_result.fact.outcome == h3.OUTCOME_BELOW_FLOOR
          and starved_result.fact.n_iters == 0,
          starved_result.fact.outcome)
    check("CMY7 below floor never arms retry150",
          not h3.arms_retry(starved_result.fact, False))
    starved_view = color_view(spec, 0, ty, tx, values, starved_observed,
                              "cmy7")
    starved_oracle = attempt_color_tile(
        starved_view, spec, "main", AttemptStage.SCAN,
        source_sha256="c" * 64, lane_id="lane")
    check("CMY7 oracle parity: below-floor state + informative",
          starved_oracle.record.state is AttemptState.BELOW_ATTEMPT_FLOOR
          and starved_oracle.record.n_informative
          == starved_result.fact.n_informative,
          f"{starved_oracle.record.state} "
          f"{starved_oracle.record.n_informative} vs "
          f"{starved_result.fact.n_informative}")

    # corrupted -> failed -> arms retry150, parity on iters
    broken = values.copy()
    flip = RNG.choice(4096, 700, replace=False)
    broken[flip] = -broken[flip]
    broken_block = evidence_from_dense("sha-a", 0, ty, tx, broken, observed)
    broken_result = h3.attempt_tile(row, geom, (broken_block,), "main",
                                    h3.STAGE_SCAN)
    check("CMY7 corrupted scan fails",
          broken_result.fact.outcome == h3.OUTCOME_FAILED,
          broken_result.fact.outcome)
    check("CMY7 corrupted arms retry150",
          h3.arms_retry(broken_result.fact, False))
    broken_view = color_view(spec, 0, ty, tx, broken, observed, "cmy7")
    broken_oracle = attempt_color_tile(
        broken_view, spec, "main", AttemptStage.SCAN,
        source_sha256="c" * 64, lane_id="lane")
    check("CMY7 oracle parity: corrupted iters (demap loop identical)",
          broken_oracle.record.n_iters == broken_result.fact.n_iters
          and broken_oracle.record.state is AttemptState.ATTEMPTED_FAILED,
          f"{broken_oracle.record.n_iters} vs {broken_result.fact.n_iters}")


# ==================================================== freeze + tilemap ======

def dense_freeze_reference(pieces, page_shape, arity):
    """holo2 payload.py:781-833 walk, densely, as the reference."""
    order = sorted(range(len(pieces)), key=lambda i: (
        np.inf if pieces[i].heldout_logloss is None
        else float(pieces[i].heldout_logloss),
        pieces[i].extent_cells, pieces[i].plane))
    owner = np.zeros(page_shape + (arity,), np.float32)
    owned = np.zeros(page_shape, bool)
    for index in order:
        piece = pieces[index]
        cells = np.asarray(piece.cells_yx, np.int64)
        observed = np.zeros(page_shape, bool)
        observed[cells[:, 0], cells[:, 1]] = True
        take = observed & ~owned
        values = np.zeros(page_shape + (arity,), np.float32)
        values[cells[:, 0], cells[:, 1]] = np.asarray(
            piece.values, np.float32).reshape(cells.shape[0], arity)
        owner[take] = values[take]
        owned |= take
    return owner, owned


def verify_freeze(row, geom, truth) -> None:
    print("\n[freeze] ownership walk + sparse TileEvidence")
    del geom, truth
    page_shape = row.cells_yx
    rng = np.random.default_rng(7)

    def make_piece(y0, x0, height, width, loss, fill):
        ys, xs = np.meshgrid(np.arange(y0, y0 + height),
                             np.arange(x0, x0 + width), indexing="ij")
        cells = np.stack((ys.ravel(), xs.ravel()), axis=1)
        values = np.full((cells.shape[0], 1), fill, np.float32)
        return h3.FreezePiece(0, cells, values, loss,
                              (y0, x0, y0 + height, x0 + width), 0, 3)

    pieces = [
        make_piece(0, 0, 80, 90, 0.40, 1.0),      # worse, first by geometry
        make_piece(40, 30, 90, 90, 0.10, 2.0),    # best
        make_piece(60, 60, 70, 70, None, 3.0),    # no loss -> ranks last
        make_piece(20, 20, 40, 40, 0.10, 4.0),    # ties on loss, smaller ext
    ]
    rows = h3.freeze_tile_evidence(row, "sha-a", 0, pieces, epoch=2)
    ref_values, ref_owned = dense_freeze_reference(pieces, page_shape, 1)

    got = np.zeros(page_shape + (1,), np.float32)
    seen = np.zeros(page_shape, bool)
    sorted_ok = True
    for block in rows:
        flat = np.asarray(block.observed_flat, np.int64)
        sorted_ok = sorted_ok and bool(np.all(np.diff(flat) > 0))
        ys = block.ty * 64 + flat // 64
        xs = block.tx * 64 + flat % 64
        got[ys, xs] = block.values
        seen[ys, xs] = True
    check("freeze: owned mask == dense reference",
          np.array_equal(seen, ref_owned))
    check("freeze: owner values == dense reference (best loss wins)",
          np.array_equal(got, ref_values))
    check("freeze: observed_flat sorted within each tile", sorted_ok)
    check("freeze: values are float32, observed_flat uint16",
          all(block.values.dtype == np.float32
              and block.observed_flat.dtype == np.uint16 for block in rows))
    check("freeze: epoch and arm carried",
          all(block.epoch == 2 and block.arm == h3.CORE_ARM
              for block in rows))
    check("freeze: one row per (capture, tile)",
          len({(block.ty, block.tx) for block in rows}) == len(rows))

    # the measured law: a contested cell goes to the best-calibrated window
    contested = (40, 30)
    block = next(b for b in rows
                 if b.ty == contested[0] // 64 and b.tx == contested[1] // 64)
    flat = (contested[0] % 64) * 64 + (contested[1] % 64)
    position = int(np.flatnonzero(
        np.asarray(block.observed_flat, np.int64) == flat)[0])
    # pieces 1 and 3 tie at loss 0.10 and both cover (40, 30); the extent
    # tuple breaks the tie ((20,20,60,60) < (40,30,130,120)), and the
    # worse-calibrated piece 0 (loss 0.40, value 1.0) never wins it.
    check("freeze: best-calibrated window wins the contested cell "
          "(extent breaks the loss tie)",
          float(block.values[position, 0]) == 4.0,
          str(block.values[position, 0]))

    # a zero-valued owned cell stays 0.0 and stays owned
    zero_pieces = [
        h3.FreezePiece(0, np.asarray([[5, 5]]), np.zeros((1, 1), np.float32),
                       0.1, (5, 5, 6, 6), 0, 3),
        h3.FreezePiece(0, np.asarray([[5, 5]]), np.full((1, 1), 9.0,
                                                        np.float32),
                       0.9, (5, 5, 6, 6), 0, 3),
    ]
    zero_rows = h3.freeze_tile_evidence(row, "sha-a", 0, zero_pieces)
    check("freeze: an owned 0.0 erasure is never re-assigned",
          len(zero_rows) == 1 and float(zero_rows[0].values[0, 0]) == 0.0)

    # latest_components / attempt_key
    a0 = TileEvidence("sha-a", 0, 0, 1, 1, np.zeros((1, 1), np.float32),
                      np.zeros(1, np.uint16), h3.CORE_ARM, 0)
    a1 = TileEvidence("sha-a", 0, 0, 1, 1, np.zeros((1, 1), np.float32),
                      np.zeros(1, np.uint16), h3.CORE_ARM, 3)
    b0 = TileEvidence("sha-b", 0, 0, 1, 1, np.zeros((1, 1), np.float32),
                      np.zeros(1, np.uint16), h3.CORE_ARM, 1)
    arm = TileEvidence("sha-c", 0, 0, 1, 1, np.zeros((1, 1), np.float32),
                       np.zeros(1, np.uint16), "u-lane", 1)
    latest = h3.latest_components((b0, a0, a1, arm))
    check("latest_components: newest epoch per capture, sha-sorted, one arm",
          tuple(r.capture_id for r in latest) == ("sha-a", "sha-b")
          and latest[0].epoch == 3)
    check("attempt_key: epoch bump changes the key, order does not",
          h3.attempt_key(0, 1, 1, "main", h3.STAGE_UNION, (a0, b0))
          == h3.attempt_key(0, 1, 1, "main", h3.STAGE_UNION, (b0, a0))
          and h3.attempt_key(0, 1, 1, "main", h3.STAGE_UNION, (a1, b0))
          != h3.attempt_key(0, 1, 1, "main", h3.STAGE_UNION, (a0, b0)))
    check("attempt_key: stage carries the decoder budget",
          h3.attempt_key(0, 1, 1, "main", h3.STAGE_RETRY150, (a0,))[5] == 150)
    del rng


def verify_projection(row) -> None:
    print("\n[tilemap] done grid + done projection")
    certs: dict[tuple[int, int, int, str], Certificate] = {}
    bits = np.zeros(row.streams[0].user_bits, np.uint8)
    for ty, tx in ((0, 0), (0, 1), (1, 0)):
        certs[(0, ty, tx, "main")] = Certificate(0, ty, tx, "main", bits,
                                                 "tiles/scan")
    grid = h3.done_tile_grid(row, certs, 0)
    check("done grid marks exactly the certified tiles",
          int(grid.sum()) == 3 and grid[0, 0] and grid[0, 1] and grid[1, 0])
    check("done grid of another page is empty",
          not h3.done_tile_grid(row, certs, 1).any())

    # identity pose at 1 px/cell: page cell (y, x) sits at native (y+0.5,x+0.5)
    shape_cells = (96, 96)
    support = np.zeros(shape_cells, bool)
    support[:80, :80] = True
    affine = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    extent = (0, 0, 96, 96)
    done = h3.project_done(((0, extent, affine),), {0: grid}, (0, 0), 1.0,
                           shape_cells, support)
    expected = np.zeros(shape_cells, bool)
    ys, xs = np.meshgrid(np.arange(96), np.arange(96), indexing="ij")
    expected = grid[np.minimum(ys // 64, grid.shape[0] - 1),
                    np.minimum(xs // 64, grid.shape[1] - 1)]
    expected = np.where((ys // 64 < grid.shape[0]) & (xs // 64
                                                      < grid.shape[1]),
                        expected, False) & support
    check("project_done == direct centre projection", np.array_equal(
        done, expected))
    check("project_done ANDs with support",
          not done[85, 10] and done[10, 10])
    check("done_covers: fully-done supported extent",
          h3.done_covers(done, (0, 0, 64, 64), support))
    check("done_covers: partially-done extent is not covered",
          not h3.done_covers(done, (0, 0, 80, 80), support))
    check("done_covers: an unsupported extent is dead, not done",
          not h3.done_covers(done, (80, 80, 96, 96), support))
    check("project_done skips pages with no certified tile",
          not h3.project_done(((1, extent, affine),), {0: grid}, (0, 0), 1.0,
                              shape_cells, support).any())


def main() -> int:
    row, geom, truth = verify_k()
    verify_cmy8()
    verify_cmy7()
    verify_freeze(row, geom, truth)
    verify_projection(row)
    print(f"\n{CHECKS[0] - len(FAILURES)}/{CHECKS[0]} checks passed")
    if FAILURES:
        print("FAILURES:")
        for line in FAILURES:
            print(f"  - {line}")
        return 1
    print("verify_tiles: GREEN")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
