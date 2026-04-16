"""MCP server exposing warden workflows to any Claude Agent SDK client.

This module registers four tools that call warden's agentic
workflows end-to-end so tools like Claude Desktop, Cursor, OpenCode,
and Windsurf can drive warden remotely when configured with the
MiniMax Anthropic-compatible endpoint.

The SDK import is deferred so the rest of warden stays importable
without the SDK on the PATH. ``build_server`` raises a clear error if
called without the SDK installed.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .adapters.github import GitHubAdapter
from .config import load_config
from .workflows.agentic_coding import run_agentic_coding
from .workflows.agentic_investigation import run_agentic_investigation
from .workflows.agentic_review import run_agentic_review
from .workflows.agentic_triage import run_agentic_triage


SERVER_NAME = "warden"
SERVER_VERSION = "0.1.0"


def _outcome_to_payload(outcome: Any, session_id: str) -> dict[str, Any]:
    payload = asdict(outcome) if hasattr(outcome, "__dataclass_fields__") else dict(outcome)
    payload.pop("trajectory", None)
    payload.pop("verification", None)
    payload["session_id"] = session_id
    if outcome.verification is not None:
        payload["verification"] = {
            "ok": outcome.verification.ok,
            "reason": outcome.verification.reason(),
        }
    return payload


def _serialize(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, indent=2)


def build_server() -> Any:
    """Build and return the warden MCP server.

    Returns the object returned by ``create_sdk_mcp_server`` in the
    Claude Agent SDK. Callers pass this server to
    ``ClaudeAgentOptions(mcp_servers=...)`` to expose warden
    workflows alongside their other tools.
    """

    sdk = importlib.import_module("claude_agent_sdk")
    tool = sdk.tool
    create_sdk_mcp_server = sdk.create_sdk_mcp_server

    @tool(
        "warden_triage",
        "Run the warden agentic triage workflow against a GitHub issue.",
        {"repo": str, "issue": int},
    )
    async def triage_tool(args: dict[str, Any]) -> Any:
        config = load_config()
        adapter = GitHubAdapter(config.github_token)
        try:
            result = run_agentic_triage(
                repo=str(args["repo"]),
                issue_number=int(args["issue"]),
                config=config,
                github_adapter=adapter,
                use_live_model=False,
            )
        finally:
            adapter.close()
        return {
            "content": [
                {
                    "type": "text",
                    "text": _serialize(_outcome_to_payload(result.outcome, result.session_id)),
                }
            ]
        }

    @tool(
        "warden_investigate",
        "Run the warden investigation workflow over a local repository.",
        {"repo_root": str, "issue_title": str, "issue_body": str},
    )
    async def investigate_tool(args: dict[str, Any]) -> Any:
        result = run_agentic_investigation(
            repo_root=Path(str(args["repo_root"])),
            issue_title=str(args["issue_title"]),
            issue_body=str(args["issue_body"]),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": _serialize(_outcome_to_payload(result.outcome, result.session_id)),
                }
            ]
        }

    @tool(
        "warden_code",
        "Run the warden coding workflow for a targeted patch proposal.",
        {"repo_root": str, "target_file": str, "goal": str, "evidence": str},
    )
    async def code_tool(args: dict[str, Any]) -> Any:
        result = run_agentic_coding(
            repo_root=Path(str(args["repo_root"])),
            target_file=str(args["target_file"]),
            goal=str(args["goal"]),
            evidence=str(args["evidence"]),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": _serialize(_outcome_to_payload(result.outcome, result.session_id)),
                }
            ]
        }

    @tool(
        "warden_review",
        "Run the warden PR review workflow against a GitHub pull request.",
        {"repo": str, "pr": int},
    )
    async def review_tool(args: dict[str, Any]) -> Any:
        result = run_agentic_review(
            repo=str(args["repo"]),
            pr_number=int(args["pr"]),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": _serialize(_outcome_to_payload(result.outcome, result.session_id)),
                }
            ]
        }

    return create_sdk_mcp_server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        tools=[triage_tool, investigate_tool, code_tool, review_tool],
    )


def server_metadata() -> dict[str, Any]:
    """Return a non-SDK description of the exposed tools.

    Useful for documentation, tests, and clients that prefer to inspect
    tool schemas without loading the SDK.
    """

    return {
        "name": SERVER_NAME,
        "version": SERVER_VERSION,
        "tools": [
            {
                "name": "warden_triage",
                "description": "Run the warden agentic triage workflow against a GitHub issue.",
                "parameters": {"repo": "str", "issue": "int"},
            },
            {
                "name": "warden_investigate",
                "description": "Run the warden investigation workflow over a local repository.",
                "parameters": {"repo_root": "str", "issue_title": "str", "issue_body": "str"},
            },
            {
                "name": "warden_code",
                "description": "Run the warden coding workflow for a targeted patch proposal.",
                "parameters": {
                    "repo_root": "str",
                    "target_file": "str",
                    "goal": "str",
                    "evidence": "str",
                },
            },
            {
                "name": "warden_review",
                "description": "Run the warden PR review workflow against a GitHub pull request.",
                "parameters": {"repo": "str", "pr": "int"},
            },
        ],
    }
