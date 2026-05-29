"""Logical validation: business rules implied by the request must actually be realized.

Examples from the task: "admins can see analytics" and "premium plan with payments"."""
from __future__ import annotations

from typing import List

from app.schemas import AppConfig
from app.validation.errors import ValidationError, Code


def validate(config: AppConfig) -> List[ValidationError]:
    errors: List[ValidationError] = []
    arch = config.architecture
    features = set(config.intent.features)
    has_admin = any(r.is_admin for r in arch.roles)

    pages_by_path = {p.path: p for p in config.ui.pages}

    # Analytics requested -> endpoint + page must exist (and be admin-gated).
    if "analytics" in features:
        has_ep = config.api.by_path("/api/analytics", "GET") is not None
        analytics_page = next((p for p in config.ui.pages if "analytic" in p.name.lower()), None)
        if not has_ep or analytics_page is None:
            errors.append(ValidationError(
                layer="logical", code=Code.MISSING_ANALYTICS, component="ui",
                path="ui.pages", message="Analytics requested but endpoint/page missing",
                repair_hint="Add /api/analytics endpoint and an Analytics page.",
                auto_fixable=True))
        elif has_admin and analytics_page.role_required != "admin":
            errors.append(ValidationError(
                layer="logical", code=Code.ANALYTICS_NOT_ADMIN, component="ui",
                path=f"ui.{analytics_page.name}.role_required",
                message="Analytics page must be admin-only ('admins can see analytics')",
                repair_hint="Set role_required='admin'.", auto_fixable=True))

    # Premium requested -> a premium plan with gated features must exist.
    if arch.premium:
        premium_plan = next((p for p in config.auth.plans if p.is_premium), None)
        if premium_plan is None or not premium_plan.gated_features:
            errors.append(ValidationError(
                layer="logical", code=Code.MISSING_PREMIUM_PLAN, component="auth",
                path="auth.plans", message="Premium app but no premium plan with gated features",
                repair_hint="Add a premium plan gating the premium features.",
                auto_fixable=True))

    # Auth enabled -> there must be a login page.
    if config.auth.auth_enabled:
        if not any("login" in p.path.lower() or p.name.lower() == "login" for p in config.ui.pages):
            errors.append(ValidationError(
                layer="logical", code=Code.MISSING_LOGIN_PAGE, component="ui",
                path="ui.pages", message="Auth enabled but no login page",
                repair_hint="Add a Login page.", auto_fixable=True))

    # Dashboard requested -> dashboard page exists.
    if "dashboard" in features and "/dashboard" not in pages_by_path:
        errors.append(ValidationError(
            layer="logical", code=Code.MISSING_DASHBOARD, component="ui",
            path="ui.pages", message="Dashboard requested but no dashboard page",
            repair_hint="Add a Dashboard page.", auto_fixable=True))

    # Every entity should have at least one CRUD endpoint.
    api_entities = {ep.entity for ep in config.api.endpoints}
    for t in config.db.tables:
        if t.name not in api_entities:
            errors.append(ValidationError(
                layer="logical", code=Code.NO_CRUD_FOR_ENTITY, component="api",
                path=f"api.{t.name}", message=f"Table '{t.name}' has no API endpoints",
                repair_hint="Generate CRUD endpoints for the table.", auto_fixable=True))
    return errors


def validate_all(config: AppConfig) -> List[ValidationError]:
    """Run all three validation layers and return the combined error list."""
    from app.validation import structural, referential
    return structural.validate(config) + referential.validate(config) + validate(config)
