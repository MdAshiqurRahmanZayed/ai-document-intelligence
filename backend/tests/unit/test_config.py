from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, load_settings


def test_missing_required_variable_names_it(
    valid_env: pytest.MonkeyPatch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    valid_env.delenv("DATABASE_URL")
    with pytest.raises(SystemExit) as exc:
        load_settings()
    assert "DATABASE_URL" in str(exc.value)


def test_invalid_value_names_variable(
    valid_env: pytest.MonkeyPatch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    valid_env.setenv("MAX_UPLOAD_MB", "abc")
    with pytest.raises(SystemExit) as exc:
        load_settings()
    assert "MAX_UPLOAD_MB" in str(exc.value)


def test_validation_error_does_not_leak_secret(
    valid_env: pytest.MonkeyPatch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    valid_env.setenv("S3_SECRET_KEY", "short")
    with pytest.raises(SystemExit) as exc:
        load_settings()
    message = str(exc.value)
    assert "S3_SECRET_KEY" in message
    assert "short" not in message


def test_secrets_are_masked(valid_env: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)
    dumped = str(settings.model_dump(mode="json")) + repr(settings)
    assert "secret-key-1234" not in dumped
    assert "access-key" not in dumped
    assert "u:p@" not in dumped


def test_environment_overrides_env_file(valid_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("S3_BUCKET=from-file\nREDIS_URL=redis://file:6379/0\n")
    valid_env.setenv("S3_BUCKET", "from-env")
    settings = Settings(_env_file=env_file)
    assert settings.s3_bucket == "from-env"
    assert settings.redis_url.get_secret_value() == "redis://localhost:6379/0"


@pytest.mark.parametrize(
    ("name", "attr", "default"),
    [
        ("APP_ENV", "app_env", "local"),
        ("LOG_LEVEL", "log_level", "INFO"),
        ("WEB_ORIGIN", "web_origin", "http://localhost:3000"),
        ("S3_BUCKET", "s3_bucket", "documents"),
        ("S3_REGION", "s3_region", "us-east-1"),
    ],
)
def test_default_used_when_variable_unset(
    name: str,
    attr: str,
    default: str,
    valid_env: pytest.MonkeyPatch,
) -> None:
    valid_env.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert getattr(settings, attr) == default


def test_default_is_overridden_by_environment(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.setenv("LOG_LEVEL", "DEBUG")
    assert Settings(_env_file=None).log_level == "DEBUG"


def test_ocr_concurrency_defaults_to_four_and_can_be_overridden(
    valid_env: pytest.MonkeyPatch,
) -> None:
    valid_env.delenv("OCR_CONCURRENCY", raising=False)
    assert Settings(_env_file=None).ocr_concurrency == 4
    valid_env.setenv("OCR_CONCURRENCY", "2")
    assert Settings(_env_file=None).ocr_concurrency == 2


def test_ocr_concurrency_of_zero_is_rejected(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.setenv("OCR_CONCURRENCY", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("name", "attr", "default", "override", "expected"),
    [
        ("GEMINI_EXTRACTION_MODEL", "gemini_extraction_model", "gemini-3.5-flash", "m1", "m1"),
        ("GEMINI_FALLBACK_MODEL", "gemini_fallback_model", "gemini-3.8-flash", "m2", "m2"),
        ("EXTRACTION_PAGES_PER_CALL", "extraction_pages_per_call", 6, "3", 3),
        ("LOW_CONFIDENCE_THRESHOLD", "low_confidence_threshold", 0.5, "0.8", 0.8),
    ],
)
def test_extraction_settings_have_defaults_and_can_be_overridden(
    valid_env: pytest.MonkeyPatch,
    name: str,
    attr: str,
    default: object,
    override: str,
    expected: object,
) -> None:
    valid_env.delenv(name, raising=False)
    assert getattr(Settings(_env_file=None), attr) == default
    valid_env.setenv(name, override)
    assert getattr(Settings(_env_file=None), attr) == expected


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EXTRACTION_PAGES_PER_CALL", "0"),
        ("LOW_CONFIDENCE_THRESHOLD", "1.5"),
        ("LOW_CONFIDENCE_THRESHOLD", "-0.1"),
    ],
)
def test_invalid_extraction_settings_are_rejected(
    valid_env: pytest.MonkeyPatch, name: str, value: str
) -> None:
    valid_env.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_api_key_is_optional_and_masked(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.delenv("API_KEY", raising=False)
    assert Settings(_env_file=None).api_key is None

    valid_env.setenv("API_KEY", "s3cret-value")
    settings = Settings(_env_file=None)
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "s3cret-value"
    assert "s3cret-value" not in repr(settings)  # a SecretStr never prints its value


def test_embedding_model_has_a_default_and_can_be_overridden(
    valid_env: pytest.MonkeyPatch,
) -> None:
    valid_env.delenv("EMBEDDING_MODEL", raising=False)
    assert Settings(_env_file=None).embedding_model == "models/gemini-embedding-001"

    valid_env.setenv("EMBEDDING_MODEL", "models/other")
    assert Settings(_env_file=None).embedding_model == "models/other"


@pytest.mark.parametrize("name", ["GOOGLE_API_KEY", "API_KEY"])
def test_an_empty_optional_secret_means_not_set(valid_env: pytest.MonkeyPatch, name: str) -> None:
    valid_env.setenv(name, "")  # what copying .env.example as it is produces

    settings = Settings(_env_file=None)

    assert settings.google_api_key is None and settings.api_key is None


def test_an_empty_required_variable_is_reported_as_missing(
    valid_env: pytest.MonkeyPatch, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here to fill the value in
    valid_env.setenv("DATABASE_URL", "")

    with pytest.raises(SystemExit) as exc:
        load_settings()

    assert "DATABASE_URL" in str(exc.value)
