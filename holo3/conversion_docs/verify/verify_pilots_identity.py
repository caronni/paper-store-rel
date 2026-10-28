# Verify holo3/format/pilots.py + holo3/format/identity.py bit-exact
# against the src/holo oracle, in ONE process under env314t.
#
# holo3.lib.bch and holo3.format.keystream do not exist yet (B1/B3);
# they are stubbed here with the ORACLE modules themselves — legitimate
# because the contract freezes those surfaces as signature-verbatim
# copies of src/holo, so composing my modules with the oracle proves my
# code is bit-exact given conforming siblings.

import sys

import numpy as np

import holo.core.bch as obch
import holo.core.keystream as oks
import holo.format.pilots as opilots
import holo.format.fossils as ofossils
import holo.format.layout as olayout
import holo.format.resolve as oresolve

import holo3.format.pilots as pilots           # noqa: E402
import holo3.format.identity as identity       # noqa: E402

N_CHECKS = 0
FAILED = []


def check(name: str, cond: bool) -> None:
    global N_CHECKS
    N_CHECKS += 1
    tag = "ok " if cond else "FAIL"
    print(f"{tag} {name}")
    if not cond:
        FAILED.append(name)


def eq(a, b) -> bool:
    a = np.asarray(a)
    b = np.asarray(b)
    return a.shape == b.shape and a.dtype == b.dtype and bool(
        np.array_equal(a, b))


P100 = ofossils.FAMILY_SEED_P100
P120 = ofossils.FAMILY_SEED_P120

# ------------------------------------------------------ site constructions
for fam_seed, label in ((P100, "p100"), (P120, "p120")):
    check(f"word sites {label}",
          eq(pilots.word_site_cells_yx(fam_seed),
             opilots.word_site_cells_yx(fam_seed)))
w_mine = pilots.word_site_cells_yx(P120)
w_orac = opilots.word_site_cells_yx(P120)
check("filler sites p120 F=20",
      eq(pilots.filler_site_cells_yx(P120, 20, w_mine),
         opilots.filler_site_cells_yx(P120, 20, w_orac)))
check("site_cell_indices p100 F=0",
      eq(pilots.site_cell_indices(P100, 0),
         opilots.site_cell_indices(P100, 0)))
check("site_cell_indices p120 F=20",
      eq(pilots.site_cell_indices(P120, 20),
         opilots.site_cell_indices(P120, 20)))
check("dust sites p120",
      eq(pilots.dust_site_cells_yx(P120, 20),
         opilots.dust_site_cells_yx(P120, 20)))
mine_c = pilots.color_site_cells_yx(P120)
orac_c = opilots.color_site_cells_yx(P120)
check("color sites p120", eq(mine_c[0], orac_c[0]) and eq(mine_c[1],
                                                          orac_c[1]))
check("color payload cell indices p120",
      eq(pilots.color_payload_cell_indices(P120),
         opilots.color_payload_cell_indices(P120)))
check("color payload count 3976",
      pilots.color_payload_cell_indices(P120).size == 3976)

# ----------------------------------------- per-seed word/dust value parity
SEED_ROWS = [
    ("c3-r0550@2240x1536", False),
    ("c2-r0700@3392x2368", False),
    ("c2-cmy7-p120-v0@3328x2304", True),
    ("c2-cmy8-p120-v0@3328x2304", True),
    ("c2-cmy8-r0700-p120-x1@3392x2368", True),
]
rng = np.random.default_rng(20260828)
for spec_id, is_color in SEED_ROWS:
    fossil = ofossils.FOSSILS[spec_id]
    seed = fossil.seed
    ospec = oresolve.resolve_format_ref("L:" + spec_id)
    n_tiles = ospec.layout.tiles_yx[0] * ospec.layout.tiles_yx[1]
    counters = np.concatenate([
        np.array([0, 1, n_tiles - 1], dtype=np.int64),
        rng.integers(0, n_tiles, size=13, dtype=np.int64)])
    for plane in (0, oks.PLANE_K):
        check(f"scramble bits {spec_id} plane {plane}",
              eq(pilots.value_scramble_bits(seed, plane),
                 opilots.value_scramble_bits(seed, plane)))
    check(f"word_values {spec_id}",
          eq(pilots.word_values(seed, counters),
             opilots.word_values(seed, counters)))
    if is_color:
        check(f"color_word_states {spec_id}",
              eq(pilots.color_word_states(seed, counters),
                 opilots.color_word_states(seed, counters)))
        codec = ospec.coding.codec
        check(f"dust_state_values {spec_id}",
              eq(pilots.dust_state_values(seed, counters,
                                          codec.dust_base_cycle,
                                          codec.n_dust),
                 opilots.dust_state_values(seed, counters, codec)))
    # decode parity: clean, noisy (<=13 errors), erasures, pad gate
    vals = opilots.word_values(seed, counters)
    ok_all = True
    for i, c in enumerate(counters):
        noisy = vals[i].copy()
        n_err = int(rng.integers(0, 14))
        flip = rng.choice(100, size=n_err, replace=False)
        noisy[flip] ^= 1
        mine = pilots.decode_word(noisy, seed)
        orac = opilots.decode_word(noisy, seed)
        ok_all &= (mine == orac)
        if n_err <= 13:
            ok_all &= (mine == int(c))
        era = np.unique(rng.choice(100, size=8, replace=False))
        erased = vals[i].copy()
        erased[era] ^= rng.integers(0, 2, size=era.size).astype(np.uint8)
        mine_e = pilots.decode_word(erased, seed, erasure_idx=era)
        orac_e = opilots.decode_word(erased, seed, erasure_idx=era)
        ok_all &= (mine_e == orac_e)
    check(f"decode_word parity {spec_id}", ok_all)
    # pad gate: a codeword whose message has a nonzero pad must refuse
    msg = np.zeros(23, dtype=np.uint8)
    msg[0] = 1
    msg[20] = 1
    bad = obch.encode(msg) ^ opilots.value_scramble_bits(seed)
    check(f"pad gate {spec_id}",
          pilots.decode_word(bad, seed) is None
          and opilots.decode_word(bad, seed) is None)
    if is_color:
        ok_all = True
        for i, c in enumerate(counters):
            states = (vals[i] * np.uint8(3)).astype(np.uint8)
            ok_all &= (pilots.decode_color_word(states, seed)
                       == opilots.decode_color_word(states, seed) == int(c))
        bad_states = (vals[0] * np.uint8(3)).astype(np.uint8)
        bad_states[7] = 1
        ok_all &= (pilots.decode_color_word(bad_states, seed) is None)
        check(f"decode_color_word parity {spec_id}", ok_all)

# ------------------------------------------------------- fossil catalogue
check("fossil count 14", len(identity._FOSSILS) == 14
      and len(ofossils.FOSSILS) == 14)
check("fossil key set", set(identity._FOSSILS) == set(ofossils.FOSSILS))
for spec_id, fossil in ofossils.FOSSILS.items():
    ospec = oresolve.resolve_format_ref("L:" + spec_id)
    row = identity.resolve_format_ref("L:" + spec_id)
    ok = (row.seed == fossil.seed
          and row.row_id == "L:" + spec_id
          and row.tiles_yx == ospec.layout.tiles_yx
          and row.cells_yx == fossil.cells_yx
          and row.pooled_fountain == ospec.pooled_fountain
          and row.family.value == ospec.coding.codec.family.value
          and row.n_sites == ospec.coding.codec.n_sites
          and row.n_dust == ospec.coding.codec.n_dust
          and row.dust_base_cycle == tuple(
              ospec.coding.codec.dust_base_cycle)
          and row.word_states == tuple(ospec.coding.codec.word_states)
          and row.bits_per_mapper_unit
          == ospec.coding.codec.bits_per_mapper_unit
          and row.cells_per_mapper_unit
          == ospec.coding.codec.cells_per_mapper_unit
          and row.family_seed == ospec.coding.family_seed)
    ostreams = ospec.coding.codec.streams
    ok &= len(row.streams) == len(ostreams)
    for mine_s, orac_s in zip(row.streams, ostreams):
        ok &= (mine_s.stream_id == orac_s.stream_id
               and mine_s.fountain_aux == orac_s.fountain_aux
               and mine_s.user_bits == orac_s.user_bits
               and mine_s.symbol_bits == orac_s.symbol_bits
               and mine_s.rung_children == tuple(
                   (ch.code_id, ch.shortened_info_tail)
                   for ch in orac_s.fec.children))
    check(f"fossil row {spec_id}", ok)

# --------------------------------------------------------- v2 canonical ids
V2_IDS = [
    "c3-k-r0550@7x7",
    "c3-cmy8-r0550x0550x0547@10x10",
    "c3-k-r0550-p100-v1@7x7",
    "c3-cmy8-r0550@10x10",
    "c2-cmy7@52x36",
    "1i200-k-r0550@7x7",
]
for ref in V2_IDS:
    ospec = oresolve.resolve_format_ref(ref)
    row = identity.resolve_format_ref(ref)
    ok = (row.row_id == ospec.spec_id and row.seed == ospec.seed
          and row.tiles_yx == ospec.layout.tiles_yx
          and row.n_sites == ospec.coding.codec.n_sites
          and row.pooled_fountain == ospec.pooled_fountain
          and row.family_seed == ospec.coding.family_seed)
    ostreams = ospec.coding.codec.streams
    for mine_s, orac_s in zip(row.streams, ostreams):
        ok &= (mine_s.stream_id == orac_s.stream_id
               and mine_s.user_bits == orac_s.user_bits
               and mine_s.symbol_bits == orac_s.symbol_bits
               and mine_s.rung_children == tuple(
                   (ch.code_id, ch.shortened_info_tail)
                   for ch in orac_s.fec.children))
    check(f"v2 resolve {ref} -> {row.row_id}", ok)
check("v2 fixed point",
      identity.resolve_format_ref("c3-k-r0550-p100-v1@7x7").row_id
      == identity.resolve_format_ref("c3-k-r0550@7x7").row_id
      == "c3-k-r0550@7x7")

for bad in ("c2-cmy8-r0700x0700x0550@10x10",   # mixed widths
            "c2-cmy7-r0550@10x10",             # cmy7 rung token
            "c2-k-r0700@600x600",              # counter space
            "c2-cmy8-r0700-p100@10x10",        # dust-free cmy8
            "c2-k-r0700-v2@7x7",               # undefined generation
            "c2-k-r0700-p100-r0550@7x7",       # misordered
            "c2-r0700@3392x2368",              # bare legacy spelling
            "L:c2-r0700@9999x9999"):           # unknown fossil
    refused = False
    try:
        identity.resolve_format_ref(bad)
    except ValueError:
        refused = True
    check(f"refuses {bad}", refused)

# ---------------------------------------------------------- derive_field
FIELD_TABLE = [
    ((210.0, 297.0), 6.0, 2, (3328, 2304)),
    ((210.0, 297.0), 6.0, 3, (2240, 1536)),
    ((210.0, 297.0), 6.0, 4, (1664, 1152)),
    ((210.0, 297.0), 4.0, 2, (3392, 2368)),
    ((210.0, 297.0), 4.0, 3, (2240, 1536)),
    ((210.0, 297.0), 4.5, 2, (3392, 2368)),
    ((297.0, 420.0), 4.0, 2, (4864, 3392)),
]
for media, margin, cell_dots, expect in FIELD_TABLE:
    mine = identity.derive_field(media, margin, cell_dots)
    orac = olayout.derive_field(media, margin, cell_dots).cells_yx
    check(f"derive_field {media} {margin}mm c{cell_dots}",
          mine == orac == expect)

check("sugar hp-m281-ink",
      identity.coding_printer_ref("c2-r0700", "hp-m281-ink")
      == "L:c2-r0700@3392x2368")
check("sugar default c2",
      identity.coding_printer_ref("c2-r0700", "default")
      == "L:c2-r0700@3328x2304")
check("sugar default c3",
      identity.coding_printer_ref("c3-r0550", "default")
      == "L:c3-r0550@2240x1536")
check("sugar resolves to e029 seed",
      identity.resolve_format_ref(
          identity.coding_printer_ref("c2-r0700", "hp-m281-ink")).seed
      == b"holo/v1/c2-r0700/3392x2368")

# ---------------------------------------------------- symbol_bits algebra
row = identity.resolve_format_ref("L:c2-r0700@3392x2368")
check("K r0700 p100 user/symbol",
      row.streams[0].user_bits == 2748 and row.streams[0].symbol_bits == 2747)
row = identity.resolve_format_ref("L:c2-cmy8-p120-v0@3328x2304")
check("cmy8 v0 user/symbol + Y=r0547",
      all(s.user_bits == 2088 and s.symbol_bits == 2087
          for s in row.streams)
      and row.streams[2].rung_children == (("r0547", 120),))
row = identity.resolve_format_ref("L:c2-cmy8-r0700-p120-x1@3392x2368")
check("cmy8 r0700 user/symbol",
      all(s.user_bits == 2728 and s.symbol_bits == 2727
          for s in row.streams))
row = identity.resolve_format_ref("L:c2-cmy7-p120-v0@3328x2304")
check("cmy7 user/symbol",
      row.streams[0].user_bits == 5974
      and row.streams[0].symbol_bits == 5973
      and row.streams[0].rung_children
      == (("r0550", 0), ("r0625", 677), ("r0625", 677)))

# ---------------------------------------------- addressing + derived props
row = identity.resolve_format_ref("L:c2-r0700@3392x2368")
check("tiles/cells/pages",
      row.tiles_per_page == 1961 and row.max_pages == 133
      and row.payload_cells == 3996 and row.n_transmitted_slots == 3996)
ok = True
for _ in range(64):
    page = int(rng.integers(0, row.max_pages))
    ty = int(rng.integers(0, 53))
    tx = int(rng.integers(0, 37))
    c = row.tile_counter(page, ty, tx)
    ok &= c == olayout.tile_counter(page, ty, tx, (53, 37))
    ok &= row.tile_address(c) == olayout.tile_address(c, (53, 37))
check("tile_counter/tile_address parity", ok)

# ------------------------------------------------- SiteGeometry precompute
row4 = identity.resolve_format_ref("L:c2-r0700@3392x2368")
geo4 = identity.build_site_geometry(row4)
check("K geometry sites",
      eq(geo4.word_cells_yx, opilots.word_site_cells_yx(P100))
      and geo4.extra_cells_yx.shape == (0, 2)
      and eq(geo4.shorten_flat, opilots.site_cell_indices(P100, 0))
      and geo4.payload_flat.size == 3996)
oa, ob = oks.slot_perm_params(row4.seed,
                              np.arange(1961, dtype=np.int64), 3996)
check("K slot perm batch", eq(geo4.slot_a, oa) and eq(geo4.slot_b, ob))
check("K scramble plane page 0",
      geo4.scramble_planes.shape == (1, 3392, 2368)
      and eq(geo4.scramble_planes[0],
             oks.payload_bits(row4.seed, oks.PLANE_K, 0, (3392, 2368))))

rowI = identity.resolve_format_ref("L:c2-cmy8-r0700-p120-x1@3392x2368")
geoI = identity.build_site_geometry(rowI)
check("colour geometry sites (sheet I)",
      eq(geoI.word_cells_yx, opilots.word_site_cells_yx(P120))
      and eq(geoI.extra_cells_yx, opilots.dust_site_cells_yx(P120, 20))
      and eq(geoI.shorten_flat, opilots.site_cell_indices(P120, 20))
      and eq(geoI.payload_flat, opilots.color_payload_cell_indices(P120))
      and geoI.scramble_planes.shape == (0, 3392, 2368))
oa, ob = oks.slot_perm_params(rowI.seed,
                              np.arange(1961, dtype=np.int64), 3976)
check("colour slot perm batch (sheet I)",
      eq(geoI.slot_a, oa) and eq(geoI.slot_b, ob))

row7 = identity.resolve_format_ref("c3-k-r0550@7x7", n_pages=3)
geo7 = identity.build_site_geometry(row7)
oa, ob = oks.slot_perm_params(row7.seed,
                              np.arange(3 * 49, dtype=np.int64), 3996)
check("multi-page slot perm", eq(geo7.slot_a, oa) and eq(geo7.slot_b, ob))
check("multi-page scramble planes",
      geo7.scramble_planes.shape == (3, 448, 448)
      and all(eq(geo7.scramble_planes[p],
                 oks.payload_bits(row7.seed, oks.PLANE_K, p, (448, 448)))
              for p in range(3)))
check("geometry read-only",
      not geo4.slot_a.flags.writeable
      and not geoI.payload_flat.flags.writeable)

print(f"\n{N_CHECKS} checks, {len(FAILED)} failed")
if FAILED:
    for name in FAILED:
        print("FAILED:", name)
    sys.exit(1)
print("ALL GREEN")
