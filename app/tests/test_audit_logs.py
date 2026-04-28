"""GET /api/audit-logs — admin only."""

import uuid
from datetime import datetime, timedelta, timezone

from app.models import AuditLog


def _seed_logs(db):
    now = datetime.now(timezone.utc)
    rows = [
        AuditLog(
            id=str(uuid.uuid4()),
            user_id=None,
            action="LOGIN",
            resource="user",
            resource_id="u1",
            detail="login a",
            ip_address="1.2.3.4",
            timestamp=now - timedelta(days=2),
        ),
        AuditLog(
            id=str(uuid.uuid4()),
            user_id=None,
            action="CREATE_SURVEY",
            resource="survey",
            resource_id="s1",
            detail="created",
            ip_address="1.2.3.4",
            timestamp=now - timedelta(hours=1),
        ),
        AuditLog(
            id=str(uuid.uuid4()),
            user_id=None,
            action="DELETE_SURVEY",
            resource="survey",
            resource_id="s2",
            detail="deleted",
            ip_address="1.2.3.4",
            timestamp=now,
        ),
    ]
    for r in rows:
        db.add(r)
    db.commit()


def test_audit_logs_admin_lists(client, admin_headers, db):
    _seed_logs(db)
    r = client.get("/api/audit-logs", headers=admin_headers)
    assert r.status_code == 200
    actions = [row["action"] for row in r.json()]
    # Sorted by timestamp desc
    assert actions[0] == "DELETE_SURVEY"


def test_audit_logs_filter_by_action(client, admin_headers, db):
    _seed_logs(db)
    r = client.get("/api/audit-logs?action=LOGIN", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["action"] == "LOGIN"


def test_audit_logs_filter_by_resource(client, admin_headers, db):
    _seed_logs(db)
    r = client.get("/api/audit-logs?resource=survey", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert {row["action"] for row in body} == {"CREATE_SURVEY", "DELETE_SURVEY"}


def test_audit_logs_pagination(client, admin_headers, db):
    _seed_logs(db)
    r = client.get("/api/audit-logs?limit=2", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2

    r2 = client.get("/api/audit-logs?limit=2&offset=2", headers=admin_headers)
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_audit_logs_resolves_user_email(
    client, admin_headers, admin_user, db
):
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            user_id=admin_user.id,
            action="UPDATE_SURVEY",
            resource="survey",
            resource_id="s9",
            detail="x",
            ip_address="1.2.3.4",
        )
    )
    db.commit()
    r = client.get("/api/audit-logs?action=UPDATE_SURVEY", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body[0]["user_email"] == admin_user.email


def test_audit_logs_manager_forbidden(client, manager_headers):
    r = client.get("/api/audit-logs", headers=manager_headers)
    assert r.status_code == 403


def test_audit_logs_unauth(client):
    r = client.get("/api/audit-logs")
    assert r.status_code == 401
