import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.config import Settings
from app.datto_client import DattoApiError, DattoClient
from app.scheduler import run_quickjob_for_device_uid
from app.store import DeviceStore

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_secret(
    settings: Settings,
    secret_query: str | None,
    secret_header: str | None,
) -> None:
    provided = secret_query or secret_header
    if not provided or provided != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


async def _resolve_device_uid(payload: dict[str, Any], datto: DattoClient) -> str:
    device_uid = payload.get("device_uid") or payload.get("deviceUid")
    if device_uid:
        return str(device_uid)

    device_id = payload.get("device_id") or payload.get("deviceId")
    if device_id is None:
        raise HTTPException(status_code=400, detail="device_uid or device_id required")

    try:
        device = await datto.get_device_by_id(device_id)
    except DattoApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    uid = device.get("uid")
    if not uid:
        raise HTTPException(status_code=502, detail="Device response missing uid")
    return str(uid)


@router.post("/webhook/datto")
async def datto_webhook(
    request: Request,
    secret: str | None = Query(default=None),
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    store: DeviceStore = request.app.state.store
    datto: DattoClient = request.app.state.datto

    _validate_secret(settings, secret, x_webhook_secret)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    event = payload.get("event")
    if event not in ("detected", "cleared"):
        raise HTTPException(status_code=400, detail="event must be 'detected' or 'cleared'")

    device_uid = await _resolve_device_uid(payload, datto)
    hostname = payload.get("hostname") or payload.get("device_hostname")

    if event == "detected":
        store.upsert_detected(device_uid, hostname)
        logger.info("Software detected on %s (%s)", device_uid, hostname or "unknown")
        if settings.run_on_detect:
            await run_quickjob_for_device_uid(request.app, device_uid)
        return {"status": "ok", "action": "tracking"}

    removed = store.remove(device_uid)
    logger.info("Software cleared on %s (removed=%s)", device_uid, removed)
    return {"status": "ok", "action": "stopped"}
