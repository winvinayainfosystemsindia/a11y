"""
Business logic for the standalone WCAG Success Criteria Library reference
sheet - pure static data, no DB access, so this controller takes no Session.
Kept as a controller (rather than building the DTOs directly in the view)
to match the rest of the app's "views stay thin" convention.
"""
from __future__ import annotations

from app.schemas.wcag import SuccessCriterionOut
from app.utils.wcag_criteria import all_success_criteria, principle_for_criterion, success_criteria_for_level


def list_success_criteria(level: str | None) -> list[SuccessCriterionOut]:
    criteria = success_criteria_for_level(level) if level else all_success_criteria()
    return [
        SuccessCriterionOut(
            s_no=index,
            sc_number=criterion.sc_number,
            name=criterion.name,
            wcag_version=criterion.wcag_version,
            level=criterion.level,
            principle=principle_for_criterion(criterion.sc_number),
            guideline=criterion.guideline,
            description=criterion.description,
        )
        for index, criterion in enumerate(criteria, start=1)
    ]
