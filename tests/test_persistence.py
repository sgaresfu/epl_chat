"""Predictions must survive a restart.

Render restarts a service on every deploy, so a prediction held in memory is a
prediction that disappears -- and the one thing this app must not lose is
somebody's filed table.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from services.api.repository import load_predictions, save_prediction, seed_predictions
from shared.cache import MemoryCache
from shared.clubs import CLUBS
from shared.config import Settings
from shared.db import Base
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.conftest import CODES, _build_app

TABLE = [c.short_name for c in CLUBS]


@pytest.fixture
async def db_factory() -> Any:
    """A file-backed engine so two 'processes' can share one database."""
    engine = create_async_engine("sqlite+aiosqlite://", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class TestSeeding:
    async def test_every_seeded_prediction_is_written_once(self, db_factory: Any) -> None:
        import json
        import pathlib

        seed = json.loads(
            (pathlib.Path(__file__).parents[1] / "shared" / "data" / "seed_predictions.json").read_text()
        )
        expected = len(seed["predictions"])

        async with db_factory() as db:
            written = await seed_predictions(db)
            await db.commit()
        assert written == expected

    async def test_seeding_twice_does_not_duplicate(self, db_factory: Any) -> None:
        async with db_factory() as db:
            await seed_predictions(db)
            await db.commit()
        async with db_factory() as db:
            second = await seed_predictions(db)
            await db.commit()
        assert second == 0

    async def test_re_seeding_never_overwrites_a_filed_prediction(self, db_factory: Any) -> None:
        """The failure this guards against: a redeploy resetting somebody's table."""
        async with db_factory() as db:
            await seed_predictions(db)
            await db.commit()

        # COYG changes their mind and refiles with a different order.
        reversed_table = list(reversed(TABLE))
        async with db_factory() as db:
            await save_prediction(db, "coyg", reversed_table, {}, {})
            await db.commit()

        # A deploy restarts the service and seeding runs again.
        async with db_factory() as db:
            await seed_predictions(db)
            await db.commit()

        async with db_factory() as db:
            stored = await load_predictions(db)
        assert stored["coyg"]["table"] == reversed_table


class TestSurvivesRestart:
    async def test_a_filed_prediction_is_still_there_after_a_restart(
        self, settings: Settings, cache: MemoryCache, db_factory: Any
    ) -> None:
        async with db_factory() as db:
            await seed_predictions(db)
            await db.commit()

        # First "process": TWZT files a table.
        app = _build_app(settings, cache, db_factory)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as http:
            await http.post("/api/session", json={"code": CODES["twzt"]})
            response = await http.put(
                "/api/predictions",
                json={"table": TABLE},
                headers={"X-CSRF-Token": http.cookies.get("pl_csrf") or ""},
            )
            assert response.status_code == 200

        # Second "process": a completely new app object, same database.
        restarted = _build_app(settings, cache, db_factory)
        async with AsyncClient(transport=ASGITransport(app=restarted), base_url="http://api.test") as http:
            await http.post("/api/session", json={"code": CODES["twzt"]})
            body = (await http.get("/api/predictions")).json()

        twzt = next(p for p in body["predictions"] if p["person"] == "twzt")
        assert twzt["filed"] is True
        assert twzt["table"] == TABLE
        assert twzt["submitted_at"]

    async def test_refiling_replaces_rather_than_duplicates(
        self, settings: Settings, cache: MemoryCache, db_factory: Any
    ) -> None:
        async with db_factory() as db:
            await seed_predictions(db)
            await db.commit()

        app = _build_app(settings, cache, db_factory)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as http:
            await http.post("/api/session", json={"code": CODES["bulba"]})
            token = http.cookies.get("pl_csrf") or ""
            await http.put("/api/predictions", json={"table": TABLE}, headers={"X-CSRF-Token": token})
            await http.put(
                "/api/predictions",
                json={"table": list(reversed(TABLE))},
                headers={"X-CSRF-Token": token},
            )
            body = (await http.get("/api/predictions")).json()

        rows = [p for p in body["predictions"] if p["person"] == "bulba"]
        assert len(rows) == 1
        assert rows[0]["table"] == list(reversed(TABLE))
