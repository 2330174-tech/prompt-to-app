"""Stage 4 — Refinement / Linking.

Deterministic pass that assembles the four generated layers into one AppConfig and
normalizes obvious cross-layer drift (a 'linker' in the compiler analogy). It does NOT
call the LLM: deterministic normalization is cheaper and more reliable than asking a model
to be consistent. Anything it cannot resolve is left for the validation+repair loop.
"""
from __future__ import annotations

from app.schemas import (IntentIR, AppArchitecture, DBSchema, APISchema, UISchema,
                         AuthSchema, AppConfig)


def assemble(intent: IntentIR, arch: AppArchitecture, db: DBSchema, api: APISchema,
             ui: UISchema, auth: AuthSchema) -> AppConfig:
    # Ensure auth roles cover the architecture's roles (so API allowed_roles resolve).
    arch_roles = [r.name for r in arch.roles]
    for r in arch_roles:
        if r not in auth.roles:
            auth.roles.append(r)
    auth.auth_enabled = bool(arch_roles)

    return AppConfig(intent=intent, architecture=arch, db=db, api=api, ui=ui, auth=auth)
