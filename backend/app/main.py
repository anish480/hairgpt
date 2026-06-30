import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

from contextlib import asynccontextmanager

from app.config import settings
from app.db import close as close_db
from app.kiosk import (
    KIOSK_HTML,
    KIOSK_ADMIN_HTML,
    build_routine,
    save_kiosk_session,
    list_pending_sessions,
    mark_sampler_given,
    ensure_sampler_column,
)
from app.llm import classify_hair_photo, format_classification_summary
from app.orchestrator import chat
from app.session_logger import log_session
from app.throttle import check_rate_limit, check_token_budget, record_tokens

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ensure_sampler_column()
    yield
    await close_db()


app = FastAPI(title="MoxieBuddy Backend", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    history: list[dict] = Field(default_factory=list)
    device_info: dict | None = None
    ga_context: dict | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    history: list[dict]
    suggested_options: list[str] = Field(default_factory=list)
    routine: dict | None = None


class PhotoAnalysisResponse(BaseModel):
    classification: dict
    summary: str
    needs_retry: bool = False


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "project": settings.gcp_project_id,
        "location": settings.gcp_location,
        "shop": settings.shopify_shop,
    }


RATE_LIMIT_MSG = "You're sending messages a bit too fast! Take a breath and try again in a moment."
TOKEN_LIMIT_MSG = "We've had a great chat! For more help, reach out to us at support@moxiebeauty.in or start a new session."


@app.post("/chat")
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    session_id = req.session_id or str(uuid.uuid4())

    if not check_rate_limit(session_id):
        return ChatResponse(
            response=RATE_LIMIT_MSG,
            session_id=session_id,
            history=req.history,
            suggested_options=[],
        )

    if not await check_token_budget(session_id):
        return ChatResponse(
            response=TOKEN_LIMIT_MSG,
            session_id=session_id,
            history=req.history,
            suggested_options=[],
        )

    response_text, updated_history, options, routine_data, output_tokens = await chat(req.message, req.history)

    if output_tokens > 0:
        await record_tokens(session_id, output_tokens)

    photo_uploaded = any(
        "[User uploaded a hair photo" in (m.get("content") or "")
        for m in updated_history
    )

    await log_session(
        session_id=session_id,
        history=updated_history,
        device_info=req.device_info,
        ga_context=req.ga_context,
        routine_data=routine_data,
        photo_uploaded=photo_uploaded,
    )

    return ChatResponse(
        response=response_text,
        session_id=session_id,
        history=updated_history,
        suggested_options=options,
        routine=routine_data,
    )


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


logger = logging.getLogger(__name__)


@app.post("/photo/analyze")
async def analyze_photo(
    file: UploadFile = File(...),
    is_retry: bool = False,
) -> PhotoAnalysisResponse:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Unsupported image type: {file.content_type}. Use JPEG, PNG, WebP, or HEIC.")
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image too large. Max 10 MB.")
    try:
        classification = await classify_hair_photo(image_bytes, file.content_type, is_retry=is_retry)
    except Exception:
        logger.exception("classify_hair_photo failed")
        raise HTTPException(500, "Something went wrong analysing your photo. Please try again.")
    needs_retry = classification.get("needs_retry", False)
    summary = format_classification_summary(classification)
    return PhotoAnalysisResponse(classification=classification, summary=summary, needs_retry=needs_retry)


@app.get("/static/{filename:path}")
async def static_file(filename: str):
    path = STATIC_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path)


PREVIEW_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HairGPT Preview</title>
  <style>
    body{margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}
    .bar{position:fixed;top:0;left:0;right:0;background:#2D2D2D;color:#fff;padding:8px 16px;font-size:13px;z-index:9999999;display:flex;align-items:center;gap:12px;}
    .bar span{opacity:.7;}
    .bar button{background:#7EC8B7;border:none;color:#fff;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px;}
    .site{margin-top:40px;padding:40px 20px;max-width:1200px;margin:40px auto 0;}
    .site h1{color:#2D2D2D;margin-bottom:8px;}
    .site p{color:#666;max-width:600px;}
  </style>
</head>
<body>
  <div class="bar">
    <strong>HairGPT Preview</strong>
    <span>|</span>
    <span>Click the chat bubble to open the widget</span>
    <span>|</span>
    <button onclick="localStorage.removeItem('moxiebuddy_session');location.reload();">Reset Chat</button>
  </div>
  <div class="site">
    <h1>Moxie Beauty</h1>
    <p>This is a simulated storefront. The HairGPT chat widget floats on top of the page.</p>
  </div>
  <script>
    window.MoxieBuddyConfig = {
      apiBaseUrl: window.location.origin,
      shopContext: { pageType: "index", productHandle: "", customerId: "" }
    };
  </script>
  <script src="/static/moxiebuddy-widget.js"></script>
</body>
</html>
"""


@app.get("/preview", response_class=HTMLResponse)
async def preview():
    return PREVIEW_HTML


# ---------------------------------------------------------------------------
# Kiosk mode (Flipkart brand event)
# ---------------------------------------------------------------------------

class KioskSubmitRequest(BaseModel):
    name: str
    phone: str
    hair_analysis: dict
    primary_concern: str


class KioskSubmitResponse(BaseModel):
    session_id: str
    routine: dict


@app.get("/kiosk", response_class=HTMLResponse)
async def kiosk():
    return KIOSK_HTML


@app.post("/kiosk/submit")
async def kiosk_submit(req: KioskSubmitRequest) -> KioskSubmitResponse:
    routine = build_routine(req.hair_analysis, req.primary_concern)
    try:
        session_id = await save_kiosk_session(
            user_name=req.name,
            phone=req.phone,
            hair_analysis=req.hair_analysis,
            primary_concern=req.primary_concern,
            routine_name=routine["routine"],
            routine_steps=routine["steps"],
        )
    except Exception:
        logger.exception("Failed to save kiosk session")
        session_id = "unsaved"

    return KioskSubmitResponse(session_id=session_id, routine=routine)


# ---------------------------------------------------------------------------
# Kiosk Admin — sampler tracker
# ---------------------------------------------------------------------------

@app.get("/kioskadmin", response_class=HTMLResponse)
async def kiosk_admin():
    return KIOSK_ADMIN_HTML


@app.get("/kioskadmin/sessions")
async def kiosk_admin_sessions():
    sessions = await list_pending_sessions()
    return {"sessions": sessions}


class MarkGivenRequest(BaseModel):
    session_id: str


@app.post("/kioskadmin/mark-given")
async def kiosk_admin_mark_given(req: MarkGivenRequest):
    ok = await mark_sampler_given(req.session_id)
    if not ok:
        raise HTTPException(404, "Session not found or already marked")
    return {"status": "ok"}
