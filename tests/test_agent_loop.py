from pathlib import Path
from typing import Any

from warden.runtime.agent_loop import (
    AgentBudget,
    AgentLoop,
    Thought,
    ToolCall,
    ToolRegistry,
)
from warden.runtime.memory import MemoryStore
from warden.runtime.session_store import SessionStore
from warden.runtime.verifier import SchemaSpec


class _ScriptedThinker:
    def __init__(self, thoughts: list[Thought]) -> None:
        self._thoughts = thoughts
        self.calls = 0

    def think(self, *, goal: str, context: str, iteration: int) -> Thought:
        thought = self._thoughts[min(self.calls, len(self._thoughts) - 1)]
        self.calls += 1
        return thought


SCHEMA = SchemaSpec(
    required_keys=("answer",),
    cited_fields=("answer",),
)


def _make_loop(tmp_path: Path, thinker: _ScriptedThinker) -> AgentLoop:
    tools = ToolRegistry()

    def echo_tool(args: dict[str, Any]) -> dict[str, Any]:
        return {"echo": args.get("text", "")}

    tools.register("echo", echo_tool)
    return AgentLoop(
        thinker=thinker,
        tools=tools,
        memory=MemoryStore(tmp_path / "memory.sqlite3"),
        session_store=SessionStore(tmp_path / "sessions.sqlite3"),
        schema=SCHEMA,
        budget=AgentBudget(max_iterations=4, max_tool_calls=4),
    )


def test_agent_loop_terminates_on_verified_result(tmp_path: Path) -> None:
    thinker = _ScriptedThinker(
        [
            Thought(
                commentary="Call echo first.",
                tool_call=ToolCall(name="echo", arguments={"text": "hello"}),
            ),
            Thought(
                commentary="Emit final answer citing echoed text.",
                final_result={"answer": "hello from echo tool"},
            ),
        ]
    )
    loop = _make_loop(tmp_path, thinker)
    session_store = loop._session_store  # type: ignore[attr-defined]
    session_store.create_session("s1", "test", {})

    outcome = loop.run(
        session_id="s1",
        goal="Return a final answer that says hello.",
        evidence_seed="context mentions hello",
    )
    assert outcome.status == "verified"
    assert outcome.result == {"answer": "hello from echo tool"}
    assert outcome.tool_calls == 1
    assert outcome.iterations == 2


def test_agent_loop_reflects_on_failed_verification(tmp_path: Path) -> None:
    thinker = _ScriptedThinker(
        [
            Thought(
                commentary="Unverified attempt.",
                final_result={"answer": "xylophone turbine synergy"},
            ),
            Thought(
                commentary="Retry with cited answer.",
                final_result={"answer": "hello world from retry"},
            ),
        ]
    )
    loop = _make_loop(tmp_path, thinker)
    loop._session_store.create_session("s2", "test", {})  # type: ignore[attr-defined]

    outcome = loop.run(
        session_id="s2",
        goal="Return an answer grounded in context.",
        evidence_seed="hello world is the allowed context",
    )
    assert outcome.status == "verified"
    assert outcome.iterations == 2


def test_agent_loop_respects_iteration_budget(tmp_path: Path) -> None:
    thinker = _ScriptedThinker(
        [
            Thought(
                commentary="Never finishes.",
                tool_call=ToolCall(name="echo", arguments={"text": "nope"}),
            )
        ]
    )
    loop = _make_loop(tmp_path, thinker)
    loop._session_store.create_session("s3", "test", {})  # type: ignore[attr-defined]

    outcome = loop.run(
        session_id="s3",
        goal="Hopeless goal.",
        evidence_seed="irrelevant",
    )
    assert outcome.status == "iteration_budget_exhausted"
    assert outcome.tool_calls <= 4
    assert outcome.iterations == 4
