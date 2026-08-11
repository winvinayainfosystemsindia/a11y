"""
System/user prompt templates for the PLAN stage. Plain string-building
functions (no template engine dependency) - the planner prompt is built
once per run from a PageSnapshot and a MemoryContext.
"""
from __future__ import annotations

import json

from app.ai.prompts.judgment_prompts import JUDGMENT_KIND_DESCRIPTIONS
from app.ai.schemas import MemoryContext, PageSnapshot
from app.utils.wcag_criteria import ELEMENT_TYPES, PRINCIPLE_ORDER, criteria_by_principle

AVAILABLE_TOOLS = {
    "axe": "Deterministic axe-core rule checks (alt text presence, ARIA validity, heading structure, landmarks, "
    "form labels, language attributes, ...). Set target_element.axe_rule_ids to a list of axe rule ids when known.",
    "contrast": "Deterministic color-contrast ratio calculation. Set target_element.selector to ONE specific "
    "element's selector copied verbatim from a single contrast sample below (e.g. '#hero-heading' or "
    "'p:nth-of-type(3)') - never a comma-separated list of tags/selectors ('button, p, span' is INVALID: it "
    "measures whichever one of those the browser happens to match first, not a specific element) and never a bare "
    "tag name shared by many elements. One PlanStep per sample you want checked. Omit target_element.selector "
    "entirely only to let the tool pick the single worst-contrast sample automatically.",
    "keyboard_nav": "Deterministic Tab-order/focus-trap simulation across the whole page. Use at most once per run.",
    "screenshot": "Captures visual evidence for a finding. Set target_element.selector for an element screenshot, "
    "or omit for a full-page screenshot.",
}

_PRINCIPLE_FRAMING = {
    "Perceivable": "Can information and UI components be perceived - is anything conveyed only visually, only "
    "audibly, or only through color/shape, with no text/programmatic equivalent a screen reader can announce?",
    "Operable": "Can UI components and navigation actually be operated - by keyboard alone, without traps, "
    "without unpredictable focus changes, and with enough time/control over motion and timing?",
    "Understandable": "Is information and the operation of the UI understandable - readable language, "
    "predictable behavior, and clear identification/recovery for input errors?",
    "Robust": "Is content robust enough to be reliably interpreted by assistive technology - valid markup and "
    "correct accessible name/role/value/state for every custom or non-native UI component?",
}


def build_planner_system_prompt(conformance_level: str) -> str:
    grouped = criteria_by_principle(conformance_level)
    principles_block = "\n\n".join(
        f'### {principle} - {_PRINCIPLE_FRAMING[principle]}\n'
        + "\n".join(f"- {sc_id} {name}" for sc_id, name in grouped[principle])
        for principle in PRINCIPLE_ORDER
        if grouped[principle]
    )
    tools_block = "\n".join(f"- {name}: {desc}" for name, desc in AVAILABLE_TOOLS.items())
    judgment_kinds_block = "\n".join(f"- {kind}: {desc}" for kind, desc in JUDGMENT_KIND_DESCRIPTIONS.items())
    element_types_block = "\n".join(f"- {element_type}" for element_type in ELEMENT_TYPES)

    return f"""You are a certified accessibility professional (in the manner of an IAAP CPACC/WAS-credentialed \
auditor) planning a WCAG {conformance_level} conformance audit of a web page. Given a snapshot of the page and \
relevant memory from past audits, produce a complete, ordered set of test cases (the audit plan).

## Methodology
This audit is organized around WCAG's four principles - Perceivable, Operable, Understandable, Robust (POUR) - \
and every test case must be evaluated primarily through the lens of a real assistive-technology user, not just \
automated DOM presence. Specifically:
- Default to testing as a screen reader user (NVDA/JAWS/VoiceOver) would experience the page: what gets \
announced, in what order, and whether that's enough to understand and operate the page without sight.
- A check that only verifies markup is "technically present" (e.g. an alt attribute exists) is not sufficient on \
its own where the actual content of that markup matters (e.g. whether the alt text is meaningful) - plan a \
judgment step for the qualitative half of a check whenever the deterministic tool can only verify presence.
- Also consider keyboard-only operation (no mouse), and cognitive/understandability factors (clear language, \
predictable behavior, adequate time).

## Mandatory WCAG {conformance_level} success criteria, grouped by principle
Every one of these MUST be covered by at least one test case (a step can legitimately conclude "not applicable \
to this page" via its target_element, but it must not be omitted from the plan entirely):

{principles_block}

## Per-element enumeration (mandatory — this is what makes the report specific instead of generic)
Do NOT write one generic test case per WCAG criterion that silently covers "the page" as a whole. For any \
criterion that applies to a concrete, enumerable set of elements, create ONE PlanStep PER ACTUAL ELEMENT INSTANCE \
found in the Structure data below, each with its own title and target_element naming that specific element. \
Concretely:
- **Headings** (WCAG 1.3.1, 2.4.6, 2.4.1/2.4.10 navigation): create one step that evaluates the *overall* heading \
hierarchy (e.g. "Heading hierarchy: h1 > h2 > h2 > h3 ..." using the real levels/text in order, flagging any \
skipped level), AND if any individual heading's text is vague/unhelpful or its level looks structurally wrong, \
create an additional step per such heading with the title naming its real level and text, e.g. "H2 'Our Services' \
- heading text does not describe the section that follows". Put {{selector, level, text}} from that heading into \
target_element.
- **Images** (WCAG 1.1.1): create one step per image in the Images list (or per distinct src if there are near-\
duplicates), with the title naming the actual image, e.g. "Hero banner image (hero.jpg) missing alt text" or \
"Logo image alt text quality". Put {{selector, src, alt_text, context}} into target_element.
- **Form fields** (WCAG 1.3.1, 3.3.2, 4.1.2): create one step per field in the Forms list, titled with its real \
label/placeholder/type, e.g. "Email input has no visible label" or "'Promo code' text field placeholder used as \
the only label". Put {{selector, tag, input_type, label_text, placeholder}} into target_element.
- **Links** (WCAG 2.4.4): when the HTML excerpt or context surfaces vague link text ("click here", "read more", \
bare URLs), create one step per such link naming its actual text, e.g. "'Click here' link (near pricing section) \
- purpose unclear out of context". Put {{selector or text, context}} into target_element.
- **Landmarks/skip link/page title/language** (WCAG 2.4.1, 2.4.2, 3.1.1, 1.3.1 navigation): these are legitimately \
whole-page checks (there's only one instance to check) - one step each is correct, use element_type "General Page" \
or "Navigation / Landmarks / Page Structure".
- **Contrast, keyboard/focus order, custom widgets, dynamic status messages**: one step per distinct component/\
sample rather than one blanket page-wide step, using the concrete selector/text already provided in the Structure \
data (contrast samples, etc.) so each failure can be traced to one real element.
Every target_element you set must contain enough concrete, real data (selector, actual text/alt/label, level) \
that someone reading only the test case row - without opening the browser - knows exactly which element on the \
page it refers to. Never leave target_element as just a restated WCAG criterion name.

## Each test case (PlanStep) needs:
- `title`: a short, SPECIFIC test case name naming the actual element/component under test - e.g. "Search icon \
button has no accessible name", not a generic restatement of the WCAG criterion name. This is what a human \
reviewer sees first in the test case list, so make it identify exactly what's being checked.
- `wcag_criterion` / `level`: the success criterion this test case verifies.
- `method`: "tool" for a deterministic, objective check, or "llm" for a judgment call requiring understanding of \
meaning, context, or the assistive-technology experience.
- `target_element`: structured details the check needs (see below).
- `element_type`: exactly one of the categories below - the kind of page element this test case actually \
targets (not a restatement of the WCAG criterion). Pick the closest match to what's really on the page; use \
"General Page" only when no specific element/component is involved (e.g. a whole-page language or title check):
{element_types_block}
- `priority` (1 = highest, 5 = lowest) and `reasoning` (why this test case matters / why this priority).

### method="tool" - set tool_name to one of:
{tools_block}

### method="llm" - set target_element.judgment_kind to the best match, so the check is asked a properly scoped \
question instead of a generic one:
{judgment_kinds_block}
If none of these fit, omit judgment_kind and instead set target_element.description to a specific, concrete \
description of what to evaluate and why - never a vague restatement of the criterion name.

## Prioritization (priority 1 = highest, 5 = lowest)
- If memory shows a WCAG rule usually fails for pages structurally similar to this one, prioritize it (lower \
priority number) and note that in `reasoning` - this is what makes the agent get better over time.
- If memory shows a rule usually passes for this page type, it can still be included but at lower priority.
- Never skip a mandatory criterion just because memory suggests it usually passes - always verify.

Order steps so related checks run together (e.g. all image/alt-text checks, then all form checks, then keyboard/\
focus/screen-reader-navigation checks), and so tool-based checks generally precede llm-judgment checks that might \
reference their output.

Output ONLY the structured JSON plan matching the provided schema - no free text, no markdown."""


def build_planner_user_message(snapshot: PageSnapshot, memory: MemoryContext) -> str:
    parts: list[str] = []

    parts.append(f"## Page\nURL: {snapshot.url}\nTitle: {snapshot.title or '(none)'}\n"
                 f"Detected page type signature: {snapshot.page_type_signature}\n"
                 f"HTML lang attribute: {snapshot.lang_attribute or '(missing)'}\n"
                 f"Has skip link: {snapshot.has_skip_link}")

    parts.append("## Structure")
    parts.append(f"Landmarks: {', '.join(snapshot.landmarks) or '(none detected)'}")
    parts.append(f"Headings: {json.dumps([h.model_dump() for h in snapshot.headings[:30]])}")
    parts.append(f"Images ({len(snapshot.images)} total, first 20): "
                 f"{json.dumps([i.model_dump() for i in snapshot.images[:20]])}")
    parts.append(f"Forms ({len(snapshot.forms)} total): "
                 f"{json.dumps([[f.model_dump() for f in form] for form in snapshot.forms[:5]])}")
    parts.append(f"Links: {snapshot.links_count} | Interactive elements: {snapshot.interactive_elements_count}")

    if snapshot.contrast_samples:
        parts.append(
            f"Pre-sampled text/background color pairs ({len(snapshot.contrast_samples)}): "
            f"{json.dumps([c.model_dump() for c in snapshot.contrast_samples[:20]])}"
        )

    if not memory.is_empty():
        parts.append("## Memory from past audits (use this to prioritize, never to skip mandatory criteria)")
        if memory.exact_url_history:
            parts.append(f"Past audits of this exact page: {json.dumps(memory.exact_url_history)}")
        if memory.similar_page_findings:
            parts.append(
                f"Patterns from structurally similar pages (by similarity): "
                f"{json.dumps(memory.similar_page_findings)}"
            )
        if memory.rule_specific_patterns:
            parts.append(
                f"Known rule-specific patterns for this exact page type: "
                f"{json.dumps(memory.rule_specific_patterns)}"
            )
    else:
        parts.append("## Memory\nNo prior memory for this page or page type yet - treat every criterion as unknown.")

    parts.append("\nA trimmed HTML excerpt follows for additional context:\n" + snapshot.html_excerpt[:6000])

    return "\n\n".join(parts)
