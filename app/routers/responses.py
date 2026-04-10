from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import hashlib
import uuid

from ..database import get_db
from ..models import Response, Survey, SurveyDistribution, AuditLog
from ..schemas import ResponseCreate, ResponseOut
from ..security import require_any

router = APIRouter(prefix="/api/responses", tags=["responses"])


def _build_fingerprint(request: Request, survey_id: str) -> str:
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    raw = f"{survey_id}:{ip}:{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("", response_model=ResponseOut, status_code=status.HTTP_201_CREATED)
def submit_response(payload: ResponseCreate, request: Request, db: Session = Depends(get_db)):
    survey = db.query(Survey).filter(Survey.id == payload.surveyId).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    # Enforce published status
    if survey.status != "published":
        raise HTTPException(status_code=403, detail="Survey is not accepting responses")

    # Enforce scheduling window
    now = datetime.now(timezone.utc)
    if survey.start_date and now < survey.start_date:
        raise HTTPException(status_code=403, detail="Survey has not started yet")
    if survey.end_date and now > survey.end_date:
        raise HTTPException(status_code=403, detail="Survey has closed")

    # Duplicate submission check
    fingerprint = _build_fingerprint(request, payload.surveyId)
    existing = db.query(Response).filter(
        Response.survey_id == payload.surveyId,
        Response.submission_fingerprint == fingerprint,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="You have already submitted a response to this survey")

    response = Response(
        id=str(uuid.uuid4()),
        survey_id=payload.surveyId,
        answers=payload.answers,
        submission_fingerprint=fingerprint,
        is_complete=payload.is_complete,
    )
    db.add(response)

    # Mark distribution record as responded if email is provided
    if payload.respondent_email:
        dist = db.query(SurveyDistribution).filter(
            SurveyDistribution.survey_id == payload.surveyId,
            SurveyDistribution.email == payload.respondent_email,
        ).first()
        if dist:
            dist.has_responded = True

    db.add(AuditLog(
        id=str(uuid.uuid4()),
        user_id=None,
        action="SUBMIT_RESPONSE",
        resource="response",
        resource_id=response.id,
        detail=f"Response submitted for survey: {payload.surveyId}",
        ip_address=request.client.host if request.client else "unknown",
    ))

    db.commit()
    db.refresh(response)
    return ResponseOut.from_orm_response(response)


@router.get("", response_model=list[ResponseOut])
def list_responses(
    survey_id: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_any),
):
    query = db.query(Response)
    if survey_id:
        query = query.filter(Response.survey_id == survey_id)
    responses = query.order_by(Response.submitted_at.desc()).all()
    return [ResponseOut.from_orm_response(r) for r in responses]
