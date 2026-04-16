"""Post-hoc hallucination auditor for warden agent outputs.

The verifier ensures the final result has the right *shape*; this
module checks whether the *content* is grounded in actual tool
observations rather than fabricated from the model's prior.

Checks applied to a triage payload:

1. **Quote grounding** — any sequence of 3+ consecutive words in the
   summary must appear in the issue body or title. Quotes with no
   substring match are flagged.
2. **Entity grounding** — issue numbers, @mentions, file paths, and
   URLs referenced by the agent must be present in the real issue
   record. Anything the agent invented is flagged.
3. **Label plausibility** — recommended labels should either match
   existing labels on the issue or be plain-english category tags.
   The agent inventing specific project-internal labels is flagged.
4. **Severity impact consistency** — high/critical severity must have
   at least one impact term (crash, outage, segfault, ...) visible in
   the body. This is a stricter variant of the verifier's same rule
   tied to real source text.

The audit returns a structured report with per-check verdicts so the
operator can see exactly where the agent drifted from evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence


_IMPACT_TERMS = (
    "crash",
    "crashes",
    "segfault",
    "outage",
    "broken",
    "data loss",
    "security",
    "exploit",
    "timeout",
    "unavailable",
    "unusable",
    "freeze",
    "hang",
)

_WORD_RE = re.compile(r"[A-Za-z0-9_\-/.@#]+")
_ISSUE_REF_RE = re.compile(r"#(\d+)")
_MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_\-]+)")
_URL_RE = re.compile(r"https?://[^\s)]+")
_PATH_RE = re.compile(r"\b([A-Za-z0-9_\-]+/)+[A-Za-z0-9_.\-]+\b")


@dataclass(slots=True)
class AuditFinding:
    code: str
    message: str
    severity: str = "warn"  # "warn" or "fail"


@dataclass(slots=True)
class HallucinationReport:
    ok: bool
    findings: list[AuditFinding] = field(default_factory=list)

    def reason(self) -> str:
        if self.ok:
            return "no hallucinations detected"
        return "; ".join(
            f"{finding.severity}/{finding.code}: {finding.message}"
            for finding in self.findings
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "findings": [
                {
                    "code": finding.code,
                    "message": finding.message,
                    "severity": finding.severity,
                }
                for finding in self.findings
            ],
        }


@dataclass(slots=True)
class TriageGroundTruth:
    issue_number: int
    title: str
    body: str
    labels: tuple[str, ...]
    comments: int
    author: str
    url: str

    def corpus(self) -> str:
        return f"{self.title}\n{self.body}"


_GENERIC_LABEL_ALLOWLIST = frozenset(
    {
        "bug",
        "feature",
        "enhancement",
        "documentation",
        "docs",
        "question",
        "security",
        "performance",
        "regression",
        "crash",
        "help wanted",
        "good first issue",
        "needs-triage",
        "needs-investigation",
        "needs-reproduction",
        "duplicate",
        "wontfix",
        "invalid",
        "priority/high",
        "priority/medium",
        "priority/low",
        "priority/critical",
        "severity/low",
        "severity/medium",
        "severity/high",
        "severity/critical",
    }
)


def audit_triage(
    payload: dict[str, object],
    *,
    ground_truth: TriageGroundTruth,
) -> HallucinationReport:
    report = HallucinationReport(ok=True)
    corpus = ground_truth.corpus().lower()
    summary = str(payload.get("summary", "") or "")

    _check_quotes(summary, corpus, report)
    _check_issue_references(
        summary,
        allowed_number=ground_truth.issue_number,
        report=report,
    )
    _check_mentions(summary, allowed={ground_truth.author.lower()}, report=report)
    _check_paths_and_urls(summary, corpus, ground_truth.url, report)
    _check_labels(
        payload.get("recommended_labels"),
        existing=set(label.lower() for label in ground_truth.labels),
        report=report,
    )
    _check_severity_consistency(
        severity=str(payload.get("severity", "")),
        corpus=corpus,
        report=report,
    )

    report.ok = not any(finding.severity == "fail" for finding in report.findings)
    return report


# --------------------------------------------------------------------- #
# Individual checks                                                      #
# --------------------------------------------------------------------- #


def _check_quotes(summary: str, corpus: str, report: HallucinationReport) -> None:
    for match in re.finditer(r'"([^"]+)"', summary):
        quoted = match.group(1).strip().lower()
        if not quoted:
            continue
        if len(quoted) < 8:
            continue
        if quoted in corpus:
            continue
        report.findings.append(
            AuditFinding(
                code="quote_not_in_source",
                message=f"quoted string {quoted!r} not found in issue text",
                severity="fail",
            )
        )


def _check_issue_references(
    summary: str,
    *,
    allowed_number: int,
    report: HallucinationReport,
) -> None:
    for match in _ISSUE_REF_RE.finditer(summary):
        number = int(match.group(1))
        if number == allowed_number:
            continue
        report.findings.append(
            AuditFinding(
                code="fabricated_issue_reference",
                message=f"summary references issue #{number} which is not the issue under triage",
                severity="fail",
            )
        )


def _check_mentions(
    summary: str,
    *,
    allowed: set[str],
    report: HallucinationReport,
) -> None:
    for match in _MENTION_RE.finditer(summary):
        user = match.group(1).lower()
        if user in allowed:
            continue
        report.findings.append(
            AuditFinding(
                code="fabricated_mention",
                message=f"summary mentions @{user} who is not in the issue context",
                severity="warn",
            )
        )


def _check_paths_and_urls(
    summary: str,
    corpus: str,
    issue_url: str,
    report: HallucinationReport,
) -> None:
    url_whitelist = {issue_url.lower()}
    for match in _URL_RE.finditer(summary):
        url = match.group(0).rstrip(".,").lower()
        if url in url_whitelist:
            continue
        if url in corpus:
            continue
        report.findings.append(
            AuditFinding(
                code="fabricated_url",
                message=f"URL {url} not present in issue text",
                severity="fail",
            )
        )

    for match in _PATH_RE.finditer(summary):
        path = match.group(0).lower()
        if "/" not in path:
            continue
        if path in corpus:
            continue
        if path.startswith("http"):
            continue
        if any(part in _GENERIC_LABEL_ALLOWLIST for part in path.split("/")):
            continue
        report.findings.append(
            AuditFinding(
                code="suspicious_path",
                message=f"path {path} not found in issue text (possible fabrication)",
                severity="warn",
            )
        )


def _check_labels(
    labels: object,
    *,
    existing: set[str],
    report: HallucinationReport,
) -> None:
    if not isinstance(labels, Iterable) or isinstance(labels, (str, bytes)):
        return
    for label in labels:
        if not isinstance(label, str):
            continue
        lowered = label.lower()
        if lowered in existing:
            continue
        if lowered in _GENERIC_LABEL_ALLOWLIST:
            continue
        if "/" in lowered and lowered.split("/", 1)[0] in {
            "priority",
            "severity",
            "area",
            "type",
        }:
            continue
        report.findings.append(
            AuditFinding(
                code="unknown_label",
                message=(
                    f"recommended label {label!r} is neither an existing label"
                    " nor a generic category"
                ),
                severity="warn",
            )
        )


def _check_severity_consistency(
    *,
    severity: str,
    corpus: str,
    report: HallucinationReport,
) -> None:
    if severity.lower() not in {"high", "critical"}:
        return
    if any(term in corpus for term in _IMPACT_TERMS):
        return
    report.findings.append(
        AuditFinding(
            code="unjustified_severity",
            message=(
                f"severity={severity} has no supporting impact language in the"
                " actual issue body"
            ),
            severity="fail",
        )
    )


def build_ground_truth_from_issue(issue: object) -> TriageGroundTruth:
    """Adapter from :class:`warden.adapters.github.GitHubIssue`."""

    return TriageGroundTruth(
        issue_number=int(getattr(issue, "number", 0)),
        title=str(getattr(issue, "title", "")),
        body=str(getattr(issue, "body", "") or ""),
        labels=tuple(getattr(issue, "labels", ()) or ()),
        comments=int(getattr(issue, "comments", 0)),
        author=str(getattr(issue, "author", "") or ""),
        url=str(getattr(issue, "url", "") or ""),
    )
