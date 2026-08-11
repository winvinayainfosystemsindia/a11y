"""Unit tests for app.ai.planner._harden_axe_rule_ids - the deterministic
backstop that grounds each axe-tagged plan step's target_element.axe_rule_ids
in WCAG_TO_AXE_RULES, or demotes the step to an LLM judgment call when axe
has no rule for that criterion at all."""
from app.ai.planner import _harden_axe_rule_ids
from app.ai.schemas import AuditPlan, PlanStepSchema


def _plan(*steps: PlanStepSchema) -> AuditPlan:
    return AuditPlan(
        page_type_signature="generic", conformance_level="AA", plan_reasoning="", steps=list(steps),
    )


def test_demotes_axe_step_with_no_axe_coverage_to_llm():
    """2.1.4 (Character Key Shortcuts) has no axe-core rule - a step the
    planner mistakenly tagged as method='tool'/tool_name='axe' for it must
    be converted to an LLM judgment step, not executed as an unscoped axe run."""
    step = PlanStepSchema(
        title="Character key shortcuts check", wcag_criterion="2.1.4", level="A",
        method="tool", tool_name="axe", target_element={},
    )
    plan = _plan(step)
    _harden_axe_rule_ids(plan)
    assert plan.steps[0].method == "llm"
    assert plan.steps[0].tool_name is None


def test_fills_in_axe_rule_ids_when_missing():
    step = PlanStepSchema(
        title="Language of page check", wcag_criterion="3.1.1", level="A",
        method="tool", tool_name="axe", target_element={},
    )
    plan = _plan(step)
    _harden_axe_rule_ids(plan)
    assert plan.steps[0].method == "tool"
    assert set(plan.steps[0].target_element["axe_rule_ids"]) == {"html-has-lang", "html-lang-valid", "html-xml-lang-mismatch"}


def test_corrects_wrong_axe_rule_id_guess():
    """Model guessed a rule id ('region') that has nothing to do with 4.1.2
    (Name, Role, Value) - must be replaced with the correct rule set, not
    left in place to later mis-bind a violation."""
    step = PlanStepSchema(
        title="Name role value accessibility check", wcag_criterion="4.1.2", level="A",
        method="tool", tool_name="axe", target_element={"axe_rule_ids": ["region"]},
    )
    plan = _plan(step)
    _harden_axe_rule_ids(plan)
    assert "region" not in plan.steps[0].target_element["axe_rule_ids"]
    assert "button-name" in plan.steps[0].target_element["axe_rule_ids"]


def test_keeps_correct_axe_rule_id_and_drops_unrelated_extras():
    step = PlanStepSchema(
        title="Contrast check", wcag_criterion="1.4.3", level="AA",
        method="tool", tool_name="axe",
        target_element={"axe_rule_ids": ["color-contrast", "region"]},
    )
    plan = _plan(step)
    _harden_axe_rule_ids(plan)
    assert plan.steps[0].target_element["axe_rule_ids"] == ["color-contrast"]


def test_llm_steps_untouched():
    step = PlanStepSchema(
        title="Focus order review", wcag_criterion="2.4.3", level="A",
        method="llm", target_element={"description": "the modal dialog"},
    )
    plan = _plan(step)
    _harden_axe_rule_ids(plan)
    assert plan.steps[0].method == "llm"
    assert plan.steps[0].target_element == {"description": "the modal dialog"}
