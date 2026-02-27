import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "media_path": "/media",
    "threads": 2,
    "generate_poster": True,
    "generate_fanart": True,
    "generate_nfo": False,
    "poster_percent": 10,
    "fanart_percent": 50,
    "cron": "0 2 * * *",
    "overwrite": False,
}


class AppDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    success_count INTEGER NOT NULL,
                    failed_count INTEGER NOT NULL,
                    skipped_count INTEGER NOT NULL,
                    total_files INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL,
                    details_json TEXT NOT NULL
                )
                """
            )

            row = conn.execute("SELECT COUNT(*) AS c FROM config").fetchone()
            if row and row["c"] == 0:
                for key, value in DEFAULT_CONFIG.items():
                    conn.execute(
                        "INSERT INTO config(key, value) VALUES (?, ?)",
                        (key, json.dumps(value, ensure_ascii=False)),
                    )

    def get_config(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
        config: dict[str, Any] = {}
        for row in rows:
            config[row["key"]] = json.loads(row["value"])

        merged = DEFAULT_CONFIG.copy()
        merged.update(config)
        return merged

    def save_config(self, data: dict[str, Any]) -> dict[str, Any]:
        merged = self.get_config()
        merged.update(data)
        with self._connect() as conn:
            for key, value in merged.items():
                conn.execute(
                    "INSERT OR REPLACE INTO config(key, value) VALUES (?, ?)",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
        return merged

    def save_task_stats(self, stats: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_stats (
                    started_at, ended_at, status, mode,
                    success_count, failed_count, skipped_count,
                    total_files, duration_seconds, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stats["started_at"],
                    stats["ended_at"],
                    stats["status"],
                    stats.get("mode", "full"),
                    stats.get("success_count", 0),
                    stats.get("failed_count", 0),
                    stats.get("skipped_count", 0),
                    stats.get("total_files", 0),
                    stats.get("duration_seconds", 0.0),
                    json.dumps(stats, ensure_ascii=False),
                ),
            )

    def get_latest_stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT details_json FROM task_stats ORDER BY id DESC LIMIT 1"
            ).fetchone()

        if not row:
            now = datetime.now().isoformat()
            return {
                "started_at": now,
                "ended_at": now,
                "status": "idle",
                "mode": "full",
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "total_files": 0,
                "duration_seconds": 0.0,
            }

        return json.loads(row["details_json"])
