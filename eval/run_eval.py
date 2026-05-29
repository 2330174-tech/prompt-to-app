"""Evaluation harness.

Runs the dataset (10 real prompts + 10 edge cases) through the compiler and reports
success rate, repairs/request, failure types, latency, and token cost. Also checks
execution: every successful config must actually boot in the runtime and serve its first
GET endpoint. Writes JSON + Markdown to eval/report/.

Usage:
    python -m eval.run_eval            # mock mode (no key) or Gemini if GEMINI_API_KEY set
"""
from __future__ import annotations

import json
import os
import statistics
import time
from collections import Counter

from dotenv import load_dotenv

from app.pipeline import generate
from app.runtime import Interpreter

load_dotenv()
HERE = os.path.dirname(__file__)
API_KEY = os.getenv("GEMINI_API_KEY") or None
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def _executes(config) -> bool:
    """Execution-awareness check: the config must boot and serve a real GET."""
    try:
        interp = Interpreter(config)
        get_ep = next((e for e in config.api.endpoints if e.method == "GET"), None)
        if get_ep is None:
            return False
        status, _ = interp.handle("GET", get_ep.path,
                                  role=(config.auth.roles[0] if config.auth.roles else None))
        return status in (200, 403)  # 403 = auth correctly enforced, still "runs"
    except Exception:
        return False


def run_case(prompt: str, mode: str) -> dict:
    t0 = time.time()
    res = generate(prompt, mode=mode, api_key=API_KEY, model=MODEL)
    wall = (time.time() - t0) * 1000.0
    executes = res.status == "ok" and res.config is not None and _executes(res.config)
    # "success": produced a usable, executable config OR correctly asked to clarify.
    success = executes or res.status == "needs_clarification"
    return {
        "prompt": prompt,
        "status": res.status,
        "executes": executes,
        "success": success,
        "repairs": res.total_retries,
        "latency_ms": round(wall, 1),
        "tokens": res.total_input_tokens + res.total_output_tokens,
        "cost_usd": res.est_cost_usd,
        "failure_types": res.failure_types,
    }


def main():
    with open(os.path.join(HERE, "dataset.json")) as f:
        data = json.load(f)

    results = []
    for p in data["real"]:
        results.append({"bucket": "real", **run_case(p, mode="assume")})
    for p in data["edge"]:
        # Edge cases run in clarify mode so vague prompts can resolve by asking.
        results.append({"bucket": "edge", **run_case(p, mode="clarify")})

    n = len(results)
    succ = sum(r["success"] for r in results)
    execs = sum(r["executes"] for r in results)
    failures = Counter()
    for r in results:
        for ft in r["failure_types"]:
            failures[ft] += 1

    summary = {
        "total": n,
        "success_rate": round(100 * succ / n, 1),
        "executable_rate": round(100 * execs / n, 1),
        "avg_repairs": round(statistics.mean(r["repairs"] for r in results), 2),
        "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in results), 1),
        "total_tokens": sum(r["tokens"] for r in results),
        "total_cost_usd": round(sum(r["cost_usd"] for r in results), 6),
        "failure_types": dict(failures),
        "mode": "gemini" if API_KEY else "mock",
    }

    os.makedirs(os.path.join(HERE, "report"), exist_ok=True)
    with open(os.path.join(HERE, "report", "results.json"), "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)

    md = ["# PromptCompiler — Evaluation Report", "",
          f"LLM mode: **{summary['mode']}**  ·  cases: **{n}**", "",
          "## Summary", "",
          f"- Success rate: **{summary['success_rate']}%**",
          f"- Executable rate: **{summary['executable_rate']}%**",
          f"- Avg repairs/request: **{summary['avg_repairs']}**",
          f"- Avg latency: **{summary['avg_latency_ms']} ms**",
          f"- Total tokens: **{summary['total_tokens']}**  ·  est cost: **${summary['total_cost_usd']}**",
          f"- Failure types: `{summary['failure_types']}`", "",
          "## Per-case", "",
          "| bucket | status | executes | repairs | latency(ms) | prompt |",
          "|---|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['bucket']} | {r['status']} | {'✅' if r['executes'] else '—'} "
                  f"| {r['repairs']} | {r['latency_ms']} | {r['prompt'][:60]} |")
    with open(os.path.join(HERE, "report", "report.md"), "w") as f:
        f.write("\n".join(md))

    print(json.dumps(summary, indent=2))
    print("\nWrote eval/report/report.md and eval/report/results.json")


if __name__ == "__main__":
    main()
