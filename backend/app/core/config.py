from functools import lru_cache

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # attribute = Field(validation_alias="ENV_VARIABLE_IT_IS_READ_FROM")
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    web_origin: str = Field(default="http://localhost:3000", validation_alias="WEB_ORIGIN")
    readiness_timeout_seconds: float = Field(
        default=2, gt=0, validation_alias="READINESS_TIMEOUT_SECONDS"
    )
    max_upload_mb: int = Field(default=100, gt=0, validation_alias="MAX_UPLOAD_MB")

    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    redis_url: SecretStr = Field(validation_alias="REDIS_URL")

    s3_endpoint_url: str = Field(validation_alias="S3_ENDPOINT_URL")
    s3_access_key: SecretStr = Field(validation_alias="S3_ACCESS_KEY")
    s3_secret_key: SecretStr = Field(min_length=8, validation_alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="documents", validation_alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", validation_alias="S3_REGION")

    google_api_key: SecretStr | None = Field(default=None, validation_alias="GOOGLE_API_KEY")


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
