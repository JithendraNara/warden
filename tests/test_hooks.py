import asyncio
from pathlib import Path

from warden.runtime.hooks import ApprovalRequest, make_pre_tool_hook
from warden.runtime.session_store import SessionStore


def _run(coro: object) -> object:
    return asyncio.get_event_loop().run_until_complete(coro)  # type: ignore[arg-type]


def test_pre_hook_allows_safe_tools(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite3")
    store.create_session("s1", "triage", {})
    hook = make_pre_tool_hook(store, "s1", approval_mode="auto")

    async def runner() -> dict[str, object]:
        return await hook({"tool_name": "Read", "tool_input": {}}, None, {})

    assert asyncio.run(runner())["permissionDecision"] == "allow"
    events = [event.kind for event in store.list_events("s1")]
    assert events == ["tool_allowed"]


def test_pre_hook_requires_approval_for_write(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite3")
    store.create_session("s1", "triage", {})

    approvals: list[ApprovalRequest] = []

    def approver(request: ApprovalRequest) -> bool:
        approvals.append(request)
        return False

    hook = make_pre_tool_hook(store, "s1", approval_mode="auto", approver=approver)

    async def runner() -> dict[str, object]:
        return await hook({"tool_name": "Write", "tool_input": {"path": "x"}}, None, {})

    decision = asyncio.run(runner())
    assert decision["permissionDecision"] == "deny"
    assert len(approvals) == 1
    events = [event.kind for event in store.list_events("s1")]
    assert events == ["tool_approval"]
