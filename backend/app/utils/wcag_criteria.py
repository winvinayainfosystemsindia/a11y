"""
The canonical WCAG 2.0/2.1/2.2 success criteria list, by conformance level and by
the four WCAG principles (POUR: Perceivable, Operable, Understandable,
Robust). Shared between app/ai/prompts/planner_prompts.py (which needs the
full list to build the PLAN stage's "must cover every mandatory criterion"
instruction, grouped by principle), app/controllers/audit_controller.py
(which needs criterion names/principles for the Test Case and Defects
report mapping), and app/views/wcag_routes.py (the standalone Success
Criteria Library reference sheet) - kept here, outside app/ai/, so neither
the controller nor the library endpoint have to reach into the AI package
for it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SuccessCriterion:
    """One row of the Success Criteria Library reference sheet."""

    sc_number: str
    name: str
    wcag_version: str  # "2.0", "2.1", or "2.2" - the version that introduced this criterion
    level: str  # "A" or "AA"
    guideline: str  # parent WCAG guideline, e.g. "1.1 Text Alternatives"
    description: str  # plain-language requirement / what to check


# ── Level A (32 criteria in WCAG 2.2) ────────────────────────────────────

_LEVEL_A: list[SuccessCriterion] = [
    SuccessCriterion(
        "1.1.1", "Non-text Content", "2.2", "A", "1.1 Text Alternatives",
        "All non-text content has a text alternative that serves the equivalent purpose (e.g. alt text for "
        "images, a name for icon buttons; purely decorative content is hidden from assistive technology).",
    ),
    SuccessCriterion(
        "1.2.1", "Audio-only and Video-only (Prerecorded)", "2.2", "A", "1.2 Time-based Media",
        "An alternative for time-based media is provided for prerecorded audio-only and video-only content.",
    ),
    SuccessCriterion(
        "1.2.2", "Captions (Prerecorded)", "2.2", "A", "1.2 Time-based Media",
        "Captions are provided for all prerecorded audio content in synchronized media.",
    ),
    SuccessCriterion(
        "1.2.3", "Audio Description or Media Alternative (Prerecorded)", "2.2", "A", "1.2 Time-based Media",
        "An alternative for time-based media or an audio description of the prerecorded video content is "
        "provided for synchronized media.",
    ),
    SuccessCriterion(
        "1.3.1", "Info and Relationships", "2.2", "A", "1.3 Adaptable",
        "Information, structure, and relationships conveyed through presentation can be programmatically "
        "determined or are available in text (headings, lists, tables, labels use real semantic markup).",
    ),
    SuccessCriterion(
        "1.3.2", "Meaningful Sequence", "2.2", "A", "1.3 Adaptable",
        "When the sequence in which content is presented affects its meaning, a correct reading sequence can "
        "be programmatically determined (DOM order matches visual/reading order).",
    ),
    SuccessCriterion(
        "1.3.3", "Sensory Characteristics", "2.2", "A", "1.3 Adaptable",
        "Instructions for understanding and operating content do not rely solely on sensory characteristics "
        "such as shape, size, visual location, orientation, or sound.",
    ),
    SuccessCriterion(
        "1.4.1", "Use of Color", "2.2", "A", "1.4 Distinguishable",
        "Color is not used as the only visual means of conveying information, indicating an action, prompting "
        "a response, or distinguishing a visual element.",
    ),
    SuccessCriterion(
        "1.4.2", "Audio Control", "2.2", "A", "1.4 Distinguishable",
        "If any audio plays automatically for more than 3 seconds, a mechanism is available to pause, stop, "
        "or control its volume independently of the overall system volume.",
    ),
    SuccessCriterion(
        "2.1.1", "Keyboard", "2.2", "A", "2.1 Keyboard Accessible",
        "All functionality of the content is operable through a keyboard interface, without requiring "
        "specific timings for individual keystrokes.",
    ),
    SuccessCriterion(
        "2.1.2", "No Keyboard Trap", "2.2", "A", "2.1 Keyboard Accessible",
        "If keyboard focus can be moved to a component using a keyboard, focus can also be moved away from "
        "that component using only the keyboard.",
    ),
    SuccessCriterion(
        "2.1.4", "Character Key Shortcuts", "2.2", "A", "2.1 Keyboard Accessible",
        "If a keyboard shortcut uses only letter, punctuation, number, or symbol characters, a mechanism "
        "exists to turn it off, remap it, or restrict it to when the relevant component has focus.",
    ),
    SuccessCriterion(
        "2.2.1", "Timing Adjustable", "2.2", "A", "2.2 Enough Time",
        "For each time limit set by the content, the user can turn off, adjust, or extend the time limit, "
        "with certain exceptions (e.g. real-time events).",
    ),
    SuccessCriterion(
        "2.2.2", "Pause, Stop, Hide", "2.2", "A", "2.2 Enough Time",
        "For moving, blinking, scrolling, or auto-updating information, the user can pause, stop, or hide it.",
    ),
    SuccessCriterion(
        "2.3.1", "Three Flashes or Below Threshold", "2.2", "A", "2.3 Seizures and Physical Reactions",
        "Content does not contain anything that flashes more than three times in any one-second period, or "
        "the flash is below the general flash and red flash thresholds.",
    ),
    SuccessCriterion(
        "2.4.1", "Bypass Blocks", "2.2", "A", "2.4 Navigable",
        "A mechanism is available to bypass blocks of content that are repeated on multiple pages (e.g. a "
        "skip link or landmark regions).",
    ),
    SuccessCriterion(
        "2.4.2", "Page Titled", "2.2", "A", "2.4 Navigable",
        "Web pages have titles that describe topic or purpose.",
    ),
    SuccessCriterion(
        "2.4.3", "Focus Order", "2.2", "A", "2.4 Navigable",
        "If a page can be navigated sequentially and the navigation sequence affects meaning or operation, "
        "focusable components receive focus in an order that preserves meaning and operability.",
    ),
    SuccessCriterion(
        "2.4.4", "Link Purpose (In Context)", "2.2", "A", "2.4 Navigable",
        "The purpose of each link can be determined from the link text alone or from the link text together "
        "with its programmatically determined context.",
    ),
    SuccessCriterion(
        "2.5.1", "Pointer Gestures", "2.2", "A", "2.5 Input Modalities",
        "All functionality that uses multipoint or path-based gestures can be operated with a single pointer "
        "without a path-based gesture, unless the multipoint/path-based gesture is essential.",
    ),
    SuccessCriterion(
        "2.5.2", "Pointer Cancellation", "2.2", "A", "2.5 Input Modalities",
        "For functionality operated using a single pointer, at least one of the following is true: no "
        "down-event activation, ability to abort/undo, up-event reversal, or the down-event is essential.",
    ),
    SuccessCriterion(
        "2.5.3", "Label in Name", "2.2", "A", "2.5 Input Modalities",
        "For UI components with a visible text label, the accessible name contains the visible text, so "
        "speech-input users can activate the control by speaking its visible label.",
    ),
    SuccessCriterion(
        "2.5.4", "Motion Actuation", "2.2", "A", "2.5 Input Modalities",
        "Functionality operated by device motion or user motion can also be operated by standard UI "
        "components, and motion actuation can be disabled to prevent accidental activation.",
    ),
    SuccessCriterion(
        "3.1.1", "Language of Page", "2.2", "A", "3.1 Readable",
        "The default human language of each web page can be programmatically determined (e.g. the html lang "
        "attribute is set correctly).",
    ),
    SuccessCriterion(
        "3.2.1", "On Focus", "2.2", "A", "3.2 Predictable",
        "When any component receives focus, it does not initiate a change of context.",
    ),
    SuccessCriterion(
        "3.2.2", "On Input", "2.2", "A", "3.2 Predictable",
        "Changing the setting of any UI component does not automatically cause a change of context, unless "
        "the user is advised of the behavior before using the component.",
    ),
    SuccessCriterion(
        "3.2.6", "Consistent Help", "2.2", "A", "3.2 Predictable",
        "If a web page contains any of the following help mechanisms, and those mechanisms are repeated on "
        "multiple web pages within a set of web pages, they occur in the same relative order to other page "
        "content: human contact details, human contact mechanism, self-help option, or a fully automated contact mechanism.",
    ),
    SuccessCriterion(
        "3.3.1", "Error Identification", "2.2", "A", "3.3 Input Assistance",
        "If an input error is automatically detected, the item in error is identified and the error is "
        "described to the user in text.",
    ),
    SuccessCriterion(
        "3.3.2", "Labels or Instructions", "2.2", "A", "3.3 Input Assistance",
        "Labels or instructions are provided when content requires user input.",
    ),
    SuccessCriterion(
        "3.3.7", "Redundant Entry", "2.2", "A", "3.3 Input Assistance",
        "Information previously entered by or provided to the user that is required to be entered again in the "
        "same process is either auto-populated, or available for the user to select, unless re-entering is essential "
        "or required for security.",
    ),
    SuccessCriterion(
        "4.1.1", "Parsing", "2.2", "A", "4.1 Compatible",
        "In content implemented using markup languages, elements have complete start/end tags, are nested "
        "according to specification, and have unique IDs, except where the specification allows (Note: marked "
        "obsolete in WCAG 2.2; maintained for backwards compatibility with WCAG 2.0/2.1).",
    ),
    SuccessCriterion(
        "4.1.2", "Name, Role, Value", "2.2", "A", "4.1 Compatible",
        "For all UI components, the name and role can be programmatically determined; states, properties, "
        "and values that can be set by the user can be programmatically set and are exposed to assistive "
        "technology.",
    ),
]

# ── Level AA additional criteria (24 criteria in WCAG 2.2, on top of Level A) ──

_LEVEL_AA_ADDITIONAL: list[SuccessCriterion] = [
    SuccessCriterion(
        "1.2.4", "Captions (Live)", "2.2", "AA", "1.2 Time-based Media",
        "Captions are provided for all live audio content in synchronized media.",
    ),
    SuccessCriterion(
        "1.2.5", "Audio Description (Prerecorded)", "2.2", "AA", "1.2 Time-based Media",
        "Audio description is provided for all prerecorded video content in synchronized media.",
    ),
    SuccessCriterion(
        "1.3.4", "Orientation", "2.2", "AA", "1.3 Adaptable",
        "Content does not restrict its view and operation to a single display orientation (portrait or "
        "landscape), unless a specific orientation is essential.",
    ),
    SuccessCriterion(
        "1.3.5", "Identify Input Purpose", "2.2", "AA", "1.3 Adaptable",
        "The purpose of each input field collecting information about the user can be programmatically "
        "determined (e.g. via HTML autocomplete attributes).",
    ),
    SuccessCriterion(
        "1.4.3", "Contrast (Minimum)", "2.2", "AA", "1.4 Distinguishable",
        "Text and images of text have a contrast ratio of at least 4.5:1 against their background (3:1 for "
        "large-scale text).",
    ),
    SuccessCriterion(
        "1.4.4", "Resize Text", "2.2", "AA", "1.4 Distinguishable",
        "Text can be resized up to 200 percent without loss of content or functionality, without requiring "
        "assistive technology.",
    ),
    SuccessCriterion(
        "1.4.5", "Images of Text", "2.2", "AA", "1.4 Distinguishable",
        "If the same visual presentation can be made using text alone, an image of text is not used instead, "
        "except where the image of text is essential (e.g. a logo).",
    ),
    SuccessCriterion(
        "1.4.10", "Reflow", "2.2", "AA", "1.4 Distinguishable",
        "Content can be presented without loss of information or functionality, and without requiring "
        "scrolling in two dimensions, at a 320 CSS-pixel-wide (or 256 CSS-pixel-tall) viewport.",
    ),
    SuccessCriterion(
        "1.4.11", "Non-text Contrast", "2.2", "AA", "1.4 Distinguishable",
        "The visual presentation of UI components (input borders, focus indicators) and graphical objects "
        "has a contrast ratio of at least 3:1 against adjacent colors.",
    ),
    SuccessCriterion(
        "1.4.12", "Text Spacing", "2.2", "AA", "1.4 Distinguishable",
        "No loss of content or functionality occurs when line height, paragraph spacing, letter spacing, and "
        "word spacing are adjusted to specified minimum values via user/author stylesheets.",
    ),
    SuccessCriterion(
        "1.4.13", "Content on Hover or Focus", "2.2", "AA", "1.4 Distinguishable",
        "Additional content that appears on hover or keyboard focus is dismissible, hoverable, and "
        "persistent, unless the underlying trigger is a native browser tooltip.",
    ),
    SuccessCriterion(
        "2.4.5", "Multiple Ways", "2.2", "AA", "2.4 Navigable",
        "More than one way is available to locate a web page within a set of pages, except where the page is "
        "the result of, or a step in, a process.",
    ),
    SuccessCriterion(
        "2.4.6", "Headings and Labels", "2.2", "AA", "2.4 Navigable",
        "Headings and labels describe topic or purpose.",
    ),
    SuccessCriterion(
        "2.4.7", "Focus Visible", "2.2", "AA", "2.4 Navigable",
        "Any keyboard-operable user interface has a mode of operation where the keyboard focus indicator is "
        "visible.",
    ),
    SuccessCriterion(
        "2.4.11", "Focus Not Obscured (Minimum)", "2.2", "AA", "2.4 Navigable",
        "When a user interface component receives keyboard focus, the component is not entirely hidden due to "
        "author-created content (e.g. sticky headers, banners, or floating footers do not completely obscure the focused element).",
    ),
    SuccessCriterion(
        "2.5.7", "Dragging Movements", "2.2", "AA", "2.5 Input Modalities",
        "All functionality that uses a dragging movement for operation can be achieved by a single pointer "
        "without dragging, unless dragging is essential or the functionality is determined by the user agent and not modified by the author.",
    ),
    SuccessCriterion(
        "2.5.8", "Target Size (Minimum)", "2.2", "AA", "2.5 Input Modalities",
        "The size of the target for pointer inputs is at least 24 by 24 CSS pixels, except where spacing/offset, "
        "inline text, default user agent controls, or essential presentations apply.",
    ),
    SuccessCriterion(
        "3.1.2", "Language of Parts", "2.2", "AA", "3.1 Readable",
        "The human language of each passage or phrase in the content can be programmatically determined, "
        "except for proper names, technical terms, and words of indeterminate language.",
    ),
    SuccessCriterion(
        "3.2.3", "Consistent Navigation", "2.2", "AA", "3.2 Predictable",
        "Navigational mechanisms that are repeated on multiple pages occur in the same relative order each "
        "time they are repeated, unless a change is initiated by the user.",
    ),
    SuccessCriterion(
        "3.2.4", "Consistent Identification", "2.2", "AA", "3.2 Predictable",
        "Components that have the same functionality within a set of pages are identified consistently.",
    ),
    SuccessCriterion(
        "3.3.3", "Error Suggestion", "2.2", "AA", "3.3 Input Assistance",
        "If an input error is detected and suggestions for correction are known, the suggestions are "
        "provided to the user, unless it would jeopardize the security or purpose of the content.",
    ),
    SuccessCriterion(
        "3.3.4", "Error Prevention (Legal, Financial, Data)", "2.2", "AA", "3.3 Input Assistance",
        "For pages that cause legal commitments, financial transactions, or modification/deletion of "
        "user-controllable data, submissions are reversible, checked for errors, or confirmed before "
        "finalizing.",
    ),
    SuccessCriterion(
        "3.3.8", "Accessible Authentication (Minimum)", "2.2", "AA", "3.3 Input Assistance",
        "A cognitive function test (such as remembering a password or solving a puzzle) is not required for "
        "any step in an authentication process unless that step provides an alternative method or a mechanism to assist the user.",
    ),
    SuccessCriterion(
        "4.1.3", "Status Messages", "2.2", "AA", "4.1 Compatible",
        "Status messages can be programmatically determined through role or properties so they can be "
        "presented to the user by assistive technology without receiving focus (e.g. aria-live regions).",
    ),
]

ALL_CRITERIA: list[SuccessCriterion] = _LEVEL_A + _LEVEL_AA_ADDITIONAL

# ── Backward-compatible (sc_id, name) tuple lists ────────────────────────
# planner_prompts.py and audit_controller.py already import these two names
# directly - kept as plain tuples so neither caller needs to change.

WCAG_LEVEL_A: list[tuple[str, str]] = [(c.sc_number, c.name) for c in _LEVEL_A]
WCAG_LEVEL_AA_ADDITIONAL: list[tuple[str, str]] = [(c.sc_number, c.name) for c in _LEVEL_AA_ADDITIONAL]


def criteria_for_level(conformance_level: str) -> list[tuple[str, str]]:
    if conformance_level == "A":
        return WCAG_LEVEL_A
    return WCAG_LEVEL_A + WCAG_LEVEL_AA_ADDITIONAL


NAME_BY_CRITERION: dict[str, str] = {sc_id: name for sc_id, name in WCAG_LEVEL_A + WCAG_LEVEL_AA_ADDITIONAL}
_CRITERION_BY_ID: dict[str, SuccessCriterion] = {c.sc_number: c for c in ALL_CRITERIA}

_LEVEL_A_IDS: set[str] = {sc_id for sc_id, _ in WCAG_LEVEL_A}


def level_for_criterion(wcag_criterion: str) -> str:
    """The official WCAG level (A or AA) for a known criterion - a fixed
    fact, not something worth trusting an LLM to get right. Criteria this
    module doesn't recognize (e.g. an AAA-only success criterion) default to
    "AA" rather than raising, since callers use this to *correct* LLM output,
    not to validate it."""
    if wcag_criterion in _LEVEL_A_IDS:
        return "A"
    return "AA"


def criterion_name(wcag_criterion: str) -> str:
    return NAME_BY_CRITERION.get(wcag_criterion, "General Accessibility Review")


# ── The four WCAG principles (POUR) ─────────────────────────────────────
# Purely a function of the criterion's leading digit - this is guaranteed by
# the WCAG numbering scheme itself (1.x = Perceivable, 2.x = Operable,
# 3.x = Understandable, 4.x = Robust), so it's derived rather than
# hand-annotated per criterion, and is always correct.

PRINCIPLES: dict[str, str] = {
    "1": "Perceivable",
    "2": "Operable",
    "3": "Understandable",
    "4": "Robust",
}

PRINCIPLE_ORDER: list[str] = ["Perceivable", "Operable", "Understandable", "Robust"]


def principle_for_criterion(wcag_criterion: str) -> str:
    leading_digit = wcag_criterion.split(".", 1)[0]
    return PRINCIPLES.get(leading_digit, "Robust")


# ── WCAG Success Criterion -> axe-core rule id mapping ──────────────────
# The deterministic backstop that _find_relevant_violation (audit_controller.py)
# and _run_axe_step (executor.py) use to decide which axe-core rule(s) are
# actually relevant to a given test case, instead of trusting the planner
# LLM's target_element.axe_rule_ids guess unconditionally (it can omit the
# field, or name a rule that doesn't exist) or falling back to "whatever
# violation happened to be in the results array" (the root cause of the
# color-contrast / region mis-binding bug: axe genuinely has no rule for
# most WCAG criteria, so an unscoped run returns every violation on the
# page and something else gets stamped onto the row instead).
#
# An empty list is a deliberate, meaningful value: it means axe-core has no
# rule that reliably tests this criterion at all, so a step targeting it
# must never be executed as a raw/unscoped axe run - it has to be routed to
# AI judgment (method="llm") instead. Not exhaustive of every axe-core rule
# in existence, but covers the rules axe ships in its default ruleset that
# map cleanly onto a single WCAG success criterion.
WCAG_TO_AXE_RULES: dict[str, list[str]] = {
    "1.1.1": ["image-alt", "input-image-alt", "area-alt", "object-alt", "role-img-alt", "svg-img-alt"],
    "1.2.1": [],
    "1.2.2": [],
    "1.2.3": [],
    "1.2.4": [],
    "1.2.5": [],
    "1.3.1": [
        "definition-list", "dlitem", "list", "listitem",
        "th-has-data-cells", "td-headers-attr", "table-duplicate-name",
        "aria-required-children", "aria-required-parent",
    ],
    "1.3.2": [],
    "1.3.3": [],
    "1.3.4": [],
    "1.3.5": ["autocomplete-valid"],
    "1.4.1": [],
    "1.4.2": ["no-autoplay-audio"],
    "1.4.3": ["color-contrast"],
    "1.4.4": [],
    "1.4.5": [],
    "1.4.10": [],
    "1.4.11": [],
    "1.4.12": [],
    "1.4.13": [],
    "2.1.1": [],
    "2.1.2": [],  # covered by the dedicated keyboard_nav tool, not axe
    "2.1.4": [],
    "2.2.1": [],
    "2.2.2": [],
    "2.3.1": [],
    "2.4.1": ["bypass", "skip-link", "region"],
    "2.4.2": ["document-title"],
    "2.4.3": [],
    "2.4.4": [],  # axe's link-name rule tests *presence* of accessible text (see 4.1.2), not link purpose in context
    "2.4.5": [],
    "2.4.6": ["empty-heading"],
    "2.4.7": [],
    "2.4.11": [],
    "2.5.1": [],
    "2.5.2": [],
    "2.5.3": ["label-content-name-mismatch"],
    "2.5.4": [],
    "2.5.7": [],
    "2.5.8": ["target-size"],
    "3.1.1": ["html-has-lang", "html-lang-valid", "html-xml-lang-mismatch"],
    "3.1.2": ["valid-lang"],
    "3.2.1": [],
    "3.2.2": [],
    "3.2.3": [],
    "3.2.4": [],
    "3.2.6": [],
    "3.3.1": [],
    "3.3.2": ["label", "form-field-multiple-labels"],
    "3.3.3": [],
    "3.3.4": [],
    "3.3.7": [],
    "3.3.8": [],
    "4.1.1": ["duplicate-id", "duplicate-id-active", "duplicate-id-aria"],
    "4.1.2": [
        "aria-allowed-attr", "aria-required-attr", "aria-roles", "aria-valid-attr", "aria-valid-attr-value",
        "aria-allowed-role", "aria-command-name", "aria-input-field-name", "aria-toggle-field-name",
        "button-name", "input-button-name", "select-name", "link-name",
    ],
    "4.1.3": [],
}


def axe_rules_for_criterion(wcag_criterion: str) -> list[str]:
    """The axe-core rule ids that reliably test `wcag_criterion`, or an
    empty list if axe has no rule for it (criterion not in the table, or
    explicitly mapped to []) - both cases mean "do not run axe unscoped for
    this criterion", so callers don't need to distinguish them."""
    return list(WCAG_TO_AXE_RULES.get(wcag_criterion, []))


def criteria_by_principle(conformance_level: str) -> dict[str, list[tuple[str, str]]]:
    """criteria_for_level(), grouped into an ordered {principle: [(id, name), ...]}
    mapping - used to build the PLAN stage's mandatory-coverage prompt so the
    model reasons about the audit one WCAG principle at a time."""
    grouped: dict[str, list[tuple[str, str]]] = {principle: [] for principle in PRINCIPLE_ORDER}
    for sc_id, name in criteria_for_level(conformance_level):
        grouped[principle_for_criterion(sc_id)].append((sc_id, name))
    return grouped


# ── Success Criteria Library (the standalone reference sheet) ───────────

def _sort_key(sc_number: str) -> tuple[int, ...]:
    return tuple(int(part) for part in sc_number.split("."))


def all_success_criteria() -> list[SuccessCriterion]:
    """All 56 WCAG 2.0/2.1/2.2 Level A + AA success criteria, sorted numerically
    (1.1.1, 1.2.1, ... 4.1.3) for the Success Criteria Library sheet."""
    return sorted(ALL_CRITERIA, key=lambda c: _sort_key(c.sc_number))


def success_criteria_for_level(conformance_level: str) -> list[SuccessCriterion]:
    """Same as all_success_criteria(), filtered to a single conformance
    level - "A" returns the 32 Level A criteria, "AA" (or anything
    else) returns all 56."""
    ids = {sc_id for sc_id, _ in criteria_for_level(conformance_level)}
    return [c for c in all_success_criteria() if c.sc_number in ids]


# ── Element / Component Type taxonomy ────────────────────────────────────
# A closed list of page-element categories a test case can target, so the
# "Element / Component Type on Page" column stays consistent and filterable
# instead of free text. Used by app/ai/schemas.py (PlanStepSchema.element_type)
# and app/ai/prompts/planner_prompts.py to constrain what the planner LLM
# assigns to each generated test case.

ELEMENT_TYPES: list[str] = [
    "Images / Icons / Image Buttons",
    "Embedded Audio/Video (audio-only or video-only)",
    "Video Player (prerecorded)",
    "Navigation / Landmarks / Page Structure",
    "Headings / Reading Order",
    "Links",
    "Forms / Form Validation",
    "Custom Widgets (accordions, tabs, sliders, modals)",
    "Focus / Keyboard Navigation",
    "Color & Contrast",
    "Language / Text Content",
    "Status Messages / Live Regions",
    "Media Player Controls",
    "General Page",
]
