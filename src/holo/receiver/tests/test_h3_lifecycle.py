"""The lifecycle laws: how a row is seated, re-armed and retired.

One module for the CONVENTIONS the 2026-09-21 lifecycle work pinned —
the engine carries no plugin name and no key literal, every row's
`retire` answers with a cause, and a row whose clause comes true while
it sits on a standing seat leaves at the next wake rather than waiting
for a pop it may never get.  The per-row behaviour lives in each row's
own module's tests -- `place`'s subdivision, dormancy and afterlife in
`test_h3_place_lifecycle`, split out at the 1000-line seam 2026-10-03
-- and what is here is what holds for ALL of them.
"""
from __future__ import annotations

import ast
import dataclasses
import importlib
import pkgutil
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import data, engine, schedule, sched_trace, store
from holo.receiver import store_folds
from holo.receiver import descriptor as descriptor_module
from holo.receiver import plugins as plugins_package
from holo.receiver.format.identity import resolve_format_ref
from holo.receiver.descriptor import (
    TERMINAL_FACTS,
    PluginDescriptor,
    WorkerBookmark,
)
from holo.receiver.lib import geometry
from holo.receiver.plugins import refine, tiles, tiles_sched
from holo.receiver.tests import _h3_facts, _h3_sims, _h3_support

PROBE = "probe"
STAGE = "probing"
PRICE = 20


def _descriptor(retire: object) -> PluginDescriptor:
    return PluginDescriptor(
        name=PROBE, subject_kind="probe", born_by=(data.Capture,),
        subjects_of=lambda store, fact: (),
        reads=lambda store, subject: (),
        eligible=lambda store, subject: True,
        stage=lambda store, subject: STAGE,
        cost=lambda store, subject, named, attempts, last_cost: PRICE,
        retire=retire,
        prepare=lambda store, subject, stage: (
            lambda: data.JobResult((), (), 0.0)),
        produces=(), prices=((STAGE, PRICE),))


def _bench(monkeypatch: pytest.MonkeyPatch,
           retire: object) -> tuple[object, WorkerBookmark]:
    instance = _h3_facts.new_engine(workers=4)
    row = _descriptor(retire)
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        {**engine.DESCRIPTOR_BY_NAME, PROBE: row})
    worker = WorkerBookmark(plugin=PROBE, subject="s", reads=())
    instance._bookmarks[(PROBE, "s")] = worker
    return instance, worker


# --------------------------------------------------- the engine is generic

def _tree(module: object) -> ast.Module:
    path = Path(module.__file__)
    return ast.parse(path.read_text(), filename=str(path))


def _plugin_spellings() -> frozenset[str]:
    """Every name a row goes by: each descriptor's, and every plugin
    module's own `PLUGIN` / `PLUGIN_*` constant (`tiles` included, which
    names a module rather than a row)."""
    names = {descriptor.name for descriptor in engine.DESCRIPTORS}
    for info in pkgutil.iter_modules(plugins_package.__path__):
        module = importlib.import_module(
            f"{plugins_package.__name__}.{info.name}")
        names.update(
            value for name, value in vars(module).items()
            if (name == "PLUGIN" or name.startswith("PLUGIN_"))
            and isinstance(value, str))
    return frozenset(names)


def _string_constants(tree: ast.AST) -> set[str]:
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def _enclosing_functions(tree: ast.AST) -> dict[ast.AST, str]:
    """node -> the name of the innermost def it sits in ("" at module)."""
    owner: dict[ast.AST, str] = {}

    def visit(node: ast.AST, name: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (child.name if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)) else name)
            owner[child] = inner
            visit(child, inner)

    visit(tree, "")
    return owner


def test_engine_py_names_no_plugin_row_and_no_key_constant():
    """The engine's ONE legitimate special case is the close consult.

    Everything else it does it does off `PluginDescriptor` alone, so a
    plugin name or a key kind appearing here is a mechanism that belongs
    in a row.  Until 2026-09-21 one name survived — `REARM_PLUGINS`,
    the single-writer check's `revisit` exemption — and dissolving that
    row emptied the set and the set went with it.  ZERO now, and the
    assertion says so rather than naming anything.

    STRUCTURAL SINCE 2026-10-03 (S10): every string constant in the
    module is checked against the key-kind vocabulary itself and against
    every spelling a row goes by, so a raw `("place_stage", wid)` tuple
    or a `"tiles.scan"` literal fails here whatever it is assigned to —
    not only an identifier that happens to start `KEY_`.
    """
    tree = _tree(engine)
    constants = _string_constants(tree)
    checks = _h3_support.Checks("engine.py is generic")
    checks.equal("plugin names spelled in engine.py",
                 sorted(constants & _plugin_spellings()), [])
    checks.equal("key kinds spelled in engine.py",
                 sorted(constants & set(descriptor_module.KEY_KINDS)), [])
    key_names = sorted(
        {node.id for node in ast.walk(tree)
         if isinstance(node, ast.Name) and node.id.startswith("KEY_")}
        | {node.attr for node in ast.walk(tree)
           if isinstance(node, ast.Attribute)
           and node.attr.startswith("KEY_")}
        | {(alias.asname or alias.name) for node in ast.walk(tree)
           if isinstance(node, ast.ImportFrom)
           for alias in node.names if alias.name.startswith("KEY_")})
    checks.check("no key-kind constant is named", not key_names,
                 f"found {key_names}")
    checks.assert_clean()


def test_the_conventions_catch_what_they_claim_to():
    """The two vocabularies above are not vacuous: a raw key tuple and a
    row name, planted in a copy of the engine's source, are both found."""
    source = Path(engine.__file__).read_text() + (
        "\n\ndef _planted(wid):\n"
        "    return ('place_stage', wid), 'tiles.scan'\n")
    constants = _string_constants(ast.parse(source))
    assert constants & set(descriptor_module.KEY_KINDS) == {"place_stage"}
    assert constants & _plugin_spellings() == {"tiles.scan"}


def test_no_fold_reads_an_engine_bookmark_by_plugin_name():
    """S7 (2026-10-03) took `worker_version("place", wid)` out of the
    place-outcome fold; the fold now stamps a sleep through the generic
    `merging_sleep_version`.  As a law over both store modules: no fold
    reads a bookmark (`_bookmarks`, `worker_version`) and neither module
    spells a row's name.  `store.worker_version` itself is the one
    reader of `_bookmarks` in the store, and its only caller is a row
    (`place_sched.dormant`), which may name itself.
    """
    checks = _h3_support.Checks("folds read no bookmark")
    folds = _tree(store_folds)
    checks.equal("bookmark reads in store_folds.py", sorted(
        (node.lineno, node.attr) for node in ast.walk(folds)
        if isinstance(node, ast.Attribute)
        and node.attr in ("_bookmarks", "worker_version")), [])
    store_tree = _tree(store)
    owner = _enclosing_functions(store_tree)
    checks.equal("store.py functions reading `_bookmarks`", sorted(
        {owner[node] for node in ast.walk(store_tree)
         if isinstance(node, ast.Attribute) and node.attr == "_bookmarks"}),
        ["worker_version"])
    checks.equal("store.py calls to worker_version", sorted(
        node.lineno for node in ast.walk(store_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "worker_version"), [])
    for module, tree in (("store_folds.py", folds), ("store.py", store_tree)):
        checks.equal(f"plugin names spelled in {module}", sorted(
            _string_constants(tree) & _plugin_spellings()), [])
    checks.assert_clean()


def test_every_descriptor_retire_declares_the_cause_contract():
    """`retire` answers `str | None` -- the CAUSE, or None while it lives.

    The engine tallies the string and stamps it on `WorkerRetired`; a
    bool would give it nothing to stamp, which is the record the
    2026-08-31 done-gate finding was made of.  The subject shape is each
    row's own, so this is the declaration; the decode below is the
    behaviour.
    """
    checks = _h3_support.Checks("retire declares str | None")
    for descriptor in engine.DESCRIPTORS:
        annotation = descriptor.retire.__annotations__.get("return")
        checks.check(f"{descriptor.name}.retire -> str | None",
                     annotation == "str | None", f"got {annotation!r}")
    checks.assert_clean()


def test_every_retirement_in_a_real_decode_carries_a_cause(decode_k_w8):
    """And the run's own tally says the same thing."""
    retired = [event for event in decode_k_w8.events
               if isinstance(event, data.WorkerRetired)]
    assert retired, "a K decode retires rows; this pin needs some"
    assert all(isinstance(event.cause, str) and event.cause
               for event in retired)
    stat = [event for event in decode_k_w8.events
            if isinstance(event, data.EngineStat)][-1]
    assert dict(stat.retire_causes), (
        "the retire causes reach EngineStat, so nobody has to walk the "
        "event file to find out whether a gate bit")
    assert sum(dict(stat.retire_causes).values()) == len(retired), (
        "one cause tallied per WorkerRetired, and exactly one: a "
        "double-tally would pass an inequality")


# ------------------------------------------------- the push door (2026-09-21)

def test_a_woken_worker_whose_clause_came_true_retires_at_the_push(
        monkeypatch):
    """The standing-seat blind spot, closed.

    A wake that leaves the price unchanged returns at `seat_stands` and
    is never popped, so before this door a row whose retire clause came
    true while it sat there waited for a pop it might never get — on
    sheet H, `place` took 35,418 wakes and retired 0 windows in 36
    minutes.
    """
    clause: list[str | None] = [None]
    instance, worker = _bench(monkeypatch,
                              lambda store, subject: clause[0])
    instance._push_worker(worker)
    assert worker.seat_seq >= 0 and not worker.retired
    seated = len(instance._frontier)

    clause[0] = "probed"
    instance._push_worker(worker)
    assert worker.retired is True
    assert len(instance._frontier) == seated, (
        "the retirement takes no new seat; the standing entry is "
        "skipped at its pop")
    retired = [event for event in instance._events
               if isinstance(event, data.WorkerRetired)]
    assert [(event.plugin, event.subject, event.cause)
            for event in retired] == [(PROBE, "s", "probed")]
    assert instance._retire_causes == {"probed": 1}


def test_a_retirement_takes_its_seat_count_with_it_and_happens_once(
        monkeypatch):
    """Two doors reach `_retire_worker`, so its invariant is asserted.

    Retiring at the push leaves a standing heap entry behind (lazy
    deletion), and counting that entry in `EngineStat.queued` until some
    later pop overstates the frontier — permanently for entries still in
    the heap at RunDone, which is where an A/B reads it.  And with a
    second door, "a worker retires once" is load-bearing for
    `_retired_count`, the cause tally and the event stream.
    """
    instance, worker = _bench(monkeypatch, lambda store, subject: None)
    instance._push_worker(worker)
    assert instance._queued[PROBE] == 1
    instance._retire_worker(worker, "probed")
    assert instance._queued[PROBE] == 0 and worker.seat_seq == -1
    instance._retire_worker(worker, "probed_again")
    assert instance._retire_causes == {"probed": 1}
    assert instance._retired_count == 1
    assert instance._queued[PROBE] == 0, (
        "the second call is a no-op, not a second decrement")
    assert len([event for event in instance._events
                if isinstance(event, data.WorkerRetired)]) == 1


def test_a_worker_that_must_retire_is_never_seated_at_all(monkeypatch):
    instance, worker = _bench(monkeypatch,
                              lambda store, subject: "born_done")
    instance._push_worker(worker)
    assert worker.retired is True
    assert instance._frontier == [], (
        "retire runs before stage, so a row that must go never prices "
        "itself and never enters the heap")


# ------------------------------------------------ reads are fixed at birth

def test_no_worker_s_reads_are_re_derived_after_birth():
    """THE AMENDMENT, 2026-09-21, as a law over the source.

    A worker's declared reads are its TRUE INPUTS, fixed when the fact
    that creates its work is folded.  Every derived relation — which
    tiles a window reaches, which parent a child's settle concerns — is
    the STORE's, and the store routes a change to the key its owner
    already holds.  So there is no descriptor field naming keys that
    re-derive a read set, and no engine path that re-evaluates `reads`
    for a standing worker on a wake: `_births` extending a re-born
    bookmark is the one way a live worker's reads grow.
    """
    checks = _h3_support.Checks("reads are fixed at birth")
    fields = {field.name for field in
              dataclasses.fields(engine.PluginDescriptor)}
    checks.check("no read-set re-derivation field on the descriptor",
                 not {name for name in fields if "rederive" in name})
    path = Path(engine.__file__)
    tree = ast.parse(path.read_text(), filename=str(path))
    names = {node.name for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    checks.check("no engine method re-derives reads",
                 not {name for name in names if "rederive" in name})
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)}
    checks.check("nothing calls one either",
                 not {name for name in calls if "rederive" in name})
    # `reads` and `subjects_of` are consulted only at a birth (new or
    # standing), so neither may be reached anywhere else in the engine --
    # as a CALL on any receiver, as a callable HANDED to something (the
    # trace's `timed`), or by name through `getattr` (2026-10-03, S10:
    # the old check caught only `descriptor.reads` spelled with that
    # receiver name).  A bookmark's own `.reads` tuple is data, read
    # wherever the engine (un)subscribes it, and stays out of scope.
    owner = _enclosing_functions(tree)
    consulted = sorted(
        (owner[node], node.lineno) for node in ast.walk(tree)
        if owner.get(node) != "_births" and (
            (isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr in DERIVERS)
            or (isinstance(node, ast.Call) and any(
                isinstance(arg, ast.Attribute) and arg.attr in DERIVERS
                and not (isinstance(arg.value, ast.Name)
                         and arg.value.id in BOOKMARK_NAMES)
                for arg in node.args))
            or (isinstance(node, ast.Attribute)
                and node.attr == "subjects_of")
            or (isinstance(node, ast.Constant)
                and node.value in DERIVERS)))
    checks.equal("reads / subjects_of consulted outside `_births`",
                 consulted, [])
    checks.check("and `_births` does consult both",
                 {"reads", "subjects_of"} <= {
                     node.attr for node in ast.walk(tree)
                     if isinstance(node, ast.Attribute)
                     and owner.get(node) == "_births"})
    checks.assert_clean()


#: The two descriptor callables a birth consults.
DERIVERS = frozenset({"reads", "subjects_of"})
#: The engine's local names for a `WorkerBookmark`, whose `.reads` is the
#: tuple fixed at birth and may be handed to `_register_reads` /
#: iterated at retirement.
BOOKMARK_NAMES = frozenset({"worker", "standing"})


# ------------------------------------------ every exit of the two funnels

def _exit_reasons(function: ast.FunctionDef, exit_type: type,
                  trace_call: str) -> list[str | None]:
    """The trace reason that labels each `exit_type` statement, in source
    order -- None for an exit with no label.

    An exit is labelled when, walking back through its own block past
    the bookkeeping calls an exit may make (`_retire_worker`,
    `_repush`), the first statement is `if on: trace.<trace_call>(...,
    "<reason>")`.
    """
    passthrough = {"_retire_worker", "_repush"}
    reasons: list[tuple[int, str | None]] = []
    for node in ast.walk(function):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for index, statement in enumerate(block):
                if not isinstance(statement, exit_type):
                    continue
                reason = None
                for prior in reversed(block[:index]):
                    if (isinstance(prior, ast.Expr)
                            and isinstance(prior.value, ast.Call)
                            and isinstance(prior.value.func, ast.Attribute)
                            and prior.value.func.attr in passthrough):
                        continue
                    if (isinstance(prior, ast.If)
                            and isinstance(prior.test, ast.Name)
                            and prior.test.id == "on"):
                        labels = [
                            call.args[-1].value for call in ast.walk(prior)
                            if isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Attribute)
                            and call.func.attr == trace_call
                            and call.args
                            and isinstance(call.args[-1], ast.Constant)]
                        reason = labels[0] if len(labels) == 1 else None
                    break
                reasons.append((statement.lineno, reason))
    return [reason for _line, reason in sorted(reasons)]


def test_every_exit_of_push_and_fill_is_an_enumerated_trace_reason():
    """A live worker leaves either funnel unseated only by a NAMED door.

    `_push_worker` seats a worker or returns; `_fill` fires a job or
    `continue`s to the next pop.  Every one of those early exits is a
    worker that is live (or just retired) and holds no seat afterwards,
    and the trace's two vocabularies (`sched_trace.PUSH_OUTCOMES`,
    `POP_CAUSES`) are the enumeration of why.  STRUCTURAL SINCE
    2026-10-03 (S10): every `return` of the push and every `continue` of
    the fill must be labelled by its own `if on: trace.push/pop(...)`
    with a reason from that vocabulary, in the vocabulary's order, once
    each -- an exit added without a label, or labelled with an
    unenumerated reason, fails here.  The fall-through paths are the
    seat (`reseat_price` / `first_seat`, one `heappush`) and the fire
    (`fired`, one `submit`).
    """
    tree = _tree(engine)
    functions = {node.name: node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)}
    push, fill = functions["_push_worker"], functions["_fill"]
    checks = _h3_support.Checks("every funnel exit is enumerated")
    checks.equal("_push_worker's returns, labelled in order",
                 _exit_reasons(push, ast.Return, "push"),
                 list(sched_trace.PUSH_OUTCOMES[:-2]))
    checks.equal("_fill's continues, labelled in order",
                 _exit_reasons(fill, ast.Continue, "pop"),
                 list(sched_trace.POP_CAUSES[:-1]))
    for name, function, foreign in (("_push_worker", push, ast.Continue),
                                    ("_fill", fill, ast.Return)):
        checks.equal(f"{name} exits no other way", sorted(
            type(node).__name__ for node in ast.walk(function)
            if isinstance(node, (foreign, ast.Break, ast.Raise))), [])

    def calls(function: ast.FunctionDef, attr: str) -> int:
        return sum(1 for node in ast.walk(function)
                   if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Attribute)
                   and node.func.attr == attr)

    checks.equal("the push seats in one place", calls(push, "heappush"), 1)
    checks.equal("the fill fires in one place", calls(fill, "submit"), 1)
    seat_labels = {node.value for node in ast.walk(push)
                   if isinstance(node, ast.Constant)
                   and node.value in sched_trace.PUSH_OUTCOMES[-2:]}
    checks.equal("the seat path's two labels",
                 seat_labels, set(sched_trace.PUSH_OUTCOMES[-2:]))
    checks.check("the fire path's label", "fired" in {
        node.value for node in ast.walk(fill)
        if isinstance(node, ast.Constant)})
    checks.assert_clean()


# ------------------------------------------- every fact is a re-arm or terminal

def test_every_folded_fact_emits_a_key_or_declares_itself_terminal():
    """The law `AttemptFact` broke for the whole of holo3's life.

    A fold that changes a cell and emits no key can only ever re-arm
    work at BIRTH; anything already standing sleeps through it.  That
    is what the residue ladder was made of, and it is why every row
    below `tiles.scan` had drifted into subscribing to `tiles.scan`'s
    own reads instead.  So: a fact type either emits a key or is on the
    allowlist with its reason, and nothing else compiles.

    The emission is read the way SCHEDULE.md is generated — by
    following the fold's own calls for `KEY_*` constants — so a fold
    that gains a key family is caught here and in the table at once.
    """
    dispatch = schedule.fold_dispatch()
    allowed = dict(TERMINAL_FACTS)
    checks = _h3_support.Checks("every fold re-arms or is terminal")
    for fact_name in sorted(dispatch):
        families = schedule.write_families(dispatch[fact_name])
        checks.check(
            f"{fact_name} emits a key or is allowlisted",
            bool(families) or fact_name in allowed,
            "a fold that wakes nobody can only re-arm work at birth")
    checks.equal("allowlisted types that DO emit a key",
                 tuple(sorted(name for name in allowed
                              if schedule.write_families(
                                  dispatch.get(name, "")))),
                 ())
    checks.equal("allowlisted types nothing dispatches",
                 tuple(sorted(set(allowed) - set(dispatch))), ())
    checks.assert_clean()
    assert all(reason for reason in allowed.values()), (
        "an allowlist entry without a reason is a lost re-arm with "
        "paperwork")


# ------------------------------------------------------ no two identical reads

def _armed_engine() -> engine._Engine:
    """A store with one placed, read window and one failed tile-stream.

    Enough for the three payload rows to exist at once, which is all
    the law below needs: `tiles.scan` and `tiles.union` are born by the
    evidence, `tiles.retry`, `tiles.local`, `tiles.planek`, `tiles.swim`
    and `tiles.uplift` by the verdict.
    """
    instance = _h3_facts.new_engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.placement())
    instance._ingest(_h3_facts.evidence())
    cover = instance.window_cover_tiles(_h3_facts.WINDOW_ID)
    assert cover, "the evidence must cover a tile for the payload rows"
    page, ty, tx, capture_id, level_index = cover[0]
    instance._ingest(data.AttemptFact(
        page=page, ty=ty, tx=tx,
        stream_id=instance.row.streams[0].stream_id,
        stage="scan", outcome="attempted_failed", n_informative=1000,
        n_iters=60, syndrome_ok=False, crc_ok=False,
        components=((capture_id, level_index),),
        generation=instance.tile_lane_generation(cover[0])))
    return instance


def test_no_two_rows_hold_the_same_read_set_for_one_subject():
    """THE regression, stated as a law.

    `tiles.retry`'s reads were literally `tiles.scan`'s, at the same
    price, so the two rows woke together and decoded the SAME cut
    concurrently — 65 % of scan's re-fires on sheet H decoded a cut a
    retry already had.  Two different rows holding an identical
    non-empty read set means one of them is subscribed to the other's
    inputs rather than to its output.
    """
    instance = _armed_engine()
    by_reads: dict[tuple, set[str]] = {}
    for (plugin, _subject), worker in instance._bookmarks.items():
        if worker.reads:
            by_reads.setdefault(tuple(worker.reads), set()).add(plugin)
    clashes = {reads: sorted(plugins)
               for reads, plugins in by_reads.items() if len(plugins) > 1}
    assert not clashes, (
        f"rows sharing an identical read set: "
        f"{sorted(tuple(names) for names in clashes.values())}")
    retry = [worker for (plugin, _s), worker in instance._bookmarks.items()
             if plugin == "tiles.retry"]
    assert retry and all(len(worker.reads) == 1 for worker in retry), (
        "the retry row reads its own baseline verdict and nothing else")


#: The residue rows whose work is per tile-LANE: `tiles.local` since
#: 2026-09-21, `tiles.swim` since 2026-10-03.  `tiles.planek` is NOT one
#: of them -- its search is genuinely per plane.
TILE_LANE_ROWS: tuple[str, ...] = ("tiles.local", "tiles.swim")


def test_the_colour_residue_rows_hold_one_bookmark_per_tile_lane(
        decode_color_w8):
    """The siblings are gone, on a real colour decode.

    `tiles.local` was subjected per tile-STREAM while its work — the
    covering windows' whole colour head, re-fitted — is per tile-LANE,
    and `tiles.swim` the same way until 2026-10-03 (its three-plane
    affine search and the head read through it never touch a stream).
    Every seated subject of either row on a colour page therefore names
    a tile-lane, and C, M and Y of one tile name the same one.
    """
    seated = {(event.plugin, event.subject)
              for event in decode_color_w8.events
              if isinstance(event, data.WorkerSeated)
              and event.plugin in TILE_LANE_ROWS}
    assert any(plugin == "tiles.local" for plugin, _subject in seated), (
        "the colour sim must reach the residue ladder")
    streams = {stream.stream_id for stream in resolve_format_ref(
        decode_color_w8.format_ref).streams}
    assert len(streams) == 3
    for plugin, subject in seated:
        assert len(subject) == 4, (plugin, subject)
        assert not streams.intersection(
            part for part in subject if isinstance(part, str)), (
            f"a stream id in a {plugin} subject is the sibling bug "
            f"coming back")


# ------------------------------------------------------------------- INV-G1

def test_a_generation_bump_never_happens_without_a_scan_wake(monkeypatch):
    """INV-G1, the invariant the narrowed residue reads rest on.

    Every `_advance_tile_lanes` call must sit inside a fold that ALSO
    emits a key `tiles.scan` subscribes to over the same cover.  Break
    it and a generation moves with the chain head asleep, so the head
    never re-decodes, never publishes a fresh verdict, and every rung
    that reads only verdicts freezes — silently, and for the rest of
    the run.
    """
    instance = _h3_facts.new_engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.placement())
    bumped: list[tuple] = []
    original = engine._Engine._advance_tile_lanes

    def spy(self, keys):
        bumped.extend(sorted(keys))
        return original(self, keys)

    monkeypatch.setattr(engine._Engine, "_advance_tile_lanes", spy)
    # ALL THREE BUMP PATHS, because one of them is the colour one the
    # whole residue depends on: the K evidence fold, the colour row's,
    # and the ctx outcome's nested evidence folds (2026-09-21 review).
    for fact in (_h3_facts.evidence(), _h3_facts.color_row(),
                 _h3_facts.ctx_outcome()):
        bumped.clear()
        changed, keys, _kind = instance._fold(fact)
        assert changed and bumped, (
            f"{type(fact).__name__} must advance its own cover")
        emitted = set(keys)
        for cover in bumped:
            assert set(tiles_sched._scan_reads(instance, cover)) & emitted, (
                f"{cover} advanced with no key the chain head holds "
                f"({type(fact).__name__})")


# ------------------------------------------------------------ retire is monotone

#: The UNPLACED window both benches carry beside the placed one: its
#: extent sits inside tile (0, 0), so the pose-free done projection
#: covers it once that tile is certified and a pose revision can take
#: it back.
UNPLACED_WID = (_h3_facts.CAPTURE_ID, 0, 0, (0, 0, 16, 16))


def _drive_latch(instance: engine._Engine, driver: tuple[object, ...]
                 ) -> tuple[dict[tuple, str], list[bool], list[str | None]]:
    """Fold `driver` and consult every armed row's retire after each fact.

    Returns the clauses seen true (first cause per subject), the
    unplaced window's done verdict and `place`'s stage for it after each
    fact; fails through `Checks` if any clause seen true reads None
    again.
    """
    subjects = sorted(
        ((plugin, worker.subject) for (plugin, _s), worker
         in instance._bookmarks.items()), key=repr)
    assert subjects, "the bench must arm some rows"
    place_row = engine.DESCRIPTOR_BY_NAME["place"]
    seen: dict[tuple, str] = {}
    done: list[bool] = []
    stages: list[str | None] = []
    checks = _h3_support.Checks("retire latches")
    for fact in driver:
        instance._ingest(fact)
        for plugin, subject in subjects:
            cause = engine.DESCRIPTOR_BY_NAME[plugin].retire(
                instance, subject)
            key = (plugin, repr(subject))
            if key in seen:
                checks.check(f"{plugin} stays retired",
                             cause is not None,
                             f"was {seen[key]!r}, now None")
            elif cause is not None:
                seen[key] = cause
        done.append(instance.window_extent_done(UNPLACED_WID))
        stages.append(place_row.stage(instance, UNPLACED_WID))
    checks.assert_clean()
    return seen, done, stages


def test_no_row_s_retire_clause_can_come_true_and_then_false():
    """Retire is consulted at every WAKE, so it may only latch.

    A clause that can go false again would kill a live worker at the
    first wake that sampled it high.  This drives a rising certificate
    frontier — the quantity every retire clause in the tree reads — with
    an adopted POSE REVISION in the middle (2026-10-03): the revision is
    the fact that can take a derived geometry back, which is why the
    done gate left `retire`.  The bench carries an UNPLACED window on
    the placed one's cells, and asserts the path is really walked: it
    reads done after the first certificate (place's stage suppresses
    it), OPEN after the revision (the stage is back), done again at the
    end -- and its place row's clause stays None throughout.
    """
    instance = _armed_engine()
    instance._ingest(_h3_facts.survey())
    instance._ingest(_h3_facts.window(wid=UNPLACED_WID, ordinal=5))
    driver = (_h3_facts.certificate(0, 0, 0), _h3_facts.certificate(0, 0, 1),
              _h3_facts.refine_outcome(adopted=True, shift=-240.0),
              _h3_facts.certificate(0, 1, 0), _h3_facts.certificate(0, 1, 1))
    seen, done, stages = _drive_latch(instance, driver)
    assert done == [True, True, False, False, True], (
        "the unplaced window is judged done, re-opened by the revision, "
        "and done again")
    assert [stage is None for stage in stages] == done, (
        "place's stage suppresses exactly while the window reads done")
    assert ("place", repr(UNPLACED_WID)) not in seen, (
        "done is not a retire clause since 2026-10-03")
    assert {plugin for plugin, _subject in seen} >= {
        "place", "refine", "tiles.scan", "tiles.retry", "tiles.local"}, (
        "the latch was observed on the K rows, not passed vacuously")


def _color_latch_engine() -> engine._Engine:
    """The colour sim's row on the in-memory engine: one placed window
    over a 2x2-tile reach, its colour evidence, a scan failure on every
    stream of every tile -- `tiles.planek` per stream, `tiles.swim` and
    `tiles.local` per tile-lane, `refine.color` on the window -- and the
    unplaced window beside it."""
    request = dataclasses.replace(_h3_facts.new_engine()._request,
                                  format_ref=_h3_sims.COLOR_FORMAT_REF)
    instance = engine._Engine(request, [])
    span = 2 * geometry.TILE_CELLS
    wid = (_h3_facts.CAPTURE_ID, 0, 0, (0, 0, span, span))
    cells = _h3_facts.tile_cells(span)
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.survey())
    instance._ingest(_h3_facts.window(wid, ordinal=0))
    instance._ingest(dataclasses.replace(
        _h3_facts.placement(wid), local_cells_yx=cells.astype(np.int16)))
    instance._ingest(dataclasses.replace(
        _h3_facts.color_row(), page_cells_yx=cells,
        values=np.zeros((cells.shape[0], 3), np.float32)))
    instance._ingest(_h3_facts.window(UNPLACED_WID, ordinal=5))
    for ty, tx in ((0, 0), (0, 1), (1, 0), (1, 1)):
        lane = (0, ty, tx, _h3_facts.CAPTURE_ID, 0)
        for stream in instance.row.streams:
            instance._ingest(data.AttemptFact(
                page=0, ty=ty, tx=tx, stream_id=stream.stream_id,
                stage=tiles.STAGE_SCAN, outcome=tiles.OUTCOME_FAILED,
                n_informative=1000, n_iters=60, syndrome_ok=False,
                crc_ok=False, components=((_h3_facts.CAPTURE_ID, 0),),
                generation=instance.tile_lane_generation(lane)))
    return instance


def test_the_colour_rows_retire_clauses_latch_too():
    """The same law on the colour sim's row, where the residue rows live.

    The K bench has no colour subjects, so `tiles.planek`, `tiles.swim`
    and `refine.color` -- the rows whose clauses read per-stream
    certificates over a reach a revision moves -- were never driven
    (2026-10-03, S10).  Here every stream of a 2x2-tile reach is
    certified one by one with an adopted revision of the placed window
    after the first tile closes: the unplaced window reads done, the
    revision re-opens it, the last certificate closes it again.  The
    revision lands while `refine.color` is still live, which is the
    only order production allows (a retired refine writes no
    RefineOutcome; `color_refine._color_refine_retire`).
    """
    instance = _color_latch_engine()
    streams = instance.row.streams
    wid = next(iter(instance.placements()))

    def certificate(ty: int, tx: int, index: int) -> data.Certificate:
        stream = streams[index]
        return data.Certificate(
            page=0, ty=ty, tx=tx, stream_id=stream.stream_id,
            user_bits=np.zeros(stream.user_bits, np.uint8),
            source="tiles/scan")

    revision = refine.RefineOutcome(window_id=wid, revision=refine.Revision(
        adopted=True, reason="probe",
        affine=(4.0, 0.0, -240.0, 0.0, 4.0, -240.0)))
    first_tile = tuple(certificate(0, 0, index)
                       for index in range(len(streams)))
    rest = tuple(certificate(ty, tx, index)
                 for ty, tx in ((0, 1), (1, 0), (1, 1))
                 for index in range(len(streams)))
    seen, done, stages = _drive_latch(
        instance, first_tile + (revision,) + rest)
    n_first = len(first_tile)
    assert done[n_first - 1] and not done[n_first] and done[-1], (
        f"done after the first tile, re-opened by the revision, done at "
        f"the end: {done}")
    assert [stage is None for stage in stages] == done
    retired = {plugin for plugin, _subject in seen}
    assert retired >= {"tiles.planek", "tiles.swim", "refine.color",
                       "tiles.local", "tiles.scan", "tiles.retry"}, (
        f"the colour residue rows' clauses must be observed true: "
        f"{sorted(retired)}")
