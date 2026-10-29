from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from holo.receiver import cli, data, engine
from holo.receiver.format import identity
from holo.receiver.tests import _h3_support

PAYLOAD = b"holo3-cli-payload"
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()

FOSSIL_REF = "L:c2-r0700@3392x2368"
#: The schedule verb prints a header line off the row alone: a small
#: declared identity carries it, no fossil needed.
SMALL_REF = "c3-k-r0550@10x10"
CODING_ID = "c2-r0700"
PRINTER_ID = "hp-m281-ink"

EXIT_VERIFIED = 0
EXIT_ERROR = 1
EXIT_NOT_RECOVERED = 2

DESCRIPTOR_NAMES = tuple(
    descriptor.name for descriptor in engine.DESCRIPTORS)


class _Recorder:

    def __init__(self, status: str = "verified") -> None:
        self.status = status
        self.requests: list[engine.DecodeRequest] = []

    def __call__(self, request: engine.DecodeRequest,
                 events: list | None = None) -> data.RunResult:
        self.requests.append(request)
        payload = PAYLOAD if self.status == "verified" else None
        return data.RunResult(
            status=self.status, payload=payload,
            payload_sha256=PAYLOAD_SHA if payload is not None else None,
            certified=7 if payload is not None else 3,
            plugin_rows=(data.PluginRow("tiles.scan", 4, 0.5, 4, 0, 0),))

    @property
    def only(self) -> engine.DecodeRequest:
        assert len(self.requests) == 1, self.requests
        return self.requests[0]


@pytest.fixture
def scan(tmp_path: Path) -> Path:
    path = tmp_path / "scan.tiff"
    path.write_bytes(b"not-a-real-tiff")
    return path


@pytest.fixture
def decoder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(engine, "decode", recorder)
    return recorder


def _argv(scan: Path, out: Path, tmp_path: Path,
          *extra: str) -> list[str]:
    return ["decode", str(scan), "--dpi", "1200", "--format", FOSSIL_REF,
            "--out", str(out), "--run-dir", str(tmp_path / "run"), *extra]


def test_a_verified_run_exits_zero_and_writes_the_payload_atomically(
        scan, tmp_path, decoder, capsys):
    out = tmp_path / "payload.bin"
    assert cli.main(_argv(scan, out, tmp_path)) == EXIT_VERIFIED
    assert out.read_bytes() == PAYLOAD
    captured = capsys.readouterr()
    assert (f"VERIFIED {len(PAYLOAD)} bytes sha256 {PAYLOAD_SHA}"
            in captured.out)
    assert not list(tmp_path.glob(".payload.bin.*.tmp"))


def test_an_open_run_exits_two_and_publishes_nothing(
        scan, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(engine, "decode", _Recorder(status="open"))
    out = tmp_path / "payload.bin"
    assert cli.main(_argv(scan, out, tmp_path)) == EXIT_NOT_RECOVERED
    assert not out.exists()
    assert "NOT RECOVERED — status open" in capsys.readouterr().err


def test_an_integrity_error_exits_one_and_publishes_nothing(
        scan, tmp_path, monkeypatch, capsys):
    def raising(request: object, events: list | None = None) -> object:
        raise data.IntegrityError("conflicting certificates at (0, 0, 0, "
                                  "'main')")

    monkeypatch.setattr(engine, "decode", raising)
    out = tmp_path / "payload.bin"
    assert cli.main(_argv(scan, out, tmp_path)) == EXIT_ERROR
    assert not out.exists()
    assert "holo3: integrity error:" in capsys.readouterr().err


REFUSALS = (
    ("one --dpi per scan",
     ["exactly one --dpi per scan: 1 scans, 0 --dpi values"],
     lambda scan, out, run: ["decode", str(scan), "--format", FOSSIL_REF,
                             "--out", str(out), "--run-dir", str(run)]),
    # `--dpi-force` is counted as a --dpi: one ordered declaration
    ("one --dpi per scan, forced values counted",
     ["exactly one --dpi per scan: 3 scans, 2 --dpi values"],
     lambda scan, out, run: ["decode", str(scan), str(scan), str(scan),
                             "--dpi", "1200", "--dpi-force", "2400",
                             "--format", FOSSIL_REF, "--out", str(out),
                             "--run-dir", str(run)]),
    ("non-positive dpi",
     ["declared --dpi 0.0 for", "must be finite and positive"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "0", "--format",
                             FOSSIL_REF, "--out", str(out), "--run-dir",
                             str(run)]),
    ("non-finite dpi",
     ["declared --dpi nan for", "must be finite and positive"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "nan",
                             "--format", FOSSIL_REF, "--out", str(out),
                             "--run-dir", str(run)]),
    ("both identity routes",
     ["--format and --coding/--printer are exclusive routes"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "1200",
                             "--format", FOSSIL_REF, "--coding", CODING_ID,
                             "--printer", PRINTER_ID, "--out", str(out),
                             "--run-dir", str(run)]),
    ("neither identity route",
     ["format identity required: --format REF, or both --coding ID and "
      "--printer ID"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "1200", "--out",
                             str(out), "--run-dir", str(run)]),
    ("coding without printer",
     ["format identity required"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "1200",
                             "--coding", CODING_ID, "--out", str(out),
                             "--run-dir", str(run)]),
    ("unknown printer",
     ["unknown --coding/--printer identity", "'nope'"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "1200",
                             "--coding", CODING_ID, "--printer", "nope",
                             "--out", str(out), "--run-dir", str(run)]),
    ("workers below one",
     ["--workers 0 must be >= 1"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "1200",
                             "--format", FOSSIL_REF, "--workers", "0",
                             "--out", str(out), "--run-dir", str(run)]),
    ("max-pages below one",
     ["--max-pages 0 must be >= 1"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "1200",
                             "--format", FOSSIL_REF, "--max-pages", "0",
                             "--out", str(out), "--run-dir", str(run)]),
    ("max-pages exceeds possible",
     ["--max-pages 134 exceeds 133 possible"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "1200",
                             "--format", FOSSIL_REF, "--max-pages", "134",
                             "--out", str(out), "--run-dir", str(run)]),
    ("max-pages exceeds 7x7 possible",
     ["--max-pages 5350 exceeds 5349 possible"],
     lambda scan, out, run: ["decode", str(scan), "--dpi", "1200",
                             "--format", "c3-k-r0550@7x7", "--max-pages",
                             "5350", "--out", str(out),
                             "--run-dir", str(run)]),
)


@pytest.mark.parametrize("label,fragments,build",
                         REFUSALS, ids=[row[0] for row in REFUSALS])
def test_the_decode_surface_refuses_with_its_exact_reason(
        label, fragments, build, scan, tmp_path, decoder, capsys):
    out = tmp_path / "payload.bin"
    assert cli.main(build(scan, out, tmp_path / "run")) == EXIT_ERROR
    stderr = capsys.readouterr().err
    for fragment in fragments:
        assert fragment in stderr, stderr
    assert not out.exists()
    assert decoder.requests == []


def test_an_existing_out_file_is_never_overwritten(
        scan, tmp_path, decoder, capsys):
    out = tmp_path / "payload.bin"
    out.write_bytes(b"standing")
    assert cli.main(_argv(scan, out, tmp_path)) == EXIT_ERROR
    assert out.read_bytes() == b"standing"
    assert f"refusing to overwrite existing --out {out}" in (
        capsys.readouterr().err)
    assert decoder.requests == []


def test_an_unknown_format_refuses_before_any_scan_is_opened(
        scan, tmp_path, capsys):
    out = tmp_path / "payload.bin"
    argv = ["decode", str(scan), "--dpi", "1200", "--format", "L:nope",
            "--out", str(out), "--run-dir", str(tmp_path / "run")]
    assert cli.main(argv) == EXIT_ERROR
    stderr = capsys.readouterr().err
    assert "unknown fossil id 'nope'" in stderr
    assert not out.exists()
    assert not (tmp_path / "run").exists()


def test_a_missing_required_argument_is_an_argparse_refusal(scan, tmp_path):
    with pytest.raises(SystemExit) as raised:
        cli.main(["decode", str(scan), "--dpi", "1200", "--format",
                  FOSSIL_REF])
    assert raised.value.code == EXIT_ERROR


def test_an_unknown_verb_is_an_argparse_refusal():
    with pytest.raises(SystemExit) as raised:
        cli.main(["transcode"])
    assert raised.value.code == EXIT_ERROR


#: The declared state file, written as a token because its value is the
#: test's own directory.
STATE_TOKEN = "{state}"

#: (argv after the common flags, request field, value).  The zero row is
#: the DEFAULT request — every field of it, so a new default cannot
#: arrive unnamed — and each later row declares one flag's effect.  A
#: value that is callable is handed the scan and the test directory.
REQUEST_FIELDS = (
    ((), "scans", lambda scan, tmp_path: (scan,)),
    ((), "dpis", (1200.0,)),
    ((), "dpi_forced", (False,)),
    ((), "format_ref", FOSSIL_REF),
    ((), "max_pages", None),
    ((), "workers", 1),
    ((), "complete", False),
    ((), "no_close", False),
    ((), "diag_port", None),
    ((), "run_dir",
     lambda scan, tmp_path: cli.run_dir_for(tmp_path / "run")),
    ((), "resume", None),
    ((), "refine_gate", data.REFINE_GATE_CONTEXT),
    # one state file and nothing else: the flag moves `resume` alone
    (("--resume", STATE_TOKEN), "resume",
     lambda scan, tmp_path: tmp_path / "earlier" / "facts.npz"),
    (("--resume", STATE_TOKEN), "scans", lambda scan, tmp_path: (scan,)),
    # the three plain dials, declared together in one argv
    (("--workers", "8", "--max-pages", "3", "--diag", "8025"),
     "workers", 8),
    (("--workers", "8", "--max-pages", "3", "--diag", "8025"),
     "max_pages", 3),
    (("--workers", "8", "--max-pages", "3", "--diag", "8025"),
     "diag_port", 8025),
)


@pytest.mark.parametrize(
    "extra,field,value", REQUEST_FIELDS,
    ids=[f"{'-'.join(row[0]) or 'defaults'}:{row[1]}"
         for row in REQUEST_FIELDS])
def test_the_request_field_carries_the_declared_value(
        extra, field, value, scan, tmp_path, decoder):
    state = tmp_path / "earlier" / "facts.npz"
    argv = tuple(str(state) if word == STATE_TOKEN else word
                 for word in extra)
    cli.main(_argv(scan, tmp_path / "payload.bin", tmp_path, *argv))
    expected = value(scan, tmp_path) if callable(value) else value
    assert getattr(decoder.only, field) == expected


@pytest.mark.parametrize("gate", data.REFINE_GATES)
def test_the_refinement_gate_dial_plumbs_straight_into_the_request(
        gate, scan, tmp_path, decoder):
    cli.main(_argv(scan, tmp_path / "payload.bin", tmp_path,
                   "--refine-gate", gate))
    assert decoder.only.refine_gate == gate


def test_an_unknown_refinement_gate_is_an_argparse_refusal(scan, tmp_path,
                                                           decoder):
    with pytest.raises(SystemExit) as raised:
        cli.main(_argv(scan, tmp_path / "payload.bin", tmp_path,
                       "--refine-gate", "corrected"))
    assert raised.value.code == EXIT_ERROR


@pytest.mark.parametrize("flag,field", [("--complete", "complete"),
                                        ("--no-close", "no_close")])
def test_the_close_mode_flags_plumb_straight_into_the_request(
        flag, field, scan, tmp_path, decoder):
    out = tmp_path / "payload.bin"
    cli.main(_argv(scan, out, tmp_path, flag))
    request = decoder.only
    assert getattr(request, field) is True
    other = "no_close" if field == "complete" else "complete"
    assert getattr(request, other) is False


def test_duplicate_scan_paths_are_passed_through_in_positional_order(
        scan, tmp_path, decoder):
    out = tmp_path / "payload.bin"
    cli.main(["decode", str(scan), str(scan), "--dpi", "1200", "--dpi",
              "1200", "--format", FOSSIL_REF, "--out", str(out),
              "--run-dir", str(tmp_path / "run")])
    assert decoder.only.scans == (scan, scan)
    assert decoder.only.dpis == (1200.0, 1200.0)


def test_mixed_declared_dpis_are_forwarded_per_scan_in_positional_order(
        scan, tmp_path, decoder):
    other = tmp_path / "half.tiff"
    other.write_bytes(b"not-a-real-tiff-either")
    out = tmp_path / "payload.bin"
    cli.main(["decode", str(scan), str(other), "--dpi", "1200", "--dpi",
              "600", "--format", FOSSIL_REF, "--out", str(out),
              "--run-dir", str(tmp_path / "run")])
    assert decoder.only.scans == (scan, other)
    assert decoder.only.dpis == (1200.0, 600.0)


def test_dpi_force_shares_the_dpi_order_and_marks_only_its_own_scan(
        scan, tmp_path, decoder):
    other = tmp_path / "forced.tiff"
    other.write_bytes(b"not-a-real-tiff-either")
    cli.main(["decode", str(scan), str(other), "--dpi", "1200",
              "--dpi-force", "2400", "--format", FOSSIL_REF, "--out",
              str(tmp_path / "payload.bin"), "--run-dir",
              str(tmp_path / "run")])
    assert decoder.only.scans == (scan, other)
    assert decoder.only.dpis == (1200.0, 2400.0)
    assert decoder.only.dpi_forced == (False, True)


def test_dpi_force_alone_declares_its_one_scan(scan, tmp_path, decoder):
    cli.main(["decode", str(scan), "--dpi-force", "4800", "--format",
              FOSSIL_REF, "--out", str(tmp_path / "payload.bin"),
              "--run-dir", str(tmp_path / "run")])
    assert decoder.only.dpis == (4800.0,)
    assert decoder.only.dpi_forced == (True,)


def test_the_two_identity_routes_resolve_to_one_and_the_same_format_row(
        scan, tmp_path, decoder):
    cli.main(_argv(scan, tmp_path / "a.bin", tmp_path))
    cli.main(["decode", str(scan), "--dpi", "1200", "--coding", CODING_ID,
              "--printer", PRINTER_ID, "--out", str(tmp_path / "b.bin"),
              "--run-dir", str(tmp_path / "run")])
    refs = [request.format_ref for request in decoder.requests]
    assert refs == [FOSSIL_REF, FOSSIL_REF]
    rows = {identity.resolve_format_ref(ref) for ref in refs}
    assert len(rows) == 1


def test_publish_payload_writes_the_exact_bytes_and_leaves_no_temp_file(
        tmp_path):
    out = tmp_path / "published.bin"
    cli._publish_payload(out, PAYLOAD)
    assert out.read_bytes() == PAYLOAD
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "published.bin"]


def test_publish_payload_refuses_a_target_that_appeared_under_it(tmp_path):
    out = tmp_path / "published.bin"
    out.write_bytes(b"standing")
    with pytest.raises(ValueError,
                       match="refusing to overwrite existing payload"):
        cli._publish_payload(out, PAYLOAD)
    assert out.read_bytes() == b"standing"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "published.bin"]


def test_publish_payload_refuses_an_unwritable_directory(tmp_path):
    out = tmp_path / "missing" / "published.bin"
    with pytest.raises(ValueError, match="could not write recovered payload"):
        cli._publish_payload(out, PAYLOAD)
    assert not out.exists()


def test_a_publish_failure_turns_a_verified_run_into_an_error_exit(
        scan, tmp_path, decoder, monkeypatch, capsys):
    def refusing(out_path: Path, payload: bytes) -> None:
        raise ValueError("could not write recovered payload")

    monkeypatch.setattr(cli, "_publish_payload", refusing)
    out = tmp_path / "payload.bin"
    assert cli.main(_argv(scan, out, tmp_path)) == EXIT_ERROR
    assert not out.exists()
    assert "could not write recovered payload" in capsys.readouterr().err


def test_the_schedule_verb_exits_zero_and_names_every_descriptor(capsys):
    assert cli.main(["schedule"]) == EXIT_VERIFIED
    printed = capsys.readouterr().out
    checks = _h3_support.Checks("schedule verb coverage")
    for name in DESCRIPTOR_NAMES:
        checks.check(f"schedule lists {name}", name in printed)
    checks.assert_clean()


def test_the_schedule_verb_names_a_declared_format_and_its_family(capsys):
    assert cli.main(["schedule", "--format", SMALL_REF]) == EXIT_VERIFIED
    printed = capsys.readouterr().out
    assert f"format {SMALL_REF}" in printed
    assert "family K" in printed


def test_the_schedule_verb_refuses_an_unknown_format(capsys):
    assert cli.main(["schedule", "--format", "L:nope"]) == EXIT_ERROR
    assert "holo3: unknown --format:" in capsys.readouterr().err


def test_the_status_block_and_accounting_table_go_to_stderr_not_stdout(
        scan, tmp_path, decoder, capsys):
    out = tmp_path / "payload.bin"
    cli.main(_argv(scan, out, tmp_path))
    captured = capsys.readouterr()
    assert "tiles.scan" in captured.err
    assert f"run dir: {cli.run_dir_for(tmp_path / 'run')}" in captured.err
    assert captured.out.splitlines() == [
        f"VERIFIED {len(PAYLOAD)} bytes sha256 {PAYLOAD_SHA}"]


def test_a_run_dir_is_minted_under_tmp_when_none_is_declared(
        scan, tmp_path, decoder):
    out = tmp_path / "payload.bin"
    cli.main(["decode", str(scan), "--dpi", "1200", "--format", FOSSIL_REF,
              "--out", str(out)])
    run_dir = decoder.only.run_dir
    assert run_dir.is_dir()
    assert run_dir.name.startswith("holo3-")
    os.rmdir(run_dir)
