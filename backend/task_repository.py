import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Dict, Iterable


class TaskRepository:
    """Small SQLite-backed store for task state that must survive process restarts."""

    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(str(self.database_path), timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        created_ts REAL NOT NULL,
                        updated_ts REAL NOT NULL,
                        task_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_created_ts ON tasks(created_ts DESC)"
                )
        if os.name != "nt":
            try:
                self.database_path.chmod(0o600)
            except OSError:
                pass

    @staticmethod
    def _serializable_task(task: dict):
        return {
            key: value
            for key, value in task.items()
            if key not in {"thread", "api_key"}
        }

    def save(self, task: dict):
        task_id = str(task.get("id") or "")
        if not task_id:
            raise ValueError("task id is required")

        created_ts = float(task.get("created_ts") or time.time())
        payload = json.dumps(
            self._serializable_task(task),
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        with self._lock:
            with closing(self._connect()) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO tasks(id, created_ts, updated_ts, task_json)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            created_ts = excluded.created_ts,
                            updated_ts = excluded.updated_ts,
                            task_json = excluded.task_json
                        """,
                        (task_id, created_ts, time.time(), payload),
                    )

    def load_all(self) -> Dict[str, dict]:
        with self._lock:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT id, task_json FROM tasks ORDER BY created_ts DESC"
                ).fetchall()

        tasks = {}
        for task_id, task_json in rows:
            try:
                task = json.loads(task_json)
            except (TypeError, ValueError):
                continue
            if not isinstance(task, dict):
                continue
            task["id"] = str(task.get("id") or task_id)
            task.pop("thread", None)
            tasks[task["id"]] = task
        return tasks

    def delete(self, task_ids: Iterable[str]):
        task_ids = [str(task_id) for task_id in task_ids if task_id]
        if not task_ids:
            return
        placeholders = ", ".join("?" for _ in task_ids)
        with self._lock:
            with closing(self._connect()) as connection:
                with connection:
                    connection.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", task_ids)
