"""(b) gates 1 and 2: equivalence and determinism for the mlx BP port.

GATE 1 — EQUIVALENCE.  Every attempt in the corpus is decoded twice: by
``holo.receiver.lib.ldpc.decode`` (float64, CPU, one tile at a time) and by
``bp_mlx.decode_batch`` (float32, GPU, the whole rate's attempts at
once).  Both outcomes are then run through the codec's own acceptance
test — syndrome AND CRC — because that, not bitwise float agreement, is
what decides whether a tile becomes a certificate.  The gate reports:

* attempts the CPU certifies where the GPU's user bits differ (the
  number that must be understood, whatever it is),
* attempts either side certifies against a wrong codeword (must be 0:
  a wrong certificate is the one failure mode with no honest reading),
* attempts one side certifies and the other does not, split by direction.

GATE 2 — DETERMINISM.  The same batch is decoded twice on the GPU, and
the same attempts are decoded again in a batch of a different size and
with a different host-sync cadence.  Three separate questions: does a
repeat give the same bits; does batch COMPOSITION change a tile's
answer; does the sync cadence.  Reported as measured, not as a target.

    PYTHONPATH=<worktree> <venv>/bin/python measure/accel/bp_equivalence.py \\
        --corpus <dir> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from holo.receiver.format import tile_codec
from holo.receiver.lib import ldpc

from measure.accel import bp_mlx

MAX_ITERS = (60, 150)
DETERMINISM_BATCH = (128, 61)
DETERMINISM_SYNC = (1, 8)
ALPHA = 0.8


def load(corpus: Path) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    llr = np.load(corpus / "corpus_llr.npy")
    truth = np.load(corpus / "corpus_truth.npy")
    meta = json.loads((corpus / "corpus_meta.json").read_text())["attempts"]
    return llr, truth, meta


def certified(hard: np.ndarray, cap: int) -> tuple[bool, np.ndarray]:
    user = hard[:cap].astype(np.uint8)
    crc_ok = bool(np.array_equal(
        hard[cap:cap + tile_codec.CRC_BITS], tile_codec.crc32_bits(user)))
    return crc_ok, user


def cpu_pass(llr: np.ndarray, meta: list[dict], max_iters: int) -> dict:
    syndrome = np.zeros(len(meta), bool)
    accept = np.zeros(len(meta), bool)
    hards = np.zeros((len(meta), tile_codec.N_CELLS), np.uint8)
    iters = np.zeros(len(meta), np.int64)
    started = time.perf_counter()
    for index, entry in enumerate(meta):
        code = ldpc.CODES[entry["rate_id"]]
        syn_ok, hard, n_iters, _extrinsic = ldpc.decode(
            llr[index, :code.n_bits], code, max_iters, ALPHA)
        crc_ok, _user = certified(hard, entry["cap"])
        syndrome[index] = syn_ok
        accept[index] = bool(syn_ok and crc_ok)
        hards[index, :code.n_bits] = hard
        iters[index] = n_iters
    return {"syndrome": syndrome, "accept": accept, "hard": hards,
            "iters": iters, "wall_s": time.perf_counter() - started}


def gpu_pass(llr: np.ndarray, meta: list[dict], max_iters: int,
             batch_size: int | None = None, sync_every: int = 1) -> dict:
    by_rate: dict[str, list[int]] = defaultdict(list)
    for index, entry in enumerate(meta):
        by_rate[entry["rate_id"]].append(index)
    syndrome = np.zeros(len(meta), bool)
    accept = np.zeros(len(meta), bool)
    hards = np.zeros((len(meta), tile_codec.N_CELLS), np.uint8)
    iters = np.zeros(len(meta), np.int64)
    started = time.perf_counter()
    for rate_id, rows in sorted(by_rate.items()):
        code = ldpc.CODES[rate_id]
        batched = bp_mlx.prepare(code)
        prepared = bp_mlx.prepare_llr(llr[rows, :code.n_bits])
        size = batch_size or len(rows)
        for start in range(0, len(rows), size):
            block = rows[start:start + size]
            hard, ok, spent = _decode_block(
                prepared[start:start + size], code, batched, max_iters,
                sync_every)
            for offset, index in enumerate(block):
                syndrome[index] = bool(ok[offset])
                hards[index, :code.n_bits] = hard[offset]
                crc_ok, _user = certified(hard[offset], meta[index]["cap"])
                accept[index] = bool(ok[offset] and crc_ok)
                iters[index] = int(spent[offset])
    return {"syndrome": syndrome, "accept": accept, "hard": hards,
            "iters": iters, "wall_s": time.perf_counter() - started}


def _decode_block(prepared: np.ndarray, code: ldpc.Code,
                  batched: bp_mlx.BatchedCode, max_iters: int,
                  sync_every: int):
    import mlx.core as mx

    L = mx.array(np.asarray(prepared, np.float32))
    hard, ok, iters = bp_mlx.bp_batch(L, batched, max_iters, ALPHA, False,
                                      sync_every)
    hard_np, ok_np = np.asarray(hard), np.asarray(ok)
    iters_np = np.asarray(iters).astype(np.int64)
    failed = np.flatnonzero(~ok_np)
    if max_iters > 0 and failed.size:
        retry = mx.array(np.asarray(prepared, np.float32)[failed])
        hard2, ok2, iters2 = bp_mlx.bp_batch(retry, batched, max_iters,
                                             ALPHA, True, sync_every)
        hard_np[failed] = np.asarray(hard2)
        ok_np[failed] = np.asarray(ok2)
        iters_np[failed] += np.asarray(iters2).astype(np.int64)
    return hard_np, ok_np, iters_np


def compare(cpu: dict, gpu: dict, truth: np.ndarray,
            meta: list[dict]) -> dict:
    rows: list[dict] = []
    wrong_cpu = 0
    wrong_gpu = 0
    both_certify_same = 0
    both_certify_differ = 0
    for index, entry in enumerate(meta):
        n_bits = entry["n_bits"]
        cap = entry["cap"]
        cpu_hard = cpu["hard"][index, :n_bits]
        gpu_hard = gpu["hard"][index, :n_bits]
        want = truth[index, :n_bits]
        if cpu["accept"][index] and not np.array_equal(cpu_hard, want):
            wrong_cpu += 1
        if gpu["accept"][index] and not np.array_equal(gpu_hard, want):
            wrong_gpu += 1
        if cpu["accept"][index] and gpu["accept"][index]:
            if np.array_equal(cpu_hard[:cap], gpu_hard[:cap]):
                both_certify_same += 1
            else:
                both_certify_differ += 1
                rows.append({
                    "index": index, "kind": "both_certify_different_bits",
                    **entry})
        elif cpu["accept"][index] and not gpu["accept"][index]:
            rows.append({"index": index, "kind": "cpu_only",
                         "cpu_iters": int(cpu["iters"][index]),
                         "gpu_iters": int(gpu["iters"][index]), **entry})
        elif gpu["accept"][index] and not cpu["accept"][index]:
            rows.append({"index": index, "kind": "gpu_only",
                         "cpu_iters": int(cpu["iters"][index]),
                         "gpu_iters": int(gpu["iters"][index]), **entry})
    per_rate: dict[str, dict] = defaultdict(
        lambda: {"attempts": 0, "cpu_certified": 0, "gpu_certified": 0,
                 "agree": 0})
    for index, entry in enumerate(meta):
        bucket = per_rate[entry["rate_id"]]
        bucket["attempts"] += 1
        bucket["cpu_certified"] += int(cpu["accept"][index])
        bucket["gpu_certified"] += int(gpu["accept"][index])
        bucket["agree"] += int(
            cpu["accept"][index] == gpu["accept"][index])
    return {
        "attempts": len(meta),
        "cpu_certified": int(cpu["accept"].sum()),
        "gpu_certified": int(gpu["accept"].sum()),
        "cpu_syndrome_ok": int(cpu["syndrome"].sum()),
        "gpu_syndrome_ok": int(gpu["syndrome"].sum()),
        "both_certify_same_bits": both_certify_same,
        "both_certify_different_bits": both_certify_differ,
        "cpu_only": sum(1 for row in rows if row["kind"] == "cpu_only"),
        "gpu_only": sum(1 for row in rows if row["kind"] == "gpu_only"),
        "wrong_certificates_cpu": wrong_cpu,
        "wrong_certificates_gpu": wrong_gpu,
        "cpu_wall_s": round(cpu["wall_s"], 2),
        "gpu_wall_s": round(gpu["wall_s"], 2),
        "per_rate": dict(per_rate),
        "divergences": rows[:200],
    }


def determinism(llr: np.ndarray, meta: list[dict], max_iters: int) -> dict:
    subset = list(range(0, len(meta), 3))
    sub_llr = llr[subset]
    sub_meta = [meta[index] for index in subset]
    first = gpu_pass(sub_llr, sub_meta, max_iters,
                     batch_size=DETERMINISM_BATCH[0],
                     sync_every=DETERMINISM_SYNC[0])
    repeat = gpu_pass(sub_llr, sub_meta, max_iters,
                      batch_size=DETERMINISM_BATCH[0],
                      sync_every=DETERMINISM_SYNC[0])
    regrouped = gpu_pass(sub_llr, sub_meta, max_iters,
                         batch_size=DETERMINISM_BATCH[1],
                         sync_every=DETERMINISM_SYNC[0])
    resynced = gpu_pass(sub_llr, sub_meta, max_iters,
                        batch_size=DETERMINISM_BATCH[0],
                        sync_every=DETERMINISM_SYNC[1])

    def diff(a: dict, b: dict) -> dict:
        return {
            "hard_bits_identical": bool(
                np.array_equal(a["hard"], b["hard"])),
            "accept_identical": bool(
                np.array_equal(a["accept"], b["accept"])),
            "iters_identical": bool(np.array_equal(a["iters"], b["iters"])),
            "attempts_with_differing_bits": int(np.count_nonzero(
                np.any(a["hard"] != b["hard"], axis=1))),
            "attempts_with_differing_accept": int(np.count_nonzero(
                a["accept"] != b["accept"])),
        }

    return {
        "attempts": len(subset),
        "max_iters": max_iters,
        "repeat_same_batching": diff(first, repeat),
        f"batch_{DETERMINISM_BATCH[0]}_vs_{DETERMINISM_BATCH[1]}":
            diff(first, regrouped),
        f"sync_{DETERMINISM_SYNC[0]}_vs_{DETERMINISM_SYNC[1]}":
            diff(first, resynced),
    }


def control_pass(llr: np.ndarray, meta: list[dict], max_iters: int) -> dict:
    """The same padded-layout decoder at float64, on mlx's CPU stream.

    mlx refuses float64 on the GPU and allows it on the CPU, so this is
    the port's own layout run at the CPU decoder's precision.  If it
    agrees with numpy where the GPU run does not, the divergence is
    float32, not the port.
    """
    import mlx.core as mx

    by_rate: dict[str, list[int]] = defaultdict(list)
    for index, entry in enumerate(meta):
        by_rate[entry["rate_id"]].append(index)
    syndrome = np.zeros(len(meta), bool)
    accept = np.zeros(len(meta), bool)
    hards = np.zeros((len(meta), tile_codec.N_CELLS), np.uint8)
    iters = np.zeros(len(meta), np.int64)
    started = time.perf_counter()
    for rate_id, rows in sorted(by_rate.items()):
        code = ldpc.CODES[rate_id]
        batched = bp_mlx.prepare(code)
        prepared = bp_mlx.prepare_llr(llr[rows, :code.n_bits])
        hard, ok, spent = bp_mlx.decode_batch(
            prepared, code, batched, max_iters, ALPHA,
            dtype=mx.float64, device=mx.cpu)
        for offset, index in enumerate(rows):
            syndrome[index] = bool(ok[offset])
            hards[index, :code.n_bits] = hard[offset]
            crc_ok, _user = certified(hard[offset], meta[index]["cap"])
            accept[index] = bool(ok[offset] and crc_ok)
            iters[index] = int(spent[offset])
    return {"syndrome": syndrome, "accept": accept, "hard": hards,
            "iters": iters, "wall_s": time.perf_counter() - started}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-iters", type=int, nargs="+",
                        default=list(MAX_ITERS))
    parser.add_argument("--mode", choices=("full", "control"),
                        default="full")
    parser.add_argument("--stride", type=int, default=1,
                        help="take every Nth attempt (control mode)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    llr, truth, meta = load(args.corpus)
    if args.mode == "control":
        rows = list(range(0, len(meta), args.stride))
        sub_llr, sub_truth = llr[rows], truth[rows]
        sub_meta = [meta[index] for index in rows]
        control: dict = {"attempts": len(rows), "by_max_iters": {}}
        for max_iters in args.max_iters:
            cpu = cpu_pass(sub_llr, sub_meta, max_iters)
            f64 = control_pass(sub_llr, sub_meta, max_iters)
            gpu = gpu_pass(sub_llr, sub_meta, max_iters)
            control["by_max_iters"][str(max_iters)] = {
                "mlx_float64_cpu_vs_numpy": compare(
                    cpu, f64, sub_truth, sub_meta),
                "mlx_float32_gpu_vs_numpy": compare(
                    cpu, gpu, sub_truth, sub_meta),
            }
            print(f"control max_iters={max_iters} done", flush=True)
        (args.out / "equivalence-control.json").write_text(
            json.dumps(control, indent=2, sort_keys=True, default=str)
            + "\n")
        return 0
    report: dict = {"corpus_attempts": len(meta), "alpha": ALPHA,
                    "equivalence": {}, "determinism": {}}
    for max_iters in args.max_iters:
        cpu = cpu_pass(llr, meta, max_iters)
        gpu = gpu_pass(llr, meta, max_iters)
        report["equivalence"][str(max_iters)] = compare(
            cpu, gpu, truth, meta)
        report["determinism"][str(max_iters)] = determinism(
            llr, meta, max_iters)
        print(f"max_iters={max_iters} "
              f"cpu_cert={report['equivalence'][str(max_iters)]['cpu_certified']} "
              f"gpu_cert={report['equivalence'][str(max_iters)]['gpu_certified']}",
              flush=True)
    (args.out / "equivalence.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key != "equivalence"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
