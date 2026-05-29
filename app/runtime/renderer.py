"""Renders a running AppConfig into a live HTML preview (server-side).

Pages, tables, forms, stats and charts are produced from the UI schema and populated with
real data from the Interpreter. Role and plan switchers let a reviewer watch auth and
premium gating work live."""
from __future__ import annotations

import html
from typing import Optional

from app.schemas import AppConfig
from app.runtime.interpreter import Interpreter

_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#1c2330;background:#f6f8fb}
.wrap{display:flex;min-height:100vh}
.side{width:200px;background:#0f1b2d;color:#cdd7e6;padding:16px 0}
.side h3{color:#fff;font-size:13px;text-transform:uppercase;letter-spacing:.05em;padding:0 16px;opacity:.6}
.side a{display:block;padding:9px 16px;color:#cdd7e6;text-decoration:none;font-size:14px}
.side a.active{background:#1d4ed8;color:#fff}
.side a.locked{opacity:.45}
.main{flex:1;padding:24px 30px}
.bar{display:flex;gap:18px;align-items:center;font-size:13px;margin-bottom:18px;color:#475569}
.bar select{padding:4px 6px;border-radius:6px;border:1px solid #cbd5e1}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 18px;margin-bottom:18px}
.card h2{margin:0 0 12px;font-size:16px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #eef2f7}
th{color:#64748b;font-weight:600}
.stat{display:inline-block;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 20px;margin:0 12px 12px 0;min-width:120px}
.stat .n{font-size:26px;font-weight:700;color:#1d4ed8}
.stat .l{font-size:12px;color:#64748b;text-transform:capitalize}
input{padding:7px 9px;border:1px solid #cbd5e1;border-radius:6px;margin:0 8px 8px 0;font-size:13px}
button{background:#1d4ed8;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer}
.bar-chart div{background:#1d4ed8;color:#fff;font-size:12px;padding:4px 8px;border-radius:4px;margin:4px 0}
.locked-msg{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;padding:14px;border-radius:10px}
.badge{font-size:11px;background:#eef2ff;color:#3730a3;border-radius:10px;padding:2px 8px;margin-left:6px}
"""


def _e(s) -> str:
    return html.escape(str(s))


def _accessible(page, role: Optional[str], plan: str):
    if page.role_required and role != page.role_required and role != "admin":
        return False, f"Requires role '{page.role_required}'"
    if page.premium_required and plan != "premium":
        return False, "Requires the premium plan"
    return True, ""


def render(config: AppConfig, interp: Interpreter, cid: str, page_path: str,
           role: Optional[str], plan: str) -> str:
    pages = config.ui.pages
    if not pages:
        return "<p>No pages generated.</p>"
    current = next((p for p in pages if p.path == page_path), pages[0])
    roles = config.auth.roles or ["(none)"]

    # sidebar
    links = []
    for p in pages:
        ok, _ = _accessible(p, role, plan)
        cls = "active" if p.path == current.path else ""
        if not ok:
            cls += " locked"
        lock = " 🔒" if not ok else ""
        href = f"/preview/{cid}?page={_e(p.path)}&role={_e(role or '')}&plan={_e(plan)}"
        links.append(f'<a class="{cls}" href="{href}">{_e(p.name)}{lock}</a>')

    # role/plan switcher (reloads page)
    role_opts = "".join(
        f'<option value="{_e(r)}" {"selected" if r==role else ""}>{_e(r)}</option>'
        for r in roles)
    plan_names = [pl.name for pl in config.auth.plans] or ["free"]
    plan_opts = "".join(
        f'<option value="{_e(p)}" {"selected" if p==plan else ""}>{_e(p)}</option>'
        for p in plan_names)
    switch_js = (f"location.href='/preview/{cid}?page={_e(current.path)}"
                 "&role='+document.getElementById('rl').value"
                 "+'&plan='+document.getElementById('pl').value")
    bar = (f'<div class="bar"><b>{_e(config.architecture.app_name)}</b>'
           f'<span>Role: <select id="rl" onchange="{switch_js}">{role_opts}</select></span>'
           f'<span>Plan: <select id="pl" onchange="{switch_js}">{plan_opts}</select></span></div>')

    ok, reason = _accessible(current, role, plan)
    body = (f'<div class="locked-msg">🔒 <b>{_e(current.name)}</b> is locked. {_e(reason)}.'
            f' Switch role/plan above.</div>') if not ok else _render_components(config, interp, cid, current, role, plan)

    nav = "".join(links)
    return f"""<!doctype html><html><head><meta charset=utf-8><style>{_CSS}</style></head>
<body><div class="wrap"><div class="side"><h3>{_e(config.architecture.app_name)}</h3>{nav}</div>
<div class="main">{bar}{body}</div></div></body></html>"""


def _render_components(config, interp, cid, page, role, plan) -> str:
    out = [f"<h1 style='font-size:20px'>{_e(page.name)}</h1>"]
    for comp in page.components:
        if comp.type == "table":
            out.append(_table(interp, comp, role))
        elif comp.type == "form":
            out.append(_form(cid, comp, page, role, plan))
        elif comp.type == "stat":
            out.append(_stat(interp, comp, role))
        elif comp.type == "chart":
            out.append(_chart(interp, comp, role))
        else:
            out.append(f'<div class="card"><b>{_e(comp.title or comp.type)}</b></div>')
    # group stats into one card visually
    return "".join(out)


def _table(interp, comp, role) -> str:
    status, rows = (200, [])
    if comp.api_endpoint:
        status, rows = interp.handle("GET", comp.api_endpoint, role=role)
    if status == 403:
        return f'<div class="locked-msg">🔒 API denied: {_e(rows.get("error"))}</div>'
    rows = rows if isinstance(rows, list) else []
    fields = comp.fields or (list(rows[0].keys()) if rows else [])
    head = "".join(f"<th>{_e(f)}</th>" for f in fields)
    body = "".join("<tr>" + "".join(f"<td>{_e(r.get(f,''))}</td>" for f in fields) + "</tr>"
                   for r in rows)
    return (f'<div class="card"><h2>{_e(comp.title or "Records")} '
            f'<span class="badge">{len(rows)} rows</span></h2>'
            f'<table><tr>{head}</tr>{body}</table></div>')


def _form(cid, comp, page, role, plan) -> str:
    inputs = "".join(
        f'<input name="{_e(f)}" placeholder="{_e(f)}">' for f in comp.fields if f not in ("id",))
    method, path = "POST", comp.api_endpoint or ""
    hidden = (f'<input type=hidden name=_method value="{method}">'
              f'<input type=hidden name=_path value="{_e(path)}">'
              f'<input type=hidden name=_page value="{_e(page.path)}">'
              f'<input type=hidden name=_role value="{_e(role or "")}">'
              f'<input type=hidden name=_plan value="{_e(plan)}">')
    return (f'<div class="card"><h2>{_e(comp.title or "New record")}</h2>'
            f'<form method="post" action="/preview/{cid}/run">{hidden}{inputs}'
            f'<button>Submit</button></form></div>')


def _stat(interp, comp, role) -> str:
    count = 0
    if comp.api_endpoint:
        status, rows = interp.handle("GET", comp.api_endpoint, role=role)
        count = len(rows) if isinstance(rows, list) else 0
    return (f'<div class="stat"><div class="n">{count}</div>'
            f'<div class="l">{_e(comp.title or comp.entity)}</div></div>')


def _chart(interp, comp, role) -> str:
    status, data = interp.handle("GET", comp.api_endpoint or "/api/analytics", role=role)
    if status == 403:
        return f'<div class="locked-msg">🔒 {_e(data.get("error"))}</div>'
    data = data if isinstance(data, list) else []
    mx = max((d.get("value", 0) for d in data), default=1) or 1
    bars = "".join(
        f'<div style="width:{max(8,int(100*d.get("value",0)/mx))}%">'
        f'{_e(d.get("metric"))}: {_e(d.get("value"))}</div>' for d in data)
    return f'<div class="card"><h2>{_e(comp.title or "Analytics")}</h2><div class="bar-chart">{bars}</div></div>'
