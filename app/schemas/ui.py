"""Stage 3 contract: UI schema (pages, components, layouts)."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

COMPONENT_TYPES = {"form", "table", "chart", "text", "stat", "button"}


class Component(BaseModel):
    type: str = Field(description="One of: " + ", ".join(sorted(COMPONENT_TYPES)))
    title: str = ""
    entity: Optional[str] = Field(default=None, description="Entity this component is bound to")
    fields: List[str] = Field(default_factory=list, description="Field names shown/edited")
    api_endpoint: Optional[str] = Field(default=None, description="Path of the endpoint it calls")


class Page(BaseModel):
    name: str
    path: str = Field(description="e.g. /contacts")
    layout: str = "list"
    role_required: Optional[str] = Field(default=None, description="Role needed to view, if any")
    premium_required: bool = False
    components: List[Component] = Field(default_factory=list)


class UISchema(BaseModel):
    pages: List[Page] = Field(default_factory=list)
