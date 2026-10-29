"""Shared, process-memoised test inputs, all built at test time.

The owner's ruling of 2026-10-09: no tracked test reads scratch/,
scans/ or a build dir as input, and nothing is checked in.  Two tiers.
TIER F needs no pixels and runs in the fast lane; TIER S is the
receiver's colour sim decoded once into the receiver lane's own
content-keyed cache and read back as a run dir, behind
`HOLO_RUN_SLOW_TESTS=1`.  The sheet-I numbers the tests these replaced
were pinned to are dated records in analyzer/PAGE-FIELD-PLAN.md (A1b);
sheet J's are experiments/035-sheet-j-confetti.md's.

A plain memo rather than a module-scoped fixture, so a test process
builds each input once whichever module asks first.  Underscore-prefixed
so pytest never collects it as a test module, and NOT a `conftest.py` so
a parallel wave can add one without a collision.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import tempfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_MEMO: dict[str, Any] = {}

#: The fossil identity sheet I was printed as (manifest `spec_id`).
I_FORMAT_REF = "L:c2-cmy8-r0700-p120-x1@3392x2368"


# ----------------------------------- TIER F: generated at test time (2026-10-09)
# The owner's ruling of 2026-10-09: no tracked test reads scratch/ as
# input, and nothing is checked in.  These three are built from a
# deterministic payload in a per-process temp dir, in about a second
# each, and need no pixels: the emitted volume (F1), sheet I's printed
# identity with a payload of sheet I's length (F2), a `RunInputs`
# carrying a certificate set and nothing a run dir would add (F3), and
# F1's identity emitted over two pages (F4).

#: The receiver's clean colour sim identity, length and source fraction
#: (src/holo/receiver/tests/_h3_sims.py, COLOR_*); the payload tag is ours.
F1_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
F1_PAYLOAD_BYTES = 20000
F1_SOURCE_FRACTION = 0.35

#: F4's payload: twice F1's, past one 10x10 page at F1's source fraction.
F4_PAYLOAD_BYTES = 2 * F1_PAYLOAD_BYTES

#: Sheet I's payload length: K, the symbol count and the redundancy are
#: functions of the identity and the length alone, so every W7 pin
#: (5,277 / 5,883 / 606) carries to a generated payload of this length.
F2_PAYLOAD_BYTES = 1798761


@dataclass(frozen=True)
class Emitted:
    """One test-time volume: the identity, its holo3 row and the truth."""

    format_ref: str
    row: Any
    emit_dir: Path | None
    payload_path: Path
    truth: Any


def det_bytes(tag: bytes, n_bytes: int) -> bytes:
    """A sha256 chain — the receiver sims' payload rule."""
    out = b""
    chain = tag
    while len(out) < n_bytes:
        chain = hashlib.sha256(chain).digest()
        out += chain
    return out[:n_bytes]


def _work_dir() -> Path:
    hit = _MEMO.get("work_dir")
    if hit is None:
        hit = Path(tempfile.mkdtemp(prefix="analyzer-tier-f-"))
        atexit.register(shutil.rmtree, hit, True)
        _MEMO["work_dir"] = hit
    return hit


def _emit(name: str, tag: bytes, n_bytes: int, n_pages: int) -> Emitted:
    from holo.format.resolve import resolve_format_ref as holo1_resolve
    from holo.gen.emit import emit_volume
    from holo.receiver.format.identity import resolve_format_ref

    from analyzer import truth as truth_mod
    root = _work_dir()
    payload = det_bytes(tag, n_bytes)
    payload_path = root / f"{name}-payload.bin"
    payload_path.write_bytes(payload)
    emit_dir = root / f"{name}-emit"
    emit_volume(holo1_resolve(F1_FORMAT_REF), payload,
                F1_SOURCE_FRACTION, emit_dir)
    row = resolve_format_ref(F1_FORMAT_REF)
    gt = truth_mod.load_truth(emit_dir, payload_path, row, n_pages,
                              format_ref=F1_FORMAT_REF)
    return Emitted(F1_FORMAT_REF, row, emit_dir, payload_path, gt)


def emitted_volume() -> Emitted:
    """F1: `emit_volume` at 10x10 colour — manifest, GT field, payload.

    The truth is loaded WITH the generation dir, so it carries the
    emitted per-cell field and its payload is sha-gated by the manifest.
    """
    hit = _MEMO.get("emitted_volume")
    if hit is None:
        hit = _emit("f1", b"analyzer-tier-f1", F1_PAYLOAD_BYTES, 1)
        _MEMO["emitted_volume"] = hit
    return hit


def emitted_two_pages() -> Emitted:
    """F4: F1's identity with a payload too long for one page."""
    hit = _MEMO.get("emitted_two_pages")
    if hit is None:
        hit = _emit("f4", b"analyzer-tier-f4", F4_PAYLOAD_BYTES, 2)
        _MEMO["emitted_two_pages"] = hit
    return hit


def fossil_i() -> Emitted:
    """F2: sheet I's fossil identity, a generated payload, no gen dir.

    `analyzer.truth` re-encodes the payload through holo1's generation
    arithmetic, an INDEPENDENT implementation of the fountain from the
    holo3 one the close and the consistency check call — what makes
    these fixtures a test rather than a tautology.
    """
    hit = _MEMO.get("fossil_i")
    if hit is None:
        from holo.receiver.format.identity import resolve_format_ref

        from analyzer import truth as truth_mod
        payload_path = _work_dir() / "f2-payload.bin"
        payload_path.write_bytes(
            det_bytes(b"analyzer-tier-f2", F2_PAYLOAD_BYTES))
        row = resolve_format_ref(I_FORMAT_REF)
        gt = truth_mod.load_truth(None, payload_path, row, 1,
                                  format_ref=I_FORMAT_REF)
        hit = Emitted(I_FORMAT_REF, row, None, payload_path, gt)
        _MEMO["fossil_i"] = hit
    return hit


def fossil_i_user_bits() -> dict:
    """F2's whole certificate set.  Shared and read-only: copy to poison."""
    return fossil_i().truth.user_bits


def emitted_inputs(volume: Emitted, user_bits: dict | None = None) -> Any:
    """F3: a `RunInputs` whose certificates are `user_bits` (default all).

    It carries the row, the site geometry, the certificates and what the
    receiver's own metadata solve makes of them — K for both `k_total`
    and the reported rank, as a run that closed reports it — and nothing
    a run dir would add: no captures, lanes, placements or fields.
    """
    from analyzer import close as close_mod
    from analyzer import frame
    from analyzer.inputs import _metadata_state
    from analyzer.types import RunInputs

    row = volume.row
    bits = volume.truth.user_bits if user_bits is None else user_bits
    certificates = {key: close_mod.as_certificate(key, bits[key],
                                                  source="emitted")
                    for key in sorted(bits)}
    word, version, state, k_total = _metadata_state(
        certificates.values(), row)
    return RunInputs(
        run_dir=volume.emit_dir or volume.payload_path.parent,
        format_ref=volume.format_ref, row=row,
        geometry=frame.geometry_of(row), pitch_in=row.pitch_in,
        tiles_yx=tuple(row.tiles_yx), cells_yx=tuple(row.cells_yx),
        live_pages=(0,), declared_pages=(0,), captures=(), lanes=(),
        lane_policy="all", rung_ppc=None, certificates=certificates,
        plane_fields={}, pooled_ctx={}, lattice_seeds=(), windows={},
        surveys={}, metadata_word=word, metadata_version=version,
        metadata_state=state, k_total=k_total, rank_report=k_total,
        close_report={}, provenance={})


def fossil_i_inputs() -> Any:
    """F3 over F2's whole certificate set.  Shared and read-only."""
    hit = _MEMO.get("fossil_i_inputs")
    if hit is None:
        hit = emitted_inputs(fossil_i())
        _MEMO["fossil_i_inputs"] = hit
    return hit


# ----------------------------- TIER S: the receiver's colour sim (2026-10-09)
# S0 is the receiver lane's frozen displaced colour page — the clean
# 10x10 cmy8 emit with Y two dots out of register along a one-cycle
# sinusoid down the page — and S1 its `--complete` decode, read back as
# a run dir.  S1 is the SAME decode, label and argv as the receiver's
# `decode_color_shifted`, so both lanes share one content-keyed cache
# entry (`_h3_fixture_build.cached_decode`); it decodes cold once per
# production tree, and a warm read is a few seconds.  S2 are run dirs
# derived from S1 in a per-process temp dir — symlinks to S1's files
# with one file rewritten — and are never cached.  Nothing here writes
# into the cache dir: `load_run` maps the rasters read-only.

SLOW_ENV = "HOLO_RUN_SLOW_TESTS"

needs_sim = pytest.mark.skipif(
    os.environ.get(SLOW_ENV, "") in ("", "0"),
    reason=f"decodes the receiver's displaced colour sim into a run dir "
           f"(cold once per production tree): set {SLOW_ENV}=1")

SIM_LABEL = "color-shifted"
SIM_WORKERS = 8
SIM_ARGV = ("--complete", "--max-pages", "1")

#: The RESIDUE derivative's withheld certificates: the page corner (0,
#: 0, C) with one of its neighbours, so the corner keeps two of three;
#: Y at the displacement's two extremes (ty 2 and 7 on a ten-tile page)
#: with (2, 5, Y)'s eight neighbours all left certified; C, M and Y
#: elsewhere.  Explicit rather than drawn, so the residue IS this set.
RESIDUE_WITHHELD: tuple[tuple[int, int, int, str], ...] = (
    (0, 0, 0, "C"), (0, 0, 1, "C"), (0, 5, 5, "C"), (0, 9, 8, "C"),
    (0, 3, 8, "M"), (0, 6, 2, "M"), (0, 8, 5, "M"),
    (0, 2, 1, "Y"), (0, 2, 5, "Y"), (0, 4, 9, "Y"), (0, 7, 3, "Y"),
    (0, 7, 7, "Y"))

#: The FRAGMENT derivative keeps the placements whose page cells stay
#: left of this tile column, and the certificates on tiles they cover.
FRAGMENT_TX = 5

#: The DECLARED derivative's report names this many pages; one is placed.
DECLARED_PAGES = 100


def _require_sim_producer() -> None:
    from holo.receiver.tests import _h3_sims
    reason = _h3_sims.producer_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)


def sim_capture() -> Any:
    """S0: the displaced colour page, materialised (or served) by the
    receiver lane's own render cache, sha-verified against its freeze."""
    hit = _MEMO.get("sim_capture")
    if hit is None:
        _require_sim_producer()
        from holo.receiver.tests import _h3_sims_field
        from holo.receiver.tests._h3_fixture_build import _materialise
        outdir = _materialise(SIM_LABEL, _h3_sims_field.make_color_shifted,
                              _h3_sims_field.EXPECTED_COLOR_SHIFTED,
                              _work_dir() / "sims")
        hit = _h3_sims_field.capture_color_shifted(outdir)
        _MEMO["sim_capture"] = hit
    return hit


def sim_record() -> Any:
    """S1's decode record: the cached receiver decode of S0."""
    hit = _MEMO.get("sim_record")
    if hit is None:
        from holo.receiver.tests._h3_fixture_build import cached_decode
        # keep_planes: `inputs.load_run` opens the lane rasters out of
        # the run dir, and the cache publishes intake's plane scratch
        # only for a record that asks (2026-10-18, review D4).
        hit = cached_decode(SIM_LABEL, (sim_capture(),),
                            _work_dir() / "decodes", workers=SIM_WORKERS,
                            extra_argv=SIM_ARGV, keep_planes=True)
        if hit.status != "verified":
            raise RuntimeError(
                f"the {SIM_LABEL} sim decode did not verify (exit "
                f"{hit.exit_code}); every S-tier test stands on a closed "
                f"run:\n{hit.stderr[-2000:]}")
        _MEMO["sim_record"] = hit
    return hit


def sim_run_dir() -> Path:
    """S1: the run dir itself — report, events, argv, facts, rasters."""
    return Path(sim_record().run_dir)


def sim_run() -> Any:
    """S1 through `load_run`.  Shared and read-only."""
    hit = _MEMO.get("sim_run")
    if hit is None:
        from analyzer import inputs
        hit = inputs.load_run(sim_run_dir())
        _MEMO["sim_run"] = hit
    return hit


def sim_truth() -> Any:
    """S0's emit dir and payload as the scorer's truth for S1's row."""
    hit = _MEMO.get("sim_truth")
    if hit is None:
        from analyzer import truth
        capture = sim_capture()
        run = sim_run()
        hit = truth.load_truth(capture.emit_dir, capture.payload, run.row,
                               max(run.live_pages) + 1,
                               format_ref=run.format_ref)
        _MEMO["sim_truth"] = hit
    return hit


def _derive(name: str, *, facts: Callable[[tuple], tuple] | None = None,
            report: Callable[[dict], dict] | None = None,
            rasters: Callable[[str, Any], Any] | None = None) -> Path:
    """S2: S1's run dir as symlinks, with the snapshot, the report and/or
    every lane raster rewritten.  Built once per process; the cache entry
    is never written."""
    import numpy as np

    from holo.receiver import snapshot
    base = sim_run_dir()
    target = _work_dir() / "derived" / name
    if target.exists():
        return target
    staging = target.with_name(f".{name}")
    staging.mkdir(parents=True)
    rewritten = {snapshot.NAME if facts else None,
                 "report.json" if report else None}
    for path in sorted(base.iterdir()):
        if path.name in rewritten:
            continue
        if rasters is None or not path.is_dir():
            (staging / path.name).symlink_to(path)
            continue
        (staging / path.name).mkdir()
        for item in sorted(path.iterdir()):
            if item.suffix == ".npy":
                np.save(staging / path.name / item.name,
                        rasters(item.name, np.load(item)))
            else:
                (staging / path.name / item.name).symlink_to(item)
    if facts is not None:
        snapshot.write(staging / snapshot.NAME,
                       facts(snapshot.read(base / snapshot.NAME)))
    if report is not None:
        edited = report(json.loads((base / "report.json").read_text("utf-8")))
        (staging / "report.json").write_text(json.dumps(edited), "utf-8")
    staging.rename(target)
    return target


def _is_certificate(fact: object) -> bool:
    return type(fact).__name__ == "Certificate"


def _fact_key(fact: Any) -> tuple[int, int, int, str]:
    return (int(fact.page), int(fact.ty), int(fact.tx), str(fact.stream_id))


#: The NOISY derivatives' channel: every lane raster of S1 plus seeded
#: Gaussian noise of this standard deviation in grey levels, clipped to
#: uint8, one draw per raster file — on the 0/255 sim page a pixel
#: flips with probability ~0.37.  Measured 2026-10-09 over the twelve
#: `RESIDUE_WITHHELD` keys (frame null certified / positive control
#: recovered, default battery): grey 0 9/12, 60 9/12, 150 8/12, 250
#: 7/12, 320 5/12, 400 0/12 and 11/12; a fixed point over the residue
#: certifies 12 at 400 and 0 at 440, 470 and 500.  400 is the one level
#: where the frame null has no read left and the true frame still reads.
NOISE_SIGMA_GREY = 400.0
NOISE_SEED = 20261009

#: The DAMAGED residue: per-tile noise over the NOISY channel, so its
#: residue does not all certify in generation 0.  Tile (ty, tx) -> grey.
#: Measured 2026-10-09 at the fixed point of test_analyzer_fixedpoint:
#: the corner (0, 0) certifies in generation 0 at 410, at 413-440 it is
#: re-attacked in generation 1 once its neighbour (0, 0, 1, C) certifies
#: and stays open; (4, 9) at 500 stays open from the start.
DAMAGE_SIGMA_GREY: dict[tuple[int, int], float] = {
    (0, 0): 420.0, (4, 9): 500.0}


def add_noise(name: str, raster: Any, sigma_grey: Any) -> Any:
    """`raster` plus N(0, `sigma_grey`) — a scalar or a per-pixel map —
    seeded by NOISE_SEED and the file name (a crc, not `hash`, so the
    draw holds across processes)."""
    import numpy as np
    rng = np.random.default_rng([NOISE_SEED, zlib.crc32(name.encode())])
    noisy = raster + rng.standard_normal(raster.shape) * sigma_grey
    return np.clip(np.rint(noisy), 0, 255).astype(np.uint8)


def _without_withheld(facts: tuple) -> tuple:
    withheld = set(RESIDUE_WITHHELD)
    return tuple(fact for fact in facts
                 if not (_is_certificate(fact)
                         and _fact_key(fact) in withheld))


def _tile_boxes_px(tiles: Any) -> dict[int, list[tuple[Any, float]]]:
    """Level index -> [(the tile's pixel box as slices, grey)], from S1's
    own placements: every pixel within half a cell of a tile cell."""
    import numpy as np

    from analyzer import frame, sample
    run = sim_run()
    out: dict[int, list[tuple[Any, float]]] = {}
    for lane in run.lanes:
        for (ty, tx), sigma_grey in sorted(tiles.items()):
            fp = frame.tile_footprint(run.row, 0, ty, tx, 0,
                                      geometry=run.geometry)
            lfp = sample.lane_footprint(lane, fp)
            if lfp is None:
                continue                # this level never placed the tile
            points = lfp.points_yx[lfp.observed]
            half = 0.5 * float(lane.pitch_px_level)
            low = np.floor(points.min(axis=0) - half).astype(int)
            high = np.ceil(points.max(axis=0) + half).astype(int) + 1
            box = (slice(max(0, int(low[0])), int(high[0])),
                   slice(max(0, int(low[1])), int(high[1])))
            out.setdefault(lane.level_index, []).append((box, sigma_grey))
    return out


def _noised(sigma_grey: float, tiles: Any = None) -> Callable[[str, Any],
                                                              Any]:
    import numpy as np
    boxes = _tile_boxes_px(tiles) if tiles else {}

    def apply(name: str, raster: Any) -> Any:
        level_index = int(name[1:3])
        sigma_map = np.full(raster.shape, sigma_grey, np.float64)
        for box, tile_sigma in boxes.get(level_index, ()):
            sigma_map[box] = tile_sigma
        return add_noise(name, raster, sigma_map)
    return apply


def noisy_run_dir(sigma_grey: float = NOISE_SIGMA_GREY) -> Path:
    """S2(d): S1 with every lane raster noised, every certificate kept."""
    return _derive(f"noisy-{sigma_grey:g}", rasters=_noised(sigma_grey))


def damaged_residue_run_dir(
        damage: dict[tuple[int, int], float] | None = None) -> Path:
    """S2(e): the NOISY channel, `damage`'s tiles noised harder, and
    RESIDUE's certificates withheld."""
    damage = DAMAGE_SIGMA_GREY if damage is None else damage
    tag = "-".join(f"{ty}.{tx}.{grey:g}"
                   for (ty, tx), grey in sorted(damage.items()))
    return _derive(f"damaged-residue-{NOISE_SIGMA_GREY:g}-{tag}",
                   facts=_without_withheld,
                   rasters=_noised(NOISE_SIGMA_GREY, damage))


def residue_run_dir() -> Path:
    """S2(a): S1 with `RESIDUE_WITHHELD`'s certificates taken out.

    Its events still name those keys as minted: `run_mint_keys` and the
    positive control read S1, not this."""
    return _derive("residue", facts=_without_withheld)


def residue_run() -> Any:
    hit = _MEMO.get("residue_run")
    if hit is None:
        from analyzer import inputs
        hit = inputs.load_run(residue_run_dir())
        _MEMO["residue_run"] = hit
    return hit


def residue_census() -> Any:
    """The blind census of S2(a): every tile covered, the residue the
    withheld set."""
    hit = _MEMO.get("residue_census")
    if hit is None:
        from analyzer import residue
        hit = residue.census(residue_run())
        _MEMO["residue_census"] = hit
    return hit


def sim_census() -> Any:
    """The blind census of S1, whose every tile-stream is certified."""
    hit = _MEMO.get("sim_census")
    if hit is None:
        from analyzer import residue
        hit = residue.census(sim_run())
        _MEMO["sim_census"] = hit
    return hit


def fragment_run() -> Any:
    """S2(b): only the placements whose page cells stay left of tile
    column `FRAGMENT_TX`, and only the certificates on tiles they cover
    — a scrap of the page, sheet J's uncovered path."""
    hit = _MEMO.get("fragment_run")
    if hit is None:
        from analyzer import inputs
        base = sim_run()
        tile_cells = 64

        def keep(placement: Any) -> bool:
            cells = inputs._placement_page_cells(base, placement)
            return bool(cells.size) and int(cells[:, 1].max()) < (
                FRAGMENT_TX * tile_cells)

        def cut(facts: tuple) -> tuple:
            placements = [fact for fact in facts
                          if type(fact).__name__ == "Placement"]
            kept = {id(fact) for fact in placements if keep(fact)}
            covered: set[tuple[int, int, int]] = set()
            for fact in placements:
                if id(fact) not in kept:
                    continue
                cells = inputs._placement_page_cells(base, fact)
                for ty, tx in {(int(y) // tile_cells, int(x) // tile_cells)
                               for y, x in cells}:
                    covered.add((int(fact.page), ty, tx))
            return tuple(
                fact for fact in facts
                if not (type(fact).__name__ == "Placement"
                        and id(fact) not in kept)
                and not (_is_certificate(fact)
                         and _fact_key(fact)[:3] not in covered))

        hit = inputs.load_run(_derive("fragment", facts=cut))
        _MEMO["fragment_run"] = hit
    return hit


def declared_run_dir() -> Path:
    """S2(c): S1 whose report declares `DECLARED_PAGES` pages."""
    def widen(report: dict) -> dict:
        return {**report, "pages": list(range(DECLARED_PAGES))}
    return _derive("declared", report=widen)


def unplaced_run_dir() -> Path:
    """S1 with every `Placement` taken out of the snapshot."""
    return _derive("unplaced", facts=lambda facts: tuple(
        fact for fact in facts if type(fact).__name__ != "Placement"))
