"""
AuditAgent orchestrator: runs the Perceive -> Plan -> Execute -> Reflect ->
Learn loop for one AuditRun.

This is the ONLY module in app/ai/ that app/controllers/audit_controller.py
is allowed to import - the rest of app/ai/ (planner, executor, reflector,
memory/, tools/, prompts/) are internal collaborators wired together here.
Every persistent write goes through app/repositories/*; nothing here (or
anywhere else in app/ai/) executes raw SQLAlchemy, and the LLM itself never
gets a database-writing tool - LEARN produces plain `Lesson` data that this
function hands to memory_store.record_lesson.
"""
from __future__ import annotations

import logging

from app.ai import executor, perceiver, planner, reflector
from app.ai.memory import memory_store
from app.ai.tools.browser import open_page
from app.database import SessionLocal
from app.models.audit_run import (
    AUDIT_STATUS_COMPLETED,
    AUDIT_STATUS_EXECUTING,
    AUDIT_STATUS_FAILED,
    AUDIT_STATUS_LEARNING,
    AUDIT_STATUS_PERCEIVING,
    AUDIT_STATUS_PLANNING,
    AUDIT_STATUS_REFLECTING,
)
from app.repositories import audit_repository

logger = logging.getLogger(__name__)


async def run_audit(run_id: int) -> None:
    """The full loop for one AuditRun, scheduled as a FastAPI background
    task (see app/controllers/audit_controller.py). Opens its own DB
    session - matching crawl_controller.run_crawl_job's pattern - since it
    runs after the original HTTP request's session has already closed."""
    db = SessionLocal()
    try:
        run = audit_repository.get_run(db, run_id)
        if run is None:
            logger.error("AuditRun %s not found - cannot start the loop", run_id)
            return

        page_row = audit_repository.get_page(db, run.page_id)
        if page_row is None:
            audit_repository.finalize_run(db, run_id, status=AUDIT_STATUS_FAILED, error="Crawled page no longer exists")
            return

        conformance_level = run.conformance_level

        # ── PERCEIVE ─────────────────────────────────────────────────────
        audit_repository.mark_status(db, run_id, AUDIT_STATUS_PERCEIVING)
        async with open_page(page_row.url) as page:
            snapshot = await perceiver.perceive(
                db,
                page,
                url=page_row.url,
                final_url=page.url,
                status_code=page_row.status_code,
                page_id=page_row.id,
                run_id=run_id,
            )
            audit_repository.set_perception(db, run_id, snapshot.model_dump())

            # ── PLAN ─────────────────────────────────────────────────────
            audit_repository.mark_status(db, run_id, AUDIT_STATUS_PLANNING)
            plan = await planner.build_plan(snapshot, conformance_level)
            audit_repository.create_plan_steps(db, run_id, [step.model_dump() for step in plan.steps])

            # ── EXECUTE ──────────────────────────────────────────────────
            # Reload the steps we just persisted (with generated ids) and
            # run them against the *same* page the plan was built from.
            audit_repository.mark_status(db, run_id, AUDIT_STATUS_EXECUTING)
            plan_step_rows = audit_repository.list_plan_steps(db, run_id)
            await executor.run(
                db, page, plan_step_rows, snapshot, conformance_level=conformance_level, run_id=run_id
            )
        # Browser closed here - REFLECT/LEARN are pure LLM + DB stages.

        # ── REFLECT ──────────────────────────────────────────────────────
        audit_repository.mark_status(db, run_id, AUDIT_STATUS_REFLECTING)
        plan_step_rows = audit_repository.list_plan_steps(db, run_id)  # reload with fresh StepResults
        reflection = await reflector.reflect(plan_step_rows, snapshot, conformance_level)
        audit_repository.set_reflection(db, run_id, summary=reflection.summary, data=reflection.model_dump())

        # ── LEARN ────────────────────────────────────────────────────────
        # Never skipped, even under time pressure - this is what makes the
        # next audit smarter. Each lesson is applied independently so one
        # bad lesson doesn't block the rest from being recorded.
        audit_repository.mark_status(db, run_id, AUDIT_STATUS_LEARNING)
        for lesson in reflection.lessons:
            try:
                memory_store.record_lesson(db, lesson, audit_run_id=run_id)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to persist a lesson for run %s: %r", run_id, lesson)
                db.rollback()  # a failed statement leaves the session's transaction aborted

        audit_repository.finalize_run(db, run_id, status=AUDIT_STATUS_COMPLETED)

    except Exception as exc:  # noqa: BLE001 - surface any run failure, matching crawl_controller's pattern
        logger.exception("Audit run %s failed", run_id)
        db.rollback()  # a failed statement leaves the session's transaction aborted
        audit_repository.finalize_run(db, run_id, status=AUDIT_STATUS_FAILED, error=str(exc))
    finally:
        db.close()
