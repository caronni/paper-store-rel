"""Export a fact snapshot with the analyzer's certificates folded in.

The analyzer certifies tile-streams production left open, but it writes
them into its own ledger, not into the run's `facts.npz`.  A holo3
`--resume` reads only the snapshot, so an analyzer certificate cannot
reach a production rerun — its labels never join the known frame of a
neighbouring tile, and its bits never reach the close.  This module is
the one-way door between the two: snapshot + ledger(s) -> a NEW
snapshot that holo3 resumes from.

WHAT IS PRESERVED.  `snapshot.collect` documents its order as a
DEPENDENCY order — surveys, windows, seeds, placements, ctx, fields,
pooled ctx, and certificates LAST, so the rows born by a certificate see
the poses they enumerate.  The export therefore copies the input fact
tuple verbatim and APPENDS the analyzer's certificates after the
snapshot's own, sorted by key for determinism.  Nothing is reordered,
rewritten or dropped, and the output is read back and compared fact by
fact before the manifest is written.

THE SOURCE SPELLING is `analyzer/<certifying_rung>` — e.g.
`analyzer/L2:damped@300`.  Nothing on the resume path PARSES a
certificate's `source`: `store._fold_certificate` and
`tiles._merge_certificate` only quote it in the conflict message, and
`tiles.source_tag` merely MINTS the production `tiles/<stage>` strings.
So the spelling is free, and it is chosen to be legible in a conflict
message and to say which rung of which instrument minted the bits.  A
`:` and an `@` inside it are safe for the same reason.

THE CAVEAT the operator must respect: a resume from the exported
snapshot must declare the SAME captures the base snapshot's poses were
fitted on.  The snapshot carries poses, not evidence (holo3 regenerates
evidence from the rasters), so resuming with a different capture set
either crashes in the survey fold (a dropped capture — ruled and
accepted upstream) or re-poses against rasters the placements were never
fitted to.  Export from the base snapshot of the run you intend to
resume; never mix one run's snapshot with another run's ledger.

CONFLICTS ARE FATAL, never silently resolved.  Two ledgers that certify
different user bits for one key, or a ledger that disagrees with the
snapshot's own certificate, stop the export: both bits passed a CRC over
the same k bits, so a disagreement is a false accept somewhere and the
operator must be told which key.
"""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from holo3 import data, snapshot

from . import close as close_mod
from . import ledger as ledger_mod
from .types import (LIST_RUNGS, VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST,
                    VERDICT_WRONG, Key)

#: The `source` prefix of every certificate this module mints.
SOURCE_PREFIX = "analyzer"

MANIFEST_SUFFIX = ".manifest.json"


class ExportError(RuntimeError):
    """The export refuses — nothing was written."""


def source_for(rung: str | None) -> str:
    """`analyzer/<certifying_rung>`; an unnamed rung degrades to the prefix."""
    rung = str(rung).strip() if rung else ""
    return f"{SOURCE_PREFIX}/{rung}" if rung else SOURCE_PREFIX


# ------------------------------------------------------------- digests

def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(Path(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _feed(digest: Any, value: Any) -> None:
    """Hash one encodable value the way `snapshot._encode` walks it.

    A per-fact digest exists so the read-back comparison does not need
    the input fact tuple alive beside the output one: sheet I's blob is
    2.1 GB and holding two decoded copies costs 13 GB of RAM for a
    comparison a 32-byte digest settles.
    """
    import dataclasses

    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        digest.update(f"a|{array.dtype.str}|{array.shape}|".encode())
        digest.update(memoryview(array).cast("B"))
        return
    if isinstance(value, np.generic):
        _feed(digest, value.item())
        return
    if isinstance(value, Fraction):
        digest.update(f"f|{value.numerator}/{value.denominator}|".encode())
        return
    if isinstance(value, tuple):
        digest.update(f"t|{len(value)}|".encode())
        for item in value:
            _feed(digest, item)
        return
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        digest.update(f"d|{type(value).__name__}|".encode())
        for held in dataclasses.fields(value):
            digest.update(f"{held.name}|".encode())
            _feed(digest, getattr(value, held.name))
        return
    digest.update(f"s|{type(value).__name__}|{value!r}|".encode())


def fact_digest(fact: Any) -> str:
    digest = hashlib.blake2b(digest_size=16)
    _feed(digest, fact)
    return digest.hexdigest()


def fact_digests(facts: Iterable[Any]) -> list[str]:
    return [fact_digest(fact) for fact in facts]


# ------------------------------------------------------------- ledgers

def _row_key(row: Mapping[str, Any]) -> Key:
    return (int(row["page"]), int(row["ty"]), int(row["tx"]),
            str(row["stream_id"]))


def _row_bits(row: Mapping[str, Any]) -> np.ndarray | None:
    bits = (row.get("rungs") or {}).get("user_bits")
    if bits is None:
        return None
    bits = np.asarray(bits, np.uint8)
    return None if bits.size == 0 else bits


def _exposure_of(header: Mapping[str, Any]) -> dict:
    """The RUN-level exposure the ledger header states (DESIGN §0).

    Copied, never recomputed: exposure is a property of the pass that
    consulted the CRC, and this tool consults nothing.
    """
    return {
        "distinct": (None if header.get("exposure_distinct") is None
                     else int(header["exposure_distinct"])),
        "expected_false": (None
                           if header.get("exposure_expected_false") is None
                           else float(header["exposure_expected_false"])),
        "bound_expected_false": (
            None if header.get("exposure_bound_expected_false") is None
            else float(header["exposure_bound_expected_false"])),
    }


def read_ledger(path: Path | str) -> tuple[dict, list[dict]]:
    header, rows = ledger_mod.read_rows(path)
    return header, rows


def _is_list_rung(rung: str | None) -> bool:
    return str(rung or "").split(":")[0] in LIST_RUNGS


class Collected:
    """The analyzer certificates one export will append."""

    def __init__(self) -> None:
        self.bits: dict[Key, np.ndarray] = {}
        self.detail: dict[Key, dict] = {}
        self.skipped_already_certified: list[Key] = []
        self.skipped_list_rung: list[Key] = []
        self.duplicates: list[Key] = []
        #: A row that HOLDS user bits under a verdict this tool does not
        #: export — `false_accept` is the live case (a list rung certified
        #: against GT and lost, and DESIGN §0's sticky rule then paints the
        #: whole row).  Dropping it is right; dropping it SILENTLY is not,
        #: so it is counted and its keys are named in the manifest.
        self.skipped_other_verdict: list[Key] = []
        #: `certified` with no `rungs["user_bits"]` — nothing to fold.
        self.skipped_no_user_bits: list[Key] = []

    @property
    def keys(self) -> tuple[Key, ...]:
        return tuple(sorted(self.bits))


def collect(snapshot_certs: Mapping[Key, Any],
            ledgers: Sequence[tuple[str, Mapping[str, Any],
                                    Sequence[Mapping[str, Any]]]],
            *, include_list_rungs: bool = True) -> Collected:
    """Certificates from the ledgers, minus what the snapshot already has.

    First ledger wins a duplicate; a disagreement — between two ledgers,
    or with the snapshot — is fatal.
    """
    out = Collected()
    for name, _header, rows in ledgers:
        for row in rows:
            verdict = row.get("verdict")
            key = _row_key(row)
            if verdict == VERDICT_WRONG:
                raise ExportError(
                    f"{name}: row {key} carries verdict 'wrong' — a ledger "
                    f"with a wrong certificate never seeds a snapshot")
            if verdict not in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST):
                if _row_bits(row) is not None:
                    out.skipped_other_verdict.append(key)
                continue
            bits = _row_bits(row)
            if bits is None:
                out.skipped_no_user_bits.append(key)
                continue
            rung = row.get("certifying_rung")
            if verdict == VERDICT_CERTIFIED_LIST or _is_list_rung(rung):
                if not include_list_rungs:
                    out.skipped_list_rung.append(key)
                    continue
            standing = snapshot_certs.get(key)
            if standing is not None:
                if not np.array_equal(np.asarray(standing.user_bits,
                                                 np.uint8), bits):
                    raise ExportError(
                        f"CONFLICT at {key}: the snapshot's certificate "
                        f"({standing.source}) and {name}'s row certify "
                        f"different user bits")
                out.skipped_already_certified.append(key)
                continue
            held = out.bits.get(key)
            if held is not None:
                if not np.array_equal(held, bits):
                    raise ExportError(
                        f"CONFLICT at {key}: {out.detail[key]['ledger']} and "
                        f"{name} certify different user bits")
                out.duplicates.append(key)
                continue
            out.bits[key] = bits
            out.detail[key] = {
                "ledger": name,
                "verdict": str(verdict),
                "rung": None if rung is None else str(rung),
                "rule": (None if row.get("certifying_rule") is None
                         else str(row["certifying_rule"])),
                "generation": (None if row.get("generation") is None
                               else int(row["generation"])),
                "source": source_for(rung),
            }
    return out


def certificates_for(collected: Collected) -> tuple[Any, ...]:
    """`holo3.data.Certificate` per collected key, in key order."""
    out = []
    for key in collected.keys:
        page, ty, tx, stream_id = key
        out.append(data.Certificate(
            page=int(page), ty=int(ty), tx=int(tx), stream_id=str(stream_id),
            user_bits=np.asarray(collected.bits[key], np.uint8),
            source=str(collected.detail[key]["source"])))
    return tuple(out)


def _counter(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        name = "none" if value is None else str(value)
        out[name] = out.get(name, 0) + 1
    return dict(sorted(out.items()))


def counts_of(collected: Collected, n_snapshot_certs: int) -> dict:
    detail = [collected.detail[key] for key in collected.keys]
    return {
        "snapshot_certificates": int(n_snapshot_certs),
        "added": len(collected.keys),
        "added_certified": sum(1 for item in detail
                               if item["verdict"] == VERDICT_CERTIFIED),
        "added_certified_list": sum(
            1 for item in detail
            if item["verdict"] == VERDICT_CERTIFIED_LIST),
        "skipped_already_certified": len(collected.skipped_already_certified),
        "skipped_duplicate_across_ledgers": len(collected.duplicates),
        "skipped_list_rung_excluded": len(collected.skipped_list_rung),
        "skipped_other_verdict": len(collected.skipped_other_verdict),
        "skipped_no_user_bits": len(collected.skipped_no_user_bits),
        "by_stream": _counter(key[3] for key in collected.keys),
        "by_rung": _counter(item["rung"] for item in detail),
        "by_generation": _counter(item["generation"] for item in detail),
        "total_after_export": int(n_snapshot_certs) + len(collected.keys),
    }


# ------------------------------------------------- the consistency hook

def consistency_of(certificates: Sequence[Any], row: Any) -> dict | None:
    """The FOUNTAIN consistency check on the union, when one exists.

    Gate 1 used to live here: every added certificate was compared with
    the emitted payload's user bits, which meant `export-facts` opened a
    payload.  The 2026-09-04 ruling took that away — truth is an offline
    column — and put a truth-free check in its place: the fountain is
    over-determined above K, so an over-determined GF(2) system both
    DETECTS a wrong symbol and can localize it, with no payload in the
    room at all.

    That check is `analyzer.close.consistency`, and it LANDED on
    2026-09-04.  The call stays guarded because the manifest must be able
    to say that no consistency check ran rather than silently claim one
    did; the guard is pinned from both sides by a test.  When the check
    reports trouble (`ok` False), the export REFUSES — exactly the place
    gate 1 refused — and the refusal NAMES the disagreeing keys, because
    the operator's next move is `analyzer close --localize`, which turns
    them into an excluded set and a close on the survivors.
    """
    hook = getattr(close_mod, "consistency", None)
    if hook is None:
        return None
    result = hook(tuple(certificates), row)
    if isinstance(result, Mapping) and result.get("ok") is False:
        keys = [",".join(str(part) for part in key)
                for key in (result.get("inconsistent_keys") or ())]
        shown = ", ".join(keys[:8]) + ("…" if len(keys) > 8 else "")
        raise ExportError(
            f"FOUNTAIN CONSISTENCY FAILED on the union: "
            f"{result.get('reason') or result}"
            + (f"; disagreeing key(s): {shown}" if keys else "")
            + "; run `analyzer close --localize` to name and exclude the "
              "poisoned symbol(s)")
    return dict(result) if isinstance(result, Mapping) else {"result": result}


# ------------------------------------------------------------- the export

def snapshot_certificates(facts: Sequence[Any]) -> dict[Key, Any]:
    return {(int(fact.page), int(fact.ty), int(fact.tx), str(fact.stream_id)):
            fact for fact in facts
            if type(fact).__name__ == "Certificate"}


def max_page(facts: Sequence[Any]) -> int:
    pages = [int(fact.page) for fact in facts if hasattr(fact, "page")]
    if not pages:
        raise ExportError("no fact in the snapshot carries a page")
    return max(pages)


def _format_ref(ledgers: Sequence[tuple[str, Mapping[str, Any], Any]],
                override: str | None) -> tuple[str | None, str]:
    if override:
        return str(override), "--format-ref"
    seen = {str(header["format_ref"]) for _name, header, _rows in ledgers
            if header.get("format_ref")}
    if not seen:
        return None, "absent"
    if len(seen) > 1:
        raise ExportError(
            f"the ledgers declare different format refs {sorted(seen)}; "
            f"pass --format-ref to say which one the snapshot is")
    return sorted(seen)[0], "ledger header"


def export(snapshot_path: Path | str, ledger_paths: Sequence[Path | str],
           out_path: Path | str, *, format_ref: str | None = None,
           include_list_rungs: bool = True,
           dry_run: bool = False) -> dict:
    """Snapshot + ledger(s) -> a new snapshot; returns the manifest."""
    snapshot_path = Path(snapshot_path)
    out_path = Path(out_path)
    if not snapshot_path.exists():
        raise ExportError(f"{snapshot_path} is absent")
    if not ledger_paths:
        raise ExportError("no --ledger given")
    if out_path.resolve() == snapshot_path.resolve():
        raise ExportError(
            f"--out {out_path} is the input snapshot; an export never "
            f"overwrites the base a resume must be able to fall back to")

    ledgers: list[tuple[str, dict, list[dict]]] = []
    for path in ledger_paths:
        path = Path(path)
        if not path.exists():
            raise ExportError(f"ledger {path} is absent")
        header, rows = read_ledger(path)
        ledgers.append((str(path), header, rows))

    used_ref, ref_from = _format_ref(ledgers, format_ref)
    facts = snapshot.read(snapshot_path)
    certs = snapshot_certificates(facts)
    collected = collect(certs, ledgers,
                        include_list_rungs=include_list_rungs)
    added = certificates_for(collected)

    consistency: dict | None = None
    consistency_reason = "no format ref (no ledger header declares one)"
    if used_ref is not None:
        from holo3.format import identity
        try:
            row = identity.resolve_format_ref(used_ref)
        except ValueError as error:
            raise ExportError(
                f"format ref {used_ref!r} does not resolve: {error}"
            ) from error
        consistency = consistency_of(
            tuple(certs.values()) + tuple(added), row)
        if consistency is None:
            consistency_reason = "analyzer.close.consistency is not built yet"

    manifest: dict[str, Any] = {
        "tool": "analyzer export-facts",
        "snapshot": {
            "path": str(snapshot_path),
            "sha256": file_sha256(snapshot_path),
            "n_facts": len(facts),
            "n_certificates": len(certs),
        },
        "ledgers": [
            {"path": name,
             "sha256": file_sha256(name),
             "n_rows": len(rows),
             "format_ref": header.get("format_ref"),
             "run_dir": header.get("run_dir"),
             "seed": header.get("seed"),
             "rungs": header.get("rungs"),
             "rules": header.get("rules"),
             "exposure": _exposure_of(header)}
            for name, header, rows in ledgers],
        "format_ref": used_ref,
        "format_ref_from": ref_from,
        "include_list_rungs": bool(include_list_rungs),
        "source_spelling": f"{SOURCE_PREFIX}/<certifying_rung>",
        "counts": counts_of(collected, len(certs)),
        "added_keys": [list(key) for key in collected.keys],
        "skipped_other_verdict_keys": [
            list(key) for key in sorted(collected.skipped_other_verdict)],
        "added_detail": {",".join(str(part) for part in key):
                         collected.detail[key] for key in collected.keys},
        "consistency": consistency,
        "consistency_skipped": (None if consistency is not None
                                else consistency_reason),
        "output": {"path": str(out_path), "n_facts": len(facts) + len(added),
                   "n_certificates": len(certs) + len(added),
                   "sha256": None},
        "dry_run": bool(dry_run),
        "verified": None,
    }
    if dry_run:
        return manifest

    digests = fact_digests(facts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write(out_path, tuple(facts) + added)
    added_digests = fact_digests(added)
    n_facts, n_certs = len(facts), len(certs)
    del facts, certs, collected
    manifest["verified"] = verify(out_path, digests, added_digests,
                                  n_facts=n_facts, n_certificates=n_certs)
    manifest["output"]["sha256"] = file_sha256(out_path)
    manifest_path = Path(str(out_path) + MANIFEST_SUFFIX)
    manifest_path.write_text(json.dumps(manifest, indent=2), "utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def verify(out_path: Path, digests: Sequence[str],
           added_digests: Sequence[str], *, n_facts: int,
           n_certificates: int) -> dict:
    """Read the output back and prove nothing moved (PLAN §6)."""
    back = snapshot.read(out_path)
    if len(back) != n_facts + len(added_digests):
        raise ExportError(
            f"{out_path}: read back {len(back)} facts, wrote "
            f"{n_facts + len(added_digests)}")
    got = fact_digests(back)
    for index, (want, have) in enumerate(zip(digests, got)):
        if want != have:
            raise ExportError(
                f"{out_path}: fact {index} "
                f"({type(back[index]).__name__}) changed in the round trip")
    if list(got[n_facts:]) != list(added_digests):
        raise ExportError(
            f"{out_path}: the appended certificates did not survive the "
            f"round trip")
    back_certs = snapshot_certificates(back)
    if len(back_certs) != n_certificates + len(added_digests):
        raise ExportError(
            f"{out_path}: {len(back_certs)} certificates read back, "
            f"{n_certificates + len(added_digests)} expected")
    tail = back[n_facts:]
    if any(type(fact).__name__ != "Certificate" for fact in tail):
        raise ExportError(f"{out_path}: a non-certificate was appended")
    return {
        "n_facts": len(back),
        "n_certificates": len(back_certs),
        "snapshot_facts_unchanged": True,
        "appended_certificates": len(tail),
    }
