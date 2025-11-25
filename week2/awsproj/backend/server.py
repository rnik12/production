from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent          # /app/backend
MEMORY_DIR = BASE_DIR / "memory"
STATIC_DIR = BASE_DIR.parent / "static"             # /app/static

MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def load_personality() -> str:
    p = BASE_DIR / "me.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return "You are a helpful assistant."

PERSONALITY = load_personality()

# Keep a reasonable context window (last N messages)
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))

# --- FastAPI ---
app = FastAPI(title="Twin (App Runner)")

# Local dev convenience (in production we run same-origin so CORS is irrelevant)
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str

# --- Memory ---
def _mem_path(session_id: str) -> Path:
    return MEMORY_DIR / f"{session_id}.json"

def load_conversation(session_id: str) -> List[Dict]:
    p = _mem_path(session_id)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_conversation(session_id: str, messages: List[Dict]) -> None:
    p = _mem_path(session_id)
    p.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

# --- Routes ---
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL,
        "openai_key_set": bool(OPENAI_API_KEY),
        "time": datetime.utcnow().isoformat() + "Z",
    }

@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not set in the environment.",
        )

    session_id = payload.session_id or str(uuid.uuid4())
    history = load_conversation(session_id)

    # build messages to LLM
    msgs: List[Dict[str, str]] = [{"role": "system", "content": PERSONALITY}]

    # add recent history (already stored as role/content)
    for m in history[-MAX_HISTORY_MESSAGES:]:
        if "role" in m and "content" in m:
            msgs.append({"role": m["role"], "content": m["content"]})

    # current user message
    msgs.append({"role": "user", "content": payload.message})

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=msgs,
        )
        answer = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    # persist history
    history.append({"role": "user", "content": payload.message, "timestamp": datetime.utcnow().isoformat() + "Z"})
    history.append({"role": "assistant", "content": answer, "timestamp": datetime.utcnow().isoformat() + "Z"})
    save_conversation(session_id, history)

    return ChatResponse(response=answer, session_id=session_id)

# Serve the static Next.js export (single-service deployment)
# IMPORTANT: mount AFTER /api routes so /api/* keeps working.
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:
    # If someone runs backend alone without building frontend
    @app.get("/")
    async def root():
        return {"message": "Backend running. Build frontend to enable UI at /"}
