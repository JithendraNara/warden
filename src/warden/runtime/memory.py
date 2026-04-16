"""Memory subsystem for warden agents.

warden uses a three-tier memory model matching the production
patterns observed in real agent deployments:

- **Working memory**: the currently active task context. Purely in
  process, bounded in size, cleared at end-of-workflow.
- **Episodic memory**: a durable JSON log of past agent steps stored
  alongside the session audit trail. Used for "what did we try?" style
  lookups and for post-hoc analysis.
- **Semantic memory**: durable summaries of past workflows indexed by
  (repo, workflow_kind, subject) so future runs can recall prior
  decisions without replaying the whole trajectory.

The memory layer intentionally stays simple: SQLite + JSON. It is
meant to be replaceable by embeddings / vector stores later without
rewriting callers.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    step_name TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_episodic_session
    ON episodic(session_id);

CREATE TABLE IF NOT EXISTS semantic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    workflow TEXT NOT NULL,
    subject TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_semantic_lookup
    ON semantic(repo, workflow, subject);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class WorkingMemory:
    """Bounded in-memory store for the current agent turn.

    The agent loop writes "observations" (tool outputs, plan revisions,
    reflections) here. When the total payload exceeds ``max_chars`` we
    drop oldest tool results first and keep plan and reflection notes.
    """

    max_chars: int = 6000
    items: list[dict[str, Any]] = field(default_factory=list)

    def add(self, kind: str, data: dict[str, Any]) -> None:
        self.items.append({"kind": kind, "data": data, "ts": _utcnow().isoformat()})
        self._compact()

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self.items)

    def render(self) -> str:
        lines: list[str] = []
        for item in self.items:
            kind = item["kind"]
            ts = item["ts"]
            data_blob = json.dumps(item["data"], sort_keys=True, default=str)
            lines.append(f"[{ts}] {kind}: {data_blob}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #

    def _size(self) -> int:
        return sum(len(json.dumps(item, default=str)) for item in self.items)

    def _compact(self) -> None:
        while self._size() > self.max_chars:
            for idx, item in enumerate(self.items):
                if item["kind"] == "tool_result":
                    del self.items[idx]
                    break
            else:
                # No tool result left to drop — stop compacting.
                return


@dataclass(slots=True)
class SemanticRecord:
    repo: str
    workflow: str
    subject: str
    summary: str
    tags: tuple[str, ...]


class MemoryStore:
    """SQLite-backed episodic and semantic memory."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Episodic                                                           #
    # ------------------------------------------------------------------ #

    def record_step(self, session_id: str, step_name: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO episodic (session_id, created_at, step_name, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    _utcnow().isoformat(),
                    step_name,
                    json.dumps(payload, default=str, sort_keys=True),
                ),
            )

    def session_steps(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT step_name, payload_json, created_at
                FROM episodic WHERE session_id = ? ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            {
                "step_name": row[0],
                "payload": json.loads(row[1]),
                "created_at": row[2],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    # Semantic                                                           #
    # ------------------------------------------------------------------ #

    def remember(self, record: SemanticRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic (repo, workflow, subject, summary, tags_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.repo,
                    record.workflow,
                    record.subject,
                    record.summary,
                    json.dumps(list(record.tags), sort_keys=True),
                    _utcnow().isoformat(),
                ),
            )

    def recall(
        self,
        *,
        repo: str,
        workflow: str,
        subject: str,
        limit: int = 3,
    ) -> list[SemanticRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT repo, workflow, subject, summary, tags_json
                FROM semantic
                WHERE repo = ? AND workflow = ? AND subject LIKE ?
                ORDER BY id DESC LIMIT ?
                """,
                (repo, workflow, f"%{subject}%", limit),
            ).fetchall()
        return [
            SemanticRecord(
                repo=row[0],
                workflow=row[1],
                subject=row[2],
                summary=row[3],
                tags=tuple(json.loads(row[4])),
            )
            for row in rows
        ]
