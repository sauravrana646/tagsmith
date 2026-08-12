"""`python -m tagsmith.api` — start the Phase 5 API server."""

from __future__ import annotations

import uvicorn

from tagsmith.config import get_settings
from tagsmith.db.session import init_db
from tagsmith.telemetry import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db(settings)
    uvicorn.run(
        "tagsmith.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
