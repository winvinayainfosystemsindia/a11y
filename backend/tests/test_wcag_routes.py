"""Integration tests for the Success Criteria Library endpoint."""

VALID_PASSWORD = "Str0ngPass1"


def _signup_and_login(client, email="reviewer@example.com"):
    client.post("/api/auth/signup", json={"full_name": "Reviewer", "email": email, "password": VALID_PASSWORD})
    resp = client.post("/api/auth/login", json={"email": email, "password": VALID_PASSWORD})
    return resp.json()["access_token"]


def test_requires_auth(client):
    resp = client.get("/api/wcag/success-criteria")
    assert resp.status_code == 401


def test_returns_all_fifty_by_default(client):
    token = _signup_and_login(client)
    resp = client.get("/api/wcag/success-criteria", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 50
    first = items[0]
    assert set(first.keys()) == {
        "s_no", "sc_number", "name", "wcag_version", "level", "principle", "guideline", "description",
    }
    assert [item["s_no"] for item in items] == list(range(1, 51))


def test_level_a_filter_returns_thirty(client):
    token = _signup_and_login(client)
    resp = client.get(
        "/api/wcag/success-criteria", params={"level": "A"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 30
    assert all(item["level"] == "A" for item in items)


def test_invalid_level_rejected(client):
    token = _signup_and_login(client)
    resp = client.get(
        "/api/wcag/success-criteria", params={"level": "AAA"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 422
