"""Generation-side holo commands: registry | fit | capacity | generate.

Split out of cli.py at the FORMAT-SPACE P6 seam (the 1000-line signal):
cli.py keeps the parser, dispatch, and the decode session; this module
holds the emission-side command implementations.  No behavior change —
pure extraction.
"""
from __future__ import annotations

import json
from pathlib import Path

from holo.devices.profiles import PROFILES
from holo.devices.registry import PRINTERS, SCANNERS, Printer
from holo.format.descriptor import CODINGS, FormatSpec, get_coding
from holo.format.fossils import FOSSILS, is_fossil_ref
from holo.format.layout import MEDIA_MM
from holo.format.lattice import display_pitch_token, parse_pitch
from holo.format.profiles import Family
from holo.format.registry import FORMAT_ROWS
from holo.format.resolve import resolve_format_ref
from holo.gen.emit import color_route, default_out_dir, emit_volume
from holo.gen.plan import (max_payload_bytes, plan_volume, pooled_plane_tier,
                           tier_word)
from holo.gen.sheet import (
    DEFAULT_ENGINE_DPI,
    DEFAULT_PAPER,
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
    "capacity. `registry` lists the profiles' documented dials.")


def _resolve_spec_q(args) -> tuple:
    """(spec, q, sheet) from ``--format``, the whole identity.

    ``sheet`` is the v2 emission placement (paper x engine grid), or None
    for an ``L:`` fossil, which carries its own page (A4 x its margin).
    A bare legacy id refuses: on the CLI a fossil is spelled ``L:``.
    """
    if getattr(args, "coding", None):
        return _recipe_coding_spec(args)
    if not args.format:
        raise SystemExit("pick --format ID: a v2 id (see `fit`) or an "
                         "L: fossil (FORMAT-SPACE §8)")
    if args.source_fraction is None:
        raise SystemExit("--format needs an explicit --source-fraction")
    ref = args.format
    if not is_fossil_ref(ref) and (ref in FOSSILS or ref in FORMAT_ROWS):
        raise SystemExit(f"{ref!r} is a legacy id; a fossil is spelled "
                         f"--format L:{ref}")
    try:
        spec = resolve_format_ref(ref)
        if spec.coding.namespace == "v1":
            if args.paper is not None or args.dpi is not None:
                raise SystemExit(
                    f"{ref}: an L: fossil carries its own page (A4 x "
                    f"{spec.margin_mm:g} mm); --paper/--dpi place a v2 "
                    f"field")
            return spec, args.source_fraction, None
        sheet = sheet_layout(
            spec,
            DEFAULT_PAPER if args.paper is None else args.paper,
            DEFAULT_ENGINE_DPI if args.dpi is None else args.dpi)
    except (KeyError, ValueError) as exc:
        raise SystemExit(str(exc))
    return spec, args.source_fraction, sheet


# retained for measure/evidence_regen until the owner's ruling (CMY-GENERATOR-PLAN W2b ii)
def _recipe_coding_spec(args) -> tuple:
    """The evidence recipes' ``--coding ID --printer ID`` door: the page
    on A4 from that printer row's margin, as the published jobs and
    manifests were made, opening only onto a fossil identity; the printer
    is recorded, never an emission engine (cmyk1)."""
    if args.format or args.paper is not None or args.dpi is not None:
        raise SystemExit("--coding is the evidence recipes' legacy door; "
                         "it takes --printer and --source-fraction only")
    if args.source_fraction is None:
        raise SystemExit("--coding needs an explicit --source-fraction")
    printer = PRINTERS.get(args.printer or "default")
    if printer is None:
        raise SystemExit(f"unknown printer {args.printer!r}; known: "
                         f"{', '.join(sorted(PRINTERS))}")
    try:
        spec = FormatSpec(coding=get_coding(args.coding), media_id="a4",
                          media_mm=MEDIA_MM["a4"],
                          margin_mm=printer.payload_safe_margin_mm)
    except KeyError as exc:
        raise SystemExit(str(exc)) from None
    fossil = FOSSILS.get(spec.spec_id)
    if fossil is None or fossil.seed != spec.seed:
        raise SystemExit(f"{spec.spec_id} is not a fossil; new work "
                         f"spells --format")
    if spec.codec_family is not Family.K and printer.color_route is None:
        raise SystemExit(f"{printer.printer_id}: no colour record — it "
                         f"prints no {spec.codec_family.name} row")
    return spec, args.source_fraction, None


def _engine(args, spec: FormatSpec) -> Printer | None:
    """The emission engine a --format row names (None = cmyk1, unnamed).

    Never a geometry: paper and grid come from --paper/--dpi or the
    fossil.  The route is checked here so ``capacity`` refuses what
    ``generate`` would."""
    if args.printer is None:
        return None
    try:
        printer = PRINTERS[args.printer]
    except KeyError:
        raise SystemExit(
            f"unknown emission engine {args.printer!r}; known: "
            f"{', '.join(sorted(PRINTERS))}") from None
    if spec.codec_family is not Family.K:
        try:
            color_route(spec, printer)
        except ValueError as exc:
            raise SystemExit(str(exc))
    return printer


def _engine_block(spec: FormatSpec, printer: Printer | None) -> dict:
    if printer is None:
        return {}
    block = {"printer": printer.printer_id}
    if spec.codec_family is not Family.K:
        block["color_route"] = printer.color_route
    return block


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
    print("printers (emission engines for --printer; never a geometry):")
    for pid, p in sorted(PRINTERS.items()):
        print(f"  {pid}: {p.name}")
        print(f"      {p.usable_dpi} dpi usable, media {'/'.join(p.media_ids)}, "
              f"margins {p.payload_safe_margin_mm}mm "
              f"({p.margin_footing})")
        print(f"      b/w:   {p.bw}")
        print(f"      color: {p.color}")
        route = p.color_route or "none (colour formats refuse)"
        if p.rgb_solid is not None:
            route += " at C/M/Y " + " ".join(map(str, p.rgb_solid))
        print(f"      colour route: {route}")
        if v:
            _printer_detail(p)
    print("scanners:")
    for sid, s in sorted(SCANNERS.items()):
        print(f"  {sid}: {s.name} [{s.scanner_class}], "
              f"dpi {'/'.join(map(str, s.dpi_modes))}")
        if v:
            for n in s.notes:
                print(f"      note: {n}")
    print("profiles (documentation: coding + redundancy, priced on the "
          "measured record; select with --format + --source-fraction):")
    for name, p in sorted(PROFILES.items()):
        print(f"  {name}: {p.coding_id}, source-fraction "
              f"{p.source_fraction_q} [{p.evidence}, {p.priced_on}] — "
              f"{p.note}")
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
    spec, q, sheet = _resolve_spec_q(args)
    engine = _engine_block(spec, _engine(args, spec))
    head = (engine if sheet is None else
            {"paper": sheet.paper.name, "engine_dpi": sheet.engine_dpi,
             "dots_per_cell": sheet.dots_per_cell, **engine})
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
            out[f"{tier_word(spec)}_tier"] = tier
    except ValueError as e:
        raise SystemExit(str(e))
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
    print(f"  {token}-cmy-<rung>@{tiles_y}x{tiles_x}"
          f"   (or a stream pair <rHi>x<rLo>)")
    return 0


def cmd_generate(args) -> int:
    spec, q, sheet = _resolve_spec_q(args)
    payload = Path(args.payload).read_bytes()
    if not payload:
        raise SystemExit("empty payload")
    out_dir = Path(args.out) if args.out else default_out_dir(spec, payload)
    # A v2 row records paper + engine grid, a fossil its own page; both
    # record the emission engine, if named.  The recipes' --coding door
    # records its legacy printer id (cmyk1).
    engine = None if args.coding else _engine(args, spec)
    emission = ({"printer_id": args.printer or "default"} if args.coding
                else {"printer": engine} if sheet is None
                else {"paper": sheet.paper.name,
                      "engine_dpi": sheet.engine_dpi,
                      "printer": engine})
    try:
        vol = emit_volume(spec, payload, q, out_dir, **emission)
    except (FileExistsError, ValueError) as e:
        # ValueError = a legitimate planner refusal (dirty float dial,
        # 18-bit page cap): the operator gets the message, not a trace.
        raise SystemExit(str(e))
    tier = ("" if vol.plan.plane_tier is None
            else f", dead-{tier_word(spec)} tier {vol.plan.plane_tier}")
    # The echo is the DISPLAY spelling (FORMAT-SPACE §6): the canonical
    # identity is what the seed and the manifest carry, and it is what
    # --json reports; a person reading stdout gets the short form.
    where = (f"on {args.printer or 'default'}" if args.coding else
             (f"on its fossil page (A4, {spec.margin_mm:g} mm)"
              if sheet is None else
              f"on {sheet.paper.name} @ {sheet.engine_dpi} dpi "
              f"({sheet.dots_per_cell} dots/cell)")
             + ("" if engine is None else
                f", engine {engine.printer_id}"
                + ("" if spec.codec_family is Family.K else
                   f" ({engine.color_route} route)")))
    print(f"{spec.display_id} {where}: "
          f"{vol.plan.payload_bytes} bytes -> K={vol.plan.k_total} over "
          f"{vol.plan.n_pages} page(s), "
          f"K/N={vol.plan.effective_k_over_n:.3f}{tier}")
    for p in vol.pages:
        print(f"  {p.ps_path}  sha256 {p.ps_sha256[:16]}…")
    print(f"  {out_dir}/manifest.json  (sidecar — sheets decode "
          f"without it)")
    return 0
