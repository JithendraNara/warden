from warden.runtime.subagents import REGISTRY, all_subagents, get_subagent


def test_registry_contains_expected_agents() -> None:
    names = {spec.name for spec in all_subagents()}
    assert names == {
        "triage-agent",
        "investigator-agent",
        "coder-agent",
        "reviewer-agent",
        "scribe-agent",
    }


def test_get_subagent_returns_spec() -> None:
    spec = get_subagent("triage-agent")
    assert spec.description.startswith("Classify")
    assert "Read" in spec.allowed_tools


def test_all_subagents_have_documented_skills() -> None:
    for spec in REGISTRY.values():
        assert spec.skills, f"{spec.name} missing skills metadata"
        assert spec.system_prompt.strip(), f"{spec.name} missing system prompt"
