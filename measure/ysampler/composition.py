"""The ink-free anchor kernel, composed at RUNTIME from production parts.

**src/holo diff: zero.**  The variant measured here exists only inside
this process, for the duration of one measurement pass, and nothing
outside it observes the substitution.  Standing rule from the project
lead (2026-08-30): *v1 measurement needs are met by runtime composition
inside a harness, never by tree edits.*

WHAT THE VARIANT IS
-------------------
``color_anchoring._fit_registration`` places NCC anchors on cells whose
component value the format already fixes.  Two facts in that path make
the Y word lattice unmeasurable:

* the candidate gate (inline in ``_fit_registration``) demands known
  **INK** at the anchor centre --
  ``known_component_mask & known_component_bits & search``; and
* ``_measure_anchor`` forces ``bits[1, 1] = 1`` / ``weights[1, 1] =
  1.0`` before templating.

``pilots.color_word_states`` renders the v1 colour word as states
{0, 3}, and state 3 is C+M -- so **no word site ever carries Y**.  Every
Y word site is a cell whose value the format knows exactly and which the
sampler refuses purely for its polarity.  The archived PK6/A2 field
corpus states the consequence: 0 Y word anchors on all four captures.

The ink-free variant lifts the polarity requirement in both places and
changes nothing else.  Polarity is not what makes an anchor: the NCC
template is built from the whole 3x3 known/blind block, so a known
ink-free centre in an inked neighbourhood localizes exactly as an inked
centre in a bare one.

HOW IT IS COMPOSED (no kernel copy of the enumeration path)
-----------------------------------------------------------
The candidate gate is INLINE in ``_fit_registration``, so there is no
function to substitute for it.  Instead the *rows* are substituted:
``flip_known_component_bits`` returns a ``_Rows`` whose known component
bits are inverted **at known sites only**.  That inversion retargets the
inline gate onto exactly the ink-free population --
``mask & ~true_bits & search`` -- and is undone inside the one
substituted function, so the template still sees the true field:

* ``_fit_registration`` writes ``detected[mask] = flipped[mask]``;
* the substituted ``_measure_anchor`` restores ``detected[mask] =
  ~detected[mask]`` before reading the 3x3 block.

The inversion is an exact involution over the only two readers of
``known_component_bits`` in the ``_fit_registration`` call tree (the
gate and the prepared field; verified by grep over
``src/holo/receive/``), so selection, dedupe, budget, key order and
``RegistrationAnchors`` construction all remain production's own code.

THE ONE COPIED BODY, AND ITS SEAM
---------------------------------
``_measure_anchor`` is substituted with ``measure_anchor_true_centre``:
production's body with the two forced-centre lines absent and the
un-flip added.  It is the only production body this harness restates.

SEAM (fragile against future refactors, named on purpose):
``measure_anchor_true_centre`` must track ``_measure_anchor``.  Three
guards make drift loud rather than silent:

1. ``assert_kernel_seam`` refuses to run unless production's
   ``_measure_anchor`` body is still statement-for-statement the one
   this variant copied (``ast.unparse`` normalized, docstring dropped --
   a reflow or a comment edit is not a false alarm);
2. ``assert_inline_gate_seam`` refuses unless ``_fit_registration``
   still carries the inline known-ink gate the rows flip retargets and
   the prepared-field write the un-flip cancels; and
3. the IDENTITY CONTROL in ``anchor_supply`` re-runs the composed pass
   with the flip switched off and requires the result to be bit-identical
   to the production return.  A copied body that has drifted from
   production cannot pass that control.

THE PER-PLANE SEARCH RADIUS
---------------------------
Project-lead ruling 2026-08-31: the anchor search radius becomes
PER-PLANE -- Y at +-2.2 dots, C and M untouched -- implemented
harness-side.  ``_ANCHOR_MAX_SHIFT_PX`` is plane-COMMON in production
(§15.6 says so, and says widening it moves C and M too), so the override
is applied by setting that module constant around ONE ``_rectified_ncc``
call and restoring it in ``finally``.  A plane the caller does not name
never enters that branch at all, so its arithmetic is production's own,
unchanged, and byte-identical to a run with no override -- which is what
makes "C/M untouched" a structural property rather than a claim.
``assert_radius_seam`` refuses the override if the radius is no longer
derived from that constant.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import textwrap

import numpy as np

# Everything below is ``ast.unparse`` output, so a cosmetic reflow or a
# docstring edit upstream is not a false alarm -- only a semantic move is.

# The two statements the ink-free variant drops.
FORCED_CENTRE_STATEMENTS = ("bits[1, 1] = 1", "weights[1, 1] = 1.0")

# The whole of ``_measure_anchor``'s body as this variant copied it.  Any
# semantic change upstream trips the guard, not just a change to the two
# forced lines.
PRODUCTION_MEASURE_ANCHOR_STATEMENTS = (
    "local = np.asarray(rows.local_cells_yx, np.int64)",
    "center = local[row_index]",
    "neighbor_indices = rows.neighbor_indices[row_index]",
    "if np.any(neighbor_indices < 0):\n    return None",
    "bits = detected[neighbor_indices, plane].reshape(3, 3).copy()",
    "weights = np.where(confident[neighbor_indices, plane]"
    ".reshape(3, 3), 1.0, 0.05)",
    "bits[1, 1] = 1",
    "weights[1, 1] = 1.0",
    "if bits.min() == bits.max():\n    return None",
    "measured = _rectified_ncc(raster, rows.patch, spec, "
    "(int(center[0]), int(center[1])), bits, weights, plane)",
    "if measured is None or measured[1] < _ANCHOR_MIN_Q:\n    return None",
    "return measured",
)

# Load-bearing expressions of ``_rectified_ncc``: the search radius the
# per-plane override re-sizes, and the cell pitch it is expressed in.
# The override sets ``_ANCHOR_MAX_SHIFT_PX`` for the duration of ONE
# call, so both of these must still be the arithmetic that reads it.
RADIUS_EXPRESSIONS = (
    "max_shift = max(2, round(_ANCHOR_MAX_SHIFT_PX * cell_px / 6.0))",
    "cell_px = _RECTIFIED_PX_PER_DOT * spec.cell_dots",
)

# Load-bearing expressions of ``_fit_registration``: the inline candidate
# gate the rows flip retargets, its search-lattice term, and the prepared
# field write the un-flip cancels.  These three are the entire contract
# the composition depends on inside that function.
INLINE_GATE_EXPRESSIONS = (
    "window.known_component_mask[:, plane] & "
    "window.known_component_bits[:, plane].astype(bool) & search",
    "search = 131 * window.page_cells_yx[:, 0] + "
    "17 * window.page_cells_yx[:, 1] & 1 == 0",
    "detected[window.known_component_mask] = "
    "window.known_component_bits[window.known_component_mask].astype(bool)",
)


class SeamError(RuntimeError):
    """Production moved under the harness; refuse rather than mislead."""


def _source(function) -> str:
    """Source of one production function, or refuse."""
    try:
        return textwrap.dedent(inspect.getsource(function))
    except (OSError, TypeError) as exc:
        raise SeamError(
            f"cannot read the source of {function!r} -- the seam guards "
            "cannot verify a function they cannot read, so this run "
            "refuses rather than report unverified numbers") from exc


def _statements(function) -> tuple[str, ...]:
    """Normalized statement text of one function body, docstring dropped."""
    tree = ast.parse(_source(function))
    body = tree.body[0].body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return tuple(ast.unparse(node) for node in body)


def _expressions(function) -> tuple[str, ...]:
    """Every expression node in one function, normalized."""
    tree = ast.parse(_source(function))
    return tuple(ast.unparse(node) for node in ast.walk(tree))


def assert_kernel_seam(color_anchoring) -> None:
    """``_measure_anchor`` is still the body this variant copied."""
    statements = _statements(color_anchoring._measure_anchor)
    if statements == PRODUCTION_MEASURE_ANCHOR_STATEMENTS:
        return
    lifted = [
        text for text in FORCED_CENTRE_STATEMENTS
        if text not in statements]
    note = (
        "the forced ink centre is GONE upstream "
        f"({lifted}) -- this harness has been superseded"
        if lifted else
        "the forced ink centre is still there; something else moved")
    raise SeamError(
        "color_anchoring._measure_anchor has moved since "
        f"measure/ysampler copied its body: {note}.\n"
        f"  production: {statements}\n"
        f"  composed against: {PRODUCTION_MEASURE_ANCHOR_STATEMENTS}\n"
        "Re-derive measure_anchor_true_centre before trusting any "
        "number.")


def assert_inline_gate_seam(color_anchoring) -> None:
    """``_fit_registration`` still carries the gate the rows flip moves."""
    expressions = _expressions(color_anchoring._fit_registration)
    missing = [
        text for text in INLINE_GATE_EXPRESSIONS
        if text not in expressions]
    if missing:
        raise SeamError(
            "color_anchoring._fit_registration no longer carries "
            f"{missing} -- the rows flip cannot retarget a gate that is "
            "not there, and the un-flip cannot cancel a prepared-field "
            "write that has moved.  Re-derive the composition in "
            "measure/ysampler before trusting any number.")


def assert_radius_seam(color_anchoring) -> None:
    """``_rectified_ncc`` still sizes its search from the module constant."""
    statements = _statements(color_anchoring._rectified_ncc)
    missing = [text for text in RADIUS_EXPRESSIONS if text not in statements]
    if missing:
        raise SeamError(
            "color_anchoring._rectified_ncc no longer carries "
            f"{missing} -- the per-plane search radius is realized by "
            "setting _ANCHOR_MAX_SHIFT_PX around one call, and that "
            "cannot work if the radius is no longer derived from it.  "
            "Re-derive the composition in measure/ysampler before "
            "trusting any number.")


def realized_radius(color_anchoring, cell_dots: int,
                    radius_dots: float) -> tuple[float, float]:
    """The constant that realizes ``radius_dots``, and what it realizes.

    The NCC runs on a fixed ``_RECTIFIED_PX_PER_DOT`` rectification and
    its search radius is a whole number of those pixels, so the radius
    is quantized to 1 / ``_RECTIFIED_PX_PER_DOT`` dots.  A request is a
    LOWER BOUND -- §15.6's "at least ~+-2.2 dots at c2" is itself a
    censored bound -- so the smallest realizable radius that is not
    below the request is the one taken, and the realized value is
    reported rather than the requested one.
    """
    px_per_dot = int(color_anchoring._RECTIFIED_PX_PER_DOT)
    cell_px = px_per_dot * int(cell_dots)
    wanted_px = max(2, int(np.ceil(float(radius_dots) * px_per_dot - 1e-9)))
    return wanted_px * 6.0 / cell_px, wanted_px / px_per_dot


def production_radius_dots(color_anchoring, cell_dots: int) -> float:
    """What the untouched production constant allows at this pitch."""
    px_per_dot = int(color_anchoring._RECTIFIED_PX_PER_DOT)
    cell_px = px_per_dot * int(cell_dots)
    max_shift = max(
        2, round(color_anchoring._ANCHOR_MAX_SHIFT_PX * cell_px / 6.0))
    return max_shift / px_per_dot


def flip_known_component_bits(window):
    """One ``_Rows`` with known component bits inverted at known sites.

    Non-known entries are left exactly as they are; only cells under
    ``known_component_mask`` move, and those are the only cells either
    reader of the array consults.
    """
    bits = np.asarray(window.known_component_bits)
    mask = np.asarray(window.known_component_mask, np.bool_)
    flipped = bits.copy()
    flipped[mask] = np.where(bits[mask] != 0, 0, 1).astype(bits.dtype)
    return dataclasses.replace(window, known_component_bits=flipped)


def _unflipped(detected: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Undo ``flip_known_component_bits`` inside the prepared field."""
    restored = np.asarray(detected).copy()
    known = np.asarray(mask, np.bool_)
    restored[known] = ~restored[known]
    return restored


def make_measure_anchor_true_centre(
    color_anchoring, *, unflip: bool,
    radius_dots_by_plane: dict[int, float] | None = None,
):
    """``_measure_anchor`` without the forced ink centre.

    Production's body verbatim except that the two forced-centre lines
    are absent and, when ``unflip`` is set, the prepared field is
    restored from the flipped rows first.  ``unflip=False`` is the
    IDENTITY CONTROL: on the historical known-INK population the forced
    centre is provably a no-op (``_fit_registration`` has already
    written the known bit into ``detected`` and marked the cell
    confident), so the control must reproduce production bit-for-bit.

    ``radius_dots_by_plane`` is the PER-PLANE SEARCH RADIUS (project-lead
    ruling 2026-08-31: Y at +-2.2 dots, C and M untouched).  A plane that
    is not named keeps production's own expression, unevaluated and
    unrounded, so its measurements are byte-identical to a run without
    this argument -- the override is applied by setting the module
    constant around ONE call and restoring it immediately, which is
    exact and confined (the composed passes are main-thread and serial).
    """
    rectified_ncc = color_anchoring._rectified_ncc
    min_quality = color_anchoring._ANCHOR_MIN_Q
    overrides = dict(radius_dots_by_plane or {})

    def measure_anchor_true_centre(
        raster, rows, row_index, plane, detected, confident, spec,
    ):
        local = np.asarray(rows.local_cells_yx, np.int64)
        center = local[row_index]
        neighbor_indices = rows.neighbor_indices[row_index]
        if np.any(neighbor_indices < 0):
            return None
        field = (
            _unflipped(detected, rows.known_component_mask)
            if unflip else detected)
        bits = field[neighbor_indices, plane].reshape(3, 3).copy()
        weights = np.where(
            confident[neighbor_indices, plane].reshape(3, 3),
            1.0, 0.05)
        # Production forces bits[1, 1] = 1 and weights[1, 1] = 1.0 here.
        # Dropping them is the whole variant.
        if bits.min() == bits.max():
            return None
        if plane in overrides:
            constant, _realized = realized_radius(
                color_anchoring, spec.cell_dots, overrides[plane])
            saved = color_anchoring._ANCHOR_MAX_SHIFT_PX
            color_anchoring._ANCHOR_MAX_SHIFT_PX = constant
            try:
                measured = rectified_ncc(
                    raster, rows.patch, spec,
                    (int(center[0]), int(center[1])), bits, weights, plane)
            finally:
                color_anchoring._ANCHOR_MAX_SHIFT_PX = saved
        else:
            measured = rectified_ncc(
                raster, rows.patch, spec,
                (int(center[0]), int(center[1])), bits, weights, plane)
        if measured is None or measured[1] < min_quality:
            return None
        return measured

    return measure_anchor_true_centre


def composed_anchor_planes(
    real_fit, raster, rows, base_features, spec, *, ink_free: bool,
    radius_dots_by_plane: dict[int, float] | None = None,
):
    """Run one measurement-only ``_fit_registration`` with the variant.

    Returns production's ``RegistrationAnchors`` triple for the composed
    population.  ``fit_plane_residual`` is stubbed for the duration --
    nothing consumes the residual of a measurement pass, and a Theil-Sen
    over these anchor sets is pure cost.  Every substitution is restored
    in ``finally``; the seams are main-thread and serial (the
    ``_color_uplift_harness.regmap`` verification), so nothing outside
    this call observes them.
    """
    from holo.receive import color_anchoring
    from holo.receive.color_registration import PlaneResidual

    assert_kernel_seam(color_anchoring)
    assert_inline_gate_seam(color_anchoring)
    if radius_dots_by_plane:
        assert_radius_seam(color_anchoring)

    used_rows = (
        tuple(flip_known_component_bits(window) for window in rows)
        if ink_free else rows)
    zero_residual = PlaneResidual((0.0, 0.0), (0.0, 0.0), 0)
    saved_measure = color_anchoring._measure_anchor
    saved_residual = color_anchoring.fit_plane_residual
    color_anchoring._measure_anchor = make_measure_anchor_true_centre(
        color_anchoring, unflip=ink_free,
        radius_dots_by_plane=radius_dots_by_plane)
    color_anchoring.fit_plane_residual = (
        lambda y_fraction, offsets, quality: zero_residual)
    try:
        _residuals, anchor_planes = real_fit(
            raster, used_rows, base_features, spec)
    finally:
        color_anchoring._measure_anchor = saved_measure
        color_anchoring.fit_plane_residual = saved_residual
    return anchor_planes


def anchor_planes_identical(left, right) -> bool:
    """Bit-for-bit equality of two ``RegistrationAnchors`` triples."""
    fields = (
        "page", "cell_yx", "window_index",
        "offset_dots_xy", "quality", "bucket",
    )
    for left_plane, right_plane in zip(left, right, strict=True):
        for name in fields:
            a = np.asarray(getattr(left_plane, name))
            b = np.asarray(getattr(right_plane, name))
            if a.shape != b.shape or a.dtype != b.dtype:
                return False
            if not np.array_equal(a, b):
                return False
    return True
