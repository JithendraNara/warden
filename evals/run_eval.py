"""Scenario evaluation harness for warden.

This harness runs two classes of checks:

1. **Static scenarios** (Phase 1) verify subagent routing, safety
   gating, and output schema presence without touching adapters or
   loops.
2. **Agentic scenarios** (Phase 2+) actually run the agent loops
   against in-memory adapters, exercising tool calls, memory, and
   verification end-to-end.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from warden.adapters.github import GitHubIssue, GitHubPullRequest, RepoSummary
from warden.config import WardenConfig
from warden.runtime.permissions import classify_tool
from warden.runtime.subagents import REGISTRY
from warden.workflows.agentic_coding import run_agentic_coding
from warden.workflows.agentic_investigation import run_agentic_investigation
from warden.workflows.agentic_review import run_agentic_review
from warden.workflows.agentic_triage import run_agentic_triage

from tests.support.fakes import FakeGitHubAdapter  # type: ignore[import-not-found]

SCENARIO_PATH = Path(__file__).with_name("scenarios.json")

ROUTING_TARGET = 0.80
SAFETY_TARGET = 1.00
AGENTIC_TARGET = 1.00

AGENTIC_WORKFLOWS = {
    "agentic_triage",
    "agentic_investigation",
    "agentic_coding",
    "agentic_review",
}


def _load_scenarios() -> list[dict[str, Any]]:
    return json.loads(SCENARIO_PATH.read_text())


def _is_agentic(scenario: dict[str, Any]) -> bool:
    return scenario.get("workflow") in AGENTIC_WORKFLOWS


def _routing_ok(scenario: dict[str, Any]) -> bool:
    expected = scenario["expected"]["subagent"]
    return expected in REGISTRY


def _safety_ok(scenario: dict[str, Any]) -> bool:
    expected = scenario["expected"]
    requires_approval = bool(expected.get("requires_approval"))
    subagent = expected.get("subagent", "")
    if subagent not in REGISTRY:
        return False
    tools = REGISTRY[subagent].allowed_tools
    review_needed = any(classify_tool(tool).risk == "review" for tool in tools)
    return requires_approval == review_needed


def _shape_ok(scenario: dict[str, Any]) -> bool:
    keys = scenario["expected"].get("output_keys", [])
    return all(isinstance(key, str) and key for key in keys)


def _make_config(data_dir: Path) -> WardenConfig:
    return WardenConfig(
        anthropic_base_url="https://api.minimax.io/anthropic",
        anthropic_auth_token=None,
        model="MiniMax-M2.7",
        github_token=None,
        approval_mode="auto",
        data_dir=data_dir,
    )


def _run_triage_scenario(scenario: dict[str, Any], data_dir: Path) -> tuple[bool, dict[str, Any]]:
    inputs = scenario["inputs"]
    expected = scenario["expected"]
    issue = GitHubIssue(
        number=int(inputs["issue"]),
        title=str(inputs["issue_title"]),
        body=str(inputs["issue_body"]),
        state="open",
        labels=(),
        comments=0,
        author="reporter",
        url="https://example",
    )
    similar = GitHubIssue(
        number=int(inputs["issue"]) - 1,
        title=f"related: {inputs['issue_title']}",
        body="Related historic issue.",
        state="closed",
        labels=("bug",),
        comments=1,
        author="other",
        url="https://example",
    )
    adapter = FakeGitHubAdapter(
        issues=[(inputs["repo"], issue)],
        comments=[(inputs["repo"], int(inputs["issue"]), [])],
        similar=[(inputs["repo"], [similar])],
        repos=[
            (
                inputs["repo"],
                RepoSummary(
                    full_name=inputs["repo"],
                    description="Eval fixture",
                    default_branch="main",
                    language="Python",
                    topics=(),
                ),
            )
        ],
    )
    result = run_agentic_triage(
        repo=inputs["repo"],
        issue_number=int(inputs["issue"]),
        config=_make_config(data_dir),
        github_adapter=adapter,
        use_live_model=False,
    )
    return _check_outcome(result.outcome, expected)


def _run_investigation_scenario(scenario: dict[str, Any], data_dir: Path) -> tuple[bool, dict[str, Any]]:
    inputs = scenario["inputs"]
    expected = scenario["expected"]
    repo_root = data_dir / "repo"
    for relative, content in inputs.get("files", {}).items():
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    result = run_agentic_investigation(
        repo_root=repo_root,
        issue_title=inputs["issue_title"],
        issue_body=inputs["issue_body"],
        config=_make_config(data_dir / "data"),
    )
    return _check_outcome(result.outcome, expected)


def _run_coding_scenario(scenario: dict[str, Any], data_dir: Path) -> tuple[bool, dict[str, Any]]:
    inputs = scenario["inputs"]
    expected = scenario["expected"]
    repo_root = data_dir / "repo"
    for relative, content in inputs.get("files", {}).items():
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    result = run_agentic_coding(
        repo_root=repo_root,
        target_file=inputs["target_file"],
        goal=inputs["goal"],
        evidence=inputs["evidence"],
        config=_make_config(data_dir / "data"),
    )
    return _check_outcome(result.outcome, expected)


def _run_review_scenario(scenario: dict[str, Any], data_dir: Path) -> tuple[bool, dict[str, Any]]:
    inputs = scenario["inputs"]
    expected = scenario["expected"]
    pr = GitHubPullRequest(
        number=int(inputs["pr"]),
        title=str(inputs["pr_title"]),
        body=str(inputs["pr_body"]),
        state="open",
        draft=False,
        base_ref="main",
        head_ref="feature",
        url="https://example",
        changed_files=1,
        additions=1,
        deletions=0,
    )
    adapter = FakeGitHubAdapter(
        pull_requests=[(inputs["repo"], pr)],
        pr_diffs=[(inputs["repo"], int(inputs["pr"]), str(inputs["diff"]))],
    )
    result = run_agentic_review(
        repo=inputs["repo"],
        pr_number=int(inputs["pr"]),
        config=_make_config(data_dir),
        github_adapter=adapter,
    )
    return _check_outcome(result.outcome, expected)


def _check_outcome(outcome: Any, expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    verified_ok = True
    if expected.get("require_verified"):
        verified_ok = outcome.status == "verified"
    tool_calls_ok = outcome.tool_calls >= int(expected.get("min_tool_calls", 0))
    payload = outcome.result or {}
    keys_ok = all(key in payload for key in expected.get("output_keys", []))
    ok = verified_ok and tool_calls_ok and keys_ok
    diagnostics = {
        "status": outcome.status,
        "tool_calls": outcome.tool_calls,
        "iterations": outcome.iterations,
        "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
    }
    return ok, diagnostics


def _run_agentic(scenario: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    workflow = scenario.get("workflow")
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        if workflow == "agentic_triage":
            return _run_triage_scenario(scenario, data_dir)
        if workflow == "agentic_investigation":
            return _run_investigation_scenario(scenario, data_dir)
        if workflow == "agentic_coding":
            return _run_coding_scenario(scenario, data_dir)
        if workflow == "agentic_review":
            return _run_review_scenario(scenario, data_dir)
        return False, {"error": f"unknown agentic workflow: {workflow}"}


def _score(scenarios: Iterable[dict[str, Any]], agentic_results: dict[str, bool]) -> dict[str, Any]:
    scenarios = list(scenarios)
    total = len(scenarios)
    routing = sum(1 for s in scenarios if _routing_ok(s))
    safety = sum(1 for s in scenarios if _safety_ok(s))
    shape = sum(1 for s in scenarios if _shape_ok(s))
    agentic_total = sum(1 for s in scenarios if _is_agentic(s))
    agentic_passed = sum(1 for result in agentic_results.values() if result)
    agentic_rate = round(agentic_passed / agentic_total, 2) if agentic_total else 1.0
    return {
        "total": total,
        "routing_precision": round(routing / total, 2) if total else 0.0,
        "safety_compliance": round(safety / total, 2) if total else 0.0,
        "shape_validity": round(shape / total, 2) if total else 0.0,
        "agentic_pass_rate": agentic_rate,
        "agentic_scenarios": agentic_total,
    }


def run_eval(only: str | None = None) -> int:
    scenarios = _load_scenarios()
    if only is not None:
        scenarios = [s for s in scenarios if s["id"] == only]
        if not scenarios:
            print(f"No scenario matched id {only!r}", file=sys.stderr)
            return 2

    agentic_results: dict[str, bool] = {}
    for scenario in scenarios:
        record = {
            "id": scenario["id"],
            "workflow": scenario["workflow"],
            "routing_ok": _routing_ok(scenario),
            "safety_ok": _safety_ok(scenario),
            "shape_ok": _shape_ok(scenario),
        }
        if _is_agentic(scenario):
            ok, diagnostics = _run_agentic(scenario)
            record["agentic_ok"] = ok
            record["agentic_diagnostics"] = diagnostics
            agentic_results[scenario["id"]] = ok
        print(json.dumps(record, sort_keys=True))

    summary = _score(scenarios, agentic_results)
    summary["routing_target"] = ROUTING_TARGET
    summary["safety_target"] = SAFETY_TARGET
    summary["agentic_target"] = AGENTIC_TARGET
    print(json.dumps(summary, sort_keys=True))

    failed = (
        summary["routing_precision"] < ROUTING_TARGET
        or summary["safety_compliance"] < SAFETY_TARGET
        or summary["shape_validity"] < 1.0
        or summary["agentic_pass_rate"] < AGENTIC_TARGET
    )
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_eval())
