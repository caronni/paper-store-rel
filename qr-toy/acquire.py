"""Toy image acquisition: ink components, quadrilaterals, known-cell poses.

All coordinates here are image x,y with cell boundaries at 0 and 64.
Payload content is never an input to this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage, optimize, spatial

from holo.receiver.plugins import survey

Log = Callable[[str, str], None]
BOUNDARY = np.array([[0., 0.], [64., 0.], [64., 64.], [0., 64.]])


@dataclass
class Pose:
    quad: np.ndarray
    loss: float
    errors: int
    rotation: int
    mirrored: bool
    candidate: int


def homography(quad: np.ndarray) -> np.ndarray:
    if quad.shape != (4, 2) or not np.isfinite(quad).all():
        raise ValueError("pose needs four finite corners")
    rows, values = [], []
    for (x, y), (u, v) in zip(BOUNDARY, quad):
        rows.extend([
            [x, y, 1, 0, 0, 0, -u * x, -u * y],
            [0, 0, 0, x, y, 1, -v * x, -v * y],
        ])
        values.extend([u, v])
    return np.append(np.linalg.solve(rows, values), 1.).reshape(3, 3)


def project(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    p = np.concatenate((points, np.ones((*points.shape[:-1], 1))), axis=-1)
    q = p @ matrix.T
    return q[..., :2] / q[..., 2:]


def sample(
    image: np.ndarray, matrix: np.ndarray, points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    xy = project(matrix, points)
    valid = (np.isfinite(xy).all(axis=-1) & (xy[..., 0] >= 0)
             & (xy[..., 1] >= 0) & (xy[..., 0] <= image.shape[1] - 1)
             & (xy[..., 1] <= image.shape[0] - 1))
    values = ndimage.map_coordinates(
        image, [xy[..., 1], xy[..., 0]], order=1, mode="constant", cval=1.,
    )
    return values, valid


def read_image(
    path: Path, max_side: int, flatten: bool, radial_k1: float, log: Log,
) -> tuple[np.ndarray, np.ndarray]:
    with Image.open(path) as opened:
        im = ImageOps.exif_transpose(opened)
        if "A" in im.getbands() or "transparency" in im.info:
            rgba = im.convert("RGBA")
            im = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba)
        im = im.convert("RGB")
        original_size = im.size
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        rgb = np.asarray(im).copy()
        grey = np.asarray(im.convert("L"), dtype=np.float32) / 255.
    log("input", f"{original_size[0]}x{original_size[1]} -> "
        f"working {im.width}x{im.height}; EXIF orientation applied; EXIF DPI ignored")
    if radial_k1:
        yy, xx = np.indices(grey.shape, dtype=np.float32)
        cy, cx = (np.array(grey.shape) - 1) / 2
        radius_px = max(grey.shape) / 2
        x, y = (xx - cx) / radius_px, (yy - cy) / radius_px
        factor = 1 + radial_k1 * (x * x + y * y)
        coordinates = [cy + y * factor * radius_px, cx + x * factor * radius_px]
        grey = ndimage.map_coordinates(grey, coordinates, order=1, cval=1.)
        rgb = np.stack([
            ndimage.map_coordinates(rgb[..., k], coordinates, order=1, cval=255)
            for k in range(3)
        ], axis=-1)
        log("optics", f"explicit radial pullback k1={radial_k1:g}; "
            "source radius = output radius*(1+k1*r²)")
    if flatten:
        # A deliberately optional illumination-only correction, before segmentation.
        background = ndimage.maximum_filter(grey, size=max(9, min(grey.shape) // 24))
        background = ndimage.gaussian_filter(background, max(2, min(grey.shape) / 100))
        grey = np.clip(grey / np.maximum(background, .05), 0, 1)
        log("optics", "local white-background normalization enabled before segmentation")
    return grey, rgb


def threshold(image: np.ndarray) -> float:
    hist, edges = np.histogram(image, bins=256, range=(0, 1))
    p = hist.astype(float) / image.size
    weight = np.cumsum(p)
    mean = np.cumsum(p * np.arange(256))
    score = (mean[-1] * weight - mean)**2 / np.maximum(weight * (1 - weight), 1e-12)
    return float(edges[int(np.argmax(score)) + 1])


def quadrilateral(xy: np.ndarray) -> np.ndarray:
    hull = xy[spatial.ConvexHull(xy).vertices]
    if len(hull) < 4:
        raise ValueError("ink envelope has fewer than four corners")
    envelope = hull.copy()
    # Simplify the convex ink envelope to its four dominant corners. This
    # gives a pose proposal only; all acceptance is downstream from pixels.
    while len(hull) > 4:
        a, b = hull - np.roll(hull, 1, axis=0), np.roll(hull, -1, axis=0) - hull
        areas = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
        hull = np.delete(hull, int(np.argmin(areas)), axis=0)
    centre = hull.mean(axis=0)
    hull = hull[np.argsort(np.arctan2(hull[:, 1] - centre[1], hull[:, 0] - centre[0]))]
    hull = np.roll(hull, -int(np.argmin(hull.sum(axis=1))), axis=0)
    # A corner cell may be white. Recover intersections of the long outer
    # edges instead of treating the nearest black corner as the tile corner.
    starts, ends = envelope, np.roll(envelope, -1, axis=0)
    vectors = ends - starts
    lengths = np.linalg.norm(vectors, axis=1)
    lines = []
    for a, b in zip(hull, np.roll(hull, -1, axis=0)):
        direction = (b - a) / np.linalg.norm(b - a)
        normal = np.array([-direction[1], direction[0]])
        aligned = np.abs(vectors @ direction) / lengths > np.cos(np.deg2rad(12))
        nearby = np.abs(((starts + ends) / 2 - a) @ normal) < .08 * np.linalg.norm(b - a)
        keep = aligned & nearby
        if not keep.any():
            lines.append((normal, normal @ a))
            continue
        points = np.concatenate((starts[keep], ends[keep]))
        weights = np.tile(lengths[keep], 2)
        centre_line = np.average(points, axis=0, weights=weights)
        delta = points - centre_line
        covariance = (delta * weights[:, None]).T @ delta
        _, axes = np.linalg.eigh(covariance)
        normal = axes[:, 0]
        lines.append((normal, normal @ centre_line))
    hull = np.array([
        np.linalg.solve(
            np.array([lines[i - 1][0], lines[i][0]]),
            np.array([lines[i - 1][1], lines[i][1]]),
        )
        for i in range(4)
    ])
    centre = hull.mean(axis=0)
    # Ink samples are pixel centres, whereas the mapping uses cell boundaries.
    return centre + (hull - centre) * (1 + 1 / max(np.ptp(hull, axis=0)))


def segment(
    image: np.ndarray, max_candidates: int, log: Log,
) -> tuple[np.ndarray, list[np.ndarray]]:
    cut = threshold(image)
    ink = image < cut
    if np.std(image) < .015 or not ink.any() or ink.all():
        raise ValueError("no usable black/white contrast")
    black = float(np.percentile(image[ink], 20))
    white = float(np.percentile(image[~ink], 60))
    if white - black < .05:
        raise ValueError("insufficient ink/background separation")
    normalized = np.clip((image - black) / (white - black), 0, 1)
    proposals: list[tuple[int, np.ndarray]] = []
    for radius in (3, 7, 15):
        joined = ndimage.maximum_filter(ink, size=2 * radius + 1)
        labels, _ = ndimage.label(joined)
        for number, bounds in enumerate(ndimage.find_objects(labels), 1):
            if bounds is None:
                continue
            h, w = [s.stop - s.start for s in bounds]
            if min(h, w) < 96 or max(h, w) / min(h, w) > 2.5:
                continue
            local = ink[bounds] & (labels[bounds] == number)
            density = np.count_nonzero(local) / (h * w)
            if not .12 < density < .85:
                continue
            # Component boundary is enough for the hull; keep actual ink pixels.
            edge = local & ~ndimage.binary_erosion(local)
            yy, xx = np.nonzero(edge)
            xy = np.column_stack((xx + bounds[1].start, yy + bounds[0].start))
            try:
                quad = quadrilateral(xy)
            except (spatial.QhullError, ValueError, np.linalg.LinAlgError):
                continue
            if any(
                np.linalg.norm(quad.mean(0) - q.mean(0)) < .1 * min(h, w)
                and abs(np.ptp(quad, axis=0).max() / np.ptp(q, axis=0).max() - 1) < .2
                for _, q in proposals
            ):
                continue
            proposals.append((len(xx), quad))
    proposals.sort(key=lambda item: item[0], reverse=True)
    quads = [q for _, q in proposals[:max_candidates]]
    log("segment", f"toy ink-envelope proposals={len(quads)}; "
        f"threshold={cut:.3f}, black={black:.3f}, white={white:.3f}")
    if not quads:
        raise ValueError("no plausible complete tile component (need about 96+ pixels across)")
    return normalized, quads


def production_survey(
    image: np.ndarray, quad: np.ndarray, pitch: Fraction, log: Log,
) -> tuple[np.ndarray, np.ndarray, int]:
    # Rectify BEFORE the existing survey: the phone's projective image has
    # no single physical DPI. This synthetic sampling grid has a known one.
    side, border, samples_per_cell = 576, 32, 8
    yy, xx = np.indices((side, side), dtype=float)
    points = np.stack((
        (xx - border + .5) / samples_per_cell,
        (yy - border + .5) / samples_per_cell,
    ), axis=-1)
    rectified, _ = sample(image, homography(quad), points)
    dpi = samples_per_cell / float(pitch)
    view = survey.NativeView(dpi, rectified.shape, (rectified.astype(np.float32),))
    result = survey.survey_view(view, pitch)
    regions, voted, measured, score, _ = result
    log("survey", "production survey after coarse perspective rectification: "
        f"{len(regions)} regions; vote={voted}; measured px/cell={measured}; "
        f"normalized dpi={dpi:g}")
    return rectified, score, len(regions)


def find_poses(
    image: np.ndarray, quad: np.ndarray, known_xy: np.ndarray,
    labels: np.ndarray, radius: float, candidate: int, log: Log,
) -> list[Pose]:
    target = 1 - labels.astype(float)
    shifts = np.arange(-radius, radius + .001, .5)
    sx, sy, scale = np.meshgrid(shifts, shifts, [.96, 1., 1.04], indexing="ij")
    offsets = np.column_stack((sx.ravel(), sy.ravel()))
    scales = scale.ravel()
    points = (known_xy[None, :, :] - 32) * scales[:, None, None] + 32 + offsets[:, None, :]
    pitch_px = np.mean(np.linalg.norm(np.roll(quad, -1, axis=0) - quad, axis=1)) / 64
    smooth = ndimage.gaussian_filter(image, max(.4, pitch_px * .30))
    finalists: list[Pose] = []
    for mirrored in (False, True):
        base = quad[[1, 0, 3, 2]] if mirrored else quad
        for rotation in range(4):
            matrix = homography(np.roll(base, -rotation, axis=0))
            values, valid = sample(smooth, matrix, points)
            loss = np.mean((values - target)**2, axis=1) + np.mean(~valid, axis=1)
            best = int(np.argmin(loss))
            shifted = (BOUNDARY - 32) * scales[best] + 32 + offsets[best]
            seed_quad = project(matrix, shifted)

            def residual(delta: np.ndarray) -> np.ndarray:
                q = seed_quad + delta.reshape(4, 2) * pitch_px
                v, observed = sample(smooth, homography(q), known_xy)
                return np.where(observed, v - target, 1.)

            # Cell-sized finite differences keep the derivative meaningful
            # on nearly piecewise-constant laser rasters.
            def jacobian(delta: np.ndarray) -> np.ndarray:
                step = .04
                return np.column_stack([
                    (residual(delta + np.eye(8)[i] * step)
                     - residual(delta - np.eye(8)[i] * step)) / (2 * step)
                    for i in range(8)
                ])

            try:
                fitted = optimize.least_squares(
                    residual, np.zeros(8), jac=jacobian, bounds=(-radius, radius),
                    loss="soft_l1", f_scale=.2, max_nfev=60,
                )
                fitted_quad = seed_quad + fitted.x.reshape(4, 2) * pitch_px
                v, observed = sample(image, homography(fitted_quad), known_xy)
            except (ValueError, np.linalg.LinAlgError) as exc:
                log("pose", f"candidate {candidate}, rotation={rotation * 90}°, "
                    f"mirror={mirrored}: invalid refinement: {exc}")
                continue
            errors = int(np.count_nonzero(((v < .5) != labels) | ~observed))
            final_loss = float(np.mean((v - target)**2) + np.mean(~observed))
            finalists.append(Pose(
                fitted_quad, final_loss, errors, rotation, mirrored, candidate,
            ))
            log("pose", f"candidate {candidate}, rotation={rotation * 90}°, "
                f"mirror={mirrored}: coarse loss={loss[best]:.4f}, "
                f"fitted={final_loss:.4f}, known-cell errors={errors}/103, "
                f"evaluations={fitted.nfev}")
    return sorted(finalists, key=lambda p: (p.errors, p.loss))


def cell_samples(
    image: np.ndarray, quad: np.ndarray, aperture: float,
) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.indices((64, 64), dtype=float)
    centres = np.stack((xx + .5, yy + .5), axis=-1)
    matrix = homography(quad)
    means = np.zeros((64, 64))
    observed = np.ones((64, 64), bool)
    for dx in (-aperture, 0, aperture):
        for dy in (-aperture, 0, aperture):
            value, valid = sample(image, matrix, centres + (dx, dy))
            means += value / 9
            observed &= valid
    return means.ravel().astype(np.float32), observed.ravel()
