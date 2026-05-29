"""Stage 3 contract: database schema."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class Column(BaseModel):
    name: str
    type: str = Field(description="Canonical field type (string/int/bool/datetime/...)")
    nullable: bool = False
    primary_key: bool = False
    foreign_key: Optional[str] = Field(default=None, description="'table.column' reference")


class Table(BaseModel):
    name: str
    columns: List[Column] = Field(default_factory=list)


class DBSchema(BaseModel):
    tables: List[Table] = Field(default_factory=list)

    def table(self, name: str) -> Optional[Table]:
        return next((t for t in self.tables if t.name == name), None)
