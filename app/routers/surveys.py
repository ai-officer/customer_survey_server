from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from ..database import get_db
from ..models import Survey, Question, User, UserRole
from ..schemas import SurveyCreate, SurveyUpdate, SurveyOut, PublicSurveyOut
from ..security import require_admin_or_manager, require_any, decode_token
from ..utils.audit import get_client_ip, record_audit
from ..utils.authorization import ensure_owner_or_admin

router = APIRouter(prefix="/api/surveys", tags=["surveys"])


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
    # Managers see only their own surveys; admins see all.
    if current_user.role != UserRole.admin:
        q = q.filter(Survey.created_by == current_user.id)
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
        department_id=payload.department_id,
        customer=payload.customer,
        created_by=current_user.id,
    )
    db.add(survey)
    db.flush()
    _sync_questions(survey, payload.questions, db)
    record_audit(
        db,
        user_id=current_user.id,
        action="CREATE_SURVEY",
        resource="survey",
        resource_id=survey.id,
        detail=f"Created: {survey.title}",
        ip=get_client_ip(request),
    )
    db.commit()
    db.refresh(survey)
    return SurveyOut.from_orm_survey(survey)


def _try_current_user(request: Request, db: Session) -> Optional[User]:
    """Decode bearer token if present; return User or None. Never raises."""
    auth = request.headers.get("authorization", "")
    scheme, token = get_authorization_scheme_param(auth)
    if not token or scheme.lower() != "bearer":
        return None
    try:
        payload = decode_token(token)
    except HTTPException:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


@router.get("/{survey_id}")
def get_survey(survey_id: str, request: Request, db: Session = Depends(get_db)):
    """Public endpoint — customers use it to fill out surveys.
    Authenticated admins/managers (or the owner) receive full metadata; public
    visitors see a stripped-down view."""
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    user = _try_current_user(request, db)
    if user and (user.role == UserRole.admin or survey.created_by == user.id):
        return SurveyOut.from_orm_survey(survey)
    return PublicSurveyOut.from_orm_survey(survey)


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

    ensure_owner_or_admin(
        current_user,
        survey.created_by,
        message="You can only edit surveys you created",
    )

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
    if payload.department_id is not None:
        survey.department_id = payload.department_id or None
    if payload.customer is not None:
        survey.customer = payload.customer or None
    if payload.questions is not None:
        _sync_questions(survey, payload.questions, db)

    record_audit(
        db,
        user_id=current_user.id,
        action="UPDATE_SURVEY",
        resource="survey",
        resource_id=survey.id,
        detail=f"Updated: {survey.title}",
        ip=get_client_ip(request),
    )
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
    ensure_owner_or_admin(
        current_user,
        survey.created_by,
        message="You can only delete surveys you created",
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="DELETE_SURVEY",
        resource="survey",
        resource_id=survey_id,
        detail=f"Deleted: {survey.title}",
        ip=get_client_ip(request),
    )
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

    record_audit(
        db,
        user_id=current_user.id,
        action="DUPLICATE_SURVEY",
        resource="survey",
        resource_id=new_survey.id,
        detail=f"Duplicated from: {original.id}",
        ip=get_client_ip(request),
    )
    db.commit()
    db.refresh(new_survey)
    return SurveyOut.from_orm_survey(new_survey)
