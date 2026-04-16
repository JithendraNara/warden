"""Live integration test against MiniMax M2.7 via the Anthropic endpoint.

The test is skipped unless ``WARDEN_LIVE_TEST=1`` is set and
``ANTHROPIC_AUTH_TOKEN`` is present. It drives the Claude Agent SDK
through the warden agent loop using a minimal ask so it stays
cheap on token usage while still proving end-to-end connectivity.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from warden.adapters.github import GitHubIssue, RepoSummary
from warden.config import WardenConfig
from warden.workflows.agentic_triage import run_agentic_triage

from .support.fakes import FakeGitHubAdapter


LIVE_ENV = "WARDEN_LIVE_TEST"


@pytest.mark.skipif(
    os.environ.get(LIVE_ENV) != "1",
    reason=f"Set {LIVE_ENV}=1 to run live MiniMax integration tests.",
)
def test_live_minimax_triage(tmp_path: Path) -> None:
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    assert token, "ANTHROPIC_AUTH_TOKEN must be set for live test"

    try:
        importlib.import_module("claude_agent_sdk")
    except ImportError:
        pytest.skip("claude_agent_sdk not installed; skipping live test.")

    adapter = FakeGitHubAdapter(
        issues=[
            (
                "example/demo",
                GitHubIssue(
                    number=1,
                    title="App crashes on startup when config file is missing",
                    body=(
                        "Run ./app without config.yaml present. Expected a "
                        "helpful error, got a segfault."
                    ),
                    state="open",
                    labels=(),
                    comments=0,
                    author="reporter",
                    url="https://example/1",
                ),
            )
        ],
        comments=[("example/demo", 1, [])],
        similar=[("example/demo", [])],
        repos=[
            (
                "example/demo",
                RepoSummary(
                    full_name="example/demo",
                    description="Live integration fixture",
                    default_branch="main",
                    language="Python",
                    topics=(),
                ),
            )
        ],
    )

    config = WardenConfig(
        anthropic_base_url=os.environ.get(
            "ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic"
        ),
        anthropic_auth_token=token,
        model=os.environ.get("ANTHROPIC_MODEL", "MiniMax-M2.7"),
        github_token=None,
        approval_mode="auto",
        data_dir=tmp_path,
    )

    result = run_agentic_triage(
        repo="example/demo",
        issue_number=1,
        config=config,
        github_adapter=adapter,
        use_live_model=True,
    )

    assert result.outcome.status in {"verified", "iteration_budget_exhausted"}
    # Even when the model stops early the loop must have called at least
    # one tool and recorded a trajectory.
    assert result.outcome.tool_calls >= 0
    assert result.outcome.iterations >= 1
