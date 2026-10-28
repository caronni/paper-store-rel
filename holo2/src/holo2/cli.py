"""holo2 CLI — the composition root, and the pinned operator surface.

The argument set is the user's spec of 2026-08-09 and is pinned by
``holo2/tests/test_cli_surface.py``; changing it is a user decision.

One command (decode is implicit): repeated ``--scan``/``--dpi`` pairs,
``--workers``, ``--diag-port``, ``--state-dir`` (created if missing;
holds the envelope + blob-sidecar store, DESIGN §5.6), ``--output``
(recovered-payload object), ``--complete`` (stop-condition form,
DESIGN §9: a solvable fountain state no longer stops the session, work
exhaustion does), ``--no-close`` (the third point on that one axis, ruled
2026-08-22: the close layer is never entered and the session ends OPEN
with its certificates accumulated), and the printed sheet: ``--format``
plus ``--pages``. Nothing else. **DPI is operator-declared per capture —
no invented defaults.**

**ONE FLAG NAMES THE SHEET** (C5, 2026-08-22, RULINGS G6 — the user:
"yes, the --format syntax looks better, complies with the FORMAT-SPACE
decisions"). ``--format ID`` takes a v2 format id (``c2-k-r0700@53x37``)
or an ``L:`` fossil line (``L:c2-r0700@3392x2368``, the identity of both
hardware-certified K volumes), and it REPLACES ``--coding`` +
``--tiles-y`` + ``--tiles-x``: three arguments that had to agree with
each other became one string that cannot disagree with itself, because
geometry IS the tile matrix and the matrix is in the id (FORMAT-SPACE
§7/§10). No printer and no paper argument, ever — "the receiver measures
pose from the scan and needs none of it" — and a legacy sheet is
nameable again, which it was not between C2 and this package.
``--pages`` stays: a page count is not identity in either tree.

A RESUME NEEDS NO IDENTITY ARGUMENT AT ALL. The state directory holds
the one it was started with, and this CLI reads it first
(``core.Store.peek_identity`` over journal line 1) rather than making an
operator retype a string the state already knows. Given anyway, the
flags must AGREE: a ``--format`` or ``--pages`` that names a different
sheet is refused by name, both values printed, before any record is
interpreted — never a state reinterpreted under an identity it was not
built with (there are no migration decoders).

A RESUME may also name fewer captures than the state holds, down to none
at all (B9): every capture the store knows comes back by record —
footings, regions, lattices — and only work that genuinely needs pixels
declines and sleeps on its attachment key. Starting a session still
needs at least one ``--scan``.

The sheet is OPERATOR-NAMED and that is not a shortcut: the
hardware-certified K volumes on record are ``L:c2-r0700@3392x2368``
(53x37 tiles), a probe-row geometry deliberately absent from v1's
``FORMAT_ROWS``, so a receiver that could only name registry rows could
not read the sheets this project printed.

Both bindings can also arrive as DATA through :func:`main`'s
``format_row``/``providers`` keywords — that is how the oracle fixtures
and the staged-provider rigs drive the same skin. **THE ROW IS THE
GATE** (C5, 2026-08-22): a run that has a resolved row, HOWEVER it was
named — flag, state directory or keyword — composes the real worker
families, and the ``providers`` keyword is for a rig that means to
replace them. Without a row from any of the three, ``main`` refuses
honestly and exits 2.

This module is the only place where solve, format, capture, engine and
diag meet: :func:`open_receiver` puts a lineage (engine, over a state
directory) together with a plane (solve, over the declared captures), and
this is also what writes the recovered payload out.

**The diag endpoint is always on** (user ruling 2026-08-09): every
``main`` run serves status on ``--diag-port``, which selects the port and
nothing else. L12 still binds in the other direction — a port that will
not bind costs one stderr line and the decode proceeds untouched, and the
clock-free guarantee is pinned on :func:`decode` (the library path a
headless caller uses), not on this skin.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from . import capture, core, diag, engine as engine_pkg, solve
# The durability primitive that publishes the recovered object lives in
# core (``publish_once``); the composition root decides WHAT is published
# and catches the refusal, which is the only CLI-shaped half of S2. The
# two cadence constants are named for the same reason they exist: a
# relayed default that repeats the literal is a knob whose ruling never
# reaches the caller that matters.
from .core import (DEFAULT_SNAPSHOT_EVERY, DEFAULT_TRACE_SAMPLE_EVERY,
                   JOURNAL_NAME, CertificateConflict, CommitEngine, Provider,
                   RecordRegistry, Store, StoreError, WorkSource, compose,
                   providers_identity, publish_once)
from .engine import (POLICY_ID, Orchestrator, Plane, RECIPE_V1, Recipe,
                     RunOutcome, SessionContext, SessionIdentity, open_session)
from .format import (FormatRowSpec, ResolvedRef, format_row_for,
                     resolve_format_ref)
from .solve import (PlacementScheduler, RealIngestProvider, VolumeClose,
                    calibration, open_plane, payload, refine)

# RULED 2026-08-15 (M-WS): serial is the measured-fastest configuration
# on the current leaves (real sheet 329 s vs 562-565 s at 8 — the
# stand-in fires are GIL-bound). Default 1 until H4's real kernels
# re-measure the workers curve.
DEFAULT_WORKERS = 1
DEFAULT_DIAG_PORT = 8024
DEFAULT_PAGES = 1

_PROVISIONAL_WARNING = (
    "holo2: receiver status PROVISIONAL — nothing in this tree is "
    "qualified (holo2/docs/DESIGN.md L15).")

EXIT_VERIFIED = 0
EXIT_OPEN = 2
EXIT_REFUSED_OUTPUT = 3
EXIT_TERMINAL = 4


#: The §5.5 statuses a lineage cannot leave. An operator loop that adds
#: scans and reruns until exit 0 must be able to tell "not yet" from
#: "never": EXIT_OPEN is resumable, EXIT_TERMINAL is not.
TERMINAL_STATUSES = frozenset({"integrity_failure", "unsupported"})


@dataclass(frozen=True)
class DecodeRequest:
    """Validated CLI surface, ready for the runtime (H2)."""

    scans: tuple[tuple[Path, float], ...]   # (path, dpi_true) per capture
    workers: int
    diag_port: int
    state_dir: Path
    output: Path
    complete: bool
    #: The printed sheet, as ONE reference (C5, 2026-08-22, RULINGS G6):
    #: a v2 format id or an ``L:`` fossil line. It was ``coding`` +
    #: ``tiles_yx``, which could name a sheet only if the operator kept
    #: three arguments in agreement. ``None`` means the sheet was not
    #: named here — the caller supplies a format row as data, or the
    #: state directory is asked what it holds.
    format_ref: str | None = None
    #: DECLARED, never invented, and ``None`` is the declaration that
    #: none was made: a fresh run then means :data:`DEFAULT_PAGES`, and a
    #: resume reads the page count off the state's own identity. An
    #: ``int`` here is the operator's word and must AGREE with a state
    #: being resumed.
    pages: int | None = None
    #: `--no-close`, ruled 2026-08-22. DEFAULTED and appended LAST because
    #: eleven instruments construct this record directly (the verdicts'
    #: conftest, ``measure/v1_side_by_side.py``, the oracle rigs); a field
    #: without a default would break every one of them.
    no_close: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="confetti2",
        description="holo2 receiver — decode printed format v1 captures.",
    )
    parser.add_argument(
        "--scan", action="append", default=[], metavar="PATH",
        help="capture raster (repeat; pairs with --dpi in order; a resume "
             "may omit captures the state already holds)")
    parser.add_argument(
        "--dpi", action="append", default=[], type=float, metavar="DPI",
        help="operator-declared true DPI of the matching --scan (repeat)")
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help=f"concurrent workers (default {DEFAULT_WORKERS})")
    parser.add_argument(
        "--diag-port", type=int, default=DEFAULT_DIAG_PORT,
        help=f"diag status port (default {DEFAULT_DIAG_PORT})")
    parser.add_argument(
        "--state-dir", type=Path, required=True,
        help="session state directory (created if missing)")
    parser.add_argument(
        "--output", type=Path, required=True,
        help="recovered-payload object name")
    parser.add_argument(
        "--complete", action="store_true",
        help="a solvable fountain state no longer stops the session; "
             "run until no work remains, then close once")
    parser.add_argument(
        "--no-close", action="store_true",
        help="never enter the close layer: no closing record is read, "
             "attempted or written, and the session ends OPEN with its "
             "certificates accumulated. Forfeits close preemption (the "
             "biggest scheduling win there is); close later with a plain "
             "or --complete run. Implies --complete's deferral (giving "
             "both is fine)")
    parser.add_argument(
        "--format", dest="format_ref", metavar="ID",
        help="the printed sheet, as ONE identity: a v2 format id "
             "(c2-k-r0700@53x37) or an L: fossil line "
             "(L:c2-r0700@3392x2368). The tile matrix is in the id, so "
             "there is no geometry, printer or paper argument. Optional "
             "on a resume — the state names its own sheet")
    parser.add_argument(
        "--pages", type=int, default=None, metavar="N",
        help=f"declared page count of the volume (a fresh run without it "
             f"means {DEFAULT_PAGES}; a resume reads the state's own)")
    return parser


def parse_request(argv: list[str]) -> DecodeRequest:
    args = build_parser().parse_args(argv)
    if not args.scan and not _has_state(args.state_dir):
        raise SystemExit(
            "confetti2: at least one --scan is required to START a session "
            f"({args.state_dir} holds no state to resume)")
    if len(args.scan) != len(args.dpi):
        raise SystemExit(
            f"confetti2: {len(args.scan)} --scan but {len(args.dpi)} "
            "--dpi — every scan needs its operator-declared DPI")
    scans = []
    for raw_path, dpi in zip(args.scan, args.dpi):
        path = Path(raw_path)
        if not path.is_file():
            raise SystemExit(f"confetti2: scan not found: {path}")
        if not dpi > 0:
            raise SystemExit(f"confetti2: non-positive DPI {dpi} for {path}")
        scans.append((path, dpi))
    if args.workers < 1:
        raise SystemExit(f"confetti2: --workers must be >= 1, got {args.workers}")
    if args.pages is not None and args.pages < 1:
        raise SystemExit(f"confetti2: --pages must be >= 1, got {args.pages}")
    # THE FORMAT REFERENCE IS NOT RESOLVED HERE, and that is the point of
    # the one flag (C5, 2026-08-22, RULINGS G6). ``--coding`` was checked
    # by construction at this boundary — argparse ``choices`` cannot
    # answer a GRAMMAR — and the row it built was then thrown away and
    # built again at composition. The reference is now resolved where the
    # row is built, in ``main``, so the thing that was checked IS the
    # thing the run uses. What stays here is what this function is for:
    # the arguments that are wrong on their face, whatever sheet they
    # name.
    args.state_dir.mkdir(parents=True, exist_ok=True)
    return DecodeRequest(
        scans=tuple(scans),
        workers=args.workers,
        diag_port=args.diag_port,
        state_dir=args.state_dir,
        output=args.output,
        complete=args.complete,
        format_ref=args.format_ref,
        pages=args.pages,
        no_close=args.no_close,
    )


def _has_state(state_dir: Path) -> bool:
    """Does this directory already hold a session to resume (B9)?

    The one place the CLI cares whether pixels are optional. Starting a
    session with no capture at all is nonsense — there is nothing to
    decode and no lineage to open — but RESUMING one without re-supplying
    the file is exactly what the catalog path is for: footings, regions,
    poses and evidence LLRs are durable, so a resume can carry the decode
    forward and let anything that genuinely needs pixels sleep on the
    attachment key. The check is a file test, not a load: ``Store.open``
    is the authority on whether the state is any good, and it refuses
    loudly a moment later. The JOURNAL is what makes a directory a
    session: it is the authoritative file, and the cache beside it is a
    memo that may be deleted (F-16).
    """
    return (state_dir / JOURNAL_NAME).is_file()


def _resolved(format_ref: str) -> ResolvedRef:
    """What ``--format`` names, by its route — or a clean refusal
    (C5, 2026-08-22, RULINGS G6).

    The resolver is total over both routes (``L:`` byte-matched, else
    the v2 grammar) and raises the failing route's own diagnosis, which
    is the sentence an operator needs: an unregistered pitch class, a
    rung with no mother code, a bare legacy spelling and the ``L:`` form
    it should have had. A traceback out of ``main`` would say the same
    thing worse, so this is the one place it becomes an exit.
    """
    try:
        return resolve_format_ref(format_ref)
    except (KeyError, ValueError) as exc:
        raise SystemExit(f"confetti2: {exc}") from None


def _declared_pages(request: DecodeRequest) -> int:
    """How many pages this run builds its row with — ONE law, both doors.

    C5 review fix (2026-08-22, RULINGS G6). ``--pages`` is optional on a
    resume, and that has to hold whether or not the operator ALSO retyped
    ``--format``: a page count is a property of the STATE, so the branch
    that reads it may not depend on which other flag was given. The first
    cut read the state's page domain only where ``--format`` was absent
    and invented :data:`DEFAULT_PAGES` on the other side, so a correctly
    named multi-page resume was refused — and refused ``(--pages)``, a
    flag that run never passed. A refusal may only name a value the
    operator actually typed; this function is what makes that true.

    The order IS the contract. A declared ``--pages`` is the operator's
    word and is built with, never overruled, so a count that disagrees
    with the state meets :func:`_require_agreement`'s one refusal rather
    than a second copy of it written here. Only an UNDECLARED count is
    read off the state, and only a directory holding no state at all
    falls back to :data:`DEFAULT_PAGES`.
    """
    if request.pages is not None:
        return request.pages
    if not _has_state(request.state_dir):
        return DEFAULT_PAGES
    return len(_peek_or_exit(request.state_dir).page_domain)


def _row_for(request: DecodeRequest) -> FormatRowSpec | None:
    """The printed row this run decodes: from ``--format``, or the state.

    THE RESUME NEEDS NO IDENTITY ARGUMENT (C5, 2026-08-22, RULINGS G6).
    A state directory holds the identity it was started with, so when no
    ``--format`` is given and a session is there to resume, it is READ —
    ``Store.peek_identity`` over journal line 1 — and the row is rebuilt
    from that string alone. That is what the total resolver bought: a
    persisted ``format_row_id`` reconstructs its row, which is also why
    session state needed no schema change (FORMAT-SPACE §10, and the
    e033 §033.5 incident it closes, where a row id meant something only
    if a table in that build still held the row).

    ``None`` is the honest "no sheet was named here": neither flag nor
    state, and :func:`main` refuses with the one line that says so.
    """
    # The page count is settled BEFORE the branch, because it is the same
    # fact on both sides of it (:func:`_declared_pages`).
    pages = _declared_pages(request)
    if request.format_ref is not None:
        resolved = _resolved(request.format_ref)
        # P9's operator courtesy: the CANONICAL spelling is the one that
        # gets PERSISTED, so an operator is told which string their state
        # is about to be named by — and, since FORMAT-SPACE §16 made
        # canonical the explicit form, that is now almost always a
        # different string from the one they typed.  Both are printed:
        # the short spelling they recognize, and the id their state will
        # carry.  An ``L:`` line that matched byte-exactly prints
        # nothing, because the marker rides on ``spec_id`` and the two
        # are then equal.
        if resolved.spec_id != request.format_ref:
            print(f"confetti2: format {resolved.display_id} -> state "
                  f"{resolved.spec_id}", file=sys.stderr)
        try:
            return format_row_for(request.format_ref, pages)
        except (KeyError, ValueError) as exc:
            raise SystemExit(f"confetti2: {exc}") from None
    if not _has_state(request.state_dir):
        return None
    identity = _peek_or_exit(request.state_dir)
    try:
        return format_row_for(identity.format_row_id, pages)
    except (KeyError, ValueError) as exc:
        raise SystemExit(
            f"confetti2: {request.state_dir} names a printed format this "
            f"build cannot resolve: {exc}") from None


def _peek(state_dir: Path) -> SessionIdentity:
    """The identity a state directory was started with (C5, 2026-08-22).

    The registry is composed with an EMPTY page domain deliberately: the
    domain parameterises solve's structural validator, never a family
    name or version, so the manifest this gate compares is the same one
    every run of this build writes — and asking the state what its page
    count is would otherwise need the page count to ask with.

    Raises ``core.StoreError`` on a state this build may not open, which
    is :meth:`Store.peek_identity`'s own gate and not this function's
    judgement. The CLI path takes it through :func:`_peek_or_exit`; a
    library caller gets the exception.
    """
    identity: SessionIdentity = Store.peek_identity(state_dir,
                                                    record_registry())
    return identity


def _peek_or_exit(state_dir: Path) -> SessionIdentity:
    """:func:`_peek` for the CLI path: the store's sentence, as an exit.

    C5 review fix (2026-08-22). Reading the state first made the peek the
    FIRST thing a resume touches, and it runs ``open``'s whole gate — so
    the freshness refusals RULINGS G1 expects operators to meet (a state
    dir from an older schema, a bare legacy id) started arriving as a
    ``StoreError`` traceback at the very argument-checking layer whose
    job is to turn refusals into ``confetti2:`` lines. The store's own
    sentence is kept verbatim; only its delivery changes.

    Two dispositions, one law — the same split :func:`_require_agreement`
    already documents: this wrapper is the CLI's, and every library door
    (``_peek`` itself, :func:`open_receiver`) still raises, because a rig
    holding a bad state directory wants the exception.
    """
    try:
        return _peek(state_dir)
    except StoreError as exc:
        raise SystemExit(f"confetti2: {exc}") from None


def _require_agreement(state_dir: Path, format_row: FormatRowSpec) -> None:
    """A named sheet must be the state's OWN sheet — refused BY NAME
    (C5, 2026-08-22, RULINGS G6).

    ``src/holo/receive/session.py:786-789`` is the model ("receive state
    format {a!r} != requested {b!r}") and the reason is the same: a
    ``--format`` that disagrees with a state file is a refused resume,
    never a reinterpretation. What holo2 adds is the FIELD and both
    values, because ``Store.open`` would refuse this too — by whole-value
    identity compare, without naming what moved (``store.py:305-312``),
    which is the silent-looking break ``engine/session.py:41-56`` warns
    about. Raised as a ``ValueError`` (builtins only, the taxonomy law):
    :func:`main` turns it into an exit, and a library caller composing a
    session over the wrong state gets it as an error rather than as a
    lineage mismatch three layers down.
    """
    if not _has_state(state_dir):
        return
    identity = _peek(state_dir)
    if identity.format_row_id != format_row.row_id:
        raise ValueError(
            f"{state_dir} was started as format {identity.format_row_id!r}; "
            f"this run names {format_row.row_id!r} (--format). holo2 has no "
            "migration decoders: resume it as itself, or decode into a new "
            "state directory.")
    if identity.page_domain != format_row.page_domain:
        # A REMEDY, in the format sibling's shape (C5 review fix): this
        # can now only fire on a page count the operator DECLARED
        # (:func:`_declared_pages` reads an undeclared one off the state),
        # so omitting the flag is always the cure and the state's own
        # number is always the alternative.
        raise ValueError(
            f"{state_dir} was started as a {len(identity.page_domain)}-page "
            f"volume; this run names {format_row.n_pages} (--pages). Omit "
            f"--pages, or declare {len(identity.page_domain)}.")


def record_registry(page_domain: tuple[int, ...] = ()) -> RecordRegistry:
    """The composed durable data model of one run (R3).

    Each package declares the record families it WRITES; this is the only
    place they are put together, exactly like the provider binding below.
    The registry's manifest is the store's schema identity, so what a
    state may hold is decided here and refused at open if it moved.

    ``page_domain`` is the session's declared page hypothesis set (§5.1):
    solve binds it into the structural validator that keeps a committed
    pose inside the domain the lineage declared.
    """
    return compose(core.RECORD_FAMILIES, capture.RECORD_FAMILIES,
                   solve.record_families(page_domain),
                   engine_pkg.RECORD_FAMILIES)


def real_providers(row: FormatRowSpec,
                   scans: Sequence[tuple[Path, float]] = (),
                   ) -> tuple[Provider, ...]:
    """The descriptor binding: INGEST, then calibration, then payload
    (H4 W2, then streaming ingestion, then H5 P1's region ctx family —
    ``solve.calibration.CtxCalibrationProvider``, the CA2 reduce whose
    adopted fits the payload fire applies at assembly).

    Naming the families that decode a printed K sheet together is
    composition, so it lives here (R2, with the ``real_workers`` split):
    ``solve`` publishes the families, the root decides which ones a run
    is made of.

    **Ingest joined the roster with the streaming-ingestion build** and
    it is why this function takes the scans: reading an acquisition is
    WORK now, not session assembly, and the work is named by the
    DECLARED scan — path plus
    operator DPI — which is a session input rather than a derived fact.
    So the provider closes over the request's scan list here, at
    composition, exactly as the payload provider closes over the printed
    row. ``scans=()`` composes a session that can ingest nothing, which
    is the honest binding for a resume driven by durable evidence alone.
    It is FIRST in the tuple because the arbitration order is the binding
    order and because nothing else can produce work until it has run.

    **Placement is not on this roster any more.** It is the pull model's
    scheduling set, admitted from the engine's second work source
    (:func:`real_source`), so the family that used to bind two providers —
    a WORD route that seeds a page from nothing and a CHAIN route that
    consumed pushed hints — binds none: one job does both, choosing at
    fire time between the seeds its neighbourhood offers and the word
    slots under its own pixels.

    **The volume close is not on this roster either** (worklist B12): it
    is the engine's terminal consumer, not a provider, and :func:`decode`
    hands it over on its own channel. Two consequences worth naming,
    since both are visible: the lineage identity's provider list carries
    no close id (the close's POLICY is in the identity anyway, as the
    recipe's close entry and its gate), and the observer's provider row
    lists the queued families plus the source's own id.

    **Refinement joined at H5 P4** (``solve.refine.PoseRefineProvider``,
    the census's RF1): one bounded, certificate-labeled pose revision per
    ELIGIBLE pose. It is last because it is dearest — ``COST_REFINE`` =
    200 puts it above every tier any other family DECLARES, and above
    every ordinary pass at any lane depth (a deep COLD sweep overtakes it
    from rung 3: see ``engine.recipe``) — and because its own
    eligibility gate keeps it silent wherever the reach it would refine
    is already certified. **It is LIVE here since W3** (the user's ruling
    of 2026-08-23): the provider's ``revise`` default carries it, so this
    roster reads the same as it did while the family was dialled off and
    the dial is a ctor flag a measurement arm binds, never a CLI knob.
    """
    return (RealIngestProvider(row, scans),
            calibration.CtxCalibrationProvider(row),
            payload.RealPayloadProvider(row),
            refine.PoseRefineProvider(row))


def real_source(row: FormatRowSpec,
                recipe: Recipe = RECIPE_V1) -> PlacementScheduler:
    """The placement scheduler, as the composition root builds it (H4 W2).

    One source, one family, and the same shape every other binding here
    has: ``solve`` owns the algorithm, the root decides that a run is
    made of it. It is handed to the orchestrator separately from the
    providers because it admits differently — a monotone set with a flag
    per member, not a frontier expanded into descriptors — and the
    engine's ``core.WorkSource`` protocol is where those two shapes meet.

    It takes the RECIPE since H4-LANES stage 1, for one field: which
    rungs of a capture actually place (``Recipe.reading_set``). That is
    policy, it is declared on the recipe's entries, and the entries ARE
    the lineage identity — so composing it here is what makes "this run
    reads the whole ladder" (stage 2's default) or "this run reads the
    finest rung only" (``RECIPE_V1_FINEST``) a durable statement instead
    of a constant somebody would have to remember to look at.
    """
    return PlacementScheduler(row, reading_set=recipe.reading_set)


def open_receiver(request: DecodeRequest, format_row: FormatRowSpec, *,
                  recipe: Recipe = RECIPE_V1,
                  providers: Sequence[Provider] = (),
                  source: WorkSource | None = None,
                  policy_id: str = POLICY_ID,
                  fsync: bool = True,
                  snapshot_every: int = DEFAULT_SNAPSHOT_EVERY,
                  trace_sample_every: int = DEFAULT_TRACE_SAMPLE_EVERY,
                  ) -> SessionContext:
    """Compose one session: a lineage (engine) over a plane (solve).

    The two halves of the dissolved runtime, wired where wiring belongs.
    The plane is built from the store the engine just opened, which is why
    it arrives as a factory: a resumed state may be terminal, and a
    terminal session ingests nothing (§5.5).

    **It opens with no captures of its own (H4 streaming ingestion)**: the plane
    catalogues what the store already holds, attaches the declared scans
    whose records stand, and everything else arrives as ingest work
    inside the run. That is also why this no longer takes the observer —
    ingest commits used to be handed to it here, before the orchestrator
    existed, and they are ordinary scheduled commits now, counted by the
    one ledger that owns them (L12).

    The recipe and the source binding ARE the executable policy, so they
    go into the lineage as data (``providers_identity`` keeps the order,
    which is the arbitration order, and refuses a duplicated provider
    id): resuming under a moved policy is a whole-value mismatch the
    store refuses. The work SOURCE joins that binding by its own id, last
    — it is not a provider and has no place in the arbitration order, but
    it is every bit as much the executable policy, so a run under a
    different placement scheduler is a different lineage.

    **The identity is READ before it is composed** (C5, 2026-08-22,
    RULINGS G6): a state directory that already holds a session is asked
    what sheet it was started as, and a row naming a different one is
    refused here, by name, before any record is interpreted. The store
    would refuse it too, a moment later and without saying which field
    moved; this is the same law stated where the identity is built.
    """
    _require_agreement(request.state_dir, format_row)

    def plane(store: Store, engine: CommitEngine) -> Plane:
        return open_plane(store, engine, format_row, request.scans)

    session = open_session(
        request.state_dir, format_row_id=format_row.row_id,
        page_domain=format_row.page_domain, recipe=recipe,
        providers=providers_identity(providers)
        + ((source.source_id,) if source is not None else ()),
        plane=plane, registry=record_registry(format_row.page_domain),
        policy_id=policy_id, fsync=fsync, no_close=request.no_close,
        snapshot_every=snapshot_every, trace_sample_every=trace_sample_every)
    # THE SKIP IS OPERATOR-VISIBLE, AND HERE IS THE MOMENT (review fix,
    # 2026-08-22). The epilogue speaks after the run and only about what
    # this run did; nothing else would ever say that an existing TERMINAL
    # close was set aside — and in holo2 that is a stronger act than v1's
    # in-memory detach was: the moment one commit lands, the close is
    # SUPERSEDED, and the state directory reads OPEN until someone
    # re-closes it. Said before the work, on stderr, once.
    skipped = session.store.unadmitted_close
    if request.no_close and skipped is not None:
        print(f"confetti2: this state's {skipped.status.value.upper()} close "
              "is SKIPPED (--no-close): it becomes SUPERSEDED as soon as this "
              "run commits, and a later plain or --complete run recomputes it "
              "from every certificate then standing.", file=sys.stderr)
    return session


def decode(request: DecodeRequest, format_row: FormatRowSpec,
           providers: Sequence[Provider], *,
           source: WorkSource | None = None,
           recipe: Recipe = RECIPE_V1,
           policy_id: str | None = None,
           status: diag.StatusProvider | None = None,
           fsync: bool = True,
           snapshot_every: int = DEFAULT_SNAPSHOT_EVERY,
           trace_sample_every: int = DEFAULT_TRACE_SAMPLE_EVERY,
           replay: Sequence[str] | None = None,
           ) -> tuple[RunOutcome, diag.StatusProvider]:
    """Run one session end to end. The API path; ``main`` is its CLI skin.

    ``replay`` is the §10.3 debug/qualification path: a recorded commit
    ordering (``core.journal.read_journal`` on a finished state directory,
    or ``Store.ordering()`` on an open one) the orchestrator follows
    instead of the live queue. It has no CLI surface — the pinned argument
    set is the user's spec, and a replay is an instrument, not an operator
    mode. CRASH RECOVERY needs no flag: a run whose journal is ahead of
    its cache re-earns that tail through the same machinery (F-16).

    The volume close is composed HERE and handed to the orchestrator as
    its terminal consumer (worklist B12). It takes no parameter: there is
    exactly one close in this tree, it is not an operator choice, and a
    knob whose only customer would be an out-of-tree implementor is the
    slack B14 ruled out.
    """
    observer = status if status is not None else diag.StatusProvider()
    work_source = (source if source is not None
                   else real_source(format_row, recipe))
    session = open_receiver(
        request, format_row, recipe=recipe, providers=providers,
        source=work_source, policy_id=policy_id or POLICY_ID,
        fsync=fsync, snapshot_every=snapshot_every,
        trace_sample_every=trace_sample_every)
    # Bind the observer to the plane EXPLICITLY (L12 stays intact — the
    # binding is one-directional and read-only). The observer can also
    # discover it by duck-typing through the orchestrator's snapshot
    # binding, but that path degrades silently when the orchestrator's
    # attribute shape moves; naming it here does not. The PLANE is what
    # the panes read: captures, regions and the printed row are its facts,
    # not the session's (R2).
    observer.bind_plane(session.plane)
    try:
        orchestrator = Orchestrator(session, recipe, providers,
                                    close=VolumeClose(),
                                    source=work_source,
                                    complete=request.complete,
                                    no_close=request.no_close,
                                    status=observer,
                                    workers=1 if replay is not None
                                    else request.workers,
                                    replay=replay)
        outcome = orchestrator.run()
    finally:
        session.close()
    return outcome, observer


def main(argv: list[str] | None = None, *,
         format_row: FormatRowSpec | None = None,
         providers: Sequence[Provider] | None = None,
         recipe: Recipe = RECIPE_V1) -> int:
    request = parse_request(sys.argv[1:] if argv is None else argv)
    print(_PROVISIONAL_WARNING, file=sys.stderr)
    if format_row is None:
        format_row = _row_for(request)
        if format_row is not None:
            # THE AGREEMENT IS CHECKED HERE so that an operator meets it
            # as a line rather than as a traceback: this is the row the
            # arguments named, and the refusal is about the arguments. A
            # row handed in as data (the keyword below, the rigs' door)
            # meets the same law one layer down, where the identity is
            # actually composed — ``open_receiver``, which raises. One
            # statement of the law, two dispositions, each right for its
            # caller.
            # ``StoreError`` joins the catch for the same reason the
            # ``ValueError`` is here (C5 review fix): this call peeks, so
            # a state this build may not open refuses HERE, and an
            # operator meets that as a line too.
            try:
                _require_agreement(request.state_dir, format_row)
            except (StoreError, ValueError) as exc:
                raise SystemExit(f"confetti2: {exc}") from None
            tiles_y, tiles_x = format_row.tiles_yx
            named = ("operator-declared" if request.format_ref is not None
                     else f"read from {request.state_dir}")
            print(f"confetti2: format row {format_row.row_id} "
                  f"({tiles_y}x{tiles_x} tiles, {format_row.n_pages} "
                  f"page(s)), {named}.", file=sys.stderr)
    # THE REAL FAMILIES NEED A ROW, and that is the whole gate (C5,
    # 2026-08-22). It used to read ``and request.coding`` — the flag,
    # not the row — so replacing that flag without moving this would
    # have left every real decode falling through to the honest refusal
    # below (CRITIQUE-missing #20). What composes a worker roster is a
    # RESOLVED ROW in hand, however it was named.
    if providers is None and format_row is not None:
        # F1 (C2, RULINGS G2) MEETS AN OPERATOR HERE: holo2 names and
        # builds every lawful colour format and fails FATALLY at codec
        # instantiation, which is a provider constructor — so a colour
        # ``--format`` dies here, before a state exists or a capture is
        # read. As an exit line, not a traceback: the sheet is real, the
        # refusal is about this build, and the operator needs the
        # sentence rather than the stack.
        try:
            providers = real_providers(format_row, request.scans)
        except ValueError as exc:
            raise SystemExit(f"confetti2: {exc}") from None
    if format_row is None or providers is None:
        print(
            "confetti2: no printed format named — pass --format (or supply "
            "a format row and worker families as data); "
            f"{len(request.scans)} capture(s) validated, "
            f"state directory {request.state_dir} ready.", file=sys.stderr)
        return EXIT_OPEN
    output = request.output
    if output.exists():
        print(f"confetti2: {output} exists; holo2 never overwrites a "
              "recovered payload", file=sys.stderr)
        return EXIT_REFUSED_OUTPUT

    # F-12's baseline, taken at the CLI's own entry: the whole advisory
    # lives in this file, so the stat that seals it is taken here rather
    # than borrowed from the ingest path.
    baseline = {path: _stat_pair(path) for path, _dpi in request.scans}

    observer = diag.StatusProvider()
    # The observer is ALWAYS ON (user ruling 2026-08-09): --diag-port moves
    # the endpoint, it does not decide whether there is one. L12 still
    # binds in the other direction — a port that will not bind is an
    # observer failure and may not touch the run, so it costs one stderr
    # line and nothing else.
    server = diag.serve(request.diag_port, observer)
    if server is None:
        print(f"confetti2: diag endpoint unavailable on port "
              f"{request.diag_port}; the run is unaffected.", file=sys.stderr)
    else:
        print(f"confetti2: diag {server.home}", file=sys.stderr)
    outcome: RunOutcome | None = None
    conflict: CertificateConflict | None = None
    try:
        outcome, _ = decode(request, format_row, providers,
                            recipe=recipe, status=observer)
    except CertificateConflict as exc:
        # A pinned raise at the API layer (a decode is allowed to kill the
        # run over a contradicted certificate); at the CLI it is an exit
        # code and one line, never a traceback at an operator.
        conflict = exc
    finally:
        # The v1 termination pattern: publish the terminal view THROUGH the
        # live endpoint first (status frozen, final frames composed and
        # pinned), then write the disposable artifacts to the
        # <state-dir>.diag SIBLING, and only then release the port. A
        # browser polling during teardown therefore keeps the done pane.
        # No linger and no grace period — v1 had neither.
        final = diag.finalize(observer, request.state_dir, outcome=outcome)
        print(f"confetti2: {final.notice()}", file=sys.stderr)
        if server is not None:
            server.stop()
    # The six-row operator block the status channel already publishes —
    # one formatter, not a second terminal one that says strictly less.
    status = observer.status()
    for row in status.get("rows") or ():
        print(row, file=sys.stderr)
    for line in _source_advisory(request, baseline, status):
        print(line, file=sys.stderr)
    if conflict is not None:
        print(f"confetti2: INTEGRITY FAILURE — {conflict}. This lineage is "
              "terminal and immutable (§5.5); rerunning it with more "
              "captures cannot change that.", file=sys.stderr)
        return EXIT_TERMINAL
    # The two exits of ``decode`` are an outcome or the conflict handled
    # above; there is no third one, and saying so here is what lets the
    # rest of this function read the outcome without a null dance.
    assert outcome is not None
    if outcome.verified:
        assert outcome.payload is not None
        try:
            publish_once(output, outcome.payload)
        except FileExistsError as exc:
            # The pre-flight above passed and the object appeared during
            # the run: the payload is recovered and the state directory
            # holds it, so this is a refused OUTPUT, not a failed decode.
            print(f"confetti2: {exc}", file=sys.stderr)
            return EXIT_REFUSED_OUTPUT
        print(f"confetti2: VERIFIED {len(outcome.payload)} bytes -> {output} "
              f"({outcome.certified} certified tiles, {outcome.commits} "
              "commits). Status remains PROVISIONAL.", file=sys.stderr)
        return EXIT_VERIFIED
    print(_epilogue(request, outcome), file=sys.stderr)
    return (EXIT_TERMINAL if outcome.status in TERMINAL_STATUSES
            else EXIT_OPEN)


def _stat_pair(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_advisory(request: DecodeRequest,
                     baseline: dict[Path, tuple[int, int] | None],
                     status: dict[str, object]) -> list[str]:
    """F-12: did a handed source move under the run? ADVISORY only.

    Correctness is closed by architecture — per-tile CRC and the
    payload envelope's own SHA-256 mean tainted pixels produce honest
    failures, never a wrong VERIFIED — so this touches no status and no
    exit code, and writes nothing durable. It is operator-error service:
    one stat per named source (µs), and the hash recomputed ONLY when
    that stat moved. The ingested identity rides the observer catalog
    ``main`` already reads; a source this run never ingested (a terminal
    resume ingests nothing) has no ingest window and stays silent.

    The catalog is read as a SET since streaming ingestion (H4).
    Captures used to arrive at session assembly, in the order the scans
    were declared, so the pane could be indexed positionally; they now
    arrive as fires land, beside captures the store already knew, so the
    honest question is "did any capture of this run authenticate these
    bytes" — which is what the advisory was always asking.
    """
    panes = status.get("panes")
    ingested = frozenset(
        str(item) for item in
        ((panes.get("captures") or ()) if isinstance(panes, dict) else ()))
    lines: list[str] = []
    for path, _dpi in request.scans:
        before = baseline.get(path)
        if not ingested or before is None:
            continue
        if _stat_pair(path) in (before, None):
            continue
        digest = _sha256_file(path)
        if any(digest.startswith(short) for short in ingested):
            lines.append(f"confetti2: source touched but identical during "
                         f"this run: {path} ({digest[:8]}).")
        else:
            lines.append(
                f"confetti2: SOURCE CHANGED DURING THIS RUN: {path} now "
                f"hashes {digest[:8]}, which none of this run's captures "
                f"({', '.join(sorted(ingested))}) authenticated — the decode "
                "read the pixels it authenticated at ingest, so a recovered "
                "payload stands; this explains dead yield.")
    return lines


def _epilogue(request: DecodeRequest, outcome: RunOutcome) -> str:
    """The honest partial state of an exhausted-but-open session (§9).

    **`--no-close` replaces the fountain line, it does not join it**
    (2026-08-22). The shortfall block below is derived from the LAST
    CONSULT's report, and under `--no-close` every consult is an
    ``observe`` — so a run that never asked the fountain question would
    otherwise print a fountain shortfall, which is exactly the false
    claim the flag exists to forbid. The observation itself stays alive
    and reaches the status view; what is suppressed here is the CLAIM.

    The accumulation line is gated on the session still being OPEN, and
    that is not belt-and-braces: `--no-close` never skips an INTEGRITY
    FAILURE (F-11 — the record is the only durable trace of a write the
    wall refused, not a derivation), so a conflict mid-run commits a
    close under this flag too. "No closing record was written" would be
    a lie on exactly that path.

    The REASON line goes with the fountain line under this flag, for the
    same reason (review fix, 2026-08-22): ``outcome.reason`` is read off
    the last consult's report, and an observe consult over a ready volume
    reports ``deferred`` — which under `--no-close` names a wait that
    does not exist. Nothing is deferred here; the close layer is never
    entered. The accumulation line below is the whole honest answer.
    """
    lines = [
        f"confetti2: session {outcome.status.upper()} after "
        f"{outcome.fires} worker fires / {outcome.commits} commits; "
        f"{outcome.certified} certified tiles.",
    ]
    if outcome.exhausted and outcome.status == "open":
        lines.append(
            "  no worker can contribute on any recipe entry — the session "
            "is exhausted, not finished; it stays OPEN and resumable "
            f"from {request.state_dir} when new captures arrive.")
    if outcome.status in TERMINAL_STATUSES:
        lines.append(
            f"  this lineage is TERMINAL and immutable (§5.5): {request.state_dir} "
            "will report the same status on every rerun, with or without new "
            "captures. Nothing here is resumable.")
    if outcome.certified == 0:
        lines.append(
            "  no work key reached a certificate: nothing on these captures "
            "decoded as this format row. Ingest and segmentation still "
            "succeeded — the diag worker outcomes say whether addressing "
            "refused (a foreign printed format) or decoding did.")
    if outcome.reason and not request.no_close:
        lines.append(f"  reason: {outcome.reason}")
    if request.no_close and outcome.status == "open":
        lines.append(
            f"  close skipped (--no-close): {outcome.certified} certificates "
            "accumulated; no closing record was read, attempted, or written. "
            "Close with a plain or --complete run.")
    elif outcome.close is not None:
        blocks = outcome.close.get("blocks") or ()
        unsolved = tuple(row for row in blocks if not _block_solved(row))
        if unsolved:
            ranked = "shortfall" in unsolved[0]
            lines.append(
                f"  fountain: {len(unsolved)} of {len(blocks)} "
                f"blocks unsolved, {'rank' if ranked else 'symbol'} shortfall "
                f"{sum(_block_shortfall(row) for row in unsolved)}.")
    return "\n".join(lines)


# A close report comes in TWO shapes and the epilogue reads both. A
# decoded one (``solve.close._close_report``) carries rank and ``solved``;
# a COUNTING one (``VolumeClose.counting_report`` — a consult that decided
# nothing yet) carries only ``needed``/``have``, because rank is the
# decoder's and no decoder has run. Reading ``solved`` unconditionally
# raised KeyError, which is a CRASH in the operator's epilogue on a real
# partial sheet: counting rows exist only once K is trusted (48 distinct
# certified counters), and the retired toy spine's open runs never reached
# that floor, so nothing exercised it until H4 W1b put the architecture
# rigs on real sheets.

def _block_solved(row: dict[str, Any]) -> bool:
    if "solved" in row:
        return bool(row["solved"])
    return int(row["have"]) >= int(row["needed"])


def _block_shortfall(row: dict[str, Any]) -> int:
    if "shortfall" in row:
        return int(row["shortfall"])
    return max(0, int(row["needed"]) - int(row["have"]))


__all__ = ["DecodeRequest", "DEFAULT_DIAG_PORT", "DEFAULT_PAGES",
           "DEFAULT_WORKERS", "EXIT_OPEN", "EXIT_REFUSED_OUTPUT",
           "EXIT_TERMINAL", "EXIT_VERIFIED",
           "TERMINAL_STATUSES",
           "build_parser", "decode", "main", "open_receiver",
           "parse_request", "real_providers", "real_source",
           "record_registry"]
