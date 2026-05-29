"""Stage 3 contract: auth system (roles, permissions, plans)."""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field

ACTIONS = {"create", "read", "update", "delete", "view"}


class Permission(BaseModel):
    role: str
    resource: str = Field(description="Entity or page name")
    actions: List[str] = Field(default_factory=list)


class Plan(BaseModel):
    name: str
    is_premium: bool = False
    gated_features: List[str] = Field(default_factory=list)


class AuthSchema(BaseModel):
    auth_enabled: bool = True
    roles: List[str] = Field(default_factory=list)
    permissions: List[Permission] = Field(default_factory=list)
    plans: List[Plan] = Field(default_factory=list)
