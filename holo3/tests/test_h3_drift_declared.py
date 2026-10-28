from __future__ import annotations

import hashlib
import importlib
import inspect
import re
from pathlib import Path

import numpy as np
import pytest

from holo3.format import close as h3_close
from holo3.format import identity as h3_identity
from holo3.format import metadata as h3_md
from holo3.format import tile_codec as h3_tc
from holo3.lib import ldpc as h3_ldpc
from holo3.tests import _h3_support

v1_fossils = pytest.importorskip("holo.format.fossils")
v1_ldpc_construct = pytest.importorskip("holo.core.ldpc.construct")
v1_ldpc_tile = pytest.importorskip("holo.core.ldpc.tile")
v1_md = pytest.importorskip("holo.format.metadata")
h2_fossils = pytest.importorskip("holo2.format.fossils")
h2_ldpc_construct = pytest.importorskip("holo2.format.ldpc.construct")

pytestmark = pytest.mark.skipif(
    not _h3_support.slow_lane(),
    reason=f"cross-tree drift equivalence is a full-lane corpus: set "
           f"{_h3_support.SLOW_LANE_ENV}=1")

RATE_IDS = ("r0547", "r0550", "r0625", "r0700", "r0775", "r0850")

H3_LDPC_DATA = Path(h3_ldpc.__file__).resolve().parent / "ldpc_data"
V1_LDPC_DATA = Path(v1_ldpc_construct.__file__).resolve().parent / "data"
H2_LDPC_DATA = Path(h2_ldpc_construct.__file__).resolve().parent / "data"

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
            and not (dropped & set(h2_fossils.FOSSILS))
            and len(h3_identity._FOSSILS) == 15
            and len(v1_fossils.FOSSILS) == 14
            and len(h2_fossils.FOSSILS) == 12)


def _still_diverges_sheet_j_v2_fossil() -> bool:
    sheet_j = "c2-cmy8-r0547@53x37"
    entry = h3_identity._FOSSILS.get(sheet_j)
    return (entry is not None
            and entry[0] == b"holo/v2/" + sheet_j.encode()
            and sheet_j not in v1_fossils.FOSSILS
            and sheet_j not in h2_fossils.FOSSILS
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
    return (importlib.util.find_spec("holo.format.envelope") is not None
            and importlib.util.find_spec("holo2.format.envelope") is not None)


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
     "holo3.format.tile_codec.decode_tile takes max_iters/alpha with no "
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
     "overhead live in format/close.py; both holo.format.envelope and "
     "holo2.format.envelope are separate modules",
     _still_diverges_envelope_folded_into_close),
    ("decode-metadata-takes-a-dict",
     "holo3.format.metadata.decode_metadata takes an already-deduplicated "
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


def test_library_clock_readers_are_the_declared_fourteen_modules():
    # engine.py joined 2026-08-29 with the one ruled engine clock: the
    # consult gauge (EngineStat.consult_cpu_s, 05-fountain §9.4);
    # plugins/local_ctx.py, plugins/color_pooled.py and
    # plugins/fields.py joined 2026-08-30 with the ordinary per-job
    # meter every row that prepares work carries; plugins/uplift.py
    # joined with the supplemental residue row, which owns a region
    # derivation no other row's meter covers — a row reporting no CPU at
    # all would be the one unavailable number the diag law forbids
    # printing as zero; plugins/plane_k.py joined 2026-08-31 with the
    # plane-isolated residue row, whose one fire owns a three-channel
    # re-read and a sampling-offset search no other row's meter covers;
    # plugins/swim.py joined the same day and for the sharpest version of
    # that reason — it is the row that spends CPU on a bounded raster
    # SEARCH, so its meter is what tells a reader whether the dearest row
    # in the tree is earning its price
    assert _clock_reading_modules() == (
        "engine.py",
        "plugins/calibrate.py", "plugins/color_pooled.py",
        "plugins/color_refine.py", "plugins/color_region.py",
        "plugins/fields.py", "plugins/local_ctx.py",
        "plugins/place_sched.py", "plugins/plane_k.py",
        "plugins/refine.py", "plugins/survey.py", "plugins/swim.py",
        "plugins/tiles.py", "plugins/uplift.py")


CONSTANT_PAIRS = (
    ("holo3.format.metadata", "holo.format.metadata"),
    ("holo3.format.keystream", "holo.core.keystream"),
    ("holo3.format.close", "holo.format.envelope"),
    ("holo3.format.fountain", "holo.core.fountain"),
    ("holo3.format.fountain", "holo.core.column_groups"),
    ("holo3.format.pilots", "holo.format.pilots"),
    ("holo3.format.tile_codec", "holo.core.channel"),
    ("holo3.format.identity", "holo.format.layout"),
    ("holo3.lib.bch", "holo.core.bch"),
    ("holo3.lib.geometry", "holo2.solve.geometry"),
    ("holo3.lib.pava", "holo.receive.detect"),
    ("holo3.plugins.calibrate", "holo.receive.detect"),
    ("holo3.plugins.color_model", "holo.receive.color_calibration"),
    ("holo3.plugins.color_model", "holo.receive.color_detect"),
    ("holo3.plugins.color_refine", "holo.receive.color_refine"),
    ("holo3.plugins.refine", "holo.receive.certified_refine"),
    ("holo3.plugins.survey", "holo2.capture.survey"),
    ("holo3.plugins.tiles", "holo.receive.tiles"),
)

COMPARABLE = (int, float, str, bytes, bool, tuple, frozenset)

ALLOWED_CONSTANT_DIVERGENCES: frozenset[tuple[str, str, str]] = frozenset()

MIN_SHARED_CONSTANTS = {
    ("holo3.format.metadata", "holo.format.metadata"): 12,
    ("holo3.format.keystream", "holo.core.keystream"): 20,
    ("holo3.format.close", "holo.format.envelope"): 3,
    ("holo3.format.fountain", "holo.core.fountain"): 5,
    ("holo3.format.fountain", "holo.core.column_groups"): 1,
    ("holo3.format.pilots", "holo.format.pilots"): 7,
    ("holo3.format.tile_codec", "holo.core.channel"): 4,
    ("holo3.format.identity", "holo.format.layout"): 5,
    ("holo3.lib.bch", "holo.core.bch"): 9,
    ("holo3.lib.geometry", "holo2.solve.geometry"): 4,
    ("holo3.lib.pava", "holo.receive.detect"): 11,
    ("holo3.plugins.calibrate", "holo.receive.detect"): 8,
    ("holo3.plugins.color_model", "holo.receive.color_calibration"): 11,
    ("holo3.plugins.color_model", "holo.receive.color_detect"): 7,
    ("holo3.plugins.color_refine", "holo.receive.color_refine"): 12,
    ("holo3.plugins.refine", "holo.receive.certified_refine"): 19,
    ("holo3.plugins.survey", "holo2.capture.survey"): 15,
    ("holo3.plugins.tiles", "holo.receive.tiles"): 5,
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
def test_ldpc_mother_code_json_identical_to_both_reference_trees(rate_id):
    mine = (H3_LDPC_DATA / f"{rate_id}.json").read_bytes()
    v1_bytes = (V1_LDPC_DATA / f"{rate_id}.json").read_bytes()
    h2_bytes = (H2_LDPC_DATA / f"{rate_id}.json").read_bytes()
    assert hashlib.sha256(mine).hexdigest() == \
        hashlib.sha256(v1_bytes).hexdigest(), (
        f"{rate_id}.json differs from src/holo — the frozen mother codes ARE "
        f"the format, so a copy that is not a copy is a format fork")
    assert hashlib.sha256(mine).hexdigest() == \
        hashlib.sha256(h2_bytes).hexdigest(), (
        f"{rate_id}.json differs from holo2's copy")


def test_fossil_seed_bytes_equal_v1_on_every_shared_identity():
    for spec_id in sorted(v1_fossils.FOSSILS):
        assert h3_identity.resolve_format_ref("L:" + spec_id).seed == \
            v1_fossils.FOSSILS[spec_id].seed, spec_id


def test_fossil_seed_bytes_equal_holo2_on_the_twelve_it_kept():
    shared = sorted(set(h3_identity._FOSSILS) & set(h2_fossils.FOSSILS))
    assert len(shared) == 12
    for spec_id in shared:
        assert h3_identity.resolve_format_ref("L:" + spec_id).seed == \
            h2_fossils.FOSSILS[spec_id].seed, spec_id


def test_site_seeds_are_identical_across_all_three_trees():
    for name in ("FAMILY_SEED_P100", "FAMILY_SEED_P120"):
        assert getattr(v1_fossils, name) == getattr(h2_fossils, name), name
    assert h3_identity.resolve_format_ref(
        "L:c2-r0700@3392x2368").sites_seed == v1_fossils.FAMILY_SEED_P100
    assert h3_identity.resolve_format_ref(
        "L:c2-cmy8-r0700-p120-x1@3392x2368").sites_seed == \
        v1_fossils.FAMILY_SEED_P120
