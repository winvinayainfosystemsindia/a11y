"""Pydantic DTOs for the standalone WCAG Success Criteria Library reference sheet."""
from pydantic import BaseModel


class SuccessCriterionOut(BaseModel):
    s_no: int
    sc_number: str
    name: str
    wcag_version: str
    level: str
    principle: str
    guideline: str
    description: str


class SuccessCriteriaListOut(BaseModel):
    items: list[SuccessCriterionOut]
