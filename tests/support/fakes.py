"""In-memory fakes for offline tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from warden.adapters.github import (
    GitHubAdapter,
    GitHubComment,
    GitHubIssue,
    GitHubPullRequest,
    RepoSummary,
)


@dataclass(slots=True)
class FakeGitHubAdapter(GitHubAdapter):
    """Drop-in replacement for :class:`GitHubAdapter` in tests."""

    issues: dict[tuple[str, int], GitHubIssue] = field(default_factory=dict)
    comments: dict[tuple[str, int], list[GitHubComment]] = field(default_factory=dict)
    similar: dict[str, list[GitHubIssue]] = field(default_factory=dict)
    repos: dict[str, RepoSummary] = field(default_factory=dict)
    posted: list[tuple[str, int, str]] = field(default_factory=list)

    pull_requests: dict[tuple[str, int], GitHubPullRequest] = field(default_factory=dict)
    pr_diffs: dict[tuple[str, int], str] = field(default_factory=dict)

    def __init__(
        self,
        *,
        issues: Iterable[tuple[str, GitHubIssue]] = (),
        comments: Iterable[tuple[str, int, list[GitHubComment]]] = (),
        similar: Iterable[tuple[str, list[GitHubIssue]]] = (),
        repos: Iterable[tuple[str, RepoSummary]] = (),
        pull_requests: Iterable[tuple[str, GitHubPullRequest]] = (),
        pr_diffs: Iterable[tuple[str, int, str]] = (),
    ) -> None:
        # Do NOT call super().__init__ - we don't need HTTP machinery.
        self.issues = {(repo, issue.number): issue for repo, issue in issues}
        self.comments = {(repo, number): value for repo, number, value in comments}
        self.similar = dict(similar)
        self.repos = dict(repos)
        self.pull_requests = {(repo, pr.number): pr for repo, pr in pull_requests}
        self.pr_diffs = {(repo, number): diff for repo, number, diff in pr_diffs}
        self.posted = []

    def close(self) -> None:  # pragma: no cover - noop
        return None

    def fetch_repo(self, repo: str) -> RepoSummary:
        return self.repos[repo]

    def fetch_issue(self, repo: str, number: int) -> GitHubIssue:
        return self.issues[(repo, number)]

    def fetch_issue_comments(self, repo: str, number: int) -> list[GitHubComment]:
        return list(self.comments.get((repo, number), []))

    def search_similar_issues(
        self, repo: str, query: str, *, limit: int = 5
    ) -> list[GitHubIssue]:
        return list(self.similar.get(repo, []))[:limit]

    def post_issue_comment(self, repo: str, number: int, body: str) -> GitHubComment:
        self.posted.append((repo, number, body))
        return GitHubComment(author="warden", body=body, created_at="2026-04-16T00:00:00Z")

    def fetch_pull_request(self, repo: str, number: int) -> GitHubPullRequest:
        return self.pull_requests[(repo, number)]

    def fetch_pr_diff(self, repo: str, number: int) -> str:
        return self.pr_diffs[(repo, number)]
