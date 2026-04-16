"""Agentic triage workflow.

This workflow exercises the real agent loop: it fetches live context,
invokes tools, records memory, and verifies the final result before
returning. It is what makes warden an agent platform rather than a
thin SDK wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..adapters.github import GitHubAdapter
from ..config import WardenConfig, load_config
from ..runtime.agent_loop import AgentBudget, AgentLoop, AgentOutcome, ToolRegistry
from ..runtime.memory import MemoryStore
from ..runtime.session_store import SessionStore
from ..runtime.thinkers import ClaudeAgentThinker, RuleBasedTriageThinker
from ..runtime.tools import register_github_tools
from ..runtime.verifier import SchemaSpec
from ..telemetry.tracing import Tracer
from .prompts import TriageInputs, build_triage_prompt


TRIAGE_SCHEMA = SchemaSpec(
    required_keys=(
        "category",
        "severity",
        "priority",
        "summary",
        "recommended_labels",
        "suggested_next_action",
    ),
    cited_fields=("summary",),
)

BASE_SYSTEM_PROMPT = (
    "You are warden's triage specialist. Use only the tool observations"
    " and the issue body as evidence. Never fabricate details."
)


@dataclass(frozen=True, slots=True)
class AgenticTriageResult:
    outcome: AgentOutcome
    session_id: str


def run_agentic_triage(
    repo: str,
    issue_number: int,
    *,
    config: WardenConfig | None = None,
    github_adapter: GitHubAdapter | None = None,
    use_live_model: bool = False,
    tracer: Tracer | None = None,
) -> AgenticTriageResult:
    """Run the agentic triage workflow end-to-end.

    ``use_live_model=True`` switches the thinker to
    :class:`ClaudeAgentThinker` which talks to MiniMax-M2.7 via the
    Anthropic-compatible endpoint. Leaving it ``False`` uses the
    deterministic rule-based thinker, which is ideal for tests, CI, and
    reproducible demos.
    """

    resolved_config = config or load_config()
    adapter_owned = False
    if github_adapter is None:
        github_adapter = GitHubAdapter(resolved_config.github_token)
        adapter_owned = True

    try:
        issue = github_adapter.fetch_issue(repo, issue_number)
    except Exception:
        if adapter_owned:
            github_adapter.close()
        raise

    session_store = SessionStore(resolved_config.data_dir / "sessions.sqlite3")
    memory = MemoryStore(resolved_config.data_dir / "memory.sqlite3")

    session_id = f"cf-triage-{repo.replace('/', '_')}-{issue_number}"
    session_store.create_session(
        session_id,
        workflow="agentic_triage",
        metadata={"repo": repo, "issue": issue_number, "use_live_model": use_live_model},
    )

    tools = ToolRegistry()
    register_github_tools(tools, github_adapter)

    if use_live_model:
        thinker = ClaudeAgentThinker(
            model=resolved_config.model,
            base_system_prompt=BASE_SYSTEM_PROMPT,
            tool_catalog={
                "fetch_issue": "Fetch a single issue and its comments.",
                "list_similar_issues": "Search the repository for related issues.",
                "get_repo_context": "Fetch repo-level summary and topics.",
            },
            min_tool_calls=1,
        )
    else:
        thinker = RuleBasedTriageThinker(repo=repo)

    loop = AgentLoop(
        thinker=thinker,
        tools=tools,
        memory=memory,
        session_store=session_store,
        schema=TRIAGE_SCHEMA,
        budget=AgentBudget(max_iterations=5, max_tool_calls=6),
        tracer=tracer,
    )

    prompt = build_triage_prompt(
        TriageInputs(
            repo=repo,
            issue=issue_number,
            issue_title=issue.title,
            issue_body=issue.body,
        )
    )
    evidence_seed = _evidence_from_issue(issue)

    outcome = loop.run(
        session_id=session_id,
        goal=prompt,
        evidence_seed=evidence_seed,
        semantic_key=(repo, "triage", issue.title[:120]),
    )
    session_store.complete_session(session_id, outcome.status)

    if adapter_owned:
        github_adapter.close()

    return AgenticTriageResult(outcome=outcome, session_id=session_id)


def _evidence_from_issue(issue: Any) -> str:
    return "\n".join(
        [
            f"Title: {getattr(issue, 'title', '')}",
            f"Labels: {', '.join(getattr(issue, 'labels', ()) or ())}",
            "Body:",
            str(getattr(issue, "body", "") or ""),
        ]
    )
