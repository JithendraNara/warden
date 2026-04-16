"""Workflow orchestrator built on the Claude Agent SDK runtime.

The orchestrator wires together configuration, session persistence, hook
installation, and the actual ``query`` invocation. It intentionally keeps
the agent loop transparent: callers stream back structured events rather
than opaque SDK messages.
"""

from __future__ import annotations

import importlib
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from ..config import WardenConfig, load_config
from .client import build_runtime_bundle
from .hooks import (
    ApprovalRequest,
    make_post_tool_hook,
    make_pre_tool_hook,
    make_session_hooks,
)
from .session_store import SessionStore


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """Simplified event surfaced by :class:`Orchestrator`.

    The raw SDK messages are kept in ``raw`` for debugging, but workflows
    interact with ``kind`` and ``data``.
    """

    kind: str
    data: dict[str, Any]
    raw: Any | None = None


class Orchestrator:
    """High-level entry point for running warden workflows."""

    def __init__(
        self,
        config: WardenConfig | None = None,
        *,
        store: SessionStore | None = None,
        approver: Callable[[ApprovalRequest], bool] | None = None,
    ) -> None:
        self.config = config or load_config()
        self.store = store or SessionStore(self.config.data_dir / "sessions.sqlite3")
        self._approver = approver

    def _new_session_id(self) -> str:
        return f"cf-{uuid.uuid4().hex[:12]}"

    async def run_workflow(
        self,
        workflow: str,
        prompt: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[WorkflowEvent]:
        """Run a workflow against the configured MiniMax-backed runtime.

        Yields :class:`WorkflowEvent` instances as they are observed.
        The SQLite audit trail stays authoritative regardless of whether
        the caller consumes the whole stream.
        """

        sdk = importlib.import_module("claude_agent_sdk")

        session_id = self._new_session_id()
        self.store.create_session(session_id, workflow, metadata or {})

        pre_hook = make_pre_tool_hook(
            self.store,
            session_id,
            self.config.approval_mode,
            approver=self._approver,
        )
        post_hook = make_post_tool_hook(self.store, session_id)
        on_start, on_end = make_session_hooks(self.store, session_id)

        hooks = {
            "PreToolUse": [sdk.HookMatcher(matcher="", hooks=[pre_hook])],
            "PostToolUse": [sdk.HookMatcher(matcher="", hooks=[post_hook])],
            "SessionStart": [sdk.HookMatcher(matcher="", hooks=[on_start])],
            "SessionEnd": [sdk.HookMatcher(matcher="", hooks=[on_end])],
        }

        bundle = build_runtime_bundle(self.config, extra_hooks=hooks)
        status = "completed"
        try:
            async for message in sdk.query(prompt=prompt, options=bundle.options):
                yield _translate(message)
        except Exception as exc:
            status = "error"
            self.store.record_event(
                session_id,
                "workflow_error",
                {"error": repr(exc)},
            )
            raise
        finally:
            self.store.complete_session(session_id, status)


def _translate(message: Any) -> WorkflowEvent:
    """Convert SDK messages into :class:`WorkflowEvent`."""

    if hasattr(message, "result"):
        return WorkflowEvent(
            kind="result",
            data={"result": getattr(message, "result")},
            raw=message,
        )

    subtype = getattr(message, "subtype", None)
    data: dict[str, Any] = {}
    for attr in ("data", "message", "content"):
        value = getattr(message, attr, None)
        if value is not None:
            data[attr] = value
    return WorkflowEvent(
        kind=str(subtype or type(message).__name__),
        data=data,
        raw=message,
    )
