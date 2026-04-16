from pathlib import Path

import pytest

from warden.adapters.github import GitHubIssue, RepoSummary
from warden.config import WardenConfig
from warden.workflows.agentic_triage import run_agentic_triage

from .support.fakes import FakeGitHubAdapter


def _make_fake_adapter(body: str) -> FakeGitHubAdapter:
    primary = GitHubIssue(
        number=42,
        title="App crashes on startup when config file is missing",
        body=body,
        state="open",
        labels=(),
        comments=0,
        author="reporter",
        url="https://example/42",
    )
    similar = GitHubIssue(
        number=9,
        title="Startup crash with missing config",
        body="Similar crash reported months ago.",
        state="closed",
        labels=("bug",),
        comments=1,
        author="other",
        url="https://example/9",
    )
    return FakeGitHubAdapter(
        issues=[("example/demo", primary)],
        comments=[("example/demo", 42, [])],
        similar=[("example/demo", [similar])],
        repos=[
            (
                "example/demo",
                RepoSummary(
                    full_name="example/demo",
                    description="Demo repository",
                    default_branch="main",
                    language="Python",
                    topics=("demo",),
                ),
            )
        ],
    )


def _make_config(tmp_path: Path) -> WardenConfig:
    return WardenConfig(
        anthropic_base_url="https://api.minimax.io/anthropic",
        anthropic_auth_token=None,
        model="MiniMax-M2.7",
        github_token=None,
        approval_mode="auto",
        data_dir=tmp_path,
    )


def test_agentic_triage_uses_tools_and_verifies(tmp_path: Path) -> None:
    adapter = _make_fake_adapter(
        "Steps: run ./app with no config.yaml present. Actual: the binary crashes with a segfault."
    )
    config = _make_config(tmp_path)

    result = run_agentic_triage(
        repo="example/demo",
        issue_number=42,
        config=config,
        github_adapter=adapter,
        use_live_model=False,
    )

    assert result.outcome.status == "verified"
    payload = result.outcome.result or {}
    assert payload["category"] == "bug"
    assert payload["severity"] in {"high", "critical"}
    assert payload["priority"] in {"p0", "p1"}
    assert "bug" in payload["recommended_labels"]
    assert any("severity/" in label for label in payload["recommended_labels"])
    # Must have actually called a tool (real agent behaviour).
    assert result.outcome.tool_calls >= 1


def test_agentic_triage_fails_when_issue_missing(tmp_path: Path) -> None:
    adapter = FakeGitHubAdapter()
    config = _make_config(tmp_path)
    with pytest.raises(KeyError):
        run_agentic_triage(
            repo="example/demo",
            issue_number=99,
            config=config,
            github_adapter=adapter,
            use_live_model=False,
        )
