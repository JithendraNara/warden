"""Safe shell adapter for controlled command execution.

This adapter is intentionally narrow:

- Commands are executed as an **argv list**, never via a shell string.
- Each command is matched against an **allowlist** of argv prefixes. No
  match → no execution.
- A hard **timeout** is enforced.
- Output is captured and size-capped so a runaway process cannot bloat
  the agent context.
- The current working directory must be a real path that the caller
  explicitly passes; no implicit inheritance.

The agent loop pairs this adapter with the permission hook. A
non-allowlisted command returns a structured refusal without calling
``subprocess``.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_BYTES = 16 * 1024

# Default allowlist: the smallest set needed for warden investigation.
# Operators can extend this list explicitly; we never widen it at runtime.
DEFAULT_ALLOWLIST: tuple[tuple[str, ...], ...] = (
    ("python", "-V"),
    ("python", "--version"),
    ("python", "-m", "pytest"),
    ("pytest",),
    ("git", "status"),
    ("git", "log"),
    ("git", "diff"),
    ("git", "apply", "--check"),
    ("ls",),
    ("cat",),
    ("head",),
    ("tail",),
    ("grep",),
    ("rg",),
    ("node", "--version"),
    ("npm", "--version"),
)


class CommandRefused(Exception):
    """Raised when a command does not match the allowlist."""


@dataclass(slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    truncated: bool
    duration_ms: int


@dataclass(slots=True)
class ShellPolicy:
    allowlist: tuple[tuple[str, ...], ...] = field(default_factory=lambda: DEFAULT_ALLOWLIST)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    def allows(self, argv: Sequence[str]) -> bool:
        for prefix in self.allowlist:
            if _matches_prefix(argv, prefix):
                return True
        return False


def _matches_prefix(argv: Sequence[str], prefix: Sequence[str]) -> bool:
    if len(argv) < len(prefix):
        return False
    return tuple(argv[: len(prefix)]) == tuple(prefix)


class ShellAdapter:
    """Controlled command executor with allowlist enforcement."""

    def __init__(self, policy: ShellPolicy | None = None) -> None:
        self._policy = policy or ShellPolicy()

    @property
    def policy(self) -> ShellPolicy:
        return self._policy

    def run(self, argv: Sequence[str], *, cwd: Path) -> CommandResult:
        argv = tuple(argv)
        if not argv:
            raise ValueError("argv must be non-empty")
        if not self._policy.allows(argv):
            raise CommandRefused(
                f"Command refused by policy: {shlex.join(argv)}"
            )

        import time

        start = time.monotonic()
        completed = subprocess.run(  # noqa: S603 - argv form, no shell
            argv,
            cwd=str(cwd),
            capture_output=True,
            timeout=self._policy.timeout_seconds,
            check=False,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        stdout, truncated_out = _clip(completed.stdout, self._policy.max_output_bytes)
        stderr, truncated_err = _clip(completed.stderr, self._policy.max_output_bytes)
        return CommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated_out or truncated_err,
            duration_ms=duration_ms,
        )


def _clip(data: bytes | None, limit: int) -> tuple[str, bool]:
    if not data:
        return "", False
    truncated = len(data) > limit
    if truncated:
        data = data[:limit]
    return data.decode("utf-8", errors="replace"), truncated
