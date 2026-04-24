"""Email delivery via Resend. FROM stays on the verified domain; sender
identity is surfaced via display name + reply-to, so recipients see
"Lisa Smith via Customer Survey" and replies route back to the admin's
real inbox regardless of where it's hosted."""
import os
import html
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


FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
COLOR_BG = "#f5f6f8"
COLOR_CARD = "#ffffff"
COLOR_BORDER = "#e5e7eb"
COLOR_TEXT = "#111827"
COLOR_MUTED = "#6b7280"
COLOR_ACCENT = "#4f46e5"
COLOR_SUBTLE_BG = "#f9fafb"


def _cta_button(url: str, label: str) -> str:
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0">
      <tr>
        <td align="center" bgcolor="{COLOR_ACCENT}" style="border-radius:8px;background:{COLOR_ACCENT}">
          <a href="{url}"
             style="display:inline-block;padding:14px 28px;font-family:{FONT_STACK};font-size:15px;font-weight:600;line-height:1;color:#ffffff;text-decoration:none;border-radius:8px">
            {label}&nbsp;&rarr;
          </a>
        </td>
      </tr>
    </table>""".strip()


def _email_shell(*, preheader: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{html.escape(APP_NAME)}</title>
</head>
<body style="margin:0;padding:0;background:{COLOR_BG};-webkit-font-smoothing:antialiased">
  <div style="display:none!important;opacity:0;color:transparent;height:0;width:0;overflow:hidden;mso-hide:all;visibility:hidden">{html.escape(preheader)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{COLOR_BG};padding:32px 12px">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;width:100%;background:{COLOR_CARD};border:1px solid {COLOR_BORDER};border-radius:12px;overflow:hidden">
          <tr>
            <td style="height:4px;background:{COLOR_ACCENT};line-height:4px;font-size:0">&nbsp;</td>
          </tr>
          <tr>
            <td style="padding:28px 32px 0;font-family:{FONT_STACK}">
              <div style="font-size:11px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:{COLOR_ACCENT}">{html.escape(APP_NAME)}</div>
            </td>
          </tr>
          <tr>
            <td style="padding:12px 32px 32px;font-family:{FONT_STACK};color:{COLOR_TEXT};font-size:15px;line-height:1.55">
              {body_html}
            </td>
          </tr>
        </table>
        <div style="max-width:560px;margin:12px auto 0;padding:12px 24px;font-family:{FONT_STACK};font-size:12px;color:{COLOR_MUTED};text-align:center">
          Sent by {html.escape(APP_NAME)}. If this wasn't meant for you, feel free to ignore it.
        </div>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _survey_card(survey_title: str) -> str:
    return f"""
      <div style="margin:0 0 24px;padding:16px 20px;background:{COLOR_SUBTLE_BG};border:1px solid {COLOR_BORDER};border-left:3px solid {COLOR_ACCENT};border-radius:6px">
        <div style="font-family:{FONT_STACK};font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:{COLOR_MUTED};margin:0 0 4px">Survey</div>
        <div style="font-family:{FONT_STACK};font-size:17px;font-weight:600;color:{COLOR_TEXT};line-height:1.35">{html.escape(survey_title)}</div>
      </div>""".strip()


def _fallback_link(url: str) -> str:
    return f"""
      <hr style="border:none;border-top:1px solid {COLOR_BORDER};margin:28px 0 18px">
      <p style="margin:0 0 6px;font-family:{FONT_STACK};font-size:12px;color:{COLOR_MUTED}">Button not working? Copy and paste this link:</p>
      <p style="margin:0;font-family:{FONT_STACK};font-size:12px;word-break:break-all">
        <a href="{url}" style="color:{COLOR_ACCENT};text-decoration:underline">{url}</a>
      </p>""".strip()


def _invite_html(survey_title: str, survey_url: str, sender_name: str) -> str:
    safe_sender = html.escape(sender_name)
    body = f"""
      <p style="margin:0 0 10px;font-size:22px;font-weight:700;color:{COLOR_TEXT};line-height:1.3">You're invited to share your feedback.</p>
      <p style="margin:0 0 24px;color:{COLOR_MUTED};font-size:15px;line-height:1.55">
        <strong style="color:{COLOR_TEXT};font-weight:600">{safe_sender}</strong> would love a minute of your time on a short survey.
      </p>
      {_survey_card(survey_title)}
      {_cta_button(survey_url, "Open survey")}
      <p style="margin:14px 0 0;font-size:13px;color:{COLOR_MUTED}">Takes about a minute — every answer helps.</p>
      {_fallback_link(survey_url)}
    """
    preheader = f"{sender_name} invited you to a short survey — about a minute of your time."
    return _email_shell(preheader=preheader, body_html=body)


def _reminder_html(survey_title: str, survey_url: str, sender_name: str) -> str:
    safe_sender = html.escape(sender_name)
    body = f"""
      <p style="margin:0 0 10px;font-size:22px;font-weight:700;color:{COLOR_TEXT};line-height:1.3">A quick nudge &mdash; the survey's still open.</p>
      <p style="margin:0 0 24px;color:{COLOR_MUTED};font-size:15px;line-height:1.55">
        <strong style="color:{COLOR_TEXT};font-weight:600">{safe_sender}</strong> is still hoping to hear from you. It only takes a moment.
      </p>
      {_survey_card(survey_title)}
      {_cta_button(survey_url, "Open survey")}
      <p style="margin:14px 0 0;font-size:13px;color:{COLOR_MUTED}">One minute, and you're done. Thank you.</p>
      {_fallback_link(survey_url)}
    """
    preheader = f"Reminder from {sender_name} — the survey is still open."
    return _email_shell(preheader=preheader, body_html=body)


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
