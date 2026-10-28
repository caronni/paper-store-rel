#!/usr/bin/env python
"""Emit one forward E025 printer/scanner metrology page.

Two page kinds are intentionally separate: ``mono`` keeps a true K-only
printer path, while ``color`` contains CMY and therefore measures the color
operating path.  Both pages carry redundant print-time machine readback,
physical and payload-safe edge probes, geometry instruments, typed physical
patterns, large deterministic channel fields, and compact house-LDPC
confirmation coupons.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from paperholo import ldpc
from paperholo.metrology import GridSpec
from paperholo.psgen import A4_PT, CMYK, PSDoc

import e025_common as ec

PRESETS = {
    "hp-m281-bw": "mono",
    "hp-m281-color": "color",
}
DEFAULT_COMPARISON_GRIDS = (300, 1200, 2400)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _corner_mark(n_sat: int, inward: tuple[int, int]) -> np.ndarray:
    bits = np.zeros((123, 123), np.uint8)
    bits[60:63, :] = 1
    bits[:, 60:63] = 1
    dy, dx = inward
    for k in range(n_sat):
        d = 18 + 12 * k
        cy, cx = 61 + dy * d, 61 + dx * d
        bits[cy - 4:cy + 4, cx - 4:cx + 4] = 1
    return bits


def _plus_mark() -> np.ndarray:
    bits = np.zeros((31, 31), np.uint8)
    bits[14:17, :] = 1
    bits[:, 14:17] = 1
    return bits


def _ps_prolog() -> list[str]:
    """Snapshot default pagedevice before PSDoc's guarded request."""
    return [
        "% E025 default-device snapshot; namespace remains open for page code",
        "/PHC 160 dict def PHC begin",
        "/BUF 160 string def",
        "/TRY { /DFLT exch def mark exch stopped",
        "  { cleartomark DFLT }",
        "  { counttomark 1 eq { exch pop } { cleartomark DFLT } ifelse } ifelse } bind def",
        "/PDD { currentpagedevice } 1 dict TRY def",
        "/LL { languagelevel } 1 TRY def",
    ]


def _ps_device_payload(*, bundle_id: str, page_kind: str,
                       primary_grid: int,
                       request: tuple[int, int] | None) -> list[str]:
    request_text = "default" if request is None else f"{request[0]}x{request[1]}"
    return [
        "% E025 effective-device snapshot and 390-byte CRC strip payload",
        "/PDGET { 3 1 roll 2 copy known { get exch pop } { pop pop } ifelse } bind def",
        "/PDE { currentpagedevice } 1 dict TRY def",
        "/HWR PDE /HWResolution [72 72] PDGET def",
        "/HWX HWR 0 get round cvi def /HWY HWR 1 get round cvi def",
        "/PGSZ PDE /PageSize [595 842] PDGET def",
        "/PAGEHD PGSZ 1 get 72 div HWY mul round cvi def",
        "/MMX { 25.4 div HWX mul round cvi } bind def",
        "/MMY { 25.4 div HWY mul round cvi } bind def",
        "/MX HWX 100 div round cvi dup 3 lt { pop 3 } if def",
        "/MY HWY 100 div round cvi dup 3 lt { pop 3 } if def",
        "/DOTSPACE { initmatrix 72 HWX div 72 HWY div scale",
        "  0 PAGEHD translate 1 -1 scale } bind def",
        "/ELEM { mark exch gsave stopped grestore cleartomark } bind def",
        "/PAY 512 string def /PLEN 0 def",
        "/EMIT { dup length /LT exch def PLEN LT add PAY length le",
        "  { PAY PLEN 3 -1 roll putinterval /PLEN PLEN LT add def } { pop } ifelse } bind def",
        "/EMITN { BUF cvs EMIT } bind def",
        "(PHCAL1;LAY=1;) EMIT",
        f"(J={bundle_id};S={ec.SEED_TEXT};R0={request_text};) EMIT",
        f"(EX=E025;PV={ec.LAYOUT_VERSION};PK={page_kind};"
        f"AR={primary_grid}x{primary_grid};) EMIT",
        "(LL=) EMIT LL EMITN",
        "(;RD=) EMIT PDD /HWResolution [0 0] PDGET dup 0 get round cvi EMITN",
        "  (x) EMIT 1 get round cvi EMITN",
        "(;RE=) EMIT HWX EMITN (x) EMIT HWY EMITN",
        "(;PS=) EMIT PGSZ 0 get round cvi EMITN (x) EMIT PGSZ 1 get round cvi EMITN",
        "(;IB=) EMIT PDE /ImagingBBox null PDGET",
        "  dup null eq { pop (null) EMIT } { { EMITN ( ) EMIT } forall } ifelse",
        "(;DU=) EMIT PDE /Duplex false PDGET BUF cvs EMIT",
        "(;TU=) EMIT PDE /Tumble false PDGET BUF cvs EMIT",
        "(;CM=) EMIT PDE /ProcessColorModel (unknown) PDGET BUF cvs EMIT",
        "(;PR=) EMIT { /product where { /product get }",
        "  { statusdict /product get } ifelse dup length 32 gt",
        "  { 0 32 getinterval } if } (unknown) TRY EMIT",
        "(;V=) EMIT { /version where { /version get }",
        "  { statusdict /version get } ifelse dup type /stringtype ne",
        "  { BUF cvs } if dup length 16 gt { 0 16 getinterval } if } (unknown) TRY EMIT",
        "(;RV=) EMIT { /revision where { /revision get } { 0 } ifelse } 0 TRY EMITN",
        "(;SN=) EMIT { statusdict /serialnumber get exec } -1 TRY EMITN",
        "(;) EMIT",
        "PLEN 388 lt { PAY PLEN 0 put /PLEN PLEN 1 add def } if",
        "PLEN 1 387 { PAY exch 16#A5 put } for",
        "/CRC 16#FFFF def",
        "/CRCB { 8 bitshift CRC xor 16#FFFF and /CRC exch def",
        "  8 { CRC 16#8000 and 0 ne { CRC 1 bitshift 16#1021 xor }",
        "    { CRC 1 bitshift } ifelse 16#FFFF and /CRC exch def } repeat } bind def",
        "0 1 387 { PAY exch get CRCB } for",
        "PAY 388 CRC -8 bitshift 16#FF and put PAY 389 CRC 16#FF and put",
        "/PZ 388 def 0 1 387 { dup PAY exch get 0 eq",
        "  { /PZ exch def exit } { pop } ifelse } for",
    ]


def _ps_machine_strips(x_mm: float, y_values_mm: Iterable[float]) -> list[str]:
    lines = [
        "% E025 LAY=1 strips: 724x11 modules; exp002-compatible decoder",
        "/NB 78 def /NR 5 def /WI 720 def /HI NR 2 add def",
        "/MODB { exch MX mul SX0 add exch MY mul SY0 add MX MY rectfill } bind def",
        "/PUTBIT { 1 eq { COL ROW 1 add MODB } if /COL COL 1 add def } bind def",
        "/PUTBYTE { /B exch def /PARITY 0 def 7 -1 0 { /I exch def",
        "  B I neg bitshift 1 and dup PARITY xor /PARITY exch def PUTBIT } for",
        "  PARITY PUTBIT } bind def",
        "/STRIP { MMY /SBY0 exch def MMX /SBX0 exch def 0 0 0 1 setcmykcolor",
        "  SBX0 SBY0 WI 4 add MX mul MY rectfill",
        "  SBX0 SBY0 HI 3 add MY mul add WI 4 add MX mul MY rectfill",
        "  SBX0 SBY0 MX HI 4 add MY mul rectfill",
        "  SBX0 WI 3 add MX mul add SBY0 MX HI 4 add MY mul rectfill",
        "  /SX0 SBX0 MX 2 mul add def /SY0 SBY0 MY 2 mul add def",
        "  0 2 WI 1 sub { 0 MODB } for 1 2 WI 1 sub { HI 1 sub MODB } for",
        "  0 1 NR 1 sub { /ROW exch def /COL 0 def 1 PUTBIT 0 PUTBIT 1 PUTBIT 1 PUTBIT",
        "    /RX 0 def 0 1 NB 1 sub { ROW NB mul add PAY exch get",
        "      dup RX xor /RX exch def PUTBYTE } for RX PUTBYTE } for } bind def",
    ]
    lines.extend(f"{{ DOTSPACE {x_mm} {y_mm} STRIP }} ELEM" for y_mm in y_values_mm)
    return lines


class PageBuilder:
    def __init__(self, *, page_kind: str, primary_grid: int,
                 comparison_grids: tuple[int, ...],
                 request: tuple[int, int] | None,
                 bundle_id: str) -> None:
        self.page_kind = page_kind
        self.primary_grid = primary_grid
        self.comparison_grids = comparison_grids
        self.request = request
        self.bundle_id = bundle_id
        self.doc = PSDoc(
            hw_dpi=ec.BASE_DPI,
            page_size_pt=A4_PT,
            title=f"E025 {page_kind} channel metrology {bundle_id}",
            prolog_lines=_ps_prolog(),
            guard_setpagedevice=True,
            request_hw_dpi=request,
        )
        self.page: dict[str, Any] = {
            "page_index": 1,
            "page_id": f"{bundle_id}-p001",
            "page_kind": page_kind,
            "candidates": {},
            "infrastructure": [],
            "probes": [],
            "fields": [],
        }

    def label(self, text: str, x_mm: float, y_mm: float,
              size_pt: float = 4.0) -> None:
        self.doc.put_label(text, ec.mm_to_dots(x_mm), ec.mm_to_dots(y_mm),
                           CMYK["K"], size_pt=size_pt)

    def add_infrastructure(self) -> None:
        centers = {
            1: (16.8, 22.5), 2: (193.2, 22.5),
            3: (193.2, 274.5), 4: (16.8, 274.5),
        }
        inward = {1: (1, 1), 2: (1, -1), 3: (-1, -1), 4: (-1, 1)}
        for n_sat, (cx_mm, cy_mm) in centers.items():
            bits = _corner_mark(n_sat, inward[n_sat])
            cx, cy = ec.mm_to_dots(cx_mm), ec.mm_to_dots(cy_mm)
            x, y = cx - bits.shape[1] // 2, cy - bits.shape[0] // 2
            self.doc.put_bitmap(bits, x, y, CMYK["K"])
            self.page["infrastructure"].append({
                "kind": "corner_mark", "satellites": n_sat,
                "inward": list(inward[n_sat]),
                "cx_layout_dots": cx, "cy_layout_dots": cy,
                "x_layout_dots": x, "y_layout_dots": y,
                "w_layout_dots": int(bits.shape[1]),
                "h_layout_dots": int(bits.shape[0]),
            })

        # Internal marks expose residual warp after the corner affine.  Their
        # sparse perimeter/gutter placement keeps them out of science fields.
        plus = _plus_mark()
        positions = [
            (24.0, y) for y in (30.0, 86.0, 145.0, 204.0, 263.0)
        ] + [
            (186.0, y) for y in (30.0, 86.0, 145.0, 204.0, 263.0)
        ] + [(105.0, y) for y in (30.0, 86.0, 204.0, 263.0)]
        for index, (cx_mm, cy_mm) in enumerate(positions):
            cx, cy = ec.mm_to_dots(cx_mm), ec.mm_to_dots(cy_mm)
            x, y = cx - 15, cy - 15
            self.doc.put_bitmap(plus, x, y, CMYK["K"])
            self.page["infrastructure"].append({
                "kind": "geometry_plus", "index": index,
                "cx_layout_dots": cx, "cy_layout_dots": cy,
                "x_layout_dots": x, "y_layout_dots": y,
                "w_layout_dots": 31, "h_layout_dots": 31,
            })

        self.doc.put_raw(_ps_machine_strips(12.5, (13.5, 280.5)))
        for index, y_mm in enumerate((13.5, 280.5)):
            self.page["infrastructure"].append({
                "kind": "machine_strip", "index": index,
                "format": "PHCAL1/LAY=1", "x_mm": 12.5, "y_mm": y_mm,
                "modules": [724, 11], "payload_bytes": 390,
                "crc": "CRC-16/CCITT-FALSE big-endian",
                "module_formula": "max(3,round(effective_dpi/100))",
                "dynamic_excluded_from_static_ground_truth": True,
            })

    def add_probe(self, *, probe_id: str, kind: str, x_mm: float, y_mm: float,
                  w_mm: float, h_mm: float, plane: str = "K",
                  dpi: int | None = None, params: dict[str, Any] | None = None,
                  group: str = "physical", seed_label: str | None = None) -> dict[str, Any]:
        dpi = dpi or self.primary_grid
        x_source, y_source = ec.mm_to_dots(x_mm, dpi), ec.mm_to_dots(y_mm, dpi)
        w_source = max(1, ec.mm_to_dots(w_mm, dpi))
        h_source = max(1, ec.mm_to_dots(h_mm, dpi))
        probe = {
            "probe_id": probe_id, "group": group, "kind": kind,
            "plane": plane, "source_dpi": dpi,
            "x_source_dots": x_source, "y_source_dots": y_source,
            "w_source_dots": w_source, "h_source_dots": h_source,
            "x_layout_dots": x_source * ec.BASE_DPI / dpi,
            "y_layout_dots": y_source * ec.BASE_DPI / dpi,
            "w_layout_dots": w_source * ec.BASE_DPI / dpi,
            "h_layout_dots": h_source * ec.BASE_DPI / dpi,
            "params": dict(params or {}),
            "seed_label": seed_label or f"probe/{probe_id}",
        }
        bits = ec.pattern_bits(probe)
        probe["ground_truth_sha256"] = hashlib.sha256(bits.tobytes()).hexdigest()
        if kind != "paper":
            self.doc.put_bitmap(bits, x_source, y_source, CMYK[plane], dpi=dpi)
        self.page["probes"].append(probe)
        return probe

    def add_random_field(self, *, field_id: str, definition_id: str,
                         grid_dpi: int, cell: int | tuple[int, int],
                         x_mm: float, y_mm: float,
                         w_mm: float, h_mm: float, family: str = "prnd",
                         role: str = "channel", edge: str | None = None,
                         edge_gap_mm: float | None = None) -> dict[str, Any]:
        definition = ec.CHANNELS[definition_id]
        c_x, c_y = (cell, cell) if isinstance(cell, int) else cell
        grid = GridSpec(grid_dpi, grid_dpi, c_x, c_y)
        nx = max(8, int(math.floor(w_mm / grid.cell_pitch_mm_x)))
        ny = max(8, int(math.floor(h_mm / grid.cell_pitch_mm_y)))
        return self._add_field(
            field_id=field_id, definition=definition, grid=grid,
            x_mm=x_mm, y_mm=y_mm, nx=nx, ny=ny, family=family,
            role=role, edge=edge, edge_gap_mm=edge_gap_mm,
        )

    def add_fec_coupon(self, *, field_id: str, definition_id: str,
                       grid_dpi: int, cell: int, x_mm: float, y_mm: float,
                       rate_id: str, n_codewords: int = 2) -> dict[str, Any]:
        definition = ec.CHANNELS[definition_id]
        grid = GridSpec(grid_dpi, grid_dpi, cell, cell)
        calibration = max(2048, len(definition.states) * 256)
        total = calibration + n_codewords * ldpc.N_BITS
        # 10240 = 256x40 for the default two-word coupon.  For a custom
        # population choose a divisor close to a wide, short 6:1 rectangle.
        divisors = [n for n in range(8, int(math.sqrt(total)) + 1) if total % n == 0]
        ny = min(divisors, key=lambda n: abs(total / n / n - 6.0))
        nx = total // ny
        return self._add_field(
            field_id=field_id, definition=definition, grid=grid,
            x_mm=x_mm, y_mm=y_mm, nx=nx, ny=ny, family="fec_coupon",
            role="production-confirmation", rate_id=rate_id,
            calibration_cells=calibration, n_codewords=n_codewords,
        )

    def _add_field(self, *, field_id: str, definition: ec.ChannelDefinition,
                   grid: GridSpec, x_mm: float, y_mm: float, nx: int, ny: int,
                   family: str, role: str, edge: str | None = None,
                   edge_gap_mm: float | None = None, rate_id: str | None = None,
                   calibration_cells: int | None = None,
                   n_codewords: int = 0) -> dict[str, Any]:
        candidate = ec.candidate_manifest(definition, grid)
        candidate_key = candidate["candidate_id"]
        self.page["candidates"][candidate_key] = candidate
        x_source = ec.mm_to_dots(x_mm, grid.dpi_x)
        y_source = ec.mm_to_dots(y_mm, grid.dpi_y)
        field: dict[str, Any] = {
            "field_id": field_id, "family": family, "role": role,
            "candidate_key": candidate_key,
            "seed_label": f"field/{field_id}",
            "x_source_dots": x_source, "y_source_dots": y_source,
            "x_layout_dots": x_source * ec.BASE_DPI / grid.dpi_x,
            "y_layout_dots": y_source * ec.BASE_DPI / grid.dpi_y,
            "nx": nx, "ny": ny,
            "w_layout_dots": nx * grid.c_x * ec.BASE_DPI / grid.dpi_x,
            "h_layout_dots": ny * grid.c_y * ec.BASE_DPI / grid.dpi_y,
            "stratum": "top" if y_mm < 99 else "middle" if y_mm < 198 else "bottom",
        }
        if edge is not None:
            field.update({"edge": edge, "edge_gap_mm": edge_gap_mm})
        if family == "fec_coupon":
            field.update({
                "rate_id": rate_id,
                "calibration_cells": calibration_cells,
                "n_codewords": n_codewords,
                "codeword_start": calibration_cells,
            })
        states = ec.field_states(field, definition)
        field["state_sha256"] = ec.state_sha256(states)
        self._emit_states(definition, grid, states, x_source, y_source)
        self.page["fields"].append(field)
        return field

    def _emit_states(self, definition: ec.ChannelDefinition, grid: GridSpec,
                     states: np.ndarray, x_source: int, y_source: int) -> None:
        cells = ec.state_planes(states, definition)
        planes = {
            plane: ec.expand_cells(bits, grid, definition.symbol_shape)
            for plane, bits in cells.items()
        }
        dpi = (grid.dpi_x, grid.dpi_y)
        if definition.emission_path == "single-plane-imagemask":
            ((plane, bits),) = planes.items()
            self.doc.put_bitmap(bits, x_source, y_source, CMYK[plane], dpi=dpi)
        elif definition.emission_path == "DeviceCMYK-image":
            self.doc.put_cmyk_bitmap(planes, x_source, y_source, dpi=dpi)
        elif definition.emission_path == "sequential-imagemask-overprint-opm1":
            for plane in "CMYK":
                if plane in planes:
                    self.doc.put_bitmap(
                        planes[plane], x_source, y_source, CMYK[plane], dpi=dpi,
                        overprint=True, opm=True,
                    )
        else:
            raise ValueError(f"unsupported emission path {definition.emission_path}")

    def add_edge_measurements(self) -> None:
        # Compact tick clusters leave separate along-edge stations for the
        # larger random canaries.  A tick's `gap_mm` is its outer-edge gap.
        for index, gap in enumerate(ec.EDGE_GAPS_MM):
            along = 20.0 + 3.5 * index
            placements = {
                "top": (along, gap),
                "bottom": (210.0 - along - 1.5, 297.0 - gap - 1.5),
                "left": (gap, 34.0 + 3.5 * index),
                "right": (210.0 - gap - 1.5, 34.0 + 3.5 * index),
            }
            for edge, (x_mm, y_mm) in placements.items():
                self.add_probe(
                    probe_id=f"edge/{edge}/tick-{gap:g}", kind="edge_tick",
                    x_mm=x_mm, y_mm=y_mm, w_mm=1.5, h_mm=1.5,
                    group="printable-extent",
                    params={"edge": edge, "gap_mm": gap}, dpi=600,
                )

        definition_id = "k1-mask" if self.page_kind == "mono" else "cmy8-image"
        for index, gap in enumerate(ec.EDGE_CANARY_GAPS_MM):
            # Top/bottom: wide and shallow; left/right: narrow and tall.
            x_top = 76.0 + 16.0 * index
            y_side = 88.0 + 24.0 * index
            placements = {
                "top": (x_top, gap, 8.0, 2.8),
                "bottom": (202.0 - x_top, 297.0 - gap - 2.8, 8.0, 2.8),
                "left": (gap, y_side, 2.8, 8.0),
                "right": (210.0 - gap - 2.8, y_side, 2.8, 8.0),
            }
            for edge, (x_mm, y_mm, w_mm, h_mm) in placements.items():
                self.add_random_field(
                    field_id=f"edge/{edge}/c2-{gap:g}",
                    definition_id=definition_id,
                    grid_dpi=self.primary_grid, cell=2,
                    x_mm=x_mm, y_mm=y_mm, w_mm=w_mm, h_mm=h_mm,
                    family="edge_canary", role="payload-safe-extent",
                    edge=edge, edge_gap_mm=gap,
                )

    @staticmethod
    def _tone_kind(coverage: float) -> str:
        return "paper" if coverage == 0.0 else "solid" if coverage == 1.0 else "tone"

    @staticmethod
    def _profile_kind(coverage: float) -> str:
        return ("paper" if coverage == 0.0 else
                "solid" if coverage == 1.0 else "profile_tone")

    @staticmethod
    def _coverage_order(shift: int, *, reverse: bool = False
                        ) -> tuple[float, ...]:
        base = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)
        shift %= len(base)
        order = base[shift:] + base[:shift]
        return tuple(reversed(order)) if reverse else order

    def add_tone_station(self, *, station_id: str, plane: str,
                         x_mm: float, y_mm: float, w_mm: float, h_mm: float,
                         fixed_coverage: float,
                         response_order: tuple[float, ...],
                         vertical: bool = False) -> None:
        """Share one old ramp footprint between direct and response evidence."""
        guard = 0.20
        if vertical:
            fixed_w = min(0.90, 0.42 * w_mm)
            response_x = x_mm + fixed_w + guard
            response_w = w_mm - fixed_w - guard
            fixed_rect = (x_mm, y_mm, fixed_w, h_mm)
        else:
            fixed_h = min(0.95, 0.42 * h_mm)
            response_y = y_mm + fixed_h + guard
            response_h = h_mm - fixed_h - guard
            fixed_rect = (x_mm, y_mm, w_mm, fixed_h)
        self.add_probe(
            probe_id=f"tone/{station_id}/fixed",
            kind=self._profile_kind(fixed_coverage),
            x_mm=fixed_rect[0], y_mm=fixed_rect[1],
            w_mm=fixed_rect[2], h_mm=fixed_rect[3], plane=plane,
            group="tone-metrology",
            params={"mode": "fixed-profile", "coverage": fixed_coverage,
                    "station": station_id,
                    "axis": "y" if vertical else "x"},
        )
        for index, coverage in enumerate(response_order):
            if vertical:
                sx, sy = response_x, y_mm + h_mm * index / len(response_order)
                sw, sh = response_w, h_mm / len(response_order)
            else:
                sx, sy = x_mm + w_mm * index / len(response_order), response_y
                sw, sh = w_mm / len(response_order), response_h
            self.add_probe(
                probe_id=f"tone/{station_id}/response-{index}",
                kind=self._tone_kind(coverage),
                x_mm=sx, y_mm=sy, w_mm=sw, h_mm=sh, plane=plane,
                group="tone-metrology",
                params={"mode": "response", "coverage": coverage,
                        "station": station_id,
                        "axis": "y" if vertical else "x",
                        "sequence_index": index},
            )

    def add_fixed_profile(self, *, profile_id: str, plane: str,
                          x_mm: float, y_mm: float, w_mm: float, h_mm: float,
                          coverage: float, axis: str) -> None:
        self.add_probe(
            probe_id=f"tone/{profile_id}/fixed",
            kind=self._profile_kind(coverage),
            x_mm=x_mm, y_mm=y_mm, w_mm=w_mm, h_mm=h_mm, plane=plane,
            group="tone-metrology",
            params={"mode": "fixed-profile", "coverage": coverage,
                    "station": profile_id, "axis": axis},
        )

    def add_background_witnesses(self) -> None:
        positions = [
            (23.0, 55.0), (23.0, 114.0), (23.0, 173.0), (23.0, 232.0),
            (184.0, 55.0), (184.0, 114.0), (184.0, 173.0), (184.0, 232.0),
            (104.0, 25.5), (104.0, 272.5),
        ]
        for index, (x_mm, y_mm) in enumerate(positions):
            self.add_probe(
                probe_id=f"background/paper-{index}", kind="paper",
                x_mm=x_mm, y_mm=y_mm, w_mm=2.0, h_mm=2.0,
                group="background", dpi=600,
                params={"station": index},
            )

    def add_color_registration_targets(self) -> None:
        planes = "KCMY"
        for row, y_mm in enumerate((101.0, 159.5, 217.5)):
            for col, x_mm in enumerate((28.0, 101.0, 174.0)):
                target = f"r{row}c{col}"
                for index, plane in enumerate(planes):
                    self.add_probe(
                        probe_id=f"registration/{target}/{plane}",
                        kind="registration_cross",
                        x_mm=x_mm + 2.0 * index, y_mm=y_mm,
                        w_mm=1.5, h_mm=3.0, plane=plane, dpi=600,
                        group="plane-registration",
                        params={"target": target, "plane_index": index,
                                "stroke_dots": 2},
                    )

    def add_probe_matrix(self, *, color: bool) -> None:
        planes = "KCMY" if color else "K"
        size, gap = 4.6, 1.0
        # Fine H/V frequency and isolated-feature ladders.
        specs: list[tuple[str, dict[str, Any]]] = []
        for orientation in ("horizontal_lines", "vertical_lines"):
            for width in (1, 2, 3, 4):
                specs.append(("grating", {
                    "orientation": orientation, "on_dots": width,
                    "off_dots": width,
                }))
        for orientation in ("horizontal_lines", "vertical_lines"):
            for width in (1, 2, 3, 4):
                specs.append(("line_width", {
                    "orientation": orientation, "width_dots": width,
                    "period_dots": 4 * width,
                }))
        for width in (1, 2, 3, 4):
            specs.append(("isolated_dots", {"dot_dots": width,
                                             "pitch_dots": 4 * width + 4}))
            specs.append(("white_holes", {"hole_dots": width,
                                           "pitch_dots": 4 * width + 4}))
        for stroke in (1, 2, 3, 4):
            specs.append(("microtext", {"stroke_dots": stroke,
                                         "text": "E025 METRY"}))
        specs.extend([
            ("slanted_edge", {"angle_deg": 5.0}),
            ("slanted_edge", {"angle_deg": 45.0}),
            ("checker", {"n_dots": 1}),
            ("checker", {"n_dots": 2}),
        ])
        columns = 6
        for index, (kind, params) in enumerate(specs):
            plane = planes[index % len(planes)]
            col, row = index % columns, index // columns
            self.add_probe(
                probe_id=f"morph/{plane}/{kind}-{index}", kind=kind,
                x_mm=28.0 + col * (size + gap),
                y_mm=47.0 + row * (size + gap),
                w_mm=size, h_mm=size, plane=plane, group="morphology",
                params=params,
            )

    def add_phase_rails(self) -> None:
        self.add_probe(
            probe_id="geometry/rx", kind="phase_rail",
            x_mm=28.0, y_mm=265.0, w_mm=154.0, h_mm=2.0,
            group="geometry", params={
                "orientation": "vertical_lines", "on_dots": 3,
                "off_dots": 3, "axis": "x",
            }, dpi=600,
        )
        self.add_probe(
            probe_id="geometry/ry", kind="phase_rail",
            x_mm=188.5, y_mm=47.0, w_mm=2.0, h_mm=196.0,
            group="geometry", params={
                "orientation": "horizontal_lines", "on_dots": 3,
                "off_dots": 3, "axis": "y",
            }, dpi=600,
        )

    def build_mono(self) -> None:
        for index, (y_mm, coverage) in enumerate(zip(
                (31.0, 89.0, 147.0, 205.0),
                (1.0, 0.50, 0.75, 0.25), strict=True)):
            self.add_tone_station(
                station_id=f"k-horizontal-{index}", plane="K",
                x_mm=28.0, y_mm=y_mm, w_mm=154.0, h_mm=2.2,
                fixed_coverage=coverage,
                response_order=self._coverage_order(2 * index),
            )
        self.add_tone_station(
            station_id="k-vertical", plane="K", x_mm=20.0, y_mm=31.0,
            w_mm=2.2, h_mm=230.0, vertical=True,
            fixed_coverage=0.50,
            response_order=self._coverage_order(1, reverse=True),
        )
        self.add_probe_matrix(color=False)

        # Equal physical pitch, distinct authored grids.  These controls say
        # whether a finer addressing path adds information or merely resamples.
        grids = (self.primary_grid,) + self.comparison_grids
        grids = tuple(dict.fromkeys(sorted(grids)))
        for index, grid_dpi in enumerate(grids[:4]):
            cell = max(1, round(2 * grid_dpi / self.primary_grid))
            self.add_random_field(
                field_id=f"grid-control/{grid_dpi}-c{cell}",
                definition_id="k1-mask", grid_dpi=grid_dpi, cell=cell,
                x_mm=64.0 + 29.5 * index, y_mm=47.0,
                w_mm=27.0, h_mm=15.0, role="equal-pitch-control",
            )
        for index, cell in enumerate((1, 2, 3)):
            self.add_random_field(
                field_id=f"frontier/top/c{cell}", definition_id="k1-mask",
                grid_dpi=self.primary_grid, cell=cell,
                x_mm=64.0 + 39.0 * index, y_mm=66.0,
                w_mm=36.0, h_mm=7.5, role="frontier-control",
            )
        shape_fields = (
            ("factor/shape/solid-c2", "k1-mask", 2, "shape-control"),
            ("factor/shape/diagonal-c2", "k1-diagonal-mask", 2,
             "shape-control"),
            ("factor/shape/horizontal-c2", "k1-horizontal-mask", 2,
             "shape-control"),
            ("factor/shape/vertical-c2", "k1-vertical-mask", 2,
             "shape-control"),
            ("factor/aspect/c1x2", "k1-mask", (1, 2), "aspect-control"),
            ("factor/aspect/c2x1", "k1-mask", (2, 1), "aspect-control"),
        )
        for index, (field_id, definition_id, cell, role) in enumerate(shape_fields):
            self.add_random_field(
                field_id=field_id, definition_id=definition_id,
                grid_dpi=self.primary_grid, cell=cell,
                x_mm=64.0 + 19.5 * index, y_mm=75.5,
                w_mm=17.5, h_mm=7.0, role=role,
            )

        self.add_random_field(
            field_id="spatial/top/c2", definition_id="k1-mask",
            grid_dpi=self.primary_grid, cell=2,
            x_mm=28.0, y_mm=94.0, w_mm=74.0, h_mm=46.0,
        )
        self.add_random_field(
            field_id="spatial/top/c3", definition_id="k1-mask",
            grid_dpi=self.primary_grid, cell=3,
            x_mm=108.0, y_mm=94.0, w_mm=74.0, h_mm=46.0,
        )
        self.add_random_field(
            field_id="spatial/middle/c1", definition_id="k1-mask",
            grid_dpi=self.primary_grid, cell=1,
            x_mm=28.0, y_mm=152.0, w_mm=35.0, h_mm=45.0,
        )
        self.add_random_field(
            field_id="spatial/middle/c2", definition_id="k1-mask",
            grid_dpi=self.primary_grid, cell=2,
            x_mm=67.0, y_mm=152.0, w_mm=75.0, h_mm=45.0,
        )
        self.add_random_field(
            field_id="spatial/middle/c4", definition_id="k1-mask",
            grid_dpi=self.primary_grid, cell=4,
            x_mm=146.0, y_mm=152.0, w_mm=36.0, h_mm=45.0,
        )
        self.add_random_field(
            field_id="spatial/bottom/c2", definition_id="k1-mask",
            grid_dpi=self.primary_grid, cell=2,
            x_mm=28.0, y_mm=210.0, w_mm=75.0, h_mm=33.0,
        )
        self.add_random_field(
            field_id="spatial/bottom/c3", definition_id="k1-mask",
            grid_dpi=self.primary_grid, cell=3,
            x_mm=108.0, y_mm=210.0, w_mm=48.0, h_mm=33.0,
        )
        self.add_random_field(
            field_id="spatial/bottom/c6", definition_id="k1-mask",
            grid_dpi=self.primary_grid, cell=6,
            x_mm=160.0, y_mm=210.0, w_mm=22.0, h_mm=15.0,
        )
        for index, rate_id in enumerate(("r0550", "r0775")):
            self.add_fec_coupon(
                field_id=f"fec/c2/{rate_id}", definition_id="k1-mask",
                grid_dpi=self.primary_grid, cell=2,
                x_mm=160.0, y_mm=229.0 + 5.0 * index,
                rate_id=rate_id,
            )

    def build_color(self) -> None:
        for index, plane in enumerate("KYMC"):
            self.add_tone_station(
                station_id=f"{plane.lower()}-horizontal-top", plane=plane,
                x_mm=28.0, y_mm=31.0 + 3.1 * index,
                w_mm=154.0, h_mm=2.3,
                fixed_coverage=1.0,
                response_order=self._coverage_order(2 * index),
            )
            self.add_tone_station(
                station_id=f"{plane.lower()}-horizontal-bottom", plane=plane,
                x_mm=28.0, y_mm=249.0 + 3.1 * index,
                w_mm=154.0, h_mm=2.3,
                fixed_coverage=0.50,
                response_order=self._coverage_order(2 * index + 1,
                                                    reverse=True),
            )
            self.add_fixed_profile(
                profile_id=f"{plane.lower()}-vertical-feed", plane=plane,
                x_mm=192.0 + 0.95 * index, y_mm=47.0,
                w_mm=0.65, h_mm=196.0, coverage=0.50, axis="y",
            )
        self.add_color_registration_targets()
        self.add_probe_matrix(color=True)

        pure = (("k1-mask", "K"), ("c1-mask", "C"),
                ("m1-mask", "M"), ("y1-mask", "Y"))
        for index, (definition_id, plane) in enumerate(pure):
            col, row = index % 2, index // 2
            self.add_random_field(
                field_id=f"pure/{plane}/c2", definition_id=definition_id,
                grid_dpi=self.primary_grid, cell=2,
                x_mm=68.0 + 58.0 * col, y_mm=48.0 + 27.0 * row,
                w_mm=54.0, h_mm=23.0, role="pure-plane-control",
            )

        self.add_random_field(
            field_id="states/middle/cm4-c2", definition_id="cm4-image",
            grid_dpi=self.primary_grid, cell=2,
            x_mm=28.0, y_mm=106.0, w_mm=72.0, h_mm=52.0,
        )
        self.add_random_field(
            field_id="states/middle/cmy8-c2", definition_id="cmy8-image",
            grid_dpi=self.primary_grid, cell=2,
            x_mm=106.0, y_mm=106.0, w_mm=76.0, h_mm=52.0,
        )
        bottom_fields = (
            ("states/bottom/cm4-c3", "cm4-image", 3,
             28.0, 164.0, 40.0, 22.0, "spatial-control"),
            ("states/bottom/cmy8-c3", "cmy8-image", 3,
             72.0, 164.0, 44.0, 22.0, "spatial-control"),
            ("states/top/kcmy4-c2", "kcmy4-image", 2,
             120.0, 164.0, 62.0, 22.0, "constellation-control"),
            ("states/bottom/cmy8-c2", "cmy8-image", 2,
             28.0, 190.0, 70.0, 26.0, "spatial-control"),
            ("states/bottom/cmy8-opm-c2", "cmy8-opm", 2,
             102.0, 190.0, 38.0, 26.0, "emission-path-control"),
            ("states/bottom/kcmy4-c2", "kcmy4-image", 2,
             144.0, 190.0, 38.0, 26.0, "constellation-control"),
        )
        for (field_id, definition_id, cell, x_mm, y_mm, w_mm, h_mm,
             role) in bottom_fields:
            self.add_random_field(
                field_id=field_id, definition_id=definition_id,
                grid_dpi=self.primary_grid, cell=cell,
                x_mm=x_mm, y_mm=y_mm, w_mm=w_mm, h_mm=h_mm, role=role,
            )

        grids = (self.primary_grid,) + self.comparison_grids
        grids = tuple(dict.fromkeys(sorted(grids)))
        for index, grid_dpi in enumerate(grids[:4]):
            cell = max(1, round(2 * grid_dpi / self.primary_grid))
            self.add_random_field(
                field_id=f"grid-control/cmy8-{grid_dpi}-c{cell}",
                definition_id="cmy8-image", grid_dpi=grid_dpi, cell=cell,
                x_mm=28.0 + 27.0 * index, y_mm=222.0,
                w_mm=24.0, h_mm=16.0, role="equal-pitch-control",
            )
        for index, rate_id in enumerate(("r0550", "r0700", "r0775")):
            self.add_fec_coupon(
                field_id=f"fec/cmy8-c2/{rate_id}",
                definition_id="cmy8-image",
                grid_dpi=self.primary_grid, cell=2,
                x_mm=138.0, y_mm=222.0 + 5.0 * index,
                rate_id=rate_id,
            )

    def build(self) -> None:
        self.doc.begin_page()
        self.doc.put_raw(_ps_device_payload(
            bundle_id=self.bundle_id, page_kind=self.page_kind,
            primary_grid=self.primary_grid, request=self.request,
        ))
        self.add_infrastructure()
        self.add_edge_measurements()
        self.add_background_witnesses()
        self.label(
            f"E025 {self.page_kind.upper()} {self.page['page_id']}  "
            f"grid={self.primary_grid} seed={ec.SEED_TEXT}",
            75.0, 19.0, 5.2,
        )
        if self.page_kind == "mono":
            self.build_mono()
        else:
            self.build_color()
        self.add_phase_rails()
        self.label("physical channel evidence; FEC coupons are confirmation only",
                   69.0, 270.0, 4.0)
        self.doc.end_page()


def capacity_rows(page: dict[str, Any], *, safe_margin_mm: float = 10.0
                  ) -> list[dict[str, Any]]:
    width = ec.PAGE_MM[0] - 2 * safe_margin_mm
    height = ec.PAGE_MM[1] - 2 * safe_margin_mm
    rows = []
    for key, value in sorted(page["candidates"].items()):
        grid = GridSpec.from_dict(value["grid"])
        nx = int(width / grid.cell_pitch_mm_x)
        ny = int(height / grid.cell_pitch_mm_y)
        bits = nx * ny * float(value["payload_bits_per_cell"])
        rows.append({
            "candidate_id": key, "safe_margin_mm": safe_margin_mm,
            "usable_width_mm": width, "usable_height_mm": height,
            "nx": nx, "ny": ny, "raw_bits": bits,
            "raw_megabytes": bits / 8e6,
            "raw_bits_per_mm2": float(value["raw_bits_per_mm2"]),
        })
    return rows


def emit(*, output_prefix: Path, page_kind: str, primary_grid: int,
         comparison_grids: tuple[int, ...], request: tuple[int, int] | None,
         preset: str = "custom", write: bool = True
         ) -> tuple[Path, Path, dict[str, Any]]:
    config = {
        "schema": ec.SCHEMA, "layout_version": ec.LAYOUT_VERSION,
        "seed": ec.SEED_TEXT, "preset": preset, "page_kind": page_kind,
        "primary_authored_grid": [primary_grid, primary_grid],
        "comparison_authored_grids": [[value, value] for value in comparison_grids],
        "requested_dpi": None if request is None else list(request),
    }
    bundle_id = hashlib.sha256(ec.SEED + b"/" + _canonical(config)).hexdigest()[:12]
    builder = PageBuilder(
        page_kind=page_kind, primary_grid=primary_grid,
        comparison_grids=comparison_grids, request=request,
        bundle_id=bundle_id,
    )
    builder.build()
    ps_text = builder.doc.render()
    manifest: dict[str, Any] = {
        **config, "bundle_id": bundle_id, "base_layout_dpi": ec.BASE_DPI,
        "page_size_mm": list(ec.PAGE_MM), "page_size_pt": list(A4_PT),
        "pages": [builder.page],
        "nominal_capacity_at_10mm_margin": capacity_rows(builder.page),
        "ps_bytes": len(ps_text.encode("ascii")),
        "postscript_sha256": hashlib.sha256(ps_text.encode("ascii")).hexdigest(),
    }
    manifest["manifest_semantic_sha256"] = hashlib.sha256(
        _canonical(manifest)
    ).hexdigest()
    ps_path = output_prefix.with_suffix(".ps")
    manifest_path = output_prefix.parent / f"{output_prefix.name}_manifest.json"
    if write:
        ps_path.parent.mkdir(parents=True, exist_ok=True)
        ps_path.write_text(ps_text, encoding="ascii")
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
    return ps_path, manifest_path, manifest


def _request(text: str, primary_grid: int) -> tuple[int, int] | None:
    if text == "default":
        return None
    if text == "authored":
        return primary_grid, primary_grid
    return ec.parse_pair(text)


def _print_capacity(manifest: dict[str, Any]) -> None:
    page = manifest["pages"][0]
    print(
        f"E025 {manifest['page_kind']} page: {len(page['fields'])} channel fields, "
        f"{len(page['probes'])} physical probes, "
        f"{manifest['ps_bytes'] / 1e6:.2f} MB PostScript"
    )
    print("candidate                              raw b/mm2  raw MB @10mm")
    seen = set()
    for row in manifest["nominal_capacity_at_10mm_margin"]:
        # Many distributed fields share one candidate; capacity rows are unique.
        if row["candidate_id"] in seen:
            continue
        seen.add(row["candidate_id"])
        print(f"{row['candidate_id']:<38} {row['raw_bits_per_mm2']:9.2f} "
              f"{row['raw_megabytes']:13.2f}")
    print("The 10 mm table is planning only; scan analysis replaces it with the")
    print("measured payload-safe rectangle and reports raw, MI, and FEC capacities.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=tuple(PRESETS), default="hp-m281-bw")
    parser.add_argument("--kind", choices=("mono", "color"),
                        help="override preset page kind")
    parser.add_argument("--primary-grid", type=int, default=600)
    parser.add_argument(
        "--comparison-grids", default=",".join(map(str, DEFAULT_COMPARISON_GRIDS)),
        help="comma-separated authored-grid controls (default: 300,1200,2400)",
    )
    parser.add_argument(
        "--request", default="authored",
        help="authored, default (omit HWResolution), or XxY",
    )
    parser.add_argument("--out", type=Path,
                        help="output prefix (default: experiment build/PRESET)")
    parser.add_argument("--capacity-only", action="store_true")
    args = parser.parse_args()
    kind = args.kind or PRESETS[args.preset]
    comparisons = tuple(
        int(token) for token in args.comparison_grids.split(",") if token.strip()
    )
    if args.primary_grid <= 0 or any(value <= 0 for value in comparisons):
        raise SystemExit("authored grids must be positive")
    output = args.out or (
        Path(__file__).resolve().parent / "build" / args.preset
    )
    ps_path, manifest_path, manifest = emit(
        output_prefix=output, page_kind=kind,
        primary_grid=args.primary_grid, comparison_grids=comparisons,
        request=_request(args.request, args.primary_grid), preset=args.preset,
        write=not args.capacity_only,
    )
    _print_capacity(manifest)
    if args.capacity_only:
        return
    print(f"PostScript {ps_path}")
    print(f"Manifest   {manifest_path}")


if __name__ == "__main__":
    main()
