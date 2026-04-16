"""Environment-driven configuration for warden.

Centralizes access to the MiniMax Anthropic-compatible endpoint, session
persistence paths, and safety defaults. Keeping this in one module makes
the rest of the codebase free of scattered environment lookups.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ApprovalMode = Literal["auto", "manual"]

DEFAULT_BASE_URL = "https://api.minimax.io/anthropic"
DEFAULT_MODEL = "MiniMax-M2.7"


@dataclass(frozen=True, slots=True)
class WardenConfig:
    """Resolved runtime configuration.

    Fields come from environment variables with documented defaults. We use
    a frozen dataclass so that configuration cannot silently mutate during a
    workflow run.
    """

    anthropic_base_url: str
    anthropic_auth_token: str | None
    model: str
    github_token: str | None
    approval_mode: ApprovalMode
    data_dir: Path

    @property
    def has_model_credentials(self) -> bool:
        return bool(self.anthropic_auth_token)


def _resolve_data_dir(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".warden"


def _resolve_approval_mode(raw: str | None) -> ApprovalMode:
    if raw is None:
        return "manual"
    candidate = raw.strip().lower()
    if candidate in {"auto", "manual"}:
        return candidate  # type: ignore[return-value]
    raise ValueError(
        f"Invalid WARDEN_APPROVAL_MODE value: {raw!r} (expected 'auto' or 'manual')"
    )


def load_config() -> WardenConfig:
    """Build a :class:`WardenConfig` from the current environment."""

    data_dir = _resolve_data_dir(os.environ.get("WARDEN_DATA_DIR"))
    data_dir.mkdir(parents=True, exist_ok=True)

    return WardenConfig(
        anthropic_base_url=os.environ.get("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL),
        anthropic_auth_token=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
        model=os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        github_token=os.environ.get("WARDEN_GITHUB_TOKEN"),
        approval_mode=_resolve_approval_mode(os.environ.get("WARDEN_APPROVAL_MODE")),
        data_dir=data_dir,
    )
