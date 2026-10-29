# close

Verified stop. The only consumer of certificates that is allowed to
end the run.

## What it is

The algebra and the *policy* that turn a set of CRC-certified tiles
into a payload or an honest "not yet":

- Each certificate donates one metadata bit (addressed LFSR equation)
  and one fountain symbol (the rest of the user bits).
- Metadata: solve over GF(2), require rank 24 **and** ≥48 distinct
  counters, reserved zeros and K valid. Inconsistency is
  `IntegrityError`, not a vote.
- Fountain: per-block dense GE on certified symbols. Rank complete →
  unwrap `{sha256}{len}{data}` → SHA over `data[0:len]` → canonical-K
  and zero-pad gates. Rank counts are never a stop condition. A wrong
  SHA is fatal.
- Pooled CMY8 is one fountain over `esi = counter·3 + stream`. A dead
  plane is a quota tier, not a second close.

The **algebra** (GE, unwrap, LFSR) is format/lib. The **consult**
(when the engine asks, whether a verified close preempts remaining
work, what `--complete` / `--no-close` mean) is engine. This note
exists so those two are not mashed into a plugin.

## Why close is not a plugin

A plugin is work that might be worth doing. Close is a question asked
of already-committed facts. Queue-ordering it as a dear row defeats
preemption (holo2 measured verified-close as a 3.7× prize vs running
out). Eligibility is an integer compare on certified membership.
Putting it on the heap made it compete with `tiles.local`. It must
not.

## Policy (engine-owned)

| mode | behaviour |
|---|---|
| ordinary | consult at barriers / when count_ready; first verified SHA stops |
| `--complete` | defer the authoritative solve until the requested work is exhausted; still *observe* mid-run |
| `--no-close` | never treat a close as terminal; later commits can join; a close with later facts is superseded |

`--complete` is invocation-local. It does not reopen a terminal state,
change lane work, or enter persisted policy. Highest seen page is a
lower bound on the page domain, never `n_pages`.

## Why the SHA is not "good"

CHARTER §4: fountain close is a counting function of harvest and of
printed K/N. The r0850 soak on `:48023` had 4690/5277 symbols, close
deferred, Y at 1013/1961 — a future SHA would not disclose that.
Certificate harvest is the yield measure. Close is the product stop.
Integrity is a constraint on both.

## Seams

close ← format (VolumeCode, envelope, metadata).
close ← store (the certificate set and the equation table).
close → engine (status, preemption, `RunResult`).
close ↛ plugins (they mint certificates; they do not unwrap).

## holo4 stance

Keep the consult in the engine's main loop, next to done-geometry and
accounting. Keep the algebra in format. Do not add a `close` descriptor
row. Do not let a residue arm "help close" by writing envelope bytes.
