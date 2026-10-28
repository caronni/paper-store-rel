"""Optional sidecar manifest — convenience, never required for decode.

Printed sheets are self-describing (metadata channel + payload
envelope); this JSON exists for humans and for print-run bookkeeping.

Two identity namespaces write through here.  A v1 row records the legacy
spec id and its printer-derived geometry.  A v2 row records the canonical
format id (which IS the seed) plus the emission facts that are
deliberately NOT identity: paper profile, engine grid, dots/cell, and
where the field landed on the page (FORMAT-SPACE §7/§9).
"""
from __future__ import annotations

import json
from pathlib import Path

from ..format.layout import TILE_CELLS
from ..format.profiles import Family
from .sheet import SheetLayout


def _column_groups_block(spec) -> dict:
    groups = spec.column_groups
    if groups.uniform:
        return {}
    return {"column_groups": {
        "n_groups": groups.n_groups,
        "symbol_bits": groups.symbol_bits,
        "carried_per_tile": dict(zip(spec.stream_ids, groups.carried)),
        "spare_bits_per_site": str(groups.spare_bits_per_site),
        "dead_plane_ceiling": {
            stream_id: str(groups.plane_tier_ceiling(index))
            for index, stream_id in enumerate(spec.stream_ids)},
    }}


def write_manifest(path: Path, vol, *, profile=None,
                   printer_id: str | None = None,
                   sheet: SheetLayout | None = None) -> dict:
    """profile: the PayloadProfile actually used, or None for explicit
    coding + dial selections (recorded as "custom"). Every manifest
    carries the provisional flag until a print qualifies
    (HOLO-DESIGN §11).

    sheet: the v2 emission placement (required for a v2 row, refused for
    a v1 row, whose page geometry is derived)."""
    spec = vol.plan.spec
    is_v2 = spec.coding.namespace == "v2"
    if is_v2 and sheet is None:
        raise ValueError(
            f"{spec.spec_id}: a v2 manifest records the sheet it was "
            f"placed on — pass the emission's SheetLayout")
    if not is_v2 and sheet is not None:
        raise ValueError(
            f"{spec.spec_id}: a v1 row's page geometry is derived from "
            f"media x margin; it has no sheet placement to record")
    field_dots_yx = (sheet.field_dots_yx if sheet is not None
                     else spec.layout.field_dots_yx)
    cells_yx = spec.cells_yx
    tiles_yx = [cells_yx[0] // TILE_CELLS, cells_yx[1] // TILE_CELLS]
    page_rows = [
        {"page": p.page, "ps": p.ps_path.name,
         "ps_sha256": p.ps_sha256, "gt": p.gt_path.name,
         "gt_sha256": p.gt_sha256,
         "gt_packed_shape": list(field_dots_yx[:-1])
         + [-(-field_dots_yx[1] // 8)],
         "gt_bitorder": "big"}
        for p in vol.pages
    ]
    is_color = spec.codec_family is not Family.K
    if is_color:
        h, w = field_dots_yx
        for page_row, page in zip(page_rows, vol.pages, strict=True):
            if page.gt_plane_sha256 is None:
                raise ValueError("color page is missing plane GT digests")
            page_row.update({
                "gt_packed_shape": [3, h, -(-w // 8)],
                "gt_axis_order": ["plane", "y", "packed_x"],
                "gt_plane_order": ["C", "M", "Y"],
                "gt_plane_sha256": list(page.gt_plane_sha256),
            })

    doc = {
        "holo": "v2" if is_v2 else "v1",
        **({"status": "provisional — no printed format has qualified yet"}
           if is_v2 else
           {"v1_status": "provisional — no format-v1 print qualified yet"}),
        "profile": ({"name": profile.name, "evidence": profile.evidence,
                     "priced_on": profile.priced_on} if profile is not None
                    else {"name": "custom",
                          "evidence": "none — explicit parameters"}),
        "printer_id": printer_id,
        "spec_id": spec.spec_id,
        # The canonical v2 id is the whole identity AND the seed payload.
        **({"format_id": spec.spec_id} if is_v2 else {}),
        "coding_id": spec.coding.coding_id,
        "media_id": sheet.media_id if is_v2 else spec.media_id,
        "margin_mm": sheet.margin_mm if is_v2 else spec.margin_mm,
        # Emission facts, never identity (FORMAT-SPACE §5/§9).
        **({"paper": sheet.paper.name,
            "engine_dpi": sheet.engine_dpi,
            "pitch": str(spec.pitch),
            "dots_per_cell": sheet.dots_per_cell,
            "page_dots_xy": list(sheet.page_dots_xy),
            "origin_dots_yx": list(sheet.origin_dots_yx),
            "borders_mm": {"top": round(sheet.border_top_mm, 3),
                           "bottom": round(sheet.border_bottom_mm, 3),
                           "left": round(sheet.border_left_mm, 3),
                           "right": round(sheet.border_right_mm, 3)}}
           if is_v2 else {}),
        "seed": spec.seed.decode(),
        "family_seed": spec.family_seed.decode(),
        "rate_id": spec.rate_id,
        # v1: dots/cell on the frozen 600 grid.  v2: dots/cell on THIS
        # emission's engine grid (== dots_per_cell above).
        "cell_dots": sheet.dots_per_cell if is_v2 else spec.cell_dots,
        "page_cells_yx": list(cells_yx),
        "tiles_yx": tiles_yx,
        "payload": {
            "bytes": vol.plan.payload_bytes,
            "sha256": vol.payload_sha256,
        },
        "volume": {
            "fountain_version": "fountain-v2",
            "k_total": vol.plan.k_total,
            "n_pages": vol.plan.n_pages,
            "n_symbols_total": vol.plan.n_symbols_total,
            "symbol_bits": vol.plan.symbol_bits,
            "q_dial": vol.plan.q,
            "effective_k_over_n": round(vol.plan.effective_k_over_n, 6),
        },
        # -v0 manifests are byte-stable: pooled keys appear only on
        # pooled rows (docs/CMY8-POOLED-FOUNTAIN.md), and the column-group
        # block only where the streams differ in width
        # (docs/CMY8-COLUMN-GROUPS.md) — uniform -v1 manifests are
        # byte-stable too.
        **({"pooled_fountain": {
            "pooled": True,
            "k_meta": vol.plan.k_meta,
            "n_streams": spec.n_streams,
            "esi": "counter*n_streams + stream_idx",
            "metadata_k_field": "k_meta (k_total = n_streams*k_meta)",
            "plane_tier": vol.plan.plane_tier,
            **_column_groups_block(spec),
        }} if spec.pooled_fountain else {}),
        "pages": page_rows,
        "print_command": "scripts/print_plane.sh <ps-file>   # raw 9100",
        "note": ("sidecar only — printed sheets decode with zero "
                 "out-of-band data") if is_v2 else
                "sidecar only — v1 sheets decode with zero out-of-band data",
    }
    if is_color:
        doc["codec"] = {
            "codec_id": spec.codec_id,
            "state_names": list(spec.codec.state_names),
            "word_states": list(spec.codec.word_states),
            "furniture": {
                "word_sites": 100,
                "dust_sites": spec.n_dust,
                "payload_cells": spec.payload_cells,
            },
            "renderer": {
                "color_space": "DeviceCMYK",
                "bits_per_component": 1,
                "plane_order": ["C", "M", "Y"],
                "K": "zero",
                "operation": "one composite image",
            },
            "streams": [
                {
                    "stream_id": stream.stream_id,
                    "symbol_bits": stream.symbol_bits,
                    "user_bits": stream.user_bits,
                    "fec_bank_id": stream.fec.profile_id,
                    "children": [
                        {
                            "code_id": child.code_id,
                            "shortened_info_tail":
                                child.shortened_info_tail,
                        }
                        for child in stream.fec.children
                    ],
                }
                for stream in spec.stream_profiles
            ],
        }
        doc["volume"]["stream_symbol_bits"] = list(spec.stream_symbol_bits)
        doc["volume"]["aggregate_symbol_bits"] = \
            spec.aggregate_symbol_bits
        doc["volume"]["n_streams"] = len(spec.stream_profiles)
    path.write_text(json.dumps(doc, indent=1) + "\n")
    return doc
