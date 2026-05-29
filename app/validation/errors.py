"""Structured validation errors. Every check emits one of these, never a bare string,
so the repair engine can route each error to the right fix."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


# Error codes grouped by layer. The repair engine dispatches on these.
class Code:
    # structural
    BAD_FIELD_TYPE = "BAD_FIELD_TYPE"
    BAD_COMPONENT_TYPE = "BAD_COMPONENT_TYPE"
    BAD_METHOD = "BAD_METHOD"
    DUP_TABLE = "DUP_TABLE"
    # referential
    API_ENTITY_MISSING = "API_ENTITY_MISSING"
    HALLUCINATED_API_FIELD = "HALLUCINATED_API_FIELD"
    BAD_FOREIGN_KEY = "BAD_FOREIGN_KEY"
    UI_ENDPOINT_MISSING = "UI_ENDPOINT_MISSING"
    HALLUCINATED_UI_FIELD = "HALLUCINATED_UI_FIELD"
    UI_ENTITY_MISSING = "UI_ENTITY_MISSING"
    UNKNOWN_ROLE = "UNKNOWN_ROLE"
    PERM_RESOURCE_MISSING = "PERM_RESOURCE_MISSING"
    # logical
    MISSING_ANALYTICS = "MISSING_ANALYTICS"
    ANALYTICS_NOT_ADMIN = "ANALYTICS_NOT_ADMIN"
    MISSING_PREMIUM_PLAN = "MISSING_PREMIUM_PLAN"
    MISSING_LOGIN_PAGE = "MISSING_LOGIN_PAGE"
    MISSING_DASHBOARD = "MISSING_DASHBOARD"
    NO_CRUD_FOR_ENTITY = "NO_CRUD_FOR_ENTITY"


class ValidationError(BaseModel):
    layer: str          # structural | referential | logical
    code: str
    component: str      # db | api | ui | auth
    path: str           # where in the config
    message: str
    repair_hint: str = ""
    auto_fixable: bool = False

    def short(self) -> str:
        return f"[{self.layer}/{self.code}] {self.path}: {self.message}"
