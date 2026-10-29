"""Device registry: printers and scanners as measured capability records.

DATA, not code paths (HOLO-DESIGN §8, G3). A printer is an EMISSION
engine (``--printer ENGINE``, CMY-DESIGN §2.8, R21): it gives generation
its colour route (``color_route``: "cmyk1" = one bit per CMYK plane, "rgb"
= one mask per toner at the engine's measured device-RGB solid points,
None = no colour record, so a colour family refuses) and, for "rgb", those
points (``rgb_solid``, C M Y; W is unpainted paper) — an emission fact
that shapes the job's bytes and never enters a seed. Geometry comes from
``--paper``/``--dpi`` or the ``L:`` fossil, never from a printer; the
margin fields survive only for the evidence recipes' ``--coding`` door
(retained for measure/evidence_regen until the owner's ruling,
CMY-GENERATOR-PLAN W2b ii). Everything else here is capability context:
what the engine can do in b/w and in color, with the evidence class
stated.

The "default" printer is the locked conservative target: 600 dpi, 6 mm
margins, A4, b/w only — no colour record.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Printer:
    printer_id: str
    name: str
    usable_dpi: int                    # the honored dot grid; never more
    media_ids: tuple[str, ...]
    payload_safe_margin_mm: float      # per-edge, conservative
    margin_footing: str                # where that number comes from
    bw: str                            # measured b/w capability, evidence
    color: str                         # measured color capability, evidence
    print_path: str
    notes: tuple[str, ...] = field(default=())
    color_route: str | None = None     # emission route, never in a seed
    rgb_solid: tuple[tuple[int, int, int], ...] | None = None  # C, M, Y


@dataclass(frozen=True)
class Scanner:
    scanner_id: str
    name: str
    dpi_modes: tuple[int, ...]
    scanner_class: str                 # profile key: "reference" | "weak"
    notes: tuple[str, ...] = field(default=())


PRINTERS: dict[str, Printer] = {p.printer_id: p for p in (
    Printer(
        printer_id="default",
        name="conservative 600dpi target (locked)",
        usable_dpi=600,
        media_ids=("a4",),
        payload_safe_margin_mm=6.0,
        margin_footing="policy constant; safe on every engine measured "
                       "to date (ink reach 3.5-4mm on both)",
        bw="assume c3 workable, c2 unqualified — characterize before "
           "trusting c2 on an unknown engine",
        color="none (b/w only by definition)",
        print_path="raw socket 9100 preferred; any driver that honors "
                   "600x600 1-bit",
    ),
    Printer(
        printer_id="hp-m281",
        name="HP Color LaserJet Pro MFP M281fdw",
        usable_dpi=600,
        media_ids=("a4",),
        payload_safe_margin_mm=6.0,
        margin_footing="policy 6.0mm; ink reach 3.5-4.0mm measured "
                       "(e025); payload-safe rectangle NOT yet qualified",
        bw="c3 sub-1% per-window, c2 ~5-6% raw / 2-5% ctx at 16px/cell, "
           "c1 dead (e025 v3, e016/e018 certified volumes)",
        color="single toners lay solid through the device-RGB points "
              "(e041, e043); the engine adds a screened 212 lpi yellow "
              "component to cyan above G ~176 in the page's left and "
              "middle column zones and to every magenta, and dark dots "
              "to any yellow off the corner; inside a cell field the "
              "stipple is the cyan value's — C (0,176,255) reads a "
              "quarter of (0,184,255)'s at c2, a third at c3, flat "
              "across the zones (experiments/043-m281-cmy-probe.md "
              "s043.3c, s043.5, s043.6); composites "
              "(toner overlaps) are screened on every route tried; "
              "K-only pages are MIC-free",
        print_path="raw JetDirect 9100 only (scripts/print_plane.sh); "
                   "request /HWResolution [600 600] only — 1200 corrupts",
        notes=("single-plane K imagemask bit-faithful; region overlap "
               "re-screens ~165lpi (layer-0 freeze)",),
        color_route="rgb",
        rgb_solid=((0, 176, 255), (240, 0, 192), (255, 255, 0)),
    ),
    # retained for measure/evidence_regen until the owner's ruling (CMY-GENERATOR-PLAN W2b ii)
    # Its page is the fossil L:c2-r0700@3392x2368; the 4.5 mm margin is what
    # the recipes' `--coding c2-r0700 --printer hp-m281-ink` records.
    Printer(
        printer_id="hp-m281-ink",
        name="HP M281 ink-tight (e028 clip experiment)",
        usable_dpi=600,
        media_ids=("a4",),
        payload_safe_margin_mm=4.5,
        margin_footing="e028 2026-08-04 printable clip ~4.15-4.28mm; "
                       "4.5mm request selects next 64-quantum field "
                       "(c2: 3392x2368 cells, actual borders ~4.91/4.74mm — "
                       "~0.5-0.7mm inside measured clip; edge tiles "
                       "expected clipped)",
        bw="same engine as hp-m281; geometry probe only — not a "
           "qualified payload-safe promotion",
        color="same as hp-m281 (K-only)",
        print_path="raw JetDirect 9100 only (scripts/print_plane.sh); "
                   "request /HWResolution [600 600] only — 1200 corrupts",
        color_route="rgb",                                   # the same engine as hp-m281 (W2a refuter)
        rgb_solid=((0, 176, 255), (240, 0, 192), (255, 255, 0)),
        notes=("emitted counting page (e029): seed "
               "holo/v1/c2-r0700/3392x2368, regenerable with "
               "confetti.py generate --format L:c2-r0700@3392x2368",),
    ),
    Printer(
        printer_id="xerox-altalink-c8245",
        name="Xerox AltaLink C8245",
        usable_dpi=600,
        media_ids=("a4",),
        payload_safe_margin_mm=6.0,
        margin_footing="policy 6.0mm; ticks survive to 4mm (007.6); "
                       "payload-safe rectangle not qualified",
        bw="K ladder M281-class: c3 2.5-3.5%, c2 ~12% raw, c1 dead "
           "(007.6)",
        color="healthy CMY (8-state MI 2.208, A3 record 133 b/mm2) but "
              "current CMY7/CMY8 rows remain software-provisional and "
              "paper-unqualified; color pages carry yellow tracking dots "
              "(K-only pages clean)",
        print_path="raw 9100; PS RIP fixed-600, no resolution unlock on "
                   "any path (007.6/009)",
        color_route="cmyk1",
    ),
    Printer(
        printer_id="canon-iradv-c257",
        name="Canon imageRUNNER ADVANCE C257/357",
        usable_dpi=600,
        media_ids=("a4", "letter"),
        payload_safe_margin_mm=6.0,
        margin_footing="policy 6.0mm; payload-safe rectangle not "
                       "qualified; the site's Letter stock trims an A4 "
                       "page (e040 s040.4f: rows 50-52 of a 53x37 page "
                       "never printed)",
        bw="c3 0.05-0.06%, c2 2.1-4.6%, c2x3 0.21-0.26% (discovery, "
           "e040 s040.4d); single 1-dot dots print faintly, c1-K 21% "
           "raw, 0 certificates (s040.3, s040.4c); c4/c3/c2-K VERIFIED "
           "(s040.4d)",
        color="cells unscreened on raw PostScript, healthy Y (tone "
              "range 0.41-0.44); CMY7 1.7-3.5%, CMY8 4.4-8.0% "
              "(discovery, s040.4d); c2-cmy8 r0700 VERIFIED 1,598,326 B "
              "(s040.4f), r0775 VERIFIED with the analyzer (s040.4i), "
              "r0850 NOT recovered (s040.4g); C vs M a 93 mm sinusoid "
              "of 1.58 dots p-p; no cmy page printed here "
              "(experiments/040-canon-iradv.md)",
        print_path="raw PostScript accepted; the 2026-09-24 door is "
                   "UNRECORDED (lpr -o raw through an AirPrint queue, or "
                   "print_plane.sh to 9100 — e040's owed list), so the "
                   "footing is unqualified; PS LanguageLevel 3, fixed "
                   "600 — the [1200 2400] request refused (s040.2)",
        color_route="cmyk1",
    ),
)}

SCANNERS: dict[str, Scanner] = {s.scanner_id: s for s in (
    Scanner(
        scanner_id="canon-4800",
        name="Canon flatbed 4800dpi",
        dpi_modes=(1200, 2400, 4800),
        scanner_class="reference",
        notes=("E017.4 first RGB scan: scale +0.126% x/+0.074% y, "
               "near-isotropic; versus the home flatbed, Canon capture at "
               "the same 2px/dot cuts C/M/Y BER 40-47%, while native "
               "8px/dot adds another 6-9%; no acquisition-breaking color "
               "comb; rotated attribution, MTF, repeats, and step catalog "
               "still owed",),
    ),
    Scanner(
        scanner_id="hp-m281-flatbed",
        name="HP M281 flatbed (1200dpi)",
        dpi_modes=(1200,),
        scanner_class="weak",
        notes=("stochastic y-steps + 18.63mm CCD comb; never mix modes; "
               "color mode lays an 11.3px comb — grey only",),
    ),
)}
