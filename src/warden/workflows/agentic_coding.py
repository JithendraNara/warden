"""Agentic coding workflow.

The coder drafts a minimal patch grounded in the real file contents,
validates the diff, and returns a structured proposal. It never writes
to disk: the approval layer is the only path to applying the patch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..adapters.repo_fs import RepoFilesystem
from ..config import WardenConfig, load_config
from ..runtime.agent_loop import AgentBudget, AgentLoop, AgentOutcome, ToolRegistry
from ..runtime.memory import MemoryStore
from ..runtime.session_store import SessionStore
from ..runtime.thinkers import RuleBasedCoderThinker
from ..runtime.tools import register_patch_tools, register_repo_fs_tools
from ..runtime.verifier import SchemaSpec


CODING_SCHEMA = SchemaSpec(
    required_keys=(
        "affected_files",
        "diff",
        "rationale",
        "tests_to_add",
        "safety_notes",
    ),
    cited_fields=("rationale",),
)


@dataclass(frozen=True, slots=True)
class AgenticCodingResult:
    outcome: AgentOutcome
    session_id: str


def run_agentic_coding(
    *,
    repo_root: Path,
    target_file: str,
    goal: str,
    evidence: str,
    config: WardenConfig | None = None,
) -> AgenticCodingResult:
    resolved_config = config or load_config()
    fs = RepoFilesystem(repo_root)
    session_store = SessionStore(resolved_config.data_dir / "sessions.sqlite3")
    memory = MemoryStore(resolved_config.data_dir / "memory.sqlite3")

    tools = ToolRegistry()
    register_repo_fs_tools(tools, fs)
    register_patch_tools(tools)

    session_id = f"cf-code-{fs.root.name}-{Path(target_file).stem}"
    session_store.create_session(
        session_id,
        workflow="agentic_coding",
        metadata={"repo_root": str(fs.root), "target_file": target_file},
    )

    thinker = RuleBasedCoderThinker(target_file=target_file)
    loop = AgentLoop(
        thinker=thinker,
        tools=tools,
        memory=memory,
        session_store=session_store,
        schema=CODING_SCHEMA,
        budget=AgentBudget(max_iterations=4, max_tool_calls=4),
    )

    outcome = loop.run(
        session_id=session_id,
        goal=goal,
        evidence_seed=evidence,
        semantic_key=(fs.root.name, "coding", target_file),
    )
    session_store.complete_session(session_id, outcome.status)
    return AgenticCodingResult(outcome=outcome, session_id=session_id)
