"""Hook factories for the Claude Agent SDK runtime.

Hooks are the enforcement boundary of warden. They decide whether a
tool call may proceed, stamp every action into the session audit log,
and surface approval events back to the operator.

We keep hooks implemented as plain callables rather than relying on
Claude Agent SDK-specific decorators so they are trivially unit-testable
without SDK imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .permissions import classify_tool
from .session_store import SessionStore


HookInput = dict[str, Any]
HookContext = dict[str, Any]
HookResult = dict[str, Any]
HookCallable = Callable[[HookInput, str | None, HookContext], Awaitable[HookResult]]


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    tool_name: str
    tool_input: dict[str, Any]
    reason: str


def _resolve_tool_name(input_data: HookInput) -> str:
    value = input_data.get("tool_name")
    if isinstance(value, str) and value:
        return value
    return "<unknown>"


def make_pre_tool_hook(
    store: SessionStore,
    session_id: str,
    approval_mode: str,
    approver: Callable[[ApprovalRequest], bool] | None = None,
) -> HookCallable:
    """Build a pre-tool-use hook.

    - In ``manual`` mode every tool usage requires approval.
    - In ``auto`` mode, only ``review``-tier tools pause for approval.
    - ``block``-tier tools are always refused.
    """

    async def hook(
        input_data: HookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> HookResult:
        tool_name = _resolve_tool_name(input_data)
        decision = classify_tool(tool_name)
        event_payload: dict[str, Any] = {
            "tool_name": tool_name,
            "risk": decision.risk,
            "reason": decision.reason,
            "approval_mode": approval_mode,
        }

        if decision.risk == "block":
            store.record_event(session_id, "tool_blocked", event_payload)
            return {"permissionDecision": "deny", "reason": decision.reason}

        needs_approval = approval_mode == "manual" or decision.risk == "review"
        if needs_approval:
            request = ApprovalRequest(
                tool_name=tool_name,
                tool_input=dict(input_data.get("tool_input") or {}),
                reason=decision.reason,
            )
            approved = bool(approver(request)) if approver else False
            event_payload["approval"] = "granted" if approved else "declined"
            store.record_event(session_id, "tool_approval", event_payload)
            if not approved:
                return {
                    "permissionDecision": "deny",
                    "reason": f"Approval declined for {tool_name}",
                }

        store.record_event(session_id, "tool_allowed", event_payload)
        return {"permissionDecision": "allow"}

    return hook


def make_post_tool_hook(
    store: SessionStore,
    session_id: str,
) -> HookCallable:
    """Build a post-tool-use hook that records the tool outcome."""

    async def hook(
        input_data: HookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> HookResult:
        tool_name = _resolve_tool_name(input_data)
        store.record_event(
            session_id,
            "tool_completed",
            {
                "tool_name": tool_name,
                "tool_output_present": "tool_output" in input_data,
            },
        )
        return {}

    return hook


def make_session_hooks(
    store: SessionStore,
    session_id: str,
) -> tuple[HookCallable, HookCallable]:
    """Session start/end hooks that bracket the audit log."""

    async def on_start(
        _input_data: HookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> HookResult:
        store.record_event(session_id, "session_start", {})
        return {}

    async def on_end(
        _input_data: HookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> HookResult:
        store.record_event(session_id, "session_end", {})
        return {}

    return on_start, on_end
