import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
import os

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..models import Survey, SurveyDistribution, AuditLog, User
from ..security import require_admin_or_manager

router = APIRouter(prefix="/api/surveys", tags=["distribution"])

APP_URL = os.getenv("APP_URL", "http://localhost:3000")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)


class DistributeRequest(BaseModel):
    emails: list[str]


def _send_email(to_email: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, to_email, msg.as_string())


def _survey_email_html(survey_title: str, survey_url: str, is_reminder: bool = False) -> str:
    intro = "This is a reminder" if is_reminder else "You are invited"
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <h2 style="color:#4f46e5;">{'Reminder: ' if is_reminder else ''}{survey_title}</h2>
      <p>{intro} to complete our customer survey. Your feedback helps us improve our services.</p>
      <a href="{survey_url}"
         style="display:inline-block;padding:12px 24px;background:#4f46e5;color:#fff;
                border-radius:8px;text-decoration:none;font-weight:bold;margin-top:16px;">
        {'Complete Survey' if is_reminder else 'Take Survey'}
      </a>
      <p style="color:#9ca3af;font-size:12px;margin-top:32px;">
        If the button doesn't work, copy this link: {survey_url}
      </p>
    </div>
    """


def _dispatch_emails(survey_id: str, survey_title: str, emails: list[str], is_reminder: bool, db: Session):
    """Background task: send emails and update distribution records."""
    survey_url = f"{APP_URL}/s/{survey_id}"
    subject = f"{'Reminder: ' if is_reminder else ''}Please complete our survey — {survey_title}"
    html = _survey_email_html(survey_title, survey_url, is_reminder)

    for email in emails:
        try:
            _send_email(email, subject, html)
        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send to {email}: {e}")
            continue

        dist = db.query(SurveyDistribution).filter(
            SurveyDistribution.survey_id == survey_id,
            SurveyDistribution.email == email,
        ).first()

        if dist:
            if is_reminder:
                dist.reminder_sent_at = datetime.now(timezone.utc)
        else:
            db.add(SurveyDistribution(
                id=str(uuid.uuid4()),
                survey_id=survey_id,
                email=email,
            ))

    db.commit()


@router.post("/{survey_id}/distribute", status_code=202)
def distribute_survey(
    survey_id: str,
    payload: DistributeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_manager),
):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    if survey.status != "published":
        raise HTTPException(status_code=400, detail="Only published surveys can be distributed")

    db.add(AuditLog(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        action="DISTRIBUTE_SURVEY",
        resource="survey",
        resource_id=survey_id,
        detail=f"Distributed to {len(payload.emails)} recipients",
        ip_address=request.client.host if request.client else "unknown",
    ))
    db.commit()

    background_tasks.add_task(_dispatch_emails, survey_id, survey.title, payload.emails, False, db)
    return {"message": f"Distribution queued for {len(payload.emails)} recipients"}


@router.post("/{survey_id}/remind", status_code=202)
def remind_non_respondents(
    survey_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_manager),
):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    non_respondents = db.query(SurveyDistribution).filter(
        SurveyDistribution.survey_id == survey_id,
        SurveyDistribution.has_responded == False,
    ).all()

    emails = [d.email for d in non_respondents]
    if not emails:
        return {"message": "No non-respondents to remind"}

    db.add(AuditLog(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        action="REMIND_NON_RESPONDENTS",
        resource="survey",
        resource_id=survey_id,
        detail=f"Sent reminders to {len(emails)} non-respondents",
        ip_address=request.client.host if request.client else "unknown",
    ))
    db.commit()

    background_tasks.add_task(_dispatch_emails, survey_id, survey.title, emails, True, db)
    return {"message": f"Reminders queued for {len(emails)} non-respondents"}
