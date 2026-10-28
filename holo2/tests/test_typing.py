"""Static typing as interface enforcement (R1 cross-cutting adoption).

``core`` is the package the rest of the tree types against, so it is the
one that goes strict first: a cross-package wiring mistake should fail at
check time, not three layers down at a lookup that returns ``None``. The
typed ids (``WindowId``, ``FootingId``, ...) are the other half of that —
they cost nothing at runtime (``NewType`` erases to ``str``) and make
"footing id where a window id belongs" a type error instead of a silent
miss.

The gate RUNS: mypy is installed here, and since worklist B12 (RULED
2026-08-12 — "widen the strict-mypy perimeter: cli AND engine into the
gate now, remaining packages as they get touched") its scope is ``core``
plus ``engine`` plus ``cli``: the interfaces the tree types against, the
scheduler that consumes them, and the composition root that joins the
two — which is exactly where a cross-package wiring mistake lives.
``format``, ``capture``, ``solve`` and ``diag`` are measured but not
clean; each joins the perimeter as it is touched. An environment without
mypy skips rather than passing quietly.

The H4 W0-B reconcile (2026-08-15) added five ``solve`` kernel modules —
``pose_fit``, ``reference``, ``pose_audit``, ``cold`` and ``words`` — the
first ``solve`` files in the gate; all five were strict-clean already, so
this only pins that the reconcile's nominal-import swap kept them so. W1
added the three modules that consume them (``lattice_seed``,
``place_shared``, ``placement``), written strict from birth. W2's two
strict newcomers, ``hint_state`` and ``place_chain``, were DELETED whole
by the pull model's clean-slate sweep; the score they carried moved into
``place_job``, which joins the gate here in their place along with the
scheduler that reads it.

``--follow-imports=silent`` is what makes a PARTIAL perimeter mean
anything: a module outside the gate is still analysed, so a call from
``cli`` into ``solve`` is checked against ``solve``'s real signatures —
that is how B12's false ``real_providers() -> tuple[Provider, ...]`` was
caught — while errors inside that module are not reported. ``skip``
would have made those modules ``Any`` and the gate blind.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"


def _cache_dir() -> str:
    """One mypy cache PER XDIST WORKER: the cache is not multi-process
    safe, and four workers racing one ``.mypy_cache`` produce mypy
    INTERNAL ERRORs on a different package each run (observed on an
    unmodified tree). Sub-directories of the default location keep the
    warm-cache speed across runs, and mypy self-ignores every cache
    dir it creates (it writes a ``*`` .gitignore inside), so git stays
    clean without a repo rule.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "serial")
    return str(_SRC / ".mypy_cache" / worker)

# Strict, minus the two flags that would fight the tree's own conventions:
# numpy is untyped here (no stubs installed), and the carried leaves use
# ``Any`` at the raster boundary on purpose.
STRICT_FLAGS = (
    "--strict",
    "--ignore-missing-imports",
    "--disallow-any-generics",
    "--warn-unreachable",
    "--no-error-summary",
    "--follow-imports=silent",
)

PACKAGES = (
    "holo2/core", "holo2/engine", "holo2/cli.py",
    "holo2/solve/pose_fit.py", "holo2/solve/reference.py",
    "holo2/solve/pose_audit.py", "holo2/solve/cold.py",
    "holo2/solve/words.py",
    # H4 W1: the family-``place`` provider and everything it was built
    # from — strict from birth, which is what the wave promised.
    "holo2/solve/lattice_seed.py", "holo2/solve/place_shared.py",
    "holo2/solve/placement.py",
    # H4 W1a: the prepared plane that provider reads its pixels through.
    "holo2/solve/prepared.py",
    # H4 W2's pull model: the per-window job (which now owns the
    # ratified distance ``hint_state`` used to) and the scheduler that
    # ranks by it — the promise W1's own modules were written to, kept
    # across the sweep that deleted the two files it applied to before.
    "holo2/solve/place_job.py", "holo2/solve/place_sched.py",
    # H4 streaming ingestion: the ingest frontier — the third family the
    # composition root binds, written strict from birth like the two
    # waves before it.
    "holo2/solve/ingest.py",
    # H4 W5: the contradiction fact and its consumer — the same
    # strict-from-birth promise, kept for the wave that decides what a
    # placement is allowed to have contributed.
    "holo2/solve/contradiction.py", "holo2/solve/quarantine.py",
    # H4 W6: the scheduler's growth half, carved out of ``place_sched``
    # at the file cap. It arrives strict because its parent was — a
    # relocation may not lose a guarantee the code already had.
    "holo2/solve/place_subdivide.py",
    # F2a (2026-08-23, ruling J2-3): the re-read and the two seams it
    # forced. ``generation`` and ``resample`` are strict from birth;
    # ``place_slot`` and ``ctx_apply`` arrive strict because the files
    # they were carved out of were (``place_sched`` was in the gate) or
    # because the carve is where the guarantee is cheapest to take.
    "holo2/solve/ctx_apply.py", "holo2/solve/generation.py",
    "holo2/solve/place_slot.py", "holo2/solve/resample.py",
    # WP-1.0 (2026-08-22, RULINGS B11): the close's format input surface,
    # split out of the carried fountain_close leaf — strict from birth;
    # the carried leaves stay out (39 strict errors, all carried code).
    "holo2/format/close_spec.py",
    # WP-1.1 (2026-08-22): the family enum, the one dispatch key. Same
    # rule — a new format module is strict from birth.
    "holo2/format/family.py",
    # WP-1.2 (2026-08-22, RULINGS B11): the identity lattice — the
    # grammar, the frozen legacy catalogue and the total resolver. Three
    # more strict-from-birth format modules; the CARRIED leaves stay out
    # (39 strict errors, all of them in carried code, and annotating a
    # carried function is drift the AST oracle would have to declare).
    "holo2/format/lattice.py", "holo2/format/fossils.py",
    "holo2/format/resolve.py",
    # WP-1.2 review (2026-08-22): the two holo2-ORIGINAL format modules
    # the lattice reshaped — ``format_v1`` took +260/-53 lines in that
    # package and ``registry_rows`` its coding-id ground. Both measured
    # strict-clean already, so this is the tree's own rule applied ("each
    # joins the perimeter as it is touched"), and the colour port edits
    # both next, which is when a regression would otherwise land.
    "holo2/format/format_v1.py", "holo2/format/registry_rows.py",
    # C2 (2026-08-22, RULINGS G2): the colour family constructors. A new
    # format module, so strict from birth — and the one the colour port
    # will lean on hardest, since holo2 can build these rows and never
    # decode them: nothing downstream will catch a type error here for
    # it.
    "holo2/format/families.py",
    # F1 review (2026-08-23): the record layer F1 gave the context halo
    # to (+124 lines: ``ring_masks``, ``pack_piece_observation``,
    # ``unpack_piece_halo``). Measured strict-clean already, so this is
    # the tree's own rule applied to a module that WAS touched — the rule
    # is about touched modules, not new ones — and it is the layer where
    # a blob-layout type error would reach every reader of a piece.
    "holo2/solve/records.py",
)


@pytest.mark.parametrize("package", PACKAGES)
def test_package_is_mypy_strict(package: str) -> None:
    pytest.importorskip(
        "mypy", reason="mypy is not installed here; strict-mode cleanliness "
                       "of the perimeter goes unverified in this environment")
    result = subprocess.run(
        [sys.executable, "-m", "mypy", *STRICT_FLAGS,
         "--cache-dir", _cache_dir(), package],
        cwd=_SRC, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"mypy --strict refuses {package}:\n{result.stdout}{result.stderr}")


def test_the_typed_ids_are_erased_at_runtime() -> None:
    """A NewType costs nothing: the envelope must not change shape.

    The atoms are still ``NewType``s (a capture sha, a footing, a
    stream); a STRUCTURED id is its ``ResourceKey``, and it encodes as
    the flat array that key has always been.
    """
    from holo2.core import FootingId
    from holo2.core.codec import encode_dataclass
    from holo2.solve import PoseRecord
    from conftest import FOOTING, WINDOW

    record = PoseRecord(window_id=WINDOW, footing_id=FootingId(FOOTING),
                        page=0,
                        native_affine=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
    encoded = encode_dataclass(record)
    assert encoded["window_id"] == WINDOW.to_json() == ["window", *WINDOW.parts]
    assert isinstance(encoded["footing_id"], str)
    assert FootingId(FOOTING) == FOOTING, "NewType is not a wrapper"
