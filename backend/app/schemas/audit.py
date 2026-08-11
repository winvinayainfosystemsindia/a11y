"""Pydantic DTOs for the AI audit agent feature."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditStartResponse(BaseModel):
    audit_run_id: int
    page_id: int
    status: str
    message: str


class BatchAuditRequest(BaseModel):
    page_ids: list[int] = Field(..., min_length=1, max_length=100)
    conformance_level: str = Field(default="AA", pattern="^(A|AA|AAA)$")


class AuditExecutionStartResponse(BaseModel):
    """Response for POST /audit-batch: ONE execution grouping every page the
    user selected, instead of a bag of independent audit_run_ids."""

    execution_id: int
    project_id: int
    total_pages: int
    message: str


class StepResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    confidence: float
    reasoning: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    is_follow_up: bool
    created_at: datetime


class PlanStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_order: int
    title: str
    wcag_criterion: str
    level: str
    element_type: str
    method: str
    tool_name: str | None = None
    priority: int
    reasoning: str | None = None
    status: str
    manual_status_override: str | None = None
    defect_status: str
    results: list[StepResultOut] = Field(default_factory=list)


class AuditRunStatusOut(BaseModel):
    id: int
    project_id: int
    page_id: int
    page_url: str
    status: str
    conformance_level: str
    total_steps: int
    completed_steps: int
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    plan_steps: list[PlanStepOut] = Field(default_factory=list)


class AuditExecutionPageStatus(BaseModel):
    """Progress for one page inside a single AuditExecution - what the UI
    renders as one row/stepper among many, all under one execution."""

    page_id: int
    page_url: str
    audit_run_id: int | None = None
    status: str
    total_steps: int = 0
    completed_steps: int = 0
    error: str | None = None
    message: str | None = None


class AuditExecutionStatusOut(BaseModel):
    """Aggregate status for a whole execution - the single thing the UI
    polls, in place of polling N independent audit_run ids."""

    execution_id: int
    project_id: int
    conformance_level: str
    status: str
    total_pages: int
    completed_pages: int
    created_at: datetime
    pages: list[AuditExecutionPageStatus] = Field(default_factory=list)


class TestCaseRow(BaseModel):
    """One test case, shaped to map directly onto a Test Case sheet:
    tcid, tcname, page title, page url, description, expected, steps to
    reproduce, criteria, level, severity, status."""

    test_case_id: str
    audit_run_id: int
    plan_step_id: int
    tc_name: str
    page_id: int
    page_title: str
    page_url: str
    principle: str
    criteria: str
    level: str
    element_type: str
    severity: str
    status: str
    description: str
    expected_result: str
    actual_result: str
    steps_to_reproduce: str
    remediation: str
    html_snippet: str | None = None
    screenshot: str | None = None
    confidence: float
    is_low_confidence: bool
    reasoning: str


class DefectRow(BaseModel):
    """One defect (a failed or needs-review test case), shaped to map
    directly onto a Defects sheet: defectid, testcase id, page title, page
    url, description, expected, actual, steps to reproduce, criteria,
    level, severity, status, suggestion to fix it."""

    defect_id: str
    test_case_id: str
    audit_run_id: int
    plan_step_id: int
    page_id: int
    page_title: str
    page_url: str
    principle: str
    criteria: str
    level: str
    element_type: str
    severity: str
    status: str
    verification_status: str
    defect_status: str
    description: str
    expected_result: str
    actual_result: str
    steps_to_reproduce: str
    suggestion_to_fix: str
    html_snippet: str | None = None
    screenshot: str | None = None
    confidence: float
    is_low_confidence: bool


class ConformanceBreakdown(BaseModel):
    """Pass/fail/needs-review tally for one bucket (a WCAG principle, a
    conformance level, or a severity) - always computed deterministically
    from the stored test cases, never asked of the LLM."""

    label: str
    total: int
    passed: int
    failed: int
    needs_review: int


class AuditReportSummary(BaseModel):
    """The IAAP-style report: an executive summary (LLM-authored, see
    reflection_prompts.py) paired with deterministically-computed
    conformance statistics (never trust the LLM for counts/tallies)."""

    methodology: str
    executive_summary: str | None = None
    total_test_cases: int
    total_defects: int
    pass_rate: float
    by_principle: list[ConformanceBreakdown] = Field(default_factory=list)
    by_level: list[ConformanceBreakdown] = Field(default_factory=list)
    by_severity: dict[str, int] = Field(default_factory=dict)


class AuditResultsOut(BaseModel):
    audit_run_id: int
    page_id: int
    page_title: str
    page_url: str
    status: str
    conformance_level: str
    low_confidence_test_case_ids: list[str] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    report: AuditReportSummary
    test_cases: list[TestCaseRow] = Field(default_factory=list)
    defects: list[DefectRow] = Field(default_factory=list)


class AuditExecutionPageSummary(BaseModel):
    """Per-page rollup shown at the top of the combined report, so the
    single report still tells you how each page did individually."""

    page_id: int
    audit_run_id: int | None = None
    page_title: str
    page_url: str
    status: str
    total_test_cases: int = 0
    total_defects: int = 0
    pass_rate: float = 0.0
    error: str | None = None


class AuditExecutionResultsOut(BaseModel):
    """The single combined report for a whole execution: one set of
    test_cases/defects spanning every page that was audited, plus a
    per-page breakdown and one aggregated conformance summary."""

    execution_id: int
    project_id: int
    status: str
    conformance_level: str
    pages: list[AuditExecutionPageSummary] = Field(default_factory=list)
    low_confidence_test_case_ids: list[str] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    report: AuditReportSummary
    test_cases: list[TestCaseRow] = Field(default_factory=list)
    defects: list[DefectRow] = Field(default_factory=list)


class PlanStepOverrideRequest(BaseModel):
    """Manual QA override for one PlanStep - a human correcting or tracking
    what the AI agent produced, not a re-run. Both fields are optional so a
    caller can patch just the test verdict, just the defect lifecycle
    status, or both in one request; at least one must be supplied."""

    status: str | None = Field(default=None, pattern="^(pass|fail|needs_review)$")
    defect_status: str | None = Field(
        default=None, pattern="^(Open|In Progress|Fixed|Retest|Closed|Won't Fix)$"
    )
