# PAGE-DOMAIN — the dynamic page domain

Status: v1.0, 2026-09-01. Built on `page-domain` (W0–W4). v0.2 → v0.3
after second review: the W1 rest-off pin (the missing third pin), diag
selectors pulled into W1, format-agnostic numbers, prose trimmed.
v0.3 → v0.4: §5 reframed on the address-space identity (H prices
counters × cell phase × rotation, not "pages") and the 10x10 instances
corrected — v0.3 computed them with 8-cell tiles; the tile is 64x64
cells (`TILE_CELLS = 64`). Companion: `PAGE-DOMAIN-WORKPLAN.md`.

Receiver-axis only. No format change, no emission change, no printed-
format golden touched (decoder-axis job-count pins moved with the
ladder). The fountain close never consults a page count and cannot be
disturbed. The printed word is the counter, not (page, ty, tx);
`tile_address` is the only split and it already uses `tiles_per_page`,
so every edit below is the same path on every tile matrix.

## 1. The ruling

1. The page domain is dynamic: the live set seeds `{0}` and grows to any
   legal subset of the possible set as decoded addresses warrant.
   Counter 0 is page 0 on every matrix — the prior is unique.
2. An address word committed as a placement on a not-yet-live page makes
   that page live (`store.py:672-674` already folds this and bumps
   `KEY_LIVE_PAGES` — the wake exists).
3. Floors are priced per flavour, on the flavour's PARTITION:
   cold.live on `len(live)`, cold.rest on `len(possible) − len(live)`.
   One global floor from the live set would under-price rest; pricing on
   the tried-reduced sweep subset would let a window burn the partition
   down and accept at a cheaper floor. Both rejected.
4. cold.live sweeps live; cold.rest sweeps the complement, strictly
   last by price (§6).
5. `possible = range(min(row.max_pages, bound))` where `row.max_pages =
   2^18 // tiles_per_page` (133 @53x37, 140 @52x36, 2621 @10x10,
   5349 @7x7). `--max-pages N` caps it (pages `0..N-1`; absent =
   unbounded; `N > row.max_pages` refused by name). The bound is a
   per-run admission filter — no resume guard, no stored policy.

The word route is the page-opener: admission accepts any possible page,
and precisely because it does, the W5 rival population is drawn from the
possible set (a marginal word must not instantiate a phantom page).
Rival cost is O(`row.max_pages`) whole-word scores per admission —
cheap at 133, still cheap at 2621, not free on a degenerate row pointed
at unbounded rest.

## 2. What already exists (build nothing twice)

| mechanism | where |
|---|---|
| live set grown on placement fold + wake | `store.py:95,672-674`, `KEY_LIVE_PAGES`, subscribed `place_sched.py:205` |
| live/rest partition + untried subset at fire time | `place.cold_flavour_pages` via `place_sched.cold_pages_of` (returns both) |
| cross-page rival scoring over a domain | `words.word_rival_rows(winner, candidates, domain, …)` |
| lazy per-page reference values | `ReferenceField.page()` memo dict |
| per-window cold exhaustion arming | `place_sched` `cold_armed`/`*_spent` |
| live-derived diag page list | `diag/readout.py field_pages` |

## 3. The build, in seven edits

1. `store.page_domain = possible` replaces `range(row.n_pages)`. It
   means possible everywhere — word and cold jobs alike; the live filter
   is a separate consult, never a second meaning of this tuple.
2. `store._live_pages` seeds `{0}`, not `set()`. Contract 07-7 reborn as
   a PRIOR, and load-bearing: without it, the first cold on a
   word-failed single sheet is a full-possible rest sweep at the rest
   floor, and small-support windows never rest-place.
3. Word admission filters `page in possible` (same filter, bigger set);
   `word_rival_rows` gets `possible` as its domain.
4. Cold H from the flavour's partition size — `len(live_all)` /
   `len(rest_all)`, both already returned by `cold_pages_of`
   (`place_sched.py:114-117`) — instead of the declared count
   (`place.py:751-754`). The untried subset stays the sweep. WindowPass
   carries at most one extra int.
5. Delete the `engine.py:234-235` whole-domain ReferenceField warm-up.
6. Scramble plane per page on first touch, memoized on
   `SiteGeometry._scramble` (a field, default empty — no new geometry
   type; supersedes 03-5's store-init stack:
   ~7.7 MiB/page @53x37, ~0.4 @10x10; a full stack is ~a gigabyte on
   any matrix). `slot_a`/`slot_b` stay eager: they are counter-space
   arrays, always ~2^18 tiles ≈ 2-4 MB regardless of matrix.
   `FormatRow.n_pages` DIES — the row already derives `max_pages`;
   `resolve_format_ref(ref)` loses its pages parameter;
   `DecodeRequest.n_pages` becomes `max_pages: int | None`.
7. Revisit read-subscriptions per LIVE page (`revisit.py:100-101` today
   multiplies the subscription graph by the whole domain).

And the diag seam, in the same wave as the bound (a viewer must never
grow `row.max_pages` empty page links): `page_selectors` derives from
live (the `field_pages` pattern — PoseCommitted ∪ {0}), panes clip and
refuse against possible, tile denominators count live, the format row
prints possible as a count ("133 possible"), and `RunOpen.pages` stops
being the selector source (either it carries the bound and nothing
derives pane slots from it, or it dies — build decides, trap named).

With rest (W3 only): cold tried marks become per-flavour — a page swept
as rest and later live deserves a live re-sweep at the lower floor;
today's flavourless `cold-page/p` dedup was sound only under one shared
floor.

No new types, no stored live-set schema, no instantiation ritual: a page
is live when it is in `_live_pages`, and its MiB-scale state builds on
first touch like everything else.

## 4. Supersessions (banners owed at workplan W4)

| clause | today | this design |
|---|---|---|
| 04-6 / 07-8 | `--pages N` (default 1) IS the domain | `--max-pages N` caps it; default = `row.max_pages` |
| 07-7 | `cold_first_max_pages` dropped | reborn as the `{0}` live prior |
| 03-5 | scramble planes stacked at store init | per-page on first touch |
| C-12 | `--workers N` payload-byte-identical | kept as written and as the gate; certificate-SET identity across N is explicitly dropped (floors read fire-time live state) — the banner states the narrowing, and no e2e may promise cert-set identity across workers |
| C-8 | no resume | untouched; the bound is per-run |
| C-2 | no prepared memmaps, memory bounded per job | UPHELD — the transform store is NOT built (§7) |

## 5. Floors price the address space

Formula unchanged (`min_support_for(hypothesis_count(frag, cells_yx,
n))`); only H's page operand moves (edit 4). What H actually counts is
the searched VALID ADDRESS SPACE, refined and inflated:

    H = (counters in the domain) x 4096 cell phases x 4 rotations
        x overhang(frag, page shape)

"Pages" is merely the unit in which a domain narrows the address space
at a fixed matrix (pages x tiles_per_page = counters); the overhang
factor is constant per (matrix, fragment) — measured 1.15 @53x37/200,
1.72 @10x10/200, 2.09 @7x7/200 (small pages pay proportionally more
margin). Consequence: the full possible set is ~2^18 counters on EVERY
matrix (only the floor-division remainder differs), so the full-rest
floor is ~54-56 universally — v1's "about 50-57" was an address-space
constant, never an A4 fact. Pin the FUNCTION, not any matrix's triple.
Instances (derived from the tree's own functions, constants 30/0.08/0,
window 200x200):

| matrix | 1 page | 10 | full rest |
|---|---|---|---|
| 53x37 | 43 | 48 | 54 (133p) |
| 10x10 | 36 | — | 55 (2621p) |
| 7x7 | 35 | — | 56 (5349p) |

~1.67 sites/parity per doubling of the searched address space. The
floor stays the pre-FFT eligibility mask, so the live route's lower
floor admits origins rest excludes — yield, not just cost. Accepted
consequence: small-support windows never cold-place into non-live
pages; they wait for a word to open the page and re-arm via the
`KEY_LIVE_PAGES` wake.

Lawfulness in one breath: v1 banned self-narrowing but named the escape
(`RECEIVE-DESIGN.md:415-425` — independent authority, exact page set,
floor, domain epoch). Here the authority is other windows' rival-priced
placements, the epoch is `facts_version`, and rest keeps the complement
fully priced.

## 6. Rest is last by price

cold.live is 250, cold.rest is 260 — above swim (240) and every other
recovery row. An idle worker takes the cheapest *ready* job; there is
no second gate. On a healthy non-`--complete` run the close still
preempts before rest is the head of the heap. Under `--complete` rest
is the remaining work and runs when nothing cheaper is ready. Unbounded
rest on a sheet that never closes is a derived ~60-85 cpu-hours (A4
extrapolation — census × per-fire cost); the archived census showed
~5.2k whole-sheet fires for zero poses. Price, not a dryness cliff,
is what keeps that off the ordinary path.

## 7. Rejected: the memmapped transform store

Adjudicated 2026-09-01 and NOT built. The per-page cold transform
(complex64 page rFFT; 45.8 MiB measured @53x37, 5.95 GiB derived at
133 pages — A4 instance) is rebuilt per fire today, and caching it buys
27% of a rest fire's wall (measured 0.444 → 0.324 s/page) on a tier
that must not run on a healthy sheet. C-2 stands; the invocation-local
dict stays. Reopen only if a measured rest fire on a real capture is
the wall — these numbers are the reopening brief.

## 8. Determinism

Fire-time floors on a growing live set make intermediate outcomes
schedule-dependent: certificate sets may differ across worker counts.
Kept: zero-wrong (certificates are proof-carrying; floors gate search,
not validity), C-12's letter (`--workers N` payload-byte-identical),
and convergence (the wake re-arms refused windows as live grows).

## 9. CLI

`--pages` retired → `--max-pages N`: an admission bound on the page
domain; absent = all addressable pages of the row. `--max-pages 1` is
the null-control spelling (the pre-PAGE-DOMAIN default).

## 10. Parked (not this line)

- Transform store: §7. ReferenceField eviction for rest/decoy pages:
  revisit on RSS.
- Wrong pose → random tile decode. A CRC/syndrome refuse on a
  certified-looking placement could retry the search's runner-up.
  Placements are final today (`RETIRE_PLACED`); `SearchOutcome.runner_ups`
  is computed and dropped. v1's runner-up hints and address quarantine
  are C-8. Reopens with quarantine tooling, not here.
