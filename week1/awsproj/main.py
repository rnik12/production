import os
import json
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi_clerk_auth import (
    ClerkConfig,
    ClerkHTTPBearer,
    HTTPAuthorizationCredentials,
)
from openai import OpenAI

app = FastAPI()

# CORS (simple, since frontend is served from same origin in App Runner)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clerk configuration
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"), debug_mode=True)
clerk_guard = ClerkHTTPBearer(clerk_config)


class Visit(BaseModel):
    patient_name: str
    date_of_visit: str
    notes: str


SYSTEM_PROMPT = """
You are provided with notes written by a doctor from a patient's visit.
Your job is to summarize the visit for the doctor and provide an email.

You MUST reply with a single valid JSON object, and nothing else.
The JSON must have exactly these keys:

- "summary": markdown string summarizing the visit for the doctor's records
- "next_steps": markdown string listing next steps for the doctor (bullets or numbered list)
- "email": markdown string with a draft email to the patient in patient-friendly language

Example format (do NOT wrap in backticks, do NOT add extra text):

{
  "summary": "....",
  "next_steps": "....",
  "email": "...."
}
"""


def user_prompt_for(visit: Visit) -> str:
    return f"""Create the summary, next steps, and draft email for this visit:

Patient Name: {visit.patient_name}
Date of Visit: {visit.date_of_visit}

Notes:
{visit.notes}
"""


@app.post("/api/consultation")
def consultation_summary(
    visit: Visit,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    # User ID (available for logging / per-user limits, etc.)
    user_id = creds.decoded.get("sub")

    client = OpenAI()

    user_prompt = user_prompt_for(visit)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )

    content = completion.choices[0].message.content
    if not content:
        raise HTTPException(status_code=500, detail="Empty response from model")

    # Try to parse JSON from the model
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: if model messed up, at least return something
        data = {
            "summary": content,
            "next_steps": "",
            "email": "",
        }

    # Ensure keys exist
    summary = data.get("summary", "")
    next_steps = data.get("next_steps", "")
    email = data.get("email", "")

    return {
        "summary": summary,
        "next_steps": next_steps,
        "email": email,
    }


@app.get("/health")
def health_check():
    """Health check endpoint for App Runner."""
    return {"status": "ok"}


# ---- Static Next.js export (MUST be registered after API routes) ----
static_path = Path("static")
if static_path.exists():
    @app.get("/")
    async def serve_root():
        return FileResponse(static_path / "index.html")

    # Serve the rest of the Next.js export and assets
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
