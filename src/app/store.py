import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ActiveDevice:
    device_uid: str
    hostname: str | None
    started_at: str
    last_run_at: str | None


class DeviceStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def migrate(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_devices (
                    device_uid TEXT PRIMARY KEY,
                    hostname TEXT,
                    started_at TEXT NOT NULL,
                    last_run_at TEXT
                )
                """
            )
            conn.commit()

    def upsert_detected(self, device_uid: str, hostname: str | None) -> ActiveDevice:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT device_uid, hostname, started_at, last_run_at FROM active_devices WHERE device_uid = ?",
                (device_uid,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO active_devices (device_uid, hostname, started_at, last_run_at) VALUES (?, ?, ?, NULL)",
                    (device_uid, hostname, now),
                )
                started_at = now
                last_run_at = None
            else:
                conn.execute(
                    "UPDATE active_devices SET hostname = COALESCE(?, hostname) WHERE device_uid = ?",
                    (hostname, device_uid),
                )
                started_at = row["started_at"]
                last_run_at = row["last_run_at"]
            conn.commit()
        return ActiveDevice(device_uid, hostname, started_at, last_run_at)

    def remove(self, device_uid: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM active_devices WHERE device_uid = ?", (device_uid,))
            conn.commit()
            return cur.rowcount > 0

    def list_all(self) -> list[ActiveDevice]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT device_uid, hostname, started_at, last_run_at FROM active_devices ORDER BY device_uid"
            ).fetchall()
        return [
            ActiveDevice(r["device_uid"], r["hostname"], r["started_at"], r["last_run_at"]) for r in rows
        ]

    def set_last_run(self, device_uid: str, last_run_at: str | None = None) -> None:
        ts = last_run_at or _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE active_devices SET last_run_at = ? WHERE device_uid = ?",
                (ts, device_uid),
            )
            conn.commit()

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM active_devices").fetchone()
        return int(row["c"])
