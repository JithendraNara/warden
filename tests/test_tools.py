from warden.adapters.github import GitHubIssue, RepoSummary
from warden.runtime.agent_loop import ToolCall, ToolRegistry
from warden.runtime.tools import register_github_tools

from .support.fakes import FakeGitHubAdapter


def _make_adapter() -> FakeGitHubAdapter:
    issue = GitHubIssue(
        number=1,
        title="crash on startup",
        body="segfault when config missing",
        state="open",
        labels=("bug",),
        comments=0,
        author="author",
        url="https://example/1",
    )
    similar = GitHubIssue(
        number=11,
        title="similar crash",
        body="also crashes",
        state="closed",
        labels=("bug", "duplicate"),
        comments=2,
        author="other",
        url="https://example/11",
    )
    repo = RepoSummary(
        full_name="example/demo",
        description="A demo repo",
        default_branch="main",
        language="Python",
        topics=("demo",),
    )
    return FakeGitHubAdapter(
        issues=[("example/demo", issue)],
        comments=[("example/demo", 1, [])],
        similar=[("example/demo", [similar])],
        repos=[("example/demo", repo)],
    )


def test_fetch_issue_tool_returns_payload() -> None:
    adapter = _make_adapter()
    registry = ToolRegistry()
    register_github_tools(registry, adapter)
    result = registry.execute(ToolCall(name="fetch_issue", arguments={"repo": "example/demo", "number": 1}))
    assert result["issue"]["number"] == 1
    assert result["issue"]["labels"] == ["bug"]
    assert result["comments"] == []


def test_list_similar_issues_tool_returns_matches() -> None:
    adapter = _make_adapter()
    registry = ToolRegistry()
    register_github_tools(registry, adapter)
    result = registry.execute(
        ToolCall(
            name="list_similar_issues",
            arguments={"repo": "example/demo", "query": "crash", "limit": 2},
        )
    )
    assert len(result["matches"]) == 1
    assert result["matches"][0]["number"] == 11


def test_get_repo_context_tool_returns_summary() -> None:
    adapter = _make_adapter()
    registry = ToolRegistry()
    register_github_tools(registry, adapter)
    result = registry.execute(ToolCall(name="get_repo_context", arguments={"repo": "example/demo"}))
    assert result["full_name"] == "example/demo"
    assert result["language"] == "Python"
    assert result["topics"] == ["demo"]
