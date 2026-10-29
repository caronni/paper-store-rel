# RECEIVE-DESIGN.md §8 — discovery clauses (archived verbatim)

Copied verbatim, with original line numbers, from `docs/RECEIVE-DESIGN.md`
at f006abc (branch `receiver-retirement`). `docs/RECEIVE-DESIGN.md` itself
is not archived — it stays as the normative record for the rest of the v1
receiver and gets its own retirement header in Phase 4.4 — but its
discovery-specific clauses are quoted here in full so a future port does
not have to search a superseded design doc for them. Every excerpt below
is unedited prose from that file; only the line-number labels are added.

## The discovery-first entry (lines 1341-1365)

This is the paragraph the port brief and this archive's README cite as the
primary definition of cold format discovery.

> 1341: The default CLI entry is discovery-first. `format/registry.py` supplies the
> 1342: frozen complete-row domain. `discovery_state.py` persists only the discovery
> 1343: policy id, requested rows, cross-row placement-domain envelope, authenticated
> 1344: capture facts plus the native E021 `c` decision, and isolated exact-row
> 1345: `SessionState` branches; candidate ids come from those branches, and
> 1346: per-candidate completion, c-based exclusion, the selected row, root status,
> 1347: and decoder count are derived directly — no parallel prune, trial, or
> 1348: selection ledger. E021 `c` votes only exclude incompatible cell families;
> 1349: each surviving row runs the unchanged E022→E023 branch under the global
> 1350: hypothesis envelope. Exactly one row with a CRC tile certificate is
> 1351: provisionally selected; a certificate from any other row is a terminal format
> 1352: conflict, and a second row certificate stops nested work at that exact
> 1353: committed barrier. Root verification waits until every candidate/acquisition
> 1354: pair in the current round is derivably complete or c-excluded; a deliberately
> 1355: interrupted, partially active exact-row call is not complete. Native
> 1356: discovery facts and every branch ingest are SHA-bound to the same bytes;
> 1357: resume reauthenticates those facts instead of rerunning E021, and every
> 1358: ACTIVE branch capture must be present in a resume request (since v0.33
> 1359: multiple captures are legally ACTIVE; the phased driver advances them
> 1360: rung-major within each branch). Per-scale E023c lanes
> 1361: still execute their own E021 survey, including the native lane, so discovery
> 1362: retains only the native `c` decision used to exclude incompatible rows rather
> 1363: than duplicating exact-row E021 products. The root exposes the receiver-wide
> 1364: count of all actual CRC decoder invocations. `--coding` remains an optional
> 1365: exact-row narrowing/debugging path.

## Persisted-state authority: discovery derivations (lines 1449-1458)

Part of the general "persisted state follows authority, not presentation
convenience" clause; the sentence spanning 1455-1457 is discovery-specific
(the schema-version fact and the "discovery completion/selection/status are
derived" rule).

> 1449: Persisted state follows authority rather than presentation convenience:
> 1450: `LevelRecord.status` and its operational stage/disposition view derive from
> 1451: the survey/address/payload artifact prefix; `CaptureRecord.status` and the
> 1452: next lane derive from the complete scale plan and number of retained levels;
> 1453: `SessionState.status` derives from the close record; level ordinal, lane,
> 1454: scale, source identity, dtype, and shape come from the owning capture and
> 1455: plan rather than being copied into every level; discovery completion,
> 1456: selection, and status are derived as described above. The current strict
> 1457: schemas are receiver 24 and discovery 10; no migration or compatibility
> 1458: decoder is maintained.

(Schema numbers are as of this sha; discovery_state.py's own
`DISCOVERY_SCHEMA_VERSION` had since advanced to 12 with additional
migrations — see this archive's README for the reconciliation.)

## §8.1 Invocation-only deferred close — the discovery carve-outs

§8.1 as a whole specifies `holo decode --complete`, a mechanism shared by
exact-row and discovery receive alike. The excerpts below are the
sentences within it that name discovery's own behavior under that flag;
surrounding lines are included where needed for the sentence to parse.

Receiver-wide discovery performs its one final close only for the
uniquely recognized branch (lines 1526-1536):

> 1526: validated, source-authenticated,
> 1527: persisted atomically, and exposed to the next lane, but their session close
> 1528: remains `open`; after the invocation's final requested barrier, one
> 1529: exact-row session
> 1530: invokes the installed close processor exactly once over its final certificate
> 1531: frontier and persists that result, and receiver-wide discovery performs that
> 1532: one final check only for its uniquely recognized branch — once every
> 1533: candidate/acquisition pair is c-excluded, terminal, or has committed its
> 1534: flag-bounded prefix — never once per
> 1535: candidate row or capture-shaped child call. This includes the K and color advisory
> 1536: precloses: because they call the fountain implementation, both are suppressed

`--complete` is invocation-only and absent from the discovery schema
(lines 1549-1550):

> 1549: The flag is invocation-only, absent from the semantic pipeline policy and
> 1550: receiver/discovery schemas, creates no lane, and changes no numerical gate.

Validated loading, discovery-state hashing and saves, and the automatic
discovery boundary itself (lines 1558-1577):

> 1558: Validated loading, discovery-state hashing, and discovery-state saves preserve
> 1559: the same invocation boundary. Ordinary validation reproduces the close
> 1560: processor and therefore requires an `open` record to remain numerically open;
> 1561: only a `--complete` invocation may structurally validate any frontier without
> 1562: asking the fountain during load, hashing, or save. Open-but-solvable is the
> 1563: legal state throughout deferred reception and across a crash between the final
> 1564: retained barrier and the deferred close. At the common final phase, an exact
> 1565: session or uniquely selected discovery branch performs one close: a completed
> 1566: open frontier may apply its final result; a retained terminal close is only
> 1567: reproduced and compared, never reopened or changed; a verified replay must
> 1568: also reproduce its payload bytes. An unrecognized or receiver-wide-conflicted
> 1569: discovery root has no selected interpretation to solve and performs no
> 1570: fountain call. No persisted marker or schema axis is introduced. Automatic
> 1571: discovery obeys the same boundary across its internal child calls and must
> 1572: not accidentally close once per capture-shaped call: candidate branches
> 1573: finish their requested acquisition work first, then only the uniquely
> 1574: recognized branch is checked once on its final frontier. A certificate from a
> 1575: second row remains an integrity-fatal format conflict independent of fountain
> 1576: scheduling; having no selected interpretation, it is structurally validated
> 1577: but not fountain-solved.

## Scope note

§8's other bullets (binding rules at 1367-1429, the certified-work-boundary
clauses of §8.2 at and after 1579) apply to the receiver generally — exact
rows and discovery rows both — and are not reproduced here; they stay with
the living `docs/RECEIVE-DESIGN.md`. Every "discovery" occurrence within
§8 (lines 1335-1666) is accounted for above.
