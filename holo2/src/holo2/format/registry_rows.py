"""``FormatRowSpec`` — the printed sheet a decode names, and its constructor.

WORKPLAN H3bis: the operator's naming of a printed sheet becomes one
:class:`FormatRowSpec`.  That naming was ``--coding
{c3-r0550,c2-r0550,c2-r0700}`` plus ``--tiles-y/--tiles-x/--pages``; it
is ``--format ID`` plus ``--pages`` since C5 (2026-08-22, RULINGS G6),
the geometry having moved INSIDE the identity string, where it cannot be
stated inconsistently — so the door a CLI opens is
``resolve.format_row_for``, and this module is what it builds through.
The dimensions are OPERATOR-SUPPLIED either way and that is not a
shortcut: the two
hardware-certified K volumes on record (e029 on the M281, e032 on the
AltaLink) are ``L:c2-r0700@3392x2368`` = 53x37 tiles, derived from the
``hp-m281-ink`` 4.5 mm probe row and deliberately absent from v1's
``FORMAT_ROWS`` (whose A4/6 mm ``c2-r0700`` is 52x36 = 3328x2304).  A
receiver that could only name registry rows could not read the sheets the
project actually printed.

The row is built from :mod:`holo2.format.format_v1`, so the close's view
(``CloseSpec`` via :meth:`FormatRowSpec.close_spec`) and the tile chain's
view (:class:`~holo2.format.format_v1.TileFormat`) cannot drift apart: both
are projections of one coding + one tile grid.  :func:`tile_format_for` is
the inverse direction, for a session that already holds its row.

R2 moved the row type here from ``engine/runtime.py``.  It is printed-format
truth — a tile grid, a physical cell pitch, the stream profiles the close
reads — and holding it in the engine forced ``format`` to import ``engine``
to build one.
The engine now names no format type at all: a row reaches the scheduler as
data on the derived plane.

This module exists separately from ``format_v1`` only to keep the
direction of dependency honest: the numeric leaves (``format_v1``,
``pilots``, ``ldpc``) must not pull the row constructor in behind them.
The tile chain that reads those leaves is ``solve``'s, one package up.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..core import StreamId
from .close_spec import COUNTER_BITS, MAX_TILES, CloseSpec, CloseStreamProfile
from .families import CodecFacts, colour_codec
from .family import Family
from .format_v1 import (STREAM_MAIN, TILE_CELLS, TileFormat,
                        _legacy_coding, colour_codec_refusal,
                        legacy_identity, tile_format)
from .lattice import CodingParams, ParsedFormat, is_fossil_ref


def native_cell_pitch_px(dpi_true: float, pitch_in: Fraction) -> Fraction:
    """Cell pitch in native pixels (exact rational): pitch x this dpi.

    THE WHOLE OF WHAT A RECEIVE PATH NEEDS TO KNOW ABOUT PRINTED CELL
    SIZE (RULINGS G4, 2026-08-22).  It used to be
    ``Fraction(c_dots) * Fraction(str(dpi)) / PRINT_DPI`` with
    ``PRINT_DPI = 600`` — the ENGINE grid privileged in the middle of a
    SCAN measurement, which is ``src/holo``'s deviation §15.3-2 that
    holo2 had copied.  The two forms are ARITHMETICALLY IDENTICAL
    wherever the old one applied, because ``pitch_in`` IS
    ``Fraction(c_dots, 600)`` for a 600-grid row and Fraction
    multiplication is exact — pinned by
    ``holo2/tests/format/test_format_rows.py`` and cross-tree by
    ``tests/holo2_oracles/test_oracle_lattice.py``.  The fork it
    prevents: a 1200-dpi engine's 3-dot cell (``1i400``) read as if the
    number 3 meant anything without the engine that printed it.

    Not row state: which pitch a capture SHOWS is one capture's
    measurement (the survey's vote), and which pitch a row IS, is
    identity; this function is where the two meet.

    THE ONE-INCH BOUND IS THE UNIT'S OWN GUARD (review fix, C3,
    2026-08-22).  The pre-C3 signature took a dot count and refused a
    pitch loudly (``_positive_integer(Fraction(1, 300))`` raised); the
    post-C3 one takes a pitch and would accept a dot count SILENTLY, at
    600x the intended pixel pitch.  A printed cell is never an inch
    wide, so the bound forbids nothing constructible (L17) and makes a
    caller left on the old unit fail by name rather than numerically
    (P12).

    THE BOUND IS TWO-SIDED (review fix, C3b-c4, 2026-08-22).  A
    non-positive pitch lays a zero-step or backwards cell lattice; at
    ``Fraction(0)`` this returned ``0`` px/cell and at
    ``Fraction(-1, 300)`` it returned ``-4``, both silently.  That is
    the same class of statement as the one-inch bound — a sheet that
    cannot exist — and it is NOT the H1(a) refusal, which was about
    pitches this tree had not met.  Every sibling pitch-carrying
    constructor in holo2 already says it by name
    (``format/lattice.py``, ``capture/lattice.py``,
    ``capture/records.py``).
    """
    pitch = Fraction(pitch_in)
    if pitch <= 0:
        raise ValueError(
            f"cell pitch {pitch} in is not a printed cell: a cell pitch is "
            "positive (RULINGS H1(a) deleted the SCOPE set, not the "
            "declared domain)")
    if pitch >= 1:
        raise ValueError(
            f"cell pitch {pitch} in is not a printed cell: this argument is "
            "a PITCH in inches since C3 (RULINGS G4, 2026-08-22), not a "
            "count of engine dots")
    # Fraction(str(float(dpi))) is deliberate: the rational the declared
    # decimal names (600.0, 1197.6), not the binary float's exact value.
    return pitch * Fraction(str(float(dpi_true)))


@dataclass(frozen=True)
class FormatRowSpec:
    """The printed-format facts a decode needs, as data on the request.

    Deliberately the minimum: the close's ``CloseSpec`` surface plus the
    physical cell pitch (which turns an operator-declared DPI into a
    pixel pitch — :func:`native_cell_pitch_px`) and the declared page
    count.  ``pitch_in`` was ``cell_dots: int`` until C3 (RULINGS G4,
    2026-08-22): a dot count is an emission fact that needs its engine's
    dpi to mean anything, and no receive path here has one.
    :func:`format_row` binds it to a real
    coding; a caller may also supply one directly, and such a row carries
    no ``coding_id`` and therefore has no :func:`tile_format_for` view.
    The WHOLE declared domain is validated here (F-15), not at the first
    ``tile_counter`` call.

    **The empty-``coding_id`` sentinel survives WP-1.2, on narrower
    ground than it had.**  It used to be how a fixture named "a sheet no
    registry row describes"; after the lattice there is no such sheet —
    every K format holo2 can decode has a lawful identity, legacy or v2,
    and ``format_row_for`` builds a row from that string alone.  What is
    left is FIXTURE CONVENIENCE: seven test modules hand-build a row with
    a symbol width and a tile grid and no interest in a coding, and
    making them name one would change what they assert rather than how
    they say it.  The sentinel is therefore a stated escape, not an
    off-catalog fallback — the degraded mode FORMAT-SPACE §10 deletes
    rather than guards is the one where an UNNAMEABLE identity still
    decodes, and that mode no longer exists here.
    """

    row_id: str
    codec_id: str
    seed: bytes
    tiles_yx: tuple[int, int]
    pitch_in: Fraction
    streams: tuple[CloseStreamProfile, ...]
    n_pages: int = 1
    coding_id: str = ""
    # WP-1.1 (2026-08-22): the row's dispatch key, appended LAST and
    # defaulted to K — the only family holo2 DECODES.  ``codec_id``
    # stays an informative label (FORMAT-SPACE P1, ``format/family.py``).
    codec_family: Family = Family.K
    # C2 (2026-08-22, RULINGS G2): the outer-code axis, and the colour
    # codec's frozen facts.  Both defaulted, so every K row is what it
    # was.  ``pooled_fountain`` is SEPARATE from the family by design
    # (P13): it is a family fact in v2 and not one in v1, where the
    # printed -v0 CMY8 sheets are unpooled and their -v1 twins pooled
    # with the identical tile codec.  ``codec`` is ``None`` on a K row
    # because a K row's codec facts are recoverable exactly, through
    # :func:`tile_format_for` — the tile chain's own view — and a second
    # copy of them on the row would be a second answer to "how wide is
    # this symbol".  A colour row has no such view (that is the whole
    # point of the fatal refusal), so it carries them here.
    pooled_fountain: bool = False
    codec: CodecFacts | None = None

    def __post_init__(self) -> None:
        # NO PITCH REFUSAL (C3b, RULINGS H1(a), 2026-08-22).  This was
        # the colour half of scope refusal H4 — the K constructor's
        # sentence with the row id as its subject — and it went with the
        # K half: "every registered pitch class (c1..c4) and every
        # lawful rational builds".  A row's pitch is now validated only
        # by what it is USED for (``native_cell_pitch_px``'s one-inch
        # bound catches a dot count passed as a pitch); a pitch this
        # tree has simply never met is not a defect to refuse (L17/P11).
        #
        # THE DECLARED DOMAIN STILL HAS A FLOOR (review fix, C3b-c4,
        # 2026-08-22).  Deleting the scope set also deleted the only
        # statement that a row's pitch is POSITIVE — ``SCOPE_PITCHES``
        # refused 0 and negatives as a side effect of naming two
        # members — which left this docstring's "the WHOLE declared
        # domain is validated here" false for a hand-built row (the
        # customer this constructor names).  This line is a different
        # KIND of refusal from the deleted one: a non-positive pitch
        # describes no constructible sheet, where H1(a)'s set refused
        # sheets holo2 had merely not met.
        if self.codec is not None:
            self._agrees_with_its_codec()
        if self.pitch_in <= 0:
            raise ValueError(
                f"{self.row_id}: cell pitch {self.pitch_in} in is not a "
                "printed cell")
        if self.n_pages < 1:
            raise ValueError("a volume declares at least one page")
        tiles_y, tiles_x = self.tiles_yx
        if tiles_y < 1 or tiles_x < 1:
            raise ValueError(f"invalid tiles_yx {self.tiles_yx}")
        if self.n_pages * tiles_y * tiles_x > MAX_TILES:
            raise ValueError(
                f"{self.n_pages} pages of {tiles_y}x{tiles_x} tiles exceed "
                f"the {COUNTER_BITS}-bit tile counter")

    @property
    def page_domain(self) -> tuple[int, ...]:
        return tuple(range(self.n_pages))

    @property
    def cells_yx(self) -> tuple[int, int]:
        return (self.tiles_yx[0] * TILE_CELLS, self.tiles_yx[1] * TILE_CELLS)

    @property
    def stream_ids(self) -> tuple[StreamId, ...]:
        return tuple(StreamId(profile.stream_id) for profile in self.streams)

    def _agrees_with_its_codec(self) -> None:
        """A carried codec is a CROSS-CHECK, never a second source.

        The four facts below appear both on the row (because the close
        and the scheduler read them there) and inside
        :class:`~holo2.format.families.CodecFacts` (because that is what
        a family constructor produces).  A row that says K over a cmy8
        codec, or declares two streams over a three-stream codec,
        describes no printed sheet.

        **Its customer is a HAND-BUILT row**, and the docstring says so
        rather than claiming more (review, 2026-08-22): :func:`_colour_row`
        fills all four fields FROM the codec it then stores, so on the
        production path this compares the codec with itself.  What it
        catches is the shape a fixture, an oracle or a future frozen
        bundle writes out by hand — which the sentinel row makes
        constructible — and that fork is pinned in
        ``holo2/tests/format/test_format_rows.py``.
        """
        codec = self.codec
        assert codec is not None                      # the caller's guard
        if codec.family is not self.codec_family:
            raise ValueError(
                f"{self.row_id}: row declares family "
                f"{self.codec_family.value!r}, codec declares "
                f"{codec.family.value!r}")
        if codec.codec_id != self.codec_id:
            raise ValueError(
                f"{self.row_id}: row declares codec {self.codec_id!r}, "
                f"codec declares {codec.codec_id!r}")
        if codec.close_profiles != self.streams:
            raise ValueError(
                f"{self.row_id}: row streams {self.stream_ids} are not the "
                f"codec's {codec.stream_ids}")
        if codec.pooled_fountain != self.pooled_fountain:
            raise ValueError(
                f"{self.row_id}: row and codec disagree about the pooled "
                f"outer code")

    def close_spec(self) -> CloseSpec:
        return CloseSpec(codec_id=self.codec_id, seed=self.seed,
                         tiles_yx=self.tiles_yx,
                         stream_profiles=self.streams,
                         spec_id=self.row_id,
                         pooled_fountain=self.pooled_fountain,
                         codec_family=self.codec_family)



def format_row(coding_id: str, tiles_yx: tuple[int, int],
               pages: int = 1) -> FormatRowSpec:
    """One printed K row: V2 coding id + tile grid + declared page count.

    ``coding_id`` is a *coding* name (``c2-k-r0700``), not a *codec*
    name (``k-v1``); the resulting row carries both, as ``row_id``
    (``c2-k-r0700@53x37``) and ``codec_id``.  The row stores the
    coding's OWN id rather than the caller's spelling, so a
    non-canonical v2 spelling normalizes on the way in and only
    canonical strings are ever serialized (FORMAT-SPACE P9).

    C2 (2026-08-22, RULINGS G1) narrowed it to the v2 namespace: a
    legacy coding NAME is no longer a route here, because a legacy
    identity is a whole ``L:`` line matched byte-exactly and never half
    of one.  Legacy rows are built by ``fossils.resolve_fossil_spec``
    from their frozen bundles; :func:`make_format` and
    ``resolve.format_row_for`` are the v2 doors, and this stays the one
    that takes a coding and a grid apart.
    """
    fmt = tile_format(coding_id, tiles_yx)
    return _k_row(fmt, pages)


def _k_row(fmt: TileFormat, pages: int) -> FormatRowSpec:
    """The K projection: one tile format -> the row a decode names.

    Private because the tile format is the only lawful input: a K row
    and its ``TileFormat`` are two views of one coding on one grid, and
    ``tile_format_for`` inverts exactly this function.
    """
    return FormatRowSpec(
        row_id=fmt.spec_id,
        codec_id=fmt.codec_id,
        seed=fmt.seed,
        tiles_yx=fmt.tiles_yx,
        pitch_in=fmt.pitch_in,
        streams=(CloseStreamProfile(STREAM_MAIN, fmt.symbol_bits, None),),
        n_pages=int(pages),
        coding_id=fmt.coding.coding_id,
        codec_family=fmt.codec_family,
    )


def _colour_row(*, coding_id: str, spec_id: str, seed: bytes,
                tiles_yx: tuple[int, int], pitch_in: Fraction,
                codec: CodecFacts, pages: int) -> FormatRowSpec:
    """The colour projection: identity x codec facts -> the printed row.

    Takes the identity as data because the two namespaces derive it
    differently and neither derivation belongs to a codec: a v2 colour
    row's id IS its seed payload, a legacy one's is the frozen
    ``holo/v1/...`` string its sheet was printed under.  Both callers
    (:func:`make_format` and ``fossils``' legacy recipe) hand in the
    pair they computed and this function never guesses one.
    """
    return FormatRowSpec(
        row_id=spec_id,
        codec_id=codec.codec_id,
        seed=seed,
        tiles_yx=tiles_yx,
        pitch_in=pitch_in,
        streams=codec.close_profiles,
        n_pages=int(pages),
        coding_id=coding_id,
        codec_family=codec.family,
        pooled_fountain=codec.pooled_fountain,
        codec=codec,
    )


def make_format(parsed: ParsedFormat, pages: int = 1) -> FormatRowSpec:
    """One parsed v2 identity + a page count -> the printed row.

    The FAMILY CONSTRUCTOR TABLE, and the seam RULINGS B1 drew: the
    grammar (``lattice``) is total over the string space and builds no
    codec; construction is per-family and happens here.  RULINGS G2
    (2026-08-22) filled the colour half of it — every lawful cmy7/cmy8
    identity now builds a real row, carrying its streams, its FEC bank
    ids and its furniture — and left exactly one thing refused: the
    colour CODEC, fatally, at :func:`tile_format_for`.

    Dispatch is on the family enum and nothing else (FORMAT-SPACE P1).
    """
    if parsed.params.family is Family.K:
        return format_row(parsed.coding_id, parsed.tiles_yx, pages)
    codec = colour_codec(parsed.params)
    return _colour_row(
        coding_id=parsed.coding_id, spec_id=parsed.spec_id,
        seed=parsed.seed, tiles_yx=parsed.tiles_yx,
        pitch_in=parsed.params.pitch, codec=codec, pages=pages)


def legacy_row(*, coding_id: str, params: CodingParams,
               tiles_yx: tuple[int, int], pages: int,
               codec_id: str | None = None,
               bank_ids: tuple[str, ...] | None = None) -> FormatRowSpec:
    """Rebuild ONE legacy row from a frozen catalogue bundle.

    The RECIPE half of the two-witness discipline, for every family:
    ``fossils`` holds the record (literal seed bytes, literal spec id)
    and calls this to rebuild the object, then asserts the frozen bytes
    back.  It is deliberately not reachable with a bare coding NAME —
    the bundle is the input, and only the catalogue has bundles
    (RULINGS G1, 2026-08-22).

    The frozen ``codec_id``/``bank_ids`` are passed through to the
    colour constructor because the branch-era names have no v2 spelling
    and are hashed into persisted certificate identities; for K they are
    checked against the derived names instead, since a K bank id is the
    same string in both namespaces (FORMAT-SPACE §6, "identical ids are
    correct — they are the same mathematical object").

    It no longer takes the bundle's ``cell_dots``.  A legacy row's pitch
    is ``params.pitch``, frozen with the rest of the bundle, and the
    dots the sheet was actually printed at are EMISSION evidence that
    ``fossils._self_check`` compares against it, with the engine dpi
    that gives them meaning (RULINGS G4, C3, 2026-08-22).  Taking them
    here only to divide by a hard-coded 600 and compare would have been
    one constant cancelling itself.
    """
    cells_yx = (tiles_yx[0] * TILE_CELLS, tiles_yx[1] * TILE_CELLS)
    spec_id, seed = legacy_identity(coding_id, cells_yx)
    if params.family is Family.K:
        fmt = TileFormat(_legacy_coding(coding_id, params), tiles_yx)
        row = _k_row(fmt, pages)
        frozen = (codec_id or row.codec_id, bank_ids or (fmt.fec_profile_id,))
        if frozen != (row.codec_id, (fmt.fec_profile_id,)):
            raise AssertionError(
                f"legacy identity {spec_id}: frozen codec/bank names "
                f"{frozen} are not the ones this coding derives "
                f"({row.codec_id}, {(fmt.fec_profile_id,)})")
        return row
    codec = colour_codec(params, _codec_id=codec_id, _bank_ids=bank_ids)
    return _colour_row(coding_id=coding_id, spec_id=spec_id, seed=seed,
                       tiles_yx=tiles_yx, pitch_in=params.pitch, codec=codec,
                       pages=pages)


def _tile_format_of(row: FormatRowSpec) -> TileFormat:
    """Rebuild the tile format a K row projects, in its own namespace.

    A v2 row's coding id is a grammar string and mints through
    ``coding_for``; a v1 row's is a legacy NAME, which since RULINGS G1
    (2026-08-22) no grammar and no alias table resolves.  Its parameters
    live where the printed record put them — in the catalogue's frozen
    bundle — so that is where this reads them.  Deferred import: the
    catalogue's import-time self-check builds rows through this module,
    so naming it at module level would close the cycle.
    """
    if not is_fossil_ref(row.row_id):
        return tile_format(row.coding_id, row.tiles_yx)
    from .fossils import legacy_bundle_for
    bundle = legacy_bundle_for(row.coding_id)
    return TileFormat(_legacy_coding(row.coding_id, bundle.params),
                      row.tiles_yx)


def tile_format_for(row: FormatRowSpec) -> TileFormat:
    """The tile chain's view of a row, cross-checked against the row itself.

    A mismatch here would mean two descriptions of one printed sheet
    disagree — the class of fault that decodes a page to coin flips — so
    it raises rather than preferring one side.

    **This is the fatal colour door** (RULINGS G2, 2026-08-22).  holo2
    NAMES and BUILDS every lawful colour format; what it cannot do is
    decode one, and every decode composition asks for this view — the
    placement scheduler, the payload provider, the calibration provider
    and the refine provider each call it in their constructor.  So a
    colour row fails here, by name, before the first fire, rather than
    somewhere deep in a K tile chain that would otherwise read a
    three-stream sheet as one stream of the wrong width.  The refusal
    comes FIRST, ahead of the coding-name check, because "holo2 cannot
    decode cmy8" is the true and useful answer even for a hand-built
    colour row that names no coding.
    """
    if row.codec_family is not Family.K:
        raise ValueError(colour_codec_refusal(row.row_id, row.codec_family))
    if not row.coding_id:
        raise ValueError(
            f"format row {row.row_id!r} names no coding, so it has no "
            "tile-chain view")
    fmt = _tile_format_of(row)
    if fmt.spec_id != row.row_id or fmt.seed != row.seed:
        raise ValueError(
            f"format row {row.row_id!r} disagrees with coding "
            f"{fmt.spec_id!r} — one of them does not describe this sheet")
    if fmt.codec_family is not row.codec_family:
        raise ValueError(
            f"{row.row_id}: row declares family {row.codec_family.value!r}, "
            f"coding declares {fmt.codec_family.value!r}")
    if fmt.pitch_in != row.pitch_in:
        raise ValueError(
            f"{row.row_id}: row declares pitch {row.pitch_in} in, coding "
            f"declares {fmt.pitch_in} in")
    if row.stream_ids != fmt.stream_ids:
        raise ValueError(
            f"{row.row_id}: row streams {row.stream_ids} are not the K row's "
            f"{fmt.stream_ids}")
    if row.streams[0].symbol_bits != fmt.symbol_bits:
        raise ValueError(
            f"{row.row_id}: row symbol width {row.streams[0].symbol_bits} "
            f"!= coding {fmt.symbol_bits}")
    return fmt


__all__ = ["FormatRowSpec", "format_row", "legacy_row",
           "make_format", "native_cell_pitch_px", "tile_format_for"]
