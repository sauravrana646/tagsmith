"""FastAPI application factory (Phase 5)."""

from __future__ import annotations

import html
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from tagsmith import __version__
from tagsmith.api.deps import allowed_origins, safe_web_app_url
from tagsmith.api.routes import billing, health, oauth, review, status, sync, taxonomy
from tagsmith.background import start_background_loop, stop_background_loop
from tagsmith.config import get_settings
from tagsmith.db.session import init_db
from tagsmith.telemetry import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    task = start_background_loop(settings)
    try:
        yield
    finally:
        await stop_background_loop(task)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db(settings)

    docs_url = "/docs" if settings.enable_api_docs else None
    redoc_url = "/redoc" if settings.enable_api_docs else None
    openapi_url = "/openapi.json" if settings.enable_api_docs else None

    app = FastAPI(
        title="Tagsmith API",
        version=__version__,
        description="Phase 5 product API wrapping the Tagsmith service layer.",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    origins = sorted(allowed_origins(settings))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(status.router)
    app.include_router(oauth.router)
    app.include_router(review.router)
    app.include_router(sync.router)
    app.include_router(taxonomy.router)
    app.include_router(billing.router)

    web_dist = Path(__file__).resolve().parents[3] / "web" / "out"
    dashboard = safe_web_app_url(settings)
    if web_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=web_dist / "_next"), name="assets")

        @app.get("/")
        async def dashboard_index() -> FileResponse:
            return FileResponse(web_dist / "index.html")
    else:

        @app.get("/")
        async def api_root() -> HTMLResponse:
            safe_dash = html.escape(dashboard)
            docs_line = (
                '<p>Docs: <a href="/docs">/docs</a> · Health: <a href="/health">/health</a></p>'
                if settings.enable_api_docs
                else '<p>Health: <a href="/health">/health</a></p>'
            )
            return HTMLResponse(
                f"""<!doctype html>
<html><body style="font-family:system-ui;padding:2rem;max-width:40rem">
  <h1>Tagsmith API</h1>
  <p>OAuth succeeded. The UI runs on the Next.js app, not this port.</p>
  <p><a href="{safe_dash}/?auth=ok">Open dashboard → {safe_dash}</a></p>
  {docs_line}
</body></html>"""
            )

        @app.get("/go")
        async def go_dashboard() -> RedirectResponse:
            return RedirectResponse(dashboard + "/?auth=ok")

    @app.middleware("http")
    async def attach_tenant_cookie(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.tenant_id = request.cookies.get("tagsmith_tenant")
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.url.path.startswith("/api/")
            and origin
            and origin.rstrip("/") not in allowed_origins(settings)
        ):
            return JSONResponse({"detail": "invalid origin"}, status_code=403)
        return await call_next(request)

    return app


app = create_app()
