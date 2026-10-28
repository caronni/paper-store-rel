#!/usr/bin/env python
"""Qualification-only E023b native/decimated multi-view measurement.

The two footings are deterministic rasterizations of the same six physical
captures.  This runner therefore never adds a native LLR to a decimated LLR
as if the views were independent observations.  It measures:

* parallel context+BP branches followed by certificate-level union; and
* correlated one-vote candidates that emit at most one composite LLR for
  each (physical capture, page, payload cell).

Both legacy input pickles are complete-file SHA-256 pinned before unpickling
by ``qualify_e023b_arms``.  All detector, decoder, certificate, and paired
hard-observation outputs are compacted before the ground-truth field is
opened.  Ground truth is used only for the final wrong-certificate audit.

This is deliberately not a production state migration or receiver entry
point.  It uses E023b's numerical scheduling primitives on qualification-only
compact scan records whose correlated-view provenance is explicit here.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

import qualify_e023b_arms as arms  # noqa: E402
from paperholo import payloaddec, receiver  # noqa: E402


REPORT_PATH = HERE / "MULTIVIEW-QUALIFICATION.json"

PROFILE_METHODS = {
    payloaddec.DETECTOR_PAVA_V1: (
        "prefer_decimated",
        "prefer_native",
        "lower_loss",
        "mean",
        "loss_weighted",
        "max_abs",
    ),
    payloaddec.DETECTOR_CTX_PAVA_V1: (
        "prefer_decimated",
        "lower_loss",
        "mean",
    ),
}

# Frozen numerical and identity expectations from the blind design described
# in this module.  Certificate counts alone are not reproducibility evidence:
# every set and bit digest, branch cost, and view-exclusive tile is pinned.
EXPECTED = {
    "input_geometry": {
        "decimated": {
            "scans": 6, "accepted_placements": 462, "dpi": 1600.0},
        "native": {
            "scans": 6, "accepted_placements": 481, "dpi": 4800.0},
    },
    "branches": {
        "decimated": {
            "before_bp": {
                "count": 749,
                "set_sha256": (
                    "0db6bdb570c3286d1990855dafcd9c85f2f2467d10049338fc126c7869dabdc9"),
                "bits_sha256": (
                    "daa71427e90de224eea1af7063f3d29679f6bb19c370a15702018139a2b73d65"),
            },
            "after_bp": {
                "count": 757,
                "set_sha256": (
                    "6f4a786aa48c6a6342a5c9550a7f3f4d5a9c9b5bdbbbbb3633f22d5bc5bab103"),
                "bits_sha256": (
                    "d04d51fef4cf2dca8424b294cbc0d464ec640d495400ac702a2068b5561e12cd"),
            },
            "cost": {
                "crc_calls": 1101,
                "bp_iterations": 57544,
                "ledger_records": 1614,
                "below_floor_records": 478,
            },
        },
        "native": {
            "before_bp": {
                "count": 746,
                "set_sha256": (
                    "c05b95a072def32405cc5b5234cb5fb9c9c8745a077047622d3f8f3709ab8de8"),
                "bits_sha256": (
                    "aa24d0fe2629b8aea21ac1626e6e936a4a19eb0aa3473224a170aefb1ae221f0"),
            },
            "after_bp": {
                "count": 752,
                "set_sha256": (
                    "4a6435c91064865ca9bb9444d817ac801b77f83b7545272b5aa2d3402f875ef6"),
                "bits_sha256": (
                    "c2154b32c5ba07563d42c22780c6740dd3da9ce7be8b2a3dbd40cf985516fa5d"),
            },
            "cost": {
                "crc_calls": 1125,
                "bp_iterations": 62246,
                "ledger_records": 1639,
                "below_floor_records": 479,
            },
        },
        "union": {
            "certificates": {
                "count": 769,
                "set_sha256": (
                    "a910cce60403edd5f01a31a30aa4cf4226a78e29ecde246c59086524b65125b5"),
                "bits_sha256": (
                    "2c462b6e9fda47c77e25b903bb1fc760a750a456c561932fa33bb285aa76e444"),
            },
            "common": 740,
            "decimated_only_tiles": (
                (0, 1, 14), (0, 1, 18),
                (0, 7, 17), (0, 7, 19), (0, 7, 20),
                (0, 8, 3), (0, 8, 5), (0, 10, 8), (0, 12, 0),
                (0, 21, 15), (0, 25, 11),
                (0, 27, 13), (0, 27, 14), (0, 27, 15),
                (0, 27, 20), (0, 27, 22), (0, 28, 11),
            ),
            "native_only_tiles": (
                (0, 9, 19),
                (0, 13, 14), (0, 13, 15), (0, 13, 16),
                (0, 13, 17), (0, 13, 18),
                (0, 18, 12), (0, 18, 16), (0, 18, 17),
                (0, 18, 18), (0, 21, 18), (0, 21, 21),
            ),
            "cost": {
                "crc_calls": 2226,
                "bp_iterations": 119790,
                "ledger_records": 3253,
                "below_floor_records": 957,
            },
        },
    },
    "observations": {
        payloaddec.DETECTOR_PAVA_V1: {
            "cells": 6_200_308,
            "paired": 6_049_897,
            "hard_disagree": 138_192,
            "llr_pearson_rounded_4": 0.9697,
        },
        payloaddec.DETECTOR_CTX_PAVA_V1: {
            "cells": 6_200_308,
            "paired": 6_049_897,
            "hard_disagree": 102_453,
        },
    },
    "fusion": {
        payloaddec.DETECTOR_PAVA_V1: {
            "prefer_decimated": {
                "before_bp": (749,
                    "bffb289f59d8f14e0e3f2945f807adf22c75436ef4ac654a2591c312f7b7ea6e",
                    "57a448a6df5e99f7dd8f73f602dfbef1d2c59401aa9adb36fcb4a61ace530fb6"),
                "after_bp": (753,
                    "68f3f5a7dc8e8c456270f6d78b934b01a70ff624bfc7815f7824859f531b124f",
                    "e9f5a9d5a331081b52e0192839a49bcc7d99f5092935708c73beb09443a1e06d"),
            },
            "prefer_native": {
                "before_bp": (743,
                    "3ac2498c512d03583523ee21a1e7013b79bd111f883d8bd3bbccf7de7edb8a49",
                    "87ee9c217aa2fca1ced51b950bca8c5bc134c9dadf7c7b63a5f8d21b1a24107e"),
                "after_bp": (747,
                    "02b3f2743ac2dab87585fca2a26b9ecc89324ead850307255f95083832557599",
                    "0ff57ccf3ca2c645097b0df1b39e766b29bbbe0d4f2fcf02b43e5ac28426c9fc"),
            },
            "lower_loss": {
                "before_bp": (749,
                    "d1ea17232b9ca0cf7cef378ff8033301b9726289c7b1848fe462c62b26a4ed65",
                    "d32ae7fc21da478f510ee605d076eab490c330f17428aa87ed181c65a679beff"),
                "after_bp": (754,
                    "a6eaf9ec135154266fa4b7bceeca2e4591bde8bb0a790e87268625f41747c843",
                    "32282b95263797ff1e6b5ed69c3ac42bd5cf1a0e9f155643bc5f6872f998a83d"),
            },
            "mean": {
                "before_bp": (753,
                    "adbb8307bd0cf956e97ae60124ce422d2d906451630bb7bd9b17e48b86078ac4",
                    "6c41dc6931d149eb2e547ec555fb2cba29820244b13b8c5dfab8d62e4cb492d8"),
                "after_bp": (757,
                    "891e116ed7826ab7e722e1cf419a73d3dc32a52a37c4924a437abe2f9840b24d",
                    "2f0f13e8ed276ea5f2698efe2dcb424c66fd777589516171fa9f58cb43bf584c"),
            },
            "loss_weighted": {
                "before_bp": (753,
                    "adbb8307bd0cf956e97ae60124ce422d2d906451630bb7bd9b17e48b86078ac4",
                    "6c41dc6931d149eb2e547ec555fb2cba29820244b13b8c5dfab8d62e4cb492d8"),
                "after_bp": (757,
                    "891e116ed7826ab7e722e1cf419a73d3dc32a52a37c4924a437abe2f9840b24d",
                    "2f0f13e8ed276ea5f2698efe2dcb424c66fd777589516171fa9f58cb43bf584c"),
            },
            "max_abs": {
                "before_bp": (750,
                    "967e5a45601a3c7141f9c9ab1cc4d9dccd859de7bc7a3b3492711ec5f60715ec",
                    "683041e45b3db3f45aff7efb6aa5d852e169e2e93a62823c8fe998a3ac0d6fdc"),
                "after_bp": (754,
                    "dc3bc15d2242691188d5985764958ab6538acff3610609d04107335761658c01",
                    "f63d432a80e5e7a8abc56e51b8ee523d127c27c789a9b0085eaf4b257e8f71a6"),
            },
        },
        payloaddec.DETECTOR_CTX_PAVA_V1: {
            "prefer_decimated": {
                "before_bp": (755,
                    "2eb44ac67b5f8a1cabe1d175a89729b2e969e3dd2c77b4c05325b95063e172bd",
                    "1f2b80fb340d4509414678e6b0bdaf2f5f7148634ab602b9425efa0b88b40833"),
                "after_bp": (761,
                    "37809c389f824483b54a2f5fc8b102d24903130f596c6b0ffb218ab0ef358b85",
                    "cc1b86e353de314143e5d5fb5bf064a38c8c1a4de1e46a253471fceca2e6184c"),
            },
            "lower_loss": {
                "before_bp": (757,
                    "d3dd733227957c12a8b824a7f640eab9ceaded010cd5ffdc464516ba0a0dedad",
                    "74eabe5ab82ba309c5533216c297ea04e5819abf29970a61de94c2714e34a7ef"),
                "after_bp": (761,
                    "43aa109406794a39626aed505fbc040daa57d0e004c52037e9d1542003774ae4",
                    "8df352fa2cae641c74db9557a81cbc173a1b7abbf4dd52bf819b3cae8d10136e"),
            },
            "mean": {
                "before_bp": (759,
                    "724f1e7b89ca0b796963da44ab643859ac37838b1b801e61577aba60f4303ae4",
                    "af8d0b34b164a0ff191bac57af1f14b191836bf334fbd678ff5b760cbae6d1ac"),
                "after_bp": (763,
                    "abdd08e3930c845154fd48f4e85bfd1fc6090b901609d37cb4aaad2b0f1920b1",
                    "3a70a2cc0b8bcdab78a114610c2dc4bef5e16b2429cb6fec995a16c754c3c89f"),
            },
        },
    },
    "ground_truth_integer_counts": {
        payloaddec.DETECTOR_PAVA_V1: {
            "paired": 6_049_897,
            "decimated_wrong": 108_910,
            "native_wrong": 146_014,
            "both_wrong": 58_366,
            "decimated_only_wrong": 50_544,
            "native_only_wrong": 87_648,
            "both_correct": 5_853_339,
        },
        payloaddec.DETECTOR_CTX_PAVA_V1: {
            "paired": 6_049_897,
            "decimated_wrong": 74_889,
            "native_wrong": 99_970,
            "both_wrong": 36_203,
            "decimated_only_wrong": 38_686,
            "native_only_wrong": 63_767,
            "both_correct": 5_911_241,
        },
    },
}


@dataclass(frozen=True)
class CompactScan:
    """Only the frozen one-owner fields needed by this measurement."""

    scan_id: str
    capture_id: str
    source_sha256: str
    pages: dict[int, dict[str, np.ndarray]]


def _compact_record(record: receiver.ScanRecord) -> CompactScan:
    loss_by_owner = {
        int(row["placement"]): float(row["heldout_logloss"])
        for row in record.emission.window_rows
        if row["heldout_logloss"] is not None
    }
    pages = {}
    for page, vector in sorted(record.emission.pages.items()):
        owner = np.asarray(vector["owner"], np.int32)
        try:
            loss = np.asarray(
                [loss_by_owner[int(value)] for value in owner],
                np.float32)
        except KeyError as exc:
            raise ValueError(
                "frozen owner has no admitted held-out score") from exc
        pages[int(page)] = {
            "index": np.asarray(vector["index"], np.int64).copy(),
            "llr": np.asarray(vector["llr"], np.float32).copy(),
            "owner": owner.copy(),
            "loss": loss,
        }
    return CompactScan(
        scan_id=str(record.scan_id),
        capture_id=str(record.capture_id),
        source_sha256=str(record.source_sha256),
        pages=pages,
    )


def _load_footing(
    name: str,
    path: Path,
) -> tuple[object, dict, dict[str, list[CompactScan]], dict]:
    info = arms.FOOTINGS[name]
    legacy, reference = arms._load_frozen_session(
        path, info["sha256"])
    descriptor = arms._descriptor(legacy.envelope.format_id)
    profiles = {
        payloaddec.DETECTOR_PAVA_V1: [],
        payloaddec.DETECTOR_CTX_PAVA_V1: [],
    }
    context_checks = {
        "nonadopted_and_refused_rows_exact": True,
        "fits": 0,
        "adopted": 0,
    }
    accepted_placements = 0
    for index, record in enumerate(legacy.scans):
        accepted_placements += len(record.result.placements)
        print(f"  {name} scan {index + 1}/{len(legacy.scans)}: "
              "compact PAVA + replay context", flush=True)
        profiles[payloaddec.DETECTOR_PAVA_V1].append(
            _compact_record(record))
        profiled, replay, _baseline_exact, nonadopted_exact = (
            arms._profile_record(
                record, descriptor, payloaddec.DETECTOR_CTX_PAVA_V1))
        context_checks["nonadopted_and_refused_rows_exact"] &= bool(
            nonadopted_exact)
        context_checks["fits"] += len(replay.context_fits)
        context_checks["adopted"] += sum(
            bool(fit.adopted) for fit in replay.context_fits)
        profiles[payloaddec.DETECTOR_CTX_PAVA_V1].append(
            _compact_record(profiled))
    metadata = {
        "pages": tuple(legacy.envelope.pages),
        "dpi": float(legacy.envelope.dpi),
        "rate_id": str(legacy.envelope.rate_id),
        "search_config": legacy.envelope.search_config,
    }
    if not context_checks["nonadopted_and_refused_rows_exact"]:
        raise ValueError("context rejected/refused replay differs from PAVA")
    del legacy
    gc.collect()
    return descriptor, metadata, profiles, {
        "state_sha256": reference["sha256"],
        "legacy_implementation_sha256": reference[
            "legacy_implementation_sha256"],
        "input_geometry": {
            "scans": len(profiles[payloaddec.DETECTOR_PAVA_V1]),
            "accepted_placements": accepted_placements,
            "dpi": float(metadata["dpi"]),
        },
        "context_replay": context_checks,
    }


def _paired_positions(a: dict, b: dict) -> tuple[
        np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ai = np.asarray(a["index"], np.int64)
    bi = np.asarray(b["index"], np.int64)
    index = np.union1d(ai, bi)
    apos = np.searchsorted(ai, index)
    bpos = np.searchsorted(bi, index)
    ahas = apos < ai.size
    bhas = bpos < bi.size
    ahas[ahas] = ai[apos[ahas]] == index[ahas]
    bhas[bhas] = bi[bpos[bhas]] == index[bhas]
    return index, apos, bpos, ahas, bhas


def _observation_stats(
    decimated: list[CompactScan],
    native: list[CompactScan],
) -> dict:
    cells = paired = decimated_only = native_only = hard_disagree = 0
    sum_decimated = sum_native = 0.0
    sum_decimated_sq = sum_native_sq = sum_product = 0.0
    decimated_zero = native_zero = 0
    for dec, nat in zip(decimated, native, strict=True):
        if dec.capture_id != nat.capture_id:
            raise ValueError("native/decimated capture order differs")
        for page in sorted(set(dec.pages) | set(nat.pages)):
            if page not in dec.pages:
                size = int(nat.pages[page]["index"].size)
                cells += size
                native_only += size
                continue
            if page not in nat.pages:
                size = int(dec.pages[page]["index"].size)
                cells += size
                decimated_only += size
                continue
            a, b = dec.pages[page], nat.pages[page]
            index, apos, bpos, ahas, bhas = _paired_positions(a, b)
            both = ahas & bhas
            cells += int(index.size)
            paired += int(both.sum())
            decimated_only += int((ahas & ~bhas).sum())
            native_only += int((bhas & ~ahas).sum())
            dec_llr = a["llr"][apos[both]].astype(np.float64)
            nat_llr = b["llr"][bpos[both]].astype(np.float64)
            hard_disagree += int(np.count_nonzero(
                (dec_llr > 0.0) != (nat_llr > 0.0)))
            decimated_zero += int(np.count_nonzero(dec_llr == 0.0))
            native_zero += int(np.count_nonzero(nat_llr == 0.0))
            sum_decimated += float(np.sum(dec_llr, dtype=np.float64))
            sum_native += float(np.sum(nat_llr, dtype=np.float64))
            sum_decimated_sq += float(
                np.sum(dec_llr * dec_llr, dtype=np.float64))
            sum_native_sq += float(
                np.sum(nat_llr * nat_llr, dtype=np.float64))
            sum_product += float(
                np.sum(dec_llr * nat_llr, dtype=np.float64))
    if cells != paired + decimated_only + native_only:
        raise ValueError("paired observation accounting is incomplete")
    covariance = paired * sum_product - sum_decimated * sum_native
    dec_variance = (
        paired * sum_decimated_sq - sum_decimated * sum_decimated)
    nat_variance = paired * sum_native_sq - sum_native * sum_native
    denominator = math.sqrt(dec_variance * nat_variance)
    pearson = covariance / denominator if denominator else None
    return {
        "cells": cells,
        "paired": paired,
        "decimated_only": decimated_only,
        "native_only": native_only,
        "paired_fraction": paired / cells,
        "hard_disagree": hard_disagree,
        "hard_disagree_fraction_of_paired": (
            hard_disagree / paired if paired else None),
        "hard_semantics": "payload bit is one iff emitted LLR > 0",
        "llr_pearson": pearson,
        "llr_moments_float64": {
            "n": paired,
            "sum_decimated": sum_decimated,
            "sum_native": sum_native,
            "sum_decimated_squared": sum_decimated_sq,
            "sum_native_squared": sum_native_sq,
            "sum_product": sum_product,
            "decimated_exact_zero": decimated_zero,
            "native_exact_zero": native_zero,
        },
    }


def _merge_page(a: dict, b: dict, method: str) -> dict[str, np.ndarray]:
    index, apos, bpos, ahas, bhas = _paired_positions(a, b)
    both = ahas & bhas
    only_a = ahas & ~bhas
    only_b = bhas & ~ahas
    llr = np.zeros(index.size, np.float32)
    owner = np.full(index.size, -1, np.int32)
    llr[only_a] = a["llr"][apos[only_a]]
    owner[only_a] = 0
    llr[only_b] = b["llr"][bpos[only_b]]
    owner[only_b] = 1

    ax = apos[both]
    bx = bpos[both]
    al = a["llr"][ax].astype(np.float64)
    bl = b["llr"][bx].astype(np.float64)
    ar = a["loss"][ax].astype(np.float64)
    br = b["loss"][bx].astype(np.float64)
    if method == "prefer_decimated":
        value = al
        selected = np.zeros(al.size, np.int32)
    elif method == "prefer_native":
        value = bl
        selected = np.ones(al.size, np.int32)
    elif method == "lower_loss":
        use_native = br < ar
        value = np.where(use_native, bl, al)
        selected = use_native.astype(np.int32)
    elif method == "mean":
        value = 0.5 * (al + bl)
        selected = np.full(al.size, 2, np.int32)
    elif method == "loss_weighted":
        # Non-negative pilot information above an uninformative Bernoulli
        # predictor.  The normalized weights sum to one, so this is never an
        # independent-evidence LLR sum.
        aq = np.maximum(math.log(2.0) - ar, 1e-6)
        bq = np.maximum(math.log(2.0) - br, 1e-6)
        value = (aq * al + bq * bl) / (aq + bq)
        selected = np.full(al.size, 3, np.int32)
    elif method == "max_abs":
        use_native = np.abs(bl) > np.abs(al)
        value = np.where(use_native, bl, al)
        selected = 4 + use_native.astype(np.int32)
    else:
        raise ValueError(f"unknown fusion method {method!r}")
    llr[both] = value.astype(np.float32)
    owner[both] = selected
    return {"index": index, "llr": llr, "owner": owner}


def _record_from_pages(
    *,
    scan_id: str,
    capture_id: str,
    source_sha256: str,
    pages: dict[int, dict[str, np.ndarray]],
    descriptor,
):
    emission = payloaddec.ScanEmission(
        scan_id=scan_id, source_sha256=source_sha256, pages=pages,
        window_rows=[])
    return SimpleNamespace(
        scan_id=scan_id,
        source_sha256=source_sha256,
        capture_id=capture_id,
        emission=emission,
        tile_evidence_digests=receiver.tile_evidence_digests(
            emission, descriptor.spec(), descriptor.seed),
    )


def _view_records(
    scans: list[CompactScan],
    descriptor,
    prefix: str,
) -> list:
    records = []
    for index, scan in enumerate(scans):
        pages = {
            page: {
                "index": row["index"],
                "llr": row["llr"],
                "owner": row["owner"],
            }
            for page, row in scan.pages.items()
        }
        records.append(_record_from_pages(
            scan_id=f"{prefix}{index:03d}",
            capture_id=scan.capture_id,
            source_sha256=scan.source_sha256,
            pages=pages,
            descriptor=descriptor))
    return records


def _fusion_records(
    decimated: list[CompactScan],
    native: list[CompactScan],
    descriptor,
    profile: str,
    method: str,
) -> list:
    records = []
    for index, (dec, nat) in enumerate(
            zip(decimated, native, strict=True)):
        if dec.capture_id != nat.capture_id:
            raise ValueError("native/decimated capture order differs")
        pages = {}
        for page in sorted(set(dec.pages) | set(nat.pages)):
            if page not in dec.pages:
                row = nat.pages[page]
                pages[page] = {
                    "index": row["index"],
                    "llr": row["llr"],
                    "owner": np.ones(row["index"].size, np.int32),
                }
            elif page not in nat.pages:
                row = dec.pages[page]
                pages[page] = {
                    "index": row["index"],
                    "llr": row["llr"],
                    "owner": np.zeros(row["index"].size, np.int32),
                }
            else:
                pages[page] = _merge_page(
                    dec.pages[page], nat.pages[page], method)
        source_sha256 = hashlib.sha256(
            (f"e023b/correlated-multiview/v1:{profile}:{method}:"
             f"{dec.source_sha256}:{nat.source_sha256}").encode("ascii")
        ).hexdigest()
        records.append(_record_from_pages(
            scan_id=f"mv{index:03d}",
            capture_id=dec.capture_id,
            source_sha256=source_sha256,
            pages=pages,
            descriptor=descriptor))
    return records


def _retry_without_record_validation(
    session: receiver.ReceiverSession,
) -> dict:
    """Numerically mirror retry_failed_bp for compact qualifier records."""
    baseline_profile = receiver.decoder_profile(
        session.envelope.rate_id, receiver.BASELINE_BP_MAX_ITERS,
        receiver.BP_ALPHA)
    failed = {
        key for key, outcome in session.decode.tiles.items()
        if outcome.state == "attempted_failed"
    }
    parents = {}
    seen = set()
    for row in reversed(session.attempts):
        key = (row.page, *row.tile_yx)
        if (key not in failed or key in seen
                or row.stage not in ("scan", "union")
                or row.decoder_profile != baseline_profile):
            continue
        seen.add(key)
        if row.decoder_invoked and row.state == "attempted_failed":
            parents[key] = row

    newly_certified = 0
    cache = {}
    for key, parent in sorted(parents.items()):
        payload_index, llr = receiver._attempt_evidence(
            session, parent, cache)
        row, certified = receiver._apply_evaluation(
            session,
            key=key,
            stage="retry150",
            source=parent.source,
            evidence_digest=parent.evidence_digest,
            scan_ids=parent.scan_ids,
            capture_ids=parent.capture_ids,
            llr_values=llr,
            payload_indices=payload_index,
            decoder_max_iters=receiver.RETRY_BP_MAX_ITERS,
            decoder_alpha=receiver.BP_ALPHA,
            certificate_source=(
                "union" if parent.stage == "union" else parent.source),
        )
        if row is None or not row.decoder_invoked:
            raise ValueError("compact BP frontier changed during retry")
        newly_certified += int(certified)
    return {
        "eligible": len(parents),
        "attempted": len(parents),
        "certified": newly_certified,
    }


def _run_schedule(
    records: list,
    descriptor,
    metadata: dict,
    detector_profile: str,
    envelope_provenance: dict,
) -> tuple[dict, dict, dict]:
    session = receiver.ReceiverSession.create(
        descriptor,
        metadata["pages"],
        metadata["dpi"],
        rate_id=metadata["rate_id"],
        detector_profile=detector_profile,
        search_config=metadata["search_config"],
    )
    for record in records:
        session, _counts = receiver._apply_scan_unchecked(session, record)
    before = arms._certificate_snapshot(session)
    retry = _retry_without_record_validation(session)
    after = arms._certificate_snapshot(session)
    metrics = arms._attempt_metrics(session)
    metrics["tile_states"] = arms._state_counts(session)
    metrics["fatal"] = list(session.decode.fatal)
    return before, after, {
        "retry": retry,
        "attempts": metrics,
        "schedule_envelope": {
            "detector_profile": session.envelope.detector_profile,
            "scheduler_dpi": session.envelope.dpi,
            "pages": list(session.envelope.pages),
            "rate_id": session.envelope.rate_id,
            **envelope_provenance,
        },
    }


def _certificate_summary(certs: dict) -> dict:
    return {
        "count": len(certs),
        "set_sha256": arms._certificate_set_digest(certs),
        "bits_sha256": arms._certificate_bits_digest(certs),
    }


def _merge_certificates(decimated: dict, native: dict) -> tuple[dict, dict]:
    common = set(decimated) & set(native)
    conflicts = [
        key for key in sorted(common)
        if decimated[key] != native[key]
    ]
    if conflicts:
        raise ValueError(
            f"native/decimated certificate conflict at {conflicts[:8]}")
    merged = dict(decimated)
    merged.update(native)
    decimated_only = sorted(set(decimated) - set(native))
    native_only = sorted(set(native) - set(decimated))
    return merged, {
        "common": len(common),
        "decimated_only": len(decimated_only),
        "native_only": len(native_only),
        "conflicts": [],
        "decimated_only_tiles": [list(key) for key in decimated_only],
        "native_only_tiles": [list(key) for key in native_only],
    }


def _summary_matches(observed: dict, expected: dict | tuple) -> bool:
    if isinstance(expected, tuple):
        expected = {
            "count": expected[0],
            "set_sha256": expected[1],
            "bits_sha256": expected[2],
        }
    return observed == expected


def _cost_matches(observed: dict, expected: dict) -> bool:
    return all(observed[key] == value for key, value in expected.items())


def _expected_blind_identities_ok(blind: dict) -> bool:
    branch = blind["branches"]
    for name in ("decimated", "native"):
        expected = EXPECTED["branches"][name]
        envelope = branch[name]["schedule_envelope"]
        if (not _summary_matches(
                    branch[name]["before_bp"], expected["before_bp"])
                or not _summary_matches(
                    branch[name]["after_bp"], expected["after_bp"])
                or not _cost_matches(
                    branch[name]["attempts"], expected["cost"])
                or envelope["detector_profile"]
                != payloaddec.DETECTOR_CTX_PAVA_V1
                or envelope["kind"] != "replayed-real-footing"
                or envelope["source_footing"] != name
                or envelope["scheduler_dpi"]
                != EXPECTED["input_geometry"][name]["dpi"]):
            return False
    expected_union = EXPECTED["branches"]["union"]
    union = branch["certificate_union"]
    if any((
        not _summary_matches(
            union["certificates"], expected_union["certificates"]),
        union["overlap"]["common"] != expected_union["common"],
        tuple(tuple(row) for row in
              union["overlap"]["decimated_only_tiles"])
        != expected_union["decimated_only_tiles"],
        tuple(tuple(row) for row in
              union["overlap"]["native_only_tiles"])
        != expected_union["native_only_tiles"],
        not _cost_matches(
            union["aggregate_cost"], expected_union["cost"]),
    )):
        return False
    for profile, expected in EXPECTED["observations"].items():
        observed = blind["paired_observations"][profile]
        if any(observed[key] != expected[key]
               for key in ("cells", "paired", "hard_disagree")):
            return False
        expected_pearson = expected.get("llr_pearson_rounded_4")
        if (expected_pearson is not None
                and round(float(observed["llr_pearson"]), 4)
                != expected_pearson):
            return False
    for profile, methods in EXPECTED["fusion"].items():
        for method, expected in methods.items():
            row = blind["one_vote_fusion"][profile][method]
            envelope = row["schedule_envelope"]
            if (not _summary_matches(
                    row["before_bp"], expected["before_bp"])
                    or not _summary_matches(
                        row["after_bp"], expected["after_bp"])
                    or envelope["detector_profile"] != profile
                    or envelope["kind"]
                    != "synthetic-correlated-view-qualification"
                    or envelope["scheduler_dpi_source"]
                    != "decimated pinned state"
                    or envelope["scheduler_dpi"]
                    != EXPECTED["input_geometry"]["decimated"]["dpi"]
                    or envelope["physical_view_dpis"] != {
                        name: EXPECTED["input_geometry"][name]["dpi"]
                        for name in ("decimated", "native")}):
                return False
            if row["new_beyond_branch_union"]["count"] != 0:
                return False
    return True


def _run_blind(
    descriptor,
    metadata_by_footing: dict[str, dict],
    views: dict[str, dict[str, list[CompactScan]]],
) -> tuple[dict, dict[str, dict]]:
    print("\nBlind context+BP view branches", flush=True)
    branch_certs = {}
    branches = {}
    for name, prefix in (("decimated", "d"), ("native", "n")):
        records = _view_records(
            views[name][payloaddec.DETECTOR_CTX_PAVA_V1],
            descriptor, prefix)
        before, after, metrics = _run_schedule(
            records, descriptor, metadata_by_footing[name],
            payloaddec.DETECTOR_CTX_PAVA_V1,
            {
                "kind": "replayed-real-footing",
                "source_footing": name,
                "dpi_semantics": (
                    "exact DPI frozen by this footing's pinned state"),
            })
        branch_certs[name] = after
        branches[name] = {
            "before_bp": _certificate_summary(before),
            "after_bp": _certificate_summary(after),
            **metrics,
        }
        print(f"  {name}: {len(before)} -> {len(after)}", flush=True)

    branch_union, overlap = _merge_certificates(
        branch_certs["decimated"], branch_certs["native"])
    aggregate_cost = {
        key: sum(
            branches[name]["attempts"][key]
            for name in ("decimated", "native"))
        for key in (
            "crc_calls", "bp_iterations", "ledger_records",
            "below_floor_records")
    }
    branches["certificate_union"] = {
        "certificates": _certificate_summary(branch_union),
        "overlap": overlap,
        "aggregate_cost": aggregate_cost,
        "conservative_crc_false_accept_budget": sum(
            branches[name]["attempts"]["crc_false_accept_budget"]
            for name in ("decimated", "native")),
        "semantics": (
            "parallel correlated decoding hypotheses; union only certified "
            "bits, never native+decimated LLR evidence"),
    }
    print(f"  union: {len(branch_union)} "
          f"(common {overlap['common']}, "
          f"dec-only {overlap['decimated_only']}, "
          f"native-only {overlap['native_only']})", flush=True)

    observations = {}
    fusion = {}
    fusion_certs = {}
    fusion_metadata = metadata_by_footing["decimated"]
    view_dpis = {
        name: metadata_by_footing[name]["dpi"]
        for name in ("decimated", "native")
    }
    for profile, methods in PROFILE_METHODS.items():
        observations[profile] = _observation_stats(
            views["decimated"][profile], views["native"][profile])
        fusion[profile] = {}
        fusion_certs[profile] = {}
        print(f"\nBlind {profile} one-vote candidates", flush=True)
        for method in methods:
            records = _fusion_records(
                views["decimated"][profile],
                views["native"][profile],
                descriptor, profile, method)
            before, after, metrics = _run_schedule(
                records, descriptor, fusion_metadata, profile,
                {
                    "kind": "synthetic-correlated-view-qualification",
                    "physical_view_dpis": view_dpis,
                    "scheduler_dpi_source": "decimated pinned state",
                    "dpi_semantics": (
                        "qualification-only scheduler envelope; synthetic "
                        "records already contain page-indexed LLRs, so this "
                        "DPI is not attributed to either fused observation"),
                    "fusion_method": method,
                })
            new = sorted(set(after) - set(branch_union))
            differing = sorted(
                key for key in set(after) & set(branch_union)
                if after[key] != branch_union[key])
            fusion_certs[profile][method] = after
            fusion[profile][method] = {
                "before_bp": _certificate_summary(before),
                "after_bp": _certificate_summary(after),
                "new_beyond_branch_union": {
                    "count": len(new),
                    "tiles": [list(key) for key in new],
                },
                "different_bits_on_shared_certificate": {
                    "count": len(differing),
                    "tiles": [list(key) for key in differing],
                },
                "missing_from_branch_union": len(
                    set(branch_union) - set(after)),
                **metrics,
            }
            print(f"  {method}: {len(before)} -> {len(after)}, "
                  f"new beyond union={len(new)}", flush=True)

    blind = {
        "branches": branches,
        "paired_observations": observations,
        "one_vote_fusion": fusion,
    }
    compact_outputs = {
        "branch_union": branch_union,
        **{
            f"{profile}/{method}": certs
            for profile, rows in fusion_certs.items()
            for method, certs in rows.items()
        },
    }
    return blind, compact_outputs


def _paired_ground_truth_audit(
    decimated: list[CompactScan],
    native: list[CompactScan],
    gt_bits: np.ndarray,
) -> dict:
    paired = both_wrong = decimated_only_wrong = native_only_wrong = 0
    for dec, nat in zip(decimated, native, strict=True):
        if dec.capture_id != nat.capture_id:
            raise ValueError("native/decimated capture order differs")
        for page in sorted(set(dec.pages) & set(nat.pages)):
            if page != 0:
                raise ValueError(
                    "frozen E018 paired GT audit is page-0-only")
            a, b = dec.pages[page], nat.pages[page]
            index, apos, bpos, ahas, bhas = _paired_positions(a, b)
            both = ahas & bhas
            physical_index = index[both]
            truth = gt_bits[physical_index]
            dec_wrong = (
                (a["llr"][apos[both]] > 0.0).astype(np.uint8) != truth)
            nat_wrong = (
                (b["llr"][bpos[both]] > 0.0).astype(np.uint8) != truth)
            paired += int(physical_index.size)
            both_wrong += int(np.count_nonzero(dec_wrong & nat_wrong))
            decimated_only_wrong += int(np.count_nonzero(
                dec_wrong & ~nat_wrong))
            native_only_wrong += int(np.count_nonzero(
                ~dec_wrong & nat_wrong))
    decimated_wrong = both_wrong + decimated_only_wrong
    native_wrong = both_wrong + native_only_wrong

    def metric(count: int) -> dict:
        return {
            "count": count,
            "fraction_of_paired": count / paired if paired else None,
            "percent_of_paired": 100.0 * count / paired if paired else None,
        }

    return {
        "paired": paired,
        "decimated_wrong": metric(decimated_wrong),
        "native_wrong": metric(native_wrong),
        "both_wrong": metric(both_wrong),
        "decimated_only_wrong": metric(decimated_only_wrong),
        "native_only_wrong": metric(native_only_wrong),
        "both_correct": metric(
            paired - both_wrong - decimated_only_wrong
            - native_only_wrong),
        "error_domain": "descrambled transmitted payload bits",
    }


def _attach_ground_truth(
    blind: dict,
    compact_outputs: dict[str, dict],
    views: dict[str, dict[str, list[CompactScan]]],
    descriptor,
    rate_id: str,
) -> dict:
    # This is the only ground-truth open in the runner.  It occurs after
    # both branches, every fusion candidate, and all paired-observation
    # snapshots have been reduced to compact blind results.
    _field, gt_bits, _neighbors, reference = arms._load_ground_truth(
        descriptor)
    audits = {}
    for name, certs in sorted(compact_outputs.items()):
        wrong = arms._wrong_certificates(
            certs, descriptor, gt_bits, rate_id)
        audits[name] = {
            "certificates": len(certs),
            "wrong_count": len(wrong),
            "wrong_tiles": [list(key) for key in wrong],
        }
    paired_errors = {
        profile: _paired_ground_truth_audit(
            views["decimated"][profile],
            views["native"][profile],
            gt_bits)
        for profile in PROFILE_METHODS
    }
    return {
        "sha256": reference["sha256"],
        "loaded_after_all_blind_outputs": True,
        "audits": audits,
        "paired_observation_errors": paired_errors,
        "all_certificates_correct": all(
            row["wrong_count"] == 0 for row in audits.values()),
    }


def _expected_ground_truth_integer_counts_ok(
    ground_truth: dict,
) -> bool:
    observed_profiles = ground_truth["paired_observation_errors"]
    for profile, expected in EXPECTED[
            "ground_truth_integer_counts"].items():
        observed = observed_profiles[profile]
        if observed["paired"] != expected["paired"]:
            return False
        for name in (
                "decimated_wrong", "native_wrong", "both_wrong",
                "decimated_only_wrong", "native_only_wrong",
                "both_correct"):
            if observed[name]["count"] != expected[name]:
                return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--decimated", type=Path,
        default=arms.FOOTINGS["decimated"]["path"])
    parser.add_argument(
        "--native", type=Path,
        default=arms.FOOTINGS["native"]["path"])
    parser.add_argument("--out", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    started = time.monotonic()

    print("Load byte-pinned states and compact both detector views",
          flush=True)
    descriptor, dec_metadata, dec_views, dec_reference = _load_footing(
        "decimated", args.decimated)
    descriptor2, nat_metadata, nat_views, nat_reference = _load_footing(
        "native", args.native)
    if descriptor2.format_id != descriptor.format_id:
        raise ValueError("native/decimated format differs")
    comparable_metadata = ("pages", "rate_id")
    if any(dec_metadata[key] != nat_metadata[key]
           for key in comparable_metadata):
        raise ValueError("native/decimated decode envelope differs")
    if [
        row.capture_id
        for row in dec_views[payloaddec.DETECTOR_PAVA_V1]
    ] != [
        row.capture_id
        for row in nat_views[payloaddec.DETECTOR_PAVA_V1]
    ]:
        raise ValueError("native/decimated physical captures do not pair")
    views = {"decimated": dec_views, "native": nat_views}

    blind, compact_outputs = _run_blind(
        descriptor,
        {"decimated": dec_metadata, "native": nat_metadata},
        views)
    expected_ok = _expected_blind_identities_ok(blind)

    ground_truth = _attach_ground_truth(
        blind, compact_outputs, views, descriptor, dec_metadata["rate_id"])
    input_geometry_ok = all(
        reference["input_geometry"] == EXPECTED["input_geometry"][name]
        for name, reference in (
            ("decimated", dec_reference), ("native", nat_reference))
    )
    gates = {
        "complete_state_sha256_pins": True,
        "expected_input_geometry_exact": input_geometry_ok,
        "physical_capture_pairing": True,
        "no_cross_view_independent_llr_sum": True,
        "overlap_certificate_bits_equal": (
            not blind["branches"]["certificate_union"]["overlap"][
                "conflicts"]),
        "all_fusion_shared_certificate_bits_equal": all(
            row["different_bits_on_shared_certificate"]["count"] == 0
            for profile in blind["one_vote_fusion"].values()
            for row in profile.values()),
        "expected_blind_certificate_identities_and_costs_exact": expected_ok,
        "ground_truth_loaded_after_blind_outputs": (
            ground_truth["loaded_after_all_blind_outputs"]),
        "expected_ground_truth_integer_counts_exact": (
            _expected_ground_truth_integer_counts_ok(ground_truth)),
        "all_certificates_ground_truth_correct": (
            ground_truth["all_certificates_correct"]),
    }
    ok = all(value is True for value in gates.values())
    report = {
        "experiment": "e023b-correlated-multiview-qualification-v1",
        "qualification_only": True,
        "boundary": "LDPC and below; no fountain/rank/stop condition",
        "semantics": {
            "views": (
                "native 4800 and deterministic box3 decimated 1600 are "
                "correlated derivations of the same physical captures"),
            "parallel_branch_union": (
                "multiple decoder hypotheses and CRC exposures; only "
                "certificates are unioned"),
            "one_vote_fusion": (
                "at most one composite LLR per physical capture/page/"
                "payload cell before independent-capture union"),
            "production_state_created": False,
        },
        "implementation": {
            "script_sha256": arms._stream_sha256(Path(__file__).resolve()),
            "arms_qualifier_sha256": arms._stream_sha256(
                HERE / "qualify_e023b_arms.py"),
            "payloaddec_sha256": arms._stream_sha256(
                Path(payloaddec.__file__).resolve()),
            "receiver_sha256": arms._stream_sha256(
                Path(receiver.__file__).resolve()),
        },
        "inputs": {
            "decimated": {
                "artifact": args.decimated.name,
                **dec_reference,
            },
            "native": {
                "artifact": args.native.name,
                **nat_reference,
            },
        },
        "blind": blind,
        "ground_truth": ground_truth,
        "gates": gates,
        "gates_ok": ok,
    }
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    elapsed = time.monotonic() - started
    print(f"\nMULTIVIEW {'PASS' if ok else 'FAIL'} "
          f"in {elapsed:.2f}s -> {args.out}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
