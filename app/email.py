"""Email delivery via Resend. FROM stays on the verified domain; sender
identity is surfaced via display name + reply-to, so recipients see
"Lisa Smith via Customer Survey" and replies route back to the admin's
real inbox regardless of where it's hosted."""
import os
import logging
from typing import Optional, List

import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "surveys@hotelsogo-ai.com")
APP_NAME = os.getenv("APP_NAME", "Customer Survey")
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")


def _from_field(sender_name: Optional[str]) -> str:
    if sender_name:
        return f'{sender_name} via {APP_NAME} <{FROM_EMAIL}>'
    return f'{APP_NAME} <{FROM_EMAIL}>'


def _survey_url(survey_id: str) -> str:
    return f'{PUBLIC_APP_URL}/s/{survey_id}'


def _invite_html(survey_title: str, survey_url: str, sender_name: str) -> str:
    return f"""
<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;color:#1f2937">
  <p style="margin:0 0 16px">Hi,</p>
  <p style="margin:0 0 24px"><strong>{sender_name}</strong> has invited you to take a short survey:</p>
  <h2 style="font-size:20px;margin:0 0 24px;color:#111827">{survey_title}</h2>
  <p style="margin:0 0 32px">
    <a href="{survey_url}" style="display:inline-block;background:#4f46e5;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">Open survey</a>
  </p>
  <p style="font-size:12px;color:#6b7280;margin:0 0 8px">If the button doesn't work, paste this link:</p>
  <p style="font-size:12px;color:#6b7280;word-break:break-all;margin:0">{survey_url}</p>
</body></html>
""".strip()


def _reminder_html(survey_title: str, survey_url: str, sender_name: str) -> str:
    return f"""
<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;color:#1f2937">
  <p style="margin:0 0 16px">Hi,</p>
  <p style="margin:0 0 24px">Just a friendly reminder from <strong>{sender_name}</strong> — your input would be appreciated:</p>
  <h2 style="font-size:20px;margin:0 0 24px;color:#111827">{survey_title}</h2>
  <p style="margin:0 0 32px">
    <a href="{survey_url}" style="display:inline-block;background:#4f46e5;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">Open survey</a>
  </p>
  <p style="font-size:12px;color:#6b7280;margin:0">It only takes a minute. Thank you.</p>
</body></html>
""".strip()


def _batch_send(*, payload: list, kind: str) -> dict:
    if not resend.api_key or not payload:
        logger.warning("Resend: api_key missing or empty payload (%d items)", len(payload))
        return {"sent": 0, "failed": len(payload)}
    print(f"[EMAIL] sending {len(payload)} {kind} via Resend")
    sent, failed = 0, 0
    for i in range(0, len(payload), 100):
        chunk = payload[i:i + 100]
        try:
            resend.Batch.send(chunk)
            sent += len(chunk)
        except Exception as e:
            logger.exception("Resend batch %s failed: %s", kind, e)
            failed += len(chunk)
    return {"sent": sent, "failed": failed}


def send_survey_invites_batch(
    *, recipients: List[str], survey_id: str, survey_title: str,
    sender_name: str, sender_email: str,
) -> dict:
    url = _survey_url(survey_id)
    html = _invite_html(survey_title, url, sender_name)
    subject = f"Your feedback wanted: {survey_title}"
    payload = [{
        "from": _from_field(sender_name),
        "to": [addr],
        "reply_to": [sender_email] if sender_email else [FROM_EMAIL],
        "subject": subject,
        "html": html,
        "tags": [
            {"name": "app", "value": "customer-survey"},
            {"name": "type", "value": "invite"},
            {"name": "survey_id", "value": survey_id},
        ],
    } for addr in recipients]
    return _batch_send(payload=payload, kind="invites")


def send_survey_reminders_batch(
    *, recipients: List[str], survey_id: str, survey_title: str,
    sender_name: str, sender_email: str,
) -> dict:
    url = _survey_url(survey_id)
    html = _reminder_html(survey_title, url, sender_name)
    subject = f"Reminder: {survey_title}"
    payload = [{
        "from": _from_field(sender_name),
        "to": [addr],
        "reply_to": [sender_email] if sender_email else [FROM_EMAIL],
        "subject": subject,
        "html": html,
        "tags": [
            {"name": "app", "value": "customer-survey"},
            {"name": "type", "value": "reminder"},
            {"name": "survey_id", "value": survey_id},
        ],
    } for addr in recipients]
    return _batch_send(payload=payload, kind="reminders")
