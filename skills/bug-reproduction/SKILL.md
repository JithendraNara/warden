---
name: bug-reproduction
description: Reproduce reported bugs with minimal steps and collect supporting evidence.
---

# bug-reproduction

Use this skill when the investigator-agent is asked to reproduce a failure.

## Operating procedure

1. Read the issue and any linked context.
2. Draft a minimal reproduction plan (commands, inputs, environment).
3. Execute the plan step-by-step with Bash only when approved by the operator.
4. Capture exit codes, stack traces, and relevant logs verbatim.
5. Record at least one hypothesis with evidence before concluding.

## Quality checks

- Plans must be deterministic and idempotent.
- Never delete files or mutate databases without approval.
- If reproduction fails, record what was tried and why it failed.

## Output format

```json
{
  "reproduced": true,
  "steps": ["…"],
  "evidence": ["…"],
  "hypotheses": [{"statement": "…", "support": "…"}]
}
```
