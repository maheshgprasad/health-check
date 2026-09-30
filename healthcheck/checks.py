"""Connectivity checks for each supported service."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from healthcheck.config import Settings


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    elapsed_ms: int


def check_redis(settings: Settings, timeout: float, client_factory=None) -> CheckResult:
    started = time.perf_counter()
    client = None
    secrets = _secrets(settings.redis_password)
    try:
        if client_factory is None:
            from redis import Redis

            client_factory = Redis
        # redis-py retries timeouts several times unless this is set, which
        # would ignore --timeout.
        from redis.backoff import NoBackoff
        from redis.retry import Retry

        client = client_factory(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            db=settings.redis_db,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            retry=Retry(NoBackoff(), 0),
        )
        client.ping()
        ok = True
        detail = f"connection established ({settings.redis_host}:{settings.redis_port})"
    except Exception as exc:
        ok = False
        detail = _detail_from_exc(exc, secrets)
    finally:
        _close(client)
    return CheckResult("redis", ok, detail, _elapsed_ms(started))


def check_mongo(settings: Settings, timeout: float, client_factory=None) -> CheckResult:
    started = time.perf_counter()
    client = None
    secrets = _mongo_secrets(settings.mongo_url or "")
    try:
        if client_factory is None:
            from pymongo import MongoClient

            client_factory = MongoClient
        timeout_ms = max(1, int(timeout * 1000))
        client = client_factory(
            settings.mongo_url,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        client.admin.command("ping")
        ok = True
        detail = f"connection established ({_mongo_target(settings.mongo_url or '')})"
    except Exception as exc:
        ok = False
        detail = _detail_from_exc(exc, secrets)
    finally:
        _close(client)
    return CheckResult("mongodb", ok, detail, _elapsed_ms(started))


def check_mysql(settings: Settings, timeout: float, client_factory=None) -> CheckResult:
    started = time.perf_counter()
    connection = None
    secrets = _secrets(settings.db_password)
    try:
        if client_factory is None:
            from mysql.connector import connect

            client_factory = connect
        connection = client_factory(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_username,
            password=settings.db_password,
            database=settings.db_name,
            connection_timeout=timeout,
        )
        if not connection:
            ok = False
            detail = "connection failed"
        else:
            ok = True
            detail = f"connection established ({settings.db_host}:{settings.db_port})"
    except Exception as exc:
        ok = False
        detail = _detail_from_exc(exc, secrets)
    finally:
        _close(connection)
    return CheckResult("mysql", ok, detail, _elapsed_ms(started))


def check_rabbit(settings: Settings, timeout: float, connect=None) -> CheckResult:
    started = time.perf_counter()
    connection = None
    secrets = _secrets(settings.rabbit_password)
    try:
        opener = connect or _rabbit_connect
        connection = opener(settings, timeout)
        if not getattr(connection, "is_open", False):
            ok = False
            detail = "connection is not open"
        else:
            ok = True
            detail = (
                f"connection established ({settings.rabbit_host}:{settings.rabbit_port})"
            )
    except Exception as exc:
        ok = False
        detail = _detail_from_exc(exc, secrets)
    finally:
        _close(connection)
    return CheckResult("rabbitmq", ok, detail, _elapsed_ms(started))


def _rabbit_connect(settings: Settings, timeout: float):
    import pika

    credentials = pika.PlainCredentials(
        settings.rabbit_username or "",
        settings.rabbit_password or "",
    )
    parameters = pika.ConnectionParameters(
        host=settings.rabbit_host,
        port=settings.rabbit_port,
        virtual_host=settings.rabbit_vhost or "/",
        credentials=credentials,
        socket_timeout=timeout,
        stack_timeout=timeout,
        blocked_connection_timeout=timeout,
        connection_attempts=1,
        retry_delay=0,
    )
    return pika.BlockingConnection(parameters)


CHECKS = {
    "redis": check_redis,
    "mongodb": check_mongo,
    "mysql": check_mysql,
    "rabbitmq": check_rabbit,
}


def _close(resource) -> None:
    if resource is None:
        return
    close = getattr(resource, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        return


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _secrets(*values: str | None) -> tuple[str, ...]:
    return tuple(value for value in values if value and len(value) >= 3)


def _mongo_secrets(url: str) -> tuple[str, ...]:
    parsed = urlparse(url)
    password = unquote(parsed.password) if parsed.password else None
    return _secrets(url, parsed.password, password)


def _mongo_target(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.hostname:
        return "mongodb"
    if parsed.port:
        return f"{parsed.hostname}:{parsed.port}"
    return parsed.hostname


def _detail_from_exc(exc: Exception, secrets: tuple[str, ...]) -> str:
    text = _redact(f"{type(exc).__name__}: {exc}", secrets)
    text = " ".join(text.split())
    # PyMongo appends a topology dump after this marker.
    marker = " (configured "
    if marker in text:
        text = text.split(marker, 1)[0]
    if len(text) > 300:
        return text[:299] + "…"
    return text


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in sorted(set(secrets), key=len, reverse=True):
        text = text.replace(secret, "***")
    return text
