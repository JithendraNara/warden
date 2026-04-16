---
name: issue-triage
description: Classify GitHub issues into category, severity, priority and recommend labels.
---

# issue-triage

Apply this skill when the triage-agent reads an issue. Always return structured output. Never modify repository state.

## Operating procedure

1. Read the issue title and body in full.
2. Extract any reproduction steps, environment details, and affected versions.
3. Classify the issue:
   - category: bug | feature | question | docs | regression | security
   - severity: low | medium | high | critical
   - priority: p0 | p1 | p2 | p3
4. Write a short neutral summary (max 50 words).
5. Suggest labels using the repository's existing convention if known.
6. Propose a next action: `needs_reproduction`, `needs_design`, `ready`, `duplicate`, `close`.

## Quality checks

- Summary must cite specific phrases from the body.
- Severity must match observable impact, not author tone.
- Refuse to classify without a body; ask for more information instead.

## Output format

```json
{
  "category": "bug",
  "severity": "high",
  "priority": "p1",
  "summary": "…",
  "recommended_labels": ["bug", "area/runtime"],
  "suggested_next_action": "needs_reproduction"
}
```
