"""SQLite-backed session store for audit and resume semantics.

warden treats every workflow run as a durable session. This module
owns the schema and provides narrow, typed helpers used by the runtime
and telemetry layers.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    workflow TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_events_session
    ON audit_events(session_id);
"""


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: str
    workflow: str
    started_at: datetime
    ended_at: datetime | None
    status: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class AuditEvent:
    session_id: str
    created_at: datetime
    kind: str
    payload: dict[str, object]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(value: dict[str, object]) -> str:
    return json.dumps(value, default=str, sort_keys=True)


class SessionStore:
    """Thin wrapper over a SQLite database file."""

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

    def create_session(
        self,
        session_id: str,
        workflow: str,
        metadata: dict[str, object],
    ) -> SessionRecord:
        started = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, workflow, started_at, status, metadata_json)
                VALUES (?, ?, ?, 'running', ?)
                """,
                (session_id, workflow, started.isoformat(), _serialize(metadata)),
            )
        return SessionRecord(
            id=session_id,
            workflow=workflow,
            started_at=started,
            ended_at=None,
            status="running",
            metadata=metadata,
        )

    def complete_session(self, session_id: str, status: str) -> None:
        ended = _utcnow()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET ended_at = ?, status = ? WHERE id = ?",
                (ended.isoformat(), status, session_id),
            )

    def record_event(self, session_id: str, kind: str, payload: dict[str, object]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (session_id, created_at, kind, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, _utcnow().isoformat(), kind, _serialize(payload)),
            )

    def list_events(self, session_id: str) -> list[AuditEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, created_at, kind, payload_json
                FROM audit_events WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            AuditEvent(
                session_id=row[0],
                created_at=datetime.fromisoformat(row[1]),
                kind=row[2],
                payload=json.loads(row[3]),
            )
            for row in rows
        ]

    def tail_events(self, limit: int = 20) -> list[AuditEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, created_at, kind, payload_json
                FROM audit_events ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            AuditEvent(
                session_id=row[0],
                created_at=datetime.fromisoformat(row[1]),
                kind=row[2],
                payload=json.loads(row[3]),
            )
            for row in rows
        ][::-1]
