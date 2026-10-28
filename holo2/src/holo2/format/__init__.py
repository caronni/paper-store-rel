"""format — printed-format v1 truth: addressing, coding, close.

Imports: ``core`` (plus stdlib/numpy/cryptography). format owns what the
sheet IS — geometry rows, the BCH address words, the pilot lattice, the
LDPC tile code, the AES-CTR keystream, the fountain and its close — and
nothing about how a capture is read.

:class:`FormatRowSpec` — the printed row a decode names — is format's,
not the engine's: a row reaches the scheduler as data.

**The surface is what the tree consumes** (B4). Four carried leaves are
here as MODULES: ``bch``, ``keystream`` and ``pilots`` because callers
genuinely walk them, many names at a time, and ``ldpc_tile`` because its
one caller is ``solve/tiles.py``, whose carried functions are AST-pinned
against ``holo.receive.tiles`` — the module-qualified spelling is part of
the carry, and flattening it would cost a declared adaptation to buy
nothing. ``bch_batch`` is the fifth, and is a MODULE for the same reason
its twin is: ``solve/words.py`` names one arm or the other at a single
call site, and the two spellings should read side by side there. It is
NOT carried and NOT format-axis — it decodes the carried code word for
word, with bch's own tables and bch's own Berlekamp-Massey, and exists
only so that one hot sweep pays numpy dispatch per batch instead of per
candidate. ``registry_rows`` was the one namespace published so that four
call sites could reach a single function apiece, so those three
functions stand here by name instead (``format_row``,
``tile_format_for``, ``native_cell_pitch_px``). Everything else format
defines stays importable from its own module; a name rejoins this list in
the diff that first imports it from another package.

**Error taxonomy**: format's integrity refusals (``EnvelopeError``,
``FountainIntegrityError``, ``MetadataIntegrityError``,
``StreamSetIntegrityError``) are raised and handled inside format today,
so none is on the surface — the taxonomy law (``tests/
test_error_taxonomy.py``) reads DECLARED off ``__all__``, and declaring
a type nobody catches across a package boundary is API kept alive by its
own pin.

**The incremental close gate's names** (P3-1, first consumed 2026-08-13
by ``solve/close.py``): the consult keeps per-certificate derived state
instead of recomputing the close's input per consult, and the format
truth it consumes joined the surface in that diff — the metadata
equation algebra (``coefficient_mask``, ``decode_metadata``,
``MetadataDecode``, ``METADATA_WORD_BITS``, ``MIN_METADATA_EQUATIONS``,
``SUPPORTED_METADATA_VERSIONS``) and the one authoritative
ESI-to-block mapping (``volume_code_for``, publishing
``fountain_close._volume_code`` so no second copy of the colour-args
derivation can ever fork it, plus ``VolumeCode`` for its type).
``METADATA_WORD_BITS`` is ``metadata.METADATA_BITS`` (the 24-bit word)
under the name that cannot re-create the homonym B4 killed
(``METADATA_BITS_PER_TILE`` = 1 is the per-tile channel width).

**``Family``** (WP-1.1, 2026-08-22) joins under the same B4 law: the
first cross-package importer is ``solve/close.py``, whose counting report
labels per-stream rows only when the row is not K. It is on the surface
because it is the ONE legal dispatch key (FORMAT-SPACE P1) — a package
that must ask "is this sheet K?" has to be able to spell the answer, and
the alternative it replaces is a ``codec_id`` string compare that the
origin retired for cause.

**``LEGACY_CODINGS`` LEFT the surface and the tree** (C2, 2026-08-22,
RULINGS G1). WP-1.2 had turned the old ``CODINGS`` registry into a
three-row alias table of lattice points; the ruling deletes the table
itself, because a legacy coding NAME is not an identity — a printed
sheet is named by a whole ``L:`` line, coding *and* geometry, matched
byte-exactly — so a table of half-names could only build sheets nobody
printed. Its one cross-package consumer was ``cli.py``'s ``--coding``
choices; that surface shrank by one name and gained none at C2, and the
legacy route an operator lost there came back at C5 as
``--format L:<id>`` (RULINGS G6, below).

**THE GRAMMAR'S DOOR JOINS, AND ``format_row`` LEAVES** (C5,
2026-08-22, RULINGS G6 — the ``--format`` CLI). ``resolve_format_ref``,
``ResolvedRef`` and ``format_row_for`` are what the composition root
imports to turn one operator string into the printed row: the resolver
answers *which identity is this, and by which route* (the CLI prints
``format <display> -> state <canonical>`` when the typed spelling is
not the canonical one — P9's echo), and the door builds and
byte-verifies the row. Exactly B4's law:
they join in the diff that first imports them from another package, and
``format_row`` leaves it in the same diff, because that same import was
its only cross-package consumer — a coding id plus a tile grid is half
an identity taken apart, which is now no operator's spelling of
anything. It stays where it lives (``registry_rows``), as the one door
that takes the pair apart, for the tests and constructors that mean to.
``parse_format_id`` is NOT here: the CLI never needs it, since a
reference is resolved, not parsed.
"""
from __future__ import annotations

from . import bch, bch_batch, keystream, pilots
from .close_spec import CloseSpec
from .family import Family
from .format_v1 import STREAM_MAIN, TILE_CELLS, TileFormat
from .fountain import VolumeCode
from .fountain_close import (SUPPORTED_METADATA_VERSIONS,
                             CertifiedStreamSymbol, CloseResult,
                             _volume_code as volume_code_for,
                             close_count_ready, close_record_from_result,
                             close_volume, metadata_from_certificates)
# One constant, one home, one publication point: the per-tile metadata
# width is the lattice's (identity algebra), and the surface takes it
# from there rather than through ``format_v1``, which only consumes it.
from .lattice import METADATA_BITS_PER_TILE
from .ldpc import tile as ldpc_tile
from .ldpc.construct import LADDER
from .metadata import (METADATA_BITS as METADATA_WORD_BITS,
                       MIN_METADATA_EQUATIONS, MetadataDecode,
                       coefficient_mask, decode_metadata)
from .registry_rows import (FormatRowSpec, native_cell_pitch_px,
                            tile_format_for)
from .resolve import ResolvedRef, format_row_for, resolve_format_ref

__all__ = [
    # carried format leaves a caller reads module-qualified: the
    # alphabet, the address keystream, the pilot lattice, and the tile
    # code whose caller is itself AST-pinned to v1's spelling.
    "bch", "bch_batch", "keystream", "ldpc_tile", "pilots",
    # format v1 constants, rows and the row builders
    "Family", "FormatRowSpec", "LADDER", "METADATA_BITS_PER_TILE",
    "STREAM_MAIN", "TILE_CELLS", "TileFormat",
    "native_cell_pitch_px", "tile_format_for",
    # the identity door: one operator string -> the printed row
    "ResolvedRef", "format_row_for", "resolve_format_ref",
    # fountain close
    "CertifiedStreamSymbol", "CloseResult", "CloseSpec", "close_count_ready",
    "close_record_from_result", "close_volume", "metadata_from_certificates",
    # the incremental close gate's dependencies (P3-1)
    "METADATA_WORD_BITS", "MIN_METADATA_EQUATIONS", "MetadataDecode",
    "SUPPORTED_METADATA_VERSIONS", "VolumeCode", "coefficient_mask",
    "decode_metadata", "volume_code_for",
]
