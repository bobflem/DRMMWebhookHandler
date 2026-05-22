import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.config import Settings, get_settings
from app.datto_client import DattoApiError, DattoClient
from app.profiles import load_profile_registry
from app.scheduler import start_scheduler, stop_scheduler
from app.store import DeviceStore
from app.webhook import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    profiles = load_profile_registry(settings)
    store = DeviceStore(settings.db_path)
    store.migrate()
    datto = DattoClient(settings)

    app.state.settings = settings
    app.state.profiles = profiles
    app.state.store = store
    app.state.datto = datto

    active = store.count()
    logger.info(
        "Started with %s profile(s), %s scheduled device(s), db=%s",
        len(profiles.profiles),
        active,
        settings.db_path,
    )

    start_scheduler(app)
    yield
    await stop_scheduler()


app = FastAPI(title="Datto RMM Webhook Quickjob Service", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request):
    from fastapi.responses import JSONResponse

    store: DeviceStore = request.app.state.store
    datto: DattoClient = request.app.state.datto

    try:
        store.migrate()
        await datto.ensure_token()
    except DattoApiError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": str(exc)},
        )

    return {"status": "ready", "active_devices": store.count()}
