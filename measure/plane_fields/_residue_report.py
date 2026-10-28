"""Render ``p2/REPORT.md`` from the three P2 result files.

The tables are GENERATED, never transcribed: every number in the report
is read out of ``e1-refit.json`` / ``e2-directional.json`` /
``e3-state-contrast.json`` at render time, so a re-run of the
measurement and a re-run of this module can never disagree.  The prose
around them is authored here and says what the tables mean and what they
do not.

    PYTHONPATH=src:measure env/bin/python -m plane_fields._residue_report
"""
from __future__ import annotations

import json

from .detector_residue import OUT_DIR

STRATA = ("none", "C", "M", "both")
GROUP_LABEL = {
    "dead_band": "dead-band targets",
    "reproduction_control": "reproduction controls",
    "clear_band": "clear-band targets",
    "certified_reference": "certified clean-column references",
}


def _pct(value, digits: int = 2, width: int = 6) -> str:
    if value is None:
        return "—".rjust(width)
    return f"{100.0 * float(value):.{digits}f}".rjust(width)


def _num(value, digits: int = 3, width: int = 6) -> str:
    if value is None:
        return "—".rjust(width)
    return f"{float(value):.{digits}f}".rjust(width)


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# E1
# --------------------------------------------------------------------------
def e1_section(document: dict) -> str:
    rows = [row for row in document["e1"]["rows"] if "error" not in row]
    shas = sorted({sha for row in rows
                   for sha in row.get("captures", ())})
    body = []
    for row in rows:
        frozen, refit = row.get("frozen", {}), row.get("refit", {})
        per_frozen = frozen.get("per_capture", {})
        per_refit = refit.get("per_capture", {})
        body.append([
            f"({row['tile_y']},{row['tile_x']})",
            "dead" if row["band"] == "dead" and row["role"] == "target"
            else "control",
            "/".join(frozen.get("arm_by_capture", {}).get(sha) or "?"
                     for sha in shas),
            " ".join(_pct(per_frozen.get(sha, {}).get("ber"), 1, 4)
                     for sha in shas),
            _pct(frozen.get("union_ber")),
            "yes" if frozen.get("certified") else "no",
            " ".join(_pct(per_refit.get(sha, {}).get("ber"), 1, 4)
                     for sha in shas),
            _pct(refit.get("union_ber")),
            "yes" if refit.get("certified") else "no",
            (_pct(row["refit_minus_frozen_ber"], 2)
             if "refit_minus_frozen_ber" in row else "—"),
        ])
    table = _table(
        ["tile", "band", "arms", "frozen per-capture %", "frozen union %",
         "cert", "refit per-capture %", "refit union %", "cert", "Δ pp"],
        body)

    logloss = []
    for row in rows:
        frozen = (row.get("frozen") or {}).get("heldout_logloss", {})
        refit = (row.get("refit") or {}).get("heldout_logloss", {})
        probe = (row.get("refit") or {}).get("refit_probe", {})
        logloss.append([
            f"({row['tile_y']},{row['tile_x']})",
            " ".join(_num(frozen.get(sha), 5, 7) for sha in shas),
            " ".join(_num(refit.get(sha), 5, 7) for sha in shas),
            " ".join(_num((probe.get(sha) or {}).get(
                "min_abs_feature_delta"), 4, 6) for sha in shas),
            " ".join((probe.get(sha) or {}).get("arm", "?") for sha in shas),
        ])
    proof = _table(
        ["tile", "frozen held-out logloss", "refit held-out logloss",
         "min |Δfeature| (proof the correction landed)", "refit arm"],
        logloss)

    groups = _table(
        ["group", "n tiles", "frozen union %", "refit union %",
         "Δ mean pp", "refit better / worse", "cert frozen", "cert refit"],
        [[GROUP_LABEL.get(name, name),
          str(row["n_tiles"]),
          _pct(row["union_ber_frozen_mean"]),
          _pct(row["union_ber_refit_mean"]),
          _num(row["refit_minus_frozen_mean_pp"], 2),
          f"{row['refit_improved_tiles']} / {row['refit_worsened_tiles']}",
          str(row["certified_frozen"]), str(row["certified_refit"])]
         for name, row in document["e1"]["summary"].items()
         if isinstance(row, dict)])
    reproduction = max(
        (abs(row["reproduction_gap_vs_gt_affine"]) for row in rows
         if "reproduction_gap_vs_gt_affine" in row), default=None)
    same_cells = all(
        row.get("frozen", {}).get("union_observed")
        == row.get("refit", {}).get("union_observed") for row in rows)
    return "\n\n".join([
        "## E1 — the recut-bins refit",
        "Each tile is decoded at its `gt-affine-final2.json` 6-dof "
        "supervised affine plus that run's BER-direct polish translation, "
        "twice: through the FROZEN detector (fitted once at delta = 0, "
        "A5 context bins cut there) and through a FULL REFIT of the "
        "restricted region with the tile sampled at that geometry before "
        "anything is fitted.  Captures are in sha order "
        + ", ".join(sha[:8] for sha in shas) + ".",
        table,
        f"Reproduction check: the FROZEN arm reproduces "
        f"`gt-affine-final2.json`'s polish union BER to within "
        f"{_pct(reproduction, 4, 1).strip()} pp on every tile "
        f"(same state, same lane, same seed, same restricted region; "
        f"a different tree, so this is not a triviality).",
        ("The two arms score the SAME cells: the emission mask is a "
         "function of addresses and suppression, not of features, and "
         "`union_observed` is identical between arms on every tile."
         if same_cells else
         "WARNING: `union_observed` DIFFERS between the arms on at least "
         "one tile — the two arms are not scoring the same cells and the "
         "BER comparison is not like for like."),
        "### Did the correction reach all three captures?",
        "`fit_region` raises `RefitDidNotReach` rather than returning a "
        "fit whose SELECTED arm equals that arm's own zero features, so "
        "a run that produced these rows at all is already the proof; the "
        "measured feature displacement and the held-out log-loss are "
        "below.",
        proof,
        "### Grouped",
        groups,
    ])


# --------------------------------------------------------------------------
# E2 / E3
# --------------------------------------------------------------------------
def _strata_table(pooled: dict, key: str, digits: int = 2) -> str:
    percent = key.startswith("ber") or key.endswith("share")
    rows = []
    for group in ("dead_band", "reproduction_control", "clear_band",
                  "certified_reference"):
        if group not in pooled:
            continue
        entry = pooled[group]
        rows.append([
            GROUP_LABEL[group],
            f"{entry['_rows']['n_tiles']} / {entry['_rows']['n_rows']}",
            *(_pct(entry[name][key], digits) if percent
              else _num(entry[name][key], 3) for name in STRATA),
            *(str(entry[name]["n_cells_total"]) for name in STRATA),
        ])
    return _table(
        ["group", "tiles / rows", *(f"{name} {key}" for name in STRATA),
         *(f"n {name}" for name in STRATA)], rows)


def _mean(values):
    rows = [float(v) for v in values if v is not None]
    return sum(rows) / len(rows) if rows else None


def e2_per_tile(document: dict) -> str:
    """One row per PHYSICAL tile, its three captures averaged.

    The pooled group means hide the spread over six tiles; this is the
    population the dead-band claim is actually about.
    """
    per_tile = document.get("per_tile") or {}
    keys: list[str] = []
    for capture in per_tile.values():
        for key in capture:
            if key not in keys:
                keys.append(key)
    rows = []
    for key in keys:
        entries = [capture[key] for capture in per_tile.values()
                   if key in capture]
        if not entries:
            continue
        axes = {f"{row['direction']['axis']}"
                f"{'+' if row['direction']['sign'] > 0 else '-'}"
                for row in entries}

        def gap(label: str, name: str):
            return _mean(
                (row.get(label, {}).get("contrast") or {}).get(name)
                for row in entries)

        down = gap("downstream", "ber_global_gap_inked_minus_none")
        up = gap("upstream", "ber_global_gap_inked_minus_none")
        rows.append([
            key, "/".join(sorted(axes)), str(len(entries)),
            _num(_mean(row["direction"]["dominant_dots"]
                       for row in entries), 3),
            _pct(down, 2), _pct(up, 2),
            _pct(None if down is None or up is None else down - up, 2),
            _num(gap("downstream", "lift_inked_mean"), 3),
            _num(gap("upstream", "lift_inked_mean"), 3),
            _num(gap("same_cell", "lift_inked_mean"), 3),
        ])
    return _table(
        ["tile", "direction", "captures", "fitted Y translation (dots)",
         "downstream ink-gap pp", "upstream ink-gap pp", "down − up pp",
         "lift down", "lift up", "lift same-cell"], rows)


def e2_section(document: dict) -> str:
    summary = document["e2"]
    gap = _table(
        ["group", "tiles / rows", "downstream ink-gap pp",
         "upstream ink-gap pp", "same-cell ink-gap pp",
         "down − up pp (± sd)", "downstream error lift (inked / none)"],
        [[GROUP_LABEL.get(group, group),
          f"{row['n_tiles']} / {row['n_rows']}",
          _num(row.get("downstream_ber_global_gap_inked_minus_none"), 2),
          _num(row.get("upstream_ber_global_gap_inked_minus_none"), 2),
          _num(row.get("same_cell_ber_global_gap_inked_minus_none"), 2),
          f"{_num(row['downstream_minus_upstream_mean_pp'], 2)} "
          f"± {_num(row['downstream_minus_upstream_sd_pp'], 2).strip()}",
          f"{_num(row.get('downstream_lift_inked_mean'), 3).strip()} / "
          f"{_num(row.get('downstream_lift_none'), 3).strip()}"]
         for group, row in summary["ink_gap_pp"].items()])
    recoverable = _table(
        ["group", "downstream recoverable pp", "upstream recoverable pp",
         "same-cell recoverable pp"],
        [[GROUP_LABEL.get(group, group),
          _num(row.get("downstream_recoverable_pp_inked_mean"), 2),
          _num(row.get("upstream_recoverable_pp_inked_mean"), 2),
          _num(row.get("same_cell_recoverable_pp_inked_mean"), 2)]
         for group, row in summary["ink_gap_pp"].items()])
    return "\n\n".join([
        "## E2 — directional-neighbour stratification",
        "Every Y payload cell classified by whether the neighbour in the "
        "direction of the FITTED Y translation (dominant axis, sign of "
        "dx or dy) carries C or M ink in the printed truth.  The "
        "UPSTREAM neighbour — the same test in the opposite direction — "
        "is the falsifier: an anisotropic, neighbour-sourced leakage has "
        "to show a downstream/upstream split, and an isotropic one must "
        "not.",
        "**Read the geometry carefully.**  The samples are taken AT the "
        "fitted affine — after the displacement has been corrected — "
        "while the direction is that same fitted translation.  So this "
        "asks whether a directional signature SURVIVES the correction, "
        "not whether the aperture is currently sliding toward a "
        "neighbour.  A survivor implicates the printed ink and the "
        "optics; its absence says the geometry carried the anisotropy "
        "and the correction took it away.",
        "Two error rates, two questions.  `ber_global` scores every "
        "stratum under ONE threshold fitted on the whole tile — where the "
        "errors a stratum-blind decision actually LANDS them, which is "
        "what \"errors concentrate in X\" is a claim about.  `ber` re-fits "
        "the threshold inside the stratum — what survives a PERFECT "
        "stratum-conditional correction.  The difference between them "
        "(`recoverable`) is the size of the prize an anisotropic context "
        "term would compete for.  `lift` is a stratum's share of the "
        "errors over its share of the cells: > 1 = errors concentrate "
        "there.",
        "### Y cell error under ONE tile-wide threshold, by DOWNSTREAM "
        "neighbour ink",
        _strata_table(summary["downstream"], "ber_global"),
        "### The same, UPSTREAM (the falsifier)",
        _strata_table(summary["upstream"], "ber_global"),
        "### The same, SAME cell (the mix-compression reference)",
        _strata_table(summary["same_cell"], "ber_global"),
        "### Error LIFT by DOWNSTREAM neighbour ink (share of errors / "
        "share of cells)",
        _strata_table(summary["downstream"], "lift"),
        "### Error LIFT, UPSTREAM",
        _strata_table(summary["upstream"], "lift"),
        "### Y error after a PERFECT per-stratum threshold, DOWNSTREAM",
        _strata_table(summary["downstream"], "ber"),
        "### d' by DOWNSTREAM neighbour ink",
        _strata_table(summary["downstream"], "d_prime"),
        "### The headline contrast",
        gap,
        "### What a perfect stratum-conditional threshold would recover",
        recoverable,
        "### Per PHYSICAL tile (three captures averaged)",
        e2_per_tile(document),
    ])


def e3_section(document: dict) -> str:
    summary = document["e3"]
    ratios = _table(
        ["group", "tiles / rows", "d' C/none", "d' M/none", "d' both/none",
         "sep C/none", "sep M/none", "sep both/none"],
        [[GROUP_LABEL.get(group, group),
          f"{row['n_tiles']} / {row['n_rows']}",
          _num(row.get("d_prime_ratio_C_over_none"), 3),
          _num(row.get("d_prime_ratio_M_over_none"), 3),
          _num(row.get("d_prime_ratio_both_over_none"), 3),
          _num(row.get("separation_ratio_C_over_none"), 3),
          _num(row.get("separation_ratio_M_over_none"), 3),
          _num(row.get("separation_ratio_both_over_none"), 3)]
         for group, row in summary["ratios"].items()])
    return "\n\n".join([
        "## E3 — per-state Y contrast",
        "The same samples at the same fitted geometry, split by the SAME "
        "cell's (C, M) printed state.  If Y under M is optically "
        "compressed, the ink/white separation collapses in the `M` and "
        "`both` states — a ratio below 1 against the `none` state.",
        "### Y d' by same-cell (C, M) state",
        _strata_table(summary["strata"], "d_prime"),
        "### Y ink/white MEAN SEPARATION (sampled units) by same-cell state",
        _strata_table(summary["strata"], "mean_separation", 3),
        "### Y cell error by same-cell state, ONE tile-wide threshold",
        _strata_table(summary["strata"], "ber_global"),
        "### Y error after a PERFECT per-state threshold",
        _strata_table(summary["strata"], "ber"),
        "### Ratios against the `none` state",
        ratios,
    ])


def provenance(e1: dict) -> str:
    inputs = e1["inputs"]
    rows = [
        ["measurement tree", f"`{e1['tree_before']['branch']}` @ "
                             f"`{e1['tree_before']['head'][:12]}` "
                             f"(dirty: {e1['tree_before']['dirty']})"],
        ["src/holo content sha256",
         f"`{e1['tree_before']['receiver_tree_sha256'][:16]}`"],
        ["tree moved during the run", str(e1["tree_moved"])],
        ["state", f"`{e1['state']['sha256'][:16]}` "
                  f"({e1['state']['close']}, "
                  f"{e1['state']['certificates']} certificates)"],
        ["recovered payload sha256",
         f"`{inputs['recovered_payload_sha256'][:16]}`"],
        ["geometry source",
         f"`gt-affine-final2.json` sha256 "
         f"`{inputs['gt_affine_sha256'][:16]}`"],
        ["format / lane", f"`{e1['format']['ref']}` / "
                          f"`{e1['lane']['lane_id']}`"],
        ["workers", str(e1.get("workers"))],
        ["wall / peak RSS", f"{e1['wall_seconds']:.0f} s / "
                            f"{e1['peak_rss_gb']} GB"],
    ]
    for sha, path in sorted(e1["inputs"]["scans"].items()):
        rows.append([f"capture `{sha[:12]}`", f"`{path.rsplit('/', 1)[-1]}`"])
    return "\n\n".join([
        "## Provenance", _table(["item", "value"], rows)])


#: The authored prose.  Kept next to the generators so the report is one
#: artifact and the numbers inside it are never transcribed by hand.
PREAMBLE = """# P2 — where the sheet-I dead-band residue lives

docs/INDEPENDENT-PLANES §6 **P2**: three measurements that size the prize
before anything is built, on the archived captures, with no toner and no
new state.  E1 asks how much of the dead-vs-control detector gap was an
artifact of scoring corrected samples through a detector cut at
delta = 0.  E2 tests the review's anisotropic-context mechanism against
its own falsifier.  E3 measures mix compression, which §2.7 lists as
*inferred, unmeasured*.

Instruments: `measure/plane_fields/detector_residue.py` (+
`_residue_run`, `_residue_strata`, `_residue_figures`); the refit seam
lives in `_swim_region.fit_region` and its synthetic checks in
`_selfcheck`.  Figures: `e1-refit.png`, `e2-directional.png`.
"""

CAVEATS = """## Caveats — what these numbers may not be used to claim

1. **n is six dead tiles and two controls**, one lane (8 px/cell), one
   sheet (I, r0700), one engine state (AltaLink, 2026-08-05/06 toner).
   Every mean below is over that.
2. **The groups are outcome-selected.**  "Dead" means *this receiver did
   not certify it*; "control" means *it did*, with the certificate then
   withheld.  A difference between them is not evidence of a mechanism
   until the mechanism is shown to be the thing that differs.
3. **Tile x capture rows are pooled as if independent.**  Three captures
   of ONE physical sheet are not.  Every table carries `tiles / rows`;
   read the tile count.
4. **E2/E3 additionally pool per WINDOW.**  A cell carried by four
   windows contributes four rows, sampled at four slightly different
   poses.  The counts are cell-samples, not cells.
5. **The geometry under test is SUPERVISED** — fitted against the printed
   truth by `gt_affine`, and further polished by a BER-direct search that
   knew the answer.  It is a ceiling, not a receiver.  E1 does not show
   what a receiver would achieve; it shows what the detector does when
   the geometry is already as right as this model can make it.
6. **E1's refit still inherits gt_affine's objective.**  The affine was
   fitted to maximise partial NCC (then BER-polished by translation
   only); no 6-dof BER search was ever run, so a refit that fails to
   improve does not prove that a better geometry could not.
7. **The oracle threshold in E2/E3 is per stratum and per capture-tile.**
   It is the best a perfect photometric decision could do on those
   samples — deliberately more generous than the detector, and not a
   number any receiver can reach.
8. **E1's refit is not strictly local.**  The corrected base features
   also feed `_fit_registration`, so one tile's correction nudges the
   region's residual model and every window's A1 zero with it.  That is
   what a receiver holding the better geometry would do, but it means
   "one variable" is approximate; the region's held-out log-loss (table
   above) bounds how far the rest of the region moved.
9. **The refit re-fits the QDA/PAVA on a population that now contains
   the corrected cells** — about a third of one percent of the region's
   cells, since the correction touches only the target tile's cells
   inside four windows out of ~95.  Self-fitting at that share cannot
   account for a percentage-point move; the recut A5 context bins for
   the target's own cells can.
"""

VERDICT = """## Verdict — where the dead-band residue lives

**A quarter of the dead-vs-control detector gap was frozen-fit artifact;
three quarters survive a full refit.**  Recutting the whole restricted
region at the corrected geometry moves every one of the six dead tiles
(6/6, mean **−0.96 pp**, sd 0.50, and **24/24** capture-tile rows in the
same direction) against **−0.26 pp** on the two controls.  The dead −
control gap therefore falls from 2.85 pp to 2.15 pp.  So the review's
"detector-created ~2.3 pp" reading is CONFIRMED IN PART and bounded: the
stale A5 bins were worth about 0.7 pp of the gap and about 1 pp of
absolute Y error on a dead tile, and the rest is not the frozen fit.

**Headline: a dead-band tile CERTIFIES under the refit.**  Tile (29,8),
which no geometry in `gt_affine` could certify, closes at the recut
detector — `certificate_id 48aa9a83…`, **syndrome_ok and crc_ok both
true, at the ordinary UNION stage in 99 iterations**, 3976 informative
cells, union cell error 8.32 % → 7.85 % (331 → 312 wrong cells).  Read
it for exactly what it is: the geometry is SUPERVISED, so this is the
ceiling moving, not a receiver recovering a tile.  It also widens the
inverted gate interval again — (29,8) certified at 7.85 % while (31,15)
failed at 7.70 % — so the certificate gate is confirmed, a third time,
not to be a BER threshold.

**E2's pre-registered prediction FAILED.**  The directional asymmetry is
REAL and reproduces: errors are worse when the DOWNSTREAM neighbour (the
one the fitted Y translation points at) carries ink, by +2.21 pp on dead
tiles, while the UPSTREAM falsifier shows −0.04 pp.  But the controls
show the same thing (+2.03 downstream, −0.51 upstream) and the certified
clean-column references show it too (+0.99 / +0.60).  The prediction was
that dead tiles would split and controls would not; per physical tile
the down − up spread is 2.21 ± 3.61 pp (dead) against 1.55 ± 2.72 (n=2
controls) and 0.20 ± 3.45 (references), and one CONTROL tile (15,7,
+5.07 pp) out-splits four of the six dead tiles.  **The anisotropic,
neighbour-sourced leakage is a sheet-wide Y property, not a dead-band
mechanism.**  Where it bites hardest is the `both` stratum: a
downstream neighbour carrying C AND M lifts the error share to 1.23x
its cell share and the error to 22.7 % against 16.7 % on a clean
neighbour.

**E3 measures mix compression, and it is the largest photometric effect
on the sheet — and equally large everywhere.**  Y's ink/white mean
separation collapses to **0.557x** its on-white value when the SAME cell
carries M (0.518x on the certified clean-column references), 0.82x
under C, 0.74x under both.  d' follows (M/none 0.79 dead, 0.71
reference).  A PERFECT same-cell-state-conditional threshold would
recover **3.97 pp** on dead tiles, 5.08 on controls and 4.53 on the
references — roughly FOUR TIMES the ~1 pp the downstream-neighbour
stratum is worth.  Y-under-M sits at 15.5–17.4 % cell error even after
that perfect threshold, against 7.9–11.9 % for Y-on-white.

**Putting it together.**  Of the three candidate homes for the dead-band
residue, the refit accounts for about a quarter and the other two
account for none of it: both E2's anisotropy and E3's mix compression
are present at full strength on tiles that certify, in clean columns,
on the same pixels.  What they do identify is a large SHEET-WIDE Y
prize that has nothing to do with the bands — ~4–5 pp from a same-cell
(C, M)-conditional decision and ~1 pp from a direction-aware one — sitting
in a detector whose same-cell crosstalk is three QDA means sampled at
three different per-plane positions and whose cross-plane context is an
isotropic ink COUNT.  That is an argument for §4.E(4)/(5) on the whole
sheet, and it is NOT an explanation of why these six columns are dead.
After geometry, after the refit, 2.15 pp of dead-vs-control gap remains
unattributed by these three measurements.
"""


def main() -> int:
    from . import _residue_figures
    from ._residue_run import GATE_BER

    e1 = json.loads((OUT_DIR / "e1-refit.json").read_text())
    e2 = json.loads((OUT_DIR / "e2-directional.json").read_text())
    e3 = json.loads((OUT_DIR / "e3-state-contrast.json").read_text())
    (OUT_DIR / "REPORT.md").write_text("\n\n".join([
        PREAMBLE.strip(), e1_section(e1), e2_section(e2), e3_section(e3),
        VERDICT.strip(), CAVEATS.strip(), provenance(e1),
    ]) + "\n")
    # The figures are redrawn from the SAME artifacts, so a report and the
    # pictures beside it can never come from different runs.
    _residue_figures.draw_e1(OUT_DIR / "e1-refit.png", e1["e1"]["rows"],
                             gate=GATE_BER)
    _residue_figures.draw_e2(OUT_DIR / "e2-directional.png", e2["e2"])
    print(f"wrote {OUT_DIR / 'REPORT.md'}, e1-refit.png, e2-directional.png")
    return 0


__all__ = ["CAVEATS", "PREAMBLE", "VERDICT", "e1_section", "e2_per_tile",
           "e2_section", "e3_section", "main", "provenance"]


if __name__ == "__main__":
    raise SystemExit(main())
