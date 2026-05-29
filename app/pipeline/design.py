"""Stage 2 — System Design. IntentIR -> AppArchitecture (entities, roles, flows)."""
from __future__ import annotations

from typing import Tuple

from app.llm.base import LLMClient
from app.schemas import IntentIR, AppArchitecture, StageMetric
from app.pipeline import heuristics as H


def _instruction(intent: IntentIR) -> str:
    return (
        "You are the system-design stage of a software-generation compiler.\n"
        "Given the structured intent, design the application architecture: for every entity\n"
        "define typed fields (types: string,text,int,float,bool,datetime,email,ref). Use 'ref'\n"
        "with a `ref` target for relationships. Define roles (mark admins) and key user flows.\n"
        "If payments/premium are present, set premium=true and list premium_features.\n\n"
        f"INTENT:\n{intent.model_dump_json(indent=2)}"
    )


def _mock_builder(intent: IntentIR):
    def build() -> dict:
        has_auth = bool(intent.roles)
        entities = list(intent.entities)
        # Auth implies a user entity to own/relate records.
        if has_auth and "user" not in entities:
            entities = entities + ["user"]

        entity_objs = []
        for e in entities:
            entity_objs.append({"name": e, "fields": H.fields_for(e)})

        roles = []
        for r in (intent.roles or []):
            roles.append({"name": r, "description": f"{r} role",
                          "is_admin": r == "admin"})

        premium = "premium" in intent.features or "payments" in intent.integrations
        premium_features = []
        if premium:
            premium_features = [f for f in ("analytics", "dashboard") if f in intent.features] or ["analytics"]

        flows = [{"name": "crud", "description": "Create/read/update/delete records",
                  "steps": ["open page", "submit form", "list updates"]}]
        if has_auth:
            flows.insert(0, {"name": "auth", "description": "Login and role routing",
                             "steps": ["enter credentials", "validate", "route by role"]})
        if premium:
            flows.append({"name": "premium_gating", "description": "Gate features by plan",
                          "steps": ["check plan", "allow or block"]})

        return {
            "app_name": intent.app_name,
            "entities": entity_objs,
            "roles": roles,
            "flows": flows,
            "features": list(intent.features),
            "premium": premium,
            "premium_features": premium_features,
        }

    return build


def run(llm: LLMClient, intent: IntentIR) -> Tuple[AppArchitecture, StageMetric]:
    return llm.structured(
        _instruction(intent), AppArchitecture, stage="design", mock_builder=_mock_builder(intent))
