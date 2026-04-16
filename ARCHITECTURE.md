# Architecture

warden is a thin, opinionated control plane wrapped around the Claude Agent SDK runtime. Its job is to compose specialist subagents into repeatable maintainer workflows while keeping every write action behind human approval.

## Design principles

- Every effectful action must pass an approval gate.
- Every agent step must be observable, typed, and replayable.
- Specialist agents must have narrow responsibilities and clean contexts.
- Skills and prompts live in version control, not in code.
- The model layer is replaceable; MiniMax M2.7 is the default.

## Layered model

```
┌─────────────────────────────────────────────┐
│ CLI / Python API / Scheduled workers        │
├─────────────────────────────────────────────┤
│ Workflows (triage / investigation / ...)    │
├─────────────────────────────────────────────┤
│ Orchestrator + Subagent registry            │
├─────────────────────────────────────────────┤
│ Claude Agent SDK runtime                    │
│  - tools, hooks, skills, sessions, MCP      │
├─────────────────────────────────────────────┤
│ Model provider (MiniMax M2.7 via Anthropic) │
└─────────────────────────────────────────────┘
```

## The agent loop

warden is not a thin SDK wrapper. Every workflow runs through a
bounded **Plan → Act → Observe → Verify → Reflect** loop implemented in
`runtime/agent_loop.py`:

1. A **thinker** produces the next step as a strict JSON object: either
   a `tool_call` or a `final_result`.
2. `ToolRegistry` executes the tool against a real adapter and feeds the
   observation back into working memory.
3. When a `final_result` arrives it is validated by
   `runtime/verifier.py` against a schema, a citation rule, and severity
   justification checks.
4. Failed verifications trigger a reflection pass; the loop retries
   until the iteration or tool-call budget is exhausted.
5. Successful outputs are persisted to episodic + semantic memory so
   future runs can recall prior decisions.

Two thinkers ship today:

- `RuleBasedTriageThinker` — deterministic brain used for tests, CI,
  and reproducible demos.
- `ClaudeAgentThinker` — wraps the Claude Agent SDK and drives
  MiniMax-M2.7 via the Anthropic-compatible endpoint for live runs.

## Runtime components

### `runtime/client.py`
Builds `ClaudeAgentOptions` with MiniMax environment, default safety hooks, the registered subagent map, and any MCP servers configured in the active profile.

### `runtime/orchestrator.py`
Single entry point that runs a workflow by name against a session, collecting structured events.

### `runtime/subagents.py`
Declarative definitions for the specialist agents. Each subagent has:
- `description` — used by the router agent
- `system prompt` — a compiled persona
- `allowed_tools` — the smallest safe set
- `skills` — skill folders relevant to its role

### `runtime/hooks.py`
Production hook chain:
- `PreToolUse` → approval gate (blocks risky tools until policy allows)
- `PostToolUse` → structured audit log
- `SessionStart` → load repository context
- `SessionEnd` → flush telemetry
- `UserPromptSubmit` → sanitize + record

### `runtime/permissions.py`
Risk classification for every tool call: `safe`, `review`, `block`. Writes to GitHub, shell side-effects, and file mutations default to `review` with a policy table override.

### `runtime/session_store.py`
Persists session IDs, metadata, and the audit log to SQLite. Enables `warden resume <session>` semantics across CLI runs.

## Workflows

Workflows are small orchestrations that bind subagents together for a maintainer use case:

- `triage` — classify issues/PRs and draft responses
- `investigation` — reproduce a bug and gather context
- `coding` — propose a patch against a failing scenario
- `review` — assess a PR and produce a structured review
- `release` — compose release notes and communication drafts

Workflows are pure Python functions that assemble a prompt, select subagents, and stream results through the orchestrator.

## Skills

Skills live under `skills/<name>/SKILL.md` and are loaded by the Claude Agent SDK runtime when `setting_sources=["project"]` is set. Each skill contains:
- domain expertise
- step-by-step operating procedure
- quality checks and output format

This design keeps the behavior of each subagent tunable without code changes.

## MCP integrations

warden composes at least two MCP servers in production:

- **GitHub MCP** — issues, PRs, discussions, releases
- **MiniMax Coding Plan MCP** — `web_search` and `understand_image`

Custom MCP servers can be added via `runtime/client.py`'s `mcp_servers` option.

## Telemetry

- Structured logs are written as JSON lines.
- OpenTelemetry tracing wraps the orchestrator and hook chain.
- Per-workflow cost + latency summaries are persisted to SQLite.

## Evaluation

Scenarios in `evals/scenarios.json` capture canonical maintainer situations. `evals/run_eval.py` replays them through workflows and asserts on routing, approval gating, and output structure. This runs in CI and as a local command.

## Extension points

- Add a subagent → register in `runtime/subagents.py`.
- Add a workflow → add a function under `workflows/` and expose via CLI.
- Add a skill → drop a folder under `skills/`.
- Add a tool → attach via MCP server or SDK option; declare risk in `permissions.py`.
- Add a provider → swap `ANTHROPIC_*` env and update `client.py` if needed.
