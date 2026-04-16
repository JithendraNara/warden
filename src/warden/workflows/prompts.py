"""Prompt builders for warden workflows.

Each builder produces a single prompt string that the orchestrator passes
to the Claude Agent SDK ``query`` entry point. Keeping the prompts in
this module makes them unit-testable without a live model.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent


@dataclass(frozen=True, slots=True)
class TriageInputs:
    repo: str
    issue: int
    issue_title: str
    issue_body: str


def build_triage_prompt(inputs: TriageInputs) -> str:
    return dedent(
        f"""
        Use the triage-agent subagent to classify the following issue and
        return a JSON object with keys category, severity, priority, summary,
        recommended_labels, and suggested_next_action.

        Repository: {inputs.repo}
        Issue #{inputs.issue}: {inputs.issue_title}

        Body:
        ---
        {inputs.issue_body.strip()}
        ---
        """
    ).strip()


@dataclass(frozen=True, slots=True)
class ReleaseInputs:
    repo: str
    from_ref: str
    to_ref: str
    commit_summaries: tuple[str, ...]


def build_release_prompt(inputs: ReleaseInputs) -> str:
    commits = "\n".join(f"- {line}" for line in inputs.commit_summaries)
    return dedent(
        f"""
        Use the scribe-agent subagent to draft release notes for
        {inputs.repo} covering the range {inputs.from_ref}..{inputs.to_ref}.
        Return a Markdown document with sections for Highlights, Breaking
        Changes, Fixes, and Internal. Use the following commit summaries as
        the only source of truth:

        {commits}
        """
    ).strip()
