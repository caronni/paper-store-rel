"""Checked anchors for the production E023c cascade qualification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023c-scale-space-receiver"
REPORT = EXP / "E023C-CASCADE-HP1200.json"
C2_REPORT = EXP / "E023C-CASCADE-HP1200-C2.json"
QUALIFIER = EXP / "qualify_e023c_cascade.py"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

import qualify_e023c_cascade as qualify  # noqa: E402
import run_e023c  # noqa: E402


# This independently pins the complete numerical SOURCE closure that the
# qualifier compares with the receiver state.  Update it only together with
# a fresh blind state and regenerated qualification report.  Runtime
# environment rows (``lower:runtime:*`` — installed numpy/scipy/tifffile/
# Pillow/python versions) are deliberately excluded since 2026-07-30: the
# venv legitimately moves between qualification campaigns, the frozen
# report still records the qualified environment, and CI pins sources.
QUALIFIED_IMPLEMENTATION_AGGREGATE_SHA256 = (
    "1f89006817d7827c3731465069d59ded7d5554dea8dee1ba16d0fcae4b5f53af")
OBSERVER_ONLY_IMPLEMENTATION_AGGREGATE_SHA256 = (
    "0a65566922168c965919a227fe0864a4b0a3a8c173b596cad12aabdb1d8b83bc")
OBSERVER_ONLY_FINGERPRINT_DELTA = {
    "e023c:cascade": {
        "qualified": (
            "a085daaa5ac0b9623546050c7fe85a3450677657cd939f0fdf75dad77156a91b"),
        "live": (
            "ae6ad7646792fddbf3c07707e29a38d028c7f5292908c7329629a4555ca7059a"),
    },
    "e023c:run": {
        "qualified": (
            "01c3ef3527ac51b81333e65a38544cae1c83622447243307394ba56dcba68c29"),
        "live": (
            "9aa2305f7f8e5c3c1211fc3246a8ff60861a19f0d782ca4944e8861ac0162485"),
    },
    "lower:paperholo.pilotsearch": {
        "qualified": (
            "1fa18faf682815f6b2605a417bdc64b5c4429320fb7101bbc563249130bdeee2"),
        "live": (
            "632857d02fa2e4d8568ac245e6d71e4723a04fdef8526d43a0bbca87c9bd62c6"),
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _report() -> dict:
    return json.loads(REPORT.read_text())


def _c2_report() -> dict:
    return json.loads(C2_REPORT.read_text())


def _implementation_aggregate(fingerprints) -> str:
    payload = json.dumps(
        tuple(fingerprints),
        separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def test_qualification_scope_comes_from_manifest_and_state() -> None:
    for profile in ("c2", "c3"):
        format_id = f"e018b-v3-{profile}"
        session = SimpleNamespace(envelope=SimpleNamespace(
            native_dpi=1200.0, format_id=format_id))
        manifest = SimpleNamespace(profile=profile)
        assert qualify._qualification_scope(session, manifest) == (
            f"single 1200-dpi physical capture for profile {profile} / "
            f"format {format_id}; architectural and numerical "
            "qualification, not cross-scanner generalization"
        )


def test_c2_production_report_is_frozen_and_qualified() -> None:
    report = _c2_report()
    assert _sha256(C2_REPORT) == (
        "ede948168a737d67f268f3ce340639e8951914bfc515e0b1ff825efbf6f3867c")
    assert report["status"] == "QUALIFIED_SINGLE_CAPTURE"
    assert report["gates_ok"] is True
    assert all(report["gates"].values())
    assert report["scope"] == (
        "single 1200-dpi physical capture for profile c2 / format "
        "e018b-v3-c2; architectural and numerical qualification, not "
        "cross-scanner generalization")
    assert report["qualifier"]["sha256"] == _sha256(QUALIFIER)
    assert report["implementation"]["matches"] is True
    assert report["implementation"]["stored"] == (
        report["implementation"]["current"])
    assert report["schedule_control"] is None

    assert report["state"]["attempt_records"] == 3165
    assert report["state"]["authoritative_sha256"] == (
        "0adfa6f2dc493aed02f760bac496a7771dbe0af34bef82bf43c6701e3578367a")
    assert report["state"]["file_sha256"] == (
        "319e93ce7e2943d436781d88f1cb8f9c0ff75222d4d4ac85ad73a13ece844044")
    assert {
        level: row["certified_after_retry"]
        for level, row in report["lanes"].items()
    } == {
        "l00-2ppc-600dpi": 1310,
        "l01-4ppc-1200dpi": 128,
    }
    assert report["portfolio"] == {
        "certified": 1438,
        "certificate_set_sha256": (
            "1c2d01a42ff1ed91088d8757bf253a45f3dcf5f4ae37b4dba9e71c9a89c00d73"),
        "certificate_bits_sha256": (
            "79fc0abc0d04f61c42db20b04ab2a1562f6ad9243c36df26eae728a0dd4c4106"),
        "wrong_certificates": [],
    }
    assert report["historical_baseline"]["certified"] == 1416
    assert report["historical_baseline"]["vs_portfolio"]["left_only"] == []
    assert report["completion"]["certificates"]["certified_fountain"] == 1363
    assert report["completion"]["payload"]["verified"] is True
    assert report["diagnostics"]["qualified"] is True


def test_live_source_delta_is_exact_observer_only_instrumentation() -> None:
    qualified = _report()["implementation"]["current"]
    assert _c2_report()["implementation"]["current"] == qualified
    live_rows = tuple(
        row for row in run_e023c.implementation_fingerprints()
        if not row[0].startswith("lower:runtime:"))
    qualified_rows = tuple(
        (key, qualified[key]) for key, _value in live_rows)
    assert _implementation_aggregate(qualified_rows) == (
        QUALIFIED_IMPLEMENTATION_AGGREGATE_SHA256)

    live = dict(live_rows)
    delta = {
        key: {"qualified": qualified[key], "live": live[key]}
        for key in sorted(live)
        if qualified[key] != live[key]
    }
    assert delta == OBSERVER_ONLY_FINGERPRINT_DELTA
    assert _implementation_aggregate(live_rows) == (
        OBSERVER_ONLY_IMPLEMENTATION_AGGREGATE_SHA256)


def test_production_report_is_frozen_and_all_gates_pass() -> None:
    report = _report()
    assert _sha256(REPORT) == (
        "84276f235ab38548c916270dc2517c7ca659cd49d9968e2e82115ecadc37b8c9")
    assert report["magic"] == "e023c-cascade-qualification-v1"
    assert report["status"] == "QUALIFIED_SINGLE_CAPTURE"
    assert report["gates_ok"] is True
    assert all(report["gates"].values())
    assert report["scope"] == (
        "single 1200-dpi physical capture for profile c3 / format "
        "e018b-v3-c3; architectural and numerical qualification, not "
        "cross-scanner generalization")
    assert report["qualifier"]["sha256"] == _sha256(QUALIFIER)
    assert report["implementation"]["matches"] is True
    assert report["implementation"]["stored"] == (
        report["implementation"]["current"])
    state = report["state"]
    assert state["captures"] == 1
    assert state["attempt_records"] == 1321
    assert state["authoritative_sha256"] == (
        "46194a2861819f56b2423c7240c7b5ee86fa37f8c4a53cdf9e26bf17bc0b541b")
    assert state["file_sha256"] == (
        "02e32656d31a236be8dd65b96232aba8c219156dc2bc22c79f8e1b9a211f8faf")
    assert state["implementation_matches_current"] is True
    assert state["run_policy_sha256"] == (
        "4f47ee96942e3a5bca4811b0b41b1c22a2714a92c478ebc3fcaf3a722ddc4167")


def test_level_marginals_and_decoder_cost_are_frozen() -> None:
    report = _report()
    assert report["ordered_marginal_contributions"] == {
        "l00-2ppc-400dpi": 671,
        "l01-3ppc-600dpi": 74,
        "l02-6ppc-1200dpi": 9,
    }
    expected = {
        "l00-2ppc-400dpi": (184, 650, 21, 671, 866, 44942, 944, 0),
        "l01-3ppc-600dpi": (143, 73, 1, 74, 195, 26150, 230, 50),
        "l02-6ppc-1200dpi": (143, 7, 2, 9, 111, 21838, 147, 43),
    }
    for level, values in expected.items():
        row = report["lanes"][level]
        got = (
            row["placements"], row["certified_before_retry"],
            row["retry_gain"], row["certified_after_retry"],
            row["crc_calls"], row["bp_iterations"],
            row["attempt_records"], row["feedback_adopted"],
        )
        assert got == values
        assert row["wrong_certificates"] == []


def test_automatic_portfolio_is_correct_and_strictly_beats_control() -> None:
    report = _report()
    assert report["portfolio"] == {
        "certified": 754,
        "certificate_set_sha256": (
            "70ed14f8e9582535632ca8fc803dc5848d6e1238a24f44fc289b05995aa80324"),
        "certificate_bits_sha256": (
            "806b1c1aa91b494d98efe0327d2a70438e9517c6afc8fd83bea5402195628c25"),
        "wrong_certificates": [],
    }
    control = report["schedule_control"]
    assert control["ppc"] == [2.0, 6.0]
    assert control["file_sha256"] == (
        "d6eb372dc2640cc9bb8f832f84cdfd795c7d1e446f1577a80bf48446c669cb70")
    assert control["authoritative_sha256"] == (
        "bca2655b2afda70b6c60562aa407451bf065ba9263fefc1ebe0691a5c18da31b")
    assert control["portfolio"]["certified"] == 747
    assert control["vs_automatic"] == {
        "left": 747,
        "right": 754,
        "intersection": 747,
        "left_only": [],
        "right_only": [
            [0, 4, 20], [0, 4, 22],
            [0, 12, 8], [0, 12, 9], [0, 12, 10],
            [0, 15, 7], [0, 15, 9],
        ],
        "conflicts": [],
    }
    assert control["cost"] == {
        "crc_calls": 1056, "bp_iterations": 69613,
        "attempt_records": 1171}
    assert control["automatic_cost"] == {
        "crc_calls": 1172, "bp_iterations": 92930,
        "attempt_records": 1321}


def test_historical_native_baseline_is_a_strict_subset() -> None:
    report = _report()
    baseline = report["historical_baseline"]
    comparison = baseline["vs_portfolio"]
    assert baseline["source_matches"] is True
    assert baseline["certified"] == 730
    assert comparison["intersection"] == 730
    assert comparison["left_only"] == []
    assert comparison["conflicts"] == []
    assert len(comparison["right_only"]) == 24
    assert baseline["wrong_certificates"] == []


def test_real_fountain_and_diagnostic_commit_are_verified() -> None:
    report = _report()
    completion = report["completion"]
    assert completion["payload"]["verified"] is True
    assert completion["payload"]["actual_len_bytes"] == 88157
    assert completion["payload"]["actual_sha256"] == (
        "012d9e3ae693c00e464637eeffa519329f081a42262dedbfc9e0e8e1e86acf28")
    assert completion["fountain"]["rank"] == 338
    assert completion["fountain"]["rank_shortfall"] == 0
    assert completion["fountain"]["symbols_received"] == 731
    diagnostics = report["diagnostics"]
    assert diagnostics["qualified"] is True
    assert diagnostics["final_event"] == "session_complete"
    assert diagnostics["frames"] == 38
    assert diagnostics["metadata_matches_state"] is True
