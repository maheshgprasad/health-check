import json
import os
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

from healthcheck import checks
from healthcheck.checks import (
    CheckResult,
    check_mongo,
    check_mysql,
    check_rabbit,
    check_redis,
)
from healthcheck.cli import main, render_human, render_json
from healthcheck.config import ConfigError, Settings, load_settings, missing_settings


def configured_settings(**overrides) -> Settings:
    values = dict(
        redis_host="redis.example",
        redis_port=6379,
        mongo_url="mongodb://mongo.example:27017",
        db_host="mysql.example",
        db_port=3306,
        db_username="app",
        db_password="db-secret",
        db_name="app",
        rabbit_host="rabbit.example",
        rabbit_port=5672,
        rabbit_username="guest",
        rabbit_password="rabbit-secret",
        rabbit_vhost="/",
    )
    values.update(overrides)
    return Settings(**values)


class RedisCheckTests(unittest.TestCase):
    def test_success_pings_and_closes(self):
        client = MagicMock()
        result = check_redis(
            configured_settings(),
            timeout=2,
            client_factory=lambda **kwargs: client,
        )
        client.ping.assert_called_once_with()
        client.close.assert_called_once_with()
        self.assertTrue(result.ok)
        self.assertEqual(result.name, "redis")
        self.assertIn("redis.example:6379", result.detail)

    def test_failure_closes_and_redacts_password(self):
        client = MagicMock()
        client.ping.side_effect = ConnectionError("auth failed for secret-pass")

        def factory(**kwargs):
            self.assertEqual(kwargs["socket_connect_timeout"], 1)
            self.assertEqual(kwargs["socket_timeout"], 1)
            self.assertEqual(kwargs["retry"].get_retries(), 0)
            self.assertEqual(kwargs["password"], "secret-pass")
            return client

        result = check_redis(
            configured_settings(redis_password="secret-pass"),
            timeout=1,
            client_factory=factory,
        )
        client.close.assert_called_once_with()
        self.assertFalse(result.ok)
        self.assertIn("ConnectionError", result.detail)
        self.assertNotIn("secret-pass", result.detail)

    def test_constructor_failure_has_no_close(self):
        def factory(**kwargs):
            raise OSError("refused")

        result = check_redis(configured_settings(), 1, client_factory=factory)
        self.assertFalse(result.ok)
        self.assertIn("OSError", result.detail)


class MongoCheckTests(unittest.TestCase):
    def test_success_pings_without_credentials_in_detail(self):
        client = MagicMock()
        url = "mongodb://user:s3cret@mongo.example:27017/?authSource=admin"
        result = check_mongo(
            configured_settings(mongo_url=url),
            timeout=1.5,
            client_factory=lambda *args, **kwargs: client,
        )
        client.admin.command.assert_called_once_with("ping")
        client.close.assert_called_once_with()
        self.assertTrue(result.ok)
        self.assertEqual(result.detail, "connection established (mongo.example:27017)")
        self.assertNotIn("s3cret", result.detail)

    def test_failure_redacts_url_and_password(self):
        url = "mongodb://user:s3cret@mongo.example:27017/admin"

        def factory(*args, **kwargs):
            self.assertEqual(kwargs["serverSelectionTimeoutMS"], 1000)
            raise RuntimeError(f"failed {args[0]} password=s3cret")

        result = check_mongo(
            configured_settings(mongo_url=url),
            timeout=1,
            client_factory=factory,
        )
        self.assertNotIn(url, result.detail)
        self.assertNotIn("s3cret", result.detail)
        self.assertIn("***", result.detail)

    def test_timeout_detail_drops_topology_dump(self):
        message = (
            "192.0.2.1:27017: timed out (configured timeouts: socketTimeoutMS: 1000.0ms), "
            "Timeout: 1.0s, Topology Description: <TopologyDescription id: abc>"
        )

        def factory(*args, **kwargs):
            raise RuntimeError(message)

        result = check_mongo(configured_settings(), 1, client_factory=factory)
        self.assertEqual(result.detail, "RuntimeError: 192.0.2.1:27017: timed out")


class MySqlCheckTests(unittest.TestCase):
    def test_success_passes_integer_port_and_closes(self):
        connection = MagicMock()
        seen = {}

        def factory(**kwargs):
            seen.update(kwargs)
            return connection

        result = check_mysql(configured_settings(), 3, client_factory=factory)
        self.assertTrue(result.ok)
        self.assertIsInstance(seen["port"], int)
        self.assertEqual(seen["port"], 3306)
        self.assertEqual(seen["connection_timeout"], 3)
        connection.close.assert_called_once_with()

    def test_connection_error_is_a_failed_check(self):
        def factory(**kwargs):
            raise RuntimeError("can't connect")

        result = check_mysql(configured_settings(), 1, client_factory=factory)
        self.assertFalse(result.ok)
        self.assertIn("RuntimeError", result.detail)
        self.assertNotIn("db-secret", result.detail)


class RabbitCheckTests(unittest.TestCase):
    def test_closed_connection_fails(self):
        connection = MagicMock()
        connection.is_open = False
        result = check_rabbit(
            configured_settings(),
            1,
            connect=lambda settings, timeout: connection,
        )
        self.assertFalse(result.ok)
        connection.close.assert_called_once_with()

    def test_failure_redacts_password(self):
        def connect(settings, timeout):
            raise RuntimeError(f"auth failed: {settings.rabbit_password}")

        result = check_rabbit(configured_settings(), 1, connect=connect)
        self.assertFalse(result.ok)
        self.assertNotIn("rabbit-secret", result.detail)

    def test_parameters_use_timeout_and_integer_port(self):
        settings = configured_settings(rabbit_port=5673, rabbit_vhost="/app")
        with patch("pika.BlockingConnection") as blocking:
            blocking.return_value.is_open = True
            result = check_rabbit(settings, timeout=2)
        self.assertTrue(result.ok)
        parameters = blocking.call_args.args[0]
        self.assertEqual(parameters.host, "rabbit.example")
        self.assertEqual(parameters.port, 5673)
        self.assertIsInstance(parameters.port, int)
        self.assertEqual(parameters.virtual_host, "/app")
        self.assertEqual(parameters.socket_timeout, 2)
        self.assertEqual(parameters.stack_timeout, 2)
        self.assertEqual(parameters.blocked_connection_timeout, 2)
        self.assertEqual(parameters.connection_attempts, 1)
        self.assertEqual(parameters.credentials.username, "guest")
        self.assertEqual(parameters.credentials.password, "rabbit-secret")


class ConfigTests(unittest.TestCase):
    def test_missing_settings_lists_required_names(self):
        missing = missing_settings(Settings(), ["redis", "mysql", "rabbitmq"])
        self.assertEqual(
            missing,
            ["REDIS_HOST", "DB_HOST", "DB_USERNAME", "DB_NAME", "RABBIT_HOST", "RABBIT_USERNAME"],
        )

    def test_load_settings_casts_ports_and_strips_quotes(self):
        env = {
            "REDIS_HOST": '"redis.example"',
            "REDIS_PORT": "6380",
            "REDIS_PASSWORD": "pw",
            "REDIS_DB": "2",
            "MONGO_URL": "mongodb://localhost:27017",
            "DB_HOST": "mysql.example",
            "DB_PORT": "3307",
            "DB_USERNAME": "root",
            "DB_PASSWORD": "",
            "DB_NAME": "app",
            "RABBIT_HOST": "rabbit.example",
            "RABBIT_PORT": "5673",
            "RABBIT_USERNAME": "guest",
            "RABBIT_PASSWORD": "guest",
            "RABBIT_VHOST": "/app",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = load_settings()
        self.assertEqual(settings.redis_host, "redis.example")
        self.assertEqual(settings.redis_port, 6380)
        self.assertEqual(settings.redis_db, 2)
        self.assertEqual(settings.db_port, 3307)
        self.assertEqual(settings.db_password, "")
        self.assertEqual(settings.rabbit_port, 5673)
        self.assertEqual(settings.rabbit_vhost, "/app")
        self.assertIsInstance(settings.db_port, int)

    def test_invalid_port_raises_config_error(self):
        with patch.dict(os.environ, {"DB_PORT": "abc"}, clear=False):
            with self.assertRaises(ConfigError) as caught:
                load_settings()
        self.assertIn("DB_PORT", str(caught.exception))

    def test_port_out_of_range(self):
        with patch.dict(os.environ, {"RABBIT_PORT": "70000"}, clear=False):
            with self.assertRaises(ConfigError):
                load_settings()


class CliTests(unittest.TestCase):
    def test_failure_status_is_red_for_mysql_and_rabbitmq(self):
        text = render_human(
            [
                CheckResult("mysql", False, "down", 10),
                CheckResult("rabbitmq", False, "down", 12),
            ],
            color=True,
            attempts=1,
        )
        self.assertEqual(text.count("\033[31mFAIL\033[0m"), 2)
        self.assertNotIn("\033[32m", text)
        self.assertIn("2 of 2 checks failed", text)

    def test_success_status_is_green(self):
        text = render_human(
            [CheckResult("redis", True, "up", 4)],
            color=True,
            attempts=1,
        )
        self.assertIn("\033[32mOK\033[0m", text)
        self.assertIn("all 1 checks passed", text)

    def test_json_report(self):
        text = render_json(
            [CheckResult("redis", False, "down", 4)],
            attempts=2,
        )
        payload = json.loads(text)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["attempts"], 2)
        self.assertEqual(payload["checks"][0]["elapsed_ms"], 4)

    def test_one_failure_still_checks_the_rest(self):
        called = []

        def make(name, ok):
            def _check(settings, timeout):
                called.append(name)
                return CheckResult(name, ok, "x", 1)

            return _check

        fake = {
            "redis": make("redis", False),
            "mongodb": make("mongodb", True),
            "mysql": make("mysql", True),
            "rabbitmq": make("rabbitmq", True),
        }
        stdout = StringIO()
        with patch.object(checks, "CHECKS", fake):
            with patch("healthcheck.cli.load_settings", return_value=configured_settings()):
                with patch("sys.stdout", stdout):
                    code = main(["--no-color"])
        self.assertEqual(code, 1)
        self.assertEqual(called, ["redis", "mongodb", "mysql", "rabbitmq"])
        self.assertIn("FAIL", stdout.getvalue())

    def test_retries_skip_checks_that_already_passed(self):
        counts = {"redis": 0, "mysql": 0}

        def redis_check(settings, timeout):
            counts["redis"] += 1
            return CheckResult("redis", counts["redis"] >= 2, "x", 1)

        def mysql_check(settings, timeout):
            counts["mysql"] += 1
            return CheckResult("mysql", True, "x", 1)

        fake = {"redis": redis_check, "mysql": mysql_check}
        stdout = StringIO()
        with patch.object(checks, "CHECKS", fake):
            with patch("healthcheck.cli.load_settings", return_value=configured_settings()):
                with patch("healthcheck.cli.time.sleep") as sleep:
                    with patch("sys.stdout", stdout):
                        code = main(
                            [
                                "--only",
                                "redis,mysql",
                                "--retries",
                                "2",
                                "--delay",
                                "5",
                                "--no-color",
                            ]
                        )
        self.assertIn("finished after 2 attempts", stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(counts["redis"], 2)
        self.assertEqual(counts["mysql"], 1)
        sleep.assert_called_once_with(5)

    def test_json_output_has_no_color_codes(self):
        fake = {
            "redis": lambda settings, timeout: CheckResult("redis", True, "up", 3),
        }
        stdout = StringIO()
        with patch.object(checks, "CHECKS", fake):
            with patch("healthcheck.cli.load_settings", return_value=configured_settings()):
                with patch("sys.stdout", stdout):
                    code = main(["--only", "redis", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertNotIn("\033", stdout.getvalue())

    def test_missing_config_skips_connections(self):
        called = []

        def boom(settings, timeout):
            called.append(True)
            return CheckResult("redis", True, "x", 1)

        fake = {name: boom for name in ("redis", "mongodb", "mysql", "rabbitmq")}
        stderr = StringIO()
        with patch.object(checks, "CHECKS", fake):
            with patch("healthcheck.cli.load_settings", return_value=Settings()):
                with patch("sys.stderr", stderr):
                    code = main([])
        self.assertEqual(code, 2)
        self.assertEqual(called, [])
        self.assertIn("REDIS_HOST", stderr.getvalue())

    def test_unknown_service(self):
        stderr = StringIO()
        with patch("sys.stderr", stderr):
            code = main(["--only", "postgres"])
        self.assertEqual(code, 2)
        self.assertIn("postgres", stderr.getvalue())

    def test_long_error_is_truncated(self):
        def factory(**kwargs):
            raise RuntimeError("x" * 500)

        result = check_redis(configured_settings(), 1, client_factory=factory)
        self.assertLessEqual(len(result.detail), 300)
        self.assertTrue(result.detail.endswith("…"))


if __name__ == "__main__":
    unittest.main()
