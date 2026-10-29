"""Sizes of receiver_arch.py and receiver_arch_os.py by bootstrap/r3/measure.py's
method (its strip / minify / stdlib_variant / sizes, cm2 v2 primed with
bootstrap/build/loader/r.py, R2 pages = ceil(cm2 / 5,304)), beside
receiver.py's own.  Harness only.
  PYTHONPATH=src env/bin/python bootstrap/r3/arch/measure_arch.py [--no-cm2-decode]
Writes the forms to build/r3/arch/forms_arch/ and build/r3/arch/measure_arch.json.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import measure as M  # noqa: E402

OUT = HERE.parents[1] / "build" / "r3" / "arch"
FORMS = OUT / "forms_arch"


def forms_of(src, stdlib):
    f = {"raw": src, "stripped": M.strip(src), "minified": M.minify(src), "minified-g": M.minify(src, True)}
    if stdlib:
        f["stdlib-minified-g"] = M.minify(M.stdlib_variant(src), True)
    return f


def main():
    FORMS.mkdir(parents=True, exist_ok=True)
    decode = "--no-cm2-decode" not in sys.argv
    files = {"receiver.py": HERE.parent / "receiver.py", "receiver_arch.py": HERE / "receiver_arch.py",
             "receiver_arch_os.py": HERE / "receiver_arch_os.py"}
    rows = []
    for fname, path in files.items():
        src = path.read_text()
        for form, text in forms_of(src, fname != "receiver_arch_os.py").items():
            out = FORMS / ("%s.%s.py" % (fname[:-3], form))
            out.write_text(text)
            compile(text, out.name, "exec")
            r = M.sizes(text.encode(), form, decode=decode and form == "minified-g" and fname != "receiver.py")
            r.update(file=fname, lines=len(text.splitlines()), path=str(out.relative_to(HERE.parents[2])))
            rows.append(r)
            print(f"{fname:20s} {form:18s} {r['lines']:5d} lines {r['bytes']:7d} B  cm2 {r['cm2']:6d}  "
                  f"R2 pages {r['r2_pages_cm2']} (raw {r['r2_pages_raw']})"
                  + (f"  cm2 dec {r['cm2_decode_s']} s ok={r['cm2_roundtrip']}" if "cm2_decode_s" in r else ""),
                  flush=True)
    base = {r["form"]: r["cm2"] for r in rows if r["file"] == "receiver.py"}
    for r in rows:
        r["cm2_over_receiver"] = r["cm2"] - base[r["form"]]
        r["r2_spare"] = r["r2_pages_cm2"] * M.PAGE - r["cm2"]
    (OUT / "measure_arch.json").write_text(json.dumps({"primer": M.PRIMER_NAME, "page_bytes": M.PAGE,
                                                       "rows": rows}, indent=1))
    for r in rows:
        if r["file"] != "receiver.py":
            print(f"{r['file']:20s} {r['form']:18s} +{r['cm2_over_receiver']} cm2 over receiver.py, "
                  f"{r['r2_spare']} B spare on {r['r2_pages_cm2']} R2 pages")


if __name__ == "__main__":
    main()
