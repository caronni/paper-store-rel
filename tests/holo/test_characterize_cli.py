from __future__ import annotations

import json
from pathlib import Path

import pytest

from holo import cli
from holo.characterize import __main__ as characterize_cli


def test_main_help_lists_discover(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--help"])

    assert stopped.value.code == 0
    assert "discover" in capsys.readouterr().out


def test_discover_help_is_current_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["discover", "--help"])

    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "{emit,analyze,calibrate,combine,candidates}" in help_text
    assert "emit-discovery" not in help_text
    assert "emit-calibration" not in help_text
    assert "combine-calibration" not in help_text
    assert "list-candidates" not in help_text


@pytest.mark.parametrize(
    "obsolete",
    (
        "emit-discovery",
        "emit-calibration",
        "combine-calibration",
        "list-candidates",
    ),
)
def test_discover_rejects_obsolete_verbs(
    obsolete: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["discover", obsolete])

    assert stopped.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_discover_emit_routes_to_isolated_emitter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: dict[str, object] = {}

    def fake_emit_bundle(output_dir: str, **kwargs: object) -> dict:
        observed["output_dir"] = output_dir
        observed.update(kwargs)
        return {
            "bundle_manifest": {"path": "bundle.json"},
            "pages": [
                {
                    "kind": "bw",
                    "postscript": {"path": "bw.ps"},
                    "page_manifest": {"path": "bw.json"},
                },
                {
                    "kind": "color",
                    "postscript": {"path": "color.ps"},
                    "page_manifest": {"path": "color.json"},
                },
            ],
        }

    monkeypatch.setattr(characterize_cli, "emit_bundle", fake_emit_bundle)

    assert cli.main([
        "discover", "emit", str(tmp_path),
        "--request", "1200", "--copy-index", "4",
    ]) == 0
    assert observed == {
        "output_dir": str(tmp_path),
        "stage": "discovery",
        "copy_index": 4,
        "request_code": "1200",
        "kinds": ("bw", "color"),
        "max_job_bytes": 128 << 20,
    }
    assert '"postscript"' in capsys.readouterr().out


def test_calibrate_malformed_from_report_is_a_clean_user_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    malformed = tmp_path / "malformed-report.json"
    malformed.write_text('{"page_identity":null}\n', encoding="utf-8")

    with pytest.raises(SystemExit) as stopped:
        characterize_cli.main([
            "calibrate",
            str(tmp_path / "out"),
            "--kind",
            "bw",
            "--from-report",
            str(malformed),
        ])

    assert stopped.value.code == 2
    assert "analysis report schema must be exactly" in capsys.readouterr().err


def test_module_entry_point_uses_the_same_current_verbs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        characterize_cli.main(["--help"])

    assert stopped.value.code == 0
    assert "{emit,analyze,calibrate,combine,candidates}" in (
        capsys.readouterr().out
    )


@pytest.mark.parametrize(
    ("kind", "expected_count"),
    (("both", 86), ("bw", 34), ("color", 52)),
)
def test_candidates_lists_the_fixed_current_characterization_registry(
    kind: str,
    expected_count: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert characterize_cli.main(["candidates", "--kind", kind]) == 0

    rows = json.loads(capsys.readouterr().out)

    assert len(rows) == expected_count
    assert len({row["code"] for row in rows}) == expected_count
    assert all(row["page_kind"] in {"bw", "color"} for row in rows)
