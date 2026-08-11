"""Export human review corrections into golden-set candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from tagsmith.db.models import ClassificationRecord, Message, ReviewStatus
from tagsmith.evals.rebuild import normalized_payload_to_gmail_message


def export_corrections_jsonl(
    session: Session,
    path: Path,
    *,
    only_changed: bool = True,
) -> int:
    """Write JSONL golden-ish rows from reviewed classifications.

    Reconstructs a Gmail-shaped `message` from the normalized SQLite payload when
    present so rows can be merged into `evals/golden_set.jsonl` after spot checks.
    """
    stmt = select(ClassificationRecord).where(col(ClassificationRecord.final_key).is_not(None))
    if only_changed:
        stmt = stmt.where(
            ClassificationRecord.review_status.in_(  # type: ignore[union-attr]
                [ReviewStatus.CHANGED, ReviewStatus.CONFIRMED, ReviewStatus.PROPOSED_NEW]
            )
        )
    records = list(session.exec(stmt).all())
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            message = session.get(Message, record.gmail_id)
            gmail_message: dict[str, Any] = {}
            if message and message.payload_json:
                gmail_message = normalized_payload_to_gmail_message(
                    gmail_id=record.gmail_id,
                    thread_id=message.thread_id,
                    payload=dict(message.payload_json),
                )
            if not gmail_message:
                continue
            row = {
                "id": f"correction_{record.gmail_id}_{record.id}",
                "expected_label_key": record.final_key,
                "notes": (
                    f"from review status={record.review_status}; predicted={record.predicted_key}"
                ),
                "message": gmail_message,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    return written
