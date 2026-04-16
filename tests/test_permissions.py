from warden.runtime.permissions import classify_tool


def test_safe_tools_classified_as_safe() -> None:
    for name in ["Read", "Glob", "Grep", "WebSearch", "WebFetch", "AskUserQuestion"]:
        assert classify_tool(name).risk == "safe"


def test_review_tools_require_review() -> None:
    for name in ["Write", "Edit", "Bash", "Monitor"]:
        assert classify_tool(name).risk == "review"


def test_unknown_tools_default_to_review() -> None:
    decision = classify_tool("MysteryTool")
    assert decision.risk == "review"
    assert "not recognized" in decision.reason
