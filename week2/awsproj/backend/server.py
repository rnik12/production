from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

load_dotenv(override=True)

# ----------------------------
# Logging (stdout for App Runner)
# ----------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("twin")

BASE_DIR = Path(__file__).resolve().parent          # /app/backend
MEMORY_DIR = BASE_DIR / "memory"
STATIC_DIR = BASE_DIR.parent / "static"             # /app/static

MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# --- Bedrock (Nova) ---
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0").strip()
DEFAULT_AWS_REGION = os.getenv("DEFAULT_AWS_REGION", "us-east-1").strip()

bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name=DEFAULT_AWS_REGION,
)

def load_personality() -> str:
    p = BASE_DIR / "me.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return "You are a helpful assistant."

PERSONALITY = load_personality()
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))

# --- FastAPI ---
app = FastAPI(title="Twin (App Runner)")

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # NOTE: currently overrides `origins` above
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Request logging + request_id
# ----------------------------
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id

    start = time.time()
    logger.info(
        "request.start request_id=%s method=%s path=%s client=%s",
        request_id,
        request.method,
        request.url.path,
        request.client.host if request.client else None,
    )
    try:
        response = await call_next(request)
    except Exception:
        # Full stack trace in logs (critical for 500 diagnosis)
        logger.exception("request.crash request_id=%s path=%s", request_id, request.url.path)
        raise
    finally:
        dur_ms = int((time.time() - start) * 1000)

    response.headers["x-request-id"] = request_id
    logger.info(
        "request.end request_id=%s status=%s duration_ms=%s",
        request_id,
        getattr(response, "status_code", None),
        dur_ms,
    )
    return response

# ----------------------------
# Global exception handler (logs stack trace)
# ----------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("unhandled_exception request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "request_id": request_id},
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
        logger.exception("memory.load_failed session_id=%s path=%s", session_id, str(p))
        return []

def save_conversation(session_id: str, messages: List[Dict]) -> None:
    p = _mem_path(session_id)
    try:
        p.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("memory.save_failed session_id=%s path=%s", session_id, str(p))

def call_bedrock(history: List[Dict], user_message: str, request_id: str) -> str:
    """
    Bedrock Converse API format.
    We include PERSONALITY as a "System: ..." first message.
    """
    messages = [
        {"role": "user", "content": [{"text": f"System: {PERSONALITY}"}]},
    ]

    for m in history[-MAX_HISTORY_MESSAGES:]:
        if "role" in m and "content" in m and m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": [{"text": m["content"]}]})

    messages.append({"role": "user", "content": [{"text": user_message}]})

    logger.info(
        "bedrock.request request_id=%s model=%s region=%s history_count=%s user_msg_len=%s",
        request_id,
        BEDROCK_MODEL_ID,
        DEFAULT_AWS_REGION,
        len(history),
        len(user_message),
    )

    try:
        resp = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=messages,
            inferenceConfig={"maxTokens": 1200, "temperature": 0.7, "topP": 0.9},
        )

        # Helpful trace details without dumping full content
        rm = resp.get("ResponseMetadata", {})
        logger.info(
            "bedrock.response request_id=%s http_status=%s aws_request_id=%s",
            request_id,
            rm.get("HTTPStatusCode"),
            rm.get("RequestId"),
        )

        return resp["output"]["message"]["content"][0]["text"].strip()

    except ClientError as e:
        err = e.response.get("Error", {})
        meta = e.response.get("ResponseMetadata", {})
        code = err.get("Code", "Unknown")
        msg = err.get("Message", str(e))

        logger.error(
            "bedrock.client_error request_id=%s code=%s message=%s http_status=%s aws_request_id=%s model=%s region=%s",
            request_id,
            code,
            msg,
            meta.get("HTTPStatusCode"),
            meta.get("RequestId"),
            BEDROCK_MODEL_ID,
            DEFAULT_AWS_REGION,
        )
        logger.exception("bedrock.client_error_stack request_id=%s", request_id)

        if code in ("AccessDeniedException", "UnauthorizedException"):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Bedrock access denied. Check IAM permissions + model access. "
                    f"model={BEDROCK_MODEL_ID} region={DEFAULT_AWS_REGION}"
                ),
            )
        if code in ("ValidationException",):
            raise HTTPException(
                status_code=400,
                detail=f"Bedrock validation error (check modelId/message format): {msg}",
            )
        raise HTTPException(status_code=500, detail=f"Bedrock error: {code}")

    except Exception:
        logger.exception(
            "bedrock.unknown_error request_id=%s model=%s region=%s",
            request_id,
            BEDROCK_MODEL_ID,
            DEFAULT_AWS_REGION,
        )
        raise HTTPException(status_code=500, detail="Bedrock error")

# --- Routes ---
@app.on_event("startup")
async def startup_log():
    logger.info(
        "startup bedrock_model=%s aws_region=%s memory_dir=%s static_dir=%s log_level=%s",
        BEDROCK_MODEL_ID,
        DEFAULT_AWS_REGION,
        str(MEMORY_DIR),
        str(STATIC_DIR),
        LOG_LEVEL,
    )
    # Optional identity sanity check (won't crash app if blocked)
    try:
        sts = boto3.client("sts", region_name=DEFAULT_AWS_REGION)
        ident = sts.get_caller_identity()
        logger.info(
            "startup.aws_identity account=%s arn=%s user_id=%s",
            ident.get("Account"),
            ident.get("Arn"),
            ident.get("UserId"),
        )
    except Exception:
        logger.warning("startup.aws_identity_unavailable (sts may be blocked or unpermitted)", exc_info=True)

@app.get("/api/health")
async def health(request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    return {
        "status": "ok",
        "bedrock_model": BEDROCK_MODEL_ID,
        "aws_region": DEFAULT_AWS_REGION,
        "time": datetime.utcnow().isoformat() + "Z",
        "request_id": request_id,
    }

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    session_id = payload.session_id or str(uuid.uuid4())

    logger.info(
        "chat.start request_id=%s session_id=%s msg_len=%s",
        request_id,
        session_id,
        len(payload.message),
    )

    history = load_conversation(session_id)
    answer = call_bedrock(history, payload.message, request_id=request_id)

    history.append({"role": "user", "content": payload.message, "timestamp": datetime.utcnow().isoformat() + "Z"})
    history.append({"role": "assistant", "content": answer, "timestamp": datetime.utcnow().isoformat() + "Z"})
    save_conversation(session_id, history)

    logger.info(
        "chat.end request_id=%s session_id=%s answer_len=%s",
        request_id,
        session_id,
        len(answer),
    )

    return ChatResponse(response=answer, session_id=session_id)

# Serve the static Next.js export (single-service deployment)
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return {"message": "Backend running. Build frontend to enable UI at /"}
