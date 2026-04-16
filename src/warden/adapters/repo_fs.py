"""Sandboxed filesystem adapter for local repository operations.

warden never touches arbitrary paths. Every read and write goes
through :class:`RepoFilesystem`, which resolves the requested path to
an absolute path *within* a pre-configured root, rejects escapes, and
enforces size limits. Write operations are always permission-gated by
the hook layer before this adapter is called.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


DEFAULT_MAX_FILE_BYTES = 256 * 1024  # 256 KiB keeps an iteration cheap
DEFAULT_MAX_SEARCH_MATCHES = 50


class SandboxEscape(Exception):
    """Raised when a requested path escapes the configured root."""


@dataclass(slots=True)
class FileContent:
    path: str
    size_bytes: int
    text: str
    truncated: bool


@dataclass(slots=True)
class SearchMatch:
    path: str
    line_number: int
    line: str


class RepoFilesystem:
    """Narrow, sandboxed filesystem interface."""

    def __init__(self, root: Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None:
        if not root.is_absolute():
            root = root.resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Repo root {root} does not exist or is not a directory")
        self._root = root
        self._max_file_bytes = max_file_bytes

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, relative: str) -> Path:
        candidate = (self._root / relative).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise SandboxEscape(f"Path {relative!r} escapes the sandbox") from exc
        return candidate

    def read_file(self, relative: str) -> FileContent:
        path = self._resolve(relative)
        if not path.is_file():
            raise FileNotFoundError(f"{relative} is not a regular file inside the sandbox")
        size = path.stat().st_size
        data = path.read_bytes()
        truncated = size > self._max_file_bytes
        if truncated:
            data = data[: self._max_file_bytes]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
        return FileContent(path=relative, size_bytes=size, text=text, truncated=truncated)

    def list_dir(self, relative: str = ".") -> list[str]:
        path = self._resolve(relative)
        if not path.is_dir():
            raise NotADirectoryError(f"{relative} is not a directory inside the sandbox")
        entries: list[str] = []
        for child in sorted(path.iterdir()):
            suffix = "/" if child.is_dir() else ""
            entries.append(f"{child.relative_to(self._root)}{suffix}")
        return entries

    def search_text(
        self,
        query: str,
        *,
        pattern: str = "**/*",
        max_matches: int = DEFAULT_MAX_SEARCH_MATCHES,
    ) -> list[SearchMatch]:
        if not query:
            return []
        matches: list[SearchMatch] = []
        lowered = query.lower()
        for path in self._root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self._root).as_posix()
            if pattern != "**/*" and not fnmatch(rel, pattern):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if lowered in line.lower():
                    matches.append(SearchMatch(path=rel, line_number=lineno, line=line.rstrip()))
                    if len(matches) >= max_matches:
                        return matches
        return matches

    def write_file(self, relative: str, content: str) -> FileContent:
        path = self._resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return FileContent(
            path=relative,
            size_bytes=len(content.encode("utf-8")),
            text=content,
            truncated=False,
        )
