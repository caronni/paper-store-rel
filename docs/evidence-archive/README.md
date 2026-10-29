# docs/evidence-archive — the evidence releases' pointers

The two evidence releases, `paper-store-evidence-paperholo-era` (experiments 001–026) and
`paper-store-evidence-holo-2026-10` (experiments 027–042), are published as torrents with a
plain-HTTPS webseed. How to fetch them and run a first decode is on the front page under
"Try a published scan" and in `docs/HOWTO.md`. This folder carries what a reader of the
releases needs from the repository:

- `TORRENTS.md` — the two torrents' infohashes, sizes, piece counts, the webseed URL, the
  magnets, and the `.torrent` files' hashes.
- `paper-store-evidence-paperholo-era.torrent`, `paper-store-evidence-holo-2026-10.torrent` —
  the torrent files (v1, 16 MiB pieces, webseed only). Open these in the client rather than the
  magnets: a magnet needs a peer to supply the metadata first, and these torrents have no tracker.
- `REGENERATION-2026-10-22.md` — the measurement record of which trees regenerate which
  published jobs byte-identically, and how. Re-running its sweep needs the private history and
  the archive's hash table, neither of which is in this repository.
- `LICENSE` — the MIT text of the releases, the same as the repository's.

The archive's build record (the inventory it was cut from, the hashes taken before packing,
the redaction boxes, the local-path twins of the manifests, the plan of the line) is private
working papers and is not in this repository.
