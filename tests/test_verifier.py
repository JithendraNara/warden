from warden.runtime.verifier import SchemaSpec, verify_result


SCHEMA = SchemaSpec(
    required_keys=(
        "category",
        "severity",
        "priority",
        "summary",
        "recommended_labels",
        "suggested_next_action",
    ),
    cited_fields=("summary",),
)


EVIDENCE = (
    "Title: App crashes on startup when config file is missing\n"
    "Body: Running ./app with no config.yaml results in a segfault."
)


def test_valid_payload_passes() -> None:
    payload = {
        "category": "bug",
        "severity": "high",
        "priority": "p1",
        "summary": "App crashes on startup because config.yaml is missing and the binary segfaults.",
        "recommended_labels": ["bug", "severity/high"],
        "suggested_next_action": "needs_reproduction",
    }
    report = verify_result(payload, schema=SCHEMA, evidence_corpus=EVIDENCE)
    assert report.ok, report.reason()


def test_missing_key_fails() -> None:
    payload = {
        "category": "bug",
        "severity": "low",
        "priority": "p3",
        "summary": "Small issue.",
    }
    report = verify_result(payload, schema=SCHEMA, evidence_corpus=EVIDENCE)
    assert not report.ok
    assert any(failure.code == "missing_key" for failure in report.failures)


def test_high_severity_without_impact_language_fails() -> None:
    payload = {
        "category": "bug",
        "severity": "critical",
        "priority": "p0",
        "summary": "Please check this config thing.",
        "recommended_labels": ["bug"],
        "suggested_next_action": "needs_reproduction",
    }
    report = verify_result(payload, schema=SCHEMA, evidence_corpus=EVIDENCE)
    assert not report.ok
    assert any(
        failure.code == "severity_justification" for failure in report.failures
    )


def test_uncited_summary_fails() -> None:
    payload = {
        "category": "bug",
        "severity": "low",
        "priority": "p3",
        "summary": "Xylophone synergy turbine resonates quietly.",
        "recommended_labels": ["bug"],
        "suggested_next_action": "ready",
    }
    report = verify_result(payload, schema=SCHEMA, evidence_corpus=EVIDENCE)
    assert not report.ok
    assert any(failure.code == "uncited_claim" for failure in report.failures)
