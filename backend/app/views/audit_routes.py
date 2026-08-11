"""
HTTP layer for the AI audit agent: kicks off Plan -> Execute -> Reflect ->
Learn runs (single page or batch) and exposes live status + final results.
Never calls into app/ai/ directly - only app/controllers/audit_controller.py,
matching the pattern set by crawl_routes.py for Phase 1.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.controllers import audit_controller, project_controller
from app.controllers.audit_controller import AuditNotReadyError
from app.controllers.errors import NotFoundError
from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.audit import (
    AuditExecutionResultsOut,
    AuditExecutionStartResponse,
    AuditExecutionStatusOut,
    AuditResultsOut,
    AuditRunStatusOut,
    AuditStartResponse,
    BatchAuditRequest,
    PlanStepOut,
    PlanStepOverrideRequest,
)
from app.utils.report_exporter import build_excel_report, build_word_report

router = APIRouter(tags=["audit"])


def _get_owned_project(db: Session, project_id: int, current_user: User):
    try:
        return project_controller.get_project_or_raise(db, project_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/api/projects/{project_id}/pages/{page_id}/audit",
    response_model=AuditStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_page_audit(
    project_id: int,
    page_id: int,
    background_tasks: BackgroundTasks,
    conformance_level: str = Query(default="AA", pattern="^(A|AA|AAA)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditStartResponse:
    project = _get_owned_project(db, project_id, current_user)
    try:
        run = audit_controller.start_audit(db, project, page_id, conformance_level)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    background_tasks.add_task(audit_controller.run_audit_job, run.id)
    return AuditStartResponse(audit_run_id=run.id, page_id=run.page_id, status=run.status, message="Audit started")


@router.post(
    "/api/projects/{project_id}/audit-batch",
    response_model=AuditExecutionStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_batch_audit(
    project_id: int,
    payload: BatchAuditRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditExecutionStartResponse:
    """Selecting N pages and clicking "Audit Selected Pages" is ONE execution
    with one combined report - not N separate ones. Each page still runs its
    own background job (that pipeline is inherently per-page), but they're
    all grouped under a single execution_id the frontend polls/reports on."""
    project = _get_owned_project(db, project_id, current_user)
    execution, outcomes = audit_controller.start_batch_audit(db, project, payload.page_ids, payload.conformance_level)

    started = 0
    for _page_id, run, _error in outcomes:
        if run is not None:
            background_tasks.add_task(audit_controller.run_audit_job, run.id)
            started += 1

    return AuditExecutionStartResponse(
        execution_id=execution.id,
        project_id=project.id,
        total_pages=len(payload.page_ids),
        message=f"Audit started for {started} of {len(payload.page_ids)} page(s)",
    )


@router.get("/api/audit-executions/{execution_id}", response_model=AuditExecutionStatusOut)
def get_audit_execution(
    execution_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditExecutionStatusOut:
    try:
        data = audit_controller.get_execution_status(db, execution_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return AuditExecutionStatusOut(**data)


@router.get("/api/audit-executions/{execution_id}/results", response_model=AuditExecutionResultsOut)
def get_audit_execution_results(
    execution_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditExecutionResultsOut:
    try:
        data = audit_controller.get_execution_results(db, execution_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuditNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AuditExecutionResultsOut(**data)


@router.get("/api/audit-executions/{execution_id}/export/excel")
def export_audit_execution_excel(
    execution_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the combined Excel workbook (all selected pages' Defects +
    Test Cases in one file) for the whole execution."""
    try:
        data = audit_controller.get_execution_results(db, execution_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuditNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    xlsx_bytes = build_excel_report(data)
    filename = f"audit_execution_{execution_id}_report.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/audit-executions/{execution_id}/export/word")
def export_audit_execution_word(
    execution_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download the combined IAAP-style Word document (.docx) covering every
    page in the execution."""
    try:
        data = audit_controller.get_execution_results(db, execution_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuditNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    docx_bytes = build_word_report(data)
    filename = f"audit_execution_{execution_id}_iaap_report.docx"
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/audit-runs/{audit_run_id}", response_model=AuditRunStatusOut)
def get_audit_run(
    audit_run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditRunStatusOut:
    try:
        run, steps = audit_controller.get_run_with_steps(db, audit_run_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return AuditRunStatusOut(
        id=run.id,
        project_id=run.project_id,
        page_id=run.page_id,
        page_url=run.page.url if run.page else "",
        status=run.status,
        conformance_level=run.conformance_level,
        total_steps=run.total_steps,
        completed_steps=run.completed_steps,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        plan_steps=[PlanStepOut.model_validate(step) for step in steps],
    )


@router.get("/api/audit-runs/{audit_run_id}/results", response_model=AuditResultsOut)
def get_audit_run_results(
    audit_run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditResultsOut:
    try:
        data = audit_controller.get_results(db, audit_run_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuditNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AuditResultsOut(**data)


@router.patch("/api/audit-runs/{audit_run_id}/plan-steps/{plan_step_id}", response_model=PlanStepOut)
def override_plan_step(
    audit_run_id: int,
    plan_step_id: int,
    payload: PlanStepOverrideRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanStepOut:
    """Manual QA correction: override a test case's pass/fail/needs_review
    verdict and/or a defect's lifecycle status (Open/Fixed/Retest/...)."""
    if payload.status is None and payload.defect_status is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nothing to update")
    try:
        step = audit_controller.override_step(
            db, audit_run_id, plan_step_id, current_user.id, status=payload.status, defect_status=payload.defect_status
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return PlanStepOut.model_validate(step)


@router.get("/api/audit-runs/{audit_run_id}/export/excel")
def export_audit_excel(
    audit_run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download a combined Excel workbook: Sheet 1 = Defects, Sheet 2 = Test Cases."""
    try:
        data = audit_controller.get_results(db, audit_run_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuditNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    xlsx_bytes = build_excel_report(data)
    filename = f"audit_{audit_run_id}_report.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/audit-runs/{audit_run_id}/export/word")
def export_audit_word(
    audit_run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download an IAAP-style Word document (.docx) for the audit run."""
    try:
        data = audit_controller.get_results(db, audit_run_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuditNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    docx_bytes = build_word_report(data)
    filename = f"audit_{audit_run_id}_iaap_report.docx"
    return StreamingResponse(
        iter([docx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

