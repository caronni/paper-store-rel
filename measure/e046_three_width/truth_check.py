"""e046 truth check: every certificate of the chain against the EMISSION.

Measures, per source (M1/M2 facts.npz, A1-A4 mints.jsonl) and per plane,
how many certificates were checked against the emitted user bits and how
many disagree (with a bits-wrong histogram).  The emitted user bits are
re-derived through the generator's own calls (holo.gen.emit's pooled
column-group symbol path, holo.gen.color_compose's metadata bits) and
proven by re-rendering the page through compose_color_page_cells and
comparing it byte-exact with page000_gt.npy.  The analyzer's offline GT
path (analyzer.truth.load_truth) is also run and its per-stream widths
and agreement recorded.

Inputs: build/e046/A (manifest.json, page000_gt.npy), the payload
scratch/e046/payloads/counting-A-c2-1782790.bin, scratch/e046/runs.
Output: scratch/e046/analysis/truth/truth_check.json.

    cd <repo> && PYTHONPATH=src:. env/bin/python \
        -m measure.e046_three_width.truth_check
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
GEN_DIR = REPO / "build/e046/A"
PAYLOAD = REPO / "scratch/e046/payloads/counting-A-c2-1782790.bin"
RUNS = REPO / "scratch/e046/runs"
OUT_DIR = REPO / "scratch/e046/analysis/truth"
FACTS = {"M1": RUNS / "M1/rundir.40735/facts.npz",
         "M2": RUNS / "M2/rundir.42487/facts.npz"}
MINTS = {name: RUNS / name / "mints.jsonl" for name in ("A1", "A2", "A3", "A4")}

Key = tuple[int, int, int, str]


def emitted_user_bits(manifest: dict, payload: bytes
                      ) -> tuple[dict[Key, np.ndarray], dict]:
    """The emission's user bits per key, and the re-render proof."""
    from holo.core import fountain
    from holo.format import metadata, streamset
    from holo.format.resolve import resolve_format_ref
    from holo.gen.color_compose import (color_cells_to_dot_planes,
                                        compose_color_page_cells)
    from holo.gen.emit import METADATA_VERSION
    from holo.gen.plan import plan_volume

    spec = resolve_format_ref(str(manifest["format_id"]))
    q_dial = float(manifest["volume"]["q_dial"])
    plan = plan_volume(spec, len(payload), q_dial)
    layout = streamset.StreamSet(tuple(
        (stream.stream_id, stream.symbol_bits)
        for stream in spec.stream_profiles))
    k_meta, pooled_source = streamset.pooled_pack_payload(payload, layout)
    assert k_meta == plan.k_meta and plan.k_total == spec.n_streams * k_meta
    code = fountain.VolumeCode(plan.k_total, spec.symbol_bits, spec.seed,
                               tiles_per_page=spec.tiles_per_page,
                               n_streams=spec.n_streams,
                               groups=spec.column_groups)
    tpp = spec.tiles_per_page
    n_streams = spec.n_streams
    tiles_y, tiles_x = spec.cells_yx[0] // 64, spec.cells_yx[1] // 64
    out: dict[Key, np.ndarray] = {}
    render: dict[str, Any] = {"pages": []}
    for page in range(plan.n_pages):
        spp = tpp * n_streams
        pooled = code.encode_symbols(
            pooled_source, np.arange(page * spp, (page + 1) * spp,
                                     dtype=np.int64))
        symbols = {stream.stream_id: pooled[index::n_streams,
                                            :stream.symbol_bits]
                   for index, stream in enumerate(spec.stream_profiles)}
        counters = np.asarray([spec.tile_counter(page, ty, tx)
                               for ty in range(tiles_y)
                               for tx in range(tiles_x)], dtype=np.int64)
        word = metadata.encode_metadata(METADATA_VERSION, k_meta)
        meta_bits = metadata.tile_bits(
            word, metadata.equation_indices(counters, n_streams),
            max_index=metadata.max_equation_index(n_streams))
        for local in range(tpp):
            ty, tx = divmod(local, tiles_x)
            for index, stream_id in enumerate(spec.stream_ids):
                user = np.concatenate((
                    np.asarray([meta_bits[local, index]], np.uint8),
                    np.asarray(symbols[stream_id][local], np.uint8)))
                out[(page, ty, tx, stream_id)] = user
        states = compose_color_page_cells(spec, page, symbols, k_meta,
                                          version=METADATA_VERSION)
        dots = color_cells_to_dot_planes(states, int(manifest["cell_dots"]))
        packed = np.packbits(np.moveaxis(dots, -1, 0), axis=2,
                             bitorder="big")
        page_meta = manifest["pages"][page]
        emitted = np.load(GEN_DIR / page_meta["gt"])
        render["pages"].append({
            "page": page,
            "rerender_sha256": hashlib.sha256(
                packed.tobytes(order="C")).hexdigest(),
            "manifest_gt_sha256": page_meta["gt_sha256"],
            "file_gt_sha256": hashlib.sha256(
                emitted.tobytes(order="C")).hexdigest(),
            "byte_identical_to_file": bool(np.array_equal(packed, emitted)),
        })
    render["k_meta"] = int(k_meta)
    render["k_total"] = int(plan.k_total)
    render["stream_user_bits"] = {
        stream.stream_id: int(stream.symbol_bits) + 1
        for stream in spec.stream_profiles}
    render["n_keys"] = len(out)
    return out, render


def analyzer_truth_path(gt: dict[Key, np.ndarray]) -> dict:
    """What analyzer.truth.load_truth reconstructs for this row."""
    from analyzer import truth as truth_mod
    from holo.receiver.format import identity

    manifest = json.loads((GEN_DIR / "manifest.json").read_text("utf-8"))
    row = identity.resolve_format_ref(str(manifest["format_id"]))
    try:
        truth = truth_mod.load_truth(GEN_DIR, PAYLOAD, row, 1)
    except Exception as error:  # recorded, not raised
        return {"error": f"{type(error).__name__}: {error}"}
    widths: dict[str, Counter] = {}
    agree: Counter = Counter()
    for key, bits in truth.user_bits.items():
        widths.setdefault(key[3], Counter())[int(np.asarray(bits).size)] += 1
        want = gt.get(key)
        if want is None:
            agree["key_absent_from_emission"] += 1
        elif want.size != np.asarray(bits).size:
            agree[f"{key[3]}:width_differs"] += 1
        elif np.array_equal(want, np.asarray(bits, np.uint8)):
            agree[f"{key[3]}:equal"] += 1
        else:
            agree[f"{key[3]}:bits_differ"] += 1
    return {"widths": {s: dict(c) for s, c in sorted(widths.items())},
            "vs_emission": dict(sorted(agree.items()))}


def compare(gt: dict[Key, np.ndarray], key: Key, bits: np.ndarray
            ) -> tuple[str, int]:
    """('ok'|'wrong'|'width'|'outside', n_bits_wrong)."""
    want = gt.get(key)
    if want is None:
        return "outside", -1
    bits = np.asarray(bits, np.uint8).ravel()
    if bits.size != want.size:
        return "width", -1
    n_bad = int(np.count_nonzero(bits != want))
    return ("ok" if n_bad == 0 else "wrong"), n_bad


def tally(items: list[tuple[str, str, Key, str, int]]) -> dict:
    """items: (source, origin, key, verdict, n_bad) -> per source/plane."""
    table: dict[str, dict[str, dict[str, int]]] = {}
    hist: Counter = Counter()
    wrong: list[dict] = []
    for source, origin, key, verdict, n_bad in items:
        cell = table.setdefault(source, {}).setdefault(
            key[3], {"checked": 0, "wrong": 0, "width": 0, "outside": 0})
        if verdict in ("ok", "wrong"):
            cell["checked"] += 1
        if verdict != "ok":
            cell[verdict] += 1
        if verdict in ("wrong", "width", "outside"):
            wrong.append({"source": source, "origin": origin,
                          "key": list(key), "verdict": verdict,
                          "bits_wrong": n_bad})
            if verdict == "wrong":
                hist[n_bad] += 1
    return {"table": table, "bits_wrong_histogram": dict(sorted(hist.items())),
            "nonmatching": wrong}


def main() -> None:
    from holo.receiver import snapshot

    manifest = json.loads((GEN_DIR / "manifest.json").read_text("utf-8"))
    payload = PAYLOAD.read_bytes()
    payload_sha = hashlib.sha256(payload).hexdigest()
    assert payload_sha == manifest["payload"]["sha256"]
    assert len(payload) == int(manifest["payload"]["bytes"])
    gt, render = emitted_user_bits(manifest, payload)

    items: list[tuple[str, str, Key, str, int]] = []
    facts_summary: dict[str, Any] = {}
    production_bits: dict[str, dict[Key, np.ndarray]] = {}
    for name, path in FACTS.items():
        certs = [fact for fact in snapshot.read(path)
                 if type(fact).__name__ == "Certificate"]
        by_key: dict[Key, np.ndarray] = {}
        origins: Counter = Counter()
        for cert in certs:
            key = (int(cert.page), int(cert.ty), int(cert.tx),
                   str(cert.stream_id))
            origin = ("analyzer-import"
                      if str(cert.source).startswith("analyzer/")
                      else "receiver")
            origins[(origin, key[3])] += 1
            verdict, n_bad = compare(gt, key, cert.user_bits)
            items.append((f"{name}:{origin}", str(cert.source), key,
                          verdict, n_bad))
            by_key[key] = np.asarray(cert.user_bits, np.uint8).ravel()
        production_bits[name] = by_key
        facts_summary[name] = {
            "n_certificates": len(certs), "n_distinct_keys": len(by_key),
            "by_origin_plane": {f"{o}:{s}": n
                                for (o, s), n in sorted(origins.items())}}

    mint_bits: dict[str, dict[Key, np.ndarray]] = {}
    mints_summary: dict[str, Any] = {}
    for name, path in MINTS.items():
        rows = 0
        rungs: Counter = Counter()
        mine: dict[Key, np.ndarray] = {}
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                raw = json.loads(line)
                if raw.get("type") != "row":
                    continue
                bits = (raw.get("rungs") or {}).get("user_bits")
                if bits is None:
                    continue
                rows += 1
                key = (int(raw["page"]), int(raw["ty"]), int(raw["tx"]),
                       str(raw["stream_id"]))
                arr = np.asarray(bits, np.uint8).ravel()
                rungs[str(raw.get("certifying_rung"))] += 1
                verdict, n_bad = compare(gt, key, arr)
                items.append((name, str(raw.get("certifying_rung")), key,
                              verdict, n_bad))
                mine[key] = arr
        mint_bits[name] = mine
        mints_summary[name] = {"n_mint_rows": rows,
                               "n_distinct_keys": len(mine),
                               "certifying_rungs": dict(sorted(rungs.items()))}

    # Cross-consistency: overlaps between sources and bit agreement.
    overlaps: dict[str, Any] = {}
    names = list(mint_bits)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            both = set(mint_bits[left]) & set(mint_bits[right])
            overlaps[f"{left}&{right}"] = len(both)
    m1 = production_bits["M1"]
    m2 = production_bits["M2"]
    overlaps["M1&A_any"] = len(set(m1) & set().union(*map(set, mint_bits.values())))
    imported = set(m2) - set(m1)
    a123 = {}
    for name in ("A1", "A2", "A3"):
        a123.update(mint_bits[name])
    overlaps["M2_not_in_M1"] = len(imported)
    overlaps["M2_not_in_M1_found_in_A1to3"] = len(imported & set(a123))
    overlaps["M2_not_in_M1_bits_equal_A1to3"] = sum(
        1 for key in imported & set(a123)
        if np.array_equal(m2[key], a123[key]))
    overlaps["M1_keys_in_M2_bits_equal"] = sum(
        1 for key in m1 if key in m2 and np.array_equal(m1[key], m2[key]))
    overlaps["A4&M2"] = len(set(mint_bits["A4"]) & set(m2))

    union = set(m2) | set(mint_bits["A4"])
    per_plane = Counter(key[3] for key in union)
    missing = sorted(set(gt) - union)

    result = {
        "payload_sha256": payload_sha,
        "format_id": manifest["format_id"],
        "emission": render,
        "analyzer_truth_path": analyzer_truth_path(gt),
        "facts": facts_summary,
        "mints": mints_summary,
        "overlaps": overlaps,
        "union_final": {"n_keys": len(union),
                        "per_plane": dict(sorted(per_plane.items())),
                        "missing": [list(key) for key in missing]},
        **tally(items),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "truth_check.json").write_text(
        json.dumps(result, indent=1, default=str) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k != "nonmatching"}, indent=1, default=str))


if __name__ == "__main__":
    main()
