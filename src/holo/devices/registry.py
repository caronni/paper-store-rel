"""Device registry: printers and scanners as measured capability records.

DATA, not code paths (HOLO-DESIGN §8, G3). A printer contributes exactly
two things to generation: its dot grid (max USABLE dpi — what the engine
honors, not what the driver advertises) and its real margins (payload-
safe area). Everything else here is capability context for choosing a
profile: what the engine can do in b/w and in color, with the evidence
class stated. Margins ride the 6.0 mm policy until a device's payload-
safe rectangle is qualified by the characterization track (E025 canary
doctrine: payload-safe reach, never ImagingBBox, never solid-ink reach).
``hp-m281-ink`` is an explicit e028 clip-geometry probe (4.5 mm), not a
qualified promotion of that doctrine.

The "default" printer is the locked conservative target: 600 dpi, 6 mm
margins, A4, b/w only. Sheets generated for it should print safely on
any 600-dpi-class engine.
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
        color="NOT usable: CMY triple toxic on this engine (017.6 "
              "hardware fail); K-only pages are also MIC-free",
        print_path="raw JetDirect 9100 only (scripts/print_plane.sh); "
                   "request /HWResolution [600 600] only — 1200 corrupts",
        notes=("single-plane K imagemask bit-faithful; region overlap "
               "re-screens ~165lpi (layer-0 freeze)",),
    ),
    # Ink-clip geometry for exact --coding decode of the e028 tight page.
    # Not a FORMAT_ROWS entry: discovery without --coding still refuses
    # (make_spec → c2-r0700@3392x2368 ∉ catalog). Use:
    #   --coding c2-r0700 --printer hp-m281-ink
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
        notes=("emitted counting page: scratch/e028/"
               "holo-c2-r0700-q07-ink-counting/; seed "
               "holo/v1/c2-r0700/3392x2368",),
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
