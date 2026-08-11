from __future__ import annotations
import types
import pytest
from app.controllers.audit_controller import (
    _build_defects,
    _build_test_cases,
    _description,
    _element_label,
    _find_relevant_violation,
    _html_snippet,
    _suggestion_to_fix,
)
from app.models.audit_run import AuditRun
from app.models.crawled_page import CrawledPage
from app.models.plan_step import PlanStep
from app.models.step_result import StepResult
from app.models.project import Project


def _axe_ev(rule_id, description, node_html, selector):
    return {
        "violations": [{
            "rule_id": rule_id, "impact": "serious",
            "description": description, "help": rule_id,
            "nodes": [{"html": node_html, "target": [selector], "failure_summary": rule_id}],
        }]
    }


def _kbd_ev():
    return {"stop_count": 12, "trap_detected": True, "reordering_flags": [], "invisible_focus_targets": []}


@pytest.fixture()
def audit_run(db_session):
    project = Project(user_id=1, name="Test", base_url="https://example.com")
    db_session.add(project); db_session.commit(); db_session.refresh(project)
    page = CrawledPage(project_id=project.id, url="https://example.com/", page_title="Home")
    db_session.add(page); db_session.commit(); db_session.refresh(page)
    run = AuditRun(project_id=project.id, page_id=page.id, status="completed", conformance_level="AA")
    db_session.add(run); db_session.commit(); db_session.refresh(run)

    defs = [
        (1, "Anoop Profile image missing alt text", "1.1.1", "tool", "axe",
         "Images / Icons / Image Buttons",
         {"axe_rule_ids": ["image-alt"], "selector": "img.anoop"},
         _axe_ev("image-alt", "Images must have alternate text",
                 "<img src=/img/Anoop_Profile.png class=anoop>", "img.anoop")),
        (2, "Great Place to Work badge missing alt text", "1.1.1", "tool", "axe",
         "Images / Icons / Image Buttons",
         {"axe_rule_ids": ["image-alt"], "selector": "img.gptw"},
         _axe_ev("image-alt", "Images must have alternate text",
                 "<img src=/img/gptw_badge.png class=gptw>", "img.gptw")),
        (3, "Skip link check", "2.4.1", "tool", "axe",
         "Navigation / Menus / Skip Links",
         {"axe_rule_ids": ["skip-link"], "selector": ".skip-link"},
         _axe_ev("skip-link", "Page must have skip links",
                 '<a href="#main-content" class="skip-link">Skip to content</a>', ".skip-link")),
        (4, "Keyboard focus trap check", "2.1.2", "tool", "keyboard_nav",
         "Navigation / Menus / Skip Links",
         {"description": "entire page keyboard navigation"}, _kbd_ev()),
        (5, "Nav menu ARIA name and role check", "4.1.2", "llm", None,
         "Navigation / Menus / Skip Links",
         {"description": "primary navigation menu", "selector": "nav#main-nav"},
         {"html": "<nav id=main-nav>...</nav>"}),
    ]

    steps = []
    for order, title, crit, method, tool, etype, target, evidence in defs:
        step = PlanStep(
            audit_run_id=run.id, step_order=order, title=title,
            wcag_criterion=crit,
            level="A" if crit in ("1.1.1", "2.1.2") else "AA",
            method=method, tool_name=tool, element_type=etype,
            target_element=target, priority=2,
        )
        db_session.add(step); db_session.commit(); db_session.refresh(step)
        result = StepResult(
            plan_step_id=step.id, status="fail", confidence=1.0,
            evidence=evidence, reasoning="Failed: " + title,
        )
        db_session.add(result); db_session.commit(); db_session.refresh(step)
        steps.append(step)
    return run, steps, page


@pytest.fixture()
def rows(audit_run):
    run, steps, page = audit_run
    run.page = page
    return _build_test_cases(run, steps, page.page_title or "", page.url)


def test_no_duplicate_description(rows):
    """No two rows with different tc_name share the same Description string."""
    seen = {}
    for r in rows:
        name, desc = r["tc_name"], r["description"]
        for oname, odesc in seen.items():
            if oname != name:
                assert desc != odesc, "Desc collision: " + name + " vs " + oname + "\n" + desc
        seen[name] = desc


def test_no_duplicate_actual_result(rows):
    """No two rows with different tc_name share the same Actual Result string."""
    seen = {}
    for r in rows:
        name, actual = r["tc_name"], r["actual_result"]
        for oname, oactual in seen.items():
            if oname != name:
                assert actual != oactual, "Actual collision: " + name + " vs " + oname
        seen[name] = actual


def test_no_empty_rule_id_in_actual_result(rows):
    """Actual Result must not contain the empty-rule-ID artifact.
    This catches violations[0].get("id") vs correct key "rule_id".
    """
    marker = "rule '' reports"
    for r in rows:
        actual = r["actual_result"]
        assert marker not in actual, "Empty rule ID found in: " + r["tc_name"] + "\n" + actual[:120]


def test_image_rows_reference_their_own_element(rows):
    """Each image row must reference its own image element, not another row's."""
    img = [r for r in rows if "alt" in r["tc_name"].lower() or "badge" in r["tc_name"].lower()]
    assert len(img) >= 2
    descs = [r["description"] for r in img]
    assert len(set(descs)) == len(descs), "Image rows share descriptions: " + str(descs)
    for r in img:
        snip = r.get("html_snippet") or ""
        if "Anoop" in r["tc_name"]:
            assert "Anoop" in r["description"] or "Anoop" in snip, (
                "Anoop row missing ref: " + r["description"][:80])
        if "badge" in r["tc_name"].lower() or "Great Place" in r["tc_name"]:
            assert "gptw" in r["description"] or "gptw" in snip, (
                "Badge row missing ref: " + r["description"][:80])


def test_skip_link_does_not_contaminate_others(rows):
    """The skip-link HTML must not appear in non-skip-link rows Description."""
    for r in rows:
        if "skip" not in r["tc_name"].lower():
            assert "skip-link" not in r["description"].lower(), (
                "skip-link contaminating: " + r["tc_name"])


def test_html_snippet_consistent_with_description(rows):
    """html_snippet must be the same element as in Description (same violation node)."""
    for r in rows:
        snip = r.get("html_snippet")
        if not snip:
            continue
        key = snip[:30]
        assert key in r["description"], (
            "HTML snippet not in description for " + r["tc_name"] +
            ": snippet=" + snip[:60])


# ---- unit tests for _find_relevant_violation --------------------------------

def _s(**kw):
    """SimpleNamespace avoids SQLAlchemy ORM initialisation."""
    d = {"target_element": {}, "tool_name": "axe", "element_type": "General Page", "wcag_criterion": None, "title": ""}
    d.update(kw)
    return types.SimpleNamespace(**d)


def test_frv_matches_axe_rule_id():
    """Must return violation matching axe_rule_ids, not violations[0]."""
    ev = {"violations": [
        {"rule_id": "color-contrast", "nodes": [{"html": "<p>Low</p>", "target": [".low"]}]},
        {"rule_id": "image-alt",      "nodes": [{"html": "<img src=p.png>", "target": ["img.p"]}]},
        {"rule_id": "skip-link",      "nodes": [{"html": "<a class=s>Skip</a>", "target": [".s"]}]},
    ]}
    v = _find_relevant_violation(_s(target_element={"axe_rule_ids": ["image-alt"]}), ev)
    assert v is not None and v["rule_id"] == "image-alt"
    assert "p.png" in v["nodes"][0]["html"]


def test_frv_falls_back_to_selector():
    """When axe_rule_ids absent, match by selector in node targets."""
    ev = {"violations": [
        {"rule_id": "color-contrast", "nodes": [{"html": "<p>", "target": [".low"]}]},
        {"rule_id": "image-alt",      "nodes": [{"html": "<img src=g.png>", "target": ["img.gptw"]}]},
    ]}
    v = _find_relevant_violation(_s(target_element={"selector": "img.gptw"}), ev)
    assert v is not None and v["rule_id"] == "image-alt"


def test_frv_returns_none_when_no_match():
    """When no rule_id/selector/mapping-table match, return None - never
    substitute an unrelated violation like violations[0]. This is the bug:
    the old fallback stamped whatever was first in `violations` (often
    color-contrast) onto rows it has nothing to do with."""
    ev = {"violations": [
        {"rule_id": "color-contrast", "nodes": [{"html": "<p>", "target": [".low"]}]},
        {"rule_id": "image-alt",      "nodes": [{"html": "<img>", "target": ["img"]}]},
    ]}
    step = _s(target_element={"description": "keyboard"}, wcag_criterion="2.1.4")  # no axe rule maps to 2.1.4
    v = _find_relevant_violation(step, ev)
    assert v is None


def test_frv_backstops_with_wcag_mapping_table_when_axe_rule_ids_missing():
    """When the planner LLM forgot to set target_element.axe_rule_ids, the
    deterministic WCAG->axe mapping table (Strategy 1.5) must still find the
    right violation by the step's wcag_criterion alone."""
    ev = {"violations": [
        {"rule_id": "region",         "nodes": [{"html": "<div>", "target": [".r"]}]},
        {"rule_id": "html-has-lang",  "nodes": [{"html": "<html>", "target": ["html"]}]},
    ]}
    step = _s(target_element={}, wcag_criterion="3.1.1")  # Language of Page -> html-has-lang
    v = _find_relevant_violation(step, ev)
    assert v is not None and v["rule_id"] == "html-has-lang"


def test_frv_none_when_empty():
    step = _s()
    assert _find_relevant_violation(step, {}) is None
    assert _find_relevant_violation(step, {"violations": []}) is None


def test_ai_judgment_description_uses_specific_instance_not_generic_category():
    """Description for a needs_review/AI-judgment row must name the specific
    element instance (already available via plan_step.title, the same value
    used for Test Case Name), not fall back to the generic element_type
    taxonomy category - e.g. 'Anoop's profile photo', not 'Images / Icons /
    Image Buttons'."""
    step = _s(
        wcag_criterion="1.1.1",
        method="llm",
        tool_name=None,
        title="Anoop's profile photo missing alt text",
        element_type="Images / Icons / Image Buttons",
        target_element={},  # no per-instance description/selector supplied
    )
    desc = _description(step, {}, None)
    assert "Anoop's profile photo" in desc
    assert "Images / Icons / Image Buttons" not in desc


# ---- end-to-end regression test (Section 3 of the bug report) --------------
#
# A single mocked axe-core `violations` array with 3 unrelated rule ids, fed
# as the SAME evidence to 3 test cases each targeting a different one of
# those rules (simulating the worst case: a page-global/unscoped axe run
# whose results got attached to every row). Before this fix, every row's
# Actual Result would report whichever violation happened to be first in the
# array (or, after the first attempted fix, one of only two rule ids) -
# regardless of that row's own Criteria. This test would have caught both
# the v1 (empty rule id) and v2 (color-contrast/region for everything) bugs.

@pytest.fixture()
def contaminated_evidence():
    """One evidence blob containing 3 unrelated violations - stands in for
    an unscoped axe run whose results get reused across rows."""
    return {
        "violations": [
            {"rule_id": "color-contrast", "impact": "serious", "description": "Contrast too low", "help": "color-contrast",
             "nodes": [{"html": "<p class=low>Low contrast text</p>", "target": [".low"], "failure_summary": "color-contrast"}]},
            {"rule_id": "image-alt", "impact": "critical", "description": "Images must have alternate text", "help": "image-alt",
             "nodes": [{"html": "<img src=/logo.png class=logo>", "target": ["img.logo"], "failure_summary": "image-alt"}]},
            {"rule_id": "html-has-lang", "impact": "serious", "description": "html element must have a lang attribute", "help": "html-has-lang",
             "nodes": [{"html": "<html>", "target": ["html"], "failure_summary": "html-has-lang"}]},
        ]
    }


@pytest.fixture()
def cross_contamination_run(db_session, contaminated_evidence):
    project = Project(user_id=1, name="Cross-contam", base_url="https://example.com")
    db_session.add(project); db_session.commit(); db_session.refresh(project)
    page = CrawledPage(project_id=project.id, url="https://example.com/", page_title="Home")
    db_session.add(page); db_session.commit(); db_session.refresh(page)
    run = AuditRun(project_id=project.id, page_id=page.id, status="completed", conformance_level="AA")
    db_session.add(run); db_session.commit(); db_session.refresh(run)

    # 3 steps, each expecting a DIFFERENT one of the 3 rules in the shared
    # evidence blob, via the deterministic mapping table (no axe_rule_ids
    # set explicitly - proves the WCAG->axe backstop, not just an explicit hint).
    defs = [
        (1, "Body text contrast check", "1.4.3", {}),
        (2, "Logo image alt text check", "1.1.1", {}),
        (3, "Language of page check", "3.1.1", {}),
    ]
    steps = []
    for order, title, crit, target in defs:
        step = PlanStep(
            audit_run_id=run.id, step_order=order, title=title, wcag_criterion=crit,
            level="AA", method="tool", tool_name="axe", element_type="General Page",
            target_element=target, priority=2,
        )
        db_session.add(step); db_session.commit(); db_session.refresh(step)
        result = StepResult(
            plan_step_id=step.id, status="fail", confidence=1.0,
            evidence=contaminated_evidence, reasoning="Failed: " + title,
        )
        db_session.add(result); db_session.commit(); db_session.refresh(step)
        steps.append(step)

    run.page = page
    return _build_test_cases(run, steps, page.page_title or "", page.url)


def test_each_row_bound_to_its_own_expected_rule(cross_contamination_run):
    rows = {r["tc_name"]: r for r in cross_contamination_run}

    contrast_row = rows["Body text contrast check"]
    assert "color-contrast" in contrast_row["actual_result"]
    assert "image-alt" not in contrast_row["actual_result"]
    assert "html-has-lang" not in contrast_row["actual_result"]

    alt_row = rows["Logo image alt text check"]
    assert "image-alt" in alt_row["actual_result"]
    assert "color-contrast" not in alt_row["actual_result"]
    assert "html-has-lang" not in alt_row["actual_result"]

    lang_row = rows["Language of page check"]
    assert "html-has-lang" in lang_row["actual_result"]
    assert "color-contrast" not in lang_row["actual_result"]
    assert "image-alt" not in lang_row["actual_result"]


def test_element_label_names_specific_keyboard_nav_trap_stop():
    """A keyboard_nav finding must name the specific tab stop it flagged,
    not the generic 'entire page keyboard navigation' target description."""
    evidence = {
        "stops": [
            {"tag": "a", "selector": ".skip", "label": "Skip", "x": 0, "y": 0, "visible": True, "html": "<a class=skip>Skip</a>"},
            {"tag": "button", "selector": ".menu-toggle", "label": "Open menu", "x": 5, "y": 5, "visible": True, "html": "<button class=menu-toggle>"},
        ],
        "trap_detected": True,
        "reordering_flags": [],
        "invisible_focus_targets": [],
    }
    step = _s(target_element={"description": "entire page keyboard navigation"}, wcag_criterion="2.1.2", tool_name="keyboard_nav")
    label = _element_label(step, evidence, None)
    assert "menu-toggle" in label
    assert label != "entire page keyboard navigation"


def test_element_label_names_specific_reordering_target():
    evidence = {
        "stops": [],
        "trap_detected": False,
        "reordering_flags": [{
            "from": {"tag": "div", "selector": ".footer-link", "label": "Contact", "x": 0, "y": 500, "visible": True, "html": ""},
            "to": {"tag": "a", "selector": ".nav-link", "label": "Home", "x": 0, "y": 20, "visible": True, "html": "<a class=nav-link>Home</a>"},
            "note": "upward jump",
        }],
        "invisible_focus_targets": [],
    }
    step = _s(target_element={"description": "entire page keyboard navigation"}, wcag_criterion="2.4.3", tool_name="keyboard_nav")
    label = _element_label(step, evidence, None)
    assert "nav-link" in label


def test_element_label_rejects_compound_selector():
    """A comma-separated selector list names a set of elements, not one
    specific instance - must not be used verbatim as 'the element'."""
    step = _s(target_element={"selector": "button, p, span, h3, h4"}, wcag_criterion="1.4.3", title="Body text contrast check")
    label = _element_label(step, {}, None)
    assert label == "Body text contrast check"
    assert "," not in label


def test_html_snippet_uses_flagged_keyboard_stop_html():
    evidence = {
        "stops": [{"tag": "button", "selector": ".menu-toggle", "label": "", "x": 5, "y": 5, "visible": True, "html": "<button class=menu-toggle></button>"}],
        "trap_detected": True,
        "reordering_flags": [],
        "invisible_focus_targets": [],
    }
    assert _html_snippet(evidence, None) == "<button class=menu-toggle></button>"


def test_suggestion_to_fix_includes_measured_contrast_values():
    step = _s(wcag_criterion="1.4.3")
    evidence = {"ratio": 1.02, "required_ratio": 4.5, "foreground": "rgb(20,20,20)", "background": "rgb(25,25,25)"}
    suggestion = _suggestion_to_fix(step, "fail", evidence, None)
    assert "1.02" in suggestion
    assert "4.5" in suggestion
    assert "rgb(20,20,20)" in suggestion


def test_suggestion_to_fix_includes_axe_failure_summary():
    step = _s(wcag_criterion="1.4.3")
    violation = {"nodes": [{"failure_summary": "insufficient color contrast of 2.93 (foreground #767676, background #ffffff)"}]}
    suggestion = _suggestion_to_fix(step, "fail", {}, violation)
    assert "2.93" in suggestion


def test_suggestion_to_fix_names_keyboard_trap_element():
    step = _s(wcag_criterion="2.1.2")
    evidence = {
        "stops": [{"tag": "div", "selector": ".modal", "label": "", "x": 0, "y": 0, "visible": True, "html": ""}],
        "trap_detected": True, "reordering_flags": [], "invisible_focus_targets": [],
    }
    suggestion = _suggestion_to_fix(step, "fail", evidence, None)
    assert "modal" in suggestion


def test_suggestion_to_fix_falls_back_to_generic_hint_without_evidence():
    step = _s(wcag_criterion="1.4.3")
    assert "contrast" in _suggestion_to_fix(step, "fail", None, None).lower()


# ---- Defects sheet: confidence/verification_status must not conflate -------

def test_defects_verification_status_distinguishes_confirmed_from_needs_review(db_session):
    project = Project(user_id=1, name="Defect status", base_url="https://example.com")
    db_session.add(project); db_session.commit(); db_session.refresh(project)
    page = CrawledPage(project_id=project.id, url="https://example.com/", page_title="Home")
    db_session.add(page); db_session.commit(); db_session.refresh(page)
    run = AuditRun(project_id=project.id, page_id=page.id, status="completed", conformance_level="AA")
    db_session.add(run); db_session.commit(); db_session.refresh(run)

    defs = [
        (1, "Confirmed axe failure", "1.1.1", "tool", "axe", {"axe_rule_ids": ["image-alt"]},
         _axe_ev("image-alt", "Images must have alternate text", "<img>", "img"), "fail"),
        (2, "Ambiguous AI judgment", "3.3.1", "llm", None, {}, {}, "needs_review"),
    ]
    steps = []
    for order, title, crit, method, tool, target, evidence, status in defs:
        step = PlanStep(
            audit_run_id=run.id, step_order=order, title=title, wcag_criterion=crit,
            level="A", method=method, tool_name=tool, element_type="General Page",
            target_element=target, priority=2,
        )
        db_session.add(step); db_session.commit(); db_session.refresh(step)
        result = StepResult(plan_step_id=step.id, status=status, confidence=1.0 if status == "fail" else 0.4,
                             evidence=evidence, reasoning="x")
        db_session.add(result); db_session.commit(); db_session.refresh(step)
        steps.append(step)

    run.page = page
    rows = _build_test_cases(run, steps, page.page_title or "", page.url)
    defects = _build_defects(rows, steps)
    confirmed = next(d for d in defects if d["status"] == "fail")
    review = next(d for d in defects if d["status"] == "needs_review")
    assert confirmed["verification_status"] == "Confirmed"
    assert review["verification_status"] == "AI Judgment - Needs Review"
    assert confirmed["verification_status"] != review["verification_status"]
    # confidence must be present per-row, not dropped between test cases and defects
    assert confirmed["confidence"] == 1.0
    assert review["confidence"] == 0.4


def test_no_axe_rule_id_appears_for_more_rows_than_it_actually_covers(cross_contamination_run):
    """No single axe rule id (e.g. color-contrast) may be bound to more test
    cases than are genuinely about that rule - each of the 3 rows here is
    about a different rule, so each rule id may appear in at most 1 row's
    Actual Result."""
    import re
    counts: dict[str, int] = {}
    for r in cross_contamination_run:
        m = re.search(r"Axe-core rule '([^']+)' reports", r["actual_result"])
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    for rule_id, count in counts.items():
        assert count == 1, f"rule {rule_id!r} bound to {count} rows, expected exactly 1"
