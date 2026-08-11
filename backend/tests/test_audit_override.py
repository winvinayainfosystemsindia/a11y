"""Integration tests for the manual QA override endpoint:
PATCH /api/audit-runs/{run_id}/plan-steps/{plan_step_id}
"""
from app.models.audit_run import AuditRun
from app.models.crawled_page import CrawledPage
from app.models.plan_step import PlanStep
from app.models.project import Project

VALID_PASSWORD = "Str0ngPass1"


def _signup_and_login(client, email):
    signup_resp = client.post(
        "/api/auth/signup", json={"full_name": "Reviewer", "email": email, "password": VALID_PASSWORD}
    )
    user_id = signup_resp.json()["id"]
    login_resp = client.post("/api/auth/login", json={"email": email, "password": VALID_PASSWORD})
    return user_id, login_resp.json()["access_token"]


def _create_run_with_step(db_session, user_id):
    project = Project(user_id=user_id, name="Test Site", base_url="https://example.com")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    page = CrawledPage(project_id=project.id, url="https://example.com/", page_title="Home")
    db_session.add(page)
    db_session.commit()
    db_session.refresh(page)

    run = AuditRun(project_id=project.id, page_id=page.id, status="completed", conformance_level="AA")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    step = PlanStep(
        audit_run_id=run.id,
        step_order=1,
        title="Search icon button has no accessible name",
        wcag_criterion="4.1.2",
        level="A",
        method="llm",
        element_type="Images / Icons / Image Buttons",
        target_element={"description": "search icon button"},
        priority=1,
        status="failed",
    )
    db_session.add(step)
    db_session.commit()
    db_session.refresh(step)

    return run, step


def test_override_status_wins_over_ai_verdict(client, db_session):
    user_id, token = _signup_and_login(client, "reviewer1@example.com")
    run, step = _create_run_with_step(db_session, user_id)

    resp = client.patch(
        f"/api/audit-runs/{run.id}/plan-steps/{step.id}",
        json={"status": "pass"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["manual_status_override"] == "pass"


def test_override_defect_status(client, db_session):
    user_id, token = _signup_and_login(client, "reviewer2@example.com")
    run, step = _create_run_with_step(db_session, user_id)

    resp = client.patch(
        f"/api/audit-runs/{run.id}/plan-steps/{step.id}",
        json={"defect_status": "Fixed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["defect_status"] == "Fixed"


def test_empty_payload_rejected(client, db_session):
    user_id, token = _signup_and_login(client, "reviewer3@example.com")
    run, step = _create_run_with_step(db_session, user_id)

    resp = client.patch(
        f"/api/audit-runs/{run.id}/plan-steps/{step.id}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_invalid_status_value_rejected(client, db_session):
    user_id, token = _signup_and_login(client, "reviewer4@example.com")
    run, step = _create_run_with_step(db_session, user_id)

    resp = client.patch(
        f"/api/audit-runs/{run.id}/plan-steps/{step.id}",
        json={"status": "maybe"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_other_users_run_returns_404(client, db_session):
    owner_id, _owner_token = _signup_and_login(client, "owner@example.com")
    run, step = _create_run_with_step(db_session, owner_id)

    _intruder_id, intruder_token = _signup_and_login(client, "intruder@example.com")
    resp = client.patch(
        f"/api/audit-runs/{run.id}/plan-steps/{step.id}",
        json={"status": "pass"},
        headers={"Authorization": f"Bearer {intruder_token}"},
    )
    assert resp.status_code == 404


def test_unauthenticated_request_rejected(client, db_session):
    user_id, _token = _signup_and_login(client, "reviewer5@example.com")
    run, step = _create_run_with_step(db_session, user_id)

    resp = client.patch(f"/api/audit-runs/{run.id}/plan-steps/{step.id}", json={"status": "pass"})
    assert resp.status_code == 401
