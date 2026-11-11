"""Runtime configuration. Every value has a laptop-safe default; Compose overrides via env."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: str = "production"
    app_version: str = "1.0.0"
    app_timezone: str = "Asia/Jerusalem"
    database_url: str = (
        "mysql+pymysql://squanchy:squanchy@mysql:3306/squanchy_kitchens?charset=utf8mb4"
    )

    alert_threshold_c: float = 5.0
    sample_interval_minutes: int = 15
    min_excursion_readings: int = 2

    seed_on_startup: bool = True
    seed_demo_data: bool = True
    seed_registry_file: str = "/data/seed/loggers.csv"
    seed_demo_dir: str = "/data/seed/mock-logger-files"

    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 5

    # Auth. No secrets have defaults in the repo. If ADMIN_PASSWORD / DEMO_MANAGER_PASSWORD
    # are unset, first start generates random passwords and prints them once in the API log;
    # if JWT_SECRET is unset, a random one is generated and kept in STATE_DIR.
    admin_username: str = "admin"
    admin_password: str | None = None
    admin_full_name: str = "Summer Smith"
    jwt_secret: str | None = None
    jwt_expire_minutes: int = 480
    demo_manager_password: str | None = None
    state_dir: str = "/data/state"

    @field_validator("admin_password", "jwt_secret", "demo_manager_password", mode="before")
    @classmethod
    def _blank_is_unset(cls, v: object) -> object:
        # Compose passes ${VAR:-} as an empty string when the variable is not set.
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
