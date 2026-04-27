"""Cross-cutting helpers for audit-log writes and request inspection.

These were duplicated as `_log` / `_audit` / `_ip` across every
router; consolidating them here removes ~30 lines of copy-paste
and ensures a single audit-row shape everywhere.
"""
from __future__ import annotations
import uuid
from typing import Optional
from fastapi import Request
from sqlalchemy.orm import Session
from ..models import AuditLog


def get_client_ip(request: Optional[Request]) -> str:
    """Best-effort client IP, with a stable fallback. Never raises."""
    if request and request.client:
        return request.client.host
    return "unknown"


def record_audit(
    db: Session,
    *,
    user_id: Optional[str],
    action: str,
    resource: str,
    resource_id: Optional[str],
    detail: Optional[str],
    ip: str,
) -> None:
    """Append an audit-log row. Caller is responsible for db.commit()."""
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip,
    ))
