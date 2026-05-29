"""Stage 1 — Intent Extraction. Natural language -> structured IntentIR."""
from __future__ import annotations

from typing import Tuple

from app.llm.base import LLMClient
from app.schemas import IntentIR, StageMetric
from app.pipeline import heuristics as H

VAGUE_PROMPTS = {"build an app", "make an app", "make a website", "build something",
                 "create an app", "app", "website", "something"}


def _instruction(prompt: str) -> str:
    return (
        "You are the intent-extraction stage of a software-generation compiler.\n"
        "Parse the user request into a structured IntentIR. Identify the domain, the core\n"
        "data entities (singular nouns), user roles, features (login, dashboard, analytics,\n"
        "payments...), and external integrations.\n"
        "If the request is vague, conflicting, or underspecified, record that in `ambiguities`\n"
        "and set `needs_clarification`. Always record the defaults you assume in `assumptions`.\n\n"
        f"USER REQUEST:\n{prompt}"
    )


def _mock_builder(prompt: str):
    def build() -> dict:
        text = prompt.lower().strip()
        domain = H.detect_domain(text)
        entities = H.detect_entities(text)

        assumptions: list = []
        ambiguities: list = []

        wants_login = H.has_any(text, H.LOGIN_WORDS) or "role" in text
        no_auth = H.has_any(text, H.NO_AUTH_WORDS)
        wants_roles = "role" in text or "admin" in text or "permission" in text
        wants_analytics = H.has_any(text, H.ANALYTICS_WORDS)
        wants_dashboard = H.has_any(text, H.DASHBOARD_WORDS)
        wants_payments = H.has_any(text, H.PAYMENT_WORDS)

        # Conflict detection.
        if no_auth and wants_roles:
            ambiguities.append(
                "Conflicting: authentication is declined but role-based access requires it.")
            assumptions.append("Resolved conflict by enabling authentication (roles need it).")
            wants_login = True
        elif no_auth:
            wants_login = False

        # Vagueness detection.
        is_vague = (len(text) < 12) or (text in VAGUE_PROMPTS) or (not entities and domain == "generic")
        if is_vague:
            ambiguities.append("Request is underspecified: no clear entities or domain.")

        # Fill entity defaults per domain when none were detected.
        if not entities:
            defaults = {
                "crm": ["contact", "deal"], "blog": ["post", "comment"],
                "ecommerce": ["product", "order"], "todo": ["task", "project"],
                "helpdesk": ["ticket"], "events": ["event", "booking"],
                "generic": ["item"],
            }[domain]
            entities = defaults
            assumptions.append(f"Assumed core entities for a {domain} app: {', '.join(entities)}.")

        roles = []
        if wants_login or wants_roles:
            roles = ["admin", "user"]
            for r in H.EXTRA_ROLES:
                if r in text:
                    roles.append(r)
            assumptions.append("Assumed roles admin + user with email/password login.")
        else:
            assumptions.append("No authentication requested; app is open/anonymous.")

        features = []
        if wants_login:
            features.append("login")
        if wants_dashboard or domain in ("crm", "ecommerce"):
            features.append("dashboard")
        if wants_analytics:
            features.append("analytics")
        if wants_payments:
            features.append("premium")
        features.append("crud")

        integrations = ["payments"] if wants_payments else []
        if wants_payments:
            assumptions.append("Premium plan gates analytics/advanced features.")

        name_domain = domain if domain != "generic" else "app"
        return {
            "app_name": f"{name_domain.upper()} App" if domain != "generic" else "Generated App",
            "domain": domain,
            "description": prompt.strip()[:160] or "Generated application",
            "entities": entities,
            "roles": roles,
            "features": sorted(set(features)),
            "integrations": integrations,
            "assumptions": assumptions,
            "ambiguities": ambiguities,
            "needs_clarification": is_vague,
        }

    return build


def run(llm: LLMClient, prompt: str) -> Tuple[IntentIR, StageMetric]:
    return llm.structured(
        _instruction(prompt), IntentIR, stage="intent", mock_builder=_mock_builder(prompt))
