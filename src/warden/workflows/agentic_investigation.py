"""Agentic investigation workflow.

The investigator reproduces reported bugs using the sandboxed
filesystem and (optionally) the shell adapter. It produces a
reproduction plan grounded in evidence from the actual repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..adapters.repo_fs import RepoFilesystem
from ..adapters.shell import ShellAdapter
from ..config import WardenConfig, load_config
from ..runtime.agent_loop import AgentBudget, AgentLoop, AgentOutcome, ToolRegistry
from ..runtime.memory import MemoryStore
from ..runtime.session_store import SessionStore
from ..runtime.thinkers import RuleBasedInvestigatorThinker
from ..runtime.tools import register_repo_fs_tools, register_shell_tools
from ..runtime.verifier import SchemaSpec


INVESTIGATION_SCHEMA = SchemaSpec(
    required_keys=("reproduced", "steps", "evidence", "hypotheses"),
    cited_fields=(),
)


@dataclass(frozen=True, slots=True)
class AgenticInvestigationResult:
    outcome: AgentOutcome
    session_id: str


def run_agentic_investigation(
    *,
    repo_root: Path,
    issue_title: str,
    issue_body: str,
    config: WardenConfig | None = None,
    shell: ShellAdapter | None = None,
) -> AgenticInvestigationResult:
    resolved_config = config or load_config()
    fs = RepoFilesystem(repo_root)
    session_store = SessionStore(resolved_config.data_dir / "sessions.sqlite3")
    memory = MemoryStore(resolved_config.data_dir / "memory.sqlite3")

    tools = ToolRegistry()
    register_repo_fs_tools(tools, fs)
    if shell is not None:
        register_shell_tools(tools, shell, cwd=fs.root)

    session_id = f"cf-invest-{fs.root.name}"
    session_store.create_session(
        session_id,
        workflow="agentic_investigation",
        metadata={"repo_root": str(fs.root), "issue_title": issue_title},
    )

    hint = _extract_hint(issue_title, issue_body)
    thinker = RuleBasedInvestigatorThinker(hint_phrase=hint)

    loop = AgentLoop(
        thinker=thinker,
        tools=tools,
        memory=memory,
        session_store=session_store,
        schema=INVESTIGATION_SCHEMA,
        budget=AgentBudget(max_iterations=5, max_tool_calls=6),
    )

    goal = (
        f"Reproduce and investigate the reported issue titled {issue_title!r}."
        f" Use sandboxed filesystem and shell tools only."
    )
    evidence_seed = f"{issue_title}\n{issue_body}".strip()
    outcome = loop.run(
        session_id=session_id,
        goal=goal,
        evidence_seed=evidence_seed,
        semantic_key=(fs.root.name, "investigation", issue_title[:120]),
    )
    session_store.complete_session(session_id, outcome.status)
    return AgenticInvestigationResult(outcome=outcome, session_id=session_id)


def _extract_hint(title: str, body: str) -> str:
    text = f"{title}\n{body}".lower()
    for candidate in ("config", "timeout", "token", "startup", "permission"):
        if candidate in text:
            return candidate
    words = [word for word in title.split() if len(word) > 4]
    return words[0] if words else "issue"
