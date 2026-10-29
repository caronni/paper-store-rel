"""Numerical and reproducibility checks for the conditional FEC study."""
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
import pytest

import resilience


def _decimal_rs_log_probability(p: float, erasures: bool) -> float:
    """Independent high-precision sum of the allowed byte-error counts."""
    with localcontext() as context:
        context.prec = 100
        byte_p = 1 - (1 - Decimal(str(p))) ** 8
        limit = 30 if erasures else 15
        blocks = []
        for length in (148, 149):
            blocks.append(sum(
                Decimal(math.comb(length, errors)) * byte_p ** errors
                * (1 - byte_p) ** (length - errors)
                for errors in range(limit + 1)
            ))
        return float((blocks[0] ** 19 * blocks[1] ** 6).ln())


@pytest.mark.parametrize("p,erasures", [
    (0.01, False), (0.02, True), (0.06, False), (0.20, True),
    (0.999999, False),
])
def test_rs_log_probability_against_decimal(p: float, erasures: bool) -> None:
    actual = resilience.rs_log_success(p, erasures)
    expected = _decimal_rs_log_probability(p, erasures)
    assert actual == pytest.approx(expected, rel=1e-11, abs=1e-9)
    assert math.isfinite(actual)
    if p == 0.06:
        assert resilience.rs_success(p) == 0.0  # Underflows, but log stays finite.


def test_rs_limits_and_erasure_advantage() -> None:
    for erasures in (False, True):
        assert resilience.rs_success(0, erasures) == 1
        assert resilience.rs_success(1, erasures) == 0
    assert resilience.rs_success(0.02, True) > resilience.rs_success(0.02)


@pytest.mark.parametrize("p", [-0.1, 1.1, math.nan, math.inf])
def test_invalid_rs_probability(p: float) -> None:
    with pytest.raises(ValueError, match="probability"):
        resilience.rs_success(p)


def test_wilson_interval_boundaries() -> None:
    low, high = resilience.wilson_interval(1000, 1000)
    assert low == pytest.approx(0.996173241514445)
    assert high == 1
    zero_low, zero_high = resilience.wilson_interval(0, 1000)
    assert zero_low == 0
    assert zero_high == pytest.approx(1 - low)


@pytest.mark.parametrize("trials,workers", [(0, 1), (1, 0), (-1, 2), (True, 1)])
def test_bad_run_settings_do_not_create_output(
        tmp_path: Path, trials: int, workers: int) -> None:
    out = tmp_path / "invalid"
    with pytest.raises(ValueError, match="positive integer"):
        resilience.run(out, trials, workers)
    assert not out.exists()


@pytest.mark.parametrize("channel,p", [
    ("unknown", 0.01), ("bit_flips", 0), ("gaussian_soft", 0.5),
    ("known_cell_erasures", math.nan),
])
def test_invalid_trial_channel(channel: str, p: float) -> None:
    with pytest.raises(ValueError):
        resilience.trial((channel, p, np.random.SeedSequence(4)))


def test_run_is_independent_of_worker_scheduling(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resilience, "CHANNELS", {
        "bit_flips": [0.01], "gaussian_soft": [0.02],
        "known_cell_erasures": [0.10],
    })
    serial = resilience.run(tmp_path / "serial", trials=2, workers=1)
    parallel = resilience.run(tmp_path / "parallel", trials=2, workers=2)
    assert serial["rows"] == parallel["rows"]
    saved = json.loads((tmp_path / "serial/results.json").read_text())
    assert saved == serial
    assert len(saved["rows"]) == 3
    assert all(row["wrong_certificates"] == 0 for row in saved["rows"])
    assert all(len(value) == 64
               for value in saved["provenance"]["source_sha256"].values())
    assert "out of band" in saved["full_object_model"]


def test_cli_preserves_existing_output(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("existing record")
    monkeypatch.setattr(sys, "argv", ["resilience.py", "--out", str(tmp_path)])
    with pytest.raises(SystemExit) as caught:
        resilience.main()
    assert caught.value.code == 2
    assert sentinel.read_text() == "existing record"
    assert not (tmp_path / "results.json").exists()
    assert "resilience:" in capsys.readouterr().err
