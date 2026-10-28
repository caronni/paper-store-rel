"""The eight-capture corpus registry, paths, and provenance access.

COLOR-UPLIFT-PLAN v1.3 §4 names the corpus; this module is the single
machine-readable statement of it.  Paths are declared relative to the
READ-ONLY corpus root (the main repo's ``scratch/``); everything the
harness produces goes under the work root.

    corpus root  $HOLO_COLOR_UPLIFT_CORPUS  (default scratch)
    work root    $HOLO_COLOR_UPLIFT_WORK    (default <corpus root>/color-uplift)

Nothing in this module writes to the corpus root.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_DEFAULT_CORPUS = Path("scratch")
HARNESS_DIR = Path(__file__).resolve().parent
PROVENANCE_PATH = HARNESS_DIR / "provenance.json"


def corpus_root() -> Path:
    """The read-only corpus root (never written by this harness)."""
    return Path(
        os.environ.get("HOLO_COLOR_UPLIFT_CORPUS", str(_DEFAULT_CORPUS))
    ).resolve()


def work_root() -> Path:
    """The writable run root; created on demand."""
    value = os.environ.get("HOLO_COLOR_UPLIFT_WORK")
    root = Path(value) if value else corpus_root() / "color-uplift"
    return root.resolve()


def work_dir(*parts: str) -> Path:
    path = work_root().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True, slots=True)
class CaptureRow:
    """One archived (capture, baseline state) pair of the campaign corpus."""

    key: str
    engine: str
    kind: str
    role: str
    tiff: str
    scan_dpi: float
    state: str
    emit_dir: str
    recovered: str | None

    @property
    def is_color(self) -> bool:
        return self.kind in ("cmy7", "cmy8")

    def tiff_path(self) -> Path:
        return corpus_root() / self.tiff

    def state_path(self) -> Path:
        return corpus_root() / self.state

    def emit_path(self) -> Path:
        return corpus_root() / self.emit_dir

    def recovered_path(self) -> Path | None:
        return None if self.recovered is None else corpus_root() / self.recovered

    def diag_path(self) -> Path:
        return Path(str(self.state_path()) + ".diag")

    def manifest(self) -> dict:
        return json.loads((self.emit_path() / "manifest.json").read_text())

    def gt_path(self) -> Path:
        return self.emit_path() / "page000_gt.npy"

    def payload_bin_path(self) -> Path:
        rows = sorted(self.emit_path().glob("payload*.bin"))
        if len(rows) != 1:
            raise ValueError(
                f"{self.key}: expected exactly one payload*.bin in "
                f"{self.emit_path()}, found {len(rows)}")
        return rows[0]


# Ordered cheap-first: the 1.7 GB / 2400 dpi xerox c3-cmy7 is the iteration
# canary; the 6.9 GB rows run once each (COLOR-UPLIFT-PLAN §4 budget note).
CAPTURES: tuple[CaptureRow, ...] = (
    CaptureRow(
        key="xerox-c3-cmy7", engine="xerox", kind="cmy7",
        role="non-regression (cheap iteration canary; 720 certs, VERIFIED)",
        tiff="in/xerox-canon-c3-cmy7-2400dpi.tiff", scan_dpi=2400.0,
        state="in/holo-xerox-c3-cmy7-counting-receive.state",
        emit_dir="e030/holo-c3-cmy7-q05-counting",
        recovered="in/holo-xerox-c3-cmy7-counting-recovered.bin",
    ),
    CaptureRow(
        key="hp-c3-cmy8", engine="hp", kind="cmy8",
        role="uplift target (663 certs C620/M43/Y0; close OPEN)",
        tiff="e030/hp-canon-c3-cmy8-q05-counting.tiff", scan_dpi=4800.0,
        state="e030/holo-c3-cmy8-q05-counting/receive.state",
        emit_dir="e030/holo-c3-cmy8-q05-counting",
        recovered=None,
    ),
    CaptureRow(
        key="xerox-c2-cmy8", engine="xerox", kind="cmy8",
        role="non-regression (5370 certs, VERIFIED 718,413 B)",
        tiff="in/xerox-canon-c2-cmy8.tiff", scan_dpi=4800.0,
        state="in/holo-xerox-c2-cmy8-q05-counting-receive.state",
        emit_dir="e030/holo-c2-cmy8-q05-counting",
        recovered="in/holo-xerox-c2-cmy8-q05-counting-recovered.bin",
    ),
    CaptureRow(
        key="xerox-c2-k", engine="xerox", kind="k",
        role="non-regression K (1930 certs, VERIFIED 465,580 B)",
        tiff="in/xerox-canon-c2-bw.tiff", scan_dpi=4800.0,
        state="in/holo-xerox-c2-counting-receive.state",
        emit_dir="e028/holo-c2-r0700-q07-ink-counting",
        recovered="in/holo-xerox-c2-counting-recovered.bin",
    ),
    CaptureRow(
        key="hp-c2-k", engine="hp", kind="k",
        role="non-regression K (1940 certs, VERIFIED 465,580 B)",
        tiff="e028/hp-canon-c2-ink-counting.tiff", scan_dpi=4800.0,
        state="e028/holo-c2-r0700-q07-ink-counting/receive.state",
        emit_dir="e028/holo-c2-r0700-q07-ink-counting",
        recovered="e028/holo-c2-r0700-q07-ink-counting/recovered.bin",
    ),
    CaptureRow(
        key="xerox-c2-cmy7", engine="xerox", kind="cmy7",
        role="report-only negative (83 certs; print-frozen cell error)",
        tiff="in/xerox-canon-c2-cmy7.tiff", scan_dpi=4800.0,
        state="in/holo-xerox-c2-cmy7-counting-receive.state",
        emit_dir="e030/holo-c2-cmy7-q05-counting",
        recovered=None,
    ),
    CaptureRow(
        key="hp-c2-cmy8", engine="hp", kind="cmy8",
        role="payload-reached negative control (6586 LDPC calls, 0 certs)",
        tiff="e030/hp-canon-c2-cmy8-q05-counting.tiff", scan_dpi=4800.0,
        state="e030/holo-c2-cmy8-q05-counting/receive.state",
        emit_dir="e030/holo-c2-cmy8-q05-counting",
        recovered=None,
    ),
    CaptureRow(
        key="hp-c2-cmy7", engine="hp", kind="cmy7",
        role="address-dead no-op control (60.3% footprint, 0 LDPC calls)",
        tiff="in/hp-canon-c2-cmy7.tiff", scan_dpi=4800.0,
        state="in/holo-hp-c2-cmy7-counting-receive.state",
        emit_dir="e030/holo-c2-cmy7-q05-counting",
        recovered=None,
    ),
)

CAPTURES_BY_KEY = {row.key: row for row in CAPTURES}

# The two e030 TIFFs whose SHAs are independently recorded by the
# experiment (cross-check; a mismatch FAILS provenance).
E030_TIFF_SHA_FILE = "e030/tiff-shas.txt"


def capture(key: str) -> CaptureRow:
    try:
        return CAPTURES_BY_KEY[key]
    except KeyError:
        raise SystemExit(
            f"unknown capture {key!r}; known: "
            + ", ".join(row.key for row in CAPTURES)) from None


def sha256_file(path: Path, chunk: int = 1 << 24) -> str:
    """Stream one file's SHA-256 (multi-GB inputs are never slurped)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def iter_e030_recorded_shas() -> Iterator[tuple[str, str]]:
    """Yield (basename, sha256) from the experiment's own record."""
    text = (corpus_root() / E030_TIFF_SHA_FILE).read_text()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            yield Path(parts[1]).name, parts[0]


def load_provenance() -> dict:
    if not PROVENANCE_PATH.is_file():
        raise SystemExit(
            f"no provenance at {PROVENANCE_PATH}; run "
            "`python -m _color_uplift_harness.provenance write` first")
    return json.loads(PROVENANCE_PATH.read_text())


def provenance_row(key: str) -> dict:
    rows = load_provenance()["captures"]
    if key not in rows:
        raise SystemExit(f"provenance.json has no capture {key!r}")
    return rows[key]


def resolve_spec(row: CaptureRow, format_row_id: str):
    """Resolve the archived format row, falling back to coding+printer.

    ``c2-r0700@3392x2368`` (hp-m281-ink) and any other geometry that is
    deliberately absent from ``FORMAT_ROWS`` resolve through the emit
    manifest's coding/printer pair, exactly as ``confetti.py decode
    --coding --printer`` does.
    """
    from holo.format.registry import get_format_row

    try:
        spec = get_format_row(format_row_id)
    except KeyError:
        from holo.devices.profiles import make_spec

        manifest = row.manifest()
        spec = make_spec(manifest["coding_id"], manifest["printer_id"])
    if spec.spec_id != format_row_id:
        raise ValueError(
            f"{row.key}: resolved spec {spec.spec_id} != archived "
            f"{format_row_id}")
    return spec


__all__ = [
    "CAPTURES", "CAPTURES_BY_KEY", "CaptureRow", "HARNESS_DIR",
    "PROVENANCE_PATH", "capture", "corpus_root", "iter_e030_recorded_shas",
    "load_provenance", "provenance_row", "resolve_spec", "sha256_file",
    "work_dir", "work_root",
]
