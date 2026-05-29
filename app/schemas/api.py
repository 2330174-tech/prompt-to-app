"""Stage 3 contract: REST API schema."""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class IOField(BaseModel):
    name: str
    type: str
    required: bool = True


class Endpoint(BaseModel):
    path: str = Field(description="e.g. /api/contacts")
    method: str = Field(description="GET/POST/PUT/DELETE")
    entity: str = Field(description="DB table this endpoint operates on")
    description: str = ""
    request_fields: List[IOField] = Field(default_factory=list)
    response_fields: List[IOField] = Field(default_factory=list)
    auth_required: bool = True
    allowed_roles: List[str] = Field(default_factory=list)


class APISchema(BaseModel):
    endpoints: List[Endpoint] = Field(default_factory=list)

    def by_path(self, path: str, method: str = None):
        for e in self.endpoints:
            if e.path == path and (method is None or e.method == method):
                return e
        return None
