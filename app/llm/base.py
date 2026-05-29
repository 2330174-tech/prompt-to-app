"""LLM client abstraction shared by the real Gemini client and the mock client.

The base class owns the cross-cutting concerns that make the system reliable and
measurable: caching (for determinism + cost), JSON parsing, Pydantic validation, and
per-call metrics. Subclasses only implement how raw text is produced.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Callable, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas import StageMetric

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised when the LLM produces output that cannot be parsed or validated."""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


class LLMClient:
    """Base client. Subclasses implement `_raw`."""

    def __init__(self, default_model: str = "mock"):
        self.default_model = default_model
        self._cache: dict = {}

    # -- public API ---------------------------------------------------------

    def structured(
        self,
        instruction: str,
        schema_model: Type[T],
        *,
        stage: str,
        mock_builder: Optional[Callable[[], dict]] = None,
        model: Optional[str] = None,
    ) -> Tuple[T, StageMetric]:
        """Produce a validated instance of `schema_model`.

        `instruction` is the full prompt for a real LLM and the cache key for both
        paths. `mock_builder`, when provided, is a deterministic fallback used when no
        real model is configured.
        """
        model = model or self.default_model
        key = self._cache_key(stage, instruction, model)
        if key in self._cache:
            raw_dict, in_tok, out_tok = self._cache[key]
            metric = StageMetric(stage=stage, model=model, latency_ms=0.0,
                                  input_tokens=in_tok, output_tokens=out_tok, cache_hit=True)
            return schema_model.model_validate(raw_dict), metric

        start = time.time()
        raw_dict, in_tok, out_tok, used_model = self._produce(
            instruction, schema_model, stage=stage, mock_builder=mock_builder, model=model
        )
        latency = (time.time() - start) * 1000.0

        try:
            instance = schema_model.model_validate(raw_dict)
        except ValidationError as exc:
            raise LLMError(f"{stage}: output failed schema validation: {exc}",
                           raw=json.dumps(raw_dict)) from exc

        self._cache[key] = (raw_dict, in_tok, out_tok)
        metric = StageMetric(stage=stage, model=used_model, latency_ms=latency,
                             input_tokens=in_tok, output_tokens=out_tok, cache_hit=False)
        return instance, metric

    # -- internals ----------------------------------------------------------

    def _produce(self, instruction, schema_model, *, stage, mock_builder, model):
        raise NotImplementedError

    @staticmethod
    def _cache_key(stage: str, instruction: str, model: str) -> str:
        h = hashlib.sha256(f"{stage}::{model}::{instruction}".encode()).hexdigest()
        return h[:32]

    @staticmethod
    def parse_json(text: str) -> dict:
        """Best-effort JSON extraction from model output (handles code fences/prose)."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Salvage the outermost JSON object.
            first, last = text.find("{"), text.rfind("}")
            if first != -1 and last != -1 and last > first:
                return json.loads(text[first:last + 1])
            raise
