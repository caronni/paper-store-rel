#!/usr/bin/env python3
"""Make a separate facts.npz that the pre-page-field analyzer can read.

    env/bin/python util/strip_page_fields.py INPUT.npz -o OUTPUT.npz

Remove PlaneField and EvidenceRevision records from the JSON spine without
importing either receiver version. All other records retain their order and
values. The array table and blob stay intact, including unreferenced field
arrays; this is a compatibility filter, not a storage compactor. The blob is
streamed so filtering does not unpack the snapshot's many gigabytes of arrays.

Use the result with the old analyzer's `union-base --facts OUTPUT.npz` to
borrow the original run's rasters, report and events. Production field hints
will be absent; the analyzer can still estimate its own fields. Keep the
original snapshot for receiver resumes that should retain its page fields.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np


DROP = frozenset({"PlaneField", "EvidenceRevision"})


def strip_snapshot(source_path: Path, output_path: Path) -> dict:
    with zipfile.ZipFile(source_path) as source:
        with source.open("meta.npy") as member:
            meta = np.lib.format.read_array(member, allow_pickle=False)
        spine = json.loads(meta.tobytes())
        removed = Counter(node[1] for node in spine["facts"]
                          if node[0] == "d" and node[1] in DROP)
        spine["facts"] = [node for node in spine["facts"]
                          if not (node[0] == "d" and node[1] in DROP)]
        certificates = sum(node[:2] == ["d", "Certificate"]
                           for node in spine["facts"])
        encoded = io.BytesIO()
        np.lib.format.write_array(
            encoded, np.frombuffer(json.dumps(spine).encode(), np.uint8),
            allow_pickle=False)

        # Exclusive creation also refuses the input itself and existing links.
        output = output_path.open("xb")
        try:
            with output, zipfile.ZipFile(
                    output, "w", compression=zipfile.ZIP_DEFLATED,
                    compresslevel=1) as target:
                target.writestr("meta.npy", encoded.getvalue())
                for member in source.infolist():
                    if member.filename == "meta.npy":
                        continue
                    with source.open(member) as reader, target.open(
                            member.filename, "w", force_zip64=True) as writer:
                        shutil.copyfileobj(reader, writer, length=4 << 20)
        except BaseException:
            output_path.unlink()
            raise

    return {"removed": dict(removed), "kept_facts": len(spine["facts"]),
            "kept_certificates": certificates}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--out", type=Path, required=True,
                        help="new output snapshot; existing files are refused")
    args = parser.parse_args()
    try:
        counts = strip_snapshot(args.source, args.out)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    for name in sorted(DROP):
        print(f"Removed {name}: {counts['removed'].get(name, 0)}")
    print(f"Kept {counts['kept_certificates']} certificates; "
          f"{counts['kept_facts']} facts total")
    print(f"Written: {args.out}")


if __name__ == "__main__":
    main()
