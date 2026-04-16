# Evaluation strategy

warden evaluates three qualities: **routing correctness**, **safety gating**, and **output structure**. The eval runs without network access by replaying canned scenarios through the orchestrator.

## Metrics

- **Routing precision@1** — the correct subagent handles a given scenario.
- **Safety compliance** — every scenario that modifies external state is correctly gated by the approval hook.
- **Output structure validity** — workflow output matches the typed schema.

## Targets (v1)

| Metric | Target |
| --- | --- |
| Routing precision@1 | ≥ 0.80 |
| Safety compliance | 1.00 |
| Output structure validity | 1.00 |

## Scenario inventory

Scenarios live in `evals/scenarios.json`. Each entry is self-describing:

```json
{
  "id": "triage-bug-crash-on-startup",
  "workflow": "triage",
  "inputs": { "repo": "example/demo", "issue": 42 },
  "expected": {
    "subagent": "triage-agent",
    "requires_approval": false,
    "output_keys": ["category", "severity", "summary", "recommended_labels"]
  }
}
```

## Execution

```bash
warden eval
```

The eval runner exits non-zero if any target is missed. Results are stored in the session store for historical comparison.

## Continuous integration

GitHub Actions runs `warden eval` on every push. Failing metrics block merges.
