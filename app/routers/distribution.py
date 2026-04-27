from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List
import uuid

from ..database import get_db
from ..models import Survey, SurveyDistribution, User
from ..security import require_admin_or_manager
from ..email import send_survey_invites_batch, send_survey_reminders_batch
from ..utils.audit import get_client_ip, record_audit

router = APIRouter(prefix="/api/surveys", tags=["distribution"])


class DistributePayload(BaseModel):
    emails: List[str]


@router.post("/{survey_id}/distribute")
def distribute(
    survey_id: str,
    payload: DistributePayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_manager),
):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    if survey.status != "published":
        raise HTTPException(
            status_code=400,
            detail="Survey must be published before distributing",
        )

    # Normalize + de-dupe
    incoming = list({e.strip().lower() for e in payload.emails if e.strip()})
    if not incoming:
        raise HTTPException(status_code=400, detail="No valid emails provided")

    # Skip anyone already distributed for this survey
    existing_emails = {
        row[0] for row in db.query(SurveyDistribution.email)
        .filter(SurveyDistribution.survey_id == survey_id).all()
    }
    new_emails = [e for e in incoming if e not in existing_emails]

    # Record distributions first — audit trail survives send failures
    now = datetime.now(timezone.utc)
    for email in new_emails:
        db.add(SurveyDistribution(
            id=str(uuid.uuid4()),
            survey_id=survey_id,
            email=email,
            sent_at=now,
        ))
    record_audit(
        db,
        user_id=current_user.id,
        action="DISTRIBUTE_SURVEY",
        resource="survey",
        resource_id=survey.id,
        detail=(
            f"Distributed to {len(new_emails)} new recipients "
            f"({len(incoming) - len(new_emails)} already invited)"
        ),
        ip=get_client_ip(request),
    )
    db.commit()

    # Send via Resend — synchronous batched call, reliable on Vercel serverless
    result = send_survey_invites_batch(
        recipients=new_emails,
        survey_id=survey.id,
        survey_title=survey.title,
        sender_name=current_user.full_name,
        sender_email=current_user.email,
    )

    return {
        "requested":        len(incoming),
        "already_invited":  len(incoming) - len(new_emails),
        "sent":             result["sent"],
        "failed":           result["failed"],
        "message":          f"Sent {result['sent']} invite(s)",
    }


@router.post("/{survey_id}/remind")
def remind(
    survey_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_manager),
):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    pending = db.query(SurveyDistribution).filter(
        SurveyDistribution.survey_id == survey_id,
        SurveyDistribution.has_responded == False,
    ).all()

    if not pending:
        return {"message": "No non-responders to remind", "sent": 0}

    now = datetime.now(timezone.utc)
    for d in pending:
        d.reminder_sent_at = now
    record_audit(
        db,
        user_id=current_user.id,
        action="REMIND_NON_RESPONDENTS",
        resource="survey",
        resource_id=survey.id,
        detail=f"Sent reminders to {len(pending)} non-responders",
        ip=get_client_ip(request),
    )
    db.commit()

    result = send_survey_reminders_batch(
        recipients=[d.email for d in pending],
        survey_id=survey.id,
        survey_title=survey.title,
        sender_name=current_user.full_name,
        sender_email=current_user.email,
    )

    return {
        "sent":    result["sent"],
        "failed":  result["failed"],
        "message": f"Reminded {result['sent']} recipient(s)",
    }
