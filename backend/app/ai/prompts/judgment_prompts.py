"""
Prompt templates for LLM judgment-based checks. Each judgment call executor.py
makes is scoped to exactly one question about one element - never a full-page
prompt - so reasoning stays traceable and cost/latency stay low. The planner
sets `target_element.judgment_kind` to pick a specialized question; unknown
kinds fall back to a generic one built from the WCAG criterion + description.

Every question is framed from the perspective of someone actually operating
the page with assistive technology (a screen reader such as NVDA, JAWS, or
VoiceOver) - not just "is the markup technically present", but "does the
resulting experience actually work non-visually". That framing is what the
user-facing audit is graded on, so it lives in the system prompt itself
rather than being repeated per question.
"""
from __future__ import annotations

JUDGMENT_SYSTEM_PROMPT_TEMPLATE = """You are a certified accessibility professional (in the manner of an IAAP \
CPACC/WAS-credentialed auditor) making one focused, expert judgment call as part of a WCAG {level} conformance \
audit. You are answering exactly one narrow question about one specific part of a page - you are not running a \
full audit and should not comment on anything outside the question asked.

Ground every judgment in how the page actually behaves for a person using assistive technology, primarily a \
screen reader (NVDA, JAWS, or VoiceOver). Ask yourself: if I closed my eyes and navigated this with only what a \
screen reader announces - the accessible name, role, state, and reading order - would I get the same information \
and be able to complete the same task as a sighted mouse user? Markup that is technically present but produces a \
confusing, misleading, or silent experience for a screen reader user is a failure, even if an automated DOM-only \
check would call it a pass. Conversely, do not fail something for a cosmetic reason that has no real effect on \
the assistive-technology experience.

Be decisive. If you are genuinely unsure, reflect that with a lower confidence score rather than hedging in the \
reasoning text - a confident wrong answer is worse than an honest low-confidence one, but a low-confidence "I \
don't know" on every step is not useful either.

Respond with ONLY a JSON object, no markdown fences, no extra text, in exactly this shape:
{{"status": "pass" | "fail" | "needs_review", "confidence": <number 0.0-1.0>, "reasoning": "<1-3 sentences \
explaining the verdict, referencing the screen-reader experience specifically where relevant>", "evidence": \
{{<any short supporting details worth keeping, e.g. the text you evaluated or what a screen reader would announce>}}}}
"""


def build_judgment_system_prompt(conformance_level: str) -> str:
    return JUDGMENT_SYSTEM_PROMPT_TEMPLATE.format(level=conformance_level)


def build_judgment_user_message(*, wcag_criterion: str, question: str, target_html: str, page_context: str) -> str:
    return (
        f"## WCAG criterion\n{wcag_criterion}\n\n"
        f"## Question\n{question}\n\n"
        f"## Relevant HTML\n{target_html or '(not available)'}\n\n"
        f"## Page context\n{page_context or '(none)'}\n\n"
        "Answer now with the JSON object described in the system prompt."
    )


def alt_text_question(alt_text: str | None, image_context: str) -> str:
    if not alt_text:
        return (
            "This image has no alt attribute at all (or an empty one). A screen reader will either announce the "
            "raw filename or skip the image entirely. Confirm this is a genuine failure of WCAG 1.1.1 rather than "
            f"a decorative image that should legitimately have alt=\"\" (in which case it correctly produces "
            f"silence for a screen reader user). Context: {image_context}"
        )
    return (
        f'A screen reader will announce this image\'s alt text as: "{alt_text}". Does that meaningfully convey '
        f"the image's content or purpose in context, per WCAG 1.1.1 - not just present, but genuinely useful to "
        f"someone who cannot see the image and is relying entirely on what gets announced? "
        f"Context: {image_context}"
    )


def error_message_question(error_text: str, field_context: str) -> str:
    return (
        f'A screen reader user submits this form and needs to know what went wrong. Is this error message '
        f'("{error_text}") understandable and actionable per WCAG 3.3.1/3.3.3 - specific about which field and '
        f"what to fix, not just present? Also consider whether the error would actually be announced to a screen "
        f"reader user at all (e.g. via aria-live, role=\"alert\", or programmatic association with the field) "
        f"rather than only being visible as styled text - see WCAG 4.1.3 Status Messages. "
        f"Field context: {field_context}"
    )


def focus_order_question(sequence_summary: str) -> str:
    return (
        "Given this simulated Tab-key focus order (each stop's tag, label, and position), does it follow a "
        f"logical reading/visual order per WCAG 2.4.3, so a keyboard user's mental model of the page stays "
        f"coherent as they tab through it? Sequence: {sequence_summary}"
    )


def link_purpose_question(link_text: str, surrounding_context: str) -> str:
    return (
        f'A screen reader user often browses a page\'s links out of context (e.g. via a links list). Is this '
        f'link\'s purpose clear from its link text alone (or together with its immediate surrounding context), '
        f'per WCAG 2.4.4? A link that only says "click here" or "read more" fails this even if the surrounding '
        f'paragraph makes it obvious visually. Link text: "{link_text}". Surrounding context: {surrounding_context}'
    )


def reading_order_question(dom_order_summary: str, visual_order_summary: str) -> str:
    return (
        "A screen reader reads content in DOM order, not visual/CSS order. Given the DOM order of this content "
        f"({dom_order_summary}) versus how it's laid out visually ({visual_order_summary}), would a screen "
        f"reader user hear this content in a sequence that still makes sense, per WCAG 1.3.2 Meaningful Sequence? "
        "Flag it if CSS positioning/ordering has made the visual and DOM reading order diverge in a way that "
        "would confuse someone who can only hear the DOM order."
    )


def landmark_and_heading_question(landmarks_summary: str, headings_summary: str, target_description: str) -> str:
    return (
        "Screen reader users typically navigate a page by jumping between landmarks (banner, navigation, main, "
        "contentinfo, ...) and headings, rather than reading linearly. Given the landmarks on this page "
        f"({landmarks_summary}) and headings ({headings_summary}), can a screen reader user efficiently discover "
        f"and reach {target_description} this way, per WCAG 1.3.1 / 2.4.1 / 2.4.6? Flag missing landmarks, a "
        "missing or misplaced <main>, or a heading structure that skips levels or doesn't describe the content "
        "that follows it."
    )


def name_role_value_question(element_description: str, expected_name: str, expected_role: str) -> str:
    return (
        f"For this UI component ({element_description}), a screen reader announces only its accessible name, "
        f"role, and state - not how it looks. It should announce something like a {expected_role} named "
        f'"{expected_name}", including its current state (e.g. pressed/expanded/checked/selected) if applicable. '
        "Does the actual accessible name/role/state exposed to assistive technology match what a sighted user "
        "would understand from looking at it, per WCAG 4.1.2 Name, Role, Value? Flag a custom widget (e.g. a "
        "<div> styled as a button or a JS-built dropdown) that lacks the ARIA role/state a real screen reader "
        "needs to announce it correctly."
    )


def status_message_question(update_description: str, mechanism_description: str) -> str:
    return (
        f"This part of the page updates dynamically without a full page reload or a focus change: "
        f"{update_description}. For WCAG 4.1.3 Status Messages, a screen reader user who isn't currently focused "
        "there needs to be told about it too (e.g. via aria-live, role=\"status\"/\"alert\", or an equivalent "
        f"programmatic mechanism), without their focus being forcibly moved. Mechanism observed: "
        f"{mechanism_description or '(none apparent)'}. Would a screen reader user actually hear this update "
        "happen, or would it pass silently for them while sighted users see it?"
    )


def sensory_characteristics_question(instruction_text: str, context: str) -> str:
    return (
        f'This instruction or content ("{instruction_text}") appears to reference shape, size, visual position, '
        f"or color (e.g. \"click the round green button\", \"see the box on the right\"). Per WCAG 1.3.3 Sensory "
        f"Characteristics and 1.4.1 Use of Color, could a screen reader user (who has no access to shape/position/"
        f"color) still identify and act on the correct element from the text alone? Context: {context}"
    )


def table_semantics_question(table_summary: str) -> str:
    return (
        f"For this data table ({table_summary}), a screen reader announces column/row headers as a user moves "
        "between cells, so the header-to-data-cell association (via <th>/scope, or headers/id) is what lets a "
        "screen reader user understand what each cell means out of visual context. Per WCAG 1.3.1, is the header "
        "association correct and complete, or would a screen reader user hear unlabeled data with no way to tell "
        "which row/column it belongs to?"
    )


def generic_question(wcag_criterion: str, description: str) -> str:
    return (
        f"Evaluate whether this page element satisfies WCAG {wcag_criterion}, specifically considering whether "
        f"the experience holds up for a screen reader user, not just whether the markup is technically present. "
        f"{description}"
    )


# Human-readable reference for the PLAN stage prompt (planner_prompts.py) so
# the model knows which judgment_kind to set and when.
JUDGMENT_KIND_DESCRIPTIONS: dict[str, str] = {
    "alt_text_quality": "An <img>'s alt text may be missing or unhelpful (WCAG 1.1.1). "
    "target_element: {alt_text, context}.",
    "error_message_clarity": "A form validation error's text/announcement may be unclear or not exposed to AT "
    "(WCAG 3.3.1, 3.3.3, 4.1.3). target_element: {text, context}.",
    "focus_order_sanity": "Whether the simulated keyboard tab order is logical (WCAG 2.4.3) - normally handled "
    "by the deterministic keyboard_nav tool; use this judgment kind only to interpret an ambiguous case its "
    "output already surfaced. target_element: {sequence_summary}.",
    "link_purpose": "A link's text may not be clear out of context, e.g. \"click here\"/\"read more\" (WCAG 2.4.4). "
    "target_element: {text, context}.",
    "reading_order_sanity": "CSS layout/positioning may make the visual reading order diverge from DOM order "
    "(WCAG 1.3.2). target_element: {dom_order_summary, visual_order_summary} (or use context/description).",
    "landmark_and_heading_navigation": "Whether a screen reader user can navigate to specific content via "
    "landmarks/headings (WCAG 1.3.1, 2.4.1, 2.4.6). target_element: {landmarks_summary, headings_summary, "
    "description} (or use context/description with the page's landmarks/headings already provided).",
    "name_role_value_accuracy": "A custom/interactive widget (buttons built from <div>, custom dropdowns, "
    "toggles, tabs, ...) whose accessible name/role/state may not be correctly exposed (WCAG 4.1.2). "
    "target_element: {description, expected_name, expected_role} (or use context/description).",
    "status_message_announcement": "Dynamic content that updates without a page reload or focus move (toasts, "
    "cart counters, live search results, validation summaries) may not be announced to AT (WCAG 4.1.3). "
    "target_element: {update_description, mechanism_description} (or use context/description).",
    "sensory_characteristics": "Instructions/content that reference shape, size, position, or color alone "
    "(WCAG 1.3.3, 1.4.1). target_element: {instruction_text, context}.",
    "table_semantics": "A data table whose header-to-cell association may be missing or incorrect (WCAG 1.3.1). "
    "target_element: {table_summary} (or use description).",
}


def build_question(*, judgment_kind: str | None, wcag_criterion: str, target_element: dict) -> str:
    if judgment_kind == "alt_text_quality":
        return alt_text_question(target_element.get("alt_text"), target_element.get("context", ""))
    if judgment_kind == "error_message_clarity":
        return error_message_question(target_element.get("text", ""), target_element.get("context", ""))
    if judgment_kind == "focus_order_sanity":
        return focus_order_question(target_element.get("sequence_summary", ""))
    if judgment_kind == "link_purpose":
        return link_purpose_question(target_element.get("text", ""), target_element.get("context", ""))
    if judgment_kind == "reading_order_sanity":
        return reading_order_question(
            target_element.get("dom_order_summary") or target_element.get("description", ""),
            target_element.get("visual_order_summary") or target_element.get("context", ""),
        )
    if judgment_kind == "landmark_and_heading_navigation":
        return landmark_and_heading_question(
            target_element.get("landmarks_summary") or target_element.get("context", ""),
            target_element.get("headings_summary", ""),
            target_element.get("description") or "the relevant content",
        )
    if judgment_kind == "name_role_value_accuracy":
        return name_role_value_question(
            target_element.get("description") or target_element.get("selector", "this element"),
            target_element.get("expected_name") or target_element.get("text", ""),
            target_element.get("expected_role") or "control",
        )
    if judgment_kind == "status_message_announcement":
        return status_message_question(
            target_element.get("update_description") or target_element.get("description", ""),
            target_element.get("mechanism_description") or target_element.get("context", ""),
        )
    if judgment_kind == "sensory_characteristics":
        return sensory_characteristics_question(
            target_element.get("instruction_text") or target_element.get("text", ""),
            target_element.get("context", ""),
        )
    if judgment_kind == "table_semantics":
        return table_semantics_question(target_element.get("table_summary") or target_element.get("description", ""))
    return generic_question(wcag_criterion, target_element.get("description", ""))
