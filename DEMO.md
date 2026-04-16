# Demo

A scripted walkthrough of warden against a real repository.

## Prereqs

- Python 3.11+
- MiniMax M2.7 API key
- GitHub personal access token (optional for live fetches)

## Setup

```bash
export ANTHROPIC_BASE_URL="https://api.minimax.io/anthropic"
export ANTHROPIC_AUTH_TOKEN="<MINIMAX_API_KEY>"
export ANTHROPIC_MODEL="MiniMax-M2.7"
uv pip install -e ".[dev]"
warden health
```

## Walkthrough

### 1. Inspect environment

```bash
warden health
```

Confirms endpoint, model, data directory, and registered subagents.

### 2. Triage a known issue (offline scenario)

```bash
warden eval --only triage-bug-crash-on-startup
```

Shows router → `triage-agent`, structured output, and zero approval prompts for a read-only scenario.

### 3. Trigger an approval gate

```bash
warden eval --only coding-risky-patch
```

Shows an action classified as `review`, hook firing, and workflow pausing until approval. Approve with `--approve` or decline to abort.

### 4. Review the audit trail

```bash
warden audit --last 5
```

Displays the structured trail of hook decisions, tool calls, and state transitions.

## What to watch

- Subagent routing in real time.
- Pre-tool hook firing before any `Write`, `Edit`, `Bash`, or `WebFetch` call.
- Cost and latency summary for each session.
