# warden

Autonomous open-source maintainer agent platform powered by **Claude Agent SDK** and **MiniMax M2.7** via the Anthropic-compatible endpoint.

warden helps repository maintainers operate at scale with a team of specialist agents that triage issues, investigate bugs, draft fixes, review patches, and compose release notes — with human approval gates on every write action.

## Why warden

Large open-source portfolios suffer from backlog sprawl, inconsistent responses, and lost context across repositories. warden turns that noise into a structured workflow:

- Unified triage across multiple repositories
- Consistent, high-quality drafts for responses, summaries, and release notes
- HITL approval gates for any destructive or public-facing action
- Full audit trail and observability for every agent step
- Reusable `SKILL.md` expertise and scenario-based evaluation

## Architecture at a glance

warden is organized as a small control plane over a team of specialist subagents:

- `triage-agent` — classify and prioritize issues
- `investigator-agent` — reproduce bugs and gather context
- `coder-agent` — propose patches with rationale
- `reviewer-agent` — assess proposed changes
- `scribe-agent` — draft responses, release notes, and summaries

The control plane wires them through the Claude Agent SDK runtime, providing hooks, sessions, skills, and MCP server integration on top of MiniMax M2.7.

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

## Model configuration

warden uses MiniMax M2.7 through the Anthropic-compatible endpoint. All runtime components read these environment variables:

```bash
export ANTHROPIC_BASE_URL="https://api.minimax.io/anthropic"
export ANTHROPIC_AUTH_TOKEN="<YOUR_MINIMAX_API_KEY>"
export ANTHROPIC_MODEL="MiniMax-M2.7"
```

No Anthropic API key is required. MiniMax's Anthropic-compatible surface is the officially documented integration path for Claude Agent SDK and related tools.

## Install

```bash
uv pip install -e ".[dev]"
```

or with plain pip:

```bash
python -m pip install -e ".[dev]"
```

## Quick start

```bash
warden health
warden triage --repo JithendraNara/example --issue 42
warden eval
```

See [RUNBOOK.md](RUNBOOK.md) for operational guidance and [DEMO.md](DEMO.md) for a scripted walkthrough.

## Repository layout

```text
.
├── ARCHITECTURE.md
├── EVALS.md
├── RUNBOOK.md
├── DEMO.md
├── pyproject.toml
├── src/warden/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── runtime/
│   │   ├── client.py
│   │   ├── orchestrator.py
│   │   ├── subagents.py
│   │   ├── hooks.py
│   │   ├── permissions.py
│   │   └── session_store.py
│   ├── workflows/
│   │   ├── triage.py
│   │   ├── investigation.py
│   │   ├── coding.py
│   │   ├── review.py
│   │   └── release.py
│   ├── adapters/
│   │   └── github.py
│   └── telemetry/
│       ├── logging.py
│       └── tracing.py
├── skills/
│   ├── issue-triage/SKILL.md
│   ├── bug-reproduction/SKILL.md
│   ├── code-fix-proposal/SKILL.md
│   ├── pr-review/SKILL.md
│   └── release-notes/SKILL.md
├── evals/
│   ├── scenarios.json
│   └── run_eval.py
├── tests/
└── .github/workflows/ci.yml
```

## Safety model

Every write action — GitHub API mutation, file modification, shell command, push — passes through the approval hook chain. warden refuses to execute uncontrolled commands, never writes outside configured repositories, and logs every decision for audit.

## License

MIT.

## Status

This is an active flagship build. The roadmap tracks phase-level progress in [EVALS.md](EVALS.md) and the architecture.
