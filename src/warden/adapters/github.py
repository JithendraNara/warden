"""GitHub adapter for warden.

This module is a real HTTP client, not a placeholder. It exposes
narrow, typed operations that the agent loop and custom tools call.
All write operations go through the permission layer before reaching
this adapter.

Rate limiting is respected by reading ``X-RateLimit-*`` headers and
backing off when ``remaining`` drops to zero.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx

logger = logging.getLogger("warden.github")


DEFAULT_BASE_URL = "https://api.github.com"
USER_AGENT = "warden/0.1 (+https://github.com/JithendraNara/warden)"


@dataclass(slots=True)
class GitHubIssue:
    number: int
    title: str
    body: str
    state: str
    labels: tuple[str, ...]
    comments: int
    author: str
    url: str


@dataclass(slots=True)
class GitHubComment:
    author: str
    body: str
    created_at: str


@dataclass(slots=True)
class GitHubPullRequest:
    number: int
    title: str
    body: str
    state: str
    draft: bool
    base_ref: str
    head_ref: str
    url: str
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0


@dataclass(slots=True)
class RepoSummary:
    full_name: str
    description: str | None
    default_branch: str
    language: str | None
    topics: tuple[str, ...]


@dataclass(slots=True)
class RateBudget:
    remaining: int = 5000
    reset_at: float = field(default_factory=time.time)


class GitHubAdapter:
    """Thin HTTP wrapper around the GitHub REST API.

    The adapter takes an optional token. Unauthenticated requests are
    subject to a low rate limit, so the agent layer should prefer a
    token when doing real work.
    """

    def __init__(
        self,
        token: str | None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=30.0)
        self._rate = RateBudget()

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _update_rate(self, response: httpx.Response) -> None:
        try:
            remaining = int(response.headers.get("x-ratelimit-remaining", self._rate.remaining))
            reset_at = float(response.headers.get("x-ratelimit-reset", self._rate.reset_at))
        except ValueError:
            return
        self._rate = RateBudget(remaining=remaining, reset_at=reset_at)

    def _sleep_if_exhausted(self) -> None:
        if self._rate.remaining == 0:
            wait = max(self._rate.reset_at - time.time(), 0.0)
            if wait:
                logger.info("GitHub rate limit exhausted, sleeping %.1fs", wait)
                time.sleep(wait)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._sleep_if_exhausted()
        url = f"{self._base_url}{path}"
        response = self._client.get(url, headers=self._headers(), params=params)
        self._update_rate(response)
        response.raise_for_status()
        return response.json()

    def _get_text(self, path: str, accept: str) -> str:
        self._sleep_if_exhausted()
        url = f"{self._base_url}{path}"
        headers = self._headers()
        headers["Accept"] = accept
        response = self._client.get(url, headers=headers)
        self._update_rate(response)
        response.raise_for_status()
        return response.text

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        self._sleep_if_exhausted()
        url = f"{self._base_url}{path}"
        response = self._client.post(url, headers=self._headers(), json=body)
        self._update_rate(response)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------ #
    # Read operations                                                    #
    # ------------------------------------------------------------------ #

    def fetch_repo(self, repo: str) -> RepoSummary:
        data = self._get(f"/repos/{repo}")
        return RepoSummary(
            full_name=data["full_name"],
            description=data.get("description"),
            default_branch=data.get("default_branch", "main"),
            language=data.get("language"),
            topics=tuple(data.get("topics", [])),
        )

    def fetch_issue(self, repo: str, number: int) -> GitHubIssue:
        data = self._get(f"/repos/{repo}/issues/{number}")
        return _issue_from_payload(data)

    def fetch_issue_comments(self, repo: str, number: int) -> list[GitHubComment]:
        data = self._get(f"/repos/{repo}/issues/{number}/comments")
        comments: list[GitHubComment] = []
        for item in data:
            comments.append(
                GitHubComment(
                    author=(item.get("user") or {}).get("login", "<unknown>"),
                    body=item.get("body") or "",
                    created_at=item.get("created_at") or "",
                )
            )
        return comments

    def fetch_pull_request(self, repo: str, number: int) -> GitHubPullRequest:
        data = self._get(f"/repos/{repo}/pulls/{number}")
        return GitHubPullRequest(
            number=int(data.get("number", 0)),
            title=str(data.get("title", "")),
            body=str(data.get("body") or ""),
            state=str(data.get("state", "open")),
            draft=bool(data.get("draft", False)),
            base_ref=str((data.get("base") or {}).get("ref", "")),
            head_ref=str((data.get("head") or {}).get("ref", "")),
            url=str(data.get("html_url", "")),
            changed_files=int(data.get("changed_files", 0)),
            additions=int(data.get("additions", 0)),
            deletions=int(data.get("deletions", 0)),
        )

    def fetch_pr_diff(self, repo: str, number: int) -> str:
        """Return the raw unified diff for a pull request."""

        return self._get_text(
            f"/repos/{repo}/pulls/{number}",
            accept="application/vnd.github.v3.diff",
        )

    def search_similar_issues(
        self,
        repo: str,
        query: str,
        *,
        limit: int = 5,
    ) -> list[GitHubIssue]:
        q = f"repo:{repo} is:issue {query}"
        data = self._get(
            "/search/issues",
            params={"q": q, "per_page": limit, "sort": "updated"},
        )
        issues: list[GitHubIssue] = []
        for item in data.get("items", []):
            issues.append(_issue_from_payload(item))
        return issues

    # ------------------------------------------------------------------ #
    # Write operations (permission-gated via hook layer)                 #
    # ------------------------------------------------------------------ #

    def post_issue_comment(self, repo: str, number: int, body: str) -> GitHubComment:
        data = self._post(
            f"/repos/{repo}/issues/{number}/comments",
            body={"body": body},
        )
        return GitHubComment(
            author=(data.get("user") or {}).get("login", "<unknown>"),
            body=data.get("body") or "",
            created_at=data.get("created_at") or "",
        )


def _issue_from_payload(data: dict[str, Any]) -> GitHubIssue:
    labels: Iterable[Any] = data.get("labels") or []
    label_names: list[str] = []
    for label in labels:
        if isinstance(label, dict) and "name" in label:
            label_names.append(str(label["name"]))
        elif isinstance(label, str):
            label_names.append(label)
    return GitHubIssue(
        number=int(data.get("number", 0)),
        title=str(data.get("title", "")),
        body=str(data.get("body") or ""),
        state=str(data.get("state", "open")),
        labels=tuple(label_names),
        comments=int(data.get("comments", 0)),
        author=str((data.get("user") or {}).get("login", "<unknown>")),
        url=str(data.get("html_url", "")),
    )
