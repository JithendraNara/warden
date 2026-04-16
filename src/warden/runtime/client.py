"""Factory for Claude Agent SDK option bundles.

Separated from the orchestrator so that option construction can be
unit-tested without importing the SDK at module load time.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from ..config import WardenConfig
from .subagents import all_subagents


@dataclass(frozen=True, slots=True)
class RuntimeBundle:
    """Container for the resolved SDK options and associated metadata."""

    options: Any
    model: str
    system_prompt: str
    subagent_names: tuple[str, ...]


BASE_SYSTEM_PROMPT = (
    "You are warden, an autonomous open-source maintainer assistant."
    " Operate across multiple repositories, prefer small reversible actions,"
    " always defer effectful operations to the approval hook, and cite the"
    " source of any claim you make."
)


def _load_sdk() -> Any:
    """Import the claude_agent_sdk lazily so tests don't require it."""

    return importlib.import_module("claude_agent_sdk")


def _agent_definition(sdk: Any, spec: Any) -> Any:
    return sdk.AgentDefinition(
        description=spec.description,
        prompt=spec.system_prompt,
        tools=list(spec.allowed_tools),
    )


def build_runtime_bundle(
    config: WardenConfig,
    *,
    extra_hooks: dict[str, Any] | None = None,
    mcp_servers: dict[str, Any] | None = None,
) -> RuntimeBundle:
    """Assemble ClaudeAgentOptions for a warden session."""

    sdk = _load_sdk()
    subagents = all_subagents()

    env = {
        "ANTHROPIC_BASE_URL": config.anthropic_base_url,
        "ANTHROPIC_MODEL": config.model,
    }
    if config.anthropic_auth_token:
        env["ANTHROPIC_AUTH_TOKEN"] = config.anthropic_auth_token

    options = sdk.ClaudeAgentOptions(
        model=config.model,
        system_prompt=BASE_SYSTEM_PROMPT,
        allowed_tools=["Read", "Glob", "Grep", "Agent", "WebSearch", "WebFetch"],
        agents={spec.name: _agent_definition(sdk, spec) for spec in subagents},
        hooks=extra_hooks or {},
        mcp_servers=mcp_servers or {},
        setting_sources=["project"],
        env=env,
    )

    return RuntimeBundle(
        options=options,
        model=config.model,
        system_prompt=BASE_SYSTEM_PROMPT,
        subagent_names=tuple(spec.name for spec in subagents),
    )
