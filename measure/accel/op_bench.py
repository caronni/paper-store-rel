"""(a) part two: what the receiver's own kernels cost, at census shapes.

Every shape here is either taken from ``measure/accel/shapes.py``'s census
of a real (sim) decode, or derived from a printed format's geometry — see
the ``source`` field on each row.  The question the bench answers is not
"how fast is this machine at GEMM" (``blas_probe`` answers that) but
"does any receiver kernel sit in a regime where the BLAS, and therefore
AMX, can matter".

The feature-width sweep is the crossover probe: the colour head runs at
three features, and the sweep shows what the same QDA scoring costs as
the feature count grows, i.e. how far the receiver is from the regime
where the matrix engine earns anything.

    PYTHONPATH=<worktree> <python> measure/accel/op_bench.py --out <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from holo.receiver.format import identity, tile_codec
from holo.receiver.lib import pava
from holo.receiver.plugins import cold, color_model, words
from holo.receiver.plugins import color_region_ctx as ctx

SEED = 20260831
REPEATS = 9
HEAVY_REPEATS = 3

# Census shapes (from the accel census of the colour + K sim decodes,
# 2026-09; measure/accel/README.md).
QDA_ROWS = (422, 677, 31164, 32610)
FIT_ROWS = (483, 745)
PAVA_N = (417, 4096, 40000)
FEATURE_WIDTHS = (3, 8, 16, 32, 64, 128, 256)
CROSSOVER_ROWS = 32610
CTX_ROWS = (500, 1200, 8000)
COLD_ROWS = (
    ("sim-colour-page c3-cmy8-r0550x0550x0547@10x10",
     "c3-cmy8-r0550x0550x0547@10x10"),
    ("sheet-H-class c2-cmy8-r0700@53x37", "c2-cmy8-r0700x0700x0700@53x37"),
)
CMY7_BANK = identity.CMY7_BANK_CHILDREN


def bench(name: str, source: str, fn: Callable[[], object],
          repeats: int = REPEATS, note: str = "",
          flop: float | None = None) -> dict:
    """Time one call.

    ``flop`` is the op's arithmetic count where it is known exactly, so
    the row can carry an achieved GFLOP/s next to ``blas_probe``'s peak.
    That ratio, not the millisecond, is what says whether a matrix
    engine has anything to bite on.
    """
    fn()
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - started)
    samples.sort()
    row = {
        "op": name,
        "source": source,
        "note": note,
        "repeats": repeats,
        "min_ms": samples[0] * 1e3,
        "median_ms": samples[len(samples) // 2] * 1e3,
        "max_ms": samples[-1] * 1e3,
    }
    if flop is not None:
        row["flop"] = float(flop)
        row["achieved_gflops"] = float(flop) / samples[0] / 1e9
    return row


def qda_score_flop(rows: int, width: int, states: int) -> float:
    """Two triangular solves per state (each rows*width^2 mults plus as
    many adds), then the squared-norm reduction."""
    return states * (2.0 * rows * width * width + 2.0 * rows * width)


def _qda_model(rng: np.random.Generator, n_features: int,
               n_states: int) -> color_model.QdaModel:
    rows = max(64 * n_states, 16 * n_features)
    features = rng.standard_normal((rows, n_features))
    states = rng.integers(0, n_states, size=rows)
    features += states[:, None] * 0.7
    return color_model.fit_qda(features, states, n_states)


def qda_rows(rng: np.random.Generator) -> list[dict]:
    out: list[dict] = []
    models: dict[int, color_model.QdaModel] = {}
    for n_states in (8, 7):
        model = _qda_model(rng, 3, n_states)
        models[n_states] = model
        for rows in QDA_ROWS:
            features = rng.standard_normal((rows, 3))
            out.append(bench(
                f"qda_log_scores rows={rows} F=3 S={n_states}",
                "census: colour sim decode"
                if n_states == 8 else "census shapes, cmy7 state count",
                lambda m=model, f=features: color_model.qda_log_scores(m, f),
                flop=qda_score_flop(rows, 3, n_states)))
    # The primitives underneath one state's score, at the widest census
    # row count: this is where the BLAS actually gets called.
    model = models[8]
    features = rng.standard_normal((CROSSOVER_ROWS, 3))
    difference = features - model.means[0]
    out.append(bench(
        f"  primitive np.linalg.solve (3,3) x (3,{CROSSOVER_ROWS})",
        "census: colour sim decode",
        lambda a=model.cholesky[0], b=difference: np.linalg.solve(a, b.T),
        flop=2.0 * CROSSOVER_ROWS * 9))
    out.append(bench(
        "  primitive np.linalg.cholesky (3,3)",
        "census: colour sim decode",
        lambda a=model.cholesky[0] @ model.cholesky[0].T:
        np.linalg.cholesky(a)))
    out.append(bench(
        f"  primitive gram X.T@X ({CROSSOVER_ROWS},3)",
        "census: colour sim decode",
        lambda x=features: x.T @ x,
        flop=2.0 * CROSSOVER_ROWS * 9))
    return out


def fit_rows(rng: np.random.Generator) -> list[dict]:
    out: list[dict] = []
    for rows in FIT_ROWS:
        features = rng.standard_normal((rows, 3))
        states = rng.integers(0, 8, size=rows)
        features += states[:, None] * 0.7
        out.append(bench(
            f"fit_qda rows={rows} F=3 S=8", "census: colour sim decode",
            lambda f=features, s=states: color_model.fit_qda(f, s, 8)))
    return out


def crossover_rows(rng: np.random.Generator) -> list[dict]:
    out: list[dict] = []
    for width in FEATURE_WIDTHS:
        model = _qda_model(rng, width, 8)
        features = rng.standard_normal((CROSSOVER_ROWS, width))
        out.append(bench(
            f"qda_log_scores rows={CROSSOVER_ROWS} F={width} S=8",
            "derived: feature-width crossover sweep",
            lambda m=model, f=features: color_model.qda_log_scores(m, f),
            note="F=3 is the shipped colour head",
            flop=qda_score_flop(CROSSOVER_ROWS, width, 8)))
    return out


def pava_rows(rng: np.random.Generator) -> list[dict]:
    out: list[dict] = []
    for n in PAVA_N:
        scores = rng.standard_normal(n).astype(np.float32)
        labels = (rng.random(n) < 0.5).astype(np.float64)
        out.append(bench(
            f"pava_nodes n={n}",
            "census: K sim decode (n=417)" if n == 417
            else "derived: PAVA size sweep",
            lambda s=scores, y=labels: pava._pava_nodes(s, y)))
    return out


def _population(rng: np.random.Generator, rows: int) -> ctx.Population:
    scores = rng.standard_normal((rows, 8))
    states = rng.integers(0, 8, size=rows)
    scores[np.arange(rows), states] += 1.5
    bins = rng.integers(-1, ctx.N_CONTEXT_BINS, size=(rows, 3)).astype(
        np.int8)
    kinds = (rng.random(rows) < 0.3).astype(np.int8)
    return ctx.Population(scores, states.astype(np.int64), bins, kinds)


def ctx_rows(rng: np.random.Generator) -> list[dict]:
    out: list[dict] = []
    config = ctx.ContextConfig()
    for rows in CTX_ROWS:
        search = _population(rng, rows)
        validation = _population(rng, max(rows // 2, 100))
        out.append(bench(
            f"ctx _fit_matrix_curves rows={rows} S=8",
            "census-adjacent: owner-selection split sizes 483/745",
            lambda s=search, v=validation: ctx._fit_matrix_curves(
                s, v, config, False)))
    cells = np.stack(np.meshgrid(np.arange(200), np.arange(200),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    ink = (rng.random(cells.shape[0]) < 0.5).astype(np.uint8)
    out.append(bench(
        "ctx context_neighbour_counts 200x200 window",
        "derived: WINDOW_CELLS grid",
        lambda c=cells, i=ink: ctx.context_neighbour_counts(c, i)))
    return out


def cmy7_rows(rng: np.random.Generator) -> list[dict]:
    n_code = tile_codec.bank_transmitted_bits(CMY7_BANK)
    n_packs = n_code // tile_codec.CMY7_BITS_PER_PACK
    scores = rng.standard_normal(
        (n_packs, tile_codec.CMY7_CELLS_PER_PACK, 6)) * 3.0
    prior = rng.standard_normal((n_packs, tile_codec.CMY7_BITS_PER_PACK))
    weights = rng.random((n_packs, tile_codec.CMY7_N_CANDIDATES))
    bits = tile_codec._CMY7_CANDIDATE_BITS
    return [
        bench(f"cmy7_soft_demap packs={n_packs} (no prior)",
              f"derived: CMY7 bank {CMY7_BANK}",
              lambda s=scores: tile_codec.cmy7_soft_demap(s, None),
              repeats=HEAVY_REPEATS),
        bench(f"cmy7_soft_demap packs={n_packs} (with prior)",
              f"derived: CMY7 bank {CMY7_BANK}",
              lambda s=scores, p=prior: tile_codec.cmy7_soft_demap(s, p),
              repeats=HEAVY_REPEATS),
        bench(f"  primitive ({n_packs},2048) @ (2048,11) bool rhs",
              "the one true GEMM in the receiver's hot path",
              lambda w=weights, b=bits: w @ b,
              repeats=HEAVY_REPEATS,
              flop=2.0 * n_packs * tile_codec.CMY7_N_CANDIDATES
              * tile_codec.CMY7_BITS_PER_PACK),
        bench(f"  primitive ({n_packs},2048) @ (2048,11) float rhs",
              "the same GEMM with a float right-hand side",
              lambda w=weights,
              b=tile_codec._CMY7_CANDIDATE_BITS_F: w @ b,
              repeats=HEAVY_REPEATS,
              flop=2.0 * n_packs * tile_codec.CMY7_N_CANDIDATES
              * tile_codec.CMY7_BITS_PER_PACK),
    ]


def cold_rows(rng: np.random.Generator) -> list[dict]:
    out: list[dict] = []
    for label, format_ref in COLD_ROWS:
        row = identity.resolve_format_ref(format_ref)
        reference = words.ReferenceField(row).page(0)
        patch = 200
        evidence = rng.standard_normal((patch, patch)).astype(np.float32)
        mask = rng.random((patch, patch)) < 0.6
        geometries = cold._cold_map_geometries(
            evidence, mask, reference.sites, 8, True)
        geometry = next(g for g in geometries if g is not None)
        out.append(bench(
            f"cold _page_candidate_map {label}",
            f"derived: {format_ref} page + WINDOW_CELLS patch",
            lambda v=reference.values, g=geometry:
            cold._page_candidate_map(v, g, 0, {}),
            repeats=HEAVY_REPEATS,
            note=f"search={tuple(geometry.search_sites.shape)} "
                 f"kernel={tuple(geometry.soft_kernel.shape)} "
                 f"fshape={tuple(geometry.fshape)}"))
    return out


SECTIONS = (
    ("qda_scoring", qda_rows),
    ("qda_fit", fit_rows),
    ("feature_width_crossover", crossover_rows),
    ("pava", pava_rows),
    ("context_matrix", ctx_rows),
    ("cmy7_demap", cmy7_rows),
    ("cold_fft", cold_rows),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--sections", nargs="+",
                        default=[name for name, _fn in SECTIONS])
    args = parser.parse_args()
    rng = np.random.default_rng(SEED)
    report = {
        "host": {
            "platform": platform.platform(),
            "loadavg_before": os.getloadavg(),
            "veclib_maximum_threads": os.environ.get(
                "VECLIB_MAXIMUM_THREADS", "<unset>"),
        },
        "sections": {},
    }
    for name, builder in SECTIONS:
        if name not in args.sections:
            continue
        report["sections"][name] = builder(rng)
    report["host"]["loadavg_after"] = os.getloadavg()
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "ops.json").write_text(text + "\n")
    for name, rows in report["sections"].items():
        print(f"== {name} ==")
        for entry in rows:
            achieved = (f"{entry['achieved_gflops']:8.2f} GF/s"
                        if "achieved_gflops" in entry else " " * 13)
            print(f"  {entry['op']:<58} "
                  f"median {entry['median_ms']:9.4f} ms  "
                  f"min {entry['min_ms']:9.4f} ms  {achieved}   "
                  f"[{entry['source']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
