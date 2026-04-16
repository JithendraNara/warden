from pathlib import Path

import pytest

from warden.config import load_config


def test_load_config_uses_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in [
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_MODEL",
        "WARDEN_GITHUB_TOKEN",
        "WARDEN_APPROVAL_MODE",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WARDEN_DATA_DIR", str(tmp_path))

    config = load_config()
    assert config.anthropic_base_url == "https://api.minimax.io/anthropic"
    assert config.model == "MiniMax-M2.7"
    assert config.approval_mode == "manual"
    assert config.data_dir == tmp_path
    assert config.has_model_credentials is False


def test_load_config_with_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_MODEL", "MiniMax-M2.7")
    monkeypatch.setenv("WARDEN_APPROVAL_MODE", "auto")
    monkeypatch.setenv("WARDEN_DATA_DIR", str(tmp_path))

    config = load_config()
    assert config.anthropic_base_url == "https://proxy.example/anthropic"
    assert config.has_model_credentials is True
    assert config.approval_mode == "auto"


def test_invalid_approval_mode_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WARDEN_APPROVAL_MODE", "weird")
    monkeypatch.setenv("WARDEN_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        load_config()
