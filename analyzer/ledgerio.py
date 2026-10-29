"""The ledger ON DISK — the lines, the live writer, the readers.

One row per (page, ty, tx, stream) with the per-(lane, arm) blind
diagnostics, the per-rule combination summaries and the per-rung results
(each carrying its packed exit hard vector), preceded by a header with
the seed, the knobs and the provenance (run dir, format, captures, where
the targets came from, where the knobs came from, and whether the run
was non-blind).  What the rows MEAN — the attribution, the stream x band
table, the histograms, the Markdown report and the maps — is
`analyzer.ledger`, which re-exports every name here so that the twenty
call sites and the tests still spell `ledger.iter_rows`.

STREAMED, since the memory wave of 2026-09-13.  A pass no longer holds
its rows: :class:`LedgerWriter` writes the header BEFORE the first
generation runs and appends each row as its generation folds it, so a
kill at hour three leaves the rows it had (the 2026-09-10 pass was
killed at 350 keys and 51 certificates with nothing on disk at all).
The mint of a key lands even earlier, in `mints.jsonl` beside the
ledger, because a row is only final when its whole generation has
folded.  Two consequences for every READER, here and elsewhere:

* a re-attacked key APPENDS a second row rather than replacing the
  first, so a reader takes the LAST row per key — `iter_rows_latest`;
* the last line of a killed ledger may be half-written, so a reader
  skips a line it cannot decode and COUNTS it (`ReadStats`).

ROW ORDER CHANGED WITH IT, and one downstream artefact shows it.  A
ledger used to carry one row per key in TARGET order, because a
re-attack replaced its row in place; a streamed one carries them in
FOLD order, with the re-attacks appended where they happened.  Nothing
reads a ledger positionally, but `analyzer score` writes its rows out in
the order it met them, so `score.jsonl` is in that same fold order —
which is what `score --limit N` truncates and what its maps then
decorate.  The set is unchanged; the order is not.

The final header — the counts, the stop reason, the exposure — cannot be
written on line 1 before the pass has run, so `finish` appends it as a
FOOTER line and `read_header` merges the two.  A ledger with no footer is
a partial one and says so (`partial`).

NOTHING HERE IS SCORED: a ledger is the blind record of a run (the
2026-09-04 ruling), and the bits-wrong columns are `analyzer score`'s,
computed offline from these lines plus a payload.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

from .types import LedgerRow


HEADER_TYPE = "header"
ROW_TYPE = "row"
#: The FINAL header of a streamed pass, appended when the pass ends.
#: Line 1 cannot carry the counts, the stop reason or the exposure of a
#: pass that has not run yet, and a fixed-width line 1 rewritten in
#: place would put a seek into the one path that must survive a kill.
FOOTER_TYPE = "footer"

#: The mint file that rides beside a streamed ledger (item 2 of the
#: memory wave).  A row is final only when its whole generation has
#: folded; a CERTIFICATE is final the moment the key returns, and this
#: is where it lands.  The file is a ledger in miniature — a header
#: line and one row-shaped line per certificate — so `export-facts`,
#: `close --ledger` and `score --ledger` read it with no special case.
#: This is the name for `ledger.jsonl`; `mints_beside` derives the rest.
MINTS_NAME = "mints.jsonl"

#: What a writer renames an existing file to rather than truncating it.
BACKUP_SUFFIX = ".bak"


def mints_beside(path: Path | str) -> Path:
    """The mint file of a ledger: `ledger` -> `mints`, suffix kept.

    `ledger.jsonl` -> `mints.jsonl` and `ledger-read.jsonl` ->
    `mints-read.jsonl`, because `read` and `ladder` can be pointed at
    the SAME `--out` and one fixed mint name would have had them share
    a file.  Anything not
    called `ledger*` gets `<stem>-mints`.
    """
    path = Path(path)
    stem = path.stem
    name = (f"mints{stem[len('ledger'):]}" if stem.startswith("ledger")
            else f"{stem}-mints")
    return path.with_name(name + path.suffix)


def keep_aside(path: Path | str) -> Path | None:
    """Rename an existing file to `<name>.bak`; returns where it went.

    A streamed writer opens its files BEFORE the pass runs, so a second
    pass into one out dir would destroy the first pass's ledger and
    mints before doing any work — where the batch writer it replaced
    only overwrote at the end, after a pass had earned the right to.
    The `unionbase` idiom instead: the old file is moved aside, exactly
    once (a second run overwrites the `.bak`, which is the previous
    pass's, not this one's).
    """
    path = Path(path)
    if not path.exists():
        return None
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    path.replace(backup)
    return backup
# ------------------------------------------------------------- json-able

def jsonable(value: Any) -> Any:
    """numpy and tuples down to what `json` will take."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        # NaN and +-inf are not JSON; a missing number is `null`, never a
        # token no other reader will parse.
        value = float(value)
        return value if np.isfinite(value) else None
    if isinstance(value, np.ndarray):
        return [jsonable(item) for item in value.tolist()]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        return {str(name): jsonable(item) for name, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(item) for item in value]
    return str(value)


def row_to_dict(row: LedgerRow, *, row_seq: int | None = None) -> dict:
    """The row as one JSON line.

    `row_seq` is the row's ordinal in the FILE, which a streamed ledger
    writes because a re-attacked key appends rather than replaces: two
    rows with one key are then ordered on disk by something a reader can
    see, whatever order it meets them in.  Left out, the field is absent
    and the line is the one this function always wrote.
    """
    return {
        "type": ROW_TYPE,
        "page": int(row.page), "ty": int(row.ty), "tx": int(row.tx),
        "stream_id": str(row.stream_id), "esi": int(row.esi),
        "covered": bool(row.covered),
        "certified_by_production": bool(row.certified_by_production),
        "source": row.source, "band": row.band, "band_any": row.band_any,
        "neighbours_certified": int(row.neighbours_certified),
        "siblings_certified": list(row.siblings_certified),
        "known_cells_in_halo": int(row.known_cells_in_halo),
        "n_discriminating_labels": int(row.n_discriminating_labels),
        "production_attempts": jsonable(row.production_attempts),
        "metadata_known": bool(row.metadata_known),
        "evidence": jsonable(row.evidence),
        "combined": jsonable(row.combined),
        "rungs": jsonable(row.rungs),
        "verdict": row.verdict,
        "certifying_rung": row.certifying_rung,
        "certifying_rule": row.certifying_rule,
        # W8 B1: the driver set it since GAPS-2026-09-03 and README §4
        # claimed it; the row never wrote it.  `reroll:<arm>` names the
        # arm whose already-computed evidence won after the selection's.
        "certifying_arm": row.certifying_arm,
        "generation": row.generation,
        "predecessors": [list(key) for key in row.predecessors],
        "diag": jsonable(row.diag),
        "rank_report": row.rank_report,
        "rank_recomputed": row.rank_recomputed,
        **({} if row_seq is None else {"row_seq": int(row_seq)}),
    }


def write_rows(path: Path | str, rows: Sequence[LedgerRow],
               header: Mapping[str, Any] | None = None) -> Path:
    """A ledger written in one go, from rows that are already in hand.

    The census writes one, and so does any caller small enough to hold
    its rows; a PASS writes through :class:`LedgerWriter` instead, which
    puts the header on disk before the first key and each row as it
    folds.  Both produce the same file, minus the footer this one has no
    use for: its header is final when it is written — and minus the row
    ORDER: the rows here are the caller's, one per key, where a streamed
    ledger's are in fold order and a re-attacked key appears twice.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(
            {"type": HEADER_TYPE, **jsonable(dict(header or {}))}) + "\n")
        for seq, row in enumerate(rows):
            stream.write(json.dumps(row_to_dict(row, row_seq=seq)) + "\n")
    return path


class LedgerWriter:
    """The ledger of a RUNNING pass: header first, rows as they fold.

    Item 1 and 2 of the 2026-09-13 memory wave.  `fixedpoint.run` used
    to hand its whole `Ledger` back and the CLI wrote the file after —
    which cost the pass twice over.  A row is 1.6 MB of JSON on the
    four-capture sheet-J pass and about twice that as live Python, so a
    2,700-target pass held 15-32 GB of rows and was the dominant holder
    of the process; and a kill lost every one of them, mints included,
    because the out dir was created after the pass returned.

    So: the header is on disk before generation 0 starts, `append` puts
    each row down as its generation folds it and the driver does not
    keep it, `mint` puts every certificate down the moment its key
    returns (a whole generation earlier than its row), and `finish`
    appends the FOOTER with the counts the header could not carry.
    Every line is flushed, because the reader this exists for is a
    `kill -9`.

    `mint` is called from the worker threads and `append` from the main
    one, so both take the lock; the interpreter is free-threaded and
    interleaved lines would be a corrupt file.

    OPENING IS NOT DESTRUCTIVE.  Both files are opened before the pass
    does any work, so an existing ledger or mint file in the out dir is
    RENAMED ASIDE (`keep_aside`, `<name>.bak`) rather than truncated —
    the batch writer this replaced only overwrote at the end, and a
    second pass into one out dir must not cost the first its record
    before earning anything.  `kept_aside` names what moved.

    ROW ORDER.  A re-attacked key appends a second row instead of
    replacing the first, so rows are in FOLD order and a key may appear
    more than once; readers take the last (`iter_rows_latest`).
    """

    def __init__(self, path: Path | str,
                 header: Mapping[str, Any] | None = None,
                 *, mints_path: Path | str | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.mints_path = (mints_beside(self.path) if mints_path is None
                           else Path(mints_path))
        self.kept_aside = tuple(
            moved for moved in (keep_aside(self.path),
                                keep_aside(self.mints_path))
            if moved is not None)
        self._lock = threading.Lock()
        self._closed = False
        self._started = False
        self.n_rows = 0
        self.n_mints = 0
        self._rows = open(self.path, "w", encoding="utf-8")
        self._mints = open(self.mints_path, "w", encoding="utf-8")
        if header is not None:
            self.start(header)

    def start(self, header: Mapping[str, Any]) -> None:
        """Put the header on disk; the first call wins.

        The CLI opens the writer before it has a header (the driver
        builds that) and `fixedpoint.run` calls this before its first
        generation, which is the whole point: the file exists, and says
        what the pass IS, before any key is attempted.
        """
        with self._lock:
            if self._started:
                return
            self._started = True
            head = {"type": HEADER_TYPE, **jsonable(dict(header)),
                    "partial": True}
            _write_line(self._rows, head)
            _write_line(self._mints, {**head, "mints_of": str(self.path)})

    def __enter__(self) -> "LedgerWriter":

        return self

    def __exit__(self, *_exception: Any) -> None:
        self.close()

    def append(self, row: LedgerRow) -> int:
        """One folded row, appended; returns its `row_seq`."""
        with self._lock:
            seq = self.n_rows
            _write_line(self._rows, row_to_dict(row, row_seq=seq))
            self.n_rows += 1
        return seq

    def mint(self, record: Mapping[str, Any]) -> int:
        """One certificate, appended to `mints.jsonl` as it lands.

        The record is row-shaped and carries `mint`, so the file reads
        as a ledger whose every row certified — which is what makes it
        the recovery door: `export-facts --ledger mints.jsonl` folds a
        killed pass's certificates into a snapshot with no special case.
        The key stays FIRST, ahead of `mint`, so `_row_counts` reads this
        file down its fast path too.
        """
        with self._lock:
            seq = self.n_mints
            _write_line(self._mints, {"type": ROW_TYPE,
                                      **jsonable(dict(record)),
                                      "mint": True, "row_seq": seq})
            self.n_mints += 1
        return seq


    def finish(self, header: Mapping[str, Any] | None) -> None:
        """The final header, as the footer of both files."""
        footer = {"type": FOOTER_TYPE, **jsonable(dict(header or {})),
                  "partial": False}
        with self._lock:
            if self._closed:
                return
            _write_line(self._rows, footer)
            _write_line(self._mints, {**footer, "n_mints": self.n_mints})
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._rows.close()
            self._mints.close()


def _write_line(stream: Any, record: Mapping[str, Any]) -> None:
    stream.write(json.dumps(record) + "\n")
    stream.flush()


# ----------------------------------------------------------- the readers

@dataclass
class ReadStats:
    """What a reader met on the way through a ledger.

    `truncated_lines` is the honest half: a pass that was killed mid-line
    leaves one that will not decode, and a reader skips it rather than
    refusing the whole file — but a recovery report that does not SAY so
    is claiming the file was whole.
    """

    lines: int = 0
    rows: int = 0
    superseded: int = 0
    truncated_lines: int = 0
    header: dict = field(default_factory=dict)
    footer: dict = field(default_factory=dict)

    @property
    def partial(self) -> bool:
        """A STREAMED ledger with no footer: its pass never reached the
        end.  Both halves are needed — a `write_rows` file (the census)
        has no footer either and is complete, and it is the streamed
        header's own `partial` flag that tells the two apart.
        """
        return not self.footer and bool(self.header.get("partial"))


#: The head of a row line, for the key scan of `iter_rows_latest`.  The
#: writer puts the key first (`row_to_dict`), so the last-row index costs
#: a regex per line instead of a JSON decode of 1.6 MB.
_ROW_HEAD = re.compile(
    r'^\{"type": "row", "page": (-?\d+), "ty": (-?\d+), "tx": (-?\d+), '
    r'"stream_id": "([^"]*)"')

#: The TAIL that says a row line is whole.  `row_to_dict` writes
#: `row_seq` last and every writer passes it (`write_rows`,
#: `LedgerWriter.append`, `LedgerWriter.mint`), so a line that ends here
#: cannot be half-written — which is what the head scan alone could not
#: tell (review §6, 2026-09-13).  Only the last few characters are
#: looked at: a row line is 1.6 MB, and searching one from the front
#: would cost what the JSON decode this scan exists to avoid costs.
_ROW_TAIL = re.compile(r'"row_seq": \d+\}$')
_ROW_TAIL_WINDOW = 48


def key_of(row: Mapping[str, Any]) -> tuple:
    """`(page, ty, tx, stream_id)` off a row dict, defaults tolerated."""
    return (int(row.get("page", 0)), int(row.get("ty", -1)),
            int(row.get("tx", -1)), str(row.get("stream_id")))


def _records(path: Path | str, stats: ReadStats | None) -> Iterator[dict]:
    """Every decodable line of the file, headers and footers included."""
    with open(Path(path), "r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            if stats is not None:
                stats.lines += 1
            try:
                record = json.loads(line)
            except ValueError:
                if stats is not None:
                    stats.truncated_lines += 1
                continue
            yield record


#: How far back `read_footer` looks.  A footer is a header plus a dozen
#: counts; 64 KiB holds one many times over, and the newline before it.
FOOTER_TAIL_BYTES = 1 << 16


def read_footer(path: Path | str) -> dict:
    """The final header of a streamed ledger, or `{}` for a partial one.

    Read from the TAIL, never by walking the file: the whole point of
    `read_header` is that it costs nothing on a 4.5 GB ledger.
    """
    path = Path(path)
    with open(path, "rb") as stream:
        size = path.stat().st_size
        stream.seek(max(0, size - FOOTER_TAIL_BYTES))
        tail = stream.read()
    for chunk in reversed(tail.split(b"\n")):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            record = json.loads(chunk.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}                 # a half-written last line: no footer
        return record if record.get("type") == FOOTER_TYPE else {}
    return {}


def read_header(path: Path | str) -> dict:
    """The header — line 1, with the footer's final counts merged in.

    A ledger can be GIGABYTES (sheet H: 2.6-5.8 GB each), so the scorer
    reads headers first and rows in a stream.  A streamed pass writes
    line 1 before it runs, so the counts, the stop reason and the
    exposure arrive in the footer; both are cheap to reach and the
    caller sees one dict.  `partial` says which it got.
    """
    path = Path(path)
    header: dict = {}
    with open(path, "r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            header = record if record.get("type") == HEADER_TYPE else {}
            break
    footer = read_footer(path)
    if footer:
        header = {**header, **footer, "type": HEADER_TYPE}
    return header


def iter_rows(path: Path | str, *, stats: ReadStats | None = None
              ) -> Iterator[dict]:
    """Row dicts one at a time, never all of them at once.

    `read_rows` materialises the whole file, which is right for a small
    ledger and impossible for a big one: sheet H's five passes are 18 GB
    of JSON between them, and decoded dicts are several times that.

    EVERY row, including the superseded attempt of a key a later
    generation re-attacked; `iter_rows_latest` is the one that applies
    last-write-wins.
    """
    for record in _records(path, stats):
        kind = record.get("type")
        if kind == HEADER_TYPE:
            if stats is not None and not stats.header:
                stats.header = record
            continue
        if kind == FOOTER_TYPE:
            if stats is not None:
                stats.footer = record
            continue
        if stats is not None:
            stats.rows += 1
        yield record


def _row_counts(path: Path | str) -> dict[tuple, int]:
    """How many rows each key has, from the line HEADS alone.

    The one pass that has to be cheap: it decodes nothing but the four
    fields the writer puts first, so the index of a 4.5 GB ledger costs
    two regexes per line.  The second is the one that says the line is
    WHOLE — every row this analyzer writes ends in `"row_seq": <n>}` —
    because a head match alone counts a half-written line whose reader
    below then cannot parse it, which suppresses the key's earlier
    COMPLETE row as superseded and loses it.  A `kill -9` leaves that
    line at the end of the file, but a torn line anywhere has the same
    effect, and the tail test catches both (review §6, 2026-09-13).

    WHAT IT DOES NOT CATCH, stated exactly (M5, 2026-09-13): one line
    that is the HEAD of one row CONCATENATED with the TAIL of the next.
    Both patterns match, the line counts as the first key's and then
    fails to parse below, and the first key's earlier complete row is
    lost as superseded.  Nothing this writer does can produce one — the
    rows file is opened `"w"` and appended to by one process, and there
    is no resume — so the guard that would close it is not bought: a
    third test `line.count('{"type": "row"') == 1` is EXACT and costs
    384 us on a 1.6 MB row against 0.5 us for the two regexes, which is
    23% of the `json.loads` this whole scan exists to avoid (measured
    2026-09-13).  A writer that ever appends to an existing ledger owes
    that test, and pays for it.

    A line that does not match both is decoded in FULL instead, which is
    how a ledger older than `row_seq` still indexes — and how a torn
    line is caught there too: JSON cut at a nested `}` does not parse.
    """
    counts: dict[tuple, int] = {}
    with open(Path(path), "r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line or not line.endswith("}"):
                continue
            match = _ROW_HEAD.match(line)
            if (match is not None
                    and _ROW_TAIL.search(line[-_ROW_TAIL_WINDOW:])):
                key = (int(match[1]), int(match[2]), int(match[3]),
                       str(match[4]))
            else:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") in (HEADER_TYPE, FOOTER_TYPE):
                    continue
                key = key_of(record)
            counts[key] = counts.get(key, 0) + 1
    return counts


def iter_rows_latest(path: Path | str, *, stats: ReadStats | None = None
                     ) -> Iterator[dict]:
    """One row per key — the LAST one the file carries.

    A re-attacked key appends a new row rather than replacing the old
    one (a streamed ledger cannot rewrite what it has already flushed),
    so every reader that counts keys — the summary, the maps, the
    close, `export-facts`, the scorer — takes the last write.  Two
    passes: the cheap key scan above, then the file itself, yielding a
    key's row when its count runs out.  Memory is one small dict, not
    one row.
    """
    remaining = _row_counts(path)
    for record in iter_rows(path, stats=stats):
        key = key_of(record)
        left = remaining.get(key, 1) - 1
        remaining[key] = left
        if left > 0:
            if stats is not None:
                stats.superseded += 1
            continue
        yield record


def read_rows(path: Path | str, *, stats: ReadStats | None = None
              ) -> tuple[dict, list[dict]]:
    """Header and EVERY row, in memory — small ledgers only.

    A superseded attempt is a row here like any other; the readers that
    count keys take `iter_rows_latest`.
    """
    header: dict = {}
    rows: list[dict] = []

    for record in _records(path, stats):
        kind = record.get("type")
        if kind == HEADER_TYPE:
            if not header:
                header = record
                if stats is not None:
                    stats.header = record
        elif kind == FOOTER_TYPE:
            header = {**header, **record, "type": HEADER_TYPE}
            if stats is not None:
                stats.footer = record
        else:
            if stats is not None:
                stats.rows += 1
            rows.append(record)
    return header, rows
