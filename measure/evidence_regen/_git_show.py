"""Write one blob of this checkout's history to a file: ``git show <ref:path> > <out>``.

    <python> measure/evidence_regen/_git_show.py 9df37bf1:experiments/025-channel-metrology/emit_e025.py OUT

A family step that needs a script as it stood at an older commit (the e025 -v1
emitter) materializes it with this, run from any cwd: the repository is the
checkout holding this file.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or ":" not in args[0]:
        print("usage: _git_show.py REF:PATH OUT", file=sys.stderr)
        return 2
    blob = subprocess.run(["git", "-C", str(TOOL), "show", args[0]], check=True, capture_output=True).stdout
    out = Path(args[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
