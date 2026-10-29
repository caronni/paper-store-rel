# lib

Pure functions. No store, no `FactKey`, no plugin name, no run.

## What it is

The numerical kernels a plugin may call without knowing it is in a
decoder: AES-CTR blocks, BCH encode/decode (scalar and batched), LDPC
encode and BP, GF(2) elimination, the isotonic PAVA *solver*, affine
geometry, integer-box area decimation, robust stats, ownership total
order, spectral helpers, local-affine search.

A function here is specified by its types and its goldens. The only
lawful test against `src/holo` that claims bit-identity lives here
(and in format data that those kernels consume).

## What it is not

- Channel *policy*. "PAVA on search-parity labels, refuse below 10 per
  class, clamp `log(n+1)`" is a mechanism. The isotonic fit itself is
  lib.
- Scheduling. `cost()` is not lib.
- Anything that opens a capture, a window, or a certificate.

## Why the cut exists

holo3's charter: format law is copy-and-stripped; scaffolding is
dropped; measured channel knowledge is kept. Lib is the first half of
that. If a kernel is reimplemented from a comment, it will fork. If a
policy constant is baked into a kernel "for convenience," the next
plugin cannot refuse it.

BCH is format law *and* ~72% of placement CPU in holo2's measurement.
Vectorising it is lib work (bit-exact or it is a fork). Putting a
rival-bar constant inside `decode_many` is not.

## Typical inhabitants

| kernel | job | pin |
|---|---|---|
| bch | (127,50,t=13)→(100,23), erasures `2e+f≤26` | spectrum d=27; `decode_many` |
| ldpc | six e-IRA rungs, min-sum then SP retry | `ldpc_data/*.json` byte-identical |
| aes / keystream draws | one block per address | golden vectors per domain |
| pava solver | unweighted isotonic score→P | numeric goldens |
| decimate | integer-box u8, exact-area ppc ladder | E018 order: RGB mean then box |
| geometry | cell-edge affines, 131/17 parity hash | |
| gf2 | dense GE for fountain / metadata | |
| owners | one owner per page cell, total order | |

## Laws

- Deterministic. No unseeded RNG. No clocks.
- Units in names (`pitch_dots`, `cell_px`) even here.
- No import of store, engine, plugins, diag.
- A new kernel earns its place by having two callers, or by being the
  pin of a format object. One plugin's helper stays in the plugin.

## Seams

lib ← format (codes, sites, domains as *data*).
lib → mechanisms and plugins (they compose kernels into channel
behaviour).
lib ↛ engine.

## holo4 stance

Small, boring, pinned. The temptation is to grow lib into "all the
math we like." Resist. Spectral isolation and local-affine search
started as residue-plugin helpers; they become lib only when a second
row needs the same function under the same contract.
