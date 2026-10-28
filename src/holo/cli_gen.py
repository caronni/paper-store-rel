"""Generation-side holo commands: registry | fit | capacity | generate.

Split out of cli.py at the FORMAT-SPACE P6 seam (the 1000-line signal):
cli.py keeps the parser, dispatch, and the decode session; this module
holds the emission-side command implementations.  No behavior change —
pure extraction.
"""
from __future__ import annotations

import json
from pathlib import Path

from holo.devices.profiles import PROFILES, get_profile, make_spec
from holo.devices.registry import PRINTERS, SCANNERS
from holo.format.descriptor import CODINGS
from holo.format.lattice import (display_pitch_token, parse_format_id,
                                 parse_pitch)
from holo.format.profiles import Family
from holo.gen.emit import default_out_dir, emit_volume
from holo.gen.plan import max_payload_bytes, plan_volume, pooled_plane_tier
from holo.gen.sheet import (
    DEFAULT_ENGINE_DPI,
    DEFAULT_PAPER,
    PAPER_PROFILES,
    dots_per_cell,
    fit,
    get_paper,
    page_dots_xy,
    sheet_layout,
    usable_dots_xy,
)

_SOURCE_FRACTION_HELP = (
    "fraction of printed tiles that carry SOURCE data; the rest are "
    "repair (fountain redundancy). 0.5 means any ~half of the printed "
    "tiles recovers the whole payload; lower = more robust, less "
    "capacity. Profiles set this — override it only when you know why.")


def _resolve_spec_q(args) -> tuple:
    """(spec, q, profile, sheet) from the mutually exclusive selectors.

    ``sheet`` is the v2 emission placement (paper x engine grid), or None
    for a legacy row, whose page geometry comes from the printer registry.
    """
    if args.format:
        if args.profile or args.coding:
            raise SystemExit(
                "--format is the whole identity (coding x tile matrix); "
                "it does not combine with --profile/--coding")
        if args.printer:
            raise SystemExit(
                "--format takes its paper from --paper and its engine grid "
                "from --dpi; printers are not part of the v2 generation "
                "path (FORMAT-SPACE §9)")
        if args.source_fraction is None:
            raise SystemExit("--format needs an explicit --source-fraction")
        try:
            spec = parse_format_id(args.format)
            sheet = sheet_layout(
                spec,
                DEFAULT_PAPER if args.paper is None else args.paper,
                DEFAULT_ENGINE_DPI if args.dpi is None else args.dpi)
        except (KeyError, ValueError) as exc:
            raise SystemExit(str(exc))
        return spec, args.source_fraction, None, sheet
    if args.paper is not None or args.dpi is not None:
        raise SystemExit(
            "--paper/--dpi place a v2 --format field on paper; a "
            "--profile/--coding row derives its page from --printer")
    if args.profile and args.source_fraction is not None:
        raise SystemExit(
            "--profile fixes the source fraction; for custom parameters "
            "use --coding ID --source-fraction Q instead (the result is "
            "then recorded as 'custom', carrying no profile evidence)")
    printer = args.printer or "default"
    if args.profile:
        p = get_profile(args.profile)
        return make_spec(p.coding_id, printer), p.source_fraction_q, p, None
    if args.coding:
        if args.source_fraction is None:
            raise SystemExit("--coding needs an explicit --source-fraction")
        return make_spec(args.coding, printer), args.source_fraction, \
            None, None
    raise SystemExit("pick --format ID (the v2 lattice), --profile NAME or "
                     "--coding ID (see `registry` for the legacy lists)")


def _coding_detail(c) -> None:
    from holo.core import bch
    from holo.format import pilots
    cell_um = c.cell_dots * 25.4e3 / 600
    tile_mm = 64 * cell_um / 1000
    print(f"      cell {cell_um:.0f}um ({c.cell_dots}x{c.cell_dots} dots "
          f"@600dpi), tile 64x64 cells = {tile_mm:.2f}mm square")
    if c.codec_family is Family.K:
        print(
            f"      inner FEC: e-IRA LDPC n=4096 "
            f"k={4096 - c.ldpc_parity_bits}"
            f" ({c.rate_id}), shortened by the {c.n_sites} site cells; "
            f"CRC-32 certifies each tile")
    else:
        print(
            f"      provisional color codec {c.codec_id}: "
            f"{'/'.join(c.codec.state_names)}; "
            f"{c.payload_cells} payload cells, streams "
            f"{'/'.join(c.stream_ids)}")
        for stream in c.stream_profiles:
            children = ", ".join(
                f"{child.code_id}/s{child.shortened_info_tail}"
                for child in stream.fec.children)
            print(
                f"        {stream.stream_id}: {stream.symbol_bits} symbol "
                f"bits + metadata + CRC, FEC bank {children}")
    print(f"      address word: BCH({bch.N_FULL},{bch.K_FULL},t={bch.T})->"
          f"({bch.N_WORD},{bch.K_MSG}) d>={bch.D_MIN} on the 100 pilot "
          f"sites; message = {pilots.COUNTER_BITS}-bit tile counter + "
          f"{pilots.PAD_BITS} known-zero pads")
    if c.codec_family is Family.K:
        print(f"      pilot density {100 * c.pilot_density:.2f}% "
              f"(floor; filler rungs would add sites), family seed "
              f"{c.family_seed.decode()}")
    else:
        print(
            f"      known-furniture density "
            f"{100 * c.pilot_density:.2f}% "
            f"(100 word + {c.n_dust} dust), family seed "
            f"{c.family_seed.decode()}")
    print("      metadata sidechannel: 1 LDPC user bit/tile, 24-bit word "
          "[version:1][K:18][reserved:5], counter-addressed GF(2) "
          "equations (rank 24; trust after 48 distinct tiles)")


def _printer_detail(p) -> None:
    if p.print_path:
        print(f"      print path: {p.print_path}")
    for n in p.notes:
        print(f"      note: {n}")
    print(f"      derived geometry on {p.media_ids[0]} "
          f"@ {p.payload_safe_margin_mm}mm margins:")
    for cid in sorted(CODINGS):
        spec = make_spec(cid, p)
        lay = spec.layout
        raw_kb = spec.tiles_per_page * spec.aggregate_symbol_bits / 8192
        print(f"        {spec.display_id}: field "
              f"{lay.cells_yx[0]}x{lay.cells_yx[1]} cells = "
              f"{lay.tiles_yx[0]}x{lay.tiles_yx[1]} tiles "
              f"({spec.tiles_per_page}/page), borders t/b/l/r "
              f"{lay.border_top_mm:.2f}/{lay.border_bottom_mm:.2f}/"
              f"{lay.border_left_mm:.2f}/{lay.border_right_mm:.2f}mm, "
              f"max {spec.max_pages} pages/volume, "
              f"{raw_kb:.0f} KiB/page before redundancy")


def _profile_detail(p) -> None:
    spec = make_spec(p.coding_id, "default")
    cap1 = max_payload_bytes(spec, p.source_fraction_q, 1)
    plan = plan_volume(spec, cap1, p.source_fraction_q)
    print(f"      on the default printer: {spec.display_id}, promise-grade "
          f"{cap1:,} B/page ({plan.net_bits_per_mm2:.1f} b/mm2 net); "
          f"any >={p.source_fraction_q:.0%} of printed tiles (+rank "
          f"reserve) recovers the volume")


def cmd_registry(args) -> int:
    v = args.verbose
    print("codings (printer-independent; 64x64-cell tile budget):")
    for cid, c in sorted(CODINGS.items()):
        if c.codec_family is Family.K:
            print(
                f"  {cid}: {c.cell_dots}x{c.cell_dots} dots/cell; "
                f"4096 cells = {c.n_sites} pilots + "
                f"{c.ldpc_parity_bits} LDPC parity + 32 CRC + "
                f"1 metadata + {c.payload_bits_per_tile} payload "
                f"(~{c.payload_bits_per_tile // 8} B/tile)")
        else:
            print(
                f"  {cid}: {c.cell_dots}x{c.cell_dots} dots/cell; "
                f"4096 cells = 100 word + {c.n_dust} dust + "
                f"{c.payload_cells} payload-state cells; "
                f"{c.codec_id}, streams {'/'.join(c.stream_ids)}, "
                f"{c.aggregate_symbol_bits} aggregate payload bits "
                f"(~{c.aggregate_symbol_bits // 8} B/tile)")
        if v:
            _coding_detail(c)
    print("printers (geometry + capability; margins decide capacity):")
    for pid, p in sorted(PRINTERS.items()):
        print(f"  {pid}: {p.name}")
        print(f"      {p.usable_dpi} dpi usable, media {'/'.join(p.media_ids)}, "
              f"margins {p.payload_safe_margin_mm}mm "
              f"({p.margin_footing})")
        print(f"      b/w:   {p.bw}")
        print(f"      color: {p.color}")
        if v:
            _printer_detail(p)
    print("scanners:")
    for sid, s in sorted(SCANNERS.items()):
        print(f"  {sid}: {s.name} [{s.scanner_class}], "
              f"dpi {'/'.join(map(str, s.dpi_modes))}")
        if v:
            for n in s.notes:
                print(f"      note: {n}")
    print("profiles (coding + redundancy, priced on the measured record):")
    for name, p in sorted(PROFILES.items()):
        print(f"  {name}: {p.coding_id}, source-fraction "
              f"{p.source_fraction_q} [{p.evidence}, {p.priced_on}] — "
              f"{p.note}")
        if v:
            _profile_detail(p)
    return 0


def _geometry_block(spec, sheet=None) -> dict:
    placed = spec.layout if sheet is None else sheet
    cells_y, cells_x = spec.cells_yx
    return {"spec_id": spec.spec_id,
            "display_id": spec.display_id,
            "field_cells": f"{cells_y}x{cells_x}",
            "tiles_per_page": spec.tiles_per_page,
            "borders_mm": [round(placed.border_top_mm, 2),
                           round(placed.border_bottom_mm, 2),
                           round(placed.border_left_mm, 2),
                           round(placed.border_right_mm, 2)],
            "max_pages": spec.max_pages}


def cmd_capacity(args) -> int:
    spec, q, prof, sheet = _resolve_spec_q(args)
    head = ({"printer": args.printer or "default"} if sheet is None else
            {"paper": sheet.paper.name, "engine_dpi": sheet.engine_dpi,
             "dots_per_cell": sheet.dots_per_cell})
    out = {**head, **_geometry_block(spec, sheet), "source_fraction": q}
    try:
        if args.payload_bytes is not None:
            p = plan_volume(spec, args.payload_bytes, q)
            out.update({"payload_bytes": p.payload_bytes,
                        "k_total": p.k_total,
                        "n_pages": p.n_pages,
                        # A pooled row's n_repair is the whole-volume
                        # total of its ONE fountain.
                        ("n_repair_symbols_per_stream"
                         if p.n_streams > 1 and not spec.pooled_fountain
                         else "n_repair"): p.n_repair,
                        "effective_k_over_n": round(p.effective_k_over_n, 4),
                        "net_bits_per_mm2": round(p.net_bits_per_mm2, 2),
                        "net_area_basis": p.net_area_basis})
        else:
            out.update({"n_pages": args.pages,
                        "max_payload_bytes": max_payload_bytes(spec, q,
                                                               args.pages)})
        tier = pooled_plane_tier(spec, q)
        if tier is not None:
            out["plane_tier"] = tier
    except ValueError as e:
        raise SystemExit(str(e))
    if prof is not None:
        out["profile"] = prof.name
        out["evidence"] = prof.evidence
    if args.json:
        print(json.dumps(out, indent=1))
    else:
        for k, v in out.items():
            print(f"{k}: {v}")
    return 0


def cmd_fit(args) -> int:
    """Largest tile matrix a (paper, pitch, engine grid) admits.

    A convenience, not an identity-maker: the matrix it prints is the
    identity, this arithmetic is not (FORMAT-SPACE §7).
    """
    from holo.core.ldpc.construct import LADDER

    try:
        paper = get_paper(args.paper)
        pitch = parse_pitch(args.pitch)
        cell_dots = dots_per_cell(pitch, args.dpi)
        tiles_y, tiles_x = fit(paper, pitch, args.dpi)
    except (KeyError, ValueError) as exc:
        raise SystemExit(str(exc))
    page_x, page_y = page_dots_xy(paper.media_mm, args.dpi)
    usable_x, usable_y = usable_dots_xy(paper, args.dpi)
    token = display_pitch_token(pitch)
    micrometers = float(pitch) * 25_400
    print(f"paper {paper.name}: {paper.media_id} "
          f"{paper.media_mm[0]:.1f}x{paper.media_mm[1]:.1f} mm, "
          f"{paper.margin_mm} mm margins — {paper.note}")
    print(f"engine {args.dpi} dpi: page {page_x}x{page_y} dots, printable "
          f"{usable_x}x{usable_y} dots")
    print(f"pitch {token} = {pitch} in ({micrometers:.1f} um) = "
          f"{cell_dots} dots/cell")
    print(f"matrix {tiles_y}x{tiles_x} tiles = "
          f"{tiles_y * 64}x{tiles_x * 64} cells "
          f"({tiles_y * tiles_x} tiles/page)")
    print(f"format ids — pick a rung from the ladder "
          f"({' '.join(sorted(LADDER))}):")
    print(f"  {token}-k-<rung>@{tiles_y}x{tiles_x}")
    print(f"  {token}-cmy7@{tiles_y}x{tiles_x}"
          f"        (rungs are baked per generation)")
    print(f"  {token}-cmy8-<rung>@{tiles_y}x{tiles_x}"
          f"  (or a mixed triplet <rC>x<rM>x<rY>)")
    return 0


def cmd_generate(args) -> int:
    spec, q, prof, sheet = _resolve_spec_q(args)
    payload = Path(args.payload).read_bytes()
    if not payload:
        raise SystemExit("empty payload")
    out_dir = Path(args.out) if args.out else default_out_dir(spec, payload)
    # A v2 row records paper + engine grid; a legacy row records the
    # printer whose margins derived its page.
    emission = ({"printer_id": args.printer or "default"} if sheet is None
                else {"paper": sheet.paper.name,
                      "engine_dpi": sheet.engine_dpi})
    try:
        vol = emit_volume(spec, payload, q, out_dir, profile=prof,
                          **emission)
    except (FileExistsError, ValueError) as e:
        # ValueError = a legitimate planner refusal (dirty float dial,
        # 18-bit page cap): the operator gets the message, not a trace.
        raise SystemExit(str(e))
    label = prof.name if prof else "custom"
    tier = ("" if vol.plan.plane_tier is None
            else f", dead-plane tier {vol.plan.plane_tier}")
    # The echo is the DISPLAY spelling (FORMAT-SPACE §6): the canonical
    # identity is what the seed and the manifest carry, and it is what
    # --json reports; a person reading stdout gets the short form.
    where = (f"on {args.printer or 'default'}" if sheet is None else
             f"on {sheet.paper.name} @ {sheet.engine_dpi} dpi "
             f"({sheet.dots_per_cell} dots/cell)")
    print(f"{spec.display_id} {where} [{label}]: "
          f"{vol.plan.payload_bytes} bytes -> K={vol.plan.k_total} over "
          f"{vol.plan.n_pages} page(s), "
          f"K/N={vol.plan.effective_k_over_n:.3f}{tier}")
    for p in vol.pages:
        print(f"  {p.ps_path}  sha256 {p.ps_sha256[:16]}…")
    print(f"  {out_dir}/manifest.json  (sidecar — sheets decode "
          f"without it)")
    return 0


