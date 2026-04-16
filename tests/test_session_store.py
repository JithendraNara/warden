from pathlib import Path

from warden.runtime.session_store import SessionStore


def test_session_store_records_and_completes(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions.sqlite3")

    record = store.create_session("s1", "triage", {"repo": "example/demo"})
    assert record.id == "s1"
    assert record.status == "running"
    assert record.metadata == {"repo": "example/demo"}

    store.record_event("s1", "tool_allowed", {"tool_name": "Read"})
    store.record_event("s1", "tool_completed", {"tool_name": "Read"})
    events = store.list_events("s1")
    assert [event.kind for event in events] == ["tool_allowed", "tool_completed"]

    store.complete_session("s1", "completed")
    tail = store.tail_events(limit=5)
    assert tail[-1].kind == "tool_completed"
