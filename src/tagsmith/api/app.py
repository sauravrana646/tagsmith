"""FastAPI application factory (Phase 5)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tagsmith import __version__
from tagsmith.api.routes import billing, health, oauth, review, sync
from tagsmith.config import get_settings
from tagsmith.db.session import init_db
from tagsmith.telemetry import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db(settings)

    app = FastAPI(
        title="Tagsmith API",
        version=__version__,
        description="Phase 5 product API wrapping the Tagsmith service layer.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            settings.api_public_base_url,
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(oauth.router)
    app.include_router(review.router)
    app.include_router(sync.router)
    app.include_router(billing.router)

    web_dist = Path(__file__).resolve().parents[3] / "web" / "out"
    if web_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=web_dist / "_next"), name="assets")

        @app.get("/")
        async def dashboard_index() -> FileResponse:
            return FileResponse(web_dist / "index.html")

    @app.middleware("http")
    async def attach_tenant_cookie(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.tenant_id = request.cookies.get("tagsmith_tenant")
        return await call_next(request)

    return app


app = create_app()
