import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScheduledDevice:
    device_uid: str
    hostname: str | None
    primary_profile_id: str
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

    def _row_to_scheduled(self, row: sqlite3.Row) -> ScheduledDevice:
        return ScheduledDevice(
            device_uid=row["device_uid"],
            hostname=row["hostname"],
            primary_profile_id=row["primary_profile_id"],
            started_at=row["started_at"],
            last_run_at=row["last_run_at"],
            last_job_uid=row["last_job_uid"],
        )

    def migrate(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS device_detections (
                    device_uid TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    hostname TEXT,
                    detected_at TEXT NOT NULL,
                    PRIMARY KEY (device_uid, profile_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS device_schedule (
                    device_uid TEXT PRIMARY KEY,
                    hostname TEXT,
                    primary_profile_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    last_run_at TEXT,
                    last_job_uid TEXT
                )
                """
            )
            conn.commit()

    def record_detect(
        self,
        device_uid: str,
        profile_id: str,
        hostname: str | None,
    ) -> ScheduledDevice:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO device_detections (device_uid, profile_id, hostname, detected_at)
                VALUES (?, ?, ?, ?)
                """,
                (device_uid, profile_id, hostname, now),
            )
            conn.execute(
                """
                UPDATE device_detections SET hostname = COALESCE(?, hostname)
                WHERE device_uid = ? AND profile_id = ?
                """,
                (hostname, device_uid, profile_id),
            )

            schedule = conn.execute(
                "SELECT device_uid, hostname, primary_profile_id, started_at, last_run_at, last_job_uid "
                "FROM device_schedule WHERE device_uid = ?",
                (device_uid,),
            ).fetchone()

            if schedule is None:
                conn.execute(
                    """
                    INSERT INTO device_schedule (
                        device_uid, hostname, primary_profile_id, started_at, last_run_at, last_job_uid
                    ) VALUES (?, ?, ?, ?, NULL, NULL)
                    """,
                    (device_uid, hostname, profile_id, now),
                )
                device = ScheduledDevice(device_uid, hostname, profile_id, now, None, None)
            else:
                conn.execute(
                    "UPDATE device_schedule SET hostname = COALESCE(?, hostname) WHERE device_uid = ?",
                    (hostname, device_uid),
                )
                device = self._row_to_scheduled(schedule)
                if hostname:
                    device = ScheduledDevice(
                        device.device_uid,
                        hostname,
                        device.primary_profile_id,
                        device.started_at,
                        device.last_run_at,
                        device.last_job_uid,
                    )
            conn.commit()
        return device

    def record_clear(self, device_uid: str, profile_id: str) -> bool:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM device_detections WHERE device_uid = ? AND profile_id = ?",
                (device_uid, profile_id),
            )
            remaining = conn.execute(
                "SELECT COUNT(*) AS c FROM device_detections WHERE device_uid = ?",
                (device_uid,),
            ).fetchone()
            stopped = False
            if remaining and int(remaining["c"]) == 0:
                conn.execute("DELETE FROM device_schedule WHERE device_uid = ?", (device_uid,))
                stopped = True
            conn.commit()
        return stopped

    def get(self, device_uid: str) -> ScheduledDevice | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT device_uid, hostname, primary_profile_id, started_at, last_run_at, last_job_uid "
                "FROM device_schedule WHERE device_uid = ?",
                (device_uid,),
            ).fetchone()
        return self._row_to_scheduled(row) if row else None

    def list_scheduled(self) -> list[ScheduledDevice]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT device_uid, hostname, primary_profile_id, started_at, last_run_at, last_job_uid "
                "FROM device_schedule ORDER BY device_uid"
            ).fetchall()
        return [self._row_to_scheduled(r) for r in rows]

    def set_last_run(self, device_uid: str, last_run_at: str | None = None) -> None:
        ts = last_run_at or _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE device_schedule SET last_run_at = ? WHERE device_uid = ?",
                (ts, device_uid),
            )
            conn.commit()

    def set_last_job(self, device_uid: str, job_uid: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE device_schedule SET last_job_uid = ? WHERE device_uid = ?",
                (job_uid, device_uid),
            )
            conn.commit()

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM device_schedule").fetchone()
        return int(row["c"])

    def detection_count(self, device_uid: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM device_detections WHERE device_uid = ?",
                (device_uid,),
            ).fetchone()
        return int(row["c"])
