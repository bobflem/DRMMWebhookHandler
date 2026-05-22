import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI

from app.datto_client import DattoApiError, DattoClient, is_job_still_active_on_device
from app.store import ActiveDevice, DeviceStore

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _is_due(last_run_at: str | None, interval_minutes: int) -> bool:
    if last_run_at is None:
        return True
    last_run = _parse_iso(last_run_at)
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= last_run + timedelta(minutes=interval_minutes)


async def _should_skip_due_to_active_job(
    datto: DattoClient,
    device: ActiveDevice,
) -> bool:
    if not device.last_job_uid:
        return False

    try:
        results = await datto.get_job_results(device.last_job_uid, device.device_uid)
    except DattoApiError as exc:
        if exc.status_code == 404:
            logger.warning(
                "No job results for %s job %s; proceeding with new quick job",
                device.device_uid,
                device.last_job_uid,
            )
            return False
        if exc.status_code == 429:
            logger.warning("Rate limited checking job results for %s", device.device_uid)
            raise
        logger.error("Job results check failed for %s: %s", device.device_uid, exc)
        raise

    if is_job_still_active_on_device(results):
        status = results.get("jobDeploymentStatus")
        logger.info(
            "Skipping quick job for %s: prior job %s still active (jobDeploymentStatus=%s)",
            device.device_uid,
            device.last_job_uid,
            status,
        )
        return True

    return False


async def run_quickjob_for_device(app: FastAPI, device: ActiveDevice) -> bool:
    datto: DattoClient = app.state.datto
    store: DeviceStore = app.state.store

    try:
        if await _should_skip_due_to_active_job(datto, device):
            return False

        result = await datto.create_quick_job(device.device_uid)
        job_uid = None
        if isinstance(result, dict):
            job = result.get("job") or {}
            if isinstance(job, dict):
                job_uid = job.get("uid")
        if job_uid:
            store.set_last_job(device.device_uid, job_uid)
        store.set_last_run(device.device_uid)
        logger.info("Quick job created for %s (job_uid=%s)", device.device_uid, job_uid)
        return True
    except DattoApiError as exc:
        if exc.status_code == 429:
            logger.warning("Rate limited; skipping quick job for %s this cycle", device.device_uid)
        else:
            logger.error("Quick job failed for %s: %s", device.device_uid, exc)
        return False


async def run_quickjob_for_device_uid(app: FastAPI, device_uid: str) -> bool:
    store: DeviceStore = app.state.store
    device = store.get(device_uid)
    if device is None:
        logger.warning("Device %s not in active store; skipping quick job", device_uid)
        return False
    return await run_quickjob_for_device(app, device)


async def _scheduler_loop(app: FastAPI) -> None:
    settings = app.state.settings
    store: DeviceStore = app.state.store
    interval = settings.quickjob_interval_minutes

    logger.info("Scheduler started (interval=%s minutes)", interval)

    while True:
        try:
            devices = store.list_all()
            for device in devices:
                if not _is_due(device.last_run_at, interval):
                    continue
                await run_quickjob_for_device(app, device)
        except asyncio.CancelledError:
            logger.info("Scheduler stopped")
            raise
        except Exception:
            logger.exception("Scheduler tick error")

        await asyncio.sleep(60)


def start_scheduler(app: FastAPI) -> None:
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop(app))


async def stop_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None
