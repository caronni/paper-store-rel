"""The six parity volumes, and the gap sets recomputed from the record.

THE CASE SOURCE. ``_distill/verify/parity/`` holds the 2026-08-28/29
holo1<->holo3 certificate-level parity campaign: per volume a holo1
certificate extract (``holo1-*.json``, addresses only, itself
cross-checked against a real ``load_session``) and a holo3 full-harvest
run directory whose ``events.jsonl`` carries the ``TileOutcome`` rows.
This module RECOMPUTES the gap sets from those two primaries — never
from ``parity.json``'s summary — and then CROSS-CHECKS the recomputed
counts against the recorded ones. A mismatch refuses the run: it means
the inputs are not the recorded record (the ``crosscheck_headers`` rule
of the holo2 generator, carried over).

WHICH HOLO3 RUN IS THE BASELINE. Five of the six volumes have a `post-N`
re-harvest (the post-forensics wave); `post-4` was killed at the 58 GiB
ceiling and never measured, so volume 4's baseline stays `run-4`. The
choice is DECLARED per volume here, with its expected miss/gain counts,
rather than inferred — the driver's rule: if the tile lists are
ambiguous, the run dirs are the authority.

THE THREE CLASSES (holo1 and holo3 both at full harvest):

* ``miss``    = holo1 certified, holo3 did not — the gap under study.
* ``gain``    = holo3 certified, holo1 did not.
* ``neither`` = certified by neither side (opt-in: this is where toolbox
  yield lives, but it is 158-410 addresses on the colour volumes).

A "target" is one (page, ty, tx, stream) address; cases are cut in tile
space, so several streams of one tile position share a case.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import _paths

Address = tuple[int, int, int, str]         # (page, ty, tx, stream_id)
Tile = tuple[int, int]                      # (ty, tx)

CLASS_NAMES = ("miss", "gain", "neither")


@dataclass(frozen=True)
class Volume:
    """One declared volume: its identity, its inputs, its expectations."""

    key: str
    step: str
    label: str
    format_ref: str
    scans: tuple[Path, ...]
    dpi: tuple[float, ...]
    tile_matrix: tuple[int, int]
    holo1_state: Path
    holo1_certs_json: Path
    payload: Path
    payload_sha256: str
    payload_bytes: int
    #: The holo3 full-harvest run whose certificate set defines the gap.
    holo3_run: str
    expect_miss: int
    expect_gain: int
    #: True for the colour volumes: crops change the colour context the
    #: calibration heads pool over, so their verdicts are SCREENS.
    colour: bool

    @property
    def run_dir(self) -> Path:
        return _paths.PARITY_DIR / self.holo3_run

    @property
    def default_classes(self) -> tuple[str, ...]:
        return ("miss", "gain")


VOLUMES: tuple[Volume, ...] = (
    Volume(
        key="e029", step="2", label="e029 HP K (c2-r0700)",
        format_ref="L:c2-r0700@3392x2368",
        scans=(Path("scratch/e028/"
                    "hp-canon-c2-ink-counting.tiff"),),
        dpi=(4800.0,), tile_matrix=(53, 37),
        holo1_state=Path("scratch/e028/"
                         "holo-c2-r0700-q07-ink-counting/receive.state"),
        holo1_certs_json=_paths.PARITY_DIR / "holo1-e029-hp-k.json",
        payload=_paths.PARITY_DIR / "out-2.bin",
        payload_sha256="e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e5"
                       "02f1ab9dd165787af",
        payload_bytes=465_580,
        holo3_run="post-2", expect_miss=2, expect_gain=0, colour=False),
    Volume(
        key="xerox-k", step="5", label="xerox c2-k (c2-r0700)",
        format_ref="L:c2-r0700@3392x2368",
        scans=(Path("scratch/in/"
                    "xerox-canon-c2-bw.tiff"),),
        dpi=(4800.0,), tile_matrix=(53, 37),
        holo1_state=Path("scratch/in/"
                         "holo-xerox-c2-counting-receive.state"),
        holo1_certs_json=_paths.PARITY_DIR / "holo1-xerox-c2-k.json",
        payload=_paths.PARITY_DIR / "out-5.bin",
        payload_sha256="e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e5"
                       "02f1ab9dd165787af",
        payload_bytes=465_580,
        holo3_run="post-5", expect_miss=5, expect_gain=2, colour=False),
    Volume(
        key="xerox-c3-cmy7", step="3", label="xerox c3-cmy7",
        format_ref="L:c3-cmy7-p120-v0@2240x1536",
        scans=(Path("scratch/in/"
                    "xerox-canon-c3-cmy7-2400dpi.tiff"),),
        dpi=(2400.0,), tile_matrix=(35, 24),
        holo1_state=Path("scratch/in/"
                         "holo-xerox-c3-cmy7-counting-receive.state"),
        holo1_certs_json=_paths.PARITY_DIR / "holo1-xerox-c3-cmy7.json",
        payload=_paths.PARITY_DIR / "out-3.bin",
        payload_sha256="4f68dbf932324aa85c1af576b9724504eb5dff85039a66a0"
                       "62ff9c9adc4e50c2",
        payload_bytes=301_600,
        holo3_run="post-3", expect_miss=0, expect_gain=95, colour=True),
    Volume(
        key="xerox-c2-cmy8", step="4", label="xerox c2-cmy8",
        format_ref="L:c2-cmy8-p120-v0@3328x2304",
        scans=(Path("scratch/in/"
                    "xerox-canon-c2-cmy8.tiff"),),
        dpi=(4800.0,), tile_matrix=(52, 36),
        holo1_state=Path("scratch/in/"
                         "holo-xerox-c2-cmy8-q05-counting-receive.state"),
        holo1_certs_json=_paths.PARITY_DIR / "holo1-xerox-c2-cmy8.json",
        payload=_paths.PARITY_DIR / "out-4.bin",
        payload_sha256="f13c34db6c96796e65c812b7bb99e7618625e49a34640fce"
                       "e58bc4627e38ecca",
        payload_bytes=718_413,
        # post-4 was killed at the 58 GiB ceiling and never measured;
        # run-4 is this volume's only harvest (parity.json step 4 post:
        # "NO MEASUREMENT").
        holo3_run="run-4", expect_miss=36, expect_gain=88, colour=True),
    Volume(
        key="xerox-c2-cmy7", step="6", label="xerox c2-cmy7 (PK-FINAL)",
        format_ref="L:c2-cmy7-p120-v0@3328x2304",
        scans=(Path("scratch/in/"
                    "xerox-canon-c2-cmy7.tiff"),),
        dpi=(4800.0,), tile_matrix=(52, 36),
        holo1_state=Path("scratch/color-uplift/"
                         "full/xerox-c2-cmy7-pkfinal/receive.state"),
        holo1_certs_json=(_paths.PARITY_DIR
                          / "holo1-xerox-c2-cmy7-pkfinal.json"),
        payload=_paths.PARITY_DIR / "out-6.bin",
        payload_sha256="5963b9d16abca48d66a05f80eb137ce76624b8fdedb48ce1"
                       "3c3ee0cf8f24c993",
        payload_bytes=686_859,
        holo3_run="post-6", expect_miss=26, expect_gain=31, colour=True),
    Volume(
        key="sheet-I", step="7", label="sheet I pooled cmy8",
        format_ref="L:c2-cmy8-r0700-p120-x1@3392x2368",
        scans=(Path("scratch/xerox-canon-18.8-I-"
                    "c2-cmy8-r700-q90-p120-4mm-2400dpi.tiff"),
               Path("scratch/xerox-canon-18.8-I-"
                    "c2-cmy8-r700-q90-p120-4mm-2400dpi-displaced.tiff"),
               Path("scratch/xerox-canon-18.8-I-"
                    "c2-cmy8-r700-q90-p120-4mm-2400dpi-displaced2.tiff")),
        dpi=(2400.0, 2400.0, 2400.0), tile_matrix=(53, 37),
        holo1_state=Path("scratch/"
                         "xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/"
                         "receive.state"),
        holo1_certs_json=_paths.PARITY_DIR / "holo1-sheet-I.json",
        payload=_paths.PARITY_DIR / "out-7.bin",
        payload_sha256="2445b95db5b49bf3e05eb2538e9e247d289a48a4fed2e46e"
                       "b7ba78ab61e4350b",
        payload_bytes=1_798_761,
        holo3_run="post-7", expect_miss=34, expect_gain=176, colour=True),
)

VOLUMES_BY_KEY = {volume.key: volume for volume in VOLUMES}


# --------------------------------------------------------------------
# the two primaries
# --------------------------------------------------------------------


def holo1_addresses(volume: Volume) -> frozenset[Address]:
    """holo1's certified address set, from the recorded extract."""
    record = json.loads(volume.holo1_certs_json.read_text(encoding="utf-8"))
    rows = record["certs"]
    return frozenset((int(a), int(b), int(c), str(d)) for a, b, c, d in rows)


def holo3_addresses(run_dir: Path) -> tuple[frozenset[Address], dict]:
    """holo3's certified address set from a run dir's ``events.jsonl``.

    ``TileOutcome`` rows with ``result == "certified"``, deduped on the
    full key — deduping matters on the pooled multi-capture sheet, where
    one tile re-certifies from more than one capture
    (``compare_parity.py``'s measured note).
    """
    events = run_dir / "events.jsonl"
    if not events.is_file():
        raise SystemExit(f"crop_parity: no events.jsonl in {run_dir}")
    certs: set[Address] = set()
    results: Counter[str] = Counter()
    with events.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "TileOutcome":
                continue
            results[str(event.get("result"))] += 1
            if event.get("result") == "certified":
                certs.add((int(event["page"]), int(event["ty"]),
                           int(event["tx"]),
                           str(event.get("stream_id", "main"))))
    return frozenset(certs), {"tile_outcome_rows": int(sum(results.values())),
                              "results": dict(results)}


# --------------------------------------------------------------------
# the gap sets
# --------------------------------------------------------------------


@dataclass(frozen=True)
class GapSets:
    """One volume's recomputed classes, plus what the sides agreed on."""

    holo1: frozenset[Address]
    holo3: frozenset[Address]
    miss: frozenset[Address]
    gain: frozenset[Address]
    neither: frozenset[Address]
    both: frozenset[Address]
    streams: tuple[str, ...]
    events_meta: dict

    def class_of(self, address: Address) -> str:
        for name in CLASS_NAMES:
            if address in getattr(self, name):
                return name
        raise KeyError(address)

    def targets(self, classes: tuple[str, ...]) -> frozenset[Address]:
        out: set[Address] = set()
        for name in classes:
            if name not in CLASS_NAMES:
                raise ValueError(f"unknown class {name!r}; "
                                 f"known: {list(CLASS_NAMES)}")
            out |= getattr(self, name)
        return frozenset(out)


def gap_sets(volume: Volume, *, pages: int = 1) -> GapSets:
    """Recompute the classes and cross-check them against the record."""
    holo1 = holo1_addresses(volume)
    holo3, meta = holo3_addresses(volume.run_dir)
    streams = tuple(sorted({addr[3] for addr in holo1 | holo3}))
    tiles_y, tiles_x = volume.tile_matrix
    domain = {(page, ty, tx, stream)
              for page in range(pages)
              for ty in range(tiles_y)
              for tx in range(tiles_x)
              for stream in streams}
    for name, certs in (("holo1", holo1), ("holo3", holo3)):
        outside = sorted(set(certs) - domain)
        if outside:
            raise SystemExit(
                f"crop_parity: {volume.key}: {len(outside)} {name} "
                f"certificate(s) outside the {tiles_y}x{tiles_x}x"
                f"{len(streams)} domain, e.g. {outside[:3]}")
    miss = frozenset(holo1 - holo3)
    gain = frozenset(holo3 - holo1)
    if len(miss) != volume.expect_miss or len(gain) != volume.expect_gain:
        raise SystemExit(
            f"crop_parity: {volume.key}: recomputed gap "
            f"(miss {len(miss)}, gain {len(gain)}) disagrees with the "
            f"recorded parity record (miss {volume.expect_miss}, gain "
            f"{volume.expect_gain}) — the inputs are not the record")
    return GapSets(holo1=holo1, holo3=holo3, miss=miss, gain=gain,
                   neither=frozenset(domain - holo1 - holo3),
                   both=frozenset(holo1 & holo3), streams=streams,
                   events_meta=meta)


def resolve_volumes(names: list[str]) -> list[Volume]:
    """``--volume`` selection, with ``all`` and a named refusal."""
    wanted = names or ["all"]
    if "all" in wanted:
        return list(VOLUMES)
    unknown = [name for name in wanted if name not in VOLUMES_BY_KEY]
    if unknown:
        raise SystemExit(f"crop_parity: unknown volume(s) {unknown}; "
                         f"declared: {sorted(VOLUMES_BY_KEY)}")
    return [VOLUMES_BY_KEY[name] for name in wanted]
