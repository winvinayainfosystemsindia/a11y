"""
Import every model here so Base.metadata is fully populated for Alembic
autogeneration and for create_all() in tests.
"""
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.models.project import Project
from app.models.crawled_page import CrawledPage
from app.models.audit_execution import AuditExecution
from app.models.audit_run import AuditRun
from app.models.plan_step import PlanStep
from app.models.step_result import StepResult
from app.models.ai_memory import AIMemory
from app.models.ai_memory_update import AIMemoryUpdate

__all__ = [
    "User",
    "RefreshToken",
    "Project",
    "CrawledPage",
    "AuditExecution",
    "AuditRun",
    "PlanStep",
    "StepResult",
    "AIMemory",
    "AIMemoryUpdate",
]
