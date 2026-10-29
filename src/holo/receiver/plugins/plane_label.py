"""``tiles.planek`` on a cmy LABEL stream: its toners' isolated reads, summed.

THE TRANSLATION (R25, 2026-10-12; CMY-RECEIVER-PLAN A7).  cmy8's planek
reads one toner plane as a black-and-white page; cmy's streams are not
planes but the cell's two label bits, hi = [state in {C, M}] and lo =
[state in {C, Y}] (CMY-DESIGN §2.2).  A cmy cell carries AT MOST ONE
toner, so each label bit is exactly a SUM of toner presences — hi = C +
M, lo = C + Y — and `tile_codec.stream_toners` derives that sum from the
row's own tables (`plane_bits`, `stream_bits`), refusing any stream
whose bit is not one.  The readout `lib/spectral` fits is linear in the
planes, so the sum of the toners' unit-gain reads is a unit-gain read of
the label: a C or M cell reads one ink layer on hi, a W or Y cell none,
Y cancelled in the mean by C's and M's own functionals.  That is §2.9's
"hi is darkness in R+G, lo in R+B−G" as a derived functional, not an
input to it.

EACH TONER WHERE IT IS PRINTED.  The two toners of a label are not in
register with each other (e044's M and Y sit a dot off C), and a
toner's functional annihilates the other inks whatever their coverage at
its sampling point, so each toner is read by `plane_k`'s per-plane
machinery — sampled at its own plane field, its own mixing fit, its own
offset sweep — and only the two presences are added, cell by cell, on
the windows both toners read.  The black-and-white calibration
(`calibrate.window_evidence`, the region context) then prices the sum
against the label, exactly as cmy8's planek prices one plane.

THE PROJECT READOUT, NOT SUBTRACT.  cmy8's planek subtracts a proven
sibling's ink before it reads the target.  In a one-toner alphabet a
sibling proven PRESENT proves the target absent, and a subtraction at a
misregistered sample leaves -(1 - a)·m_sibling in the residual, which
the target's matched filter reads at rf_C·m_M = 0.45 on e043c's bars
(Σ ≈ σ²I): a score shift on exactly the target-0 cells, so the offset
sweep's held-out loss rewards misregistration (on a page with one noise
level per cell the sweep ran to -1.25 dots and hi failed; the ledger in
`test_h3_cmy_residue`).  The project functional annihilates every
sibling at any coverage and reads proven and unproven cells alike, so
the calibration fitted on the one prices the other.

LABELS FROM PROVEN STATES ONLY (`plane_k.stream_labels`).  One certified
label stream knows only TRUE ZEROS through the consistency rule
(`color_sites`: hi 0 proves C and M absent, hi 1 proves only Y absent),
so a neighbour certified in the target stream alone would label its 0
cells and none of its 1 cells — a selection on the label itself, which
skews the PAVA map toward 0.  A cell whose three planes are all proven
(furniture, a tile certified in both streams) carries its label
unselected; the toners' offset sweeps read the same cells.

THE PRODUCT FORM.  The calibrated label LLR L is written into EVERY
toner column of the transient row and 0.0 elsewhere — (L, L, 0) for hi,
(L, 0, L) for lo — which `tile_codec.cmy_soft_demap` reads back as
exactly L: BICM, log(e^L + e^L) − log 2, and conditioned on the sibling,
s_C − s_Y or s_M (s_C − s_M or s_Y).  The attempt is the stream's own
codeword at its own dither (`fact.label_index`, `fact.dither_aux`),
through the unchanged codec gate.  The two-channel K view of design
§2.9b (kview) is a different row, parked (R25a); this is planek's.
"""

from __future__ import annotations

import time
from typing import Sequence

import numpy as np

from ..data import ColorEvidenceRow, JobResult
from ..format.identity import FormatRow, SiteGeometry
from ..lib import spectral
from . import calibrate, color_region, local_ctx, plane_k, tiles

LabelRows = tuple[tuple[object, int, ColorEvidenceRow], ...]


def label_rows(row: FormatRow, geometry: SiteGeometry,
               plans: Sequence[plane_k.LanePlan], certificates: dict,
               toners: Sequence[int]) -> LabelRows:
    """One lane's label read: every toner's isolated presence, summed.

    `plans` is the lane once per toner, each carrying that toner's
    field.  The sum is in units of one ink layer, negated into
    `window_scores` units as a grey read is (`plane_k.isolated_scores`).
    """
    planes = tuple(raster.open() for raster in plans[0].planes)
    cell_dots = color_region.cell_dots_of(row)
    memo: dict = {}
    toner_reads: list[tuple[spectral.PlaneMix,
                            dict[int, plane_k.WindowRead]]] = []
    for plan, plane in zip(plans, toners, strict=True):
        found = plane_k.plane_reads(row, geometry, plan, certificates, plane,
                                    planes, cell_dots, memo,
                                    label_toner=True)
        if found is None:
            return ()
        mix, reads = found
        toner_reads.append((mix, {int(read.window.patch_ordinal): read
                                  for read in reads}))
    firsts = [read for ordinal, read in toner_reads[0][1].items()
              if all(ordinal in reads for _mix, reads in toner_reads)]
    built = []
    for first in firsts:
        ordinal = int(first.window.patch_ordinal)
        score = None
        for (mix, reads), plane in zip(toner_reads, toners, strict=True):
            read = reads[ordinal]
            presence = spectral.plane_score(
                mix, read.values, read.rows.known_component_bits,
                read.rows.known_component_mask, plane, spectral.MODE_PROJECT)
            score = presence if score is None else score + presence
        built.append(calibrate.window_evidence(
            first.placement, first.rows.page_cells_yx,
            calibrate.window_scores(np.asarray(-score, np.float32)),
            plane_k.stream_labels(first.rows, toners)))
    if not built:
        return ()
    corrected, _ctx = calibrate.apply_region_context(tuple(built))
    arity = tiles.evidence_arity(row)
    out = []
    for read, evidence in zip(firsts, corrected, strict=True):
        transient = plane_k.transient_row(read, evidence, toners, arity)
        if transient is not None:
            out.append((read.window.window_id, read.region_index, transient))
    return tuple(out)


def label_job(row: FormatRow, geometry: SiteGeometry,
              lanes: Sequence[Sequence[plane_k.LanePlan]],
              certificates: dict, page: int, ty: int, tx: int,
              stream_id: str, toners: Sequence[int],
              generations: local_ctx.Generations | None = None,
              ) -> JobResult:
    """One label-isolated attempt over every lane that produced a cut,
    stamped as `plane_k.planek_job` stamps its own."""
    started = time.thread_time()
    components: list[tiles.TileCut] = []
    for plans in lanes:
        rows = label_rows(row, geometry, plans, certificates, toners)
        cut = (plane_k.rows_cut(plans[0].lane, rows, row, geometry, page,
                                ty, tx) if rows else None)
        if cut is not None:
            components.append(cut)
    stamps = generations or local_ctx.Generations()
    facts, events = plane_k.attempt_components(
        row, geometry, components, stream_id, stamps.of(components))
    return JobResult(facts, events, time.thread_time() - started)
