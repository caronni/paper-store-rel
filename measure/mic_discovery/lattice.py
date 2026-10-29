"""The dot lattice: autocorrelation per window, site indexing over the
page, the payload repeat and the folded cell.

Coordinates are capture millimetres ``(x_mm, y_mm)`` — the scanner's
nominal scale, not printed millimetres (the Canon reads +0.3–0.6 %).
Lattice sites are integer pairs ``(i, j)`` along the reduced lattice
vectors ``a`` (nearer the capture x axis) and ``b``.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

#: Autocorrelation peaks: shortest vector considered, longest, the local
#: maximum footprint and the robust z a peak must clear.
AC_MIN_MM: float = 0.3
AC_MAX_MM: float = 6.0
AC_FOOTPRINT_MM: float = 0.25
AC_PEAK_Z: float = 8.0

#: Site indexing: neighbours within this many lattice spacings (never
#: less than ``LINK_MIN_MM``) are linked, and a link is kept when the
#: offset is this close to integer.  0.3 of the Canon's 6-dot x pitch is
#: 0.076 mm: its strings of dots sit 2-3 mm apart and disagree locally
#: by ~0.05 mm (0.22 left them unlinked, measured 2026-10-09).
LINK_SPACINGS: float = 3.5
LINK_MIN_MM: float = 3.0
LINK_TOLERANCE: float = 0.3

#: A known-empty site needs an indexed dot within this distance (mm):
#: the indexed component is where the lattice is known to be in register.
KNOWN_RADIUS_MM: float = 5.0

#: More sites than this in the indexed box is a mis-indexed dot, not a
#: page (a 0.25 x 0.5 mm lattice over A4 is ~5e5 sites).
MAX_SITES: int = 4_000_000

#: Repeat search: largest shift (mm, each lattice axis), the conditional
#: agreement a repeat vector must reach and the pairs it must rest on.
REPEAT_MAX_MM: float = 60.0
REPEAT_MIN_AGREEMENT: float = 0.80
REPEAT_MIN_PAIRS: int = 30


def reduce_basis(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lagrange–Gauss reduction, then ``a`` nearer x with ``a.x > 0`` and
    ``b`` with ``b.y > 0``."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    for _ in range(64):
        if a @ a > b @ b:
            a, b = b, a
        mu = round(float(a @ b) / float(a @ a))
        if mu == 0:
            break
        b = b - mu * a
    if abs(b[0]) > abs(a[0]):
        a, b = b, a
    if a[0] < 0:
        a = -a
    if b[1] < 0:
        b = -b
    return a, b


@dataclass(frozen=True)
class WindowLattice:
    """One window's autocorrelation verdict."""

    centre_mm: tuple[float, float]
    kind: str
    blank_fraction: float
    n_peaks: int
    a_mm: tuple[float, float] | None
    b_mm: tuple[float, float] | None
    peak_z: float

    def to_dict(self) -> dict[str, object]:
        return {
            "centre_mm_xy": [round(v, 2) for v in self.centre_mm],
            "kind": self.kind,
            "blank_fraction": round(self.blank_fraction, 3),
            "n_peaks": self.n_peaks,
            "a_mm_xy": None if self.a_mm is None else [round(v, 4) for v in self.a_mm],
            "b_mm_xy": None if self.b_mm is None else [round(v, 4) for v in self.b_mm],
            "a_len_mm": None if self.a_mm is None else round(float(np.hypot(*self.a_mm)), 4),
            "b_len_mm": None if self.b_mm is None else round(float(np.hypot(*self.b_mm)), 4),
            "best_peak_z": round(self.peak_z, 1),
        }


def autocorrelation_peaks(sparse: np.ndarray, px_per_mm: float) -> tuple[np.ndarray, np.ndarray]:
    """Peak shift vectors (mm, x/y) and their robust z in an overlap-
    normalised autocorrelation of a sparse yellow map."""
    h, w = sparse.shape
    fh, fw = 2 * h, 2 * w
    spec = np.fft.rfft2(sparse, s=(fh, fw))
    ac = np.fft.irfft2(spec * np.conj(spec), s=(fh, fw))
    ones = np.fft.rfft2(np.ones_like(sparse), s=(fh, fw))
    overlap = np.fft.irfft2(ones * np.conj(ones), s=(fh, fw))
    ac = np.fft.fftshift(ac / np.maximum(overlap, 1.0))
    cy, cx = fh // 2, fw // 2
    r = int(np.ceil(AC_MAX_MM * px_per_mm))
    view = ac[cy - r:cy + r + 1, cx - r:cx + r + 1]
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1] / px_per_mm
    rad = np.hypot(yy, xx)
    ring = (rad >= AC_MIN_MM) & (rad <= AC_MAX_MM)
    vals = view[ring]
    med = float(np.median(vals))
    # A map with few dots leaves most shifts at exactly zero overlap and
    # the MAD at zero; a tenth of the plain spread is the floor.
    sig = max(float(1.4826 * np.median(np.abs(vals - med))), 0.1 * float(np.std(vals)), 1e-12)
    z = (view - med) / sig
    foot = max(3, int(round(AC_FOOTPRINT_MM * px_per_mm)) | 1)
    peaks = (view == ndimage.maximum_filter(view, size=foot)) & ring & (z > AC_PEAK_Z)
    py, px = np.nonzero(peaks)
    vec = []
    for y, x in zip(py, px):
        dy = dx = 0.0
        if 0 < y < view.shape[0] - 1:
            c0, cm, cp = view[y, x], view[y - 1, x], view[y + 1, x]
            den = cm - 2 * c0 + cp
            dy = 0.5 * (cm - cp) / den if den < 0 else 0.0
        if 0 < x < view.shape[1] - 1:
            c0, cm, cp = view[y, x], view[y, x - 1], view[y, x + 1]
            den = cm - 2 * c0 + cp
            dx = 0.5 * (cm - cp) / den if den < 0 else 0.0
        vec.append(((x - r + dx) / px_per_mm, (y - r + dy) / px_per_mm))
    return np.array(vec, float).reshape(-1, 2), z[py, px]


#: Page-wide pair histogram: bin size in mm.
PAIR_BIN_MM: float = 0.02


def pair_vector_peaks(xy_mm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Peaks of the histogram of difference vectors between dot
    candidates (every pair closer than ``AC_MAX_MM``), with Poisson z
    against the ring's mean count — the point-set autocorrelation over
    the whole page, blind to the window choice."""
    if len(xy_mm) < 3:
        return np.empty((0, 2)), np.empty(0)
    tree = cKDTree(xy_mm)
    pairs = tree.query_pairs(AC_MAX_MM, output_type="ndarray")
    if not len(pairs):
        return np.empty((0, 2)), np.empty(0)
    diff = xy_mm[pairs[:, 1]] - xy_mm[pairs[:, 0]]
    diff = np.concatenate([diff, -diff])
    n = int(np.ceil(AC_MAX_MM / PAIR_BIN_MM))
    edges = (np.arange(-n, n + 2) - 0.5) * PAIR_BIN_MM
    hist, _, _ = np.histogram2d(diff[:, 1], diff[:, 0], bins=[edges, edges])
    hist = ndimage.uniform_filter(hist, size=3) * 9.0
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1] * PAIR_BIN_MM
    rad = np.hypot(yy, xx)
    ring = (rad >= AC_MIN_MM) & (rad <= AC_MAX_MM)
    mean = max(float(hist[ring].mean()), 1e-9)
    z = (hist - mean) / np.sqrt(mean)
    foot = max(3, int(round(AC_FOOTPRINT_MM / PAIR_BIN_MM)) | 1)
    peaks = (hist == ndimage.maximum_filter(hist, size=foot)) & ring & (z > AC_PEAK_Z)
    py, px = np.nonzero(peaks)
    centres = np.column_stack([xx[py, px], yy[py, px]])
    # Sub-bin: the mean of the difference vectors near each bin peak.
    tree = cKDTree(diff)
    for k, near in enumerate(tree.query_ball_point(centres, 2.5 * PAIR_BIN_MM)):
        if near:
            centres[k] = diff[near].mean(axis=0)
    return centres, z[py, px]


#: Lattice from peaks: the strongest peaks kept (and their pairwise
#: differences, which are lattice vectors too), the shortest vector a
#: dot pair can span, and the share of strong peaks the basis must index.
GENERATOR_PEAKS: int = 24
GENERATOR_MIN_MM: float = 0.15
GENERATOR_INDEXED: float = 0.9
GENERATOR_TRIES: int = 200


def _refine(a: np.ndarray, b: np.ndarray, gen: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Least squares over the peaks a growing radius indexes: a basis
    read off one difference of two peaks is off by a few hundredths of a
    printer dot, which twenty sites out is a fifth of a site."""
    lengths = np.hypot(gen[:, 0], gen[:, 1])
    for radius_mm in (2.0, 4.0, 8.0):
        use = gen[lengths <= radius_mm]
        n = np.linalg.solve(np.column_stack([a, b]), use.T).T
        ok = np.all(np.abs(n - np.round(n)) < 0.3, axis=1)
        idx = np.round(n[ok])
        if len(idx) < 2 or np.linalg.matrix_rank(idx) < 2:
            continue
        sol, *_ = np.linalg.lstsq(idx, use[ok], rcond=None)
        a, b = sol[0], sol[1]
    return reduce_basis(a, b)


def _basis_from_pool(pool: np.ndarray, gen: np.ndarray
                     ) -> tuple[tuple[np.ndarray, np.ndarray] | None, tuple[np.ndarray, np.ndarray] | None]:
    """(accepted basis, best basis tried): the shortest pool vector and
    the first partner whose refined basis indexes ``GENERATOR_INDEXED``
    of the strong peaks."""
    if not len(pool):
        return None, None
    a = pool[0]
    best, best_frac = None, -1.0
    for cand in pool[1:GENERATOR_TRIES]:
        if abs(a[0] * cand[1] - a[1] * cand[0]) < 0.1 * np.hypot(*a) * np.hypot(*cand):
            continue
        ra, rb = _refine(*reduce_basis(a, cand), gen)
        n = np.linalg.solve(np.column_stack([ra, rb]), gen.T).T
        frac = float(np.mean(np.all(np.abs(n - np.round(n)) < 0.15, axis=1)))
        if frac >= GENERATOR_INDEXED:
            return (ra, rb), (ra, rb)
        if frac > best_frac:
            best, best_frac = (ra, rb), frac
    return None, best


def lattice_from_peaks(vectors: np.ndarray, z: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """The lattice generated by the strong peaks, reduced, then refined
    by least squares over every peak it indexes to within 0.15 of a site.

    Differences of peaks are lattice vectors as well: the Canon's sites
    are 6 x 12 printer dots apart but no two occupied sites are closer
    than 24 dots, so the shortest PEAK is a multiple of the site pitch
    and only a difference of two peaks shows the pitch itself."""
    if len(vectors) < 2:
        return None
    strong = np.flatnonzero(z >= max(AC_PEAK_Z, 0.1 * float(z.max())))
    strong = strong[np.argsort(z[strong])[::-1][:GENERATOR_PEAKS]]
    gen = vectors[strong]
    diffs = (gen[:, None, :] - gen[None, :, :]).reshape(-1, 2)
    pool = np.concatenate([gen, diffs])
    lengths = np.hypot(pool[:, 0], pool[:, 1])
    pool = pool[lengths >= GENERATOR_MIN_MM]
    pool = pool[np.argsort(np.hypot(pool[:, 0], pool[:, 1]))]
    if not len(pool):
        return None
    found = None
    for _ in range(3):
        found, best = _basis_from_pool(pool, gen)
        if found is not None or best is None:
            break
        # The best basis misses some strong peaks at simple fractions
        # (the HP's centred (18, 18) sites against peaks at (108, -54)
        # printer dots, a half-integer there): the lattice the peaks
        # generate is finer, so the fractional remainders join the pool.
        frac = np.linalg.solve(np.column_stack(best), gen.T).T
        miss = ~np.all(np.abs(frac - np.round(frac)) < 0.15, axis=1)
        rem = frac[miss] - np.floor(frac[miss])
        extra = (np.column_stack(best) @ rem.T).T
        pool = np.concatenate([extra, extra - best[0], extra - best[1], pool])
        pool = pool[np.hypot(pool[:, 0], pool[:, 1]) >= GENERATOR_MIN_MM]
        pool = pool[np.argsort(np.hypot(pool[:, 0], pool[:, 1]))]
    if found is None:
        return None
    a, b = found
    basis = np.column_stack([a, b])
    n = np.linalg.solve(basis, vectors.T).T
    good = np.all(np.abs(n - np.round(n)) < 0.15, axis=1)
    idx = np.round(n[good])
    if np.linalg.matrix_rank(idx) == 2:
        sol, *_ = np.linalg.lstsq(idx, vectors[good], rcond=None)
        a, b = reduce_basis(sol[0], sol[1])
    return a, b


@dataclass
class SiteFit:
    """Dots indexed onto lattice sites and the smooth site -> mm map."""

    a_mm: np.ndarray
    b_mm: np.ndarray
    ij: np.ndarray              # (n, 2) int site of each indexed dot
    xy_mm: np.ndarray           # (n, 2) dot centroid
    coef_x: np.ndarray          # poly2 coefficients, site -> x_mm
    coef_y: np.ndarray
    rms_mm: float
    n_rejected: int
    local_rms_mm: float = float("nan")

    def predict(self, i: np.ndarray, j: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        basis = _poly2(np.asarray(i, float), np.asarray(j, float))
        return basis @ self.coef_x, basis @ self.coef_y


def _poly2(i: np.ndarray, j: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones_like(i), i, j, i * i, i * j, j * j])


def index_sites(xy_mm: np.ndarray, a: np.ndarray, b: np.ndarray, seed: int) -> np.ndarray:
    """Breadth-first site indices from ``seed``; ``-2**31`` for dots the
    walk never reached or could not place on a site."""
    unset = np.iinfo(np.int64).min
    ij = np.full((len(xy_mm), 2), unset, np.int64)
    inv = np.linalg.inv(np.column_stack([a, b]))
    tree = cKDTree(xy_mm)
    radius = max(LINK_MIN_MM, LINK_SPACINGS * max(np.hypot(*a), np.hypot(*b)))
    ij[seed] = 0
    queue: deque[int] = deque([seed])
    while queue:
        p = queue.popleft()
        for q in tree.query_ball_point(xy_mm[p], radius):
            if ij[q, 0] != unset:
                continue
            frac = inv @ (xy_mm[q] - xy_mm[p])
            step = np.round(frac)
            if np.all(np.abs(frac - step) < LINK_TOLERANCE):
                ij[q] = ij[p] + step.astype(np.int64)
                queue.append(q)
    return ij


def best_seed(xy_mm: np.ndarray, a: np.ndarray, b: np.ndarray) -> int:
    """The dot with the most neighbours at near-integer lattice offsets,
    over the whole page (a paper speck has none; on the M681 the dots
    live only where its yellow prints, a third of the page)."""
    inv = np.linalg.inv(np.column_stack([a, b]))
    tree = cKDTree(xy_mm)
    link = max(LINK_MIN_MM, LINK_SPACINGS * max(np.hypot(*a), np.hypot(*b)))
    best, score = 0, -1
    for p, nb in enumerate(tree.query_ball_point(xy_mm, link)):
        nb = [q for q in nb if q != p]
        if not nb:
            continue
        frac = (inv @ (xy_mm[nb] - xy_mm[p]).T).T
        n = int(np.all(np.abs(frac - np.round(frac)) < LINK_TOLERANCE, axis=1).sum())
        if n > score:
            best, score = p, n
    return int(best)


def _fit(ij: np.ndarray, xy: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    basis = _poly2(ij[:, 0].astype(float), ij[:, 1].astype(float))
    coef_x, *_ = np.linalg.lstsq(basis, xy[:, 0], rcond=None)
    coef_y, *_ = np.linalg.lstsq(basis, xy[:, 1], rcond=None)
    resid = np.hypot(basis @ coef_x - xy[:, 0], basis @ coef_y - xy[:, 1])
    return coef_x, coef_y, resid


#: Gap bridging and the local check: an unindexed dot within
#: ``BRIDGE_MM`` of the indexed set is placed by an affine map fitted to
#: its ``LOCAL_NEIGHBOURS`` nearest indexed dots when it lands within
#: ``BRIDGE_TOLERANCE`` of a site; an indexed dot further than
#: ``LOCAL_TOLERANCE`` (in spacings of the finer axis) from where its
#: neighbours put its site is dropped.  Local, not page-wide: the Canon's
#: page is non-affine by more than its own 0.25 mm site pitch (e040).
BRIDGE_MM: float = 25.0
BRIDGE_TOLERANCE: float = 0.15
LOCAL_NEIGHBOURS: int = 8
LOCAL_TOLERANCE: float = 0.3


def _local_affine(ij_nb: np.ndarray, xy_nb: np.ndarray) -> np.ndarray | None:
    """Least-squares (3, 2) map [1, i, j] -> (x, y); None when degenerate."""
    design = np.column_stack([np.ones(len(ij_nb)), ij_nb.astype(float)])
    if np.linalg.matrix_rank(design) < 3:
        return None
    sol, *_ = np.linalg.lstsq(design, xy_nb, rcond=None)
    return sol


def _local_residuals(ij: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """Each dot's distance (mm) from where an affine map fitted to its
    nearest indexed neighbours (itself excluded) puts its site."""
    tree = cKDTree(xy)
    k = min(LOCAL_NEIGHBOURS + 1, len(xy))
    _, nbs = tree.query(xy, k=k)
    out = np.full(len(xy), np.inf)
    for n, nb in enumerate(nbs):
        nb = nb[nb != n]
        sol = _local_affine(ij[nb], xy[nb])
        if sol is not None:
            out[n] = float(np.hypot(*(np.array([1.0, *ij[n]]) @ sol - xy[n])))
    return out


def fit_sites(xy_mm: np.ndarray, a: np.ndarray, b: np.ndarray, seed: int) -> SiteFit:
    """Index the dots from ``seed`` (breadth-first, local links), bridge
    printed gaps with local affine maps — growing by at most
    ``BRIDGE_MM`` per round — drop dots their neighbours place off-site
    and keep one dot per site; then a page-wide quadratic site -> mm map
    for prediction (its rms is the page's non-affinity, reported)."""
    unset = np.iinfo(np.int64).min
    ij = index_sites(xy_mm, a, b, seed)
    keep = ij[:, 0] != unset
    if keep.sum() < 12:
        lin = np.zeros(6)
        return SiteFit(a_mm=a, b_mm=b, ij=ij[keep], xy_mm=xy_mm[keep], coef_x=lin,
                       coef_y=lin, rms_mm=float("nan"), n_rejected=int((~keep).sum()))
    fine = min(np.hypot(*a), np.hypot(*b))
    inv = np.linalg.inv(np.column_stack([a, b]))
    for _ in range(40):
        rest = np.flatnonzero(~keep)
        if not len(rest):
            break
        where = np.flatnonzero(keep)
        tree = cKDTree(xy_mm[where])
        dist, nbs = tree.query(xy_mm[rest], k=min(LOCAL_NEIGHBOURS, len(where)),
                               distance_upper_bound=BRIDGE_MM)
        added = 0
        for r, dr, nb in zip(rest, np.atleast_2d(dist), np.atleast_2d(nbs)):
            nb = nb[np.isfinite(dr)]
            if len(nb) < 4:
                continue
            sol = _local_affine(ij[where[nb]], xy_mm[where[nb]])
            if sol is None:
                continue
            try:
                frac = np.linalg.solve(sol[1:].T, xy_mm[r] - sol[0])
            except np.linalg.LinAlgError:
                continue
            # A string of near-collinear neighbours fits an ill-posed map:
            # the local answer must agree with the page basis to half a site.
            nearest = where[nb[0]]
            coarse = ij[nearest] + inv @ (xy_mm[r] - xy_mm[nearest])
            if np.any(np.abs(frac - coarse) > 0.5):
                continue
            if np.all(np.abs(frac - np.round(frac)) < BRIDGE_TOLERANCE):
                ij[r] = np.round(frac).astype(np.int64)
                keep[r] = True
                added += 1
        if not added:
            break
    where = np.flatnonzero(keep)
    resid = _local_residuals(ij[where], xy_mm[where])
    keep[where[resid > LOCAL_TOLERANCE * fine]] = False
    where = np.flatnonzero(keep)
    resid = _local_residuals(ij[where], xy_mm[where])
    # Two dots on one site (a speck beside a dot): keep the better placed.
    order = np.argsort(resid)
    _, first = np.unique(ij[where][order], axis=0, return_index=True)
    chosen = where[order][first]
    coef_x, coef_y, gresid = _fit(ij[chosen], xy_mm[chosen])
    return SiteFit(a_mm=a, b_mm=b, ij=ij[chosen], xy_mm=xy_mm[chosen], coef_x=coef_x,
                   coef_y=coef_y, rms_mm=float(np.sqrt(np.mean(gresid ** 2))),
                   n_rejected=int(len(xy_mm) - len(chosen)),
                   local_rms_mm=float(np.sqrt(np.mean(np.square(resid[np.isfinite(resid)])))))


@dataclass
class Occupancy:
    """The site matrix: 1 dot, 0 known empty, -1 unknown; ``origin`` is
    the (i, j) of element [0, 0]; rows run along j, columns along i."""

    matrix: np.ndarray
    origin: tuple[int, int]


def occupancy(fit: SiteFit, known_fn) -> Occupancy:
    """Every site in the indexed bounding box: occupied when a dot sits
    there, known-empty when ``known_fn(x_mm, y_mm)`` says blank paper and
    an indexed dot lies within ``KNOWN_RADIUS_MM``."""
    i0, j0 = fit.ij.min(axis=0)
    i1, j1 = fit.ij.max(axis=0)
    if (i1 - i0 + 1) * (j1 - j0 + 1) > MAX_SITES:
        raise ValueError(f"site index span {i1 - i0 + 1} x {j1 - j0 + 1} exceeds any page")
    ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
    x, y = fit.predict(ii.ravel(), jj.ravel())
    near = cKDTree(fit.xy_mm).query(np.column_stack([x, y]), distance_upper_bound=KNOWN_RADIUS_MM)[0]
    known = np.isfinite(near) & known_fn(x, y)
    mat = np.where(known, 0, -1).reshape(ii.shape).astype(np.int8)
    mat[fit.ij[:, 1] - j0, fit.ij[:, 0] - i0] = 1
    return Occupancy(matrix=mat, origin=(int(i0), int(j0)))


def _corr(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """``out[u, v] = sum p[y, x] q[y + v, x + u]`` for |u|,|v| < size."""
    h, w = p.shape
    s = (2 * h, 2 * w)
    out = np.fft.irfft2(np.conj(np.fft.rfft2(p, s=s)) * np.fft.rfft2(q, s=s), s=s)
    return np.round(np.fft.fftshift(out)).astype(np.int64)


@dataclass(frozen=True)
class Repeat:
    """The payload repeat: two site vectors and their agreement."""

    r1: tuple[int, int]
    r2: tuple[int, int]
    agreement: tuple[float, float]
    pairs: tuple[int, int]


def find_repeat(occ: Occupancy, a: np.ndarray, b: np.ndarray) -> tuple[Repeat | None, list[dict[str, object]]]:
    """Shifts ``(di, dj)`` where an occupied site's partner is occupied
    too (``P(1 | 1, known)``) at or above ``REPEAT_MIN_AGREEMENT``; the
    two shortest independent ones (in mm) span the repeat lattice."""
    m = occ.matrix
    one = (m == 1).astype(float)
    known = (m >= 0).astype(float)
    n11 = _corr(one, one)
    n1k = _corr(one, known)
    h, w = m.shape
    cy, cx = h, w
    lim_i = min(w - 1, int(REPEAT_MAX_MM / np.hypot(*a)))
    lim_j = min(h - 1, int(REPEAT_MAX_MM / np.hypot(*b)))
    cands = []
    for dj in range(0, lim_j + 1):
        for di in range(-lim_i, lim_i + 1):
            if dj == 0 and di <= 0:
                continue
            pairs = int(n1k[cy + dj, cx + di])
            if pairs < REPEAT_MIN_PAIRS:
                continue
            agree = n11[cy + dj, cx + di] / pairs
            if agree >= REPEAT_MIN_AGREEMENT:
                vec = di * a + dj * b
                cands.append((float(np.hypot(*vec)), di, dj, float(agree), pairs))
    cands.sort()
    table = [{"di": di, "dj": dj, "len_mm": round(ln, 3), "agreement": round(ag, 4), "pairs": pr}
             for ln, di, dj, ag, pr in cands[:12]]
    if not cands:
        return None, table
    first = cands[0]
    for cand in cands[1:]:
        if first[1] * cand[2] - first[2] * cand[1] != 0:
            return Repeat(r1=(first[1], first[2]), r2=(cand[1], cand[2]),
                          agreement=(first[3], cand[3]), pairs=(first[4], cand[4])), table
    return None, table


def hermite_cell(r1: tuple[int, int], r2: tuple[int, int]) -> tuple[int, int, int]:
    """``(a, b, c)``: the repeat lattice is spanned by ``(a, 0)`` and
    ``(b, c)`` in (i, j) with ``0 <= b < a`` — an ``a`` x ``c`` cell whose
    rows wrap with an i-shift of ``b``."""
    (x1, y1), (x2, y2) = r1, r2
    det = abs(x1 * y2 - x2 * y1)
    if det == 0:
        raise ValueError("repeat vectors are dependent")
    g, s, t = _ext_gcd(y1, y2)
    c = abs(g)
    bx = s * x1 + t * x2
    if g < 0:
        bx = -bx
    a = det // c
    return a, bx % a, c


def best_cell(r1: tuple[int, int], r2: tuple[int, int]) -> tuple[tuple[int, int, int], bool]:
    """The squarer of the two Hermite cells — wrapping along rows, or
    (``transposed``) along columns; the same lattice either way."""
    plain = hermite_cell(r1, r2)
    swapped = hermite_cell((r1[1], r1[0]), (r2[1], r2[0]))
    ratio = lambda cell: max(cell[0], cell[2]) / min(cell[0], cell[2])  # noqa: E731
    return (swapped, True) if ratio(swapped) < ratio(plain) else (plain, False)


def _ext_gcd(p: int, q: int) -> tuple[int, int, int]:
    if q == 0:
        return p, 1, 0
    g, s, t = _ext_gcd(q, p % q)
    return g, t, s - (p // q) * t


def fold_coords(i: np.ndarray, j: np.ndarray, cell: tuple[int, int, int],
                transposed: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Site -> (column, row) in the ``a`` x ``c`` cell; ``transposed``
    swaps the roles of i and j (and the returned pair is then
    (row, column) in page orientation)."""
    if transposed:
        i, j = j, i
    a, b, c = cell
    k = np.floor_divide(j, c)
    row = j - k * c
    col = np.mod(i - k * b, a)
    return col, row


@dataclass
class FoldedCell:
    """Majority vote of every observed repeat, per cell site."""

    cell: tuple[int, int, int]
    transposed: bool
    ones: np.ndarray            # (c, a) count of dot observations
    seen: np.ndarray            # (c, a) count of known observations

    @property
    def value(self) -> np.ndarray:
        out = np.full(self.ones.shape, -1, np.int8)
        k = self.seen > 0
        out[k] = (2 * self.ones[k] > self.seen[k]).astype(np.int8)
        return out

    @property
    def page_value(self) -> np.ndarray:
        """The cell with rows along j and columns along i (the capture's
        orientation), whichever way it wraps."""
        return self.value.T if self.transposed else self.value

    @property
    def consistency(self) -> float:
        k = self.seen > 0
        agree = np.where(2 * self.ones > self.seen, self.ones, self.seen - self.ones)
        return float(agree[k].sum() / max(1, self.seen[k].sum()))

    def key(self, i: np.ndarray, j: np.ndarray) -> np.ndarray:
        col, row = fold_coords(np.asarray(i), np.asarray(j), self.cell, self.transposed)
        return row * self.cell[0] + col

    def at(self, i: np.ndarray, j: np.ndarray) -> np.ndarray:
        col, row = fold_coords(np.asarray(i), np.asarray(j), self.cell, self.transposed)
        return self.value[row, col]


def fold(occ: Occupancy, cell: tuple[int, int, int], transposed: bool = False) -> FoldedCell:
    m = occ.matrix
    jj, ii = np.nonzero(m >= 0)
    col, row = fold_coords(ii + occ.origin[0], jj + occ.origin[1], cell, transposed)
    a, _, c = cell
    ones = np.zeros((c, a), np.int64)
    seen = np.zeros((c, a), np.int64)
    np.add.at(seen, (row, col), 1)
    np.add.at(ones, (row, col), (m[jj, ii] == 1).astype(np.int64))
    return FoldedCell(cell=cell, transposed=transposed, ones=ones, seen=seen)
