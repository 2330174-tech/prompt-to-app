"""Structural validation: well-formedness beyond what Pydantic already guarantees.

Pydantic construction already enforces valid JSON, required keys, and base types. This
layer catches enum-level and uniqueness problems (bad field types, unknown component
types/methods, duplicate tables)."""
from __future__ import annotations

from typing import List

from app.schemas import AppConfig, FIELD_TYPES
from app.schemas.ui import COMPONENT_TYPES
from app.validation.errors import ValidationError, Code

METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


def validate(config: AppConfig) -> List[ValidationError]:
    errors: List[ValidationError] = []

    seen = set()
    for t in config.db.tables:
        if t.name in seen:
            errors.append(ValidationError(
                layer="structural", code=Code.DUP_TABLE, component="db",
                path=f"db.tables.{t.name}", message=f"Duplicate table '{t.name}'",
                repair_hint="Drop the duplicate table.", auto_fixable=True))
        seen.add(t.name)
        for c in t.columns:
            if c.type not in FIELD_TYPES:
                errors.append(ValidationError(
                    layer="structural", code=Code.BAD_FIELD_TYPE, component="db",
                    path=f"db.{t.name}.{c.name}",
                    message=f"Unknown column type '{c.type}'",
                    repair_hint="Coerce to 'string'.", auto_fixable=True))

    for ep in config.api.endpoints:
        if ep.method.upper() not in METHODS:
            errors.append(ValidationError(
                layer="structural", code=Code.BAD_METHOD, component="api",
                path=f"api.{ep.path}", message=f"Invalid HTTP method '{ep.method}'",
                repair_hint="Coerce to GET.", auto_fixable=True))

    for p in config.ui.pages:
        for i, comp in enumerate(p.components):
            if comp.type not in COMPONENT_TYPES:
                errors.append(ValidationError(
                    layer="structural", code=Code.BAD_COMPONENT_TYPE, component="ui",
                    path=f"ui.{p.name}.components[{i}]",
                    message=f"Unknown component type '{comp.type}'",
                    repair_hint="Coerce to 'text'.", auto_fixable=True))
    return errors
