"""Deterministic heuristics powering offline (mock) generation and the baseline.

These are pure functions of their inputs, which is what makes the mock pipeline
reproducible. Real-LLM mode does not use these except as fallbacks; it relies on the
prompt instructions defined in each stage.
"""
from __future__ import annotations

from typing import Dict, List

# Field templates per known entity. Types use the shared FIELD_TYPES vocabulary.
ENTITY_TEMPLATES: Dict[str, List[dict]] = {
    "contact": [
        {"name": "name", "type": "string", "required": True},
        {"name": "email", "type": "email", "required": True},
        {"name": "phone", "type": "string", "required": False},
        {"name": "company", "type": "string", "required": False},
    ],
    "customer": [
        {"name": "name", "type": "string", "required": True},
        {"name": "email", "type": "email", "required": True},
        {"name": "phone", "type": "string", "required": False},
    ],
    "lead": [
        {"name": "name", "type": "string", "required": True},
        {"name": "email", "type": "email", "required": True},
        {"name": "status", "type": "string", "required": True},
        {"name": "source", "type": "string", "required": False},
    ],
    "deal": [
        {"name": "title", "type": "string", "required": True},
        {"name": "amount", "type": "float", "required": True},
        {"name": "stage", "type": "string", "required": True},
        {"name": "contact", "type": "ref", "required": False, "ref": "contact"},
    ],
    "product": [
        {"name": "name", "type": "string", "required": True},
        {"name": "price", "type": "float", "required": True},
        {"name": "description", "type": "text", "required": False},
        {"name": "stock", "type": "int", "required": True},
    ],
    "order": [
        {"name": "customer", "type": "ref", "required": True, "ref": "customer"},
        {"name": "total", "type": "float", "required": True},
        {"name": "status", "type": "string", "required": True},
    ],
    "post": [
        {"name": "title", "type": "string", "required": True},
        {"name": "body", "type": "text", "required": True},
        {"name": "author", "type": "ref", "required": True, "ref": "user"},
        {"name": "published", "type": "bool", "required": True},
    ],
    "comment": [
        {"name": "body", "type": "text", "required": True},
        {"name": "post", "type": "ref", "required": True, "ref": "post"},
        {"name": "author", "type": "ref", "required": True, "ref": "user"},
    ],
    "task": [
        {"name": "title", "type": "string", "required": True},
        {"name": "description", "type": "text", "required": False},
        {"name": "done", "type": "bool", "required": True},
        {"name": "due_date", "type": "datetime", "required": False},
        {"name": "assignee", "type": "ref", "required": False, "ref": "user"},
    ],
    "project": [
        {"name": "name", "type": "string", "required": True},
        {"name": "description", "type": "text", "required": False},
        {"name": "owner", "type": "ref", "required": True, "ref": "user"},
    ],
    "ticket": [
        {"name": "subject", "type": "string", "required": True},
        {"name": "description", "type": "text", "required": True},
        {"name": "status", "type": "string", "required": True},
        {"name": "priority", "type": "string", "required": True},
        {"name": "assignee", "type": "ref", "required": False, "ref": "user"},
    ],
    "event": [
        {"name": "title", "type": "string", "required": True},
        {"name": "date", "type": "datetime", "required": True},
        {"name": "location", "type": "string", "required": False},
        {"name": "description", "type": "text", "required": False},
    ],
    "booking": [
        {"name": "user", "type": "ref", "required": True, "ref": "user"},
        {"name": "event", "type": "ref", "required": True, "ref": "event"},
        {"name": "status", "type": "string", "required": True},
    ],
}

USER_FIELDS = [
    {"name": "name", "type": "string", "required": True},
    {"name": "email", "type": "email", "required": True},
    {"name": "password", "type": "string", "required": True},
    {"name": "role", "type": "string", "required": True},
]

GENERIC_FIELDS = [
    {"name": "name", "type": "string", "required": True},
    {"name": "description", "type": "text", "required": False},
]

# Domain detection: domain -> trigger keywords.
DOMAINS = {
    "crm": ["crm", "contact", "lead", "deal", "sales", "pipeline"],
    "blog": ["blog", "post", "article", "comment", "cms"],
    "ecommerce": ["shop", "store", "ecommerce", "e-commerce", "product", "order", "cart"],
    "todo": ["todo", "task", "project", "kanban"],
    "helpdesk": ["ticket", "support", "helpdesk", "issue"],
    "events": ["event", "booking", "calendar", "reservation"],
}

# Candidate entities to look for (singular).
KNOWN_ENTITIES = list(ENTITY_TEMPLATES.keys())

EXTRA_ROLES = ["manager", "editor", "viewer", "agent", "support"]

LOGIN_WORDS = ["login", "log in", "sign in", "signup", "sign up", "auth", "account", "register"]
ANALYTICS_WORDS = ["analytics", "report", "metric", "insight", "stats"]
DASHBOARD_WORDS = ["dashboard", "overview", "home"]
PAYMENT_WORDS = ["payment", "premium", "subscription", "billing", "plan", "stripe", "paid", "pro tier"]
NO_AUTH_WORDS = ["no login", "without login", "no auth", "no authentication", "without auth"]


def plural(word: str) -> str:
    w = word.lower().strip().replace(" ", "_")
    if w.endswith("y") and w[-2:-1] not in "aeiou":
        return w[:-1] + "ies"
    if w.endswith(("s", "x", "z", "ch", "sh")):
        return w + "es"
    return w + "s"


def detect_entities(text: str) -> List[str]:
    found = []
    for ent in KNOWN_ENTITIES:
        if ent in text or plural(ent) in text:
            found.append(ent)
    return found


def detect_domain(text: str) -> str:
    for domain, kws in DOMAINS.items():
        if any(k in text for k in kws):
            return domain
    return "generic"


def has_any(text: str, words: List[str]) -> bool:
    return any(w in text for w in words)


def fields_for(entity: str) -> List[dict]:
    if entity == "user":
        return [dict(f) for f in USER_FIELDS]
    tmpl = ENTITY_TEMPLATES.get(entity)
    return [dict(f) for f in (tmpl if tmpl else GENERIC_FIELDS)]
