"""e041 S1' — sheet S1 with every CMY triple cell reduced to two inks.

Sheet F (`L:c3-cmy8-p120-v1@2240x1536`) prints eight cell states per
3x3-dot cell, the CMY triple (`e` in the image's hex stream) included.
On the M281 the triple is the one state that lays three toner layers on
one cell. S1' asks whether the screened-mush failure of e038 needs the
triple: it is S1 (the PJL BITSPERPIXEL=1 + RET=OFF wrapper around F's
unchanged PostScript) with each triple cell in the PAYLOAD (default) — or
in payload AND dust under --include-dust — rewritten to a two-ink state.
The dropped plane is chosen by the page-cell ordinal, deterministically
and evenly over the three planes:

  v = (cy * 1536 + cx) % 3;  v=0 drop C (e -> 6), v=1 drop M (e -> a),
                             v=2 drop Y (e -> c)

(1536 = 0 mod 3, so on F this is v = cx % 3: a period-3 column stripe
among the triple cells — fine for a probe, one reason a format row would
draw the order from the keystream; docs/REDUCED-ALPHABET-ERASURE-ROWS.md.)

Word sites (W/CM only) never carry a triple; dust and payload cells are
classified by the format law (holo.format.pilots under the fossil row).
Dust cells are known-value FURNITURE (keystream-drawn states the receiver
reads as detector labels and anchors), so --include-dust also perturbs
dust anchoring, not only payload; the default leaves the 2,800 dust
triples printed for that reason.
Only the nine hex digits of each flipped cell change; the line structure,
header, trailer and the PJL wrapper (but its JOB NAME) are S1's bytes.
A triple-unaware decode under the F fossil sees the flips as bit errors in
the dropped plane at those cells (~N_flipped/3 per plane); the modified
ground truth is written beside the job in the shape the e041 instruments
read (<out>/<tag>-gt/{page000_gt.npy, manifest.json}).

Gates (any failure exits nonzero and publishes nothing). On the inputs:
(a) the parsed hex planes equal F's page000_gt.npy bit-exactly; (b0) the
generator's and the receiver's cell class maps agree; (b) zero triples on
word sites. On the STAGED FILES re-read from disk: (v1) the PJL wrapper
equals S1's on-disk bytes but the JOB NAME value; (v2) the inner job's
header and trailer are F's bytes and its hex stream differs from F's only
in whole 3x3 cells, each e -> the victim rule's digit, the changed cells
exactly triple & edited (F's GT file x the receiver's class map); (v3) no
triple left in the edited classes; (v4) the written GT equals the planes
of the written hex and its manifest's shas match the file; (v5) the GT
loses, per plane, exactly the dots the byte diff removes, adds none;
(h1-h3) ghostscript bitcmyk renders of F and of the written job (PJL
stripped) differ exactly in the dots the byte diff removes, K all-zero,
each field window equal to its GT file (--no-verify-gs skips h). The
in-memory counts (digits = 9 x cells, ink lost = 9 x victim cells, ...)
are true by construction; they are kept as CONSTRUCTION ASSERTS, recorded
apart from the gates, and are no evidence. Files are staged and published
GT first, the printable .ps last.

    # inputs are flags: the sheet of record was made from sheet F's gen dir
    # (confetti.py generate --format L:<F id>) and S1 (make_ps_variants.py);
    # both are in the evidence archive
    PYTHONPATH=src env/bin/python \\
        experiments/041-m281-screen-routes/make_notriple_sheet.py \\
        --f-dir <F gen dir> --s1 <S1-pjl-bpp1.ps> \\
        [--out DIR] [--include-dust]  # --out defaults to this experiment's
                                      # build/, the tag to S1dash-notriple[-alldust]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from holo.format import pilots
from holo.format.resolve import resolve_format_ref
from holo.receiver.format import identity as rx_identity

FORMAT_REF = "L:c3-cmy8-p120-v1@2240x1536"
DEFAULT_TAG = "S1dash-notriple"
ALLDUST_SUFFIX = "-alldust"
S1_JOB = b'JOB NAME="E041-S1-BPP1"'
JOB_RE = re.compile(rb'JOB NAME="[^"\r\n]*"')
UEL = b"\x1b%-12345X"
ENTER_PS = b"@PJL ENTER LANGUAGE=POSTSCRIPT\r\n"
PS_EOF = b"%%EOF\n"
S1_PREFIX = (UEL + b'@PJL JOB NAME="E041-S1-BPP1"\r\n@PJL SET BITSPERPIXEL=1\r\n'
             b"@PJL SET RET=OFF\r\n" + ENTER_PS)
S1_SUFFIX = b"\r\n" + UEL + b"@PJL EOJ\r\n" + UEL
IMAGE_END = b">> image\n"
DATA_END = b"\n>\n"
HEX_DIGITS_PER_LINE = 128
HEX = b"0123456789abcdef"
PLANE_BITS = (8, 4, 2)          # C, M, Y bits of a CMYK nibble, MSB first
K_BIT = 1
TRIPLE = 0xE
CLASS_PAYLOAD, CLASS_WORD, CLASS_DUST = 0, 1, 2
CLASS_NAMES = ("payload", "word", "dust")
VICTIM_RULE = ("v = (cy * 1536 + cx) % 3 over page-cell coordinates; v=0 drop C (e->6), "
               "v=1 drop M (e->a), v=2 drop Y (e->c); all nine hex digits of the cell")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(path: Path) -> str:
    return sha(path.read_bytes())


@dataclass(frozen=True)
class Geometry:
    cell_dots: int
    cells_yx: tuple[int, int]
    tiles_yx: tuple[int, int]
    tile_cells: int
    origin_dots_yx: tuple[int, int]     # field's top-left on the page, dots
    page_dots_xy: tuple[int, int]

    @property
    def field_dots_yx(self) -> tuple[int, int]:
        return self.cells_yx[0] * self.cell_dots, self.cells_yx[1] * self.cell_dots


def class_map(word_yx: np.ndarray, dust_yx: np.ndarray, tile_cells: int,
              tiles_yx: tuple[int, int]) -> np.ndarray:
    """Per-page cell class map (payload/word/dust) tiled from one tile's site cells."""
    tile = np.full((tile_cells, tile_cells), CLASS_PAYLOAD, dtype=np.uint8)
    tile[word_yx[:, 0], word_yx[:, 1]] = CLASS_WORD
    tile[dust_yx[:, 0], dust_yx[:, 1]] = CLASS_DUST
    return np.tile(tile, tiles_yx)


def load_geometry() -> tuple[Geometry, np.ndarray]:
    """The fossil row's geometry and its class map through the generator's format law."""
    spec = resolve_format_ref(FORMAT_REF)
    lay = spec.layout
    geo = Geometry(cell_dots=spec.cell_dots, cells_yx=tuple(spec.cells_yx),
                   tiles_yx=tuple(lay.tiles_yx), tile_cells=pilots.TILE_CELLS,
                   origin_dots_yx=tuple(lay.origin_dots_yx), page_dots_xy=tuple(lay.page_dots_xy))
    if geo.tiles_yx[0] * geo.tile_cells != geo.cells_yx[0] or geo.tiles_yx[1] * geo.tile_cells != geo.cells_yx[1]:
        raise SystemExit(f"tile matrix {geo.tiles_yx} does not tile cells {geo.cells_yx}")
    word = pilots.word_site_cells_yx(spec.family_seed)
    dust = pilots.dust_site_cells_yx(spec.family_seed, spec.n_dust)
    cls = class_map(word, dust, geo.tile_cells, geo.tiles_yx)
    tile_counts = [int((cls[:geo.tile_cells, :geo.tile_cells] == c).sum()) for c in range(3)]
    if tile_counts != [spec.payload_cells, word.shape[0], spec.n_dust]:
        raise SystemExit(f"tile class counts {tile_counts} != payload/word/dust of the row")
    return geo, cls


def receiver_class_map(geo: Geometry) -> np.ndarray:
    """The same class map through the receiver's row and site geometry (the decoder's route)."""
    row = rx_identity.resolve_format_ref(FORMAT_REF)
    if tuple(row.tiles_yx) != geo.tiles_yx:
        raise SystemExit(f"receiver tile matrix {row.tiles_yx} != generator {geo.tiles_yx}")
    sg = rx_identity.build_site_geometry(row)
    return class_map(sg.word_cells_yx, sg.extra_cells_yx, pilots.TILE_CELLS, geo.tiles_yx)


def split_ps(ps: bytes, field_dots_yx: tuple[int, int]) -> tuple[bytes, bytes, bytes]:
    """(header through '>> image\\n', hex stream with newlines, trailer from '\\n>\\n')."""
    h_dots, w_dots = field_dots_yx
    if ps.count(IMAGE_END) != 1:
        raise SystemExit("'>> image' not found exactly once")
    head, _, rest = ps.partition(IMAGE_END)
    if f"/Width {w_dots} /Height {h_dots} /BitsPerComponent 1".encode() not in head:
        raise SystemExit("not sheet F's image header")
    cut = rest.rindex(DATA_END)
    return head + IMAGE_END, rest[:cut + 1], rest[cut + 1:]


def hex_lut() -> np.ndarray:
    lut = np.full(256, 255, dtype=np.uint8)
    for i, ch in enumerate(HEX):
        lut[ch] = i
    return lut


def parse_hex(stream: bytes, field_dots_yx: tuple[int, int]) -> np.ndarray:
    """Hex stream -> (dot_rows, dot_cols) uint8 nibbles; asserts the 128+'\\n' line layout."""
    h_dots, w_dots = field_dots_yx
    n_lines, rem = divmod(h_dots * w_dots, HEX_DIGITS_PER_LINE)
    raw = np.frombuffer(stream, dtype=np.uint8)
    if rem or raw.size != n_lines * (HEX_DIGITS_PER_LINE + 1):
        raise SystemExit(f"hex stream is {raw.size} B, not {n_lines} lines of {HEX_DIGITS_PER_LINE}+LF")
    lines = raw.reshape(n_lines, HEX_DIGITS_PER_LINE + 1)
    if not (lines[:, -1] == ord("\n")).all():
        raise SystemExit("hex line structure is not uniform 128 digits + LF")
    nib = hex_lut()[lines[:, :-1]].reshape(h_dots, w_dots)
    if (nib == 255).any():
        raise SystemExit("non-lowercase-hex byte in the image stream")
    return nib


def format_hex(nib: np.ndarray) -> bytes:
    """Inverse of parse_hex: 128 lowercase digits + LF per line."""
    digits = np.frombuffer(HEX, dtype=np.uint8)[nib.ravel()]
    lines = digits.reshape(-1, HEX_DIGITS_PER_LINE)
    lf = np.full((lines.shape[0], 1), ord("\n"), dtype=np.uint8)
    return np.concatenate((lines, lf), axis=1).tobytes()


def cell_states(nib: np.ndarray, geo: Geometry) -> np.ndarray:
    """(cells_y, cells_x) nibble per cell; refuses any non-uniform 3x3 cell."""
    cd = geo.cell_dots
    blocks = nib.reshape(geo.cells_yx[0], cd, geo.cells_yx[1], cd)
    first = blocks[:, :1, :, :1]
    bad = (blocks != first).any(axis=(1, 3))
    if bad.any():
        ys, xs = np.nonzero(bad)
        raise SystemExit(f"STOP: {bad.sum()} non-uniform cells, first at cell (y,x)=({ys[0]},{xs[0]})")
    return np.ascontiguousarray(first[:, 0, :, 0])


def to_planes(nib: np.ndarray) -> np.ndarray:
    """(3, rows, cols) uint8 0/1 C, M, Y ink planes of a nibble image."""
    return np.stack([((nib & b) != 0).astype(np.uint8) for b in PLANE_BITS])


def pack_planes(planes: np.ndarray) -> np.ndarray:
    return np.packbits(planes, axis=2, bitorder="big")


def unpack_gt(packed: np.ndarray, field_dots_yx: tuple[int, int]) -> np.ndarray:
    return np.unpackbits(packed, axis=2, bitorder="big")[:, :, :field_dots_yx[1]]


def victim_map(cells_yx: tuple[int, int]) -> np.ndarray:
    ordinal = np.arange(cells_yx[0] * cells_yx[1], dtype=np.int64).reshape(cells_yx)
    return (ordinal % 3).astype(np.uint8)


def flip_cells(states: np.ndarray, flip: np.ndarray, victim: np.ndarray) -> np.ndarray:
    drop = np.array(PLANE_BITS, dtype=np.uint8)[victim]
    return np.where(flip, states ^ drop, states).astype(np.uint8)


def expand_cells(cells: np.ndarray, cell_dots: int) -> np.ndarray:
    return np.repeat(np.repeat(cells, cell_dots, axis=0), cell_dots, axis=1)


class Gates:
    def __init__(self, kind: str = "GATE") -> None:
        self.kind = kind
        self.rows: list[dict[str, object]] = []

    def check(self, name: str, passed: bool, evidence: str) -> None:
        self.rows.append({"name": name, "passed": bool(passed), "evidence": evidence})
        print(f"[{self.kind} {'PASS' if passed else 'FAIL'}] {name}: {evidence}", flush=True)

    @property
    def ok(self) -> bool:
        return all(bool(r["passed"]) for r in self.rows)


def split_pjl(job: bytes) -> tuple[bytes, bytes, bytes]:
    """(PJL prefix through ENTER LANGUAGE, inner PostScript through its last %%EOF, suffix)."""
    at = job.find(ENTER_PS)
    end = job.rfind(PS_EOF)
    if at < 0 or end < 0 or not job.startswith(UEL):
        raise SystemExit("not a PJL-wrapped PostScript job")
    cut_lo, cut_hi = at + len(ENTER_PS), end + len(PS_EOF)
    return job[:cut_lo], job[cut_lo:cut_hi], job[cut_hi:]


@dataclass(frozen=True)
class ByteDiff:
    """The written hex stream against F's, as digit positions in dot coordinates."""
    dot_y: np.ndarray
    dot_x: np.ndarray
    old_nib: np.ndarray
    new_nib: np.ndarray
    lf_touched: int


def byte_diff(f_stream: bytes, new_stream: bytes, field_dots_yx: tuple[int, int]) -> ByteDiff:
    a = np.frombuffer(f_stream, dtype=np.uint8)
    b = np.frombuffer(new_stream, dtype=np.uint8)
    pos = np.flatnonzero(a != b)
    line, col = np.divmod(pos, HEX_DIGITS_PER_LINE + 1)
    lf_touched = int((col == HEX_DIGITS_PER_LINE).sum() + (a[pos] == ord("\n")).sum() + (b[pos] == ord("\n")).sum())
    dot = line * HEX_DIGITS_PER_LINE + col
    dot_y, dot_x = np.divmod(dot, field_dots_yx[1])
    lut = hex_lut()
    return ByteDiff(dot_y, dot_x, lut[a[pos]], lut[b[pos]], lf_touched)


def verify_wrapper(gates: Gates, out_job: bytes, s1: bytes, f_ps: bytes, job_name: bytes) -> bytes:
    """v1 on the written job; returns its inner PostScript."""
    s1_pre, s1_inner, s1_suf = split_pjl(s1)
    pre, inner, suf = split_pjl(out_job)
    names = JOB_RE.findall(pre)
    ok = (s1_inner == f_ps and s1_pre == S1_PREFIX and s1_suf == S1_SUFFIX and names == [job_name]
          and JOB_RE.sub(S1_JOB, pre) == s1_pre and suf == s1_suf and len(inner) == len(f_ps)
          and len(out_job) == len(s1) + len(job_name) - len(S1_JOB))
    gates.check("v1 written PJL wrapper == S1's on-disk bytes but the JOB NAME value", ok,
                f"S1 embeds F verbatim {s1_inner == f_ps}; S1 prefix {len(s1_pre)} B == transcription "
                f"{s1_pre == S1_PREFIX}, suffix {len(s1_suf)} B == transcription {s1_suf == S1_SUFFIX}; written "
                f"JOB NAMEs {[n.decode() for n in names]}; prefix with S1's name == S1's {JOB_RE.sub(S1_JOB, pre) == s1_pre}; "
                f"suffix == S1's {suf == s1_suf}; inner {len(inner)} B vs F {len(f_ps)} B; "
                f"job {len(out_job)} B == {len(s1)} + ({len(job_name)} - {len(S1_JOB)})")
    return inner


def verify_stream(gates: Gates, f_ps: bytes, inner: bytes, geo: Geometry, f_triple: np.ndarray,
                  edited: np.ndarray) -> ByteDiff:
    """v2 on the written inner job: only whole triple cells changed, each to the victim rule's digit."""
    f_head, f_stream, f_trail = split_ps(f_ps, geo.field_dots_yx)
    head, stream, trail = split_ps(inner, geo.field_dots_yx)
    d = byte_diff(f_stream, stream, geo.field_dots_yx) if len(stream) == len(f_stream) else None
    if d is None:
        gates.check("v2 written hex stream vs F's", False, f"stream {len(stream)} B != F's {len(f_stream)} B")
        raise SystemExit(1)
    cd, cells_x = geo.cell_dots, geo.cells_yx[1]
    cell_id = (d.dot_y // cd) * cells_x + d.dot_x // cd
    ids, per_cell = np.unique(cell_id, return_counts=True)
    expect_ids = np.flatnonzero((f_triple & edited).ravel())
    rule_digit = (TRIPLE ^ np.array(PLANE_BITS, dtype=np.uint8)[cell_id % 3]).astype(np.uint8)
    old_set = sorted({HEX[int(v)]: None for v in np.unique(d.old_nib)}.keys())
    new_set = sorted({HEX[int(v)]: None for v in np.unique(d.new_nib)}.keys())
    ok = (head == f_head and trail == f_trail and d.lf_touched == 0 and bool((per_cell == 9).all())
          and np.array_equal(ids, expect_ids) and bool((d.old_nib == TRIPLE).all())
          and bool((d.new_nib == rule_digit).all()))
    gates.check("v2 written hex vs F's: whole triple&edited cells only, e -> victim-rule digit", ok,
                f"header/trailer == F's {head == f_head}/{trail == f_trail}; {d.dot_y.size} digits differ in "
                f"{ids.size} cells (digits per cell {sorted(set(per_cell.tolist()))}); LF bytes touched "
                f"{d.lf_touched}; old digits {bytes(old_set).decode()}, new digits {bytes(new_set).decode()}; "
                f"changed cells == F-GT triples & receiver-edited ({expect_ids.size}) {np.array_equal(ids, expect_ids)}; "
                f"new digit == rule at every position {bool((d.new_nib == rule_digit).all())}")
    return d


def verify_gt(gates: Gates, gt_dir: Path, nib_out: np.ndarray, geo: Geometry) -> np.ndarray:
    """v4 on the written GT: equals the written hex's planes; its manifest's shas match the file."""
    loaded = np.load(gt_dir / "page000_gt.npy")
    man = json.loads((gt_dir / "manifest.json").read_text())["pages"][0]
    planes_out = to_planes(nib_out)
    match = np.array_equal(loaded, pack_planes(planes_out))
    shas_ok = (man["gt_sha256"] == sha(loaded.tobytes())
               and man["gt_plane_sha256"] == [sha(np.ascontiguousarray(loaded[p]).tobytes()) for p in range(3)]
               and man["gt_packed_shape"] == list(loaded.shape) == [3, geo.field_dots_yx[0], geo.field_dots_yx[1] // 8]
               and man["gt_bitorder"] == "big")
    gates.check("v4 written GT == planes of the written hex; GT manifest shas/shape == the file", match and shas_ok,
                f"GT {list(loaded.shape)} == packbits(written hex) {match}; manifest sha/plane shas/shape/bitorder {shas_ok}")
    return unpack_gt(loaded, geo.field_dots_yx)


def removed_mask(d: ByteDiff, geo: Geometry) -> tuple[np.ndarray, int]:
    """(3, rows, cols) bool dots the byte diff removes, and the count of dots it adds."""
    mask = np.zeros((3, *geo.field_dots_yx), dtype=bool)
    added = 0
    for p, bit in enumerate(PLANE_BITS):
        gone = ((d.old_nib & bit) != 0) & ((d.new_nib & bit) == 0)
        added += int((((d.new_nib & bit) != 0) & ((d.old_nib & bit) == 0)).sum())
        mask[p, d.dot_y[gone], d.dot_x[gone]] = True
    return mask, added


def verify_ink(gates: Gates, planes_f_gt: np.ndarray, planes_out_gt: np.ndarray, mask: np.ndarray,
               added: int) -> tuple[list[int], list[int]]:
    """v5: the GT files differ exactly where the byte diff removes ink."""
    gone = (planes_f_gt == 1) & (planes_out_gt == 0)
    grown = int(((planes_f_gt == 0) & (planes_out_gt == 1)).sum())
    before = [int(planes_f_gt[p].sum()) for p in range(3)]
    after = [int(planes_out_gt[p].sum()) for p in range(3)]
    ok = np.array_equal(gone, mask) and grown == 0 and added == 0
    gates.check("v5 F GT -> written GT loses exactly the dots the byte diff removes, gains none", ok,
                f"C/M/Y before {before} after {after} lost {[int(gone[p].sum()) for p in range(3)]}, "
                f"byte diff removes {[int(mask[p].sum()) for p in range(3)]}; dots gained GT {grown} / diff {added}")
    return before, after


def gs_render(gs: str, ps_path: Path, out_path: Path) -> subprocess.Popen[bytes]:
    """The repo's bitcmyk convention (experiments/039-xerox-versalink/cmyk_pdf.py): the job's own
    setpagedevice picks the page."""
    return subprocess.Popen([gs, "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER", "-r600", "-sDEVICE=bitcmyk",
                             f"-sOutputFile={out_path}", str(ps_path)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def read_bitcmyk(path: Path, page_dots_xy: tuple[int, int]) -> np.ndarray:
    """(4, rows, cols) uint8 C, M, Y, K planes of a bitcmyk render (width from the file size)."""
    raw = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    w_dots, h_dots = page_dots_xy
    for w in (w_dots, w_dots + 1):
        rowbytes = (w * 4 + 7) // 8
        if raw.size == rowbytes * h_dots:
            bits = np.unpackbits(raw.reshape(h_dots, rowbytes), axis=1)[:, :w * 4]
            return np.ascontiguousarray(bits.reshape(h_dots, w, 4).transpose(2, 0, 1))
    raise SystemExit(f"{path}: {raw.size} B is no {page_dots_xy} bitcmyk page")


def gs_gate(gates: Gates, gs: str, f_ps_path: Path, inner: bytes, geo: Geometry, planes_f_gt: np.ndarray,
            planes_out_gt: np.ndarray, mask: np.ndarray) -> dict[str, object]:
    """h1-h3 on renders of F's file and of the written job's inner PostScript."""
    with tempfile.TemporaryDirectory() as tmp:
        inner_path, r_f, r_new = Path(tmp) / "inner.ps", Path(tmp) / "f.bitcmyk", Path(tmp) / "new.bitcmyk"
        inner_path.write_bytes(inner)
        procs = [gs_render(gs, f_ps_path, r_f), gs_render(gs, inner_path, r_new)]
        for p in procs:
            _, err = p.communicate()
            if p.returncode:
                raise SystemExit(f"gs failed ({p.returncode}): {err.decode(errors='replace')[:400]}")
        rf, rn = read_bitcmyk(r_f, geo.page_dots_xy), read_bitcmyk(r_new, geo.page_dots_xy)
    oy, ox = geo.origin_dots_yx
    fh, fw = geo.field_dots_yx
    expected = np.zeros(rf[:3].shape, dtype=bool)
    expected[:, oy:oy + fh, ox:ox + fw] = mask
    diff = rf[:3] != rn[:3]
    k_ok = bool((rf[3] == 0).all() and (rn[3] == 0).all())
    gates.check("h1 gs K planes identical and all-zero", k_ok,
                f"K ink dots F={int(rf[3].sum())} new={int(rn[3].sum())}; render {rf.shape[2]}x{rf.shape[1]}")
    per_plane = [int(diff[p].sum()) for p in range(3)]
    ink_added = int(((rf[:3] == 0) & (rn[:3] == 1)).sum())
    exact = bool(np.array_equal(diff, expected)) and ink_added == 0
    gates.check("h2 gs diff == the dots the written byte diff removes, nothing else, no ink added", exact,
                f"diff dots C/M/Y {per_plane}, byte diff removes {[int(mask[p].sum()) for p in range(3)]} "
                f"at field origin dots y{oy}/x{ox}; ink added {ink_added}")
    field_f = np.array_equal(rf[:3, oy:oy + fh, ox:ox + fw], planes_f_gt)
    field_n = np.array_equal(rn[:3, oy:oy + fh, ox:ox + fw], planes_out_gt)
    outside = int(rf[:3].sum()) - int(planes_f_gt.sum()), int(rn[:3].sum()) - int(planes_out_gt.sum())
    gates.check("h3 gs field window == the GT files (F and written), no ink outside", field_f and field_n and outside == (0, 0),
                f"F field == F GT {field_f}, written field == written GT {field_n}, ink outside field F/new {outside}")
    return {"command": f"{gs} -q -dBATCH -dNOPAUSE -dSAFER -r600 -sDEVICE=bitcmyk",
            "render_dots_xy": [int(rf.shape[2]), int(rf.shape[1])], "diff_dots_CMY": per_plane}


def write_gt(gen: Path, planes: np.ndarray, geo: Geometry, source_gt_sha: str, tag: str) -> str:
    gen.mkdir(parents=True, exist_ok=True)
    packed = pack_planes(planes)
    np.save(gen / "page000_gt.npy", packed)
    gt_sha = sha(packed.tobytes())
    if gt_sha == source_gt_sha:
        raise SystemExit("modified GT sha equals F's — nothing was flipped?")
    manifest = {
        "note": f"ground truth of e041 {tag} (sheet F with triples reduced to two inks); NOT a format "
                f"identity — decode under {FORMAT_REF}, the flips read as dropped-plane bit errors",
        "format_ref": FORMAT_REF, "source_gt_sha256": source_gt_sha,
        "cell_dots": geo.cell_dots, "page_cells_yx": list(geo.cells_yx), "tiles_yx": list(geo.tiles_yx),
        "pages": [{"page": 0, "gt": "page000_gt.npy", "gt_sha256": gt_sha,
                   "gt_plane_sha256": [sha(np.ascontiguousarray(packed[p]).tobytes()) for p in range(3)],
                   "gt_packed_shape": list(packed.shape), "gt_bitorder": "big",
                   "gt_axis_order": ["plane", "y", "packed_x"], "gt_plane_order": ["C", "M", "Y"]}],
    }
    (gen / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return gt_sha


def resolve_tag(tag: str | None, include_dust: bool) -> str:
    """Default tag follows the dust policy; a tag that misstates the policy is refused."""
    if tag is None:
        return DEFAULT_TAG + (ALLDUST_SUFFIX if include_dust else "")
    if include_dust and tag == DEFAULT_TAG:
        raise SystemExit(f"--include-dust with tag {DEFAULT_TAG!r} would misname the all-dust sheet")
    if not include_dust and tag.endswith(ALLDUST_SUFFIX):
        raise SystemExit(f"tag {tag!r} claims all-dust without --include-dust")
    return tag


def publish(stage: Path, out: Path, tag: str) -> Path:
    """Move staged files into place: GT, GT manifest, job manifest, and the printable .ps LAST."""
    ps_final = out / f"{tag}.ps"
    ps_final.unlink(missing_ok=True)
    gt_final = out / f"{tag}-gt"
    gt_final.mkdir(parents=True, exist_ok=True)
    for name in ("page000_gt.npy", "manifest.json"):
        os.replace(stage / f"{tag}-gt" / name, gt_final / name)
    os.replace(stage / f"{tag}.manifest.json", out / f"{tag}.manifest.json")
    os.replace(stage / f"{tag}.ps", ps_final)
    shutil.rmtree(stage)
    return ps_final


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--f-dir", type=Path, required=True, help="sheet F's gen dir (page000.ps + GT)")
    ap.add_argument("--s1", type=Path, required=True, help="the S1 job, S1-pjl-bpp1.ps")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "build")
    ap.add_argument("--tag", default=None, help=f"default {DEFAULT_TAG}, or {DEFAULT_TAG}{ALLDUST_SUFFIX} "
                                                "with --include-dust")
    ap.add_argument("--include-dust", action="store_true", help="also flip triples on dust sites")
    ap.add_argument("--verify-gs", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--gs", default=shutil.which("gs"), help="ghostscript binary (default: gs on PATH)")
    args = ap.parse_args()
    tag = resolve_tag(args.tag, args.include_dust)
    if args.verify_gs and not args.gs:
        raise SystemExit("no ghostscript found; pass --gs or --no-verify-gs")
    gates, asserts = Gates("GATE"), Gates("CONSTRUCTION ASSERT")
    geo, cls = load_geometry()
    cls_rx = receiver_class_map(geo)
    gates.check("b0 class map: generator format law == receiver site geometry", np.array_equal(cls, cls_rx),
                f"payload/word/dust cells generator {[int((cls == c).sum()) for c in range(3)]}, "
                f"receiver {[int((cls_rx == c).sum()) for c in range(3)]}")

    f_ps_path = args.f_dir / "page000.ps"
    f_ps = f_ps_path.read_bytes()
    f_manifest = json.loads((args.f_dir / "manifest.json").read_text())
    page = f_manifest["pages"][0]
    if sha(f_ps) != page["ps_sha256"]:
        raise SystemExit("F page000.ps sha != its manifest")
    f_gt = np.load(args.f_dir / page["gt"])
    if sha(f_gt.tobytes()) != page["gt_sha256"] or page["gt_bitorder"] != "big":
        raise SystemExit("F GT sha/bitorder mismatch")
    head, stream, trailer = split_ps(f_ps, geo.field_dots_yx)
    nib = parse_hex(stream, geo.field_dots_yx)
    if format_hex(nib) != stream:
        raise SystemExit("hex re-serialisation is not byte-identical to F's stream")
    k_dots = int(((nib & K_BIT) != 0).sum())
    if k_dots:
        raise SystemExit(f"STOP: {k_dots} dots carry the K bit")
    states = cell_states(nib, geo)
    planes_f = to_planes(nib)
    gt_match = f_gt.shape == (3, geo.field_dots_yx[0], geo.field_dots_yx[1] // 8) and np.array_equal(pack_planes(planes_f), f_gt)
    gates.check("a parse == F page000_gt.npy bit-exactly", gt_match,
                f"GT shape {list(f_gt.shape)} big-endian; K dots 0; {geo.cells_yx[0] * geo.cells_yx[1]} cells "
                f"uniform 3x3; cell (cy,cx) = dots (3cy..3cy+2, 3cx..3cx+2); hex re-serialisation byte-identical")

    triple = states == TRIPLE
    counts = {f"triples_{n}": int((triple & (cls == c)).sum()) for c, n in enumerate(CLASS_NAMES)}
    word_states = sorted(int(s) for s in np.unique(states[cls == CLASS_WORD]))
    dust_states = sorted(int(s) for s in np.unique(states[cls == CLASS_DUST]))
    gates.check("b word-site triples == 0", counts["triples_word"] == 0,
                f"word triples {counts['triples_word']}; word-site states {[hex(s) for s in word_states]}; "
                f"dust-site states {[hex(s) for s in dust_states]}; payload triples {counts['triples_payload']}, "
                f"dust triples {counts['triples_dust']}")
    if not gates.ok:
        print("INPUT GATES FAILED — nothing written", file=sys.stderr)
        return 1

    edited = (cls == CLASS_PAYLOAD) | ((cls == CLASS_DUST) if args.include_dust else False)
    flip = triple & edited
    victim = victim_map(geo.cells_yx)
    new_states = flip_cells(states, flip, victim)
    new_nib = expand_cells(new_states, geo.cell_dots)
    n_flip = int(flip.sum())
    flipped_by_victim = [int((flip & (victim == p)).sum()) for p in range(3)]
    digits_changed = int((new_nib != nib).sum())
    asserts.check("c hex digits changed == 9 x flipped cells", digits_changed == 9 * n_flip,
                  f"{digits_changed} digits, {n_flip} cells (drop C/M/Y {flipped_by_victim})")
    left_edit = int((new_states[edited] == TRIPLE).sum())
    asserts.check("d no triple left in the edited classes (in memory)", left_edit == 0, f"{left_edit} left")
    planes_new = to_planes(new_nib)
    lost = [int(planes_f[p].sum()) - int(planes_new[p].sum()) for p in range(3)]
    asserts.check("g each plane loses 9 dots per victim cell (in memory)",
                  lost == [9 * v for v in flipped_by_victim], f"lost C/M/Y {lost}")
    inner_mem = head + format_hex(new_nib) + trailer
    s1 = args.s1.read_bytes()
    job_name = f'JOB NAME="E041-{tag.upper()}"'.encode()
    s1_pre, _, s1_suf = split_pjl(s1)
    if s1_pre.count(S1_JOB) != 1:
        raise SystemExit("S1 prefix carries its JOB NAME not exactly once")
    out_job = s1_pre.replace(S1_JOB, job_name) + inner_mem + s1_suf
    asserts.check("e job length == S1 + JOB NAME delta (in memory)",
                  len(out_job) == len(s1) + len(job_name) - len(S1_JOB), f"{len(out_job)} B")
    if not asserts.ok:
        print("CONSTRUCTION ASSERT FAILED — nothing written", file=sys.stderr)
        return 1
    del new_nib, planes_new, inner_mem

    args.out.mkdir(parents=True, exist_ok=True)
    stage = args.out / f".{tag}.staging"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    try:
        write_gt(stage / f"{tag}-gt", to_planes(expand_cells(new_states, geo.cell_dots)), geo, page["gt_sha256"], tag)
        (stage / f"{tag}.ps").write_bytes(out_job)
        del out_job

        job_disk = (stage / f"{tag}.ps").read_bytes()
        inner = verify_wrapper(gates, job_disk, s1, f_ps, job_name)
        f_triple = unpack_gt(f_gt, geo.field_dots_yx)[:, ::geo.cell_dots, ::geo.cell_dots].all(axis=0)
        edited_rx = (cls_rx == CLASS_PAYLOAD) | ((cls_rx == CLASS_DUST) if args.include_dust else False)
        d = verify_stream(gates, f_ps, inner, geo, f_triple, edited_rx)
        nib_out = parse_hex(split_ps(inner, geo.field_dots_yx)[1], geo.field_dots_yx)
        states_out = cell_states(nib_out, geo)
        left = {n: int(((states_out == TRIPLE) & (cls_rx == c)).sum()) for c, n in enumerate(CLASS_NAMES)}
        left_ok = left["payload"] == 0 and left["word"] == 0 and \
            left["dust"] == (0 if args.include_dust else counts["triples_dust"])
        gates.check("v3 triples left in the written job, by receiver class", left_ok,
                    f"payload {left['payload']}, word {left['word']}, dust {left['dust']} "
                    f"(expected dust {0 if args.include_dust else counts['triples_dust']})")
        planes_out_gt = verify_gt(gates, stage / f"{tag}-gt", nib_out, geo)
        planes_f_gt = unpack_gt(f_gt, geo.field_dots_yx)
        mask, added = removed_mask(d, geo)
        ink_before, ink_after = verify_ink(gates, planes_f_gt, planes_out_gt, mask, added)
        gs_info: dict[str, object] = {"skipped": True}
        if args.verify_gs:
            gs_info = gs_gate(gates, args.gs, f_ps_path, inner, geo, planes_f_gt, planes_out_gt, mask)
        if not gates.ok:
            print("GATES FAILED — nothing published", file=sys.stderr)
            return 1

        ids_disk = np.unique((d.dot_y // geo.cell_dots) * geo.cells_yx[1] + d.dot_x // geo.cell_dots)
        gt_final = args.out / f"{tag}-gt" / "page000_gt.npy"
        dust_policy = ("payload and dust triples flipped; the flipped dust cells are known-value "
                       "FURNITURE (keystream-drawn dust states the receiver reads as detector labels and "
                       "anchors), so this sheet also perturbs dust anchoring, not only payload"
                       if args.include_dust else
                       "dust untouched (dust triples stay printed); payload triples flipped")
        manifest = {
            "tag": tag,
            "what": "S1 (PJL BITSPERPIXEL=1 + RET=OFF) with every CMY triple cell in the edited classes "
                    "reduced to two inks; nothing else changed but the PJL JOB NAME",
            "source_ps": str(f_ps_path), "source_sha256": sha(f_ps),
            "s1_wrapper_source": str(args.s1), "s1_sha256": sha(s1),
            "bytes": len(job_disk), "sha256": sha(job_disk), "inner_ps_sha256": sha(inner),
            "format_ref": FORMAT_REF, "image_data_changed": True,
            "victim_rule": VICTIM_RULE, "dust_policy": dust_policy,
            "counts": {**counts, "flipped_cells": int(ids_disk.size),
                       "flipped_to_drop_CMY": [int((ids_disk % 3 == p).sum()) for p in range(3)],
                       "hex_digits_changed": int(d.dot_y.size),
                       "ink_dots_before_CMY": ink_before, "ink_dots_after_CMY": ink_after,
                       "triples_remaining_payload": left["payload"],
                       "triples_remaining_total": sum(left.values())},
            "gt": str(gt_final), "gt_sha256": sha(np.load(stage / f"{tag}-gt" / "page000_gt.npy").tobytes()),
            "gt_file_sha256": sha_file(stage / f"{tag}-gt" / "page000_gt.npy"),
            "gs_check": gs_info, "gates": gates.rows,
            "construction_asserts": {"note": "true by construction of the in-memory edit; NOT evidence",
                                     "rows": asserts.rows},
            "decode_note": (f"a triple-unaware decode under {FORMAT_REF} sees the {n_flip} flips as bit errors in "
                            f"the dropped plane at two-ink cells: C {flipped_by_victim[0]}, M {flipped_by_victim[1]}, "
                            f"Y {flipped_by_victim[2]} (~N_flipped/3 per plane); score against {tag}-gt"),
        }
        (stage / f"{tag}.manifest.json").write_text(json.dumps(manifest, indent=1))
        reread = json.loads((stage / f"{tag}.manifest.json").read_text())
        if reread["sha256"] != sha_file(stage / f"{tag}.ps") or reread["bytes"] != (stage / f"{tag}.ps").stat().st_size:
            print("job manifest sha/bytes != the staged .ps — nothing published", file=sys.stderr)
            return 1
        ps_final = publish(stage, args.out, tag)
        print(f"{ps_final.name}: {manifest['bytes']} B sha {manifest['sha256']}; GT sha {manifest['gt_sha256']}")
        return 0
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    sys.exit(main())
