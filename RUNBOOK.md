# Runbook

## Environment

warden always reads these environment variables before any workflow:

```bash
export ANTHROPIC_BASE_URL="https://api.minimax.io/anthropic"
export ANTHROPIC_AUTH_TOKEN="<MINIMAX_API_KEY>"
export ANTHROPIC_MODEL="MiniMax-M2.7"
```

Optional:

```bash
export WARDEN_GITHUB_TOKEN="<GITHUB_PAT>"
export WARDEN_APPROVAL_MODE="manual"   # auto | manual
export WARDEN_DATA_DIR="$HOME/.warden"
```

## Install

Python 3.11+ required.

```bash
uv pip install -e ".[dev]"
```

## Health check

```bash
warden health
```

Verifies environment, model reachability, SQLite store, and hook registration.

## Approval modes

- `auto`: only `safe` actions run automatically; `review` actions block.
- `manual`: every tool use is gated — operator approves from CLI.

## Common workflows

```bash
# Triage an issue
warden triage --repo JithendraNara/example --issue 42

# Investigate a failing bug report
warden investigate --repo JithendraNara/example --issue 42

# Review an open PR
warden review --repo JithendraNara/example --pr 17

# Compose release notes from commit range
warden release --repo JithendraNara/example --from v0.2.0 --to HEAD
```

## Session management

Every run returns a session ID. Resume with:

```bash
warden resume <session_id>
```

Sessions persist audit logs and outputs to SQLite in `$WARDEN_DATA_DIR`.

## Failure handling

- Model timeouts retry with exponential backoff.
- Hook exceptions bubble up and abort the workflow.
- Every abort persists a structured error record.

## Running the eval suite

```bash
warden eval
```

Fails if scenario-level precision or safety compliance drops below targets defined in `EVALS.md`.
