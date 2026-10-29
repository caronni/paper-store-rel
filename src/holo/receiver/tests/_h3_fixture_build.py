"""How a fixture BUILDS its stimulus and RUNS its decode.

Split out of ``conftest`` at the 1000-line seam (W6).  Three pieces of
machinery every sim fixture leans on and no test calls directly: the
content-keyed render cache (``_cache_key`` over both stimulus modules,
``_materialise``, the frozen-artefact refusal), the content-keyed
DECODE cache over it (``_decode_key``, ``_load_decode`` /
``_publish_decode``), and the in-process decode driver
(``DecodeRecord``, ``_decode_once`` / ``_decode_group``, the label
registry that refuses a silently reused run dir).  ``conftest`` keeps
the fixtures themselves, which is what a test asks for by name.

Importing this module registers nothing: it holds no fixture.
"""
from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import hashlib
import io
import os
import pickle
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import cli, data, engine, sched_trace
from holo.receiver.tests import (_h3_sims, _h3_sims_cmy, _h3_sims_field,
                                _h3_sims_p_axis, _h3_support)

_WORK_LOCK = threading.Lock()


def _cache_key() -> str:
    digest = hashlib.sha256()
    # EVERY stimulus module: `_h3_sims_field` carries the displaced page
    # and the confetti platen since the W6 split, `_h3_sims_p_axis` the
    # two p300 volumes since 2026-09-16, `_h3_sims_cmy` the cmy pages
    # since 2026-10-12, and a key that hashed only the half they left
    # would serve stale renders of them.
    digest.update(_h3_sims.SOURCE_DIGEST.encode())
    digest.update(_h3_sims_field.SOURCE_DIGEST.encode())
    digest.update(_h3_sims_p_axis.SOURCE_DIGEST.encode())
    digest.update(_h3_sims_cmy.SOURCE_DIGEST.encode())
    digest.update(str(_h3_sims.RENDER_CACHE_VERSION).encode())
    digest.update(_h3_sims.K_FORMAT_REF.encode())
    digest.update(_h3_sims.COLOR_FORMAT_REF.encode())
    digest.update(_h3_sims.K_PAYLOAD_TAG)
    digest.update(_h3_sims.COLOR_PAYLOAD_TAG)
    digest.update(_h3_sims.HARD_FORMAT_REF.encode())
    digest.update(_h3_sims.HARD_PAYLOAD_TAG)
    digest.update(_h3_sims.GROUPS_FORMAT_REF.encode())
    digest.update(_h3_sims.GROUPS_PAYLOAD_TAG)
    digest.update(_h3_sims.PAGES_PAYLOAD_TAG)
    digest.update(_h3_sims_p_axis.P_AXIS_FORMAT_REF.encode())
    digest.update(_h3_sims_p_axis.P_AXIS_PAYLOAD_TAG)
    digest.update(_h3_sims_p_axis.P_AXIS_K_FORMAT_REF.encode())
    digest.update(_h3_sims_p_axis.P_AXIS_K_PAYLOAD_TAG)
    digest.update(_h3_sims_cmy.CMY_FORMAT_REF.encode())
    digest.update(_h3_sims_cmy.CMY_PAYLOAD_TAG)
    digest.update(_h3_sims_cmy.CMY_C2_FORMAT_REF.encode())
    digest.update(_h3_sims_cmy.CMY_C2_PAYLOAD_TAG)
    return digest.hexdigest()[:16]


def _cache_root() -> Path | None:
    declared = os.environ.get(_h3_support.FIXTURE_CACHE_ENV)
    if declared is not None and declared.strip() == "":
        return None
    base = (Path(declared) if declared
            else Path(tempfile.gettempdir()) / "holo3-fixture-cache")
    return base / _cache_key()


DECODE_CACHE_VERSION = 1

_PRODUCTION_ROOT = _h3_support.HOLO3_ROOT.parent


def _env_tag() -> str:
    import scipy

    return (f"{sys.version}|numpy {np.__version__}"
            f"|scipy {scipy.__version__}")


# The whole receiver and the format authority it may import: a decode is
# a function of the production tree, so any edit under src/holo outside
# this test package re-keys every cached decode.  The rows are read once
# at import -- path as well as content digest, so a moved file moves the
# key -- and the key is folded from them on every call, which is what
# lets a test move one file's row and watch the key follow.
def _read_holo_source_rows() -> tuple[tuple[str, str], ...]:
    rows = []
    for path in _h3_support.source_files(_PRODUCTION_ROOT):
        if _h3_support.TESTS_DIR in path.parents:
            continue
        rows.append((str(path.relative_to(_PRODUCTION_ROOT)),
                     hashlib.sha256(path.read_bytes()).hexdigest()))
    return tuple(rows)


_ENV_TAG = _env_tag()
HOLO_SOURCE_ROWS = _read_holo_source_rows()


def _holo_source_digest() -> str:
    digest = hashlib.sha256()
    for name, sha in HOLO_SOURCE_ROWS:
        digest.update(name.encode())
        digest.update(sha.encode())
    return digest.hexdigest()


# The decode's own inputs are the label, the workers, the extra argv and
# the dropped rows plus one row per capture: the argv `_decode_group`
# builds is a pure function of those, and its two remaining tokens (the
# out path and the run dir) are session paths that carry no content.
def _decode_key(label: str, captures: tuple[_h3_sims.SimCapture, ...],
                workers: int, extra_argv: tuple[str, ...],
                drop_rows: tuple[str, ...], cache_tag: str = "",
                keep_planes: bool = False, traced: bool = False) -> str:
    digest = hashlib.sha256()
    digest.update(_cache_key().encode())
    digest.update(_holo_source_digest().encode())
    digest.update(str(DECODE_CACHE_VERSION).encode())
    digest.update(_ENV_TAG.encode())
    digest.update(label.encode())
    digest.update(str(workers).encode())
    digest.update(repr(extra_argv).encode())
    digest.update(repr(drop_rows).encode())
    digest.update(cache_tag.encode())
    # Only a record that asks for its planes moves: every other key stays
    # where it was, and a record published without them can never be
    # served to a caller that opens them.
    if keep_planes:
        digest.update(b"|keep-planes")
    # The same rule for a TRACED record (review 2026-10-17 D10, R4): the
    # scheduler trace is armed by HOLO3_SCHED_TRACE, an environment door
    # the key cannot see, so the decode declares it and `_publish_decode`
    # holds the run dir to that declaration.
    if traced:
        digest.update(b"|sched-trace")
    for capture in captures:
        digest.update(capture.format_ref.encode())
        digest.update(f"{capture.dpi!r}|{capture.rot_k}".encode())
        digest.update(capture.tiff_sha256.encode())
        digest.update(capture.payload_sha256.encode())
        digest.update(str(capture.payload_bytes).encode())
    return digest.hexdigest()[:32]


def _decode_cache_dir(key: str) -> Path | None:
    root = _cache_root()
    return None if root is None else root / "decodes" / key


@contextlib.contextmanager
def _decode_lock(directory: Path) -> Iterator[None]:
    directory.parent.mkdir(parents=True, exist_ok=True)
    handle = open(f"{directory}.lock", "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        handle.close()


def _raise_on_mismatch(name: str, outdir: Path,
                       expected: dict[str, str]) -> None:
    problem = _h3_sims.verify(outdir, expected)
    if problem is None:
        return
    raise RuntimeError(
        f"FIXTURE FAILURE: freshly generated {name} sim does not match its "
        f"frozen artefacts ({problem}). This is src/holo generator drift or "
        f"a numeric-stack change in the render path — never a holo3 "
        f"receiver regression. Bump _h3_sims.RENDER_CACHE_VERSION only "
        f"after the drift itself is understood and ruled on.")


def _materialise(name: str, builder: Callable[[Path], object],
                 expected: dict[str, str], fallback_root: Path) -> Path:
    root = _cache_root()
    if root is None:
        target = fallback_root / name
        if _h3_sims.verify(target, expected) is not None:
            builder(target)
            _raise_on_mismatch(name, target, expected)
        return target
    target = root / name
    if _h3_sims.verify(target, expected) is None:
        return target
    staging = root / f".{name}.{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    builder(staging)
    _raise_on_mismatch(name, staging, expected)
    try:
        os.replace(staging, target)
    except OSError:
        if _h3_sims.verify(target, expected) is None:
            shutil.rmtree(staging, ignore_errors=True)
        else:
            shutil.rmtree(target, ignore_errors=True)
            os.replace(staging, target)
    return target


def _sim_gate(what: str) -> None:
    _h3_support.skip_unless_slow_lane(what)
    reason = _h3_sims.producer_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)


@dataclass(frozen=True)
class DecodeRecord:
    label: str
    format_ref: str
    rot_k: int
    workers: int
    argv: tuple[str, ...]
    exit_code: int
    status: str
    payload: bytes | None
    payload_sha256: str | None
    certified: int
    certificates: dict
    certificate_signature: tuple
    events: tuple
    report: dict
    run_dir: Path
    out_path: Path
    out_exists: bool
    stdout: str
    stderr: str
    wall_s: float
    union_subjects: tuple = ()
    attempt_outcomes: dict = dataclass_field(default_factory=dict)
    live_pages: tuple = ()
    engine: object | None = None


# What the cache stores: every field of the record except the two paths,
# which belong to the session that asks for it, and the engine, which is
# a live store and never data (a decode that keeps one is not cached).
# The rest is dataclasses and numpy arrays -- no callable is pickled.
_CACHED_FIELDS = tuple(
    row.name for row in dataclasses.fields(DecodeRecord)
    if row.name not in ("run_dir", "out_path", "engine"))

_CACHED_RECORD = "record.pkl"
_CACHED_RUN = "run"
_CACHED_PAYLOAD = "payload.bin"


def _load_decode(directory: Path, out_path: Path) -> DecodeRecord | None:
    blob = directory / _CACHED_RECORD
    if not blob.is_file():
        return None
    fields = pickle.loads(blob.read_bytes())
    payload = directory / _CACHED_PAYLOAD
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if payload.is_file():
        shutil.copyfile(payload, out_path)
    return DecodeRecord(run_dir=directory / _CACHED_RUN, out_path=out_path,
                        **fields)


# What a cached decode record publishes (2026-10-18, review D4 / R3).
# The run dir's FILES are the declared products a test reads back
# (report.json, argv, events.jsonl, facts.npz, the panes, tree), and its
# product DIRECTORIES are named here: `sched-trace/` is the one today
# (39d4ebba: copying only flat files published a run dir the warm lane's
# trace tests then read a missing file out of).  Intake's per-capture
# plane scratch, `run_dir / capture_id[:12]` (plugins/intake.py), is NOT
# a product: 65 MB per colour capture, opened by no receiver test, and
# it was 1.7 GB of a 2.7 GB cache once 39d4ebba copied every directory
# (measured on machine 1 2026-10-17; on 2026-10-18 the standing cache's 108
# records, 36 labels x 3 trees, held 5,219 MB of run dirs, 186 MB under
# this rule).  The one record that opens its planes
# -- the analyzer's S-tier run dir, read by `inputs.load_run` -- asks for
# them with `keep_planes`, which is in its key.  A directory that is
# neither a named product nor a capture's scratch is refused: dropping
# it silently is 39d4ebba's bug and copying it silently is D4's.
PUBLISHED_RUN_DIRS = (sched_trace.DIR_NAME,)


def _plane_scratch_names(record: DecodeRecord,
                         captures: tuple[_h3_sims.SimCapture, ...]
                         ) -> frozenset[str]:
    # The capture id is the TIFF's sha256 (intake: `sha256_file(path)`);
    # the report's capture facts name the same ids when the run got that
    # far, and a run that died before its report still has the captures.
    ids = [capture.tiff_sha256 for capture in captures]
    ids += [str(row.get("capture", ""))
            for row in record.report.get("capture_facts", ())]
    return frozenset(capture_id[:12] for capture_id in ids if capture_id)


# A traced record and an untraced one are different records (2026-10-18,
# review D10 / R4).  `HOLO3_SCHED_TRACE` arms the trace from the
# environment, which the decode key cannot see: with it exported, a
# decode under an untraced key ran traced and was published there, and
# the trace pin's OFF-vs-ON byte identity compared a traced run with
# itself.  The run dir is the ground truth -- `sched-trace/` is there iff
# the run was traced -- so a record is published only under a key that
# declares what it is: an untraced key refuses a run dir holding the
# trace, and a traced key refuses one without it.
def _refuse_undeclared_trace(record: DecodeRecord, traced: bool) -> None:
    holds_trace = (record.run_dir / sched_trace.DIR_NAME).is_dir()
    if holds_trace == traced:
        return
    if holds_trace:
        raise RuntimeError(
            f"{record.label}: run dir {record.run_dir} holds "
            f"{sched_trace.DIR_NAME}/ but its decode key does not declare "
            f"tracing -- {sched_trace.ENV_ENABLE} is exported into a decode "
            f"that did not ask for it; unset it, or pass traced=True")
    raise RuntimeError(
        f"{record.label}: the decode key declares tracing but run dir "
        f"{record.run_dir} holds no {sched_trace.DIR_NAME}/ -- the run was "
        f"not traced; set {sched_trace.ENV_ENABLE} around the decode")


def _publish_decode(directory: Path, record: DecodeRecord,
                    captures: tuple[_h3_sims.SimCapture, ...],
                    keep_planes: bool = False, traced: bool = False) -> None:
    _refuse_undeclared_trace(record, traced)
    scratch = _plane_scratch_names(record, captures)
    staging = directory.parent / f".{directory.name}.{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    (staging / _CACHED_RUN).mkdir(parents=True, exist_ok=True)
    if record.run_dir.is_dir():
        for path in sorted(record.run_dir.iterdir()):
            if path.is_file():
                shutil.copyfile(path, staging / _CACHED_RUN / path.name)
            elif not path.is_dir():
                continue
            elif path.name in PUBLISHED_RUN_DIRS or (
                    keep_planes and path.name in scratch):
                shutil.copytree(path, staging / _CACHED_RUN / path.name)
            elif path.name not in scratch:
                shutil.rmtree(staging, ignore_errors=True)
                raise RuntimeError(
                    f"{record.label}: run dir {record.run_dir} holds a "
                    f"directory {path.name!r} that is neither a published "
                    f"product {PUBLISHED_RUN_DIRS} nor a capture's plane "
                    f"scratch {sorted(scratch)}; name it in "
                    f"_h3_fixture_build.PUBLISHED_RUN_DIRS if a test reads "
                    f"it from a cached record")
    if record.payload is not None:
        (staging / _CACHED_PAYLOAD).write_bytes(record.payload)
    fields = {name: getattr(record, name) for name in _CACHED_FIELDS}
    (staging / _CACHED_RECORD).write_bytes(pickle.dumps(fields))
    shutil.rmtree(directory, ignore_errors=True)
    os.replace(staging, directory)


def _certificate_signature(certificates: dict) -> tuple:
    rows = []
    for key in sorted(certificates):
        certificate = certificates[key]
        rows.append((tuple(key),
                     np.asarray(certificate.user_bits, np.uint8).tobytes()))
    return tuple(rows)


def _decode_once(label: str, capture: _h3_sims.SimCapture, root: Path,
                 workers: int = 8, extra_argv: tuple[str, ...] = (),
                 drop_rows: tuple[str, ...] = (),
                 keep_engine: bool = False,
                 cache_tag: str = "",
                 keep_planes: bool = False,
                 traced: bool = False) -> DecodeRecord:
    return _decode_group(label, (capture,), root, workers, extra_argv,
                         drop_rows, keep_engine, cache_tag, keep_planes,
                         traced)


# Labels name run dirs under one session decode_root; a silent reuse is
# refused by the CLI's own overwrite guard 100 seconds into the second
# decode, which reads as a decode regression rather than the harness
# error it is (the color-w1 collision, 2026-08-31).  The registry makes
# it loud and immediate instead.
_DECODE_LABELS_USED: dict[str, str] = {}


def _claim_decode_label(label: str, root: Path) -> None:
    key = f"{root}::{label}"
    holder = _DECODE_LABELS_USED.get(key)
    caller = "conftest/test"
    if holder is not None:
        raise RuntimeError(
            f"duplicate decode label {label!r} under {root} — labels name "
            f"run dirs, so every _decode_once/_decode_group call in a "
            f"session needs its own; pick a distinct label")
    _DECODE_LABELS_USED[key] = caller


# THE COLOUR-ROW ADOPTION HATCH IS NOT IN THE KEY, BY REFUSAL
# (2026-10-03, S9).  `HOLO3_COLOR_ROW_ADOPT` changes which colour rows a
# decode adopts and is read from the environment at store construction;
# a stray export would publish non-default decode records under the
# default key.  Keying on it would make a second cache population nobody
# asked for, so a decode under anything but the shipped `last` is
# refused outright -- loud, before any cache is read or written.
def refuse_non_default_adopt(environ: dict[str, str] | None = None) -> None:
    from holo.receiver import store_folds

    env = os.environ if environ is None else environ
    declared = env.get(store_folds.ENV_COLOR_ROW_ADOPT)
    if declared is None or declared.strip().lower() in (
            "", store_folds.ADOPT_LAST):
        return
    raise RuntimeError(
        f"{store_folds.ENV_COLOR_ROW_ADOPT}={declared!r} is set: the sim "
        f"decode records are the shipped receiver's "
        f"({store_folds.ADOPT_LAST!r}) and the cache key does not carry "
        f"this hatch -- unset it to run the receiver lanes; measure a "
        f"mode with a decode of its own, never through the fixture cache")


def _decode_group(label: str, captures: tuple[_h3_sims.SimCapture, ...],
                  root: Path, workers: int = 8,
                  extra_argv: tuple[str, ...] = (),
                  drop_rows: tuple[str, ...] = (),
                  keep_engine: bool = False,
                  cache_tag: str = "",
                  keep_planes: bool = False,
                  traced: bool = False) -> DecodeRecord:
    _h3_support.skip_unless_slow_lane(f"the {label} sim decode")
    return cached_decode(label, captures, root, workers, extra_argv,
                         drop_rows, keep_engine, cache_tag, keep_planes,
                         traced)


# `_decode_group` without the receiver's slow-lane gate: the analyzer's
# lane reads the same cache entry under its own flag
# (analyzer/tests/_analyzer_fixtures.py), so the gate is the caller's.
def cached_decode(label: str, captures: tuple[_h3_sims.SimCapture, ...],
                  root: Path, workers: int = 8,
                  extra_argv: tuple[str, ...] = (),
                  drop_rows: tuple[str, ...] = (),
                  keep_engine: bool = False,
                  cache_tag: str = "",
                  keep_planes: bool = False,
                  traced: bool = False) -> DecodeRecord:
    refuse_non_default_adopt()
    _claim_decode_label(label, root)
    # A decode that keeps its ENGINE is never cached: the finished store
    # is one of that decode's outputs and it is live state, not data.
    # Every other decode is a function of its inputs, so a worker that
    # misses takes the lock and decodes while its siblings WAIT on it.
    # `cache_tag` is how a fixture that decodes under a PATCH of
    # production code names that patch: the key reads the tree, and a
    # monkeypatch applied around the call is invisible to it.
    # `keep_planes` publishes intake's plane scratch with the record, for
    # the one caller that opens it (`_publish_decode`'s note); it is in
    # the key, so a record without planes is never served to that caller.
    # `traced` declares a run under HOLO3_SCHED_TRACE (the caller sets the
    # variable); it is in the key, and publication refuses a run dir that
    # contradicts it (`_refuse_undeclared_trace`).
    directory = (None if keep_engine else _decode_cache_dir(
        _decode_key(label, captures, workers, extra_argv, drop_rows,
                    cache_tag, keep_planes, traced)))
    if directory is None:
        return _run_decode(label, captures, root, workers, extra_argv,
                           drop_rows, keep_engine)
    with _decode_lock(directory):
        loaded = _load_decode(directory, root / label / "payload.bin")
        if loaded is not None:
            return loaded
        record = _run_decode(label, captures, root, workers, extra_argv,
                             drop_rows, keep_engine)
        _publish_decode(directory, record, captures, keep_planes, traced)
    return record


def _run_decode(label: str, captures: tuple[_h3_sims.SimCapture, ...],
                root: Path, workers: int, extra_argv: tuple[str, ...],
                drop_rows: tuple[str, ...],
                keep_engine: bool) -> DecodeRecord:
    run_dir_base = root / label / "run"
    run_dir = cli.run_dir_for(run_dir_base)
    out_path = root / label / "payload.bin"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    argv = ("decode", *(str(capture.tiff) for capture in captures),
            *(part for capture in captures
              for part in ("--dpi", str(int(capture.dpi)))),
            "--format", captures[0].format_ref, "--out", str(out_path),
            "--workers", str(workers), "--run-dir", str(run_dir_base),
            *extra_argv)
    captured: dict[str, object] = {}
    original = engine.decode

    def instrumented(request: object,
                     events: list | None = None) -> data.RunResult:
        collected: list = [] if events is None else events
        instance = engine._Engine(request, collected)
        result = instance.run()
        captured["certificates"] = dict(instance._certificates)
        captured["events"] = tuple(collected)
        captured["union_subjects"] = tuple(sorted(
            key[1] for key in instance._bookmarks
            if key[0] == "tiles.union"))
        captured["attempt_outcomes"] = dict(instance._attempt_outcomes)
        captured["live_pages"] = tuple(sorted(instance.live_pages()))
        if keep_engine:
            captured["engine"] = instance
        return result

    out = io.StringIO()
    err = io.StringIO()
    standing_rows = engine.DESCRIPTORS
    standing_by_name = engine.DESCRIPTOR_BY_NAME
    with _WORK_LOCK:
        engine.decode = instrumented
        if drop_rows:
            rows = tuple(descriptor for descriptor in standing_rows
                         if descriptor.name not in drop_rows)
            assert len(rows) == len(standing_rows) - len(drop_rows), (
                f"drop_rows {drop_rows} does not name live descriptor rows")
            engine.DESCRIPTORS = rows
            engine.DESCRIPTOR_BY_NAME = {descriptor.name: descriptor
                                         for descriptor in rows}
        started = time.monotonic()
        try:
            with (contextlib.redirect_stdout(out),
                  contextlib.redirect_stderr(err)):
                exit_code = cli.main(list(argv))
        finally:
            engine.decode = original
            engine.DESCRIPTORS = standing_rows
            engine.DESCRIPTOR_BY_NAME = standing_by_name
            wall_s = time.monotonic() - started
    certificates = captured.get("certificates", {})
    report_path = run_dir / "report.json"
    report: dict = {}
    if report_path.is_file():
        import json

        report = json.loads(report_path.read_text())
    payload = out_path.read_bytes() if out_path.is_file() else None
    return DecodeRecord(
        label=label, format_ref=captures[0].format_ref,
        rot_k=captures[0].rot_k,
        workers=workers, argv=argv, exit_code=exit_code,
        status="verified" if exit_code == 0 else "not-verified",
        payload=payload,
        payload_sha256=(hashlib.sha256(payload).hexdigest()
                        if payload is not None else None),
        certified=len(certificates), certificates=certificates,
        certificate_signature=_certificate_signature(certificates),
        events=captured.get("events", ()), report=report, run_dir=run_dir,
        out_path=out_path, out_exists=out_path.is_file(),
        stdout=out.getvalue(), stderr=err.getvalue(), wall_s=wall_s,
        union_subjects=captured.get("union_subjects", ()),
        attempt_outcomes=captured.get("attempt_outcomes", {}),
        live_pages=captured.get("live_pages", ()),
        engine=captured.get("engine"))
