"""Release-notes workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from ..runtime.orchestrator import Orchestrator, WorkflowEvent
from .prompts import ReleaseInputs, build_release_prompt


@dataclass(frozen=True, slots=True)
class ReleaseRequest:
    repo: str
    from_ref: str
    to_ref: str
    commit_summaries: tuple[str, ...]


async def run_release(
    orchestrator: Orchestrator,
    request: ReleaseRequest,
) -> AsyncIterator[WorkflowEvent]:
    inputs = ReleaseInputs(
        repo=request.repo,
        from_ref=request.from_ref,
        to_ref=request.to_ref,
        commit_summaries=tuple(request.commit_summaries),
    )
    prompt = build_release_prompt(inputs)
    metadata = {
        "repo": request.repo,
        "from_ref": request.from_ref,
        "to_ref": request.to_ref,
    }
    async for event in orchestrator.run_workflow(
        workflow="release",
        prompt=prompt,
        metadata=metadata,
    ):
        yield event
