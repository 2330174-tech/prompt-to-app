"""Deterministic mock client.

Lets the whole system run offline with no API key. The per-stage `mock_builder`
closures (defined in the pipeline stages) hold the heuristic logic, so this client is
trivial: it just runs the builder. Because builders are pure functions of their input,
the mock path is perfectly deterministic and doubles as a baseline.
"""
from __future__ import annotations

from app.llm.base import LLMClient, LLMError


class MockLLMClient(LLMClient):
    def __init__(self):
        super().__init__(default_model="mock")

    def _produce(self, instruction, schema_model, *, stage, mock_builder, model):
        if mock_builder is None:
            raise LLMError(f"{stage}: no mock builder available in offline mode")
        raw = mock_builder()
        # Token counts are estimated from text length so metrics stay meaningful offline.
        in_tok = max(1, len(instruction) // 4)
        out_tok = max(1, len(str(raw)) // 4)
        return raw, in_tok, out_tok, "mock"
