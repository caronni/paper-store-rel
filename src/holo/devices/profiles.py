"""Payload profiles + the coding->printer geometry resolver.

Profiles (rocksolid / resilient / high-volume / max) name one decision:
which coding at which source fraction. Each carries the measurement
context it was priced against (printer, scanner class) and an evidence
grade:

  "measured"     — the (coding, q) class has certified hardware volumes
                   (e016/e018/e018b lineage at r0550);
  "provisional"  — recorded hypothesis, pending the matched-payload rung
                   control (018b.5) and v1 requalification.

Geometry is NOT part of a profile: it comes from the printer at resolve
time (spec = coding x printer margins x media). Every profile is
provisional against format v1 itself until the first v1 print qualifies
(HOLO-DESIGN §11).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..format.descriptor import Coding, FormatSpec, get_coding
from ..format.layout import MEDIA_MM
from .registry import PRINTERS, Printer


@dataclass(frozen=True)
class PayloadProfile:
    name: str
    coding_id: str
    source_fraction_q: float       # fountain source/repair dial
    evidence: str                  # "measured" | "provisional"
    priced_on: str                 # printer + scanner class of the record
    note: str


PROFILES: dict[str, PayloadProfile] = {p.name: p for p in (
    PayloadProfile(
        name="rocksolid", coding_id="c3-r0550", source_fraction_q=0.35,
        evidence="measured", priced_on="hp-m281 + reference scanner",
        note="any ~40% of printed tiles recovers everything"),
    PayloadProfile(
        name="resilient", coding_id="c3-r0550", source_fraction_q=0.50,
        evidence="measured", priced_on="hp-m281 + reference scanner",
        note="the e018 class: real-scissors confetti session closed "
             "byte-exact"),
    PayloadProfile(
        name="high-volume", coding_id="c2-r0550", source_fraction_q=0.70,
        evidence="provisional", priced_on="hp-m281 + reference scanner",
        note="established inner rung, conservative ratio (018b.5)"),
    PayloadProfile(
        name="max", coding_id="c2-r0700", source_fraction_q=0.75,
        evidence="provisional", priced_on="hp-m281 + reference scanner",
        note="best intact-sheet hypothesis; pending the matched-payload "
             "rung control print"),
)}


def get_profile(name: str) -> PayloadProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(f"unknown profile {name!r}; "
                       f"known: {sorted(PROFILES)}") from None


def get_printer(printer_id: str) -> Printer:
    try:
        return PRINTERS[printer_id]
    except KeyError:
        raise KeyError(f"unknown printer {printer_id!r}; "
                       f"known: {sorted(PRINTERS)}") from None


def make_spec(coding: Coding | str, printer: Printer | str = "default",
              media_id: str | None = None) -> FormatSpec:
    """coding x printer -> the printed-format spec (geometry derived from
    the printer's margins and media)."""
    if isinstance(coding, str):
        coding = get_coding(coding)
    if isinstance(printer, str):
        printer = get_printer(printer)
    if media_id is None:
        media_id = printer.media_ids[0]
    if media_id not in printer.media_ids:
        raise ValueError(f"{printer.printer_id} does not take {media_id!r}")
    return FormatSpec(coding=coding, media_id=media_id,
                      media_mm=MEDIA_MM[media_id],
                      margin_mm=printer.payload_safe_margin_mm)
