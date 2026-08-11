"""
AI Audit Agent - internal execution contracts.

Pydantic models exchanged between the stages of the Perceive -> Plan ->
Execute -> Reflect -> Learn loop. Nothing outside app/ai/ (and app/schemas
which maps these onto the Test Case sheet format) should need to import
this module directly - agent.py is the seam.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Method = Literal["tool", "llm"]
ConformanceLevel = Literal["A", "AA", "AAA"]
StepStatus = Literal["pass", "fail", "needs_review"]
OutcomePattern = Literal["usually_fails", "usually_passes", "mixed"]
LearnAction = Literal["new", "confirm", "contradict"]


# ── Perceive ─────────────────────────────────────────────────────────────

class ImageInfo(BaseModel):
    src: str
    alt: str | None = None
    has_alt_attribute: bool = False


class HeadingInfo(BaseModel):
    level: int
    text: str


class FormFieldInfo(BaseModel):
    tag: str
    input_type: str | None = None
    has_label: bool = False
    label_text: str | None = None
    placeholder: str | None = None


class ContrastSample(BaseModel):
    """One text node's rendered colors, sampled for the contrast tool."""
    selector: str
    text_preview: str
    foreground: str
    background: str
    font_size_px: float
    font_weight: int
    html: str | None = None


class MemoryContext(BaseModel):
    """What retriever.py found before planning - injected into the planner
    prompt and consulted again by the reflector to flag contradictions."""
    exact_url_history: list[dict[str, Any]] = Field(default_factory=list)
    similar_page_findings: list[dict[str, Any]] = Field(default_factory=list)
    rule_specific_patterns: list[dict[str, Any]] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.exact_url_history or self.similar_page_findings or self.rule_specific_patterns)


class PageSnapshot(BaseModel):
    """Output of the PERCEIVE stage. Deliberately compact - the raw HTML is
    used transiently while building this and then discarded, not stored."""
    url: str
    final_url: str
    title: str | None = None
    page_type_signature: str
    status_code: int | None = None

    landmarks: list[str] = Field(default_factory=list)
    headings: list[HeadingInfo] = Field(default_factory=list)
    images: list[ImageInfo] = Field(default_factory=list)
    forms: list[list[FormFieldInfo]] = Field(default_factory=list)
    links_count: int = 0
    interactive_elements_count: int = 0
    has_skip_link: bool = False
    lang_attribute: str | None = None

    contrast_samples: list[ContrastSample] = Field(default_factory=list)
    html_excerpt: str = ""
    screenshot_path: str | None = None

    memory_context: MemoryContext = Field(default_factory=MemoryContext)


# ── Plan ─────────────────────────────────────────────────────────────────

class PlanStepSchema(BaseModel):
    title: str = Field(
        ..., description='Short, specific test case name, e.g. "Search icon button has no accessible name"'
    )
    wcag_criterion: str = Field(..., description='e.g. "1.1.1" (Non-text Content)')
    level: ConformanceLevel
    method: Method = Field(
        ...,
        description="Literally 'tool' (a deterministic automated check) or 'llm' (an AI judgment call) - "
        "never the specific tool's name itself, that goes in tool_name below.",
    )
    tool_name: str | None = Field(
        default=None, description="Required when method='tool': axe|contrast|keyboard_nav|screenshot"
    )
    target_element: dict[str, Any] = Field(default_factory=dict)
    element_type: str = Field(
        default="General Page",
        description="The page-element category this test case targets - must be one of the values listed in "
        "the system prompt's Element / Component Type taxonomy (e.g. 'Images / Icons / Image Buttons', "
        "'Forms / Form Validation'), not free text.",
    )
    priority: int = Field(default=3, ge=1, le=5, description="1 = highest priority")
    reasoning: str = ""


class AuditPlan(BaseModel):
    page_type_signature: str
    conformance_level: ConformanceLevel
    plan_reasoning: str
    steps: list[PlanStepSchema]


# ── Execute ──────────────────────────────────────────────────────────────

class StepResultSchema(BaseModel):
    status: StepStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


# ── Reflect / Learn ──────────────────────────────────────────────────────

class Contradiction(BaseModel):
    plan_step_id: int
    memory_pattern: str
    note: str


class Lesson(BaseModel):
    page_type_signature: str
    wcag_rule_id: str
    pattern_description: str
    outcome_pattern: OutcomePattern
    action: LearnAction
    reason: str


class Reflection(BaseModel):
    summary: str
    low_confidence_plan_step_ids: list[int] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    deduplication_notes: list[str] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)
