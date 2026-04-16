---
name: release-notes
description: Compose polished release notes from a commit range.
---

# release-notes

Use this skill when the scribe-agent drafts release notes.

## Operating procedure

1. Read the provided commit summaries as the only source of truth.
2. Cluster commits into Highlights, Breaking Changes, Fixes, Internal.
3. Use short, maintainer-voice prose with bullet points.
4. Never invent changes that are not in the commit list.
5. Do not commit or push; only return Markdown text.

## Quality checks

- Sections must appear in the required order even if empty.
- Breaking changes must be called out explicitly.
- Prefer action verbs at the start of each bullet.

## Output format

Markdown with the headings `Highlights`, `Breaking Changes`, `Fixes`,
`Internal` — each followed by a bulleted list (or `_None._` if empty).
