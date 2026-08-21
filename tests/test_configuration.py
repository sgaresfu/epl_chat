"""Deployment configuration must fail loudly and name the problem.

``database_url`` defaults to SQLite so a clean clone runs with no setup. In a
container that default is a trap: the file is on ephemeral storage and the
async driver for it is not in the production image, so a missing DATABASE_URL
surfaced as ``ModuleNotFoundError: aiosqlite`` — several frames inside
SQLAlchemy, naming a package rather than the variable that was never set.

Alembic made it worse by running first and *succeeding* against that throwaway
file, so the deploy looked half-healthy on the way down.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest
from shared.config import ConfigurationError, Settings, validate_for_deployment

ROOT = pathlib.Path(__file__).parents[1]

GOOD = {
    "database_url": "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/neondb",
    "session_secret": "a" * 64,
    "code_coyg": "something",
}


def production(**over: object) -> Settings:
    values: dict[str, object] = {"environment": "production", **GOOD, **over}
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class TestLocalIsNeverBlocked:
    def test_local_skips_validation_entirely(self) -> None:
        # The SQLite default is exactly right for a clean clone.
        validate_for_deployment(Settings(environment="local", _env_file=None))


class TestProductionRefusesToStartBroken:
    def test_a_correct_configuration_passes(self) -> None:
        validate_for_deployment(production())

    def test_a_missing_database_url_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="DATABASE_URL"):
            validate_for_deployment(production(database_url="sqlite+aiosqlite:///./league.db"))

    def test_the_message_explains_the_ephemeral_disk(self) -> None:
        with pytest.raises(ConfigurationError) as exc:
            validate_for_deployment(production(database_url="sqlite+aiosqlite:///./x.db"))
        assert "ephemeral" in str(exc.value)

    def test_the_message_warns_about_renders_expiring_free_postgres(self) -> None:
        with pytest.raises(ConfigurationError) as exc:
            validate_for_deployment(production(database_url="sqlite:///x.db"))
        assert "30 days" in str(exc.value)

    def test_no_code_words_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="code words"):
            validate_for_deployment(production(code_coyg=""))

    def test_the_placeholder_session_secret_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="SESSION_SECRET"):
            validate_for_deployment(
                production(session_secret="dev-only-secret-change-me-in-every-real-environment")
            )

    def test_a_short_session_secret_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="SESSION_SECRET"):
            validate_for_deployment(production(session_secret="tooshort"))

    def test_every_problem_is_reported_at_once(self) -> None:
        # One deploy, one list — not three rounds of fix-and-redeploy.
        with pytest.raises(ConfigurationError) as exc:
            validate_for_deployment(Settings(environment="production", _env_file=None, session_secret="x"))
        message = str(exc.value)
        assert "DATABASE_URL" in message
        assert "code words" in message
        assert "SESSION_SECRET" in message


class TestTheApiCallsIt:
    def test_the_lifespan_validates_before_touching_anything(self) -> None:
        source = (ROOT / "services" / "api" / "main.py").read_text()
        assert "validate_for_deployment(settings)" in source


class TestTheEntrypointChecksFirst:
    ENTRYPOINT = ROOT / "services" / "api" / "entrypoint.sh"

    def test_it_refuses_to_migrate_without_a_database_url(self) -> None:
        """Otherwise Alembic reports success against a throwaway file."""
        result = subprocess.run(
            ["sh", str(self.ENTRYPOINT)],
            env={"PATH": "/usr/bin:/bin", "ENVIRONMENT": "production"},
            capture_output=True,
        )
        assert result.returncode == 1
        assert b"DATABASE_URL is not set" in result.stderr

    def test_the_failure_names_a_provider_that_actually_persists(self) -> None:
        result = subprocess.run(
            ["sh", str(self.ENTRYPOINT)],
            env={"PATH": "/usr/bin:/bin", "ENVIRONMENT": "production"},
            capture_output=True,
        )
        assert b"neon.tech" in result.stderr

    def test_it_does_not_block_local_use(self) -> None:
        # ENVIRONMENT=local must not require DATABASE_URL; it will fail later
        # for want of alembic on PATH, which is a different thing entirely.
        result = subprocess.run(
            ["sh", str(self.ENTRYPOINT)],
            env={"PATH": "/usr/bin:/bin", "ENVIRONMENT": "local"},
            capture_output=True,
        )
        assert b"DATABASE_URL is not set" not in result.stderr
