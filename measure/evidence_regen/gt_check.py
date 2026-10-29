"""Is every archived ground-truth array derivable from its print job alone?

Three layouts are on disk:

- holo (``pageNNN_gt.npy``, ``charsheet_gt.npy``, e041's ``S*-gt/page000_gt.npy``):
  the packed array `holo.gen.emit` saves, compared whole against
  `util.ps_gt.holo_gt` of the job's bitmap(s) (several bitmaps tiling one
  rectangle, as on S5, are composed first);
- paperholo dot arrays (``<stem>_gt/*.npy``, e001's ``ground_truth/``): unpacked
  0/1 planes, matched against every bitmap / CMYK plane of the same shape,
  else against the crop of a bitmap at the rectangle the manifest records;
- symbol arrays (``*_states``, ``*_levels``, ``*_cells``, e010's motif maps):
  cell-scale labels, not dots.  They count as derivable when the dot planes of
  the same patch (siblings, or the manifest rectangle) determine the label
  cell by cell — the cell-pattern -> label map is then a function, and the
  map itself is the generator's alphabet.  Payload symbol arrays are not
  derivable from a job.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from util.ps_gt import PsBitmap, holo_gt, parse_bitmaps

GT_COLUMNS = ("gt", "job", "layout", "shape", "verdict", "note")
_SYMBOL_NAME = re.compile(r"_(states|levels|cells)$")


@dataclass(frozen=True)
class GtVerdict:
    gt: str
    job: str
    layout: str          # holo | dots | symbols | payload
    shape: str
    verdict: str         # gt-derivable | derivable-via-cell-map | differs | not-derivable | not-checked
    note: str

    def row(self) -> str:
        return "\t".join(str(getattr(self, c)).replace("\t", " ") for c in GT_COLUMNS)


# ---------------------------------------------------------------- discovery
def holo_sets(root: Path) -> list[tuple[Path, list[Path]]]:
    """(gt, [job]) for every holo-layout GT under scratch/ and build/."""
    out = []
    for base in ("scratch", "build"):
        for gt in sorted((root / base).rglob("*_gt.npy")):
            if gt.name.startswith("page") and gt.name.endswith("_gt.npy"):
                if gt.parent.name.endswith("-gt"):
                    job = gt.parent.parent / (gt.parent.name[:-3] + ".ps")
                else:
                    job = gt.with_name(gt.name.replace("_gt.npy", ".ps"))
            elif gt.name == "charsheet_gt.npy":
                job = gt.with_name("charsheet.ps")
            else:
                continue
            out.append((gt, [job]))
    return out


def paperholo_sets(root: Path) -> list[tuple[Path, list[Path]]]:
    """(gt dir, [jobs]) for the paperholo writers' unpacked GT trees."""
    out = []
    for d in sorted(root.glob("experiments/*/build/*_gt")) + sorted(root.glob("scratch/fullpage-*_gt")):
        stem = d.name[:-3]
        if stem == "e006":
            jobs = [d.parent / "e006bw.ps", d.parent / "e006c.ps"]
        elif stem == "ores":
            jobs = [d.parent / "ores_pspjl1200.job"]
        else:
            jobs = [d.parent / f"{stem}.ps"]
        out.append((d, jobs))
    gt001 = root / "experiments/001-engine-characterization/build/ground_truth"
    if gt001.is_dir():
        out.append((gt001, [gt001.parent / "001_patterns.ps"]))
    return out


# ---------------------------------------------------------------- holo
def compose(bms: list[PsBitmap]) -> PsBitmap:
    """Several same-kind bitmaps tiling one rectangle -> one bitmap."""
    if len(bms) == 1:
        return bms[0]
    kinds = {b.kind for b in bms}
    if len(kinds) != 1 or len({b.page for b in bms}) != 1:
        raise ValueError("bitmaps of mixed kinds or pages")
    x0, y0 = min(b.x_dots for b in bms), min(b.y_dots for b in bms)
    x1 = max(b.x_dots + b.w_dots for b in bms)
    y1 = max(b.y_dots + b.h_dots for b in bms)
    shape = (y1 - y0, x1 - x0) + ((4,) if "cmyk" in kinds else ())
    canvas = np.zeros(shape, np.uint8)
    cover = np.zeros(shape[:2], np.int32)
    for b in bms:
        sl = (slice(b.y_dots - y0, b.y_dots - y0 + b.h_dots), slice(b.x_dots - x0, b.x_dots - x0 + b.w_dots))
        canvas[sl] |= b.bits()
        cover[sl] += 1
    if (cover != 1).any():
        raise ValueError("bitmaps do not tile their bounding rectangle exactly once")
    per_px = 4 if "cmyk" in kinds else 1
    packed = np.packbits(canvas.reshape(shape[0], -1)[:, :shape[1] * per_px], axis=1).tobytes()
    b = bms[0]
    return PsBitmap(b.kind, b.page, x0, y0, shape[1], shape[0], b.dpi_xy, b.cmyk, b.polarity, packed)


def check_holo(root: Path, gt: Path, job: Path) -> GtVerdict:
    rel, jrel = str(gt.relative_to(root)), str(job.relative_to(root))
    g = np.load(gt, allow_pickle=False)
    if not job.is_file():
        return GtVerdict(rel, jrel, "holo", str(g.shape), "not-checked", "job not on disk")
    bms = parse_bitmaps(job.read_bytes())
    try:
        derived = holo_gt(compose(bms))
    except ValueError as exc:
        return GtVerdict(rel, jrel, "holo", str(g.shape), "differs", str(exc))
    same = derived.shape == g.shape and np.array_equal(derived, g)
    note = f"{len(bms)} bitmap(s)" + ("" if same else f"; derived {derived.shape}")
    return GtVerdict(rel, jrel, "holo", str(g.shape), "gt-derivable" if same else "differs", note)


# ---------------------------------------------------------------- paperholo
def _rects(build: Path) -> dict[str, tuple[int, int, int, int]]:
    """GT file name -> (x, y, w, h) dots from the manifest dict naming it (or its nearest parent with one)."""
    rects: dict[str, tuple[int, int, int, int]] = {}

    def walk(o: object, rect: tuple[int, int, int, int] | None) -> None:
        if isinstance(o, dict):
            if all(isinstance(o.get(k), int) for k in ("x_dots", "y_dots", "w_dots", "h_dots")):
                rect = (o["x_dots"], o["y_dots"], o["w_dots"], o["h_dots"])
            for v in o.values():
                if isinstance(v, str) and v.endswith(".npy"):
                    if rect is not None:
                        rects.setdefault(Path(v).name, rect)
                else:
                    walk(v, rect)
        elif isinstance(o, list):
            for v in o:
                walk(v, rect)
    for m in sorted(build.glob("*manifest*.json")):
        walk(json.loads(m.read_text()), None)
    return rects


def _planes(b: PsBitmap) -> list[np.ndarray]:
    x = b.bits()
    return [x] if b.kind == "mask" else [x[..., i] for i in range(4)]


def _crops(bms: list[PsBitmap], rect: tuple[int, int, int, int]) -> list[np.ndarray]:
    x, y, w, h = rect
    out = []
    for b in bms:
        if b.x_dots <= x and b.y_dots <= y and x + w <= b.x_dots + b.w_dots and y + h <= b.y_dots + b.h_dots:
            out += [p[y - b.y_dots:y - b.y_dots + h, x - b.x_dots:x - b.x_dots + w] for p in _planes(b)]
    return out


def cell_map_function(symbols: np.ndarray, planes: list[np.ndarray]) -> str:
    """'' if the planes' cell patterns determine ``symbols`` cell by cell, else why not."""
    if not planes or len({p.shape for p in planes}) != 1:
        return "no dot planes for this patch"
    n, m = symbols.shape
    hh, ww = planes[0].shape
    if hh % n or ww % m:
        return f"dots {planes[0].shape} not a whole multiple of the labels {symbols.shape}"
    cy, cx = hh // n, ww // m
    d = np.stack([p.astype(np.uint8) for p in planes])                      # (P, H, W)
    cells = d.reshape(len(planes), n, cy, m, cx).transpose(1, 3, 0, 2, 4).reshape(n * m, -1)
    keys = np.packbits(cells, axis=1)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    pairs = np.unique(np.stack([inv.ravel(), symbols.ravel().astype(np.int64)]), axis=1)
    if len(np.unique(pairs[0])) != pairs.shape[1]:
        return "one cell pattern carries two labels"
    return ""


def check_paperholo(root: Path, gt_dir: Path, jobs: list[Path]) -> list[GtVerdict]:
    jrel = ", ".join(str(j.relative_to(root)) for j in jobs)
    present = [j for j in jobs if j.is_file()]
    bms = [b for j in present for b in parse_bitmaps(j.read_bytes())]
    by_shape: dict[tuple[int, int], list[np.ndarray]] = {}
    for b in bms:
        for p in _planes(b):
            by_shape.setdefault(p.shape, []).append(p)
    rects = _rects(gt_dir.parent)
    if gt_dir.name == "ores_gt" and len(bms) == 1:       # e009: rects are relative to the logical bitmap
        rects = {k: (x + bms[0].x_dots, y + bms[0].y_dots, w, h) for k, (x, y, w, h) in rects.items()
                 if k.endswith("_1200.npy")}
    files = sorted(gt_dir.glob("*.npy"))
    arrays = {f.name: np.load(f, allow_pickle=False) for f in files}
    derived_dots: dict[str, np.ndarray] = {}
    verdicts: dict[str, GtVerdict] = {}
    for f in files:                              # pass 1: dot arrays
        a, rel = arrays[f.name], str(f.relative_to(root))
        if "payload" in f.stem:
            verdicts[f.name] = GtVerdict(rel, jrel, "payload", str(a.shape), "not-derivable",
                                         "payload symbols: generator only")
            continue
        if a.ndim != 2 or _SYMBOL_NAME.search(f.stem) or not set(np.unique(a).tolist()) <= {0, 1}:
            continue
        if not present:
            verdicts[f.name] = GtVerdict(rel, jrel, "dots", str(a.shape), "not-checked", "job not on disk")
            continue
        hit = any(np.array_equal(c, a) for c in by_shape.get(a.shape, []))
        where = "a whole bitmap/plane"
        if not hit and f.name in rects:
            hit = any(np.array_equal(c, a) for c in _crops(bms, rects[f.name]))
            where = f"the manifest rectangle {rects[f.name]}"
        if hit:
            derived_dots[f.name] = a
            verdicts[f.name] = GtVerdict(rel, jrel, "dots", str(a.shape), "gt-derivable", f"equals {where}")
    for f in files:                              # pass 2: labels (and 0/1 arrays that matched no bitmap)
        if f.name in verdicts:
            continue
        a, rel = arrays[f.name], str(f.relative_to(root))
        stem = _SYMBOL_NAME.sub("", f.stem)
        sib = [v for k, v in sorted(derived_dots.items())
               if (k[:-4] == stem or k.startswith(stem + "_")) and k != f.name]
        why = cell_map_function(a, sib) if a.ndim == 2 else "not 2-D"
        source = "sibling dot planes"
        if why and f.name in rects:
            why = cell_map_function(a, _crops(bms, rects[f.name]))
            source = f"the job's planes at the manifest rectangle {rects[f.name]}"
        if not present:
            verdicts[f.name] = GtVerdict(rel, jrel, "symbols", str(a.shape), "not-checked", "job not on disk")
        elif gt_dir.name == "ores_gt" and f.stem.endswith("_2400"):
            verdicts[f.name] = GtVerdict(rel, jrel, "symbols", str(a.shape), "not-checked",
                                         "the 2400 fields are only in ores_pcl2400.pcl (PCL raster); "
                                         "the parser reads PostScript")
        elif why:
            verdicts[f.name] = GtVerdict(rel, jrel, "symbols", str(a.shape),
                                         "differs" if set(np.unique(a).tolist()) <= {0, 1}
                                         and not _SYMBOL_NAME.search(f.stem) else "not-derivable", why)
        else:
            verdicts[f.name] = GtVerdict(rel, jrel, "symbols", str(a.shape), "derivable-via-cell-map",
                                         f"labels are a function of {source}")
    return [verdicts[f.name] for f in files]


def run(root: Path) -> list[GtVerdict]:
    out = [check_holo(root, gt, jobs[0]) for gt, jobs in holo_sets(root)]
    for d, jobs in paperholo_sets(root):
        out.extend(check_paperholo(root, d, jobs))
    return out


def write(path: Path, verdicts: list[GtVerdict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\t".join(GT_COLUMNS) + "\n" + "".join(v.row() + "\n" for v in verdicts))
