"""Repair engine.

Strategy (not brute retry):
1. Deterministic, code-based fixes for errors that have an unambiguous resolution
   (drop hallucinated field, coerce type, add missing FK target, synthesize a missing
   login/analytics page, etc.). These cost zero LLM calls.
2. Anything left over is grouped by component and handed back to the orchestrator, which
   re-generates ONLY that component with the specific errors as feedback.

Each fixer re-scans the config so it is idempotent and order-independent.
"""
from __future__ import annotations

from typing import List, Tuple

from app.schemas import AppConfig, Endpoint, Page, Component, Plan
from app.schemas.api import IOField
from app.pipeline.schema_gen import crud_endpoints_for_table
from app.validation.errors import ValidationError, Code

DETERMINISTIC = {
    Code.BAD_FIELD_TYPE, Code.BAD_COMPONENT_TYPE, Code.BAD_METHOD, Code.DUP_TABLE,
    Code.API_ENTITY_MISSING, Code.HALLUCINATED_API_FIELD, Code.BAD_FOREIGN_KEY,
    Code.UI_ENDPOINT_MISSING, Code.HALLUCINATED_UI_FIELD, Code.UNKNOWN_ROLE,
    Code.PERM_RESOURCE_MISSING, Code.MISSING_ANALYTICS, Code.ANALYTICS_NOT_ADMIN,
    Code.MISSING_PREMIUM_PLAN, Code.MISSING_LOGIN_PAGE, Code.MISSING_DASHBOARD,
    Code.NO_CRUD_FOR_ENTITY,
}


def repair(config: AppConfig, errors: List[ValidationError]) -> Tuple[AppConfig, int, List[ValidationError]]:
    """Apply deterministic fixes. Returns (config, num_fixed, remaining_unfixable)."""
    codes = {e.code for e in errors}
    fixed = 0

    tables = {t.name: {c.name for c in t.columns} for t in config.db.tables}
    table_names = set(tables)
    known_roles = set(config.auth.roles)
    entity_names = {e.name for e in config.architecture.entities}

    # ---- structural ----
    if Code.DUP_TABLE in codes:
        seen, keep = set(), []
        for t in config.db.tables:
            if t.name not in seen:
                keep.append(t)
                seen.add(t.name)
        config.db.tables = keep

    if Code.BAD_FIELD_TYPE in codes:
        from app.schemas import FIELD_TYPES
        for t in config.db.tables:
            for c in t.columns:
                if c.type not in FIELD_TYPES:
                    c.type = "string"

    if Code.BAD_METHOD in codes:
        for ep in config.api.endpoints:
            if ep.method.upper() not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                ep.method = "GET"

    if Code.BAD_COMPONENT_TYPE in codes:
        from app.schemas.ui import COMPONENT_TYPES
        for p in config.ui.pages:
            for comp in p.components:
                if comp.type not in COMPONENT_TYPES:
                    comp.type = "text"

    # ---- referential ----
    if Code.BAD_FOREIGN_KEY in codes:
        for t in config.db.tables:
            for c in t.columns:
                if c.foreign_key and c.foreign_key.split(".")[0] not in table_names:
                    c.foreign_key = None

    if Code.API_ENTITY_MISSING in codes:
        config.api.endpoints = [ep for ep in config.api.endpoints
                                if ep.entity in table_names or ep.entity == "analytics"]

    if Code.HALLUCINATED_API_FIELD in codes:
        for ep in config.api.endpoints:
            if ep.entity in tables:
                cols = tables[ep.entity] | {"id"}
                ep.request_fields = [f for f in ep.request_fields if f.name in cols]
                ep.response_fields = [f for f in ep.response_fields if f.name in cols]

    if Code.UNKNOWN_ROLE in codes:
        for ep in config.api.endpoints:
            ep.allowed_roles = [r for r in ep.allowed_roles if r in known_roles]
        config.auth.permissions = [p for p in config.auth.permissions if p.role in known_roles]

    if Code.PERM_RESOURCE_MISSING in codes:
        config.auth.permissions = [p for p in config.auth.permissions if p.resource in entity_names]

    # Recompute endpoint field index for UI fixes (after API fixes above).
    api_paths = {ep.path for ep in config.api.endpoints}
    endpoint_fields = {}
    for ep in config.api.endpoints:
        endpoint_fields.setdefault(ep.path, {"id"})
        endpoint_fields[ep.path].update(f.name for f in ep.response_fields)
        endpoint_fields[ep.path].update(f.name for f in ep.request_fields)

    if Code.UI_ENDPOINT_MISSING in codes:
        for p in config.ui.pages:
            for comp in p.components:
                if comp.api_endpoint is not None and comp.api_endpoint not in api_paths:
                    comp.api_endpoint = None
                    comp.fields = []

    if Code.HALLUCINATED_UI_FIELD in codes:
        for p in config.ui.pages:
            for comp in p.components:
                if comp.api_endpoint in endpoint_fields:
                    valid = endpoint_fields[comp.api_endpoint]
                    comp.fields = [f for f in comp.fields if f in valid]

    # ---- logical ----
    if Code.NO_CRUD_FOR_ENTITY in codes:
        covered = {ep.entity for ep in config.api.endpoints}
        auth_enabled = config.auth.auth_enabled
        roles = config.auth.roles
        for t in config.db.tables:
            if t.name not in covered:
                for ed in crud_endpoints_for_table(t, auth_enabled, roles):
                    config.api.endpoints.append(Endpoint(**ed))

    if Code.MISSING_ANALYTICS in codes:
        if config.api.by_path("/api/analytics", "GET") is None:
            config.api.endpoints.append(Endpoint(
                path="/api/analytics", method="GET", entity="analytics",
                description="Aggregate metrics", request_fields=[],
                response_fields=[IOField(name="metric", type="string"),
                                 IOField(name="value", type="int")],
                auth_required=config.auth.auth_enabled,
                allowed_roles=["admin"] if "admin" in known_roles else list(known_roles)))
        if not any("analytic" in p.name.lower() for p in config.ui.pages):
            has_admin = any(r.is_admin for r in config.architecture.roles)
            config.ui.pages.append(Page(
                name="Analytics", path="/analytics", layout="grid",
                role_required="admin" if has_admin else None,
                premium_required=config.architecture.premium,
                components=[Component(type="chart", title="Metrics", entity="analytics",
                                      fields=["metric", "value"], api_endpoint="/api/analytics")]))

    if Code.ANALYTICS_NOT_ADMIN in codes:
        for p in config.ui.pages:
            if "analytic" in p.name.lower():
                p.role_required = "admin"

    if Code.MISSING_PREMIUM_PLAN in codes:
        config.auth.plans = [p for p in config.auth.plans if not p.is_premium]
        gated = config.architecture.premium_features or ["analytics"]
        if not any(not p.is_premium for p in config.auth.plans):
            config.auth.plans.append(Plan(name="free", is_premium=False, gated_features=[]))
        config.auth.plans.append(Plan(name="premium", is_premium=True, gated_features=gated))

    if Code.MISSING_LOGIN_PAGE in codes:
        config.ui.pages.insert(0, Page(
            name="Login", path="/login", layout="form",
            components=[Component(type="form", title="Sign in",
                                  fields=["email", "password"], api_endpoint=None)]))

    if Code.MISSING_DASHBOARD in codes:
        get_eps = [ep for ep in config.api.endpoints if ep.method == "GET" and ep.entity != "analytics"]
        stats = [Component(type="stat", title=ep.entity, entity=ep.entity,
                           fields=["id"], api_endpoint=ep.path) for ep in get_eps]
        config.ui.pages.append(Page(name="Dashboard", path="/dashboard", layout="grid",
                                    components=stats))

    fixed = sum(1 for e in errors if e.code in DETERMINISTIC)
    remaining = [e for e in errors if e.code not in DETERMINISTIC]
    return config, fixed, remaining
