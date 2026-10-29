"""The archived-evidence root — one spelling for every instrument.

Every tool under ``measure/`` that reads archived CAPTURES or run
directories takes ``--evidence-root DIR`` (fallback
``$PAPER_EVIDENCE_ROOT``) and refuses by name when neither is given.
Tools that name individual artefacts (``--run-dir``, ``--gt-dir``,
``--payload``, ``--scan``) keep those flags; this root is for the ones
that join a declared, relative table.

The root is the PUBLISHED evidence archive: the directory that holds its
two releases, :data:`PAPERHOLO_ERA` (experiments 001–026) and
:data:`HOLO_2026_10` (027–042), each a ``<NNN-experiment>/…`` tree.  A
declared path names the published file, release directory first
(``paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/
records/corner_fit.npy``), and is joined onto the root verbatim.
Captures are published as lossless JPEG XL (``<name>.tiff.jxl``, the
TIFF's own header bytes in the release's ``headers/``); a reader expects
the UNPACKED ``<name>.tiff`` at the published path, rebuilt byte for
byte by the release's ``tools/unpack.sh`` — :func:`need` refuses with
that recipe when only the ``.jxl`` is there.  An input the archive does
not carry (tier delete: run journals, raster caches, ``*_gt.npy`` fields
that the published PostScript regenerates) is refused by name by the
tool that wanted it.

Stateless on purpose: ``scanner``/``scanfield`` import this file as the
top-level ``_evidence`` (they run with ``PYTHONPATH=measure``), the rest
as ``measure._evidence``.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

#: The command-line flag, spelled once.
FLAG = "--evidence-root"

#: The environment variable read when the flag is absent.
ENV = "PAPER_EVIDENCE_ROOT"

#: The release directory of experiments 001–026.
PAPERHOLO_ERA = "paper-store-evidence-paperholo-era"

#: The release directory of experiments 027–042.
HOLO_2026_10 = "paper-store-evidence-holo-2026-10"

#: The archive's own spelling of a capture's packed pixels.
JXL_SUFFIX = ".jxl"


def add_argument(parser: argparse.ArgumentParser) -> None:
    """Declare ``--evidence-root`` (optional on the parser; ``resolve``
    refuses later, so a ``--selftest`` arm can run without it)."""
    parser.add_argument(FLAG, dest="evidence_root", type=Path, default=None,
                        help=f"the published evidence archive root, the "
                             f"directory holding {PAPERHOLO_ERA}/ and "
                             f"{HOLO_2026_10}/ (else ${ENV})")


def resolve(given: Path | None, *, tool: str) -> Path:
    """The root: ``given``, else ``$PAPER_EVIDENCE_ROOT``, else a refusal
    that names both."""
    if given is not None:
        return Path(given)
    value = os.environ.get(ENV)
    if not value:
        raise SystemExit(f"{tool}: no evidence root — pass {FLAG} DIR "
                         f"or set ${ENV}")
    return Path(value)


def _release_root(path: Path) -> Path | None:
    """The release directory ``path`` sits under, if any."""
    for parent in path.parents:
        if parent.name in (PAPERHOLO_ERA, HOLO_2026_10):
            return parent
    return None


def _raw_bytes(release: Path, packed_rel: str) -> str | None:
    """``raw_bytes`` of a packed capture, from the release's MANIFEST.tsv."""
    manifest = release / "MANIFEST.tsv"
    if not manifest.is_file():
        return None
    lines = [line for line in manifest.read_text("utf-8").splitlines()
             if not line.startswith("#")]
    for row in csv.DictReader(lines, delimiter="\t",
                              quoting=csv.QUOTE_NONE, escapechar="\\"):
        if row.get("published_path") == packed_rel:
            return row.get("raw_bytes") or None
    return None


def unpack_recipe(path: Path) -> str:
    """How to rebuild the TIFF ``path`` from its published ``.jxl``."""
    packed = Path(f"{path}{JXL_SUFFIX}")
    release = _release_root(path)
    if release is None:
        return (f"only {packed} is there (lossless JPEG XL): rebuild the "
                f"TIFF with its release's tools/unpack.sh")
    rel = path.relative_to(release).as_posix()
    header = release / "headers" / (rel.replace("/", "__") + ".tiffhdr")
    raw = _raw_bytes(release, rel + JXL_SUFFIX) or "RAW_BYTES"
    return (f"only {packed.name} is there (lossless JPEG XL): rebuild the "
            f"TIFF first — {release / 'tools' / 'unpack.sh'} {packed} "
            f"{header} {raw} {path}  (RAW_BYTES = raw_bytes of that row in "
            f"{release / 'MANIFEST.tsv'})")


def need(*paths: Path, tool: str, regenerate: str = "") -> None:
    """Refuse, naming every absent path, unless all of ``paths`` exist.

    A capture whose ``.jxl`` is published but not yet unpacked gets the
    unpack recipe; ``regenerate`` (a command) is appended for an input
    the archive does not carry but the record can rebuild.
    """
    missing = [path for path in dict.fromkeys(Path(path) for path in paths)
               if not path.exists()]
    if not missing:
        return
    lines = [f"{tool}: required input(s) absent:"]
    for path in missing:
        lines.append(f"  {path}")
        if Path(f"{path}{JXL_SUFFIX}").exists():
            lines.append(f"    {unpack_recipe(path)}")
    if regenerate:
        lines.append(f"  not in the published archive; regenerate with: "
                     f"{regenerate}")
    raise SystemExit("\n".join(lines))


def withdrawn(*inputs: str, tool: str, why: str) -> SystemExit:
    """The refusal for inputs the published archive does not carry and
    nothing in the record rebuilds — ``raise _evidence.withdrawn(...)``."""
    return SystemExit(f"{tool}: input(s) not in the published evidence "
                      f"archive ({why}): " + ", ".join(inputs))
