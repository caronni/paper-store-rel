"""decode_diff: the null between two trees' cached sim decode records.

CMY-RECEIVER-PLAN v0.2 A0 (v0.1's N1, reduced).  Base and head each run
the receiver slow lane with their OWN `HOLO3_FIXTURE_CACHE`; every
decode the lane caches leaves `<root>/<render key>/decodes/<decode
key>/record.pkl` (`_h3_fixture_build._publish_decode`).  The two sides'
records are paired by label and compared:

- a DETERMINISTIC record (workers 1;
  test_h3_e2e_modes.py) exactly, on `status`, `exit_code`,
  `payload_sha256`, `certificate_signature` and `attempt_outcomes`;
- a POOLED record (workers > 1, `--complete` or not: its certificate
  set depends on the schedule) on `status`, `exit_code`,
  `payload_sha256` and equal user bits over the certificates both
  sides hold.

A label on one side only differs, and a certificate difference names
the first differing certificate.  Calibration before the tool gates a
wave: head against head (two cold slow lanes of one tree, fresh caches)
reads identical; a field that differs there is reclassified here.

    python -m holo.receiver.tests._h3_decode_diff BASE_CACHE HEAD_CACHE

exits 0 when every record is identical, 1 when any differs.
"""

from __future__ import annotations

import argparse
import pickle
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from holo.receiver.tests import _h3_fixture_build

Record = Mapping[str, object]

OUTCOME_FIELDS: tuple[str, ...] = ("status", "exit_code", "payload_sha256")


@dataclass(frozen=True)
class RecordDiff:
    label: str
    #: None when the label is cached on one side only.
    deterministic: bool | None
    differences: tuple[str, ...]

    @property
    def identical(self) -> bool:
        return not self.differences


def record_fields(record: object) -> dict[str, object]:
    """A live `DecodeRecord` as the cache stores it; a mapping as is."""
    if isinstance(record, Mapping):
        return dict(record)
    return {name: getattr(record, name)
            for name in _h3_fixture_build._CACHED_FIELDS}


def is_deterministic(record: Record) -> bool:
    # workers 1 only.  MEASURED 2026-10-12 (A1's null): three fresh `--complete` decodes of
    # k-complete at 8 workers on ONE tree differ among themselves in one attempt_outcomes
    # entry (which tile the scan/retry rows attempt before completion follows thread
    # timing) while status, payload sha and certificates are identical; `--complete`
    # fixes the stop, not the attempt log.
    return int(record["workers"]) == 1


def _ordered(keys: Iterable[object]) -> list[object]:
    keys = list(keys)
    try:
        return sorted(keys)
    except TypeError:
        return sorted(keys, key=repr)


def _certificates(record: Record) -> dict[tuple, bytes]:
    return {tuple(key): bytes(bits)
            for key, bits in record["certificate_signature"]}


def _first_bit(base_bits: bytes, head_bits: bytes) -> str:
    if len(base_bits) != len(head_bits):
        return f"{len(base_bits)} vs {len(head_bits)} user bits"
    index = next(i for i, (a, b) in enumerate(zip(base_bits, head_bits))
                 if a != b)
    return f"user bit {index} differs"


def first_differing_certificate(base: Record, head: Record,
                                shared_only: bool) -> str | None:
    mine = _certificates(base)
    theirs = _certificates(head)
    keys = (mine.keys() & theirs.keys() if shared_only
            else mine.keys() | theirs.keys())
    for key in _ordered(keys):
        if key not in theirs:
            return f"certificate {key} only in base"
        if key not in mine:
            return f"certificate {key} only in head"
        if mine[key] != theirs[key]:
            return (f"certificate {key}: "
                    f"{_first_bit(mine[key], theirs[key])}")
    return None


def _first_attempt_difference(base: Record, head: Record) -> str | None:
    mine = dict(base["attempt_outcomes"])
    theirs = dict(head["attempt_outcomes"])
    for key in _ordered(mine.keys() | theirs.keys()):
        if mine.get(key) != theirs.get(key):
            return (f"attempt {key}: base {mine.get(key)!r}, "
                    f"head {theirs.get(key)!r}")
    return None


def diff_records(base: Record, head: Record) -> RecordDiff:
    label = str(base["label"])
    if str(head["label"]) != label:
        raise ValueError(f"pairing {label!r} with {head['label']!r}")
    exact = is_deterministic(base) and is_deterministic(head)
    differences: list[str] = []
    if is_deterministic(base) != is_deterministic(head):
        differences.append(
            f"deterministic: base {is_deterministic(base)}, head "
            f"{is_deterministic(head)} (workers / --complete)")
    for name in OUTCOME_FIELDS:
        if base[name] != head[name]:
            differences.append(
                f"{name}: base {base[name]!r}, head {head[name]!r}")
    certificate = first_differing_certificate(base, head,
                                              shared_only=not exact)
    if certificate is not None:
        differences.append(certificate)
    if exact:
        attempt = _first_attempt_difference(base, head)
        if attempt is not None:
            differences.append(attempt)
    return RecordDiff(label, exact, tuple(differences))


def load_records(root: Path) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    where: dict[str, Path] = {}
    for path in sorted(Path(root).rglob(_h3_fixture_build._CACHED_RECORD)):
        entry = path.parent
        if entry.parent.name != "decodes" or entry.name.startswith("."):
            continue
        fields = pickle.loads(path.read_bytes())
        label = str(fields["label"])
        if label in records:
            raise ValueError(
                f"{root}: label {label!r} is cached twice ({where[label]} "
                f"and {entry}) -- this cache has seen two trees; run each "
                f"side with a fresh HOLO3_FIXTURE_CACHE")
        records[label] = fields
        where[label] = entry
    return records


def diff_caches(base_root: Path, head_root: Path) -> tuple[RecordDiff, ...]:
    base = load_records(base_root)
    head = load_records(head_root)
    if not base and not head:
        raise ValueError(
            f"no cached decode record under {base_root} or {head_root}: "
            f"an empty comparison is no null")
    out: list[RecordDiff] = []
    for label in sorted(base.keys() | head.keys()):
        if label not in head:
            out.append(RecordDiff(label, None, ("only in base",)))
        elif label not in base:
            out.append(RecordDiff(label, None, ("only in head",)))
        else:
            out.append(diff_records(base[label], head[label]))
    return tuple(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m holo.receiver.tests._h3_decode_diff",
        description="Pair two fixture caches' sim decode records by label "
                    "and report identical or the first difference.")
    parser.add_argument("base_cache", type=Path,
                        help="the base tree's HOLO3_FIXTURE_CACHE root")
    parser.add_argument("head_cache", type=Path,
                        help="the head tree's HOLO3_FIXTURE_CACHE root")
    args = parser.parse_args(argv)
    diffs = diff_caches(args.base_cache, args.head_cache)
    modes = {True: "exact", False: "pooled", None: "-"}
    for diff in diffs:
        verdict = "identical" if diff.identical else "DIFFERS"
        print(f"{diff.label:<28} {modes[diff.deterministic]:<7} {verdict}")
        for line in diff.differences:
            print(f"    {line}")
    n_differ = sum(not diff.identical for diff in diffs)
    print(f"{len(diffs)} records, {n_differ} differ")
    return 0 if n_differ == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
