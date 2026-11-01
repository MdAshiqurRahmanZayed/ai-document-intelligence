from functools import lru_cache

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    web_origin: str = "http://localhost:3000"
    readiness_timeout_seconds: float = Field(default=2, gt=0)
    max_upload_mb: int = Field(default=100, gt=0)

    database_url: SecretStr
    redis_url: SecretStr
    s3_endpoint_url: str
    s3_access_key: SecretStr
    s3_secret_key: SecretStr = Field(min_length=8)
    s3_bucket: str
    s3_region: str = "us-east-1"
    google_api_key: SecretStr | None = None


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        # Report variable names and reasons only; never echo input values (may be secrets).
        lines = [f"  {str(e['loc'][0]).upper()}: {e['msg']}" for e in exc.errors()]
        raise SystemExit("Invalid configuration:\n" + "\n".join(lines)) from None


@lru_cache
def get_settings() -> Settings:
    return load_settings()
