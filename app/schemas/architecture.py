"""Stage 2 contract: application architecture derived from intent."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

# Canonical field types used across all layers. Keeping one vocabulary is what
# makes cross-layer consistency checkable.
FIELD_TYPES = {"string", "text", "int", "float", "bool", "datetime", "email", "ref"}


class EntityField(BaseModel):
    name: str
    type: str = Field(description="One of: " + ", ".join(sorted(FIELD_TYPES)))
    required: bool = True
    ref: Optional[str] = Field(default=None, description="Target entity name when type=='ref'")


class Entity(BaseModel):
    name: str
    fields: List[EntityField] = Field(default_factory=list)


class Role(BaseModel):
    name: str
    description: str = ""
    is_admin: bool = False


class Flow(BaseModel):
    name: str
    description: str = ""
    steps: List[str] = Field(default_factory=list)


class AppArchitecture(BaseModel):
    app_name: str
    entities: List[Entity] = Field(default_factory=list)
    roles: List[Role] = Field(default_factory=list)
    flows: List[Flow] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list, description="Carried from intent")
    premium: bool = False
    premium_features: List[str] = Field(default_factory=list)
