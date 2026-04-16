"""Agent loop for warden.

The loop turns warden from a wrapper into a real agent. It is a
deliberate, bounded implementation of Plan → Act → Observe → Verify →
Reflect with:

- **Budget**: hard caps on iterations and total tool calls.
- **Tool protocol**: every tool is a typed Python callable registered
  against a name. The agent emits structured tool calls; this module
  executes them and records the observation.
- **Verification**: the candidate result must clear :mod:`verifier`
  checks before the loop terminates.
- **Reflection**: on verifier failure the agent produces a new plan
  segment with explicit failure evidence until budget is exhausted.

This implementation is transport-agnostic. It talks to the model
through a callable ``ThinkerProtocol`` so we can plug the Claude Agent
SDK, a deterministic fake for tests, or a future model in place
without changing any of the control logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from ..telemetry.tracing import Tracer
from .memory import MemoryStore, SemanticRecord, WorkingMemory
from .session_store import SessionStore
from .verifier import SchemaSpec, VerificationReport, verify_result


# --------------------------------------------------------------------- #
# Protocols and data shapes                                             #
# --------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool invocation proposed by the thinker."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Thought:
    """A single turn produced by the thinker.

    Exactly one of ``tool_call`` or ``final_result`` is populated.
    ``commentary`` is free-form reasoning shown to the operator.
    """

    commentary: str
    tool_call: ToolCall | None = None
    final_result: dict[str, Any] | None = None


@runtime_checkable
class ThinkerProtocol(Protocol):
    """Any component that turns a rendered context into the next step."""

    def think(self, *, goal: str, context: str, iteration: int) -> Thought:
        ...


ToolCallable = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class ToolRegistry:
    tools: dict[str, ToolCallable] = field(default_factory=dict)

    def register(self, name: str, fn: ToolCallable) -> None:
        if name in self.tools:
            raise ValueError(f"Tool '{name}' already registered")
        self.tools[name] = fn

    def execute(self, call: ToolCall) -> dict[str, Any]:
        fn = self.tools.get(call.name)
        if fn is None:
            raise KeyError(f"Unknown tool '{call.name}'")
        return fn(dict(call.arguments))


# --------------------------------------------------------------------- #
# Loop                                                                  #
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class AgentBudget:
    max_iterations: int = 8
    max_tool_calls: int = 16


@dataclass(slots=True)
class AgentOutcome:
    status: str
    result: dict[str, Any] | None
    verification: VerificationReport | None
    iterations: int
    tool_calls: int
    trajectory: list[dict[str, Any]] = field(default_factory=list)


class AgentLoop:
    """Orchestrates a bounded agent trajectory with verification."""

    def __init__(
        self,
        *,
        thinker: ThinkerProtocol,
        tools: ToolRegistry,
        memory: MemoryStore,
        session_store: SessionStore,
        schema: SchemaSpec,
        budget: AgentBudget | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._thinker = thinker
        self._tools = tools
        self._memory = memory
        self._session_store = session_store
        self._schema = schema
        self._budget = budget or AgentBudget()
        self._tracer = tracer or Tracer(None)

    def run(
        self,
        *,
        session_id: str,
        goal: str,
        evidence_seed: str,
        semantic_key: tuple[str, str, str] | None = None,
    ) -> AgentOutcome:
        """Execute the agent loop against a goal and return the outcome."""

        working = WorkingMemory()
        working.add("goal", {"text": goal})
        working.add("seed", {"evidence": evidence_seed})

        if semantic_key is not None:
            repo, workflow, subject = semantic_key
            for record in self._memory.recall(repo=repo, workflow=workflow, subject=subject):
                working.add(
                    "semantic_recall",
                    {"summary": record.summary, "tags": list(record.tags)},
                )

        outcome = AgentOutcome(
            status="in_progress",
            result=None,
            verification=None,
            iterations=0,
            tool_calls=0,
        )

        evidence_buffer = [evidence_seed]

        for iteration in range(1, self._budget.max_iterations + 1):
            outcome.iterations = iteration
            rendered = working.render()
            with self._tracer.span(
                "warden.think",
                {"iteration": iteration, "session_id": session_id},
            ):
                thought = self._thinker.think(
                    goal=goal,
                    context=rendered,
                    iteration=iteration,
                )
            trajectory_entry = {
                "iteration": iteration,
                "commentary": thought.commentary,
            }

            self._session_store.record_event(
                session_id,
                "agent_thought",
                {"iteration": iteration, "commentary": thought.commentary},
            )
            working.add("thought", {"commentary": thought.commentary})

            if thought.tool_call is not None:
                if outcome.tool_calls >= self._budget.max_tool_calls:
                    trajectory_entry["termination"] = "tool_budget_exhausted"
                    outcome.trajectory.append(trajectory_entry)
                    outcome.status = "tool_budget_exhausted"
                    break

                tool_result = self._execute_tool(session_id, thought.tool_call)
                outcome.tool_calls += 1
                working.add(
                    "tool_result",
                    {
                        "tool": thought.tool_call.name,
                        "arguments": thought.tool_call.arguments,
                        "data": _truncate_tool_payload(tool_result),
                    },
                )
                evidence_buffer.append(json.dumps(tool_result, default=str))
                trajectory_entry["tool_call"] = thought.tool_call.name
                outcome.trajectory.append(trajectory_entry)
                continue

            if thought.final_result is None:
                trajectory_entry["termination"] = "no_progress"
                outcome.trajectory.append(trajectory_entry)
                continue

            evidence_corpus = "\n".join(evidence_buffer)
            with self._tracer.span(
                "warden.verify",
                {"iteration": iteration, "session_id": session_id},
            ):
                report = verify_result(
                    thought.final_result,
                    schema=self._schema,
                    evidence_corpus=evidence_corpus,
                )
            trajectory_entry["verified"] = report.ok
            trajectory_entry["verification_reason"] = report.reason()
            outcome.trajectory.append(trajectory_entry)
            self._session_store.record_event(
                session_id,
                "agent_verification",
                {"ok": report.ok, "reason": report.reason()},
            )

            if report.ok:
                outcome.status = "verified"
                outcome.result = thought.final_result
                outcome.verification = report
                self._memory.record_step(
                    session_id,
                    "final_result",
                    {"result": thought.final_result},
                )
                if semantic_key is not None and isinstance(thought.final_result, dict):
                    repo, workflow, subject = semantic_key
                    summary = str(thought.final_result.get("summary", ""))[:500]
                    self._memory.remember(
                        SemanticRecord(
                            repo=repo,
                            workflow=workflow,
                            subject=subject,
                            summary=summary,
                            tags=tuple(
                                str(label)
                                for label in thought.final_result.get("recommended_labels", [])
                            ),
                        )
                    )
                return outcome

            working.add(
                "reflection",
                {"failure_reason": report.reason(), "previous_result": thought.final_result},
            )
            self._memory.record_step(
                session_id,
                "reflection",
                {"failure_reason": report.reason()},
            )
            outcome.status = "reflecting"
            outcome.verification = report

        if outcome.status == "in_progress":
            outcome.status = "iteration_budget_exhausted"
        return outcome

    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #

    @staticmethod
    def _truncate_tool_payload_static(tool_result: dict[str, Any]) -> dict[str, Any]:
        return _truncate_tool_payload(tool_result)

    def _execute_tool(self, session_id: str, call: ToolCall) -> dict[str, Any]:
        tracer_ctx = self._tracer.span(
            "warden.tool",
            {"tool": call.name, "session_id": session_id},
        )
        tracer_ctx.__enter__()
        try:
            result = self._tools.execute(call)
        except Exception as exc:  # noqa: BLE001 - we log and surface error
            self._session_store.record_event(
                session_id,
                "tool_error",
                {"tool": call.name, "error": repr(exc)},
            )
            self._memory.record_step(
                session_id,
                "tool_error",
                {"tool": call.name, "error": repr(exc)},
            )
            tracer_ctx.__exit__(type(exc), exc, exc.__traceback__)
            return {"error": repr(exc)}
        self._session_store.record_event(
            session_id,
            "tool_called",
            {"tool": call.name, "arguments": dict(call.arguments)},
        )
        self._memory.record_step(
            session_id,
            "tool_called",
            {"tool": call.name, "arguments": dict(call.arguments)},
        )
        tracer_ctx.__exit__(None, None, None)
        return result


def _truncate_tool_payload(payload: dict[str, Any], *, max_chars: int = 1800) -> dict[str, Any]:
    """Return a copy of ``payload`` safe for inclusion in working memory.

    The working memory must be small enough to stay cheap to pass back
    to the thinker, but must preserve enough structure for the thinker
    to reason. We copy scalar keys verbatim and truncate long string
    values. Nested dicts and lists are kept intact but their string
    leaves are shortened.
    """

    def _truncate_value(value: Any) -> Any:
        if isinstance(value, str):
            if len(value) <= max_chars:
                return value
            return value[:max_chars] + "…"
        if isinstance(value, list):
            return [_truncate_value(item) for item in value[:10]]
        if isinstance(value, dict):
            return {key: _truncate_value(val) for key, val in value.items()}
        return value

    return {key: _truncate_value(val) for key, val in payload.items()}
