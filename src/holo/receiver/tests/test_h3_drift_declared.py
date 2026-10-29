from __future__ import annotations

import hashlib
import importlib
import inspect
import re
from pathlib import Path

import numpy as np
import pytest

from holo.receiver.format import close as h3_close
from holo.receiver.format import identity as h3_identity
from holo.receiver.format import metadata as h3_md
from holo.receiver.format import tile_codec as h3_tc
from holo.receiver.lib import ldpc as h3_ldpc
from holo.receiver.tests import _h3_support

v1_fossils = pytest.importorskip("holo.format.fossils")
v1_ldpc_construct = pytest.importorskip("holo.core.ldpc.construct")
v1_ldpc_tile = pytest.importorskip("holo.core.ldpc.tile")
v1_md = pytest.importorskip("holo.format.metadata")

pytestmark = pytest.mark.skipif(
    not _h3_support.slow_lane(),
    reason=f"cross-tree drift equivalence is a full-lane corpus: set "
           f"{_h3_support.SLOW_LANE_ENV}=1")

RATE_IDS = ("r0547", "r0550", "r0625", "r0700", "r0775", "r0850")

H3_LDPC_DATA = Path(h3_ldpc.__file__).resolve().parent / "ldpc_data"
V1_LDPC_DATA = Path(v1_ldpc_construct.__file__).resolve().parent / "data"

# frozen 2026-09-04 from the holo2 tree at 4e6ec3e (the tree Phase 3
# deleted 2026-09-05 at a805888), via measure/h3_freeze_holo2_pins.py,
# which went with the deletion: holo2's third copy of
# the frozen mother codes, the twelve fossil seed byte strings it kept
# and its two site seeds.  The oracle moved into this file; the values
# are holo2's own, read while its tree still stood.
HOLO2_LDPC_SHA256 = {
    "r0547": "d1439d31b539786ace5e1bab28f6325f"
             "9e1608993652ad81d4a8048ef22df352",
    "r0550": "aaa7bce509b23c52f201af329d4a9399"
             "911c6c20f4fa3ca5382f883e4dc1d65d",
    "r0625": "b05aa66f85d40f0a9c38506cc840bc25"
             "b15ffacca6dc29c77d89d15083a51ce1",
    "r0700": "e5a774afa959e20ae8d4d2dccdef8594"
             "b2801fe281691dade6b4247451499d54",
    "r0775": "a1260e98afb6ca4b35b7157d61077fbf"
             "b2cf79f3e1dec3fc51f58669f49ec6d6",
    "r0850": "3f9fa52042a2bef3c6f42bbd9954aeca"
             "72dd174d05ca3cbed04b1526b4318d63",
}

HOLO2_FOSSIL_SEEDS = {
    "c2-cmy7-p120-v0@3328x2304": b"holo/v1/c2-cmy7-p120-v0/3328x2304",
    "c2-cmy8-p120-v1@3328x2304": b"holo/v1/c2-cmy8-p120-v1/3328x2304",
    "c2-cmy8-p120-v1@3392x2368": b"holo/v1/c2-cmy8-p120-v1/3392x2368",
    "c2-cmy8-r0700-p120-x1@3392x2368":
        b"holo/v1/c2-cmy8-r0700-p120-x1/3392x2368",
    "c2-cmy8-r0850-p120-x1@3392x2368":
        b"holo/v1/c2-cmy8-r0850-p120-x1/3392x2368",
    "c2-r0550@3328x2304": b"holo/v1/c2-r0550/3328x2304",
    "c2-r0700@3328x2304": b"holo/v1/c2-r0700/3328x2304",
    "c2-r0700@3392x2368": b"holo/v1/c2-r0700/3392x2368",
    "c3-cmy7-p120-v0@2240x1536": b"holo/v1/c3-cmy7-p120-v0/2240x1536",
    "c3-cmy8-p120-v1@2240x1536": b"holo/v1/c3-cmy8-p120-v1/2240x1536",
    "c3-r0550@2240x1536": b"holo/v1/c3-r0550/2240x1536",
    "c4-r0550@1664x1152": b"holo/v1/c4-r0550/1664x1152",
}

HOLO2_FAMILY_SEED_P100 = b"holo/v1/sites/p100"
HOLO2_FAMILY_SEED_P120 = b"holo/v1/sites/p120"

HOLO3_ROOT = _h3_support.HOLO3_ROOT

CLOCK_PATTERN = re.compile(r"\bthread_time\b|\bprocess_time\b")


def _still_diverges_metadata_version_gate() -> bool:
    if hasattr(v1_md, "SUPPORTED_METADATA_VERSIONS"):
        return False
    if h3_md.SUPPORTED_METADATA_VERSIONS != frozenset({0}):
        return False
    if 1 not in v1_md.VALID_VERSIONS:
        return False
    observations = [(index, int(bit)) for index, bit in enumerate(
        v1_md.tile_bits(v1_md.encode_metadata(1, 5000),
                        np.arange(60, dtype=np.int64)))]
    theirs = v1_md.decode_metadata(observations)
    mine = h3_md.decode_metadata(dict(observations), v1_md.MAX_COUNTER)
    return bool(theirs.ok and theirs.version == 1
                and not mine.ok and mine.version == 1)


def _still_diverges_decode_tile_defaults() -> bool:
    mine = inspect.signature(h3_tc.decode_tile).parameters
    theirs = inspect.signature(v1_ldpc_tile.decode_tile).parameters
    mine_open = all(mine[name].default is inspect.Parameter.empty
                    for name in ("max_iters", "alpha"))
    theirs_defaulted = (theirs["max_iters"].default == 60
                        and theirs["alpha"].default == 0.8)
    return mine_open and theirs_defaulted


def _still_diverges_cmy8_v0_fossils() -> bool:
    dropped = {"c2-cmy8-p120-v0@3328x2304", "c3-cmy8-p120-v0@2240x1536"}
    return (dropped <= set(h3_identity._FOSSILS)
            and dropped <= set(v1_fossils.FOSSILS)
            and not (dropped & set(HOLO2_FOSSIL_SEEDS))
            and len(h3_identity._FOSSILS) == 15
            and len(v1_fossils.FOSSILS) == 14
            and len(HOLO2_FOSSIL_SEEDS) == 12)


def _still_diverges_sheet_j_v2_fossil() -> bool:
    sheet_j = "c2-cmy8-r0547@53x37"
    entry = h3_identity._FOSSILS.get(sheet_j)
    return (entry is not None
            and entry[0] == b"holo/v2/" + sheet_j.encode()
            and sheet_j not in v1_fossils.FOSSILS
            and sheet_j not in HOLO2_FOSSIL_SEEDS
            and set(h3_identity._FOSSILS) - {sheet_j}
            == set(v1_fossils.FOSSILS))


def _clock_reading_modules() -> tuple[str, ...]:
    hits = []
    for path in _h3_support.source_files(HOLO3_ROOT):
        parts = path.relative_to(HOLO3_ROOT).parts
        if parts[0] in ("tests", "conversion_docs"):
            continue
        if CLOCK_PATTERN.search(path.read_text()):
            hits.append("/".join(parts))
    return tuple(sorted(hits))


def _still_diverges_library_clock_reads() -> bool:
    return len(_clock_reading_modules()) > 0


def _still_diverges_envelope_folded_into_close() -> bool:
    if (Path(h3_close.__file__).resolve().parent / "envelope.py").exists():
        return False
    if h3_close.OVERHEAD_BYTES != 36:
        return False
    return importlib.util.find_spec("holo.format.envelope") is not None


def _still_diverges_decode_metadata_takes_a_dict() -> bool:
    mine = inspect.signature(h3_md.decode_metadata).parameters
    theirs = inspect.signature(v1_md.decode_metadata).parameters
    return (list(mine)[0] == "equations" and list(theirs)[0] == "observations"
            and mine["max_index"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            and theirs["max_index"].kind is inspect.Parameter.KEYWORD_ONLY)


DECLARED_DIVERGENCES = (
    ("metadata-version-gate",
     "holo3 refuses metadata version 1 inside decode_metadata "
     "(SUPPORTED_METADATA_VERSIONS == {0}); v1 returns ok with version 1 and "
     "refuses later at the close adapter",
     _still_diverges_metadata_version_gate),
    ("decode-tile-no-defaults",
     "holo.receiver.format.tile_codec.decode_tile takes max_iters/alpha with no "
     "defaults (the executed BP budget is always named at the call site); "
     "v1's holo.core.ldpc.tile.decode_tile defaults them to 60/0.8",
     _still_diverges_decode_tile_defaults),
    ("cmy8-v0-fossils-kept",
     "holo3 keeps the two cmy8-v0 fossil rows (src/holo's fourteen, plus "
     "the sheet-J row below, so fifteen); holo2 dropped them by the G8 "
     "sunset ruling and carries 12",
     _still_diverges_cmy8_v0_fossils),
    ("sheet-j-v2-fossil",
     "holo3 carries one holo/v2-namespace fossil src/holo cannot mirror "
     "(its recipe law cannot produce holo/v2 bytes): e035 sheet J, "
     "printed inside the window FORMAT-SPACE §16 closed — see §8 row 15",
     _still_diverges_sheet_j_v2_fossil),
    ("library-clock-reads",
     "holo3 plugin modules call time.thread_time/process_time to fill "
     "JobResult.processor_seconds; holo2's test_conventions forbids clock "
     "reads in its headless sources",
     _still_diverges_library_clock_reads),
    ("envelope-folded-into-close",
     "holo3 has no format/envelope module: the wire layout and its 36-byte "
     "overhead live in format/close.py, where holo.format.envelope is a "
     "module of its own (so was holo2.format.envelope, at 4e6ec3e)",
     _still_diverges_envelope_folded_into_close),
    ("decode-metadata-takes-a-dict",
     "holo.receiver.format.metadata.decode_metadata takes an already-deduplicated "
     "dict and a positional max_index; v1 takes an iterable of observations "
     "with a keyword-only max_index, so only v1 ever sees duplicates",
     _still_diverges_decode_metadata_takes_a_dict),
)


@pytest.mark.parametrize("row_id,description,still_diverges",
                         DECLARED_DIVERGENCES,
                         ids=[row[0] for row in DECLARED_DIVERGENCES])
def test_declared_divergence_still_diverges(row_id, description,
                                            still_diverges):
    assert still_diverges(), (
        f"declared divergence {row_id!r} no longer holds — DELETE THE ROW "
        f"from DECLARED_DIVERGENCES rather than repairing the check. "
        f"The row said: {description}")


def test_declared_divergence_table_ids_are_unique_and_documented():
    ids = [row[0] for row in DECLARED_DIVERGENCES]
    assert len(ids) == len(set(ids))
    assert set(CONSTANT_PAIRS) == set(MIN_SHARED_CONSTANTS)
    for row_id, description, checker in DECLARED_DIVERGENCES:
        assert row_id and row_id == row_id.lower()
        assert len(description) > 40
        assert callable(checker)


# Seven rows were dropped 2026-09-05 with the v1 receiver
# (`src/holo/receive` deleted at 284ae3e): holo3's pava, calibrate,
# color_model (twice), color_refine, refine and tiles constants had their
# only second copy in `holo.receive.*`.  They passed one last time on the
# pre-deletion tree and are recorded there (PRESERVATION.md §2).  What is
# left is the format law, which `holo.core` and `holo.format` still hold.
CONSTANT_PAIRS = (
    ("holo.receiver.format.metadata", "holo.format.metadata"),
    ("holo.receiver.format.keystream", "holo.core.keystream"),
    ("holo.receiver.format.close", "holo.format.envelope"),
    ("holo.receiver.format.fountain", "holo.core.fountain"),
    ("holo.receiver.format.fountain", "holo.core.column_groups"),
    ("holo.receiver.format.pilots", "holo.format.pilots"),
    ("holo.receiver.format.tile_codec", "holo.core.channel"),
    ("holo.receiver.format.identity", "holo.format.layout"),
    ("holo.receiver.lib.bch", "holo.core.bch"),
)

COMPARABLE = (int, float, str, bytes, bool, tuple, frozenset)

ALLOWED_CONSTANT_DIVERGENCES: frozenset[tuple[str, str, str]] = frozenset()

MIN_SHARED_CONSTANTS = {
    ("holo.receiver.format.metadata", "holo.format.metadata"): 12,
    ("holo.receiver.format.keystream", "holo.core.keystream"): 20,
    ("holo.receiver.format.close", "holo.format.envelope"): 3,
    ("holo.receiver.format.fountain", "holo.core.fountain"): 5,
    ("holo.receiver.format.fountain", "holo.core.column_groups"): 1,
    ("holo.receiver.format.pilots", "holo.format.pilots"): 7,
    # 4 -> 7 at cmy A1: CMY_STATE_IDS, CMY_LABEL_STREAMS, CMY_LABEL_TO_STATE
    ("holo.receiver.format.tile_codec", "holo.core.channel"): 7,
    ("holo.receiver.format.identity", "holo.format.layout"): 5,
    ("holo.receiver.lib.bch", "holo.core.bch"): 9,
}


@pytest.mark.parametrize("mine_name,theirs_name", CONSTANT_PAIRS,
                         ids=[row[0].rsplit(".", 1)[-1] + "-vs-"
                              + row[1].rsplit(".", 1)[-1]
                              for row in CONSTANT_PAIRS])
def test_no_undeclared_constant_divergence(mine_name, theirs_name):
    mine = importlib.import_module(mine_name)
    theirs = importlib.import_module(theirs_name)
    n_shared = 0
    undeclared = []
    for name in sorted(vars(mine)):
        if name.startswith("_") or not name.isupper():
            continue
        if not hasattr(theirs, name):
            continue
        mine_value = getattr(mine, name)
        theirs_value = getattr(theirs, name)
        if not isinstance(mine_value, COMPARABLE):
            continue
        if not isinstance(theirs_value, COMPARABLE):
            continue
        n_shared += 1
        if mine_value == theirs_value:
            continue
        if (mine_name, theirs_name, name) in ALLOWED_CONSTANT_DIVERGENCES:
            continue
        undeclared.append(f"{name}: {mine_value!r} != {theirs_value!r}")
    assert n_shared >= MIN_SHARED_CONSTANTS[(mine_name, theirs_name)], (
        f"{mine_name} now shares only {n_shared} constants with "
        f"{theirs_name} — a shrinking surface silently weakens this gate")
    assert not undeclared, (
        f"UNDECLARED DRIFT between {mine_name} and {theirs_name}: "
        + "; ".join(undeclared)
        + " — add a row to DECLARED_DIVERGENCES only after the divergence is "
          "understood and ruled on; a format constant mismatch is a "
          "printed-format fork")


@pytest.mark.parametrize("rate_id", RATE_IDS)
def test_ldpc_mother_code_json_matches_v1_and_the_frozen_holo2_digest(rate_id):
    mine = (H3_LDPC_DATA / f"{rate_id}.json").read_bytes()
    v1_bytes = (V1_LDPC_DATA / f"{rate_id}.json").read_bytes()
    assert hashlib.sha256(mine).hexdigest() == \
        hashlib.sha256(v1_bytes).hexdigest(), (
        f"{rate_id}.json differs from src/holo — the frozen mother codes ARE "
        f"the format, so a copy that is not a copy is a format fork")
    _h3_support.assert_golden(f"holo2 {rate_id}.json",
                              hashlib.sha256(mine).hexdigest(),
                              HOLO2_LDPC_SHA256[rate_id])


def test_fossil_seed_bytes_equal_v1_on_every_shared_identity():
    for spec_id in sorted(v1_fossils.FOSSILS):
        assert h3_identity.resolve_format_ref("L:" + spec_id).seed == \
            v1_fossils.FOSSILS[spec_id].seed, spec_id


def test_fossil_seed_bytes_equal_the_frozen_twelve_holo2_kept():
    shared = sorted(set(h3_identity._FOSSILS) & set(HOLO2_FOSSIL_SEEDS))
    assert len(shared) == 12
    for spec_id in shared:
        _h3_support.assert_golden(
            f"holo2 fossil seed {spec_id}",
            h3_identity.resolve_format_ref("L:" + spec_id).seed,
            HOLO2_FOSSIL_SEEDS[spec_id])


def test_site_seeds_are_identical_across_v1_and_the_frozen_holo2_values():
    _h3_support.assert_golden("holo2 FAMILY_SEED_P100",
                              v1_fossils.FAMILY_SEED_P100,
                              HOLO2_FAMILY_SEED_P100)
    _h3_support.assert_golden("holo2 FAMILY_SEED_P120",
                              v1_fossils.FAMILY_SEED_P120,
                              HOLO2_FAMILY_SEED_P120)
    assert h3_identity.resolve_format_ref(
        "L:c2-r0700@3392x2368").sites_seed == v1_fossils.FAMILY_SEED_P100
    assert h3_identity.resolve_format_ref(
        "L:c2-cmy8-r0700-p120-x1@3392x2368").sites_seed == \
        v1_fossils.FAMILY_SEED_P120
