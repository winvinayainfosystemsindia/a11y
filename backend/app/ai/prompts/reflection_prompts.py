"""
Prompt templates for the REFLECT/LEARN stage. One structured call reviews
every StepResult from the run for low-confidence findings, near-duplicates,
and contradictions with memory, and proposes the Lesson objects LEARN will
persist - so the loop actually closes instead of treating every page as new.

`summary` is written as the executive summary of the audit report (the
headline paragraph a human reviewer reads first) - it's asked for in the
voice of a professional accessibility auditor (IAAP CPACC/WAS style):
objective, criterion-referenced, and explicit about the real-world impact
on assistive-technology users, not a generic restatement of pass/fail counts
(those are computed deterministically elsewhere and don't need repeating).
"""
from __future__ import annotations

import json

from app.ai.schemas import MemoryContext

REFLECTION_SYSTEM_PROMPT_TEMPLATE = """You are a certified accessibility professional (in the manner of an IAAP \
CPACC/WAS-credentialed auditor) closing out a WCAG {level} conformance audit run. Review the complete set of test \
case results for low-confidence findings, near-duplicate results, and results that contradict what past audits \
have learned about this page type. Produce a structured reflection AND a short list of "lessons" - the persistent \
memory updates future audits should learn from this run.

Rules:
- `summary` is the audit's executive summary - the paragraph a human reviewer reads first. Write it like a \
  professional auditor's report summary: name the page, state the overall conformance posture for WCAG {level}, \
  call out the most significant defects by real-world impact (especially anything that would block or seriously \
  degrade the experience for a screen reader user), and note anything specifically about screen-reader/keyboard \
  usability that stood out - not just a restatement of pass/fail counts.
- `low_confidence_plan_step_ids` lists the plan_step id of every result with confidence below {threshold} - never \
  silently drop or hide these; they must be surfaced to the user, flagged.
- `contradictions` lists any result that disagrees with a pattern memory already expected for this page type - \
  explain the disagreement in `note`, referencing the memory pattern text in `memory_pattern`.
- `deduplication_notes` calls out any near-identical findings (e.g. the same missing-alt-text pattern reported \
  once per image) worth merging in the summary, without deleting the underlying step results.
- For `lessons`: only propose one when this run's evidence genuinely supports it - do not invent a pattern from \
  a single ambiguous result.
  - action="new" when this (page_type_signature, wcag_rule_id) pair hasn't been seen in memory before.
  - action="confirm" when this run's result matches what memory already expected.
  - action="contradict" when this run's result disagrees with what memory expected - explain why in `reason`, \
    and set outcome_pattern to reflect the *new* evidence, not the stale expectation.
  - wcag_rule_id should be the axe rule id when the step used the axe tool, otherwise the WCAG success criterion \
    number (e.g. "1.1.1").

Output ONLY the structured JSON matching the provided schema - no free text, no markdown."""


def build_reflection_system_prompt(conformance_level: str, low_confidence_threshold: float) -> str:
    return REFLECTION_SYSTEM_PROMPT_TEMPLATE.format(level=conformance_level, threshold=low_confidence_threshold)


def build_reflection_user_message(
    *,
    page_title: str | None,
    page_url: str,
    page_type_signature: str,
    plan_steps_with_results: list[dict],
    memory: MemoryContext,
) -> str:
    parts = [
        f"## Page\nTitle: {page_title or '(none)'}\nURL: {page_url}\nPage type: {page_type_signature}",
        f"## Test cases and their results\n{json.dumps(plan_steps_with_results, default=str)}",
    ]
    if not memory.is_empty():
        parts.append(
            "## Memory consulted during planning (check results against this for contradictions)\n"
            + json.dumps(
                {
                    "similar_page_findings": memory.similar_page_findings,
                    "rule_specific_patterns": memory.rule_specific_patterns,
                }
            )
        )
    else:
        parts.append("## Memory\nNone existed for this page type before this run - every result is a candidate "
                     "for a new lesson.")
    return "\n\n".join(parts)
