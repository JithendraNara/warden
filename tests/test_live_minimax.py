"""Live integration test against MiniMax M2.7 via the Anthropic endpoint.

The test is skipped unless ``WARDEN_LIVE_TEST=1`` is set and
``ANTHROPIC_AUTH_TOKEN`` is present. It drives the full agent loop
through :class:`ClaudeAgentThinker` against the MiniMax
Anthropic-compatible endpoint and asserts that the loop:

- reached a verified final result,
- called at least one tool (so it exercised the real tool chain, not
  a one-shot answer),
- produced a structured payload matching the triage schema.
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

    # NOTE: we populate the adapter with a real issue body and similar
    # issues, but the prompt built by build_triage_prompt includes the
    # body by design. The thinker prompt additionally enforces a
    # minimum tool-call count so the model exercises the tool chain
    # (list_similar_issues, get_repo_context, etc.).
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
        similar=[
            (
                "example/demo",
                [
                    GitHubIssue(
                        number=11,
                        title="older startup config crash",
                        body="",
                        state="closed",
                        labels=("bug",),
                        comments=0,
                        author="other",
                        url="https://example/11",
                    )
                ],
            )
        ],
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

    outcome = result.outcome
    # The model must actually use the tool chain, not answer in one
    # shot. The ClaudeAgentThinker enforces this with its prompt
    # discipline.
    assert outcome.tool_calls >= 1, (
        f"expected at least 1 tool call, got {outcome.tool_calls};"
        f" trajectory={outcome.trajectory}"
    )
    assert outcome.status == "verified", (
        f"expected verified status, got {outcome.status};"
        f" reason={outcome.verification.reason() if outcome.verification else None}"
    )
    payload = outcome.result or {}
    for key in (
        "category",
        "severity",
        "priority",
        "summary",
        "recommended_labels",
        "suggested_next_action",
    ):
        assert key in payload, f"triage payload missing key {key!r}: {payload}"
