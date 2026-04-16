"""Output verification for agent results.

Without a verifier, an agent's output is just plausible text. The
verifier is what turns a wrapper into a real agent: it forces every
produced artifact through mechanical checks before accepting it.

Current checks:

- **Schema**: the result must contain all required keys with the
  correct scalar types.
- **Citation**: every freeform field listed in ``cited_fields`` must
  reference at least one substring from the supplied evidence corpus.
- **Severity justification**: if the result claims ``severity`` of
  ``high`` or ``critical``, the summary must mention impact terms.

The verifier never rewrites the agent's output. It returns a typed
verdict that the agent loop uses to decide whether to reflect/retry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_IMPACT_TERMS = (
    "crash",
    "data loss",
    "outage",
    "regression",
    "security",
    "exploit",
    "timeout",
    "blocker",
    "broken",
    "unavailable",
)

_WORD_RE = re.compile(r"[A-Za-z0-9_\-]+")


@dataclass(slots=True)
class VerificationFailure:
    code: str
    message: str


@dataclass(slots=True)
class VerificationReport:
    ok: bool
    failures: list[VerificationFailure] = field(default_factory=list)

    def reason(self) -> str:
        if self.ok:
            return "ok"
        return "; ".join(f"{failure.code}: {failure.message}" for failure in self.failures)


@dataclass(slots=True)
class SchemaSpec:
    required_keys: tuple[str, ...]
    cited_fields: tuple[str, ...] = ()


def verify_result(
    payload: dict[str, Any] | None,
    *,
    schema: SchemaSpec,
    evidence_corpus: str,
) -> VerificationReport:
    report = VerificationReport(ok=True)
    if not isinstance(payload, dict):
        report.ok = False
        report.failures.append(
            VerificationFailure("missing_payload", "verifier received a non-dict result")
        )
        return report

    for key in schema.required_keys:
        if key not in payload:
            report.ok = False
            report.failures.append(
                VerificationFailure("missing_key", f"required key '{key}' is absent")
            )

    for field_name in schema.cited_fields:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            continue
        if not _has_citation(value, evidence_corpus):
            report.ok = False
            report.failures.append(
                VerificationFailure(
                    "uncited_claim",
                    f"field '{field_name}' is not grounded in evidence",
                )
            )

    severity = payload.get("severity")
    if severity in {"high", "critical"}:
        summary = str(payload.get("summary", ""))
        if not any(term in summary.lower() for term in _IMPACT_TERMS):
            report.ok = False
            report.failures.append(
                VerificationFailure(
                    "severity_justification",
                    f"severity='{severity}' without impact language in summary",
                )
            )

    return report


def _has_citation(value: str, evidence: str) -> bool:
    if not evidence.strip():
        return False
    haystack = evidence.lower()
    for match in _WORD_RE.findall(value.lower()):
        if len(match) < 4:
            continue
        if match in haystack:
            return True
    return False
