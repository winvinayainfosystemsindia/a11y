"""Write the regression test file for the data-binding bug fix."""
import pathlib

TEST = '''\
from __future__ import annotations
import types
import pytest
from app.controllers.audit_controller import _build_test_cases, _find_relevant_violation
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
                assert desc != odesc, "Desc collision: " + name + " vs " + oname + "\\n" + desc
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
        assert marker not in actual, "Empty rule ID found in: " + r["tc_name"] + "\\n" + actual[:120]


def test_image_rows_reference_their_own_element(rows):
    """Each image row must reference its own image element, not another row\'s."""
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
    d = {"target_element": {}, "tool_name": "axe", "element_type": "General Page"}
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


def test_frv_returns_first_when_no_match():
    """When no rule_id or selector match, the first violation is the fallback."""
    ev = {"violations": [
        {"rule_id": "color-contrast", "nodes": [{"html": "<p>", "target": [".low"]}]},
        {"rule_id": "image-alt",      "nodes": [{"html": "<img>", "target": ["img"]}]},
    ]}
    v = _find_relevant_violation(_s(target_element={"description": "keyboard"}), ev)
    assert v is not None and v["rule_id"] == "color-contrast"


def test_frv_none_when_empty():
    step = _s()
    assert _find_relevant_violation(step, {}) is None
    assert _find_relevant_violation(step, {"violations": []}) is None
'''

out = pathlib.Path("tests/test_report_field_binding.py")
out.write_text(TEST, encoding="utf-8")
print(f"Written {out} ({out.stat().st_size} bytes, {TEST.count(chr(10))} lines)")
