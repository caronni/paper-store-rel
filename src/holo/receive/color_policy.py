"""The hand-bumped colour payload policy identity.

One literal string, spelled in full and never derived from a live
constant — a decode's declared identity is a fact about the code that
produced it, so it is written out and hand-bumped, never assembled from
whatever the constants happen to say today.  (The one generated segment
is A3's, and it is generated precisely so a SWEPT run cannot claim
numbers it did not use.)

It lives in its own module because every campaign packet must bump it
and its rationale block is long: kept inside ``color_payload`` it pushed
that file over the 1000-line rule on the first packet that added a
paragraph.  ``color_payload`` re-exports the name, so every importer and
every pin is unchanged.
"""
from __future__ import annotations

from .color_context import ContextConfig
from .color_locality import WindowPhotometryConfig


# Hand-bumped identity, spelled literally in full — never derived from a
# live constant.  v5-pool-law = the §8.2 pool law's color half: certified-
# complete windows and D7 label placements join the region fit and pitch
# pool as furniture-site label rows.  v6-refine (rework 6.1, ruling 10.6)
# introduced the §7 certified forward pose refinement inline.  v7-r-lane
# (v0.42 stage C): refinement moves out of the inline barrier into the
# refinement level R(Lk).  v8-r-lane: the R level's
# committed-pose domain is the SHARED ``place.place_committed``
# reconstruction (K parity) — each durable base pose re-samples and
# re-audits on the re-derived base aperture, so the window inventory is
# the base lane's audited cell set, never the full in-bounds window
# rectangle (whose off-support cells crashed the R delta on partial-
# coverage scrap material); the level gates pixel-free on the committed
# span (K's exact-superset argument), crop-free per window on
# certified-cargo overlap AND uncertified remainder, and on adoption
# contributes the affected-region delta in the R lane's OWN evidence
# namespace with the adopted poses minted under the R lane id — so every
# durable color payload product is re-derived under this identity.
#
# cmy7cal-temp7-heldout-subsplit-satfloor30 (color-uplift P1 + PK3.1,
# RECEIVE-DESIGN §6.2a arm A4): CMY7 relative scores are no longer
# emitted raw.  A seven-parameter head — one scale shared by all six
# relative logits plus one offset each, W's logit pinned at 0 — is fitted
# per region by damped Newton over the QDA's own HELD-OUT side (the
# overconfidence is out-of-sample), nested-split by ``(131y+17x)&2`` into
# a fitting and a gating population, and adopted only on BOTH a strict
# validation-NLL improvement AND a deployment population at least 30%
# saturated before any head.  That second condition is PK3.1: the
# furniture gate alone adopted in all twelve xerox c3-cmy7 lanes,
# INCLUDING the one where the head strictly loses certificates
# (``color_stack.HEAD_SATURATION_FLOOR``, COLOR-UPLIFT-MEASUREMENTS
# §4.5.1/§4.5.2).  Either refusal emits NO head and the literal pre-P1
# path.  The token FOLLOWS ``cmy7linf20``: the bound still applies, now
# to calibrated scores.
#
# winphot-gainoffset-adaptivehalo-shrink<L> (color-uplift P0/PK4.1,
# §6.2a arm A3): per-window per-RGB-channel gain+offset maps fitted
# toward the region QDA's class means over the window's OWN labelled
# search cells — neighbours pooled only for a window too starved to
# identify six parameters alone — class-balanced, shrunk toward identity
# with a prior of L effective labels, and adopted through a per-window
# held-out pre-gate plus the region-level three-way comparison on a
# REFITTED region QDA.  L is GENERATED into the token, so a decode's
# declared identity cannot drift from the number it ran.  It precedes
# ``cmy7linf20``: maps change FEATURES, the head and the bound then act
# on their scores.
#
# PK-CLEAN retired the two region-applicability constants this segment
# used to carry (``dispfloor<D>`` and ``normdisp<N>``).  Both were
# measured on all 27 lanes of two captures and NEITHER separates the
# lanes A3 helps from the lanes it taxes — refusing every harmed lane
# needs a floor above 31.1, keeping every helped one needs at most 2.09
# (COLOR-UPLIFT-MEASUREMENTS §6.3/§7.4, retired at §12).  The arm's
# applicability is answered by SCHEDULING instead, which the
# ``union-lanes-…`` segment below names: A3 is unreachable from the
# standard ladder and runs only in its own supplemental lane.
#
# knownfield-conditioned-marginals (color-uplift P9/PK10, §6.2a arm A4b):
# a CMY8 component's marginal is taken over the state SUBSET consistent
# with its prior-barrier CERTIFIED siblings — 4-vs-4 with none known (the
# normal case, and byte-identical to every earlier identity), 2-vs-2 with
# one, 1-vs-1 with both — and read through a calibration STRATIFIED by
# (plane, conditioning-pattern), fitted from cert-cross payload cells
# where they are dense and from deterministically MASKED format furniture
# everywhere (reveal field ``(131y+17x)&12``, whose low bit is the spec's
# named &4).  Two gates: each stratum earns its own map on held-out
# furniture read at ITS pattern, then the surviving set faces the
# standing three-way comparison.  Every refusal, and every cell with no
# certified sibling, emits the literal pre-P9 evidence.  The token
# FOLLOWS the cmy7 head's: they are the two halves of one ladder rung and
# neither ever runs for the other's codec.
#
# ``-ulane-only`` is the arm's REACHABILITY, spelled: A4b never runs on
# an ordinary, mop-up or refinement level.  PK10's referendum measured it
# an exact null on the uplift target and net −5 addresses on the
# non-regression capture with no statistic separating the two
# (COLOR-UPLIFT-MEASUREMENTS §9), and parked it behind a flag; PK-CLEAN
# retired the flag because a flag is still something to flip, and made
# the supplemental lane the only caller.  Where the arm DOES run its
# region comparison is measured and published but not consulted — the
# verdict is always ``region_gate_forced`` — so the token says
# "u-lane only", never "parked" (it contributes: +1 M on hp c3-cmy8,
# +2 on xerox c2-cmy8, §10).
#
# ctxmatrix-9bin-zeroanchor-floors<S>-<Sc>-<V>-<Vc> (color-uplift P2/PK5,
# §6.2a arm A5): colour finally has a context model.  A per-STATE x
# per-plane isotonic correction is added to the QDA's own state scores —
# cmy7's six W-relative logits after the A4 head and before the L-infinity
# bound, cmy8's eight state scores BEFORE marginalization — with the
# 8-neighbourhood ink count per plane binned by K's nine ordered bins and
# each curve pooled monotone by K's generalized PAVA over K's canonical
# sigmoid block solve.  The curve's DIRECTION is read off the state's own
# plane bit rather than fitted (a state that prints plane k is
# over-evidenced by plane-k neighbours; one that does not is
# under-evidenced by the same bleed), and every curve is ZERO-ANCHORED on
# its own fit population so it carries shape and never the level that
# belongs to A4 and the QDA.  K's CTX_* floors apply PER CURVE, in K's
# refusal vocabulary; a starved or gate-refused curve is exactly zero, and
# a region whose curves all refuse emits the literal pre-P2 arrays.  Two
# gates: each curve on its own held-out one-vs-rest loss, then the
# standing three-way comparison in the space the kind EMITS (per-plane
# binary loss for cmy8, joint multinomial for cmy7), class-balanced.
# The whole segment is GENERATED from ``color_context.ContextConfig``, so
# the variant AND its four floors are what the tree ran; the off state
# names itself the same way (``ctxoff``).  The per-plane K PORT measured
# beside it is RETIRED — an exact null in 0 of 17 lanes on the uplift
# target, because one curve per plane is spent on the 83-84% WORD
# population and the standing gate refuses what that does to the dust leg
# (COLOR-UPLIFT-MEASUREMENTS §11.4, retirement record §12 R7) — so
# ``ctxplanes-3x9-kport`` is a stem no tree can generate any more.  It
# FOLLOWS the conditioning segment: A5 is the last rung of the ladder and
# corrects what A4/A4b leave.
#
# union-lanes-a3-a4b-off-v4-zerofrontier-codingaware (color-uplift PK5
# lead ruling + PK-CLEAN's per-coding filter + the v4 arm split).  THE
# SUPPLEMENTAL-LANE LAW is the whole
# applicability answer for the two arms that could not prove universal
# non-regression: they are not gated and not parked, they are SCHEDULED.
# A colour plan's tail is `[U(Ln, off), U(Ln, a3), U(Ln, a4b)]` after the
# whole l/m/r sequence, bound to the finest ordinary rung.  Each u-lane
# re-runs the payload transaction over its base lane's committed poses
# with ONE arm forced, every per-window and per-stratum pre-gate, every
# other arm, and force-null untouched.  It needs no adoption gate because
# the per-address retirement law (§6.3) suppresses every certified stream
# before the leaf can offer it: a u-lane's reachable set is exactly the
# uncertified residue, so its certificate delta is non-negative BY
# CONSTRUCTION and the zero-wrong-certificate audit is the only bar.
#
# `off` is FIRST and runs the residue with every campaign arm DISABLED —
# the pre-campaign evidence path, scheduled — because adopting an arm in
# the ladder RE-TIMES the cascade: A5 moves 50-130 tiles to an earlier
# barrier, the later barriers then face a different residue and a
# different refinement domain, and measured, six tiles across the whole
# corpus that the old path certified were stranded (against 255 gained).
# That is scheduling damage, repaired by scheduling; the old path's own
# tail is monotone under the same law, and ordering it first lets the old
# configuration complete its reachable set before a forced arm reads what
# is left.
#
# `codingaware` (PK-CLEAN) is the per-coding APPLICABILITY filter: a
# coding with a single payload stream has no certified SIBLING plane, so
# A4b cannot fire at all there, and a cmy7 plan therefore schedules only
# `[U(Ln, off), U(Ln, a3)]`.  Measured: the cmy7 u-a4b lane spent 70 s
# wall / 144 s CPU re-decoding the residue for a guaranteed zero and
# emitted not one `color.conditioning.*` key (§10.7).
#
# `v4-zerofrontier` (external review disposition 2026-08-10, amendment
# RECEIVE-DESIGN §6.2a v0.54) is the PRE-GATE ARM SPLIT.  v3 inherited
# the R leaf's pre-gates verbatim, including "no certificates => stop",
# and that one was wrong for two of the three arms.  Only U(a4b)
# conditions on a certified SIBLING and is therefore vacuous without a
# frontier; U(off) and U(a3) fit from committed FURNITURE and read no
# certificate at all.  So on a capture whose base ladder certified
# NOTHING — the hardest pages, exactly the stranding case U(off) was
# scheduled for — v3 refused the two arms that could have helped and did
# it pixel-free, silently.  v4 requires a frontier for a4b only.  It is
# decode-relevant in the plain sense: the same state, same plan, now
# executes lanes that used to commit an empty barrier.
#
# cmy7-demapiter3 (color-uplift PK8).  The pack7 demapper and the frame
# decoder exchange EXTRINSICS up to three times inside ONE attempt — the
# soft-iteration half of RECEIVE-DESIGN §6.2a's two iteration laws, so it
# is one attempt identity, one retry150 spend, and no soft value crosses
# the call.  The segment sits in the decode-profile tail because that is
# what it changes: the same evidence certifies more tiles, and certifies
# them at a coarser rung (xerox c3-cmy7 771 -> 810, l00 alone 413 -> 500).
# It appears ONLY above the null, so a tree at `DEMAP_ITERATIONS == 1`
# still declares the pre-campaign identity and a byte-exact run cannot
# accidentally claim a new one.  PK9's margin-erasure floor is a MEASURED
# NEGATIVE and stays at its null, so it names nothing here
# (COLOR-UPLIFT-MEASUREMENTS §13; the live-constant pin is
# `test_policy_id_names_the_cmy7_codec_leaf_constants`).
#
# The token is decode-relevant because the PLAN is: a state minted here
# schedules a different lane set than a v8 or v2 state did, and prior
# color states refuse resume as they always have.
COLOR_PAYLOAD_POLICY_ID = (
    "holo/e023b-e023c-color/provisional-v8-r-lane/"
    "rgb-furniture-qda-sparse-split-pava-tiepool-classbal-planezero-"
    "dust20-priorcert-label-rows-"
    "register-rect2-q010-shift5-localcrop-"
    "anchor512-binleft-"
    f"{WindowPhotometryConfig().policy_token}-cmy7linf20-"
    "cmy7cal-temp7-heldout-subsplit-satfloor30-"
    "knownfield-conditioned-marginals-ulane-only-"
    f"{ContextConfig().policy_token}-"
    "union-lanes-a3-a4b-off-v4-zerofrontier-codingaware-"
    "certrefine-planecal-frozen-stripes-xy-furniture-nonregress-"
    "r-lane-audited-committed-pose-domain-affected-region-delta-"
    "nonzero-floor-max60-cmy7-demapiter3-preclose-selective-retry150"
)
