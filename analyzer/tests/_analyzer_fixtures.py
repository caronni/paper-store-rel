"""Shared, process-memoised test inputs for the W1a modules.

The sheet-I snapshot peaks at ~6.5 GB RSS, so it is loaded ONCE per test
process and handed to every module that asks (a module-scoped fixture in
three separate files would load it three times; a plain memo here does
not care which module asks first).

Underscore-prefixed so pytest never collects it as a test module, and
NOT a `conftest.py` so a parallel wave can add one without a collision.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]

#: The sheet-I resume-3 run dir (PLAN §3, Q1).
I_RUN_DIR = Path("/tmp/I/holo3-I-resume-3-run")
I_GEN_DIR = REPO / "scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm"
I_PAYLOAD = I_GEN_DIR / "payload-counting.bin"

#: Sheet J, the fragment sheet (PLAN §3, Q2).
J_RUN_DIR = REPO / "scratch/J-run.54028"
J_GEN_DIR = REPO / "scratch/c2-cmy8-r0547-q06860-1MiB"
J_PAYLOAD = J_GEN_DIR / "payload-counting.bin"

needs_i_run = pytest.mark.skipif(
    not (I_RUN_DIR / "facts.npz").exists() or not I_PAYLOAD.exists(),
    reason=f"sheet-I run dir {I_RUN_DIR} (or its generation dir) is absent")

needs_j_run = pytest.mark.skipif(
    not (J_RUN_DIR / "facts.npz").exists() or not J_PAYLOAD.exists(),
    reason=f"sheet-J run dir {J_RUN_DIR} (or its generation dir) is absent")

_MEMO: dict[str, Any] = {}


def i_inputs() -> Any:
    from analyzer import inputs
    hit = _MEMO.get("i_inputs")
    if hit is None:
        hit = inputs.load_run(I_RUN_DIR)
        _MEMO["i_inputs"] = hit
    return hit


def i_truth() -> Any:
    from analyzer import truth
    hit = _MEMO.get("i_truth")
    if hit is None:
        run = i_inputs()
        hit = truth.load_truth(I_GEN_DIR, I_PAYLOAD, run.row,
                               max(run.live_pages) + 1,
                               format_ref=run.format_ref)
        _MEMO["i_truth"] = hit
    return hit


def i_census() -> Any:
    """The census — BLIND since 2026-09-04 (it takes no truth).

    `i_truth()` is still here for the scoring tests, and it is the only
    thing that opens the payload.
    """
    from analyzer import residue
    hit = _MEMO.get("i_census")
    if hit is None:
        hit = residue.census(i_inputs())
        _MEMO["i_census"] = hit
    return hit


def j_inputs() -> Any:
    from analyzer import inputs
    hit = _MEMO.get("j_inputs")
    if hit is None:
        hit = inputs.load_run(J_RUN_DIR)
        _MEMO["j_inputs"] = hit
    return hit


# --------------------------------- sheet I WITHOUT its run dir (2026-09-04)
# The run dir lives in /tmp and does not survive a reboot; the GENERATION
# dir is in scratch/ and does.  Everything the fountain-consistency and
# localization tests need is in the generation dir alone — the printed
# identity plus the emitted payload re-encoded through holo1's own
# arithmetic — so those tests are gated on it and not on the run.

#: The fossil identity sheet I was printed as (manifest `spec_id`).
I_FORMAT_REF = "L:c2-cmy8-r0700-p120-x1@3392x2368"

needs_i_generation = pytest.mark.skipif(
    not I_PAYLOAD.exists(),
    reason=f"sheet-I generation dir {I_GEN_DIR} is absent")


def i_format_row() -> Any:
    from holo3.format.identity import resolve_format_ref
    hit = _MEMO.get("i_format_row")
    if hit is None:
        hit = resolve_format_ref(I_FORMAT_REF)
        _MEMO["i_format_row"] = hit
    return hit


def i_emitted_user_bits() -> dict:
    """Sheet I's WHOLE certificate set — every address, from the payload.

    `measure.crop_parity._gt.reconstruct` (via `analyzer.truth`) re-encodes
    the emitted payload through holo1's generation arithmetic, which is an
    INDEPENDENT implementation of the fountain from the holo3 one the
    close and the consistency check call.  That is what makes these
    fixtures a test rather than a tautology.

    The returned mapping is shared and read-only by convention: copy the
    vectors you intend to poison.
    """
    from analyzer import truth as truth_mod
    hit = _MEMO.get("i_emitted_user_bits")
    if hit is None:
        gt = truth_mod.load_truth(I_GEN_DIR, I_PAYLOAD, i_format_row(), 1,
                                  format_ref=I_FORMAT_REF)
        hit = {key: value for key, value in gt.user_bits.items()}
        _MEMO["i_emitted_user_bits"] = hit
        _MEMO["i_emitted_sha256"] = gt.payload_sha256
    return hit


def i_emitted_sha256() -> str:
    i_emitted_user_bits()
    return _MEMO["i_emitted_sha256"]
