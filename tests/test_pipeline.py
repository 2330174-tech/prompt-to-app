"""Tests for the compiler: happy path, determinism, repair, failure handling, execution."""
from __future__ import annotations

from app.pipeline import generate
from app.validation import validate_all
from app.repair import repair
from app.runtime import Interpreter
from app.schemas import Column
from app.schemas.api import IOField

CRM = ("Build a CRM with login, contacts, dashboard, role-based access, and premium "
       "plan with payments. Admins can see analytics.")


def test_happy_path_is_valid_and_consistent():
    r = generate(CRM)
    assert r.status == "ok"
    assert validate_all(r.config) == []


def test_determinism_same_input_same_output():
    a = generate(CRM).config.model_dump()
    b = generate(CRM).config.model_dump()
    # metrics differ (latency); compare the actual schema layers.
    for layer in ("intent", "architecture", "db", "api", "ui", "auth"):
        assert a[layer] == b[layer]


def test_cross_layer_consistency_ui_to_api_to_db():
    c = generate(CRM).config
    table_cols = {t.name: {col.name for col in t.columns} for t in c.db.tables}
    for ep in c.api.endpoints:
        if ep.entity in table_cols:
            for f in ep.response_fields:
                assert f.name in table_cols[ep.entity] or f.name == "id"
    api_paths = {ep.path for ep in c.api.endpoints}
    for p in c.ui.pages:
        for comp in p.components:
            if comp.api_endpoint:
                assert comp.api_endpoint in api_paths


def test_repair_fixes_injected_damage():
    c = generate("Blog with posts and comments and login").config
    c.api.endpoints[0].response_fields.append(IOField(name="ghost", type="string"))
    c.db.tables[0].columns.append(Column(name="x", type="WEIRD", foreign_key="nope.id"))
    errs = validate_all(c)
    assert errs, "damage should be detected"
    c, fixed, remaining = repair(c, errs)
    assert fixed >= 1
    assert validate_all(c) == []


def test_admins_see_analytics_rule():
    c = generate(CRM).config
    analytics = next(p for p in c.ui.pages if "analytic" in p.name.lower())
    assert analytics.role_required == "admin"
    assert c.api.by_path("/api/analytics", "GET") is not None


def test_premium_gating_rule():
    c = generate(CRM).config
    premium = [p for p in c.auth.plans if p.is_premium]
    assert premium and premium[0].gated_features


def test_vague_prompt_asks_for_clarification():
    r = generate("make an app", mode="clarify")
    assert r.status == "needs_clarification"
    assert r.clarifications


def test_conflict_is_flagged_but_resolved():
    r = generate("A todo app but with no login, yet only admins can delete tasks.")
    assert any("conflict" in a.lower() for a in r.config.intent.ambiguities)
    # resolved by enabling auth
    assert r.config.auth.auth_enabled


def test_generated_app_executes():
    c = generate(CRM).config
    interp = Interpreter(c)
    get_ep = next(e for e in c.api.endpoints if e.method == "GET")
    status, body = interp.handle("GET", get_ep.path, role="admin")
    assert status == 200
    assert isinstance(body, list)


def test_auth_enforced_at_runtime():
    c = generate(CRM).config
    interp = Interpreter(c)
    # analytics is admin-only; a non-admin must be blocked.
    status, _ = interp.handle("GET", "/api/analytics", role="user")
    assert status == 403
    status_ok, _ = interp.handle("GET", "/api/analytics", role="admin")
    assert status_ok == 200
