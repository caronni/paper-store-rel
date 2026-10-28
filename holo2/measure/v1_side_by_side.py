#!/usr/bin/env python
"""holo2 and v1 on the SAME rendered fixture pages, labeled — BY PATH.

    env/bin/python holo2/measure/v1_side_by_side.py [--arms A,B]
                                                    [--v1-workers N]
                                                    [--skip-cli]
                                                    [--cli-timeout S]

NOT A TEST and not collectable as one — same standing as
``index_equivalence.py`` and ``or5_or7_census.py``.

H4-PLAN §4 item 2: *"Placement counts within the v1 envelope, labeled —
run src/holo's receiver on the SAME rendered fixtures (they are format-v1
pages; v1 reads them) and record accepted-pose / certificate counts side
by side. Labeled comparison, not a bar (WORKPLAN:359-361)."* This driver
produces that table.

**IT IS A COMPARISON AND NOT A BAR, and the reason is the stopping rule.**
holo2 closes at solvable: the fountain verifies and the run stops, so the
tiles past K are never worked. v1 harvests: it drives its plan to
exhaustion and certifies what it can. On the real sheet the same
distinction reads 1,930 (Xerox) / 1,940 (HP) of 1,961 for v1 at full
harvest against holo2's ~1,357 — **different stopping rules, same bytes**.
Both sides here are therefore driven as far as their own CLI can drive
them (holo2 ``--complete``; v1 ``--complete --mopup --refine``, its full
harvest), and the table below still may not be read as one side beating
the other.

THE OPERATOR PATH, which was a FINDING until 2026-08-22
--------------------------------------------------------------------
This driver used to record an informative REFUSAL here: ``./confetti.py
decode`` selected its geometry from the devices registry (``--coding ID
[--printer ID]``, resolved through ``holo.cli.make_spec``) and had no
flag anywhere for a tile grid or a media size, while the fixtures were
v1 identities on searched synthetic media — so the smallest row the CLI
could name for the channel page was ``c2-r0700@3328x2304`` (A4, 52x36
tiles) against the page's own ``c2-r0700@512x512``. A geometry mismatch
is a different seed, hence a different keystream, address-counter domain
and metadata word; the attempt was run anyway and TIMED OUT at 600 s on
both arms, and the measurement went into ``holo2/docs/MEASUREMENTS.md``
as such.

**That finding is SUPERSEDED** (package C4, RULINGS G5, 2026-08-22). The
fixtures are v2 identities now, and ``src/holo``'s decode parser takes
``--format ID`` — one flag, the whole identity, no printer and no paper
argument (FORMAT-SPACE §10). So the operator path can name this exact
page: ``./confetti.py decode <capture>.png --scan-dpi … --format
c2-k-r0700@8x8``. The arm below spells it that way and records whatever
the CLI does with it; it is a real decode of the same pixels, not a
refusal transcript. **It has not been RUN as part of C4** — the arm is
bounded at 600 s and this package changed no receiver — so the table in
MEASUREMENTS keeps its dated supersession note and no new operator-path
number is claimed.

The SIDE-BY-SIDE itself stays in-process against v1's own
``run_receive`` with the fixture's ``FormatSpec``: not because the CLI
cannot spell the page any more, but because the comparison wants v1's
``--workers`` and its counters in this process, and it is the same door
``verdicts/test_v1_parity.py`` already uses to compare placement (it
calls ``v1_place.place_survey`` directly), one level up — the whole
receiver instead of the placer.

THE ARMS are the two decodes the verdicts already render, at their
parameters exactly — ``verdicts/_fixtures.py`` content-addresses its
renders, so the captures here are the verdicts' own cache entries, not a
re-rendering:

* ``channel`` — run channel's page (``c2-k-r0700@8x8``, the measured e032
  anisotropic warp, 2% cell error). holo2 decodes it on the FINEST-ONLY
  reading set, which is the configuration ``conftest.run_channel`` pins
  and the one ``test_v1_parity`` compares pose for pose.
* ``banded`` — run banded's page (16% cell error over the right quarter,
  which kills the t = 13 word code in those columns), on the DEFAULT
  reading set, as ``conftest.run_banded`` decodes it.

Both holo2 runs are SERIAL by the verdicts' ruling. v1 runs at
``--workers 4`` (execution-only; v1 documents its pooled kernels as
bit-identical at any worker count).
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any

# Self-locating, like ``./confetti.py``: neither package is pip-installed
# (env honesty), and a driver the operator runs BY PATH should not also
# demand a ``PYTHONPATH=`` prefix to find the tree it lives in.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE / "verdicts", _ROOT / "src", _ROOT / "holo2" / "src"):
    sys.path.insert(0, str(_path))

from _fixtures import (CHANNEL_ROTATION_DEG, CHANNEL_SCALE_YX,  # noqa: E402
                       build_page, render)

from holo2 import cli                                          # noqa: E402
from holo2.cli import real_providers                           # noqa: E402
from holo2.engine.recipe import RECIPE_V1, RECIPE_V1_FINEST    # noqa: E402
from holo2.solve.tilemap import StoreIndex                     # noqa: E402

PX_PER_DOT = 2
CADENCE = 32

#: run channel's arm and run banded's band, verbatim from
#: ``verdicts/conftest.py`` (re-declared rather than imported, following
#: ``index_equivalence.py``: a pytest ``conftest`` is not a module a
#: by-path driver should import).  ONE identity since C4 (RULINGS G5,
#: 2026-08-22), which is also what makes the operator arm below spellable.
CHANNEL_FORMAT = "c2-k-r0700@8x8"
CHANNEL_NOISE = 2.0
CHANNEL_CELL_ERROR_RATE = 0.02
BAND_ERROR_RATE = 0.16
BAND_COLUMNS = (0.75, 1.0)
BAND_WARP: dict[str, Any] = dict(rotation_deg=0.3, pitch_scale=1.003,
                                 noise_sigma=2.0)


# ---------------------------------------------------------------- the arms

def arms(work: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    """The verdicts' own two pages, at the verdicts' own parameters."""
    page = build_page(CHANNEL_FORMAT)
    built: list[dict[str, Any]] = []
    if "channel" in names:
        capture = render(page.dots, work / "channel.png",
                         px_per_dot=PX_PER_DOT, cell_dots=page.cell_dots,
                         rotation_deg=CHANNEL_ROTATION_DEG,
                         pitch_scale=CHANNEL_SCALE_YX,
                         noise_sigma=CHANNEL_NOISE,
                         cell_error_rate=CHANNEL_CELL_ERROR_RATE)
        built.append({"name": "channel", "page": page, "capture": capture,
                      "recipe": RECIPE_V1_FINEST,
                      "recipe_name": "RECIPE_V1_FINEST (finest-only)"})
    if "banded" in names:
        capture = render(page.dots, work / "banded.png",
                         px_per_dot=PX_PER_DOT, cell_dots=page.cell_dots,
                         cell_error_rate=BAND_ERROR_RATE,
                         cell_error_band=BAND_COLUMNS, **BAND_WARP)
        built.append({"name": "banded", "page": page, "capture": capture,
                      "recipe": RECIPE_V1,
                      "recipe_name": "RECIPE_V1 (default cascade)"})
    return built


# ------------------------------------------------------------------ holo2

def run_holo2(work: Path, arm: dict[str, Any]) -> dict[str, Any]:
    """One SERIAL, ``--complete`` holo2 decode; poses read off the state."""
    page, capture = arm["page"], arm["capture"]
    scans = ((capture.path, capture.dpi),)
    state = work / f"h2-state-{arm['name']}"
    request = cli.DecodeRequest(
        scans=scans, workers=1, diag_port=0, state_dir=state,
        output=work / f"h2-{arm['name']}.bin", complete=True)
    started = time.perf_counter()
    outcome, _observer = cli.decode(
        request, page.row, real_providers(page.row, scans),
        recipe=arm["recipe"], fsync=False, snapshot_every=CADENCE)
    wall = time.perf_counter() - started
    with cli.open_receiver(
            request, page.row, recipe=arm["recipe"],
            providers=real_providers(page.row, scans),
            source=cli.real_source(page.row, arm["recipe"]),
            fsync=False) as session:
        index = StoreIndex.build(session.store)
        poses, windows = len(index.poses), len(index.windows)
    return {
        "poses": poses, "windows": windows,
        "certificates": int(outcome.certified),
        "status": outcome.status,
        "payload_sha": (hashlib.sha256(outcome.payload).hexdigest()
                        if outcome.payload is not None else None),
        "commits": int(outcome.commits), "fires": int(outcome.fires),
        "wall_s": wall,
    }


# --------------------------------------------------------------------- v1

def run_v1(work: Path, arm: dict[str, Any], workers: int) -> dict[str, Any]:
    """v1's OWN receiver, whole, on the fixture's own ``FormatSpec``.

    ``production_pipeline`` is built by ``run_receive`` itself, which is
    exactly what ``cmd_decode`` does — the only thing bypassed is the
    argument parser, which has no syntax for this page's geometry.
    """
    from holo.receive import CaptureInput, ReceiveRequest, run_receive
    from holo.receive import _parallel

    _parallel.set_worker_count(workers)
    page, capture = arm["page"], arm["capture"]
    request = ReceiveRequest(
        page.spec,
        (CaptureInput(source=str(capture.path), dpi=capture.dpi),),
        state_path=work / f"v1-state-{arm['name']}.holo",
        # v1's FULL HARVEST — the CLI's ``--complete --mopup --refine``,
        # which is the stopping rule the real-sheet 1,930/1,940 anchors
        # were taken under.
        defer_fountain_close=True, run_mopup=True, run_refine=True)
    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_receive(request)
    wall = time.perf_counter() - started
    state = result.state
    counters = state.counters
    return {
        "poses": len(state.poses),
        # v1 has no durable "window" population to count: a window that
        # placed IS a pose, and one that could not is a ParkedWindowRecord
        # or nothing at all. ``regions`` is the SURVEY's, not the placer's.
        "regions": len(state.regions), "parked": len(state.parked),
        "proposals": len(state.proposals),
        "certificates": len(state.certificates),
        "status": state.status.value,
        "verified": bool(result.verified),
        "payload_sha": (hashlib.sha256(result.payload).hexdigest()
                        if result.payload is not None else None),
        "qualification": result.qualification_status.value,
        "warnings": tuple(sorted({type(item.message).__name__
                                  for item in caught})),
        "bp": {name: {"evaluations": tally.evaluations,
                      "decoder_calls": tally.decoder_calls,
                      "bp_iterations": tally.bp_iterations,
                      "crc_ok": tally.crc_ok}
               for name, tally in (("scan", counters.scan),
                                   ("union", counters.union),
                                   ("retry150", counters.retry150))},
        "wall_s": wall,
    }


def run_v1_cli(work: Path, arm: dict[str, Any], timeout: float,
               ) -> dict[str, Any]:
    """The OPERATOR path, attempted honestly: ``./confetti.py decode``.

    Recorded whatever it does.  Since C4 (RULINGS G5, 2026-08-22) the
    page HAS a name the parser accepts — ``--format`` takes the identity
    whole, geometry included — so this is the same decode as the
    in-process arm, driven the way an operator would drive it.  Before
    that it was an informative refusal: no flag existed for a tile grid,
    ``--coding`` alone selected the registry's A4 row, and the run timed
    out at the bound (see the module docstring and MEASUREMENTS).
    """
    capture = arm["capture"]
    # ``sys.executable`` rather than the shebang: ``confetti.py``'s
    # ``#!env/bin/python`` resolves against the CWD by design, and a git
    # WORKTREE has no ``env/`` of its own (it is gitignored, and lives in
    # the main checkout). The interpreter running this driver is the same
    # one, named explicitly.
    command = [
        sys.executable, str(_ROOT / "confetti.py"), "decode",
        str(capture.path),
        "--scan-dpi", str(capture.dpi),
        "--format", arm["page"].format_ref,
        "--state", str(work / f"v1-cli-{arm['name']}.holo"),
        "-o", str(work / f"v1-cli-{arm['name']}.bin"),
        "--complete", "--refine",
    ]
    started = time.perf_counter()
    try:
        finished = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            cwd=str(_ROOT))
        return {"argv": " ".join(command[2:]),
                "returncode": finished.returncode,
                "stdout": finished.stdout.strip(),
                "stderr": finished.stderr.strip(),
                "wall_s": time.perf_counter() - started}
    except subprocess.TimeoutExpired:
        return {"argv": " ".join(command[2:]), "returncode": None,
                "stdout": "", "stderr": f"TIMED OUT after {timeout:.0f} s",
                "wall_s": time.perf_counter() - started}


# --------------------------------------------------------------- the report

def print_table(rows: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 78)
    print("THE SIDE-BY-SIDE — different stopping rules, same bytes")
    print("=" * 78)
    header = (f"{'arm':<10} {'side':<6} {'poses':>6} {'certs':>6} "
              f"{'status':>10} {'payload sha12':>14} {'wall s':>8}")
    print(header)
    print("-" * len(header))
    for row in rows:
        for side in ("holo2", "v1"):
            data = row[side]
            sha = data["payload_sha"]
            print(f"{row['name']:<10} {side:<6} {data['poses']:>6d} "
                  f"{data['certificates']:>6d} {data['status']:>10} "
                  f"{(sha[:12] if sha else '—'):>14} "
                  f"{data['wall_s']:>8.1f}")
    print("-" * len(header))
    print("READ IT AS A COMPARISON, NEVER AS A BAR (WORKPLAN:359-361): "
          "holo2 stops\nat solvable, v1 harvests to plan exhaustion. "
          "Equal payload SHAs are the\nclaim; equal certificate counts "
          "are not, and were never expected.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arms", default="channel,banded",
                        help="comma-separated arm names (channel, banded; "
                             "default: both)")
    parser.add_argument("--v1-workers", type=int, default=4, metavar="N",
                        help="v1's pooled-kernel worker count "
                             "(execution-only; default: 4)")
    parser.add_argument("--skip-cli", action="store_true",
                        help="do not attempt the ./confetti.py decode "
                             "operator path")
    parser.add_argument("--cli-timeout", type=float, default=600.0,
                        metavar="SECONDS",
                        help="wall bound on each ./confetti.py attempt "
                             "(default: 600)")
    args = parser.parse_args(argv)

    names = tuple(name.strip() for name in args.arms.split(",")
                  if name.strip())
    unknown = set(names) - {"channel", "banded"}
    if unknown:
        parser.error(f"unknown arm(s): {', '.join(sorted(unknown))}")

    print("v1 SIDE-BY-SIDE — the verdicts' own two pages, both receivers.")
    print(f"  arms: {', '.join(names)}")
    print("  holo2: serial (--workers 1), --complete")
    print(f"  v1:    --workers {args.v1_workers}, full harvest "
          f"(--complete --mopup --refine)")

    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="v1-side-by-side-") as raw:
        work = Path(raw)
        built = arms(work, names)

        for arm in built:
            print(f"\n  --- arm '{arm['name']}' "
                  f"({arm['page'].spec.spec_id}, "
                  f"{arm['page'].spec.layout.tiles_yx[0]}x"
                  f"{arm['page'].spec.layout.tiles_yx[1]} tiles, "
                  f"{arm['page'].tiles_per_page} tiles/page, "
                  f"K = {arm['page'].k_total}) ---")
            print(f"      capture {arm['capture'].path.name} at "
                  f"{arm['capture'].dpi:g} dpi; holo2 recipe "
                  f"{arm['recipe_name']}")

            if not args.skip_cli:
                cli_row = run_v1_cli(work, arm, args.cli_timeout)
                print(f"      OPERATOR PATH: ./confetti.py {cli_row['argv']}")
                print(f"        exit {cli_row['returncode']} after "
                      f"{cli_row['wall_s']:.1f} s")
                for stream in ("stdout", "stderr"):
                    for line in cli_row[stream].splitlines():
                        print(f"        {stream}: {line}")

            h2 = run_holo2(work, arm)
            print(f"      holo2: {h2['status']}, {h2['poses']} poses of "
                  f"{h2['windows']} window records, "
                  f"{h2['certificates']} certificates, {h2['commits']} "
                  f"commits, {h2['fires']} fires, {h2['wall_s']:.1f} s")
            v1 = run_v1(work, arm, args.v1_workers)
            print(f"      v1:    {v1['status']}, {v1['poses']} poses "
                  f"({v1['proposals']} proposals, {v1['parked']} parked), "
                  f"{v1['certificates']} certificates, "
                  f"{v1['wall_s']:.1f} s "
                  f"(qualification {v1['qualification']}; warned "
                  f"{', '.join(v1['warnings']) or 'not at all'})")
            print(f"      v1 durable BP ledger (holo2 has no equivalent — "
                  f"see OR-5): {v1['bp']}")
            payload_sha = hashlib.sha256(arm["page"].payload).hexdigest()
            for side, data in (("holo2", h2), ("v1", v1)):
                if data["payload_sha"] is None:
                    print(f"      {side}: NO PAYLOAD — the volume did not "
                          f"close")
                elif data["payload_sha"] != payload_sha:
                    failures.append(
                        f"arm '{arm['name']}' {side}: recovered payload "
                        f"is NOT the emitted payload")
            rows.append({"name": arm["name"], "holo2": h2, "v1": v1,
                         "emitted_sha": payload_sha})

    print_table(rows)
    for row in rows:
        if (row["holo2"]["payload_sha"] and row["v1"]["payload_sha"]
                and row["holo2"]["payload_sha"] == row["v1"]["payload_sha"]):
            print(f"  arm '{row['name']}': SAME BYTES on both sides "
                  f"({row['emitted_sha'][:12]}…).")

    if failures:
        print("\nFAILED:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("\nSIDE-BY-SIDE COMPLETE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
