"""Command-line interface for the connectivity checks."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

from healthcheck import __version__, checks
from healthcheck.config import ConfigError, load_settings, missing_settings

SERVICE_ORDER = ("redis", "mongodb", "mysql", "rabbitmq")
ALIASES = {
    "redis": "redis",
    "mongodb": "mongodb",
    "mongo": "mongodb",
    "mysql": "mysql",
    "mysql-db": "mysql",
    "rabbitmq": "rabbitmq",
    "rabbit": "rabbitmq",
    "rabbit-mq": "rabbitmq",
}

_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


class UsageError(Exception):
    """Raised when the command line asks for an unknown service."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="health-check",
        description="Check connectivity to Redis, MongoDB, MySQL, and RabbitMQ.",
        epilog=(
            "Exit codes: 0 when every check passes, "
            "1 when a check fails, 2 when configuration is invalid."
        ),
    )
    parser.add_argument(
        "--only",
        help="Comma-separated services to check: redis, mongodb, mysql, rabbitmq",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON report on stdout",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5,
        help="Per-check timeout in seconds (default: 5)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Extra attempts for checks that fail (default: 0)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=30,
        help="Seconds to wait between retries (default: 30)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored status text",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"health-check {__version__}",
    )
    return parser


def parse_services(only: str | None) -> list[str]:
    if not only:
        return list(SERVICE_ORDER)
    selected: list[str] = []
    unknown: list[str] = []
    for raw in only.split(","):
        key = raw.strip().lower()
        if not key:
            continue
        canonical = ALIASES.get(key)
        if canonical is None:
            unknown.append(raw.strip())
        elif canonical not in selected:
            selected.append(canonical)
    if unknown:
        joined = ", ".join(unknown)
        choices = ", ".join(SERVICE_ORDER)
        raise UsageError(f"Unknown service(s): {joined}. Choose from {choices}")
    if not selected:
        raise UsageError("No services selected")
    return [name for name in SERVICE_ORDER if name in selected]


def stdout_color(no_color: bool, stream=None) -> bool:
    if no_color or os.environ.get("NO_COLOR"):
        return False
    stream = stream if stream is not None else sys.stdout
    return bool(stream.isatty())


def render_human(results: list[checks.CheckResult], *, color: bool, attempts: int) -> str:
    lines: list[str] = []
    for result in results:
        status = "OK" if result.ok else "FAIL"
        shown = status
        if color:
            paint = _GREEN if result.ok else _RED
            shown = f"{paint}{status}{_RESET}"
        padding = " " * (4 - len(status))
        lines.append(
            f"{result.name:<10} {shown}{padding}  {result.detail} ({result.elapsed_ms}ms)"
        )

    failed = sum(not result.ok for result in results)
    if failed:
        summary = f"{failed} of {len(results)} checks failed"
        paint = _RED
    else:
        summary = f"all {len(results)} checks passed"
        paint = _GREEN
    if color:
        summary = f"{paint}{summary}{_RESET}"
    lines.append("")
    lines.append(summary)
    if attempts > 1:
        lines.append(f"finished after {attempts} attempts")
    return "\n".join(lines)


def render_json(results: list[checks.CheckResult], attempts: int) -> str:
    payload = {
        "ok": all(result.ok for result in results),
        "attempts": attempts,
        "checks": [
            {
                "name": result.name,
                "ok": result.ok,
                "detail": result.detail,
                "elapsed_ms": result.elapsed_ms,
            }
            for result in results
        ],
    }
    return json.dumps(payload, indent=2)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout <= 0:
        print("--timeout must be greater than 0", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("--retries must be 0 or greater", file=sys.stderr)
        return 2
    if args.delay < 0:
        print("--delay must be 0 or greater", file=sys.stderr)
        return 2

    try:
        names = parse_services(args.only)
        settings = load_settings()
        missing = missing_settings(settings, names)
        if missing:
            raise ConfigError("Missing configuration: " + ", ".join(missing))
    except (ConfigError, UsageError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Driver libraries log their own connection errors. The report below is
    # the output callers should read.
    for logger_name in ("pika", "pymongo", "mysql.connector"):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)

    pending = list(names)
    results_by_name: dict[str, checks.CheckResult] = {}
    attempts = 0
    max_attempts = args.retries + 1
    while pending and attempts < max_attempts:
        attempts += 1
        for name in pending:
            results_by_name[name] = checks.CHECKS[name](settings, args.timeout)
        pending = [name for name in pending if not results_by_name[name].ok]
        if pending and attempts < max_attempts:
            _report_retry(pending, args.delay, attempts + 1, max_attempts, args.json)
            if args.delay:
                time.sleep(args.delay)

    results = [results_by_name[name] for name in names]
    if args.json:
        print(render_json(results, attempts))
    else:
        print(render_human(results, color=stdout_color(args.no_color), attempts=attempts))
    return 0 if all(result.ok for result in results) else 1


def _report_retry(pending, delay, attempt, max_attempts, as_json: bool) -> None:
    stream = sys.stderr if as_json else sys.stdout
    names = ", ".join(pending)
    if delay:
        print(
            f"retrying {names} in {delay:g}s ({attempt}/{max_attempts})",
            file=stream,
        )
    else:
        print(f"retrying {names} ({attempt}/{max_attempts})", file=stream)
