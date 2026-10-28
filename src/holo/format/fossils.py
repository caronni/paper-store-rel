"""The legacy (v1-namespace) fossil catalogue — frozen AES identities.

FORMAT-SPACE §8. Every printed or golden-bearing v1 identity is listed
here verbatim: the exact row-seed byte strings that key the AES-CTR
keystream of the printed record (sheets A–I of e033, the e029/e030/e032
prints, and the golden-pinned catalog rows). Fossil ids are **decode-only
history**: they are matched byte-exactly against this table — never
parsed by the v2 grammar — carry the ``L:`` prefix on every new surface,
and are deleted on the user-declared sunset. The table *mechanism*
survives the sunset as the convenience alias table.

Three fossil codings (``c4-r0550`` and the two ``-x1`` rows) were minted
on the isolated ``c4-row`` branch and are not in the legacy ``CODINGS``
catalog; their full frozen parameter bundles live here so the lattice
constructors (FORMAT-SPACE P1/P5) can rebuild their exact codecs — same
codec ids, same FEC bank ids — for decode and state replay.

Self-check at import: for every fossil whose coding is in ``CODINGS``,
the frozen seed string must equal the string the legacy descriptor
derives from the reconstruction recipe (coding x A4 x margin). The
frozen record and the recipe must agree or this module refuses to load.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

# The prefix fossil ids carry on every new (v2-era) surface, e.g.
# ``--format L:c2-cmy8-r0700-p120-x1@3392x2368``.
L_PREFIX = "L:"

FAMILY_SEED_P100 = b"holo/v1/sites/p100"
FAMILY_SEED_P120 = b"holo/v1/sites/p120"


def is_fossil_ref(format_ref: str) -> bool:
    return format_ref.startswith(L_PREFIX)


def strip_fossil_ref(format_ref: str) -> str:
    if not is_fossil_ref(format_ref):
        raise ValueError(f"not an L:-prefixed fossil reference: "
                         f"{format_ref!r}")
    return format_ref[len(L_PREFIX):]


@dataclass(frozen=True)
class Fossil:
    """One frozen printed/golden v1 identity: spec id + AES row seed."""

    spec_id: str                 # legacy "coding@cells_y x cells_x"
    coding_id: str
    cells_yx: tuple[int, int]
    margin_mm: float             # reconstruction recipe (A4, legacy rule)
    seed: bytes                  # verbatim frozen AES row seed
    evidence: str


@dataclass(frozen=True)
class FossilCoding:
    """Frozen parameter bundle for a fossil coding absent from CODINGS.

    Everything a lattice constructor needs to rebuild the exact codec,
    including the frozen derived-name strings that persisted certificate
    and decoder identities hash (FORMAT-SPACE §8).
    """

    coding_id: str
    cell_dots: int               # dots per cell on the 600 dpi grid
    family: str                  # "k" | "cmy7" | "cmy8"
    rungs: tuple[str, ...]
    n_filler: int
    codec_id: str                # frozen codec id string
    bank_ids: tuple[str, ...]    # frozen FEC bank profile ids, per stream
    pooled: bool


def _fossil(coding_id: str, cells_yx: tuple[int, int], margin_mm: float,
            evidence: str) -> Fossil:
    y, x = cells_yx
    return Fossil(
        spec_id=f"{coding_id}@{y}x{x}",
        coding_id=coding_id,
        cells_yx=cells_yx,
        margin_mm=margin_mm,
        seed=f"holo/v1/{coding_id}/{y}x{x}".encode(),
        evidence=evidence,
    )


_FOSSIL_LIST = (
    _fossil("c3-r0550", (2240, 1536), 6.0,
            "catalog; printed e033 A2 (6mm), G (4mm, same cells)"),
    _fossil("c2-r0550", (3328, 2304), 6.0,
            "catalog; goldens, unprinted"),
    _fossil("c2-r0700", (3328, 2304), 6.0,
            "catalog; goldens, unprinted"),
    _fossil("c2-r0700", (3392, 2368), 4.0,
            "e029 VERIFIED 465,580 B (4.5mm, same cells); e032 VERIFIED; "
            "e033 B, C"),
    _fossil("c2-cmy7-p120-v0", (3328, 2304), 6.0,
            "e032 print; failed live, closed 686,859 B by the uplift "
            "campaign"),
    _fossil("c3-cmy7-p120-v0", (2240, 1536), 6.0,
            "e032 VERIFIED 301,600 B"),
    _fossil("c2-cmy8-p120-v0", (3328, 2304), 6.0,
            "e030 fail; e032 VERIFIED 718,413 B (first CMY8 from paper)"),
    _fossil("c3-cmy8-p120-v0", (2240, 1536), 6.0,
            "e030 partial (663 certs)"),
    _fossil("c2-cmy8-p120-v1", (3328, 2304), 6.0,
            "catalog; sim + emit goldens"),
    _fossil("c3-cmy8-p120-v1", (2240, 1536), 6.0,
            "catalog goldens; printed e033 F (4mm, same cells)"),
    _fossil("c2-cmy8-p120-v1", (3392, 2368), 4.0,
            "e033 D, E printed"),
    _fossil("c4-r0550", (1664, 1152), 6.0,
            "e033 A printed (c4-row branch coding)"),
    _fossil("c2-cmy8-r0700-p120-x1", (3392, 2368), 4.0,
            "e033 I VERIFIED 1,798,761 B"),
    _fossil("c2-cmy8-r0850-p120-x1", (3392, 2368), 4.0,
            "e033 H printed (holo3-max twin)"),
)

FOSSILS: Mapping[str, Fossil] = MappingProxyType(
    {f.spec_id: f for f in _FOSSIL_LIST})

# Frozen parameter bundles for the codings the legacy catalog never held
# (minted on the isolated c4-row branch, frozen by the e033 prints).
FOSSIL_CODINGS: Mapping[str, FossilCoding] = MappingProxyType({
    fc.coding_id: fc for fc in (
        FossilCoding(
            coding_id="c4-r0550", cell_dots=4, family="k",
            rungs=("r0550",), n_filler=0, codec_id="k-v1",
            bank_ids=("k-r0550-p100-v1",), pooled=False),
        FossilCoding(
            coding_id="c2-cmy8-r0700-p120-x1", cell_dots=2, family="cmy8",
            rungs=("r0700", "r0700", "r0700"), n_filler=20,
            codec_id="cmy8-presence-r0700-p120-x1",
            bank_ids=("cmy8-C-r0700-p120-x1", "cmy8-M-r0700-p120-x1",
                      "cmy8-Y-r0700-p120-x1"), pooled=True),
        FossilCoding(
            coding_id="c2-cmy8-r0850-p120-x1", cell_dots=2, family="cmy8",
            rungs=("r0850", "r0850", "r0850"), n_filler=20,
            codec_id="cmy8-presence-r0850-p120-x1",
            bank_ids=("cmy8-C-r0850-p120-x1", "cmy8-M-r0850-p120-x1",
                      "cmy8-Y-r0850-p120-x1"), pooled=True),
    )
})


def get_fossil(spec_id: str) -> Fossil:
    """Byte-exact fossil lookup (accepts a bare id or an L: reference)."""
    key = strip_fossil_ref(spec_id) if is_fossil_ref(spec_id) else spec_id
    try:
        return FOSSILS[key]
    except KeyError:
        near = sorted(s for s in FOSSILS
                      if s.split("@")[0] == key.split("@")[0])
        hint = f"; closest catalogue entries: {near}" if near else ""
        raise KeyError(
            f"unknown fossil id {key!r} (fossils match byte-exactly, "
            f"they are never parsed){hint}") from None


def _fossil_coding(coding_id: str):
    """Rebuild a branch-era fossil coding from its frozen bundle."""
    from .descriptor import Coding
    from .families import cmy8_codec
    fc = FOSSIL_CODINGS[coding_id]
    if fc.family == "k":
        return Coding(coding_id=fc.coding_id, cell_dots=fc.cell_dots,
                      rate_id=fc.rungs[0], n_filler=fc.n_filler)
    if fc.family == "cmy8":
        assert len(fc.rungs) == 3 and len(fc.bank_ids) == 3
        codec = cmy8_codec(
            fc.rungs, 100 + fc.n_filler,
            _codec_id=fc.codec_id, _bank_ids=fc.bank_ids)
        return Coding(coding_id=fc.coding_id, cell_dots=fc.cell_dots,
                      rate_id=None, n_filler=fc.n_filler, codec=codec,
                      pooled_fountain=fc.pooled)
    raise AssertionError(f"{coding_id}: unhandled fossil family")


def resolve_fossil_spec(spec_id: str):
    """A fossil id -> its exact legacy FormatSpec (seed byte-verified).

    Accepts a bare legacy id or an ``L:`` reference.  The reconstruction
    must reproduce the frozen seed bytes or this refuses — the catalogue
    is the authority, the recipe merely rebuilds the object.
    """
    from .descriptor import CODINGS, FormatSpec
    from .layout import MEDIA_MM
    fossil = get_fossil(spec_id)
    coding = CODINGS.get(fossil.coding_id) or _fossil_coding(
        fossil.coding_id)
    spec = FormatSpec(coding=coding, media_id="a4",
                      media_mm=MEDIA_MM["a4"],
                      margin_mm=fossil.margin_mm)
    if spec.seed != fossil.seed or spec.spec_id != fossil.spec_id:
        raise AssertionError(
            f"fossil {fossil.spec_id}: reconstruction forked the frozen "
            f"identity ({spec.spec_id}, {spec.seed!r})")
    return spec


def _self_check() -> None:
    if len(_FOSSIL_LIST) != len(FOSSILS):
        raise AssertionError("duplicate fossil spec ids")
    # Deferred import: fossils is pure data + string law; descriptor is
    # only needed to prove recipe/record agreement.
    from .descriptor import CODINGS, FormatSpec
    from .layout import MEDIA_MM
    for fossil in _FOSSIL_LIST:
        coding = CODINGS.get(fossil.coding_id)
        if coding is None:
            if fossil.coding_id not in FOSSIL_CODINGS:
                raise AssertionError(
                    f"fossil {fossil.spec_id}: coding neither in CODINGS "
                    f"nor in FOSSIL_CODINGS")
            continue
        spec = FormatSpec(coding=coding, media_id="a4",
                          media_mm=MEDIA_MM["a4"],
                          margin_mm=fossil.margin_mm)
        if spec.spec_id != fossil.spec_id or spec.seed != fossil.seed:
            raise AssertionError(
                f"fossil {fossil.spec_id}: frozen record disagrees with "
                f"the reconstruction recipe ({spec.spec_id}, {spec.seed!r})")
        if spec.layout.cells_yx != fossil.cells_yx:
            raise AssertionError(
                f"fossil {fossil.spec_id}: cells {spec.layout.cells_yx} "
                f"!= frozen {fossil.cells_yx}")


_self_check()


__all__ = [
    "FAMILY_SEED_P100",
    "FAMILY_SEED_P120",
    "FOSSIL_CODINGS",
    "FOSSILS",
    "Fossil",
    "FossilCoding",
    "L_PREFIX",
    "get_fossil",
    "resolve_fossil_spec",
    "is_fossil_ref",
    "strip_fossil_ref",
]
