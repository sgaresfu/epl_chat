"""Database URL normalisation.

Render's Postgres ``connectionString`` is a bare ``postgresql://…`` with no
driver. SQLAlchemy resolves that to psycopg2 — a *synchronous* driver that an
async engine cannot use and that is not installed — so both the api's startup
and Alembic's pre-deploy migration failed with ``ModuleNotFoundError: psycopg2``,
an error that points at a missing package rather than at the scheme.

These tests cover every URL shape the app can be handed.
"""

from __future__ import annotations

import pytest
from shared.config import Settings
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine


def settings(url: str) -> Settings:
    return Settings(database_url=url, session_secret="test-secret-abcdefghijklmnop")


RENDER = "postgresql://league:pw@dpg-abc123.oregon-postgres.render.com/league"


class TestRenderPostgres:
    def test_a_driverless_url_gains_an_async_driver(self) -> None:
        assert settings(RENDER).async_database_url.startswith("postgresql+asyncpg://")

    def test_a_driverless_url_gains_a_sync_driver_for_alembic(self) -> None:
        assert settings(RENDER).sync_database_url.startswith("postgresql+psycopg://")

    def test_the_host_and_credentials_survive_normalisation(self) -> None:
        url = settings(RENDER).async_database_url
        assert "league:pw@dpg-abc123.oregon-postgres.render.com" in url
        assert url.endswith("/league")

    def test_an_async_engine_can_actually_be_built(self) -> None:
        create_async_engine(settings(RENDER).async_database_url)

    def test_a_sync_engine_can_actually_be_built(self) -> None:
        create_engine(settings(RENDER).sync_database_url)


class TestOtherShapes:
    def test_the_older_postgres_prefix_is_upgraded(self) -> None:
        # Some providers still hand out postgres://, which SQLAlchemy rejects.
        config = settings("postgres://u:p@host/db")
        assert config.async_database_url == "postgresql+asyncpg://u:p@host/db"

    def test_an_explicit_async_driver_is_left_alone(self) -> None:
        url = "postgresql+asyncpg://u:p@host/db"
        assert settings(url).async_database_url == url

    def test_an_explicit_driver_still_yields_a_sync_url(self) -> None:
        config = settings("postgresql+asyncpg://u:p@host/db")
        assert config.sync_database_url == "postgresql+psycopg://u:p@host/db"

    def test_sqlite_gains_its_async_driver(self) -> None:
        config = settings("sqlite:///./league.db")
        assert config.async_database_url == "sqlite+aiosqlite:///./league.db"

    def test_sqlite_sync_url_drops_the_async_driver(self) -> None:
        config = settings("sqlite+aiosqlite:///./league.db")
        assert config.sync_database_url == "sqlite:///./league.db"

    @pytest.mark.parametrize(
        "url",
        [
            RENDER,
            "postgres://u:p@host/db",
            "postgresql+asyncpg://u:p@host/db",
            "sqlite+aiosqlite:///./league.db",
            "sqlite:///./league.db",
        ],
    )
    def test_every_shape_produces_two_usable_engines(self, url: str) -> None:
        config = settings(url)
        create_async_engine(config.async_database_url)
        create_engine(config.sync_database_url)


class TestTheImageCanRunMigrations:
    def test_the_api_dockerfile_installs_a_sync_postgres_driver(self) -> None:
        """preDeployCommand runs `alembic upgrade head` inside the api image.

        Alembic is synchronous, so asyncpg alone is not enough — without a sync
        driver the first deploy fails before it serves a request.
        """
        import pathlib

        dockerfile = (pathlib.Path(__file__).parents[1] / "services" / "api" / "Dockerfile").read_text()
        assert "psycopg" in dockerfile
        assert "alembic" in dockerfile
