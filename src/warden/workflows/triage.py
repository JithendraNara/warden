"""Triage workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from ..runtime.orchestrator import Orchestrator, WorkflowEvent
from .prompts import TriageInputs, build_triage_prompt


@dataclass(frozen=True, slots=True)
class TriageRequest:
    repo: str
    issue: int
    issue_title: str
    issue_body: str


async def run_triage(
    orchestrator: Orchestrator,
    request: TriageRequest,
) -> AsyncIterator[WorkflowEvent]:
    inputs = TriageInputs(
        repo=request.repo,
        issue=request.issue,
        issue_title=request.issue_title,
        issue_body=request.issue_body,
    )
    prompt = build_triage_prompt(inputs)
    metadata = {"repo": request.repo, "issue": request.issue}
    async for event in orchestrator.run_workflow(
        workflow="triage",
        prompt=prompt,
        metadata=metadata,
    ):
        yield event
