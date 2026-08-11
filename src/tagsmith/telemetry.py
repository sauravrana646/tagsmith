"""Structured logging + optional Logfire/OpenTelemetry tracing."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

_observability_configured = False


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)


def configure_observability(
    *,
    enabled: bool = False,
    send_to_logfire: str | bool = "if-token-present",
    service_name: str = "tagsmith",
) -> bool:
    """Optionally configure Logfire + instrument Pydantic AI.

    Returns True when Logfire was configured successfully.
    Safe no-op when disabled or when the optional `logfire` package is missing.
    """
    global _observability_configured
    if not enabled:
        return False
    if _observability_configured:
        return True
    try:
        import logfire
    except ImportError:
        get_logger(__name__).warning(
            "observability.skipped",
            reason="logfire package not installed (pip/uv add logfire)",
        )
        return False

    logfire.configure(
        service_name=service_name,
        send_to_logfire=send_to_logfire,  # type: ignore[arg-type]
    )
    try:
        logfire.instrument_pydantic_ai()
    except Exception as exc:  # pragma: no cover - defensive
        get_logger(__name__).warning("observability.instrument_failed", error=str(exc))
    _observability_configured = True
    get_logger(__name__).info("observability.configured", backend="logfire")
    return True


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """Open a Logfire/OTel span when available; otherwise no-op."""
    if not _observability_configured:
        yield
        return
    try:
        import logfire
    except ImportError:
        yield
        return
    with logfire.span(name, **attributes):
        yield
