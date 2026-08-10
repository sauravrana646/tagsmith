"""Category CRUD and local <-> Gmail label reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import TYPE_CHECKING, Any

import yaml
from sqlmodel import Session, select

from tagsmith.config import Settings
from tagsmith.db.models import Category, CategoryStatus
from tagsmith.telemetry import get_logger

if TYPE_CHECKING:
    from tagsmith.gmail.client import GmailClient

log = get_logger(__name__)


@dataclass(slots=True)
class SeedCategory:
    key: str
    description: str
    exemplars: list[str]


def load_seed_categories() -> list[SeedCategory]:
    seed_text = (
        resources.files("tagsmith.taxonomy").joinpath("seed.yaml").read_text(encoding="utf-8")
    )
    data = yaml.safe_load(seed_text) or {}
    items = data.get("categories") or []
    return [
        SeedCategory(
            key=str(item["key"]),
            description=str(item["description"]).strip(),
            exemplars=[str(x) for x in (item.get("exemplars") or [])],
        )
        for item in items
    ]


class TaxonomyRegistry:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def ensure_seeded(self) -> int:
        created = 0
        for seed in load_seed_categories():
            existing = self.session.get(Category, seed.key)
            if existing is None:
                self.session.add(
                    Category(
                        key=seed.key,
                        description=seed.description,
                        exemplars=seed.exemplars,
                        status=CategoryStatus.ACTIVE,
                    )
                )
                created += 1
            else:
                # Keep descriptions/exemplars fresh from seed for active built-ins.
                if existing.status == CategoryStatus.ACTIVE:
                    existing.description = seed.description
                    existing.exemplars = seed.exemplars
        self.session.commit()
        return created

    def list_active(self) -> list[Category]:
        stmt = select(Category).where(Category.status == CategoryStatus.ACTIVE).order_by(
            Category.key
        )
        return list(self.session.exec(stmt).all())

    def get(self, key: str) -> Category | None:
        return self.session.get(Category, key)

    def active_keys(self) -> list[str]:
        return [c.key for c in self.list_active()]

    def activate_category(
        self,
        key: str,
        description: str,
        *,
        exemplars: list[str] | None = None,
        gmail_label_id: str | None = None,
    ) -> Category:
        cat = self.session.get(Category, key)
        if cat is None:
            cat = Category(
                key=key,
                description=description,
                exemplars=exemplars or [],
                status=CategoryStatus.ACTIVE,
                gmail_label_id=gmail_label_id,
            )
            self.session.add(cat)
        else:
            cat.description = description
            if exemplars is not None:
                cat.exemplars = exemplars
            cat.status = CategoryStatus.ACTIVE
            if gmail_label_id is not None:
                cat.gmail_label_id = gmail_label_id
        self.session.commit()
        self.session.refresh(cat)
        return cat

    def mark_rejected(self, key: str) -> None:
        cat = self.session.get(Category, key)
        if cat is None:
            cat = Category(
                key=key,
                description="",
                exemplars=[],
                status=CategoryStatus.REJECTED,
            )
            self.session.add(cat)
        else:
            cat.status = CategoryStatus.REJECTED
        self.session.commit()

    def reconcile_gmail_labels(self, gmail: GmailClient) -> dict[str, Any]:
        """Ensure parent + needs-review + active category labels exist; store ids."""
        labels = {label.get("name"): label for label in gmail.list_labels()}
        parent = self.settings.label_parent
        if parent not in labels:
            # Gmail creates parent path when nested label is created; create needs-review.
            pass

        needs_name = self.settings.needs_review_label_name
        needs = gmail.get_or_create_label(needs_name)
        updated = 0
        for category in self.list_active():
            name = self.settings.gmail_label_name(category.key)
            label = gmail.get_or_create_label(name)
            label_id = str(label.get("id") or "")
            if category.gmail_label_id != label_id:
                category.gmail_label_id = label_id
                updated += 1
        self.session.commit()
        return {
            "needs_review_label_id": needs.get("id"),
            "categories_updated": updated,
            "active_categories": len(self.list_active()),
        }

    def prompt_catalog(self) -> str:
        lines: list[str] = []
        for cat in self.list_active():
            exemplars = "; ".join(f'"{e}"' for e in cat.exemplars[:3])
            lines.append(f"- {cat.key}: {cat.description}")
            if exemplars:
                lines.append(f"  exemplars: {exemplars}")
        return "\n".join(lines)
