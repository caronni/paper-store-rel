# mechanisms

Channel-shaped numerics. Not printed, not scheduled, not optional
taste.

## What it is

The measured decoder-axis behaviour that plugins compose and that a
format-ignorant kernel cannot know:

- structure-tensor survey, log-Otsu, 5-of-9 density, 9 mm² floor,
  one platen pitch vote, fine silence cannot erase coarse support
- Stage-A word search: site-local descramble, t=13, five zero pads,
  legal page, lazy multi-slot, whole-word decoy bar at d=27
- complete-domain identifiability floors
  `n_r = max(30, ceil(log2 H / (1−h₂(p_max))))`
- weighted mismatch family, search/held-out disjoint, 200-cell windows
  with 40-cell overlap
- pava-v1 / ctx-pava-v1: search-parity labels, held-out adoption,
  bounded LLR (`log(n+1)`, ctx clamp 12), calibrate-or-refuse
- colour QDA, dust PAVA, cmy7 head, demapiter3, 3×9 per-plane context
- one-owner freeze (from observed mask, not from LLR==0)
- bounded-LLR invariant: raw detector scores never cross an API
  boundary (018.7)
- never-sum-same-capture; one SHA = one physical source
- W5 whole-word rival bar; R5 lattice-seed reduction

These are the "measured channel knowledge" holo3 kept when it deleted
scaffolding.

## What it is not

- Lib. The PAVA solver has no opinion about search-parity. The
  mechanism does.
- A plugin. A plugin *runs* a mechanism on a subject. The mechanism
  is the function-plus-constants; the plugin is the row that is
  allowed to fire it.
- Format. Window size 200 is decoder-axis. Changing it does not bump
  a layout version. It does bump a policy identity, and old states
  must refuse rather than silently mean something else.

## Why the cut exists

If mechanisms live in plugins, every residue arm reimplements ctx or
quietly shifts a clamp. If they live in lib, goldens start pinning
policy and a format-kernel test fails because someone changed
`CAL_MIN_PER_CLASS`. The middle shelf is the one collaborators
actually edit when the channel teaches something (ctx gain is
sampling-dependent: ~3.5× at 16 px/cell, ~nil at 8).

## Laws

- Held-out gates. A fit that cannot beat its incumbent on labels it
  did not train on is a bit-exact null, not an identity transform.
- Labels come from format-predictable furniture and from
  already-committed certificates. A candidate placement never labels
  itself.
- Constants carry provenance (experiment, PK packet, or "historical
  E022, provisional"). A bare `0.20` in a plugin is a mechanism that
  escaped.
- JPEG 16-context misfire, mixed grey/colour y-scale, raw+decimated
  of one SHA: these are mechanism laws, not folklore.

## Seams

mechanisms ← lib, format (furniture, codes).
mechanisms → plugins (the rows that invoke them).
intake shares a border (decimation order, luma laws) — see
[intake](intake.md). Keep the *order* here or there, not both.

## holo4 stance

Name the mechanism once. Plugins import it. Residue arms that need a
new constant add a named config object with a policy token, or they
are not a mechanism yet. Do not let `tiles.local` grow a private ctx.
