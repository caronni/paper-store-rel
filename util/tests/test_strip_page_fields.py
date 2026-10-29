"""Preserve old-reader facts exactly while removing the two new schemas."""

import io
import json
import zipfile

import numpy as np
import pytest

from holo.receiver import data, snapshot
from util.strip_page_fields import strip_snapshot


def _spine(path):
    with np.load(path, allow_pickle=False) as handle:
        return json.loads(handle["meta"].tobytes())


def _snapshot_with_new_fields(path):
    snapshot.write(path, (
        data.LatticeSeed(capture_id="capture", level_index=0, region_index=0,
                         rows=np.arange(6).reshape(3, 2), support_cells=17,
                         window_ordinal=2),
        data.Certificate(page=1, ty=3, tx=4, stream_id="Y",
                         user_bits=np.array([1, 0, 1, 1], np.uint8),
                         source="tiles.scan"),
    ))
    spine = _spine(path)
    with zipfile.ZipFile(path) as source:
        blob = source.read("blob.npy")
    kept = list(spine["facts"])
    # Use the new page-only constructor shape; no receiver import can load
    # both schemas. Shared array references also catch accidental blob edits.
    field = ["d", "PlaneField", [
        ["page", 1], ["plane", 2], ["delta_dots_xy", ["a", 0]],
        ["support", ["a", 0]], ["uncertainty_dots", ["a", 0]],
        ["n_observations", 3], ["n_captures", 1], ["ordinal", 12],
    ]]
    revision = ["d", "EvidenceRevision", [
        ["capture_id", "capture"], ["page", 1], ["revision", 12],
    ]]
    spine["facts"] = [kept[0], field, kept[1], revision]
    meta = io.BytesIO()
    np.lib.format.write_array(
        meta, np.frombuffer(json.dumps(spine).encode(), np.uint8),
        allow_pickle=False)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        target.writestr("meta.npy", meta.getvalue())
        target.writestr("blob.npy", blob)
    return kept


def test_filtered_facts_load_and_preserve_records_and_arrays(tmp_path):
    source = tmp_path / "facts.npz"
    output = tmp_path / "filtered.npz"
    kept = _snapshot_with_new_fields(source)
    original = source.read_bytes()
    counts = strip_snapshot(source, output)

    assert counts == {"removed": {"PlaneField": 1, "EvidenceRevision": 1},
                      "kept_facts": 2, "kept_certificates": 1}
    assert source.read_bytes() == original
    assert _spine(output) == {**_spine(source), "facts": kept}
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
        assert before.read("blob.npy") == after.read("blob.npy")
    facts = snapshot.read(output)
    assert [type(fact).__name__ for fact in facts] == [
        "LatticeSeed", "Certificate"]
    np.testing.assert_array_equal(facts[0].rows, np.arange(6).reshape(3, 2))
    np.testing.assert_array_equal(facts[1].user_bits, [1, 0, 1, 1])
    assert (facts[1].page, facts[1].ty, facts[1].tx,
            facts[1].stream_id, facts[1].source) == (1, 3, 4, "Y", "tiles.scan")


def test_snapshot_without_fields_is_unchanged_in_content(tmp_path):
    source = tmp_path / "facts.npz"
    snapshot.write(source, ())
    output = tmp_path / "filtered.npz"
    assert strip_snapshot(source, output) == {
        "removed": {}, "kept_facts": 0, "kept_certificates": 0}
    assert snapshot.read(output) == ()


@pytest.mark.parametrize("target", ["same", "existing", "symlink"])
def test_refuses_overwriting_source_or_existing_output(tmp_path, target):
    source = tmp_path / "facts.npz"
    snapshot.write(source, ())
    original = source.read_bytes()
    output = source if target == "same" else tmp_path / "filtered.npz"
    if target == "existing":
        output.write_bytes(b"keep this")
    elif target == "symlink":
        output.symlink_to(source)
    with pytest.raises(FileExistsError):
        strip_snapshot(source, output)
    assert source.read_bytes() == original
    if target == "existing":
        assert output.read_bytes() == b"keep this"
