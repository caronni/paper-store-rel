"""Fold-time records for the two evidence cells that carry a loss.

A SIBLING OF ``sched_trace``, split at the 1000-line seam along the one
functional joint the instrument has: ``sched_trace`` watches the
SCHEDULER (wakes, seats, fires), this module watches the STORE's answer
to one question the scheduler never asks — *did the value actually get
better?*

Two cells are recorded, and they are the two the engine has no quality
order for:

* ``ColorEvidenceRow`` (``store_folds._fold_color_row``) — one row per
  placed window per lane per page, carrying the marginal LLRs the tile
  decoder reads and a ``heldout_logloss``.  Its fold is bare
  change-detection last-write-wins: the newest row stands, better or
  worse (API.md, "NOT converted" — addendum 14's fourth decision cell,
  no disposition ruled).
* ``WindowEvidence`` (``_fold_evidence``) — the K analogue, whose
  ``read_changed`` leg is exactly ``ctx_adopted`` / ``heldout_logloss``
  / ``printed_llr``, again last-write-wins.

The loss is not decoration in either: ``tiles.k_candidates`` and
``tiles.color_candidates`` put it FIRST in the ownership order key, and
``lib/owners.freeze_page_owners`` gives each contested payload cell to
the first writer in that order.  A loss that moves can move a cell's
owner, which changes the tile's cut, which is a different decode input.

MEASUREMENT ONLY, and DEFAULT OFF with the rest of the instrument: the
recorder is constructed only when ``HOLO3_SCHED_TRACE=1`` armed the
trace, every call site in ``store_folds`` sits behind one
``if sched_trace.TRACE.enabled:``, and nothing here is read by a fold
decision.  A record is written whether the fold adopted the fact or
refused it, so a refusal rate is readable off the same file.

THREADING: ``note`` runs inside the fold, on the engine's merge thread,
and ``flush`` runs immediately after it in ``_Engine._ingest`` on that
same thread.  Between the two the records sit in a list because the
subscriber count they want lives on the ENGINE (``_index``) and the
fold that produced them cannot see it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["FoldRecorder", "NullFolds", "FOLD_KINDS", "value_stats",
           "PENDING_CAP"]

#: The two cells recorded.  Names are the wire values of the ``kind``
#: column in ``folds.jsonl``.
FOLD_KINDS: tuple[str, ...] = ("color_row", "evidence")

#: ``flush`` is called after every fold, so the list never holds more
#: than one fact's records -- except for the nested folds a
#: ``CtxOutcome`` drives (one per standing window of a region, hundreds).
#: The cap is a leak guard for a caller that forgets to flush, never a
#: sampling rule: crossing it writes the records with no subscriber
#: count rather than dropping them.
PENDING_CAP = 4096


def _cell_keys(cells: np.ndarray | None) -> np.ndarray:
    """One int64 per (y, x) row, for set arithmetic over cell addresses."""
    if cells is None or len(cells) == 0:
        return np.zeros(0, np.int64)
    flat = np.asarray(cells, np.int64).reshape(-1, 2)
    return (flat[:, 0] << 32) | (flat[:, 1] & 0xFFFFFFFF)


def value_stats(standing_cells: np.ndarray | None,
                standing_values: np.ndarray | None,
                new_cells: np.ndarray | None,
                new_values: np.ndarray | None) -> dict[str, Any]:
    """How far the decoder input moved, measured ON THE COMMON CELLS.

    A re-fit may hand back a row over a different cell set (the emission
    mask moves with the head), so comparing the two arrays elementwise
    would be comparing different cells.  The cells present in both are
    matched by address and only those are differenced; the cells that
    came or went are counted separately.  A row with no standing
    predecessor reports ``None`` fractions and the full count as added.
    """
    new_key = _cell_keys(new_cells)
    n_new = int(new_key.size)
    if standing_cells is None or standing_values is None:
        return {"n_values": n_new, "n_common": 0,
                "values_changed_fraction": None,
                "values_max_abs_delta": None,
                "values_mean_abs_delta": None,
                "cells_changed": True,
                "n_cells_added": n_new, "n_cells_removed": 0}
    old_key = _cell_keys(standing_cells)
    common, old_at, new_at = np.intersect1d(
        old_key, new_key, assume_unique=False, return_indices=True)
    added = n_new - int(common.size)
    removed = int(old_key.size) - int(common.size)
    if common.size == 0:
        return {"n_values": n_new, "n_common": 0,
                "values_changed_fraction": None,
                "values_max_abs_delta": None,
                "values_mean_abs_delta": None,
                "cells_changed": bool(added or removed),
                "n_cells_added": added, "n_cells_removed": removed}
    old = np.asarray(standing_values, np.float64).reshape(
        len(old_key), -1)[old_at]
    new = np.asarray(new_values, np.float64).reshape(
        len(new_key), -1)[new_at]
    delta = np.abs(new - old)
    # NaN is a value here: a cell that was NaN and is not (or the other
    # way) is a change, and `nan != nan` would otherwise read as one
    # anyway while poisoning the max and the mean.
    both_nan = np.isnan(old) & np.isnan(new)
    differs = ~(both_nan | (old == new))
    finite = delta[np.isfinite(delta)]
    return {
        "n_values": n_new,
        "n_common": int(common.size),
        "values_changed_fraction": float(np.mean(np.any(differs, axis=1))),
        "values_max_abs_delta": (float(finite.max()) if finite.size else 0.0),
        "values_mean_abs_delta": (float(finite.mean()) if finite.size
                                  else 0.0),
        "cells_changed": bool(added or removed),
        "n_cells_added": added, "n_cells_removed": removed}


class NullFolds:
    """The disarmed recorder.  Every door is a no-op."""

    enabled = False

    def note(self, *args: Any, **kwargs: Any) -> None:
        return None

    def flush(self, index: Any) -> None:
        return None

    def summary(self) -> dict[str, Any]:
        return {}

    def close(self) -> None:
        return None


class FoldRecorder:
    """Armed: one JSON line per recorded fold in ``folds.jsonl``."""

    enabled = True

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._fh = (self.out_dir / "folds.jsonl").open("a", encoding="utf-8")
        self._pending: list[dict[str, Any]] = []
        self._rows = 0
        self._counts: dict[tuple[str, str], int] = {}
        self._direction: dict[tuple[str, str], int] = {}
        self._overflows = 0

    # ------------------------------------------------------------ note

    def note(self, kind: str, key: tuple, changed: bool,
             standing: object | None, fact: object,
             standing_cells: np.ndarray | None,
             standing_values: np.ndarray | None,
             new_cells: np.ndarray | None,
             new_values: np.ndarray | None,
             keys: tuple = (), reason: str = "",
             wall_s: float = 0.0, cover: tuple = ()) -> None:
        """Record one fold of one evidence cell.

        ``standing``/``fact`` are the two cell values; only their
        ``heldout_logloss`` is read here.  The arrays are passed
        separately because the K cell's decoder input is
        ``printed_llr`` while the colour cell's is ``values``.

        ``cover`` is the tile keys this row covers AFTER the fold (the
        standing row's, when the fold refused).  It is the only way to
        ask offline which tiles are CONTESTED — two rows of one lane
        over one tile — because only a contested tile can change its
        cut when a loss moves.
        """
        standing_loss = _loss_of(standing)
        new_loss = _loss_of(fact)
        stats = value_stats(standing_cells, standing_values,
                            new_cells, new_values)
        direction = _direction(standing_loss, new_loss)
        record: dict[str, Any] = {
            "wall_s": round(float(wall_s), 6),
            "kind": kind,
            "key": list(key),
            "changed": bool(changed),
            "reason": reason,
            "standing_loss": standing_loss,
            "new_loss": new_loss,
            "loss_delta": (None if (standing_loss is None or new_loss is None)
                           else new_loss - standing_loss),
            "loss_direction": direction,
            "keys": [list(one) if isinstance(one, tuple) else one
                     for one in keys],
            "cover": [list(one) if isinstance(one, tuple) else one
                      for one in cover],
            "n_subscribers": None}
        record.update(stats)
        self._counts[(kind, "records")] = \
            self._counts.get((kind, "records"), 0) + 1
        self._counts[(kind, "changed" if changed else "refused")] = \
            self._counts.get((kind, "changed" if changed else "refused"),
                             0) + 1
        self._direction[(kind, direction)] = \
            self._direction.get((kind, direction), 0) + 1
        self._pending.append(record)
        if len(self._pending) >= PENDING_CAP:
            self._overflows += 1
            self.flush(None)

    # ----------------------------------------------------------- flush

    def flush(self, index: Any) -> None:
        """Resolve the wake fan-out and write the pending records.

        ``index`` is the engine's ``_index`` (fact key -> subscriber
        set) or ``None`` when the caller has none; the count is the
        number of worker bookmarks the record's keys would bump, summed
        over the keys, which is the fan-out ``_touch`` is about to pay.
        """
        if not self._pending:
            return
        for record in self._pending:
            if index is not None:
                total = 0
                for one in record["keys"]:
                    subscribers = index.get(
                        tuple(one) if isinstance(one, list) else one)
                    total += 0 if not subscribers else len(subscribers)
                record["n_subscribers"] = total
            self._fh.write(json.dumps(record) + "\n")
            self._rows += 1
        self._pending.clear()

    # --------------------------------------------------------- summary

    def summary(self) -> dict[str, Any]:
        return {
            "rows": self._rows,
            "pending": len(self._pending),
            "overflows": self._overflows,
            "by_kind": _two_key(self._counts),
            "loss_direction": _two_key(self._direction)}

    def close(self) -> None:
        self.flush(None)
        self._fh.flush()
        self._fh.close()


def _loss_of(cell: object | None) -> float | None:
    if cell is None:
        return None
    value = getattr(cell, "heldout_logloss", None)
    return None if value is None else float(value)


def _direction(standing: float | None, new: float | None) -> str:
    """The five answers the A/B needs to tell apart."""
    if standing is None:
        return "first"
    if new is None:
        return "unknown"
    if new < standing:
        return "improved"
    if new > standing:
        return "worsened"
    return "equal"


def _two_key(counts: dict[tuple[str, str], int]) -> dict[str, Any]:
    table: dict[str, dict[str, int]] = {}
    for (outer, inner), count in sorted(counts.items()):
        table.setdefault(outer, {})[inner] = count
    return table
