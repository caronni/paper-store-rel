"""Pin the confetti2 CLI surface (workplan H0; user spec 2026-08-09).

H2c added the real path behind that unchanged surface: exit 0 with the
payload written for a verified close, exit 2 for an exhausted-but-open
session, exit 3 rather than overwriting a recovered payload. The exit-0
path needs a real emitted page, so it is gated in
``holo2/measure/test_spine_e2e.py`` (outside this tree, where the generator
may be imported); what is pinned here is the argument surface and the
refusals that need no page.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from holo2 import cli


def _scan_file(tmp_path: Path, name: str = "scan.tif") -> Path:
    path = tmp_path / name
    path.write_bytes(b"not-a-real-raster")
    return path


def _argv(tmp_path: Path, name: str = "a") -> list[str]:
    """One validated invocation, distinct per ``name``.

    Every run gets its own scan, state directory and output object, so two
    invocations in one test never share a lineage or a recovered payload.
    """
    scan = _scan_file(tmp_path, f"scan-{name}.tif")
    return ["--scan", str(scan), "--dpi", "4800",
            "--state-dir", str(tmp_path / f"state-{name}"),
            "--output", str(tmp_path / f"out-{name}.bin")]


def test_defaults(tmp_path: Path) -> None:
    request = cli.parse_request(_argv(tmp_path))
    # RULED 2026-08-15 (M-WS): serial until H4 re-measures the curve.
    assert request.workers == 1
    assert request.diag_port == 8024
    assert request.complete is False
    # `--no-close` (ruled 2026-08-22) is DEFAULTED, on the parser and on
    # the record: instruments build a DecodeRequest directly (the
    # verdicts' conftest, ``measure/v1_side_by_side.py``), and a field
    # without a default breaks every one of them.
    assert request.no_close is False
    assert request.scans[0][1] == 4800.0


def test_the_close_policy_axis_takes_both_flags(tmp_path: Path) -> None:
    """Three close policies, ONE axis — so the pair is legal, not a clash.

    Prevents: `--no-close` arriving as a mutually-exclusive alternative to
    `--complete`. It IMPLIES the deferral (a greedy per-barrier close
    would contradict never-close), which is what makes giving both
    redundant rather than contradictory.
    """
    only = cli.parse_request(_argv(tmp_path, "n") + ["--no-close"])
    assert only.no_close is True and only.complete is False
    both = cli.parse_request(
        _argv(tmp_path, "nc") + ["--no-close", "--complete"])
    assert both.no_close is True and both.complete is True


def test_state_dir_created(tmp_path: Path) -> None:
    state_dir = tmp_path / "nested" / "state"
    argv = _argv(tmp_path)
    argv[argv.index("--state-dir") + 1] = str(state_dir)
    cli.parse_request(argv)
    assert state_dir.is_dir()


def test_scan_dpi_pairing_enforced(tmp_path: Path) -> None:
    scan = _scan_file(tmp_path)
    argv = ["--scan", str(scan), "--scan", str(scan), "--dpi", "4800",
            "--state-dir", str(tmp_path / "s"), "--output", "o"]
    with pytest.raises(SystemExit):
        cli.parse_request(argv)


def test_missing_scan_refused(tmp_path: Path) -> None:
    """A session cannot START without a capture — nothing to decode."""
    argv = ["--state-dir", str(tmp_path / "s"), "--output", "o"]
    with pytest.raises(SystemExit):
        cli.parse_request(argv)


def test_a_resume_may_name_no_capture_at_all(tmp_path: Path) -> None:
    """B9: pixels are an ATTACHMENT to a session, not a precondition.

    Every capture a state holds comes back by record — footings, regions,
    lattices — so a resume that re-supplies nothing still carries the
    decode forward, and only work that needs pixels sleeps on the
    attachment key (the end-to-end proof is
    ``holo2/measure/test_resume_without_pixels_e2e.py``). The JOURNAL here
    — the file that makes a directory a session since F-16 — is written by
    NAME rather than by running one: what this file pins is the argument
    surface, and ``Store.open`` stays the authority on whether the state
    itself is any good.
    """
    state_dir = tmp_path / "resumable"
    state_dir.mkdir()
    (state_dir / "journal").write_text("{}\n", encoding="utf-8")
    request = cli.parse_request(
        ["--state-dir", str(state_dir), "--output", str(tmp_path / "o.bin")])
    assert request.scans == ()


def test_nonexistent_scan_refused(tmp_path: Path) -> None:
    argv = ["--scan", str(tmp_path / "missing.tif"), "--dpi", "4800",
            "--state-dir", str(tmp_path / "s"), "--output", "o"]
    with pytest.raises(SystemExit):
        cli.parse_request(argv)


def test_output_required(tmp_path: Path) -> None:
    scan = _scan_file(tmp_path)
    argv = ["--scan", str(scan), "--dpi", "4800",
            "--state-dir", str(tmp_path / "s")]
    with pytest.raises(SystemExit):
        cli.parse_request(argv)


def test_main_refuses_honestly(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(_argv(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "PROVISIONAL" in err
    assert "no printed format named" in err


def test_a_non_positive_dpi_is_refused(tmp_path: Path) -> None:
    """The 'no invented defaults' law: a DPI must be a real measurement."""
    scan = _scan_file(tmp_path)
    for dpi in ("0", "-4800"):
        with pytest.raises(SystemExit):
            cli.parse_request(["--scan", str(scan), "--dpi", dpi,
                               "--state-dir", str(tmp_path / "s"),
                               "--output", "o"])


def test_a_worker_count_below_one_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.parse_request(_argv(tmp_path) + ["--workers", "0"])


def test_exit_codes_are_named(tmp_path: Path) -> None:
    """An operator loop must tell 'not yet' (2) from 'never' (4)."""
    assert (cli.EXIT_VERIFIED, cli.EXIT_OPEN, cli.EXIT_REFUSED_OUTPUT,
            cli.EXIT_TERMINAL) == (0, 2, 3, 4)
    assert cli.TERMINAL_STATUSES == {"integrity_failure", "unsupported"}


def _stub_decode(monkeypatch: pytest.MonkeyPatch, record: list | None = None,
                 *, outcome=None, raises: BaseException | None = None) -> None:
    """Stand in for the session so the CLI skin can be tested on its own.

    ``main`` needs a format row and a worker family to get past its honest
    refusal, and a real emitted page lives outside this tree (the generator
    may not be imported here — firewall). What is under test is the skin's
    observer wiring, so the decode itself is stubbed; the end-to-end diag
    behaviour is gated in ``holo2/measure/test_spine_e2e.py``.

    ``record`` collects ``("decode", format_row, providers)`` per call, so
    a caller can assert both WHAT reached the decode and WHEN, against a
    stubbed ``serve`` recording into the same list.
    """
    from holo2.engine.orchestrator import RunOutcome

    def fake_decode(request, format_row, providers, **kwargs):
        if record is not None:
            record.append(("decode", format_row, providers))
        if raises is not None:
            raise raises
        return (outcome or RunOutcome(status="open", exhausted=True,
                                      reason="stub"),
                cli.diag.StatusProvider())

    monkeypatch.setattr(cli, "decode", fake_decode)


def test_the_observer_is_always_on(tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """User ruling 2026-08-09: --diag-port moves the endpoint, never gates it."""
    served: list[int] = []
    _stub_decode(monkeypatch)
    monkeypatch.setattr(cli.diag, "serve",
                        lambda port, provider, **kw: served.append(port))

    assert cli.main(_argv(tmp_path, "default"),
                    format_row=object(), providers=()) == cli.EXIT_OPEN
    assert served == [cli.DEFAULT_DIAG_PORT], "no run may go unobserved"

    assert cli.main(_argv(tmp_path, "moved") + ["--diag-port", "9001"],
                    format_row=object(), providers=()) == cli.EXIT_OPEN
    assert served == [cli.DEFAULT_DIAG_PORT, 9001], "the flag only picks a port"


def test_main_serves_diag_before_it_decodes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint is up WHILE the session runs, not after it."""
    order: list = []
    monkeypatch.setattr(cli.diag, "serve",
                        lambda port, provider, **kw: order.append(("serve",)))
    _stub_decode(monkeypatch, order)
    cli.main(_argv(tmp_path, "order"), format_row=object(), providers=())
    assert [entry[0] for entry in order] == ["serve", "decode"]


def test_a_busy_diag_port_does_not_change_the_run(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    """L12 from the other side: an observer that cannot start is inert."""
    import socket

    _stub_decode(monkeypatch)
    # Port 0 = an ephemeral port the OS always has, so the healthy control
    # cannot fail for the very reason under test.
    healthy = cli.main(_argv(tmp_path, "healthy")
                       + ["--diag-port", "0"],
                       format_row=object(), providers=())
    healthy_err = capsys.readouterr().err

    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy_port = blocker.getsockname()[1]
    try:
        busy = cli.main(_argv(tmp_path, "busy")
                        + ["--diag-port", str(busy_port)],
                        format_row=object(), providers=())
    finally:
        blocker.close()
    busy_err = capsys.readouterr().err

    assert busy == healthy == cli.EXIT_OPEN
    assert "diag endpoint unavailable" in busy_err
    assert "diag endpoint unavailable" not in healthy_err
    assert "session OPEN" in busy_err, "the run itself reported normally"


def test_main_never_overwrites_a_recovered_payload(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    output = tmp_path / "payload.bin"
    output.write_bytes(b"an earlier recovery")
    argv = _argv(tmp_path)
    argv[argv.index("--output") + 1] = str(output)
    assert cli.main(argv, format_row=object(), providers=()) == 3
    assert "never overwrites" in capsys.readouterr().err
    assert output.read_bytes() == b"an earlier recovery"


# ------------------------------------------ C5 (RULINGS G6): naming the sheet
# ONE FLAG. ``--format`` takes a v2 format id or an ``L:`` fossil line and
# replaces ``--coding`` + ``--tiles-y`` + ``--tiles-x``: the tile matrix is
# in the id, so three arguments that had to agree became one string that
# cannot disagree with itself. The pins below are the six H3bis ones,
# rewritten to the flag that replaced them, plus what only one flag makes
# expressible — a printed ``L:`` sheet, and a resume that names nothing.


def test_the_printed_sheet_is_named_by_one_reference(tmp_path: Path) -> None:
    """The set of three is GONE: a half-named sheet is unrepresentable.

    Prevents the resurrection of a geometry flag. ``--tiles-y`` was the
    other half of an identity an operator had to keep in agreement with
    ``--coding``; argparse now refuses it as unknown, which is the
    strongest form the old "named as a set" refusal can take.
    """
    with pytest.raises(SystemExit):
        cli.parse_request(_argv(tmp_path) + ["--tiles-y", "53"])
    with pytest.raises(SystemExit):
        cli.parse_request(_argv(tmp_path) + ["--coding", "c2-k-r0700"])


def test_the_reference_reaches_the_request(tmp_path: Path) -> None:
    """The flag is CARRIED, not resolved, by ``parse_request``.

    One resolve, in ``main``, on the row the run actually uses — where
    ``--coding`` was validated by construction here and then thrown away
    and built again at composition.
    """
    request = cli.parse_request(_argv(tmp_path)
                                + ["--format", "c2-k-r0700@53x37"])
    assert request.format_ref == "c2-k-r0700@53x37"
    assert request.pages is None, "undeclared is not the same as 1"
    assert cli.DEFAULT_PAGES == 1


def test_pages_is_declared_never_invented(tmp_path: Path) -> None:
    declared = cli.parse_request(
        _argv(tmp_path) + ["--format", "c2-k-r0550@8x8", "--pages", "3"])
    assert declared.pages == 3
    with pytest.raises(SystemExit):
        cli.parse_request(
            _argv(tmp_path) + ["--format", "c2-k-r0550@8x8", "--pages", "0"])


@pytest.mark.parametrize("format_ref,diagnosis", [
    ("c2-k-r0999@8x8", "r0999"),
    ("c2-r0700@3392x2368", "L:c2-r0700@3392x2368"),
    ("c2-k-r0700@0x8", "must be at least 1x1"),
], ids=["no-such-rung", "bare-legacy-spelling", "empty-grid"])
def test_an_unresolvable_reference_is_refused_with_its_diagnosis(
        tmp_path: Path, capsys: pytest.CaptureFixture,
        format_ref: str, diagnosis: str) -> None:
    """The RESOLVER's own sentence reaches the operator, never a traceback.

    Prevents the two failures the one flag could have introduced: a
    grammar refusal swallowed into "no printed format named" (an
    operator would retype the same string), and a bare LEGACY spelling
    dead-ending — it names a real printed sheet and the refusal says so,
    with the ``L:`` form it should have had (C2, RULINGS G1). The empty
    grid is the third class: lawful grammar, unbuildable row.
    """
    with pytest.raises(SystemExit) as caught:
        cli.main(_argv(tmp_path, "bad") + ["--format", format_ref])
    assert diagnosis in str(caught.value)


def test_a_named_sheet_builds_the_row_and_the_real_families(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    """--format alone is enough: main builds the row AND the real workers."""
    seen: list = []
    _stub_decode(monkeypatch, seen)
    monkeypatch.setattr(cli.diag, "serve", lambda port, provider, **kw: None)
    code = cli.main(_argv(tmp_path, "named")
                    + ["--format", "c2-k-r0700@53x37"])
    assert code == cli.EXIT_OPEN
    _marker, row, providers = seen[0]
    assert row.row_id == "1i300-k-r0700-p100-v1@53x37"
    # FOUR families on the descriptor roster: INGEST (H4 streaming
    # ingestion — reading a declared scan is work now, and it is bound
    # FIRST because nothing else can produce work until it has run),
    # CALIBRATION (H5 P1 — the CA2 region ctx reduce whose adopted fits
    # the payload fire applies at assembly), payload, and REFINE (H5 P4 —
    # RF1's certificate-labeled bounded pose revision, bound LAST because
    # it is the dearest: its entry is born in the re-work band). The
    # volume close is not a provider (B12, handed to the orchestrator on
    # its own channel) and PLACEMENT is not one either — it is a
    # ``core.WorkSource``, composed by ``real_source`` and admitted
    # beside the queue.
    assert [provider.family for provider in providers] == [
        "ingest", "calibration", "payload", "refine"]
    # The ingest provider CLOSES OVER the declared scans (point 1): the
    # roster is a function of the REQUEST, not of the printed row alone.
    assert [path.name for path, _dpi in providers[0].scans] == [
        "scan-named.tif"]
    assert isinstance(cli.real_source(row), cli.PlacementScheduler)
    assert cli.real_source(row).family == "place"
    assert "c2-k-r0700@53x37" in capsys.readouterr().err


def test_a_v2_id_and_an_L_line_build_the_rows_the_resolver_builds(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI adds NOTHING to the identity — and the L: sheet is nameable.

    Prevents an operator surface that builds its own row: what
    ``--format`` reaches is byte-for-byte what ``format_row_for`` gives,
    seed included, so the flag can never mean a different sheet from the
    string. The ``L:`` half is the capability C2 knowingly removed and
    this package restores: ``L:c2-r0700@3392x2368`` is the identity of
    BOTH hardware-certified K volumes (e029 on the M281, e032 on the
    AltaLink), it is keyed by the frozen ``holo/v1/...`` seed the
    hardware printed under, and its v2 twin ``c2-k-r0700@53x37`` seeds
    under ``holo/v2/`` — one physical format, two keystreams, which is
    why the printed sheet must be nameable AS the fossil.
    """
    from holo2.format import format_row_for
    from holo2.format.resolve import resolve_format_ref

    for format_ref in ("c2-k-r0700@53x37", "L:c2-r0700@3392x2368"):
        seen: list = []
        _stub_decode(monkeypatch, seen)
        monkeypatch.setattr(cli.diag, "serve",
                            lambda port, provider, **kw: None)
        assert cli.main(_argv(tmp_path, f"row-{format_ref[:4]}")
                        + ["--format", format_ref]) == cli.EXIT_OPEN
        _marker, row, _providers = seen[0]
        assert row == format_row_for(format_ref, 1)
        assert row.row_id == resolve_format_ref(format_ref).spec_id
    assert format_row_for("L:c2-r0700@3392x2368", 1).seed == (
        b"holo/v1/c2-r0700/3392x2368"), "the printed sheet's frozen seed"


def test_a_non_canonical_spelling_is_normalized_out_loud(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    """P9's operator courtesy, carried from ``src/holo`` (cli.py:442-443).

    Only canonical form is ever serialized (FORMAT-SPACE §6), so the
    string an operator typed may not be the string their state is about
    to be named by. Saying which one it is, once, on stderr, is what
    keeps that bijection from being a surprise on the next resume.
    Prevents a silent rename: the run proceeds — a lawful spelling is
    lawful — and the echo is the whole difference.
    """
    seen: list = []
    _stub_decode(monkeypatch, seen)
    monkeypatch.setattr(cli.diag, "serve", lambda port, provider, **kw: None)
    assert cli.main(_argv(tmp_path, "norm")
                    + ["--format", "2i600-k-r0700@53x37"]) == cli.EXIT_OPEN
    err = capsys.readouterr().err
    assert ("format c2-k-r0700@53x37 -> state "
            "1i300-k-r0700-p100-v1@53x37") in err
    assert seen[0][1].row_id == "1i300-k-r0700-p100-v1@53x37"


def _started(state_dir: Path, format_ref: str, pages: int = 1):
    """A state directory that HOLDS a session, and the row it holds.

    Created through the store directly: what these pins are about is the
    identity in journal line 1, and a real decode would spend a page
    render and a full run to write the same line.
    """
    from holo2.core import Store
    from holo2.engine import POLICY_ID, RECIPE_V1, SessionIdentity
    from holo2.format import format_row_for

    row = format_row_for(format_ref, pages)
    Store.create(state_dir, SessionIdentity(
        format_row_id=row.row_id, receiver_policy_id=POLICY_ID,
        recipe_entries=RECIPE_V1.entries, providers=(),
        page_domain=row.page_domain), cli.record_registry(row.page_domain),
    ).close()
    return row


def test_the_manifest_does_not_depend_on_the_page_domain() -> None:
    """What makes reading a state's identity possible at all (C5).

    ``Store.peek_identity`` gates the starting point against a RECORD
    REGISTRY, and the CLI has to compose one before it knows the page
    count — which is the very thing it is asking the state for. It
    composes at the empty domain, and that is only sound because the
    domain parameterises solve's structural VALIDATOR and never a family
    name or version (``solve.families.record_families``).

    The fork this prevents is precise and silent: give any family a
    domain-dependent name or version, and every multi-page resume starts
    refusing with a manifest mismatch that names families the state has
    and this build "does not", while single-page states keep working.
    """
    assert cli.record_registry().manifest() == cli.record_registry(
        (0, 1, 2)).manifest()


def test_a_resume_needs_no_identity_argument(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    """C5 (RULINGS G6): the state names its own sheet, and is asked.

    Prevents the fork where a persisted ``format_row_id`` is decoration:
    before this, resuming meant retyping the identity, and a retyped
    identity is one an operator can get wrong — which is the e033 §033.5
    shape from the other side. The row here is rebuilt from the string
    alone (the total resolver, FORMAT-SPACE §10), which is also why
    session state needed no schema change.
    """
    state_dir = tmp_path / "resume"
    row = _started(state_dir, "c3-k-r0550@8x8")
    seen: list = []
    _stub_decode(monkeypatch, seen)
    monkeypatch.setattr(cli.diag, "serve", lambda port, provider, **kw: None)
    assert cli.main(["--state-dir", str(state_dir),
                     "--output", str(tmp_path / "out.bin")]) == cli.EXIT_OPEN
    _marker, resumed, providers = seen[0]
    assert resumed == row
    assert [provider.family for provider in providers] == [
        "ingest", "calibration", "payload", "refine"]
    assert f"read from {state_dir}" in capsys.readouterr().err


def test_a_multipage_resume_that_retypes_the_format_needs_no_pages(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--pages`` is optional on a resume that ALSO names ``--format``.

    C5 review fix (2026-08-22, RULINGS G6). The fork this prevents was
    live: the page count was read off the state only where ``--format``
    was absent and invented as :data:`cli.DEFAULT_PAGES` on the other
    branch, so an operator who correctly retyped the identity of a
    3-page volume — exactly the operator the module docstring invites,
    since a given flag must AGREE — was refused, and refused
    ``(--pages)``, a flag that run never passed. Two branches reading
    the same fact from different places is the shape; this pins the one
    law (``cli._declared_pages``) by resuming a MULTI-page state with
    the right ``--format`` and nothing else.
    """
    state_dir = tmp_path / "multipage"
    row = _started(state_dir, "c3-k-r0550@8x8", pages=3)
    seen: list = []
    _stub_decode(monkeypatch, seen)
    monkeypatch.setattr(cli.diag, "serve", lambda port, provider, **kw: None)
    assert cli.main(["--state-dir", str(state_dir),
                     "--output", str(tmp_path / "out.bin"),
                     "--format", "c3-k-r0550@8x8"]) == cli.EXIT_OPEN
    _marker, resumed, _providers = seen[0]
    assert resumed == row
    assert resumed.n_pages == 3, "the state's own page domain, not a default"


def test_a_state_this_build_cannot_open_refuses_as_a_line(
        tmp_path: Path) -> None:
    """The peek's refusal is an exit line, never a traceback.

    C5 review fix (2026-08-22). Reading the state first made the peek the
    FIRST thing a resume touches, and it deliberately runs ``open``'s
    whole gate — so the freshness refusals RULINGS G1 expects operators
    to meet (an older schema version, a bare legacy id) began arriving as
    a ``core.StoreError`` out of ARGUMENT CHECKING. This pins the fork
    where a new refusal site is added and left undressed: the store's own
    sentence must survive, wearing the ``confetti2:`` prefix every other
    refusal in this file wears. Both resume shapes peek, so both are
    named here.
    """
    state_dir = tmp_path / "stale"
    _started(state_dir, "c3-k-r0550@8x8")
    journal = state_dir / cli.JOURNAL_NAME
    lines = journal.read_bytes().split(b"\n")
    header = json.loads(lines[0])
    header["schema_version"] = header["schema_version"] - 1
    lines[0] = json.dumps(header).encode()
    journal.write_bytes(b"\n".join(lines))
    for flags in ([], ["--format", "c3-k-r0550@8x8"]):
        with pytest.raises(SystemExit) as caught:
            cli.main(["--state-dir", str(state_dir),
                      "--output", str(tmp_path / "out.bin")] + flags)
        message = str(caught.value)
        assert message.startswith("confetti2: ")
        assert "no migration decoders" in message


@pytest.mark.parametrize("flags,named", [
    (["--format", "c2-k-r0700@53x37"],
     ("1i200-k-r0550-p100-v1@8x8", "1i300-k-r0700-p100-v1@53x37",
      "--format")),
    (["--pages", "3"], ("1-page", "3 (--pages)")),
], ids=["wrong-format", "wrong-pages"])
def test_an_argument_that_disagrees_with_the_state_refuses_by_name(
        tmp_path: Path, flags: list, named: tuple) -> None:
    """Refused BY NAME — which field, and both values (RULINGS G6).

    ``src/holo/receive/session.py:786-789`` is the model: a ``--format``
    that disagrees with a state file is a refused resume, never a
    reinterpretation. What is pinned here is the NAMING. ``Store.open``
    refuses this too, one layer down, by whole-value identity compare —
    and its message does not say which field moved
    (``core/store.py:305-312``), which reads like a bug rather than like
    an operator error. This fires first, before any record is
    interpreted.
    """
    state_dir = tmp_path / "disagree"
    _started(state_dir, "c3-k-r0550@8x8")
    with pytest.raises(SystemExit) as caught:
        cli.main(["--state-dir", str(state_dir),
                  "--output", str(tmp_path / "out.bin")] + flags)
    message = str(caught.value)
    for value in named:              # the field, and BOTH values
        assert value in message
    assert str(state_dir) in message


def test_composing_a_decode_of_a_colour_row_is_fatal(
        tmp_path: Path) -> None:
    """F1 at the COMPOSITION, which is where an operator would meet it.

    RULINGS G2 (2026-08-22): holo2 names and builds every lawful colour
    format and fails FATALLY when a colour codec is instantiated.  The
    row here is real — sheet I's v2 twin, three streams, pooled outer
    code — and every family the composition root binds asks for the K
    tile-chain view in its constructor, so the run dies before a single
    fire is dispatched, no state is created and no capture is read.

    The fork this prevents is the ``-x1`` dust bug one level up: a
    colour row that reached the K chain would be a three-stream sheet
    read as one stream of the wrong width, silently, and the first sign
    would be certificates that never come.  Pinned at the composition
    rather than only at ``tile_format_for`` because "before any work" is
    the part that matters — a refusal deep in a run has already spent an
    operator's afternoon.
    """
    from holo2.format.resolve import format_row_for

    row = format_row_for("c2-cmy8-r0700@53x37", 1)
    assert row.stream_ids == ("C", "M", "Y")      # a real colour row...
    with pytest.raises(ValueError, match="colour codecs arrive with the "
                                         "colour port"):
        cli.real_source(row)
    with pytest.raises(ValueError, match="holo2 cannot decode cmy8"):
        cli.real_providers(row, ())


def test_a_colour_format_refuses_at_the_operator_surface(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """The same F1, reached the way an operator reaches it (C5).

    ``--format`` can NAME a colour sheet — every lawful colour identity
    builds a row (RULINGS G2) — so the fatal refusal is now something a
    typed command produces, and it must arrive as a message and a
    non-zero exit rather than as a traceback out of ``main``. Prevents
    the shape where an operator sees a stack and concludes holo2 is
    broken, when the honest answer is that the colour codecs arrive with
    the colour port.
    """
    with pytest.raises(SystemExit) as caught:
        cli.main(_argv(tmp_path, "colour")
                 + ["--format", "c2-cmy8-r0700@53x37"])
    assert caught.value.code not in (0, None), "a refusal is never exit 0"
    assert "holo2 cannot decode cmy8" in str(caught.value)


def test_the_diag_home_url_is_printed(tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture) -> None:
    """An operator is told where to watch the decode."""
    _stub_decode(monkeypatch)
    assert cli.main(_argv(tmp_path, "home") + ["--diag-port", "0"],
                    format_row=object(), providers=()) == cli.EXIT_OPEN
    err = capsys.readouterr().err
    assert "confetti2: diag http://127.0.0.1:" in err


# ------------------------------------------------------ payload output
# R2 moved write_payload out of the dissolved runtime; the elegance wave
# moved the durability primitive itself into ``core.publish``, where the
# store's and the sidecar's atomic writes already live. S2 is pinned
# there (``tests/core/test_publish.py``). What stays CLI-shaped is the
# DECISION — which object is published, and what a refusal exits with,
# which is what the exit-code tests below cover.


def test_a_terminal_outcome_exits_four_and_says_it_is_not_resumable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    """§5.5: 'add scans and rerun until exit 0' must not spin forever."""
    from holo2.engine.orchestrator import RunOutcome

    _stub_decode(monkeypatch, outcome=RunOutcome(
        status="integrity_failure", reason="a contradicted certificate"))
    monkeypatch.setattr(cli.diag, "serve", lambda port, provider, **kw: None)
    assert cli.main(_argv(tmp_path, "terminal"),
                    format_row=object(), providers=()) == cli.EXIT_TERMINAL
    err = capsys.readouterr().err
    assert "TERMINAL and immutable" in err
    assert "Nothing here is resumable" in err
    assert "stays OPEN and resumable" not in err


def test_a_certificate_conflict_is_an_exit_code_not_a_traceback(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    from holo2.core import CertificateConflict

    _stub_decode(monkeypatch,
                 raises=CertificateConflict("tile 0/1/2/K contradicted"))
    monkeypatch.setattr(cli.diag, "serve", lambda port, provider, **kw: None)
    assert cli.main(_argv(tmp_path, "conflict"),
                    format_row=object(), providers=()) == cli.EXIT_TERMINAL
    assert "INTEGRITY FAILURE" in capsys.readouterr().err


# --------------------------------------- the resumed-VERIFIED re-check (F-13)
# A resumed terminal session runs no work: the payload it hands back was
# read out of a state directory, which is a CACHE. The blob path checks
# the bytes against their content address; only the durable CloseRecord
# says which volume this lineage closed on, so the composition root
# compares one hash of one payload at the one moment it matters.


class _FakeSession:
    """Just the one lifecycle question the re-check asks."""

    def __init__(self, record: object) -> None:
        self._record = record

    def close_record(self) -> object:
        return self._record


def _resumed(payload: bytes) -> "object":
    from holo2.engine.orchestrator import RunOutcome

    return RunOutcome(status="verified", payload=payload,
                      resumed_terminal=True)


# ------------------------------------------- the closure advisory (F-12)
# Correctness is closed by architecture (per-tile CRC + the payload's own
# SHA), so this is operator-error service: never a status, never an exit
# code, never durable state. What is pinned is the three cases.


class _FakeObserver:
    """Just the observer surface ``main`` reads: rows, and the catalog."""

    def __init__(self, captures: tuple[str, ...]) -> None:
        self._captures = captures

    def bind_plane(self, ctx: object) -> bool:
        return True

    def status(self) -> dict:
        return {"rows": [], "panes": {"captures": list(self._captures)}}


class _FakeFinal:
    def notice(self) -> str:
        return "no diag artifacts"


def _run_with_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                       name: str, mutate) -> int:
    """One stubbed run whose 'decode' mutates the source under it."""
    import hashlib

    argv = _argv(tmp_path, name)
    scan = Path(argv[argv.index("--scan") + 1])
    ingested = hashlib.sha256(scan.read_bytes()).hexdigest()[:12]

    from holo2.engine.orchestrator import RunOutcome

    def fake_decode(request, format_row, providers, **kwargs):
        mutate(scan)
        return (RunOutcome(status="open", exhausted=True, reason="stub"),
                cli.diag.StatusProvider())

    monkeypatch.setattr(cli, "decode", fake_decode)
    monkeypatch.setattr(cli.diag, "serve", lambda port, provider, **kw: None)
    monkeypatch.setattr(cli.diag, "StatusProvider",
                        lambda: _FakeObserver((ingested,)))
    monkeypatch.setattr(cli.diag, "finalize",
                        lambda provider, state_dir, **kw: _FakeFinal())
    return cli.main(argv, format_row=object(), providers=())


def test_an_untouched_source_says_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    code = _run_with_mutation(tmp_path, monkeypatch, "quiet", lambda path: None)
    err = capsys.readouterr().err
    assert code == cli.EXIT_OPEN
    assert "touched but identical" not in err
    assert "SOURCE CHANGED" not in err


def test_a_touched_but_identical_source_is_named_as_such(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    """A utime bump is not a change: the stat moved, the bytes did not."""
    def bump(path: Path) -> None:
        stat = path.stat()
        import os
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10 ** 9))

    code = _run_with_mutation(tmp_path, monkeypatch, "touched", bump)
    err = capsys.readouterr().err
    assert code == cli.EXIT_OPEN
    assert "source touched but identical during this run" in err
    assert "SOURCE CHANGED" not in err


def test_a_changed_source_is_an_advisory_not_a_status(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    """The run keeps the exit code it earned; the operator is told why."""
    import hashlib

    changed = b"a DIFFERENT raster entirely"
    code = _run_with_mutation(tmp_path, monkeypatch, "changed",
                              lambda path: path.write_bytes(changed))
    err = capsys.readouterr().err
    assert code == cli.EXIT_OPEN, "an advisory never moves the exit code"
    assert "SOURCE CHANGED DURING THIS RUN" in err
    assert hashlib.sha256(changed).hexdigest()[:8] in err
    assert hashlib.sha256(b"not-a-real-raster").hexdigest()[:8] in err






# ------------------------------------------------- the epilogue's two shapes

def _outcome(close: dict):
    """A minimal RunOutcome carrying one close report (the epilogue's input)."""
    from holo2.engine.orchestrator import RunOutcome

    return RunOutcome(status="open", certified=64, exhausted=True,
                      close=close)


@pytest.mark.parametrize("blocks,expected", [
    # The DECODED shape: rank is the decoder's, and ``solved`` is its word.
    ([{"stream": None, "block": 0, "needed": 43, "have": 43, "rank": 41,
       "solved": False, "shortfall": 2}], "rank shortfall 2"),
    # The COUNTING shape (``VolumeClose.counting_report``): no decoder has
    # run, so there is no rank and no ``solved`` — only how many symbols a
    # block still wants. Reading ``solved`` here used to raise KeyError and
    # crash the operator's epilogue on a real partial sheet (H4 W1b).
    ([{"stream": None, "block": 0, "needed": 43, "have": 40}],
     "symbol shortfall 3"),
])
def test_the_epilogue_reads_both_close_report_shapes(
        tmp_path: Path, blocks: list, expected: str) -> None:
    request = cli.parse_request(_argv(tmp_path))
    text = cli._epilogue(request, _outcome(
        {"status": "open", "k_total": 43, "blocks": blocks}))
    assert f"1 of 1 blocks unsolved, {expected}." in text


def test_the_epilogue_stays_quiet_when_every_block_is_full(
        tmp_path: Path) -> None:
    request = cli.parse_request(_argv(tmp_path))
    text = cli._epilogue(request, _outcome({
        "status": "open", "k_total": 43,
        "blocks": [{"stream": None, "block": 0, "needed": 43, "have": 43}]}))
    assert "blocks unsolved" not in text


def test_a_no_close_run_reports_accumulation_not_a_shortfall(
        tmp_path: Path) -> None:
    """Prevents the FALSE CLOSE-SHORTFALL claim (2026-08-22).

    Under `--no-close` both consult sites run in ``observe``, and an
    observe consult's counting report carries per-block ``needed``/
    ``have`` rows — exactly what the shortfall block above renders. So a
    run that never asked the fountain question would otherwise print a
    fountain shortfall, which is the one thing this flag exists to
    forbid. The observation stays live on the status view; the CLAIM is
    what is replaced, by the accumulation line.
    """
    request = cli.parse_request(_argv(tmp_path) + ["--no-close"])
    text = cli._epilogue(request, _outcome({
        "status": "open", "reason": "deferred", "k_total": 43,
        "blocks": [{"stream": None, "block": 0, "needed": 43, "have": 40}]}))
    assert "blocks unsolved" not in text and "shortfall" not in text
    assert ("close skipped (--no-close): 64 certificates accumulated; no "
            "closing record was read, attempted, or written.") in text
    # The REASON line goes the same way, and for the same reason (review
    # fix, 2026-08-22): it is read off that same consult, where an
    # observe over a ready volume reports ``deferred`` — naming a wait
    # that does not exist here. Prevents two epilogue lines that disagree.
    assert "reason:" not in text


def test_an_integrity_failure_under_no_close_never_claims_no_record(
        tmp_path: Path) -> None:
    """Prevents a LIE on the one path where --no-close does write a close.

    An integrity failure is never skipped (F-11: the record is the only
    durable trace of a write the wall refused, not a derivation), so a
    conflict mid-run commits a CloseRecord under this flag too. The
    accumulation line is therefore gated on the session still being OPEN.
    """
    from holo2.engine.orchestrator import RunOutcome

    request = cli.parse_request(_argv(tmp_path) + ["--no-close"])
    text = cli._epilogue(request, RunOutcome(
        status="integrity_failure", certified=64, exhausted=False,
        reason="tile 0/1/2/K: certified bits differ"))
    assert "close skipped" not in text
    assert "TERMINAL and immutable" in text


def test_a_no_close_run_exits_open(tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture) -> None:
    """EXIT_OPEN (2), the resumable code — never 0 and never TERMINAL.

    Prevents: a skipped close reported as a failed recovery. The run
    accumulated and stayed OPEN, which is exactly what "not yet, come
    back with more captures" means to an operator loop.
    """
    argv = _argv(tmp_path, "exit") + ["--no-close"]

    from holo2.engine.orchestrator import RunOutcome

    def fake_decode(request, format_row, providers, **kwargs):
        assert request.no_close is True, "the flag reaches the runtime"
        return (RunOutcome(status="open", certified=7, exhausted=True),
                cli.diag.StatusProvider())

    monkeypatch.setattr(cli, "decode", fake_decode)
    monkeypatch.setattr(cli.diag, "serve", lambda port, provider, **kw: None)
    monkeypatch.setattr(cli.diag, "StatusProvider", lambda: _FakeObserver(()))
    monkeypatch.setattr(cli.diag, "finalize",
                        lambda provider, state_dir, **kw: _FakeFinal())
    code = cli.main(argv, format_row=object(), providers=())
    assert code == cli.EXIT_OPEN
    assert "close skipped (--no-close): 7 certificates" in capsys.readouterr().err
