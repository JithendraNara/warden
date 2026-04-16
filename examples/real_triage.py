"""End-to-end warden triage against a real GitHub issue.

Usage:

    python -m examples.real_triage --repo owner/name --issue N

Environment:
    ANTHROPIC_BASE_URL      MiniMax Anthropic-compatible endpoint.
    ANTHROPIC_AUTH_TOKEN    MiniMax API key.
    ANTHROPIC_MODEL         MiniMax-M2.7 (or compatible).
    WARDEN_GITHUB_TOKEN     GitHub token with read access to the repo.

The script:

1. Fetches the real issue via the live :class:`GitHubAdapter`.
2. Runs warden's agentic triage loop with the Claude Agent SDK thinker
   backed by MiniMax.
3. Passes the resulting payload through the hallucination auditor,
   which cross-checks every quote, entity, and severity claim against
   the real issue content.
4. Prints a structured report so the operator can see whether the
   agent stayed grounded or drifted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from warden.adapters.github import GitHubAdapter
from warden.config import load_config
from warden.runtime.fact_checker import FactChecker
from warden.runtime.hallucination_audit import (
    audit_triage,
    build_ground_truth_from_issue,
)
from warden.workflows.agentic_triage import run_agentic_triage


def main() -> int:
    parser = argparse.ArgumentParser(description="Run warden triage against a real GitHub issue")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--issue", required=True, type=int, help="issue number")
    parser.add_argument(
        "--live-model",
        action="store_true",
        help="Drive the Claude Agent SDK thinker against MiniMax (requires ANTHROPIC_AUTH_TOKEN).",
    )
    args = parser.parse_args()

    config = load_config()
    github_token = os.environ.get("WARDEN_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print(
            "Set WARDEN_GITHUB_TOKEN or GITHUB_TOKEN to query real GitHub issues.",
            file=sys.stderr,
        )
        return 2

    adapter = GitHubAdapter(github_token)
    try:
        issue = adapter.fetch_issue(args.repo, args.issue)
        ground_truth = build_ground_truth_from_issue(issue)

        with tempfile.TemporaryDirectory() as tmp:
            run_config = config
            run_config = type(run_config)(
                anthropic_base_url=config.anthropic_base_url,
                anthropic_auth_token=config.anthropic_auth_token,
                model=config.model,
                github_token=github_token,
                approval_mode="auto",
                data_dir=Path(tmp),
            )
            result = run_agentic_triage(
                repo=args.repo,
                issue_number=args.issue,
                config=run_config,
                github_adapter=adapter,
                use_live_model=args.live_model,
            )
    finally:
        adapter.close()

    outcome = result.outcome
    audit = audit_triage(outcome.result or {}, ground_truth=ground_truth) if outcome.result else None

    # Real-world fact-check: package refs, CVEs, URLs produced by the agent
    # are verified against PyPI/npm/NVD/HEAD endpoints.
    fact_report = None
    if outcome.result:
        checker = FactChecker()
        try:
            fact_texts = [
                str(outcome.result.get("summary", "")),
                str(outcome.result.get("suggested_next_action", "")),
                " ".join(str(label) for label in outcome.result.get("recommended_labels", [])),
            ]
            fact_report = checker.check_text("\n".join(fact_texts))
        finally:
            checker.close()

    summary = {
        "repo": args.repo,
        "issue": args.issue,
        "issue_title": ground_truth.title,
        "issue_url": ground_truth.url,
        "issue_body_len": len(ground_truth.body),
        "issue_labels": list(ground_truth.labels),
        "issue_comments": ground_truth.comments,
        "agent": {
            "status": outcome.status,
            "iterations": outcome.iterations,
            "tool_calls": outcome.tool_calls,
            "tools_called": [
                step.get("tool_call")
                for step in outcome.trajectory
                if step.get("tool_call")
            ],
            "verified": bool(outcome.verification and outcome.verification.ok),
            "verification_reason": (
                outcome.verification.reason() if outcome.verification else None
            ),
            "session_id": result.session_id,
            "payload": outcome.result,
        },
        "hallucination_audit": audit.to_dict() if audit else None,
        "real_world_fact_check": fact_report.to_dict() if fact_report else None,
    }
    print(json.dumps(summary, indent=2, default=str))

    failed = (
        outcome.status != "verified"
        or (audit and not audit.ok)
        or (fact_report and not fact_report.ok)
    )
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
