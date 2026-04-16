from pathlib import Path

import pytest

from warden.adapters.shell import CommandRefused, ShellAdapter, ShellPolicy


def test_policy_refuses_non_allowlisted_command(tmp_path: Path) -> None:
    shell = ShellAdapter(ShellPolicy(allowlist=(("echo", "ok"),), timeout_seconds=5.0))
    with pytest.raises(CommandRefused):
        shell.run(["rm", "-rf", "/"], cwd=tmp_path)


def test_policy_runs_allowlisted_command(tmp_path: Path) -> None:
    shell = ShellAdapter(ShellPolicy(allowlist=(("echo",),), timeout_seconds=5.0))
    result = shell.run(["echo", "warden"], cwd=tmp_path)
    assert result.returncode == 0
    assert "warden" in result.stdout
