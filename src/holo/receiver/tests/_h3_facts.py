from __future__ import annotations

import dataclasses
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np

from holo.receiver import data, engine
from holo.receiver.data import WindowId
from holo.receiver.format import tile_codec
from holo.receiver.plugins import calibrate, color_model, place_pass
from holo.receiver.plugins import place_sched
from holo.receiver.plugins import color_region_head, refine

FORMAT_REF = "c3-k-r0550@7x7"
CAPTURE_ID = "cafebabe" * 8
EXTENT = (0, 0, 64, 64)
WINDOW_ID = (CAPTURE_ID, 0, 0, EXTENT)
PROBE_ORDINAL = 9999

STORE_CELLS = (
    "_captures", "_levels", "_surveys", "_frames", "_plan_total", "_windows",
    "_ordinal_wid", "_place_stages", "_placements", "_page_cells",
    "_pose_gen", "_lattice_seeds", "_live_pages", "_lanes_on_page",
    "_region_pitch", "_region_sampling", "_evidence", "_region_ctx",
    "_color_rows", "_color_pops", "_pop_lanes", "_pooled_ctx",
    "_tile_cover_k", "_tile_cover_color", "_window_cover",
    "_color_row_cover", "_color_lane_assembled", "_color_lane_head",
    "_color_lane_head_fits",
    "_certificates", "_equations", "_attempt_outcomes",
    "_attempt_latest", "_attempt_ever_failed_footing", "_tile_lane_generation",
    "_union_generation",
    "_plane_fields", "_field_observations", "_evidence_revision")


def new_engine(workers: int = 1) -> engine._Engine:
    request = data.DecodeRequest(
        scans=(Path("scan.tiff"),), dpis=(1200.0,), format_ref=FORMAT_REF,
        max_pages=1, workers=workers, complete=False, no_close=False,
        diag_port=None, run_dir=Path(tempfile.mkdtemp(prefix="h3-facts-")))
    return engine._Engine(request, [])


def tile_cells(size: int = 64) -> np.ndarray:
    grid = np.stack(np.meshgrid(np.arange(size), np.arange(size),
                                indexing="ij"), axis=-1)
    return grid.reshape(-1, 2).astype(np.int64)


def capture() -> data.Capture:
    level = data.Level(index=0, ppc=Fraction(4), scale=Fraction(1),
                       shape_px=(4096, 4096), label="l0")
    return data.Capture(
        capture_id=CAPTURE_ID, path=Path("scan.tiff"), dpi=1200.0,
        shape_px=(4096, 4096), channels=1, platen_backing=0.9,
        levels=(level,), plane_dir=Path("planes"))


def survey() -> data.CaptureSurvey:
    region = data.Region(
        capture_id=CAPTURE_ID, region_index=0, origin_yx=(0, 0), step_px=32,
        cells=np.ones((16, 16), bool), extent_px=(2048, 2048),
        area_mm2=100.0, median_tensor_score=1.0)
    return data.CaptureSurvey(capture_id=CAPTURE_ID, regions=(region,),
                              pitch_class=Fraction(1, 300), pitch_px=4.0)


def window(wid: tuple = WINDOW_ID,
           ordinal: int = PROBE_ORDINAL) -> data.Window:
    return data.Window(
        window_id=wid, capture_id=wid[0], level_index=wid[1],
        region_index=wid[2], extent_cells=wid[3],
        supported_cells=64 * 64, depth=0, lane_depth=0, ordinal=ordinal)


def placement(wid: tuple = WINDOW_ID, route: str = "word", page: int = 0,
              origin_yx: tuple[float, float] = (0.0, 0.0),
              pitch_px: float = 4.0,
              quality: float = 0.0) -> data.Placement:
    return data.Placement(
        window_id=wid, capture_id=wid[0], level_index=wid[1],
        region_index=wid[2], patch_ordinal=0, page=page, rot_k=0,
        page_origin_yx=(0, 0),
        native_affine=(4.0, 0.0, origin_yx[0], 0.0, 4.0, origin_yx[1]),
        pitch_px=pitch_px, route=route,
        # the stored width (data.Placement): every fixture placement
        # carries what `place_pass.local_cells_of` mints, so the suite reads
        # the poses production writes
        local_cells_yx=tile_cells().astype(np.int16),
        quality=quality)


def evidence(wid: tuple = WINDOW_ID, loss: float | None = 0.1,
             ctx_adopted: bool = False, printed: float = 1.0,
             score: float = 0.0, accepted: bool = True,
             cells: np.ndarray | None = None) -> data.WindowEvidence:
    page_cells = tile_cells() if cells is None else np.asarray(cells,
                                                               np.int64)
    n = page_cells.shape[0]
    return data.WindowEvidence(
        window_id=wid, capture_id=wid[0], level_index=wid[1],
        region_index=wid[2], patch_ordinal=0, page=0,
        page_cells_yx=page_cells,
        scores=np.full(n, score, np.float32),
        reference_values=np.zeros(n, np.int8),
        knots=np.zeros(2, np.float32), probs=np.zeros(2, np.float32),
        n_search=0, marginal_llr=np.zeros(n, np.float32),
        printed_llr=np.full(n, printed, np.float32), accepted=accepted,
        refusal_reason="", heldout_logloss=loss, ctx_adopted=ctx_adopted)


def place_outcome(outcome: str = "accepted",
                  wid: tuple = WINDOW_ID) -> place_sched.PlaceOutcome:
    result = place_pass.WindowPassResult(
        outcome=outcome, route="word", placement=None, lattice_seed=None,
        tried_now=("probe",), stage_spent=None, wide_spent=False,
        cold_spent=None, hypotheses=1, events=())
    return place_sched.PlaceOutcome(window_id=wid, result=result)


def lattice_seed(support_cells: int = 10,
                 window_ordinal: int = 0) -> data.LatticeSeed:
    return data.LatticeSeed(
        capture_id=CAPTURE_ID, level_index=0, region_index=0,
        rows=np.zeros((2, 2), np.float64), support_cells=support_cells,
        window_ordinal=window_ordinal)


def region_ctx(adopted: bool = True, offset: float = 0.0,
               validation_logloss: float | None = None) -> data.RegionCtx:
    return data.RegionCtx(
        capture_id=CAPTURE_ID, level_index=0, region_index=0,
        offsets=np.full(4, offset, np.float32), adopted=adopted,
        reason="probe", validation_logloss=validation_logloss)


def ctx_outcome(adopted: bool = True, offset: float = 0.0,
                validation_logloss: float | None = None
                ) -> calibrate.CtxOutcome:
    return calibrate.CtxOutcome(
        region_key=(CAPTURE_ID, 0, 0),
        ctx=region_ctx(adopted, offset, validation_logloss))


def refine_outcome(adopted: bool = True,
                   shift: float = 8.0) -> refine.RefineOutcome:
    revision = refine.Revision(
        adopted=adopted, reason="probe",
        affine=(4.0, 0.0, shift, 0.0, 4.0, shift))
    return refine.RefineOutcome(window_id=WINDOW_ID, revision=revision)


def color_row(loss: float = 0.2) -> data.ColorEvidenceRow:
    cells = tile_cells()
    return data.ColorEvidenceRow(
        capture_id=CAPTURE_ID, level_index=0, patch_ordinal=0, page=0,
        page_cells_yx=cells,
        values=np.zeros((cells.shape[0], 3), np.float32),
        heldout_logloss=loss)


def lane_head() -> color_region_head.LaneHead:
    rng = np.random.default_rng(20260830)
    states = np.repeat(np.arange(8), 8)
    bits = tile_codec.states_to_planes(states.astype(np.uint8))
    features = (0.9 - 0.6 * bits.astype(np.float64)
                + rng.normal(0.0, 0.02, bits.shape))
    fit = color_region_head.DetectorFit(
        model=color_model.fit_qda(features, states, 8), detector=None,
        heldout_loss=0.2, word_heldout_loss=0.2, dust_heldout_loss=0.2,
        heldout_scores=None, heldout_states=None, heldout_keys=None)
    return color_region_head.LaneHead(fit, 6.0, 255.0, False, 0)


def color_lane_fit(head_fitted: bool = True,
                   assembled: tuple[int, ...] = (0,),
                   ) -> color_region_head.ColorLaneFit:
    return color_region_head.ColorLaneFit(
        capture_id=CAPTURE_ID, level_index=0, page=0,
        assembled=assembled, head_fitted=head_fitted,
        head=lane_head() if head_fitted else None)


def color_ctx_population(capture_id: str = CAPTURE_ID, page: int = 0,
                         rung: str = "4", n_rows: int = 240,
                         level_index: int = 0,
                         offset: float = 0.0) -> data.ColorCtxPopulation:
    index = np.arange(n_rows, dtype=np.int64)
    keys = np.stack((index // 16, index % 16), axis=-1)
    scores = (np.outer(index % 8, np.ones(8)) * 0.01
              + np.arange(8) * 0.1 + offset).astype(np.float32)
    return data.ColorCtxPopulation(
        capture_id=capture_id, level_index=level_index, page=page, rung=rung,
        keys_pyx=keys, scores=scores,
        states=(index % 8).astype(np.int8),
        kinds=(index % 2).astype(np.int8),
        bins=np.stack((index % 9, (index + 1) % 9, (index + 2) % 9),
                      axis=-1).astype(np.int8),
        search=(index % 2 == 0))


def pooled_color_ctx(adopted: bool = True, page: int = 0, rung: str = "4",
                     n_lanes: int = 2, n_rows: int = 480,
                     offset: float = 0.25,
                     validation_logloss: float | None = 0.5,
                     ) -> data.PooledColorCtx:
    return data.PooledColorCtx(
        page=page, rung=rung,
        offsets=np.full((8, 3, 9), offset, np.float64),
        applied=np.ones((8, 3), np.bool_), adopted=adopted, reason="probe",
        n_lanes=n_lanes, n_rows=n_rows,
        validation_logloss=validation_logloss)


def plane_field(plane: int = 2, page: int = 0, ordinal: int = 1,
                delta_dots: float = 0.4, uncertainty_dots: float = 0.1,
                tiles_yx: tuple[int, int] = (7, 7)) -> data.PlaneField:
    delta = np.zeros(tiles_yx + (2,), np.float64)
    delta[..., 0] = delta_dots
    return data.PlaneField(
        page=page, plane=plane, delta_dots_xy=delta,
        support=np.ones(tiles_yx, np.float64),
        uncertainty_dots=np.full(tiles_yx, uncertainty_dots, np.float64),
        n_observations=64, n_captures=1, ordinal=ordinal)


def field_observations(capture_id: str = CAPTURE_ID, page: int = 0,
                       revision: int = 8,
                       generation: int = 1, delta_dots: float = 0.4,
                       codes: tuple[int, ...] = (0, 1),
                       plane: int = 2,
                       wid: WindowId = WINDOW_ID,
                       ) -> data.FieldObservations:
    n = len(codes)
    delta = np.zeros((n, 2), np.float64)
    delta[:, 0] = delta_dots
    return data.FieldObservations(
        capture_id=capture_id, page=page,
        tile_code=np.asarray(codes, np.int64),
        plane=np.full(n, plane, np.int64), delta_dots_xy=delta,
        measured_xy=np.ones((n, 2), bool),
        weight=np.ones(n, np.float64),
        source=np.full(n, 1, np.int64),
        window=np.zeros(n, np.int64), window_ids=(wid,),
        window_generation=np.asarray([generation], np.int64),
        revision=revision)


def evidence_revision(capture_id: str = CAPTURE_ID, page: int = 1,
                      revision: int = 3) -> data.EvidenceRevision:
    return data.EvidenceRevision(capture_id=capture_id, page=page,
                                 revision=revision)


def certificate(page: int = 0, ty: int = 0, tx: int = 0,
                bit: int = 0) -> data.Certificate:
    bits = np.zeros(8, np.uint8)
    bits[0] = np.uint8(bit)
    return data.Certificate(page=page, ty=ty, tx=tx, stream_id="main",
                            user_bits=bits, source="tiles/scan")


def attempt(outcome: str = "attempted_failed") -> data.AttemptFact:
    return data.AttemptFact(
        page=0, ty=0, tx=0, stream_id="main", stage="scan", outcome=outcome,
        n_informative=100, n_iters=60, syndrome_ok=False, crc_ok=False,
        components=((CAPTURE_ID, 0),))


BUILD = {
    "Capture": capture,
    "CaptureSurvey": survey,
    "Window": window,
    "Placement": lambda: placement(page=1),
    "PlaceOutcome": place_outcome,
    "LatticeSeed": lattice_seed,
    "WindowEvidence": evidence,
    "CtxOutcome": ctx_outcome,
    "RefineOutcome": refine_outcome,
    "ColorEvidenceRow": color_row,
    "ColorLaneFit": color_lane_fit,
    "ColorCtxPopulation": color_ctx_population,
    "PooledColorCtx": pooled_color_ctx,
    "Certificate": lambda: certificate(page=1),
    "AttemptFact": attempt,
    "PlaneField": plane_field,
    "FieldObservations": field_observations,
    "EvidenceRevision": evidence_revision,
}

PREREQUISITES = {
    "Capture": (),
    "CaptureSurvey": ("Capture",),
    "Window": ("Capture",),
    "Placement": ("Capture", "Window"),
    "PlaceOutcome": ("Capture", "Window"),
    "LatticeSeed": (),
    "WindowEvidence": ("Capture", "Window"),
    # the ctx row's write is the DECISION plus the catch-up over the
    # region's standing rows (2026-10-03): a fixture with no row there
    # would measure a decision that corrects nothing
    "CtxOutcome": ("Capture", "Window", "WindowEvidence"),
    "RefineOutcome": ("Capture", "Window", "Placement"),
    "ColorEvidenceRow": ("Capture", "Window"),
    "ColorLaneFit": (),
    "ColorCtxPopulation": (),
    "PooledColorCtx": (),
    # the certificate is seeded with a window PLACED on its own page:
    # a certificate advances the evidence revision of every capture
    # standing on that face (I12), and a fixture with no window there
    # would measure the write map of a page nobody is reading
    "Certificate": ("Capture", "Window", "Placement"),
    # an attempt reads a DECLARED lane: the fold keys its failure by
    # the lane's footing (2026-10-03), which is the capture's level
    "AttemptFact": ("Capture",),
    "PlaneField": (),
    "FieldObservations": (),
    "EvidenceRevision": (),
}


def _signature(value: object, keep: list) -> object:
    keep.append(value)
    if isinstance(value, dict):
        return tuple(sorted((repr(key), _signature(item, keep))
                            for key, item in value.items()))
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(repr(item) for item in value))
    if isinstance(value, tuple):
        return tuple(_signature(item, keep) for item in value)
    if isinstance(value, np.ndarray):
        return (value.shape, str(value.dtype), value.tobytes())
    if (dataclasses.is_dataclass(value)
            and not value.__dataclass_params__.frozen):
        return repr(value)
    return id(value)


def store_snapshot(store: object) -> tuple[dict, list]:
    keep: list = []
    return ({name: _signature(getattr(store, name), keep)
             for name in STORE_CELLS}, keep)


def cells_written(before: dict, after: dict) -> tuple[str, ...]:
    return tuple(name for name in STORE_CELLS
                 if before[name] != after[name])


def seeded_engine(fact_name: str) -> engine._Engine:
    instance = new_engine()
    for prerequisite in PREREQUISITES[fact_name]:
        instance._ingest(BUILD[prerequisite]())
    return instance


def fold_write_map() -> dict[str, tuple[str, ...]]:
    written: dict[str, tuple[str, ...]] = {}
    for fact_name in BUILD:
        instance = seeded_engine(fact_name)
        before, _hold_before = store_snapshot(instance)
        instance._fold(BUILD[fact_name]())
        after, _hold_after = store_snapshot(instance)
        written[fact_name] = cells_written(before, after)
    return written
