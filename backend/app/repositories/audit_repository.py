"""
DB access for AI audit runs. This is the only module that touches
AuditRun/PlanStep/StepResult with the ORM - app/ai/agent.py (and nothing
inside app/ai/ below it) is allowed to call these functions, but never
executes raw SQLAlchemy itself. Every write here is immediate (no batching
at the end of a run) so a crash mid-run never loses completed work.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.audit_execution import AuditExecution
from app.models.audit_run import AuditRun
from app.models.crawled_page import CrawledPage
from app.models.plan_step import PlanStep
from app.models.project import Project
from app.models.step_result import StepResult


def create_run(
    db: Session, *, project_id: int, page_id: int, conformance_level: str, execution_id: int | None = None
) -> AuditRun:
    run = AuditRun(
        project_id=project_id, page_id=page_id, conformance_level=conformance_level, execution_id=execution_id
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_execution(db: Session, *, project_id: int, conformance_level: str, total_pages: int) -> AuditExecution:
    """One row per "Audit Selected Pages" click - the parent that groups all
    per-page AuditRuns from that batch into a single execution/report."""
    execution = AuditExecution(project_id=project_id, conformance_level=conformance_level, total_pages=total_pages)
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def get_execution_owned_by_user(db: Session, execution_id: int, user_id: int) -> AuditExecution | None:
    stmt = (
        select(AuditExecution)
        .join(Project, Project.id == AuditExecution.project_id)
        .where(AuditExecution.id == execution_id, Project.user_id == user_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_runs_for_execution(db: Session, execution_id: int) -> list[AuditRun]:
    stmt = (
        select(AuditRun)
        .options(joinedload(AuditRun.page))
        .where(AuditRun.execution_id == execution_id)
        .order_by(AuditRun.id)
    )
    return list(db.execute(stmt).scalars().all())


def get_run(db: Session, run_id: int) -> AuditRun | None:
    return db.get(AuditRun, run_id)


def get_run_owned_by_user(db: Session, run_id: int, user_id: int) -> AuditRun | None:
    stmt = (
        select(AuditRun)
        .join(Project, Project.id == AuditRun.project_id)
        .where(AuditRun.id == run_id, Project.user_id == user_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_recent_completed_runs_for_page(db: Session, page_id: int, *, exclude_run_id: int | None = None, limit: int = 3) -> list[AuditRun]:
    stmt = (
        select(AuditRun)
        .where(AuditRun.page_id == page_id, AuditRun.status == "completed")
        .order_by(AuditRun.completed_at.desc())
        .limit(limit)
    )
    if exclude_run_id is not None:
        stmt = stmt.where(AuditRun.id != exclude_run_id)
    return list(db.execute(stmt).scalars().all())


def mark_status(db: Session, run_id: int, status: str) -> None:
    run = db.get(AuditRun, run_id)
    if run is None:
        return
    run.status = status
    if status not in ("queued",) and run.started_at is None:
        run.started_at = datetime.now(timezone.utc)
    db.add(run)
    db.commit()


def set_perception(db: Session, run_id: int, perception: dict) -> None:
    run = db.get(AuditRun, run_id)
    if run is None:
        return
    run.perception = perception
    db.add(run)
    db.commit()


def create_plan_steps(db: Session, run_id: int, steps: list[dict]) -> list[PlanStep]:
    """Bulk-persist an AuditPlan's steps in order, immediately (before any
    execution happens) so the plan itself is durable even if execution
    never completes."""
    created: list[PlanStep] = []
    for order, step in enumerate(steps, start=1):
        plan_step = PlanStep(
            audit_run_id=run_id,
            step_order=order,
            title=step.get("title") or "Accessibility check",
            wcag_criterion=step["wcag_criterion"],
            level=step.get("level", "AA"),
            method=step["method"],
            tool_name=step.get("tool_name"),
            target_element=step.get("target_element") or {},
            element_type=step.get("element_type") or "General Page",
            priority=step.get("priority", 3),
            reasoning=step.get("reasoning"),
        )
        db.add(plan_step)
        created.append(plan_step)
    run = db.get(AuditRun, run_id)
    if run is not None:
        run.total_steps = len(created)
    db.commit()
    for plan_step in created:
        db.refresh(plan_step)
    return created


def update_plan_step_status(db: Session, plan_step_id: int, status: str) -> None:
    plan_step = db.get(PlanStep, plan_step_id)
    if plan_step is None:
        return
    plan_step.status = status
    db.add(plan_step)
    db.commit()


def create_step_result(
    db: Session,
    *,
    plan_step_id: int,
    status: str,
    confidence: float,
    evidence: dict,
    reasoning: str | None,
    is_follow_up: bool = False,
    follow_up_of_id: int | None = None,
) -> StepResult:
    """Recorded the instant a step finishes - not batched - so partial runs
    keep whatever completed before a crash or timeout."""
    result = StepResult(
        plan_step_id=plan_step_id,
        status=status,
        confidence=confidence,
        evidence=evidence,
        reasoning=reasoning,
        is_follow_up=is_follow_up,
        follow_up_of_id=follow_up_of_id,
    )
    db.add(result)

    plan_step = db.get(PlanStep, plan_step_id)
    if plan_step is not None:
        plan_step.status = {
            "pass": "passed",
            "fail": "failed",
            "needs_review": "needs_review",
        }.get(status, "needs_review")
        if not is_follow_up:
            run = db.get(AuditRun, plan_step.audit_run_id)
            if run is not None:
                run.completed_steps += 1

    db.commit()
    db.refresh(result)
    return result


def get_plan_step(db: Session, plan_step_id: int) -> PlanStep | None:
    return db.get(PlanStep, plan_step_id)


def update_plan_step_override(
    db: Session, plan_step_id: int, *, status: str | None, defect_status: str | None
) -> PlanStep | None:
    """Human QA correction, applied directly - not routed through the AI
    pipeline. Only touches the fields the caller actually supplied."""
    plan_step = db.get(PlanStep, plan_step_id)
    if plan_step is None:
        return None
    if status is not None:
        plan_step.manual_status_override = status
    if defect_status is not None:
        plan_step.defect_status = defect_status
    db.add(plan_step)
    db.commit()
    db.refresh(plan_step)
    return plan_step


def list_plan_steps(db: Session, run_id: int) -> list[PlanStep]:
    stmt = (
        select(PlanStep)
        .options(joinedload(PlanStep.results))
        .where(PlanStep.audit_run_id == run_id)
        .order_by(PlanStep.step_order)
    )
    return list(db.execute(stmt).unique().scalars().all())


def set_reflection(db: Session, run_id: int, *, summary: str, data: dict) -> None:
    run = db.get(AuditRun, run_id)
    if run is None:
        return
    run.reflection_summary = summary
    run.reflection_data = data
    db.add(run)
    db.commit()


def finalize_run(db: Session, run_id: int, *, status: str, error: str | None = None) -> None:
    run = db.get(AuditRun, run_id)
    if run is None:
        return
    run.status = status
    run.error = error[:2048] if error else None
    run.completed_at = datetime.now(timezone.utc)
    db.add(run)
    db.commit()


def get_page(db: Session, page_id: int) -> CrawledPage | None:
    return db.get(CrawledPage, page_id)
