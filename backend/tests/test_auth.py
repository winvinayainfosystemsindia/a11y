"""Integration tests for the full signup -> login -> refresh -> logout flow."""

VALID_PASSWORD = "Str0ngPass1"


def _signup(client, email="jane@example.com", password=VALID_PASSWORD):
    return client.post(
        "/api/auth/signup",
        json={"full_name": "Jane Doe", "email": email, "password": password},
    )


def test_signup_creates_user(client):
    resp = _signup(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "jane@example.com"
    assert "hashed_password" not in body
    assert "password" not in body


def test_signup_duplicate_email_rejected(client):
    _signup(client)
    resp = _signup(client)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "An account with this email already exists"


def test_signup_rejects_weak_password(client):
    resp = _signup(client, password="short")
    assert resp.status_code == 422


def test_signup_rejects_invalid_email(client):
    resp = client.post(
        "/api/auth/signup",
        json={"full_name": "Jane Doe", "email": "not-an-email", "password": VALID_PASSWORD},
    )
    assert resp.status_code == 422


def test_login_success_returns_access_and_refresh_tokens(client):
    _signup(client)
    resp = client.post("/api/auth/login", json={"email": "jane@example.com", "password": VALID_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password_rejected(client):
    _signup(client)
    resp = client.post("/api/auth/login", json={"email": "jane@example.com", "password": "WrongPass1"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


def test_login_unknown_email_rejected(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": VALID_PASSWORD})
    assert resp.status_code == 401


def test_protected_route_requires_token(client):
    resp = client.get("/api/users/me")
    assert resp.status_code == 401


def test_protected_route_accepts_valid_access_token(client):
    _signup(client)
    login_resp = client.post("/api/auth/login", json={"email": "jane@example.com", "password": VALID_PASSWORD})
    access_token = login_resp.json()["access_token"]

    resp = client.get("/api/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "jane@example.com"


def test_refresh_issues_new_access_token(client):
    _signup(client)
    login_resp = client.post("/api/auth/login", json={"email": "jane@example.com", "password": VALID_PASSWORD})
    refresh_token = login_resp.json()["refresh_token"]

    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["refresh_token"] != refresh_token  # rotated


def test_refresh_token_reuse_after_rotation_fails(client):
    _signup(client)
    login_resp = client.post("/api/auth/login", json={"email": "jane@example.com", "password": VALID_PASSWORD})
    refresh_token = login_resp.json()["refresh_token"]

    first = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200

    second = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert second.status_code == 401


def test_logout_revokes_refresh_token(client):
    _signup(client)
    login_resp = client.post("/api/auth/login", json={"email": "jane@example.com", "password": VALID_PASSWORD})
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = client.post("/api/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 200

    reuse_resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401


def test_invalid_refresh_token_rejected(client):
    resp = client.post("/api/auth/refresh", json={"refresh_token": "totally-made-up-token"})
    assert resp.status_code == 401
