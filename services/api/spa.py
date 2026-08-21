"""Serve the built React app from the api, same origin.

Mounted last, so every ``/api`` route and the health checks win first. Anything
else falls through to the app shell, because a single-page app owns its own
routing -- a hard refresh on ``/table`` must return the shell, not a 404.

Hashed assets are immutable and cached for a year; ``index.html`` never is, or
a deploy would not reach anybody.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

log = structlog.get_logger(__name__)

STATIC = Path(__file__).parents[2] / "static"

IMMUTABLE = "public, max-age=31536000, immutable"
NO_STORE = "no-cache, no-store, must-revalidate"


class HashedAssets(StaticFiles):
    """Static files under /assets, which Vite fingerprints by content.

    The mount is the assets directory, so `path` arrives relative to it and
    every file here carries a content hash in its name. That makes the whole
    mount safe to cache for a year: a changed file gets a different URL.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = IMMUTABLE
        return response


def mount(app: FastAPI) -> bool:
    """Attach the frontend if it was built into the image. Returns whether it was."""
    if not STATIC.is_dir() or not (STATIC / "index.html").is_file():
        log.info("spa.not_bundled", path=str(STATIC))
        return False

    app.mount("/assets", HashedAssets(directory=STATIC / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def shell(request: Request, full_path: str) -> Response:
        # An unmatched /api path is a missing endpoint, not a page. Returning
        # the shell there would hand JSON callers a lump of HTML and turn a
        # clear 404 into a parse error.
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)

        candidate = (STATIC / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(STATIC.resolve()):
            return FileResponse(candidate, headers={"Cache-Control": NO_STORE})

        return FileResponse(STATIC / "index.html", headers={"Cache-Control": NO_STORE})

    log.info("spa.mounted", path=str(STATIC))
    return True
