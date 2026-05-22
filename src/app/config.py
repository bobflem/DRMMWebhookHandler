from functools import lru_cache
import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    datto_api_base_url: str = "https://zinfandel-api.centrastage.net"
    datto_api_key: str
    datto_api_secret: str

    profiles_config_path: str = "/config/profiles.yaml"

    # Legacy single-profile fallback when profiles file is missing
    webhook_secret: str = ""
    datto_component_uid: str = ""
    datto_job_name: str = "Webhook remediation"
    datto_job_variables_json: str = "[]"

    quickjob_interval_minutes: int = 15
    run_on_detect: bool = True
    data_dir: str = "/data"
    port: int = 8080

    @property
    def job_variables(self) -> list[dict[str, str]]:
        raw = json.loads(self.datto_job_variables_json or "[]")
        if not isinstance(raw, list):
            raise ValueError("DATTO_JOB_VARIABLES_JSON must be a JSON array")
        return raw

    @property
    def db_path(self) -> str:
        return f"{self.data_dir.rstrip('/')}/active_devices.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
