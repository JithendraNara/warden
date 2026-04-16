"""Policy layer for tool usage.

The Claude Agent SDK exposes tools such as ``Write``, ``Edit``, and
``Bash`` that mutate external state. warden classifies each tool
invocation into one of three risk tiers so hooks can reject, review, or
permit the action consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RiskTier = Literal["safe", "review", "block"]


@dataclass(frozen=True, slots=True)
class ToolDecision:
    """Result of classifying a proposed tool call."""

    risk: RiskTier
    reason: str


_SAFE_TOOLS: frozenset[str] = frozenset(
    {"Read", "Glob", "Grep", "WebSearch", "WebFetch", "AskUserQuestion"}
)

_REVIEW_TOOLS: frozenset[str] = frozenset(
    {"Write", "Edit", "Bash", "Monitor"}
)

_BLOCKED_TOOLS: frozenset[str] = frozenset()


def classify_tool(tool_name: str) -> ToolDecision:
    """Return a :class:`ToolDecision` for the given tool name.

    Unknown tools default to ``review`` so that novel capabilities are never
    granted implicit trust.
    """

    if tool_name in _BLOCKED_TOOLS:
        return ToolDecision("block", f"{tool_name} is disallowed by policy")
    if tool_name in _SAFE_TOOLS:
        return ToolDecision("safe", f"{tool_name} is read-only in warden policy")
    if tool_name in _REVIEW_TOOLS:
        return ToolDecision("review", f"{tool_name} may modify state and needs approval")
    return ToolDecision("review", f"{tool_name} is not recognized and defaults to review")
