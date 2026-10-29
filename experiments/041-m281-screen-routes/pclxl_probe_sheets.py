"""e041 S10p2 — the two banded probe sheets' plans: which values, which slots, which images.

Imported by pclxl_probe_banded.py (the emitter and its --verify).  Two sheets: FULL (S10p2, the 337-value
sweep x three methods in nine bands + the 14-patch treatment witness) and ONLY_M (S10p2M, the fallback form:
the 84 magenta values + the C corner and W under each method, one band per method, a 3-patch witness).  The
sweep, pattern, slot-grid and rounding helpers come from pclxl_probe.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from pcl_planar import sha
from pclxl_probe import (FIDUCIALS_MM, LAYOUT_SEED, METHODS, PATCH_H_DOTS, PATTERN_DOTS, PATTERN_SEED_BASE,
                         TREAT_WITNESS, dots, mm, patch_raster, pattern, slot_grid, sweep, target)

RGB = tuple[int, int, int]
BAND_ROWS = 4
WITNESS_BAND = -1  # the manifest's "band" of the witness patches (slot row 0)
FIRST_BAND_ROW = 1
PALETTE_ENTRIES = 256  # e8Bit indexed: 2**8 entries x 3 = 768 bytes (X20 p. 85)
FIDUCIAL_IMAGES = (("fid-top", ("F0", "F1")), ("fid-left", ("F4",)), ("fid-bottom", ("F2", "F3")))
WITNESS_BLOCK = ("adaptive", "trapping", "neutral")  # no SetColorTreatment: the BeginPage default treatment
HEAD_BLOCK = ("treatment", "adaptive", "trapping", "neutral")  # S9's control block, in S9's order
C_CORNER, M_CORNER, WHITE = (0, 255, 255), (255, 0, 255), (255, 255, 255)

Split = Callable[[np.random.Generator, int, int], list[list[tuple[int, RGB]]]]


def split_full(rng: np.random.Generator, method_index: int, n_bands: int) -> list[list[tuple[int, RGB]]]:
    """One permutation of the 337 sweep values per method, split 113/112/112 over its bands; patch id =
    method index x 337 + sweep index (S10p's ids and seeds for the same patterns)."""
    values = sweep()
    perm = rng.permutation(len(values))
    return [[(method_index * len(values) + int(v), values[int(v)]) for v in chunk]
            for chunk in np.array_split(perm, n_bands)]


def m_values() -> list[RGB]:
    """The 84 magenta sweep values (target M, sweep order), then the C corner and W as controls."""
    ms = [v for v in sweep() if target(v) == "M"]
    if len(ms) != 84:
        raise SystemExit(f"{len(ms)} magenta sweep values, 84 expected")
    return ms + [C_CORNER, WHITE]


def split_m(rng: np.random.Generator, method_index: int, n_bands: int) -> list[list[tuple[int, RGB]]]:
    """No draw: the method's one band carries all 86 values in m_values() order; id = method index x 86
    + k."""
    if n_bands != 1:
        raise SystemExit(f"the M-only sheet has one band per method, not {n_bands}")
    values = m_values()
    return [[(method_index * len(values) + k, v) for k, v in enumerate(values)]]


@dataclass(frozen=True)
class Sheet:
    key: str
    tag: str
    job_name: str
    comment: bytes
    band_methods: tuple[str, ...]
    witness: tuple[RGB, ...]
    split: Split


FULL = Sheet("full", "S10p2-pclxl-rgb-probe", "E041-S10P2-PCLXL-RGB-PROBE", b"banded indexed RGB probe sheet",
             ("default", "highlpi", "matrix1x1", "matrix1x1", "default", "highlpi",
              "highlpi", "matrix1x1", "default"),  # D,H,M, M,D,H, H,M,D: each method once per page third
             TREAT_WITNESS, split_full)
ONLY_M = Sheet("M", "S10p2M-pclxl-rgb-probe-M", "E041-S10P2M-PCLXL-RGB-PROBE-M",
               b"banded indexed RGB probe sheet magenta only", ("default", "highlpi", "matrix1x1"),
               (M_CORNER, (192, 0, 192), C_CORNER), split_m)
SHEETS = {"full": FULL, "M": ONLY_M}


def rect_of_slots(slots: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    """(x, y, w, h) dots of the bounding box of whole patches at the slots."""
    x0, y0 = min(x for x, _ in slots), min(y for _, y in slots)
    x1, y1 = max(x for x, _ in slots) + PATTERN_DOTS, max(y for _, y in slots) + PATCH_H_DOTS
    return x0, y0, x1 - x0, y1 - y0


def fiducials() -> list[dict]:
    """The five fiducials of FIDUCIALS_MM, black, positions rounded to whole dots."""
    return [{"id": f, "x_mm": mm(dots(x)), "y_mm": mm(dots(y)), "w_mm": w, "h_mm": h, "rgb": [0, 0, 0],
             "_xywh": (dots(x), dots(y), dots(w), dots(h))} for f, x, y, w, h in FIDUCIALS_MM]


def fiducial_images(fids: list[dict]) -> list[dict]:
    """The three fiducial images of FIDUCIAL_IMAGES (e8Bit indexed, entry 1 black, the rest white), each with
    S9's four controls; records each fiducial's image name in fids."""
    images: list[dict] = []
    by_id = {f["id"]: f for f in fids}
    for name, ids in FIDUCIAL_IMAGES:
        boxes = [by_id[i]["_xywh"] for i in ids]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
        pal = np.full((PALETTE_ENTRIES, 3), 255, np.uint8)
        pal[1] = 0
        raster = np.zeros((y1 - y0, x1 - x0), np.uint8)
        for bx, by, bw, bh in boxes:
            raster[by - y0:by - y0 + bh, bx - x0:bx - x0 + bw] = 1
        images.append({"name": name, "kind": "fiducial", "band": None, "method": "default", "slot_rows": [],
                       "xywh": (x0, y0, x1 - x0, y1 - y0), "palette": pal, "raster": raster,
                       "members": list(ids), "block": HEAD_BLOCK})
        for i in ids:
            by_id[i]["image"] = name
    return images


def plan(sheet: Sheet) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Patches, fiducials, images (in emission order) and the layout record.  One generator,
    default_rng(LAYOUT_SEED), draws in this order: per method (METHODS order) whatever sheet.split draws
    (FULL: the permutation of the 337 values; ONLY_M: nothing), then per band of that method, in band order,
    the permutation of its 116 slots (patch k of the band takes slot perm[k]); last the witness row's
    permutation of 29 slots (witness k takes slot perm[k]).  Witness ids follow the pattern ids; pattern
    seed = 41000 + id.  Every image but the witness carries S9's control block after its SetColorSpace,
    plus its band's SetHalftoneMethod for a highlpi or matrix band."""
    slots = slot_grid()
    xs, ys = sorted({x for x, _ in slots}), sorted({y for _, y in slots})
    if (len(xs), len(ys)) != (29, 42):
        raise SystemExit(f"slot grid {len(xs)} x {len(ys)}, 29 x 42 expected")
    rng = np.random.default_rng(LAYOUT_SEED)
    patches: list[dict] = []
    members: dict[int, list[dict]] = {}

    def add(pid: int, rgb: RGB, method: str, kind: str, band: int, xy_: tuple[int, int]) -> None:
        seed = PATTERN_SEED_BASE + pid
        pat = pattern(seed)
        p = {"id": pid, "x_mm": mm(xy_[0]), "y_mm": mm(xy_[1]), "rgb": list(rgb), "method": method,
             "kind": kind, "target": target(rgb), "seed": seed, "pattern_sha256": sha(pat.tobytes()),
             "encoding": "indexed8", "band": band, "_xy": xy_, "_pattern": pat}
        patches.append(p)
        members.setdefault(band, []).append(p)

    for mi, method in enumerate(METHODS):
        bands = [b for b, m in enumerate(sheet.band_methods) if m == method]
        for band, chunk in zip(bands, sheet.split(rng, mi, len(bands)), strict=True):
            row0 = FIRST_BAND_ROW + BAND_ROWS * band
            band_slots = [(x, y) for y in ys[row0:row0 + BAND_ROWS] for x in xs]
            place = rng.permutation(len(band_slots))
            for k, (pid, rgb) in enumerate(chunk):
                add(pid, rgb, method, "pattern", band, band_slots[int(place[k])])
    witness_slots = [(x, ys[0]) for x in xs]
    place = rng.permutation(len(witness_slots))
    base = len(patches)
    for k, rgb in enumerate(sheet.witness):
        add(base + k, rgb, "default", "treatdefault", WITNESS_BAND, witness_slots[int(place[k])])
    patches.sort(key=lambda p: p["id"])

    fids = fiducials()
    images: list[dict] = []

    def band_image(name: str, band: int, method: str, rows: list[int], block: tuple[str, ...]) -> dict:
        region = [(x, ys[r]) for r in rows for x in xs]
        x, y, w, h = rect_of_slots(region)
        mem = sorted(members.get(band, []), key=lambda p: (p["_xy"][1], p["_xy"][0]))
        pal = np.full((PALETTE_ENTRIES, 3), 255, np.uint8)
        raster = np.zeros((h, w), np.uint8)
        for k, p in enumerate(mem, start=1):
            pal[k] = p["rgb"]
            p["palette_index"] = k
            px, py = p["_xy"]
            raster[py - y:py - y + PATCH_H_DOTS, px - x:px - x + PATTERN_DOTS][
                patch_raster(p["_pattern"]).astype(bool)] = k
        return {"name": name, "kind": "witness" if band == WITNESS_BAND else "band", "band": band,
                "method": method, "slot_rows": rows, "xywh": (x, y, w, h), "palette": pal, "raster": raster,
                "members": [p["id"] for p in mem], "block": block}

    images.append(band_image("witness", WITNESS_BAND, "default", [0], WITNESS_BLOCK))
    images += fiducial_images(fids)
    for method in METHODS:
        block = HEAD_BLOCK + ((method,) if method != "default" else ())
        for band in (b for b, m in enumerate(sheet.band_methods) if m == method):
            row0 = FIRST_BAND_ROW + BAND_ROWS * band
            images.append(band_image(f"band{band}", band, method, list(range(row0, row0 + BAND_ROWS)), block))
    n_bands = len(sheet.band_methods)
    record = {"slots": len(slots), "columns": len(xs), "rows": len(ys), "columns_x_dots": xs,
              "rows_y_dots": ys, "witness_slot_row": 0,
              "band_slot_rows": {b: [FIRST_BAND_ROW + BAND_ROWS * b + i for i in range(BAND_ROWS)]
                                 for b in range(n_bands)},
              "empty_slot_rows": list(range(FIRST_BAND_ROW + BAND_ROWS * n_bands, len(ys)))}
    return patches, fids, images, record
