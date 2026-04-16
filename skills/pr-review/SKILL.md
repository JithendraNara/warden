---
name: pr-review
description: Review proposed patches for correctness, safety, tests, and style.
---

# pr-review

Use this skill when the reviewer-agent evaluates a coder-agent proposal.

## Operating procedure

1. Read the proposed diff and associated rationale.
2. Check correctness against the reproduction record.
3. Verify test coverage for the change.
4. Flag anything that violates the warden safety model.
5. Choose a verdict: `accept`, `revise`, `reject`.

## Quality checks

- Line-anchored feedback only (reference file + line number).
- Prefer actionable suggestions over abstract complaints.
- Do not approve changes without reviewing tests.

## Output format

```json
{
  "verdict": "revise",
  "feedback": [
    {"file": "src/…/file.py", "line": 42, "comment": "…"}
  ],
  "blocking_issues": ["…"]
}
```
