# Experiment 018b — regenerating the jobs at main

The log `experiments/018b-payload-sheet.md` is normative (contract, profiles,
capacity proof, the fixed public keys and the never-combine rule). This note
covers one thing: how the two published jobs
(`e018b-c2-424e41a28257.ps`, `e018b-c3-012d9e3ae693.ps` and their manifests,
in the paperholo-era evidence release under `018b-payload-sheet/{c2,c3}/jobs/`)
are remade from the current tree. Measured 2026-10-22, record
`docs/evidence-archive/REGENERATION-2026-10-22.md` §4.2.

The payload files (`lena_std-192.heic`, 192,160 B; `lena_std-88.heic`,
88,157 B) are a third-party image, withheld from the archive under the
2026-10-09 D1 ruling and not in any commit. The page carries them. Recover
each payload from its published PostScript in the clean domain, no scan and
no receiver, with `measure/evidence_regen/clean_decode_e018b.py` (K bitmap via
`util/ps_gt`, the compose inverse, per-tile LDPC with exact likelihoods and
the syndrome + CRC-32 gate, fountain decode; `data_len_bytes` from the
manifest), then re-emit:

```text
PYTHONPATH=src:. env/bin/python measure/evidence_regen/clean_decode_e018b.py c2 \
    <release>/018b-payload-sheet/c2/jobs/e018b-c2-424e41a28257.ps \
    <release>/018b-payload-sheet/c2/jobs/e018b-c2-424e41a28257_manifest.json \
    build/lena_std-192.heic
PYTHONPATH=src:. env/bin/python experiments/018b-payload-sheet/gen_e018b.py emit c2 build/lena_std-192.heic
```

and the same with `c3` and `lena_std-88.heic`. The decoder reports the sha256
of the recovered bytes against the manifest's `data_sha256` (c2 `424e41a2…`
in 28 s, c3 `012d9e3a…` in 7 s; every interior tile certifies, the fountain
reaches full rank, and a repair-only re-solve gives the same bytes). The
emission goes to this experiment's ignored `build/` directory under the
content-addressed names, which is what keeps the manifest's `print_command`
repository-relative; `build/e018b-c2-424e41a28257.ps` (`995ef4ab…`),
`…c3-012d9e3ae693.ps` (`f8c948f9…`) and both manifests (`3b2b4813…`,
`d86861cc…`) are then byte-identical to the published files. Name the
recovered file as above so the manifest's `input_name` matches, and keep it
out of git.

Decoding the printed sheets is the E023b / E023c receivers' job, with the
manifest as the out-of-band volume descriptor: the pinned four-case driver
`experiments/023b-integrated-receiver/018b-take-1.sh` and the commands in
`experiments/023c-scale-space-receiver/HOWTO.md`. Never combine two physical
sheets of one profile in one decoder state.
