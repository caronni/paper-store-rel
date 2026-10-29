"""Existence probe for `tiles.planek`, with the arm-off control.

Renders the colour sim's real emitted page with ONE plane's ink
displaced over a column band (`planek_fixture`), runs the ordinary
colour path to establish a certificate frontier, and then offers the
residue to the production row's own job body.

    off      the ordinary colour head, same 150-iteration budget
    planek   `plane_k.planek_job`, unchanged
    null     the same evidence, decoded at the WRONG address

The control is the point.  A tier that simply re-attempts the residue
with a frontier it did not have the first time gains certificates for a
reason that is NOT the arm.  Here `off` and `planek` see the identical
frontier and the identical residue and differ only in how the decoder
input was built.

The null tier is the correctness bar and it is unconditional: a tile's
flat cell index is `(y % 64) * 64 + (x % 64)`, so relabelling a
neighbour's cut changes nothing about the LLR field — only the ADDRESS
it is decoded under, and with it the slot permutation, the AES dither
and the metadata equation.  Well-calibrated evidence at the wrong
address must never certify.

Usage:

    PYTHONPATH=src:. env/bin/python measure/planek_existence.py \
        <page000_gt.npy> [plane] [shift_px] [noise_sd] [jitter_sd]
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from dataclasses import replace as dc_replace
from pathlib import Path

import numpy as np

from holo.receiver.plugins import plane_k

sys.path.insert(0, str(Path(__file__).resolve().parent))

import planek_fixture as fixture  # noqa: E402
import uplift_existence as ordinary  # noqa: E402

#: the null tier decodes each tile from its right-hand neighbour's cut
NULL_OFFSET: tuple[int, int] = (0, 1)


def lane_plan(channel: fixture.PlaneChannel, windows, places, planes,
              field=None) -> plane_k.LanePlan:
    return plane_k.LanePlan(
        lane=(fixture.CAPTURE_ID, fixture.LEVEL_INDEX),
        windows=tuple(windows), placements=tuple(places),
        region_indices=tuple(0 for _window in windows),
        planes=planes, field=field)


def band_field(channel: fixture.PlaneChannel, delta_dots: float):
    """A standing page field that already knows the band's displacement.

    The delta and its support are published on the BAND tiles only,
    which is the shape a real solve produces: a tile no evidence ever
    reached reads exactly zero, and zero means "sample at the pose".
    So the band windows sweep AROUND the fit and the clean ones sweep
    around zero, which is the order the row declares since 2026-09-07.
    """
    from holo.receiver.data import PlaneField

    side = channel.tiles_side
    delta = np.zeros((side, side, 2), np.float64)
    support = np.zeros((side, side), np.float64)
    for ty, tx in fixture.band_tiles(channel):
        delta[ty, tx, 0] = delta_dots
        support[ty, tx] = 1.0
    return PlaneField(
        page=0, plane=channel.plane, delta_dots_xy=delta, support=support,
        uncertainty_dots=np.zeros_like(support),
        n_observations=int(support.sum()), n_captures=1, ordinal=1)


def true_delta_dots(row: object, channel: fixture.PlaneChannel) -> float:
    """The fixture's displacement expressed in printed dots."""
    from holo.receiver.plugins import color_region

    return (float(channel.shift_px) / fixture.PPC
            * color_region.cell_dots_of(row))


def stream_of_plane(row: object, plane: int) -> str:
    return next(fact.stream_id for fact in row.streams
                if int(fact.plane) == plane)


def run_planek(row, geometry, plan, certificates, targets, plane,
               misaddress: tuple[int, int] | None = None) -> dict:
    """The production job body over a residue, or its false-accept probe."""
    stream_id = stream_of_plane(row, plane)
    gained: dict = {}
    for ty, tx in targets:
        if misaddress is None:
            result = plane_k.planek_job(row, geometry, (plan,),
                                        certificates, 0, ty, tx, stream_id,
                                        plane)
            facts = result.facts
        else:
            source = (ty + misaddress[0], tx + misaddress[1])
            cut = plane_k.lane_cut(row, geometry, plan, certificates, 0,
                                   source[0], source[1], plane)
            if cut is None:
                continue
            relabelled = dc_replace(cut, ty=ty, tx=tx)
            facts, _events = plane_k.attempt_components(
                row, geometry, (relabelled,), stream_id)
        for fact in facts:
            if hasattr(fact, "user_bits"):
                gained[(0, ty, tx, stream_id)] = fact
    return gained


def offset_sources(row, geometry, plan: plane_k.LanePlan, certificates,
                   plane: int) -> tuple[tuple[int, str, float], ...]:
    """Where each window's sampling offset came from, and what it was.

    The row's own lane read, so the report says whether the standing
    field was consulted or the blind estimator ran — the declared order
    observed rather than asserted.
    """
    read = plane_k.lane_read(row, geometry, plan, certificates, plane)
    return () if read is None else read.offsets


def residue_of(row, frontier, tiles_side: int, plane: int,
               ) -> tuple[tuple[int, int], ...]:
    stream_id = stream_of_plane(row, plane)
    return tuple((ty, tx) for ty in range(tiles_side)
                 for tx in range(tiles_side)
                 if (0, ty, tx, stream_id) not in frontier)


def certified_in(frontier, row, plane: int,
                 addresses: tuple[tuple[int, int], ...]) -> int:
    stream_id = stream_of_plane(row, plane)
    return sum(1 for ty, tx in addresses
               if (0, ty, tx, stream_id) in frontier)


def probe(gt_path: Path, channel: fixture.PlaneChannel,
          with_field: bool = False) -> dict:
    row, geometry = fixture.format_row_and_geometry()
    bits = fixture.page_bits(gt_path, row)
    image = fixture.render(bits, channel)
    windows = fixture.region_windows(row, channel)
    places = fixture.placements(channel)
    streams = tuple(stream.stream_id for stream in row.streams)
    every = tuple((ty, tx, streams) for ty in range(channel.tiles_side)
                  for tx in range(channel.tiles_side))
    with tempfile.TemporaryDirectory() as tmp:
        planes = fixture.plane_rasters(image, Path(tmp))
        frontier, _v, _i, _s = ordinary.run_tier(
            row, geometry, windows, planes, {}, every, ordinary.ARM_OFF,
            None)
        residue_streams = tuple(
            entry for entry in (
                (ty, tx, tuple(name for name in streams
                               if (0, ty, tx, name) not in frontier))
                for ty, tx, _s in every)
            if entry[2])
        control, _v, _i, _s = ordinary.run_tier(
            row, geometry, windows, planes, dict(frontier), residue_streams,
            ordinary.ARM_OFF, None)
        field = (band_field(channel, true_delta_dots(row, channel))
                 if with_field else None)
        plan = lane_plan(channel, windows, places, planes, field)
        targets = residue_of(row, frontier, channel.tiles_side,
                             channel.plane)
        sources = offset_sources(row, geometry, plan, dict(frontier),
                                 channel.plane)
        gained = run_planek(row, geometry, plan, dict(frontier), targets,
                            channel.plane)
        null = run_planek(row, geometry, plan, dict(frontier), targets,
                          channel.plane, NULL_OFFSET)
    everything = dict(frontier)
    everything.update(control)
    everything.update(gained)
    wrong = 0
    for ty in range(channel.tiles_side):
        for tx in range(channel.tiles_side):
            wrong += fixture.audit_certificate(
                row, geometry, everything, bits, 0, ty, tx)
    band = fixture.band_tiles(channel)
    clean = tuple(address for address in
                  ((ty, tx) for ty in range(channel.tiles_side)
                   for tx in range(channel.tiles_side))
                  if address not in set(band))
    return {
        "frontier": frontier, "control": control, "gained": gained,
        "null": null, "targets": targets, "wrong": wrong,
        "offset_sources": sources,
        "band": band, "clean": clean, "bits": bits, "row": row,
        "geometry": geometry,
        "band_certified": certified_in(frontier, row, channel.plane, band),
        "clean_certified": certified_in(frontier, row, channel.plane, clean),
    }


def main() -> int:
    gt_path = Path(sys.argv[1])
    channel = fixture.PlaneChannel()
    if len(sys.argv) > 2:
        channel = replace(channel, plane=int(sys.argv[2]))
    if len(sys.argv) > 3:
        channel = replace(channel, shift_px=float(sys.argv[3]))
    if len(sys.argv) > 4:
        channel = replace(channel, noise_sd=float(sys.argv[4]))
    if len(sys.argv) > 5:
        channel = replace(channel, plane_jitter_sd=float(sys.argv[5]))
    if len(sys.argv) > 6:
        channel = replace(channel, absorption=float(sys.argv[6]))
    with_field = len(sys.argv) > 7 and sys.argv[7] == "field"
    report = probe(gt_path, channel, with_field)
    row = report["row"]
    n_tiles = channel.tiles_side * channel.tiles_side
    print(f"channel plane={channel.plane} shift_px={channel.shift_px} "
          f"noise_sd={channel.noise_sd} absorption={channel.absorption} "
          f"jitter={channel.plane_jitter_sd}")
    print(f"tiles {channel.tiles_side}x{channel.tiles_side}  "
          f"windows {channel.windows_side}x{channel.windows_side}  "
          f"band tiles {len(report['band'])}")
    print(f"ordinary frontier        {len(report['frontier'])}"
          f"/{n_tiles * len(row.streams)}")
    print(f"  target plane on band   {report['band_certified']}"
          f"/{len(report['band'])}")
    print(f"  target plane off band  {report['clean_certified']}"
          f"/{len(report['clean'])}")
    print(f"target-plane residue     {len(report['targets'])}")
    print(f"  tier off   gained      {len(report['control'])}")
    print(f"  tier planek gained     {len(report['gained'])}")
    print(f"  tier null  gained      {len(report['null'])}   "
          f"(must be 0)")
    print(f"wrong certified bits     {report['wrong']}")
    for ordinal, source, shift in report["offset_sources"]:
        print(f"  window {ordinal} offset {source:<12} {shift:+.2f} dots")
    if report["gained"]:
        print("planek certificates: "
              + ", ".join(f"({ty},{tx})" for _p, ty, tx, _s
                          in sorted(report["gained"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
