"""Taxonomy API for the dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from tagsmith.api.deps import session_dep, settings_dep
from tagsmith.config import Settings
from tagsmith.taxonomy.registry import TaxonomyRegistry

router = APIRouter(prefix="/api/taxonomy", tags=["taxonomy"])


@router.get("/labels")
def list_labels(
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> list[dict[str, Any]]:
    registry = TaxonomyRegistry(session, settings)
    registry.ensure_seeded()
    out: list[dict[str, Any]] = []
    for cat in registry.list_active():
        out.append(
            {
                "key": cat.key,
                "description": cat.description,
                "gmail_label": settings.gmail_label_name(cat.key),
                "gmail_label_id": cat.gmail_label_id,
            }
        )
    return out
