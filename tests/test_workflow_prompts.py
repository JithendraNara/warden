from warden.workflows.prompts import (
    ReleaseInputs,
    TriageInputs,
    build_release_prompt,
    build_triage_prompt,
)


def test_build_triage_prompt_includes_issue_reference() -> None:
    prompt = build_triage_prompt(
        TriageInputs(
            repo="example/demo",
            issue=42,
            issue_title="App crashes on startup",
            issue_body="Steps to reproduce…",
        )
    )
    assert "triage-agent" in prompt
    assert "#42" in prompt
    assert "example/demo" in prompt


def test_build_release_prompt_includes_commit_bullets() -> None:
    prompt = build_release_prompt(
        ReleaseInputs(
            repo="example/demo",
            from_ref="v0.1.0",
            to_ref="v0.2.0",
            commit_summaries=(
                "fix: handle missing config",
                "feat: add --dry-run",
            ),
        )
    )
    assert "scribe-agent" in prompt
    assert "v0.1.0..v0.2.0" in prompt
    assert "- fix: handle missing config" in prompt
