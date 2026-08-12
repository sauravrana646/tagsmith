"""Review queue API (Phase 5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from tagsmith.api.deps import gmail_dep, session_dep, settings_dep
from tagsmith.config import Settings
from tagsmith.gmail.client import GmailClient
from tagsmith.gmail.fake import FakeGmail
from tagsmith.services.review_ops import ReviewOps

router = APIRouter(prefix="/api/review", tags=["review"])


class AssignBody(BaseModel):
    label_key: str
    apply: bool = True


class ProposeBody(BaseModel):
    suggested_key: str
    description: str
    why: str = ""
    apply: bool = True


class ApproveBody(BaseModel):
    apply: bool = True
    key_override: str | None = None
    description_override: str | None = None


class ConfirmBody(BaseModel):
    apply: bool = True


class ChangeBody(BaseModel):
    label_key: str = Field(min_length=1)
    apply: bool = True


def _ops_readonly(
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> ReviewOps:
    return ReviewOps(session, FakeGmail(), settings)


def _ops(
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
    gmail: GmailClient = Depends(gmail_dep),
) -> ReviewOps:
    return ReviewOps(session, gmail, settings)


def _body_excerpt(payload: dict[str, Any] | None, limit: int = 280) -> str:
    if not payload:
        return ""
    text = str(payload.get("body_text") or payload.get("snippet") or "")
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


@router.get("/summary")
def review_summary(ops: ReviewOps = Depends(_ops_readonly)) -> dict[str, int]:
    return {
        "proposals": len(ops.list_proposals()),
        "needs_review": len(ops.list_needs_review()),
        "held": len(ops.list_held()),
    }


@router.get("/proposals")
def list_proposals(ops: ReviewOps = Depends(_ops_readonly)) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for view in ops.list_proposals():
        msg = view.message
        out.append(
            {
                "id": view.proposal.id,
                "gmail_id": view.proposal.gmail_id,
                "suggested_key": view.proposal.suggested_key,
                "description": view.proposal.description,
                "rationale": view.proposal.rationale,
                "why_no_existing_fit": view.proposal.why_no_existing_fit,
                "subject": msg.subject if msg else "",
                "sender": msg.sender if msg else "",
                "body_excerpt": _body_excerpt(dict(msg.payload_json) if msg else None),
            }
        )
    return out


@router.get("/held")
def list_held(ops: ReviewOps = Depends(_ops_readonly)) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message, record in ops.list_held():
        out.append(
            {
                "gmail_id": message.gmail_id,
                "subject": message.subject,
                "sender": message.sender,
                "predicted_key": record.predicted_key if record else None,
                "proposed_key": record.proposed_key if record else None,
                "proposed_description": record.proposed_description if record else None,
                "rationale": record.rationale if record else "",
                "body_excerpt": _body_excerpt(dict(message.payload_json)),
            }
        )
    return out


@router.get("/needs-review")
def list_needs_review(ops: ReviewOps = Depends(_ops_readonly)) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message, record in ops.list_needs_review():
        out.append(
            {
                "gmail_id": message.gmail_id,
                "subject": message.subject,
                "sender": message.sender,
                "predicted_key": record.predicted_key,
                "confidence": record.confidence,
                "rationale": record.rationale,
                "body_excerpt": _body_excerpt(dict(message.payload_json)),
            }
        )
    return out


@router.post("/held/{gmail_id}/assign")
def assign_held(
    gmail_id: str,
    body: AssignBody,
    ops: ReviewOps = Depends(_ops),
) -> dict[str, Any]:
    try:
        record = ops.resolve_held_with_existing(gmail_id, body.label_key, apply=body.apply)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"gmail_id": gmail_id, "label_key": record.label_key, "applied": body.apply}


@router.post("/held/{gmail_id}/propose")
def propose_held(
    gmail_id: str,
    body: ProposeBody,
    ops: ReviewOps = Depends(_ops),
) -> dict[str, Any]:
    try:
        record = ops.resolve_held_with_new(
            gmail_id,
            suggested_key=body.suggested_key,
            description=body.description,
            why=body.why or body.description,
            apply=body.apply,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"gmail_id": gmail_id, "label_key": record.label_key, "applied": body.apply}


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: int,
    body: ApproveBody,
    ops: ReviewOps = Depends(_ops),
) -> dict[str, Any]:
    try:
        result = await ops.approve_proposal(
            proposal_id,
            apply=body.apply,
            key_override=body.key_override,
            description_override=body.description_override,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "proposal_id": proposal_id,
        "applied": body.apply,
        "reclassify_counts": result.counts.as_dict(),
    }


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: int,
    ops: ReviewOps = Depends(_ops_readonly),
) -> dict[str, Any]:
    try:
        proposal = ops.reject_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"proposal_id": proposal.id, "status": proposal.status.value}


@router.post("/proposals/{proposal_id}/assign")
def assign_proposal_existing(
    proposal_id: int,
    body: AssignBody,
    ops: ReviewOps = Depends(_ops),
) -> dict[str, Any]:
    try:
        record = ops.assign_existing_label(proposal_id, body.label_key, apply=body.apply)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "proposal_id": proposal_id,
        "label_key": record.label_key,
        "applied": body.apply,
    }


@router.post("/needs-review/{gmail_id}/confirm")
def confirm_needs_review(
    gmail_id: str,
    body: ConfirmBody,
    ops: ReviewOps = Depends(_ops),
) -> dict[str, Any]:
    try:
        ops.confirm_label(gmail_id, apply=body.apply)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"gmail_id": gmail_id, "action": "confirm", "applied": body.apply}


@router.post("/needs-review/{gmail_id}/change")
def change_needs_review(
    gmail_id: str,
    body: ChangeBody,
    ops: ReviewOps = Depends(_ops),
) -> dict[str, Any]:
    try:
        ops.change_label(gmail_id, body.label_key, apply=body.apply)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"gmail_id": gmail_id, "label_key": body.label_key, "applied": body.apply}
