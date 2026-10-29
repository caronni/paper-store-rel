"""What colour material the home flatbed ever produced, and from what.

Channel geometry only exists where there are channels, so before any
estimator runs the corpus has to be asked a prior question: did the HP
M281fdw's own flatbed — "home flatbed 1200" in the record, the scanner
every experiment before 012.3 used — ever acquire in colour, and is any
of it still on disk?

The record's standing instruction is a ban.  CLAUDE.md's scanner bullet
says the home flatbed's COLOR mode "lays an 11.3 px comb — never acquire
color from it", traced to experiments/017 P2, where that comb's 5.68 px
harmonic out-contrasted the payload cell lattice and broke blind pitch
identification.  The ban is on ACQUIRING, and it was declared on
2026-07-19, two weeks after the colour captures below were taken.  They
are legacy material from before the rule, which is exactly the material
a legacy-capture compensation would have to pay for; reading them costs
no paper and breaks no rule.

Attribution is by acquisition date and filename, both cross-checked
against the experiment logs, because no capture here carries scanner
metadata:

* Everything in ``scans/`` dated 2026-07-04..06 is the home flatbed.  The
  Canon LiDE 400 does not enter the corpus until 012.3 on 2026-07-08
  (memory: project-canon-4800-scanner, "ARRIVED, first data 012.3"), so
  no earlier capture can be Canon.
* ``*-hp-scan`` marks a home-flatbed capture of a sheet printed on the
  office AltaLink — the 004.1 / 006.3 / 007.6 cross-engine runs, which
  the logs describe as "home-flatbed 1200 color single scan".
* ``*xeroxscan*`` is the AltaLink's OWN scanner, not the home flatbed,
  and is excluded despite being colour.
* ``*canon*`` is the Canon, excluded here and measured by
  ``channel_ca``.
* ``adf-triage/`` is the M281's sheet feeder, not its flatbed, and lands
  at 300 dpi — a different transport with a different failure mode, and
  0.5 px per printed dot, which is below anything this estimator can
  say a useful thing about.

Headers only: the PNG IHDR is 25 bytes at a fixed offset, so the colour
type of a 300 MB capture costs one 64-byte read.  sha256 is computed
only for captures the measurement actually uses, and matched against the
log where the log recorded one.

Historical record (2026-09); the home-flatbed captures it reads (the
``scans/`` directory of the record, ``name`` below) are in the published
evidence archive, each at its ``published`` path joined onto
``--evidence-root`` (``measure/_evidence.py``).  The archive publishes a
PNG with its metadata chunks stripped (pixels untouched), so
``sha256_matches_log`` reads False wherever chunks were removed; the
IDAT sha in the release's MANIFEST.tsv is the check then.
Output lands in the required ``--out``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import _evidence

#: The evidence root, set by ``use_evidence_root``.
EVIDENCE_ROOT: Path | None = None

COLOUR_TYPES = {0: "grey", 2: "RGB", 3: "palette", 4: "grey+alpha", 6: "RGBA"}
HOME_FLATBED = "HP CLJ Pro M281fdw flatbed (home flatbed 1200)"


@dataclass(frozen=True)
class Capture:
    """One archived capture and what the record says produced it.

    ``name`` is the record's own name for it (the experiment logs cite
    it); ``published`` is its path under the evidence root."""

    name: str
    scanner: str
    engine: str
    mode: str
    scan_dpi: float
    experiment: str
    content: str
    logged_sha256: str = ""
    role: str = ""
    placement: str = ""
    header: dict[str, Any] = field(default_factory=dict)
    published: str = ""

    @property
    def path(self) -> Path:
        return _evidence.resolve(EVIDENCE_ROOT,
                                 tool="scanfield") / self.published

    @property
    def colour(self) -> bool:
        return self.header.get("kind") in ("RGB", "RGBA")


# The home flatbed's COLOUR captures, as attributed above.  Every entry's
# experiment and content come from that experiment's run-log table; the
# sha256 column is filled in only where the log recorded one, and
# ``verify`` checks it.
HOME_COLOUR: tuple[Capture, ...] = (
    Capture("finalists.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "004.0", "finalists checkerboard: K cell tiles (B1 c2, B2 RLL) "
            "+ CMY composite tiles (A3 7-state, A4) + labels",
            "a9148acc5d7a47b409f96122e0bdd90e7ef455362020e0650c37208cdea7ccf6",
            role="primary", placement="flat 0 deg",
            published="paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-hpflatbed-1200rgb.png"),
    Capture("finalists-1-col.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "004.0b", "same sheet as finalists.png, rescan 1",
            role="primary", placement="re-placed, ~0 deg",
            published="paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-hpflatbed-1200rgb-1.png"),
    Capture("finalists-2-col.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "004.0b", "same sheet, rescan 2",
            role="primary", placement="displaced",
            published="paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-hpflatbed-1200rgb-2.png"),
    Capture("finalists-3-col.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "004.0b", "same sheet, rescan 3 (top part only)",
            role="primary", placement="rotated 90 deg",
            published="paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-hpflatbed-1200rgb-3.png"),
    Capture("finalists-4-col.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "004.0b", "same sheet, rescan 4",
            role="primary", placement="rotated 180 deg",
            published="paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-hpflatbed-1200rgb-4.png"),
    Capture("xerox-e004-finalists-hp-scan.png", HOME_FLATBED, "AltaLink",
            "colour", 1200.0, "004.1",
            "the SAME page printed on the AltaLink — the MIC control: an "
            "engine that lays yellow tracking dots, dark in blue",
            role="control", placement="flat",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/finalists-hpflatbed-1200rgb.png"),
    Capture("006bw-scan-1-color.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "006.0", "LOOP-BW page: K-only content, acquired in colour mode",
            role="k-only", placement="flat",
            published="paper-store-evidence-paperholo-era/006-loop-pages/e006bw/captures/e006bw-hpflatbed-1200rgb-1.png"),
    Capture("xerox-001-patterns-K-hp-scan.png", HOME_FLATBED, "AltaLink",
            "colour", 1200.0, "007.6",
            "e001 K-plane pattern page printed on the AltaLink",
            role="k-only", placement="flat",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/001patterns-p1-K-hpflatbed-1200rgb.png"),
    Capture("test-scan-calpage-color.png", HOME_FLATBED, "M281", "colour",
            1200.0, "002.0", "CAL-1 calibration page",
            "2bbb87042851dae071bcf197adc1152a979f8cf170019499898ab1795930a9f6",
            role="secondary", placement="flat",
            published="paper-store-evidence-paperholo-era/002-calibration-page/calpage/captures/calpage-hpflatbed-1200rgb.png"),
    Capture("test-scan-calpage-color-quer-top.png", HOME_FLATBED, "M281",
            "colour", 1200.0, "002.0b", "CAL-1, transverse placement (top)",
            role="secondary", placement="transverse, top",
            published="paper-store-evidence-paperholo-era/002-calibration-page/calpage/captures/calpage-hpflatbed-1200rgb-quer-top.png"),
    Capture("test-scan-calpage-color-quer-bot.png", HOME_FLATBED, "M281",
            "colour", 1200.0, "002.0b", "CAL-1, transverse placement (bottom)",
            role="secondary", placement="transverse, bottom",
            published="paper-store-evidence-paperholo-era/002-calibration-page/calpage/captures/calpage-hpflatbed-1200rgb-quer-bot.png"),
    Capture("test-scan-modprobe.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "003.0", "modulation probes (RLL, voids, coloured pilots)",
            "a5de3fe82e2dc2baf89557bf2fa74c906ab094773c6a361fd29877773049e963",
            role="secondary", placement="flat",
            published="paper-store-evidence-paperholo-era/003-modulation-probes/modprobe/captures/modprobe-hpflatbed-1200rgb.png"),
    Capture("test-scan-composite-probe.png", HOME_FLATBED, "M281", "colour",
            1200.0, "002.1", "composite/overlap probe page",
            "c0187114827938058bf11d2c1b5c4cd0710ca2566e74b424fff547b0d7c05a8a",
            role="secondary", placement="flat",
            published="paper-store-evidence-paperholo-era/002-calibration-page/composite-probe/captures/composite-probe-hpflatbed-1200rgb.png"),
    Capture("test-scan-overlap2.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "002.2", "plane-overlap probe page",
            "19e58f247c31faf7e55a2a1aa303f2e8cafb22c64a150bfe2b66b146e588be62",
            role="secondary", placement="flat",
            published="paper-store-evidence-paperholo-era/002-calibration-page/overlap2/captures/overlap2-hpflatbed-1200rgb.png"),
    Capture("005.1.png", HOME_FLATBED, "M281", "colour", 1200.0, "005.1",
            "density ladder, @PJL DENSITY=1 print", role="secondary",
            published="paper-store-evidence-paperholo-era/005-density-ladder/density1/captures/density1-hpflatbed-1200rgb.png"),
    Capture("005.2.png", HOME_FLATBED, "M281", "colour", 1200.0, "005.2",
            "density ladder, DENSITY=5 print", role="secondary",
            published="paper-store-evidence-paperholo-era/005-density-ladder/density5/captures/density5-hpflatbed-1200rgb.png"),
    Capture("005.3.png", HOME_FLATBED, "M281", "colour", 1200.0, "005.3",
            "density ladder, DENSITY=3 + RET=OFF print", role="secondary",
            published="paper-store-evidence-paperholo-era/005-density-ladder/density3-retoff/captures/density3-retoff-hpflatbed-1200rgb.png"),
    Capture("006col-scan-2-col.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "006.0", "LOOP-C colour loop page", role="secondary",
            published="paper-store-evidence-paperholo-era/006-loop-pages/e006c/captures/e006c-hpflatbed-1200rgb-2.png"),
    Capture("006col-scan-3-col.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "006.0", "LOOP-C, rescan", role="secondary",
            published="paper-store-evidence-paperholo-era/006-loop-pages/e006c/captures/e006c-hpflatbed-1200rgb-3.png"),
    Capture("006col-scan-4-col.png", HOME_FLATBED, "M281", "colour", 1200.0,
            "006.0", "LOOP-C, rescan", role="secondary",
            published="paper-store-evidence-paperholo-era/006-loop-pages/e006c/captures/e006c-hpflatbed-1200rgb-4.png"),
    Capture("e007off-page-1.png", HOME_FLATBED, "AltaLink", "colour", 1200.0,
            "007.0", "office DISC-1 page 1", role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/m281-disc1/captures/disc1-p1-hpflatbed-1200rgb.png"),
    Capture("e007off-page-2.png", HOME_FLATBED, "AltaLink", "colour", 1200.0,
            "007.0", "office DISC-1 page 2", role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/m281-disc1/captures/disc1-p2-hpflatbed-1200rgb.png"),
    Capture("xerox-cal-hp-scan.png", HOME_FLATBED, "AltaLink", "colour",
            1200.0, "007.6", "CAL-1 printed on the AltaLink",
            role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/calpage-hpflatbed-1200rgb.png"),
    Capture("xerox-comp-hp-scan.png", HOME_FLATBED, "AltaLink", "colour",
            1200.0, "007.6", "composite probe on the AltaLink",
            role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/composite-probe-hpflatbed-1200rgb.png"),
    Capture("xerox-overlap-hp-scan.png", HOME_FLATBED, "AltaLink", "colour",
            1200.0, "007.6", "overlap probe on the AltaLink",
            role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/overlap2-hpflatbed-1200rgb.png"),
    Capture("xerox-loop-c-hp-scan.png", HOME_FLATBED, "AltaLink", "colour",
            1200.0, "006.3", "LOOP-C on the AltaLink", role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/e006c-hpflatbed-1200rgb.png"),
    Capture("xerox-disc-1a-p1-hp-scan.png", HOME_FLATBED, "AltaLink",
            "colour", 1200.0, "007.6", "DISC-1a page 1", role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/disc1-a-p1-hpflatbed-1200rgb.png"),
    Capture("xerox-disc-1a-p2-hp-scan.png", HOME_FLATBED, "AltaLink",
            "colour", 1200.0, "007.6", "DISC-1a page 2", role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/disc1-a-p2-hpflatbed-1200rgb.png"),
    Capture("xerox-disc-1b-p1-hp-scan.png", HOME_FLATBED, "AltaLink",
            "colour", 1200.0, "007.6", "DISC-1b page 1", role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/disc1-b-p1-hpflatbed-1200rgb.png"),
    Capture("xerox-disc-1b-p2-hp-scan.png", HOME_FLATBED, "AltaLink",
            "colour", 1200.0, "007.6", "DISC-1b page 2", role="secondary",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/disc1-b-p2-hpflatbed-1200rgb.png"),
    Capture("xerox-mic-blank-hp-scan.png", HOME_FLATBED, "AltaLink", "colour",
            1200.0, "007.7", "BLANK paper from the AltaLink — the MIC hunt; "
            "no printed marks, so no targets, but a clean comb specimen",
            role="blank",
            published="paper-store-evidence-paperholo-era/007-office-disc/altalink-library/captures/001patterns-p6-micblank-hpflatbed-1200rgb.png"),
)

# Colour captures that exist but are NOT the home flatbed, kept in the
# inventory so the exclusion is on the record rather than implied.
EXCLUDED: tuple[tuple[str, str], ...] = (
    ("disc1p1-xeroxscan-col.png", "AltaLink's own scanner, not the flatbed"),
    ("disc1p1-xeroxscan-col-x2.png", "AltaLink's own scanner"),
    ("e006bw-xeroxscan-col.png", "AltaLink's own scanner"),
    ("e006bw-xeroxscan-col-x2.png", "AltaLink's own scanner"),
    ("xeroxscanner-orig-disc1p1-col-600.tif", "AltaLink's own scanner"),
    ("xeroxscanner-orig-e006bw-col-600.tif", "AltaLink's own scanner"),
    ("xerox-e012-A-canon-1200.png", "Canon LiDE 400 — channel_ca's scanner"),
    ("adf-triage/*.png", "M281 sheet feeder at 300 dpi, not the flatbed"),
)


def png_header(path: Path) -> dict[str, Any] | None:
    """IHDR only — 64 bytes, whatever the file weighs."""
    try:
        with path.open("rb") as handle:
            data = handle.read(64)
    except OSError:
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height, depth, kind, _c, _f, _i = struct.unpack(">IIBBBBB",
                                                           data[16:29])
    return {"width": int(width), "height": int(height),
            "bit_depth": int(depth),
            "kind": COLOUR_TYPES.get(kind, str(kind))}


def sha256(path: Path, chunk: int = 1 << 22) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def take(roles: tuple[str, ...] = ("primary", "control", "k-only")
         ) -> list[Capture]:
    """The captures the measurement runs on, headers filled in."""
    out: list[Capture] = []
    for capture in HOME_COLOUR:
        if capture.role not in roles or not capture.path.exists():
            continue
        header = png_header(capture.path)
        if header is None:
            continue
        out.append(Capture(**{**capture.__dict__, "header": header}))
    return out


ALL_ROLES = ("primary", "control", "k-only", "secondary", "blank")


def build(hash_roles: tuple[str, ...] = ALL_ROLES) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for capture in HOME_COLOUR:
        header = png_header(capture.path)
        row: dict[str, Any] = {
            "name": capture.name,
            "present": capture.path.exists(),
            "scanner": capture.scanner,
            "print_engine": capture.engine,
            "mode": capture.mode,
            "scan_dpi": capture.scan_dpi,
            "experiment": capture.experiment,
            "content": capture.content,
            "role": capture.role,
            "placement": capture.placement,
        }
        if header:
            row.update({"width": header["width"], "height": header["height"],
                        "channels": header["kind"],
                        "bit_depth": header["bit_depth"],
                        "bytes": capture.path.stat().st_size,
                        "colour": header["kind"] in ("RGB", "RGBA")})
        if capture.role in hash_roles and capture.path.exists():
            digest = sha256(capture.path)
            row["sha256"] = digest
            if capture.logged_sha256:
                row["sha256_logged"] = capture.logged_sha256
                row["sha256_matches_log"] = digest == capture.logged_sha256
        elif capture.logged_sha256:
            row["sha256_logged"] = capture.logged_sha256
        rows.append(row)
    colour = [r for r in rows if r.get("colour")]
    return {
        "instrument": "measure/scanfield/hp_inventory",
        "question": "does the home/HP flatbed have colour captures at all, "
                    "and what produced them?",
        "scanner": HOME_FLATBED,
        "generated_unix": int(time.time()),
        "record": {
            "ban": "CLAUDE.md scanners bullet — the home flatbed's COLOR "
                   "mode lays an 11.3 px comb, never acquire colour from "
                   "it (experiments/017 P2, declared 2026-07-19)",
            "ban_applies_to": "ACQUISITION; every capture below predates "
                              "the ruling and is read-only legacy material",
            "known_structures": {
                "ccd_comb_mm": 18.63,
                "ccd_comb_phase_mm": 14.1,
                "ccd_comb_axis": "x (sensor)",
                "ccd_comb_depth_dots": -0.9,
                "colour_mode_comb_px_at_1200dpi": 11.36,
                "colour_comb_harmonic_px": 5.68,
                "transport": "stochastic y steps, fresh every scan; "
                             "unstable mode-dependent y scale",
                "source": "experiments/002 §256/§270, experiments/017 P2",
            },
        },
        "counts": {
            "listed": len(rows),
            "present": sum(1 for r in rows if r["present"]),
            "colour": len(colour),
            "primary": sum(1 for r in colour if r["role"] == "primary"),
        },
        "captures": rows,
        "excluded_colour_captures": [
            {"name": name, "reason": reason} for name, reason in EXCLUDED],
    }


def use_evidence_root(path: Path | None) -> None:
    """Pin the evidence root every ``Capture.path`` joins (refused here,
    by name, when neither the flag nor the env var gives one)."""
    global EVIDENCE_ROOT
    EVIDENCE_ROOT = _evidence.resolve(path, tool="scanfield")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _evidence.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-hash", action="store_true")
    args = parser.parse_args(argv)
    use_evidence_root(args.evidence_root)
    out_dir = args.out
    report = build(hash_roles=() if args.no_hash else ALL_ROLES)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "hp-inventory.json"
    path.write_text(json.dumps(report, indent=1))
    print(f"wrote {path}", file=sys.stderr)

    counts = report["counts"]
    print(f"\nhome-flatbed colour inventory: {counts['colour']} colour "
          f"captures present of {counts['listed']} listed "
          f"({counts['primary']} primary)\n")
    print(f"{'capture':<42}{'exp':>8}{'engine':>10}{'kind':>7}"
          f"{'w':>7}{'h':>7}{'role':>10}  placement")
    for row in report["captures"]:
        if not row["present"]:
            print(f"{row['name']:<42}{row['experiment']:>8}  MISSING")
            continue
        print(f"{row['name']:<42}{row['experiment']:>8}"
              f"{row['print_engine']:>10}{row['channels']:>7}"
              f"{row['width']:>7}{row['height']:>7}{row['role']:>10}"
              f"  {row['placement']}")
    mismatched = [r for r in report["captures"]
                  if r.get("sha256_matches_log") is False]
    for row in mismatched:
        print(f"  SHA MISMATCH vs log: {row['name']}")
    print("\nexcluded colour material (not this scanner):")
    for entry in report["excluded_colour_captures"]:
        print(f"  {entry['name']:<44}{entry['reason']}")
    return 1 if mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
