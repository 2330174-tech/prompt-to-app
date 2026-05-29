"""FastAPI app: the generator UI, the generation API, and the live runtime preview."""
from __future__ import annotations

import os
import uuid
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.pipeline import generate
from app.runtime import Interpreter, render

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY") or ""
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

app = FastAPI(title="PromptCompiler")

# In-memory store of generated apps for the live preview. Fine for a demo.
STORE: Dict[str, Tuple[object, Interpreter]] = {}

HERE = os.path.dirname(__file__)


class GenerateRequest(BaseModel):
    prompt: str
    mode: str = "assume"  # assume | clarify


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(HERE, "static", "index.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/health")
def health():
    return {"ok": True, "mode": "gemini" if API_KEY else "mock", "model": MODEL}


@app.post("/api/generate")
def api_generate(req: GenerateRequest):
    result = generate(req.prompt, mode=req.mode, api_key=API_KEY or None, model=MODEL)
    cid = None
    if result.status == "ok" and result.config is not None:
        cid = uuid.uuid4().hex[:12]
        STORE[cid] = (result.config, Interpreter(result.config))
    payload = result.model_dump()
    payload["cid"] = cid
    payload["llm_mode"] = "gemini" if API_KEY else "mock"
    return JSONResponse(payload)


@app.get("/preview/{cid}", response_class=HTMLResponse)
def preview(cid: str, page: Optional[str] = None, role: Optional[str] = None,
            plan: str = "free"):
    if cid not in STORE:
        return HTMLResponse("<h3>Preview expired. Generate again.</h3>", status_code=404)
    config, interp = STORE[cid]
    if role is None:
        role = config.auth.roles[0] if config.auth.roles else None
    page = page or (config.ui.pages[0].path if config.ui.pages else "/")
    return render(config, interp, cid, page, role, plan)


@app.post("/preview/{cid}/run")
async def preview_run(cid: str, request: Request):
    if cid not in STORE:
        return RedirectResponse("/", status_code=303)
    _, interp = STORE[cid]
    form = await request.form()
    data = dict(form)
    method = data.pop("_method", "POST")
    path = data.pop("_path", "")
    page = data.pop("_page", "/")
    role = data.pop("_role", "") or None
    plan = data.pop("_plan", "free")
    interp.handle(method, path, payload=data, role=role)
    return RedirectResponse(
        f"/preview/{cid}?page={page}&role={role or ''}&plan={plan}", status_code=303)


# Mount static last so it doesn't shadow routes.
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
