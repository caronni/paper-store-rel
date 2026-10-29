# format

Printed law. The one domain a rewrite is not allowed to invent.

The generator-facing specification — conventions, algebra, procedures,
opaque pins — is [`PRINT.md`](PRINT.md). This note is the *receiver
package* that must not re-derive it.

## What it is

Everything that, once toner hits paper, is immutable: cell pitch and
family, site lattice, BCH words, LDPC mother codes and rungs, slot
permutation, AES-CTR keystream (format id **is** the seed), metadata
LFSR, fountain-v2 quotas and shuffle, envelope, the identity lattice
and the `L:` fossil catalogue.

A receiver that cannot decode what `src/holo` generate emitted has
forked the format. That is the worst bug in the project. The only
legal construction of these objects in a new tree is
**copy-and-strip** from `src/holo` (or from a previous copy that was
already pin-verified against it). Never re-derive from prose.

## What it is not

- The generator itself. Emission, PostScript, printer registries,
  `--paper` bundles stay in `src/holo`. Format here is the *reader's*
  copy of the same law.
- Receive policy. `--complete`, `--plane-fields`, PAVA floors, window
  size are decoder-axis. They do not live in a format id.
- A place to "clean up" a constant that looks ugly. Ugly constants
  that are on paper are fossils.

## Contents

- Identity: `Family` {k, cmy7, cmy8}, pitch as `Fraction` inches (no
  privileged 600-dpi grid), rung, site family, tile matrix. Canonical
  id is the AES seed (`holo/v2/c2-cmy8-r0700@53x37`-style). Fossils
  are byte-matched under `L:`, never parsed.
- Geometry: tile 64×64, 100 word sites (p120 = 100 + 20 dust on
  colour), page field as a 64-multiple.
- Words: BCH(127,50,t=13) shortened (100,23), message = 18-bit counter
  + 5 known-zero pads, d = 27 exact.
- Payload: e-IRA QC-LDPC n=4096, rate ladder, CRC-32 inside info bits,
  one metadata user bit, remainder = fountain symbol.
- Keystream: SHA-256 KDF, AES-128 on a structured 128-bit counter,
  frozen domain table. Site-local scramble of word *values* so Stage A
  is not circular.
- Fountain-v2: per-page exact block quotas + keystream shuffle. Pooled
  CMY8: `esi = counter·n_streams + stream`. Envelope
  `{sha256:32}{len:4 BE}{data}` zero-padded.
- Metadata: degree-24 LFSR, trust at rank 24 **and** ≥48 distinct
  equations.

## Laws

- Bit-exact with the generator, or it is a different format.
- No numpy RNG, no sequential consumption, no dtype-dependent draws.
- Geometry in the *value* seed (wrong `tiles_x` coin-flips every word).
  Site construction is geometry-free (one lattice serves a family).
- Mixing two same-profile different payloads is certificate-conflict
  fatal, not silent. Public seeds are whitening, not encryption.

## Seams

format → lib (BCH/LDPC/AES/GE are the kernels format *uses*; the
matrices, domain table, and site pattern are format *data*).
format → data (`FormatRow` is a frozen input of the run, not a fact
plugins mint).
format → close (the algebra of unwrap + GE; *when* to consult is
engine).
Generate never imports a receiver.

## holo4 stance

Do not rewrite this. Pin it. The identity grammar and the fossil
catalogue are as load-bearing as the BCH polynomial. If a future tree
needs a format change, that is a user-declared layout bump in
`src/holo`, not a receiver convenience.
