from warden.runtime.hallucination_audit import (
    TriageGroundTruth,
    audit_triage,
)


GT = TriageGroundTruth(
    issue_number=42,
    title="App crashes on startup when config file is missing",
    body=(
        "Steps to reproduce: run ./app without config.yaml.\n"
        "Expected: helpful error. Actual: the binary crashes with a segfault."
    ),
    labels=("bug",),
    comments=0,
    author="reporter",
    url="https://github.com/example/demo/issues/42",
)


def test_grounded_triage_passes() -> None:
    payload = {
        "category": "bug",
        "severity": "high",
        "priority": "p1",
        "summary": 'The binary "crashes with a segfault" when config.yaml is missing.',
        "recommended_labels": ["bug", "severity/high"],
        "suggested_next_action": "needs_reproduction",
    }
    report = audit_triage(payload, ground_truth=GT)
    assert report.ok, report.reason()


def test_quote_not_in_source_fails() -> None:
    payload = {
        "category": "bug",
        "severity": "high",
        "priority": "p1",
        "summary": 'The maintainer said "this will be fixed tomorrow" in a comment.',
        "recommended_labels": ["bug"],
        "suggested_next_action": "needs_reproduction",
    }
    report = audit_triage(payload, ground_truth=GT)
    assert not report.ok
    assert any(f.code == "quote_not_in_source" for f in report.findings)


def test_fabricated_issue_reference_fails() -> None:
    payload = {
        "category": "bug",
        "severity": "high",
        "priority": "p1",
        "summary": "Possible duplicate of #999 which also mentions the segfault.",
        "recommended_labels": ["bug"],
        "suggested_next_action": "duplicate",
    }
    report = audit_triage(payload, ground_truth=GT)
    assert not report.ok
    assert any(f.code == "fabricated_issue_reference" for f in report.findings)


def test_unjustified_high_severity_fails() -> None:
    body_only_minor = TriageGroundTruth(
        issue_number=42,
        title="Typo in docs",
        body="There is a small typo in the README.",
        labels=(),
        comments=0,
        author="reporter",
        url="https://github.com/example/demo/issues/42",
    )
    payload = {
        "category": "docs",
        "severity": "high",
        "priority": "p1",
        "summary": "There is a typo in the README.",
        "recommended_labels": ["docs"],
        "suggested_next_action": "ready",
    }
    report = audit_triage(payload, ground_truth=body_only_minor)
    assert not report.ok
    assert any(f.code == "unjustified_severity" for f in report.findings)


def test_unknown_label_warning_does_not_fail() -> None:
    payload = {
        "category": "bug",
        "severity": "low",
        "priority": "p3",
        "summary": "Minor issue.",
        "recommended_labels": ["bug", "internal/weird-label"],
        "suggested_next_action": "ready",
    }
    report = audit_triage(payload, ground_truth=GT)
    # Warning-only findings should not flip ok to False.
    assert report.ok, report.reason()
    assert any(f.code == "unknown_label" for f in report.findings)


def test_fabricated_url_fails() -> None:
    payload = {
        "category": "bug",
        "severity": "low",
        "priority": "p3",
        "summary": "See https://other-domain.example/fake-path for details.",
        "recommended_labels": ["bug"],
        "suggested_next_action": "ready",
    }
    report = audit_triage(payload, ground_truth=GT)
    assert not report.ok
    assert any(f.code == "fabricated_url" for f in report.findings)
