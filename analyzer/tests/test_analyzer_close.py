"""W2 — `analyzer.close`: production ∪ analyzer through `close_volume`.

The close is not re-implemented here; it is holo3's, called.  What these
tests check is the UNION (production certificates win, analyzer ones are
added, neither is silently dropped) and the verdict: since 2026-09-04 it
is the payload ENVELOPE's own sha — the digest the emitter wrote inside
the volume — and the close writes the recovered bytes to `payload.bin`
so the offline scorer can be pointed at them.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from analyzer import close as close_mod

from ._analyzer_fixtures import i_inputs, i_truth, needs_i_run


@needs_i_run
def test_union_keeps_production_and_adds_the_analyzer():
    run = i_inputs()
    key = (0, 0, 0, "C")
    assert key not in run.certificates          # sheet I's residue
    certs, added = close_mod.union_certificates(
        run, {key: np.zeros(run.row.streams[0].user_bits, np.uint8)})
    assert len(certs) == len(run.certificates) + 1
    assert added == (key,)
    # a key production already holds is NOT replaced
    taken = sorted(run.certificates)[0]
    certs2, added2 = close_mod.union_certificates(
        run, {taken: np.zeros(8, np.uint8)})
    assert added2 == ()
    assert len(certs2) == len(run.certificates)


@needs_i_run
def test_production_alone_closes_and_writes_the_payload(tmp_path):
    run = i_inputs()
    truth = i_truth()
    out = close_mod.close(run, {}, out_dir=tmp_path)
    print(f"\nclose (production only): status={out['status']} "
          f"k_total={out['k_total']} symbols={out['n_symbols_used']} "
          f"metadata_rank={out['metadata']['rank']} "
          f"sha={out['payload_sha256'][:12]}… verified={out['verified']}")
    assert out["status"] == "verified"
    assert out["verified"] is True
    # The envelope IS the verification (2026-09-04); that the bytes are
    # also the EMITTED ones is a separate, offline fact, checked here
    # against the generation manifest the test fixture holds.
    assert out["payload_sha256"] == truth.payload_sha256
    written = (tmp_path / close_mod.PAYLOAD_NAME).read_bytes()
    import hashlib
    assert hashlib.sha256(written).hexdigest() == out["payload_sha256"]
    assert out["payload_path"] == str(tmp_path / close_mod.PAYLOAD_NAME)
    assert out["k_total"] == run.rank_report == 5277
    assert out["metadata"]["rank"] == 24
    assert out["metadata"]["n_unique"] >= out["metadata"]["min_equations"]
    assert out["n_from_analyzer"] == 0


@needs_i_run
def test_the_union_close_still_verifies_with_analyzer_certificates():
    """DESIGN §6a: adding analyzer certificates must not break a close.

    On sheet I this is also the whole-sheet result: the three residue
    tile-streams the analyzer certifies bring the run to 5,883 of 5,883
    and the payload still comes back byte-exact.
    """
    run = i_inputs()
    truth = i_truth()
    from analyzer import fixedpoint as fp
    from analyzer import residue as residue_mod
    from analyzer.types import VERDICT_CERTIFIED, AnalyzerConfig
    from ._analyzer_fixtures import i_census
    rows = i_census()
    targets = residue_mod.residue_rows(rows)
    ledger = fp.run(run, targets,
                    AnalyzerConfig(workers=4, rules=("sum", "best"),
                                   rungs=("L0", "L1", "L2", "L3", "L7")),
                    census_rows=rows)
    certs = {row.key: row.rungs["user_bits"] for row in ledger.rows
             if row.verdict == VERDICT_CERTIFIED
             and row.rungs.get("user_bits") is not None}
    out = close_mod.close(run, certs)
    print(f"\nunion close: {out['n_from_production']} production + "
          f"{out['n_from_analyzer']} analyzer = {out['n_certificates']} "
          f"certificates, status={out['status']}, "
          f"sha={out['payload_sha256'][:12]}…, verified={out['verified']}")
    assert out["verified"] is True
    assert out["payload_sha256"] == truth.payload_sha256
    assert out["n_from_analyzer"] == len(certs)


@needs_i_run
def test_the_close_verdict_is_the_envelope_and_needs_no_manifest():
    """RULED 2026-09-04: the payload envelope is the verification.

    `close_volume` reports `verified` exactly when the sha the EMITTER
    wrote inside the volume matched what came out, so there is no
    `solved_unverified` state left and no manifest in the room: the
    close writes the bytes out and `analyzer score` can be pointed at
    them.
    """
    run = i_inputs()
    out = close_mod.close(run, {})
    assert out["status"] == "verified" and out["verified"] is True
    assert out["unverified_reason"] is None
    assert "manifest_sha256" not in out
    assert out["payload_path"] is None          # no --out, no file
    import inspect
    assert "truth" not in inspect.signature(close_mod.close).parameters


@needs_i_run
def test_the_cli_close_writes_payload_bin_and_exits_0(tmp_path):
    """PLAN §5: exit 0 on a VERIFIED close, and the bytes on disk."""
    import hashlib
    from analyzer import cli
    from ._analyzer_fixtures import I_RUN_DIR
    assert cli.main(["close", "--run-dir", str(I_RUN_DIR),
                     "--out", str(tmp_path)]) == 0
    payload = tmp_path / close_mod.PAYLOAD_NAME
    assert payload.exists()
    record = json.loads((tmp_path / "close.json").read_text("utf-8"))
    assert record["payload_sha256"] == hashlib.sha256(
        payload.read_bytes()).hexdigest()
    assert record["payload_bytes"] == payload.stat().st_size


@needs_i_run
def test_metadata_rank_is_reported_beside_the_close():
    run = i_inputs()
    out = close_mod.metadata_rank(list(run.certificates.values()), run.row)
    assert out["rank"] == 24 and out["ok"] is True
    assert out["inconsistent"] is False
    assert out["n_unique"] == len(run.certificates)


def test_as_certificate_names_its_source():
    certificate = close_mod.as_certificate((0, 1, 2, "Y"),
                                           np.zeros(4, np.uint8))
    assert certificate.stream_id == "Y" and certificate.ty == 1
    assert certificate.source == close_mod.ANALYZER_SOURCE
    assert certificate.user_bits.dtype == np.uint8


def test_as_certificate_refuses_nothing_silently():
    with pytest.raises((TypeError, ValueError)):
        close_mod.as_certificate((0, 1, 2, "Y"), "not bits")


# ===================================================================
# W7 — THE FOUNTAIN CONSISTENCY CHECK AND ITS LOCALIZATION (2026-09-04)
#
# Truth-free by construction: none of the arithmetic under test opens a
# payload.  The FIXTURES do — they rebuild sheet I's whole certificate
# set from the emitted payload through holo1's generation arithmetic, so
# the certificates the check re-encodes were produced by a DIFFERENT
# implementation of the fountain than the one doing the re-encoding, and
# the emitted sha is available to say the close landed on the right
# bytes.  That is a test rather than a tautology.
# ===================================================================

from holo3.format import close as fmt_close                      # noqa: E402
from holo3.format import fountain                                # noqa: E402

from ._analyzer_fixtures import (i_emitted_sha256,               # noqa: E402
                                 i_emitted_user_bits, i_format_row,
                                 needs_i_generation)

I_K_TOTAL = 5277
I_N_SYMBOLS = 5883
I_N_REDUNDANT = I_N_SYMBOLS - I_K_TOTAL          # 606


def _i_certificates() -> dict:
    return {key: np.asarray(bits, np.uint8).copy()
            for key, bits in i_emitted_user_bits().items()}


def _certs_of(bits_by_key) -> tuple:
    return tuple(close_mod.as_certificate(key, bits_by_key[key],
                                          source="emitted")
                 for key in sorted(bits_by_key))


def _row_index_of(row, key, bits) -> tuple[int, int, int]:
    """(block, row within the block, k of that block) for one address."""
    code = fmt_close._pooled_volume_code(row, I_K_TOTAL)
    esi = close_mod.symbol_index(row, close_mod.as_certificate(key, bits))
    block, index = code.block_row_of(esi)
    return block, index, int(code.k_per_block[block])


def _split_by_basis(row, bits_by_key) -> tuple[list, list]:
    systematic, repair = [], []
    for key in sorted(bits_by_key):
        _block, index, k_block = _row_index_of(row, key, bits_by_key[key])
        (systematic if index < k_block else repair).append(key)
    return systematic, repair


# ------------------------------------------------- what holo3 does NOT do

def test_ge_solve_ignores_a_contradictory_right_hand_side():
    """The finding the consistency check exists for, pinned directly.

    `_ge_solve_gf2` eliminates rows past the rank to zero on the LEFT and
    never looks at their right-hand sides again, so an inconsistent system
    does not raise, does not return None, and does not mark anything: it
    returns a solution of the consistent part.  Here the fourth row says
    `x0 ^ x1 = 1` while rows 0 and 1 say both are 0 — flatly impossible —
    and the solver hands back x = (0, 0, 0) with full rank.
    """
    rows = np.zeros((4, 1), np.uint64)
    rows[0, 0] = np.uint64(0b001)
    rows[1, 0] = np.uint64(0b010)
    rows[2, 0] = np.uint64(0b100)
    rows[3, 0] = np.uint64(0b011)                # x0 ^ x1
    vals = np.zeros((4, 1), np.uint64)
    vals[3, 0] = np.uint64(1)                    # ... = 1, contradicting
    rank, solved = fountain._ge_solve_gf2(rows.copy(), vals.copy(), 3)
    assert rank == 3
    assert solved is not None                    # NOT detected
    assert int(solved.sum()) == 0                # the contradiction is gone


# ------------------------------------------------------- the clean check

@needs_i_generation
def test_the_emitted_volume_is_consistent_with_606_redundant_symbols():
    row = i_format_row()
    report = close_mod.consistency(_certs_of(_i_certificates()), row)
    print(f"\nconsistency (sheet I, emitted): ok={report['ok']} "
          f"symbols={report['n_symbols']} redundant={report['n_redundant']} "
          f"consistent={report['n_consistent']} "
          f"inconsistent={report['n_inconsistent']} "
          f"{report['seconds']:.2f}s")
    assert report["ok"] is True and report["checked"] is True
    assert report["k_total"] == I_K_TOTAL
    assert report["n_symbols"] == I_N_SYMBOLS
    assert report["n_redundant"] == I_N_REDUNDANT
    assert report["n_consistent"] == I_N_SYMBOLS
    assert report["n_inconsistent"] == 0
    assert report["inconsistent_keys"] == []


@needs_i_generation
def test_below_k_the_check_is_unproven_not_failed():
    """Too few symbols to solve: `checked` False, `ok` still True.

    An unproven volume is not a poisoned one, and a caller that refuses on
    `ok` False must not be made to refuse a partial residue.
    """
    row = i_format_row()
    bits = _i_certificates()
    keys = sorted(bits)[:200]
    report = close_mod.consistency(
        _certs_of({key: bits[key] for key in keys}), row)
    assert report["checked"] is False
    assert report["ok"] is True
    assert report["proven"] is False
    assert "no fountain group could be solved" in str(report["reason"])


# ------------------------------------- a poisoned symbol OUTSIDE the basis

@needs_i_generation
def test_a_poisoned_repair_symbol_is_caught_named_and_corrected():
    row = i_format_row()
    bits = _i_certificates()
    _systematic, repair = _split_by_basis(row, bits)
    victim = repair[0]
    bits[victim][1:4] ^= 1                       # three flipped symbol bits

    report = close_mod.consistency(_certs_of(bits), row)
    assert report["ok"] is False
    assert report["n_inconsistent"] == 1
    assert report["inconsistent_keys"] == [list(victim)]
    assert report["inconsistent_bits"][
        ",".join(str(part) for part in victim)] == 3

    found = close_mod.localize(_certs_of(bits), row)
    print(f"\nlocalize (repair row poisoned): localized={found['localized']} "
          f"solves={found['n_solves']} poisoned={found['poisoned_keys']} "
          f"close={found['close']['status']} {found['seconds']:.2f}s")
    assert found["localized"] is True
    assert found["poisoned_keys"] == [list(victim)]
    assert found["n_survivors"] == I_N_SYMBOLS - 1
    evidence = found["evidence"][",".join(str(part) for part in victim)]
    assert evidence["rule"] == "direct"
    assert evidence["n_bits_disagreeing"] == 3
    # THE CLOSE ON THE SURVIVORS IS THE VERDICT, and it lands on the
    # emitted bytes — the envelope's own sha, checked here against the
    # generation manifest's, which the run never sees.
    assert found["close"]["verified"] is True
    assert found["close"]["payload_sha256"] == i_emitted_sha256()
    # THE LAST-DITCH CORRECTION: observed ^ e reproduces the emitted bits.
    name = ",".join(str(part) for part in victim)
    assert found["corrections"][name]["n_bits_flipped"] == 3
    assert np.array_equal(found["corrected_user_bits"][name],
                          i_emitted_user_bits()[victim])
    assert found["corrections_verified"]["consistent"] is True
    assert found["corrections_verified"]["n_inconsistent"] == 0


# ---------------------------------------- a poisoned symbol IN the basis

@needs_i_generation
def test_a_poisoned_source_symbol_is_localized_by_column_consensus():
    """The hard case: the poison is a SYSTEMATIC row, so the source is wrong.

    Every certificate sheet I's identity carries a systematic row for is
    present here, which is exactly when `Decoder._solve_block` takes its
    fast path and stacks the systematic symbols without ever consulting a
    repair row.  The wrong bits therefore land IN the solved source, about
    half the redundant rows disagree, and every one of their residuals is
    the same error pattern — which is what makes the AND-reduction of
    their generator rows name the poisoned column.
    """
    row = i_format_row()
    bits = _i_certificates()
    systematic, _repair = _split_by_basis(row, bits)
    victim = systematic[0]
    bits[victim][1:6] ^= 1                       # five flipped symbol bits

    # WHAT WOULD HAPPEN WITHOUT THIS CHECK: `close_volume` does not raise
    # and does not name anything — the envelope simply fails, and the
    # operator is told the volume is corrupt with no key to act on.
    plain = fmt_close.close_volume(_certs_of(bits), row)
    assert plain.status == "integrity_failure"
    assert plain.payload is None
    assert "envelope verification failed" in str(plain.reason)

    report = close_mod.consistency(_certs_of(bits), row)
    assert report["ok"] is False
    # The disagreement is a large, structured set — not one accusing row.
    assert report["n_inconsistent"] > close_mod.LOCALIZE_MIN_CONSENSUS
    assert list(victim) not in report["inconsistent_keys"]

    found = close_mod.localize(_certs_of(bits), row)
    print(f"\nlocalize (source row poisoned): "
          f"localized={found['localized']} solves={found['n_solves']} "
          f"disagreeing={report['n_inconsistent']} "
          f"poisoned={found['poisoned_keys']} {found['seconds']:.2f}s")
    assert found["localized"] is True
    assert found["poisoned_keys"] == [list(victim)]
    evidence = found["evidence"][",".join(str(part) for part in victim)]
    assert evidence["rule"] == "consensus"
    assert evidence["n_bits_disagreeing"] == 5
    assert evidence["false_candidate_bound"] < 1e-30
    assert found["close"]["verified"] is True
    assert found["close"]["payload_sha256"] == i_emitted_sha256()
    name = ",".join(str(part) for part in victim)
    assert np.array_equal(found["corrected_user_bits"][name],
                          i_emitted_user_bits()[victim])
    assert found["corrections_verified"]["consistent"] is True


@needs_i_generation
def test_two_poisoned_repair_symbols_are_both_named_in_one_round():
    row = i_format_row()
    bits = _i_certificates()
    _systematic, repair = _split_by_basis(row, bits)
    victims = sorted((repair[0], repair[7]))
    bits[victims[0]][2] ^= 1
    bits[victims[1]][5:9] ^= 1
    found = close_mod.localize(_certs_of(bits), row)
    print(f"\nlocalize (two repair rows): poisoned={found['poisoned_keys']} "
          f"rounds={found['n_rounds']}")
    assert found["localized"] is True
    assert found["poisoned_keys"] == [list(key) for key in victims]
    assert found["n_rounds"] == 2            # one accusing round, one clean
    assert found["close"]["payload_sha256"] == i_emitted_sha256()


@needs_i_generation
def test_localize_says_so_when_the_system_was_never_poisoned():
    row = i_format_row()
    found = close_mod.localize(_certs_of(_i_certificates()), row)
    assert found["localized"] is False
    assert found["poisoned_keys"] == []
    assert found["reason"] == "the system was consistent to begin with"
    assert found["close"]["verified"] is True


@needs_i_generation
def test_the_work_localize_does_is_bounded_and_reported():
    """`max_rounds` is a stated bound, not an aspiration."""
    row = i_format_row()
    bits = _i_certificates()
    _systematic, repair = _split_by_basis(row, bits)
    bits[repair[0]][1] ^= 1
    found = close_mod.localize(_certs_of(bits), row, max_rounds=0)
    assert found["localized"] is False
    assert found["n_solves"] == 1
    assert found["max_rounds"] == 0
    assert "still inconsistent after 0 exclusion round(s)" in found["reason"]


@needs_i_generation
def test_a_clean_recheck_with_no_redundancy_left_is_not_a_localization():
    """Dropping symbols until `have == K` makes consistency VACUOUS.

    The floor is what stops `localize` from "succeeding" by excluding the
    evidence: a re-check that passes with nothing redundant left proves
    nothing, and the report says `redundancy_exhausted` rather than
    claiming a poisoned key was found.
    """
    row = i_format_row()
    bits = _i_certificates()
    _systematic, repair = _split_by_basis(row, bits)
    for key in repair[:4]:
        bits[key][1] ^= 1
    found = close_mod.localize(
        _certs_of(bits), row, min_redundancy=I_N_REDUNDANT + 1)
    assert found["localized"] is False
    assert "become vacuous" in str(found["reason"])
    assert len(found["poisoned_keys"]) == 4


@needs_i_generation
def test_a_check_at_exactly_k_is_vacuous_and_says_so():
    """`ok` True with nothing redundant is SILENCE, not a clean bill.

    Handed exactly the systematic rows, the solve IS the stack of those
    rows and every one of them re-encodes to itself — so a poisoned
    symbol among them lands in the source and is then re-encoded from the
    source it corrupted.  The check reports `ok` True (nothing disagreed)
    and `checked` True (a solve happened) while `close_volume` on the same
    certificates fails its envelope.  That is exactly why `proven` exists:
    `n_redundant` is 0 here and nothing was tested.  Reviewer probe,
    2026-09-04.
    """
    row = i_format_row()
    bits = _i_certificates()
    systematic, _repair = _split_by_basis(row, bits)
    exact = {key: bits[key] for key in systematic}
    exact[systematic[5]][1:4] ^= 1
    report = close_mod.consistency(_certs_of(exact), row)
    assert report["n_symbols"] == I_K_TOTAL
    assert report["checked"] is True
    assert report["ok"] is True
    assert report["n_redundant"] == 0
    assert report["n_inconsistent"] == 0
    assert report["proven"] is False
    assert "VACUOUS" in str(report["reason"])
    # The envelope is the only verdict left on such a volume, and it fails.
    assert fmt_close.close_volume(_certs_of(exact), row).status == \
        "integrity_failure"


@needs_i_generation
def test_a_mixed_poison_refuses_rather_than_guessing():
    """One systematic AND one repair symbol poisoned: no name, no guess.

    D is large (the basis poison makes about half the redundant rows
    disagree) but the residuals are NOT one common error pattern, because
    the poisoned repair row carries its own.  The consensus rule is
    therefore inapplicable and `localize` says so instead of accusing a
    column.  Pinned as the known limit of the two-signature rule
    (reviewer probe, 2026-09-04): the refusal is honest, and the close on
    the un-excluded set still reports the envelope's failure.
    """
    row = i_format_row()
    bits = _i_certificates()
    systematic, repair = _split_by_basis(row, bits)
    bits[systematic[3]][1:6] ^= 1
    bits[repair[11]][7:9] ^= 1
    found = close_mod.localize(_certs_of(bits), row)
    assert found["localized"] is False
    assert found["poisoned_keys"] == []
    assert "does not name a symbol" in str(found["reason"])
    assert found["close"]["verified"] is False
    rules = {str(item.get("rule")) for item in found["rounds"][0]["detail"]}
    assert "refused" in rules


@needs_i_generation
def test_the_clean_sheet_i_check_is_proven():
    """The same field the other way: 606 redundant comparisons ran."""
    report = close_mod.consistency(_certs_of(_i_certificates()),
                                   i_format_row())
    assert report["proven"] is True
    assert report["n_redundant"] == I_N_REDUNDANT


# --------------------------------------------------- the close's own door

@needs_i_generation
def test_close_carries_the_consistency_report_and_localizes_on_request():
    """`close(..., localize_poison=True)` is one call end to end.

    MEASURED HERE, and the whole reason this check is not redundant with
    the close: a poisoned REPAIR symbol leaves the close VERIFIED.  Every
    systematic row of sheet I's identity is present, so
    `Decoder._solve_block` takes its fast path and never reads a repair
    row at all — the envelope passes, the payload is byte-exact, and the
    volume nonetheless carries a certificate that cannot have come from
    it.  Only the re-encoding sees it, and only `--localize` names it.
    """
    class _Inputs:
        pass

    row = i_format_row()
    bits = _i_certificates()
    _systematic, repair = _split_by_basis(row, bits)
    victim = repair[0]
    bits[victim][3] ^= 1
    run = _Inputs()
    run.row = row
    run.rank_report = I_K_TOTAL
    run.certificates = {key: close_mod.as_certificate(key, value,
                                                      source="emitted")
                        for key, value in bits.items()}
    out = close_mod.close(run, {}, localize_poison=True)
    assert out["verified"] is True                 # the close saw nothing
    assert out["payload_sha256"] == i_emitted_sha256()
    assert out["consistency"]["ok"] is False       # the re-encoding did
    assert out["consistency"]["inconsistent_keys"] == [list(victim)]
    assert out["localize"]["poisoned_keys"] == [list(victim)]
    assert out["localize"]["close"]["payload_sha256"] == i_emitted_sha256()


@needs_i_generation
def test_a_poison_inside_the_basis_is_what_makes_the_close_itself_fail():
    """The companion to the case above, and the contrast that names it.

    A poisoned SYSTEMATIC symbol lands in the solved source, so the
    envelope catches it and `close` refuses — but with no key and no
    correction, which is the whole gap `--localize` fills.
    """
    class _Inputs:
        pass

    row = i_format_row()
    bits = _i_certificates()
    systematic, _repair = _split_by_basis(row, bits)
    victim = systematic[0]
    bits[victim][3] ^= 1
    run = _Inputs()
    run.row = row
    run.rank_report = I_K_TOTAL
    run.certificates = {key: close_mod.as_certificate(key, value,
                                                      source="emitted")
                        for key, value in bits.items()}
    out = close_mod.close(run, {}, localize_poison=True)
    assert out["verified"] is False
    assert out["status"] == "integrity_failure"
    assert out["payload_sha256"] is None
    assert out["consistency"]["ok"] is False
    assert out["localize"]["poisoned_keys"] == [list(victim)]
    assert out["localize"]["close"]["verified"] is True
    assert out["localize"]["close"]["payload_sha256"] == i_emitted_sha256()


@needs_i_generation
def test_close_without_the_check_asks_the_fountain_nothing():
    row = i_format_row()

    class _Inputs:
        pass

    run = _Inputs()
    run.row = row
    run.rank_report = I_K_TOTAL
    run.certificates = {
        key: close_mod.as_certificate(key, value, source="emitted")
        for key, value in _i_certificates().items()}
    out = close_mod.close(run, {}, check_consistency=False)
    assert "consistency" not in out
    assert out["verified"] is True
    assert out["payload_sha256"] == i_emitted_sha256()
