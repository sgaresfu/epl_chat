"""Sessions, code words, rate limiting and CSRF.

One login screen, one field. The code word is compared constant-time against
the environment secret, because a timing-distinguishable comparison on a
four-word keyspace is worth avoiding even here -- four people sharing a link
means treating these as real credentials.

The cookie is the part the brief warns about. The frontend is a static site on
a CDN and the api is a separate Render service, so the two are cross-origin
unless they share a parent domain. Both paths are supported:

* ``COOKIE_DOMAIN=.example.com`` -> ``SameSite=Lax`` and the cookie just works
* no shared parent -> ``SameSite=None; Secure`` plus an explicit CORS allow-list

``SameSite=None`` also requires ``Secure``, which means the fallback cannot work
over plain HTTP; local dev therefore uses ``Lax`` on ``localhost``.
"""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from typing import Any, Final

import structlog
from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from shared.cache import Cache, key
from shared.config import Settings
from shared.timezones import BY_KEY, Place

log = structlog.get_logger(__name__)

SESSION_COOKIE: Final = "pl_session"
CSRF_COOKIE: Final = "pl_csrf"
CSRF_HEADER: Final = "X-CSRF-Token"

LOGIN_ATTEMPT_LIMIT: Final = 10
LOGIN_ATTEMPT_WINDOW: Final = 3600  # one hour, per BRIEF section 3

MAX_STREAMS_PER_PERSON: Final = 4


@dataclass(frozen=True, slots=True)
class Session:
    """The logged-in person, resolved from the cookie on every request."""

    person: str
    issued_at: float

    @property
    def place(self) -> Place:
        return BY_KEY[self.person]


def serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="pl-session")


def cookie_policy(settings: Settings) -> tuple[str, bool, str | None]:
    """Decide SameSite, Secure and Domain for the session cookie.

    Three cases, and the difference between them is the whole cross-origin
    problem from BRIEF section 3:

    * **local** -- same-origin through the Vite proxy, so ``Lax`` over plain
      HTTP. ``Secure`` would stop the cookie being stored at all on ``http://``.
    * **shared parent domain** (``COOKIE_DOMAIN`` set) -- the clean path. The
      cookie is first-party for both hosts, so ``Lax`` works and no third-party
      cookie policy applies.
    * **no shared parent** -- the cookie is third-party, so it needs
      ``SameSite=None``, which browsers only honour together with ``Secure``.

    Returned rather than applied inline so it can be asserted in tests, since
    getting it wrong fails only in a deployed browser.
    """
    if settings.environment == "local":
        return "lax", False, None
    if settings.cookie_domain:
        return "lax", True, settings.cookie_domain
    return "none", True, None


def issue_session(response: Response, person: str, settings: Settings) -> str:
    """Sign a session and set it as an httpOnly cookie."""
    token = serializer(settings).dumps({"person": person, "t": time.time()})
    assert isinstance(token, str)
    same_site_str, secure, domain = cookie_policy(settings)
    same_site: Any = same_site_str

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=secure,
        samesite=same_site,
        domain=domain,
        path="/",
    )
    # Double-submit CSRF token. Readable by JS on purpose -- it is compared
    # against the header the client echoes back, never used as an authenticator.
    csrf = serializer(settings).dumps({"person": person, "csrf": True})
    assert isinstance(csrf, str)
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=settings.session_days * 86400,
        httponly=False,
        secure=secure,
        samesite=same_site,
        domain=domain,
        path="/",
    )
    return token


def clear_session(response: Response, settings: Settings | None = None) -> None:
    # The domain must match the one the cookie was set with, or the browser
    # keeps the original and sign-out silently does nothing.
    domain = cookie_policy(settings)[2] if settings else None
    response.delete_cookie(SESSION_COOKIE, path="/", domain=domain)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=domain)


def read_session(request: Request, settings: Settings) -> Session | None:
    """Resolve the session cookie, or ``None`` if absent, forged or expired."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        data = serializer(settings).loads(raw, max_age=settings.session_days * 86400)
    except SignatureExpired:
        log.info("auth.session_expired")
        return None
    except BadSignature:
        log.warning("auth.bad_signature")
        return None
    person = str(data.get("person", ""))
    if person not in BY_KEY:
        return None
    return Session(person=person, issued_at=float(data.get("t", 0)))


def verify_code(submitted: str, settings: Settings) -> str | None:
    """Constant-time match of a submitted code word against every configured code.

    Every code is checked even after a match so the work done does not depend on
    which person logged in, and an unconfigured environment cannot be probed by
    timing to discover which slots are filled.
    """
    candidate = submitted.strip()
    matched: str | None = None
    for person, code in settings.codes.items():
        if hmac.compare_digest(candidate.encode(), code.encode()) and matched is None:
            matched = person
    return matched


async def check_rate_limit(cache: Cache, ip: str) -> None:
    """10 login attempts per IP per hour (BRIEF section 3)."""
    bucket = key("login", ip, int(time.time() // LOGIN_ATTEMPT_WINDOW))
    entry = await cache.get(bucket)
    count = int(entry.value) if entry else 0
    if count >= LOGIN_ATTEMPT_LIMIT:
        log.warning("auth.rate_limited", ip=ip)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again in an hour.",
        )
    await cache.set(bucket, count + 1, source="auth")


def require_csrf(request: Request) -> None:
    """Double-submit check on every mutating request."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")


def client_ip(request: Request) -> str:
    """Caller IP, honouring Render's proxy header."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
