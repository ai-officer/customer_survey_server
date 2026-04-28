"""GET/POST /api/users, PUT/DELETE /api/users/{id}. Admin-only."""


# ── List ─────────────────────────────────────────────────────────────────────


def test_list_users_as_admin_returns_all(client, admin_headers, admin_user, manager_user):
    r = client.get("/api/users", headers=admin_headers)
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert admin_user.email in emails
    assert manager_user.email in emails


def test_list_users_as_manager_is_forbidden(client, manager_headers):
    r = client.get("/api/users", headers=manager_headers)
    assert r.status_code == 403


def test_list_users_unauthenticated(client):
    r = client.get("/api/users")
    assert r.status_code == 401


# ── Create ───────────────────────────────────────────────────────────────────


def test_create_user_as_admin(client, admin_headers):
    payload = {
        "email": "newbie@test.local",
        "full_name": "Newbie",
        "password": "secret-secret",
        "role": "manager",
    }
    r = client.post("/api/users", headers=admin_headers, json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == payload["email"]
    assert body["full_name"] == payload["full_name"]
    assert body["role"] == "manager"
    assert body["is_active"] is True


def test_create_user_with_duplicate_email_rejected(client, admin_headers, manager_user):
    r = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "email": manager_user.email,
            "full_name": "Dup",
            "password": "secret-secret",
            "role": "manager",
        },
    )
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()


def test_create_user_as_manager_is_forbidden(client, manager_headers):
    r = client.post(
        "/api/users",
        headers=manager_headers,
        json={
            "email": "x@x.local",
            "full_name": "X",
            "password": "secret-secret",
            "role": "manager",
        },
    )
    assert r.status_code == 403


# ── Update ───────────────────────────────────────────────────────────────────


def test_update_user_full_name_and_role(client, admin_headers, manager_user):
    r = client.put(
        f"/api/users/{manager_user.id}",
        headers=admin_headers,
        json={"full_name": "Renamed Manager", "role": "admin"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "Renamed Manager"
    assert body["role"] == "admin"


def test_update_user_password_changes_login(client, admin_headers, manager_user):
    r = client.put(
        f"/api/users/{manager_user.id}",
        headers=admin_headers,
        json={"password": "ResetMe123!"},
    )
    assert r.status_code == 200
    # Old password fails, new password works
    bad = client.post(
        "/api/auth/login",
        data={"username": manager_user.email, "password": "Password123!"},
    )
    assert bad.status_code == 401
    good = client.post(
        "/api/auth/login",
        data={"username": manager_user.email, "password": "ResetMe123!"},
    )
    assert good.status_code == 200


def test_update_unknown_user_returns_404(client, admin_headers):
    r = client.put(
        "/api/users/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
        json={"full_name": "Ghost"},
    )
    assert r.status_code == 404


# ── Deactivate ───────────────────────────────────────────────────────────────


def test_deactivate_user(client, admin_headers, manager_user):
    r = client.delete(f"/api/users/{manager_user.id}", headers=admin_headers)
    assert r.status_code == 204
    # Subsequent login is rejected by 'inactive' branch
    login = client.post(
        "/api/auth/login",
        data={"username": manager_user.email, "password": "Password123!"},
    )
    assert login.status_code == 403


def test_admin_cannot_deactivate_self(client, admin_headers, admin_user):
    r = client.delete(f"/api/users/{admin_user.id}", headers=admin_headers)
    assert r.status_code == 400
    assert "cannot deactivate your own" in r.json()["detail"].lower()


def test_deactivate_unknown_user_returns_404(client, admin_headers):
    r = client.delete(
        "/api/users/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert r.status_code == 404
