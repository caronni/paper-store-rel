#!/usr/bin/env python3
"""R2 truth genie (qualification only): reads a camera.py capture with the
TRUE pose from its truth sidecar, to check the sidecar (crop, rot90, cuts,
damage) and to bound what any reader can get from the frame.

For every grid block whose 18 x 18 module lattice (interior plus the four
timing lines around it) lies inside the frame: sample each module centre
bilinearly through `homography_grid_modules_to_px` (or the page-dots one and
the page sidecar), threshold the 256 interior modules at the mean of the
block's 68 timing modules, compare with the page's grid.txt, and decode:
data blocks by CRC-32 (over the page sidecar's six header bytes + bytes
0-27), white slots (all modules 0), bullseye blocks by the
ring modules and the 20-bit header check.  No search, no repair.
chunks_lost = the page's chunks with no CRC-clean copy in this frame (on a
whole-page capture: what the frame loses outright).

Usage: genie.py CAPTURE.pgm PAGEPREFIX [--truth CAPTURE.json] [--json]
  PAGEPREFIX = the gen.py output prefix (PAGEPREFIX.json, .grid.txt).
"""
import argparse
import json
import sys
import zlib

import numpy as np


def load_pgm(path):
    raw = open(path, "rb").read()
    magic = raw[:2]
    toks, pos = [], 2
    while len(toks) < 3:
        while raw[pos:pos + 1].isspace():
            pos += 1
        end = pos
        while not raw[end:end + 1].isspace():
            end += 1
        toks.append(int(raw[pos:end]))
        pos = end
    w, h, _ = toks
    body = raw[pos + 1:]
    if magic == b"P5":
        return np.frombuffer(body[:w * h], dtype=np.uint8).reshape(h, w)
    return np.array(body.split(), dtype=np.uint8).reshape(h, w)


def read(capture, prefix, truth_path=None):
    img = load_pgm(capture).astype(np.float64)
    truth = json.load(open(truth_path or capture.rsplit(".", 1)[0] + ".json"))
    side = json.load(open(prefix + ".json"))
    grid = np.array([[int(ch) for ch in ln.strip()]
                     for ln in open(prefix + ".grid.txt")], dtype=np.uint8)
    H, W = grid.shape
    md = side["module_dots"]
    hm = np.array(truth["homography_page_dots_to_px"]) @ np.array(
        [[md, 0, side["x0_dots"]], [0, md, side["y0_dots"]], [0, 0, 1]])
    rr, cc = np.mgrid[0:H, 0:W].astype(np.float64)
    X, Y = cc + 0.5, rr + 0.5
    den = hm[2, 0] * X + hm[2, 1] * Y + hm[2, 2]
    u = (hm[0, 0] * X + hm[0, 1] * Y + hm[0, 2]) / den - 0.5
    v = (hm[1, 0] * X + hm[1, 1] * Y + hm[1, 2]) / den - 0.5
    ih, iw = img.shape
    inside = (u >= 0) & (v >= 0) & (u <= iw - 1.001) & (v <= ih - 1.001)
    uc, vc = np.clip(u, 0, iw - 1.001), np.clip(v, 0, ih - 1.001)
    i0, j0 = vc.astype(int), uc.astype(int)
    fy, fx = vc - i0, uc - j0
    val = (img[i0, j0] * (1 - fx) * (1 - fy) + img[i0, j0 + 1] * fx * (1 - fy)
           + img[i0 + 1, j0] * (1 - fx) * fy + img[i0 + 1, j0 + 1] * fx * fy)
    be = {tuple(b["block"]) for b in side["bullseyes"]}
    hdr_pos = [tuple(m) for m in side["header"]["modules_block_local_rc"]]
    six = bytes.fromhex(side["header"]["bytes_hex"])  # block CRC prefix
    slot_of = {tuple(b): s for s, b in enumerate(side["slot_block"])}
    damaged = set()
    for d in truth.get("damage", []):
        damaged |= {tuple(b) for b in d.get("blocks_touched", [])}
    st = dict(frame_px=[iw, ih], blocks_in_frame=0, modules=0,
              module_errors=0, data_in_frame=0, data_crc_ok=0,
              white_in_frame=0, white_ok=0, bullseyes_in_frame=0,
              bullseye_ring_errors=0, headers_ok=0,
              undamaged_data_in_frame=0, undamaged_data_crc_ok=0,
              damaged_blocks_in_frame=0)
    chunks = set()
    for bi in range((H - 1) // 17):
        for bj in range((W - 1) // 17):
            r0, c0 = 17 * bi, 17 * bj
            if not inside[r0:r0 + 18, c0:c0 + 18].all():
                continue
            st["blocks_in_frame"] += 1
            lat = val[r0:r0 + 18, c0:c0 + 18]
            tim = np.concatenate([lat[0, :], lat[17, :], lat[1:17, 0],
                                  lat[1:17, 17]])
            thr = tim.mean()
            bits = (lat[1:17, 1:17] < thr).astype(np.uint8)
            truth_bits = grid[r0 + 1:r0 + 17, c0 + 1:c0 + 17]
            err = int((bits != truth_bits).sum())
            st["modules"] += 256
            st["module_errors"] += err
            dmg = (bi, bj) in damaged
            st["damaged_blocks_in_frame"] += dmg
            if (bi, bj) in be:
                st["bullseyes_in_frame"] += 1
                ring = [(r, c) for r in range(16) for c in range(16)
                        if (r, c) not in set(hdr_pos)]
                st["bullseye_ring_errors"] += sum(
                    int(bits[r, c] != truth_bits[r, c]) for r, c in ring)
                hb = [int(bits[r, c]) for r, c in hdr_pos[:68]]
                read6 = int("".join(map(str, hb[:48])), 2).to_bytes(6, "big")
                chk = int("".join(map(str, hb[48:])), 2)
                st["headers_ok"] += (zlib.crc32(read6) % (1 << 20) == chk)
                continue
            s = slot_of[(bi, bj)]
            if side["slot_chunk"][s] is None:
                st["white_in_frame"] += 1
                st["white_ok"] += int(not bits.any())
                continue
            st["data_in_frame"] += 1
            st["undamaged_data_in_frame"] += not dmg
            blk = np.packbits(bits.ravel()).tobytes()
            ok = zlib.crc32(six + blk[:28]) == int.from_bytes(blk[28:], "big")
            st["data_crc_ok"] += ok
            st["undamaged_data_crc_ok"] += ok and not dmg
            if ok:
                chunks.add(int.from_bytes(blk[:2], "big"))
    st["chunks_seen"] = len(chunks)
    st["chunk_range"] = [min(chunks), max(chunks)] if chunks else None
    on_page = {c for c in side["slot_chunk"] if c is not None}
    st["chunks_on_page"] = len(on_page)
    st["chunks_lost"] = sorted(on_page - chunks)
    st["module_error_rate"] = st["module_errors"] / max(1, st["modules"])
    return st


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("capture")
    ap.add_argument("prefix")
    ap.add_argument("--truth")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    st = read(a.capture, a.prefix, a.truth)
    if a.json:
        print(json.dumps(st))
    else:
        print(f"{a.capture}: frame {st['frame_px'][0]}x{st['frame_px'][1]}, "
              f"blocks in frame {st['blocks_in_frame']}, module errors "
              f"{st['module_errors']}/{st['modules']} "
              f"({100 * st['module_error_rate']:.3f} %); data CRC ok "
              f"{st['data_crc_ok']}/{st['data_in_frame']}, white ok "
              f"{st['white_ok']}/{st['white_in_frame']}, bullseyes "
              f"{st['bullseyes_in_frame']} (headers ok {st['headers_ok']}, "
              f"ring errors {st['bullseye_ring_errors']}); chunks seen "
              f"{st['chunks_seen']} of {st['chunks_on_page']}, lost "
              f"{st['chunks_lost'][:20]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
