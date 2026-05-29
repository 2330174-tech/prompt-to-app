"""The final linked artifact: a complete, validated application configuration."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .intent import IntentIR
from .architecture import AppArchitecture
from .db import DBSchema
from .api import APISchema
from .ui import UISchema
from .auth import AuthSchema


class StageMetric(BaseModel):
    stage: str
    model: str = ""
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    repairs: int = 0
    cache_hit: bool = False


class AppConfig(BaseModel):
    intent: IntentIR
    architecture: AppArchitecture
    db: DBSchema
    api: APISchema
    ui: UISchema
    auth: AuthSchema
    metrics: List[StageMetric] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GenerationResult(BaseModel):
    """What the orchestrator returns: either a config, a failure, or clarifications."""

    status: str = Field(default="ok", description="ok | needs_clarification | failed")
    config: Optional[AppConfig] = None
    clarifications: List[str] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    total_retries: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    est_cost_usd: float = 0.0
    failure_types: List[str] = Field(default_factory=list)
