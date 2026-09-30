"""Environment configuration for service checks."""

from __future__ import annotations

from dataclasses import dataclass


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    redis_host: str | None = None
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0
    mongo_url: str | None = None
    db_host: str | None = None
    db_port: int = 3306
    db_username: str | None = None
    db_password: str = ""
    db_name: str | None = None
    rabbit_host: str | None = None
    rabbit_port: int = 5672
    rabbit_username: str | None = None
    rabbit_password: str = ""
    rabbit_vhost: str = "/"


_REQUIRED = {
    "redis": (("REDIS_HOST", "redis_host"),),
    "mongodb": (("MONGO_URL", "mongo_url"),),
    "mysql": (
        ("DB_HOST", "db_host"),
        ("DB_USERNAME", "db_username"),
        ("DB_NAME", "db_name"),
    ),
    "rabbitmq": (
        ("RABBIT_HOST", "rabbit_host"),
        ("RABBIT_USERNAME", "rabbit_username"),
    ),
}


def missing_settings(settings: Settings, services: list[str]) -> list[str]:
    missing: list[str] = []
    for service in services:
        for env_name, attr in _REQUIRED[service]:
            value = getattr(settings, attr)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(env_name)
    return missing


def load_settings() -> Settings:
    try:
        from decouple import config
    except ImportError as exc:
        raise ConfigError(
            "python-decouple is not installed. "
            "Run: python3 -m pip install -r requirements.txt"
        ) from exc

    return Settings(
        redis_host=_text(config, "REDIS_HOST"),
        redis_port=_port(config, "REDIS_PORT", 6379),
        redis_password=_secret(config, "REDIS_PASSWORD") or None,
        redis_db=_non_negative_int(config, "REDIS_DB", 0),
        mongo_url=_text(config, "MONGO_URL"),
        db_host=_text(config, "DB_HOST"),
        db_port=_port(config, "DB_PORT", 3306),
        db_username=_text(config, "DB_USERNAME"),
        db_password=_secret(config, "DB_PASSWORD") or "",
        db_name=_text(config, "DB_NAME"),
        rabbit_host=_text(config, "RABBIT_HOST"),
        rabbit_port=_port(config, "RABBIT_PORT", 5672),
        rabbit_username=_text(config, "RABBIT_USERNAME"),
        rabbit_password=_secret(config, "RABBIT_PASSWORD") or "",
        rabbit_vhost=_text(config, "RABBIT_VHOST") or "/",
    )


def _unwrap(raw) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def _text(config, key: str) -> str | None:
    value = _unwrap(config(key, default=None))
    return value or None


def _secret(config, key: str) -> str | None:
    return _unwrap(config(key, default=None))


def _port(config, key: str, default: int) -> int:
    return _integer(config, key, default, minimum=1, maximum=65535)


def _non_negative_int(config, key: str, default: int) -> int:
    return _integer(config, key, default, minimum=0, maximum=None)


def _integer(config, key: str, default: int, minimum: int, maximum: int | None) -> int:
    raw = config(key, default=default)
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return default
    if isinstance(raw, str):
        raw = _unwrap(raw)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            raise ConfigError(f"{key} must be {minimum} or greater")
        raise ConfigError(f"{key} must be a port between {minimum} and {maximum}")
    return value
