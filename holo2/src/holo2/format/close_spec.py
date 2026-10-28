"""The format input surface a volume close reads: ``CloseSpec``.

HOLO2-ORIGINAL (not a carry): ``src/holo``'s close reads its own
``FormatSpec`` directly; holo2's close (``fountain_close.py``) is a
carried-and-adapted module and must not grow a holo2-only type past its
line cap, so this narrow view of "the printed-format facts a close
touches, and only those" lives here instead.

WORKPLAN WP-1.0 (2026-08-22, catch-up wave): split out of
``fountain_close.py`` (998/1000 lines, ``test_conventions.py``'s cap) so
that module holds *only* carried code from its two declared origins
(``holo.receive.fountain_close`` and ``holo.receive.close_progress``).
Zero behaviour change — every moved def/class is byte-identical modulo
the move (AST-diffed against ``fountain_close.py`` at commit `c0afd06`
per ``holo2/docs/ENGINEERING.md:86-94`). ONE declared adaptation: the
move left ``CloseSpec``/``CloseStreamProfile`` out of ``fountain_close``'s
``__all__`` and did not re-declare them anywhere; this module now
declares its own (review fix, 2026-08-22) — no module did ``import *``
from either file, so the gap was latent, never load-bearing.

``COUNTER_BITS``/``MAX_TILES`` are sourced from ``metadata`` here, same
as before the move (CRITIQUE-missing #22) — not redeclared a fourth
time; a module that still needs them imports them from here or from
``metadata`` directly rather than re-declaring the width.

WP-1.1 (2026-08-22): ``CloseSpec`` gained ``codec_family``, the K vs
colour dispatch key (FORMAT-SPACE P1), appended LAST because positional
constructions exist (``holo2/tests/solve/test_solve_tilemap.py:340,356``).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import metadata
from .family import Family
from .keystream import COLOR_STREAM_AUX

# F12: the printed format's flat tile counter is 18 bits (the same width
# the metadata channel addresses).
COUNTER_BITS = metadata.COUNTER_BITS
MAX_TILES = 1 << COUNTER_BITS


# ------------------------------------------------- format input surface

@dataclass(frozen=True, slots=True)
class CloseStreamProfile:
    """One logical fountain stream of a format row, as the close sees it."""

    stream_id: str
    symbol_bits: int
    fountain_aux: int | None = None

    def __post_init__(self) -> None:
        if self.fountain_aux is not None:
            expected = COLOR_STREAM_AUX.get(self.stream_id)
            if expected is None or self.fountain_aux != expected:
                raise ValueError(
                    f"{self.stream_id}: fountain_aux must be {expected}")


@dataclass(frozen=True)
class CloseSpec:
    """The printed-format facts a volume close reads, and only those.

    Mirrors ``holo.format.descriptor.FormatSpec`` on exactly the surface
    :func:`close_volume` touches: ``codec_family`` (the one-stream K/CMY7
    vs multistream CMY8 branch), the volume ``seed``, the page tile grid,
    the ordered stream profiles and the pooled marker.  Cell geometry,
    pilots, FEC and media never reach the close.

    WP-1.1 (2026-08-22): the branch moved off ``codec_id``, which is now
    what the origin calls it — an informative label, never a dispatch key
    (FORMAT-SPACE P1; ``format/family.py``).  ``pooled_fountain`` stays a
    SEPARATE field on purpose: the outer-code axis is orthogonal to
    family by design (the printed ``-v0`` colour rows are unpooled CMY8),
    so it is not derivable from ``codec_family``.
    """

    codec_id: str
    seed: bytes
    tiles_yx: tuple[int, int]
    stream_profiles: tuple[CloseStreamProfile, ...]
    spec_id: str = ""
    # -v1 pooled outer code (``Coding.pooled_fountain``): ONE fountain
    # over esi = counter*n + stream.  Since C2 (2026-08-22, RULINGS G2)
    # every v2 cmy8 row and the three -v1 colour fossils set it, so this
    # branch is CONSTRUCTIBLE — what no holo2 decode does is REACH it,
    # because ``tile_format_for`` refuses a colour row (F1) before any
    # decode composes.
    pooled_fountain: bool = False
    # LAST, and defaulted: positional constructions exist in the tree,
    # and K is the only family holo2 DECODES (it names and builds all
    # three).
    codec_family: Family = Family.K

    def __post_init__(self) -> None:
        tiles_y, tiles_x = self.tiles_yx
        if tiles_y < 1 or tiles_x < 1:
            raise ValueError(f"invalid tiles_yx {self.tiles_yx}")
        if tiles_y * tiles_x > MAX_TILES:
            raise ValueError(
                f"tiles {self.tiles_yx} exceed the {COUNTER_BITS}-bit "
                "counter")
        if not self.stream_profiles:
            raise ValueError("a format row declares at least one stream")
        declared = {profile.stream_id for profile in self.stream_profiles}
        if len(declared) != len(self.stream_profiles):
            raise ValueError("duplicate stream id in a format row")
        if self.pooled_fountain:
            if len(self.stream_profiles) < 2:
                raise ValueError("a pooled fountain needs >= 2 streams")
            _ = self.symbol_bits    # equal widths are structural (§2.1)

    @property
    def stream_ids(self) -> tuple[str, ...]:
        return tuple(profile.stream_id for profile in self.stream_profiles)

    def stream_profile(self, stream_id: str) -> CloseStreamProfile:
        """The one declared profile for ``stream_id`` (or ValueError)."""
        matches = tuple(
            profile for profile in self.stream_profiles
            if profile.stream_id == stream_id
        )
        if len(matches) != 1:
            raise ValueError(
                f"stream {stream_id!r} is not declared by "
                f"{self.spec_id or self.codec_id}")
        return matches[0]

    @property
    def n_streams(self) -> int:
        return len(self.stream_profiles)

    @property
    def symbol_bits(self) -> int:
        """The ONE pooled symbol width (equal per-stream widths)."""
        widths = {profile.symbol_bits for profile in self.stream_profiles}
        if len(widths) != 1:
            raise ValueError(f"{self.spec_id}: no common symbol width")
        return widths.pop()

    @property
    def tiles_per_page(self) -> int:
        tiles_y, tiles_x = self.tiles_yx
        return tiles_y * tiles_x

    def tile_counter(self, page: int, ty: int, tx: int) -> int:
        """Flat tile counter c = page*T + ty*tiles_x + tx (§4.3)."""
        tiles_y, tiles_x = self.tiles_yx
        if not (0 <= ty < tiles_y and 0 <= tx < tiles_x):
            raise ValueError(f"tile ({ty},{tx}) outside grid {self.tiles_yx}")
        if page < 0:
            raise ValueError(f"negative page {page}")
        c = page * (tiles_y * tiles_x) + ty * tiles_x + tx
        if c >= MAX_TILES:
            raise ValueError(
                f"tile counter {c} exceeds {COUNTER_BITS} bits (F12)")
        return c


__all__ = ["CloseSpec", "CloseStreamProfile"]
