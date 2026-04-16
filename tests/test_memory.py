from pathlib import Path

from warden.runtime.memory import MemoryStore, SemanticRecord, WorkingMemory


def test_working_memory_compacts_tool_results() -> None:
    mem = WorkingMemory(max_chars=400)
    mem.add("goal", {"text": "long goal" * 10})
    for i in range(10):
        mem.add("tool_result", {"i": i, "blob": "x" * 200})
    rendered = mem.render()
    # Oldest tool results should have been dropped.
    assert rendered.count("tool_result") <= 3
    assert "goal" in rendered


def test_memory_store_round_trips(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.record_step("s1", "tool_called", {"tool": "fetch_issue"})
    store.record_step("s1", "tool_called", {"tool": "list_similar_issues"})
    steps = store.session_steps("s1")
    assert [s["step_name"] for s in steps] == ["tool_called", "tool_called"]


def test_semantic_recall_matches_subject(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.remember(
        SemanticRecord(
            repo="example/demo",
            workflow="triage",
            subject="App crashes on startup",
            summary="Previous similar triage result.",
            tags=("bug", "severity/high"),
        )
    )
    hits = store.recall(repo="example/demo", workflow="triage", subject="crashes")
    assert len(hits) == 1
    assert hits[0].summary == "Previous similar triage result."
