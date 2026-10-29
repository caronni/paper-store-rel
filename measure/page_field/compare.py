#!/usr/bin/env python
"""Score a solved page field against the fits that came before it.

    cd <repo>
    PYTHONPATH=src:. env/bin/python -m measure.page_field.compare \\
        --fields build/page-field/H/fields.json \\
        --analyzer <evidence>/analyzer/sweeps/field2/phase-C.json \\
        --lane-fields <evidence>/page-field/H7-mirror/plane_fields.npz \\
        --out build/page-field/H/compare.json

where `<evidence>` is the evidence archive.  Three sources, each optional,
each its own section, all in one run so
`PAGE-FIELD-PLAN.md` §5's before-and-after columns fill from one
command:

* `--analyzer` — the analyzer's POOLED sheet-H fits
  (`field2` phase C, one entry per (stream, page) with a whole
  `field_dots_xy` grid): B3's `<= 0.12 dots median on x`, plus the
  amplitude the design's §7 gap is about;
* `--supervised` — sheet I's supervised Y sinusoid
  (`regmap-gt/plane-offsets.json`, `dY_rel_x` per patch in scan PIXELS
  against the C/M common pose, aggregated per column exactly as that
  directory's own `report.py` does): B3's Spearman, period and
  amplitude ratio;
* `--lane-fields` — the PRE-W2 per-lane fields `extract.py` kept, which
  is the only surviving reader of them: plan §5's "before" column, per
  lane against the page field and lane against lane, scored on the
  plane DIFFERENTIALS, which is the only quantity the two gauges share.

Everything is read as arrays and compared as arrays; nothing here fits
a field.  `products.column_profile` is imported rather than restated,
so the profile this scores is the profile the PNG draws.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

from holo.receiver.format import identity
from holo.receiver.lib import plane_field

from . import products

#: Period grid for the sinusoid fit, in tiles.  The grid runs from here
#: to the profile's WHOLE length, which is where the analyzer's own
#: `sweeps/field2_paper.sinusoid_fit` stops: e033's ~100 mm is 18.5
#: tiles at sheet-I geometry, exactly half of the 37 columns, so a grid
#: capped at half the profile would sit on the AltaLink's own period and
#: report every longer one as 18.5.  The step is finer than the 3 % the
#: bar asks about.
PERIOD_MIN_TILES: float = 4.0
PERIOD_STEP_TILES: float = 0.05

#: e033's certificate-residue peak for the AltaLink Y sinusoid, in
#: printed dots (design §7, the amplitude gap).  It is a column
#: profile's MAXIMUM, not a fitted sinusoid's amplitude, so the ratio
#: that is like-for-like against it is `profile_max_over_e033_peak` and
#: the fitted-amplitude ratio beside it is a different statistic —
#: measured 2026-09-08 on sheet H, the two differ by 1.60x
#: (profile max 0.6006 dots against the analyzer's fitted 0.3743).
E033_Y_PEAK_DOTS: float = 0.83


def spearman(left: np.ndarray, right: np.ndarray) -> float:
    """Rank correlation, the spelling the retired field instruments used
    (`measure/h3_plane_fields.field_truth`, deleted at W6).

    A constant profile has no ranks to correlate — a plane no
    observation reached reads zero everywhere — and the honest answer
    there is nan, not the correlation of two argsorts of ties.
    """
    values = (np.asarray(left, np.float64), np.asarray(right, np.float64))
    if any(np.ptp(column) == 0.0 for column in values):
        return float("nan")
    ranks = [np.argsort(np.argsort(column)) for column in values]
    return float(np.corrcoef(*ranks)[0, 1])


def spearman_average_ranks(left: np.ndarray, right: np.ndarray) -> float:
    """Rank correlation with TIED VALUES AVERAGED, which is Spearman's.

    Beside :func:`spearman` rather than inside it (review 2026-09-13,
    F6): the double `argsort` above breaks a tie by position and gives
    equal values distinct ranks, so `[0, 0, 0, 1]` against
    `[0, 1, 1, 1]` reads 1.0 where Spearman's is 1/3, and
    `[0, 0, 1, 1]` against `[0, 1, 0, 1]` reads 0.8 where it is 0.
    Continuous profiles have no ties and the two agree exactly, which is
    why the sheet-H record does not move; a profile with zeroed columns
    in it does have them.  `spearman` keeps its definition because it
    produced the supervised and per-lane numbers of record, and only
    :func:`against_analyzer` reads this one.

    The constant case is `spearman`'s: a plane no observation reached
    has no ranks to correlate, and the honest answer is nan — which is
    also what SciPy would warn and return.
    """
    values = (np.asarray(left, np.float64), np.asarray(right, np.float64))
    if any(column.size < 2 or np.ptp(column) == 0.0 for column in values):
        return float("nan")
    return float(stats.spearmanr(*values).statistic)


def fit_sinusoid(profile: np.ndarray) -> dict:
    """The best single sinusoid over a period grid: amplitude, period, r².

    Least squares on `b·cos + c·sin` at each candidate period, after a
    linear trend is projected out — the analyzer's own recipe
    (`analyzer/sweeps/field2_paper.sinusoid_fit`), and the reason its
    reported C amplitude is 0.2425 where the same profile fitted with
    the tilt left in reads 0.2851: a page-wide tilt is the surface's
    business, not a sinusoid, and the numbers this scores against are
    detrended ones.  The trend is reported beside the amplitude rather
    than thrown away.  A profile with no variation at all — a plane no
    observation reached — has no period, and says so.
    """
    values = np.asarray(profile, np.float64)
    n = values.shape[0]
    index = np.arange(n, dtype=np.float64)
    trend = np.polynomial.polynomial.Polynomial.fit(index, values, 1)
    detrended = values - trend(index)
    empty = {"amplitude_dots": 0.0, "period_tiles": float("nan"),
             "r_squared": 0.0,
             "trend_dots_per_page": float(trend(index[-1]) - trend(index[0]))}
    total = float((detrended ** 2).sum())
    if total <= 0.0:
        return empty
    best = dict(empty, r_squared=-np.inf)
    periods = np.arange(PERIOD_MIN_TILES, float(n) + PERIOD_STEP_TILES,
                        PERIOD_STEP_TILES)
    for period in periods:
        phase = 2.0 * np.pi * index / period
        design = np.stack((np.cos(phase), np.sin(phase)), axis=1)
        coefficients, *_ = np.linalg.lstsq(design, detrended, rcond=None)
        residual = float(((detrended - design @ coefficients) ** 2).sum())
        r_squared = 1.0 - residual / total
        if r_squared > best["r_squared"]:
            best = dict(empty, amplitude_dots=float(np.hypot(*coefficients)),
                        period_tiles=float(period),
                        r_squared=float(r_squared))
    return best


def _plane_entry(page: dict, plane_name: str) -> dict | None:
    return next((entry for entry in page["planes"]
                 if entry["plane_name"] == plane_name), None)


def _profile(entry: dict) -> np.ndarray:
    return products.column_profile(np.asarray(entry["delta_dots_xy"]),
                                   np.asarray(entry["support"]))


def median_uncertainty_dots(mine: dict, live: np.ndarray) -> float:
    """The solve's own error bar over the tiles being compared.

    A disagreement is only worth reading beside the uncertainty the
    solve published for it (design §2.4, W8 R-B): 0.10 dots off on a
    tile the solve says it knows to 0.02 is a real disagreement, and the
    same 0.10 where it says 0.30 is the two fits agreeing inside what
    either of them measured.  Nothing gates on it here or anywhere.
    """
    bars = np.asarray(mine["uncertainty_dots"], np.float64)
    selected = bars[np.asarray(live, bool)]
    return float(np.median(selected)) if selected.size else float("nan")


def _both_live(mine: dict, support: np.ndarray) -> np.ndarray:
    """The tiles both grids carry evidence on — and the shape refusal.

    Two fields of different tile grids are two different pages, and
    every statistic below would broadcast one into the other rather
    than say so.
    """
    live = np.asarray(mine["support"], np.float64) > 0.0
    theirs = np.asarray(support, np.float64) > 0.0
    if live.shape != theirs.shape:
        raise ValueError(
            f"tile grids disagree: the field is {live.shape} and what it "
            f"is being compared to is {theirs.shape} — different pages")
    return live & theirs


# ------------------------------------------------- the analyzer's pool

def against_analyzer(solved: dict, path: Path) -> list[dict]:
    """Per (page, plane) the analyzer pooled, the two grids tile by tile.

    The analyzer's `delta_dots_xy[..., 0]` is x and `[..., 1]` is y, on
    the page tile grid.  Both components are fitted (`field2.py`, A2 of
    the analyzer's page-field plan, 2026-09-12); the x column is B3's
    bar, and the y column is the analyzer's y UNDER TEST against this
    receiver's measured y — no sheet carries supervised y, so the
    receiver is the reference on that axis and the column carries no
    bar of its own.

    THE SUPPORT THE PROFILES ARE BUILT ON (review 2026-09-13, F6).  The
    pointwise medians have always been taken over `_both_live`, and the
    profile correlation used to be taken over each field's OWN support:
    two columns that summarise different rows of the page, whose
    correlation is therefore not agreement over the shared evidence —
    and two identical grids under disjoint masks can read −1 that way.
    The correlation is now over profiles both built on the common live
    tiles, and:

    * a column with no common tile at all is DROPPED from the
      correlation rather than read as zero, which is what
      `products.column_profile` writes there and what would otherwise
      enter both profiles as a block of shared zeros and inflate the
      number.  `spearman_x_column_profile_columns` says how many
      columns survived, so a thin page cannot pass for a full one;
    * `spearman_x_column_profile_own_support` keeps the old number
      beside it as the coverage diagnostic.  Where support is full on
      both sides the two are identical — that equality is the cheapest
      evidence a sheet's recorded comparison was never affected, and on
      sheet H it holds to the digit.

    Each field's OWN sinusoid and profile maximum stay on its own
    support: those describe a field rather than compare two, and
    restricting them to the other side's evidence would make a physical
    reading depend on who it was scored against.
    """
    fits = json.loads(path.read_text())["fields"]
    rows: list[dict] = []
    for fit in fits:
        if fit.get("fit_refused"):
            # The analyzer names a (page, plane) it could not fit
            # (too few furniture anchors, no lane on the page); a
            # refusal is not a field and is not scored.
            continue
        page = next((entry for entry in solved["pages"]
                     if entry["page"] == fit["page"]), None)
        if page is None:
            continue
        mine = _plane_entry(page, fit["stream"])
        if mine is None:
            continue
        theirs = np.asarray(fit["field_dots_xy"], np.float64)
        live = _both_live(mine, np.asarray(fit["support"], np.float64))
        delta = np.asarray(mine["delta_dots_xy"], np.float64) - theirs
        profile, their_profile = (
            _profile(mine),
            products.column_profile(theirs, np.asarray(fit["support"])))
        shared = live.astype(np.float64)
        covered = live.any(axis=0)
        common, their_common = (
            products.column_profile(
                np.asarray(mine["delta_dots_xy"], np.float64), shared),
            products.column_profile(theirs, shared))
        sinusoid = fit_sinusoid(profile)
        rows.append({
            "page": fit["page"], "plane_name": fit["stream"],
            "n_tiles": int(live.sum()),
            "median_abs_dx_dots": float(
                np.median(np.abs(delta[..., 0])[live])),
            "median_abs_dy_dots": float(
                np.median(np.abs(delta[..., 1])[live])),
            "spearman_x_column_profile": spearman_average_ranks(
                common[covered], their_common[covered]),
            "spearman_x_column_profile_columns": int(covered.sum()),
            "spearman_x_column_profile_own_support": spearman(
                profile, their_profile),
            "median_uncertainty_dots": median_uncertainty_dots(mine, live),
            "mine": sinusoid,
            "analyzer": fit_sinusoid(their_profile),
            "analyzer_reported_sinusoid_x": {
                "amplitude_dots": fit["sinusoid_x"]["amplitude_dots"],
                "period_tiles": fit["sinusoid_x"]["period_tiles"],
                "r_squared": fit["sinusoid_x"]["r_squared"]},
            "profile_max_dots": float(np.abs(profile).max()),
            "profile_max_over_e033_peak": float(np.abs(profile).max()
                                                / E033_Y_PEAK_DOTS),
            "fitted_amplitude_over_e033_peak": float(
                sinusoid["amplitude_dots"] / E033_Y_PEAK_DOTS),
        })
    return rows


# -------------------------------------------- the supervised sinusoid

def supervised_profile(path: Path) -> np.ndarray:
    """Sheet I's Y-against-C/M x offset per tile COLUMN, in printed dots.

    `plane-offsets.json` carries one `dY_rel_x` per measured patch in
    scan pixels; the column value is the median over that column's
    patches and the unit is `px_per_dot`, which is the aggregation
    the e033 regmap-gt report published as `per-column.json` (evidence
    archive).
    """
    truth = json.loads(path.read_text())
    per_dot = float(truth["px_per_dot"])
    columns = sorted({int(patch["tile_x"]) for patch in truth["patches"]})
    return np.array([
        np.median([patch["dY_rel_x"] for patch in truth["patches"]
                   if int(patch["tile_x"]) == column]) / per_dot
        for column in columns], np.float64)


def against_supervised(solved: dict, path: Path,
                       plane_name: str = "Y") -> list[dict]:
    """B3's ground-truth row: Spearman, period, amplitude ratio.

    The SIGN is reported and not asserted: the supervised measurement is
    Y's displacement against the C/M common pose and the field is the
    displacement a reader adds to sample there, and no sheet-I holo3
    snapshot exists on this machine to settle which way round that
    lands.  A Spearman near -1 is the same shape read the other way and
    the report says so rather than taking an absolute value.
    """
    truth = supervised_profile(path)
    rows: list[dict] = []
    widths = {int(page["tiles_yx"][1]) for page in solved["pages"]}
    if truth.shape[0] not in widths:
        raise ValueError(
            f"the supervised profile has {truth.shape[0]} tile columns and "
            f"the solved pages have {sorted(widths)} — different pages")
    for page in solved["pages"]:
        entry = _plane_entry(page, plane_name)
        if entry is None or page["tiles_yx"][1] != truth.shape[0]:
            continue
        profile = _profile(entry)
        mine, theirs = fit_sinusoid(profile), fit_sinusoid(truth)
        rows.append({
            "page": page["page"], "plane_name": plane_name,
            "n_columns": int(truth.shape[0]),
            "spearman_x_column_profile": spearman(profile, truth),
            "median_uncertainty_dots": median_uncertainty_dots(
                entry, np.asarray(entry["support"], np.float64) > 0.0),
            "mine": mine, "supervised": theirs,
            "period_ratio": mine["period_tiles"] / theirs["period_tiles"],
            "amplitude_ratio": (mine["amplitude_dots"]
                                / theirs["amplitude_dots"]),
            "profile_max_dots": float(np.abs(profile).max()),
            "supervised_profile_max_dots": float(np.abs(truth).max()),
            "profile_max_ratio": float(np.abs(profile).max()
                                       / np.abs(truth).max()),
            "supervised_fitted_amplitude_over_e033_peak": (
                theirs["amplitude_dots"] / E033_Y_PEAK_DOTS),
        })
    return rows


# ------------------------------------------------ the pre-W2 per-lane fits

#: The plane pairs the lane comparison is scored on.  Three planes span a
#: two-dimensional differential space, so a third INDEPENDENT pair is the
#: most there is; `C-M` is `M-C` negated and every statistic below is
#: invariant under that sign, so it would be a duplicate row.
LANE_PAIRS: tuple[tuple[str, str], ...] = (("Y", "C"), ("Y", "M"),
                                           ("M", "C"))


def _differential(grids: dict[str, tuple[np.ndarray, np.ndarray]],
                  pair: tuple[str, str],
                  ) -> tuple[np.ndarray, np.ndarray] | None:
    """One plane's field minus another's, and where both carry evidence.

    THE GAUGE CANCELS HERE.  A gauge is one per-tile vector subtracted
    from every plane of the same fit — zero for the pre-W2 fitter that
    never had all three planes to take a median over, the weighted C/M
    common mode for the page field (design §2.3) — so the difference of
    two planes of ONE fit is the same quantity whichever of them was
    used.  It is the only thing the two sides can be scored on.
    """
    above, below = pair
    if above not in grids or below not in grids:
        return None
    (delta_above, support_above), (delta_below, support_below) = (
        grids[above], grids[below])
    return (delta_above - delta_below,
            (support_above > 0.0) & (support_below > 0.0))


def _lane_grids(held, indices: list[int],
                ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    return {
        identity.CMY_PLANE_ORDER[int(held["plane"][index])]: (
            np.asarray(held["delta_dots_xy"][index], np.float64),
            np.asarray(held["support"][index], np.float64))
        for index in indices}


def _page_grids(page: dict) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    return {
        entry["plane_name"]: (
            np.asarray(entry["delta_dots_xy"], np.float64),
            np.asarray(entry["support"], np.float64))
        for entry in page["planes"]}


def against_lane_fields(solved: dict, path: Path) -> list[dict]:
    """The archived per-lane fields against the page field, and each other.

    Scored on the PLANE DIFFERENTIALS, one row per (page, pair): the two
    sides are fitted in different gauges — the page field drops the
    weighted common mode of the word-ink planes, the pre-W2 fitter's
    median-of-three only ran where all three planes fitted at once, so
    an archived single-plane lane carries the plane-common bias whole —
    and a per-plane comparison scores that difference of convention as
    error.  A lane enters a pair only if it published BOTH planes; a
    page's lane inventory is reported beside the rows, because on the
    archived corpus most lanes published one plane and can be scored on
    no pair at all.
    """
    rows: list[dict] = []
    with np.load(path) as held:
        pages = sorted({int(page) for page in held["page"]})
        for page_index in pages:
            page = next((entry for entry in solved["pages"]
                         if entry["page"] == page_index), None)
            if page is None:
                continue
            mine = _page_grids(page)
            on_page = [index for index in range(held["page"].shape[0])
                       if int(held["page"][index]) == page_index]
            # the WHOLE capture id: a lane is a fit, and a differential
            # taken across two fits is the one thing here that is not
            # gauge-free, so a shared 48-bit prefix must not merge them
            lanes_by_key: dict[tuple[str, int], list[int]] = {}
            for index in on_page:
                key = (str(held["capture_id"][index]),
                       int(held["level_index"][index]))
                lanes_by_key.setdefault(key, []).append(index)
            inventory = {
                name: sum(1 for index in on_page
                          if identity.CMY_PLANE_ORDER[
                              int(held["plane"][index])] == name)
                for name in identity.CMY_PLANE_ORDER}
            for pair in LANE_PAIRS:
                ours = _differential(mine, pair)
                if ours is None:
                    continue
                our_delta, our_live = ours
                lanes: list[dict] = []
                stack, masks = [], []
                for (capture, level_index), indices in sorted(
                        lanes_by_key.items()):
                    theirs = _differential(_lane_grids(held, indices), pair)
                    if theirs is None:
                        continue
                    their_delta, their_live = theirs
                    if our_live.shape != their_live.shape:
                        raise ValueError(
                            f"tile grids disagree: the field is "
                            f"{our_live.shape} and lane {capture[:12]} "
                            f"l{level_index} is {their_live.shape} — "
                            f"different pages")
                    live = our_live & their_live
                    stack.append(their_delta)
                    masks.append(their_live)
                    gap = our_delta - their_delta
                    lanes.append({
                        "capture": capture[:12],
                        "level_index": level_index,
                        "n_tiles": int(live.sum()),
                        "median_abs_delta_dots": float(np.median(
                            np.linalg.norm(gap, axis=-1)[live]))
                        if live.any() else float("nan"),
                        "median_abs_dx_dots": float(np.median(
                            np.abs(gap[..., 0])[live]))
                        if live.any() else float("nan"),
                        "spearman_x_column_profile": spearman(
                            products.column_profile(our_delta, our_live),
                            products.column_profile(their_delta,
                                                    their_live)),
                    })
                # A spread needs two lanes to be a spread: over one it is
                # zero by construction and would read as perfect agreement.
                paired = len(stack) > 1
                everywhere = (np.all(np.stack(masks), axis=0) & our_live
                              if paired else np.zeros(our_live.shape, bool))
                spread = (np.stack(stack).max(axis=0)
                          - np.stack(stack).min(axis=0)) if paired else None
                rows.append({
                    "page": page_index,
                    "pair": f"{pair[0]}-{pair[1]}",
                    "n_lanes": len(lanes),
                    "n_lanes_archived": len(lanes_by_key),
                    "archived_lane_fields_by_plane": inventory,
                    "page_field_median_differential_dots": float(np.median(
                        np.linalg.norm(our_delta, axis=-1)[our_live]))
                    if our_live.any() else float("nan"),
                    "lane_to_lane_spread_median_dots": float(np.median(
                        np.linalg.norm(spread, axis=-1)[everywhere]))
                    if spread is not None and everywhere.any()
                    else float("nan"),
                    "lane_to_lane_spread_max_dots": float(np.max(
                        np.linalg.norm(spread, axis=-1)[everywhere]))
                    if spread is not None and everywhere.any()
                    else float("nan"),
                    "lanes": lanes,
                })
    return rows


# ------------------------------------------------------------- the tables

def _print_analyzer(rows: list[dict]) -> None:
    print("== against the analyzer's pooled fit ==")
    print("  page plane  tiles   med|dx|  med|dy|  med±  spearman_x   "
          "amp(mine/theirs)  period(mine/theirs)")
    for row in rows:
        print(f"  {row['page']:4d} {row['plane_name']:>5}  "
              f"{row['n_tiles']:5d}   {row['median_abs_dx_dots']:7.4f}  "
              f"{row['median_abs_dy_dots']:7.4f}  "
              f"{row['median_uncertainty_dots']:5.3f} "
              f"{row['spearman_x_column_profile']:10.4f}   "
              f"{row['mine']['amplitude_dots']:.4f}/"
              f"{row['analyzer']['amplitude_dots']:.4f}      "
              f"{row['mine']['period_tiles']:.2f}/"
              f"{row['analyzer']['period_tiles']:.2f}")
        print(f"       against e033's {E033_Y_PEAK_DOTS}-dot profile peak: "
              f"profile max {row['profile_max_dots']:.4f} dots = "
              f"{row['profile_max_over_e033_peak']:.3f}x, fitted amplitude "
              f"{row['fitted_amplitude_over_e033_peak']:.3f}x · trend "
              f"{row['mine']['trend_dots_per_page']:+.3f}/"
              f"{row['analyzer']['trend_dots_per_page']:+.3f} dots per page "
              f"· analyzer's own reported amplitude "
              f"{row['analyzer_reported_sinusoid_x']['amplitude_dots']:.4f}")


def _print_supervised(rows: list[dict]) -> None:
    print("== against the supervised sinusoid ==")
    for row in rows:
        print(f"  page {row['page']} {row['plane_name']}: profile max "
              f"{row['profile_max_dots']:.4f} vs "
              f"{row['supervised_profile_max_dots']:.4f} dots "
              f"({row['profile_max_ratio']:.3f}x)")
        print(f"  page {row['page']} {row['plane_name']}: spearman "
              f"{row['spearman_x_column_profile']:.4f} · median "
              f"uncertainty {row['median_uncertainty_dots']:.4f} dots"
              f" · period "
              f"{row['mine']['period_tiles']:.2f} vs "
              f"{row['supervised']['period_tiles']:.2f} tiles "
              f"({row['period_ratio']:.3f}x) · amplitude "
              f"{row['mine']['amplitude_dots']:.4f} vs "
              f"{row['supervised']['amplitude_dots']:.4f} dots "
              f"({row['amplitude_ratio']:.3f}x) · r2 "
              f"{row['mine']['r_squared']:.3f}/"
              f"{row['supervised']['r_squared']:.3f}")


def _print_lanes(rows: list[dict]) -> None:
    print("== against the pre-W2 per-lane fits, on plane differentials ==")
    for row in rows:
        if row["pair"] == LANE_PAIRS[0][0] + "-" + LANE_PAIRS[0][1]:
            counts = " ".join(
                f"{name} {count}" for name, count
                in row["archived_lane_fields_by_plane"].items())
            print(f"  page {row['page']}: {row['n_lanes_archived']} archived "
                  f"lanes, published fields per plane: {counts}")
        print(f"  page {row['page']} {row['pair']:>3}: {row['n_lanes']} "
              f"lanes carry both planes · page field median differential "
              f"{row['page_field_median_differential_dots']:.4f} dots · "
              f"lane-to-lane spread median "
              f"{row['lane_to_lane_spread_median_dots']:.4f} max "
              f"{row['lane_to_lane_spread_max_dots']:.4f}")
        for lane in row["lanes"]:
            print(f"      {lane['capture']} l{lane['level_index']}: "
                  f"|delta| vs page field "
                  f"{lane['median_abs_delta_dots']:.4f} "
                  f"(x {lane['median_abs_dx_dots']:.4f}) over "
                  f"{lane['n_tiles']} tiles · spearman "
                  f"{lane['spearman_x_column_profile']:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fields", type=Path, required=True,
                        help="estimate.py's fields.json")
    parser.add_argument("--analyzer", type=Path,
                        help="analyzer field2 sweep json (pooled fits)")
    parser.add_argument("--supervised", type=Path,
                        help="regmap-gt/plane-offsets.json")
    parser.add_argument("--lane-fields", dest="lane_fields", type=Path,
                        help="extract.py's plane_fields.npz")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    solved = json.loads(args.fields.read_text())
    payload: dict = {"fields": str(args.fields),
                     "field_noise_dots": plane_field.FIELD_NOISE_DOTS,
                     "e033_y_peak_dots": E033_Y_PEAK_DOTS}
    if args.analyzer is not None:
        payload["analyzer"] = {"source": str(args.analyzer),
                               "rows": against_analyzer(solved,
                                                        args.analyzer)}
        _print_analyzer(payload["analyzer"]["rows"])
    if args.supervised is not None:
        payload["supervised"] = {"source": str(args.supervised),
                                 "rows": against_supervised(solved,
                                                            args.supervised)}
        _print_supervised(payload["supervised"]["rows"])
    if args.lane_fields is not None:
        payload["lane_fields"] = {
            "source": str(args.lane_fields),
            "rows": against_lane_fields(solved, args.lane_fields)}
        _print_lanes(payload["lane_fields"]["rows"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
