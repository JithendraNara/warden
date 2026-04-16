from pathlib import Path

from warden.adapters.github import GitHubPullRequest
from warden.config import WardenConfig
from warden.workflows.agentic_review import run_agentic_review

from .support.fakes import FakeGitHubAdapter


SAMPLE_DIFF = """--- a/src/main.py
+++ b/src/main.py
@@ -1,2 +1,3 @@
+# guard missing config
 def main():
     print('hello')
"""


def _make_config(tmp_path: Path) -> WardenConfig:
    return WardenConfig(
        anthropic_base_url="https://api.minimax.io/anthropic",
        anthropic_auth_token=None,
        model="MiniMax-M2.7",
        github_token=None,
        approval_mode="auto",
        data_dir=tmp_path,
    )


def test_review_returns_structured_verdict(tmp_path: Path) -> None:
    pr = GitHubPullRequest(
        number=7,
        title="Fix startup crash",
        body="Adds a guard for missing config.",
        state="open",
        draft=False,
        base_ref="main",
        head_ref="fix/startup",
        url="https://example/7",
        changed_files=1,
        additions=1,
        deletions=0,
    )
    adapter = FakeGitHubAdapter(
        pull_requests=[("example/demo", pr)],
        pr_diffs=[("example/demo", 7, SAMPLE_DIFF)],
    )
    config = _make_config(tmp_path)

    result = run_agentic_review(
        repo="example/demo",
        pr_number=7,
        config=config,
        github_adapter=adapter,
    )

    assert result.outcome.status == "verified"
    payload = result.outcome.result or {}
    assert payload.get("verdict") in {"accept", "revise", "reject"}
    assert isinstance(payload.get("feedback"), list)
    assert payload.get("pr_summary", {}).get("number") == 7
