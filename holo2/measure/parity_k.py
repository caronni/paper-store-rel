#!/usr/bin/env python
"""THE K PARITY HARNESS — v1 against holo2, one row per K sheet (W4).

    env/bin/python holo2/measure/parity_k.py --sheet e029
    env/bin/python holo2/measure/parity_k.py --sheet all \\
        --out scratch/holo2-catchup/real/parity-k.md

NOT A TEST and not collectable as one — the same standing as
``tile_differential.py``, ``rf1_resume.py`` and every other by-path driver
in this directory (``holo2/measure/README.md``). Its two silent
classifiers and its declared list's own consistency are pinned in
``tests/holo2_oracles/test_oracle_parity_k.py`` — there and not under
``holo2/tests`` because this module imports ``holo`` (the firewall
exempts exactly that directory and ``measure/verdicts/
test_v1_parity.py``).

THE RENDERING LIVES NEXT DOOR, in ``parity_k_report.py``: this file
declares the population, measures both trees and owns every path; that
one turns finished rows into markdown and imports nothing from here.
The seam is the one HANDOFF-W4 §6 named and declined to take at 941
lines; the review fixes pushed the single file past the cap, so it was
taken (2026-08-23).

WHAT IT IS FOR (RULINGS I1, 2026-08-23 — the user's bar): *"we will not
get past H6 unless K performs as well or better than src/holo on each
available / parseable K scan, and all synthetic scrap 'scans'. There is
no 'excuse' for underperforming."* This driver is the instrument that
states the bar's arithmetic: one ROW per sheet, holo2's certificates
minus v1's, with both sides' payload sha checked against the golden so a
certificate delta can never be read without the correctness statement
beside it.

THE TWO SIDES, and why they are asymmetric (RULINGS I5, 2026-08-23):

* **v1 is READ, never re-run on paper.** v1's full harvests already exist
  on disk as ``receive.state`` files, and the state is a complete record
  of the thing this harness needs: ``certificates`` (the harvest),
  ``close.payload_sha256`` + ``close.status`` (the correctness
  statement), and — the flags question — the LANE KINDS of every declared
  capture plan, because ``--mopup`` and ``--refine`` are exactly what put
  ``mopup``/``refine`` lanes in a plan (``holo.receive.cascade.
  lane_kind``). A v1 state that carries all three kinds RAN the full
  harvest; that is a durable fact and not a claim about a command line
  nobody wrote down. Reading one is a qualification-only instrument
  (it imports ``holo``), which is why this file lives in ``measure/``.
* **holo2 runs FRESH**, through the CLI operator path — ``./confetti2.py
  --format <id> --complete --workers 8`` — and never by resume: W3's
  ``COST_REFINE`` (90 -> 200) is a ``recipe_entries`` value, and those
  bind ``SessionIdentity`` BY VALUE, so every archived holo2 state
  refuses this build at identity (HANDOFF-W3 §3.1). A fresh
  ``--complete`` run is also the only shape in which RULING I2's price
  ordering is expressible at all: on an exhausted state refine is the
  only family with anything ready.

NEVER RUN A REAL SHEET TWICE. A real-capture ``--complete`` decode costs
8-19 minutes at ``--workers 8``, so every holo2 arm writes a SIDECAR
(``<state-dir>.parity.json``: argv, wall, epilogue, exit code, the
prepared-plane counts on both sides of the decode, and the tree and dials
it ran under) beside its state and ADOPTS it on a re-invocation instead
of decoding again. Deleting
the sidecar is the only way to ask for a second decode, and it is a
deliberate act. The wall in an adopted row is the wall of the run that
wrote the sidecar, dated in the report.

WHAT A ROW MEANS, and what it does not. Certificates are the record
(measurement doctrine); the wall is reported but is a single run at one
worker count on one machine and is never a bar. A delta is only
interpretable beside the payload sha: v1 and holo2 stopping at different
certificate counts on the same bytes is the DESIGNED difference between
a harvest and a solve, and it is the payload sha that says neither side
minted a wrong tile.

THE DECLARED LIST, and the census behind it (§ ``SHEETS`` below). Every
``*.state`` under ``<repo>`` was enumerated and its
``format_row_id`` read (2026-08-23): 25 states, of which exactly FIVE are
the K row ``c2-r0700@3392x2368`` and the other twenty are colour rows
(``c2-``/``c3-cmy7-p120-v0``, ``c2-``/``c3-cmy8-p120-v0``,
``c2-cmy8-r0700-p120-x1``, ``c2-cmy8-r0850-p120-x1``) — not K, not this
harness's business, and not decodable by holo2 at all this wave (the
fatal colour door, ``registry_rows.tile_format_for``). Of the five K
states, three are DISTINCT subjects and two are duplicate harvests of
subjects already listed:

* ``scratch/color-uplift/full/hp-c2-k-pkfinal/receive.state`` and
  ``…/xerox-c2-k-pkfinal/receive.state`` are the SAME two captures
  (``d9c4e932…`` / ``57a26145…``) under a different
  ``receiver_policy_id`` (the colour-uplift PK-FINAL receiver rather than
  the counting run), and their certificate SETS are IDENTICAL to the two
  states named below — measured, not assumed: 1940 vs 1940 and 1930 vs
  1930 with an empty symmetric difference both ways, same payload sha.
  They add no row and no information; that they agree tile-for-tile
  across two v1 receiver policies is itself the reason the two v1 anchors
  below can be quoted as stable numbers.

Captures with NO v1 state are out of scope by RULING I5's own mechanism
(v1's side of a row is a state read, and there is nothing to read):
``scratch/holo2-demo/e028-genclean-c2-r0700.tiff`` (a K page, but a CLEAN
RENDER — "easy mode" in MEASUREMENTS H3bis — never decoded by v1 into a
state on this machine), the paperholo-format sheets (e016/e018/e018b/
e023c/e025 — a different printed format, not holo v1 at all), the
calibration and discovery sheets (``xerox-canon-cal-*``, e028's
knife-edge and HCAL pairs — no payload field), and every colour capture.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import inspect
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# Self-locating, like every other by-path driver here (``confetti.py``'s
# own reason): neither package is pip-installed, and an operator running
# this by path should not also have to spell a PYTHONPATH.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE, _HERE / "verdicts", _ROOT / "src",
              _ROOT / "holo2" / "src"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

import parity_k_report                                          # noqa: E402
import tile_differential                                        # noqa: E402

from holo.receive.cascade import lane_kind                      # noqa: E402
from holo.receive.session import load_session                   # noqa: E402
from holo.receive.session_model import SessionState             # noqa: E402

from holo2.engine.recipe import COST_REFINE                     # noqa: E402
from holo2.solve.refine import PoseRefineProvider               # noqa: E402

#: The repository the archived states and captures live in. This driver
#: runs from a WORKTREE (``paper-holo2-catchup``) whose ``scratch/`` is
#: its own; the physical corpus is in the main checkout beside it.
_CORPUS = Path("<repo>")

#: The one payload every K sheet in this corpus carries: the 465,580-byte
#: counting volume. Named here so a row's "zero wrong" is a comparison
#: against a constant rather than against whichever side happened to
#: publish first.
GOLDEN_K_SHA = ("e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9"
                "dd165787af")

#: The DEMO's payload is a different volume — ``scripts/demo.sh``'s 1 MB
#: counting file (byte i = i & 0xFF), spread over three sheets. Declared
#: even though NEITHER tree closes this volume from nine scrap platens
#: (K = 2,913 source symbols against 2,673 / 2,668 certified tiles), so
#: the row's zero-wrong marks read "n/a" on both sides: a golden that is
#: knowable should be named whether or not this run reaches it, and the
#: day a run does, the comparison is already correct.
GOLDEN_DEMO_SHA = ("67870dfc9c64e7aa270a3f7e8051ae65d207f93fc3df04d7572e"
                   "6365af69cd0d")


# --------------------------------------------------------------------
# the declared list
# --------------------------------------------------------------------


@dataclass(frozen=True)
class Sheet:
    """One row of the parity table, declared."""

    label: str
    #: The printed identity BOTH trees are given — an ``L:`` fossil line
    #: for a printed sheet, a v2 id for a synthetic fixture page.
    format_ref: str
    kind: str                                  # real | scrap | fixture
    #: ``(path, dpi)`` per capture, absolute. Empty for a fixture arm,
    #: which renders its own capture (see :func:`fixture_scans`).
    scans: tuple[tuple[Path, float], ...] = ()
    pages: int = 1
    #: v1's side: an archived state to READ (RULING I5), or ``None`` to
    #: run v1's own CLI at its full harvest on the same pixels.
    v1_state: Path | None = None
    #: Expected payload sha for BOTH sides. ``None`` on an arm whose
    #: volume cannot close (a partial volume): the row then reports the
    #: close status and no sha comparison, which is the honest shape.
    golden_sha: str | None = GOLDEN_K_SHA
    #: For a fixture arm: the ``_fixtures`` recipe to build it with.
    fixture: str = ""
    #: An existing ``<state-dir>.prepared`` sibling to APFS-CLONE into
    #: place before the decode. The prepared planes are content-addressed
    #: on everything they are a function of (the capture sha, the region's
    #: clipped bbox, the support mask's own bytes, the backing scalar, the
    #: pitch and the aperture — ``solve/prepared.py``), so a clone of the
    #: same capture's planes is byte-identical to what this run would
    #: build, and a changed input can only ever produce a different NAME
    #: (a stale file cannot be adopted silently). It is here because
    #: building them for a 4800-dpi sheet costs ~24 GB and several
    #: minutes, and the wall this harness reports is the SOLVE. Every
    #: report says which rows adopted planes.
    prepared_from: Path | None = None
    note: str = ""


#: THE DECLARED LIST. Three archived-v1 rows (two printed sheets and the
#: nine-scrap synthetic demo, all three of which v1 has already harvested
#: to exhaustion on disk) plus the fixture rows, where no v1 state exists
#: and BOTH trees therefore run on the same rendered pixels.
SHEETS: tuple[Sheet, ...] = (
    Sheet(label="e029", kind="real", format_ref="L:c2-r0700@3392x2368",
          scans=((_CORPUS / "scratch/e028/hp-canon-c2-ink-counting.tiff",
                  4800.0),),
          v1_state=(_CORPUS / "scratch/e028"
                    / "holo-c2-r0700-q07-ink-counting/receive.state"),
          prepared_from=(_ROOT / "scratch/holo2-catchup/real"
                         / "e029-state-complete.prepared"),
          note="the M281 ink-tight print, Canon 4800 grey (e029)"),
    Sheet(label="xerox", kind="real", format_ref="L:c2-r0700@3392x2368",
          scans=((_CORPUS / "scratch/in/xerox-canon-c2-bw.tiff", 4800.0),),
          v1_state=(_CORPUS / "scratch/in"
                    / "holo-xerox-c2-counting-receive.state"),
          prepared_from=(_ROOT / "scratch/holo2-catchup/real"
                         / "state-complete.prepared"),
          note="the AltaLink C8245 print of the same volume (e032)"),
    Sheet(label="demo9", kind="scrap", format_ref="L:c2-r0700@3392x2368",
          scans=tuple(
              (_CORPUS / f"build/demo/scrap-p{page}-{platen:03d}.tif", 4800.0)
              for page in (0, 1, 2) for platen in (1, 2, 3)),
          pages=3,
          v1_state=_CORPUS / "build/demo/receive-v1.state",
          prepared_from=_CORPUS / "build/demo/receive.prepared",
          golden_sha=GOLDEN_DEMO_SHA,
          note="scripts/demo.sh's nine scrap platens (3 pages x 3), "
               "synthetic nominal-profile scans at 4800 dpi. NEITHER "
               "tree closes this volume from these platens (K = 2,913 "
               "source symbols); both sessions end honestly OPEN, so "
               "both zero-wrong marks read n/a and the row's subject is "
               "the certificate count alone"),
    Sheet(label="fx-channel", kind="fixture", format_ref="c2-k-r0700@8x8",
          fixture="channel", golden_sha=None,
          note="the verdicts' run-channel PAGE (e032 anisotropic warp, 2% "
               "cell error), decoded at the default cascade recipe — run "
               "channel itself decodes at RECIPE_V1_FINEST, so this row is "
               "the verdict's page and NOT the verdict's decode"),
    Sheet(label="fx-banded", kind="fixture", format_ref="c2-k-r0700@8x8",
          fixture="banded", golden_sha=None,
          note="verdicts run banded: 16% cell error over the right quarter"),
    Sheet(label="fx-subdivision", kind="fixture",
          format_ref="c2-k-r0700@11x11", fixture="subdivision",
          golden_sha=None,
          note="verdicts run subdivision: the coverage ramp at 0.85"),
)

SHEETS_BY_LABEL = {sheet.label: sheet for sheet in SHEETS}

#: THE REFINE-OFF BASELINE, for the three rows that have one: the same
#: sheet, the same ``--complete --workers 8`` shape, measured on the
#: tree BEFORE W3 turned RF1 on and repriced it. Every field is quoted
#: from a committed record and never re-derived, and each row names the
#: file it came from so a reader can check it. Two caveats travel with
#: the walls and are printed with them: (1) both real-sheet baselines
#: BUILT their prepared planes inside their wall while the runs above
#: adopt theirs, so the comparison understates the difference rather
#: than overstating it; (2) the demo baseline's tree and flags were
#: never recorded — it is quoted as the only holo2 number that exists
#: for that page, not as a controlled arm.
REFINE_OFF_BASELINE: dict[str, dict[str, Any]] = {
    "e029": {"certificates": 1911, "commits": 11513,
             "fires": 12107, "done_cells": 7827512, "wall_s": 1126.85,
             "source": "scratch/holo2-catchup/real/e029-runs.log (RUN D)"},
    "xerox": {"certificates": 1882, "commits": 12263, "fires": 12532,
              "done_cells": 7728326, "wall_s": 718.97,
              "source": "scratch/holo2-catchup/real/runs.log (RUN B)"},
    "demo9": {"certificates": 2665, "commits": None, "fires": None,
              "done_cells": None, "wall_s": None,
              "source": "holo2/docs/H5-PLAN.md:57-59 (tree and flags "
                        "not recorded there)"},
}


# --------------------------------------------------------------------
# the fixture arms (no archived v1 state exists; both trees run)
# --------------------------------------------------------------------


def fixture_scans(sheet: Sheet, work: Path) -> tuple[
        tuple[tuple[Path, float], ...], bytes]:
    """Render one verdicts page and hand back its scans and its payload.

    The parameters are the verdicts' own, re-declared here rather than
    imported from ``verdicts/conftest.py`` — the precedent
    ``v1_side_by_side.py`` set and its reason: a pytest ``conftest`` is
    not a module a by-path driver imports. ``_fixtures.render`` is
    content-addressed on disk, so these are the verdicts' own cache
    entries and not a second rendering of the same page.

    THE PAGE IS THE VERDICT'S; THE DECODE IS NOT, on one arm (review
    fix, 2026-08-23). ``run banded`` and ``run subdivision`` decode at
    ``RECIPE_V1``, which is also the CLI's default, so those two rows
    are the verdicts' decode as well as their page. ``run channel``
    decodes at ``RECIPE_V1_FINEST`` (``verdicts/conftest.py``: the
    finest-only reading, the pre-lanes configuration) while this arm
    goes through the CLI at the default cascade — same pixels, a
    different reading set. Nobody may quote the fx-channel row as run
    channel's own parity.
    """
    from _fixtures import (CHANNEL_ROTATION_DEG, CHANNEL_SCALE_YX,
                           SUBDIVISION_RAMP, build_page, render)

    page = build_page(sheet.format_ref)
    if sheet.fixture == "channel":
        capture = render(page.dots, work / "channel.png", px_per_dot=2,
                         cell_dots=page.cell_dots,
                         rotation_deg=CHANNEL_ROTATION_DEG,
                         pitch_scale=CHANNEL_SCALE_YX, noise_sigma=2.0,
                         cell_error_rate=0.02)
    elif sheet.fixture == "banded":
        capture = render(page.dots, work / "banded.png", px_per_dot=2,
                         cell_dots=page.cell_dots, cell_error_rate=0.16,
                         cell_error_band=(0.75, 1.0), rotation_deg=0.3,
                         pitch_scale=1.003, noise_sigma=2.0)
    elif sheet.fixture == "subdivision":
        capture = render(page.dots, work / "faded.png", px_per_dot=2,
                         cell_dots=page.cell_dots,
                         rotation_deg=CHANNEL_ROTATION_DEG,
                         noise_sigma=2.0, ink_ramp=SUBDIVISION_RAMP)
    else:                                       # pragma: no cover - typo net
        raise SystemExit(f"parity_k: unknown fixture arm {sheet.fixture!r}")
    return ((capture.path, capture.dpi),), page.payload


# --------------------------------------------------------------------
# v1's side
# --------------------------------------------------------------------


@dataclass(frozen=True)
class V1Side:
    source: str                       # "archived state <path>" | argv
    state_path: Path
    certificates: int
    payload_sha: str | None
    close_status: str
    #: The FLAGS, as the state records them: which lane kinds the capture
    #: plans declare. ``--mopup`` puts mopup lanes in a plan and
    #: ``--refine`` puts refine lanes in it, so this IS the durable
    #: record of the harvest the run was driven at.
    lane_kinds: dict[str, int]
    receiver_policy_id: str
    format_row_id: str
    capture_shas: tuple[str, ...]
    wall_s: float | None = None


def _lane_kind_census(state: SessionState) -> dict[str, int]:
    census: dict[str, int] = {}
    for capture in state.captures:
        for lane in capture.plan:
            kind = lane_kind(lane)
            census[kind] = census.get(kind, 0) + 1
    return dict(sorted(census.items()))


def read_archived_v1(path: Path) -> V1Side:
    """v1's side of a row, READ (RULING I5). Validates it loads HERE.

    ``load_session`` is a plain file read with no lock and no write, and
    it is also the validation the package asked for: a state that no
    longer parses against the current ``src/holo`` raises out of this
    call rather than being summarised from its filename.
    """
    state = load_session(path)
    close = state.close
    return V1Side(
        source=f"archived state {path}", state_path=path,
        certificates=len(state.certificates),
        payload_sha=close.payload_sha256,
        close_status=close.status.value,
        lane_kinds=_lane_kind_census(state),
        receiver_policy_id=state.receiver_policy_id,
        format_row_id=state.format_row_id,
        capture_shas=tuple(c.source_sha256 for c in state.captures))


def run_v1_cli(sheet: Sheet, scans: Sequence[tuple[Path, float]],
               work: Path, *, workers: int, timeout: float) -> V1Side:
    """v1's FULL HARVEST on the same pixels: ``--complete --mopup --refine``.

    The stopping rule matters more than any other flag on this line:
    those three are what the archived real-sheet states were driven at
    (their plans carry ordinary+mopup+refine lanes), so a fixture arm
    driven any other way would not be comparable to the rows above it.
    """
    state_path = work / f"v1-{sheet.label}.holo"
    out_path = work / f"v1-{sheet.label}.bin"
    sidecar = work / f"v1-{sheet.label}.parity.json"
    if state_path.is_file():
        # ADOPTED, for the same reason holo2's side adopts (and one more):
        # ``confetti.py decode`` refuses an existing ``-o`` outright, so a
        # second invocation would not repeat the decode, it would REFUSE
        # it. Reading the state back is the same answer the first run
        # produced, and the sidecar carries the argv and wall that
        # produced it.
        saved = (json.loads(sidecar.read_text(encoding="utf-8"))
                 if sidecar.is_file()
                 else {"argv": "(argv unrecorded: state predates the "
                               "sidecar)", "wall_s": 0.0,
                       "ran_at": "unrecorded"})
        print(f"parity_k: adopting {state_path} "
              f"(decoded {saved['ran_at']}, {saved['wall_s']:.1f} s)",
              file=sys.stderr)
        side = read_archived_v1(state_path)
        return V1Side(source=saved["argv"] + "  [adopted]",
                      state_path=state_path,
                      certificates=side.certificates,
                      payload_sha=side.payload_sha,
                      close_status=side.close_status,
                      lane_kinds=side.lane_kinds,
                      receiver_policy_id=side.receiver_policy_id,
                      format_row_id=side.format_row_id,
                      capture_shas=side.capture_shas,
                      wall_s=float(saved["wall_s"]))
    argv: list[str] = [sys.executable, str(_ROOT / "confetti.py"), "decode"]
    for path, _dpi in scans:
        argv.append(str(path))
    for _path, dpi in scans:
        argv += ["--scan-dpi", str(dpi)]
    argv += ["--format", sheet.format_ref, "--state", str(state_path),
             "-o", str(out_path), "--complete", "--mopup", "--refine",
             "--workers", str(workers)]
    ran_at = time.strftime("%Y-%m-%d %H:%M:%S")
    started = time.perf_counter()
    finished = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, cwd=str(_ROOT))
    wall = time.perf_counter() - started
    if not state_path.is_file():
        raise SystemExit(
            f"parity_k: v1 wrote no state for {sheet.label} "
            f"(exit {finished.returncode})\n{finished.stderr.strip()}")
    side = read_archived_v1(state_path)
    sidecar.write_text(json.dumps({
        "argv": " ".join(argv[1:]), "wall_s": wall, "ran_at": ran_at,
        "returncode": finished.returncode,
        "certificates": side.certificates}, indent=2) + "\n",
        encoding="utf-8")
    return V1Side(source=" ".join(argv[1:]), state_path=state_path,
                  certificates=side.certificates,
                  payload_sha=side.payload_sha,
                  close_status=side.close_status,
                  lane_kinds=side.lane_kinds,
                  receiver_policy_id=side.receiver_policy_id,
                  format_row_id=side.format_row_id,
                  capture_shas=side.capture_shas, wall_s=wall)


# --------------------------------------------------------------------
# holo2's side
# --------------------------------------------------------------------


@dataclass(frozen=True)
class H2Side:
    argv: str
    state_dir: Path
    certificates: int
    payload_sha: str | None
    payload_bytes: int | None
    returncode: int
    wall_s: float
    epilogue: tuple[str, ...]
    adopted: bool                     # True = a sidecar was reused
    ran_at: str
    #: What happened to the prepared planes before the decode — built by
    #: this run, or adopted from a declared sibling (see
    #: :func:`_adopt_prepared`).
    #:
    #: REVIEW FIX (2026-08-23): this field used to carry the claim that
    #: "the wall is the SOLVE either way", and that claim was FALSE on
    #: the demo row — the clone held 2,151 planes and the directory held
    #: 2,187 afterwards, so 36 planes were BUILT INSIDE the 12,251 s
    #: wall. Adoption is now MEASURED and not asserted: the two counts
    #: below are taken immediately before and after the subprocess, and
    #: a row whose counts differ reports solve+prepare, not solve.
    prepared: str = "built by this run"
    #: Files in ``<state-dir>.prepared`` before the decode (after any
    #: clone) and after it. ``None`` on a sidecar written before this
    #: field existed — the report then says "unmeasured", never "hit".
    prepared_before: int | None = None
    prepared_after: int | None = None
    #: The tree and the dials AT DECODE TIME (review fix, 2026-08-23):
    #: ``git_head``, ``git_dirty`` and :func:`_dial_state`'s keys, plus
    #: ``backfilled`` on the sidecars that predate the field. Read from
    #: the sidecar PER ROW rather than off the live tree, so a re-render
    #: after a reprice cannot silently relabel an adopted row.
    provenance: dict[str, Any] = dataclasses.field(default_factory=dict)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _h2_certificate_count(state_dir: Path, stream: str = "main") -> int:
    """Counted off the STATE, never parsed out of the epilogue line.

    The epilogue and the state agree by construction, but the state is
    the record and a parse is a second thing to get wrong. Opened
    through ``tile_differential``'s own read-only door (its docstring
    carries the lock caveat).
    """
    with tile_differential.open_h2_store(state_dir) as store:
        index = tile_differential.build_h2_index(store)
        return len(tile_differential.h2_certified_tiles(
            index.store_index, stream))


def _epilogue_lines(*streams: str) -> tuple[str, ...]:
    """The CLI's own six-row summary, kept verbatim for the report.

    Both streams are scanned because the epilogue is written to STDERR
    (measured, 2026-08-23: a fixture run's stdout carries none of it) —
    the CLI's own choice, stdout being the operator's data channel.
    """
    keep = ("format ", "capture ", "queue ", "work ", "tiles ", "close ",
            "confetti2:")
    return tuple(line.rstrip() for stream in streams
                 for line in stream.splitlines()
                 if line.startswith(keep))


def _adopt_prepared(sheet: Sheet, state_dir: Path) -> str:
    """Clone a declared ``.prepared`` sibling into place, or say why not.

    ``cp -Rc`` is an APFS CLONE: no bytes are copied and no space is
    used until one side is written, which is what makes adopting 24 GB
    of prepared planes free. It is a plain recursive copy anywhere
    ``-c`` is refused, which costs the space but never the correctness
    (the planes are content-addressed either way).
    """
    target = state_dir.parent / f"{state_dir.name}.prepared"
    if sheet.prepared_from is None:
        return "built by this run"
    if target.exists():
        return f"already present at {target.name}"
    if not sheet.prepared_from.is_dir():
        return (f"declared source {sheet.prepared_from} is absent — "
                "planes built by this run")
    for flags in (["-Rc"], ["-R"]):
        done = subprocess.run(["cp", *flags, str(sheet.prepared_from),
                               str(target)], capture_output=True, text=True)
        if done.returncode == 0:
            return (f"adopted from {sheet.prepared_from} "
                    f"({'APFS clone' if flags == ['-Rc'] else 'copy'})")
    return f"clone of {sheet.prepared_from} FAILED — planes built by this run"


def _prepared_count(state_dir: Path) -> int:
    """Files in ``<state-dir>.prepared`` — 0 when the directory is absent.

    Absent is a COUNT (nothing prepared yet), not an unknown; ``None``
    is reserved for a sidecar written before this field existed, which
    is the only case the report may call unmeasured.

    Review fix, 2026-08-23. The W4 hand-off asserted a "100% cache hit"
    on all three big rows from one spot check; it held on the two real
    sheets and NOT on the demo (2,151 cloned, 2,187 afterwards). Counting
    both sides of the subprocess turns the claim into a measurement that
    the report renders per row, so no reader has to trust a spot check.
    """
    target = state_dir.parent / f"{state_dir.name}.prepared"
    if not target.is_dir():
        return 0
    return sum(1 for entry in target.iterdir() if entry.is_file())


def _git_state() -> dict[str, Any]:
    """The tree a decode ran on: ``git rev-parse HEAD`` + a dirty flag.

    Review fix, 2026-08-23. Nothing in W4's artifacts recorded a tree
    identity; the only support for "measured on W3's tip" was wall-clock
    ordering against commit timestamps. Recorded at DECODE time now, and
    rendered from the sidecar, because that is the one moment at which
    the answer is not an inference.
    """
    def _run(*args: str) -> str:
        done = subprocess.run(["git", *args], capture_output=True,
                              text=True, cwd=str(_ROOT))
        return done.stdout.strip() if done.returncode == 0 else ""
    head = _run("rev-parse", "HEAD")
    porcelain = _run("status", "--porcelain")
    return {"git_head": head or "(unavailable)",
            "git_dirty": bool(porcelain)}


def run_holo2_cli(sheet: Sheet, scans: Sequence[tuple[Path, float]],
                  state_dir: Path, out_path: Path, *, workers: int,
                  diag_port: int, timeout: float) -> H2Side:
    """ONE fresh ``--complete`` decode through the operator path.

    ADOPTS a sidecar rather than decoding twice (module docstring). The
    guard is deliberately crude — the sidecar's existence, not a
    comparison of argv — because the only way it can be wrong is if a
    person edited the declared list and kept the old state directory,
    and the sidecar records the argv it ran so the report says which.
    """
    sidecar = state_dir.parent / f"{state_dir.name}.parity.json"
    if sidecar.is_file():
        saved = json.loads(sidecar.read_text(encoding="utf-8"))
        print(f"parity_k: adopting {sidecar} "
              f"(decoded {saved['ran_at']}, {saved['wall_s']:.1f} s) — "
              f"delete it to decode again", file=sys.stderr)
        return H2Side(argv=saved["argv"], state_dir=state_dir,
                      certificates=int(saved["certificates"]),
                      payload_sha=saved["payload_sha"],
                      payload_bytes=saved["payload_bytes"],
                      returncode=int(saved["returncode"]),
                      wall_s=float(saved["wall_s"]),
                      epilogue=tuple(saved["epilogue"]), adopted=True,
                      ran_at=saved["ran_at"],
                      prepared=saved.get("prepared", "unrecorded"),
                      prepared_before=saved.get("prepared_before"),
                      prepared_after=saved.get("prepared_after"),
                      provenance=dict(saved.get("provenance", {})))

    adopted_planes = _adopt_prepared(sheet, state_dir)
    provenance = {**_git_state(), **_dial_state()}
    prepared_before = _prepared_count(state_dir)
    argv: list[str] = [sys.executable, str(_ROOT / "confetti2.py")]
    for path, dpi in scans:
        argv += ["--scan", str(path), "--dpi", str(dpi)]
    argv += ["--format", sheet.format_ref, "--complete",
             "--workers", str(workers), "--pages", str(sheet.pages),
             "--state-dir", str(state_dir), "--output", str(out_path),
             "--diag-port", str(diag_port)]
    ran_at = time.strftime("%Y-%m-%d %H:%M:%S")
    started = time.perf_counter()
    finished = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, cwd=str(_ROOT))
    wall = time.perf_counter() - started
    sys.stderr.write(finished.stdout)
    sys.stderr.write(finished.stderr)
    if not state_dir.is_dir():
        raise SystemExit(
            f"parity_k: holo2 wrote no state for {sheet.label} "
            f"(exit {finished.returncode})")
    payload_sha = _sha256_file(out_path) if out_path.is_file() else None
    payload_bytes = out_path.stat().st_size if out_path.is_file() else None
    side = H2Side(argv=" ".join(argv[1:]), state_dir=state_dir,
                  certificates=_h2_certificate_count(state_dir),
                  payload_sha=payload_sha, payload_bytes=payload_bytes,
                  returncode=finished.returncode, wall_s=wall,
                  epilogue=_epilogue_lines(finished.stdout,
                                           finished.stderr), adopted=False,
                  ran_at=ran_at, prepared=adopted_planes,
                  prepared_before=prepared_before,
                  prepared_after=_prepared_count(state_dir),
                  provenance=provenance)
    sidecar.write_text(json.dumps({
        "argv": side.argv, "certificates": side.certificates,
        "payload_sha": side.payload_sha, "payload_bytes": side.payload_bytes,
        "returncode": side.returncode, "wall_s": side.wall_s,
        "epilogue": list(side.epilogue), "ran_at": side.ran_at,
        "prepared": side.prepared,
        "prepared_before": side.prepared_before,
        "prepared_after": side.prepared_after,
        "provenance": side.provenance,
    }, indent=2) + "\n", encoding="utf-8")
    return side


# --------------------------------------------------------------------
# the row
# --------------------------------------------------------------------


@dataclass
class ParityRow:
    sheet: Sheet
    v1: V1Side
    h2: H2Side
    golden_sha: str | None
    #: W1's instrument, over the same two states. ``None`` when the
    #: differential itself refused (it is not the measurement — the
    #: counts above are — so a refusal is reported, never fatal).
    diff: Any = None
    diff_error: str = ""

    @property
    def delta(self) -> int:
        return self.h2.certificates - self.v1.certificates

    @property
    def v1_zero_wrong(self) -> bool | None:
        return _zero_wrong(self.v1.payload_sha, self.golden_sha)

    @property
    def h2_zero_wrong(self) -> bool | None:
        return _zero_wrong(self.h2.payload_sha, self.golden_sha)


def _zero_wrong(observed: str | None, golden: str | None) -> bool | None:
    """The correctness statement, or ``None`` where there is not one.

    A published payload whose sha equals the golden is the zero-wrong
    proof for EVERY certificate that fed it: the fountain's own envelope
    is sha-gated, so a single wrong tile cannot survive into a matching
    payload. No payload (an arm whose volume cannot close) is not a
    failure and is not a pass — it is the absence of the statement, and
    saying ``False`` there would be a lie about a run that never claimed
    to close.
    """
    if golden is None or observed is None:
        return None
    return observed == golden


def measure(sheet: Sheet, work: Path, *, workers: int, v1_workers: int,
            diag_port: int, timeout: float,
            with_differential: bool = True) -> ParityRow:
    scans = sheet.scans
    golden = sheet.golden_sha
    if sheet.kind == "fixture":
        scans, payload = fixture_scans(sheet, work)
        golden = hashlib.sha256(payload).hexdigest()

    if sheet.v1_state is not None:
        v1 = read_archived_v1(sheet.v1_state)
    else:
        v1 = run_v1_cli(sheet, scans, work, workers=v1_workers,
                        timeout=timeout)

    state_dir = work / f"h2-{sheet.label}"
    h2 = run_holo2_cli(sheet, scans, state_dir,
                       work / f"h2-{sheet.label}.bin", workers=workers,
                       diag_port=diag_port, timeout=timeout)

    row = ParityRow(sheet=sheet, v1=v1, h2=h2, golden_sha=golden)
    if with_differential:
        try:
            row.diff = tile_differential.run(
                v1.state_path, h2.state_dir, sheet.format_ref,
                label=sheet.label)
        except Exception as error:                # noqa: BLE001 - reported
            row.diff_error = f"{type(error).__name__}: {error}"
    return row


# --------------------------------------------------------------------
# the report
# --------------------------------------------------------------------


def _dial_state() -> dict[str, Any]:
    """The dials a decode runs under, read off the TREE — AT DECODE TIME.

    RULING I2's price and RF1's production dial are the two that decide
    what a fresh ``--complete`` run does, and both are code, so both are
    read rather than retyped (measurement doctrine: label every number
    with the flags it was measured under).

    WHEN it is read is the review fix (2026-08-23). This used to be
    called only by the renderer, which then asserted its answer over
    rows decoded hours earlier on a possibly different tree — a reprice
    would have silently relabelled every adopted row. It is now called
    in :func:`run_holo2_cli` before the subprocess and stored in the
    sidecar with ``git rev-parse HEAD``; the renderer prints each row's
    own record and quotes this only as the render-time tree's state.
    """
    revise = inspect.signature(PoseRefineProvider.__init__
                              ).parameters["revise"].default
    return {"COST_REFINE": COST_REFINE,
            "PoseRefineProvider.revise (ctor default)": revise}


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet", action="append", default=[],
                        help="a label from the declared list, or 'all' "
                             f"({', '.join(SHEETS_BY_LABEL)})")
    parser.add_argument("--work", type=Path,
                        default=_ROOT / "scratch/holo2-catchup/real/parity",
                        help="where states, payloads and sidecars live")
    parser.add_argument("--workers", type=int, default=8,
                        help="holo2 --workers (default 8, the H6 shape)")
    parser.add_argument("--v1-workers", type=int, default=4,
                        help="v1 --workers for a LIVE v1 arm "
                             "(execution-only; results are bit-identical)")
    parser.add_argument("--diag-port", type=int, default=8041)
    parser.add_argument("--timeout", type=float, default=36000.0,
                        help="seconds per subprocess decode")
    parser.add_argument("--no-differential", action="store_true",
                        help="skip W1's per-tile differential")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the markdown report here")
    args = parser.parse_args(argv)

    labels = args.sheet or ["all"]
    if "all" in labels:
        chosen = list(SHEETS)
    else:
        unknown = [name for name in labels if name not in SHEETS_BY_LABEL]
        if unknown:
            raise SystemExit(f"parity_k: unknown sheet(s) {unknown}; "
                            f"declared: {sorted(SHEETS_BY_LABEL)}")
        chosen = [SHEETS_BY_LABEL[name] for name in labels]

    args.work.mkdir(parents=True, exist_ok=True)
    rows: list[ParityRow] = []
    for offset, sheet in enumerate(chosen):
        print(f"parity_k: {sheet.label} …", file=sys.stderr)
        rows.append(measure(
            sheet, args.work, workers=args.workers,
            v1_workers=args.v1_workers, diag_port=args.diag_port + offset,
            timeout=args.timeout,
            with_differential=not args.no_differential))

    text = parity_k_report.render_report(
        rows, workers=args.workers, dials=_dial_state(),
        baselines=REFINE_OFF_BASELINE)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
