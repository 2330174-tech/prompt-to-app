# 🧩 PromptCompiler — a compiler for software generation

Natural language → **multi-stage pipeline** → strict **validated config** (UI / API / DB /
Auth / business logic) → a **running app** via a built-in runtime.

This is built as a *compiler*, not a prompt: each stage is a pass with a strict typed
contract, and a validation + repair engine guarantees the output is internally consistent
and executable. It runs **100% free** — Google Gemini's free tier, or a built-in
deterministic **mock mode** that needs no API key at all.

> **🔗 Live demo:** https://promptcompiler.onrender.com  ·  **Source:** https://github.com/2330174-tech/prompt-to-app
>
> The live demo runs in free mock mode by default (no API key needed). On Render's free
> tier the first request after idle can take ~50s to wake up.

```
prompt ──▶ Intent ──▶ System Design ──▶ Schema Gen (DB→API→UI→Auth) ──▶ Refine/Link
                                                                          │
                                              ┌───────────────────────────┘
                                              ▼
                              Validate (structural · referential · logical)
                                              │  errors
                                              ▼
                              Repair (deterministic fixes + targeted re-gen)
                                              │  clean
                                              ▼
                              Runtime  ──▶  live working app preview
```

## Quick start (zero setup — runs in mock mode, no API key)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://localhost:8000>, type a prompt (e.g. *"Build a CRM with login, contacts,
dashboard, role-based access, and premium plan with payments. Admins can see analytics."*),
and click **Compile**. You'll see the generated config per layer, the validation/repair
metrics, and a **live preview** of the app actually running (switch role/plan to watch auth
and premium gating work).

## Use the real LLM (Google Gemini — free tier)

1. Get a free key at <https://aistudio.google.com/app/apikey>.
2. `cp .env.example .env` and set `GEMINI_API_KEY=...`
3. Run as above. The header shows whether it's using Gemini or the mock.

## Run the tests

```bash
pytest -q
```

## Run the evaluation harness (success rate / repairs / latency / cost)

```bash
python -m eval.run_eval
# writes eval/report/report.md and eval/report/results.json
```

The dataset has **10 real product prompts + 10 edge cases** (vague, conflicting,
incomplete). The harness checks each config also **boots in the runtime**.

## Deployment (free)

Deployed on **Render's free tier** — live at <https://promptcompiler.onrender.com>.

The repo ships a `render.yaml` blueprint, so deploying is one click:

1. Push the repo to GitHub (already done: <https://github.com/2330174-tech/prompt-to-app>).
2. On [render.com](https://render.com): **New → Blueprint** → pick the repo → **Apply**.
   Render reads `render.yaml` and configures the web service automatically.
3. (Optional) add `GEMINI_API_KEY` under the service's **Environment** tab to use Gemini
   instead of mock mode. No key → it runs the deterministic engine, so the URL works either way.

Python is pinned to 3.12 (`.python-version`) because Render's default 3.14 has no
prebuilt `pydantic-core` wheel yet. A `Dockerfile` is also included for Hugging Face
Spaces / Railway / any container host.

## Data & storage

There is **no database** — state is in-memory and intentionally ephemeral (this is a
compiler demo, not a hosting platform):

- Generated configs + their runtimes live in a dict in [app/main.py](app/main.py), keyed by a `cid`.
- Each generated app's data is in-memory in the [Interpreter](app/runtime/interpreter.py),
  seeded with sample rows; live CRUD mutates it in place.
- The LLM cache (for determinism + cost) is per-process.

A restart (or Render's idle spin-down) resets everything — regenerate to get a fresh `cid`.
Only the eval report is written to disk.

## How it satisfies the task

| Requirement | Where |
|---|---|
| Multi-stage pipeline (not a single prompt) | [app/pipeline/](app/pipeline/) — `intent → design → schema_gen → refine` |
| Strict schema enforcement | Pydantic contracts in [app/schemas/](app/schemas/) + JSON mode |
| Validation + repair engine | [app/validation/](app/validation/) (3 layers) + [app/repair/repair.py](app/repair/repair.py) |
| Intelligent repair (not brute retry) | deterministic code fixes + targeted component re-gen |
| Determinism | `temperature=0`, constrained JSON, modular prompts, input-hash caching |
| Execution awareness | [app/runtime/](app/runtime/) — in-memory DB + live API + rendered UI with auth |
| Failure handling | vague/conflict detection in intent; clarify-or-assume modes |
| Evaluation framework | [eval/](eval/) — 20 prompts, real metrics |
| Cost vs quality | per-stage token tracking; fast (Flash) vs quality (Pro design stage) modes |

## Project layout

```
app/
  pipeline/    intent.py · design.py · schema_gen.py · refine.py · orchestrator.py · heuristics.py
  schemas/     intent · architecture · db · api · ui · auth · config  (Pydantic contracts)
  validation/  errors · structural · referential · logical
  repair/      repair.py
  llm/         base · gemini · mock   (Gemini client + deterministic fallback)
  runtime/     interpreter.py (in-memory DB + API) · renderer.py (live HTML preview)
  static/      index.html   (generator UI)
  main.py      FastAPI app
eval/          dataset.json · run_eval.py
tests/         test_pipeline.py
docs/superpowers/specs/   design document
```

See [docs/superpowers/specs/2026-05-29-promptcompiler-design.md](docs/superpowers/specs/2026-05-29-promptcompiler-design.md)
for the full design rationale.
