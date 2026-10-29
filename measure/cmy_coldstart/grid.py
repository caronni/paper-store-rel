"""G12's grid — cold start on c2 cmy fragments (CMY-RECEIVER-PLAN A9; CMY-DESIGN §11 G12).

What: every scrap the suite's stimulus module can cut (`holo.receiver.tests._h3_sims_cmy`: the 1x2, 2x2 and 2x3-tile
shapes, each at its seeded origin, x the plants Z (0, 0), A (0.5, -0.5), B (1.0, 1.0) dots in (dM, dY), each with its
+-0.5-dot M/Y drift and the drift's same-blur control, and C (2.5, -2.5) constant -- 21 scraps), rendered by the
suite's own builders and decoded by the production receiver in process at ONE worker, `--max-pages 1`, as the
tests decode their three 2x3 scraps.  Per scrap: placed at the true counters (address coverage = the scrap's tiles,
every committed pose within half a cell of the printed one), certificates per stream and per minting row, how many
came before the first field solve, every certificate's user bits against the GENERATOR's (the GT plane states'
labels decoded at +-24 through holo.core's own stream decoder, W3's route -- independent of the receiver's frame
code), the CRC exposure bound (LDPC attempts, which every CRC consult is one of, x 2^-32), the last field solve on
the scrap's tiles (tiles with data, mean F_p - F_C, its x range across the scrap, error against the plant), and
whether the run closed.
And the FULL 10x10 page under Z, A and B as constant offsets (no drift: the scrap's +-0.5 dot over two tiles would be
+-2.5 dots over ten), decoded at eight workers as the suite decodes its c2 page (B is that page): status, payload
against the emission, certificates against the generator's, minting rows, the field if it solved before the close.
Why: G12 is a TEST at three 2x3 scraps and a RECORD over the rest (R19): the 1x2 and 2x2 shapes and B, the drift
and its control side by side, and the whole page's byte-exact close under Z, A and B (CMY-DESIGN §11 G12, the
plan's "byte-exact in Z, A, B"; the suite tests B, its c2 page).
How: `python -m measure.cmy_coldstart.grid --out DIR` renders into DIR/scraps and DIR/pages, decodes into
DIR/runs/<name>/run.<pid>, writes DIR/grid.json and prints the tables; a scrap or page already decoded is read back
from runs/<name>/record.json.

    cd <repo> && PYTHONPATH=src:. \\
        env/bin/python -u -m measure.cmy_coldstart.grid --out <dir>
"""
from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

Scrap = tuple[tuple[int, int], str, str]
TILE_CELLS = 64
CRC_BITS = 32


def all_scraps(sims: Any) -> tuple[Scrap, ...]:
    """Every shape x (Z, A, B) x (drift, control), then C constant."""
    out: list[Scrap] = []
    for shape in sims.CMY_C2_CROP_SHAPES:
        for plant in ("Z", "A", "B"):
            for drift in ("drift", "control"):
                out.append((shape, plant, drift))
        out.append((shape, "C", "none"))
    return tuple(out)


def generator_user_bits(sims: Any, emit_dir: Path) -> dict[tuple[int, int, int, str], np.ndarray]:
    """The generator's user bits for every tile and stream of the c2 page: W3's route
    (tests/holo/test_cmy_round_trip._tile_user_bits) over the emission's GT planes."""
    from holo.core import channel, color_tile, keystream
    from holo.format.resolve import resolve_format_ref
    from holo.gen.color_compose import _color_geometry

    spec = resolve_format_ref(sims.CMY_C2_FORMAT_REF)
    dots = spec.cell_dots
    packed = np.load(emit_dir / "page000_gt.npy", allow_pickle=False)
    planes = np.unpackbits(packed, axis=2, count=spec.cells_yx[1] * dots, bitorder="big")[:, ::dots, ::dots]
    field = (planes[0] | planes[1] << 1 | planes[2] << 2).astype(np.uint8)
    placed_flat = _color_geometry(spec)[0]
    truth: dict[tuple[int, int, int, str], np.ndarray] = {}
    for counter in range(spec.tiles_per_page):
        page, ty, tx = spec.tile_address(counter)
        tile = field[ty * TILE_CELLS:(ty + 1) * TILE_CELLS, tx * TILE_CELLS:(tx + 1) * TILE_CELLS].reshape(-1)
        placed = tile[placed_flat]
        sequential = np.empty_like(placed)
        sequential[keystream.color_cell_permutation(spec.seed, counter, spec.payload_cells)] = placed
        for aux, (stream, labels) in enumerate(zip(spec.stream_profiles, channel.cmy_state_labels(sequential),
                                                   strict=True), start=1):
            outcome = color_tile.cmy8_decode_stream(
                np.where(labels == 1, 24.0, -24.0), stream.fec,
                keystream.cmy8_dither_bits(spec.seed, aux, counter, stream.fec.transmitted_bits))
            if not outcome.ok:
                raise SystemExit(f"GT tile {counter} {stream.stream_id} does not decode -- truth-path fork")
            truth[(page, ty, tx, stream.stream_id)] = outcome.certified_user_bits.astype(np.uint8)
    return truth


def decode(tiff: Path, run_dir: Path, sims: Any, workers: int) -> tuple[Any, list, float, bytes | None]:
    from holo.receiver import cli, engine

    out = run_dir.parent / "payload.bin"
    argv = ["decode", str(tiff), "--dpi", str(int(sims.CMY_C2_DPI)), "--format", sims.CMY_C2_FORMAT_REF,
            "--max-pages", "1", "--out", str(out), "--run-dir", str(run_dir), "--workers", str(workers)]
    request = cli._request(cli._build_parser().parse_args(argv))
    events: list = []
    started = time.perf_counter()
    eng = engine._Engine(request, events)
    result = eng.run()
    payload = getattr(result, "payload", None)
    return eng, events, time.perf_counter() - started, payload


def pose_error_px(event: Any, origin_tiles: tuple[int, int], border_px: float, pitch_px: float) -> float:
    """Placed minus printed pixel of a committed window's centre cell (the scrap prints page cell c at
    border + pitch * (c - its first cell), pixel-edge frame; the native affine is pixel-centre)."""
    first = np.asarray(origin_tiles, np.float64) * TILE_CELLS
    centre = np.asarray(event.page_origin_yx, np.float64) + np.asarray(event.shape_yx, np.float64) / 2.0
    affine = np.asarray(event.native_affine, np.float64).reshape(2, 3)
    placed = affine[:, :2] @ centre + affine[:, 2]
    return float(np.abs(placed - (border_px - 0.5 + pitch_px * (centre - first))).max())


def measure_scrap(sims: Any, scrap: Scrap, eng: Any, events: list, wall_s: float,
                  truth: dict[tuple[int, int, int, str], np.ndarray]) -> dict[str, Any]:
    from holo.receiver import data

    shape, plant, drift = scrap
    ty0, tx0 = sims.cmy_c2_crop_origin(shape)
    tiles = {(0, ty0 + dy, tx0 + dx) for dy in range(shape[0]) for dx in range(shape[1])}
    pitch_px = sims.CMY_C2_DPI / 300.0
    border_px = sims.COLOR_BORDER_DOTS * sims.CMY_C2_PX_PER_DOT
    covered = {(e.page, ty, tx) for e in events if isinstance(e, data.AddressCoverage) for ty, tx, _ in e.tiles}
    poses = [e for e in events if isinstance(e, data.PoseCommitted)]
    worst_pose = max((pose_error_px(e, (ty0, tx0), border_px, pitch_px) for e in poses), default=float("nan"))
    certificates = eng.certificates()
    wrong = sorted(str(key) for key, cert in certificates.items()
                   if not np.array_equal(np.asarray(cert.user_bits, np.uint8), truth[key]))
    outcomes = [e for e in events if isinstance(e, data.TileOutcome)]
    first_solve = next((i for i, e in enumerate(events) if isinstance(e, data.FieldSolved)), None)
    minted = collections.Counter(e.source for e in outcomes if e.result == "certified")
    before = sum(1 for i, e in enumerate(events) if isinstance(e, data.TileOutcome) and e.result == "certified"
                 and (first_solve is None or i < first_solve))
    ldpc = sum(1 for e in outcomes if e.result in ("certified", "attempted_failed"))
    done = [e for e in events if isinstance(e, data.RunDone)]
    field: dict[str, Any] = {"solves": sum(1 for e in events if isinstance(e, data.FieldSolved))}
    solved = [e for e in events if isinstance(e, data.FieldSolved)]
    if solved:
        planes = {p.plane: p for p in solved[-1].planes}
        cut = (slice(ty0, ty0 + shape[0]), slice(tx0, tx0 + shape[1]))
        zero = np.asarray(planes[0].delta_grid_dots_xy, np.float64)[cut]
        for plane, name, planted in zip((1, 2), ("M", "Y"), sims.CMY_C2_CROP_PLANTS_DOTS[plant]):
            has = np.asarray(planes[plane].has_data, bool)[cut]
            if not has.any():
                field[name] = {"tiles": 0}
                continue
            read = (np.asarray(planes[plane].delta_grid_dots_xy, np.float64)[cut] - zero)[has]
            mean = read.mean(axis=0)
            field[name] = {"tiles": int(has.sum()), "mean_xy": [round(float(v), 3) for v in mean],
                           "x_range": [round(float(read[:, 0].min()), 3), round(float(read[:, 0].max()), 3)],
                           "error_xy": [round(float(mean[0] - planted), 3), round(float(mean[1]), 3)]}
    return {"scrap": sims.cmy_c2_crop_name(shape, plant, drift), "shape": list(shape), "plant": plant,
            "drift": drift, "origin_tiles": [ty0, tx0], "placed_true": covered == tiles and bool(poses)
            and worst_pose < pitch_px / 2, "covered": len(covered), "worst_pose_px": round(worst_pose, 2),
            "certified": {s: sum(1 for k in certificates if k[3] == s) for s in ("hi", "lo")},
            "minted_by": dict(minted), "before_first_solve": before, "wrong": wrong, "ldpc_attempts": ldpc,
            "crc_exposure": ldpc * 2.0 ** -CRC_BITS, "closed": bool(done and done[-1].status == "verified"),
            "run_status": done[-1].status if done else None, "field": field, "wall_s": round(wall_s, 1)}


def measure_page(sims: Any, plant: str, eng: Any, events: list, wall_s: float, payload: bytes | None,
                 truth: dict[tuple[int, int, int, str], np.ndarray]) -> dict[str, Any]:
    from holo.receiver import data

    import hashlib

    certificates = eng.certificates()
    wrong = sorted(str(key) for key, cert in certificates.items()
                   if not np.array_equal(np.asarray(cert.user_bits, np.uint8), truth[key]))
    outcomes = [e for e in events if isinstance(e, data.TileOutcome)]
    ldpc = sum(1 for e in outcomes if e.result in ("certified", "attempted_failed"))
    solved = [e for e in events if isinstance(e, data.FieldSolved)]
    field: dict[str, Any] = {"solves": len(solved)}
    if solved:
        planes = {p.plane: p for p in solved[-1].planes}
        zero = np.asarray(planes[0].delta_grid_dots_xy, np.float64)
        for plane, name in ((1, "M"), (2, "Y")):
            has = np.asarray(planes[plane].has_data, bool)
            if has.any():
                read = (np.asarray(planes[plane].delta_grid_dots_xy, np.float64) - zero)[has]
                field[name] = {"tiles": int(has.sum()), "mean_xy": [round(float(v), 3) for v in read.mean(axis=0)]}
    done = [e for e in events if isinstance(e, data.RunDone)]
    return {"page": plant, "plant_dots": list(sims.CMY_C2_CROP_PLANTS_DOTS[plant]),
            "status": done[-1].status if done else None,
            "byte_exact": payload is not None and hashlib.sha256(payload).hexdigest() == sims.CMY_C2_PAYLOAD_SHA256,
            "certified": {s: sum(1 for k in certificates if k[3] == s) for s in ("hi", "lo")},
            "minted_by": dict(collections.Counter(e.source for e in outcomes if e.result == "certified")),
            "wrong": wrong, "ldpc_attempts": ldpc, "crc_exposure": ldpc * 2.0 ** -CRC_BITS, "field": field,
            "wall_s": round(wall_s, 1)}


def page_text(r: dict[str, Any]) -> str:
    c = r["certified"]
    mints = " ".join(f"{k.split('/')[-1]} {v}" for k, v in sorted(r["minted_by"].items())) or "-"
    field = " ".join(f"{k} {v['mean_xy'][0]:+.2f}" for k, v in r["field"].items() if k in ("M", "Y")) or "unsolved"
    return (f"| {r['page']} {tuple(r['plant_dots'])} | {r['status']} | {'yes' if r['byte_exact'] else 'NO'} | "
            f"{c['hi']}/{c['lo']} | {len(r['wrong'])} | {mints} | {field} | {r['ldpc_attempts']} "
            f"({r['crc_exposure']:.1e}) | {r['wall_s']} |")


PAGE_HEADER = ("| page (dM, dY) | status | byte-exact | hi/lo | wrong | minted by | field before the close | LDPC "
               "attempts (CRC exposure) | wall s |\n|---|---|---|---|---|---|---|---|---|")


def row_text(r: dict[str, Any]) -> str:
    def plane(name: str) -> str:
        f = r["field"].get(name)
        if f is None:
            return "-"
        if not f["tiles"]:
            return "no data"
        return f"{f['mean_xy'][0]:+.2f} [{f['x_range'][0]:+.2f},{f['x_range'][1]:+.2f}] /{f['tiles']}"
    c = r["certified"]
    mints = " ".join(f"{k.split('/')[-1]} {v}" for k, v in sorted(r["minted_by"].items())) or "-"
    return (f"| {r['scrap'][12:]} | {tuple(r['origin_tiles'])} | {'yes' if r['placed_true'] else 'NO'} | "
            f"{c['hi']}/{c['lo']} | {len(r['wrong'])} | {mints} | {r['before_first_solve']} | {plane('M')} | "
            f"{plane('Y')} | {r['ldpc_attempts']} ({r['crc_exposure']:.1e}) | {'yes' if r['closed'] else 'no'} | "
            f"{r['wall_s']} |")


HEADER = ("| scrap | origin | true counters | hi/lo | wrong | minted by | before 1st solve | field M - C (x, range "
          "/tiles) | field Y - C | LDPC attempts (CRC exposure) | closes | wall s |\n|---|---|---|---|---|---|---|---|---|"
          "---|---|---|")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1, help="scrap decodes (the tests' one)")
    parser.add_argument("--page-workers", type=int, default=8, help="page decodes (the suite's c2 record's eight)")
    args = parser.parse_args(argv)
    from holo.receiver.tests import _h3_sims, _h3_sims_cmy as sims

    pages = []
    page_dir = args.out / "pages"
    for plant in ("Z", "A", "B"):
        record = args.out / "runs" / f"page-{plant}" / "record.json"
        if record.is_file():
            pages.append(json.loads(record.read_text()))
            print(page_text(pages[-1]), flush=True)
            continue
        d_m, d_y = sims.CMY_C2_CROP_PLANTS_DOTS[plant]
        offsets = ((0, 0), (round(d_m * sims.CMY_C2_PX_PER_DOT), 0), (round(d_y * sims.CMY_C2_PX_PER_DOT), 0))
        tiff = page_dir / f"sim-cmy-c2-page-{plant}-2400dpi.tiff"
        page_dir.mkdir(parents=True, exist_ok=True)
        _spec, coverage = sims._emit_cmy_c2(page_dir)
        import tifffile

        tifffile.imwrite(tiff, sims._render_c2(coverage, sims.cmy_c2_channel(offsets)))
        del coverage
        truth = generator_user_bits(sims, page_dir / sims.CMY_C2_EMIT_DIRNAME)
        record.parent.mkdir(parents=True, exist_ok=True)
        eng, events, wall, payload = decode(tiff, record.parent / "run", sims, args.page_workers)
        pages.append(measure_page(sims, plant, eng, events, wall, payload, truth))
        record.write_text(json.dumps(pages[-1], indent=1))
        tiff.unlink()
        print(page_text(pages[-1]), flush=True)

    scraps = all_scraps(sims)
    staging = args.out / "scraps"
    if not all((staging / sims.cmy_c2_crop_tiff_name(*s)).is_file() for s in scraps):
        sims.make_cmy_c2_crops(staging, scraps)
    truth = generator_user_bits(sims, staging / sims.CMY_C2_EMIT_DIRNAME)
    rows = []
    for scrap in scraps:
        name = sims.cmy_c2_crop_name(*scrap)
        record = args.out / "runs" / name / "record.json"
        if record.is_file():
            rows.append(json.loads(record.read_text()))
        else:
            record.parent.mkdir(parents=True, exist_ok=True)
            eng, events, wall, _payload = decode(staging / sims.cmy_c2_crop_tiff_name(*scrap), record.parent / "run",
                                                 sims, args.workers)
            rows.append(measure_scrap(sims, scrap, eng, events, wall, truth))
            record.write_text(json.dumps(rows[-1], indent=1))
        print(row_text(rows[-1]), flush=True)
    meta = {"format": sims.CMY_C2_FORMAT_REF, "workers": args.workers, "page_workers": args.page_workers,
            "sims_source": sims.SOURCE_DIGEST, "base_sims_source": _h3_sims.SOURCE_DIGEST,
            "payload_sha256": sims.CMY_C2_PAYLOAD_SHA256}
    (args.out / "grid.json").write_text(json.dumps({"meta": meta, "pages": pages, "scraps": rows}, indent=1))
    print(PAGE_HEADER)
    for page in pages:
        print(page_text(page))
    print(HEADER)
    for row in rows:
        print(row_text(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
