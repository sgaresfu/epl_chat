"""Cookie policy tests.

BRIEF section 3 calls the cookie "the one thing that will bite you", and it
bites only in a deployed browser -- a wrong SameSite silently drops the session
on the real site while every local test passes. These assert the decision
directly.
"""

from __future__ import annotations

from services.api.auth import cookie_policy
from shared.config import Settings


def settings(**kw: object) -> Settings:
    base: dict[str, object] = {
        "session_secret": "test-secret-long-enough-for-signing-abcdefghijk",
    }
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


class TestLocal:
    def test_local_uses_lax_over_plain_http(self) -> None:
        same_site, _secure, domain = cookie_policy(settings(environment="local"))
        assert same_site == "lax"
        assert domain is None

    def test_local_does_not_set_secure(self) -> None:
        # Secure on http:// means the browser refuses to store the cookie, so
        # local dev would never log in.
        _, secure, _ = cookie_policy(settings(environment="local"))
        assert secure is False


class TestApiServesTheFrontend:
    """The default, and the only arrangement iOS keeps a session in."""

    def test_same_origin_uses_lax(self) -> None:
        same_site, _, _ = cookie_policy(settings(environment="production", serve_frontend=True))
        assert same_site == "lax"

    def test_it_is_secure_and_host_only(self) -> None:
        _, secure, domain = cookie_policy(settings(environment="production", serve_frontend=True))
        assert secure is True
        assert domain is None

    def test_it_never_falls_back_to_samesite_none(self) -> None:
        # SameSite=None is what WebKit drops; serving same-origin must not
        # reach that branch even with no COOKIE_DOMAIN set.
        same_site, _, _ = cookie_policy(
            settings(environment="production", serve_frontend=True, cookie_domain="")
        )
        assert same_site != "none"


class TestSharedParentDomain:
    """The clean path: league.example.com and api.example.com."""

    def test_a_shared_parent_uses_lax(self) -> None:
        same_site, _, _ = cookie_policy(settings(environment="production", cookie_domain=".example.com"))
        assert same_site == "lax"

    def test_the_cookie_is_scoped_to_the_parent_domain(self) -> None:
        _, _, domain = cookie_policy(
            settings(environment="production", serve_frontend=False, cookie_domain=".example.com")
        )
        assert domain == ".example.com"

    def test_it_is_still_secure(self) -> None:
        _, secure, _ = cookie_policy(settings(environment="production", cookie_domain=".example.com"))
        assert secure is True


class TestNoSharedParent:
    """The fallback: a CDN origin and a Render origin with nothing in common."""

    def test_it_falls_back_to_samesite_none(self) -> None:
        same_site, _, _ = cookie_policy(settings(environment="production", serve_frontend=False))
        assert same_site == "none"

    def test_samesite_none_is_always_paired_with_secure(self) -> None:
        # Browsers reject SameSite=None without Secure outright.
        same_site, secure, _ = cookie_policy(settings(environment="production", serve_frontend=False))
        assert same_site == "none"
        assert secure is True

    def test_no_domain_is_set_when_there_is_no_shared_parent(self) -> None:
        _, _, domain = cookie_policy(settings(environment="production", serve_frontend=False))
        assert domain is None


class TestCors:
    def test_the_allow_list_is_explicit_never_a_wildcard(self) -> None:
        # A wildcard is rejected by browsers when credentials are sent, and
        # EventSource needs credentials.
        config = settings(frontend_origin="https://league.example.com")
        assert config.cors_origins == ["https://league.example.com"]
        assert "*" not in config.cors_origins

    def test_several_origins_can_be_allowed(self) -> None:
        config = settings(frontend_origin="https://league.example.com, https://preview.example.com")
        assert config.cors_origins == [
            "https://league.example.com",
            "https://preview.example.com",
        ]
