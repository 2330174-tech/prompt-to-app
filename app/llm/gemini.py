"""Google Gemini client (free tier). Uses JSON output mode + temperature=0.

Strict schema enforcement = JSON mode here + Pydantic re-validation in the base class +
the repair engine downstream. The JSON Schema is embedded in the instruction so the model
knows the exact contract to satisfy.
"""
from __future__ import annotations

import json
from typing import Optional

from app.llm.base import LLMClient, LLMError


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, default_model: str = "gemini-2.0-flash"):
        super().__init__(default_model=default_model)
        import google.generativeai as genai  # imported lazily so offline runs need no dep

        genai.configure(api_key=api_key)
        self._genai = genai
        self.degraded = False       # set True if any stage fell back to the deterministic engine
        self.last_error = ""

    def _produce(self, instruction, schema_model, *, stage, mock_builder, model):
        schema_json = json.dumps(schema_model.model_json_schema(), indent=2)
        prompt = (
            instruction
            + "\n\nReturn ONLY a JSON object that conforms exactly to this JSON Schema. "
            + "No prose, no markdown.\n\nJSON Schema:\n" + schema_json
        )
        try:
            gen_model = self._genai.GenerativeModel(model)
            resp = gen_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                },
            )
            raw_dict = self.parse_json(resp.text)
            usage = getattr(resp, "usage_metadata", None)
            in_tok = getattr(usage, "prompt_token_count", 0) or 0
            out_tok = getattr(usage, "candidates_token_count", 0) or 0
            return raw_dict, in_tok, out_tok, model
        except Exception as exc:  # quota/network/parse — degrade instead of hard-failing
            self.degraded = True
            self.last_error = str(exc)
            if mock_builder is not None:
                raw = mock_builder()
                return (raw, max(1, len(instruction) // 4), max(1, len(str(raw)) // 4),
                        f"mock-fallback({model})")
            raise LLMError(f"{stage}: Gemini call failed and no fallback: {exc}") from exc


def build_client(api_key: Optional[str], default_model: str = "gemini-2.0-flash"):
    """Factory: real Gemini client when a key is present, else deterministic mock."""
    if api_key:
        return GeminiClient(api_key, default_model=default_model)
    from app.llm.mock import MockLLMClient

    return MockLLMClient()
