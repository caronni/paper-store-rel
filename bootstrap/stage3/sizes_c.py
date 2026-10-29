"""sizes_c.py -- exact R2 sizes of c.py and of every intermediate form, by the
chain's own coder (bootstrap/typed/cm2_enc.py encode(data, primer, orders),
the function stage1/make_typed.py's r2_payload and stage1/e2e.py's pages()
call), R2 pages = ceil(bytes / 5,304).

Rows: the r0550 text (the record's receiver_arch.py) and the r0547 text
(stage3/c_readable.py, the source of record), each minified-g (pre-pipeline)
and after the pipeline (M1, M2, M3 = c.py for r0547; for r0550 the same
pipeline run here under the same primer, cached in
build/stage3/forms/r0550.c.py), under
  NEW   the stand-in stage-1 build's b.py at (0,1,2,3,4,6,8) (the primer the
        pipeline was scored under);
  CHAIN the chain builds' b.py (build/sheets/stage1/<case>/b.py, the current
        chain build of rebuild_v2.py, c.py as the content, at the tuple each
        build chose), when present;
  OLD   bootstrap/build/loader/r.py at (0,1,2,3,4,6,8,12,16) (the record's
        primer and tuple: reproduces 10,599 and, for the lab's own
        compressor-exploration/encoder-side/mono_final.py, 9,876).
  env/bin/python bootstrap/stage3/sizes_c.py [--workers N]
Writes build/stage3/sizes.json.
"""
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOT = HERE.parent
BUILD = BOOT / "build" / "stage3"
FORMS = BUILD / "forms"
sys.path.insert(0, str(BOOT / "typed"))
import cm2_enc  # noqa: E402

PAGE = 5304
NEW_ORDERS = (0, 1, 2, 3, 4, 6, 8)
OLD_ORDERS = cm2_enc.orders_of(str(BOOT / "typed" / "cm2_dec.py"))
OLD_PRIMER = BOOT / "build" / "loader" / "r.py"
LAB_FINAL = BOOT / "compressor-exploration" / "encoder-side" / "mono_final.py"
RECORD_MING = BOOT / "build" / "r3" / "arch" / "forms_arch" / "receiver_arch.minified-g.py"


def r0550_pipeline():
    """M1-M3 of make_c.py on the r0550 minified-g, the same primer."""
    out = FORMS / "r0550.c.py"
    if out.exists():
        return out
    sys.argv += [] if "--workers" in sys.argv else ["--workers", "6"]
    sys.path.insert(0, str(HERE))
    import make_c as MC
    from concurrent.futures import ThreadPoolExecutor
    src = (FORMS / "r0550.minified-g.py").read_text()
    pb, _ = MC.primer()
    sc, ex = MC.Scorer(pb), ThreadPoolExecutor(MC.WORKERS)
    m1, r1 = MC.m1_inline(src, sc, ex)
    assert MC.m1_equivalent(src, m1, r1["steps"])
    (FORMS / "r0550.m1.py").write_text(m1)
    m2, _ = MC.m2_rename(m1, pb)
    (FORMS / "r0550.m2.py").write_text(m2)
    m3, r3 = MC.m3_attrs(m2, sc, ex)
    MC.rename_equivalent(m1, m3)
    out.write_text(m3)
    (FORMS / "r0550.pipeline.json").write_text(json.dumps(dict(m1=r1, m3=r3), indent=1))
    return out


def enc(job):
    name, text_path, primer_name, primer_path, orders = job
    data, primer = Path(text_path).read_bytes(), Path(primer_path).read_bytes()
    t = time.time()
    n = len(cm2_enc.encode(data, primer, tuple(orders)))
    return dict(form=name, text=str(Path(text_path).relative_to(BOOT)), primer=primer_name,
                primer_path=str(Path(primer_path).relative_to(BOOT)), primer_bytes=len(primer),
                orders=list(orders), bytes=len(data), cm2=n, r2_pages=math.ceil(n / PAGE),
                headroom=math.ceil(n / PAGE) * PAGE - n, spare_on_2=2 * PAGE - n, encode_s=round(time.time() - t, 1))


def main():
    r0550c = r0550_pipeline()
    texts = {"r0550 minified-g": FORMS / "r0550.minified-g.py", "r0550 M1": FORMS / "r0550.m1.py",
             "r0550 pipeline": r0550c,
             "r0547 minified-g": FORMS / "r0547.minified-g.py", "r0547 M1": FORMS / "r0547.m1.py",
             "r0547 M1+M2": FORMS / "r0547.m2.py", "r0547 c.py": HERE / "c.py"}
    primers = {"NEW stand-in lower b.py": (BUILD / "stage1_standin" / "lower" / "b.py", NEW_ORDERS)}
    for case in ("lower", "upper"):
        b = BOOT / "build" / "sheets" / "stage1" / case / "build.json"
        if b.exists():
            primers[f"CHAIN {case} b.py"] = (b.parent / "b.py", tuple(json.loads(b.read_text())["orders"]))
    jobs = [(n, str(p), pn, str(pp), o) for n, p in texts.items() for pn, (pp, o) in primers.items()]
    jobs += [(n, str(texts[n]), "OLD build/loader/r.py", str(OLD_PRIMER), OLD_ORDERS)
             for n in ("r0550 minified-g", "r0547 minified-g", "r0547 c.py")]
    jobs += [("lab mono_final.py (r0550, old-primer pipeline)", str(LAB_FINAL), "OLD build/loader/r.py",
              str(OLD_PRIMER), OLD_ORDERS),
             ("record minified-g (r0550)", str(RECORD_MING), "OLD build/loader/r.py", str(OLD_PRIMER), OLD_ORDERS)]
    w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 6
    with ProcessPoolExecutor(w) as ex:
        rows = list(ex.map(enc, jobs))
    for r in rows:
        print(f"{r['form']:48s} {r['bytes']:6d} B  {r['primer']:26s} {str(tuple(r['orders'])):28s} "
              f"cm2 {r['cm2']:6d}  pages {r['r2_pages']}  spare on 2 {r['spare_on_2']:5d}", flush=True)
    (BUILD / "sizes.json").write_text(json.dumps(dict(page_bytes=PAGE, rows=rows), indent=1) + "\n")


if __name__ == "__main__":
    main()
