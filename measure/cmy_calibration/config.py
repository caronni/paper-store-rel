"""R11 calibration instrument — the fixed inputs: paths, band-captures, seeds and the pre-registered parameters.

What: one table of the ten band-captures the protocol names (id, sheet, band, scan, manifest, role, cell size),
the scale readouts C1 and the extraction parity gate read (located by flag, never by default), the seed law
(np.random.default_rng([MASTER_SEED, REGIME, BC, n, k])) and every numeric parameter of the run.  Why: the
protocol is pre-registered, so the numbers live in one place that the run hashes into meta.code_sha256 before
any decision is read.  How: plain constants and frozen dataclasses, nothing computed at import.

Nothing here is run on its own; the stages are `python -m measure.cmy_calibration --stage ...`.

Inputs (the 2026-10-09 evidence-vs-code ruling, docs/EVIDENCE-ARCHIVE-2026-10-08.md §10): the scans, the job
manifests and their bands npz are PUBLISHED paths joined onto --evidence-root (or $PAPER_EVIDENCE_ROOT;
measure/_evidence.py), the scans read as the unpacked <name>.tiff of the published <name>.tiff.jxl; the e041 scale
readouts are not published (regenerable by measure.e041_scale_readout from the same scan and manifest) and are read
under --scale-root as <scale root>/<capture key>/<tag>-{windows.csv,summary.json}.  The run of record (2026-10-10)
read the same scans as scratch/e041/e041-{s14,s17,x01}-2400.tiff and e041-s17-4800.tiff, the same manifests under
evidence/paper-store-evidence-holo-2026-10/, and the readouts from scratch/e041/scale (S14-2400, S17-4800),
scratch/e041/scale-2400 (S17-2400) and scratch/e042/scale (X1-2400).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from measure import _evidence

WORKTREE = Path(__file__).resolve().parents[2]
#: The stage driver's default work directory: every stage writes here and later stages read back what earlier
#: ones wrote (the run of record used scratch/cmy-calibration-20261010/).
ARTEFACTS = WORKTREE / "build" / "cmy-calibration"
#: The published release every capture and manifest below sits in, relative to the evidence root.
RELEASE = Path(_evidence.HOLO_2026_10)
S14_MANIFEST = RELEASE / "041-m281-screen-routes" / "S14" / "jobs" / "S14-ps-scale.manifest.json"
S17_MANIFEST = RELEASE / "041-m281-screen-routes" / "S17" / "jobs" / "S17-ps-layouts.manifest.json"
X1_MANIFEST = RELEASE / "042-altalink-cell-encodings" / "X1" / "jobs" / "X1-altalink-probe.manifest.json"

PROTOCOL_VERSION = "R11-yield-2026-10-10"
MASTER_SEED = 20261010
REGIME = {"page_furniture": 1, "fold": 2, "cold": 3, "ldpc_page": 4, "ldpc_cold": 5, "deadY": 6, "shuffle": 7,
          "synth_s1": 8, "painted_s2": 9, "bootstrap": 10, "twocapture": 11, "valsplit": 12}

RUNGS = ("r0700", "r0775", "r0850")
SHORTEN = 120
#: Expected fountain bits per tile per stream (§3.1: k - 153).
FOUNTAIN_BITS = {"r0700": 2727, "r0775": 3047, "r0850": 3367}
#: Tile-yield pairs (hi rung, lo rung): the uniform rungs, the R4 probe and the two r0850 mixes.
YIELD_PAIRS = (("r0700", "r0700"), ("r0775", "r0775"), ("r0850", "r0850"), ("r0775", "r0700"),
               ("r0850", "r0700"), ("r0850", "r0775"))
LLR_BOUND = 20.0
GATE_SLACK = 1e-9


@dataclass(frozen=True)
class Capture:
    """One (sheet, scan): the extraction unit (one npz per capture).  scan and manifest are published paths relative
    to the evidence root; tag is the manifest's tag (its bands npz <tag>-bands.npz beside it, the scale readout's
    file prefix)."""
    key: str
    sheet: str
    scan: Path
    scan_dpi: int
    manifest: Path
    bands: tuple[str, ...]
    white_rgb: tuple[float, float, float]
    tag: str

    def scan_at(self, evidence_root: Path) -> Path:
        return evidence_root / self.scan

    def manifest_at(self, evidence_root: Path) -> Path:
        return evidence_root / self.manifest

    def bands_npz_at(self, evidence_root: Path) -> Path:
        return self.manifest_at(evidence_root).parent / f"{self.tag}-bands.npz"

    def windows_csv_at(self, scale_root: Path) -> Path:
        """The readout CSV the extraction parity gate compares against."""
        return scale_root / self.key / f"{self.tag}-windows.csv"

    def summary_json_at(self, scale_root: Path) -> Path:
        """The readout summary whose confusion_loo C1 compares against."""
        return scale_root / self.key / f"{self.tag}-summary.json"

    def readout_command(self, evidence_root: Path, scale_root: Path) -> str:
        """The e041 scale readout of this scan, written where windows_csv_at / summary_json_at read it."""
        return (f"PYTHONPATH=src:. env/bin/python -m measure.e041_scale_readout --scan {self.scan_at(evidence_root)} "
                f"--scan-dpi {self.scan_dpi} --manifest {self.manifest_at(evidence_root)} "
                f"--out {scale_root / self.key}")


CAPTURES: dict[str, Capture] = {c.key: c for c in (
    Capture("S14-2400", "S14", RELEASE / "041-m281-screen-routes" / "S14" / "captures" / "S14-canon-2400rgb.tiff",
            2400, S14_MANIFEST, ("A1", "B1", "B2", "B3"), (231.0, 232.0, 234.0), "S14-ps-scale"),
    Capture("S17-2400", "S17", RELEASE / "041-m281-screen-routes" / "S17" / "captures" / "S17-canon-2400rgb.tiff",
            2400, S17_MANIFEST, ("U12", "U13"), (231.0, 232.0, 234.0), "S17-ps-layouts"),
    Capture("S17-4800", "S17", RELEASE / "041-m281-screen-routes" / "S17" / "captures" / "S17-canon-4800rgb.tiff",
            4800, S17_MANIFEST, ("U12", "U13"), (231.0, 232.0, 234.0), "S17-ps-layouts"),
    Capture("X1-2400", "X1", RELEASE / "042-altalink-cell-encodings" / "X1" / "captures" / "X1-canon-2400rgb.tiff",
            2400, X1_MANIFEST, ("X10", "X11"), (232.0, 231.0, 231.0), "X1-altalink-probe"),
)}


@dataclass(frozen=True)
class BandCaptureSpec:
    bc: int
    capture: str
    band: str
    role: str                      # "decision" | "control"
    cell_dots: int


BAND_CAPTURES: tuple[BandCaptureSpec, ...] = (
    BandCaptureSpec(0, "S14-2400", "B3", "decision", 2),
    BandCaptureSpec(1, "S17-2400", "U12", "decision", 2),
    BandCaptureSpec(2, "S17-4800", "U12", "decision", 2),
    BandCaptureSpec(3, "X1-2400", "X10", "decision", 2),
    BandCaptureSpec(4, "S14-2400", "A1", "control", 3),
    BandCaptureSpec(5, "S14-2400", "B1", "control", 3),
    BandCaptureSpec(6, "S14-2400", "B2", "control", 3),
    BandCaptureSpec(7, "S17-2400", "U13", "control", 3),
    BandCaptureSpec(8, "S17-4800", "U13", "control", 3),
    BandCaptureSpec(9, "X1-2400", "X11", "control", 3),
)
DECISION_BCS = (0, 1, 2, 3)
TWO_CAPTURE_PAIRS = ((1, 2, "U12"), (7, 8, "U13"))
DEADY_CONTROL_BCS = (9, 8)
NULL_BCS = (0, 2)
SYNTH_S1_BC, SYNTH_S1B_BC, PAINTED_S2_BC = 10, 11, 12

#: Committed anchors (rebuilt from the readout summaries' confusion_loo; C1 compares against the summary itself,
#: these are the protocol's stated values, kept for the report).
ANCHORS = {
    0: {"err_hi": 1.427, "err_lo": 2.032, "I_hi": 0.8971, "I_lo": 0.8630, "I_hi_lo": 0.9335, "I_lo_hi": 0.8995,
        "MI": 1.7966, "BICM": 1.760},
    2: {"err_hi": 3.343, "err_lo": 4.609, "I_hi": 0.8049, "I_lo": 0.7458, "I_hi_lo": 0.8584, "I_lo_hi": 0.7992,
        "MI": 1.6042},
    1: {"err_hi": 3.434, "err_lo": 4.666, "I_hi": 0.8005, "I_lo": 0.7431, "I_hi_lo": 0.8544, "I_lo_hi": 0.7969,
        "MI": 1.5974},
    3: {"err_hi": 1.794, "err_lo": 1.943, "I_hi": 0.8756, "I_lo": 0.8647, "I_hi_lo": 0.9170, "I_lo_hi": 0.9062,
        "MI": 1.7817},
}
C3_MIN_I = 0.990

# p120 furniture per emulated tile (the lattice's own &1 split)
SEARCH_WORDS, SEARCH_DUST = 53, 11
HELD_WORDS, HELD_DUST = 47, 9
COLD_SIZES = (1, 2, 3, 4, 8)
COLD_SHAPES = {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2), 8: (2, 4)}
POLICIES = ("NEVER", "ALWAYS", "D1-DEFAULT", "FLOORS(i)", "FLOORS(ii)")
GATES = ("G0", "G1", "G2", "G3")


@dataclass(frozen=True)
class Params:
    """The run's sizes; floors T_page >= 100, D_ldpc >= 100, D_info >= 200 are pre-registered."""
    T_page: int = 400
    T_c3: int = 100
    D_info: int = 400
    D_ldpc: int = 150
    B: int = 2000
    B_slope: int = 200
    R: int = 3
    K: int = 5
    max_iters: int = 60
    retry_iters: int = 150
    alpha: float = 0.8
    workers: int = 8
    c3_rungs: tuple[str, ...] = RUNGS
    rs_ldpc: bool = True
    cb_ldpc: bool = True
    n8_ldpc: bool = True
    retry150: bool = True
    T_null: int = 100
    D_null: int = 100
    D_detect: int = 200

    def floors_ok(self) -> bool:
        return self.T_page >= 100 and self.D_ldpc >= 100 and self.D_info >= 200
