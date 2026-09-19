"""Authenticated single-GPU SemIf decision service; no generated answer tokens."""
import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from semif_phase1.core import load_causal_model, validate_row
from semif_phase1.direct import score

MODEL = "Qwen/Qwen3.5-4B"
REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
SOURCE_COMMIT = "b9cb32537e78be65f19abfcb1de8fc504b627d84"
api_key = Path(os.environ["SEMIF_KEY_FILE"]).read_text().strip()
if len(api_key) < 32:
    raise RuntimeError("A strong API key is required")
lock = asyncio.Lock()
engine = None


@asynccontextmanager
async def lifespan(app):
    global engine
    engine = await run_in_threadpool(load_causal_model, MODEL, REVISION)
    yield


app = FastAPI(title="SemIf decision API", version="0.1.0", lifespan=lifespan)


class Option(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=4096)


class Decision(BaseModel):
    id: str = Field(default="decision", min_length=1, max_length=128)
    state: str | dict | list
    question: str = Field(min_length=1, max_length=4096)
    options: list[Option] = Field(min_length=2, max_length=16)


@app.get("/health")
def health():
    return {"status": "ready", "model": MODEL, "revision": REVISION,
            "source_commit": SOURCE_COMMIT, "mode": "direct", "max_tokens": 4096}


@app.post("/v1/decide")
async def decide(body: Decision, authorization: str = Header(default="")):
    if not hmac.compare_digest(authorization, "Bearer " + api_key):
        raise HTTPException(401, "Invalid bearer token")
    row = body.model_dump()
    if len(json.dumps(row, ensure_ascii=False).encode()) > 65536:
        raise HTTPException(413, "Request exceeds 64 KiB")
    try:
        validate_row(row)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if lock.locked():
        raise HTTPException(429, "GPU busy; retry later", headers={"Retry-After": "1"})
    async with lock:
        try:
            result = await run_in_threadpool(score, *engine[:2], row, engine[2], 4096)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
    best = max(range(len(result["probabilities"])), key=result["probabilities"].__getitem__)
    return {**result, "choice": result["option_ids"][best], "source_commit": SOURCE_COMMIT}
