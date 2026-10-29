"""Payload profiles — documentation of the measured dials, listed by
``registry``.

Profiles (rocksolid / resilient / high-volume / max) name one decision:
which coding at which source fraction. Each carries the measurement
context it was priced against (printer, scanner class) and an evidence
grade:

  "measured"     — the (coding, q) class has certified hardware volumes
                   (e016/e018/e018b lineage at r0550);
  "provisional"  — recorded hypothesis, pending the matched-payload rung
                   control (018b.5) and v1 requalification.

Every profile is provisional against format v1 itself until the first v1
print qualifies (HOLO-DESIGN §11). Generation no longer selects them
(R21, CMY-DESIGN §2.8): a volume is named by ``--format`` with an
explicit ``--source-fraction``, and a
legacy row by its ``L:`` fossil, which carries its own page.
"""
from __future__ import annotations

from dataclasses import dataclass


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
