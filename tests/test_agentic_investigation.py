from pathlib import Path

from warden.config import WardenConfig
from warden.workflows.agentic_investigation import run_agentic_investigation


def _make_config(tmp_path: Path) -> WardenConfig:
    return WardenConfig(
        anthropic_base_url="https://api.minimax.io/anthropic",
        anthropic_auth_token=None,
        model="MiniMax-M2.7",
        github_token=None,
        approval_mode="auto",
        data_dir=tmp_path,
    )


def test_investigation_uses_filesystem_and_returns_plan(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "main.py").write_text(
        "def load_config():\n    return open('config.yaml').read()\n"
    )
    data_dir = tmp_path / "data"
    config = _make_config(data_dir)

    result = run_agentic_investigation(
        repo_root=repo_root,
        issue_title="config file missing at startup",
        issue_body="When config.yaml is missing we expected a friendly error, but got a traceback.",
        config=config,
    )

    outcome = result.outcome
    assert outcome.status == "verified", outcome.verification and outcome.verification.reason()
    assert outcome.tool_calls >= 2
    payload = outcome.result or {}
    assert "steps" in payload and payload["steps"]
    assert "hypotheses" in payload and payload["hypotheses"]
