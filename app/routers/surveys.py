from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import uuid

from ..database import get_db
from ..models import Survey, Question, AuditLog, User
from ..schemas import SurveyCreate, SurveyUpdate, SurveyOut
from ..security import require_admin_or_manager, require_any

router = APIRouter(prefix="/api/surveys", tags=["surveys"])


def _log(db, user_id, action, resource_id, detail, ip):
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource="survey",
        resource_id=resource_id,
        detail=detail,
        ip_address=ip,
    ))


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _sync_questions(survey: Survey, questions_data: list, db: Session):
    for q in list(survey.questions):
        db.delete(q)
    db.flush()
    for idx, q_data in enumerate(questions_data):
        db.add(Question(
            id=q_data.id if q_data.id else str(uuid.uuid4()),
            survey_id=survey.id,
            type=q_data.type,
            text=q_data.text,
            required=q_data.required,
            options=q_data.options,
            order=idx,
        ))


@router.get("", response_model=list[SurveyOut])
def list_surveys(
    filter_status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any),
):
    q = db.query(Survey)
    if filter_status:
        q = q.filter(Survey.status == filter_status)
    surveys = q.order_by(Survey.created_at.desc()).all()
    return [SurveyOut.from_orm_survey(s) for s in surveys]


@router.post("", response_model=SurveyOut, status_code=status.HTTP_201_CREATED)
def create_survey(
    payload: SurveyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_manager),
):
    survey = Survey(
        id=str(uuid.uuid4()),
        title=payload.title,
        description=payload.description,
        status=payload.status,
        start_date=payload.start_date,
        end_date=payload.end_date,
        created_by=current_user.id,
    )
    db.add(survey)
    db.flush()
    _sync_questions(survey, payload.questions, db)
    _log(db, current_user.id, "CREATE_SURVEY", survey.id, f"Created: {survey.title}", _ip(request))
    db.commit()
    db.refresh(survey)
    return SurveyOut.from_orm_survey(survey)


@router.get("/{survey_id}", response_model=SurveyOut)
def get_survey(survey_id: str, db: Session = Depends(get_db)):
    # Public — no auth required (customers take surveys)
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    return SurveyOut.from_orm_survey(survey)


@router.put("/{survey_id}", response_model=SurveyOut)
def update_survey(
    survey_id: str,
    payload: SurveyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_manager),
):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    if payload.title is not None:
        survey.title = payload.title
    if payload.description is not None:
        survey.description = payload.description
    if payload.status is not None:
        survey.status = payload.status
    if payload.start_date is not None:
        survey.start_date = payload.start_date
    if payload.end_date is not None:
        survey.end_date = payload.end_date
    if payload.questions is not None:
        _sync_questions(survey, payload.questions, db)

    _log(db, current_user.id, "UPDATE_SURVEY", survey.id, f"Updated: {survey.title}", _ip(request))
    db.commit()
    db.refresh(survey)
    return SurveyOut.from_orm_survey(survey)


@router.delete("/{survey_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_survey(
    survey_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_manager),
):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    _log(db, current_user.id, "DELETE_SURVEY", survey_id, f"Deleted: {survey.title}", _ip(request))
    db.delete(survey)
    db.commit()


@router.post("/{survey_id}/duplicate", response_model=SurveyOut, status_code=201)
def duplicate_survey(
    survey_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_manager),
):
    original = db.query(Survey).filter(Survey.id == survey_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Survey not found")

    new_survey = Survey(
        id=str(uuid.uuid4()),
        title=f"{original.title} (Copy)",
        description=original.description,
        status="draft",
        start_date=original.start_date,
        end_date=original.end_date,
        created_by=current_user.id,
    )
    db.add(new_survey)
    db.flush()

    for q in original.questions:
        db.add(Question(
            id=str(uuid.uuid4()),
            survey_id=new_survey.id,
            type=q.type,
            text=q.text,
            required=q.required,
            options=q.options,
            order=q.order,
        ))

    _log(db, current_user.id, "DUPLICATE_SURVEY", new_survey.id, f"Duplicated from: {original.id}", _ip(request))
    db.commit()
    db.refresh(new_survey)
    return SurveyOut.from_orm_survey(new_survey)
