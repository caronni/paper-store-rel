#!/usr/bin/env python
"""Give an archived snapshot the page field its own run never published.

    PYTHONPATH=src:. env/bin/python -m measure.page_field.convert self-check
    PYTHONPATH=src:. env/bin/python -m measure.page_field.convert append \\
        --facts RUN/facts.npz --out RUN/facts.post-W2.npz --format REF \\
        --fields-json .../estimate/fields.json
    PYTHONPATH=src:. env/bin/python -m measure.page_field.convert append \\
        --facts RUN/facts.npz --out RUN/facts.post-W2.npz --format REF \\
        --scan A.tiff --dpi 2400 --scan B.tiff --dpi 2400

THE ARCHIVED-CORPUS DOOR, second half.  W2 re-keyed `PlaneField` from
(capture, level, page, plane) to (page, plane), so a pre-W2 snapshot
cannot be read by `snapshot.read` at all; `util/strip_page_fields.py`
(Germano's, tag-based, importing neither receiver version) removes the
old facts without unpacking the blob, and this module puts post-W2 ones
back.  Strip first, ALWAYS: the input is read through `snapshot.read`
and a spine still carrying a pre-W2 node dies there.

WHY THE FIELD GOES BACK IN.  A stripped corpus is safe to read and
useless to resume from: it drops `EvidenceRevision` with the field, and
the sheet-J export that did so cost the resumed receiver its revisions
(9,118 -> 8,977 and 8,602 -> 8,276, `analyzer/README.md` §2.1a) and made
it re-solve from nothing.

TWO SOURCES, ONE APPEND.  `--fields-json` reads a `measure/page_field`
product and costs a file read; what makes that product THIS input's is
four gates, not one — the seed the archive attests, the grid and the
page/plane ids the declared format fixes, the captures the run dir
declares, and the Placement/Certificate counts the product says it
folded (:func:`from_product`).  `--scan/--dpi` re-solves with the
harness beside this file, one capture in memory at a
time.  Either way the appended facts are `data.PlaneField` and
`data.EvidenceRevision` and NOTHING ELSE MOVES: the output is read back
and every non-field fact's `export_facts.fact_digest` must be
identical, which is the whole claim this module makes.  The declared
`--format` is checked against what the archive attests before anything
is read — a format id IS the AES seed (FORMAT-SPACE §16), the
2026-09-02 re-key gave one spelling to two rows, and a solve under the
wrong seed measures its own null and looks ordinary doing it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import NamedTuple

import numpy as np

from holo.receiver import data, snapshot
from holo.receiver.format import identity

from analyzer import unionbase
from analyzer.export_facts import fact_digests

from . import estimate as estimate_module
from . import extract as extract_module
from .products import Declaration

#: The families this module appends, and the only ones it may.
APPENDED: tuple[str, ...] = ("PlaneField", "EvidenceRevision")
#: The families the product's `source.folded_facts` census speaks about.
FOLDED: tuple[str, ...] = ("Placement", "Certificate")
MANIFEST_SUFFIX: str = ".convert.json"


def census(facts: tuple[object, ...]) -> dict[str, int]:
    """How many of each family a snapshot holds."""
    counts: dict[str, int] = {}
    for fact in facts:
        name = type(fact).__name__
        counts[name] = counts.get(name, 0) + 1
    return counts


def check_stripped(facts: tuple[object, ...]) -> None:
    """Refuse an input that already carries a field.

    Appending beside a standing fact would leave two fields for one
    (page, plane) in one spine, and the fold takes whichever the
    ordinal ranks higher — a silent choice this module has no business
    making.
    """
    standing = {name: count for name, count in census(facts).items()
                if name in APPENDED}
    if standing:
        raise ValueError(
            f"the input already carries {standing}; strip it first "
            f"(util/strip_page_fields.py) or append to the stripped copy")


class Declared(NamedTuple):
    """What the RUN DIR around a snapshot says it is: captures and pages.

    The pages ride WITH the captures because they come out of the same
    two readers and answer the same question — is this product about
    this archive — and asking for them separately would open the report
    twice.
    """

    captures: tuple[str, ...]
    pages: tuple[int, ...]


def declared(facts_path: Path) -> Declared:
    """Every capture id and every page the RUN DIR around `facts_path`
    declares.

    `report.json` is what `analyzer/unionbase` reads for exactly this
    question and a finished or converted run dir always has one; a dir
    that has only its journal answers from the head `estimate` already
    reads for the identity.  The two spell the pages differently — the
    report lists the ids it ran (`pages: [0]` on sheet H's mirror), the
    journal's `RunOpen` gives the COUNT — and both come back here as
    the ids themselves.
    """
    run_dir = facts_path.parent
    if (run_dir / "report.json").is_file():
        report = json.loads((run_dir / "report.json").read_text("utf-8"))
        if "pages" not in report:
            raise ValueError(
                f"{run_dir / 'report.json'} declares no `pages` — not a "
                f"finished run's report")
        return Declared(unionbase.declared_captures(run_dir),
                        tuple(int(page) for page in report["pages"]))
    events = extract_module.sibling_events(facts_path)
    if events is None:
        raise ValueError(
            f"{run_dir} declares no captures — no report.json and no "
            f"journal — so a product's evidence revisions cannot be bound "
            f"to it")
    opened, captures = extract_module.events_head(events)
    return Declared(captures, tuple(range(int(opened["pages"]))))


def check_product_shape(payload: dict, format_ref: str, where: Path,
                        archive: Declared) -> None:
    """The grid, the identifiers and the captures — what counts cannot say.

    A census says how BIG the evidence was; these say the product
    describes THIS page of THIS format, measured over captures this
    archive declares.  The grid gate carries the most weight because
    nothing downstream refuses a wrong one: `lib/plane_field.evaluate`
    CLAMPS the tile coordinates it samples at, so a 7x7 grid appended to
    a 53x37 page would read as its edge value everywhere past tile 7 and
    look like a measurement doing it.  The capture gate is the one real
    binding to the archive: `from_product` mints an `EvidenceRevision`
    per capture the product names, and a revision for a capture this run
    never held is a fact about another run.

    THE PAGE GATE IS THE ARCHIVE'S TOO (M3, 2026-09-13).  It used to ask
    only whether the index fell inside the FORMAT's page range, which
    for sheet H's row is 133 — so `page: 7` passed on a one-page
    archive and appended a field bound to nothing.  The run declares
    which pages it ran; that is the range.

    AND THE CAPTURE MAP MUST SAY SOMETHING (M4).  An empty
    `evidence_revision_by_capture` passed the subset test vacuously and
    left the appended `PlaneField` with no revision beside it — the
    same shape of hole the census gate refuses for `folded_facts`, and
    refused here the same way.
    """
    row = identity.resolve_format_ref(format_ref)
    tiles_yx = (int(row.tiles_yx[0]), int(row.tiles_yx[1]))
    planes = {int(fact.plane) for fact in row.streams}
    captures = set(archive.captures)
    pages = set(archive.pages)
    for page in payload["pages"]:
        index = int(page["page"])
        if not 0 <= index < int(row.max_pages):
            raise ValueError(f"{where}: page {index} is outside the "
                             f"{row.max_pages} pages of {format_ref!r}")
        if index not in pages:
            raise ValueError(
                f"{where}: page {index} is not one of the pages this "
                f"archive declares, {sorted(pages)}")
        if tuple(int(value) for value in page["tiles_yx"]) != tiles_yx:
            raise ValueError(
                f"{where}: page {index} is {page['tiles_yx']} tiles; "
                f"{format_ref!r} is {list(tiles_yx)}")
        revisions = page["evidence_revision_by_capture"]
        if not revisions:
            raise ValueError(
                f"{where}: page {index} names no evidence revision, so "
                f"the capture gate would be vacuous and the appended "
                f"field would be bound to no capture at all")
        foreign = sorted(set(revisions) - captures)
        if foreign:
            raise ValueError(
                f"{where}: page {index} carries evidence revisions for "
                f"{foreign}, which this archive does not declare")
        for plane in page["planes"]:
            if int(plane["plane"]) not in planes:
                raise ValueError(
                    f"{where}: plane {plane['plane']} is not one of "
                    f"{format_ref!r}'s {sorted(planes)}")
            for name, want_shape in (("delta_dots_xy", tiles_yx + (2,)),
                                     ("support", tiles_yx),
                                     ("uncertainty_dots", tiles_yx)):
                shape = np.asarray(plane[name]).shape
                if shape != want_shape:
                    raise ValueError(
                        f"{where}: page {index} plane {plane['plane']} "
                        f"{name} is {shape}, not {want_shape}")


def from_product(payload: dict, facts: tuple[object, ...], format_ref: str,
                 where: Path, facts_path: Path) -> tuple[tuple[object, ...],
                                                         dict]:
    """A `fields.json` this snapshot's own spine was solved from.

    FOUR GATES, all refusals, and no one of them is "this exact input".
    `append` has already held the declared reference against what the RUN
    attests in its own journal; here the identity gate is `estimate`'s
    own, run against what the PRODUCT attests it read, so a product
    solved under another seed cannot be appended to this archive under a
    reference that resolves elsewhere.  :func:`check_product_shape` then
    holds the grid, the page and plane ids and the named captures against
    the declared format and the run dir — the shape of the thing and its
    binding to this archive's evidence.  The census gate is the last and
    the weakest: a product carries the Placement and Certificate counts
    it folded, and if they are not this input's counts then the field was
    fitted from other evidence and its revisions describe another run.
    Equal counts do NOT say the evidence was the same evidence — an
    updated pose or a changed certificate keeps a census — which is why
    the other three exist and why a product written from here on should
    carry the source snapshot's digest (the review's fix, 2026-09-13;
    the H product of record predates it and carries none).
    """
    source = dict(payload["source"])
    estimate_module.check_identity(
        estimate_module.Archive("product", where,
                                source.get("archived_identity")), format_ref)
    solved_under = str(source.get("format_ref", ""))
    if estimate_module.archived_seed(solved_under) != \
            identity.resolve_format_ref(format_ref).seed:
        raise ValueError(
            f"{where} was solved under --format {solved_under!r}, which is "
            f"not the seed {format_ref!r} resolves to")
    check_product_shape(payload, format_ref, where, declared(facts_path))
    folded = source.get("folded_facts") or {}
    if not folded:
        raise ValueError(
            f"{where} carries no `folded_facts` census, so it says nothing "
            f"about the evidence it was solved from")
    missing = [name for name in FOLDED if name not in folded]
    if missing:
        raise ValueError(
            f"{where}'s census names no {missing}; the gate would be "
            f"vacuous, which is not the same as passing it")
    counted = census(facts)
    want = {name: int(count) for name, count in folded.items()
            if name in FOLDED}
    got = {name: int(counted.get(name, 0)) for name in want}
    if want != got:
        raise ValueError(
            f"{where} was solved from {want}; this snapshot holds {got}, "
            f"so the product is not this spine's field")

    appended: list[object] = []
    for page in payload["pages"]:
        for plane in page["planes"]:
            appended.append(data.PlaneField(
                page=int(page["page"]), plane=int(plane["plane"]),
                delta_dots_xy=np.asarray(plane["delta_dots_xy"], np.float64),
                support=np.asarray(plane["support"], np.float64),
                uncertainty_dots=np.asarray(plane["uncertainty_dots"],
                                            np.float64),
                n_observations=int(plane["n_observations"]),
                n_captures=int(plane["n_captures"]),
                ordinal=int(page["field_revision"])))
    for page in payload["pages"]:
        for capture_id, revision in sorted(
                page["evidence_revision_by_capture"].items()):
            appended.append(data.EvidenceRevision(
                capture_id=str(capture_id), page=int(page["page"]),
                revision=int(revision)))
    # `conversion_route` is THIS module's; `route` inside `**source` is
    # the product's own (what `estimate` read), and neither overwrites
    # the other — the three manifests of record all named the second and
    # called it the first (F5's P3, 2026-09-13).
    return tuple(appended), {"conversion_route": "fields-json",
                             "product": str(where), **source}


def claim_work_dir(work: Path) -> Path:
    """Take the solve's scratch dir, or refuse a directory already there.

    THE OTHER THING THIS MODULE WRITES, and the same rule as the output
    (`append`: "this module never overwrites").  The name is fixed —
    `<out parent>/convert-planes` — and the solve REMOVES it when it
    returns, so a directory that was already there belongs to a prior or
    a concurrent conversion and is not this invocation's to delete.
    Refusing rather than picking a temporary name is deliberate: the dir
    holds the ingested plane rasters of one capture at a time, gigabytes
    of them at 4800, and an operator who has to restart wants them where
    the recipe says they are.

    The claim IS the `mkdir`, not a test before one: two conversions
    starting together both saw the dir absent and both went on, and the
    second then removed the first's rasters on its way out.
    """
    try:
        work.mkdir(parents=True)
    except FileExistsError:
        raise ValueError(
            f"{work} exists; this module never overwrites — move it aside, "
            f"or convert into another --out parent") from None
    return work


def from_solve(declaration: Declaration, facts: tuple[object, ...],
               facts_path: Path, work: Path) -> tuple[tuple[object, ...],
                                                      dict]:
    """`estimate`'s own pieces, over this snapshot's placements.

    The archived `argv` is not usable — it names flags this tree has
    retired (`--plane-fields`, `--pages`), which is why the captures are
    spelled on the command line — so the `Declaration` is built by hand
    and the identity is taken from the run's own journal, never from
    anything the operator typed.

    The scratch dir is claimed BEFORE the store opens, so the `rmtree`
    at the end removes only what this call created.
    """
    claim_work_dir(work)
    archive = estimate_module.run_dir_archive(facts_path.parent)
    store = estimate_module.open_store(declaration, work)
    folded = estimate_module.fold_evidence(store, facts)
    captures, collections, _cpu_s = estimate_module.collect_captures(
        store, declaration, work)
    solved, _solve_cpu_s = estimate_module.solve_pages(store)
    appended: list[object] = []
    for page in solved:
        appended.extend(page.facts)
    appended.extend(fact for fact in snapshot.collect(store)
                    if isinstance(fact, data.EvidenceRevision))
    shutil.rmtree(work, ignore_errors=True)
    return tuple(appended), {"conversion_route": "solve", **archive.source(),
                             "folded_facts": folded, "captures": captures,
                             "collections": collections,
                             "scans": [str(path)
                                       for path in declaration.scans],
                             "dpis": list(declaration.dpis)}


def report(appended: tuple[object, ...]) -> dict:
    """What went in, per page and per plane."""
    fields = [fact for fact in appended if isinstance(fact, data.PlaneField)]
    return {
        "field_revision_by_page": {
            str(fact.page): int(fact.ordinal) for fact in fields},
        "observations_by_page_plane": {
            f"{fact.page},{fact.plane}": int(fact.n_observations)
            for fact in fields},
        "appended": {name: sum(1 for fact in appended
                               if type(fact).__name__ == name)
                     for name in APPENDED}}


def _verify(out_path: Path, digests: list, n_added: int) -> None:
    back = snapshot.read(out_path)
    if len(back) != len(digests) + n_added:
        raise ValueError(f"{out_path}: read back {len(back)} facts, wrote "
                         f"{len(digests) + n_added}")
    got = fact_digests(back[:len(digests)])
    for index, (want, have) in enumerate(zip(digests, got)):
        if want != have:
            raise ValueError(
                f"{out_path}: fact {index} "
                f"({type(back[index]).__name__}) changed in the round trip")
    tail = {type(fact).__name__ for fact in back[len(digests):]}
    if not tail <= set(APPENDED):
        raise ValueError(f"{out_path}: appended {sorted(tail)}")


def append(facts_path: Path, out_path: Path, format_ref: str, *,
           product: Path | None = None,
           declaration: Declaration | None = None) -> dict:
    """Read, gate, append, write, read back, prove nothing else moved.

    The first gate is the archive's OWN: the run's journal says what it
    was decoded under, and the declared reference must resolve to that
    seed before either route reads a fact — a product's attestation is
    checked after, against the same reference, so a field can only ever
    be appended to the archive it was solved from.
    """
    if out_path.exists():
        raise ValueError(f"{out_path} exists; this module never overwrites")
    estimate_module.check_identity(
        estimate_module.run_dir_archive(facts_path.parent), format_ref)
    facts = tuple(snapshot.read(facts_path))
    check_stripped(facts)
    if product is not None:
        added, source = from_product(json.loads(product.read_text("utf-8")),
                                     facts, format_ref, product, facts_path)
    else:
        assert declaration is not None
        added, source = from_solve(declaration, facts, facts_path,
                                   out_path.parent / "convert-planes")
    if not added:
        raise ValueError("nothing to append: the source published no field")

    digests = fact_digests(facts)
    before = census(facts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write(out_path, facts + added)
    del facts
    try:
        _verify(out_path, digests, len(added))
    except BaseException:
        # An output that failed its own read-back is exactly the file
        # that would be renamed into place; it does not survive.
        out_path.unlink(missing_ok=True)
        raise

    manifest = {"facts": str(facts_path), "out": str(out_path),
                "format_ref": format_ref, "source": source,
                "non_field": {"n_facts": len(digests), "families": before,
                              "digests_sha": fact_digests(
                                  [tuple(digests)])[0]},
                **report(added)}
    Path(str(out_path) + MANIFEST_SUFFIX).write_text(
        json.dumps(manifest, indent=1), "utf-8")
    return manifest


# --------------------------------------------------------- the self-check

#: THE DECLARED FORMAT'S OWN GRID, since 2026-09-13: a synthetic product
#: at any other shape is now a refusal (F5), so the fixture that proves
#: the route has to be the real page's 53x37.  A fixture, not a golden —
#: nothing is frozen against these numbers.
SELF_TILES_YX: tuple[int, int] = (53, 37)
SELF_FORMAT_REF: str = "L:c2-cmy8-r0547@53x37"
SELF_REVISION: int = 41906


def _synthetic_product(facts: tuple[object, ...], format_ref: str,
                       identity_block: dict) -> dict:
    """A `fields.json` in `products.fields_json`'s shape, for one page."""
    counted = census(facts)
    return {
        "source": {"route": "self-check", "source": "synthetic",
                   "archived_identity": identity_block,
                   "format_ref": format_ref,
                   "folded_facts": {name: counted.get(name, 0)
                                    for name in FOLDED}},
        "counts": {"captures": 1, "pages": 1},
        "field_noise_dots": 0.25,
        "pages": [{
            "page": 0, "tiles_yx": list(SELF_TILES_YX),
            "captures": ["cap0"], "field_revision": SELF_REVISION,
            "evidence_revision_by_capture": {"cap0": 7964},
            "planes": [{
                "plane": plane,
                "delta_dots_xy": (np.full(SELF_TILES_YX + (2,),
                                          0.1 * plane)).tolist(),
                "support": np.ones(SELF_TILES_YX).tolist(),
                "uncertainty_dots": np.full(SELF_TILES_YX, 0.3).tolist(),
                "n_observations": 100 + plane, "n_captures": 1,
            } for plane in range(3)]}]}


def self_check(work: Path) -> None:
    """The product route end to end, and six refusals, on no corpus.

    What it pins is this module's OWN contract: the non-field facts come
    back byte-identical, the two appended families are the only new
    ones, and a product that names another seed, another spine's census,
    a capture this archive never declared or a grid the format is not is
    refused before anything is written.
    """
    from holo.receiver.tests import _h3_facts

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    stripped = work / "facts.npz"
    facts = (_h3_facts.window(), _h3_facts.placement(),
             _h3_facts.certificate(ty=0), _h3_facts.certificate(ty=1))
    snapshot.write(stripped, facts)
    extract_module.write_journal(work / "events.jsonl",
                                 "c2-cmy8-r0547@53x37", ["cap0"])
    attested = {"format_id": "c2-cmy8-r0547@53x37",
                "attested_by": "self-check"}
    payload = _synthetic_product(facts, SELF_FORMAT_REF, attested)
    (work / "fields.json").write_text(json.dumps(payload), "utf-8")

    manifest = append(stripped, work / "out.npz", SELF_FORMAT_REF,
                      product=work / "fields.json")
    assert manifest["appended"] == {"PlaneField": 3, "EvidenceRevision": 1}, \
        manifest["appended"]
    assert manifest["field_revision_by_page"] == {"0": SELF_REVISION}
    back = snapshot.read(work / "out.npz")
    assert fact_digests(back[:len(facts)]) == fact_digests(facts), \
        "a non-field fact moved in the round trip"
    assert [type(fact).__name__ for fact in back[len(facts):]] == \
        ["PlaneField"] * 3 + ["EvidenceRevision"]
    assert {(fact.page, fact.plane) for fact in back[len(facts):-1]} == \
        {(0, 0), (0, 1), (0, 2)}
    assert back[-1].revision == 7964

    # THE TWO REFUSALS, and one more: an input that never lost its field.
    extract_module.refuses(
        lambda: append(stripped, work / "seed.npz",
                       "L:c2-cmy8-r0700-p120-x1@3392x2368",
                       product=work / "fields.json"),
        "a product solved under another sheet's seed was appended")
    census_forked = _synthetic_product(facts + (_h3_facts.certificate(ty=2),),
                                       SELF_FORMAT_REF, attested)
    (work / "other.json").write_text(json.dumps(census_forked), "utf-8")
    extract_module.refuses(
        lambda: append(stripped, work / "census.npz", SELF_FORMAT_REF,
                       product=work / "other.json"),
        "a product solved from another spine's census was appended")
    extract_module.refuses(
        lambda: append(work / "out.npz", work / "twice.npz", SELF_FORMAT_REF,
                       product=work / "fields.json"),
        "a snapshot that already carries a field was appended to")
    # And the archive's own word outranks the product's: a run dir whose
    # journal names another sheet refuses the same product.
    other = work / "other-run"
    other.mkdir()
    shutil.copy(stripped, other / "facts.npz")
    extract_module.write_journal(other / "events.jsonl",
                                 "L:c2-cmy8-r0700-p120-x1@3392x2368",
                                 ["cap0"])
    extract_module.refuses(
        lambda: append(other / "facts.npz", work / "journal.npz",
                       SELF_FORMAT_REF, product=work / "fields.json"),
        "a run attesting another identity took the product")
    # The two F5 gates the census cannot make: a capture this run dir
    # never declared, and a grid the declared format is not.
    foreign = _synthetic_product(facts, SELF_FORMAT_REF, attested)
    foreign["pages"][0]["evidence_revision_by_capture"] = {"capX": 7964}
    (work / "foreign.json").write_text(json.dumps(foreign), "utf-8")
    extract_module.refuses(
        lambda: append(stripped, work / "foreign.npz", SELF_FORMAT_REF,
                       product=work / "foreign.json"),
        "a product naming an undeclared capture was appended")
    small = _synthetic_product(facts, SELF_FORMAT_REF, attested)
    page = small["pages"][0]
    page["tiles_yx"] = [7, 7]
    for plane in page["planes"]:
        plane["delta_dots_xy"] = np.zeros((7, 7, 2)).tolist()
        plane["support"] = np.ones((7, 7)).tolist()
        plane["uncertainty_dots"] = np.full((7, 7), 0.3).tolist()
    (work / "grid.json").write_text(json.dumps(small), "utf-8")
    extract_module.refuses(
        lambda: append(stripped, work / "grid.npz", SELF_FORMAT_REF,
                       product=work / "grid.json"),
        "a 7x7 field for a 53x37 page was appended")
    for name in ("seed.npz", "census.npz", "twice.npz", "journal.npz",
                 "foreign.npz", "grid.npz"):
        assert not (work / name).exists(), f"{name} was written anyway"
    print(f"page_field.convert self-check OK — {len(facts)} non-field facts "
          f"byte-identical, {manifest['appended']} appended at revision "
          f"{SELF_REVISION}, six refusals kept")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("append", help="a STRIPPED snapshot, plus a field")
    add.add_argument("--facts", type=Path, required=True)
    add.add_argument("--out", type=Path, required=True)
    add.add_argument("--format", dest="format_ref", required=True)
    add.add_argument("--fields-json", dest="product", type=Path,
                     help="a measure/page_field product of THIS spine")
    add.add_argument("--scan", type=Path, action="append",
                     help="re-solve instead: one --dpi per --scan")
    add.add_argument("--dpi", type=float, action="append")
    add.add_argument("--max-pages", dest="max_pages", type=int, default=None)
    checker = sub.add_parser("self-check", help="pure, no corpus")
    checker.add_argument("--work", type=Path, default=None,
                         help="scratch directory (default: a fresh temp dir)")
    args = parser.parse_args()
    if args.command != "append":
        work = args.work or Path(tempfile.mkdtemp(prefix="convert-self-"))
        print(f"self-check work dir: {work}")
        self_check(work)
        return
    if bool(args.product) == bool(args.scan):
        raise SystemExit("exactly one of --fields-json and --scan/--dpi")
    declaration = None
    if args.scan:
        if len(args.scan) != len(args.dpi or ()):
            raise SystemExit("exactly one --dpi per --scan")
        declaration = Declaration(
            scans=tuple(args.scan),
            dpis=tuple(float(value) for value in args.dpi),
            format_ref=args.format_ref, max_pages=args.max_pages)
    print(json.dumps(append(args.facts, args.out, args.format_ref,
                            product=args.product,
                            declaration=declaration), indent=1))


if __name__ == "__main__":
    main()
