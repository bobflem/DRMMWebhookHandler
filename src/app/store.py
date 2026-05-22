import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_DEVICE_COLUMNS = "device_uid, hostname, started_at, last_run_at, last_job_uid"


@dataclass
class ActiveDevice:
    device_uid: str
    hostname: str | None
    started_at: str
    last_run_at: str | None
    last_job_uid: str | None = None


class DeviceStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_device(self, row: sqlite3.Row) -> ActiveDevice:
        return ActiveDevice(
            row["device_uid"],
            row["hostname"],
            row["started_at"],
            row["last_run_at"],
            row["last_job_uid"],
        )

    def migrate(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_devices (
                    device_uid TEXT PRIMARY KEY,
                    hostname TEXT,
                    started_at TEXT NOT NULL,
                    last_run_at TEXT,
                    last_job_uid TEXT
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(active_devices)").fetchall()}
            if "last_job_uid" not in columns:
                conn.execute("ALTER TABLE active_devices ADD COLUMN last_job_uid TEXT")
            conn.commit()

    def get(self, device_uid: str) -> ActiveDevice | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_DEVICE_COLUMNS} FROM active_devices WHERE device_uid = ?",
                (device_uid,),
            ).fetchone()
        return self._row_to_device(row) if row else None

    def upsert_detected(self, device_uid: str, hostname: str | None) -> ActiveDevice:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_DEVICE_COLUMNS} FROM active_devices WHERE device_uid = ?",
                (device_uid,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO active_devices (device_uid, hostname, started_at, last_run_at, last_job_uid)
                    VALUES (?, ?, ?, NULL, NULL)
                    """,
                    (device_uid, hostname, now),
                )
                device = ActiveDevice(device_uid, hostname, now, None, None)
            else:
                conn.execute(
                    "UPDATE active_devices SET hostname = COALESCE(?, hostname) WHERE device_uid = ?",
                    (hostname, device_uid),
                )
                device = self._row_to_device(row)
                if hostname:
                    device = ActiveDevice(
                        device.device_uid,
                        hostname,
                        device.started_at,
                        device.last_run_at,
                        device.last_job_uid,
                    )
            conn.commit()
        return device

    def remove(self, device_uid: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM active_devices WHERE device_uid = ?", (device_uid,))
            conn.commit()
            return cur.rowcount > 0

    def list_all(self) -> list[ActiveDevice]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_DEVICE_COLUMNS} FROM active_devices ORDER BY device_uid"
            ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def set_last_run(self, device_uid: str, last_run_at: str | None = None) -> None:
        ts = last_run_at or _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE active_devices SET last_run_at = ? WHERE device_uid = ?",
                (ts, device_uid),
            )
            conn.commit()

    def set_last_job(self, device_uid: str, job_uid: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE active_devices SET last_job_uid = ? WHERE device_uid = ?",
                (job_uid, device_uid),
            )
            conn.commit()

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM active_devices").fetchone()
        return int(row["c"])
