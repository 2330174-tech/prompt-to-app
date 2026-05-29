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

    def _produce(self, instruction, schema_model, *, stage, mock_builder, model):
        schema_json = json.dumps(schema_model.model_json_schema(), indent=2)
        prompt = (
            instruction
            + "\n\nReturn ONLY a JSON object that conforms exactly to this JSON Schema. "
            + "No prose, no markdown.\n\nJSON Schema:\n" + schema_json
        )
        gen_model = self._genai.GenerativeModel(model)
        try:
            resp = gen_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json",
                },
            )
        except Exception as exc:  # network/quota/etc.
            raise LLMError(f"{stage}: Gemini call failed: {exc}") from exc

        raw_dict = self.parse_json(resp.text)
        usage = getattr(resp, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", 0) or 0
        out_tok = getattr(usage, "candidates_token_count", 0) or 0
        return raw_dict, in_tok, out_tok, model


def build_client(api_key: Optional[str], default_model: str = "gemini-2.0-flash"):
    """Factory: real Gemini client when a key is present, else deterministic mock."""
    if api_key:
        return GeminiClient(api_key, default_model=default_model)
    from app.llm.mock import MockLLMClient

    return MockLLMClient()
