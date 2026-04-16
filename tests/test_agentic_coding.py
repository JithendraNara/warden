from pathlib import Path

from warden.config import WardenConfig
from warden.workflows.agentic_coding import run_agentic_coding


def _make_config(tmp_path: Path) -> WardenConfig:
    return WardenConfig(
        anthropic_base_url="https://api.minimax.io/anthropic",
        anthropic_auth_token=None,
        model="MiniMax-M2.7",
        github_token=None,
        approval_mode="auto",
        data_dir=tmp_path,
    )


def test_coding_returns_validated_patch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "main.py").write_text("# existing first line\n")

    data_dir = tmp_path / "data"
    config = _make_config(data_dir)

    result = run_agentic_coding(
        repo_root=repo_root,
        target_file="main.py",
        goal="Annotate missing guard near main.py",
        evidence="Users report an unhandled exception when the config file is missing on startup.",
        config=config,
    )

    payload = result.outcome.result or {}
    assert result.outcome.status == "verified", result.outcome.verification and result.outcome.verification.reason()
    assert payload.get("affected_files") == ["main.py"]
    assert "diff" in payload and payload["diff"].strip().startswith("---")
    assert "rationale" in payload and "main.py" in payload["rationale"]
