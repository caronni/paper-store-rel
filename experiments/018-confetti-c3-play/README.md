# Experiment 018 — regenerating the job at main

The log `experiments/018-confetti-c3-play.md` is normative. This note covers
one thing: how the published job (`e018.ps`, `e018_manifest.json`, published
in the paperholo-era evidence release under `018-confetti-c3-play/confetti/jobs/`)
is remade from the current tree. Measured 2026-10-22, record
`docs/evidence-archive/REGENERATION-2026-10-22.md` §4.1.

The page's payload is a deterministic tar.gz of eighteen `src/paperholo` CORE
modules as they stood when the page was emitted (sha256 `4c75fe59…`,
103,195 B). `gen_e018.py` tars the *current* source, so the page comes out
byte-identical only from the four trees of 2026-07-10 whose CORE bytes it
was: `eb5174e9`, `56918373`, `e98346df`, `f8de66eb`. From any later tree,
main included, supply the tar instead:

1. Obtain the tar. Three sources agree byte for byte: decode the page (the
   confetti sessions did, §018.0 and §018.3); or check out one of the four
   trees, copy this directory's `gen_e018.py` in, and call its `make_targz()`;
   or keep the file beside this README out of git.
2. At main, run the generator with the tar in place of `make_targz()`:

```text
PYTHONPATH=src:. env/bin/python -c '
import importlib.util, pathlib
s = importlib.util.spec_from_file_location("gen_e018", "experiments/018-confetti-c3-play/gen_e018.py")
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
data = pathlib.Path("build/recovered_e018.tar.gz").read_bytes()
m.make_targz = lambda: data
raise SystemExit(m.main())'
```

`build/e018.ps` (`a691c7d7…`) and `build/e018_manifest.json` (`f8d6d401…`)
are then byte-identical to the published files; this holds at every tree
from `f3b71a6d` (2026-07-08) through main. The manifest records the payload's
hash and file list, not its bytes, so it is exact by either route.

Decoding the printed sheets is `session_decode.py` with `repass.py`, under the
operational rule in the log (1600-dpi decimations, one global `--dpi`, never
raw and decimated together); the published captures are the six Canon 4800
scissors takes.
