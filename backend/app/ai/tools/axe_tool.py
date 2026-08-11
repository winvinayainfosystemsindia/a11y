"""
Deterministic WCAG rule checks via axe-core. Wraps axe-playwright-python so
the rest of the agent (planner/executor) never touches axe-core's JS API
directly - only this normalized, plain-dict shape.
"""
from __future__ import annotations

from axe_playwright_python.async_playwright import Axe
from playwright.async_api import Page

_axe = Axe()


async def run_axe(
    page: Page,
    *,
    rule_ids: list[str] | None = None,
    context_selector: str | None = None,
) -> list[dict]:
    """Run axe-core against `page`. `rule_ids` scopes the run to specific
    axe rules (much faster and more precise than running the full ruleset
    and filtering afterwards); `context_selector` scopes to a DOM subtree."""
    options: dict = {"resultTypes": ["violations"]}
    if rule_ids:
        options["runOnly"] = {"type": "rule", "values": rule_ids}

    results = await _axe.run(page, context=context_selector, options=options)

    violations: list[dict] = []
    for violation in results.response.get("violations", []):
        violations.append(
            {
                "rule_id": violation.get("id"),
                "impact": violation.get("impact"),
                "description": violation.get("description"),
                "help": violation.get("help"),
                "help_url": violation.get("helpUrl"),
                "tags": violation.get("tags", []),
                "nodes": [
                    {
                        "html": node.get("html"),
                        "target": node.get("target"),
                        "failure_summary": node.get("failureSummary"),
                    }
                    for node in violation.get("nodes", [])
                ],
            }
        )
    return violations
