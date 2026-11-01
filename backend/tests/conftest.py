import pytest

VALID_ENV = {
    "APP_ENV": "test",
    "LOG_LEVEL": "INFO",
    "WEB_ORIGIN": "http://localhost:3000",
    "S3_REGION": "us-east-1",
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "S3_ENDPOINT_URL": "http://localhost:9000",
    "S3_ACCESS_KEY": "access-key",
    "S3_SECRET_KEY": "secret-key-1234",
    "S3_BUCKET": "documents",
}


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    return monkeypatch
