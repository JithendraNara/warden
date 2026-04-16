# warden — Case Study

An autonomous open-source maintainer agent platform built on the
**Claude Agent SDK** with **MiniMax M2.7** as the model brain, routed
through MiniMax's Anthropic-compatible endpoint. warden is not a
chatbot and not a thin SDK wrapper — it is a bounded, tool-using agent
system with four specialised workflows, three-tier memory, a verifier,
an MCP server, and an evaluation harness.

## Problem

Maintaining 100+ repositories is a systemic problem, not a prompt
problem. Maintainers lose context between repos, backlog triage drifts,
PR reviews get uneven, and release notes slip. The common failure mode
is not model quality — it is the absence of a reliable loop around the
model: memory, observation, verification, and safety.

## Solution

A production-shaped agent platform with:

- Four agentic workflows: **triage**, **investigation**, **coding**,
  **review** — each implemented as a bounded
  Plan → Act → Observe → Verify → Reflect loop.
- Real tool integrations: GitHub REST, sandboxed filesystem with path
  escape protection, shell with argv-only execution and allowlist,
  unified-diff parser and validator.
- Three-tier memory: working (in-process, compaction-aware), episodic
  (SQLite trajectory log), semantic (repo + workflow keyed summaries
  recalled across runs).
- A verifier that enforces schema, citation grounding, and severity
  justification before a result is accepted.
- Hook-based safety: `PreToolUse` approval gating, `PostToolUse` audit,
  session lifecycle markers, all persisted to SQLite.
- MCP server exposing warden workflows to any Claude Agent SDK
  client (Claude Desktop, Cursor, OpenCode, Windsurf).
- OpenTelemetry tracing with optional OTLP export to Langfuse for
  per-session cost and latency summaries.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ CLI / Python API / MCP clients                               │
├──────────────────────────────────────────────────────────────┤
│ Workflows                                                    │
│  triage · investigation · coding · review                    │
├──────────────────────────────────────────────────────────────┤
│ Agent loop                                                   │
│  plan → act → observe → verify → reflect                     │
│  budgeted iterations · working memory · trajectory log       │
├──────────────────────────────────────────────────────────────┤
│ Runtime                                                      │
│  thinkers · tools · memory · permissions · hooks · tracing   │
├──────────────────────────────────────────────────────────────┤
│ Adapters                                                     │
│  GitHub · repo filesystem · shell · unified-diff             │
├──────────────────────────────────────────────────────────────┤
│ Claude Agent SDK → MiniMax M2.7 (Anthropic-compatible)       │
└──────────────────────────────────────────────────────────────┘
```

## Agent loop in detail

Every workflow runs through `runtime/agent_loop.py`:

1. The thinker emits a strict JSON turn: either a tool call or a
   final result.
2. If the turn is a tool call, the registered callable executes it
   against a real adapter. The truncated observation is recorded in
   working memory so the next iteration can reason about it.
3. If the turn is a final result, the verifier runs three checks:
   schema coverage, citation grounding, and severity justification.
4. A failed verification does not silently become output — it
   becomes a reflection entry in memory and the loop continues until
   the budget is exhausted.
5. Successful runs are persisted to episodic and semantic memory so
   future workflows can recall previous decisions.

Two thinkers ship today:

- `RuleBasedTriageThinker` / `RuleBasedInvestigatorThinker` /
  `RuleBasedCoderThinker` / `RuleBasedReviewerThinker` — deterministic
  brains used for CI, tests, and reproducible demos.
- `ClaudeAgentThinker` — drives MiniMax M2.7 via the Claude Agent SDK
  with a strict JSON system prompt for each turn.

## Safety model

Every tool is classified by `runtime/permissions.py` into
`safe`, `review`, or `block`. The `PreToolUse` hook consults the
active `approval_mode`:

- `auto` — safe tools run, review tools require approval.
- `manual` — every tool use requires approval.

The shell adapter additionally requires every command to match an
argv-prefix allowlist. Unknown commands are refused before
`subprocess` is touched.

## Tool catalog

| Domain       | Tool                   | Risk    |
| ------------ | ---------------------- | ------- |
| GitHub       | `fetch_issue`          | safe    |
| GitHub       | `list_similar_issues`  | safe    |
| GitHub       | `get_repo_context`     | safe    |
| GitHub       | `fetch_pull_request`   | safe    |
| GitHub       | `fetch_pr_diff`        | safe    |
| Filesystem   | `read_file`            | safe    |
| Filesystem   | `list_dir`             | safe    |
| Filesystem   | `search_text`          | safe    |
| Filesystem   | `write_file` (adapter) | review  |
| Shell        | `run_shell`            | review  |
| Patch        | `validate_patch`       | safe    |

## Evaluation

Scenarios live in `evals/scenarios.json`. Every scenario is exercised
by the offline eval harness, which runs real agent loops against
in-memory adapters and asserts on tool calls, iterations, schema
coverage, and verification status.

Current eval summary:

```
routing_precision   : 1.00 (target 0.80)
safety_compliance   : 1.00 (target 1.00)
shape_validity      : 1.00 (target 1.00)
agentic_pass_rate   : 1.00 (target 1.00) across 4 agentic scenarios
total scenarios     : 7
```

## MCP integration

warden ships an MCP server (`src/warden/mcp_server.py`) with
four tools:

- `warden_triage(repo, issue)`
- `warden_investigate(repo_root, issue_title, issue_body)`
- `warden_code(repo_root, target_file, goal, evidence)`
- `warden_review(repo, pr)`

Any Claude Agent SDK host can mount the server via
`ClaudeAgentOptions(mcp_servers=...)` and delegate maintainer work to
warden through structured tool calls.

## Observability

`src/warden/telemetry/tracing.py` instruments the agent loop,
tool execution, verification, and thinker invocations with
OpenTelemetry spans. Setting `OTEL_EXPORTER_OTLP_ENDPOINT` (plus
`OTEL_EXPORTER_OTLP_HEADERS` for Langfuse) starts exporting traces
immediately. Without OTel installed, the system continues with
no-op spans.

## Repository metrics

At the Phase 4 checkpoint:

- 50+ passing tests across adapters, tools, memory, verifier, agent
  loop, each of the four agentic workflows, MCP server, and tracing.
- 7 scenarios in the eval harness including 4 real agent loop runs.
- Zero lint findings under `ruff check src tests evals`.
- CI runs lint, tests, and the eval harness on every push.

## Live MiniMax run

The `tests/test_live_minimax.py` test exercises the full loop against
MiniMax M2.7. It is skipped by default and enabled with:

```bash
export WARDEN_LIVE_TEST=1
export ANTHROPIC_AUTH_TOKEN="<MINIMAX_API_KEY>"
export ANTHROPIC_BASE_URL="https://api.minimax.io/anthropic"
export ANTHROPIC_MODEL="MiniMax-M2.7"
python -m pytest tests/test_live_minimax.py -q
```

## What this demonstrates

- Correct use of Claude Agent SDK primitives (subagents, hooks,
  skills, permissions, sessions, MCP).
- Correct integration with MiniMax's Anthropic-compatible endpoint —
  no Anthropic key required, no LiteLLM layer.
- A disciplined agent loop with verification, not a prompt loop.
- Real adapters with realistic safety constraints.
- Reproducible evaluation, not hand-waved quality claims.
- Production-style observability and MCP interop.

## Next directions

- Add a Langfuse dashboard export illustrating trajectory costs.
- Expand the subagent catalog with a release-notes scribe variant that
  ingests commit ranges directly.
- Publish the MCP server configuration for Claude Desktop and Cursor.
- Build a dedicated demo repository that exercises every workflow on
  a real maintained project.
