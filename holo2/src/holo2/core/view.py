"""``SolveView`` — what a worker may see (R1, DESIGN §7 / PROVIDERS P3).

Before R1 a worker held the whole ``SessionContext``: the store, the
commit engine, the derived indexes, and the blob sidecar's append path.
Three of those four are authority, and the fourth is a cache whose shape
is the engine's business. This protocol is the narrow half — the
**read-only** half — and it is the only thing a provider or a worker is
handed.

What it grants:

* **facts** — one record at one key, and the version of any key (which
  for a collection is its membership count, the cheap frontier digest a
  close consult reads before it materialises anything);
* **bulk values** — read-only array reads through content-addressed
  refs; a worker never appends, it stages (``WorkResult.blobs``);
* **frontier queries** — the typed membership questions that used to be
  index attribute reads: the open and certified work keys, the evidence
  standing on a work key, the poses committed for a window, the subjects
  a provider minted.

What it withholds, deliberately: the store, the commit engine, the
resource table, the index objects, ``put_array``/``put_blob``,
``apply``, the session lifecycle, and any clock. A worker that cannot
reach them cannot mutate state during the concurrent phase, which is the
property §10.1 rests on and used to get by convention.

The **physical plane** — format row, regions, footings, window plans,
rasters — is not here: core knows no printed format and no pixels. The
solve package extends this protocol with exactly those reads
(``holo2.solve.PlaneView``), and the engine's concrete view satisfies
both. R3 moved ``tile()`` across that line for the same reason: a
``TileRecord`` is solve's record, so reading one typed is solve's query
(``PlaneView.tile``). What stays here is key-shaped and record-blind —
the open and certified frontiers, the evidence standing on a work key,
the poses of a window — which core can answer without knowing what any of
those records contain.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from .keys import Record, ResourceKey
from .records import BlobRef, SubjectSpec


@runtime_checkable
class SolveView(Protocol):
    """The DURABLE-FACT plane, read-only — never the printed page plane.

    ``solve.PlaneView`` extends this with the physical one (format row,
    regions, footings, rasters); this one knows nothing about paper.
    """

    def record(self, key: ResourceKey) -> Record | None:
        """The durable record at ``key``, or None."""

    def version(self, key: ResourceKey) -> int:
        """The version the scheduler currently holds for ``key``.

        For a collection key this is its membership count — the derived
        digest that lets an expensive consult decide in integer time
        whether its input moved at all (M11).
        """

    def read_array(self, ref: BlobRef) -> np.ndarray:
        """A read-only numpy view of a committed bulk value."""

    def open_work_keys(self) -> tuple[ResourceKey, ...]:
        """Work keys that are addressed or attempted and not yet certified."""

    def certified_work_keys(self) -> tuple[ResourceKey, ...]:
        """The certified frontier, sorted."""

    def evidence_on(self, key: ResourceKey) -> tuple[ResourceKey, ...]:
        """The observation pieces standing on one work key, sorted."""

    def poses_of_window(self,
                        window_id: ResourceKey) -> tuple[ResourceKey, ...]:
        """The poses committed for one window, sorted."""

    def subjects(self, family: str) -> tuple[SubjectSpec, ...]:
        """The subjects a provider minted for one family (M3), sorted."""


__all__ = ["SolveView"]
