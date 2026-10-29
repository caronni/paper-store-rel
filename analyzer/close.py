"""The close — production ∪ analyzer certificates (DESIGN §6a).

`holo.receiver.format.close.close_volume` is callable standalone and is what
production itself uses, so this module CALLS it rather than reproducing
any part of the fountain arithmetic: the union of the run's certificates
and the analyzer's own goes in, and a `CloseResult` comes back with the
status, the block rows (each with `have`, `needed`, `rank`, `solved`),
the symbol count and — when it verifies — the payload bytes themselves.

THE VERDICT IS THE ENVELOPE (RULED 2026-09-04).  The payload envelope is
`{sha256}{len:4B BE}{data}`, so a volume that closes has already checked
its own contents against a digest the EMITTER wrote inside the volume;
`close_volume` reports `verified` exactly when that check passed.  This
module therefore no longer consults a generation manifest — the analyzer
opens no payload during a run — and instead WRITES the recovered bytes
out (`<out>/payload.bin`, sha in `close.json`), which is what makes an
offline `analyzer score` possible against a payload nobody handed us.

A close is WELCOME AND NOT PRE-REGISTERED (DESIGN §6a).  On sheet I the
production run alone already exceeds K, so the union close is a
regression test of the analyzer's certificates: adding them must not
break a close that already verified.

## THE FOUNTAIN CONSISTENCY CHECK (2026-09-04)

Third leg of the ruling's correctness argument, and the one that needs
no payload at all: above K the fountain is OVER-DETERMINED, so the
symbols the close did not need are a parity check on the ones it used.
:func:`consistency` solves the source block exactly as `close_volume`
does and then RE-ENCODES every input symbol from that solution through
holo3's own generator rows — systematic rows read straight off the
source, repair rows as the XOR of the source rows their keystream-drawn
row selects.  A symbol that disagrees with its re-encoding is a symbol
that cannot have come from the same volume as the rest.  With `have`
symbols and K source rows, `have − K` of those comparisons are genuinely
free evidence (a basis row reproduces itself by construction and proves
nothing), so a clean check with `n_redundant` large is the TRUTH-FREE
statement that every certificate the close consumed is right.

WHAT holo3 DOES NOT DO, and why this is not redundant with it.
`fountain._ge_solve_gf2` performs Gauss–Jordan elimination over the K
columns and returns `vals[pivot_of_col]` as soon as every column has a
pivot.  Rows beyond the rank are eliminated to zero on the LEFT and
their right-hand sides are never looked at again — so a CONTRADICTORY
right-hand side is not detected, it is silently ignored, and the solver
returns a wrong source.  Worse for detection, `Decoder._solve_block` has
a fast path: when all k systematic rows are present it stacks them and
never consults a repair row at all.  Neither behaviour is a defect (the
production caller has no redundancy to spend and the CRC is its gate),
but it does mean that nothing downstream of `close_volume` would notice
a poisoned symbol except by the envelope failing — which is exactly the
failure this check turns into a NAMED key.

MEASURED ON SHEET I (2026-09-04), and stronger than that argument.  Both
of holo3's behaviours are pinned by tests, and the fast path has a
consequence worth stating plainly: when every systematic row is present
— which is the case for sheet I's identity, and for any volume read past
K on its source rows — a poisoned REPAIR symbol leaves the close
**VERIFIED**.  The envelope passes, the payload is byte-exact, and the
volume still carries a certificate that cannot have come from it.  The
close cannot see that symbol because it never reads it.  This check
does, in 0.3 s over 5,883 symbols, and it is the only thing that does.

## LOCALIZATION AND THE LAST-DITCH CORRECTION

:func:`localize` runs when the check fails.  Two signatures, and they
are decided by the size of the disagreeing set D, not by taste:

* **D is small** — the poisoned symbols are OUTSIDE the solve basis, so
  each one disagrees on its own and nothing else does.  Hypothesis: D.
  Drop it, re-solve, re-check.
* **D is large** — the poison is IN the basis, so the source itself is
  wrong and roughly half the redundant rows disagree.  For a single
  poisoned source row `j` every residual in D is the SAME error pattern
  `e` (the residual of row i is `G[i]·(x + x_true) = G[i,j]·e`), and D is
  exactly the set of rows whose generator has a 1 in column j.  So the
  poisoned column is found by AND-reducing the generator rows of D: a
  column that is not j survives all |D| of them with probability
  2^-|D|, which the report states as `false_candidate_bound`.

Either way the error pattern is known, so the poisoned symbol can be
CORRECTED (`observed ^ e`) rather than merely excluded — the report
carries the corrected bits and says whether they reproduce the source
that the survivors solve, which is the proof the correction is right.

BOUNDED WORK, STATED.  One round is one `Decoder.try_solve` over the
surviving symbols plus one re-encode of them; `localize` runs at most
`max_rounds + 1` of them (default 5) and stops the moment a check comes
back clean.  It never searches the basis, so a poisoned REPAIR row that
entered the basis is reported `unlocalized` with its evidence rather
than hunted at O(K) solves.

MIXED POISON REFUSES — MEASURED, reviewer probe 2026-09-04.  Poison one
SYSTEMATIC and one REPAIR symbol at once and D is large (the basis
poison) but its residuals are not one common error pattern (the repair
row carries its own), so the consensus rule cannot name a column and
`localize` returns `localized` False with that stated reason rather than
a guess.  Two poisoned source rows in one block refuse the same way.
Both are honest refusals, not wrong answers; separating the MODAL
residual from its outliers would recover the mixed case and is not
built.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from holo.receiver import data
from holo.receiver.format import close as fmt_close
from holo.receiver.format import fountain
from holo.receiver.format import metadata as fmt_metadata

from .types import Key

ANALYZER_SOURCE = "analyzer"

#: What a close writes its recovered bytes to, inside `--out`.
PAYLOAD_NAME = "payload.bin"

#: `localize` stops after this many exclusion rounds (each round is one
#: solve + one re-encode of the survivors).
LOCALIZE_MAX_ROUNDS = 4

#: |D| at or below this is read as "the poison is outside the basis" and
#: D itself is the hypothesis.
LOCALIZE_DIRECT_MAX = 8

#: |D| at or above this makes the column consensus decisive: a column
#: that is not the poisoned one survives |D| AND-reductions with
#: probability 2^-|D|, so 24 leaves a bound of k·6e-8 on a 5,277-row
#: block.  Between the two thresholds `localize` refuses and says so.
LOCALIZE_MIN_CONSENSUS = 24

#: A check with fewer redundant comparisons than this proves nothing —
#: dropping symbols until `have == K` makes consistency VACUOUS, so a
#: clean re-check below this floor is reported `redundancy_exhausted`
#: rather than `localized`.
LOCALIZE_MIN_REDUNDANCY = 8

_POPCOUNT8 = np.array([bin(value).count("1") for value in range(256)],
                      np.int64)


def as_certificate(key: Key, user_bits: Any, *,
                   source: str = ANALYZER_SOURCE) -> Any:
    page, ty, tx, stream_id = key
    return data.Certificate(page=int(page), ty=int(ty), tx=int(tx),
                            stream_id=str(stream_id),
                            user_bits=np.asarray(user_bits, np.uint8),
                            source=str(source))


def union_certificates(inputs: Any,
                       analyzer_certs: Mapping[Key, Any] | None) -> tuple:
    """Production's certificates, then the analyzer's, in key order.

    A key already certified by production is NOT replaced: production's
    certificate is the one the run's own close used, and an analyzer
    certificate for the same key would have to be bit-identical anyway
    (both passed the same CRC over the same k bits).
    """
    out: dict[Key, Any] = {}
    for key, certificate in inputs.certificates.items():
        out[key] = certificate
    added: list[Key] = []
    for key, bits in (analyzer_certs or {}).items():
        if key in out:
            continue
        value = bits
        if not isinstance(value, np.ndarray) and hasattr(value, "user_bits"):
            value = value.user_bits
        out[key] = as_certificate(key, value)
        added.append(key)
    return tuple(out[key] for key in sorted(out)), tuple(sorted(added))


def metadata_rank(certs, row) -> dict:
    """The rank of the certified metadata equation system.

    `close_volume` reports only whether the word was solvable; DESIGN §6a
    wants the rank beside it, and `metadata.decode_metadata` returns it.
    """
    streams = tuple(row.streams)
    n = len(streams)
    index_of = {fact.stream_id: position
                for position, fact in enumerate(streams)}
    equations: dict[int, int] = {}
    for certificate in certs:
        counter = row.tile_counter(int(certificate.page), int(certificate.ty),
                                   int(certificate.tx))
        index = (fmt_metadata.equation_index(
            counter, index_of[certificate.stream_id], n)
            if row.pooled_fountain else counter)
        equations[index] = int(certificate.user_bits[0])
    max_index = (fmt_metadata.max_equation_index(n) if row.pooled_fountain
                 else fmt_metadata.MAX_COUNTER)
    solved = fmt_metadata.decode_metadata(equations, max_index=max_index)
    return {"rank": int(solved.rank), "n_unique": int(solved.n_unique),
            "min_equations": int(fmt_metadata.MIN_METADATA_EQUATIONS),
            "metadata_bits": int(fmt_metadata.METADATA_BITS),
            "ok": bool(solved.ok), "inconsistent": bool(solved.inconsistent)}


# ------------------------------------------------- fountain consistency

def key_of(certificate: Any) -> Key:
    return (int(certificate.page), int(certificate.ty), int(certificate.tx),
            str(certificate.stream_id))


def symbol_index(row: Any, certificate: Any) -> int:
    """holo3's own ESI for one certificate (`close._symbol_index`)."""
    index_of = {fact.stream_id: position
                for position, fact in enumerate(tuple(row.streams))}
    return int(fmt_close._symbol_index(
        row, certificate, index_of[str(certificate.stream_id)]))


#: `(row, esi, lo, hi)` — the decoder's own item: the source or repair
#: row this slice of the symbol carries, and the slice's column bounds.
SlotItem = tuple[int, int, int, int]


def slot_items(code: Any, esis: Iterable[int]
               ) -> dict[tuple[int, int], list[SlotItem]]:
    """The decoder's items per `(block, group)`, for EVERY symbol given.

    Built through `code.tile_slots` exactly as `fountain.Decoder.add_symbol`
    builds them (row-sorted, as `try_solve` sorts them), but kept after
    the solve — the decoder itself forgets a group's items once it is
    solved, and the consistency check needs all of them.  A uniform row
    is the one-group case: every item then spans the whole symbol.
    """
    out: dict[tuple[int, int], list[SlotItem]] = {}
    for esi in sorted(int(value) for value in esis):
        tile = code.tile_slots(esi)
        for group, source_row, lo, hi in zip(tile.groups, tile.source_rows,
                                             tile.edges, tile.edges[1:]):
            row = source_row if source_row >= 0 else tile.repair_row
            out.setdefault((int(tile.block), int(group)), []).append(
                (int(row), esi, int(lo), int(hi)))
    for items in out.values():
        items.sort()
    return out


def _popcount_rows(packed: np.ndarray) -> np.ndarray:
    """Set bits per row of a packed uint64 matrix."""
    flat = np.ascontiguousarray(packed).view(np.uint8)
    return _POPCOUNT8[flat].sum(axis=1)


def _groups(certs: Sequence[Any], row: Any,
            k_total: int) -> list[tuple[str, Any, dict[int, Any]]]:
    """(label, VolumeCode, {esi: certificate}) per independent fountain.

    The esi arithmetic and the code construction are holo3's own
    (`close._symbol_index`, `close._tile_counter`, `close._volume_code`,
    `close._pooled_volume_code` — the last one carries the column groups
    of an uneven cmy8 triplet), called rather than reproduced: a second
    spelling of the ESI mapping would be a format fork waiting to happen.
    """
    out: list[tuple[str, Any, dict[int, Any]]] = []
    if row.pooled_fountain:
        code = fmt_close._pooled_volume_code(row, k_total)
        by_esi = {symbol_index(row, cert): cert for cert in certs}
        return [("pooled", code, by_esi)]
    for stream in tuple(row.streams):
        code = fmt_close._volume_code(row, stream, k_total)
        by_esi = {fmt_close._tile_counter(row, cert): cert for cert in certs
                  if cert.stream_id == stream.stream_id}
        out.append((str(stream.stream_id), code, by_esi))
    return out


@dataclass(frozen=True)
class BlockCheck:
    """One fountain (block, column group)'s re-encoding, with everything
    localization needs.  A uniform row has one group per block, spanning
    the whole symbol; an uneven cmy8 triplet has several, each a column
    slice of the symbols that carry it."""

    label: str
    block: int
    group: int
    k_bits: int
    #: (row, esi) per item, in the decoder's own order (row-sorted).
    items: tuple[tuple[int, int], ...]
    #: (lo, hi) per item: the symbol columns this group occupies in it.
    slots: tuple[tuple[int, int], ...]
    #: (n_items, k_bits) uint8 — holo3's generator rows for those items.
    generator_bits: np.ndarray
    #: packed uint64, (n_items, words): observed ^ re-encoded, over the
    #: group's columns only.
    residual: np.ndarray
    disagreeing: np.ndarray
    n_bits_disagreeing: np.ndarray
    source: np.ndarray

    @property
    def n_redundant(self) -> int:
        return max(0, len(self.items) - int(self.k_bits))

    @property
    def esi_at_row(self) -> dict[int, int]:
        return {int(row): int(esi) for row, esi in self.items}


def _check_group(label: str, code: Any, by_esi: Mapping[int, Any],
                 ) -> tuple[list[BlockCheck], dict]:
    """Solve this fountain and re-encode every symbol it was given."""
    report: dict[str, Any] = {
        "label": label, "n_symbols": len(by_esi),
        "k_source_rows": int(code.k_total), "n_blocks": int(code.n_blocks)}
    decoder = fountain.Decoder(code)
    for esi in sorted(by_esi):
        decoder.add_symbol(esi, np.asarray(by_esi[esi].user_bits[1:],
                                           np.uint8))
    source = decoder.try_solve()
    if source is None:
        report.update(checked=False,
                      reason="the certified symbols do not span the source "
                             "(below K, or rank-deficient)")
        return [], report
    bounds = code.groups.bounds
    blocks: list[BlockCheck] = []
    for (block, group), items in sorted(slot_items(code, by_esi).items()):
        k_bits = int(code.k_per_block[block])
        offset = int(code.block_offsets[block])
        source_block = np.asarray(
            source[offset:offset + k_bits, bounds[group]:bounds[group + 1]],
            np.uint8)
        packed_source = fountain._pack_bits_2d(source_block)
        generator_bits = fountain._unpack_bits_2d(
            decoder._packed_generator_rows(block, items), k_bits)
        observed = fountain._pack_bits_2d(np.stack([
            np.asarray(by_esi[esi].user_bits[1:], np.uint8)[lo:hi]
            for _row_index, esi, lo, hi in items]))
        expected = np.zeros_like(observed)
        for index, (row_index, _esi, _lo, _hi) in enumerate(items):
            if row_index < k_bits:
                expected[index] = packed_source[row_index]
                continue
            support = np.flatnonzero(generator_bits[index])
            if support.size:
                expected[index] = np.bitwise_xor.reduce(
                    packed_source[support], axis=0)
        residual = expected ^ observed
        n_bits = _popcount_rows(residual)
        blocks.append(BlockCheck(
            label=label, block=block, group=group, k_bits=k_bits,
            items=tuple((row, esi) for row, esi, _lo, _hi in items),
            slots=tuple((lo, hi) for _row, _esi, lo, hi in items),
            generator_bits=generator_bits, residual=residual,
            disagreeing=n_bits > 0, n_bits_disagreeing=n_bits,
            source=source_block))
    report.update(
        checked=True, reason=None,
        n_redundant=sum(item.n_redundant for item in blocks),
        n_consistent=int(sum(int(np.count_nonzero(~item.disagreeing))
                             for item in blocks)),
        n_inconsistent=int(sum(int(np.count_nonzero(item.disagreeing))
                               for item in blocks)))
    return blocks, report


def _consistency(certs: Sequence[Any], row: Any,
                 exclude: Iterable[Key] = ()
                 ) -> tuple[dict, list[BlockCheck], dict[tuple[str, int],
                                                         Key]]:
    """The check, the per-block internals, and (label, esi) -> key.

    The address map is built ONCE while the groups are, because the
    reverse lookup is otherwise a scan of every certificate per
    disagreeing symbol — 1.5M `_pooled_esi` calls on a sheet-H union
    with a poisoned source row.
    """
    started = time.perf_counter()
    dropped = {tuple(key) for key in exclude}
    kept = tuple(cert for cert in certs if key_of(cert) not in dropped)
    report: dict[str, Any] = {
        "n_certificates": len(kept), "n_excluded": len(dropped),
        "excluded_keys": [list(key) for key in sorted(dropped)]}
    try:
        version, k_total, state = fmt_close.metadata_from_certificates(
            kept, row)
    except fountain.FountainIntegrityError as error:
        report.update(ok=False, checked=False, proven=False, k_total=None,
                      metadata_version=None, groups=[],
                      reason=f"metadata integrity failure: {error}",
                      seconds=time.perf_counter() - started)
        return report, [], {}
    report["metadata_version"] = version
    report["k_total"] = k_total
    if k_total is None:
        report.update(ok=True, checked=False, proven=False, groups=[],
                      reason=f"metadata {state}: no K to check against",
                      seconds=time.perf_counter() - started)
        return report, [], {}
    blocks: list[BlockCheck] = []
    groups: list[dict] = []
    key_at: dict[tuple[str, int], Key] = {}
    for label, code, by_esi in _groups(kept, row, k_total):
        for esi, certificate in by_esi.items():
            key_at[(label, int(esi))] = key_of(certificate)
        try:
            group_blocks, group_report = _check_group(label, code, by_esi)
        except fountain.FountainIntegrityError as error:
            groups.append({"label": label, "checked": False,
                           "reason": f"symbol integrity failure: {error}"})
            continue
        blocks.extend(group_blocks)
        groups.append(group_report)
    checked = [item for item in groups if item.get("checked")]
    n_inconsistent = sum(int(item["n_inconsistent"]) for item in checked)
    n_redundant = sum(int(item["n_redundant"]) for item in checked)
    inconsistent: list[tuple[Key, int]] = []
    for block in blocks:
        for index in np.flatnonzero(block.disagreeing):
            _row_index, esi = block.items[int(index)]
            key = key_at.get((block.label, int(esi)))
            if key is not None:
                inconsistent.append(
                    (key, int(block.n_bits_disagreeing[index])))
    report.update(
        ok=n_inconsistent == 0,
        checked=bool(checked),
        # A solve at exactly K re-encodes only the basis, and a basis row
        # reproduces itself by construction: `checked` is then True and
        # `ok` True while NOTHING was proved.  `proven` is the field that
        # says the difference — `localize` already refuses to call such a
        # re-check a localization (LOCALIZE_MIN_REDUNDANCY) and a reader of
        # this report is owed the same distinction.
        proven=bool(checked) and n_redundant > 0,
        reason=None if checked else "no fountain group could be solved",
        groups=groups,
        n_symbols=int(sum(int(item["n_symbols"]) for item in checked)),
        n_redundant=int(n_redundant),
        n_consistent=int(sum(int(item["n_consistent"]) for item in checked)),
        n_inconsistent=int(n_inconsistent),
        inconsistent_keys=[list(key) for key, _bits in sorted(inconsistent)],
        inconsistent_bits={",".join(str(part) for part in key): int(bits)
                           for key, bits in sorted(inconsistent)},
        seconds=time.perf_counter() - started)
    if n_inconsistent:
        report["reason"] = (
            f"{n_inconsistent} certified symbol(s) disagree with their "
            f"re-encoding from the solved source")
    elif checked and not report["proven"]:
        report["reason"] = (
            "the symbols exactly span the source (0 redundant "
            "comparisons): every row re-encodes to itself, so this check "
            "is VACUOUS and proves nothing about the certificates")
    return report, blocks, key_at


def consistency(certificates: Sequence[Any], row: Any, *,
                exclude: Iterable[Key] = ()) -> dict:
    """Re-encode every certified symbol from the solved source.

    Returns the ledger-safe mapping `export-facts` and `close` record:
    `ok` is False ONLY when a disagreement was actually observed, and
    `checked` says whether there was anything to check (metadata not yet
    solvable, or fewer symbols than K, leave `ok` True and `checked`
    False — an unproven volume is not a poisoned one).

    `proven` is the third field and the one a reader must not skip: a
    volume whose certified symbols exactly span the source is `checked`
    and `ok` with `n_redundant` 0, because every row re-encoded to
    itself.  That is silence, not a clean bill of health, and the
    envelope remains the only verdict on such a volume.
    """
    report, _blocks, _key_at = _consistency(certificates, row, exclude)
    return report


# ------------------------------------- localization and the correction

def _hypothesis(block: BlockCheck, *, direct_max: int,
                min_consensus: int) -> tuple[list[int], dict]:
    """The esis this block accuses, and why (empty = it cannot tell)."""
    disagreeing = np.flatnonzero(block.disagreeing)
    detail: dict[str, Any] = {
        "label": block.label, "block": int(block.block),
        "group": int(block.group),
        "n_disagreeing": int(disagreeing.size),
        "n_redundant": int(block.n_redundant)}
    if disagreeing.size == 0:
        detail["rule"] = "clean"
        return [], detail
    if disagreeing.size <= int(direct_max):
        detail["rule"] = "direct"
        detail["evidence"] = "the disagreeing symbols are outside the " \
            "solve basis, so each one accuses itself"
        return [int(block.items[int(index)][1]) for index in disagreeing], \
            detail
    residual = block.residual[disagreeing]
    identical = bool(np.all(residual == residual[0]))
    detail["residuals_identical"] = identical
    if disagreeing.size < int(min_consensus) or not identical:
        detail["rule"] = "refused"
        detail["evidence"] = (
            "too few disagreeing rows for a decisive column consensus"
            if disagreeing.size < int(min_consensus)
            else "the disagreeing residuals are not one common error "
                 "pattern, so more than one source row is poisoned")
        return [], detail
    consensus = np.bitwise_and.reduce(block.generator_bits[disagreeing],
                                      axis=0)
    candidates = [int(value) for value in np.flatnonzero(consensus)]
    at_row = block.esi_at_row
    detail.update(
        rule="consensus", candidate_rows=candidates,
        false_candidate_bound=float(block.k_bits) * 2.0 ** -float(
            disagreeing.size),
        error_bits=int(_popcount_rows(residual[:1])[0]),
        evidence="every disagreeing row's generator has a 1 in this "
                 "column and every residual is the same error pattern")
    accused = [at_row[value] for value in candidates if value in at_row]
    detail["candidate_rows_without_symbol"] = [
        value for value in candidates if value not in at_row]
    if not accused:
        detail["rule"] = "unlocalized"
        detail["evidence"] = (
            "the poisoned source row has no systematic certificate, so "
            "the corruption entered through a repair row of the basis; "
            "finding it would cost O(K) solves and is not attempted")
    return accused, detail


def localize(certificates: Sequence[Any], row: Any, *,
             max_rounds: int = LOCALIZE_MAX_ROUNDS,
             direct_max: int = LOCALIZE_DIRECT_MAX,
             min_consensus: int = LOCALIZE_MIN_CONSENSUS,
             min_redundancy: int = LOCALIZE_MIN_REDUNDANCY) -> dict:
    """Find the poisoned symbols, exclude them, close on the survivors.

    Each round is ONE solve plus one re-encode of the survivors, and
    there are at most `max_rounds + 1` of them; the cost is reported in
    `n_solves` and `seconds` so a caller never has to guess it.
    """
    started = time.perf_counter()
    certs = tuple(certificates)
    by_key = {key_of(cert): cert for cert in certs}
    excluded: list[Key] = []
    rounds: list[dict] = []
    evidence: dict[str, Any] = {}
    corrections: dict[str, list[tuple[int, np.ndarray]]] = {}
    localized = False
    reason: str | None = None
    for index in range(int(max_rounds) + 1):
        report, blocks, key_at = _consistency(certs, row, excluded)
        record = {"round": index, "n_certificates": report["n_certificates"],
                  "checked": bool(report.get("checked")),
                  "n_redundant": int(report.get("n_redundant", 0)),
                  "n_inconsistent": int(report.get("n_inconsistent", 0)),
                  "reason": report.get("reason")}
        if not report.get("checked"):
            rounds.append(record)
            reason = report.get("reason")
            break
        if report["n_inconsistent"] == 0:
            record["rule"] = "clean"
            rounds.append(record)
            if not excluded:
                reason = "the system was consistent to begin with"
            elif record["n_redundant"] < int(min_redundancy):
                reason = (
                    f"the survivors are consistent but only "
                    f"{record['n_redundant']} redundant comparison(s) are "
                    f"left (floor {int(min_redundancy)}): the check has "
                    f"become vacuous, so this is not a localization")
            else:
                localized = True
            break
        if index == int(max_rounds):
            record["rule"] = "budget_exhausted"
            rounds.append(record)
            reason = (f"still inconsistent after {max_rounds} exclusion "
                      f"round(s)")
            break
        accused: list[Key] = []
        details: list[dict] = []
        for block in blocks:
            esis, detail = _hypothesis(block, direct_max=direct_max,
                                       min_consensus=min_consensus)
            if detail.get("rule") == "clean":
                continue
            details.append(detail)
            for esi in esis:
                key = key_at.get((block.label, int(esi)))
                if key is None or key in excluded:
                    continue
                accused.append(key)
                evidence[",".join(str(part) for part in key)] = {
                    "round": index, "rule": detail.get("rule"),
                    "n_disagreeing_rows": detail.get("n_disagreeing"),
                    "n_bits_disagreeing": int(
                        detail.get("error_bits",
                                   _bits_of(block, esi))),
                    "false_candidate_bound": detail.get(
                        "false_candidate_bound"),
                    "evidence": detail.get("evidence")}
                fix = _correction_for(block, esi, detail)
                if fix is not None:
                    corrections.setdefault(
                        ",".join(str(part) for part in key), []).append(fix)
        record["rule"] = "|".join(
            sorted({str(item.get("rule")) for item in details})) or "none"
        record["hypothesis"] = [list(key) for key in accused]
        record["detail"] = details
        rounds.append(record)
        if not accused:
            reason = ("the disagreement does not name a symbol: the "
                      "poison is inside the solve basis without a "
                      "systematic witness")
            break
        excluded.extend(key for key in accused if key not in excluded)

    survivors = tuple(by_key[key] for key in sorted(by_key)
                      if key not in set(excluded))
    result = fmt_close.close_volume(survivors, row)
    payload = result.payload
    repaired = _corrected_bits(corrections, by_key)
    checked = (_verify_corrections(repaired, survivors, row)
               if (localized and repaired) else {})
    return {
        "localized": bool(localized),
        "reason": reason,
        "n_solves": len(rounds),
        "n_rounds": len(rounds),
        "max_rounds": int(max_rounds),
        "seconds": time.perf_counter() - started,
        "poisoned_keys": [list(key) for key in excluded],
        "evidence": evidence,
        "rounds": rounds,
        "corrections": {
            name: {"n_bits_flipped": int(np.count_nonzero(
                np.asarray(bits, np.uint8)
                != np.asarray(by_key[_key_from_name(name)].user_bits,
                              np.uint8))),
                   "sha256": hashlib.sha256(
                       np.asarray(bits, np.uint8).tobytes()).hexdigest()}
            for name, bits in repaired.items()},
        "corrected_user_bits": {name: np.asarray(bits, np.uint8)
                                for name, bits in repaired.items()},
        "corrections_verified": checked,
        "n_survivors": len(survivors),
        "close": {"status": result.status,
                  "verified": bool(result.status == "verified"),
                  "reason": result.reason,
                  "k_total": result.k_total,
                  "n_symbols_used": result.symbols_used,
                  "payload_bytes": None if payload is None
                  else int(len(payload)),
                  "payload_sha256": None if payload is None
                  else hashlib.sha256(bytes(payload)).hexdigest()},
    }


def _bits_of(block: BlockCheck, esi: int) -> int:
    for index, (_row_index, item) in enumerate(block.items):
        if int(item) == int(esi):
            return int(block.n_bits_disagreeing[index])
    return 0


def _correction_for(block: BlockCheck, esi: int,
                    detail: Mapping[str, Any]
                    ) -> tuple[int, np.ndarray] | None:
    """`(lo, error)`: the error pattern to XOR into this symbol's columns
    `lo:lo+error.size` (the group's slice; the whole symbol on a uniform
    row), as unpacked bits."""
    index_of = {int(item): index
                for index, (_row_index, item) in enumerate(block.items)}
    index = index_of.get(int(esi))
    if index is None:
        return None
    if detail.get("rule") == "direct":
        packed = block.residual[index:index + 1]
    else:
        disagreeing = np.flatnonzero(block.disagreeing)
        if not disagreeing.size:
            return None
        first = int(disagreeing[0])
        packed = block.residual[first:first + 1]
    lo, _hi = block.slots[index]
    return lo, fountain._unpack_bits_2d(packed, block.source.shape[1])[0]


def _key_from_name(name: str) -> Key:
    page, ty, tx, stream_id = name.split(",")
    return (int(page), int(ty), int(tx), stream_id)


def _corrected_bits(corrections: Mapping[str, Sequence[tuple[int, Any]]],
                    by_key: Mapping[Key, Any]) -> dict[str, np.ndarray]:
    """`observed ^ error` — the whole user-bit vector, metadata bit kept.

    Each error pattern is over a column slice of the SYMBOL
    (`user_bits[1:]`, from its `lo`); the metadata bit is a separate
    equation system with its own integrity gate
    (`metadata_from_certificates` raises on a contradiction), so it is
    carried through untouched.
    """
    out: dict[str, np.ndarray] = {}
    for name, errors in corrections.items():
        certificate = by_key.get(_key_from_name(name))
        if certificate is None:
            continue
        bits = np.asarray(certificate.user_bits, np.uint8).copy()
        for lo, error in errors:
            error = np.asarray(error, np.uint8)
            start = 1 + int(lo)
            bits[start:start + error.size] ^= error
        out[name] = bits
    return out


def _verify_corrections(repaired: Mapping[str, np.ndarray],
                        survivors: Sequence[Any], row: Any) -> dict:
    """Do the repaired symbols agree with the source the SURVIVORS solve?

    This is what makes a correction a correction rather than another
    guess: the survivors alone determine the source, and each repaired
    symbol is then re-encoded from THAT source like any other input.  A
    correction that is right adds a consistent symbol; one that is wrong
    adds an inconsistent one and says so.
    """
    admitted = tuple(survivors) + tuple(
        as_certificate(_key_from_name(name), bits, source="analyzer/repair")
        for name, bits in repaired.items())
    report = consistency(admitted, row)
    return {"n_corrections": len(repaired),
            "checked": bool(report.get("checked")),
            "consistent": bool(report.get("ok")),
            "n_inconsistent": int(report.get("n_inconsistent", 0)),
            "n_redundant": int(report.get("n_redundant", 0)),
            "still_inconsistent_keys": report.get("inconsistent_keys", [])}


def close(inputs: Any, analyzer_certs: Mapping[Key, Any] | None = None, *,
          out_dir: Path | str | None = None,
          check_consistency: bool = True,
          localize_poison: bool = False) -> dict:
    """The volume-level ledger row of DESIGN §6a.

    `out_dir`, when given, receives `payload.bin` — the recovered bytes,
    verbatim, whenever `close_volume` returned any.  There is no
    manifest and no sidecar: the sha in the returned row is the sha of
    the file, and the envelope the close verified is what says the bytes
    are the volume's.

    `check_consistency` (default ON) adds the truth-free proof of §
    "THE FOUNTAIN CONSISTENCY CHECK": one extra solve and one re-encode
    of every certified symbol, reported under `consistency`.
    `localize_poison` turns the inconsistent case from a verdict into a
    named key (`localize`), and closes on the survivors.
    """
    certs, added = union_certificates(inputs, analyzer_certs)
    row = inputs.row
    result = fmt_close.close_volume(certs, row)
    payload = result.payload
    got_sha = (hashlib.sha256(bytes(payload)).hexdigest()
               if payload is not None else None)
    verified = bool(result.status == "verified")
    payload_path: str | None = None
    if payload is not None and out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / PAYLOAD_NAME
        target.write_bytes(bytes(payload))
        payload_path = str(target)
    out: dict[str, Any] = {
        "status": result.status,
        "k_total": result.k_total,
        "n_symbols_used": result.symbols_used,
        "n_certificates": len(certs),
        "n_from_production": len(certs) - len(added),
        "n_from_analyzer": len(added),
        "analyzer_keys": [list(key) for key in added],
        "metadata_version": result.metadata_version,
        "metadata": metadata_rank(certs, row),
        "reason": result.reason,
        "payload_bytes": None if payload is None else int(len(payload)),
        "payload_sha256": got_sha,
        "payload_path": payload_path,
        "rank_report": inputs.rank_report,
        "blocks": [
            {"have": int(block.have), "needed": int(block.needed),
             "rank": None if block.rank is None else int(block.rank),
             "short": int(block.short), "solved": bool(block.solved)}
            for block in (result.blocks or ())],
    }
    out["verified"] = verified
    out["unverified_reason"] = None if verified else result.reason
    if check_consistency or localize_poison:
        out["consistency"] = consistency(certs, row)
    if localize_poison and not out.get("consistency", {}).get("ok", True):
        out["localize"] = localize(certs, row)
    return out
