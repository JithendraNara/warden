---
name: code-fix-proposal
description: Draft minimal patches for reproduced issues with rationale and safety notes.
---

# code-fix-proposal

Use this skill when the coder-agent proposes a fix.

## Operating procedure

1. Read the issue and reproduction record.
2. Inspect only the files relevant to the failure.
3. Draft the smallest patch that solves the issue.
4. Note what tests exist, what tests should be added, and any safety risks.
5. Never write files to disk until the reviewer approves the plan.

## Quality checks

- Prefer targeted edits over rewrites.
- Flag any change that touches public APIs or data migration paths.
- Explain every non-obvious line.

## Output format

```json
{
  "affected_files": ["src/…/file.py"],
  "diff": "…",
  "rationale": "…",
  "tests_to_add": ["…"],
  "safety_notes": ["…"]
}
```
