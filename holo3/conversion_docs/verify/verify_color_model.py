# Verify holo3/plugins/color_model.py against src/holo oracles, in one
# process.  Run from the worktree root:
#   PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_color_model.py
import numpy as np

from holo3.format import identity as h3_identity
from holo3.lib import pava as h3_pava
from holo3.plugins import color_model as cm

from holo.core import channel as o_channel
from holo.format.resolve import resolve_format_ref as o_resolve
from holo.receive import color_anchoring as o_anchor
from holo.receive import color_calibration as o_cal
from holo.receive import color_detect as o_detect

CHECKS = 0
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILS.append(f"{name}: {detail}")
        print(f"FAIL {name} {detail}")


def eq_arr(name: str, a, b) -> None:
    a = np.asarray(a)
    b = np.asarray(b)
    check(name, a.shape == b.shape and np.array_equal(a, b),
          f"shapes {a.shape}/{b.shape} maxdiff "
          f"{np.max(np.abs(np.asarray(a, np.float64) - np.asarray(b, np.float64))) if a.shape == b.shape and a.size else 'n/a'}")


# ---------- feature generators ----------

STATE_BITS = ((np.arange(8)[:, None] >> np.arange(3)[None, :]) & 1)


def gen_features(states: np.ndarray, rng, noise: float = 0.06,
                 collapse_pair: tuple[int, int] | None = None) -> np.ndarray:
    bits = STATE_BITS[states % 8].astype(np.float64)
    means = 0.9 - 0.55 * bits
    if collapse_pair is not None:
        a, b = collapse_pair
        sel = states == b
        means[sel] = 0.9 - 0.55 * STATE_BITS[a].astype(np.float64)
    return means + rng.normal(0.0, noise, (states.size, 3))


# ---------- 1. blind EM detector ----------

rng = np.random.default_rng(20260828)
for trial in range(6):
    shape = [(40, 3), (200,), (64, 6), (25, 25), (300, 3), (12, 2)][trial]
    means = rng.uniform(0.0, 1.0, shape)
    if trial == 3:
        means = np.round(means, 1)
    m_bits, m_llr = cm.blind_component_bits(means)
    o_bits, o_llr = o_detect.blind_component_bits(means)
    eq_arr(f"blind.bits[{trial}]", m_bits, o_bits)
    eq_arr(f"blind.llr[{trial}]", m_llr, o_llr)
    check(f"blind.dtype[{trial}]",
          m_bits.dtype == np.uint8 and m_llr.dtype == np.float64)
check("blind.confident_const",
      cm.BLIND_CONFIDENT_LLR == o_detect.BLIND_CONFIDENT_LLR)


# ---------- 2. QDA fit + scores ----------

def compare_qda(tag: str, x: np.ndarray, y: np.ndarray,
                n_states: int) -> tuple[object, object]:
    mine = cm.fit_qda(x, y, n_states)
    oracle = o_detect.fit_equal_prior_qda(x, y, n_states=n_states)
    eq_arr(f"qda.means[{tag}]", mine.means, oracle.means)
    for s in range(n_states):
        eq_arr(f"qda.chol[{tag},{s}]", mine.cholesky[s], oracle.cholesky[s])
    eq_arr(f"qda.logdet[{tag}]", mine.log_determinants,
           oracle.log_determinants)
    eq_arr(f"qda.counts[{tag}]", mine.class_counts, oracle.class_counts)
    check(f"qda.clipped[{tag}]",
          mine.clipped_planes == oracle.clipped_planes,
          f"{mine.clipped_planes} vs {oracle.clipped_planes}")
    check(f"qda.degenerate[{tag}]", mine.degenerate == oracle.degenerate)
    probe = gen_features(rng.integers(0, n_states, 120), rng)
    eq_arr(f"qda.scores[{tag}]", cm.qda_log_scores(mine, probe),
           o_detect.qda_log_scores(oracle, probe))
    if n_states == 7:
        eq_arr(f"qda.cmy7rel[{tag}]", cm.cmy7_relative_scores(mine, probe),
               o_detect.cmy7_relative_scores(oracle, probe))
    else:
        raw_scores = rng.normal(0.0, 4.0, (90, 8))
        eq_arr(f"qda.cmy8marg[{tag}]", cm.cmy8_marginal_llrs(raw_scores),
               o_detect.cmy8_marginal_llrs(raw_scores))
        eq_arr(f"qda.cmy8raw[{tag}]", cm.cmy8_raw_llrs(mine, probe),
               o_detect.cmy8_raw_llrs(oracle, probe))
    return mine, oracle


saw_degenerate = saw_clipped = 0
for trial in range(10):
    n_states = 7 if trial % 2 == 0 else 8
    n = int(rng.integers(60, 400))
    y = rng.integers(0, n_states, n)
    y[:n_states] = np.arange(n_states)
    x = gen_features(y, rng)
    compare_qda(f"rand{trial}", x, y, n_states)

for trial, missing in enumerate(((3,), (0, 5), (6,))):
    n_states = 8 if trial != 1 else 7
    n = 160
    allowed = np.setdiff1d(np.arange(n_states), np.asarray(missing))
    y = rng.choice(allowed, n)
    x = gen_features(y, rng)
    mine, _oracle = compare_qda(f"empty{trial}", x, y, n_states)
    if mine.degenerate:
        saw_degenerate += 1

for trial, pair in enumerate(((1, 5), (2, 6), (0, 4))):
    n_states = 8
    n = 240
    y = rng.integers(0, n_states, n)
    y[:n_states] = np.arange(n_states)
    x = gen_features(y, rng, noise=0.03, collapse_pair=pair)
    mine, _oracle = compare_qda(f"collapse{trial}", x, y, n_states)
    if mine.clipped_planes:
        saw_clipped += 1

y = rng.integers(0, 7, 90)
y[:7] = np.arange(7)
y[y == 2] = 1
y[:2] = 2
compare_qda("lowcount", gen_features(y, rng), y, 7)

check("qda.saw_degenerate", saw_degenerate == 3)
check("qda.saw_clipped", saw_clipped >= 2, f"{saw_clipped}")


# ---------- 3. PAVA maps ----------

def compare_pava(tag: str, scores: np.ndarray, labels: np.ndarray) -> None:
    mine = cm.fit_component_pava(scores, labels)
    oracle = o_detect.fit_component_pava(scores, labels)
    eq_arr(f"pava.snodes[{tag}]", mine.score_nodes, oracle.score_nodes)
    eq_arr(f"pava.pnodes[{tag}]", mine.probability_nodes,
           oracle.probability_nodes)
    check(f"pava.nlabels[{tag}]", mine.n_labels == oracle.n_labels)
    probe = rng.normal(0.0, 5.0, 200)
    eq_arr(f"pava.llrs[{tag}]", mine.llrs(probe), oracle.llrs(probe))


for trial in range(10):
    n = int(rng.integers(12, 300))
    labels = rng.integers(0, 2, n)
    labels[:2] = (0, 1)
    scores = rng.normal(0.0, 3.0, n) + 2.5 * (labels - 0.5)
    if trial % 3 == 1:
        scores = np.round(scores, 1)
    compare_pava(f"rand{trial}", scores, labels)

compare_pava("anchor", np.asarray([-2.0, -1.0, 1.0, 2.0]),
             np.asarray([0, 0, 1, 1]))
compare_pava("antimono", np.asarray([-1.0, 0.5, 0.5, 2.0, 3.0]),
             np.asarray([1, 0, 1, 0, 0]))
anchored = cm.fit_component_pava(
    np.asarray([-2.0, -1.0, 1.0, 2.0]), np.asarray([0, 0, 1, 1]))
check("pava.anchor_node_present",
      np.any(anchored.score_nodes == 0.0)
      and np.any(anchored.probability_nodes == 0.5))

neutral = cm.neutral_pava_map(30)
eq_arr("pava.neutral_zero", neutral.llrs(rng.normal(0, 5, 50)),
       np.zeros(50))


# ---------- 4. cmy8 support qualification + detector ----------

def compare_support(tag: str, states: np.ndarray) -> None:
    m_sup, m_rea = cm.qualify_cmy8_support(states)
    oracle = o_detect.qualify_cmy8_calibration_support(states)
    check(f"support.flags[{tag}]",
          m_sup == tuple(oracle.supported_planes),
          f"{m_sup} vs {oracle.supported_planes}")
    check(f"support.reasons[{tag}]",
          m_rea == tuple(oracle.unsupported_reasons),
          f"{m_rea} vs {oracle.unsupported_reasons}")


for trial in range(8):
    n = int(rng.integers(8, 80))
    compare_support(f"rand{trial}", rng.integers(0, 8, n))
compare_support("allone", np.full(40, 7))
compare_support("oddonly", rng.choice((1, 3, 5, 7), 48))
compare_support("pair", rng.choice((0, 7), 60))
compare_support("cycle", np.tile(np.asarray((1, 2, 4, 5, 6, 7)), 3))


SEEN_DETECTOR: dict[str, int] = {
    "degenerate": 0, "collapsed": 0, "unsupported": 0, "mixed": 0,
    "all_supported": 0,
}


def compare_detector(tag: str, ty: np.ndarray, tx_feat: np.ndarray,
                     cy: np.ndarray, cx_feat: np.ndarray) -> None:
    mine = cm.fit_cmy8_detector(tx_feat, ty, cx_feat, cy)
    oracle = o_detect.fit_cmy8_detector(tx_feat, ty, cx_feat, cy)
    if any(r == "qda_degenerate" for r in mine.unsupported_reasons):
        SEEN_DETECTOR["degenerate"] += 1
    if any(r is not None and r.startswith("qda_collapsed:")
           for r in mine.unsupported_reasons):
        SEEN_DETECTOR["collapsed"] += 1
    if not all(mine.supported_planes):
        SEEN_DETECTOR["unsupported"] += 1
    if any(mine.supported_planes) and not all(mine.supported_planes):
        SEEN_DETECTOR["mixed"] += 1
    if all(mine.supported_planes):
        SEEN_DETECTOR["all_supported"] += 1
    check(f"det.supported[{tag}]",
          mine.supported_planes == tuple(oracle.supported_planes),
          f"{mine.supported_planes} vs {oracle.supported_planes}")
    check(f"det.reasons[{tag}]",
          mine.unsupported_reasons == tuple(oracle.unsupported_reasons),
          f"{mine.unsupported_reasons} vs {oracle.unsupported_reasons}")
    check(f"det.nlabels[{tag}]",
          mine.calibration_labels == oracle.calibration_labels)
    for plane in range(3):
        eq_arr(f"det.map_s[{tag},{plane}]",
               mine.calibrations[plane].score_nodes,
               oracle.calibrations[plane].score_nodes)
        eq_arr(f"det.map_p[{tag},{plane}]",
               mine.calibrations[plane].probability_nodes,
               oracle.calibrations[plane].probability_nodes)
    probe = gen_features(rng.integers(0, 8, 150), rng)
    m_llrs = mine.llrs(probe)
    o_llrs = oracle.llrs(probe)
    eq_arr(f"det.llrs[{tag}]", m_llrs, o_llrs)
    for plane in range(3):
        if not mine.supported_planes[plane]:
            check(f"det.zero[{tag},{plane}]",
                  np.all(m_llrs[:, plane] == 0.0))


for trial in range(4):
    n = 300
    ty = rng.integers(0, 8, n)
    ty[:8] = np.arange(8)
    cy = rng.integers(0, 8, 64)
    cy[:8] = np.arange(8)
    compare_detector(f"healthy{trial}", ty, gen_features(ty, rng),
                     cy, gen_features(cy, rng))

ty = rng.integers(0, 8, 300)
ty[:8] = np.arange(8)
cy = rng.choice((1, 3, 5, 7), 64)
compare_detector("csat", ty, gen_features(ty, rng), cy,
                 gen_features(cy, rng))

ty = rng.choice(np.arange(7), 300)
ty[:7] = np.arange(7)
cy = rng.integers(0, 8, 64)
cy[:8] = np.arange(8)
compare_detector("degenerate", ty, gen_features(ty, rng), cy,
                 gen_features(cy, rng))

ty = rng.integers(0, 8, 300)
ty[:8] = np.arange(8)
cy = rng.integers(0, 8, 64)
cy[:8] = np.arange(8)
compare_detector("collapse", ty,
                 gen_features(ty, rng, noise=0.03, collapse_pair=(2, 6)),
                 cy, gen_features(cy, rng, noise=0.03,
                                  collapse_pair=(2, 6)))

# One plane structurally starved in the dust population (C always inked)
# while M/Y qualify: proves a MIXED support tuple, an exactly-0.0 column
# beside live columns, and the plane_fitted -> neutral-map route.
ty = rng.integers(0, 8, 400)
ty[:8] = np.arange(8)
cy = np.concatenate([rng.choice((1, 3, 5, 7), 40), np.asarray((1, 3, 5, 7))])
mine_mixed = cm.fit_cmy8_detector(
    gen_features(ty, rng), ty, gen_features(cy, rng), cy)
oracle_mixed = o_detect.fit_cmy8_detector(
    gen_features(ty, rng), ty, gen_features(cy, rng), cy)
check("det.mixed_support_shape",
      mine_mixed.supported_planes[0] is False
      and any(mine_mixed.supported_planes[1:]),
      f"{mine_mixed.supported_planes}")
probe = gen_features(rng.integers(0, 8, 90), rng)
mixed_llrs = mine_mixed.llrs(probe)
check("det.mixed_zero_column", np.all(mixed_llrs[:, 0] == 0.0))
check("det.mixed_live_column", np.any(mixed_llrs[:, 1] != 0.0)
      or np.any(mixed_llrs[:, 2] != 0.0))
check("det.mixed_reason_class_labels",
      mine_mixed.unsupported_reasons[0] == "class_labels:0",
      f"{mine_mixed.unsupported_reasons}")
del oracle_mixed

check("det.saw_degenerate", SEEN_DETECTOR["degenerate"] >= 1,
      f"{SEEN_DETECTOR}")
check("det.saw_collapsed", SEEN_DETECTOR["collapsed"] >= 1,
      f"{SEEN_DETECTOR}")
check("det.saw_all_supported", SEEN_DETECTOR["all_supported"] >= 1,
      f"{SEEN_DETECTOR}")
check("det.saw_unsupported", SEEN_DETECTOR["unsupported"] >= 1,
      f"{SEEN_DETECTOR}")
print(f"detector coverage: {SEEN_DETECTOR}")

check("plane_order.matches_oracle",
      h3_identity.CMY_PLANE_ORDER == tuple(o_channel.PLANE_ORDER),
      f"{h3_identity.CMY_PLANE_ORDER} vs {o_channel.PLANE_ORDER}")
check("clip.constants",
      cm.DEGENERATE_LLR_CLIP == o_detect.DEGENERATE_LLR_CLIP
      and cm.QDA_RIDGE == o_detect.QDA_RIDGE
      and cm.QDA_COLLAPSE_DIST == o_detect.QDA_COLLAPSE_DIST
      and cm.CMY8_CALIBRATION_MIN_CLASS_LABELS
      == o_detect.CMY8_CALIBRATION_MIN_CLASS_LABELS
      and cm.CMY8_CALIBRATION_MIN_STATES_PER_CLASS
      == o_detect.CMY8_CALIBRATION_MIN_STATES_PER_CLASS
      and cm.CMY8_CALIBRATION_MIN_LABELS_PER_STATE
      == o_detect.CMY8_CALIBRATION_MIN_LABELS_PER_STATE)
check("head.constants",
      cm.HEAD_N_OFFSETS == o_cal.HEAD_N_OFFSETS
      and cm.HEAD_SCALE_MIN == o_cal.HEAD_SCALE_MIN
      and cm.HEAD_SCALE_MAX == o_cal.HEAD_SCALE_MAX
      and cm.HEAD_MAX_ITERATIONS == o_cal.HEAD_MAX_ITERATIONS
      and cm.HEAD_GRAD_TOL == o_cal.HEAD_GRAD_TOL
      and cm.HEAD_MIN_SEARCH_PER_STATE == o_cal.HEAD_MIN_SEARCH_PER_STATE
      and cm.HEAD_MIN_VALIDATION == o_cal.HEAD_MIN_VALIDATION
      and cm.HEAD_MIN_VALIDATION_PER_STATE
      == o_cal.HEAD_MIN_VALIDATION_PER_STATE
      and cm.HEAD_GATE_SLACK == o_cal.HEAD_GATE_SLACK)

# QDA genericity: the collapse guard indexes planes 0..2 but the fit is
# generic in D.  A four-feature population must still match exactly.
for trial in range(3):
    n = 220
    y = rng.integers(0, 8, n)
    y[:8] = np.arange(8)
    x4 = np.concatenate(
        [gen_features(y, rng), rng.normal(0.0, 0.4, (n, 1))], axis=1)
    mine = cm.fit_qda(x4, y, 8)
    oracle = o_detect.fit_equal_prior_qda(x4, y, n_states=8)
    eq_arr(f"qda4.means[{trial}]", mine.means, oracle.means)
    eq_arr(f"qda4.logdet[{trial}]", mine.log_determinants,
           oracle.log_determinants)
    check(f"qda4.clipped[{trial}]",
          mine.clipped_planes == oracle.clipped_planes)
    probe4 = np.concatenate(
        [gen_features(rng.integers(0, 8, 70), rng),
         rng.normal(0.0, 0.4, (70, 1))], axis=1)
    eq_arr(f"qda4.scores[{trial}]", cm.qda_log_scores(mine, probe4),
           o_detect.qda_log_scores(oracle, probe4))
    eq_arr(f"qda4.raw[{trial}]", cm.cmy8_raw_llrs(mine, probe4),
           o_detect.cmy8_raw_llrs(oracle, probe4))


# ---------- 5. class-balanced weights ----------

for trial in range(10):
    n = int(rng.integers(5, 200))
    labels = rng.integers(0, 7, n)
    eq_arr(f"cbw[{trial}]", h3_pava.class_balanced_weights(labels),
           o_cal.class_balanced_weights(labels))
eq_arr("cbw.onestate", h3_pava.class_balanced_weights(np.full(30, 4)),
       o_cal.class_balanced_weights(np.full(30, 4)))


# ---------- 6. head Newton trajectory end-state ----------

def gen_head_population(rng, n: int):
    states = rng.integers(0, 7, n)
    states[:7] = np.arange(7)
    base = rng.normal(0.0, 3.0, (7, 6))
    scores = base[states] + rng.normal(0.0, 1.5, (n, 6))
    return scores, states


for trial in range(25):
    n = int(rng.integers(80, 400))
    scores, states = gen_head_population(rng, n)
    weights = o_cal.class_balanced_weights(states)
    m_scale, m_offsets, m_iters = cm._newton(scores, states, weights)
    o_scale, o_offsets, o_iters = o_cal._newton(scores, states, weights)
    check(f"newton.scale[{trial}]", m_scale == o_scale,
          f"{m_scale} vs {o_scale}")
    eq_arr(f"newton.offsets[{trial}]", m_offsets, o_offsets)
    check(f"newton.iters[{trial}]", m_iters == o_iters,
          f"{m_iters} vs {o_iters}")


# ---------- 7. fit_cmy7_head ----------

def compare_head(tag: str, scores, states, keys) -> str:
    mine_head, mine_reason = cm.fit_cmy7_head(scores, states, keys)
    oracle = o_cal.fit_cmy7_head(
        scores, states, keys,
        qda_search_site_keys=np.zeros((0, 3), np.int64))
    check(f"head.reason[{tag}]", mine_reason == oracle.reason,
          f"{mine_reason} vs {oracle.reason}")
    check(f"head.adopted[{tag}]",
          (mine_head is not None) == oracle.adopted)
    if mine_head is not None and oracle.head is not None:
        check(f"head.scale[{tag}]", mine_head.scale == oracle.head.scale,
              f"{mine_head.scale} vs {oracle.head.scale}")
        eq_arr(f"head.offsets[{tag}]", mine_head.offsets,
               oracle.head.offsets)
        probe = rng.normal(0.0, 4.0, (60, 6))
        eq_arr(f"head.apply[{tag}]", mine_head.apply(probe),
               oracle.head.apply(probe))
    eq_arr(f"head.subsplit[{tag}]", cm.head_sub_split(keys),
           o_cal.head_sub_split(keys))
    if oracle.identity_validation_nll is not None:
        # Reproduce the gate arithmetic from holo3's own kernels and
        # compare with the oracle's recorded decision floats — this is
        # the only way a REFUSED head's numbers get checked.
        fit_side = cm.head_sub_split(keys)
        scale, offsets, _iters = cm._newton(
            np.asarray(scores, np.float64)[fit_side],
            np.asarray(states, np.int64)[fit_side],
            h3_pava.class_balanced_weights(
                np.asarray(states, np.int64)[fit_side]))
        v_scores = np.asarray(scores, np.float64)[~fit_side]
        v_states = np.asarray(states, np.int64)[~fit_side]
        v_weights = h3_pava.class_balanced_weights(v_states)
        identity = cm._mean_nll(v_scores, v_states, 1.0,
                                np.zeros(6, np.float64), v_weights)
        candidate = cm._mean_nll(v_scores, v_states, scale, offsets,
                                 v_weights)
        check(f"head.identity_nll[{tag}]",
              identity == oracle.identity_validation_nll,
              f"{identity} vs {oracle.identity_validation_nll}")
        check(f"head.candidate_nll[{tag}]",
              candidate == oracle.candidate_validation_nll,
              f"{candidate} vs {oracle.candidate_validation_nll}")
    return mine_reason


def unique_keys(rng, n: int) -> np.ndarray:
    cells = rng.choice(64 * 64, size=n, replace=False)
    return np.stack([np.zeros(n, np.int64), cells // 64, cells % 64],
                    axis=1)


reasons_seen: set[str] = set()
for trial in range(25):
    n = int(rng.integers(150, 700))
    scores, states = gen_head_population(rng, n)
    if trial % 4 == 0:
        scores = scores * float(rng.uniform(1.5, 4.0))
    keys = unique_keys(rng, n)
    reasons_seen.add(compare_head(f"rand{trial}", scores, states, keys))

n = 200
scores, states = gen_head_population(rng, n)
states[states == 6] = 5
states[:7] = np.arange(7)
reasons_seen.add(compare_head("searchstarved", scores, states,
                              unique_keys(rng, n)))

all_cells = np.arange(64 * 64)
fit_cells = all_cells[((131 * (all_cells // 64) + 17 * (all_cells % 64))
                       & 2) == 0]
val_cells = all_cells[((131 * (all_cells // 64) + 17 * (all_cells % 64))
                       & 2) != 0]
n_fit, n_val = 180, 20
pick = np.concatenate([rng.choice(fit_cells, n_fit, replace=False),
                       rng.choice(val_cells, n_val, replace=False)])
keys = np.stack([np.zeros(pick.size, np.int64), pick // 64, pick % 64],
                axis=1)
scores, states = gen_head_population(rng, pick.size)
reasons_seen.add(compare_head("heldoutstarved", scores, states, keys))

check("head.saw_adopted", "adopted" in reasons_seen, f"{reasons_seen}")
check("head.saw_search_starved", "search_class_starved" in reasons_seen)
check("head.saw_heldout_starved", "heldout_starved" in reasons_seen)
print(f"head reasons seen: {sorted(reasons_seen)}")


# ---------- 8. reference_states vs color_anchoring ----------

for ref in ("L:c3-cmy7-p120-v0@2240x1536", "L:c2-cmy8-p120-v0@3328x2304"):
    row = h3_identity.resolve_format_ref(ref)
    geom = h3_identity.build_site_geometry(row)
    spec = o_resolve(ref)
    cy, cx = row.cells_yx
    rand_cells = np.stack([rng.integers(0, cy, 2500),
                           rng.integers(0, cx, 2500)], axis=1)
    tiles = [(0, 0), (3, 5), (row.tiles_yx[0] - 1, row.tiles_yx[1] - 1)]
    tile_cells = np.concatenate([
        np.stack(np.meshgrid(np.arange(ty * 64, ty * 64 + 64),
                             np.arange(tx * 64, tx * 64 + 64),
                             indexing="ij"), axis=-1).reshape(-1, 2)
        for ty, tx in tiles])
    for tag, cells in (("rand", rand_cells), ("tiles", tile_cells),
                       ("empty", np.zeros((0, 2), np.int64))):
        m_states, m_kinds = cm.reference_states(row, geom, 0, cells)
        o_states, o_kinds = o_anchor.color_reference_states(spec, 0, cells)
        eq_arr(f"refstates.states[{ref},{tag}]", m_states, o_states)
        eq_arr(f"refstates.kinds[{ref},{tag}]", m_kinds, o_kinds)
        check(f"refstates.dtype[{ref},{tag}]",
              m_states.dtype == np.int8 and m_kinds.dtype == np.int8)

row = h3_identity.resolve_format_ref("L:c3-cmy7-p120-v0@2240x1536",
                                     n_pages=2)
geom = h3_identity.build_site_geometry(row)
spec = o_resolve("L:c3-cmy7-p120-v0@2240x1536")
cells = np.stack([rng.integers(0, row.cells_yx[0], 800),
                  rng.integers(0, row.cells_yx[1], 800)], axis=1)
m_states, m_kinds = cm.reference_states(row, geom, 1, cells)
o_states, o_kinds = o_anchor.color_reference_states(spec, 1, cells)
eq_arr("refstates.page1.states", m_states, o_states)
eq_arr("refstates.page1.kinds", m_kinds, o_kinds)


# ---------- 9. numerical edges ----------

# blind EM on a constant field: hi == lo exercises the max(..., 1e-6)
# guard and the mu-ordering swap.
for tag, means in (
    ("const", np.full((30, 3), 0.42)),
    ("twovalue", np.where(rng.integers(0, 2, (40, 4)) > 0, 0.8, 0.2)),
    ("tiny", np.asarray([[0.5, 0.5000001]])),
):
    m_bits, m_llr = cm.blind_component_bits(means)
    o_bits, o_llr = o_detect.blind_component_bits(means)
    eq_arr(f"blind.edge.bits[{tag}]", m_bits, o_bits)
    eq_arr(f"blind.edge.llr[{tag}]", m_llr, o_llr)

# PAVA with every score tied (one group) and with heavy tie blocks.
compare_pava("alltied", np.full(24, 1.5),
             np.concatenate([np.zeros(12, int), np.ones(12, int)]))
tied_scores = np.repeat(np.asarray([-1.0, -1.0, 0.0, 0.0, 2.0]), 8)
tied_labels = rng.integers(0, 2, tied_scores.size)
tied_labels[:2] = (0, 1)
compare_pava("tieblocks", tied_scores, tied_labels)

# Newton on a singular Hessian (constant score columns) must take the
# damping-escalation route identically.
for tag, scores in (
    ("zeros", np.zeros((120, 6))),
    ("constcol", np.tile(np.asarray([1.0, -2.0, 0.5, 0.0, 3.0, -1.0]),
                         (120, 1))),
):
    states = rng.integers(0, 7, 120)
    states[:7] = np.arange(7)
    weights = o_cal.class_balanced_weights(states)
    m_scale, m_offsets, m_iters = cm._newton(scores, states, weights)
    o_scale, o_offsets, o_iters = o_cal._newton(scores, states, weights)
    check(f"newton.edge.scale[{tag}]", m_scale == o_scale,
          f"{m_scale} vs {o_scale}")
    eq_arr(f"newton.edge.offsets[{tag}]", m_offsets, o_offsets)
    check(f"newton.edge.iters[{tag}]", m_iters == o_iters,
          f"{m_iters} vs {o_iters}")

# A head that cannot beat the identity on the held-out sub-split:
# scores drawn AS the true softmax logits leave nothing to calibrate.
gate_failed = 0
for trial in range(12):
    per_state = 40
    rows_scores: list[np.ndarray] = []
    rows_states: list[int] = []
    remaining = [per_state] * 7
    while any(remaining):
        z = rng.normal(0.0, 2.0, 6)
        logits = np.concatenate([np.zeros(1), z])
        probabilities = np.exp(logits - logits.max())
        probabilities /= probabilities.sum()
        state = int(rng.choice(7, p=probabilities))
        if remaining[state] == 0:
            continue
        remaining[state] -= 1
        rows_scores.append(z)
        rows_states.append(state)
    scores = np.asarray(rows_scores)
    states = np.asarray(rows_states, np.int64)
    order = rng.permutation(states.size)
    scores, states = scores[order], states[order]
    keys = unique_keys(rng, states.size)
    # Deliberate regime mismatch: the &2 search side is fitted on
    # HALVED scores, so the head learns a ~ 2 and must lose on the
    # unscaled validation side.  (MEASUREMENTS §9.3's failure mode,
    # used here only to reach the refusal branch.)
    scores = np.where(
        cm.head_sub_split(keys)[:, None], scores * 0.5, scores)
    reason = compare_head(f"calibrated{trial}", scores, states, keys)
    reasons_seen.add(reason)
    if reason == "validation_gate_failed":
        gate_failed += 1
check("head.saw_validation_gate_failed", gate_failed >= 1,
      f"{gate_failed} of 12; reasons {sorted(reasons_seen)}")
print(f"head reasons seen (final): {sorted(reasons_seen)}")

# reference_states on the remaining colour fossils, incl. the pooled -v1
# row and its largest tile matrix.
for ref in ("L:c2-cmy7-p120-v0@3328x2304",
            "L:c3-cmy8-p120-v0@2240x1536",
            "L:c2-cmy8-p120-v1@3392x2368",
            "L:c2-cmy8-r0700-p120-x1@3392x2368"):
    row = h3_identity.resolve_format_ref(ref)
    geom = h3_identity.build_site_geometry(row)
    spec = o_resolve(ref)
    cy, cx = row.cells_yx
    cells = np.stack([rng.integers(0, cy, 1500),
                      rng.integers(0, cx, 1500)], axis=1)
    corner = np.stack(np.meshgrid(
        np.arange(cy - 64, cy), np.arange(cx - 64, cx),
        indexing="ij"), axis=-1).reshape(-1, 2)
    for tag, probe_cells in (("rand", cells), ("lasttile", corner)):
        m_states, m_kinds = cm.reference_states(row, geom, 0, probe_cells)
        o_states, o_kinds = o_anchor.color_reference_states(
            spec, 0, probe_cells)
        eq_arr(f"refstates2.states[{ref},{tag}]", m_states, o_states)
        eq_arr(f"refstates2.kinds[{ref},{tag}]", m_kinds, o_kinds)
    check(f"refstates2.kindcover[{ref}]",
          set(np.unique(cm.reference_states(row, geom, 0, corner)[1]).tolist())
          == {-1, 0, 1})

print(f"\n{CHECKS} checks, {len(FAILS)} failures")
if FAILS:
    raise SystemExit(1)
print("verify_color_model: ALL GREEN")
