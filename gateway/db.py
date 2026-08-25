from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
from typing import Iterator
from uuid import uuid4

from gateway.models import TaskStatus


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class TaskRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    available_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    heartbeat_at TEXT,
                    worker_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_claim
                ON tasks(status, available_at, created_at);
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    conversation_url TEXT,
                    profile_name TEXT NOT NULL DEFAULT 'default',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def create_task(self, session_id: str, prompt: str, timeout_seconds: int) -> dict:
        now = utcnow()
        task_id = uuid4().hex
        with self._connection() as con:
            con.execute(
                """INSERT INTO tasks(task_id, session_id, prompt, timeout_seconds, available_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, session_id, prompt, timeout_seconds, now, now),
            )
        return self.get_task(task_id)  # type: ignore[return-value]

    def get_task(self, task_id: str) -> dict | None:
        with self._connection() as con:
            row = con.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self) -> list[dict]:
        """Return all tasks, newest first, for the built-in local test console."""
        with self._connection() as con:
            rows = con.execute("SELECT * FROM tasks ORDER BY created_at DESC, id DESC").fetchall()
        return [dict(row) for row in rows]

    def claim_next(self, worker_id: str) -> dict | None:
        now = utcnow()
        with self._connection() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                """SELECT * FROM tasks
                   WHERE status IN (?, ?) AND available_at <= ?
                   ORDER BY created_at LIMIT 1""",
                (TaskStatus.PENDING.value, TaskStatus.RETRY_WAIT.value, now),
            ).fetchone()
            if not row:
                con.execute("COMMIT")
                return None
            updated = con.execute(
                """UPDATE tasks SET status = ?, started_at = COALESCE(started_at, ?),
                   heartbeat_at = ?, worker_id = ?, attempt_count = attempt_count + 1
                   WHERE task_id = ? AND status IN (?, ?)""",
                (TaskStatus.RUNNING.value, now, now, worker_id, row["task_id"],
                 TaskStatus.PENDING.value, TaskStatus.RETRY_WAIT.value),
            )
            con.execute("COMMIT")
            if updated.rowcount != 1:
                return None
        return self.get_task(row["task_id"])

    def heartbeat(self, task_id: str, worker_id: str) -> None:
        with self._connection() as con:
            con.execute(
                "UPDATE tasks SET heartbeat_at = ? WHERE task_id = ? AND worker_id = ? AND status = ?",
                (utcnow(), task_id, worker_id, TaskStatus.RUNNING.value),
            )

    def complete(self, task_id: str, answer: str) -> None:
        now = utcnow()
        with self._connection() as con:
            con.execute(
                """UPDATE tasks SET status = ?, result = ?, completed_at = ?, heartbeat_at = ?
                   WHERE task_id = ? AND status = ?""",
                (TaskStatus.COMPLETED.value, answer, now, now, task_id, TaskStatus.RUNNING.value),
            )

    def fail(self, task_id: str, error_code: str, error_message: str, retry_after_seconds: int | None = None) -> None:
        now = datetime.now(UTC)
        with self._connection() as con:
            row = con.execute("SELECT attempt_count, max_attempts FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return
            retry = retry_after_seconds is not None and row["attempt_count"] < row["max_attempts"]
            status = TaskStatus.RETRY_WAIT.value if retry else TaskStatus.FAILED.value
            available_at = (now + timedelta(seconds=retry_after_seconds or 0)).isoformat()
            con.execute(
                """UPDATE tasks SET status = ?, error_code = ?, error_message = ?, available_at = ?,
                   completed_at = CASE WHEN ? THEN NULL ELSE ? END
                   WHERE task_id = ? AND status = ?""",
                (status, error_code, error_message, available_at, int(retry), now.isoformat(), task_id, TaskStatus.RUNNING.value),
            )

    def mark_auth_required(self, task_id: str, message: str) -> None:
        with self._connection() as con:
            con.execute(
                """UPDATE tasks SET status = ?, error_code = ?, error_message = ?, completed_at = ?
                   WHERE task_id = ? AND status = ?""",
                (TaskStatus.AUTH_REQUIRED.value, "AUTH_REQUIRED", message, utcnow(), task_id, TaskStatus.RUNNING.value),
            )

    def recover_stale(self, stale_after_seconds: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(seconds=stale_after_seconds)).isoformat()
        with self._connection() as con:
            result = con.execute(
                """UPDATE tasks SET status = ?, available_at = ?, error_code = ?,
                   error_message = ? WHERE status = ? AND heartbeat_at < ?""",
                (TaskStatus.RETRY_WAIT.value, utcnow(), "WORKER_RECOVERED", "Recovered after stale worker heartbeat.",
                 TaskStatus.RUNNING.value, cutoff),
            )
        return result.rowcount
