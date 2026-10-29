# diag

The observer. It may not change the decode.

## What it is

A pure consumer of two interfaces:

1. The append-only event list (facts already folded, plus accounting
   events the engine emits).
2. The one-slot gauge (`StatBoard` / `EngineStat`): the merge thread
   assigns a freshly built frozen snapshot; the viewer thread reads
   the reference once.

Loopback HTTP, `--diag PORT` only. Panes A capture / B page / C
payload / scheduler+close HTML / pose band / field band. Status rows
are the same formatter as the stderr epilogue and `report.json`.

## What it is not

- A third store. If diag needs a nested dictionary the state would
  have to version, that is an event (PlaneFieldTiers) or it is
  dropped.
- A control surface. No "pause this plugin" button that writes the
  store. Pause is an engine/CLI problem if it exists at all.
- A reason to keep a live object around. Events are values.

## Laws (non-negotiable)

- Byte-identity: viewer on ≡ viewer off for payload, status, exit.
- No diag failure changes the run. One stderr line, then inert.
- Never print zero where the producer has not run. "Unavailable
  before survey" beats `regions 0`.
- Durable facts own fill colours; transient work is stroke. Deep red
  is contradiction only.
- Revision is work-counted (`len(events)`). The server reads no
  clocks; liveness is client-side.
- Geometry in the producer's frame; the renderer applies exactly one
  transform.

## Seams

diag ← engine (events, gauge).
diag ↛ store, ↛ plugins, ↛ close algebra.

`events.jsonl`, `argv`, `report.json`, final frames always land in
the run dir whether or not a port was bound.

## holo4 stance

Keep it detached. The field pane's v1-fidelity fight (half-block
clamp) is the kind of shortcut diag invites: "close enough for a
picture." Pictures are not allowed to lie about support. They are
allowed to exaggerate a quiver so a human can see it, if the legend
says so.
