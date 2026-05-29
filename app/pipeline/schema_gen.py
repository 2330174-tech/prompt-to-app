"""Stage 3 — Schema Generation. Architecture -> DB, then API, then UI, then Auth.

Generation is ordered so each layer is constrained by the previous one: the API is built
against real DB columns, the UI against real API endpoints. This ordering is the main
lever that keeps cross-layer references consistent.
"""
from __future__ import annotations

from typing import Tuple

from app.llm.base import LLMClient
from app.schemas import (AppArchitecture, DBSchema, APISchema, UISchema, AuthSchema,
                         StageMetric)
from app.pipeline.heuristics import plural

SYSTEM_COLS = {"id", "created_at"}


def table_name(entity: str) -> str:
    return plural(entity)


# --------------------------------------------------------------------------- DB
def _db_instruction(arch: AppArchitecture) -> str:
    return (
        "You are the database-schema stage. Convert the architecture entities into SQL-like\n"
        "tables. Every table has an integer primary key 'id' and a 'created_at' datetime.\n"
        "Map 'ref' fields to '<field>_id' integer columns with foreign_key '<table>.id'.\n"
        "Use plural snake_case table names.\n\n"
        f"ARCHITECTURE:\n{arch.model_dump_json(indent=2)}"
    )


def _db_mock(arch: AppArchitecture):
    def build() -> dict:
        tables = []
        for ent in arch.entities:
            cols = [{"name": "id", "type": "int", "nullable": False, "primary_key": True,
                     "foreign_key": None}]
            for f in ent.fields:
                if f.type == "ref" and f.ref:
                    cols.append({"name": f"{f.name}_id", "type": "int",
                                 "nullable": not f.required, "primary_key": False,
                                 "foreign_key": f"{table_name(f.ref)}.id"})
                else:
                    cols.append({"name": f.name, "type": f.type,
                                 "nullable": not f.required, "primary_key": False,
                                 "foreign_key": None})
            cols.append({"name": "created_at", "type": "datetime", "nullable": True,
                         "primary_key": False, "foreign_key": None})
            tables.append({"name": table_name(ent.name), "columns": cols})
        return {"tables": tables}

    return build


def run_db(llm: LLMClient, arch: AppArchitecture) -> Tuple[DBSchema, StageMetric]:
    return llm.structured(_db_instruction(arch), DBSchema, stage="schema.db",
                          mock_builder=_db_mock(arch))


# -------------------------------------------------------------------------- API
def _api_instruction(arch: AppArchitecture, db: DBSchema) -> str:
    return (
        "You are the API-schema stage. For every DB table produce CRUD REST endpoints\n"
        "(GET list, POST create, PUT update, DELETE). Request/response fields MUST be exactly\n"
        "DB column names (omit 'id'/'created_at' from create requests). Set auth_required and\n"
        "allowed_roles from the architecture roles.\n\n"
        f"ARCHITECTURE:\n{arch.model_dump_json(indent=2)}\n\nDB:\n{db.model_dump_json(indent=2)}"
    )


def crud_endpoints_for_table(table, auth_enabled: bool, role_names) -> list:
    """CRUD endpoints (as dicts) for one DB table. Shared by generation and repair."""
    all_fields = [{"name": c.name, "type": c.type, "required": not c.nullable}
                  for c in table.columns]
    create_fields = [{"name": c.name, "type": c.type, "required": not c.nullable}
                     for c in table.columns if c.name not in SYSTEM_COLS]
    base = f"/api/{table.name}"
    common = {"entity": table.name, "auth_required": auth_enabled, "allowed_roles": list(role_names)}
    return [
        {"path": base, "method": "GET", "description": f"List {table.name}",
         "request_fields": [], "response_fields": all_fields, **common},
        {"path": base, "method": "POST", "description": f"Create {table.name}",
         "request_fields": create_fields, "response_fields": all_fields, **common},
        {"path": base, "method": "PUT", "description": f"Update {table.name}",
         "request_fields": all_fields, "response_fields": all_fields, **common},
        {"path": base, "method": "DELETE", "description": f"Delete {table.name}",
         "request_fields": [{"name": "id", "type": "int", "required": True}],
         "response_fields": [], **common},
    ]


def _api_mock(arch: AppArchitecture, db: DBSchema):
    auth_enabled = bool(arch.roles)
    role_names = [r.name for r in arch.roles]

    def build() -> dict:
        endpoints = []
        for t in db.tables:
            endpoints.extend(crud_endpoints_for_table(t, auth_enabled, role_names))

        if "analytics" in arch.features:
            endpoints.append({
                "path": "/api/analytics", "method": "GET", "entity": "analytics",
                "description": "Aggregate metrics", "request_fields": [],
                "response_fields": [{"name": "metric", "type": "string", "required": True},
                                    {"name": "value", "type": "int", "required": True}],
                "auth_required": auth_enabled,
                "allowed_roles": ["admin"] if "admin" in role_names else role_names})
        return {"endpoints": endpoints}

    return build


def run_api(llm: LLMClient, arch: AppArchitecture, db: DBSchema) -> Tuple[APISchema, StageMetric]:
    return llm.structured(_api_instruction(arch, db), APISchema, stage="schema.api",
                          mock_builder=_api_mock(arch, db))


# --------------------------------------------------------------------------- UI
def _ui_instruction(arch: AppArchitecture, api: APISchema) -> str:
    return (
        "You are the UI-schema stage. Build pages with components (table, form, stat, chart).\n"
        "Every component's `api_endpoint` MUST be an existing API path and its `fields` MUST be\n"
        "fields of that endpoint. Add a dashboard if requested and an analytics page (admin +\n"
        "premium) if analytics exists. Add a login page if auth is enabled.\n\n"
        f"ARCHITECTURE:\n{arch.model_dump_json(indent=2)}\n\nAPI:\n{api.model_dump_json(indent=2)}"
    )


def _ui_mock(arch: AppArchitecture, api: APISchema):
    auth_enabled = bool(arch.roles)
    has_admin = any(r.is_admin for r in arch.roles)

    def build() -> dict:
        pages = []
        if auth_enabled:
            pages.append({"name": "Login", "path": "/login", "layout": "form",
                          "role_required": None, "premium_required": False,
                          "components": [{"type": "form", "title": "Sign in", "entity": None,
                                          "fields": ["email", "password"], "api_endpoint": None}]})

        entity_tables = [e for e in api.endpoints if e.method == "GET" and e.entity != "analytics"]
        seen = set()
        for ep in entity_tables:
            if ep.entity in seen:
                continue
            seen.add(ep.entity)
            list_fields = [f.name for f in ep.response_fields]
            create_ep = api.by_path(ep.path, "POST")
            create_fields = [f.name for f in create_ep.request_fields] if create_ep else list_fields
            pages.append({
                "name": ep.entity.capitalize(), "path": f"/{ep.entity}", "layout": "list",
                "role_required": None, "premium_required": False,
                "components": [
                    {"type": "table", "title": f"All {ep.entity}", "entity": ep.entity,
                     "fields": list_fields, "api_endpoint": ep.path},
                    {"type": "form", "title": f"New {ep.entity}", "entity": ep.entity,
                     "fields": create_fields, "api_endpoint": ep.path},
                ]})

        if "dashboard" in arch.features:
            stats = [{"type": "stat", "title": f"{ep.entity}", "entity": ep.entity,
                      "fields": ["id"], "api_endpoint": ep.path} for ep in entity_tables]
            pages.insert(1 if auth_enabled else 0,
                         {"name": "Dashboard", "path": "/dashboard", "layout": "grid",
                          "role_required": None, "premium_required": False, "components": stats})

        if api.by_path("/api/analytics", "GET"):
            pages.append({"name": "Analytics", "path": "/analytics", "layout": "grid",
                          "role_required": "admin" if has_admin else None,
                          "premium_required": arch.premium,
                          "components": [{"type": "chart", "title": "Metrics", "entity": "analytics",
                                          "fields": ["metric", "value"],
                                          "api_endpoint": "/api/analytics"}]})
        return {"pages": pages}

    return build


def run_ui(llm: LLMClient, arch: AppArchitecture, api: APISchema) -> Tuple[UISchema, StageMetric]:
    return llm.structured(_ui_instruction(arch, api), UISchema, stage="schema.ui",
                          mock_builder=_ui_mock(arch, api))


# -------------------------------------------------------------------------- Auth
def _auth_instruction(arch: AppArchitecture) -> str:
    return (
        "You are the auth-schema stage. Define roles, per-role permissions (actions:\n"
        "create/read/update/delete/view) over each entity, and plans. If premium, add a free\n"
        "and a premium plan with gated_features.\n\n"
        f"ARCHITECTURE:\n{arch.model_dump_json(indent=2)}"
    )


def _auth_mock(arch: AppArchitecture):
    def build() -> dict:
        roles = [r.name for r in arch.roles]
        entities = [e.name for e in arch.entities]
        perms = []
        for r in arch.roles:
            for ent in entities:
                if r.is_admin:
                    actions = ["create", "read", "update", "delete", "view"]
                else:
                    actions = ["create", "read", "update", "view"]
                perms.append({"role": r.name, "resource": ent, "actions": actions})
        plans = []
        if arch.premium:
            plans = [
                {"name": "free", "is_premium": False, "gated_features": []},
                {"name": "premium", "is_premium": True,
                 "gated_features": arch.premium_features or ["analytics"]},
            ]
        return {"auth_enabled": bool(roles), "roles": roles, "permissions": perms, "plans": plans}

    return build


def run_auth(llm: LLMClient, arch: AppArchitecture) -> Tuple[AuthSchema, StageMetric]:
    return llm.structured(_auth_instruction(arch), AuthSchema, stage="schema.auth",
                          mock_builder=_auth_mock(arch))
