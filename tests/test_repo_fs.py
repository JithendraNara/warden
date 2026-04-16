from pathlib import Path

import pytest

from warden.adapters.repo_fs import RepoFilesystem, SandboxEscape


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    (tmp_path / "README.md").write_text("warden demo repo\n")
    return tmp_path


def test_list_dir_and_read_file(tmp_path: Path) -> None:
    fs = RepoFilesystem(_make_repo(tmp_path))
    entries = fs.list_dir(".")
    assert "README.md" in entries
    assert "src/" in entries

    content = fs.read_file("src/main.py")
    assert "def main()" in content.text
    assert content.truncated is False


def test_search_text_finds_match(tmp_path: Path) -> None:
    fs = RepoFilesystem(_make_repo(tmp_path))
    matches = fs.search_text("hello")
    assert any(m.path == "src/main.py" for m in matches)


def test_sandbox_escape_is_rejected(tmp_path: Path) -> None:
    fs = RepoFilesystem(_make_repo(tmp_path))
    with pytest.raises(SandboxEscape):
        fs.read_file("../outside.txt")
