"""Configuration, loaded from the environment.

Every secret in BRIEF section 4 appears here exactly once, with a default only
where a default is safe. A missing upstream key is deliberately *not* fatal:
the brief requires that the panel it powers degrades to a clear message while
the rest of the site keeps working, so the clients check
:meth:`Settings.has` and report a reason rather than raising at import time.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration shared by the api, poller and scheduler."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"

    # --- storage -----------------------------------------------------------
    # SQLite keeps a clean clone runnable with no services; Render supplies a
    # Postgres URL in every deployed environment.
    database_url: str = "sqlite+aiosqlite:///./league.db"
    redis_url: str = "redis://localhost:6379/0"

    # --- auth --------------------------------------------------------------
    session_secret: str = "dev-only-secret-change-me-in-every-real-environment"
    session_days: int = 90
    code_coyg: str = ""
    code_aure: str = ""
    code_twzt: str = ""
    code_bulba: str = ""

    # --- upstreams ---------------------------------------------------------
    football_data_key: str = ""
    api_football_key: str = ""
    odds_api_key: str = ""
    youtube_api_key: str = ""

    # --- push and storage --------------------------------------------------
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    r2_account_id: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = ""

    sentry_dsn: str = ""
    frontend_origin: str = "http://localhost:5173"
    # Set to ".example.com" when the web and api services share a parent domain:
    # the session cookie is then first-party and SameSite=Lax works. Leave empty
    # when they do not, and the cookie falls back to SameSite=None; Secure.
    cookie_domain: str = ""

    # --- quota budgets (see BRIEF section 4, "Quota discipline") -----------
    # The brief's stated intervals overrun both free tiers, so the ceilings are
    # enforced here rather than assumed. See docs/quotas.md for the arithmetic.
    odds_monthly_budget: int = 450  # of 500, leaving headroom
    api_football_daily_budget: int = 85  # of 100, leaving headroom

    # Local convenience only: one poll at start-up so a clean clone shows real
    # data without running a second process.
    seed_on_start: bool = False

    # Run the poller inside the api process instead of as a separate worker.
    #
    # The brief splits them, and for an app with real traffic that is right: a
    # slow upstream must not sit on a user's critical path, and many browsers
    # must not become many times the upstream calls. Neither applies at four
    # users on one instance -- asyncio keeps a slow FPL response off every other
    # request anyway, and one poll still serves all four people. What the split
    # does cost here is a $7 worker plus $10 of Redis purely to let two
    # processes share a cache.
    #
    # So this collapses them by default. Set it false and run
    # `python -m services.poller.main` separately to restore the split
    # architecture unchanged.
    poller_in_process: bool = True

    fpl_league_id: int = 412955
    season: str = "2026-27"
    prediction_lock: str = "2026-08-21T19:00:00Z"

    @staticmethod
    def _swap_ssl_param(url: str, *, to: str) -> str:
        """Rename the SSL query parameter between the two drivers' spellings.

        Hosted Postgres almost always hands out ``?sslmode=require``, which is
        libpq's spelling and what psycopg expects. asyncpg has never accepted it
        and fails with ``connect() got an unexpected keyword argument
        'sslmode'`` -- a message that reads like a library bug rather than a URL
        that needs one word changed.

        ``to`` is ``"ssl"`` for the async driver and ``"sslmode"`` for the sync
        one, so a URL written either way works with both.
        """
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(url)
        if not parts.query:
            return url

        other = "sslmode" if to == "ssl" else "ssl"
        params = [(other if k == to else k, v) for k, v in parse_qsl(parts.query)]
        params = [(to if k in ("ssl", "sslmode") else k, v) for k, v in params]
        return urlunsplit(parts._replace(query=urlencode(params)))

    @property
    def async_database_url(self) -> str:
        """The database URL with an async driver, whatever form it arrived in.

        Render's Postgres ``connectionString`` is a bare ``postgresql://…`` with
        no driver, which SQLAlchemy resolves to psycopg2 -- a *sync* driver that
        an async engine cannot use and that is not installed. The failure is
        ``ModuleNotFoundError: psycopg2``, which points at a missing package
        rather than at the scheme, so it is worth normalising here rather than
        debugging at 3am on a first deploy.
        """
        url = self.database_url
        if url.startswith("postgres://"):  # the older Heroku-style prefix
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite://") and "+aiosqlite" not in url:
            url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        if "asyncpg" in url:
            url = self._swap_ssl_param(url, to="ssl")
        return url

    @property
    def sync_database_url(self) -> str:
        """The same database, with a synchronous driver, for Alembic."""
        url = self.async_database_url.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")
        if "psycopg" in url:
            url = self._swap_ssl_param(url, to="sslmode")
        return url

    @property
    def codes(self) -> dict[str, str]:
        """Code word per person key, excluding any that are unset."""
        raw = {
            "coyg": self.code_coyg,
            "aure": self.code_aure,
            "twzt": self.code_twzt,
            "bulba": self.code_bulba,
        }
        return {k: v for k, v in raw.items() if v}

    @property
    def cors_origins(self) -> list[str]:
        """Explicit allow-list. Never ``*`` -- browsers reject that with credentials.

        Render's blueprint can only supply a service's *host* (``x.onrender.com``),
        not a full origin, so a bare host is normalised to ``https://`` here.
        A CORS entry without a scheme never matches, and the failure looks like
        a mysterious login loop rather than a configuration error.
        """
        origins: list[str] = []
        for raw in self.frontend_origin.split(","):
            value = raw.strip().rstrip("/")
            if not value:
                continue
            if not value.startswith(("http://", "https://")):
                value = f"https://{value}"
            origins.append(value)
        return origins

    def has(self, key: str) -> bool:
        """Whether an optional upstream credential is configured."""
        return bool(getattr(self, key, ""))


class ConfigurationError(RuntimeError):
    """A deployment is misconfigured in a way that cannot be recovered from."""


def validate_for_deployment(settings: Settings) -> None:
    """Refuse to start a deployed service that would lose its data.

    ``database_url`` defaults to SQLite so a clean clone runs with no setup. In
    a container that default is a trap: the file lives on ephemeral storage and
    disappears on every restart, and the async driver for it is not installed in
    the production image -- so the failure surfaces as
    ``ModuleNotFoundError: aiosqlite``, which says nothing whatsoever about the
    actual problem, which is a missing DATABASE_URL.

    Worse, Alembic runs before the app and *succeeds* against that throwaway
    file, so the deploy looks half-healthy on the way down.

    Failing here turns all of that into one sentence naming the variable.
    """
    if settings.environment == "local":
        return

    problems: list[str] = []

    if "sqlite" in settings.database_url:
        problems.append(
            "DATABASE_URL is unset, so it fell back to SQLite on ephemeral disk. "
            "Set it to a Postgres connection string — Render's own free tier is "
            "deleted after 30 days, so use Neon or Supabase."
        )

    if not settings.codes:
        problems.append(
            "No code words are set. Set at least one of CODE_COYG, CODE_AURE, "
            "CODE_TWZT, CODE_BULBA or nobody can sign in."
        )

    if len(settings.session_secret) < 32 or "dev-only" in settings.session_secret:
        problems.append(
            "SESSION_SECRET is missing or is the development placeholder. "
            "Generate one with: openssl rand -hex 32"
        )

    if problems:
        raise ConfigurationError(f"Cannot start in {settings.environment}:\n  - " + "\n  - ".join(problems))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


MISSING_KEY_MESSAGES: dict[str, str] = {
    "football_data_key": "Champions League data needs FOOTBALL_DATA_KEY.",
    "api_football_key": "Line-ups need API_FOOTBALL_KEY.",
    "odds_api_key": "bet365 prices need ODDS_API_KEY.",
    "youtube_api_key": "Video uploads need YOUTUBE_API_KEY.",
}
