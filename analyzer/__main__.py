"""`python -m analyzer …` — see `analyzer.cli`.

BLAS IS SINGLE-THREADED PER WORKER (W8 B1, APPROACHES §4.0 ruling 12).
numpy here is Apple's Accelerate; the analyzer's parallelism is its own
`ThreadPoolExecutor` of `--workers` threads, and a BLAS that fans every
solve out over the machine's cores under fourteen workers oversubscribes
it and makes a repeat of one solve depend on scheduling.  The three
environment names are pinned to ``1`` BEFORE the first numpy import,
and only when the operator has not set them.
"""

import os

for _name in ("VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS",
              "OMP_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

from .cli import main  # noqa: E402  (after the pin, on purpose)

if __name__ == "__main__":
    raise SystemExit(main())
