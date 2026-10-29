"""devices/registry.py's emission record: the route and the device-RGB solid points (C, M, Y)."""
from __future__ import annotations

from holo.devices.registry import PRINTERS


def test_hp_m281_route_and_solid_points() -> None:
    p = PRINTERS["hp-m281"]
    assert p.color_route == "rgb"
    assert p.rgb_solid == ((0, 176, 255), (240, 0, 192), (255, 255, 0))   # e043 sheet 3 (§043.6), the owner's word 2026-10-11


def test_every_other_printer_is_cmyk1_or_has_no_colour_record() -> None:
    m281 = PRINTERS["hp-m281"]
    assert (PRINTERS["hp-m281-ink"].color_route, PRINTERS["hp-m281-ink"].rgb_solid) == (m281.color_route, m281.rgb_solid)
    others = {pid: (p.color_route, p.rgb_solid) for pid, p in PRINTERS.items() if pid not in ("hp-m281", "hp-m281-ink")}
    # 2026-10-12 (cmy generator W2b, CMY-DESIGN R21): `default` has no colour record (None, so a colour
    # family refuses instead of emitting cmyk1 silently); the Canon iR-ADV C257/357 (e040) joins as cmyk1.
    assert others == {"default": (None, None), "xerox-altalink-c8245": ("cmyk1", None),
                      "canon-iradv-c257": ("cmyk1", None)}
    canon = PRINTERS["canon-iradv-c257"]
    assert (canon.usable_dpi, canon.media_ids) == (600, ("a4", "letter"))   # e040 s040.2: fixed 600
