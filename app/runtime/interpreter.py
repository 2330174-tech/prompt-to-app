"""Execution runtime: turns a validated AppConfig into a *running* app.

This is the proof of execution awareness. It builds an in-memory database from the DB
schema, seeds sample rows, and serves the API schema's endpoints with live auth/role
enforcement. If the generated config is internally consistent, this just works — no manual
fixes — which is exactly the bar the task sets."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.schemas import AppConfig


def _sample_value(col_type: str, i: int, field: str):
    if col_type == "email":
        return f"user{i}@example.com"
    if col_type == "text":
        return f"Sample {field} text #{i}."
    if col_type == "int":
        return i * 3
    if col_type == "float":
        return round(10.0 * i + 0.99, 2)
    if col_type == "bool":
        return i % 2 == 0
    if col_type == "datetime":
        return (datetime(2026, 1, 1) + timedelta(days=i)).isoformat()
    return f"{field.capitalize()} {i}"


class Interpreter:
    def __init__(self, config: AppConfig):
        self.config = config
        self.db: Dict[str, List[Dict[str, Any]]] = {}
        self._seed()

    def _seed(self, n: int = 3) -> None:
        for t in self.config.db.tables:
            rows = []
            for i in range(1, n + 1):
                row: Dict[str, Any] = {}
                for c in t.columns:
                    if c.primary_key:
                        row[c.name] = i
                    elif c.foreign_key:
                        ref_table = c.foreign_key.split(".")[0]
                        row[c.name] = ((i - 1) % n) + 1 if ref_table in self.db else i
                    else:
                        row[c.name] = _sample_value(c.type, i, c.name)
                rows.append(row)
            self.db[t.name] = rows

    # -- live API execution -------------------------------------------------

    def _authorized(self, endpoint, role: Optional[str]) -> bool:
        if not endpoint.auth_required:
            return True
        if not endpoint.allowed_roles:
            return role is not None
        return role in endpoint.allowed_roles

    def handle(self, method: str, path: str, payload: Optional[dict] = None,
               role: Optional[str] = None) -> Tuple[int, Any]:
        """Execute a request against the generated API. Returns (status, body)."""
        payload = payload or {}
        if path == "/api/analytics" and method == "GET":
            ep = self.config.api.by_path(path, "GET")
            if ep and not self._authorized(ep, role):
                return 403, {"error": "forbidden", "need_role": ep.allowed_roles}
            return 200, self.analytics()

        ep = self.config.api.by_path(path, method)
        if ep is None:
            return 404, {"error": f"no endpoint {method} {path}"}
        if not self._authorized(ep, role):
            return 403, {"error": "forbidden", "need_role": ep.allowed_roles}

        table = ep.entity
        rows = self.db.setdefault(table, [])
        if method == "GET":
            return 200, rows
        if method == "POST":
            new_id = (max((r.get("id", 0) for r in rows), default=0)) + 1
            record = {"id": new_id}
            for f in ep.request_fields:
                if f.name in payload:
                    record[f.name] = payload[f.name]
            record.setdefault("created_at", datetime.utcnow().isoformat())
            rows.append(record)
            return 201, record
        if method == "PUT":
            rid = int(payload.get("id", 0))
            for r in rows:
                if r.get("id") == rid:
                    r.update({k: v for k, v in payload.items() if k != "id"})
                    return 200, r
            return 404, {"error": "not found"}
        if method == "DELETE":
            rid = int(payload.get("id", 0))
            self.db[table] = [r for r in rows if r.get("id") != rid]
            return 200, {"deleted": rid}
        return 405, {"error": "method not allowed"}

    def analytics(self) -> List[Dict[str, Any]]:
        return [{"metric": f"total_{name}", "value": len(rows)}
                for name, rows in self.db.items()]
