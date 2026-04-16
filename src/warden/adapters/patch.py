"""Unified-diff parsing and validation.

Patches are small, structured artifacts. warden parses them instead
of passing freeform text through to write operations. The validator
catches the most common model-generated mistakes (wrong headers, files
outside the repo, hunks with implausible sizes) before any attempt to
apply them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


_FILE_HEADER_RE = re.compile(r"^\+\+\+\s+b/(?P<path>\S+)")
_OLD_HEADER_RE = re.compile(r"^---\s+a/(?P<path>\S+)")
_HUNK_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")


@dataclass(slots=True)
class PatchHunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int


@dataclass(slots=True)
class PatchFile:
    old_path: str
    new_path: str
    hunks: list[PatchHunk] = field(default_factory=list)


@dataclass(slots=True)
class ParsedPatch:
    files: list[PatchFile] = field(default_factory=list)

    def total_hunks(self) -> int:
        return sum(len(file.hunks) for file in self.files)


@dataclass(slots=True)
class PatchValidation:
    ok: bool
    issues: list[str] = field(default_factory=list)


def parse_unified_diff(text: str) -> ParsedPatch:
    """Parse a unified diff into :class:`ParsedPatch`.

    The parser is tolerant: anything that does not look like a header or
    hunk is ignored. Malformed input produces an empty patch which the
    validator will reject.
    """

    patch = ParsedPatch()
    current: PatchFile | None = None
    pending_old: str | None = None
    for line in text.splitlines():
        old_match = _OLD_HEADER_RE.match(line)
        if old_match:
            pending_old = old_match.group("path")
            continue
        new_match = _FILE_HEADER_RE.match(line)
        if new_match:
            current = PatchFile(
                old_path=pending_old or "",
                new_path=new_match.group("path"),
            )
            patch.files.append(current)
            pending_old = None
            continue
        hunk_match = _HUNK_RE.match(line)
        if hunk_match and current is not None:
            current.hunks.append(
                PatchHunk(
                    old_start=int(hunk_match.group(1)),
                    old_len=int(hunk_match.group(2) or 1),
                    new_start=int(hunk_match.group(3)),
                    new_len=int(hunk_match.group(4) or 1),
                )
            )
    return patch


def validate_patch(
    patch: ParsedPatch,
    *,
    allowed_paths: Iterable[str] | None = None,
    max_hunks: int = 50,
) -> PatchValidation:
    """Run cheap sanity checks before touching the filesystem."""

    validation = PatchValidation(ok=True)
    if not patch.files:
        validation.ok = False
        validation.issues.append("patch is empty")
        return validation

    if patch.total_hunks() > max_hunks:
        validation.ok = False
        validation.issues.append(
            f"patch exceeds max_hunks={max_hunks} (has {patch.total_hunks()})"
        )

    allowed = set(allowed_paths) if allowed_paths is not None else None
    for file in patch.files:
        if not file.new_path:
            validation.ok = False
            validation.issues.append("patch file missing new_path header")
            continue
        if ".." in file.new_path.split("/"):
            validation.ok = False
            validation.issues.append(f"path escapes repo: {file.new_path!r}")
        if allowed is not None and file.new_path not in allowed:
            validation.ok = False
            validation.issues.append(f"path not in allowlist: {file.new_path!r}")
        if not file.hunks:
            validation.ok = False
            validation.issues.append(f"no hunks for file {file.new_path}")
    return validation
