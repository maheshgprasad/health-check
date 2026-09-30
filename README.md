# health-check

Check whether Redis, MongoDB, MySQL, and RabbitMQ are reachable.

Each selected service is checked on its own, with a timeout, and open connections are closed before the command exits. The process exits 0 when every check passes and 1 when any check fails, so it can be used from cron, CI, or a container probe.

## Install

```bash
python3 -m pip install -r requirements.txt
```

Python 3.9 or newer is required.

## Configure

Copy the sample environment file and fill in the services you want to check:

```bash
cp .env-sample .env
```

Environment variables take precedence over `.env`. Only the variables for the services you select are required.

| Service | Required | Optional |
| --- | --- | --- |
| Redis | `REDIS_HOST` | `REDIS_PORT` (6379), `REDIS_PASSWORD`, `REDIS_DB` (0) |
| MongoDB | `MONGO_URL` | |
| MySQL | `DB_HOST`, `DB_USERNAME`, `DB_NAME` | `DB_PORT` (3306), `DB_PASSWORD` |
| RabbitMQ | `RABBIT_HOST`, `RABBIT_USERNAME` | `RABBIT_PORT` (5672), `RABBIT_PASSWORD`, `RABBIT_VHOST` (`/`) |

`.env` is gitignored. Keep passwords there or in the process environment.

## Run

From the repository directory:

```bash
python3 -m healthcheck
python3 -m healthcheck --only redis,mysql
python3 -m healthcheck --json
python3 -m healthcheck --retries 3 --delay 30
./health_check.sh
python3 redis-test.py
```

`mongo-test.py`, `mysql-test.py`, and `rabbit-test.py` check that one service. `health_check.sh` runs the full command and forwards any arguments.

`--timeout` is the per-check limit in seconds (default 5). `--retries` repeats only the checks that failed. `--delay` is the wait between those attempts (default 30 seconds).

A text report looks like this:

```text
redis      OK    connection established (redis.example:6379) (12ms)
mongodb    FAIL  ServerSelectionTimeoutError: … (5001ms)
mysql      OK    connection established (mysql.example:3306) (40ms)
rabbitmq   OK    connection established (rabbit.example:5672) (18ms)

1 of 4 checks failed
```

`--json` prints one object and keeps retry progress on stderr:

```json
{
  "ok": false,
  "attempts": 1,
  "checks": [
    {
      "name": "redis",
      "ok": true,
      "detail": "connection established (redis.example:6379)",
      "elapsed_ms": 12
    }
  ]
}
```

Colored status text is used when stdout is a terminal. Set `NO_COLOR` or pass `--no-color` to turn it off.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Every selected check passed |
| 1 | One or more checks failed |
| 2 | Missing configuration, an unknown service, or an invalid flag |

## Checks

- Redis: `PING`
- MongoDB: `ping` on the `admin` database
- MySQL: open a connection to the configured database
- RabbitMQ: open an AMQP connection and confirm it is open

Passwords are removed from error text before it is printed.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
