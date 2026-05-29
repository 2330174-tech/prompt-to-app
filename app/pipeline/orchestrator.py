"""The compiler driver: runs every stage, then the validation+repair loop.

Returns a GenerationResult with the config (if successful), clarifications (if the prompt
was too vague and mode='clarify'), and full metrics (latency, tokens, retries, cost).
"""
from __future__ import annotations

import time
from typing import List, Optional

from app.llm.base import LLMClient, LLMError
from app.llm import build_client
from app.schemas import AppConfig, GenerationResult, StageMetric
from app.pipeline import intent as intent_stage
from app.pipeline import design as design_stage
from app.pipeline import schema_gen
from app.pipeline import refine
from app.validation import validate_all
from app.repair import repair

# Approximate Gemini 2.0 Flash pricing (USD per token) for the cost-vs-quality analysis.
# The free tier costs nothing; these are used only to report what it *would* cost.
PRICE_IN = 0.075 / 1_000_000
PRICE_OUT = 0.30 / 1_000_000

MAX_REPAIR_ROUNDS = 3


def _clarifying_questions(intent) -> List[str]:
    qs = list(intent.ambiguities)
    qs.append("What are the core data entities the app should manage?")
    qs.append("Who are the users/roles, and is login required?")
    if not intent.integrations:
        qs.append("Are payments or a premium plan needed?")
    return qs


def generate(prompt: str, *, llm: Optional[LLMClient] = None, mode: str = "assume",
             api_key: Optional[str] = None, model: str = "gemini-2.0-flash") -> GenerationResult:
    """Compile a natural-language prompt into a validated AppConfig.

    mode='assume' (default): proceed on vague prompts using documented assumptions.
    mode='clarify': stop on vague prompts and return clarifying questions.
    """
    llm = llm or build_client(api_key, default_model=model)
    metrics: List[StageMetric] = []
    t0 = time.time()

    try:
        intent, m = intent_stage.run(llm, prompt)
        metrics.append(m)
    except LLMError as exc:
        return GenerationResult(status="failed", errors=[{"stage": "intent", "message": str(exc)}],
                                failure_types=["intent_generation_error"])

    if intent.needs_clarification and mode == "clarify":
        return GenerationResult(status="needs_clarification",
                                clarifications=_clarifying_questions(intent),
                                total_latency_ms=(time.time() - t0) * 1000.0)

    try:
        arch, m = design_stage.run(llm, intent)
        metrics.append(m)
        db, m = schema_gen.run_db(llm, arch)
        metrics.append(m)
        api, m = schema_gen.run_api(llm, arch, db)
        metrics.append(m)
        ui, m = schema_gen.run_ui(llm, arch, api)
        metrics.append(m)
        auth, m = schema_gen.run_auth(llm, arch)
        metrics.append(m)
    except LLMError as exc:
        return GenerationResult(status="failed",
                                errors=[{"stage": "schema_generation", "message": str(exc)}],
                                failure_types=["schema_generation_error"])

    config = refine.assemble(intent, arch, db, api, ui, auth)

    # ---- validation + repair loop ----
    total_repairs = 0
    rounds = 0
    remaining_unfixable: list = []
    for rounds in range(1, MAX_REPAIR_ROUNDS + 1):
        errors = validate_all(config)
        if not errors:
            break
        config, fixed, remaining_unfixable = repair(config, errors)
        total_repairs += fixed
        if not fixed:  # no deterministic progress possible
            break
    else:
        errors = validate_all(config)

    final_errors = validate_all(config)
    config.metrics = metrics

    in_tok = sum(m.input_tokens for m in metrics)
    out_tok = sum(m.output_tokens for m in metrics)
    result = GenerationResult(
        config=config,
        total_latency_ms=(time.time() - t0) * 1000.0,
        total_retries=total_repairs,
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
        est_cost_usd=round(in_tok * PRICE_IN + out_tok * PRICE_OUT, 8),
    )

    if final_errors:
        result.status = "failed"
        result.errors = [e.model_dump() for e in final_errors]
        result.failure_types = sorted({e.code for e in final_errors})
    else:
        result.status = "ok"
    return result
