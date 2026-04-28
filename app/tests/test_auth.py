"""POST /api/auth/login, GET /api/auth/me, POST /api/auth/change-password."""


def _login(client, email, password):
    return client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )


# ── Login ────────────────────────────────────────────────────────────────────


def test_login_returns_token_and_user_payload(client, admin_user):
    r = _login(client, admin_user.email, "Password123!")
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert body["user"]["id"] == admin_user.id
    assert body["user"]["email"] == admin_user.email
    assert body["user"]["role"] == "admin"


def test_login_with_unknown_email_returns_401(client):
    r = _login(client, "nobody@nowhere.local", "whatever")
    assert r.status_code == 401
    assert "invalid email or password" in r.json()["detail"].lower()


def test_login_with_wrong_password_returns_401(client, manager_user):
    r = _login(client, manager_user.email, "wrong-password")
    assert r.status_code == 401


def test_login_with_inactive_account_is_rejected(client, inactive_user):
    r = _login(client, inactive_user.email, "Password123!")
    assert r.status_code == 403
    assert "deactivated" in r.json()["detail"].lower()


# ── /me ──────────────────────────────────────────────────────────────────────


def test_me_returns_current_user(client, admin_headers, admin_user):
    r = client.get("/api/auth/me", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == admin_user.id
    assert body["email"] == admin_user.email
    assert body["role"] == "admin"
    assert body["is_active"] is True


def test_me_without_token_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_garbage_token_returns_401(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


# ── Change password ──────────────────────────────────────────────────────────


def test_change_password_succeeds_with_correct_current(client, manager_user, manager_headers):
    r = client.post(
        "/api/auth/change-password",
        headers=manager_headers,
        json={"current_password": "Password123!", "new_password": "NewPassword456!"},
    )
    assert r.status_code == 204

    # Old password no longer works, new password does
    assert _login(client, manager_user.email, "Password123!").status_code == 401
    assert _login(client, manager_user.email, "NewPassword456!").status_code == 200


def test_change_password_rejects_wrong_current(client, manager_headers):
    r = client.post(
        "/api/auth/change-password",
        headers=manager_headers,
        json={"current_password": "wrong", "new_password": "NewPassword456!"},
    )
    assert r.status_code == 400
    assert "current password is incorrect" in r.json()["detail"].lower()


def test_change_password_rejects_too_short_new(client, manager_headers):
    r = client.post(
        "/api/auth/change-password",
        headers=manager_headers,
        json={"current_password": "Password123!", "new_password": "abc"},
    )
    assert r.status_code == 400
    assert "at least 6 characters" in r.json()["detail"]


def test_change_password_requires_auth(client):
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "x", "new_password": "abcdef"},
    )
    assert r.status_code == 401
