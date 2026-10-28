"""Opt-in, authentic-scan qualification for the E021 production port.

The ordinary qualification battery is deliberately small and synthetic.
This module exercises the same differential contract on the large, local
scanner corpus without making tens of gigabytes of captures a CI dependency.

Two subprocesses process every case sequentially:

* ``holo`` opens the original capture and runs :func:`survey_raster`;
* ``legacy`` opens the same capture, writes the canonical E021 float32
  feature plane to a temporary memmap, and runs frozen
  :func:`paperholo.platen.detect_payload_regions`.

Before comparing segmentation, both workers must agree on the encoded source
hash and canonical feature-plane hash.  The comparison then covers every
externally visible E021 value and a streamed SHA-256 of every native support
mask bit.  Holo's compact support is expanded in bounded row strips; a
page-sized second mask is never materialized.

Examples::

    python -m holo.receive.qualification.e021_real --lane smoke
    python -m holo.receive.qualification.e021_real --lane campaign \
        --report scratch/e021-holo-authentic.json
    python -m holo.receive.qualification.e021_real --lane full \
        --report scratch/e021-holo-authentic-full.json

``smoke`` includes authentic grey/RGB decoder controls and c2/c3 HP scans.
``campaign`` adds the six authentic c3 confetti derivatives.  ``full`` adds
the multi-gigabyte native Canon scans and is intended as an offline release
gate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Iterator

import numpy as np
from scipy import ndimage

from holo.receive.scan import Raster, open_capture
from holo.receive.survey import (
    PayloadSurvey,
    SUPPORT_HOLE_RADIUS_CELLS,
    SupportMask,
    survey_raster,
)


REPORT_SCHEMA = "holo-e021-authentic-qualification-v1"
MASK_HASH_CHUNK_BYTES = 64 << 20
FEATURE_CHUNK_BYTES = 64 << 20
ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True)
class RealScanCase:
    """One immutable corpus declaration.

    ``expected_c="any"`` means differential parity only.  ``None`` is an
    asserted honest global-c refusal.  Region counts are asserted only when
    physical piece counts or a deliberate full-sheet contract are known.
    """

    name: str
    relative_path: str
    dpi: float
    tier: int
    expected_c: int | None | str = "any"
    expected_regions: int | None = None
    role: str = "differential"
    repeat_group: str | None = None

    def __post_init__(self) -> None:
        if not self.name or "/" in self.name:
            raise ValueError("case name must be a non-empty path-free label")
        path = Path(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("corpus paths must be repository-relative")
        if not math.isfinite(self.dpi) or self.dpi <= 0:
            raise ValueError("case dpi must be finite and positive")
        if self.tier not in (0, 1, 2):
            raise ValueError("case tier must be 0, 1, or 2")
        if not (
            self.expected_c == "any"
            or self.expected_c is None
            or (
                isinstance(self.expected_c, int)
                and not isinstance(self.expected_c, bool)
                and self.expected_c > 0
            )
        ):
            raise ValueError("expected_c must be 'any', None, or positive int")
        if (
            self.expected_regions is not None
            and (
                isinstance(self.expected_regions, bool)
                or self.expected_regions < 0
            )
        ):
            raise ValueError("expected_regions must be non-negative or None")


CORPUS: tuple[RealScanCase, ...] = (
    # Small authentic scanner controls.  The third is the strongest real
    # retained-hole example in the repository.
    RealScanCase(
        "xerox-grey-c6",
        "scans/xeroxscanner-orig-disc1p2-grey-600.tif",
        600.0,
        0,
        expected_c=6,
        expected_regions=31,
        role="authentic-grey-ingest",
    ),
    RealScanCase(
        "xerox-rgb-mixed-c",
        "scans/xeroxscanner-orig-disc1p1-col-600.tif",
        600.0,
        0,
        expected_c=None,
        expected_regions=48,
        role="authentic-rgb-ingest",
    ),
    RealScanCase(
        "xerox-rgb-large-holes-c5",
        "scans/xeroxscanner-orig-e006bw-col-600.tif",
        600.0,
        0,
        expected_c=5,
        expected_regions=34,
        role="authentic-retained-hole-topology",
    ),
    # Same full-sheet material at the inexpensive HP 1200-dpi footing.
    RealScanCase(
        "e018b-c2-hp1200",
        "scratch/e018b/hp-e018b-c2-hp-1200-page.tiff.png",
        1200.0,
        0,
        expected_c=2,
        expected_regions=1,
        role="c2-full-sheet",
        repeat_group="e018b-c2-sheet",
    ),
    RealScanCase(
        "e018b-c2-hp1200-second",
        "scratch/e018b/hp-e018b-c2-hp-1200-page-2nd.png",
        1200.0,
        0,
        expected_c=2,
        expected_regions=1,
        role="c2-full-sheet-repeat",
        repeat_group="e018b-c2-sheet",
    ),
    RealScanCase(
        "e018b-c3-hp1200",
        "scratch/e018b/hp-e018b-c3-hp-1200-page.tiff.png",
        1200.0,
        0,
        expected_c=3,
        expected_regions=1,
        role="c3-full-sheet",
        repeat_group="e018b-c3-sheet",
    ),
    # Authentic c3 scanner pixels decimated to the historical 1600-dpi
    # receiver footing.  Physical piece counts were inspected by hand.
    RealScanCase(
        "e018-c3-confetti-1-1600",
        "scratch/e018/decimated-1_1600.tiff",
        1600.0,
        1,
        expected_c=3,
        expected_regions=17,
        role="c3-confetti-count",
        repeat_group="e018-c3-confetti-1",
    ),
    RealScanCase(
        "e018-c3-confetti-1b-1600",
        "scratch/e018/decimated-1-2nd_1600.tiff",
        1600.0,
        1,
        expected_c=3,
        expected_regions=17,
        role="c3-confetti-repeat",
        repeat_group="e018-c3-confetti-1",
    ),
    RealScanCase(
        "e018-c3-confetti-2-1600",
        "scratch/e018/decimated-2_1600.tiff",
        1600.0,
        1,
        expected_c=3,
        expected_regions=10,
        role="c3-confetti-count",
        repeat_group="e018-c3-confetti-2",
    ),
    RealScanCase(
        "e018-c3-confetti-2b-1600",
        "scratch/e018/decimated-2-2nd_1600.tiff",
        1600.0,
        1,
        expected_c=3,
        expected_regions=10,
        role="c3-confetti-repeat",
        repeat_group="e018-c3-confetti-2",
    ),
    RealScanCase(
        "e018-c3-confetti-3-1600",
        "scratch/e018/decimated-3_1600.tiff",
        1600.0,
        1,
        expected_c=3,
        expected_regions=8,
        role="c3-close-scraps",
        repeat_group="e018-c3-confetti-3",
    ),
    RealScanCase(
        "e018-c3-confetti-3b-1600",
        "scratch/e018/decimated-3-2nd_1600.tiff",
        1600.0,
        1,
        expected_c=3,
        expected_regions=8,
        role="c3-close-scraps-repeat",
        repeat_group="e018-c3-confetti-3",
    ),
    RealScanCase(
        "e012-c3-canon2400",
        "scans/xerox-e012-A-canon-2400bw.png",
        2400.0,
        1,
        expected_c=3,
        expected_regions=1,
        role="cross-resolution-c3-full-sheet",
        repeat_group="e012-c3-resolution",
    ),
    # Native Canon 4800-dpi release corpus.
    RealScanCase(
        "e012-c3-canon4800",
        "scans/xerox-e012-A-canon-4800.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=1,
        role="native-c3-full-sheet",
        repeat_group="e012-c3-resolution",
    ),
    RealScanCase(
        "e014-c2-canon4800",
        "scans/xerox-e014-A-canon-4800gray.tiff",
        4800.0,
        2,
        expected_c=2,
        expected_regions=1,
        role="native-c2-full-sheet",
        repeat_group="e014-c2-displacement",
    ),
    RealScanCase(
        "e014-c2-canon4800-displaced",
        "scans/xerox-e014-A-canon-4800gray-B-displaced.tiff",
        4800.0,
        2,
        expected_c=2,
        expected_regions=1,
        role="native-c2-displacement",
        repeat_group="e014-c2-displacement",
    ),
    RealScanCase(
        "e014-c2-canon4800-flattened",
        "scans/xerox-e014-A-canon-4800gray-C-flattened.tiff",
        4800.0,
        2,
        expected_c=2,
        expected_regions=1,
        role="native-c2-displacement",
        repeat_group="e014-c2-displacement",
    ),
    RealScanCase(
        "e018-c3-confetti-1-native",
        "scratch/e018/hp-e018-canon-4800-confetti-1.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=17,
        role="native-c3-confetti",
        repeat_group="e018-c3-confetti-1-native",
    ),
    RealScanCase(
        "e018-c3-confetti-1b-native",
        "scratch/e018/hp-e018-canon-4800-confetti-1-2ndtake.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=17,
        role="native-c3-confetti-repeat",
        repeat_group="e018-c3-confetti-1-native",
    ),
    RealScanCase(
        "e018-c3-confetti-2-native",
        "scratch/e018/hp-e018-canon-4800-confetti-2.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=10,
        role="native-c3-confetti",
        repeat_group="e018-c3-confetti-2-native",
    ),
    RealScanCase(
        "e018-c3-confetti-2b-native",
        "scratch/e018/hp-e018-canon-4800-confetti-2-2ndtake.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=10,
        role="native-c3-confetti-repeat",
        repeat_group="e018-c3-confetti-2-native",
    ),
    RealScanCase(
        "e018-c3-confetti-3-native",
        "scratch/e018/hp-e018-canon-4800-confetti-3.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=8,
        role="native-c3-close-scraps",
        repeat_group="e018-c3-confetti-3-native",
    ),
    RealScanCase(
        "e018-c3-confetti-3b-native",
        "scratch/e018/hp-e018-canon-4800-confetti-3-2ndtake.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=8,
        role="native-c3-close-scraps-repeat",
        repeat_group="e018-c3-confetti-3-native",
    ),
    RealScanCase(
        "e016-c2-full-native",
        "scratch/e016c2hp-canon4800gray.tiff",
        4800.0,
        2,
        expected_c=2,
        expected_regions=1,
        role="native-c2-full-sheet",
        repeat_group="e016-c2-displacement",
    ),
    RealScanCase(
        "e016-c2-full-native-displaced-1",
        "scratch/e016c2hp-canon4800gray-displaced-1.tiff",
        4800.0,
        2,
        expected_c=2,
        expected_regions=1,
        role="native-c2-displacement",
        repeat_group="e016-c2-displacement",
    ),
    RealScanCase(
        "e016-c2-full-native-displaced-2",
        "scratch/e016c2hp-canon4800gray-displaced-2.tiff",
        4800.0,
        2,
        expected_c=2,
        expected_regions=1,
        role="native-c2-displacement",
        repeat_group="e016-c2-displacement",
    ),
    RealScanCase(
        "e017-c3-rgb-native-second",
        "scratch/hp-e017-arch-c-canon-4800rgb-take2.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=1,
        role="native-c3-rgb-full-sheet-repeat",
        repeat_group="e017-c3-rgb",
    ),
    RealScanCase(
        "e018b-c2-canon4800",
        "scratch/e018b/hp-e018b-c2-canon-4800-page.tiff",
        4800.0,
        2,
        expected_c=2,
        expected_regions=1,
        role="cross-scanner-c2-full-sheet",
        repeat_group="e018b-c2-sheet",
    ),
    RealScanCase(
        "e018b-c3-canon4800",
        "scratch/e018b/hp-e018b-c3-canon-4800-page.tiff",
        4800.0,
        2,
        expected_c=3,
        expected_regions=1,
        role="cross-scanner-c3-full-sheet",
        repeat_group="e018b-c3-sheet",
    ),
    # Later authentic c2 confetti campaigns: expected c is independent
    # truth, while region counts remain differential evidence until physical
    # polygons/counts are frozen.
    RealScanCase(
        "e023c-c2-confetti-a1",
        "scratch/e023c/e023c-hp-canon-4800-grey-c2-confetti.tiff",
        4800.0,
        2,
        expected_c=2,
        role="native-c2-confetti",
        repeat_group="e023c-c2-confetti-a",
    ),
    RealScanCase(
        "e023c-c2-confetti-a2",
        "scratch/e023c/e023c-hp-canon-4800-grey-c2-confetti-2nd.tiff",
        4800.0,
        2,
        expected_c=2,
        role="native-c2-confetti-repeat",
        repeat_group="e023c-c2-confetti-a",
    ),
    RealScanCase(
        "e023c-c2-confetti-a3",
        "scratch/e023c/e023c-hp-canon-4800-grey-c2-confetti-3rd.tiff",
        4800.0,
        2,
        expected_c=2,
        role="native-c2-confetti-repeat",
        repeat_group="e023c-c2-confetti-a",
    ),
    RealScanCase(
        "e023c-c2-confetti-b1",
        "scratch/e023c/e023c-hp-canon-4800-grey-c2-confetti-b.tiff",
        4800.0,
        2,
        expected_c=2,
        role="native-c2-confetti",
        repeat_group="e023c-c2-confetti-b",
    ),
    RealScanCase(
        "e023c-c2-confetti-b2",
        "scratch/e023c/e023c-hp-canon-4800-grey-c2-confetti-b-2nd.tiff",
        4800.0,
        2,
        expected_c=2,
        role="native-c2-confetti-repeat",
        repeat_group="e023c-c2-confetti-b",
    ),
    RealScanCase(
        "e023c-c2-confetti-b3",
        "scratch/e023c/e023c-hp-canon-4800-grey-c2-confetti-b-3rd.tiff",
        4800.0,
        2,
        expected_c=2,
        role="native-c2-confetti-repeat",
        repeat_group="e023c-c2-confetti-b",
    ),
    RealScanCase(
        "e023c-c2-confetti-c",
        "scratch/e023c/e023c-hp-canon-4800-grey-c2-confetti-c.tiff",
        4800.0,
        2,
        expected_c=2,
        role="native-c2-confetti",
    ),
    # These metrology sheets deliberately contain multiple cell structures;
    # they are useful real RGB/grey stress inputs but have no single physical
    # E021 truth.
    RealScanCase(
        "e025-grey-mixed-structure",
        "scratch/e025/e025-hp-canon-4800-grey-page-1.tiff",
        4800.0,
        2,
        role="native-grey-mixed-structure",
    ),
    RealScanCase(
        "e025-rgb-mixed-structure",
        "scratch/e025/e025-hp-canon-4800-color-page-2.tiff",
        4800.0,
        2,
        role="native-rgb-mixed-structure",
    ),
)


# Encoded-source identity is part of the corpus contract.  These hashes
# prevent an overwritten scan, converted TIFF, or regenerated derivative
# from silently becoming a new qualification input.
SOURCE_SHA256 = MappingProxyType(
    {
        "xerox-grey-c6":
            "68604f45f27fbde6fb72e83f9cd18beb54b502638737068585203540b59dfbe7",
        "xerox-rgb-mixed-c":
            "1bb30f904252e9c15a5a2a8c9b93ac1d66f3de21267833712911a4c5c5af2b69",
        "xerox-rgb-large-holes-c5":
            "2941fed104d38c3f5cea851e7c9047c1a0e86cda3dfd5f1f8b268fa8429e30d1",
        "e018b-c2-hp1200":
            "51b2841d044d939b2355c4d9069141ba5ced709a76986a492f0b2b4d514b2798",
        "e018b-c2-hp1200-second":
            "cd07d91e4db17ca7fd21eee2d4af8ce199112a7f8f9908f83f9917c2fdd0bd81",
        "e018b-c3-hp1200":
            "dca3cdff39049949cbb83b3bd9a594c2d27d46229d3bfef708eeeda254dbf282",
        "e018-c3-confetti-1-1600":
            "cd087916bf9fb241514d87353168741f0b976befd05610290c70aa73ce305af1",
        "e018-c3-confetti-1b-1600":
            "527e96db65d4ae19f55ad827dd999088bf683e29647ca6c0116a81181f47ac53",
        "e018-c3-confetti-2-1600":
            "634e593963ccd1b723b104fee650ce31a791bb5d3ff29f13865dac621a341051",
        "e018-c3-confetti-2b-1600":
            "a9edb61c74f350d4dff5ed3589021a61280d17f1af16a2a78e9a496c75ead732",
        "e018-c3-confetti-3-1600":
            "c946b481b5fcf05bdf722bfac05073c1bf3d0dce82c5a9c72ccde592b4210844",
        "e018-c3-confetti-3b-1600":
            "74c7654cb29b47e005e253c814ad89147f5aaad4f2029427385825cb8685dc19",
        "e012-c3-canon2400":
            "814701382f1c7a6b66be3d0e0f81ef026acf910e84ead68251b2b162392c031e",
        "e012-c3-canon4800":
            "2d0c5a2192492b979d75a90bdb0dddd7b7029fb8f629c6eaacbb4f5dc640b1db",
        "e014-c2-canon4800":
            "5a8f895cda0045ffad95745601c8a242a9dd91b0a2d3eb8e938099c57fddb91d",
        "e014-c2-canon4800-displaced":
            "76226088c7595d5e97393f2d50ced69e5d68d9e01f11c2d91cdf987f13059b9b",
        "e014-c2-canon4800-flattened":
            "cb9569e7f2a63fc0f1169d9e362d67bb5011c4af28c057b2743d73a8372e6bb1",
        "e018-c3-confetti-1-native":
            "293c6c9490f03923b3f73c86bd5034cee22c13d6bbf620446403ac714a9a1381",
        "e018-c3-confetti-1b-native":
            "b0a9fd56b11bb8d840bf84e38a8446f4d8a119199b66b526e2eeeb93713941d3",
        "e018-c3-confetti-2-native":
            "240624d157b0e5eaeb34f5492d66ce8a6dc2f706a6cc44e4dbcd5b203fdf64f9",
        "e018-c3-confetti-2b-native":
            "ea8403ff5425857aecc624400e053473c8e99b92e12659aa97fdd77018148ef3",
        "e018-c3-confetti-3-native":
            "bc1889249fd7ef519b65ceca215cecded46b5cf0c42107c88d19cd08074f1f08",
        "e018-c3-confetti-3b-native":
            "5e26220dfde73e5a713f89775bd6ff22e50774249e24e9465cd78995a3210910",
        "e016-c2-full-native":
            "593742f68ee81f4004c551c0128990ab278f41030e6ad26f10b19e8656ad96e4",
        "e016-c2-full-native-displaced-1":
            "7dfc3a5b9268d29310aa64a2a28de7296badbc78948ee1b3b47c1acd3a6a9659",
        "e016-c2-full-native-displaced-2":
            "aa1633252e86c91bb97ab650f581dfc77df5725935721dec59a4b7070110afb6",
        "e017-c3-rgb-native-second":
            "bb87b3790e4f6b549db0cb8537ecb36a4ac669cf961177a1970159a0668e48b5",
        "e018b-c2-canon4800":
            "b49e40f6de2872126bd2215e7779123efdc955961647680d41148a1b54b6234f",
        "e018b-c3-canon4800":
            "547ddb04a05f6ad056d340f44c8cf311f529952da3f12d6f6405f4a85576dc6d",
        "e023c-c2-confetti-a1":
            "70de95c44da1f043f7c854d90199506cdb75fbe98b954cfa0d3c51bb01395b93",
        "e023c-c2-confetti-a2":
            "ab8e9781387f9f72279de5dfcaf6c5e2d1f1c6d36cefb95034bb0d167bba98c5",
        "e023c-c2-confetti-a3":
            "dd8bbc9c6608cc32ab07c5e07cbc57c54ff3741aab814c5e98433bd8a03cdf65",
        "e023c-c2-confetti-b1":
            "e9847c24c0e675c5dcc7a5992b95eafe6b981d26b4b26a76d70339c0488e32dc",
        "e023c-c2-confetti-b2":
            "1c2f8ce7acb0650c31798966f566b78ef79c171d5f70f60f156ca1cd8073d5d8",
        "e023c-c2-confetti-b3":
            "d23adc17cd998e74fc36c84289e56defd0697904bb44b96022fc956ead8dd00c",
        "e023c-c2-confetti-c":
            "e0b89762e01b952a9cb6b448f83d69c954da81867446145f507e758c6e24b2a3",
        "e025-grey-mixed-structure":
            "4fdd6f2663221625d5954f659e792f111c4729d2ecf3c8af546bf6f9d8c06c22",
        "e025-rgb-mixed-structure":
            "4b82a52ab1809c8c4a5ef37895fdd62b7870a78bba51f863bcb878de839b9b2e",
    }
)


def _float_hex(value: float | None) -> str | None:
    if value is None:
        return None
    return float(value).hex()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_chunks(height: int, width: int, target_bytes: int) -> Iterator[slice]:
    rows = max(1, target_bytes // max(1, width))
    for row0 in range(0, height, rows):
        yield slice(row0, min(height, row0 + rows))


def _hash_bool_rows(rows: Iterable[np.ndarray]) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        block = np.ascontiguousarray(row, dtype=np.bool_)
        digest.update(memoryview(block).cast("B"))
        count += int(np.count_nonzero(block))
    return digest.hexdigest(), count


def _legacy_mask_rows(mask: np.ndarray) -> Iterator[np.ndarray]:
    height, width = mask.shape
    for rows in _row_chunks(height, width, MASK_HASH_CHUNK_BYTES):
        yield mask[rows]


def _support_mask_rows(support: SupportMask) -> Iterator[np.ndarray]:
    y0, x0, height, width = support.bbox
    for rows in _row_chunks(height, width, MASK_HASH_CHUNK_BYTES):
        yield support.rasterize_crop(
            y0 + rows.start,
            y0 + rows.stop,
            x0,
            x0 + width,
        )


def _canonical_diagnostics(
    survey: Any, *, legacy: bool
) -> dict[str, Any]:
    if legacy:
        values = survey.diagnostics
        return {
            "threshold": _float_hex(values.get("survey_threshold")),
            "survey_step_px": values.get("survey_step_px"),
            "survey_scale_px": _float_hex(values.get("survey_scale_px")),
            "component_count": values.get("survey_components"),
            "refinement_tiles": values.get("refine_tiles"),
            "refinement_scored_cells": values.get("refine_scored_cells"),
            "refinement_grid_cells": values.get("refine_grid_cells"),
            "refinement_fraction": _float_hex(
                values.get("refine_fraction")
            ),
        }
    values = survey.diagnostics
    return {
        "threshold": _float_hex(values.threshold),
        "survey_step_px": values.survey_step_px,
        "survey_scale_px": _float_hex(values.survey_scale_px),
        "component_count": values.component_count,
        "refinement_tiles": values.refinement_tiles,
        "refinement_scored_cells": values.refinement_scored_cells,
        "refinement_grid_cells": values.refinement_grid_cells,
        "refinement_fraction": _float_hex(values.refinement_fraction),
    }


def _legacy_contract(survey: Any) -> dict[str, Any]:
    regions: list[dict[str, Any]] = []
    for region in survey.regions:
        mask_sha256, true_pixels = _hash_bool_rows(
            _legacy_mask_rows(region.mask)
        )
        regions.append(
            {
                "bbox": list(region.bbox),
                "mask_sha256": mask_sha256,
                "mask_true_pixels": true_pixels,
                "area_mm2": _float_hex(region.area_mm2),
                "median_tensor_score": _float_hex(region.score),
            }
        )
    contract = {
        "c_dots": survey.c_dots,
        "cell_pitch_px": _float_hex(survey.cell_pitch_px),
        "pitch_votes": [
            [int(c_dots), _float_hex(pitch)]
            for c_dots, pitch in survey.pitch_votes
        ],
        "diagnostics": _canonical_diagnostics(survey, legacy=True),
        "regions": regions,
    }
    contract["sha256"] = _json_sha256(contract)
    return contract


def _holo_contract(survey: PayloadSurvey) -> dict[str, Any]:
    regions: list[dict[str, Any]] = []
    for region in survey.regions:
        mask_sha256, true_pixels = _hash_bool_rows(
            _support_mask_rows(region.support)
        )
        regions.append(
            {
                "bbox": list(region.bbox),
                "mask_sha256": mask_sha256,
                "mask_true_pixels": true_pixels,
                "area_mm2": _float_hex(region.area_mm2),
                "median_tensor_score": _float_hex(
                    region.median_tensor_score
                ),
            }
        )
    contract = {
        "c_dots": survey.c_dots,
        "cell_pitch_px": _float_hex(survey.cell_pitch_px),
        "pitch_votes": [
            [vote.c_dots, _float_hex(vote.pitch_px)]
            for vote in survey.pitch_votes
        ],
        "diagnostics": _canonical_diagnostics(survey, legacy=False),
        "regions": regions,
    }
    contract["sha256"] = _json_sha256(contract)
    return contract


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _topology_for_support(
    support: SupportMask, pitch_px: float | None
) -> dict[str, Any]:
    cells = np.asarray(support.cells, dtype=bool)
    foreground_components = int(ndimage.label(cells)[1])
    padded = np.pad(cells, 1, constant_values=False)
    seed = np.zeros(padded.shape, bool)
    seed[0, :] = True
    seed[-1, :] = True
    seed[:, 0] = True
    seed[:, -1] = True
    outside = ndimage.binary_propagation(seed, mask=~padded)
    holes = (~outside & ~padded)[1:-1, 1:-1]
    labels, hole_count = ndimage.label(holes)
    records: list[dict[str, Any]] = []
    eligible = 0
    for label_id, slices in enumerate(
        ndimage.find_objects(labels), start=1
    ):
        if slices is None:
            continue
        local = labels[slices] == label_id
        radius_grid = float(
            ndimage.distance_transform_edt(
                np.pad(local, 1, constant_values=False)
            )[1:-1, 1:-1].max()
        )
        radius_payload = (
            radius_grid * support.step_px / pitch_px
            if pitch_px is not None
            else None
        )
        fill_eligible = (
            radius_payload is not None
            and radius_payload <= SUPPORT_HOLE_RADIUS_CELLS + 1e-12
        )
        eligible += int(fill_eligible)
        records.append(
            {
                "area_grid_cells": int(np.count_nonzero(local)),
                "max_radius_grid_cells": _float_hex(radius_grid),
                "max_radius_payload_cells": _float_hex(radius_payload),
                "fill_eligible": (
                    bool(fill_eligible) if radius_payload is not None else None
                ),
            }
        )
    records.sort(
        key=lambda row: row["area_grid_cells"], reverse=True
    )
    cropped_outside = outside[1:-1, 1:-1]
    return {
        "foreground_components": foreground_components,
        "support_grid_shape": list(cells.shape),
        "support_step_px": support.step_px,
        "support_grid_sha256": hashlib.sha256(
            memoryview(np.ascontiguousarray(cells)).cast("B")
        ).hexdigest(),
        "enclosed_holes": int(hole_count),
        "fill_eligible_residual_holes": eligible,
        "exterior_connected_false_cells": int(
            np.count_nonzero(~cells & cropped_outside)
        ),
        "largest_holes": records[:32],
    }


def _holo_topology(survey: PayloadSurvey) -> dict[str, Any]:
    regions = [
        _topology_for_support(region.support, survey.cell_pitch_px)
        for region in survey.regions
    ]
    return {
        "regions": regions,
        "foreground_component_failures": sum(
            row["foreground_components"] != 1 for row in regions
        ),
        "enclosed_holes": sum(row["enclosed_holes"] for row in regions),
        "fill_eligible_residual_holes": sum(
            row["fill_eligible_residual_holes"] for row in regions
        ),
    }


def _canonical_feature_rows(raster: Raster) -> Iterator[np.ndarray]:
    height, width = raster.shape
    bytes_per_row = max(1, width * np.dtype(np.float32).itemsize)
    rows_per_chunk = max(1, FEATURE_CHUNK_BYTES // bytes_per_row)
    for row0 in range(0, height, rows_per_chunk):
        row1 = min(height, row0 + rows_per_chunk)
        luma = raster.crop_luma(row0, row1, 0, width)
        if raster.luma_max > 512.0:
            luma = luma / np.float32(256.0)
        yield np.ascontiguousarray(luma, dtype=np.float32)


def _feature_sha256(raster: Raster) -> str:
    digest = hashlib.sha256()
    for rows in _canonical_feature_rows(raster):
        digest.update(memoryview(rows).cast("B"))
    return digest.hexdigest()


def _feature_memmap(
    raster: Raster, directory: Path
) -> tuple[np.memmap, str]:
    path = directory / "canonical-e021-float32.bin"
    plane = np.memmap(
        path, mode="w+", dtype=np.float32, shape=raster.shape
    )
    digest = hashlib.sha256()
    row0 = 0
    for rows in _canonical_feature_rows(raster):
        row1 = row0 + rows.shape[0]
        plane[row0:row1] = rows
        digest.update(memoryview(rows).cast("B"))
        row0 = row1
    plane.flush()
    plane.setflags(write=False)
    return plane, digest.hexdigest()


def _tiff_metadata(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in {".tif", ".tiff"}:
        return {"container": path.suffix.lower().lstrip(".") or "unknown"}
    try:
        import tifffile

        with tifffile.TiffFile(path) as tiff:
            page = tiff.pages[0]
            tags = page.tags

            def tag(name: str) -> Any:
                value = tags[name].value if name in tags else None
                if isinstance(value, tuple):
                    return [tag_value(row) for row in value]
                return tag_value(value)

            def tag_value(value: Any) -> Any:
                if isinstance(value, np.generic):
                    return value.item()
                if isinstance(value, (str, int, float, bool, type(None))):
                    return value
                numerator = getattr(value, "numerator", None)
                denominator = getattr(value, "denominator", None)
                if numerator is not None and denominator is not None:
                    return [int(numerator), int(denominator)]
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return str(value)

            photometric = getattr(page.photometric, "name", page.photometric)
            return {
                "container": "tiff",
                "pages": len(tiff.pages),
                "shape": list(page.shape),
                "dtype": str(page.dtype),
                "photometric": str(photometric),
                "orientation": tag("Orientation"),
                "x_resolution": tag("XResolution"),
                "y_resolution": tag("YResolution"),
                "resolution_unit": tag("ResolutionUnit"),
                "compression": str(
                    getattr(page.compression, "name", page.compression)
                ),
            }
    except Exception as exc:
        return {"container": "tiff", "metadata_error": repr(exc)}


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _source_record(
    path: Path, raster: Raster, *, feature_sha256: str
) -> dict[str, Any]:
    return {
        "path": str(path),
        "encoded_bytes": path.stat().st_size,
        "encoded_sha256": raster.source.sha256,
        "feature_plane_sha256": feature_sha256,
        "shape": list(raster.shape),
        "dtype": raster.source.dtype,
        "channels": raster.source.channels,
        "dpi": _float_hex(raster.dpi),
        "container": _tiff_metadata(path),
    }


def _run_holo_worker(path: Path, dpi: float) -> dict[str, Any]:
    started = time.perf_counter()
    raster = open_capture(path, dpi)
    opened = time.perf_counter()
    survey = survey_raster(raster)
    surveyed = time.perf_counter()
    feature_sha256 = _feature_sha256(raster)
    featured = time.perf_counter()
    contract = _holo_contract(survey)
    topology = _holo_topology(survey)
    snapshotted = time.perf_counter()
    raster.verify_source_unchanged()
    return {
        "engine": "holo",
        "source": _source_record(
            path, raster, feature_sha256=feature_sha256
        ),
        "contract": contract,
        "topology": topology,
        "timing_s": {
            "open": opened - started,
            "survey": surveyed - opened,
            "feature_hash": featured - surveyed,
            "snapshot": snapshotted - featured,
            "total": snapshotted - started,
        },
        "peak_rss_bytes": _peak_rss_bytes(),
    }


def _run_legacy_worker(
    path: Path, dpi: float, *, temporary_root: Path | None
) -> dict[str, Any]:
    from paperholo import platen

    started = time.perf_counter()
    raster = open_capture(path, dpi)
    opened = time.perf_counter()
    with tempfile.TemporaryDirectory(
        prefix="holo-e021-real-",
        dir=None if temporary_root is None else str(temporary_root),
    ) as directory:
        plane, feature_sha256 = _feature_memmap(
            raster, Path(directory)
        )
        featured = time.perf_counter()
        survey = platen.detect_payload_regions(plane, dpi=dpi)
        surveyed = time.perf_counter()
        contract = _legacy_contract(survey)
        snapshotted = time.perf_counter()
        del survey
        del plane
    raster.verify_source_unchanged()
    return {
        "engine": "legacy",
        "source": _source_record(
            path, raster, feature_sha256=feature_sha256
        ),
        "contract": contract,
        "timing_s": {
            "open": opened - started,
            "feature_memmap": featured - opened,
            "survey": surveyed - featured,
            "snapshot": snapshotted - surveyed,
            "total": snapshotted - started,
        },
        "peak_rss_bytes": _peak_rss_bytes(),
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _worker_main(args: argparse.Namespace) -> int:
    path = Path(args.path).resolve()
    if args.engine == "holo":
        result = _run_holo_worker(path, args.dpi)
    else:
        temporary_root = (
            None if args.temporary_root is None
            else Path(args.temporary_root).resolve()
        )
        result = _run_legacy_worker(
            path, args.dpi, temporary_root=temporary_root
        )
    _write_json(Path(args.output), result)
    return 0


def _differences(
    left: Any, right: Any, *, path: str = "", limit: int = 64
) -> list[str]:
    out: list[str] = []

    def visit(a: Any, b: Any, location: str) -> None:
        if len(out) >= limit:
            return
        if type(a) is not type(b):
            out.append(
                f"{location or '<root>'}: "
                f"{type(a).__name__}!={type(b).__name__}"
            )
            return
        if isinstance(a, dict):
            keys = sorted(set(a) | set(b))
            for key in keys:
                child = f"{location}.{key}" if location else str(key)
                if key not in a:
                    out.append(f"{child}: missing left")
                elif key not in b:
                    out.append(f"{child}: missing right")
                else:
                    visit(a[key], b[key], child)
                if len(out) >= limit:
                    return
            return
        if isinstance(a, list):
            if len(a) != len(b):
                out.append(f"{location}: length {len(a)}!={len(b)}")
            for index, (a_row, b_row) in enumerate(zip(a, b)):
                visit(a_row, b_row, f"{location}[{index}]")
                if len(out) >= limit:
                    return
            return
        if a != b:
            out.append(f"{location or '<root>'}: {a!r}!={b!r}")

    visit(left, right, path)
    return out


def _run_worker_process(
    engine: str,
    path: Path,
    dpi: float,
    output: Path,
    temporary_root: Path | None,
) -> None:
    command = [
        sys.executable,
        "-m",
        "holo.receive.qualification.e021_real",
        "--_engine",
        engine,
        "--path",
        str(path),
        "--dpi",
        str(dpi),
        "--output",
        str(output),
    ]
    if temporary_root is not None:
        command.extend(["--temporary-root", str(temporary_root)])
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    started = time.monotonic()
    next_heartbeat = 30.0
    while process.poll() is None:
        time.sleep(1.0)
        elapsed = time.monotonic() - started
        if elapsed >= next_heartbeat:
            print(
                f"    {engine} still running ({elapsed:.0f}s)",
                flush=True,
            )
            next_heartbeat += 30.0
    stdout, stderr = process.communicate()
    if process.returncode:
        detail = stderr.strip() or stdout.strip() or "no worker output"
        raise RuntimeError(
            f"{engine} worker failed with {process.returncode}: {detail}"
        )
    if not output.is_file():
        raise RuntimeError(f"{engine} worker did not write {output}")


def _physical_checks(
    case: RealScanCase,
    contract: dict[str, Any],
    source: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    expected_sha256 = SOURCE_SHA256.get(case.name)
    if expected_sha256 is None:
        failures.append("case has no frozen encoded-source SHA-256")
    elif source["encoded_sha256"] != expected_sha256:
        failures.append(
            f"encoded source sha256 {source['encoded_sha256']} "
            f"!= {expected_sha256}"
        )
    if (
        case.expected_c != "any"
        and contract["c_dots"] != case.expected_c
    ):
        failures.append(
            f"c_dots {contract['c_dots']} != {case.expected_c}"
        )
    if (
        case.expected_regions is not None
        and len(contract["regions"]) != case.expected_regions
    ):
        failures.append(
            f"regions {len(contract['regions'])} "
            f"!= {case.expected_regions}"
        )
    return failures


def _orientation_failures(source: dict[str, Any]) -> list[str]:
    orientation = source["container"].get("orientation")
    if orientation not in (None, 1):
        return [f"unsupported TIFF orientation {orientation}"]
    pages = source["container"].get("pages")
    if pages not in (None, 1):
        return [f"capture has {pages} TIFF pages"]
    return []


def _run_case(
    case: RealScanCase,
    root: Path,
    *,
    temporary_root: Path | None,
    ordinal: int,
    total: int,
) -> dict[str, Any]:
    path = (root / case.relative_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    print(
        f"[{ordinal}/{total}] {case.name} "
        f"({path.stat().st_size / (1 << 20):.1f} MiB)",
        flush=True,
    )
    with tempfile.TemporaryDirectory(
        prefix="holo-e021-parent-",
        dir=None if temporary_root is None else str(temporary_root),
    ) as directory:
        work = Path(directory)
        holo_path = work / "holo.json"
        legacy_path = work / "legacy.json"
        print("  holo", flush=True)
        _run_worker_process(
            "holo", path, case.dpi, holo_path, temporary_root
        )
        print("  legacy", flush=True)
        _run_worker_process(
            "legacy", path, case.dpi, legacy_path, temporary_root
        )
        holo = json.loads(holo_path.read_text(encoding="utf-8"))
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))

    source_differences = _differences(
        {
            key: holo["source"][key]
            for key in (
                "encoded_sha256",
                "feature_plane_sha256",
                "shape",
                "dtype",
                "channels",
                "dpi",
            )
        },
        {
            key: legacy["source"][key]
            for key in (
                "encoded_sha256",
                "feature_plane_sha256",
                "shape",
                "dtype",
                "channels",
                "dpi",
            )
        },
        path="source",
    )
    contract_differences = _differences(
        holo["contract"], legacy["contract"], path="contract"
    )
    physical_failures = _physical_checks(
        case, holo["contract"], holo["source"]
    )
    topology_failures: list[str] = []
    topology = holo["topology"]
    if topology["foreground_component_failures"]:
        topology_failures.append(
            f"{topology['foreground_component_failures']} supports "
            "are disconnected"
        )
    if topology["fill_eligible_residual_holes"]:
        topology_failures.append(
            f"{topology['fill_eligible_residual_holes']} fill-eligible "
            "holes remain"
        )
    input_failures = _orientation_failures(holo["source"])
    failures = (
        source_differences
        + contract_differences
        + physical_failures
        + topology_failures
        + input_failures
    )
    result = {
        "case": asdict(case),
        "source": holo["source"],
        "holo": {
            "contract": holo["contract"],
            "topology": topology,
            "timing_s": holo["timing_s"],
            "peak_rss_bytes": holo["peak_rss_bytes"],
        },
        "legacy": {
            "contract": legacy["contract"],
            "timing_s": legacy["timing_s"],
            "peak_rss_bytes": legacy["peak_rss_bytes"],
        },
        "source_differences": source_differences,
        "contract_differences": contract_differences,
        "physical_failures": physical_failures,
        "topology_failures": topology_failures,
        "input_failures": input_failures,
        "passed": not failures,
    }
    print(
        f"  {'PASS' if result['passed'] else 'FAIL'} "
        f"n={len(holo['contract']['regions'])} "
        f"c={holo['contract']['c_dots']} "
        f"holes={topology['enclosed_holes']} "
        f"holo={holo['timing_s']['total']:.1f}s "
        f"legacy={legacy['timing_s']['total']:.1f}s",
        flush=True,
    )
    if failures:
        for failure in failures[:8]:
            print(f"    {failure}", flush=True)
    return result


def _dependency_versions() -> dict[str, str]:
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
    }
    for distribution in ("scipy", "tifffile", "Pillow"):
        try:
            result[distribution.lower()] = importlib.metadata.version(
                distribution
            )
        except importlib.metadata.PackageNotFoundError:
            result[distribution.lower()] = "missing"
    return result


def _implementation_hashes() -> dict[str, str]:
    paths = {
        "legacy_platen": ROOT / "src/paperholo/platen.py",
        "holo_scan": ROOT / "src/holo/receive/scan.py",
        "holo_survey": ROOT / "src/holo/receive/survey.py",
        "holo_survey_tensor": ROOT / "src/holo/receive/_survey_tensor.py",
        "qualification": Path(__file__).resolve(),
    }
    return {name: _sha256_file(path) for name, path in paths.items()}


def _repeat_summary(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        group = result["case"]["repeat_group"]
        if group is not None:
            grouped.setdefault(group, []).append(result)
    summaries: list[dict[str, Any]] = []
    for group, rows in sorted(grouped.items()):
        pitches = [
            float.fromhex(row["holo"]["contract"]["cell_pitch_px"])
            for row in rows
            if row["holo"]["contract"]["cell_pitch_px"] is not None
        ]
        areas = [
            sum(
                float.fromhex(region["area_mm2"])
                for region in row["holo"]["contract"]["regions"]
            )
            for row in rows
        ]
        summaries.append(
            {
                "group": group,
                "cases": [row["case"]["name"] for row in rows],
                "region_counts": [
                    len(row["holo"]["contract"]["regions"]) for row in rows
                ],
                "c_values": [
                    row["holo"]["contract"]["c_dots"] for row in rows
                ],
                "pitch_px_min": min(pitches) if pitches else None,
                "pitch_px_max": max(pitches) if pitches else None,
                "total_area_mm2_min": min(areas) if areas else None,
                "total_area_mm2_max": max(areas) if areas else None,
            }
        )
    return summaries


def qualify_real_corpus(
    cases: tuple[RealScanCase, ...],
    *,
    root: Path = ROOT,
    temporary_root: Path | None = None,
) -> dict[str, Any]:
    """Run an exact authentic-corpus qualification and return its report."""
    if temporary_root is not None:
        temporary_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index, case in enumerate(cases, start=1):
        results.append(
            _run_case(
                case,
                root.resolve(),
                temporary_root=temporary_root,
                ordinal=index,
                total=len(cases),
            )
        )
    elapsed = time.perf_counter() - started
    passed = all(row["passed"] for row in results)
    return {
        "schema": REPORT_SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dependencies": _dependency_versions(),
        "implementation_sha256": _implementation_hashes(),
        "case_count": len(results),
        "passed_count": sum(row["passed"] for row in results),
        "failed_count": sum(not row["passed"] for row in results),
        "passed": passed,
        "elapsed_s": elapsed,
        "repeat_groups": _repeat_summary(results),
        "cases": results,
    }


def _select_cases(
    lane: str, names: list[str] | None
) -> tuple[RealScanCase, ...]:
    tier = {"smoke": 0, "campaign": 1, "full": 2}[lane]
    selected = tuple(case for case in CORPUS if case.tier <= tier)
    if names:
        wanted = set(names)
        known = {case.name for case in CORPUS}
        unknown = sorted(wanted - known)
        if unknown:
            raise ValueError(f"unknown cases: {', '.join(unknown)}")
        selected = tuple(case for case in selected if case.name in wanted)
    if not selected:
        raise ValueError("case selection is empty")
    return selected


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "bit-exact authentic-scan qualification of Holo E021 against "
            "the frozen legacy implementation"
        )
    )
    parser.add_argument(
        "--lane",
        choices=("smoke", "campaign", "full"),
        default="smoke",
        help=(
            "smoke: small controls and HP c2/c3; campaign: also six c3 "
            "confetti derivatives; full: also native multi-gigabyte scans"
        ),
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="run only this named case within the selected lane (repeatable)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help=f"repository/corpus root (default: {ROOT})",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="write the complete strict-JSON report here",
    )
    parser.add_argument(
        "--temporary-root",
        type=Path,
        help=(
            "directory for worker state and the legacy float32 feature "
            "memmap; full native RGB cases need roughly 10 GiB free"
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the selected cases without opening captures",
    )
    # Private subprocess interface.
    parser.add_argument("--_engine", choices=("holo", "legacy"))
    parser.add_argument("--path")
    parser.add_argument("--dpi", type=float)
    parser.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    args.engine = args._engine
    if args.engine is not None:
        if args.path is None or args.dpi is None or args.output is None:
            parser.error("worker mode needs --path, --dpi, and --output")
        return _worker_main(args)
    try:
        cases = _select_cases(args.lane, args.cases)
    except ValueError as exc:
        parser.error(str(exc))
    if args.list:
        for case in cases:
            path = args.root / case.relative_path
            status = "present" if path.is_file() else "MISSING"
            print(
                f"{case.name:38s} {status:7s} "
                f"{case.dpi:6.0f} dpi  {case.relative_path}"
            )
        return 0
    missing = [
        case.relative_path
        for case in cases
        if not (args.root / case.relative_path).is_file()
    ]
    if missing:
        parser.error("missing corpus files: " + ", ".join(missing))
    report = qualify_real_corpus(
        cases,
        root=args.root,
        temporary_root=args.temporary_root,
    )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        _write_json(args.report, report)
        print(f"wrote {args.report}", flush=True)
    print(
        f"{'PASS' if report['passed'] else 'FAIL'} "
        f"{report['passed_count']}/{report['case_count']} authentic cases "
        f"in {report['elapsed_s']:.1f}s",
        flush=True,
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
