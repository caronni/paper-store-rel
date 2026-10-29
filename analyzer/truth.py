"""Ground truth — the OFFLINE SCORER's input, and nothing else.

RULING (Germano, 2026-09-04): the analyzer must never reference ground
truth in any shape DURING a run.  This module is therefore reachable
from exactly one place — `analyzer.score`, the offline tool — and an
import-set test pins that no module a run command can reach imports it.
A certificate's correctness rests on the syndrome+CRC gate with its
priced exposure, on the payload envelope's own sha at the close, on the
fountain's over-determination above K, and on two lanes agreeing
bit-for-bit; scoring against a payload happens afterwards, against ANY
payload we hold — the emitted one, or one a close itself verified.

Two levels of truth, kept apart exactly as ``measure/yask/_truth.py``
keeps them:

* **user bits** — ``measure.crop_parity._gt.reconstruct`` re-encodes the
  EMITTED payload through holo1's generation arithmetic and stops at the
  user-bit boundary.  This is what a certificate is checked against.
* **cell bits** — the emitted printed field (``pageNNN_gt.npy``), one bit
  per plane per cell.  This is what a DETECTOR is measured against, and
  it never makes or gates a certificate.

THREE GATES the scorer runs before it reports (:class:`TruthError`):

1. every certificate in the run's own snapshot equals its GT user bits;
2. the projection of GT user bits through
   ``color_sites.certified_projection`` equals the emitted field on a
   stratified tile sample;
3. the emitted field is block-constant per cell (the one assumption the
   one-dot-per-cell read makes).

Gates 2 and 3 are ``measure.yask._truth``'s own checks, CALLED (they are
page-general already); only their ``SystemExit`` is re-raised as a
:class:`TruthError` so a library caller can catch it.  Gate 1 used to
run inside `export-facts`; it is a scoring question, so it moved here
with the rest of them (`score.py` calls it).

WHERE THE FILES LIVE.  ``manifest.json`` sits in the generation dir for
sheets H and I and one level down in ``volume/`` for J; the ``gt`` field
files are always beside the manifest.  A generation dir is OPTIONAL: the
scorer's payload may be one a close recovered (`close`'s
``payload.bin``), which has no manifest and no emitted field — the user
bits reconstruct from the payload bytes alone, and only the cell-level
splits need the field.  When a generation dir IS given the payload is
sha-gated against its manifest, because there the two must agree.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .types import RunInputs, Truth

#: The default refusal above which a GT reconstruction is not allocated.
MAX_GT_PAGES = 4

#: Tiles per page carried through gate 2 (stratified over tile rows).
GATE_SAMPLE_TILES = 96

SEED_DEFAULT = 20260903


class TruthError(RuntimeError):
    """Ground truth failed its own gate — nothing downstream may report."""


def _rng(seed: int, *parts: Any) -> np.random.Generator:
    """A generator that is a pure function of (seed, *parts) [R §0]."""
    payload = json.dumps([int(seed), *[str(part) for part in parts]],
                         sort_keys=True).encode()
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return np.random.default_rng(int.from_bytes(digest, "big"))


def manifest_dir(gen_dir: Path | str) -> Path:
    """Where ``manifest.json`` and the ``pageNNN_gt.npy`` fields live."""
    gen_dir = Path(gen_dir)
    for candidate in (gen_dir, gen_dir / "volume"):
        if (candidate / "manifest.json").exists():
            return candidate
    raise TruthError(
        f"no manifest.json under {gen_dir} or {gen_dir / 'volume'}")


def _gt_module() -> Any:
    from measure.crop_parity import _gt
    return _gt


# ------------------------------------------------- the holo1 seed bridge

def _rebuilt_v2_spec(row: Any) -> Any:
    """holo1's `FormatSpec` for a v2 identity holo1 cannot name.

    A format id IS the AES row seed, and the two trees hold the frozen
    ids in DIFFERENT catalogues: holo3 gained sheet J's
    ``L:c2-cmy8-r0547@53x37`` (commit 6cc9640), while ``src/holo``'s
    fossil table is the ``holo/v1``-namespace one by law (its self-check
    demands the legacy recipe reproduce the frozen seed, and a v1 recipe
    cannot emit v2 bytes).  So holo1 mints the POST-b8471fc canonical
    spelling for the same sheet, which is a different seed and therefore
    a different fountain — the GT reconstruction would be coin flips.

    This rebuilds the coding holo3's row names, with the frozen coding id
    put back verbatim, and REFUSES unless every field the reconstruction
    reads agrees with holo3's row: the seed bytes first, then the tile
    matrix, the streams, the pooling and the tile counters.  Nothing is
    parsed out of the seed that is not then checked against it.
    """
    import dataclasses

    from holo.format import lattice
    from holo.format.descriptor import FormatSpec

    seed = bytes(row.seed)
    prefix = b"holo/v2/"
    if not seed.startswith(prefix):
        raise TruthError(
            f"{row.row_id}: seed {seed!r} is not a holo/v2 row seed; the "
            f"holo1 bridge is only for v2 identities holo1 cannot name")
    spec_id = seed[len(prefix):].decode()
    coding_id, _, tiles_token = spec_id.rpartition("@")
    try:
        tiles_y, tiles_x = (int(value) for value in tiles_token.split("x"))
        params = lattice.parse_coding_id(coding_id)
        coding = dataclasses.replace(lattice.coding_for(params),
                                     coding_id=coding_id)
        spec = FormatSpec(coding=coding, tiles_yx=(tiles_y, tiles_x))
    except Exception as exc:
        raise TruthError(
            f"{row.row_id}: holo1 cannot rebuild the coding {coding_id!r} "
            f"of seed {seed!r}: {exc}") from exc

    row_streams = tuple((str(fact.stream_id), int(fact.symbol_bits))
                        for fact in row.streams)
    spec_streams = tuple((str(profile.stream_id), int(profile.symbol_bits))
                         for profile in spec.stream_profiles)
    checks = (
        ("seed", bytes(spec.seed), seed),
        ("tiles_yx", tuple(spec._tiles_yx), tuple(row.tiles_yx)),
        ("streams", spec_streams, row_streams),
        ("pooled_fountain", bool(spec.pooled_fountain),
         bool(row.pooled_fountain)),
    )
    for name, got, want in checks:
        if got != want:
            raise TruthError(
                f"{row.row_id}: the holo1 rebuild disagrees on {name} "
                f"({got!r} != {want!r}) — refusing to reconstruct GT")
    for page in range(2):
        for ty in range(int(row.tiles_yx[0])):
            for tx in range(int(row.tiles_yx[1])):
                if spec.tile_counter(page, ty, tx) != row.tile_counter(
                        page, ty, tx):
                    raise TruthError(
                        f"{row.row_id}: tile counters disagree at "
                        f"({page},{ty},{tx}) — refusing to reconstruct GT")
    return spec


class _holo1_resolution:
    """Make holo1 resolve ONE ref to the spec holo3's row describes.

    ``_gt.reconstruct`` looks its spec up itself, by string.  When
    holo1's own resolution of that string already mints holo3's seed
    (every v1 fossil: sheets A–I) this is a no-op and nothing is
    patched.  Otherwise `holo.format.resolve.resolve_format_ref` is
    swapped for the duration of the call — a runtime-composed harness,
    never a tree edit (PLAN §6).
    """

    def __init__(self, ref: str, row: Any) -> None:
        self.ref = str(ref)
        self.row = row
        self._module: Any = None
        self._original: Any = None

    def __enter__(self) -> str:
        from holo.format import resolve as holo1_resolve
        try:
            spec = holo1_resolve.resolve_format_ref(self.ref)
        except Exception:
            spec = None
        if spec is not None and bytes(spec.seed) == bytes(self.row.seed):
            return self.ref
        bridged = _rebuilt_v2_spec(self.row)
        original = holo1_resolve.resolve_format_ref
        ref = self.ref

        def resolve(given: str):
            return bridged if str(given) == ref else original(given)

        self._module, self._original = holo1_resolve, original
        holo1_resolve.resolve_format_ref = resolve
        return ref

    def __exit__(self, *exc: Any) -> None:
        if self._module is not None:
            self._module.resolve_format_ref = self._original
            self._module, self._original = None, None


def load_truth(gen_dir: Path | str | None, payload_path: Path | str,
               row: Any, n_pages: int, *, format_ref: str | None = None,
               max_pages: int = MAX_GT_PAGES) -> Truth:
    """GT user bits for `n_pages` pages, plus the field when there is one.

    `n_pages` is the caller's ``max(live page) + 1`` (DESIGN §2) — the
    declared maximum is never allocated (J's argv declares 100 pages and
    two exist).  Above `max_pages` this REFUSES rather than allocating.

    `gen_dir` is OPTIONAL (2026-09-04).  With one, the payload is
    sha-gated against the manifest and the emitted per-cell field is
    loaded beside it; without one, the user bits are reconstructed from
    the payload bytes alone and `fields` is empty — which is what
    scoring against a payload the CLOSE recovered means, and the case
    the ruling asks for ("works against ANY payload we hold, including
    one the close itself verified").
    """
    payload_path = Path(payload_path)
    n_pages = int(n_pages)
    if n_pages < 1:
        raise TruthError(f"n_pages={n_pages} is not a page count")
    if n_pages > max_pages:
        raise TruthError(
            f"n_pages={n_pages} exceeds --max-gt-pages={max_pages}: "
            f"refusing to allocate {n_pages * row.tiles_per_page * 3} "
            f"tile-stream user-bit vectors")
    if not payload_path.exists():
        raise TruthError(f"payload {payload_path} is absent")
    payload = payload_path.read_bytes()
    got_sha = hashlib.sha256(payload).hexdigest()

    fields_dir: Path | None = None
    manifest: dict = {}
    if gen_dir is not None:
        gen_dir = Path(gen_dir)
        fields_dir = manifest_dir(gen_dir)
        manifest = json.loads(
            (fields_dir / "manifest.json").read_text("utf-8"))
        want_sha = str(manifest["payload"]["sha256"])
        want_bytes = int(manifest["payload"]["bytes"])
        if got_sha != want_sha or len(payload) != want_bytes:
            raise TruthError(
                f"payload {payload_path}: sha {got_sha[:12]}…/"
                f"{len(payload)} B, the manifest declares "
                f"{want_sha[:12]}…/{want_bytes} B")
        declared_pages = len(manifest.get("pages", ()))
        if n_pages > declared_pages:
            raise TruthError(
                f"n_pages={n_pages} but the manifest declares "
                f"{declared_pages} emitted page(s)")

    ref = format_ref or row.row_id
    gt_module = _gt_module()
    with _holo1_resolution(ref, row) as resolved_ref:
        gt = gt_module.reconstruct(resolved_ref, payload, n_pages)
    if tuple(gt.tiles_yx) != tuple(row.tiles_yx):
        raise TruthError(
            f"GT tiles {gt.tiles_yx} != format tiles {row.tiles_yx}")
    if tuple(gt.streams) != tuple(fact.stream_id for fact in row.streams):
        raise TruthError(
            f"GT streams {gt.streams} != format streams "
            f"{tuple(fact.stream_id for fact in row.streams)}")

    fields: dict[int, Any] = {}
    if fields_dir is not None:
        from measure.yask import _truth as yask_truth
        for page in range(n_pages):
            try:
                fields[page] = yask_truth.load_emitted_field(fields_dir, page)
            except SystemExit as exc:
                raise TruthError(f"emitted field page {page}: {exc}") from exc

    return Truth(
        format_ref=ref,
        gen_dir=gen_dir,
        field_dir=fields_dir,
        payload_path=payload_path,
        payload_sha256=got_sha,
        payload_bytes=len(payload),
        n_pages=n_pages,
        tiles_yx=tuple(gt.tiles_yx),
        streams=tuple(gt.streams),
        user_bits=gt.user_bits,
        fields=fields,
        manifest=manifest,
    )


# ------------------------------------------------------------- the gates

def _sample_tiles(truth: Truth, page: int, sample: int,
                  seed: int) -> list[tuple[int, int]]:
    """`sample` tiles of one page, stratified over tile ROWS.

    EVERY tile row contributes: `sample // tiles_y` tiles, plus one more
    on `sample % tiles_y` rows drawn from a deterministic permutation.
    (Taking `round(sample/tiles_y)` per row and stopping at `sample`
    covered only the first 48 of sheet I's 53 rows — the gate then never
    looked at the bottom tenth of the page.)
    """
    tiles_y, tiles_x = truth.tiles_yx
    sample = min(int(sample), tiles_y * tiles_x)
    base, extra = divmod(sample, tiles_y)
    bonus: set[int] = set()
    if extra:
        order = _rng(seed, "gate2-rows", page).permutation(tiles_y)
        bonus = {int(ty) for ty in order[:extra].tolist()}
    out: list[tuple[int, int]] = []
    for ty in range(tiles_y):
        take = min(base + (1 if ty in bonus else 0), tiles_x)
        if take <= 0:
            continue
        rng = _rng(seed, "gate2", page, ty)
        for tx in rng.choice(tiles_x, size=take, replace=False).tolist():
            out.append((ty, int(tx)))
    return out


def gate_certificates(truth: Truth, inputs: RunInputs) -> dict:
    """Gate 1: every snapshot certificate equals its GT user bits."""
    gt_module = _gt_module()
    gt = gt_module.GroundTruth(
        format_ref=truth.format_ref, payload_sha256=truth.payload_sha256,
        tiles_yx=truth.tiles_yx, streams=truth.streams,
        user_bits=truth.user_bits)
    checked = 0
    bad: list[str] = []
    outside: list[str] = []
    for key, certificate in inputs.certificates.items():
        matched, n_bad = gt_module.check_bits(
            gt, key, np.asarray(certificate.user_bits, np.uint8))
        if n_bad < 0:
            outside.append(f"{key} outside the GT domain")
            continue
        checked += 1
        if not matched:
            bad.append(f"{key} ({certificate.source}): {n_bad} bit(s)")
    if outside:
        raise TruthError(
            "certificates outside the GT domain (a truth-path bug): "
            + "; ".join(outside[:10]))
    if bad:
        # The denominator separates the two very different causes: a few
        # mismatches are a receiver disaster; ALL of them mean the run's
        # format ref no longer mints the seed the sheet was generated
        # with (sheet J against commit b8471fc) — a format fork.
        raise TruthError(
            f"WRONG CERTIFICATE(S) in the run's own snapshot: "
            f"{len(bad)} of {checked} checked"
            + (" (every one — suspect a format fork, not the receiver)"
               if len(bad) == checked else "")
            + ": " + "; ".join(bad[:10]))
    return {"gate": "certificates", "checked": checked, "mismatches": 0}


def gate_projection(truth: Truth, inputs: RunInputs, geometry: Any, *,
                    sample: int = GATE_SAMPLE_TILES,
                    seed: int = SEED_DEFAULT) -> dict:
    """Gate 2: GT user bits projected == the emitted field."""
    from measure.yask import _truth as yask_truth
    if not truth.fields:
        return {"gate": "projection", "skipped": "no emitted field "
                "(no --gt-dir)", "tiles": 0, "cells": 0}
    tiles = 0
    cells = 0
    for page in inputs.live_pages:
        field = truth.fields.get(page)
        if field is None:
            raise TruthError(f"no emitted field for live page {page}")
        addresses = _sample_tiles(truth, page, sample, seed)
        try:
            stats = yask_truth.check_projection_against_field(
                inputs.row, geometry, truth.user_bits, field, page,
                addresses)
        except SystemExit as exc:
            raise TruthError(f"projection gate, page {page}: {exc}") from exc
        if int(stats["tiles"]) == 0:
            raise TruthError(
                f"projection gate checked no tile on page {page}")
        tiles += int(stats["tiles"])
        cells += int(stats["cells"])
    return {"gate": "projection", "tiles": tiles, "cells": cells}


def gate_block_constant(truth: Truth, inputs: RunInputs, *,
                        n_probe: int = 4096) -> dict:
    """Gate 3: the emitted field is constant over each cell's dot block."""
    from measure.yask import _truth as yask_truth
    if not truth.fields:
        return {"gate": "block_constant", "skipped": "no emitted field "
                "(no --gt-dir)", "cells_probed": 0}
    probed = 0
    for page in inputs.live_pages:
        field = truth.fields.get(page)
        if field is None:
            raise TruthError(f"no emitted field for live page {page}")
        try:
            probed += int(yask_truth.check_field_is_block_constant(
                truth.field_dir, field, page, n_probe=n_probe))
        except SystemExit as exc:
            raise TruthError(
                f"block-constancy gate, page {page}: {exc}") from exc
    return {"gate": "block_constant", "cells_probed": probed}


def validate_truth(truth: Truth, inputs: RunInputs, geometry: Any, *,
                   sample: int = GATE_SAMPLE_TILES,
                   seed: int = SEED_DEFAULT) -> dict:
    """All three gates; raises :class:`TruthError` on the first failure."""
    return {
        "certificates": gate_certificates(truth, inputs),
        "projection": gate_projection(truth, inputs, geometry,
                                      sample=sample, seed=seed),
        "block_constant": gate_block_constant(truth, inputs),
    }


