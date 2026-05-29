"""Referential validation: cross-layer consistency.

This is where "API fields must match DB schema" and "UI fields must map to API" are
enforced. These are the errors the repair engine most often fixes."""
from __future__ import annotations

from typing import List

from app.schemas import AppConfig
from app.validation.errors import ValidationError, Code

NON_TABLE_ENTITIES = {"analytics"}  # aggregate/virtual endpoints not backed by a table


def validate(config: AppConfig) -> List[ValidationError]:
    errors: List[ValidationError] = []
    tables = {t.name: {c.name for c in t.columns} for t in config.db.tables}

    # DB foreign keys must point at real table.column.
    for t in config.db.tables:
        for c in t.columns:
            if c.foreign_key:
                ref_table = c.foreign_key.split(".")[0]
                if ref_table not in tables:
                    errors.append(ValidationError(
                        layer="referential", code=Code.BAD_FOREIGN_KEY, component="db",
                        path=f"db.{t.name}.{c.name}",
                        message=f"Foreign key '{c.foreign_key}' points to unknown table",
                        repair_hint="Drop the foreign key constraint.", auto_fixable=True))

    # API endpoints must target real tables, with fields that exist on them.
    for ep in config.api.endpoints:
        if ep.entity in NON_TABLE_ENTITIES:
            continue
        if ep.entity not in tables:
            errors.append(ValidationError(
                layer="referential", code=Code.API_ENTITY_MISSING, component="api",
                path=f"api.{ep.method} {ep.path}",
                message=f"Endpoint targets unknown table '{ep.entity}'",
                repair_hint="Drop the endpoint (no backing table).", auto_fixable=True))
            continue
        cols = tables[ep.entity]
        for f in list(ep.request_fields) + list(ep.response_fields):
            if f.name not in cols and f.name != "id":
                errors.append(ValidationError(
                    layer="referential", code=Code.HALLUCINATED_API_FIELD, component="api",
                    path=f"api.{ep.method} {ep.path}.{f.name}",
                    message=f"Field '{f.name}' not in table '{ep.entity}'",
                    repair_hint="Remove the hallucinated field.", auto_fixable=True))

    # UI components must reference existing endpoints and existing endpoint fields.
    api_paths = {ep.path for ep in config.api.endpoints}
    endpoint_fields = {}
    for ep in config.api.endpoints:
        endpoint_fields.setdefault(ep.path, set())
        endpoint_fields[ep.path].update(f.name for f in ep.response_fields)
        endpoint_fields[ep.path].update(f.name for f in ep.request_fields)

    for p in config.ui.pages:
        for i, comp in enumerate(p.components):
            if comp.api_endpoint is None:
                continue  # static component (e.g. login form)
            if comp.api_endpoint not in api_paths:
                errors.append(ValidationError(
                    layer="referential", code=Code.UI_ENDPOINT_MISSING, component="ui",
                    path=f"ui.{p.name}.components[{i}]",
                    message=f"Component calls missing endpoint '{comp.api_endpoint}'",
                    repair_hint="Point at an existing endpoint or drop the binding.",
                    auto_fixable=True))
                continue
            valid = endpoint_fields.get(comp.api_endpoint, set()) | {"id"}
            for fname in comp.fields:
                if fname not in valid:
                    errors.append(ValidationError(
                        layer="referential", code=Code.HALLUCINATED_UI_FIELD, component="ui",
                        path=f"ui.{p.name}.components[{i}].{fname}",
                        message=f"UI field '{fname}' not exposed by endpoint",
                        repair_hint="Remove the field from the component.", auto_fixable=True))

    # Roles referenced by the API must exist in the auth schema.
    known_roles = set(config.auth.roles)
    for ep in config.api.endpoints:
        for r in ep.allowed_roles:
            if r not in known_roles:
                errors.append(ValidationError(
                    layer="referential", code=Code.UNKNOWN_ROLE, component="api",
                    path=f"api.{ep.method} {ep.path}",
                    message=f"allowed_roles references unknown role '{r}'",
                    repair_hint="Remove unknown role or add it to auth.roles.",
                    auto_fixable=True))

    # Permission resources must be real entities.
    entity_names = {e.name for e in config.architecture.entities}
    for i, perm in enumerate(config.auth.permissions):
        if perm.role not in known_roles:
            errors.append(ValidationError(
                layer="referential", code=Code.UNKNOWN_ROLE, component="auth",
                path=f"auth.permissions[{i}]",
                message=f"Permission for unknown role '{perm.role}'",
                repair_hint="Drop the permission.", auto_fixable=True))
        if perm.resource not in entity_names:
            errors.append(ValidationError(
                layer="referential", code=Code.PERM_RESOURCE_MISSING, component="auth",
                path=f"auth.permissions[{i}]",
                message=f"Permission references unknown resource '{perm.resource}'",
                repair_hint="Drop the permission.", auto_fixable=True))
    return errors
