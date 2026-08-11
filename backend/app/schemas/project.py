"""Pydantic DTOs for projects (the sites/apps being audited)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class ProjectCreate(BaseModel):
    name: str
    base_url: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name is required")
        return v

    @field_validator("base_url")
    @classmethod
    def base_url_valid(cls, v: str) -> str:
        v = v.strip()
        if not re_scheme_matches(v):
            raise ValueError("base_url must be a valid absolute http(s) URL")
        return v


def re_scheme_matches(url: str) -> bool:
    return url.lower().startswith("http://") or url.lower().startswith("https://")


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    crawl_status: str
    crawl_error: str | None = None
    created_at: datetime
    last_crawled_at: datetime | None = None
