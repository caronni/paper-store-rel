"""The shape census: what the benched kernels actually see in a decode.

Runs ONE colour sim decode (the ``c3-cmy8-...@10x10`` capture the holo3
suite already builds) and one K sim decode with recorders wrapped round
the kernels the acceleration trial cares about — QDA scoring, the QDA
fit's covariance work, PAVA, the cold-placement FFT correlation, and the
LDPC belief-propagation loop.  It writes a JSON census of call counts,
argument shapes and self time.

The point is narrow: ``op_bench`` must bench the shapes the receiver
really runs, not shapes that seemed plausible from reading the source.

    PYTHONPATH=<worktree> <python> measure/accel/shapes.py --out <dir>
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import time
from pathlib import Path

import numpy as np

from holo.receiver import cli
from holo.receiver.format import tile_codec
from holo.receiver.lib import ldpc, pava
from holo.receiver.plugins import cold, color_model
from holo.receiver.tests import _h3_sims

CAPTURES = ("color", "k")


class Recorder:
    """Call counts, shape histograms and self time, per kernel."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = collections.Counter()
        self.seconds: dict[str, float] = collections.Counter()
        self.shapes: dict[str, dict[str, int]] = collections.defaultdict(
            collections.Counter)
        self.scalars: dict[str, list[float]] = collections.defaultdict(list)

    def note(self, kernel: str, shape: str, seconds: float) -> None:
        self.counts[kernel] += 1
        self.seconds[kernel] += seconds
        self.shapes[kernel][shape] += 1

    def scalar(self, name: str, value: float) -> None:
        self.scalars[name].append(float(value))

    def report(self, top: int = 12) -> dict:
        out: dict[str, dict] = {}
        for kernel, count in sorted(self.counts.items()):
            histogram = self.shapes[kernel]
            out[kernel] = {
                "calls": int(count),
                "self_s": round(self.seconds[kernel], 4),
                "distinct_shapes": len(histogram),
                "top_shapes": [
                    {"shape": shape, "calls": int(hits)}
                    for shape, hits in histogram.most_common(top)],
            }
        for name, values in sorted(self.scalars.items()):
            array = np.asarray(values, np.float64)
            out[f"scalar:{name}"] = {
                "n": int(array.size),
                "sum": float(array.sum()),
                "mean": float(array.mean()) if array.size else 0.0,
                "median": float(np.median(array)) if array.size else 0.0,
                "max": float(array.max()) if array.size else 0.0,
            }
        return out


def _wrap_qda_log_scores(recorder: Recorder):
    original = color_model.qda_log_scores

    def wrapped(model, features):
        x = np.asarray(features)
        started = time.perf_counter()
        result = original(model, features)
        recorder.note(
            "qda_log_scores",
            f"rows={x.shape[0]} features={x.shape[1]} "
            f"states={model.n_states}",
            time.perf_counter() - started)
        return result

    return original, wrapped


def _wrap_fit_qda(recorder: Recorder):
    original = color_model.fit_qda

    def wrapped(features, states, n_states):
        x = np.asarray(features)
        started = time.perf_counter()
        result = original(features, states, n_states)
        recorder.note(
            "fit_qda",
            f"rows={x.shape[0]} features={x.shape[1]} states={n_states}",
            time.perf_counter() - started)
        return result

    return original, wrapped


def _wrap_pava(recorder: Recorder):
    original = pava._pava_nodes

    def wrapped(scores, labels):
        n = int(np.asarray(scores).size)
        started = time.perf_counter()
        result = original(scores, labels)
        recorder.note("pava_nodes", f"n={n}",
                      time.perf_counter() - started)
        return result

    return original, wrapped


def _wrap_cold_map(recorder: Recorder):
    original = cold._page_candidate_map

    def wrapped(values, geometry, page, page_transforms):
        started = time.perf_counter()
        result = original(values, geometry, page, page_transforms)
        recorder.note(
            "cold_page_candidate_map",
            f"search={tuple(geometry.search_sites.shape)} "
            f"kernel={tuple(geometry.soft_kernel.shape)} "
            f"fshape={tuple(geometry.fshape)}",
            time.perf_counter() - started)
        return result

    return original, wrapped


def _wrap_bp(recorder: Recorder):
    original = ldpc._bp_loop

    def wrapped(L, code, max_iters, alpha, sum_product):
        started = time.perf_counter()
        result = original(L, code, max_iters, alpha, sum_product)
        elapsed = time.perf_counter() - started
        kind = "sum_product" if sum_product else "min_sum"
        recorder.note(
            f"bp_loop:{kind}",
            f"rate={code.rate_id} n={code.n_bits} k={code.k_bits} "
            f"edges={code.edge_chk.size} max_iters={max_iters}",
            elapsed)
        recorder.scalar(f"bp_iters:{kind}", result[2])
        return result

    return original, wrapped


def _wrap_decode_tile(recorder: Recorder):
    original = tile_codec.decode_tile

    def wrapped(llr_flat, rate_id, site_flat, a_t, b_t, max_iters, alpha):
        started = time.perf_counter()
        result = original(llr_flat, rate_id, site_flat, a_t, b_t,
                          max_iters, alpha)
        recorder.note(
            "decode_tile",
            f"rate={rate_id} cells={int(np.asarray(llr_flat).size)} "
            f"sites={int(np.asarray(site_flat).size)} "
            f"max_iters={max_iters}",
            time.perf_counter() - started)
        return result

    return original, wrapped


def _wrap_cmy8_stream(recorder: Recorder):
    original = tile_codec.cmy8_decode_stream

    def wrapped(level_llrs, bank, dither_bits, max_iters, alpha):
        started = time.perf_counter()
        result = original(level_llrs, bank, dither_bits, max_iters, alpha)
        recorder.note(
            "cmy8_decode_stream",
            f"bank={bank} cells={int(np.asarray(level_llrs).size)} "
            f"max_iters={max_iters}",
            time.perf_counter() - started)
        return result

    return original, wrapped


WRAPPERS = (
    (color_model, "qda_log_scores", _wrap_qda_log_scores),
    (color_model, "fit_qda", _wrap_fit_qda),
    (pava, "_pava_nodes", _wrap_pava),
    (cold, "_page_candidate_map", _wrap_cold_map),
    (ldpc, "_bp_loop", _wrap_bp),
    (tile_codec, "decode_tile", _wrap_decode_tile),
    (tile_codec, "cmy8_decode_stream", _wrap_cmy8_stream),
)


@contextlib.contextmanager
def instrumented(recorder: Recorder):
    installed: list[tuple[object, str, object]] = []
    try:
        for module, name, factory in WRAPPERS:
            original, wrapped = factory(recorder)
            installed.append((module, name, original))
            setattr(module, name, wrapped)
        yield recorder
    finally:
        for module, name, original in reversed(installed):
            setattr(module, name, original)


def build_capture(name: str, root: Path) -> _h3_sims.SimCapture:
    outdir = root / name
    if name == "color":
        expected, builder, loader = (
            _h3_sims.EXPECTED_COLOR, _h3_sims.make_color,
            _h3_sims.capture_color)
    else:
        expected, builder, loader = (
            _h3_sims.EXPECTED_K, _h3_sims.make_k, _h3_sims.capture_k)
    if _h3_sims.verify(outdir, expected) is not None:
        builder(outdir)
        problem = _h3_sims.verify(outdir, expected)
        if problem is not None:
            raise RuntimeError(f"{name} sim does not match frozen: {problem}")
    return loader(outdir)


def census(name: str, root: Path, workers: int) -> dict:
    capture = build_capture(name, root)
    run_dir = root / f"{name}-run"
    out_path = root / f"{name}-payload.bin"
    argv = ["decode", str(capture.tiff), "--dpi", str(int(capture.dpi)),
            "--format", capture.format_ref, "--out", str(out_path),
            "--workers", str(workers), "--run-dir", str(run_dir)]
    recorder = Recorder()
    started = time.perf_counter()
    with instrumented(recorder):
        with (contextlib.redirect_stdout(io.StringIO()),
              contextlib.redirect_stderr(io.StringIO())):
            exit_code = cli.main(list(argv))
    wall_s = time.perf_counter() - started
    return {
        "capture": name,
        "format_ref": capture.format_ref,
        "workers": workers,
        "exit_code": int(exit_code),
        "wall_s": round(wall_s, 3),
        "kernels": recorder.report(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="directory for sims, run dirs and census.json")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--captures", nargs="+", default=list(CAPTURES))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    reason = _h3_sims.producer_unavailable_reason()
    if reason is not None:
        raise SystemExit(f"cannot build sims: {reason}")
    report = {
        "codes": {
            rate_id: {
                "n_bits": int(code.n_bits), "k_bits": int(code.k_bits),
                "checks": int(code.n_bits - code.k_bits),
                "edges": int(code.edge_chk.size),
            }
            for rate_id, code in sorted(ldpc.CODES.items())},
        "captures": [census(name, args.out, args.workers)
                     for name in args.captures],
    }
    target = args.out / "census.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
