from pathlib import Path

import pytest

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
