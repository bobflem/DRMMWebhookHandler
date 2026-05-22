from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings


@dataclass(frozen=True)
class WebhookProfile:
    id: str
    secret: str
    component_uid: str
    job_name: str
    variables: list[dict[str, str]]


class ProfileRegistry:
    def __init__(self, profiles: list[WebhookProfile]) -> None:
        self._by_id = {p.id: p for p in profiles}
        self._by_secret = {p.secret: p for p in profiles}

    @property
    def profiles(self) -> list[WebhookProfile]:
        return list(self._by_id.values())

    def get_by_id(self, profile_id: str) -> WebhookProfile | None:
        return self._by_id.get(profile_id)

    def resolve_secret(self, secret: str | None) -> WebhookProfile | None:
        if not secret:
            return None
        return self._by_secret.get(secret)


def _parse_profile(raw: dict[str, Any], index: int) -> WebhookProfile:
    profile_id = raw.get("id")
    secret = raw.get("secret")
    component_uid = raw.get("component_uid")
    if not profile_id or not secret or not component_uid:
        raise ValueError(
            f"Profile at index {index} requires id, secret, and component_uid"
        )
    variables = raw.get("variables") or []
    if not isinstance(variables, list):
        raise ValueError(f"Profile {profile_id}: variables must be a list")
    return WebhookProfile(
        id=str(profile_id),
        secret=str(secret),
        component_uid=str(component_uid),
        job_name=str(raw.get("job_name") or "Webhook remediation"),
        variables=variables,
    )


def load_profile_registry(settings: Settings) -> ProfileRegistry:
    path = Path(settings.profiles_config_path)
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Profiles config {path} must be a YAML mapping")
        raw_profiles = data.get("profiles")
        if not isinstance(raw_profiles, list) or not raw_profiles:
            raise ValueError(f"Profiles config {path} must contain a non-empty profiles list")
        profiles = [_parse_profile(p, i) for i, p in enumerate(raw_profiles)]
    else:
        profiles = _legacy_profile_from_env(settings)

    secrets = [p.secret for p in profiles]
    if len(secrets) != len(set(secrets)):
        raise ValueError("Duplicate webhook secrets in profiles configuration")

    ids = [p.id for p in profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate profile ids in profiles configuration")

    return ProfileRegistry(profiles)


def _legacy_profile_from_env(settings: Settings) -> list[WebhookProfile]:
    if not settings.webhook_secret or not settings.datto_component_uid:
        raise ValueError(
            f"Profiles config not found at {settings.profiles_config_path} "
            "and legacy WEBHOOK_SECRET / DATTO_COMPONENT_UID are not set"
        )
    return [
        WebhookProfile(
            id="default",
            secret=settings.webhook_secret,
            component_uid=settings.datto_component_uid,
            job_name=settings.datto_job_name,
            variables=settings.job_variables,
        )
    ]
