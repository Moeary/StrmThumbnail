from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class Profile:
    id: int | None
    name: str
    directory: str
    threads: int = 4
    cron: str = "0 2 * * *"
    enabled: bool = True
    scheduled: bool = True
    generate_nfo: bool = False
    overwrite_existing: bool = False
    generate_poster: bool = True
    generate_fanart: bool = False
    poster_pct: float = 0.1
    fanart_pct: float = 0.5
    include_local_media: bool = False


class Storage:
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
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    directory TEXT NOT NULL,
                    threads INTEGER NOT NULL DEFAULT 4,
                    cron TEXT NOT NULL DEFAULT '0 2 * * *',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    scheduled INTEGER NOT NULL DEFAULT 1,
                    generate_nfo INTEGER NOT NULL DEFAULT 0,
                    overwrite_existing INTEGER NOT NULL DEFAULT 0,
                    generate_poster INTEGER NOT NULL DEFAULT 1,
                    generate_fanart INTEGER NOT NULL DEFAULT 0,
                    poster_pct REAL NOT NULL DEFAULT 0.1,
                    fanart_pct REAL NOT NULL DEFAULT 0.5,
                    include_local_media INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._migrate_profiles_schema(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER,
                    mode TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    output_bytes INTEGER NOT NULL DEFAULT 0,
                    download_bytes INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    strm_path TEXT NOT NULL,
                    poster_exists INTEGER NOT NULL DEFAULT 0,
                    fanart_exists INTEGER NOT NULL DEFAULT 0,
                    nfo_exists INTEGER NOT NULL DEFAULT 0,
                    last_status TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    UNIQUE(profile_id, strm_path),
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                )
                """
            )

    def _migrate_profiles_schema(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(profiles)").fetchall()
        columns = {row[1] for row in rows}

        def add_column(sql: str) -> None:
            conn.execute(sql)

        if "directory" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN directory TEXT")
        if "threads" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN threads INTEGER NOT NULL DEFAULT 4")
        if "scheduled" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN scheduled INTEGER NOT NULL DEFAULT 1")
        if "generate_nfo" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN generate_nfo INTEGER NOT NULL DEFAULT 0")
        if "overwrite_existing" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN overwrite_existing INTEGER NOT NULL DEFAULT 0")
        if "generate_poster" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN generate_poster INTEGER NOT NULL DEFAULT 1")
        if "generate_fanart" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN generate_fanart INTEGER NOT NULL DEFAULT 0")
        if "poster_pct" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN poster_pct REAL NOT NULL DEFAULT 0.1")
        if "fanart_pct" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN fanart_pct REAL NOT NULL DEFAULT 0.5")
        if "include_local_media" not in columns:
            add_column("ALTER TABLE profiles ADD COLUMN include_local_media INTEGER NOT NULL DEFAULT 0")

        has_relative_path = "relative_path" in columns
        has_schedule_enabled = "schedule_enabled" in columns
        has_settings_json = "settings_json" in columns

        if has_relative_path:
            conn.execute(
                """
                UPDATE profiles
                SET directory = COALESCE(NULLIF(directory, ''), relative_path)
                WHERE directory IS NULL OR directory = ''
                """
            )
        if has_schedule_enabled:
            conn.execute(
                """
                UPDATE profiles
                SET scheduled = COALESCE(scheduled, schedule_enabled)
                """
            )

        if has_settings_json:
            profile_rows = conn.execute(
                "SELECT id, settings_json FROM profiles"
            ).fetchall()
            for row in profile_rows:
                settings_raw = row["settings_json"] if isinstance(row, sqlite3.Row) else row[1]
                settings: dict = {}
                if settings_raw:
                    try:
                        settings = json.loads(settings_raw)
                    except (TypeError, json.JSONDecodeError):
                        settings = {}

                conn.execute(
                    """
                    UPDATE profiles
                    SET
                        threads = COALESCE(threads, ?),
                        generate_nfo = COALESCE(generate_nfo, ?),
                        overwrite_existing = COALESCE(overwrite_existing, ?),
                        generate_poster = COALESCE(generate_poster, ?),
                        generate_fanart = COALESCE(generate_fanart, ?),
                        poster_pct = COALESCE(poster_pct, ?),
                        fanart_pct = COALESCE(fanart_pct, ?)
                    WHERE id = ?
                    """,
                    (
                        int(settings.get("threads", settings.get("thread_count", 4))),
                        int(bool(settings.get("generate_nfo", False))),
                        int(bool(settings.get("overwrite_existing", settings.get("overwrite", False)))),
                        int(bool(settings.get("generate_poster", True))),
                        int(bool(settings.get("generate_fanart", False))),
                        float(settings.get("poster_pct", settings.get("poster_percent", 0.1))),
                        float(settings.get("fanart_pct", settings.get("fanart_percent", 0.5))),
                        int(row["id"] if isinstance(row, sqlite3.Row) else row[0]),
                    ),
                )

    def _profile_columns(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA table_info(profiles)").fetchall()
        return {row[1] for row in rows}

    def _legacy_settings_json(self, profile: Profile) -> str:
        payload = {
            "threads": profile.threads,
            "generate_nfo": profile.generate_nfo,
            "overwrite_existing": profile.overwrite_existing,
            "generate_poster": profile.generate_poster,
            "generate_fanart": profile.generate_fanart,
            "poster_pct": profile.poster_pct,
            "fanart_pct": profile.fanart_pct,
            "include_local_media": profile.include_local_media,
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _row_value(row: sqlite3.Row, key: str, default=None):
        keys = row.keys()
        return row[key] if key in keys else default

    def _row_to_profile(self, row: sqlite3.Row) -> Profile:
        settings_raw = self._row_value(row, "settings_json", "")
        settings: dict = {}
        if settings_raw:
            try:
                settings = json.loads(settings_raw)
            except (TypeError, json.JSONDecodeError):
                settings = {}

        directory = self._row_value(row, "directory", "") or self._row_value(row, "relative_path", "")
        threads = self._row_value(row, "threads", None)
        if threads is None:
            threads = int(settings.get("threads", settings.get("thread_count", 4)))

        scheduled = self._row_value(row, "scheduled", None)
        if scheduled is None:
            scheduled = self._row_value(row, "schedule_enabled", 1)

        return Profile(
            id=row["id"],
            name=row["name"],
            directory=directory,
            threads=int(threads),
            cron=self._row_value(row, "cron", "0 2 * * *") or "0 2 * * *",
            enabled=bool(self._row_value(row, "enabled", 1)),
            scheduled=bool(scheduled),
            generate_nfo=bool(self._row_value(row, "generate_nfo", settings.get("generate_nfo", False))),
            overwrite_existing=bool(
                self._row_value(
                    row,
                    "overwrite_existing",
                    settings.get("overwrite_existing", settings.get("overwrite", False)),
                )
            ),
            generate_poster=bool(self._row_value(row, "generate_poster", settings.get("generate_poster", True))),
            generate_fanart=bool(self._row_value(row, "generate_fanart", settings.get("generate_fanart", False))),
            poster_pct=float(self._row_value(row, "poster_pct", settings.get("poster_pct", 0.1))),
            fanart_pct=float(self._row_value(row, "fanart_pct", settings.get("fanart_pct", 0.5))),
            include_local_media=bool(
                self._row_value(row, "include_local_media", settings.get("include_local_media", False))
            ),
        )

    def list_profiles(self, keyword: str = "") -> list[Profile]:
        with self._connect() as conn:
            if keyword:
                rows = conn.execute(
                    "SELECT * FROM profiles WHERE name LIKE ? OR directory LIKE ? ORDER BY id DESC",
                    (f"%{keyword}%", f"%{keyword}%"),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM profiles ORDER BY id DESC").fetchall()
        return [self._row_to_profile(r) for r in rows]

    def get_profile(self, profile_id: int) -> Profile | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return self._row_to_profile(row) if row else None

    def create_profile(self, profile: Profile) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            columns = self._profile_columns(conn)
            values: dict[str, object] = {
                "name": profile.name,
                "directory": profile.directory,
                "threads": profile.threads,
                "cron": profile.cron,
                "enabled": int(profile.enabled),
                "scheduled": int(profile.scheduled),
                "generate_nfo": int(profile.generate_nfo),
                "overwrite_existing": int(profile.overwrite_existing),
                "generate_poster": int(profile.generate_poster),
                "generate_fanart": int(profile.generate_fanart),
                "poster_pct": profile.poster_pct,
                "fanart_pct": profile.fanart_pct,
                "include_local_media": int(profile.include_local_media),
                "created_at": now,
                "updated_at": now,
            }

            if "relative_path" in columns:
                values["relative_path"] = profile.directory
            if "schedule_enabled" in columns:
                values["schedule_enabled"] = int(profile.scheduled)
            if "settings_json" in columns:
                values["settings_json"] = self._legacy_settings_json(profile)

            filtered = {key: val for key, val in values.items() if key in columns}
            columns_sql = ", ".join(filtered.keys())
            placeholders = ", ".join(["?"] * len(filtered))
            cur = conn.execute(
                f"INSERT INTO profiles ({columns_sql}) VALUES ({placeholders})",
                tuple(filtered.values()),
            )
            return int(cur.lastrowid)

    def update_profile(self, profile: Profile) -> None:
        if profile.id is None:
            raise ValueError("profile id is required")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            columns = self._profile_columns(conn)
            values: dict[str, object] = {
                "name": profile.name,
                "directory": profile.directory,
                "threads": profile.threads,
                "cron": profile.cron,
                "enabled": int(profile.enabled),
                "scheduled": int(profile.scheduled),
                "generate_nfo": int(profile.generate_nfo),
                "overwrite_existing": int(profile.overwrite_existing),
                "generate_poster": int(profile.generate_poster),
                "generate_fanart": int(profile.generate_fanart),
                "poster_pct": profile.poster_pct,
                "fanart_pct": profile.fanart_pct,
                "include_local_media": int(profile.include_local_media),
                "updated_at": now,
            }

            if "relative_path" in columns:
                values["relative_path"] = profile.directory
            if "schedule_enabled" in columns:
                values["schedule_enabled"] = int(profile.scheduled)
            if "settings_json" in columns:
                values["settings_json"] = self._legacy_settings_json(profile)

            filtered = {key: val for key, val in values.items() if key in columns}
            assignments = ", ".join(f"{key} = ?" for key in filtered)
            conn.execute(
                f"UPDATE profiles SET {assignments} WHERE id = ?",
                (*tuple(filtered.values()), profile.id),
            )

    def delete_profile(self, profile_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM file_state WHERE profile_id = ?", (profile_id,))
            conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))

    def upsert_file_state(
        self,
        *,
        profile_id: int | None,
        strm_path: str,
        poster_exists: bool,
        fanart_exists: bool,
        nfo_exists: bool,
        last_status: str,
        last_error: str = "",
    ) -> None:
        if profile_id is None:
            return
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO file_state (
                    profile_id, strm_path, poster_exists, fanart_exists, nfo_exists,
                    last_status, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id, strm_path) DO UPDATE SET
                    poster_exists = excluded.poster_exists,
                    fanart_exists = excluded.fanart_exists,
                    nfo_exists = excluded.nfo_exists,
                    last_status = excluded.last_status,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    profile_id,
                    strm_path,
                    int(poster_exists),
                    int(fanart_exists),
                    int(nfo_exists),
                    last_status,
                    last_error,
                    now,
                ),
            )

    def log_run_start(self, profile_id: int | None, mode: str) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO run_log (profile_id, mode, started_at) VALUES (?, ?, ?)",
                (profile_id, mode, now),
            )
            return int(cur.lastrowid)

    def log_run_finish(
        self,
        run_id: int,
        *,
        success_count: int,
        fail_count: int,
        skipped_count: int,
        output_bytes: int,
        download_bytes: int,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE run_log SET
                    finished_at = ?,
                    success_count = ?,
                    fail_count = ?,
                    skipped_count = ?,
                    output_bytes = ?,
                    download_bytes = ?
                WHERE id = ?
                """,
                (now, success_count, fail_count, skipped_count, output_bytes, download_bytes, run_id),
            )
