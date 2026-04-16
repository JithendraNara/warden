"""Tool factories wiring real adapters into the agent loop.

The agent loop never imports adapters directly. Instead this module
produces typed callables that handle validation, permission policy,
and observation shaping. Replacing an adapter (for example switching
from REST to GraphQL) only touches this file.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..adapters.github import GitHubAdapter, GitHubIssue, GitHubPullRequest
from ..adapters.patch import parse_unified_diff, validate_patch
from ..adapters.repo_fs import RepoFilesystem
from ..adapters.shell import CommandRefused, ShellAdapter
from .agent_loop import ToolCallable, ToolRegistry


def _issue_to_dict(issue: GitHubIssue) -> dict[str, Any]:
    payload = asdict(issue)
    payload["labels"] = list(issue.labels)
    return payload


def _pr_to_dict(pr: GitHubPullRequest) -> dict[str, Any]:
    return asdict(pr)


def make_github_tools(adapter: GitHubAdapter) -> dict[str, ToolCallable]:
    """Return the tool name → callable map for GitHub operations."""

    def fetch_issue(args: dict[str, Any]) -> dict[str, Any]:
        repo = str(args["repo"])
        number = int(args["number"])
        issue = adapter.fetch_issue(repo, number)
        comments = adapter.fetch_issue_comments(repo, number)
        return {
            "issue": _issue_to_dict(issue),
            "comments": [
                {"author": c.author, "body": c.body, "created_at": c.created_at}
                for c in comments
            ],
        }

    def list_similar_issues(args: dict[str, Any]) -> dict[str, Any]:
        repo = str(args["repo"])
        query = str(args["query"])
        limit = int(args.get("limit", 5))
        matches = adapter.search_similar_issues(repo, query, limit=limit)
        return {"matches": [_issue_to_dict(issue) for issue in matches]}

    def get_repo_context(args: dict[str, Any]) -> dict[str, Any]:
        repo = str(args["repo"])
        summary = adapter.fetch_repo(repo)
        return {
            "full_name": summary.full_name,
            "description": summary.description,
            "default_branch": summary.default_branch,
            "language": summary.language,
            "topics": list(summary.topics),
        }

    def fetch_pull_request(args: dict[str, Any]) -> dict[str, Any]:
        repo = str(args["repo"])
        number = int(args["number"])
        pr = adapter.fetch_pull_request(repo, number)
        return {"pull_request": _pr_to_dict(pr)}

    def fetch_pr_diff(args: dict[str, Any]) -> dict[str, Any]:
        repo = str(args["repo"])
        number = int(args["number"])
        diff = adapter.fetch_pr_diff(repo, number)
        return {"diff": diff, "size_bytes": len(diff)}

    return {
        "fetch_issue": fetch_issue,
        "list_similar_issues": list_similar_issues,
        "get_repo_context": get_repo_context,
        "fetch_pull_request": fetch_pull_request,
        "fetch_pr_diff": fetch_pr_diff,
    }


def register_github_tools(registry: ToolRegistry, adapter: GitHubAdapter) -> None:
    for name, fn in make_github_tools(adapter).items():
        registry.register(name, fn)


def make_repo_fs_tools(fs: RepoFilesystem) -> dict[str, ToolCallable]:
    def read_file(args: dict[str, Any]) -> dict[str, Any]:
        content = fs.read_file(str(args["path"]))
        return {
            "path": content.path,
            "size_bytes": content.size_bytes,
            "text": content.text,
            "truncated": content.truncated,
        }

    def list_dir(args: dict[str, Any]) -> dict[str, Any]:
        relative = str(args.get("path", "."))
        return {"entries": fs.list_dir(relative)}

    def search_text(args: dict[str, Any]) -> dict[str, Any]:
        matches = fs.search_text(
            str(args["query"]),
            pattern=str(args.get("pattern", "**/*")),
            max_matches=int(args.get("max_matches", 50)),
        )
        return {
            "matches": [
                {"path": m.path, "line": m.line_number, "text": m.line}
                for m in matches
            ]
        }

    return {
        "read_file": read_file,
        "list_dir": list_dir,
        "search_text": search_text,
    }


def register_repo_fs_tools(registry: ToolRegistry, fs: RepoFilesystem) -> None:
    for name, fn in make_repo_fs_tools(fs).items():
        registry.register(name, fn)


def make_shell_tools(shell: ShellAdapter, *, cwd: Path) -> dict[str, ToolCallable]:
    def run_shell(args: dict[str, Any]) -> dict[str, Any]:
        argv = list(args.get("argv") or [])
        try:
            result = shell.run(argv, cwd=cwd)
        except CommandRefused as exc:
            return {"refused": True, "reason": str(exc)}
        return {
            "argv": list(result.argv),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "truncated": result.truncated,
        }

    return {"run_shell": run_shell}


def register_shell_tools(registry: ToolRegistry, shell: ShellAdapter, *, cwd: Path) -> None:
    for name, fn in make_shell_tools(shell, cwd=cwd).items():
        registry.register(name, fn)


def make_patch_tools() -> dict[str, ToolCallable]:
    def validate_patch_tool(args: dict[str, Any]) -> dict[str, Any]:
        diff_text = str(args.get("diff", ""))
        allowed = args.get("allowed_paths")
        parsed = parse_unified_diff(diff_text)
        report = validate_patch(
            parsed,
            allowed_paths=list(allowed) if isinstance(allowed, list) else None,
        )
        return {
            "ok": report.ok,
            "issues": list(report.issues),
            "files": [
                {
                    "old_path": f.old_path,
                    "new_path": f.new_path,
                    "hunks": len(f.hunks),
                }
                for f in parsed.files
            ],
            "total_hunks": parsed.total_hunks(),
        }

    return {"validate_patch": validate_patch_tool}


def register_patch_tools(registry: ToolRegistry) -> None:
    for name, fn in make_patch_tools().items():
        registry.register(name, fn)
