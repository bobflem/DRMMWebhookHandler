import base64
import logging
import time
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class DattoApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DattoClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.datto_api_base_url.rstrip("/")
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def _api_root(self) -> str:
        return f"{self._base}/api"

    @property
    def _token_url(self) -> str:
        return f"{self._base}/auth/oauth/token"

    async def ensure_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token
        await self._refresh_token()
        return self._access_token  # type: ignore[return-value]

    async def _refresh_token(self) -> None:
        # Datto RMM uses OAuth password grant with public-client credentials (see API v2 docs / Postman guide).
        basic = base64.b64encode(b"public-client:public").decode()
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "password",
            "username": self._settings.datto_api_key,
            "password": self._settings.datto_api_secret,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self._token_url, headers=headers, data=data)

        if response.status_code != 200:
            raise DattoApiError(
                f"OAuth token request failed: {response.status_code} {response.text[:200]}",
                response.status_code,
            )

        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 360000))
        self._token_expires_at = time.time() + expires_in
        logger.info("Datto API access token refreshed")

    async def get_device_by_id(self, device_id: int | str) -> dict[str, Any]:
        token = await self.ensure_token()
        url = f"{self._api_root}/v2/device/id/{device_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if response.status_code == 404:
            raise DattoApiError(f"Device id {device_id} not found", 404)
        if response.status_code == 401:
            await self._refresh_token()
            return await self.get_device_by_id(device_id)
        if response.status_code != 200:
            raise DattoApiError(
                f"Get device failed: {response.status_code} {response.text[:200]}",
                response.status_code,
            )
        return response.json()

    async def create_quick_job(self, device_uid: str, *, retry_auth: bool = True) -> dict[str, Any]:
        token = await self.ensure_token()
        url = f"{self._api_root}/v2/device/{device_uid}/quickjob"
        body = {
            "jobName": self._settings.datto_job_name,
            "jobComponent": {
                "componentUid": self._settings.datto_component_uid,
                "variables": self._settings.job_variables,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.put(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )

        if response.status_code == 401 and retry_auth:
            await self._refresh_token()
            return await self.create_quick_job(device_uid, retry_auth=False)

        if response.status_code == 429:
            raise DattoApiError("Rate limited (429)", 429)

        if response.status_code not in (200, 201):
            raise DattoApiError(
                f"Quick job failed for {device_uid}: {response.status_code} {response.text[:300]}",
                response.status_code,
            )

        if response.content:
            return response.json()
        return {}
