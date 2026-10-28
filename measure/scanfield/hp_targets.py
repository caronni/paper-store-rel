"""Finding achromatic marks on a page that has no manifest.

``_targets`` locates targets on the HCAL-R1 discovery page through
``scanner/_sheet`` — page manifest x corner affine.  The home flatbed's
colour corpus is four years of experiment older than that machinery: the
2026-07-04/06 pages (CAL-1, the modulation probes, the finalists
checkerboard, the loop pages, the density ladder) predate HCAL, carry no
corner chirality marks, and have no manifest a ``Sheet`` could read.
Their layouts are recorded in the experiment logs as prose and in
``.ps`` generators that no longer round-trip to a box table.

So this module finds its targets in the capture instead of looking them
up.  That is a weaker footing than a manifest — the instrument does not
know what any mark IS — and it is deliberately traded for the only thing
the measurement actually needs: a population of small black objects that

* are ONE physical object in every channel, so the printer, the toner and
  the paper cancel in a channel difference (the whole premise of
  ``_marks``), and
* are spread across the platen, because a scanner field is a function of
  platen position and the outer band is where lateral chromatic
  aberration would live.

Three gates do the work, and each one is a measured hazard on this
corpus rather than a tidy-up:

**Isolation.**  ``_marks.mark_offsets`` derives its window from the ink
footprint of the WHOLE patch.  A second mark inside the crop joins that
footprint, the window spans both, and the support mask then protects
neither.  On these pages the hazard is not hypothetical: the finalists
checkerboard sets 7-state CMY composite tiles a few millimetres from K
tiles, and a window that reached one would put a cyan object — dark in
red, bright in green — inside a red-minus-green estimate.  A candidate is
therefore kept only if a dilation of the ink mask by ``isolation_mm``
merges nothing else into it.

**Achromaticity.**  The premise fails outright for a coloured mark: a
cyan square is not one object seen three ways, it is an object the red
channel sees and the others do not, and its channel difference is
printer registration plus demosaic, not scanner geometry.  Candidates
are gated on the ratio of their largest to smallest per-channel
contrast, measured by ``mark_offsets`` itself.  The cut is loose enough
to pass K toner (whose reflectance is flat but not perfectly so, and
which the scanner reads through three different channel gains) and tight
enough to reject any single-plane C, M or Y object, whose contrast ratio
is several-fold.

**Size.**  Big enough that a 1200-dpi centroid has pixels to work with
(the corpus is 2 px per printed dot, a quarter of the Canon footing the
estimator was calibrated on), small enough that the mark is a mark and
not a tile edge.

Candidates are found on a box-mean decimation, which is what keeps this
affordable: a 9920x14028 RGBA capture is 557 MB decoded and there are
twenty of them, so the search runs on 1/16 of that and only the accepted
crops are ever read at full resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
from PIL import Image
from scipy import ndimage

from scanner._edge import linearize_srgb

Image.MAX_IMAGE_PIXELS = None                 # these captures are 139 Mpix

MM_PER_INCH = 25.4

# --- gates, all in physical units so they port across scan resolutions ---
DECIMATE = 4                                  # search footing
MIN_MARK_MM = 0.60                            # >= 28 px at 1200 dpi
MAX_MARK_MM = 4.00
MIN_FILL = 0.18                               # bbox occupancy: reject hairlines
ISOLATION_MM = 0.90                           # clear paper required all round
# A white hole is ENCLOSED by ink, so "no other light region within 0.9
# mm" is not a weaker version of the dark gate — it is the wrong test,
# and it measured as such: dilating the light mask by 0.9 mm bridges
# every 1-to-2-dot ink stroke on these pages and merges every hole into
# the one connected paper sea, which is why the first light run returned
# 0 isolated components out of 230,743.  What a hole needs is an
# unbroken ink COLLAR, so the distance is the collar width and nothing
# else changes.
LIGHT_ISOLATION_MM = 0.40
LIGHT_MIN_MARK_MM = 0.35
PAD_MM = 0.35                                 # dark crops
LIGHT_PAD_MM = 0.30                           # must stay inside the collar
ACHROMATIC_RATIO = 1.45                       # max/min per-channel contrast
INK_FRACTION = 0.45                           # threshold between paper and ink


@dataclass(frozen=True)
class MarkCandidate:
    """One isolated dark object, in full-resolution capture pixels."""

    index: int
    y0: int
    y1: int
    x0: int
    x1: int
    area_px: int

    @property
    def cx(self) -> float:
        return 0.5 * (self.x0 + self.x1)

    @property
    def cy(self) -> float:
        return 0.5 * (self.y0 + self.y1)


def load_rgb(path: str) -> np.ndarray:
    """Whole capture as (rows, columns, 3) uint8, alpha dropped.

    PNG has no random access, so there is no windowed read to be had:
    the decoder must walk every row regardless.  One capture at a time is
    the memory discipline — 557 MB resident, released before the next.

    The conversion to RGB happens inside PIL rather than by slicing an
    RGBA array, and the difference is not cosmetic: these captures are
    RGBA, so ``asarray`` then ``[:, :, :3]`` materializes 780 MB and then
    copies 557 MB out of it, and running that peak over twenty-odd
    captures walked RSS to 4 GB.  Converting first means the alpha plane
    is dropped before any numpy array exists.
    """
    with Image.open(path) as handle:
        if handle.mode in ("L", "I;16", "I"):
            raise ValueError(
                f"{path}: single-channel capture, no channel geometry")
        array = np.asarray(handle.convert("RGB"))
    return array


def decimate_mean(plane: np.ndarray, factor: int) -> np.ndarray:
    rows = plane.shape[0] // factor * factor
    columns = plane.shape[1] // factor * factor
    block = plane[:rows, :columns].reshape(
        rows // factor, factor, columns // factor, factor)
    return block.mean(axis=(1, 3), dtype=np.float32)


def find_candidates(rgb: np.ndarray, *, scan_dpi: float,
                    decimate: int = DECIMATE,
                    min_mark_mm: float | None = None,
                    max_mark_mm: float = MAX_MARK_MM,
                    isolation_mm: float | None = None,
                    min_fill: float = MIN_FILL,
                    polarity: str = "dark",
                    small: np.ndarray | None = None,
                    ) -> tuple[list[MarkCandidate], dict[str, float]]:
    """Isolated marks of one polarity, with the census of what was removed.

    ``polarity="dark"`` finds black objects on paper; ``"light"`` finds
    paper islands enclosed by ink — the voids and quiet zones these
    probe pages carry.  The pair is the polarity split: a genuine
    per-channel DISPLACEMENT moves a black mark and a white hole the
    same way, while a per-channel PSF asymmetry (one channel's ink
    spreading further) moves them in OPPOSITE directions, because what
    grows the mark shrinks the hole.  A first moment cannot separate the
    two on either polarity alone, which is why ``channel_ca`` carries a
    slanted-edge arm; these pages have no rectangle big enough for that
    engine at 2 px per dot, and the hole is the same discriminator built
    from targets they do have.

    The margin is a light region too, and an enormous one: it is removed
    by the size gate rather than by a special case, so an enclosed hole
    and a page border go through identical code.

    The census is reported rather than discarded: a capture that yields
    few targets because everything failed isolation is a different
    statement about the corpus than one that yields few because the page
    is empty, and the verdict has to be able to tell them apart.
    """
    if min_mark_mm is None:
        min_mark_mm = (MIN_MARK_MM if polarity == "dark"
                       else LIGHT_MIN_MARK_MM)
    if isolation_mm is None:
        isolation_mm = (ISOLATION_MM if polarity == "dark"
                        else LIGHT_ISOLATION_MM)
    if small is None:
        small = decimate_mean(rgb.mean(axis=2, dtype=np.float32), decimate)
    paper = float(np.percentile(small, 98.0))
    ink = float(np.percentile(small, 2.0))
    census = {"paper_level": paper, "ink_level": ink,
              "polarity": polarity}
    if paper - ink < 12.0:                     # 8-bit levels; a blank sheet
        census["note"] = "no ink on this capture"
        return [], census

    threshold = paper - INK_FRACTION * (paper - ink)
    mask = (small < threshold) if polarity == "dark" else (small > threshold)
    px_per_mm = scan_dpi / MM_PER_INCH / decimate
    isolation_px = max(1, int(round(isolation_mm * px_per_mm)))

    labels, count = ndimage.label(mask)
    census["components"] = float(count)
    if count == 0:
        return [], census

    # One dilation, labelled again: a candidate survives only if its
    # halo merges nothing else into it.  Counting the distinct original
    # labels inside each grown component is O(pixels) and needs no
    # pairwise distances between components.
    grown_labels, _ = ndimage.label(
        ndimage.binary_dilation(mask, iterations=isolation_px))
    members: dict[int, set[int]] = {}
    flat_grown = grown_labels[mask]
    flat_own = labels[mask]
    order = np.argsort(flat_grown, kind="stable")
    sorted_grown = flat_grown[order]
    sorted_own = flat_own[order]
    edges = np.flatnonzero(np.diff(sorted_grown)) + 1
    for start, stop in zip(np.r_[0, edges], np.r_[edges, sorted_grown.size]):
        members[int(sorted_grown[start])] = set(
            np.unique(sorted_own[start:stop]).tolist())
    lonely = {next(iter(own)) for grown, own in members.items()
              if len(own) == 1}
    census["isolated"] = float(len(lonely))

    boxes = ndimage.find_objects(labels)
    areas = ndimage.sum_labels(mask, labels, index=np.arange(1, count + 1))
    kept: list[MarkCandidate] = []
    too_small = too_big = too_thin = 0
    for index, box in enumerate(boxes, start=1):
        if box is None or index not in lonely:
            continue
        ys, xs = box
        height_mm = (ys.stop - ys.start) / px_per_mm
        width_mm = (xs.stop - xs.start) / px_per_mm
        if min(height_mm, width_mm) < min_mark_mm:
            too_small += 1
            continue
        if max(height_mm, width_mm) > max_mark_mm:
            too_big += 1
            continue
        span = (ys.stop - ys.start) * (xs.stop - xs.start)
        if span <= 0 or areas[index - 1] / span < min_fill:
            too_thin += 1
            continue
        kept.append(MarkCandidate(
            index=index,
            y0=ys.start * decimate, y1=ys.stop * decimate,
            x0=xs.start * decimate, x1=xs.stop * decimate,
            area_px=int(areas[index - 1]) * decimate * decimate))
    census.update({"rejected_small": float(too_small),
                   "rejected_large": float(too_big),
                   "rejected_thin": float(too_thin),
                   "candidates": float(len(kept))})
    return kept, census


def crop(rgb: np.ndarray, candidate: MarkCandidate, *, scan_dpi: float,
         pad_mm: float = PAD_MM) -> np.ndarray:
    """Full-resolution patch around one candidate.

    The pad is smaller than ``ISOLATION_MM`` by construction, so the
    crop cannot reach the neighbour the isolation gate cleared.
    """
    pad = int(round(pad_mm * scan_dpi / MM_PER_INCH))
    y0 = max(0, candidate.y0 - pad)
    y1 = min(rgb.shape[0], candidate.y1 + pad)
    x0 = max(0, candidate.x0 - pad)
    x1 = min(rgb.shape[1], candidate.x1 + pad)
    return rgb[y0:y1, x0:x1, :]


def achromatic(contrast: dict[str, float],
               ratio: float = ACHROMATIC_RATIO) -> tuple[bool, float]:
    """Is this mark one object seen three ways, or a coloured one?

    Returns ``(verdict, ratio)``; the ratio is reported for every mark
    whether it passes or not, so the cut can be audited against the
    population it was applied to.
    """
    values = [v for v in contrast.values() if v > 0.0]
    if len(values) < 3:
        return False, float("inf")
    measured = max(values) / min(values)
    return measured <= ratio, measured


def iter_marks(rgb: np.ndarray, candidates: list[MarkCandidate], *,
               scan_dpi: float, polarity: str = "dark",
               tone: str = "srgb"
               ) -> Iterator[tuple[MarkCandidate, np.ndarray]]:
    """Yield ``(candidate, patch)`` ready for ``_marks.mark_offsets``.

    A light-polarity patch is inverted so the same estimator reads it,
    and the inversion is done in RADIANCE-LINEAR space rather than on
    code values: ``255 - x`` on an sRGB-encoded capture is not the
    complement of anything physical, and it would bend the three
    channels' profiles by different amounts — manufacturing exactly the
    channel difference the polarity split exists to check.  The returned
    patch is already linear, so the caller passes ``tone="none"``.
    """
    pad_mm = PAD_MM if polarity == "dark" else LIGHT_PAD_MM
    for candidate in candidates:
        patch = crop(rgb, candidate, scan_dpi=scan_dpi, pad_mm=pad_mm)
        if min(patch.shape[:2]) < 12:
            continue
        if polarity == "light":
            linear = linearize_srgb(patch, tone)
            patch = (1.0 - linear) * 255.0
        yield candidate, patch
