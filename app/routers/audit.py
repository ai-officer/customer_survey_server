from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..models import AuditLog, User
from ..security import require_admin

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


class AuditLogOut(BaseModel):
    id: str
    user_id: Optional[str]
    action: str
    resource: str
    resource_id: Optional[str]
    detail: Optional[str]
    ip_address: Optional[str]
    timestamp: datetime
    user_email: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    action: str | None = Query(None),
    resource: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if resource:
        q = q.filter(AuditLog.resource == resource)
    if start_date:
        q = q.filter(AuditLog.timestamp >= start_date)
    if end_date:
        q = q.filter(AuditLog.timestamp <= end_date)

    logs = q.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()

    result = []
    for log in logs:
        user_email = None
        if log.user_id:
            u = db.query(User).filter(User.id == log.user_id).first()
            user_email = u.email if u else None
        result.append(AuditLogOut(
            id=log.id,
            user_id=log.user_id,
            action=log.action,
            resource=log.resource,
            resource_id=log.resource_id,
            detail=log.detail,
            ip_address=log.ip_address,
            timestamp=log.timestamp,
            user_email=user_email,
        ))
    return result
