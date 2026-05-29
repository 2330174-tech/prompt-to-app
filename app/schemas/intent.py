"""Stage 1 contract: structured intermediate representation of user intent."""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class IntentIR(BaseModel):
    """Parsed, structured form of an open-ended natural-language request."""

    app_name: str = Field(description="Short product name inferred from the request")
    domain: str = Field(description="Problem domain, e.g. 'crm', 'blog', 'ecommerce'")
    description: str = Field(description="One-sentence summary of the app")
    entities: List[str] = Field(default_factory=list, description="Core nouns/data objects")
    roles: List[str] = Field(default_factory=list, description="User roles, e.g. admin, user")
    features: List[str] = Field(default_factory=list, description="Capabilities, e.g. login, dashboard")
    integrations: List[str] = Field(default_factory=list, description="External needs, e.g. payments")
    assumptions: List[str] = Field(default_factory=list, description="Defaults chosen for gaps")
    ambiguities: List[str] = Field(default_factory=list, description="Vague/conflicting points found")
    needs_clarification: bool = Field(default=False)
