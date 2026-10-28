#!/usr/bin/env python3
"""e018b — generic single-page C3/C2 K-plane payload-sheet encoder.

This is the reusable form of the two earlier one-off generators:

* e018 supplies the frozen layout-version-3 C3 page geometry.
* e016 supplies the frozen layout-version-3 C2 black-only page geometry.

For either profile, the input file's bytes are carried verbatim through
fountain-v1 -> per-tile r0550 LDPC + CRC-32 -> compose_page -> one whole-page
K imagemask.  The source-symbol budget is capped at half of the page's
interior tiles, so K/N <= 0.5.  Smaller files are not padded with invented
data; they receive proportionally more repair headroom.

The volume seed is a fixed, public profile constant known before decode:

    c3: paper-store/018b-c3-r0550-0.5
    c2: paper-store/018b-c2-r0550-0.5

The key deliberately does NOT depend on payload bytes or their hash: a
receiver can select the profile and know the key before recovering the
payload.  The manifest remains part of the volume descriptor because
fountain-v1 does not yet put the payload length or payload hash in-band.

Usage, from the repository root:

    env/bin/python experiments/018b-payload-sheet/gen_e018b.py capacity
    env/bin/python experiments/018b-payload-sheet/gen_e018b.py capacity c3
    env/bin/python experiments/018b-payload-sheet/gen_e018b.py emit \
        c3 payload.tar.zst
    env/bin/python experiments/018b-payload-sheet/gen_e018b.py emit \
        c2 payload.tar.zst -o build/archive-c2.ps

The tool only emits files.  It never invokes the printer; physical printing
still requires explicit in-session authorization under .claude/rules/hardware.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import fountain, ldpc  # noqa: E402
from paperholo.compose import ComposeSpec, compose_page, emit_composed  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

EXP = Path(__file__).resolve().parent
BUILD = EXP / "build"

LDPC_RATE_ID = "r0550"
FOUNTAIN_K_NUMERATOR = 1
FOUNTAIN_K_DENOMINATOR = 2
PS_BUDGET_BYTES = 30_000_000


@dataclass(frozen=True)
class SheetProfile:
    """One frozen single-page K-binary geometry."""

    name: str
    encoding_id: str
    page_cells_yx: tuple[int, int]
    x_dots: int
    y_dots: int
    seed: bytes

    def make_spec(self) -> ComposeSpec:
        """Return the complete layout-version-3 ComposeSpec."""
        return ComposeSpec(
            layout_version=3,
            encoding_id=self.encoding_id,
            plane="K",
            pilot=PilotLayout(version=3),
            page_cells_yx=self.page_cells_yx,
            x_dots=self.x_dots,
            y_dots=self.y_dots,
        )


PROFILES: dict[str, SheetProfile] = {
    # Byte-identical geometry to gen_e018.make_spec() / the e012 archive page.
    "c3": SheetProfile(
        name="c3",
        encoding_id="kcell-c3",
        page_cells_yx=(2220, 1500),
        x_dots=230,
        y_dots=178,
        seed=b"paper-store/018b-c3-r0550-0.5",
    ),
    # Byte-identical geometry to gen_e016.make_spec() / the e014 C2 page.
    "c2": SheetProfile(
        name="c2",
        encoding_id="kcell-c2",
        page_cells_yx=(3300, 2220),
        x_dots=260,
        y_dots=208,
        seed=b"paper-store/018b-c2-r0550-0.5",
    ),
}
PROFILE_ORDER = ("c3", "c2")


def _max_pilot_sites_per_interior_tile() -> int:
    """Universal pilot-shortening bound for the frozen p60b6 / 64-cell tile.

    A 64-cell interval contains every residue modulo 60 once and four
    consecutive residues twice.  A four-residue duplicate band can touch at
    most two of the ten 6-cell pilot blocks on an axis.  Therefore a 64x64
    LDPC tile contains at most:

        100 base sites + 2*10 y-strip + 2*10 x-strip + 2*2 corner = 144.

    This is an adversarial bound over every possible seed-derived in-block
    pilot offset, not a sample over seeds.  Tests also verify it by exhaustive
    phase/offset maximization so the advertised capacity cannot silently
    become optimistic.
    """
    layout = PilotLayout(version=3)
    period = layout.period_cells
    block = layout.block_cells
    tile = ldpc.TILE_CELLS
    if (period, block, tile) != (60, 6, 64):
        raise RuntimeError(
            "e018b capacity proof is frozen to p60b6 pilots and 64-cell "
            f"LDPC tiles, got p{period}b{block} / {tile}"
        )
    blocks_per_axis = period // block
    duplicate_residues = tile - period
    if not 0 < duplicate_residues < block:
        raise RuntimeError("e018b pilot bound needs 0 < tile-period < block")
    touched_blocks = 2
    return (
        blocks_per_axis**2
        + 2 * touched_blocks * blocks_per_axis
        + touched_blocks**2
    )


MAX_PILOT_SITES_PER_INTERIOR_TILE = _max_pilot_sites_per_interior_tile()
PROVEN_MIN_SYMBOL_BITS = (
    ldpc.LDPC_LADDER[LDPC_RATE_ID].k_bits
    - ldpc.CRC_BITS
    - MAX_PILOT_SITES_PER_INTERIOR_TILE
)


@dataclass(frozen=True)
class Capacity:
    """Exact fixed-key payload capacity for one profile."""

    profile: str
    n_symbols_total: int
    max_source_symbols: int
    symbol_bits: int
    payload_bytes: int
    net_bits_per_mm2: float

    @property
    def max_k_over_n(self) -> float:
        return self.max_source_symbols / self.n_symbols_total

    def as_dict(self) -> dict:
        return {
            "profile": self.profile,
            "safe_payload_bytes": self.payload_bytes,
            "safe_payload_kib": round(self.payload_bytes / 1024.0, 2),
            "n_symbols_total": self.n_symbols_total,
            "max_source_symbols": self.max_source_symbols,
            "repair_symbols_at_capacity": (
                self.n_symbols_total - self.max_source_symbols
            ),
            "symbol_bits": self.symbol_bits,
            "proven_min_symbol_bits": PROVEN_MIN_SYMBOL_BITS,
            "max_k_over_n": round(self.max_k_over_n, 6),
            "ldpc_rate_id": LDPC_RATE_ID,
            "net_bits_per_mm2": round(self.net_bits_per_mm2, 2),
        }


def get_profile(name: str) -> SheetProfile:
    """Look up a user-facing profile name with a useful error."""
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(
            f"unknown profile {name!r}; choose one of {', '.join(PROFILE_ORDER)}"
        ) from exc


def make_spec(profile: str) -> ComposeSpec:
    """Public helper used by tests and future decode tooling."""
    return get_profile(profile).make_spec()


def capacity_for(profile: str) -> Capacity:
    """Return the exact fixed-key K/N<=0.5 capacity of one profile."""
    sheet = get_profile(profile)
    spec = sheet.make_spec()
    probe = fountain.VolumeSpec(
        n_pages=1,
        data_len_bytes=1,
        seed=sheet.seed,
        ldpc_rate_id=LDPC_RATE_ID,
        compose_spec=spec,
    )
    n_symbols = probe.n_symbols_total
    max_source = (
        n_symbols * FOUNTAIN_K_NUMERATOR // FOUNTAIN_K_DENOMINATOR
    )
    if probe.symbol_bits < PROVEN_MIN_SYMBOL_BITS:
        raise AssertionError(
            f"fixed {profile} key gives S={probe.symbol_bits} < proven "
            f"minimum {PROVEN_MIN_SYMBOL_BITS}"
        )
    payload_bytes = max_source * probe.symbol_bits // 8
    h_dots, w_dots = spec.field_dots_yx
    area_mm2 = (
        h_dots * 25.4 / 600.0
        * w_dots * 25.4 / 600.0
    )
    return Capacity(
        profile=profile,
        n_symbols_total=n_symbols,
        max_source_symbols=max_source,
        symbol_bits=probe.symbol_bits,
        payload_bytes=payload_bytes,
        net_bits_per_mm2=payload_bytes * 8 / area_mm2,
    )


@dataclass(frozen=True)
class SheetPlan:
    """Validated encode plan before expensive LDPC/composition work."""

    profile: SheetProfile
    data: bytes
    payload_sha256: str
    seed: bytes
    capacity: Capacity
    spec: ComposeSpec
    vspec: fountain.VolumeSpec


def plan_payload(profile: str, data: bytes) -> SheetPlan:
    """Validate payload size and construct the complete volume descriptor."""
    if not data:
        raise ValueError("payload file must be non-empty")
    cap = capacity_for(profile)
    if len(data) > cap.payload_bytes:
        raise ValueError(
            f"{profile} payload is {len(data):,} bytes, above the fixed-key "
            f"K/N<=0.5 capacity of {cap.payload_bytes:,} bytes"
        )

    digest = hashlib.sha256(data).hexdigest()
    sheet = get_profile(profile)
    volume_seed = sheet.seed
    spec = sheet.make_spec()
    vspec = fountain.VolumeSpec(
        n_pages=1,
        data_len_bytes=len(data),
        seed=volume_seed,
        ldpc_rate_id=LDPC_RATE_ID,
        compose_spec=spec,
    )
    fountain.volume_geometry(vspec)

    if vspec.symbol_bits != cap.symbol_bits:
        raise AssertionError(
            f"fixed-key capacity drift: live S={vspec.symbol_bits}, "
            f"advertised S={cap.symbol_bits}"
        )
    if vspec.n_symbols_total != cap.n_symbols_total:
        raise AssertionError("profile interior-tile count changed")
    if vspec.k_total > cap.max_source_symbols:
        raise AssertionError(
            f"fixed-key capacity admitted K={vspec.k_total} > "
            f"{cap.max_source_symbols}"
        )

    return SheetPlan(
        profile=sheet,
        data=data,
        payload_sha256=digest,
        seed=volume_seed,
        capacity=cap,
        spec=spec,
        vspec=vspec,
    )


def default_output_path(plan: SheetPlan) -> Path:
    """Content-addressed default under the experiment's ignored build dir."""
    return BUILD / (
        f"e018b-{plan.profile.name}-{plan.payload_sha256[:12]}.ps"
    )


def _print_path(out_ps: Path) -> str:
    """Prefer a repository-relative path in the manifest print command."""
    try:
        display = out_ps.resolve().relative_to(ROOT.resolve())
    except ValueError:
        display = out_ps.resolve()
    return shlex.quote(str(display))


def emit_sheet(
    payload_path: Path,
    profile: str,
    *,
    output_path: Path | None = None,
) -> dict:
    """Encode one payload file and emit PS, manifest, and exact-dot GT."""
    data = payload_path.read_bytes()
    plan = plan_payload(profile, data)
    out_ps = output_path if output_path is not None else default_output_path(plan)
    if out_ps.suffix.lower() != ".ps":
        raise ValueError(f"output path must end in .ps, got {out_ps}")

    framed = fountain.encode_volume_pages(plan.data, plan.vspec)[0]
    composed = compose_page(
        framed["payload_bits"], plan.spec, plan.seed, page=0
    )

    artifact = (
        f"e018b_{plan.profile.name}_{plan.payload_sha256[:12]}"
    )
    kn = plan.vspec.k_total / plan.vspec.n_symbols_total
    manifest = emit_composed(
        composed,
        out_ps,
        title=(
            f"paperholo e018b {plan.profile.name} generic payload volume"
        ),
        artifact=artifact,
        experiment="018b-payload-sheet",
        print_command=(
            "scripts/print_plane.sh " + _print_path(out_ps)
        ),
        extra_manifest={
            "artifact": artifact,
            "run": "018b.0",
            "profile": plan.profile.name,
            "format": {
                "format_id": f"e018b-v3-{plan.profile.name}",
                "layout_version": plan.spec.layout_version,
                "encoding_id": plan.spec.encoding_id,
                "plane": plan.spec.plane,
                "page_cells_yx": list(plan.spec.page_cells_yx),
                "x_dots": plan.spec.x_dots,
                "y_dots": plan.spec.y_dots,
                "ldpc_rate_id": LDPC_RATE_ID,
                "seed": plan.seed.decode("ascii"),
            },
            "payload": {
                "input_name": payload_path.name,
                "data_len_bytes": len(plan.data),
                "data_sha256": plan.payload_sha256,
                "stored_verbatim": True,
            },
            "seed_policy": "fixed public profile constant",
            "volume": {
                "fountain_version": fountain.FOUNTAIN_VERSION,
                "n_pages": 1,
                "data_len_bytes": plan.vspec.data_len_bytes,
                "data_sha256": plan.payload_sha256,
                "ldpc_rate_id": LDPC_RATE_ID,
                "k_total": plan.vspec.k_total,
                "n_symbols_total": plan.vspec.n_symbols_total,
                "repair_symbols": (
                    plan.vspec.n_symbols_total - plan.vspec.k_total
                ),
                "symbol_bits": plan.vspec.symbol_bits,
                "k_over_n": round(kn, 6),
                "k_over_n_max": 0.5,
                "rank_overhead_reserved": False,
            },
            "capacity": {
                **plan.capacity.as_dict(),
                "policy": (
                    "exact fixed-key limit; smaller payloads get more "
                    "repair headroom"
                ),
            },
        },
    )
    if manifest["ps_bytes"] > PS_BUDGET_BYTES:
        raise AssertionError(
            f"PS is {manifest['ps_bytes']:,} bytes, above the "
            f"{PS_BUDGET_BYTES:,}-byte experiment budget"
        )
    return manifest


def _capacity_names(name: str) -> tuple[str, ...]:
    return PROFILE_ORDER if name == "all" else (name,)


def print_capacity(name: str = "all", *, as_json: bool = False) -> None:
    """Print one or both stable capacities for shell use."""
    rows = [capacity_for(profile).as_dict() for profile in _capacity_names(name)]
    if as_json:
        print(json.dumps({"profiles": rows}, indent=2))
        return
    for row in rows:
        print(
            f"{row['profile']}: {row['safe_payload_bytes']:,} bytes "
            f"({row['safe_payload_kib']:.2f} KiB), "
            f"K/N <= {row['max_source_symbols']}/"
            f"{row['n_symbols_total']} = {row['max_k_over_n']:.3f}, "
            f"S = {row['symbol_bits']} bits, "
            f"{row['ldpc_rate_id']}, "
            f"{row['net_bits_per_mm2']:.2f} net b/mm^2"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Emit one archive-style C3 or C2 K-plane sheet from a payload "
            "file, using r0550 LDPC and fountain K/N <= 0.5."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser(
        "capacity",
        help="print the exact fixed-key payload capacity",
    )
    cap.add_argument(
        "profile",
        nargs="?",
        default="all",
        choices=(*PROFILE_ORDER, "all"),
    )
    cap.add_argument("--json", action="store_true", help="machine-readable output")

    emit = sub.add_parser("emit", help="encode a payload file into one PS sheet")
    emit.add_argument("profile", choices=PROFILE_ORDER)
    emit.add_argument("payload", type=Path)
    emit.add_argument("-o", "--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "capacity":
        print_capacity(args.profile, as_json=args.json)
        return 0

    t0 = time.time()
    try:
        manifest = emit_sheet(
            args.payload,
            args.profile,
            output_path=args.output,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_ps = (
        args.output
        if args.output is not None
        else EXP / "build" / manifest["ps_file"]
    )
    volume = manifest["volume"]
    capacity = manifest["capacity"]
    print(
        f"wrote {out_ps} ({manifest['ps_bytes'] / 1e6:.2f} MB); "
        f"{volume['data_len_bytes']:,}/{capacity['safe_payload_bytes']:,} "
        f"payload bytes"
    )
    print(
        f"volume: {volume['k_total']} source + "
        f"{volume['repair_symbols']} repair = "
        f"{volume['n_symbols_total']} symbols x "
        f"{volume['symbol_bits']} bits; K/N {volume['k_over_n']:.4f}, "
        f"{volume['ldpc_rate_id']}"
    )
    print(f"data sha256 {volume['data_sha256']}")
    print(f"ps   sha256 {manifest['ps_sha256']}")
    print(f"manifest {out_ps.with_name(out_ps.stem + '_manifest.json')}")
    print(f"({time.time() - t0:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
