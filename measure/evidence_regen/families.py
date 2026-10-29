"""The family table: which tree, which command, which archived files it must re-make.

A family is run in a detached worktree of ``commit`` (``patch`` applied if
given), its ``steps`` executed in order with the worktree as cwd and
``PYTHONPATH=<wt>/src:<wt>``.  Placeholders in a step: ``{py}`` the repo's
interpreter, ``{wt}`` the worktree, ``{out}`` the family's fresh output dir,
``{root}`` the archive root (read-only inputs), ``{tool}`` this checkout (tools
that exist only on main: the fossil emitter, the duplex splice),
``{out:<family>}`` another family's output dir (run first).  Three built-ins:
``("@counting", n_bytes, path)`` writes ``bytes(i & 255 for i in range(n))``,
``("@copy", src, dst)`` and ``("@mkdir", dir, ...)``.

``compare`` pairs a produced dir (relative to ``{out}``, or ``wt:`` relative to
the worktree) with an archived dir (relative to the root); ``expect`` names the
archived files (globs, relative to the archived dir) the family must re-make.
A family with ``commit=None`` is recorded with its ``reason`` and never run.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Step = tuple[str, ...]


@dataclass(frozen=True)
class Compare:
    produced: str
    archived: str
    expect: tuple[str, ...]


@dataclass(frozen=True)
class Family:
    id: str
    title: str
    commit: str | None
    steps: tuple[Step, ...] = ()
    compare: tuple[Compare, ...] = ()
    patch: str | None = None
    needs: tuple[str, ...] = ()
    tag: str | None = None          # evidence/<tag>-<yyyymmdd>@<sha8>
    reason: str = ""                # not-regenerable: why; otherwise a note
    allow_fail: bool = False        # a failing step still lets the outputs be compared
    expect_fail: tuple[str, ...] = field(default=())   # outputs known not to be makeable here
    out_in_worktree: str = ""       # tool records repo-relative paths: run {out} at this path inside the worktree
    notes: tuple[tuple[str, str], ...] = ()   # (archived-name glob, note) attached to a 'differs' verdict


GEN = ("{py}", "confetti.py", "generate")
VOLUME = ("page000.ps", "page000_gt.npy", "manifest.json")


def _volume(dirs: tuple[str, ...], extra: tuple[str, ...] = ("payload-counting.bin",)) -> tuple[str, ...]:
    return tuple(f"{d}/{name}" for d in dirs for name in VOLUME + extra)


# ---------------------------------------------------------------- holo v1 rows
E029 = "scratch/e028/holo-c2-r0700-q07-ink-counting"
E030 = {  # dir: (coding, payload bytes, payload file name)
    "holo-c2-cmy8-q05-counting": ("c2-cmy8-p120-v0", 718413, "payload-counting.bin"),
    "holo-c3-cmy8-q05-counting": ("c3-cmy8-p120-v0", 314579, "payload-c3-counting.bin"),
    "holo-c2-cmy7-q05-counting": ("c2-cmy7-p120-v0", 686859, "payload-counting.bin"),
    "holo-c3-cmy7-q05-counting": ("c3-cmy7-p120-v0", 301600, "payload-counting.bin"),
}
E033_ROOT = "scratch/xerox-v1-20260818"
E033_DIRS = ("A-c4-r0550-q030-6mm", "A2-c3-r0550-q030-6mm", "B-c2-r0700-q070-4mm",
             "C-c2-r0700-q090-4mm", "D-c2-cmy8v1-q050-4mm", "E-c2-cmy8v1-q090-4mm",
             "F-c3-cmy8v1-q090-4mm", "G-c3-r0550-q090-4mm", "H-c2-cmy8r0850-q090-4mm",
             "I-c2-cmy8r0700-q090-4mm")
E033_SCRIPT = "experiments/033-xerox-rung-experiments/generate_set.py"
# main's catalog route: the PS depends on the cells only, so a printer row with
# the same field substitutes for the 4 mm AltaLink row main does not carry.
E033_MAIN_CLI = {  # dir: (coding, printer, q, payload bytes = tracked set.json)
    "A2-c3-r0550-q030-6mm": ("c3-r0550", "xerox-altalink-c8245", "0.3", 62120),
    "B-c2-r0700-q070-4mm": ("c2-r0700", "hp-m281-ink", "0.7", 465580),
    "C-c2-r0700-q090-4mm": ("c2-r0700", "hp-m281-ink", "0.9", 600183),
    "D-c2-cmy8v1-q050-4mm": ("c2-cmy8-p120-v1", "hp-m281-ink", "0.5", 763023),
    "E-c2-cmy8v1-q090-4mm": ("c2-cmy8-p120-v1", "hp-m281-ink", "0.9", 1376601),
    "F-c3-cmy8v1-q090-4mm": ("c3-cmy8-p120-v1", "xerox-altalink-c8245", "0.9", 586932),
    "G-c3-r0550-q090-4mm": ("c3-r0550", "xerox-altalink-c8245", "0.9", 194861),
}
E033_MAIN_FOSSIL = {  # dir: (fossil ref, q, printer id recorded in the manifest)
    "A-c4-r0550-q030-6mm": ("L:c4-r0550@1664x1152", "0.3", "xerox-altalink-c8245"),
    "H-c2-cmy8r0850-q090-4mm": ("L:c2-cmy8-r0850-p120-x1@3392x2368", "0.9", "xerox-altalink-c8245-ink"),
    "I-c2-cmy8r0700-q090-4mm": ("L:c2-cmy8-r0700-p120-x1@3392x2368", "0.9", "xerox-altalink-c8245-ink"),
}
SHEET_J = "scratch/c2-cmy8-r0547-q06860-1MiB"

# ------------------------------------------------------------------ e018 / e018b / fullpage
X18 = "experiments/018-confetti-c3-play"
# import a script by path (sys.argv[1]) as module m, then run the rest of the -c text
LOAD_BY_PATH = ("import importlib.util, pathlib, sys;"
                "s = importlib.util.spec_from_file_location('gen_e018', sys.argv[1]);"
                "m = importlib.util.module_from_spec(s); s.loader.exec_module(m);")
E018_TAR = LOAD_BY_PATH + "pathlib.Path(sys.argv[2]).write_bytes(m.make_targz())"
E018_PAGE = (LOAD_BY_PATH + "data = pathlib.Path(sys.argv[2]).read_bytes(); m.make_targz = lambda: data;"
             "raise SystemExit(m.main())")
X18B = "experiments/018b-payload-sheet"
E018B = {  # profile: (published job stem, recovered payload name = the manifest's input_name)
    "c2": ("e018b-c2-424e41a28257", "lena_std-192.heic"),
    "c3": ("e018b-c3-012d9e3ae693", "lena_std-88.heic"),
}
FULLPAGE = ("fullpage-bw-kcell-c2", "fullpage-color-a3-7st-c3")
X25 = "experiments/025-channel-metrology"

# ------------------------------------------------------------------ e039
E039 = "scratch/versalink-20260916"
E039_K = ("A-c4-k-r0700-at-26x18", "B-c3-k-r0700-at-35x24", "C-c2-k-r0700-at-53x37",
          "D-c2-k-r0850-at-53x37", "E-c1-k-r0700-at-106x74")
E039_CMY = {  # sheet dir stem: sent PDF stem (G's lost its "-at-53x37")
    "F-c3-cmy8-r0700-at-35x24": "F-c3-cmy8-r0700-at-35x24",
    "G-c2-cmy8-r0700-at-53x37": "G-c2-cmy8-r0700",
    "H-c2-cmy8-r0775-at-53x37": "H-c2-cmy8-r0775-at-53x37",
    "I-c2-cmy8-r0850-at-53x37": "I-c2-cmy8-r0850-at-53x37",
    "J-c1-cmy8-r0700-at-106x74": "J-c1-cmy8-r0700-at-106x74",
}
DISC_BW = "discovery/hcal-discovery-bw-copy0000-default-f3c9e5f807ca05bf.ps"
DISC_COL = "discovery/hcal-discovery-color-copy0000-default-6995a5d0b5b0218d.ps"
X39 = "experiments/039-xerox-versalink"
PROBES = (  # tag, variant title, extra flags
    ("high-auto", "quality HIGH, optimize AUTO", ()),
    ("normal-auto", "quality NORMAL, optimize AUTO", ("--pwg",)),
    ("normal-auto-ht1x1", "quality NORMAL, optimize AUTO", ("--ht1x1",)),
    ("normal-graphics", "quality NORMAL, optimize GRAPHICS", ()),
    ("normal-text", "quality NORMAL, optimize TEXT", ()),
)
DEVCMYK32 = ("import sys; sys.path.insert(0, 'experiments/039-xerox-versalink');"
             "from pathlib import Path; import cmyk_pdf, urf_raster;"
             "p = cmyk_pdf.place_planes(cmyk_pdf.render_cmyk(Path(sys.argv[1])), 'legal');"
             "Path(sys.argv[2]).write_bytes(urf_raster.urf_cmyk_file(p, 4))")

# ------------------------------------------------------------------ e041 / e042
X41 = "experiments/041-m281-screen-routes"
E041 = "scratch/m281-routes-20261004"
E041_JOBS = (
    "S1-pjl-bpp1.ps", "S2-sethalftone-type3.ps", "S2b-sethalftone-type1.ps", "S2-banded-halftone.ps",
    "S3-pcl-cmy3.pcl", "S3b-pcl-kcmy4.pcl", "S3c-pcl-cid-cmy.pcl", "S4-pwg-cmyk8.pwg", "S4-pwg-cmyk8.pjl",
    "S5-alphabet.ps", "S6-maxescape.ps", "S7a-media-heavy.ps", "S7b-media-cardstock.ps", "S8-rot180.ps",
    "S9-pclxl-bilevel.pclxl", "S9b-pclxl-dither1x1.pclxl", "S10p-pclxl-rgb-probe.pclxl",
    "S10p2-pclxl-rgb-probe.pclxl", "S10p2M-pclxl-rgb-probe-M.pclxl", "S11-pclxl-mixture.pclxl",
    "S11-pclxl-mixture-patterns.npz", "S12-ps-mixture.ps", "S14-ps-scale.ps", "S14-ps-scale-bands.npz",
    "S15-ps-reset.ps", "S15-ps-reset-bands.npz", "S16-ps-trigger.ps", "S16-ps-trigger-bands.npz",
    "S17-ps-layouts.ps", "S17-ps-layouts-bands.npz", "S1dash-notriple.ps", "S1dash-notriple-alldust.ps",
    "S1dash-notriple-gt/page000_gt.npy", "S1dash-notriple-alldust-gt/page000_gt.npy",
    "S5-alphabet-gt/page000_gt.npy")
F_REGEN = "{out:e033-original}/F-c3-cmy8v1-q090-4mm"
C3CMY7_REGEN = "{out:e030}/holo-c3-cmy7-q05-counting"


def _x41(script: str, *args: str) -> Step:
    return ("{py}", f"{X41}/{script}", *args)


# ------------------------------------------------------------------ paperholo
OFFICE = "scratch/office-2026-07-08"      # the 2026-07-08 office bundle: copies of build files


def _ph(exp: str, script: str, expect: tuple[str, ...], office: tuple[str, ...] = ()) -> tuple[Step, tuple[Compare, ...]]:
    build = f"experiments/{exp}/build"
    return (("{py}", f"experiments/{exp}/{script}"),
            (Compare(f"wt:{build}", build, expect),) + ((Compare(f"wt:{build}", OFFICE, office),) if office else ()))


PAPERHOLO = (
    _ph("001-engine-characterization", "gen_gridtest.py", ("gridtest.ps", "gridtest_manifest.json", "gridtest_gt/*")),
    _ph("001-engine-characterization", "gen_linetest.py", ("linetest.ps", "linetest_manifest.json", "linetest_gt/*")),
    _ph("001-engine-characterization", "generate_patterns.py", ("001_patterns.ps", "manifest.json", "ground_truth/*")),
    _ph("002-calibration-page", "gen_calpage.py", ("calpage.ps", "calpage_manifest.json", "calpage_gt/*")),
    _ph("002-calibration-page", "gen_composite_probe.py",
        ("composite_probe.ps", "composite_probe_manifest.json", "composite_probe_gt/*")),
    _ph("002-calibration-page", "gen_overlap2.py", ("overlap2.ps", "overlap2_manifest.json", "overlap2_gt/*")),
    _ph("003-modulation-probes", "gen_modprobe.py", ("modprobe.ps", "modprobe_manifest.json", "modprobe_gt/*")),
    _ph("004-finalists-checkerboard", "gen_e004.py", ("e004.ps", "e004_manifest.json", "e004_gt/*"), ("e004.ps",)),
    _ph("006-loop-pages", "gen_e006.py", ("e006bw.ps", "e006c.ps", "e006bw_manifest.json",
                                          "e006c_manifest.json", "e006_gt/*"), ("e006bw.ps", "e006c.ps")),
    _ph("007-office-disc", "gen_disc1.py", ("disc1.ps", "disc1_manifest.json", "disc1_gt/*")),
    _ph("008-mode-select", "gen_msel1.py", ("msel1.ps", "msel1_manifest.json", "msel1_gt/*")),
    _ph("009-office-resolution", "gen_ores.py", ("ores_*.pcl", "ores_*.job", "ores_*.pjl", "ores_bitmap_*.npy",
                                                 "ores_manifest.json", "ores_gt/*")),
    _ph("010-motif-b2", "gen_motif1.py", ("motif1.ps", "motif1_manifest.json", "motif1_gt/*")),
    _ph("011-pilot-roundtrip", "gen_e011.py", ("e011.ps", "e011_manifest.json", "e011_gt/*")),
    _ph("012-pilot-print", "gen_e012.py", ("e012.ps", "e012_manifest.json", "e012_gt/*"), ("e012.ps",)),
    _ph("014-c2-print", "gen_e014.py", ("e014.ps", "e014_manifest.json", "e014_gt/*"), ("e014.ps",)),
    _ph("016-arch3-c2-volume", "gen_e016.py", ("e016.ps", "e016_manifest.json", "e016_gt/*")),
    _ph("017-color-channel", "gen_e017.py", ("e017.ps", "e017_manifest.json", "e017_gt/*")),
    _ph("pilot-lattice-viz", "pilot_viz.py", ("pilot_viz.ps",)),
)


def _paperholo_families() -> tuple[Family, ...]:
    out = []
    for step, cmps in PAPERHOLO:
        script = step[1].rsplit("/", 1)[1].removesuffix(".py")
        exp = step[1].split("/")[1]
        out.append(Family(f"paperholo-{script}", f"paperholo {exp} {script}", "main",
                          (("@mkdir", f"{{wt}}/experiments/{exp}/build"), step), cmps, tag="main-regen"))
    return tuple(out)


FAMILIES: tuple[Family, ...] = (
    Family("e029", "e028/e029 holo-v1 K ink page c2-r0700@3392x2368 q0.7", "main", (
        ("@counting", "465580", "{out}/payload-counting.bin"),
        (*GEN, "{out}/payload-counting.bin", "--coding", "c2-r0700", "--printer", "hp-m281-ink",
         "--source-fraction", "0.7", "-o", "{out}/v"),
        ("@copy", "{out}/payload-counting.bin", "{out}/v/payload-counting.bin"),
    ), (Compare("v", E029, VOLUME + ("payload-counting.bin",)),), tag="main-regen"),

    Family("e030", "e030 holo-v1 colour -v0 pages, hp-m281 6 mm, q0.5", "main", tuple(
        s for d, (coding, n, pay) in E030.items() for s in (
            ("@counting", str(n), f"{{out}}/{d}.bin"),
            (*GEN, f"{{out}}/{d}.bin", "--coding", coding, "--printer", "hp-m281",
             "--source-fraction", "0.5", "-o", f"{{out}}/{d}"),
            ("@copy", f"{{out}}/{d}.bin", f"{{out}}/{d}/{pay}"))
    ), (Compare(".", "scratch/e030", tuple(f"{d}/{n}" for d, (_, _, pay) in E030.items()
                                           for n in VOLUME + (pay,))),), tag="main-regen"),

    Family("e033-original", "e033 AltaLink set A-I, the emitting tree (c4 row, 4 mm row, x1 rungs)",
           "bcd352c1", (
               ("@copy", "{tool}/" + E033_SCRIPT, "{wt}/" + E033_SCRIPT),
               ("{py}", E033_SCRIPT, "--out", "{out}"),
           ), (Compare(".", E033_ROOT, _volume(E033_DIRS)),), tag="e033-original",
           reason="bcd352c1 is the 2026-08-18 emitting commit (kept by tag preserve/e033-rung-rows-bcd352c); "
                  "generate_set.py is main's tracked copy of the scratch script, same body"),

    Family("e033-patch", "e033 AltaLink set via f1bc0d0f + c4-row-and-xerox-4mm.patch (the parked route)",
           "f1bc0d0f", (
               ("@copy", "{tool}/" + E033_SCRIPT, "{wt}/" + E033_SCRIPT),
               ("{py}", E033_SCRIPT, "--out", "{out}"),
           ), (Compare(".", E033_ROOT, _volume(E033_DIRS)),), patch="c4-row-and-xerox-4mm.patch",
           tag="e033-patch-base", allow_fail=True,
           expect_fail=tuple(f"{d}/" for d in E033_DIRS[8:]),
           reason="f1bc0d0f has dec3cb52's src/holo; the patch carries the c4 and 4 mm rows, not the x1 rungs, "
                  "so H and I are expected to fail"),

    Family("e033-main", "e033 AltaLink set at main: catalog codings via a same-field printer row, A/H/I via the "
           "python fossil route", "main", tuple(
               s for d, (coding, printer, q, n) in E033_MAIN_CLI.items() for s in (
                   ("@counting", str(n), f"{{out}}/{d}.bin"),
                   (*GEN, f"{{out}}/{d}.bin", "--coding", coding, "--printer", printer,
                    "--source-fraction", q, "-o", f"{{out}}/{d}")))
           + tuple(("{py}", "{tool}/measure/evidence_regen/_emit_fossil.py", ref, q, f"{{out}}/{d}", printer)
                   for d, (ref, q, printer) in E033_MAIN_FOSSIL.items()),
           (Compare(".", E033_ROOT, _volume(E033_DIRS, ())),), tag="main-regen",
           reason="manifest.json is expected to differ where the printer row is substituted "
                  "(printer_id, margin_mm); the PS and GT depend on the cells only"),

    Family("sheet-j", "e035 sheet J c2-cmy8-r0547@53x37 duplex, 1 MiB counting, q 0.686", "8260257d", (
        ("@counting", "1048576", "{out}/payload-counting.bin"),
        (*GEN, "{out}/payload-counting.bin", "--format", "c2-cmy8-r0547@53x37", "--paper", "A4-4mm",
         "--source-fraction", "0.686", "-o", "{out}/volume"),
        ("{py}", "{tool}/experiments/035-sheet-j-confetti/make_duplex.py", "{out}/volume/page000.ps",
         "{out}/volume/page001.ps", "-o", "{out}/volume/duplex.ps"),
    ), (Compare(".", SHEET_J, ("volume/page00[01].ps", "volume/page00[01]_gt.npy", "volume/manifest.json",
                               "volume/duplex.ps", "payload-counting.bin")),),
        tag="sheet-j-generation",
        reason="8260257d = last main before the re-key merge b8471fc0; the duplex splice is main's "
               "experiments/035-sheet-j-confetti/make_duplex.py"),

    Family("e039-set", "e039 VersaLink candidate set A-J + default discovery pair + the aggregate job", "main", (
        ("{py}", f"{X39}/generate_set.py", "--out", "{out}"),
        ("{py}", "confetti.py", "discover", "emit", "{out}/discovery", "--request", "default", "--kind", "both"),
        ("{py}", f"{X39}/coalesce_ps.py", "--root", "{out}", "-o", "{out}/e039-all-pages.ps"),
    ), (Compare(".", E039, ("[A-J]-*/page000.ps", "[A-J]-*/page000_gt.npy", "[A-J]-*/manifest.json",
                            "[A-J]-*/payload-counting.bin", "SET.json", "discovery/*", "e039-all-pages.ps")),
        Compare("discovery", "scratch/e028/discovery-m281-0804-r1", ("*",))), tag="main-regen",
        out_in_worktree=E039, reason="generate_set.py records repo-relative paths in SET.json, so {out} is "
                                     "the throwaway worktree's own scratch/versalink-20260916, copied out after"),

    Family("hcal-1200x2400", "HCAL discovery pair, 1200x2400 request", "main", (
        ("{py}", "confetti.py", "discover", "emit", "{out}/d", "--request", "1200x2400", "--kind", "both"),
    ), (Compare("d", f"{E039}/discovery-request-1200x2400", ("*",)),), tag="main-regen"),

    Family("e039-ipp", "e039 IPP renders (URF W8, CMYK PDFs, PWG, stencils, probes, sRGB chart)", "main", (
        ("@mkdir", "{out}/urf", "{out}/probe"),
        *(("{py}", f"{X39}/urf_raster.py", f"{{out:e039-set}}/{k}-q080-A4-4mm/page000.ps",
           f"{{out}}/urf/{k}-on-legal-uncut-w8.urf", "--media", "legal") for k in E039_K),
        *(("{py}", f"{X39}/cmyk_pdf.py", f"{{out:e039-set}}/{k}-q080-A4-4mm/page000.ps",
           f"{{out}}/urf/{v}-on-legal-uncut-cmyk.pdf", "--media", "legal")
          + (("--preview", "{out}/urf/G-preview-quarter.png") if k.startswith("G-") else ())
          for k, v in E039_CMY.items()),
        ("{py}", f"{X39}/urf_raster.py", "{out:e039-set}/" + DISC_BW,
         "{out}/urf/hcal-discovery-bw-K-on-legal-uncut-w8.urf", "--media", "legal"),
        ("{py}", f"{X39}/pdf_bilevel.py", "{out:e039-set}/" + DISC_BW,
         "{out}/urf/hcal-discovery-bw-K-on-legal-uncut-bilevel.pdf", "--media", "legal"),
        ("{py}", f"{X39}/cmyk_pdf.py", "{out:e039-set}/" + DISC_COL,
         "{out}/urf/hcal-discovery-color-on-legal-uncut-cmyk.pdf", "--media", "legal",
         "--preview", "{out}/urf/hcal-discovery-color-preview-quarter.png"),
        ("{py}", f"{X39}/pwg_raster.py", "{out:e039-set}/" + DISC_COL,
         "{out}/urf/hcal-discovery-color-on-legal-uncut-cmyk8.pwg", "--media", "legal", "--type", "cmyk_8"),
        ("{py}", "-c", DEVCMYK32, "{out:e039-set}/" + DISC_COL,
         "{out}/urf/hcal-discovery-color-on-legal-uncut-devcmyk32.urf"),
        *(("{py}", f"{X39}/stencil_pdf.py", "{out:e039-set}/" + DISC_COL,
           f"{{out}}/urf/hcal-discovery-color-on-legal-uncut-stencil-{s}.pdf", "--media", "legal", "--space", s)
          for s in ("devicecmyk", "separation")),
        *(("{py}", f"{X39}/probe_page.py", "{out}/probe", "--variant", var, "--tag", tag, *flags)
          for tag, var, flags in PROBES),
        ("{py}", f"{X39}/srgb_chart.py", "{out}/probe/srgb-chart-normal.urf", "--variant", "quality NORMAL",
         "--preview", "{out}/probe/srgb-chart-normal-preview.png"),
    ), (Compare("urf", f"{E039}/urf", ("*-w8.urf", "*-cmyk.pdf", "*-bilevel.pdf", "*-cmyk8.pwg",
                                       "*-devcmyk32.urf", "*-stencil-*.pdf", "G-preview-quarter.png",
                                       "hcal-discovery-color-preview-quarter.png")),
        Compare("probe", f"{E039}/probe", ("probe-page-*", "srgb-chart-*"))),
        needs=("e039-set",), tag="main-regen", allow_fail=True,
        notes=(("hcal-discovery-*", "NOT REPRODUCIBLE BY DESIGN: the discovery PostScript writes the renderer's "
                                    "`realtime` (its NONCE) into both machine strips, so every gs render differs; "
                                    "two renders today differ from each other, and the decoded pixels differ "
                                    "only inside the two strips (y 300-400, 6600-6700 dots)"),),
        reason="toolchain-dependent: ghostscript bitcmyk renders, zlib, libcups, Pillow, the macOS Helvetica; "
               "the devcmyk32 URF has no command line in the tracked tool and is rebuilt from its two helpers"),

    Family("e041", "e041 M281 screen-route jobs S1-S17, from the regenerated F and e030 c3-cmy7", "main", (
        _x41("make_ps_variants.py", "--src", F_REGEN + "/page000.ps", "--out", "{out}"),
        _x41("make_maxescape.py", "--src", F_REGEN + "/page000.ps", "--out", "{out}/S6-maxescape.ps"),
        _x41("make_media_variants.py", "--src", F_REGEN + "/page000.ps", "--out", "{out}"),
        _x41("make_rotated_sheet.py", "--src", F_REGEN + "/page000.ps", "--out", "{out}"),
        _x41("make_banded_halftone.py", "--src", F_REGEN + "/page000.ps", "--out", "{out}/S2-banded-halftone.ps"),
        _x41("make_alphabet_sheet.py", "--cmy8", F_REGEN, "--cmy7", C3CMY7_REGEN, "--out", "{out}"),
        _x41("make_notriple_sheet.py", "--f-dir", F_REGEN, "--s1", "{out}/S1-pjl-bpp1.ps", "--out", "{out}",
             "--no-verify-gs"),
        _x41("make_notriple_sheet.py", "--f-dir", F_REGEN, "--s1", "{out}/S1-pjl-bpp1.ps", "--out", "{out}",
             "--include-dust", "--no-verify-gs"),
        *(_x41("pcl_planar.py", "--gt", F_REGEN + "/page000_gt.npy", "--mode", mode, "--out", f"{{out}}/{name}")
          for mode, name in (("cmy3", "S3-pcl-cmy3.pcl"), ("kcmy4", "S3b-pcl-kcmy4.pcl"),
                             ("cid-cmy", "S3c-pcl-cid-cmy.pcl"))),
        _x41("pclxl_bilevel.py", "--gt", F_REGEN + "/page000_gt.npy", "--variant", "base",
             "--out", "{out}/S9-pclxl-bilevel.pclxl"),
        _x41("pclxl_bilevel.py", "--gt", F_REGEN + "/page000_gt.npy", "--variant", "dither1x1",
             "--out", "{out}/S9b-pclxl-dither1x1.pclxl"),
        _x41("pclxl_probe.py", "--out", "{out}/S10p-pclxl-rgb-probe.pclxl"),
        _x41("pclxl_probe_banded.py", "--out", "{out}/S10p2-pclxl-rgb-probe.pclxl"),
        _x41("pclxl_probe_banded.py", "--only", "M", "--out", "{out}/S10p2M-pclxl-rgb-probe-M.pclxl"),
        _x41("pclxl_mixture.py", "--out", "{out}/S11-pclxl-mixture.pclxl"),
        _x41("pwg_job.py", F_REGEN, "{out}/S4-pwg-cmyk8"),
        _x41("ps_mixture.py", "--s11", "{out}/S11-pclxl-mixture.manifest.json", "--out", "{out}/S12-ps-mixture.ps"),
        _x41("ps_scale.py", "--out", "{out}/S14-ps-scale.ps"),
        _x41("ps_reset.py", "--out", "{out}/S15-ps-reset.ps"),
        _x41("ps_trigger.py", "--out", "{out}/S16-ps-trigger.ps"),
        _x41("ps_layouts.py", "--out", "{out}/S17-ps-layouts.ps"),
    ), (Compare(".", E041, E041_JOBS),), needs=("e033-original", "e030"), tag="main-regen", allow_fail=True,
        reason="S11t-pclxl-mixture-twin.pclxl has no generator (S11 with the six toner-black bytes set back by "
               "hand, e041 log 041.5b); the --verify renders are skipped, the bytes are what is compared"),

    Family("e042", "e042 AltaLink X1 density probe", "main", (
        ("{py}", "experiments/042-altalink-cell-encodings/ps_altalink_probe.py", "--out",
         "{out}/X1-altalink-probe.ps"),
    ), (Compare(".", "scratch/altalink-20261006", ("X1-altalink-probe.ps", "X1-altalink-probe-bands.npz")),),
        tag="main-regen"),

    Family("e018-tar", "e018 payload: the CORE tar.gz (recovered_e018.tar.gz) from a 2026-07-10 tree", "eb5174e9", (
        ("@mkdir", f"{{wt}}/{X18}/build"),
        ("@copy", f"{{tool}}/{X18}/gen_e018.py", f"{{wt}}/{X18}/gen_e018.py"),
        ("{py}", "-c", E018_TAR, f"{X18}/gen_e018.py", "{out}/recovered_e018.tar.gz"),
    ), (Compare(".", f"{X18}/build", ("recovered_e018.tar.gz",)),), tag="e018",
        reason="the tar is make_targz() over that tree's src/paperholo CORE files; gen_e018.py is main's copy "
               "(the tree predates the script); four trees of 2026-07-10 (eb5174e9, 56918373, e98346df, "
               "f8de66eb) reproduce it, 06a8134c changed formats.py/place.py and broke it "
               "(docs/evidence-archive/REGENERATION-2026-10-22.md 4.1)"),

    Family("e018", "e018 confetti c3 play sheet (page + manifest), the tar supplied for make_targz()", "main", (
        ("@mkdir", f"{{wt}}/{X18}/build"),
        ("{py}", "-c", E018_PAGE, f"{X18}/gen_e018.py", "{out:e018-tar}/recovered_e018.tar.gz"),
    ), (Compare(f"wt:{X18}/build", f"{X18}/build", ("e018.ps", "e018_manifest.json")),),
        needs=("e018-tar",), tag="main-regen",
        reason="main's gen_e018.py with make_targz() replaced by the e018-tar row's bytes; also runnable at every "
               "tree from f3b71a6d (2026-07-08, paperholo.fountain) on; the manifest records the payload's hash "
               "and file list, not its bytes"),

    Family("e018b", "e018b payload sheets c2/c3, re-emitted from the payload recovered out of the published "
           "pages", "main", tuple(
               s for prof, (stem, payload) in E018B.items() for s in (
                   ("{py}", "{tool}/measure/evidence_regen/clean_decode_e018b.py", prof,
                    f"{{root}}/018b-payload-sheet/{prof}/jobs/{stem}.ps",
                    f"{{root}}/018b-payload-sheet/{prof}/jobs/{stem}_manifest.json", f"{{out}}/{payload}"),
                   ("{py}", f"{X18B}/gen_e018b.py", "emit", prof, f"{{out}}/{payload}"))
           ), (Compare(f"wt:{X18B}/build", f"{X18B}/build",
                       tuple(f"{stem}{ext}" for stem, _ in E018B.values() for ext in (".ps", "_manifest.json"))),),
        tag="main-regen",
        reason="the published PostScript is the input: the payload (a third-party image, withheld from the "
               "archive under D1) is decoded back out of the page in the clean domain, then re-emitted with no "
               "-o (content-addressed name, repository-relative print_command). --root must point at a "
               "directory laid out like the published paperholo-era release (018b-payload-sheet/{c2,c3}/jobs/"
               "<job>.ps and _manifest.json); the recovered image lands under --work and must never be "
               "committed"),

    Family("fullpage", "scratch/fullpage-*.ps (paperholo.encodings layout_version 1), with their ground truth",
           "main", (
               ("{py}", "-c", "import os, sys; os.symlink(sys.argv[1], sys.argv[2])", "{wt}", "{out}/regen"),
               ("@mkdir", "{wt}/out"),
               ("{py}", "{tool}/experiments/007-office-disc/regen_fullpage.py", "{out}", "--write-gt"),
           ), (Compare("wt:out", "scratch", tuple(f"{stem}{ext}" for stem in FULLPAGE
                                                  for ext in (".ps", "_manifest.json"))),),
        tag="main-regen",
        reason="regen_fullpage.py (the 2026-07-07 driver, recovered 2026-10-10) against main's paperholo; the "
               "pages regenerate at every tree from cb2a8ffb through main, the manifests only with --write-gt "
               "(their fields[0].gt block); the two payload arrays it writes are not in the hash TSV and are not "
               "compared. The expect list is literal, so the compare stats four files instead of walking the "
               "live scratch/ tree"),

    Family("charsheet1", "e027 charsheet-1 (track 2)", "41acf2eb", (
        ("{py}", "confetti.py", "characterize", "emit", "--printer", "hp-m281", "-o", "{out}/c"),
    ), (Compare("c", "build/charsheet1-hp-m281-a87c3d2fb40b", ("charsheet.ps", "charsheet_gt.npy",
                                                               "manifest.json")),), tag="charsheet1"),

    Family("e025", "e025 channel-metrology sheets hp-m281-{bw,color}", "main", (
        ("{py}", "experiments/025-channel-metrology/emit_e025.py", "--preset", "hp-m281-bw",
         "--out", "{out}/hp-m281-bw"),
        ("{py}", "experiments/025-channel-metrology/emit_e025.py", "--preset", "hp-m281-color",
         "--out", "{out}/hp-m281-color"),
    ), (Compare(".", "experiments/025-channel-metrology/build",
                ("hp-m281-bw.ps", "hp-m281-bw_manifest.json", "hp-m281-color.ps", "hp-m281-color_manifest.json")),),
        tag="main-regen", reason="the live pair regenerates from dac54673 (2026-07-17) on; the -v1 pair is "
                                 "its own family, e025-v1, verified 2026-10-26"),

    Family("e025-v1", "e025 hp-m281-{bw,color}-v1: the first emitter version (9df37bf1) against main's library",
           "main", (
               *(("{py}", "{tool}/measure/evidence_regen/_git_show.py", f"9df37bf1:{X25}/{name}",
                  f"{{out}}/v1/{name}") for name in ("emit_e025.py", "e025_common.py")),
               *(("{py}", "{out}/v1/emit_e025.py", "--preset", f"hp-m281-{k}-v1", "--out", f"{{out}}/hp-m281-{k}-v1")
                 for k in ("bw", "color")),
           ), (Compare(".", f"{X25}/build", tuple(f"hp-m281-{k}-v1{ext}" for k in ("bw", "color")
                                                   for ext in (".ps", "_manifest.json"))),),
        tag="main-regen",
        reason="paperholo/metrology.py lost 166 lines after 9df37bf1, but the CandidateSpec/GridSpec the v1 "
               "scripts import survive unchanged; the v1 scripts are self-contained only at 9df37bf1 and "
               "45275eda (2026-07-16)"),

    *_paperholo_families(),

    Family("demo", "build/demo volume (scripts/demo.sh's generate step, 1 MB counting, never printed)", "main", (
        ("@counting", "1000000", "{out}/payload-counting.bin"),
        (*GEN, "{out}/payload-counting.bin", "--coding", "c2-r0700", "--printer", "hp-m281-ink",
         "--source-fraction", "0.7", "-o", "{out}/volume"),
    ), (Compare("volume", "build/demo/volume", ("page00[0-2].ps", "page00[0-2]_gt.npy", "manifest.json")),),
        tag="main-regen"),

    Family("emit-c4-k-7x7", "sim emission 1i150-k-r0547-p100-v1@7x7 (never printed)", "main", (
        ("@counting", "2071", "{out}/counting.bin"),
        (*GEN, "{out}/counting.bin", "--format", "1i150-k-r0547-p100-v1@7x7", "--paper", "A4-6mm",
         "--source-fraction", "0.5", "-o", "{out}/volume"),
    ), (Compare(".", "scratch/emit-c4-k-r0547-7x7-counting-20260908",
                ("counting.bin", "volume/page000.ps", "volume/page000_gt.npy", "volume/manifest.json")),),
        tag="main-regen"),

    Family("local-ab-sim", "local-ab sim emission color-hard-emit (pre-re-key seed, never printed)", "63126a89", (
        ("{py}", "-c", "import sys; from pathlib import Path; from holo3.tests import _h3_sims as s; "
                       "s.make_color_hard(Path(sys.argv[1]))", "{out}/sim"),
    ), (Compare("sim", "scratch/local-ab/sim", ("color-hard-emit/*", "sim-color-hard-payload.bin")),
        *(Compare("sim/color-hard-emit", f"scratch/local-ab/sim/{v}/color-hard-emit", ("*",))
          for v in ("a2-n12", "a3-n30", "a4-n60", "a6-n140"))),
        tag="local-ab-sim", reason="only the emit (make_color_hard); the renders and decodes are not run"),

    # ---------------------------------------------------------- not regenerable
    Family("hcal-pre-print-day", "pre-print-day HCAL emissions 2026-07-24 (discovery-current, -v2 final/verified, "
           "calibration copies)", None,
           reason="emitted from a dirty tree before their code was committed (nearest dce153f9); "
                  "no tracked sha; never printed per the record"),
    Family("test-pattern", "scratch/test_pattern.ps", None, reason="hand-written PostScript: it is its own source"),
    Family("holo-c2-r0550-build", "build/holo-c2-r0550@3328x2304-c056da23302d", None,
           reason="payload unknown (sha c056da23... is neither counting nor zeros); never printed"),
    Family("e039-invalid-039.3c", "e039 039.3c pbmraw URF/PDF (quarantined)", None,
           reason="made by the pre-039.3e urf_raster/pdf_bilevel (pbmraw render); the committed tools render "
                  "the bitcmyk K plane and cannot remake them"),
    Family("e039-ps-probe", "scratch/versalink-20260916/probe/ps-probe{,-pjl}.ps", None,
           reason="hand-written probes, no generator"),
    Family("e041-S11t", "e041 S11t-pclxl-mixture-twin.pclxl", None,
           reason="no generator: S11 with the six toner-black bytes set back by hand (e041 log 041.5b); "
                  "measured 2026-10-09: the archived S11/S11t differ in exactly 6 bytes, 0 -> 1, "
                  "first at offset 12052835"),
)

BY_ID: dict[str, Family] = {f.id: f for f in FAMILIES}

# Trees named by the evidence-archive plan for its other records; no verdict here runs them.
# The text is each commit's subject line.
EXTRA_TAGS: tuple[tuple[str, str, str], ...] = (
    ("v1-receiver", "f006abcc", "retirement record: Gate E passed (verify/ deleted, mypy kept)"),
    ("holo2", "39df5cfa", "Phase 3.1: holo2's documents of record archived to docs/archive/holo2/"),
    ("hcal-v2", "1430af0c", "W6 (part): footing agreement table-driven in combine"),
)
