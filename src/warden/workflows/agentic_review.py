"""Agentic PR review workflow."""

from __future__ import annotations

from dataclasses import dataclass

from ..adapters.github import GitHubAdapter
from ..config import WardenConfig, load_config
from ..runtime.agent_loop import AgentBudget, AgentLoop, AgentOutcome, ToolRegistry
from ..runtime.memory import MemoryStore
from ..runtime.session_store import SessionStore
from ..runtime.thinkers import RuleBasedReviewerThinker
from ..runtime.tools import register_github_tools
from ..runtime.verifier import SchemaSpec


REVIEW_SCHEMA = SchemaSpec(
    required_keys=("verdict", "feedback", "blocking_issues", "pr_summary"),
    cited_fields=(),
)


_VALID_VERDICTS = {"accept", "revise", "reject"}


@dataclass(frozen=True, slots=True)
class AgenticReviewResult:
    outcome: AgentOutcome
    session_id: str


def run_agentic_review(
    *,
    repo: str,
    pr_number: int,
    config: WardenConfig | None = None,
    github_adapter: GitHubAdapter | None = None,
) -> AgenticReviewResult:
    resolved_config = config or load_config()
    adapter_owned = False
    if github_adapter is None:
        github_adapter = GitHubAdapter(resolved_config.github_token)
        adapter_owned = True

    session_store = SessionStore(resolved_config.data_dir / "sessions.sqlite3")
    memory = MemoryStore(resolved_config.data_dir / "memory.sqlite3")

    tools = ToolRegistry()
    register_github_tools(tools, github_adapter)

    session_id = f"cf-review-{repo.replace('/', '_')}-{pr_number}"
    session_store.create_session(
        session_id,
        workflow="agentic_review",
        metadata={"repo": repo, "pr": pr_number},
    )

    thinker = RuleBasedReviewerThinker(repo=repo, pr_number=pr_number)
    loop = AgentLoop(
        thinker=thinker,
        tools=tools,
        memory=memory,
        session_store=session_store,
        schema=REVIEW_SCHEMA,
        budget=AgentBudget(max_iterations=5, max_tool_calls=5),
    )

    outcome = loop.run(
        session_id=session_id,
        goal=f"Review pull request #{pr_number} in {repo} and return a structured verdict.",
        evidence_seed=f"repo={repo} pr={pr_number}",
        semantic_key=(repo, "review", f"pr#{pr_number}"),
    )

    if outcome.status == "verified" and isinstance(outcome.result, dict):
        verdict = outcome.result.get("verdict")
        if verdict not in _VALID_VERDICTS:
            outcome.status = "invalid_verdict"

    session_store.complete_session(session_id, outcome.status)
    if adapter_owned:
        github_adapter.close()
    return AgenticReviewResult(outcome=outcome, session_id=session_id)
