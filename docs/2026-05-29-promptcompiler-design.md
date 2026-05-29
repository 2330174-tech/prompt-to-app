# PromptCompiler — A Compiler for Software Generation

**Date:** 2026-05-29
**Status:** Approved

## Objective

Build a system that behaves like a compiler for software generation:

> Natural language → structured config → validated → executable → working application (via a runtime)

This is a system-design + reliability + control problem, not a prompt-engineering task.
Reference product: base44.com.

## The Compiler Analogy

Each compiler phase maps to a pipeline stage with a strict typed contract between stages.

| Compiler phase        | Stage                  | Typed output                                            |
|-----------------------|------------------------|---------------------------------------------------------|
| Lex / Parse           | 1. Intent Extraction   | `IntentIR` (domain, entities, roles, features, integrations, assumptions, ambiguities) |
| Semantic analysis     | 2. System Design       | `AppArchitecture` (entities+fields+relations, roles, flows) |
| Code generation       | 3. Schema Generation   | `DBSchema`, `APISchema`, `UISchema`, `AuthSchema`       |
| Linking / optimization| 4. Refinement          | unified `AppConfig` with cross-layer links resolved     |
| Validation passes     | Validation + Repair    | structured errors → targeted repairs                    |
| Runtime               | Execution renderer      | a live working app preview                              |

A single prompt is never used. Generation is modular by design.

## Components

### 1. Multi-stage pipeline
Each stage is its own module with a focused Gemini call using structured output
(`response_schema`) and `temperature=0`. Stage 3 generates DB → API → UI → Auth in
order so each layer is constrained by the previously generated layers.

### 2. Strict schema enforcement
Every inter-stage contract is a Pydantic model. The LLM is forced to emit JSON matching
the schema (constrained decoding); Pydantic then re-validates. Guarantees: valid JSON,
required fields present, type safety.

### 3. Validation + Repair engine (CORE)
Three validator layers, each producing `ValidationError{layer, code, path, message, repair_hint}`:

- **Structural** — JSON parses, Pydantic passes (invalid JSON, missing keys, wrong types).
- **Referential** — every UI field maps to an API field; every API field maps to a DB
  column; relations point to real tables; no hallucinated fields; auth roles exist.
- **Logical** — business rules resolve (e.g. "admins see analytics" ⟹ analytics page +
  endpoint + admin-only permission; "premium gating" ⟹ plan + gated features exist).

**Repair is intelligent, not brute retry:**
- Deterministically fixable errors (drop hallucinated field, add missing FK, coerce type,
  inject missing default) are fixed in code — no LLM call.
- Otherwise, regenerate **only the failing component**, passing it the specific errors and
  the constraints it must satisfy. Bounded retries per component; re-validate after each.
- Unresolvable → structured failure with reasons.

### 4. Determinism
`temperature=0`, constrained decoding, modular small prompts, and input-hash caching
(same prompt → same output; also reduces cost).

### 5. Execution awareness — built-in runtime renderer
An interpreter consumes the validated `AppConfig` and produces a real working preview:
in-memory DB seeded from `DBSchema`, live mock REST endpoints from `APISchema`, pages
rendered from `UISchema` (forms / tables / dashboard), and live auth (login, role switch,
premium gating). Proves the output runs with zero manual fixes.

### 6. Failure handling
Vague / conflicting / underspecified prompts are caught at the intent stage. The system
either returns clarification questions or proceeds with documented assumptions (toggle).
Conflicts (e.g. "no login" + "role-based access") are flagged explicitly.

### 7. Evaluation framework
`eval/dataset.json`: 10 real product prompts + 10 edge cases (vague / conflicting /
incomplete). Harness records success rate, retries per request, failure types, latency,
and token cost → markdown + JSON report.

### 8. Cost vs quality
Per-stage token tracking; fast mode (Flash everywhere) vs quality mode (Pro for the design
stage); caching impact — reported as actual numbers.

## Tech & layout

Python + FastAPI, Pydantic + jsonschema, Google Gemini (free tier, structured output),
vanilla HTML/JS UI, deployable free on Hugging Face Spaces (Dockerfile).
A heuristic **mock LLM** lets the system run with zero setup (no API key), doubling as a
deterministic baseline.

```
app/  main.py
      pipeline/{intent,design,schema_gen,refine,orchestrator}.py
      schemas/{intent,architecture,db,api,ui,auth,config}.py
      validation/{errors,structural,referential,logical}.py
      repair/repair.py
      llm/{gemini,mock,base}.py
      runtime/{interpreter,renderer}.py
      static/index.html
eval/{dataset.json, run_eval.py}
tests/
requirements.txt  Dockerfile  .env.example  README.md
```

## Deliverables → submission mapping
- Live URL → Hugging Face Spaces.
- Clean GitHub repo with clear pipeline separation.
- Metrics report (from eval harness) → material for the Loom video.
