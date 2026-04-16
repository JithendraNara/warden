"""Subagent registry for warden.

Each specialist agent is defined declaratively so workflows can enumerate
capabilities and operators can audit prompts without running anything.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubagentSpec:
    """Declarative definition of a specialist agent."""

    name: str
    description: str
    system_prompt: str
    allowed_tools: tuple[str, ...]
    skills: tuple[str, ...]


TRIAGE_AGENT = SubagentSpec(
    name="triage-agent",
    description=(
        "Classify GitHub issues and pull requests into category, severity, and"
        " priority, and draft a short neutral summary for the maintainer."
    ),
    system_prompt=(
        "You are warden's triage specialist. Read the issue or pull"
        " request context and produce structured triage output with category,"
        " severity, priority, summary, recommended labels, and suggested next"
        " action. Be concise, reference exact quotes, and refuse to speculate"
        " without evidence."
    ),
    allowed_tools=("Read", "Glob", "Grep", "WebSearch", "WebFetch"),
    skills=("issue-triage",),
)


INVESTIGATOR_AGENT = SubagentSpec(
    name="investigator-agent",
    description=(
        "Reproduce bug reports locally when possible and assemble a context"
        " package of logs, failing snippets, and hypothesis notes."
    ),
    system_prompt=(
        "You are warden's investigator. Build a reproduction plan, try"
        " minimal steps to confirm the failure, and record hypotheses with"
        " supporting evidence. Never modify repository state without approval."
    ),
    allowed_tools=("Read", "Glob", "Grep", "Bash"),
    skills=("bug-reproduction",),
)


CODER_AGENT = SubagentSpec(
    name="coder-agent",
    description=(
        "Draft minimal, well-explained patches for issues once a reproduction"
        " is available. Always attach a rationale and a safety note."
    ),
    system_prompt=(
        "You are warden's coding specialist. Propose the smallest patch"
        " that fixes the reproduced issue. Explain the change, list affected"
        " files, and flag risky assumptions. Do not write to disk until the"
        " reviewer has approved the plan."
    ),
    allowed_tools=("Read", "Glob", "Grep", "Write", "Edit"),
    skills=("code-fix-proposal",),
)


REVIEWER_AGENT = SubagentSpec(
    name="reviewer-agent",
    description=(
        "Review a proposed patch for correctness, safety, test coverage, and"
        " compatibility with the warden safety model."
    ),
    system_prompt=(
        "You are warden's reviewer. Critique the proposed change on"
        " correctness, tests, safety, and style. Return a structured verdict"
        " (accept, revise, reject) with specific line-anchored feedback."
    ),
    allowed_tools=("Read", "Glob", "Grep"),
    skills=("pr-review",),
)


SCRIBE_AGENT = SubagentSpec(
    name="scribe-agent",
    description=(
        "Draft polished maintainer communications: issue responses, release"
        " notes, summaries, and follow-up comments."
    ),
    system_prompt=(
        "You are warden's scribe. Write calm, accurate, maintainer-voice"
        " responses. Prefer short paragraphs, headings, and concrete callouts."
        " Reference source issues or commits when relevant."
    ),
    allowed_tools=("Read", "Glob", "Grep", "WebSearch"),
    skills=("release-notes",),
)


REGISTRY: dict[str, SubagentSpec] = {
    agent.name: agent
    for agent in (
        TRIAGE_AGENT,
        INVESTIGATOR_AGENT,
        CODER_AGENT,
        REVIEWER_AGENT,
        SCRIBE_AGENT,
    )
}


def all_subagents() -> tuple[SubagentSpec, ...]:
    return tuple(REGISTRY.values())


def get_subagent(name: str) -> SubagentSpec:
    try:
        return REGISTRY[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"Unknown warden subagent: {name!r}") from exc
