"""Compute-acceleration measurements for the holo3 receiver.

Two lines, both measurement only — nothing here is imported by holo3:

* ``blas_probe`` / ``op_bench`` — what BLAS numpy and scipy actually link
  on this host, and what the receiver's own linear-algebra shapes cost.
* ``bp_*`` — a batched belief-propagation port to mlx (Apple GPU), gated
  on equivalence, determinism and throughput against the CPU decoder in
  ``holo.receiver.lib.ldpc``.

``shapes.py`` is the census that makes "our real shapes" a measured
statement rather than a guess: it instruments one colour sim decode and
records every call shape the benched kernels actually saw.
"""
