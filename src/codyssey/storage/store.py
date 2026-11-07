"""SQLite persistence for tasks, runs, attempts, test results, and progress events."""

import json
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from codyssey.config import CodysseyConfig
from codyssey.contracts import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    Attempt,
    Contract,
    EventKind,
    ProgressEvent,
    RepairUsage,
    Run,
    RunStatus,
    StoredEvent,
    Task,
    TestResult,
)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    status TEXT NOT NULL
        CHECK (status IN ('queued','running','verified','failed','error','cancelled')),
    status_reason TEXT,
    config_json TEXT NOT NULL,
    estimated_cost_usd REAL,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS runs_by_created ON runs(created_at);
CREATE TABLE IF NOT EXISTS attempts (
    run_id TEXT NOT NULL REFERENCES runs(id),
    number INTEGER NOT NULL CHECK (number >= 1),
    method TEXT CHECK (method IN ('deterministic','llm')),
    status TEXT NOT NULL
        CHECK (status IN ('patch_invalid','tests_failed','tests_passed','timeout','error')),
    patch_path TEXT,
    error_summary TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, number)
);
CREATE TABLE IF NOT EXISTS test_results (
    run_id TEXT NOT NULL REFERENCES runs(id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 0), -- 0 is the baseline
    node_id TEXT NOT NULL,
    grp TEXT NOT NULL CHECK (grp IN ('fail_to_pass','pass_to_pass')),
    outcome TEXT NOT NULL CHECK (outcome IN ('passed','failed','error','skipped')),
    duration_seconds REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS test_results_by_attempt ON test_results(run_id, attempt_number);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL REFERENCES runs(id),
    sequence INTEGER NOT NULL,
    kind TEXT NOT NULL,
    attempt INTEGER,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
);
"""


class StorageError(Exception):
    """Base class for persistence problems."""


class TaskNotFound(StorageError):
    pass


class TaskConflict(StorageError):
    """A task id was reused with different content."""


class RunNotFound(StorageError):
    pass


class InvalidTransition(StorageError):
    pass


class StoredAttempt(Contract):
    attempt: Attempt
    usage: RepairUsage = RepairUsage()


def new_run_id(now: datetime | None = None) -> str:
    """Sortable, globally unique id, safe to merge across machines."""
    moment = now or datetime.now(UTC)
    return f"r{moment:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class RunStore:
    def __init__(self, database_path: Path, clock: Callable[[], datetime] | None = None):
        self.database_path = database_path
        self._clock = clock or (lambda: datetime.now(UTC))
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._tx() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise StorageError(f"Database schema {version} is newer than {SCHEMA_VERSION}")
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # -- connection handling -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """One write transaction; BEGIN IMMEDIATE serializes writers across processes."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def _now(self) -> str:
        return self._clock().isoformat()

    # -- tasks ---------------------------------------------------------------

    def add_task(self, task: Task) -> None:
        payload = task.model_dump_json()
        with self._tx() as conn:
            row = conn.execute("SELECT payload_json FROM tasks WHERE id = ?", (task.id,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO tasks (id, payload_json, created_at) VALUES (?, ?, ?)",
                    (task.id, payload, self._now()),
                )
            elif row["payload_json"] != payload:
                raise TaskConflict(f"Task {task.id!r} already exists with different content")

    def get_task(self, task_id: str) -> Task:
        with self._read() as conn:
            row = conn.execute("SELECT payload_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskNotFound(task_id)
        return Task.model_validate_json(row["payload_json"])

    # -- runs ----------------------------------------------------------------

    def create_run(self, task_id: str, config: CodysseyConfig, run_id: str | None = None) -> Run:
        run_id = run_id or new_run_id(self._clock())
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
                raise TaskNotFound(task_id)
            try:
                conn.execute(
                    "INSERT INTO runs (id, task_id, status, config_json, created_at)"
                    " VALUES (?, ?, 'queued', ?, ?)",
                    (run_id, task_id, config.model_dump_json(), self._now()),
                )
            except sqlite3.IntegrityError as exc:
                raise StorageError(f"Run {run_id!r} already exists") from exc
            self._insert_event(conn, run_id, ProgressEvent(kind=EventKind.RUN_QUEUED))
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> Run:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        return self._run_from_row(row)

    def list_runs(self, limit: int = 50) -> list[Run]:
        """Newest first."""
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def get_run_config(self, run_id: str) -> CodysseyConfig:
        with self._read() as conn:
            row = conn.execute("SELECT config_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        return CodysseyConfig.model_validate_json(row["config_json"])

    def transition(self, run_id: str, new_status: RunStatus, reason: str | None = None) -> Run:
        with self._tx() as conn:
            self._transition(conn, run_id, new_status, reason)
        return self.get_run(run_id)

    def _transition(
        self, conn: sqlite3.Connection, run_id: str, new_status: RunStatus, reason: str | None
    ) -> None:
        row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        current = RunStatus(row["status"])
        if new_status not in ALLOWED_TRANSITIONS[current]:
            raise InvalidTransition(f"Cannot move run {run_id!r} from {current} to {new_status}")
        now = self._now()
        conn.execute(
            "UPDATE runs SET status = ?, status_reason = ?,"
            " started_at = CASE WHEN ? = 'running' THEN ? ELSE started_at END,"
            " finished_at = CASE WHEN ? IN ('verified','failed','error','cancelled')"
            " THEN ? ELSE finished_at END WHERE id = ?",
            (new_status.value, reason, new_status.value, now, new_status.value, now, run_id),
        )

    def set_estimated_cost(self, run_id: str, cost_usd: float | None) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE runs SET estimated_cost_usd = ? WHERE id = ?", (cost_usd, run_id))

    def get_estimated_cost(self, run_id: str) -> float | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT estimated_cost_usd FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        return row["estimated_cost_usd"]

    def request_cancel(self, run_id: str) -> Run:
        """Persist a cancellation request.

        A queued run is cancelled immediately. A running run keeps going until its
        controller observes the request and finishes the transition. Terminal runs
        are returned unchanged.
        """
        with self._tx() as conn:
            row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise RunNotFound(run_id)
            status = RunStatus(row["status"])
            if status in TERMINAL_STATUSES:
                return self._get_run_in(conn, run_id)
            conn.execute("UPDATE runs SET cancel_requested = 1 WHERE id = ?", (run_id,))
            self._insert_event(conn, run_id, ProgressEvent(kind=EventKind.CANCEL_REQUESTED))
            if status == RunStatus.QUEUED:
                reason = "cancelled before start"
                self._transition(conn, run_id, RunStatus.CANCELLED, reason)
                finished = ProgressEvent(
                    kind=EventKind.RUN_FINISHED,
                    message=reason,
                    data={"status": RunStatus.CANCELLED.value},
                )
                self._insert_event(conn, run_id, finished)
            return self._get_run_in(conn, run_id)

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._read() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        return bool(row["cancel_requested"])

    def mark_interrupted_runs(self) -> list[str]:
        """After a restart, end `running` runs as `error` instead of leaving them running."""
        reason = "interrupted: controller stopped before the run finished"
        with self._tx() as conn:
            ids = [r["id"] for r in conn.execute("SELECT id FROM runs WHERE status = 'running'")]
            for run_id in ids:
                self._transition(conn, run_id, RunStatus.ERROR, reason)
                event = ProgressEvent(
                    kind=EventKind.RUN_FINISHED,
                    message=reason,
                    data={"status": RunStatus.ERROR.value},
                )
                self._insert_event(conn, run_id, event)
        return ids

    def _get_run_in(self, conn: sqlite3.Connection, run_id: str) -> Run:
        return self._run_from_row(
            conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> Run:
        return Run(
            id=row["id"],
            task_id=row["task_id"],
            status=RunStatus(row["status"]),
            status_reason=row["status_reason"],
            created_at=_parse(row["created_at"]),
            started_at=_parse(row["started_at"]),
            finished_at=_parse(row["finished_at"]),
        )

    # -- attempts and test evidence ------------------------------------------

    def add_attempt(self, attempt: Attempt, usage: RepairUsage | None = None) -> None:
        usage = usage or RepairUsage()
        try:
            with self._tx() as conn:
                conn.execute(
                    "INSERT INTO attempts (run_id, number, method, status, patch_path,"
                    " error_summary, input_tokens, output_tokens, latency_ms, requests,"
                    " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        attempt.run_id,
                        attempt.number,
                        attempt.method,
                        attempt.status,
                        attempt.patch_path,
                        attempt.error_summary,
                        usage.input_tokens,
                        usage.output_tokens,
                        usage.latency_ms,
                        usage.requests,
                        self._now(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise StorageError(
                f"Cannot record attempt {attempt.number} for run {attempt.run_id!r}: {exc}"
            ) from exc

    def list_attempts(self, run_id: str) -> list[StoredAttempt]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM attempts WHERE run_id = ? ORDER BY number", (run_id,)
            ).fetchall()
        return [
            StoredAttempt(
                attempt=Attempt(
                    run_id=row["run_id"],
                    number=row["number"],
                    method=row["method"],
                    status=row["status"],
                    patch_path=row["patch_path"],
                    error_summary=row["error_summary"],
                ),
                usage=RepairUsage(
                    input_tokens=row["input_tokens"],
                    output_tokens=row["output_tokens"],
                    latency_ms=row["latency_ms"],
                    requests=row["requests"],
                ),
            )
            for row in rows
        ]

    def add_test_results(self, run_id: str, attempt_number: int, results: list[TestResult]) -> None:
        """Record test outcomes; attempt number 0 is the baseline."""
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO test_results (run_id, attempt_number, node_id, grp, outcome,"
                " duration_seconds) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (run_id, attempt_number, r.node_id, r.group, r.outcome, r.duration_seconds)
                    for r in results
                ],
            )

    def list_test_results(self, run_id: str, attempt_number: int) -> list[TestResult]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM test_results WHERE run_id = ? AND attempt_number = ? ORDER BY rowid",
                (run_id, attempt_number),
            ).fetchall()
        return [
            TestResult(
                node_id=r["node_id"],
                group=r["grp"],
                outcome=r["outcome"],
                duration_seconds=r["duration_seconds"],
            )
            for r in rows
        ]

    def total_usage(self, run_id: str) -> RepairUsage:
        with self._read() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(input_tokens), 0) AS i, COALESCE(SUM(output_tokens), 0) AS o,"
                " COALESCE(SUM(latency_ms), 0) AS l, COALESCE(SUM(requests), 0) AS r"
                " FROM attempts WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return RepairUsage(
            input_tokens=row["i"], output_tokens=row["o"], latency_ms=row["l"], requests=row["r"]
        )

    # -- events --------------------------------------------------------------

    def append_event(self, run_id: str, event: ProgressEvent) -> StoredEvent:
        with self._tx() as conn:
            return self._insert_event(conn, run_id, event)

    def _insert_event(
        self, conn: sqlite3.Connection, run_id: str, event: ProgressEvent
    ) -> StoredEvent:
        last = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM events WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        created_at = self._now()
        try:
            conn.execute(
                "INSERT INTO events (run_id, sequence, kind, attempt, message, data_json,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    last + 1,
                    event.kind.value,
                    event.attempt,
                    event.message,
                    json.dumps(event.data, sort_keys=True),
                    created_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise RunNotFound(run_id) from exc
        return StoredEvent(
            run_id=run_id,
            sequence=last + 1,
            created_at=datetime.fromisoformat(created_at),
            event=event,
        )

    def list_events(self, run_id: str, after: int = 0) -> list[StoredEvent]:
        """Events with sequence greater than `after`, oldest first."""
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE run_id = ? AND sequence > ? ORDER BY sequence",
                (run_id, after),
            ).fetchall()
        return [
            StoredEvent(
                run_id=row["run_id"],
                sequence=row["sequence"],
                created_at=datetime.fromisoformat(row["created_at"]),
                event=ProgressEvent(
                    kind=EventKind(row["kind"]),
                    attempt=row["attempt"],
                    message=row["message"],
                    data=json.loads(row["data_json"]),
                ),
            )
            for row in rows
        ]
